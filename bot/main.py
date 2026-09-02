import os
import re
import json
import requests

from bs4 import BeautifulSoup
from datetime import datetime, timedelta

from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS
# VERSÃO 2.5
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

    if len(texto) < 500:

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


    prompt = f"""
Você é um jornalista especializado
em notícias do meio gospel brasileiro.

Crie uma matéria jornalística original
em português do Brasil com base
EXCLUSIVAMENTE nas informações
fornecidas abaixo.

Você deverá retornar SOMENTE um JSON válido
com exatamente estes dois campos:

{{
  "titulo": "título jornalístico",
  "conteudo": "<p>primeiro parágrafo...</p><p>segundo parágrafo...</p>"
}}

REGRAS DO TÍTULO:

1. O título deve ser jornalístico.
2. Deve ser claro e atrativo.
3. Não invente informações.
4. Não invente nomes.
5. Não invente datas.
6. Não invente números.
7. Não use emojis.
8. Não coloque ponto final.
9. Não use aspas desnecessárias.

REGRAS DA MATÉRIA:

1. Escreva texto original.
2. Não copie a matéria original.
3. Não invente informações.
4. Não invente declarações.
5. Não invente datas.
6. Não invente números.
7. Preserve os fatos presentes na fonte.
8. Escreva aproximadamente 400 a 600 palavras.
9. Use HTML simples.
10. Use somente <p> para os parágrafos.
11. Use <h2> somente quando realmente necessário.
12. Não coloque links externos no meio da matéria.
13. No final informe a fonte.
14. Não diga que você é uma IA.
15. Não inclua comentários fora do JSON.
16. O JSON deve ser válido.
17. Não utilize markdown.
18. Não coloque ``` antes ou depois do JSON.

FONTE:
{noticia["fonte"]}

URL ORIGINAL:
{noticia["url"]}

TÍTULO ORIGINAL:
{noticia["titulo"]}

CONTEÚDO ORIGINAL:
{noticia["texto"]}
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
        # FALLBACK DO TÍTULO
        # ----------------------------------------------------

        if not titulo:

            titulo = noticia[
                "titulo"
            ]

            print(
                "Título não retornado. "
                "Usando título original."
            )


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
        "ROBÔ DE NOTÍCIAS 2.5"
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
