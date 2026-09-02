import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
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

BLOGGER_DRAFT = True

MAX_LINKS_PER_SOURCE = 8
MAX_AGE_DAYS = 30

FONTES = [
    {
        "nome": "Fuxico Gospel",
        "url": "https://www.fuxicogospel.com.br/",
    },
    {
        "nome": "UAU Gospel",
        "url": "https://www.uaugospel.com.br/",
    },
    {
        "nome": "News Gospel",
        "url": "https://www.newsgospel.com.br/",
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
        scopes=["https://www.googleapis.com/auth/blogger"],
    )

    service = build("blogger", "v3", credentials=credentials)

    print("Conexão com Blogger: OK")

    return service


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_texto(texto):
    if not texto:
        return ""

    return re.sub(r"\s+", " ", texto).strip().lower()


# ============================================================
# VERIFICAR POSTS EXISTENTES
# ============================================================

def buscar_posts(service, status):
    posts = []

    try:
        resposta = (
            service.posts()
            .list(
                blogId=BLOGGER_BLOG_ID,
                status=status,
                maxResults=100,
            )
            .execute()
        )

        posts.extend(resposta.get("items", []))

    except Exception as erro:
        print(f"Erro ao buscar posts {status}: {erro}")

    return posts


def noticia_ja_existe(service, titulo, url):
    titulo_normalizado = normalizar_texto(titulo)

    posts = []

    posts.extend(buscar_posts(service, "LIVE"))
    posts.extend(buscar_posts(service, "DRAFT"))

    for post in posts:
        titulo_existente = normalizar_texto(
            post.get("title", "")
        )

        conteudo_existente = post.get("content", "")

        if titulo_normalizado == titulo_existente:
            print("Notícia já existe pelo título.")
            return True

        if url and url in conteudo_existente:
            print("Notícia já existe pela URL.")
            return True

    return False


# ============================================================
# ACESSAR FONTE
# ============================================================

def acessar_fonte(fonte):
    print()
    print(f"FONTE: {fonte['nome']}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }

    try:
        resposta = requests.get(
            fonte["url"],
            headers=headers,
            timeout=30,
        )

        print(f"HTTP: {resposta.status_code}")

        if resposta.status_code != 200:
            print("Não foi possível acessar a fonte.")
            return None

        return resposta.text

    except Exception as erro:
        print(f"Erro ao acessar fonte: {erro}")
        return None


# ============================================================
# FILTRO DE LINKS
# ============================================================

def link_valido(fonte, url):
    if not url:
        return False

    url = url.strip()

    if not url.startswith("http"):
        return False

    # Não queremos links externos
    if fonte["url"].rstrip("/") not in url:
        return False

    # --------------------------------------------------------
    # NEWS GOSPEL
    # Os artigos normalmente seguem:
    # /2026/08/nome-da-noticia.html
    # --------------------------------------------------------

    if fonte["nome"] == "News Gospel":
        padrao = r"^https?://www\.newsgospel\.com\.br/\d{4}/\d{2}/.+\.html/?$"

        if re.match(padrao, url):
            return True

        return False

    # --------------------------------------------------------
    # FUXICO E UAU
    # --------------------------------------------------------

    path = url.split("://", 1)[-1]

    if "/" in path:
        path = path.split("/", 1)[1]

    path = "/" + path.split("?", 1)[0].split("#", 1)[0]

    partes = [
        parte
        for parte in path.strip("/").split("/")
        if parte
    ]

    if not partes:
        return False

    # Páginas que não são notícias
    paginas_ignorar = {
        "quem-somos",
        "quem-somos",
        "fale-conosco",
        "contato",
        "contact",
        "sobre",
        "politica-de-privacidade",
        "política-de-privacidade",
        "termos-de-uso",
        "privacy-policy",
        "cookies",
        "login",
        "cadastro",
        "autor",
        "autores",
        "tag",
        "tags",
        "categoria",
        "categorias",
        "search",
        "busca",
        "feed",
        "rss",
        "videos",
        "video",
        "podcast",
        "podcasts",
        "home",
    }

    primeiro = partes[0].lower()

    # Se for uma página conhecida e tiver somente um nível,
    # não é uma notícia.
    if len(partes) == 1 and primeiro in paginas_ignorar:
        return False

    # Alguns caminhos são claramente páginas de seção.
    if len(partes) == 1:
        secoes = {
            "pastor",
            "famosos",
            "brasil",
            "mundo",
            "politica",
            "política",
            "entretenimento",
            "musica",
            "música",
            "gospel",
            "noticias",
            "notícias",
            "eventos",
        }

        if primeiro in secoes:
            return False

    return True


def encontrar_links(fonte, html):
    soup = BeautifulSoup(html, "html.parser")

    links = []
    vistos = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()

        if href.startswith("/"):
            href = fonte["url"].rstrip("/") + href

        if href.startswith("www."):
            href = "https://" + href

        href = href.split("#")[0]

        if not link_valido(fonte, href):
            continue

        if href in vistos:
            continue

        vistos.add(href)
        links.append(href)

    print(f"Links de possíveis notícias: {len(links)}")

    return links


# ============================================================
# DATA DA NOTÍCIA
# ============================================================

def extrair_data(soup, url):
    # Primeiro tenta metadados
    meta_selectors = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"property": "article:published"}),
        ("meta", {"name": "date"}),
        ("meta", {"name": "publishdate"}),
        ("meta", {"itemprop": "datePublished"}),
    ]

    for tag, atributos in meta_selectors:
        elemento = soup.find(tag, atributos)

        if elemento:
            valor = (
                elemento.get("content")
                or elemento.get("datetime")
            )

            if valor:
                try:
                    return datetime.fromisoformat(
                        valor.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except Exception:
                    pass

    # Tenta <time>
    time_tag = soup.find("time")

    if time_tag:
        valor = (
            time_tag.get("datetime")
            or time_tag.get_text(" ", strip=True)
        )

        if valor:
            try:
                return datetime.fromisoformat(
                    valor.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except Exception:
                pass

    # News Gospel usa a data na própria URL
    if "newsgospel.com.br" in url:
        padrao = r"/(\d{4})/(\d{2})/"

        resultado = re.search(padrao, url)

        if resultado:
            ano = int(resultado.group(1))
            mes = int(resultado.group(2))

            try:
                return datetime(ano, mes, 1)
            except Exception:
                pass

    return None


def noticia_recente(data):
    if not data:
        print("Data não identificada. Aceitando para análise.")
        return True

    limite = datetime.now() - timedelta(days=MAX_AGE_DAYS)

    print(f"Data encontrada: {data}")

    if data < limite:
        print("Notícia antiga. Pulando.")
        return False

    return True


# ============================================================
# EXTRAIR NOTÍCIA
# ============================================================

def extrair_noticia(fonte, url):
    print()
    print("Abrindo notícia:")
    print(url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9",
    }

    try:
        resposta = requests.get(
            url,
            headers=headers,
            timeout=30,
        )

        print(f"HTTP {resposta.status_code}")

        if resposta.status_code != 200:
            return None

        soup = BeautifulSoup(
            resposta.text,
            "html.parser",
        )

        data = extrair_data(soup, url)

        if not noticia_recente(data):
            return None

        # Título
        titulo = None

        h1 = soup.find("h1")

        if h1:
            titulo = h1.get_text(" ", strip=True)

        if not titulo:
            titulo_tag = soup.find("title")

            if titulo_tag:
                titulo = titulo_tag.get_text(
                    " ",
                    strip=True,
                )

        if not titulo:
            print("Título não encontrado.")
            return None

        # Remove elementos que atrapalham o texto
        for elemento in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "form",
            "aside",
        ]):
            elemento.decompose()

        paragrafos = []

        for p in soup.find_all("p"):
            texto = p.get_text(
                " ",
                strip=True,
            )

            if len(texto) >= 40:
                paragrafos.append(texto)

        texto = "\n\n".join(paragrafos)

        if len(texto) < 500:
            print(
                f"Texto insuficiente: {len(texto)} caracteres."
            )
            return None

        if len(texto) > 12000:
            texto = texto[:12000]

        print(f"Notícia encontrada: {titulo}")
        print(
            f"Texto extraído: {len(texto)} caracteres"
        )

        return {
            "fonte": fonte["nome"],
            "titulo": titulo,
            "url": url,
            "texto": texto,
            "data": data,
        }

    except Exception as erro:
        print(f"Erro ao extrair notícia: {erro}")
        return None


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
Você é um jornalista especializado em notícias do meio gospel brasileiro.

Escreva uma nova matéria jornalística em português do Brasil
a partir das informações da notícia abaixo.

REGRAS IMPORTANTES:

1. Não copie frases longas da fonte.
2. Reescreva o conteúdo com texto original.
3. Não invente informações.
4. Não invente declarações, números, datas ou acontecimentos.
5. Preserve os fatos apresentados na fonte.
6. Crie um título jornalístico atrativo.
7. Escreva aproximadamente 400 a 600 palavras.
8. Use HTML simples para o artigo.
9. Utilize <p> para os parágrafos.
10. Pode utilizar <h2> para subtítulos quando fizer sentido.
11. Não coloque links externos no meio da matéria.
12. No final, informe a fonte original.
13. Não diga que você é uma inteligência artificial.

FONTE:
{noticia['fonte']}

URL ORIGINAL:
{noticia['url']}

TÍTULO ORIGINAL:
{noticia['titulo']}

CONTEÚDO:
{noticia['texto']}
"""

    try:
        resposta = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )

        texto = resposta.text.strip()

        print(
            f"Texto gerado: {len(texto)} caracteres"
        )

        return texto

    except Exception as erro:
        print(f"Erro no Gemini: {erro}")
        return None


# ============================================================
# PUBLICAR NO BLOGGER
# ============================================================

def publicar_no_blogger(service, titulo, conteudo, noticia):
    print()
    print("Enviando notícia para Blogger...")

    conteudo_final = f"""
{conteudo}

<hr>

<p><strong>Fonte:</strong>
{noticia['fonte']}</p>

<p><strong>Notícia original:</strong>
<a href="{noticia['url']}" target="_blank" rel="noopener">
{noticia['url']}
</a>
</p>
"""

    corpo = {
        "kind": "blogger#post",
        "title": titulo,
        "content": conteudo_final,
    }

    try:
        if BLOGGER_DRAFT:
            resposta = (
                service.posts()
                .insert(
                    blogId=BLOGGER_BLOG_ID,
                    body=corpo,
                    isDraft=True,
                )
                .execute()
            )

            print("RASCUNHO CRIADO COM SUCESSO!")

        else:
            resposta = (
                service.posts()
                .insert(
                    blogId=BLOGGER_BLOG_ID,
                    body=corpo,
                    isDraft=False,
                )
                .execute()
            )

            print("NOTÍCIA PUBLICADA COM SUCESSO!")

        print(
            f"Título: {resposta.get('title')}"
        )

        print(
            f"ID: {resposta.get('id')}"
        )

        print(
            f"URL: {resposta.get('url')}"
        )

        return True

    except Exception as erro:
        print(
            f"Erro ao enviar para Blogger: {erro}"
        )
        return False


# ============================================================
# PRINCIPAL
# ============================================================

def main():
    print()
    print("=" * 60)
    print("RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS 2.1")
    print("=" * 60)

    service = conectar_blogger()

    for fonte in FONTES:
        html = acessar_fonte(fonte)

        if not html:
            continue

        links = encontrar_links(
            fonte,
            html,
        )

        candidatos = links[:MAX_LINKS_PER_SOURCE]

        for url in candidatos:
            noticia = extrair_noticia(
                fonte,
                url,
            )

            if not noticia:
                continue

            print()
            print("Verificando duplicidade...")

            if noticia_ja_existe(
                service,
                noticia["titulo"],
                noticia["url"],
            ):
                print("Notícia duplicada. Pulando.")
                continue

            print("Notícia nova.")

            conteudo_gerado = (
                gerar_noticia_com_gemini(noticia)
            )

            if not conteudo_gerado:
                continue

            titulo_prompt = f"""
Crie apenas um título jornalístico em português
para esta notícia.

Não use aspas desnecessárias.
Não invente informações.
Retorne somente o título.

Título original:
{noticia['titulo']}
"""

            try:
                client = genai.Client(
                    api_key=GEMINI_API_KEY
                )

                resposta_titulo = (
                    client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=titulo_prompt,
                    )
                )

                novo_titulo = (
                    resposta_titulo.text.strip()
                )

            except Exception:
                novo_titulo = noticia["titulo"]

            sucesso = publicar_no_blogger(
                service,
                novo_titulo,
                conteudo_gerado,
                noticia,
            )

            if sucesso:
                print()
                print("ROBÔ FINALIZADO COM SUCESSO.")
                return

    print()
    print(
        "Nenhuma notícia nova foi encontrada."
    )
    print("ROBÔ FINALIZADO.")


if __name__ == "__main__":
    main()
