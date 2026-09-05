import os
import re
import json
import requests
import time
from pathlib import Path

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS
# VERSÃO 3.5 - EDITORIAL ADSENSE + IMAGEM ORIGINAL + 3 FONTES + BUSCA AMPLIADA
# ============================================================


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BLOGGER_BLOG_ID = os.environ["BLOGGER_BLOG_ID"]

GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# Contador de chamadas Gemini nesta execução.
gemini_text_calls_this_run = 0

# Limites de proteção contra excesso de uso do Gemini e publicações.
MAX_GEMINI_TEXT_CALLS_PER_RUN = 1
MAX_POSTS_PER_DAY = 3

GITHUB_REPO = "Cassinaojk/radio-luz-gospel-news-bot"
GITHUB_BRANCH = "main"

# Identificação das publicações feitas pelo robô.
BOT_LABEL = "Radio Luz Gospel Bot"


# False = publicação automática
# True = cria rascunho
BLOGGER_DRAFT = False


# Quantos links serão analisados por fonte.
# O robô percorre até 50 candidatos para encontrar uma notícia realmente nova.
MAX_LINKS_PER_SOURCE = 50


# Notícias com mais de 30 dias serão ignoradas
MAX_AGE_DAYS = 30


TIMEOUT = 25

# Regras editoriais para reduzir conteúdo superficial/reutilizado.
MIN_SOURCE_CHARS = 700
MIN_SOURCE_PARAGRAPHS = 4
MIN_GENERATED_CHARS = 1000
MAX_SOURCE_OVERLAP = 0.12
MAX_POST_SIMILARITY = 0.38
MAX_TITLE_SIMILARITY = 0.82
MAX_CONTEXT_ARTICLES = 2
MAX_CONTEXT_CHARS = 1800
MAX_EXACT_PHRASE_WORDS = 20
MIN_RELEVANT_WORDS_IN_EXACT_PHRASE = 14
GEMINI_MODEL_TEXT = "gemini-3.6-flash"
GEMINI_MODEL_TEXT_FALLBACK = "gemini-3.5-flash-lite"


# ============================================================
# FONTES
# ============================================================

FONTES = [
    {
        "nome": "News Gospel",
        "url": "https://www.newsgospel.com.br/",
    },
    {
        "nome": "UAU Gospel",
        "url": "https://www.uaugospel.com.br/",
    },
    {
        "nome": "Gospel+",
        "url": "https://gospelmais.com/",
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
    )

    print("Conexão com Blogger: OK")

    return service


# ============================================================
# NORMALIZAR TEXTO
# ============================================================

def normalizar_texto(texto):

    if not texto:
        return ""

    return re.sub(
        r"\s+",
        " ",
        texto
    ).strip().lower()


# ============================================================
# LIMPAR HTML GERADO PELO GEMINI
# ============================================================

def limpar_html_gemini(texto):

    if not texto:
        return ""

    texto = texto.strip()

    # Remove bloco markdown ```html ... ```
    texto = re.sub(
        r"^```(?:html)?\s*",
        "",
        texto,
        flags=re.IGNORECASE
    )

    texto = re.sub(
        r"\s*```$",
        "",
        texto
    )

    return texto.strip()


# ============================================================
# BUSCAR POSTS DO BLOG
# ============================================================

def buscar_posts(service, status):

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

        return resposta.get(
            "items",
            []
        )

    except Exception as erro:

        print(
            f"Erro ao buscar posts {status}: {erro}"
        )

        return []


# ============================================================
# VERIFICAR DUPLICIDADE
# ============================================================

def noticia_ja_existe(
    service,
    titulo,
    url
):

    titulo_normalizado = normalizar_texto(
        titulo
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

    for post in posts:

        titulo_existente = normalizar_texto(
            post.get(
                "title",
                ""
            )
        )

        conteudo_existente = post.get(
            "content",
            ""
        )

        if (
            titulo_normalizado
            == titulo_existente
        ):

            print(
                "Notícia já existe pelo título."
            )

            return True

        if (
            url
            and url in conteudo_existente
        ):

            print(
                "Notícia já existe pela URL."
            )

            return True

    return False


# ============================================================
# LIMITE DIÁRIO DE PUBLICAÇÕES
# ============================================================

def contar_publicacoes_hoje(service):
    """Conta quantas publicações do robô foram feitas hoje."""
    hoje = datetime.now().date()
    total = 0

    for status in ("LIVE", "DRAFT"):
        posts = buscar_posts(service, status)

        for post in posts:
            labels = post.get("labels", [])

            if BOT_LABEL not in labels:
                continue

            data_post = (
                post.get("published")
                or post.get("updated")
                or ""
            )

            if not data_post:
                continue

            try:
                data_post = datetime.fromisoformat(
                    data_post.replace("Z", "+00:00")
                ).replace(tzinfo=None)

                if data_post.date() == hoje:
                    total += 1

            except Exception:
                continue

    return total


def limite_diario_atingido(service):
    total = contar_publicacoes_hoje(service)

    print()
    print(
        f"Publicações do robô hoje: "
        f"{total}/{MAX_POSTS_PER_DAY}"
    )

    if total >= MAX_POSTS_PER_DAY:
        print(
            "Limite diário atingido. "
            "Gemini não será chamado hoje."
        )
        return True

    return False


# ============================================================
# ACESSAR SITE
# ============================================================

def acessar_url(url):

    headers = {

        "User-Agent": (
            "Mozilla/5.0 "
            "(X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        ),

        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;q=0.9,"
            "*/*;q=0.8"
        ),

        "Accept-Language": (
            "pt-BR,pt;q=0.9,en;q=0.8"
        ),
    }

    try:

        resposta = requests.get(
            url,
            headers=headers,
            timeout=TIMEOUT,
        )

        print(
            f"HTTP: {resposta.status_code}"
        )

        if resposta.status_code != 200:
            if resposta.status_code in {429, 500, 502, 503, 504}:
                print("Fonte temporariamente indisponível/limitada. Pulando esta URL.")
            return None

        return resposta.text

    except Exception as erro:

        print(
            f"Erro ao acessar fonte: {erro}"
        )

        return None


# ============================================================
# NORMALIZAR URL
# ============================================================

def normalizar_url(
    fonte,
    href
):

    if not href:
        return None

    href = href.strip()

    if href.startswith("/"):
        href = (
            fonte["url"].rstrip("/")
            + href
        )

    elif href.startswith("www."):
        href = (
            "https://"
            + href
        )

    if not href.startswith(
        "http://"
    ) and not href.startswith(
        "https://"
    ):
        return None

    href = href.split(
        "#",
        1
    )[0]

    href = href.rstrip("/")

    return href


# ============================================================
# VERIFICAR SE LINK É DESTE SITE
# ============================================================

def pertence_ao_site(
    fonte,
    url
):

    dominio = (
        fonte["url"]
        .replace(
            "https://",
            ""
        )
        .replace(
            "http://",
            ""
        )
        .split(
            "/"
        )[0]
        .lower()
    )

    dominio_url = (
        url
        .replace(
            "https://",
            ""
        )
        .replace(
            "http://",
            ""
        )
        .split(
            "/"
        )[0]
        .lower()
    )

    if dominio_url == dominio:
        return True

    # Gospel+ pode redirecionar o endereço principal para
    # noticias.gospelmais.com. Os dois domínios pertencem
    # à mesma fonte e devem ser tratados como um único site.
    if fonte.get("nome") == "Gospel+":
        return dominio_url in {
            "gospelmais.com",
            "www.gospelmais.com",
            "noticias.gospelmais.com",
        }

    return False


# ============================================================
# FILTRO ESPECÍFICO DE LINKS
# ============================================================

def link_valido(
    fonte,
    url
):

    if not url:
        return False

    if not pertence_ao_site(
        fonte,
        url
    ):
        return False


    # --------------------------------------------------------
    # NEWS GOSPEL
    # --------------------------------------------------------

    if (
        fonte["nome"]
        == "News Gospel"
    ):

        padrao = (
            r"^https?://"
            r"www\.newsgospel\.com\.br/"
            r"\d{4}/\d{2}/"
            r".+\.html$"
        )

        return bool(
            re.match(
                padrao,
                url
            )
        )


    # --------------------------------------------------------
    # CAMINHO
    # --------------------------------------------------------

    caminho = re.sub(
        r"^https?://[^/]+",
        "",
        url
    )

    caminho = (
        caminho
        .split("?", 1)[0]
        .split("#", 1)[0]
        .strip("/")
    )

    partes = [
        p
        for p in caminho.split("/")
        if p
    ]

    if not partes:
        return False

    primeiro = (
        partes[0]
        .lower()
    )

    ultimo = (
        partes[-1]
        .lower()
    )


    # --------------------------------------------------------
    # PÁGINAS QUE NÃO SÃO NOTÍCIAS
    # --------------------------------------------------------

    # UAU Gospel possui páginas de categoria, autor e outros
    # arquivos que podem parecer links de notícias, mas não são
    # matérias individuais.
    if fonte.get("nome") == "UAU Gospel":
        caminhos_nao_noticia = {
            "category",
            "categoria",
            "tag",
            "author",
            "autor",
            "page",
            "feed",
            "search",
            "busca",
            "wp-content",
            "wp-json",
        }

        if primeiro in caminhos_nao_noticia:
            return False

        # Uma matéria do UAU Gospel deve ser uma página individual
        # com slug, e não a página inicial.
        if len(partes) < 1 or not ultimo:
            return False

    # --------------------------------------------------------
    # PÁGINAS INSTITUCIONAIS
    # --------------------------------------------------------

    paginas_bloqueadas = {

        "ultimas-noticias",
        "últimas-notícias",

        "quem-somos",

        "fale-conosco",
        "contato",
        "contact",

        "sobre",

        "politica-de-privacidade",
        "política-de-privacidade",

        "politica-editorial",
        "política-editorial",

        "padroes-eticos",
        "padrões-éticos",

        "politica-de-correcoes",
        "política-de-correções",

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

        "sitemap",

        "videos",
        "video",

        "podcast",
        "podcasts",

        "home",
    }

    if ultimo in paginas_bloqueadas:
        return False


    # --------------------------------------------------------
    # SEÇÕES
    # --------------------------------------------------------

    secoes = {

        "pastor",
        "pastores",

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

        "igreja",
        "igrejas",

        "ministerio",
        "ministério",

        "cantores",
        "cantor",

        "artistas",
        "artista",
    }

    if (
        len(partes) == 1
        and primeiro in secoes
    ):
        return False


    # --------------------------------------------------------
    # EXTENSÕES
    # --------------------------------------------------------

    extensoes_bloqueadas = (

        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".svg",
        ".pdf",
        ".xml",
        ".rss",
        ".mp3",
        ".mp4",
    )

    if ultimo.endswith(
        extensoes_bloqueadas
    ):
        return False


    # --------------------------------------------------------
    # WORDPRESS
    # --------------------------------------------------------

    if primeiro in {

        "wp-content",
        "wp-admin",
        "wp-includes",

        "feed",
        "comments",
    }:

        return False


    # --------------------------------------------------------
    # GOSPEL+
    # --------------------------------------------------------

    if fonte["nome"] == "Gospel+":
        # Páginas de categoria, busca, autores e demais áreas
        # institucionais já são filtradas acima. Aqui evitamos
        # também URLs que sejam claramente páginas de navegação.
        if primeiro in {
            "categoria",
            "categorias",
            "autor",
            "autores",
            "tag",
            "tags",
            "busca",
            "search",
            "popular",
        }:
            return False



    return True


# ============================================================
# ENCONTRAR LINKS
# ============================================================

def encontrar_links(
    fonte,
    html
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    links = []
    vistos = set()

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a.get(
            "href",
            ""
        )

        url = normalizar_url(
            fonte,
            href
        )

        if not url:
            continue

        if not link_valido(
            fonte,
            url
        ):
            continue

        if url in vistos:
            continue

        vistos.add(url)

        links.append(url)

    print(
        f"Links de possíveis notícias: "
        f"{len(links)}"
    )

    return links


# ============================================================
# EXTRAIR DATA
# ============================================================

def extrair_data(
    soup,
    url
):

    seletores = [

        {
            "property":
            "article:published_time"
        },

        {
            "property":
            "article:published"
        },

        {
            "name":
            "date"
        },

        {
            "name":
            "publishdate"
        },

        {
            "itemprop":
            "datePublished"
        },
    ]

    for atributos in seletores:

        elemento = soup.find(
            "meta",
            atributos
        )

        if not elemento:
            continue

        valor = (
            elemento.get(
                "content"
            )
            or elemento.get(
                "datetime"
            )
        )

        if not valor:
            continue

        try:

            return datetime.fromisoformat(
                valor.replace(
                    "Z",
                    "+00:00"
                )
            ).replace(
                tzinfo=None
            )

        except Exception:
            pass


    time_tag = soup.find(
        "time"
    )

    if time_tag:

        valor = (
            time_tag.get(
                "datetime"
            )
            or time_tag.get_text(
                " ",
                strip=True
            )
        )

        if valor:

            try:

                return datetime.fromisoformat(
                    valor.replace(
                        "Z",
                        "+00:00"
                    )
                ).replace(
                    tzinfo=None
                )

            except Exception:
                pass


    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        try:

            dados = json.loads(
                script.string
                or script.get_text()
            )

        except Exception:
            continue

        blocos = []

        if isinstance(dados, dict):
            blocos = [dados]

            if isinstance(
                dados.get("@graph"),
                list
            ):
                blocos.extend(
                    dados["@graph"]
                )

        elif isinstance(dados, list):
            blocos = dados

        for bloco in blocos:

            if not isinstance(
                bloco,
                dict
            ):
                continue

            valor = (
                bloco.get(
                    "datePublished"
                )
                or bloco.get(
                    "dateCreated"
                )
            )

            if not valor:
                continue

            try:

                return datetime.fromisoformat(
                    valor.replace(
                        "Z",
                        "+00:00"
                    )
                ).replace(
                    tzinfo=None
                )

            except Exception:
                pass


    # --------------------------------------------------------
    # NEWS GOSPEL - DATA NA URL
    # --------------------------------------------------------

    if (
        "newsgospel.com.br"
        in url
    ):

        resultado = re.search(
            r"/(\d{4})/(\d{2})/",
            url
        )

        if resultado:

            ano = int(
                resultado.group(1)
            )

            mes = int(
                resultado.group(2)
            )

            try:

                return datetime(
                    ano,
                    mes,
                    1
                )

            except Exception:
                pass

    return None


# ============================================================
# VERIFICAR DATA
# ============================================================

def noticia_recente(
    data,
    url=None
):

    if not data:

        print(
            "Data não identificada."
        )

        # Não aceitar páginas de categoria, arquivo, busca ou
        # outras páginas sem data como se fossem notícias.
        if url:
            caminho = re.sub(
                r"^https?://[^/]+",
                "",
                url
            ).strip("/").lower()

            primeiros = caminho.split("/")
            primeiro = primeiros[0] if primeiros else ""

            if primeiro in {
                "category", "categoria", "tag", "author", "autor",
                "page", "feed", "search", "busca", "archive",
                "arquivos"
            }:
                print("Página sem data não é uma notícia individual. Pulando.")
                return False

        print(
            "Data não identificada; aceitando apenas para "
            "página que já passou pelo filtro de notícia."
        )
        return True

    limite = (
        datetime.now()
        - timedelta(
            days=MAX_AGE_DAYS
        )
    )

    print(
        f"Data encontrada: {data}"
    )

    if data < limite:

        print(
            "Notícia antiga. Pulando."
        )

        return False

    return True


# ============================================================
# EXTRAIR IMAGEM
# ============================================================

def imagem_valida(url):

    if not url:
        return False

    url_lower = url.lower()

    if not (
        url_lower.startswith(
            "http://"
        )
        or url_lower.startswith(
            "https://"
        )
    ):
        return False

    bloqueios = (

        "favicon",
        "avatar",
        "sprite",
        "emoji",
        "gravatar",
    )

    for termo in bloqueios:

        if termo in url_lower:
            return False

    return True


def extrair_imagem(
    soup
):

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        try:

            dados = json.loads(
                script.string
                or script.get_text()
            )

        except Exception:
            continue

        blocos = []

        if isinstance(dados, dict):

            blocos = [dados]

            if isinstance(
                dados.get("@graph"),
                list
            ):

                blocos.extend(
                    dados["@graph"]
                )

        elif isinstance(dados, list):

            blocos = dados

        for bloco in blocos:

            if not isinstance(
                bloco,
                dict
            ):
                continue

            imagem = bloco.get(
                "image"
            )

            if isinstance(
                imagem,
                str
            ):

                if imagem_valida(
                    imagem
                ):
                    return imagem

            if isinstance(
                imagem,
                dict
            ):

                url = imagem.get(
                    "url"
                )

                if imagem_valida(
                    url
                ):
                    return url

            if isinstance(
                imagem,
                list
            ):

                for item in imagem:

                    if isinstance(
                        item,
                        str
                    ) and imagem_valida(
                        item
                    ):
                        return item

                    if isinstance(
                        item,
                        dict
                    ):

                        url = item.get(
                            "url"
                        )

                        if imagem_valida(
                            url
                        ):
                            return url


    # --------------------------------------------------------
    # OG IMAGE
    # --------------------------------------------------------

    meta = soup.find(
        "meta",
        property="og:image"
    )

    if meta:

        url = meta.get(
            "content"
        )

        if imagem_valida(
            url
        ):
            return url


    # --------------------------------------------------------
    # TWITTER IMAGE
    # --------------------------------------------------------

    meta = soup.find(
        "meta",
        attrs={
            "name":
            "twitter:image"
        }
    )

    if meta:

        url = meta.get(
            "content"
        )

        if imagem_valida(
            url
        ):
            return url


    # --------------------------------------------------------
    # IMAGENS
    # --------------------------------------------------------

    for img in soup.find_all(
        "img"
    ):

        url = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-lazy-src")
        )

        if imagem_valida(
            url
        ):
            return url

    return None


# ============================================================
# ESCOLHER CONTAINER DA NOTÍCIA
# ============================================================

def escolher_container(
    soup
):

    candidatos = []

    seletores = [

        "article",

        ".entry-content",

        ".post-content",

        ".article-content",

        ".single-content",

        ".td-post-content",

        ".content-post",

        "main",
    ]

    for seletor in seletores:

        for elemento in soup.select(
            seletor
        ):

            texto = elemento.get_text(
                " ",
                strip=True
            )

            if len(texto) >= 500:

                candidatos.append(
                    elemento
                )

    if not candidatos:
        return soup

    candidatos.sort(
        key=lambda x:
        len(
            x.get_text(
                " ",
                strip=True
            )
        ),
        reverse=True
    )

    return candidatos[0]


# ============================================================
# EXTRAIR VÍDEOS DA MATÉRIA
# ============================================================

def extrair_videos(soup):

    videos = []
    ids_vistos = set()

    def adicionar_youtube(url):

        if not url:
            return

        url = url.strip()

        video_id = None

        padroes = [
            r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{6,})",
            r"(?:youtube-nocookie\.com/embed/)([A-Za-z0-9_-]{6,})",
            r"(?:youtube\.com/watch\?v=)([A-Za-z0-9_-]{6,})",
            r"(?:youtu\.be/)([A-Za-z0-9_-]{6,})",
            r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{6,})",
        ]

        for padrao in padroes:

            encontrado = re.search(
                padrao,
                url,
                re.IGNORECASE,
            )

            if encontrado:
                video_id = encontrado.group(1)
                break

        if not video_id:
            return

        if video_id in ids_vistos:
            return

        ids_vistos.add(video_id)

        videos.append(
            f"https://www.youtube.com/embed/{video_id}"
        )

    # Iframes incorporados
    for iframe in soup.find_all("iframe"):

        src = iframe.get("src") or iframe.get("data-src")
        adicionar_youtube(src)

    # Links do YouTube presentes na matéria
    for a in soup.find_all("a", href=True):
        adicionar_youtube(a.get("href"))

    # JSON-LD: VideoObject / embedUrl / contentUrl
    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):

        try:
            dados = json.loads(script.string or script.get_text())
        except Exception:
            continue

        blocos = dados if isinstance(dados, list) else [dados]

        for bloco in blocos:

            if not isinstance(bloco, dict):
                continue

            tipos = bloco.get("@type", [])
            if isinstance(tipos, str):
                tipos = [tipos]

            if "VideoObject" not in tipos:
                continue

            adicionar_youtube(bloco.get("embedUrl"))
            adicionar_youtube(bloco.get("contentUrl"))
            adicionar_youtube(bloco.get("url"))

    return videos


# ============================================================
# EXTRAIR CONTEÚDO DA MATÉRIA
# ============================================================

def extrair_noticia(
    fonte,
    url
):

    print()
    print(
        "Abrindo notícia:"
    )

    print(url)

    html = acessar_url(
        url
    )

    if not html:
        return None

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    data = extrair_data(
        soup,
        url
    )

    if not noticia_recente(
        data,
        url
    ):
        return None


    # --------------------------------------------------------
    # TÍTULO - METADADOS PRIMEIRO
    # --------------------------------------------------------

    titulo = None

    # Muitos portais usam H1 genérico e colocam o título real em
    # og:title/twitter:title ou em H2/H3. Priorizar metadados evita
    # publicar o nome do site como título da notícia.
    for attrs in [
        {"property": "og:title"},
        {"name": "twitter:title"},
    ]:
        meta = soup.find("meta", attrs)
        if meta and meta.get("content"):
            candidato = meta.get("content", "").strip()
            if candidato:
                titulo = candidato
                break

    if not titulo:
        candidatos_titulo = []
        for tag_name in ("h1", "h2", "h3"):
            for tag in soup.find_all(tag_name):
                candidato = tag.get_text(" ", strip=True)
                if len(candidato) >= 20:
                    candidatos_titulo.append(candidato)
        if candidatos_titulo:
            titulo = candidatos_titulo[0]

    if not titulo:
        titulo_tag = soup.find("title")
        if titulo_tag:
            titulo = titulo_tag.get_text(" ", strip=True)

    if not titulo:
        print("Título não encontrado.")
        return None


    # --------------------------------------------------------
    # IMAGEM
    # --------------------------------------------------------

    imagem = extrair_imagem(
        soup
    )

    if imagem:

        print(
            "Imagem encontrada:"
        )

        print(imagem)

    else:

        print(
            "Imagem não encontrada."
        )


    # --------------------------------------------------------
    # VÍDEOS
    # --------------------------------------------------------

    videos = extrair_videos(
        soup
    )

    if videos:

        print(
            f"Vídeos encontrados: {len(videos)}"
        )

        for video in videos:
            print(
                f"YouTube: {video}"
            )

    else:

        print(
            "Vídeos encontrados: 0"
        )


    # --------------------------------------------------------
    # REMOVER ELEMENTOS
    # --------------------------------------------------------

    for elemento in soup([
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "form",
        "aside",
        "noscript",
        "iframe",
    ]):

        elemento.decompose()


    # --------------------------------------------------------
    # CONTAINER
    # --------------------------------------------------------

    container = escolher_container(
        soup
    )


    # --------------------------------------------------------
    # PARÁGRAFOS
    # --------------------------------------------------------

    paragrafos = []

    for p in container.find_all(
        "p"
    ):

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


    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    if len(texto) < MIN_SOURCE_CHARS:

        paragrafos = []

        for p in soup.find_all(
            "p"
        ):

            texto_p = p.get_text(
                " ",
                strip=True
            )

            if len(texto_p) >= 40:

                paragrafos.append(
                    texto_p
                )

        texto = "\n\n".join(
            paragrafos
        )


    # --------------------------------------------------------
    # VALIDAÇÃO
    # --------------------------------------------------------

    if len(texto) < MIN_SOURCE_CHARS:

        print(
            "Texto insuficiente: "
            f"{len(texto)} caracteres."
        )

        return None

    paragrafos_validos = [
        p for p in texto.split("\n\n")
        if len(p.strip()) >= 40
    ]

    if len(paragrafos_validos) < MIN_SOURCE_PARAGRAPHS:
        print(
            "Fonte descartada: poucos parágrafos úteis "
            f"({len(paragrafos_validos)})."
        )
        return None

    if len(texto) > 12000:

        texto = texto[:12000]

    print(
        "Notícia encontrada: "
        f"{titulo}"
    )

    print(
        "Texto extraído: "
        f"{len(texto)} caracteres"
    )

    return {

        "fonte":
        fonte["nome"],

        "titulo":
        titulo,

        "url":
        url,

        "texto":
        texto,

        "imagem":
        imagem,

        "videos":
        videos,

        "data":
        data,
    }



# ============================================================
# CONTROLE DE ORIGINALIDADE E QUALIDADE EDITORIAL
# ============================================================

def palavras_relevantes(texto):
    palavras = re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", normalizar_texto(texto))
    ignoradas = {
        "para", "como", "mais", "sobre", "entre", "depois", "antes",
        "quando", "também", "porque", "pelo", "pela", "pelos", "pelas",
        "este", "esta", "esse", "essa", "seus", "suas", "com", "uma",
        "uns", "umas", "eles", "elas", "seu", "sua", "que", "dos", "das",
        "nas", "nos", "por", "não", "sem", "ainda", "onde", "muito"
    }
    return {p for p in palavras if p not in ignoradas}


def ngramas(texto, n=6):
    palavras = re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", normalizar_texto(texto))
    return set(" ".join(palavras[i:i+n]) for i in range(max(0, len(palavras)-n+1)))


def sobreposicao_textual(a, b, n=6):
    na = ngramas(a, n)
    nb = ngramas(b, n)
    if not na or not nb:
        return 0.0
    return len(na & nb) / max(1, len(na))


def similaridade_textual(a, b):
    a = normalizar_texto(a)
    b = normalizar_texto(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a[:12000], b[:12000]).ratio()


def validar_materia_gerada(noticia, titulo, conteudo):
    """Bloqueia matérias rasas, cópias e reformulações mecânicas."""
    texto_limpo = BeautifulSoup(conteudo, "html.parser").get_text(" ", strip=True)

    if len(texto_limpo) < MIN_GENERATED_CHARS:
        print(f"REPROVADA: matéria muito curta ({len(texto_limpo)} caracteres).")
        return False

    paragrafos = [
        p.get_text(" ", strip=True)
        for p in BeautifulSoup(conteudo, "html.parser").find_all("p")
        if len(p.get_text(" ", strip=True)) >= 50
    ]

    if len(paragrafos) < 5:
        print(f"REPROVADA: poucos parágrafos úteis ({len(paragrafos)}).")
        return False

    if not titulo or similaridade_textual(titulo, noticia.get("titulo", "")) >= MAX_TITLE_SIMILARITY:
        print("REPROVADA: título excessivamente parecido com o original.")
        return False

    sobreposicao = sobreposicao_textual(texto_limpo, noticia.get("texto", ""))
    print(f"Sobreposição textual com a fonte: {sobreposicao:.3f}")
    if sobreposicao > MAX_SOURCE_OVERLAP:
        print("REPROVADA: possível cópia/reformulação mecânica da fonte.")
        return False

    # Só bloquear uma sequência realmente longa e semanticamente relevante.
    # Isso evita falsos positivos em nomes, títulos de músicas e expressões
    # jornalísticas comuns.
    fonte = normalizar_texto(noticia.get("texto", ""))
    gerado = normalizar_texto(texto_limpo)
    palavras = fonte.split()
    relevantes_fonte = palavras_relevantes(fonte)
    encontrou_frase = False
    n = MAX_EXACT_PHRASE_WORDS
    for i in range(max(0, len(palavras) - n + 1)):
        trecho_palavras = palavras[i:i+n]
        trecho = " ".join(trecho_palavras)
        if trecho in gerado:
            relevantes = sum(1 for p in trecho_palavras if p in relevantes_fonte)
            if relevantes >= MIN_RELEVANT_WORDS_IN_EXACT_PHRASE:
                encontrou_frase = True
                break
    if encontrou_frase:
        print("REPROVADA: frase longa idêntica encontrada na fonte.")
        return False

    return True


def postagem_muito_parecida(service, titulo, conteudo):
    """Evita uma sequência de posts praticamente iguais no próprio blog."""
    texto = BeautifulSoup(conteudo, "html.parser").get_text(" ", strip=True)
    posts = []
    posts.extend(buscar_posts(service, "LIVE"))
    posts.extend(buscar_posts(service, "DRAFT"))

    for post in posts:
        if BOT_LABEL not in post.get("labels", []):
            continue

        titulo_existente = post.get("title", "")
        conteudo_existente = BeautifulSoup(
            post.get("content", ""), "html.parser"
        ).get_text(" ", strip=True)

        sim_titulo = similaridade_textual(titulo, titulo_existente)
        sim_texto = similaridade_textual(texto, conteudo_existente)
        overlap = sobreposicao_textual(texto, conteudo_existente)

        if sim_titulo >= MAX_TITLE_SIMILARITY or sim_texto >= MAX_POST_SIMILARITY or overlap >= 0.28:
            print("REPROVADA: muito parecida com uma publicação existente.")
            print(f"Título similaridade: {sim_titulo:.3f}")
            print(f"Texto similaridade: {sim_texto:.3f}")
            print(f"N-gram overlap: {overlap:.3f}")
            return True

    return False


def coletar_contexto_verificado(noticia):
    """Busca até dois textos relacionados em outras fontes configuradas.
    O contexto é apenas auxiliar; o Gemini deve usar somente fatos verificáveis.
    """
    contexto = []
    termos = palavras_relevantes(noticia.get("titulo", ""))

    if not termos:
        return contexto

    for fonte in FONTES:
        if fonte.get("nome") == noticia.get("fonte"):
            continue
        if len(contexto) >= MAX_CONTEXT_ARTICLES:
            break

        # Proteção contra configuração incompleta de uma fonte.
        fonte_url = fonte.get("url")
        if not fonte_url:
            print(
                f"⚠️ Fonte secundária ignorada: configuração sem URL "
                f"({fonte.get('nome', 'sem nome')})."
            )
            continue

        try:
            html = acessar_url(fonte_url)
        except Exception as erro:
            print(
                f"⚠️ Não foi possível consultar contexto de "
                f"{fonte.get('nome', 'fonte')}: {erro}"
            )
            continue

        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        candidatos = []

        for a in soup.find_all("a", href=True):
            texto_link = a.get_text(" ", strip=True)
            try:
                href = normalizar_url(fonte, a.get("href"))
            except Exception:
                href = None
            if not href or not texto_link or len(texto_link) < 25:
                continue
            if not pertence_ao_site(fonte, href):
                continue
            palavras_link = palavras_relevantes(texto_link)
            pontos = len(termos & palavras_link)
            if pontos >= 2:
                candidatos.append((pontos, href))

        vistos = set()
        for _, url in sorted(candidatos, reverse=True):
            if url in vistos:
                continue
            vistos.add(url)
            item = extrair_noticia(fonte, url)
            if not item:
                continue
            if item["url"] == noticia["url"]:
                continue
            contexto.append({
                "fonte": item["fonte"],
                "titulo": item["titulo"],
                "url": item["url"],
                "texto": item["texto"][:MAX_CONTEXT_CHARS],
            })
            break

    return contexto


# ============================================================
# CHAMADA ROBUSTA AO GEMINI
# ============================================================

def chamar_gemini_com_retry(client, prompt):
    modelos = [GEMINI_MODEL_TEXT, GEMINI_MODEL_TEXT_FALLBACK]
    ultimo_erro = None

    for modelo in modelos:
        for tentativa in range(3):
            try:
                print(f"Gemini: modelo {modelo}, tentativa {tentativa + 1}/3")
                resposta = client.models.generate_content(
                    model=modelo,
                    contents=prompt,
                )
                print("HTTP: 200")
                return resposta
            except Exception as erro:
                ultimo_erro = erro
                mensagem = str(erro)
                if any(x in mensagem for x in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED")):
                    espera = 5 * (tentativa + 1)
                    print(f"Gemini temporariamente indisponível ({modelo}). Aguardando {espera}s...")
                    time.sleep(espera)
                    continue
                print(f"Gemini recusou o modelo {modelo}: {mensagem}")
                break

        if modelo == GEMINI_MODEL_TEXT:
            print(f"Tentativas esgotadas para {modelo}. Tentando modelo reserva: {GEMINI_MODEL_TEXT_FALLBACK}")

    if ultimo_erro:
        raise ultimo_erro
    return None


# ============================================================
# GERAR TÍTULO + MATÉRIA COM UMA ÚNICA CHAMADA
# ============================================================

def gerar_conteudo_com_gemini(
    noticia
):

    global gemini_text_calls_this_run

    if gemini_text_calls_this_run >= MAX_GEMINI_TEXT_CALLS_PER_RUN:
        print()
        print(
            "Limite de chamadas Gemini desta execução atingido."
        )
        return None

    gemini_text_calls_this_run += 1

    print()
    print(
        "Gerando título e matéria com Gemini..."
    )

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )


    contexto = coletar_contexto_verificado(noticia)

    contexto_formatado = "\n\n".join(
        f"FONTE SECUNDÁRIA: {item['fonte']}\nTÍTULO: {item['titulo']}\nURL: {item['url']}\nTEXTO: {item['texto']}"
        for item in contexto
    )

    if not contexto_formatado:
        contexto_formatado = "Nenhuma fonte secundária relacionada foi encontrada. Não invente contexto."

    prompt = f"""
Você é o editor responsável por uma redação jornalística gospel brasileira.

Fluxo obrigatório: FONTE → PESQUISA → APURAÇÃO/CONTEXTUALIZAÇÃO → REDAÇÃO PRÓPRIA → REVISÃO → PUBLICAÇÃO.

A matéria será publicada em um site que pretende manter alto padrão editorial e futuramente solicitar o Google AdSense. Portanto, NÃO produza conteúdo superficial, copiado, traduzido ou apenas para preencher espaço.

Retorne SOMENTE um JSON válido com:
{{
  "publicar": true ou false,
  "titulo": "título novo",
  "conteudo": "<p>...</p>..."
}}

REGRAS OBRIGATÓRIAS:
1. O texto deve ser uma matéria nova, em português brasileiro natural.
2. Crie um título próprio, diferente do título da fonte.
3. Crie uma introdução própria; não comece repetindo a abertura da fonte.
4. Reescreva a notícia integralmente com estrutura e ordem de informações próprias.
5. NÃO faça tradução, substituição de sinônimos ou paráfrase frase a frase.
6. Não copie frases longas da fonte.
7. Preserve nomes, datas, números e fatos somente quando estiverem sustentados pelas fontes fornecidas.
8. Não invente declarações, números, datas, locais, links, eventos ou informações biográficas.
9. Use a fonte secundária apenas quando ela tratar claramente do mesmo assunto e acrescentar um fato verificável.
10. Não misture pessoas ou acontecimentos de matérias diferentes.
11. Acrescente contexto jornalístico útil quando houver informação suficiente.
12. Se as fontes forem insuficientes, contraditórias ou não permitirem uma matéria de qualidade, retorne publicar=false.
13. Escreva entre 450 e 650 palavras quando publicar=true.
14. Use pelo menos 5 parágrafos substantivos.
15. Use somente HTML simples: <p> e, se necessário, <h2>.
16. Não inclua markdown.
17. Não coloque links externos dentro do corpo da matéria.
18. Não escreva observações sobre IA.
19. Não copie o título ou a introdução da fonte.
20. A fonte será informada automaticamente pelo sistema após a matéria. Não precisa criar uma seção de fonte.

FONTE PRINCIPAL: {noticia["fonte"]}
URL PRINCIPAL: {noticia["url"]}
TÍTULO ORIGINAL: {noticia["titulo"]}

CONTEÚDO DA FONTE PRINCIPAL:
{noticia["texto"]}

PESQUISA SECUNDÁRIA DISPONÍVEL:
{contexto_formatado}
"""

    try:

        try:
            resposta = chamar_gemini_com_retry(client, prompt)
        except Exception as erro:
            print(
                f"Gemini indisponível nesta execução: {erro}"
            )
            return None

        if resposta is None:
            print("Gemini não retornou resposta.")
            return None

        bruto = (
            resposta.text
            or ""
        ).strip()


        print(
            f"Resposta do Gemini: "
            f"{len(bruto)} caracteres"
        )


        # ----------------------------------------------------
        # LIMPAR POSSÍVEL MARKDOWN
        # ----------------------------------------------------

        bruto = limpar_html_gemini(
            bruto
        )


        # ----------------------------------------------------
        # LOCALIZAR JSON
        # ----------------------------------------------------

        inicio = bruto.find(
            "{"
        )

        fim = bruto.rfind(
            "}"
        )

        if (
            inicio == -1
            or fim == -1
            or fim <= inicio
        ):

            print(
                "Gemini não retornou JSON válido."
            )

            return None


        bruto_json = bruto[
            inicio:fim + 1
        ]


        dados = json.loads(
            bruto_json
        )


        titulo = (
            str(
                dados.get(
                    "titulo",
                    ""
                )
            )
            .strip()
        )

        conteudo = (
            str(
                dados.get(
                    "conteudo",
                    ""
                )
            )
            .strip()
        )


        publicar = dados.get("publicar", True)
        if publicar is False:
            print("Gemini marcou a matéria como não publicável por falta de informação suficiente.")
            return None

        conteudo = limpar_html_gemini(conteudo)

        if not titulo:
            print("Gemini não retornou título próprio.")
            return None

        if not validar_materia_gerada(noticia, titulo, conteudo):
            return None


        print(
            f"Título novo: {titulo}"
        )

        print(
            f"Texto gerado: "
            f"{len(conteudo)} caracteres"
        )


        return {

            "titulo":
            titulo,

            "conteudo":
            conteudo,
        }


    except json.JSONDecodeError as erro:

        print(
            f"Erro ao interpretar JSON "
            f"do Gemini: {erro}"
        )

        print(
            "Usando título original "
            "não é suficiente: "
            "a matéria não será publicada."
        )

        return None


    except Exception as erro:

        mensagem = str(
            erro
        )

        print(
            f"Erro no Gemini: {mensagem}"
        )


        # ----------------------------------------------------
        # QUOTA 429
        # ----------------------------------------------------

        if (
            "429" in mensagem
            or "RESOURCE_EXHAUSTED"
            in mensagem
            or "quota" in mensagem.lower()
        ):

            print()
            print(
                "QUOTA DO GEMINI EXCEDIDA."
            )

            print(
                "A notícia não será publicada "
                "sem a geração da matéria."
            )

        return None


# ============================================================
# PUBLICAR NO BLOGGER
# ============================================================

def publicar_no_blogger(
    service,
    titulo,
    conteudo,
    noticia
):

    print()
    print(
        "Enviando notícia para Blogger..."
    )


    # --------------------------------------------------------
    # IMAGEM
    # --------------------------------------------------------

    bloco_imagem = ""

    if noticia.get(
        "imagem"
    ):

        bloco_imagem = f"""
<p>
<img src="{noticia["imagem"]}"
alt="{titulo}"
style="max-width:100%;height:auto;"
loading="lazy">
</p>
"""


    # --------------------------------------------------------
    # VÍDEOS
    # --------------------------------------------------------

    bloco_videos = ""

    for video_url in noticia.get("videos", []):

        bloco_videos += f"""
<p>
<iframe
src="{video_url}"
width="560"
height="315"
style="max-width:100%;width:100%;border:0;border-radius:12px;"
allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
allowfullscreen
loading="lazy">
</iframe>
</p>
"""

    # --------------------------------------------------------
    # CONTEÚDO FINAL
    # --------------------------------------------------------

    conteudo_final = f"""
{bloco_imagem}

{bloco_videos}

{conteudo}

<hr>

<p>
<strong>Fonte:</strong>
{noticia["fonte"]}
</p>

"""


    corpo = {

        "kind":
        "blogger#post",

        "title":
        titulo,

        "content":
        conteudo_final,

        "labels": [
            BOT_LABEL
        ],
    }


    try:

        resposta = (
            service.posts()
            .insert(
                blogId=BLOGGER_BLOG_ID,
                body=corpo,
                isDraft=BLOGGER_DRAFT,
            )
            .execute()
        )


        if BLOGGER_DRAFT:

            print(
                "RASCUNHO CRIADO COM SUCESSO!"
            )

        else:

            print(
                "PUBLICAÇÃO REALIZADA "
                "COM SUCESSO!"
            )


        print(
            f"Título: "
            f"{resposta.get('title')}"
        )

        print(
            f"ID: "
            f"{resposta.get('id')}"
        )

        print(
            f"URL: "
            f"{resposta.get('url')}"
        )


        if noticia.get(
            "imagem"
        ):

            print(
                "Imagem original da notícia adicionada à postagem: SIM"
            )

        else:

            print(
                "Imagem original da notícia adicionada à postagem: NÃO"
            )

        if noticia.get("videos"):

            print(
                f"Vídeos adicionados à postagem: {len(noticia['videos'])}"
            )

        else:

            print(
                "Vídeos adicionados à postagem: 0"
            )


        return True


    except Exception as erro:

        print(
            "Erro ao enviar para Blogger: "
            f"{erro}"
        )

        return False


# ============================================================
# PRINCIPAL
# ============================================================

def main():

    print()
    print(
        "=" * 60
    )

    print(
        "RÁDIO LUZ GOSPEL - "
        "ROBÔ DE NOTÍCIAS 3.5"
    )

    print(
        "Modo: "
        + (
            "RASCUNHO"
            if BLOGGER_DRAFT
            else "PUBLICAÇÃO AUTOMÁTICA"
        )
    )

    print(
        f"Fontes configuradas: "
        f"{len(FONTES)}"
    )

    print(
        "=" * 60
    )


    service = conectar_blogger()

    # --------------------------------------------------------
    # PROTEÇÃO DE COTA DIÁRIA
    # --------------------------------------------------------

    if limite_diario_atingido(service):
        print()
        print(
            "ROBÔ FINALIZADO SEM CONSULTAR O GEMINI."
        )
        return

    # --------------------------------------------------------
    # TESTAR CADA FONTE
    # --------------------------------------------------------

    for fonte in FONTES:

        print()
        print(
            "=" * 60
        )

        print(
            f"FONTE: {fonte['nome']}"
        )

        print(
            "=" * 60
        )


        html = acessar_url(
            fonte["url"]
        )


        if not html:

            print(
                "Não foi possível "
                "acessar a fonte."
            )

            continue


        links = encontrar_links(
            fonte,
            html
        )


        if not links:

            print(
                "Nenhum link válido "
                "encontrado nesta fonte."
            )

            continue


        candidatos = links[
            :MAX_LINKS_PER_SOURCE
        ]


        print(
            f"Analisando "
            f"{len(candidatos)} "
            f"candidatos..."
        )


        # ----------------------------------------------------
        # ANALISAR CANDIDATOS
        # ----------------------------------------------------

        for url in candidatos:

            noticia = extrair_noticia(
                fonte,
                url
            )


            if not noticia:
                continue


            print()
            print(
                "Verificando duplicidade..."
            )


            if noticia_ja_existe(
                service,
                noticia["titulo"],
                noticia["url"],
            ):

                print(
                    "Notícia já publicada. "
                    "Pulando."
                )

                continue


            print(
                "Notícia nova."
            )


            # ------------------------------------------------
            # GEMINI - UMA ÚNICA CHAMADA
            # ------------------------------------------------

            resultado_gemini = (
                gerar_conteudo_com_gemini(
                    noticia
                )
            )


            if not resultado_gemini:

                print(
                    "Não foi possível "
                    "gerar a matéria."
                )

                print(
                    "O robô NÃO tentará outro candidato "
                    "nesta execução para preservar a cota "
                    "do Gemini."
                )

                print(
                    "ROBÔ FINALIZADO SEM PUBLICAÇÃO."
                )

                return


            titulo = resultado_gemini[
                "titulo"
            ]

            conteudo_gerado = (
                resultado_gemini[
                    "conteudo"
                ]
            )


            # ------------------------------------------------
            # REVISÃO FINAL DE ORIGINALIDADE
            # ------------------------------------------------

            if postagem_muito_parecida(
                service,
                titulo,
                conteudo_gerado,
            ):
                print(
                    "Publicação cancelada: conteúdo muito parecido com matéria já publicada."
                )
                return

            # ------------------------------------------------
            # IMAGEM ORIGINAL DA NOTÍCIA
            # ------------------------------------------------

            url_imagem = noticia.get("imagem")

            if url_imagem:
                print("🖼️ Usando a imagem original da notícia.")
            else:
                print("⚠️ Notícia sem imagem original. Publicação cancelada.")
                return

            # ------------------------------------------------
            # BLOGGER
            # ------------------------------------------------

            sucesso = (
                publicar_no_blogger(
                    service,
                    titulo,
                    conteudo_gerado,
                    noticia,
                )
            )


            if sucesso:

                print()
                print(
                    "ROBÔ FINALIZADO "
                    "COM SUCESSO."
                )

                return


        print()
        print(
            f"Nenhuma notícia nova "
            f"publicada na fonte "
            f"{fonte['nome']}."
        )


    # --------------------------------------------------------
    # NENHUMA NOTÍCIA
    # --------------------------------------------------------

    print()
    print(
        "Nenhuma notícia nova "
        "foi encontrada."
    )

    print(
        "ROBÔ FINALIZADO."
    )


# ============================================================
# EXECUTAR
# ============================================================

if __name__ == "__main__":

    main()
