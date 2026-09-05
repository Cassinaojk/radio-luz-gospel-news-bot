import os
import re
import json
import time
import requests
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS
# VERSÃO 3.7 - EDITORIAL ADSENSE + IMAGEM ORIGINAL + FILTRO DE NOTÍCIAS + GOSPEL+
# ============================================================

BLOGGER_BLOG_ID = os.environ["BLOGGER_BLOG_ID"]
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

MAX_POSTS_PER_DAY = 3
MAX_GEMINI_TEXT_CALLS_PER_RUN = 1
MAX_LINKS_PER_SOURCE = 50
MAX_AGE_DAYS = 30

MIN_SOURCE_CHARS = 700
MIN_SOURCE_PARAGRAPHS = 4
MIN_GENERATED_CHARS = 1000

MAX_POST_SIMILARITY = 0.38
MAX_TITLE_SIMILARITY = 0.82

BOT_LABEL = "Radio Luz Gospel Bot"
BLOGGER_DRAFT = False

GEMINI_MODEL_TEXT = "gemini-3.6-flash"
GEMINI_MODEL_TEXT_FALLBACK = "gemini-3.5-flash-lite"

gemini_calls = 0


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
# FUNÇÕES BÁSICAS
# ============================================================

def norm(texto):
    return re.sub(
        r"\s+",
        " ",
        texto or ""
    ).strip().lower()


def words(texto):
    return re.findall(
        r"\b[\wÀ-ÿ]{3,}\b",
        norm(texto)
    )


def similar(a, b):
    return SequenceMatcher(
        None,
        norm(a),
        norm(b)
    ).ratio()


def text_clean(texto):
    return re.sub(
        r"\s+",
        " ",
        BeautifulSoup(
            texto or "",
            "html.parser"
        ).get_text(
            " ",
            strip=True
        )
    ).strip()


# ============================================================
# BLOGGER
# ============================================================

def blogger():

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

    return build(
        "blogger",
        "v3",
        credentials=credentials
    )


def posts(service, status):

    try:

        return (
            service.posts()
            .list(
                blogId=BLOGGER_BLOG_ID,
                status=status,
                maxResults=100
            )
            .execute()
            .get(
                "items",
                []
            )
        )

    except Exception as erro:

        print(
            f"Erro ao buscar posts {status}: {erro}"
        )

        return []


def count_today(service):

    hoje = datetime.now().date()

    total = 0

    for status in (
        "LIVE",
        "DRAFT"
    ):

        for post in posts(
            service,
            status
        ):

            if BOT_LABEL not in post.get(
                "labels",
                []
            ):
                continue

            data = (
                post.get("published")
                or post.get("updated")
                or ""
            )

            try:

                data = datetime.fromisoformat(
                    data.replace(
                        "Z",
                        "+00:00"
                    )
                ).replace(
                    tzinfo=None
                )

                if data.date() == hoje:
                    total += 1

            except Exception:
                pass

    return total


def exists(
    service,
    titulo,
    url
):

    titulo = norm(titulo)

    for status in (
        "LIVE",
        "DRAFT"
    ):

        for post in posts(
            service,
            status
        ):

            titulo_existente = norm(
                post.get(
                    "title",
                    ""
                )
            )

            conteudo = post.get(
                "content",
                ""
            )

            if titulo == titulo_existente:
                return True

            if url and url in conteudo:
                return True

    return False


# ============================================================
# ACESSO À INTERNET
# ============================================================

def request_headers():

    return {

        "User-Agent":
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36",

        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8",

        "Accept-Language":
            "pt-BR,pt;q=0.9,en;q=0.8",

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache",
    }


def get(
    url,
    tries=2
):

    for tentativa in range(
        tries
    ):

        try:

            resposta = requests.get(
                url,
                headers=request_headers(),
                timeout=25,
                allow_redirects=True
            )

            print(
                f"HTTP: {resposta.status_code}"
            )

            if resposta.status_code == 200:
                return resposta.text

            if (
                resposta.status_code
                in {
                    403,
                    429,
                    500,
                    502,
                    503,
                    504
                }
                and tentativa + 1 < tries
            ):

                time.sleep(1.5)
                continue

            return None

        except Exception as erro:

            print(
                f"Erro ao acessar fonte: {erro}"
            )

            if tentativa + 1 < tries:
                time.sleep(1)

    return None


# ============================================================
# GOSPEL+
# ============================================================

def gospel_get(url):

    html = get(url)

    if html:
        return html

    if "gospelmais.com" not in url.lower():
        return None

    parsed = urlparse(url)

    caminho = parsed.path or "/"

    dominios = [
        "gospelmais.com",
        "www.gospelmais.com",
        "noticias.gospelmais.com"
    ]

    for dominio in dominios:

        alternativa = (
            f"https://{dominio}"
            f"{caminho}"
        )

        if alternativa == url:
            continue

        print(
            "Tentando domínio alternativo "
            f"do Gospel+: {alternativa}"
        )

        html = get(
            alternativa,
            tries=1
        )

        if html:
            return html

    return None


# ============================================================
# DOMÍNIO
# ============================================================

def site_ok(
    fonte,
    url
):

    dominio_fonte = (
        urlparse(
            fonte["url"]
        )
        .netloc
        .lower()
    )

    dominio_url = (
        urlparse(
            url
        )
        .netloc
        .lower()
    )

    if fonte["nome"] == "Gospel+":

        return dominio_url in {
            "gospelmais.com",
            "www.gospelmais.com",
            "noticias.gospelmais.com"
        }

    return dominio_url == dominio_fonte


# ============================================================
# FILTROS
# ============================================================

BLOQUEADOS = {

    "ultimas-noticias",
    "últimas-notícias",

    "quem-somos",
    "sobre",

    "fale-conosco",
    "contato",
    "contact",

    "politica-de-privacidade",
    "política-de-privacidade",

    "politica-de-uso-e-privacidade",
    "política-de-uso-e-privacidade",

    "privacy",
    "privacy-policy",

    "politica-editorial",
    "política-editorial",

    "termos-de-uso",
    "termos",

    "anuncie-aqui",
    "anuncie",
    "publicidade",
    "anuncie-no-site",

    "parceiros",
    "parceria",

    "expediente",

    "redacao",
    "redação",

    "newsletter",

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

    "podcast",
    "podcasts",

    "videos",
    "video",

    "home",

    "arquivo",
    "arquivos"
}


NAO_NOTICIA = {

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
    "arquivo",
    "arquivos",
    "date"
}


def valid(
    fonte,
    url
):

    if not url:
        return False

    if not site_ok(
        fonte,
        url
    ):
        return False

    parsed = urlparse(url)

    caminho = parsed.path.strip("/")

    partes = [
        x
        for x in caminho.split("/")
        if x
    ]

    if not partes:
        return False

    ultimo = partes[-1].lower()

    if fonte["nome"] == "News Gospel":

        return bool(
            re.match(
                r"^/\d{4}/\d{2}/.+\.html$",
                parsed.path
            )
        )

    if (
        fonte["nome"] == "UAU Gospel"
        and partes[0].lower()
        in NAO_NOTICIA
    ):
        return False

    if ultimo in BLOQUEADOS:
        return False

    caminho_lower = caminho.lower()

    for trecho in (
        "/wp-login",
        "/wp-admin",
        "/feed/",
        "/rss/",
        "/page/"
    ):

        if trecho in caminho_lower:
            return False

    return True


# ============================================================
# LINKS
# ============================================================

def links_from_html(
    fonte,
    html
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    resultado = []

    vistos = set()

    for a in soup.find_all(
        "a",
        href=True
    ):

        url = urljoin(
            fonte["url"],
            a["href"]
        )

        url = url.split(
            "#",
            1
        )[0].rstrip("/")

        if (
            valid(
                fonte,
                url
            )
            and url not in vistos
        ):

            vistos.add(url)
            resultado.append(url)

    return resultado


def feed_links(fonte):

    if fonte["nome"] == "UAU Gospel":

        bases = [

            fonte["url"],

            "https://www.uaugospel.com.br/feed/",

            "https://www.uaugospel.com.br/"
            "wp-json/wp/v2/posts?per_page=50"
        ]

    elif fonte["nome"] == "News Gospel":

        bases = [

            fonte["url"],

            "https://www.newsgospel.com.br/feed/"
        ]

    else:

        bases = [

            fonte["url"],

            "https://gospelmais.com/feed/",

            "https://www.gospelmais.com/feed/",

            "https://noticias.gospelmais.com/feed/"
        ]

    resultado = []

    vistos = set()

    for base in bases:

        if fonte["nome"] == "Gospel+":

            html = gospel_get(base)

        else:

            html = get(
                base,
                tries=1
            )

        if not html:
            continue

        if "wp-json/wp/v2/posts" in base:

            try:

                data = json.loads(
                    html
                )

                for item in data:

                    url = item.get(
                        "link"
                    )

                    if (
                        url
                        and valid(
                            fonte,
                            url
                        )
                        and url not in vistos
                    ):

                        vistos.add(url)
                        resultado.append(url)

                continue

            except Exception:
                pass

        soup = BeautifulSoup(
            html,
            "xml"
        )

        for item in soup.find_all(
            [
                "link",
                "loc"
            ]
        ):

            url = item.get_text(
                "",
                strip=True
            )

            if (
                valid(
                    fonte,
                    url
                )
                and url not in vistos
            ):

                vistos.add(url)
                resultado.append(url)

    return resultado


def candidates(
    fonte,
    home
):

    resultado = []

    vistos = set()

    for url in feed_links(
        fonte
    ) + links_from_html(
        fonte,
        home
    ):

        if (
            url not in vistos
            and valid(
                fonte,
                url
            )
        ):

            vistos.add(url)
            resultado.append(url)

    return resultado[
        :MAX_LINKS_PER_SOURCE
    ]


# ============================================================
# DATA
# ============================================================

def date_from(
    soup
):

    valores = []

    seletores = [

        (
            "meta[property='article:published_time']",
            "content"
        ),

        (
            "meta[property='article:modified_time']",
            "content"
        ),

        (
            "meta[name='date']",
            "content"
        ),

        (
            "time",
            "datetime"
        )
    ]

    for seletor, atributo in seletores:

        for item in soup.select(
            seletor
        ):

            valor = item.get(
                atributo
            )

            if valor:
                valores.append(valor)

    for valor in valores:

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

        match = re.search(
            r"(20\d{2})[-/]([01]\d)[-/]([0-3]\d)",
            valor
        )

        if match:

            try:

                return datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3))
                )

            except Exception:
                pass

    return None


def recent(
    data,
    url=""
):

    if not data:

        return bool(
            re.search(
                r"/20\d{2}/[01]\d/",
                url
            )
        )

    idade = (
        datetime.now()
        - data
    )

    return idade <= timedelta(
        days=MAX_AGE_DAYS
    )


# ============================================================
# IMAGEM
# ============================================================

def image_of(
    soup
):

    seletores = [

        (
            "meta[property='og:image']",
            "content"
        ),

        (
            "meta[name='twitter:image']",
            "content"
        )
    ]

    for seletor, atributo in seletores:

        item = soup.select_one(
            seletor
        )

        if (
            item
            and item.get(atributo)
        ):

            return item.get(
                atributo
            ).strip()

    for img in soup.find_all(
        "img"
    ):

        url = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-lazy-src")
        )

        if (
            url
            and not url.startswith(
                "data:"
            )
        ):

            return url

    return None


# ============================================================
# VÍDEOS
# ============================================================

def videos_of(
    soup
):

    resultado = []

    vistos = set()

    for iframe in soup.find_all(
        "iframe",
        src=True
    ):

        url = iframe[
            "src"
        ].strip()

        if not any(
            dominio in url.lower()
            for dominio in (
                "youtube.com",
                "youtu.be",
                "vimeo.com"
            )
        ):
            continue

        if url in vistos:
            continue

        vistos.add(url)

        resultado.append(
            url
        )

    return resultado[:3]


# ============================================================
# EXTRAIR NOTÍCIA
# ============================================================

def extract(
    fonte,
    url
):

    if fonte["nome"] == "Gospel+":

        html = gospel_get(
            url
        )

    else:

        html = get(
            url
        )

    if not html:
        return None

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    data = date_from(
        soup
    )

    print(
        f"Data encontrada: {data}"
    )

    if not recent(
        data,
        url
    ):

        print(
            "Notícia antiga. Pulando."
        )

        return None

    titulo = ""

    for seletor in (
        "meta[property='og:title']",
        "meta[name='twitter:title']"
    ):

        item = soup.select_one(
            seletor
        )

        if (
            item
            and item.get("content")
        ):

            titulo = item[
                "content"
            ].strip()

            break

    if not titulo:

        for tag in (
            "h1",
            "h2",
            "h3",
            "title"
        ):

            item = soup.find(
                tag
            )

            if item:

                titulo = text_clean(
                    item.get_text()
                )

                if titulo:
                    break

    if not titulo:
        return None

    principal = (
        soup.find("article")
        or soup.find("main")
        or soup.body
    )

    if not principal:
        return None

    for item in principal.find_all(
        [
            "script",
            "style",
            "nav",
            "header",
            "footer",
            "aside",
            "form"
        ]
    ):

        item.decompose()

    paragrafos = []

    for p in principal.find_all(
        "p"
    ):

        texto = text_clean(
            p.get_text(
                " ",
                strip=True
            )
        )

        if len(texto) >= 45:
            paragrafos.append(
                texto
            )

    texto = "\n".join(
        paragrafos
    )

    if (
        len(texto)
        < MIN_SOURCE_CHARS
        or len(paragrafos)
        < MIN_SOURCE_PARAGRAPHS
    ):

        print(
            "Conteúdo insuficiente. Pulando."
        )

        return None

    imagem = image_of(
        soup
    )

    if not imagem:

        print(
            "Sem imagem original. Pulando."
        )

        return None

    imagem = urljoin(
        url,
        imagem
    )

    return {

        "fonte":
            fonte["nome"],

        "url":
            url,

        "titulo":
            titulo,

        "texto":
            texto[:12000],

        "imagem":
            imagem,

        "videos":
            videos_of(soup),

        "data":
            data
    }


# ============================================================
# GEMINI
# ============================================================

def prompt(noticia):

    return f"""
Você é editor de notícias para um blog gospel brasileiro.

Reescreva a notícia abaixo de forma jornalística, original e adequada ao Google AdSense.

NÃO copie frases longas da fonte.

NÃO invente fatos, nomes, datas, números ou declarações.

Use somente informações presentes no texto fornecido.

Gere JSON válido com exatamente estas chaves:

"titulo"
"conteudo"

O conteúdo deve ser HTML simples.

Use:
<p>
<h2> quando necessário

Não use Markdown.

O conteúdo deve ter pelo menos 1000 caracteres.

O título deve ser informativo e diferente do título original.

FONTE:
{noticia["fonte"]}

TÍTULO ORIGINAL:
{noticia["titulo"]}

URL:
{noticia["url"]}

TEXTO ORIGINAL:

{noticia["texto"]}
"""


def gemini(
    noticia
):

    global gemini_calls

    if (
        gemini_calls
        >= MAX_GEMINI_TEXT_CALLS_PER_RUN
    ):

        print(
            "Limite de chamadas Gemini atingido."
        )

        return None

    gemini_calls += 1

    try:

        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        resposta = (
            client.models.generate_content(
                model=GEMINI_MODEL_TEXT,
                contents=prompt(
                    noticia
                ),
                config={
                    "response_mime_type":
                        "application/json"
                }
            )
        )

        bruto = (
            resposta.text
            or ""
        ).strip()

        bruto = re.sub(
            r"^```json\s*|\s*```$",
            "",
            bruto,
            flags=re.IGNORECASE
        )

        dados = json.loads(
            bruto
        )

        titulo = text_clean(
            dados.get(
                "titulo"
            )
        )

        conteudo = dados.get(
            "conteudo",
            ""
        )

        if not titulo:
            return None

        if (
            len(
                text_clean(
                    conteudo
                )
            )
            < MIN_GENERATED_CHARS
        ):

            print(
                "Conteúdo gerado muito curto."
            )

            return None

        if (
            similar(
                titulo,
                noticia["titulo"]
            )
            >= MAX_TITLE_SIMILARITY
        ):

            print(
                "Título gerado muito parecido "
                "com o original."
            )

            return None

        return {

            "titulo":
                titulo,

            "conteudo":
                conteudo
        }

    except Exception as erro:

        print(
            f"Erro no Gemini: {erro}"
        )

        return None


# ============================================================
# VERIFICAÇÃO DE SIMILARIDADE
# ============================================================

def too_similar(
    service,
    titulo,
    conteudo
):

    for status in (
        "LIVE",
        "DRAFT"
    ):

        for post in posts(
            service,
            status
        ):

            titulo_antigo = post.get(
                "title",
                ""
            )

            if (
                similar(
                    titulo,
                    titulo_antigo
                )
                >= MAX_TITLE_SIMILARITY
            ):

                return True

            conteudo_antigo = text_clean(
                post.get(
                    "content",
                    ""
                )
            )

            if (
                len(conteudo_antigo)
                > 500
                and similar(
                    conteudo,
                    conteudo_antigo
                )
                >= MAX_POST_SIMILARITY
            ):

                return True

    return False


# ============================================================
# PUBLICAR
# ============================================================

def publish(
    service,
    noticia,
    resultado
):

    imagem = f"""
<p>
<img
src="{noticia["imagem"]}"
alt="{resultado["titulo"]}"
style="max-width:100%;height:auto;"
loading="lazy">
</p>
"""

    videos = ""

    for video in noticia[
        "videos"
    ]:

        videos += f"""
<p>
<iframe
src="{video}"
width="560"
height="315"
style="max-width:100%;width:100%;border:0;border-radius:12px;"
allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
allowfullscreen
loading="lazy">
</iframe>
</p>
"""

    conteudo_final = f"""
{imagem}

{videos}

{resultado["conteudo"]}

<hr>

<p>
<strong>Fonte:</strong>
{noticia["fonte"]}
</p>
"""

    corpo = {

        "title":
            resultado["titulo"],

        "content":
            conteudo_final,

        "labels": [
            BOT_LABEL
        ]
    }

    try:

        resposta = (
            service.posts()
            .insert(
                blogId=BLOGGER_BLOG_ID,
                body=corpo,
                isDraft=BLOGGER_DRAFT
            )
            .execute()
        )

        if BLOGGER_DRAFT:

            print(
                "RASCUNHO CRIADO COM SUCESSO!"
            )

        else:

            print(
                "PUBLICAÇÃO REALIZADA COM SUCESSO!"
            )

        print(
            f"Título: {resposta.get('title')}"
        )

        print(
            f"URL: {resposta.get('url')}"
        )

        print(
            "Imagem original da notícia "
            "adicionada à postagem: SIM"
        )

        print(
            f"Vídeos adicionados à postagem: "
            f"{len(noticia['videos'])}"
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

    print(
        "RÁDIO LUZ GOSPEL - "
        "ROBÔ DE NOTÍCIAS 3.7"
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

    print("=" * 60)

    service = blogger()

    total_hoje = count_today(
        service
    )

    print()
    print(
        f"Publicações do robô hoje: "
        f"{total_hoje}/{MAX_POSTS_PER_DAY}"
    )

    if total_hoje >= MAX_POSTS_PER_DAY:

        print(
            "Limite diário atingido."
        )

        print(
            "ROBÔ FINALIZADO."
        )

        return

    for fonte in FONTES:

        print()
        print("=" * 60)

        print(
            f"FONTE: {fonte['nome']}"
        )

        print("=" * 60)

        if fonte["nome"] == "Gospel+":

            home = gospel_get(
                fonte["url"]
            )

        else:

            home = get(
                fonte["url"]
            )

        if not home:

            print(
                "Não foi possível acessar a fonte."
            )

            continue

        urls = candidates(
            fonte,
            home
        )

        print(
            f"Analisando {len(urls)} candidatos..."
        )

        for url in urls:

            noticia = extract(
                fonte,
                url
            )

            if not noticia:
                continue

            print()
            print(
                "Verificando duplicidade..."
            )

            if exists(
                service,
                noticia["titulo"],
                noticia["url"]
            ):

                print(
                    "Notícia já publicada. Pulando."
                )

                continue

            print(
                "Notícia nova."
            )

            print(
                "Consultando Gemini..."
            )

            resultado = gemini(
                noticia
            )

            if not resultado:

                print(
                    "Não foi possível gerar a matéria."
                )

                print(
                    "ROBÔ FINALIZADO SEM PUBLICAÇÃO."
                )

                return

            if too_similar(
                service,
                resultado["titulo"],
                resultado["conteudo"]
            ):

                print(
                    "Publicação cancelada: "
                    "conteúdo muito parecido "
                    "com matéria já publicada."
                )

                return

            if not noticia.get(
                "imagem"
            ):

                print(
                    "Notícia sem imagem original."
                )

                print(
                    "Publicação cancelada."
                )

                return

            print(
                "Usando a imagem original da notícia."
            )

            sucesso = publish(
                service,
                noticia,
                resultado
            )

            if sucesso:

                print()
                print(
                    "ROBÔ FINALIZADO COM SUCESSO."
                )

                return

        print()
        print(
            f"Nenhuma notícia nova publicada "
            f"na fonte {fonte['nome']}."
        )

    print()
    print(
        "Nenhuma notícia nova foi encontrada."
    )

    print(
        "ROBÔ FINALIZADO."
    )


# ============================================================
# EXECUTAR
# ============================================================

if __name__ == "__main__":
    main()
