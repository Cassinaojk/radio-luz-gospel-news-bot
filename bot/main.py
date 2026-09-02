import os
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BLOGGER_BLOG_ID = os.environ["BLOGGER_BLOG_ID"]

GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# TRUE = cria rascunho
# FALSE = publica automaticamente
BLOGGER_DRAFT = True

# Quantidade máxima de links que serão analisados por fonte
MAX_LINKS_PER_SOURCE = 5

# Quantos dias uma notícia pode ter para ser considerada recente
MAX_AGE_DAYS = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}


# ============================================================
# FONTES
# ============================================================

FONTES = [
    {
        "nome": "Fuxico Gospel",
        "pagina": "https://www.fuxicogospel.com.br/",
        "dominio": "www.fuxicogospel.com.br",
    },
    {
        "nome": "UAU Gospel",
        "pagina": "https://www.uaugospel.com.br/",
        "dominio": "www.uaugospel.com.br",
    },
    {
        "nome": "News Gospel",
        "pagina": "https://www.newsgospel.com.br/",
        "dominio": "www.newsgospel.com.br",
    },
]


# ============================================================
# CONEXÃO COM BLOGGER
# ============================================================

def conectar_blogger():

    print("Conectando ao Blogger...")

    credentials = Credentials(
        token=None,
        refresh_token=BLOGGER_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=[
            "https://www.googleapis.com/auth/blogger"
        ],
    )

    service = build(
        "blogger",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    service.blogs().get(
        blogId=BLOGGER_BLOG_ID
    ).execute()

    print("Conexão com Blogger: OK")

    return service


# ============================================================
# NORMALIZAR TEXTO
# ============================================================

def normalizar_texto(texto):

    texto = texto.lower()

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


# ============================================================
# BUSCAR POSTS DO BLOGGER
# ============================================================

def buscar_posts(service, status):

    posts = []

    try:

        resposta = service.posts().list(
            blogId=BLOGGER_BLOG_ID,
            status=status,
            maxResults=50,
        ).execute()

        posts.extend(
            resposta.get("items", [])
        )

        while resposta.get("nextPageToken"):

            resposta = service.posts().list(
                blogId=BLOGGER_BLOG_ID,
                status=status,
                maxResults=50,
                pageToken=resposta["nextPageToken"],
            ).execute()

            posts.extend(
                resposta.get("items", [])
            )

    except Exception as e:

        print(
            f"Erro buscando posts {status}: {e}"
        )

    return posts


# ============================================================
# VERIFICAR DUPLICIDADE
# ============================================================

def noticia_ja_existe(service, titulo, url):

    print(
        "Verificando se a notícia já existe..."
    )

    posts = []

    posts.extend(
        buscar_posts(
            service,
            "LIVE"
        )
    )

    posts.extend(
        buscar_posts(
            service,
            "DRAFT"
        )
    )

    titulo_normalizado = normalizar_texto(
        titulo
    )

    for post in posts:

        titulo_post = post.get(
            "title",
            ""
        )

        conteudo_post = post.get(
            "content",
            ""
        )

        # Verificação pelo título
        if (
            normalizar_texto(
                titulo_post
            )
            == titulo_normalizado
        ):

            print(
                "Notícia já existe pelo título."
            )

            return True

        # Verificação pela fonte
        if url in conteudo_post:

            print(
                "Notícia já existe pelo link."
            )

            return True

    print(
        "Notícia nova."
    )

    return False


# ============================================================
# ACESSAR UMA FONTE
# ============================================================

def acessar_fonte(fonte):

    nome = fonte["nome"]
    pagina = fonte["pagina"]

    print()
    print("-" * 60)
    print(
        f"FONTE: {nome}"
    )
    print("-" * 60)

    try:

        response = requests.get(
            pagina,
            headers=HEADERS,
            timeout=30,
        )

        print(
            f"HTTP: {response.status_code}"
        )

        if response.status_code != 200:

            print(
                f"{nome}: acesso recusado ou indisponível."
            )

            return None

        return response.text

    except Exception as e:

        print(
            f"{nome}: erro de conexão: {e}"
        )

        return None


# ============================================================
# ENCONTRAR LINKS DE ARTIGOS
# ============================================================

def encontrar_links(fonte, html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    dominio = fonte["dominio"]

    links = []

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a["href"].strip()

        href = urljoin(
            fonte["pagina"],
            href
        )

        if not href.startswith(
            f"https://{dominio}/"
        ):

            continue

        # Remove fragmentos
        href = href.split("#")[0]

        # Ignorar páginas que não são matérias
        ignorar = [
            "/category/",
            "/tag/",
            "/autor/",
            "/author/",
            "/page/",
            "/search/",
            "/feed/",
            "/wp-json/",
            "/contato",
            "/sobre",
            "/politica",
            "/termos",
            "/privacidade",
            "/ultimas-noticias/",
        ]

        if any(
            item in href
            for item in ignorar
        ):

            continue

        # Evita duplicidade
        if href not in links:

            links.append(href)

    print(
        f"Links encontrados: {len(links)}"
    )

    return links[:MAX_LINKS_PER_SOURCE]


# ============================================================
# EXTRAIR DATA
# ============================================================

def extrair_data(soup):

    candidatos = []

    # Meta tags
    metas = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"property": "og:published_time"}),
        ("meta", {"name": "date"}),
        ("meta", {"name": "publish-date"}),
    ]

    for tag, atributos in metas:

        elemento = soup.find(
            tag,
            atributos
        )

        if elemento:

            valor = (
                elemento.get("content")
                or elemento.get("datetime")
            )

            if valor:
                candidatos.append(valor)

    # Tags time
    for elemento in soup.find_all("time"):

        valor = (
            elemento.get("datetime")
            or elemento.get_text(
                " ",
                strip=True
            )
        )

        if valor:
            candidatos.append(valor)

    # Tenta interpretar as datas
    agora = datetime.now(
        timezone.utc
    )

    for valor in candidatos:

        valor = valor.strip()

        try:

            # ISO
            data = datetime.fromisoformat(
                valor.replace(
                    "Z",
                    "+00:00"
                )
            )

            if data.tzinfo is None:

                data = data.replace(
                    tzinfo=timezone.utc
                )

            return data

        except Exception:
            pass

    return None


# ============================================================
# VERIFICAR SE É RECENTE
# ============================================================

def noticia_recente(data):

    if data is None:

        # Se não conseguirmos identificar a data,
        # permitimos a análise.
        return True

    limite = datetime.now(
        timezone.utc
    ) - timedelta(
        days=MAX_AGE_DAYS
    )

    return data >= limite


# ============================================================
# EXTRAIR NOTÍCIA
# ============================================================

def extrair_noticia(fonte, url):

    print()
    print(
        f"Abrindo notícia:"
    )
    print(url)

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )

        print(
            f"HTTP: {response.status_code}"
        )

        if response.status_code != 200:

            return None

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # ----------------------------------------------------
        # TÍTULO
        # ----------------------------------------------------

        titulo = ""

        h1 = soup.find("h1")

        if h1:

            titulo = h1.get_text(
                " ",
                strip=True
            )

        if not titulo:

            title = soup.find("title")

            if title:

                titulo = title.get_text(
                    " ",
                    strip=True
                )

        if not titulo:

            return None

        # ----------------------------------------------------
        # DATA
        # ----------------------------------------------------

        data = extrair_data(
            soup
        )

        if data:

            print(
                f"Data encontrada: {data.isoformat()}"
            )

            if not noticia_recente(data):

                print(
                    "Notícia antiga. Pulando."
                )

                return None

        # ----------------------------------------------------
        # CONTEÚDO
        # ----------------------------------------------------

        seletores = [
            "article",
            ".post-content",
            ".entry-content",
            ".td-post-content",
            ".single-post-content",
            "main",
        ]

        container = None

        for seletor in seletores:

            encontrado = soup.select_one(
                seletor
            )

            if encontrado:

                container = encontrado

                break

        if container:

            elementos = (
                container.find_all("p")
            )

        else:

            elementos = (
                soup.find_all("p")
            )

        paragrafos = []

        for p in elementos:

            texto = p.get_text(
                " ",
                strip=True
            )

            if len(texto) >= 40:

                paragrafos.append(
                    texto
                )

        texto = "\n\n".join(
            paragrafos
        )

        if len(texto) < 200:

            print(
                "Texto insuficiente."
            )

            return None

        texto = texto[:12000]

        print(
            f"Notícia encontrada: {titulo}"
        )

        print(
            f"Texto extraído: {len(texto)} caracteres"
        )

        return {
            "titulo": titulo,
            "texto": texto,
            "url": url,
            "fonte": fonte["nome"],
        }

    except Exception as e:

        print(
            f"Erro ao abrir notícia: {e}"
        )

        return None


# ============================================================
# GEMINI
# ============================================================

def gerar_noticia_com_gemini(noticia):

    print()
    print(
        "Gerando notícia com Gemini..."
    )

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    prompt = f"""
Você é jornalista de um portal de notícias gospel brasileiro.

Produza uma matéria jornalística ORIGINAL a partir das
informações fornecidas abaixo.

REGRAS OBRIGATÓRIAS:

- Não copie frases da fonte.
- Não faça simples troca de palavras.
- Reescreva a matéria de forma original.
- Não invente fatos.
- Não invente nomes.
- Não invente datas.
- Não invente números.
- Não invente declarações.
- Preserve os fatos importantes.
- Escreva em português brasileiro.
- Use linguagem jornalística clara.
- Crie um título novo.
- Crie um subtítulo novo.
- Use parágrafos curtos.
- Não use emojis.
- Não mencione inteligência artificial.
- Não mencione ChatGPT.
- Não use Markdown.
- Retorne somente HTML simples.

A matéria deve ter aproximadamente
400 a 600 palavras.

ESTRUTURA:

<h1>Título novo</h1>

<p><strong>Subtítulo novo.</strong></p>

<p>Primeiro parágrafo...</p>

<p>Segundo parágrafo...</p>

<p>Terceiro parágrafo...</p>

FONTE:
{noticia["fonte"]}

TÍTULO ORIGINAL:
{noticia["titulo"]}

CONTEÚDO ORIGINAL:
{noticia["texto"]}
"""

    try:

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )

        texto = response.text.strip()

        if not texto:

            print(
                "Gemini não retornou conteúdo."
            )

            return None

        texto = texto.replace(
            "```html",
            ""
        )

        texto = texto.replace(
            "```",
            ""
        )

        texto = texto.strip()

        print(
            f"Texto gerado: {len(texto)} caracteres"
        )

        return texto

    except Exception as e:

        print(
            f"Erro no Gemini: {e}"
        )

        return None


# ============================================================
# PUBLICAR NO BLOGGER
# ============================================================

def publicar_no_blogger(
    service,
    conteudo,
    noticia
):

    print()
    print(
        "Enviando notícia para o Blogger..."
    )

    soup = BeautifulSoup(
        conteudo,
        "html.parser"
    )

    h1 = soup.find("h1")

    if h1:

        titulo = h1.get_text(
            " ",
            strip=True
        )

        h1.decompose()

        conteudo = str(soup)

    else:

        titulo = noticia["titulo"]

    # --------------------------------------------------------
    # FONTE
    # --------------------------------------------------------

    conteudo += f"""
<hr>

<p>
<strong>Fonte:</strong>
<a href="{noticia['url']}"
target="_blank"
rel="nofollow noopener">
{noticia['fonte']}
</a>
</p>
"""

    post = {
        "title": titulo,
        "content": conteudo,
    }

    try:

        if BLOGGER_DRAFT:

            resultado = service.posts().insert(
                blogId=BLOGGER_BLOG_ID,
                body=post,
                isDraft=True,
            ).execute()

            print()
            print(
                "========================================"
            )
            print(
                "RASCUNHO CRIADO COM SUCESSO!"
            )
            print(
                "========================================"
            )

        else:

            resultado = service.posts().insert(
                blogId=BLOGGER_BLOG_ID,
                body=post,
                isDraft=False,
            ).execute()

            print()
            print(
                "========================================"
            )
            print(
                "NOTÍCIA PUBLICADA COM SUCESSO!"
            )
            print(
                "========================================"
            )

        print(
            f"Título: {resultado.get('title')}"
        )

        print(
            f"ID: {resultado.get('id')}"
        )

        print(
            f"URL: {resultado.get('url', 'rascunho')}"
        )

        return resultado

    except Exception as e:

        print(
            f"Erro publicando no Blogger: {e}"
        )

        return None


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print()
    print("=" * 60)
    print(
        "RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS 2.0"
    )
    print("=" * 60)
    print()

    # --------------------------------------------------------
    # BLOGGER
    # --------------------------------------------------------

    try:

        service = conectar_blogger()

    except Exception as e:

        print()
        print(
            "ERRO AO CONECTAR AO BLOGGER:"
        )

        print(e)

        return

    # --------------------------------------------------------
    # PROCESSAR FONTES
    # --------------------------------------------------------

    total_links = 0
    total_noticias = 0

    for fonte in FONTES:

        html = acessar_fonte(
            fonte
        )

        if not html:

            print(
                f"Pulando {fonte['nome']}."
            )

            continue

        links = encontrar_links(
            fonte,
            html
        )

        total_links += len(links)

        if not links:

            print(
                f"Nenhuma notícia encontrada em "
                f"{fonte['nome']}."
            )

            continue

        # ----------------------------------------------------
        # PROCESSAR LINKS
        # ----------------------------------------------------

        for url in links:

            noticia = extrair_noticia(
                fonte,
                url
            )

            if not noticia:

                continue

            total_noticias += 1

            # ------------------------------------------------
            # DUPLICIDADE
            # ------------------------------------------------

            if noticia_ja_existe(
                service,
                noticia["titulo"],
                noticia["url"],
            ):

                print(
                    "Notícia duplicada. Pulando."
                )

                continue

            # ------------------------------------------------
            # GEMINI
            # ------------------------------------------------

            conteudo = (
                gerar_noticia_com_gemini(
                    noticia
                )
            )

            if not conteudo:

                print(
                    "Falha no Gemini."
                )

                print(
                    "Tentando próxima notícia..."
                )

                time.sleep(2)

                continue

            # ------------------------------------------------
            # BLOGGER
            # ------------------------------------------------

            resultado = publicar_no_blogger(
                service,
                conteudo,
                noticia,
            )

            if resultado:

                print()
                print("=" * 60)
                print(
                    "ROBÔ FINALIZADO COM SUCESSO."
                )
                print("=" * 60)

                return

            time.sleep(2)

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print(
        "PROCESSAMENTO FINALIZADO."
    )
    print("=" * 60)

    print(
        f"Links encontrados: {total_links}"
    )

    print(
        f"Notícias analisadas: {total_noticias}"
    )

    print(
        "Nenhuma notícia nova pôde ser publicada."
    )


# ============================================================
# EXECUTAR
# ============================================================

if __name__ == "__main__":
    main()
