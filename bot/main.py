import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS
# VERSÃO 2.2
# ============================================================


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BLOGGER_BLOG_ID = os.environ["BLOGGER_BLOG_ID"]

GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]


# IMPORTANTE:
# True = cria rascunho
# False = publica automaticamente
BLOGGER_DRAFT = True


# Quantos links serão analisados por fonte
MAX_LINKS_PER_SOURCE = 8


# Notícias com mais de 30 dias serão ignoradas
MAX_AGE_DAYS = 30


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
            timeout=30,
        )

        print(
            f"HTTP: {resposta.status_code}"
        )

        if resposta.status_code != 200:
            return None

        return resposta.text

    except Exception as erro:

        print(
            f"Erro ao acessar URL: {erro}"
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
        url.replace(
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
    #
    # As matérias seguem normalmente:
    #
    # /2026/08/nome-da-materia.html
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
    # PEGAR CAMINHO DA URL
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

    # Homepage
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
    # PÁGINAS QUE NUNCA DEVEM SER TRATADAS
    # COMO NOTÍCIAS
    # --------------------------------------------------------

    paginas_bloqueadas = {

        "ultimas-noticias",
        "últimas-notícias",

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

        "sitemap",

        "videos",
        "video",

        "podcast",
        "podcasts",

        "home",
    }

    if (
        ultimo
        in paginas_bloqueadas
    ):
        return False

    # --------------------------------------------------------
    # SEÇÕES DO SITE
    #
    # Se for apenas:
    # /pastor
    #
    # não é notícia.
    #
    # Mas:
    # /pastor/nome-da-materia
    #
    # pode ser notícia.
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
    # EXTENSÕES QUE NÃO SÃO MATÉRIAS
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
    # URLs DE ARQUIVO/WORDPRESS
    # --------------------------------------------------------

    if primeiro in {
        "wp-content",
        "wp-admin",
        "wp-includes",
        "feed",
        "comments",
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

    # --------------------------------------------------------
    # META TAGS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # TIME
    # --------------------------------------------------------

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
    # NEWS GOSPEL
    # DATA NA URL
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
    # REMOVER ELEMENTOS DESNECESSÁRIOS
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
    ]):

        elemento.decompose()

    # --------------------------------------------------------
    # PARÁGRAFOS
    # --------------------------------------------------------

    paragrafos = []

    for p in soup.find_all(
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
        f"Notícia encontrada: "
        f"{titulo}"
    )

    print(
        f"Texto extraído: "
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

        "data":
        data,
    }


# ============================================================
# GERAR MATÉRIA COM GEMINI
# ============================================================

def gerar_noticia_com_gemini(
    noticia
):

    print()
    print(
        "Gerando notícia com Gemini..."
    )

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    prompt = f"""
Você é um jornalista especializado
em notícias do meio gospel brasileiro.

Crie uma nova matéria jornalística
em português do Brasil com base
nas informações fornecidas abaixo.

REGRAS:

1. Escreva com texto original.
2. Não copie a matéria original.
3. Não invente informações.
4. Não invente declarações.
5. Não invente datas.
6. Não invente números.
7. Preserve os fatos presentes na fonte.
8. Escreva aproximadamente
   400 a 600 palavras.
9. Use HTML simples.
10. Use <p> nos parágrafos.
11. Use <h2> somente quando necessário.
12. Não coloque links externos
    no meio da matéria.
13. No final, informe a fonte.
14. Não diga que você é uma IA.
15. O resultado deve ser somente
    o conteúdo da matéria, sem
    comentários adicionais.

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

        texto = (
            resposta.text
            or ""
        ).strip()

        print(
            f"Texto gerado: "
            f"{len(texto)} caracteres"
        )

        if len(texto) < 300:

            print(
                "Texto gerado muito curto."
            )

            return None

        return texto

    except Exception as erro:

        print(
            f"Erro no Gemini: {erro}"
        )

        return None


# ============================================================
# GERAR TÍTULO
# ============================================================

def gerar_titulo(
    noticia
):

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    prompt = f"""
Crie um título jornalístico
em português do Brasil para
esta notícia.

REGRAS:

- Retorne somente o título.
- Não use aspas desnecessárias.
- Não invente informações.
- Não use emojis.
- Não coloque ponto final.

Título original:

{noticia["titulo"]}
"""

    try:

        resposta = (
            client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
            )
        )

        titulo = (
            resposta.text
            or ""
        ).strip()

        if titulo:

            return titulo

    except Exception as erro:

        print(
            f"Erro ao gerar título: {erro}"
        )

    return noticia["titulo"]


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

    conteudo_final = f"""
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
                "NOTÍCIA PUBLICADA COM SUCESSO!"
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

        return True

    except Exception as erro:

        print(
            f"Erro ao enviar para Blogger: "
            f"{erro}"
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
        "ROBÔ DE NOTÍCIAS 2.2"
    )

    print("=" * 60)

    service = conectar_blogger()

    # --------------------------------------------------------
    # TESTAR CADA FONTE
    # --------------------------------------------------------

    for fonte in FONTES:

        html = acessar_url(
            fonte["url"]
        )

        if not html:

            print(
                "Fonte indisponível."
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
                    "Notícia duplicada. "
                    "Pulando."
                )

                continue

            print(
                "Notícia nova."
            )

            # ------------------------------------------------
            # GEMINI
            # ------------------------------------------------

            conteudo_gerado = (
                gerar_noticia_com_gemini(
                    noticia
                )
            )

            if not conteudo_gerado:

                print(
                    "Não foi possível "
                    "gerar a matéria."
                )

                continue

            titulo = gerar_titulo(
                noticia
            )

            print(
                f"Título novo: {titulo}"
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
