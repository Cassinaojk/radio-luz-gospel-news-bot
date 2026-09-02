import os
import re
import time
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

# Primeiro vamos trabalhar com RASCUNHO.
# Depois que estiver funcionando, podemos mudar para publicação automática.
BLOGGER_DRAFT = True

SOURCE_URL = "https://www.fuxicogospel.com.br/ultimas-noticias/"

MAX_ARTICLES_TO_CHECK = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )
}


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

    # Testa a conexão
    service.blogs().get(
        blogId=BLOGGER_BLOG_ID
    ).execute()

    print("Conexão com Blogger: OK")

    return service


# ============================================================
# BUSCAR PÁGINA DE ÚLTIMAS NOTÍCIAS
# ============================================================

def buscar_pagina_noticias():
    print()
    print("Buscando últimas notícias...")

    response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=30,
    )

    print(f"Página acessada: HTTP {response.status_code}")

    response.raise_for_status()

    return response.text


# ============================================================
# ENCONTRAR LINKS DOS ARTIGOS
# ============================================================

def encontrar_links(html):
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for a in soup.find_all("a", href=True):

        href = a["href"].strip()

        if not href.startswith("https://www.fuxicogospel.com.br/"):
            continue

        # Ignora páginas que não são notícias
        ignorar = [
            "/ultimas-noticias/",
            "/politica-de-privacidade/",
            "/politica-de-cookies/",
            "/termos-de-uso/",
            "/contato/",
            "/sobre/",
            "/autor/",
            "/category/",
            "/tag/",
            "/page/",
        ]

        if any(item in href for item in ignorar):
            continue

        # Evita links duplicados
        if href not in links:
            links.append(href)

    print(f"Links encontrados: {len(links)}")

    return links


# ============================================================
# EXTRAIR NOTÍCIA
# ============================================================

def extrair_noticia(url):
    print()
    print(f"Abrindo notícia:")
    print(url)

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )

        print(f"HTTP: {response.status_code}")

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
            title_tag = soup.find("title")

            if title_tag:
                titulo = title_tag.get_text(
                    " ",
                    strip=True
                )

        if not titulo:
            return None

        # ----------------------------------------------------
        # TEXTO DA NOTÍCIA
        # ----------------------------------------------------

        paragrafos = []

        # Primeiro tenta encontrar o conteúdo principal
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
            encontrado = soup.select_one(seletor)

            if encontrado:
                container = encontrado
                break

        if container:
            elementos = container.find_all("p")
        else:
            elementos = soup.find_all("p")

        for p in elementos:
            texto = p.get_text(
                " ",
                strip=True
            )

            if len(texto) >= 40:
                paragrafos.append(texto)

        texto = "\n\n".join(paragrafos)

        if len(texto) < 200:
            print("Texto insuficiente.")
            return None

        # Limita o tamanho enviado ao Gemini
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
        }

    except Exception as e:
        print(
            f"Erro ao abrir notícia: {e}"
        )

        return None


# ============================================================
# VERIFICAR DUPLICIDADE NO BLOGGER
# ============================================================

def noticia_ja_existe(service, titulo, url):
    print("Verificando se a notícia já existe...")

    try:

        # Verifica posts publicados
        resultado_live = service.posts().list(
            blogId=BLOGGER_BLOG_ID,
            status="live",
            maxResults=50,
        ).execute()

        posts_live = resultado_live.get(
            "items",
            []
        )

        # Verifica rascunhos
        resultado_draft = service.posts().list(
            blogId=BLOGGER_BLOG_ID,
            status="draft",
            maxResults=50,
        ).execute()

        posts_draft = resultado_draft.get(
            "items",
            []
        )

        posts = posts_live + posts_draft

        titulo_normalizado = normalizar_texto(titulo)

        for post in posts:

            titulo_post = post.get(
                "title",
                ""
            )

            conteudo_post = post.get(
                "content",
                ""
            )

            if (
                normalizar_texto(titulo_post)
                == titulo_normalizado
            ):
                print(
                    "Notícia já existe pelo título."
                )
                return True

            if url in conteudo_post:
                print(
                    "Notícia já existe pelo link."
                )
                return True

        print("Notícia nova.")

        return False

    except Exception as e:
        print(
            f"Erro verificando duplicidade: {e}"
        )

        return False


def normalizar_texto(texto):
    texto = texto.lower()
    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


# ============================================================
# GEMINI
# ============================================================

def gerar_noticia_com_gemini(noticia):
    print()
    print("Gerando notícia com Gemini...")

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    prompt = f"""
Você é jornalista de um portal de notícias gospel brasileiro.

Sua tarefa é produzir uma nova matéria jornalística ORIGINAL
a partir das informações da notícia abaixo.

IMPORTANTE:

- NÃO copie frases da matéria original.
- NÃO invente informações.
- NÃO invente nomes, datas, números ou declarações.
- Preserve os fatos principais.
- Escreva em português brasileiro.
- Use linguagem jornalística clara.
- O texto deve parecer uma matéria publicada em um portal gospel.
- Crie um novo título.
- Crie um subtítulo.
- Organize o texto com parágrafos curtos.
- Não use emojis.
- Não escreva "segundo o ChatGPT".
- Não mencione que o texto foi produzido por inteligência artificial.
- Não use Markdown.
- Retorne HTML simples.

Estrutura obrigatória:

<h1>Título da notícia</h1>

<p><strong>Subtítulo da notícia.</strong></p>

<p>Primeiro parágrafo...</p>

<p>Segundo parágrafo...</p>

...

A matéria deve ter aproximadamente 400 a 600 palavras.

NOTÍCIA ORIGINAL:

Título:
{noticia["titulo"]}

Conteúdo:
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

        # Remove possíveis blocos Markdown
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
        print()
        print(
            f"Erro no Gemini: {e}"
        )

        return None


# ============================================================
# PUBLICAR NO BLOGGER
# ============================================================

def publicar_no_blogger(service, conteudo, noticia):
    print()
    print("Enviando notícia para o Blogger...")

    # Extrai o H1 gerado pelo Gemini
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

        # Remove H1 do conteúdo
        h1.decompose()

        conteudo = str(soup)

    else:
        titulo = noticia["titulo"]

    # Acrescenta fonte
    conteudo += f"""
<hr>

<p><strong>Fonte:</strong>
<a href="{noticia['url']}" target="_blank" rel="nofollow noopener">
Fuxico Gospel
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

        print()
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
    print("RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS")
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
    # BUSCAR PÁGINA
    # --------------------------------------------------------

    try:
        html = buscar_pagina_noticias()

    except Exception as e:

        print()
        print(
            "ERRO AO ACESSAR O SITE DE NOTÍCIAS:"
        )
        print(e)

        return

    # --------------------------------------------------------
    # LINKS
    # --------------------------------------------------------

    links = encontrar_links(html)

    if not links:

        print()
        print(
            "Nenhum link de notícia encontrado."
        )

        return

    # Limita quantidade
    links = links[:MAX_ARTICLES_TO_CHECK]

    print(
        f"Notícias encontradas: {len(links)}"
    )

    # --------------------------------------------------------
    # PROCESSAR NOTÍCIAS
    # --------------------------------------------------------

    for numero, url in enumerate(
        links,
        start=1
    ):

        print()
        print("=" * 60)
        print(
            f"PROCESSANDO NOTÍCIA {numero}/{len(links)}"
        )
        print("=" * 60)

        noticia = extrair_noticia(url)

        if not noticia:
            print(
                "Não foi possível extrair esta notícia."
            )
            continue

        # ----------------------------------------------------
        # DUPLICIDADE
        # ----------------------------------------------------

        if noticia_ja_existe(
            service,
            noticia["titulo"],
            noticia["url"],
        ):

            print(
                "Pulando notícia duplicada."
            )

            continue

        # ----------------------------------------------------
        # GEMINI
        # ----------------------------------------------------

        conteudo = gerar_noticia_com_gemini(
            noticia
        )

        if not conteudo:

            print(
                "Falha na geração. Tentando próxima notícia..."
            )

            time.sleep(2)

            continue

        # ----------------------------------------------------
        # BLOGGER
        # ----------------------------------------------------

        resultado = publicar_no_blogger(
            service,
            conteudo,
            noticia,
        )

        if resultado:

            print()
            print(
                "Robô finalizado com sucesso."
            )

            return

        time.sleep(2)

    # --------------------------------------------------------
    # NENHUMA NOTÍCIA PUBLICADA
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print(
        "NENHUMA NOTÍCIA NOVA PÔDE SER PUBLICADA."
    )
    print("=" * 60)


# ============================================================
# EXECUTAR
# ============================================================

if __name__ == "__main__":
    main()
