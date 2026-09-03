import os
import re
import json
import difflib
import requests

from bs4 import BeautifulSoup
from datetime import datetime, timedelta

from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS
# VERSÃO 2.6
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
gemini_calls_this_run = 0

# Limites de proteção contra excesso de uso do Gemini e publicações.
MAX_GEMINI_CALLS_PER_RUN = 1
MAX_POSTS_PER_DAY = 3

# Identificação das publicações feitas pelo robô.
BOT_LABEL = "Radio Luz Gospel Bot"


# False = publicação automática
# True = cria rascunho
BLOGGER_DRAFT = False


# Quantos links serão analisados por fonte
MAX_LINKS_PER_SOURCE = 10


# Notícias com mais de 30 dias serão ignoradas
MAX_AGE_DAYS = 30


TIMEOUT = 25

# Qualidade editorial e originalidade.
MIN_SOURCE_CHARS = 700
MIN_SOURCE_PARAGRAPHS = 4
MIN_GENERATED_CHARS = 1000
MAX_SOURCE_OVERLAP = 0.12
MAX_TITLE_SIMILARITY = 0.82
MAX_POST_SIMILARITY = 0.36
MAX_CONTEXT_ARTICLES = 2
MAX_CONTEXT_CHARS = 2500


# ============================================================
# FONTES
# ============================================================

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

    return (
        dominio_url
        == dominio
    )


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
    # FUXICO
    # --------------------------------------------------------

    if (
        fonte["nome"]
        == "Fuxico Gospel"
    ):

        if len(partes) < 2:
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
    data
):

    if not data:

        print(
            "Data não identificada."
        )

        print(
            "Aceitando para análise."
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
        data
    ):
        return None


    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    titulo = None

    h1 = soup.find(
        "h1"
    )

    if h1:

        titulo = h1.get_text(
            " ",
            strip=True
        )

    if not titulo:

        titulo_tag = soup.find(
            "title"
        )

        if titulo_tag:

            titulo = titulo_tag.get_text(
                " ",
                strip=True
            )

    if not titulo:

        print(
            "Título não encontrado."
        )

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

    if len(texto) < 500:

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

    if len(paragrafos) < MIN_SOURCE_PARAGRAPHS:
        print(
            "Fonte insuficiente: "
            f"apenas {len(paragrafos)} parágrafos úteis."
        )
        return None

    if len(texto) < MIN_SOURCE_CHARS:
        print(
            "Texto insuficiente: "
            f"{len(texto)} caracteres."
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

        "data":
        data,
    }


# ============================================================
# FERRAMENTAS DE PESQUISA E ORIGINALIDADE
# ============================================================

STOPWORDS = {
    "a", "o", "e", "de", "do", "da", "dos", "das", "em", "no", "na",
    "nos", "nas", "um", "uma", "uns", "umas", "para", "por", "com",
    "sem", "que", "se", "ao", "aos", "à", "às", "como", "mais", "menos",
    "sobre", "entre", "após", "antes", "durante", "já", "também", "foi",
    "ser", "são", "é", "tem", "teve", "ter", "pelo", "pela", "pelos",
    "pelas", "seu", "sua", "seus", "suas", "este", "esta", "esse", "essa",
    "isso", "ele", "ela", "eles", "elas", "ou", "até",
}

def palavras_relevantes(texto):
    palavras = re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", (texto or "").lower())
    return [p for p in palavras if p not in STOPWORDS]


def similaridade_textual(texto_a, texto_b):
    a = normalizar_texto(BeautifulSoup(texto_a or "", "html.parser").get_text(" ", strip=True))
    b = normalizar_texto(BeautifulSoup(texto_b or "", "html.parser").get_text(" ", strip=True))
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def sobreposicao_ngram(texto_a, texto_b, n=6):
    a = re.findall(r"[a-zà-ÿ0-9]+", normalizar_texto(BeautifulSoup(texto_a or "", "html.parser").get_text(" ", strip=True)))
    b = re.findall(r"[a-zà-ÿ0-9]+", normalizar_texto(BeautifulSoup(texto_b or "", "html.parser").get_text(" ", strip=True)))
    if len(a) < n or len(b) < n:
        return 0.0
    conjunto_a = {" ".join(a[i:i+n]) for i in range(len(a)-n+1)}
    conjunto_b = {" ".join(b[i:i+n]) for i in range(len(b)-n+1)}
    return len(conjunto_a & conjunto_b) / len(conjunto_a) if conjunto_a else 0.0


def possui_frase_copiada(texto_gerado, texto_fonte, tamanho=8):
    a = re.findall(r"[a-zà-ÿ0-9]+", normalizar_texto(BeautifulSoup(texto_gerado or "", "html.parser").get_text(" ", strip=True)))
    b = re.findall(r"[a-zà-ÿ0-9]+", normalizar_texto(BeautifulSoup(texto_fonte or "", "html.parser").get_text(" ", strip=True)))
    if len(a) < tamanho or len(b) < tamanho:
        return False
    fonte = {" ".join(b[i:i+tamanho]) for i in range(len(b)-tamanho+1)}
    return any(" ".join(a[i:i+tamanho]) in fonte for i in range(len(a)-tamanho+1))


def validar_materia_gerada(noticia, resultado):
    if not resultado:
        return False
    titulo = str(resultado.get("titulo", "")).strip()
    conteudo = str(resultado.get("conteudo", "")).strip()
    if not titulo or not conteudo:
        print("Revisão editorial: título ou conteúdo ausente.")
        return False
    texto_gerado = BeautifulSoup(conteudo, "html.parser").get_text(" ", strip=True)
    texto_fonte = noticia.get("texto", "")
    if len(texto_gerado) < MIN_GENERATED_CHARS:
        print("Revisão editorial: matéria gerada muito curta.")
        return False
    paragrafos = BeautifulSoup(conteudo, "html.parser").find_all("p")
    if len(paragrafos) < 4:
        print("Revisão editorial: poucos parágrafos.")
        return False
    similaridade_titulo = similaridade_textual(titulo, noticia["titulo"])
    if normalizar_texto(titulo) == normalizar_texto(noticia["titulo"]) or similaridade_titulo >= MAX_TITLE_SIMILARITY:
        print("Revisão editorial: título muito parecido com o original.")
        return False
    sobreposicao = sobreposicao_ngram(texto_gerado, texto_fonte, n=6)
    if sobreposicao > MAX_SOURCE_OVERLAP:
        print(f"Revisão editorial: sobreposição excessiva com a fonte ({sobreposicao:.1%}).")
        return False
    if possui_frase_copiada(texto_gerado, texto_fonte, tamanho=8):
        print("Revisão editorial: frase longa em comum com a fonte. Publicação bloqueada.")
        return False
    if similaridade_textual(texto_gerado, texto_fonte) >= 0.72:
        print("Revisão editorial: texto aparenta ser reformulação mecânica da fonte.")
        return False
    print("Revisão editorial: OK - texto considerado original.")
    return True


def postagem_muito_parecida(service, titulo, conteudo):
    titulo_normalizado = normalizar_texto(titulo)
    posts = buscar_posts(service, "LIVE") + buscar_posts(service, "DRAFT")
    for post in posts:
        titulo_existente = post.get("title", "")
        conteudo_existente = post.get("content", "")
        if titulo_normalizado == normalizar_texto(titulo_existente):
            print("Revisão de duplicidade: título já utilizado.")
            return True
        if similaridade_textual(titulo, titulo_existente) >= 0.88:
            print("Revisão de duplicidade: títulos muito parecidos.")
            return True
        if sobreposicao_ngram(conteudo, conteudo_existente, n=6) >= MAX_POST_SIMILARITY:
            print("Revisão de duplicidade: conteúdo muito parecido.")
            return True
    return False


def encontrar_contexto_relacionado(titulo, fonte_principal, html):
    soup = BeautifulSoup(html, "html.parser")
    palavras = set(palavras_relevantes(titulo))
    candidatos = []
    vistos = set()
    for a in soup.find_all("a", href=True):
        url = normalizar_url(fonte_principal, a.get("href", ""))
        if not url or not link_valido(fonte_principal, url) or url in vistos:
            continue
        vistos.add(url)
        texto_link = a.get_text(" ", strip=True)
        score = len(palavras.intersection(palavras_relevantes(texto_link + " " + url)))
        if score > 0:
            candidatos.append((score, url))
    candidatos.sort(key=lambda item: item[0], reverse=True)
    return [url for _, url in candidatos[:4]]


def coletar_contexto_verificado(noticia):
    contexto = []
    for fonte in FONTES:
        if fonte["nome"] == noticia["fonte"]:
            continue
        html = acessar_url(fonte["url"])
        if not html:
            continue
        urls = encontrar_contexto_relacionado(noticia["titulo"], fonte, html)
        for url in urls:
            relacionada = extrair_noticia(fonte, url)
            if not relacionada:
                continue
            texto = relacionada.get("texto", "")
            if len(texto) < 500:
                continue
            contexto.append({
                "fonte": relacionada["fonte"],
                "titulo": relacionada["titulo"],
                "url": relacionada["url"],
                "texto": texto[:MAX_CONTEXT_CHARS],
            })
            if len(contexto) >= MAX_CONTEXT_ARTICLES:
                return contexto
    return contexto


# ============================================================
# GERAR TÍTULO + MATÉRIA COM UMA ÚNICA CHAMADA
# ============================================================

def gerar_conteudo_com_gemini(
    noticia
):

    global gemini_calls_this_run

    if gemini_calls_this_run >= MAX_GEMINI_CALLS_PER_RUN:
        print()
        print(
            "Limite de chamadas Gemini desta execução atingido."
        )
        return None

    gemini_calls_this_run += 1

    print()
    print(
        "Gerando título e matéria com Gemini..."
    )

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )


    contexto = coletar_contexto_verificado(noticia)

    bloco_contexto = "NENHUMA FONTE SECUNDÁRIA RELEVANTE FOI ENCONTRADA."
    if contexto:
        partes_contexto = []
        for item in contexto:
            partes_contexto.append(
                f"""
FONTE SECUNDÁRIA: {item["fonte"]}
TÍTULO: {item["titulo"]}
URL: {item["url"]}
INFORMAÇÕES:
{item["texto"]}
"""
            )
        bloco_contexto = "\n".join(partes_contexto)

    prompt = f"""
Você é um jornalista profissional especializado em notícias do meio gospel brasileiro.

Sua tarefa NÃO é resumir nem parafrasear mecanicamente uma notícia.
Faça este processo: FONTE → PESQUISA → APURAÇÃO/CONTEXTUALIZAÇÃO → REDAÇÃO ORIGINAL → REVISÃO → PUBLICAÇÃO.

A notícia principal é a fonte de partida. As fontes secundárias servem para CONFERIR e COMPLEMENTAR quando houver correspondência clara.

REGRAS DE APURAÇÃO:
1. Use somente fatos sustentados pelas informações fornecidas.
2. Não invente fatos, nomes, datas, números, cargos, declarações ou acontecimentos.
3. Só acrescente contexto de fontes secundárias quando ele realmente se relacionar ao mesmo assunto.
4. Não misture pessoas ou acontecimentos diferentes.
5. Se não houver informação suficiente para uma matéria segura, retorne "publicar": false.
6. Se as fontes forem contraditórias ou insuficientes, retorne "publicar": false.
7. Não preencha lacunas com conhecimento presumido.

REGRAS DE ORIGINALIDADE:
1. Crie título totalmente próprio, sem copiar a estrutura do original.
2. Crie introdução própria, com outro encadeamento de ideias.
3. Reescreva completamente a notícia.
4. NÃO copie frases, períodos ou sequência de parágrafos.
5. NÃO faça simples substituição de palavras nem tradução.
6. NÃO mantenha a mesma ordem da fonte quando isso não for necessário.
7. Evite repetir expressões características do texto original.
8. O texto deve parecer escrito originalmente para a Rádio Luz Gospel.
9. Não reproduza citações longas.

REGRAS DE CONTEXTUALIZAÇÃO:
1. Explique por que o fato é relevante para o leitor.
2. Acrescente contexto factual somente quando as fontes permitirem.
3. Quando não houver contexto adicional confiável, não invente.

REGRAS DO TÍTULO:
1. Jornalístico, claro, atrativo e original.
2. Sem clickbait e sem informação inventada.
3. Sem emojis e sem ponto final.

REGRAS DA MATÉRIA:
1. Português do Brasil natural.
2. Aproximadamente 450 a 650 palavras quando houver informação suficiente.
3. Introdução própria, desenvolvimento contextualizado e conclusão informativa.
4. HTML simples, somente <p> e, se necessário, <h2>.
5. Não coloque links externos no meio da matéria.
6. Não coloque a fonte dentro do conteúdo; o sistema adicionará a identificação.
7. Não utilize markdown.

REVISÃO ANTES DE RESPONDER:
- Título realmente diferente do original?
- Introdução realmente própria?
- Matéria reorganizada e reescrita, e não apenas parafraseada?
- Contexto útil quando disponível?
- Todos os fatos sustentados pelas fontes?
- Alguma frase longa copiada?
- Texto parece tradução ou reformulação mecânica?
- Há informação suficiente para publicação?
Se qualquer resposta for negativa, retorne "publicar": false.

RETORNE SOMENTE JSON VÁLIDO:
{{
  "publicar": true,
  "titulo": "título jornalístico original",
  "conteudo": "<p>introdução própria...</p><p>desenvolvimento...</p>"
}}

Se não houver informação suficiente:
{{
  "publicar": false,
  "titulo": "",
  "conteudo": ""
}}

FONTE PRINCIPAL:
{noticia["fonte"]}

URL ORIGINAL:
{noticia["url"]}

TÍTULO ORIGINAL:
{noticia["titulo"]}

CONTEÚDO ORIGINAL:
{noticia["texto"][:10000]}

PESQUISA/CONTEXTUALIZAÇÃO VERIFICADA:
{bloco_contexto}
"""

    try:

        resposta = (
            client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
            )
        )

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


        if dados.get("publicar", True) is False:
            print(
                "Gemini marcou a notícia como insuficiente "
                "ou sem segurança para publicação."
            )
            return None

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


        # ----------------------------------------------------
        conteudo = limpar_html_gemini(
            conteudo
        )


        if len(conteudo) < 300:

            print(
                "Conteúdo gerado muito curto."
            )

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
    # CONTEÚDO FINAL
    # --------------------------------------------------------

    conteudo_final = f"""
{bloco_imagem}

{conteudo}

<hr>

<p>
<strong>Fonte:</strong>
{noticia["fonte"]}
</p>

<p>
<strong>Notícia original:</strong>
<a href="{noticia["url"]}"
target="_blank"
rel="noopener">
{noticia["url"]}
</a>
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
                "Imagem adicionada à postagem: SIM"
            )

        else:

            print(
                "Imagem adicionada à postagem: NÃO"
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
        "ROBÔ DE NOTÍCIAS 2.6"
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
            # REVISÃO DE ORIGINALIDADE E QUALIDADE
            # ------------------------------------------------
            if not validar_materia_gerada(
                noticia,
                resultado_gemini
            ):
                print(
                    "A matéria foi reprovada na revisão "
                    "automática de originalidade/qualidade."
                )
                print(
                    "O robô NÃO tentará outro candidato "
                    "nesta execução."
                )
                return

            # ------------------------------------------------
            # REVISÃO CONTRA PUBLICAÇÕES SEMELHANTES
            # ------------------------------------------------
            if postagem_muito_parecida(
                service,
                titulo,
                conteudo_gerado
            ):
                print(
                    "Publicação bloqueada para evitar "
                    "notícias praticamente iguais."
                )
                print(
                    "ROBÔ FINALIZADO SEM PUBLICAÇÃO."
                )
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
