import os
import base64
import hashlib
import html
import json
import re
import sqlite3
import socket
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURAÇÕES
# ============================================================

WP_URL = os.getenv("WP_URL", "").strip().rstrip("/")
WP_USERNAME = os.getenv("WP_USERNAME", "").strip()
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "").strip()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Modelo Gemini estável
GEMINI_MODEL = "gemini-2.5-flash"

# IMPORTANTE:
# Primeiro vamos testar como RASCUNHO.
# Depois que confirmarmos que tudo funciona,
# mudaremos para "publish".
WP_POST_STATUS = "draft"

# Quantidade máxima de notícias por execução
ARTICLES_PER_RUN = 3

# Fonte de notícias
RSS_FEEDS = [
    ("Gospel", "https://fuxicogospel.com.br")
]

# Banco local para controlar notícias já processadas
DB_PATH = "data/news.db"

TIMEOUT = 30

socket.setdefaulttimeout(30)

# Durante o teste, não bloqueia notícias já vistas.
# Depois do teste, podemos mudar para False.
TEST_MODE = True


# ============================================================
# VALIDAÇÃO DAS CONFIGURAÇÕES
# ============================================================

def validate_config():
    print("[CHECK] Verificando configurações...")

    missing = []

    if not WP_URL:
        missing.append("WP_URL")

    if not WP_USERNAME:
        missing.append("WP_USERNAME")

    if not WP_APP_PASSWORD:
        missing.append("WP_APP_PASSWORD")

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if missing:
        raise RuntimeError(
            "Secrets ausentes no GitHub: " + ", ".join(missing)
        )

    print("[CHECK] WP_URL: configurado")
    print("[CHECK] WP_USERNAME: configurado")
    print("[CHECK] WP_APP_PASSWORD: configurado")
    print("[CHECK] GEMINI_API_KEY: configurado")
    print("[CHECK] Configuração OK.")


# ============================================================
# BANCO DE DADOS
# ============================================================

def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed (
            fingerprint TEXT PRIMARY KEY,
            source_url TEXT,
            title TEXT,
            created_at TEXT,
            wp_post_id INTEGER
        )
        """
    )

    conn.commit()

    return conn


def fingerprint(title, url):
    raw = (
        re.sub(r"\W+", " ", (title or "").lower()).strip()
        + "|"
        + (url or "")
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def already_seen(conn, fp):
    if TEST_MODE:
        return False

    result = conn.execute(
        "SELECT 1 FROM processed WHERE fingerprint = ?",
        (fp,)
    ).fetchone()

    return result is not None


def mark_seen(conn, fp, item, post_id=None):
    conn.execute(
        """
        INSERT OR REPLACE INTO processed
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            fp,
            item["url"],
            item["title"],
            datetime.now(timezone.utc).isoformat(),
            post_id
        )
    )

    conn.commit()


# ============================================================
# LIMPEZA DE TEXTO
# ============================================================

def clean_text(value):
    if not value:
        return ""

    soup = BeautifulSoup(
        value,
        "html.parser"
    )

    text = soup.get_text(" ")

    text = html.unescape(text)

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# COLETA DAS NOTÍCIAS
# ============================================================

def collect():
    items = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120 Safari/537.36"
        )
    }

    for category, feed_url in RSS_FEEDS:

        try:
            print(
                f"[PROCESS] Lendo fonte: {feed_url}"
            )

            response = requests.get(
                feed_url,
                timeout=TIMEOUT,
                headers=headers
            )

            print(
                "[PROCESS] Status da fonte:",
                response.status_code
            )

            if response.status_code >= 400:
                print(
                    "[WARN] Fonte retornou erro:",
                    response.status_code
                )
                continue

            feed = feedparser.parse(
                response.content
            )

            print(
                "[PROCESS] Notícias encontradas:",
                len(feed.entries)
            )

            for entry in feed.entries[:12]:

                title = clean_text(
                    entry.get("title", "")
                )

                url = entry.get(
                    "link",
                    ""
                )

                summary = clean_text(
                    entry.get("summary", "")
                    or entry.get("description", "")
                )

                published = (
                    entry.get("published", "")
                    or entry.get("updated", "")
                )

                if title and url:

                    items.append(
                        {
                            "category": category,
                            "title": title,
                            "url": url,
                            "summary": summary[:4000],
                            "published": published
                        }
                    )

        except Exception as exc:

            print(
                f"[ERROR] Falha ao ler fonte {feed_url}: {exc}"
            )

    return items


# ============================================================
# EXTRAÇÃO DO TEXTO DA NOTÍCIA
# ============================================================

def page_extract(url):

    try:

        print(
            f"[PROCESS] Abrindo notícia: {url}"
        )

        response = requests.get(
            url,
            timeout=TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                )
            }
        )

        print(
            "[PROCESS] Status da página:",
            response.status_code
        )

        if response.status_code >= 400:

            print(
                "[WARN] Página retornou erro."
            )

            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for tag in soup(
            [
                "script",
                "style",
                "noscript",
                "svg",
                "nav",
                "footer",
                "header"
            ]
        ):
            tag.decompose()

        target = (
            soup.find("article")
            or soup.find("main")
            or soup.body
        )

        if not target:
            print(
                "[WARN] Não foi encontrado conteúdo da notícia."
            )
            return ""

        text = target.get_text(
            " ",
            strip=True
        )

        text = re.sub(
            r"\s+",
            " ",
            text
        )

        text = text.strip()

        print(
            "[PROCESS] Texto extraído:",
            len(text),
            "caracteres"
        )

        return text[:12000]

    except Exception as exc:

        print(
            f"[ERROR] Falha ao extrair página: {exc}"
        )

        return ""


# ============================================================
# GEMINI
# ============================================================

def gemini(prompt):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY não foi configurada."
        )

    endpoint = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }

    print(
        "[GEMINI] Enviando solicitação..."
    )

    response = requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=90
    )

    print(
        "[GEMINI] Status:",
        response.status_code
    )

    if response.status_code >= 400:

        print(
            "[GEMINI] Erro:",
            response.text[:3000]
        )

        response.raise_for_status()

    data = response.json()

    try:

        text_response = (
            data["candidates"][0]
            ["content"]["parts"][0]
            ["text"]
            .strip()
        )

    except (
        KeyError,
        IndexError,
        TypeError
    ):

        print(
            "[GEMINI] Resposta inesperada:",
            json.dumps(
                data,
                ensure_ascii=False
            )[:5000]
        )

        raise ValueError(
            "Estrutura de resposta inesperada do Gemini."
        )

    # Remove possíveis blocos Markdown
    text_response = re.sub(
        r"^```json\s*",
        "",
        text_response,
        flags=re.IGNORECASE
    )

    text_response = re.sub(
        r"^```\s*",
        "",
        text_response,
        flags=re.IGNORECASE
    )

    text_response = re.sub(
        r"\s*```$",
        "",
        text_response,
        flags=re.IGNORECASE
    )

    text_response = text_response.strip()

    try:

        article = json.loads(
            text_response
        )

    except json.JSONDecodeError as exc:

        print(
            "[GEMINI] JSON recebido:",
            text_response[:5000]
        )

        raise ValueError(
            "Gemini não retornou JSON válido."
        ) from exc

    return article


# ============================================================
# GERAÇÃO DA MATÉRIA
# ============================================================

def generate_article(
    item,
    source_text
):

    material = (
        f"FONTE PRINCIPAL\n"
        f"Título: {item['title']}\n"
        f"URL: {item['url']}\n"
        f"Categoria: {item['category']}\n"
        f"Resumo RSS: {item['summary']}\n\n"
        f"TEXTO DA PÁGINA:\n"
        f"{source_text[:12000]}"
    )

    prompt = f"""
Você é editor jornalístico do portal Rádio Luz Gospel.

Sua tarefa é produzir uma reportagem ORIGINAL em português
do Brasil com base SOMENTE nos fatos presentes no material.

REGRAS OBRIGATÓRIAS:

- Não invente fatos.
- Não invente nomes.
- Não invente números.
- Não invente datas.
- Não invente declarações.
- Não invente acontecimentos.
- Não copie frases longas da fonte.
- Não faça simples substituição de sinônimos.
- Escreva uma reportagem jornalística original.
- Preserve corretamente a atribuição das informações.
- Se não houver informações suficientes para uma reportagem confiável,
  retorne "publish": false.
- Crie um título jornalístico próprio.
- O texto deve ter aproximadamente 400 a 650 palavras.
- O conteúdo deve ser HTML simples.
- Não utilize Markdown.
- Utilize parágrafos HTML <p>.
- Pode utilizar <strong> quando necessário.
- Inclua ao final uma seção chamada "Fontes consultadas".
- A fonte original deve ser indicada.
- Não inclua comentários fora do JSON.

RETORNE SOMENTE JSON VÁLIDO:

{{
  "publish": true,
  "title": "Título da reportagem",
  "excerpt": "Resumo curto da reportagem",
  "content": "<p>Primeiro parágrafo...</p><p>Segundo parágrafo...</p>",
  "tags": ["Gospel", "Notícias", "Música"],
  "category": "Gospel"
}}

MATERIAL:

{material}
"""

    return gemini(prompt)


# ============================================================
# WORDPRESS
# ============================================================

def wp_auth():

    token = base64.b64encode(
        (
            f"{WP_USERNAME}:{WP_APP_PASSWORD}"
        ).encode("utf-8")
    ).decode("ascii")

    return {
        "Authorization": f"Basic {token}"
    }


def wp_get(
    path,
    params=None
):

    url = (
        f"{WP_URL}/wp-json/wp/v2/{path}"
    )

    response = requests.get(
        url,
        headers=wp_auth(),
        params=params,
        timeout=TIMEOUT
    )

    if response.status_code >= 400:

        print(
            "[WORDPRESS] GET erro:",
            response.status_code,
            response.text[:2000]
        )

        response.raise_for_status()

    return response.json()


def wp_post(
    path,
    payload
):

    url = (
        f"{WP_URL}/wp-json/wp/v2/{path}"
    )

    headers = {
        **wp_auth(),
        "Content-Type": "application/json"
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=TIMEOUT
    )

    print(
        "[WORDPRESS] POST",
        path,
        "Status:",
        response.status_code
    )

    if response.status_code >= 400:

        print(
            "[WORDPRESS] Erro:",
            response.text[:3000]
        )

        response.raise_for_status()

    return response.json()


def test_wordpress_connection():

    print(
        "[WORDPRESS] Testando conexão..."
    )

    data = wp_get(
        "users/me"
    )

    print(
        "[WORDPRESS] Usuário autenticado:",
        data.get("name", "OK")
    )

    return True


# ============================================================
# CATEGORIAS
# ============================================================

def get_or_create_category(
    name
):

    name = (
        str(name or "Gospel")
        .strip()
    )

    try:

        found = wp_get(
            "categories",
            {
                "search": name,
                "per_page": 20
            }
        )

        for category in found:

            if (
                category["name"].lower()
                == name.lower()
            ):
                return category["id"]

        created = wp_post(
            "categories",
            {
                "name": name
            }
        )

        return created["id"]

    except Exception as exc:

        print(
            "[WARN] Não foi possível criar categoria:",
            exc
        )

        # Categoria padrão do WordPress
        return 1


# ============================================================
# TAGS
# ============================================================

def get_or_create_tags(
    names
):

    ids = []

    if not isinstance(
        names,
        list
    ):
        return ids

    for name in names[:8]:

        name = re.sub(
            r"\s+",
            " ",
            str(name)
        ).strip()

        if not name:
            continue

        try:

            found = wp_get(
                "tags",
                {
                    "search": name,
                    "per_page": 20
                }
            )

            exact = next(
                (
                    tag
                    for tag in found
                    if tag["name"].lower()
                    == name.lower()
                ),
                None
            )

            if exact:

                ids.append(
                    exact["id"]
                )

            else:

                created = wp_post(
                    "tags",
                    {
                        "name": name
                    }
                )

                ids.append(
                    created["id"]
                )

        except Exception as exc:

            print(
                "[WARN] Não foi possível criar tag:",
                name,
                exc
            )

    return ids


# ============================================================
# PUBLICAÇÃO NO WORDPRESS
# ============================================================

def publish_article(
    article,
    item
):

    if not article.get(
        "publish",
        True
    ):

        print(
            "[INFO] Gemini marcou a notícia como não publicável."
        )

        return None

    title = str(
        article.get(
            "title",
            ""
        )
    ).strip()

    content = str(
        article.get(
            "content",
            ""
        )
    ).strip()

    excerpt = str(
        article.get(
            "excerpt",
            ""
        )
    ).strip()

    if not title:

        raise ValueError(
            "Gemini não retornou título."
        )

    if not content:

        raise ValueError(
            "Gemini não retornou conteúdo."
        )

    category_name = (
        article.get(
            "category"
        )
        or item["category"]
    )

    category_id = get_or_create_category(
        category_name
    )

    tag_ids = get_or_create_tags(
        article.get(
            "tags",
            []
        )
    )

    source_url = html.escape(
        item["url"],
        quote=True
    )

    content += (
        "<p><strong>Fonte de apuração:</strong> "
        f'<a href="{source_url}" '
        'rel="nofollow noopener" '
        'target="_blank">'
        f"{source_url}"
        "</a></p>"
    )

    payload = {
        "title": title,
        "content": content,
        "excerpt": excerpt,
        "status": WP_POST_STATUS,
        "categories": [
            category_id
        ],
        "tags": tag_ids
    }

    print(
        "[WORDPRESS] Enviando notícia:",
        title
    )

    result = wp_post(
        "posts",
        payload
    )

    post_id = result.get(
        "id"
    )

    post_status = result.get(
        "status"
    )

    post_link = result.get(
        "link",
        ""
    )

    print(
        "[SUCCESS] Notícia enviada ao WordPress!"
    )

    print(
        "[SUCCESS] ID:",
        post_id
    )

    print(
        "[SUCCESS] Status:",
        post_status
    )

    if post_link:
        print(
            "[SUCCESS] Link:",
            post_link
        )

    return result


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print(
        "=================================================="
    )

    print(
        "[START] Rádio Luz Gospel - Robô de Notícias"
    )

    print(
        "=================================================="
    )

    try:

        validate_config()

        test_wordpress_connection()

    except Exception as exc:

        print(
            "[FATAL] Falha na configuração:",
            exc
        )

        raise

    conn = db()

    collected_items = collect()

    print(
        "[INFO] Total de notícias coletadas:",
        len(collected_items)
    )

    if not collected_items:

        print(
            "[INFO] Nenhuma notícia encontrada."
        )

        return

    candidates = []

    for item in collected_items:

        fp = fingerprint(
            item["title"],
            item["url"]
        )

        if not already_seen(
            conn,
            fp
        ):

            candidates.append(
                (
                    fp,
                    item
                )
            )

    print(
        "[INFO] Notícias disponíveis para processamento:",
        len(candidates)
    )

    if not candidates:

        print(
            "[INFO] Nenhuma notícia nova."
        )

        return

    # Durante o teste processaremos até 3
    # para confirmar que tudo funciona.
    candidates = candidates[
        :ARTICLES_PER_RUN
    ]

    processed_count = 0

    for fp, item in candidates:

        print(
            ""
        )

        print(
            "--------------------------------------------------"
        )

        print(
            "[INFO] Processando:",
            item["title"]
        )

        print(
            "--------------------------------------------------"
        )

        try:

            source_text = page_extract(
                item["url"]
            )

            if not source_text:

                print(
                    "[WARN] Não foi possível obter o texto."
                )

                continue

            print(
                "[GEMINI] Gerando reportagem..."
            )

            article = generate_article(
                item,
                source_text
            )

            print(
                "[GEMINI] Reportagem gerada."
            )

            print(
                "[GEMINI] Título:",
                article.get(
                    "title",
                    "(sem título)"
                )
            )

            if not article.get(
                "publish",
                True
            ):

                print(
                    "[INFO] Notícia rejeitada pelo Gemini."
                )

                mark_seen(
                    conn,
                    fp,
                    item,
                    None
                )

                continue

            result = publish_article(
                article,
                item
            )

            if result:

                mark_seen(
                    conn,
                    fp,
                    item,
                    result.get("id")
                )

                processed_count += 1

                print(
                    "[SUCCESS] Processamento concluído."
                )

        except Exception as exc:

            print(
                "[ERROR] Erro ao processar notícia:"
            )

            print(
                repr(exc)
            )

            # Continua para a próxima notícia
            continue

    print(
        ""
    )

    print(
        "=================================================="
    )

    print(
        "[FINISH] Execução concluída."
    )

    print(
        "[FINISH] Notícias enviadas:",
        processed_count
    )

    print(
        "[FINISH] Status atual:",
        WP_POST_STATUS
    )

    print(
        "=================================================="
    )


if __name__ == "__main__":
    main()
