import os
import re
import json
import html
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ============================================================
# RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS
# VERSÃO 2.3
# ============================================================

VERSAO = "2.3"

# ATENÇÃO:
# True  = cria rascunho
# False = PUBLICA AUTOMATICAMENTE
BLOGGER_DRAFT = False

MAX_LINKS_PER_SOURCE = 10
MAX_AGE_DAYS = 30
TIMEOUT = 25

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

SCOPES = ["https://www.googleapis.com/auth/blogger"]


# ============================================================
# UTILIDADES
# ============================================================

def normalizar_texto(texto):
    if not texto:
        return ""

    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )

    texto = texto.lower()
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def limpar_url(url):
    try:
        p = urlparse(url)
        return urlunparse((
            p.scheme,
            p.netloc,
            p.path,
            "",
            "",
            ""
        ))
    except Exception:
        return url


def converter_data(valor):
    if not valor:
        return None

    valor = str(valor).strip()

    formatos = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ]

    try:
        return datetime.fromisoformat(
            valor.replace("Z", "+00:00")
        ).replace(tzinfo=None)
    except Exception:
        pass

    for formato in formatos:
        try:
            return datetime.strptime(valor, formato)
        except Exception:
            continue

    return None


# ============================================================
# BLOGGER
# ============================================================

def conectar_blogger():
    print("Conectando ao Blogger...")

    client_id = os.environ["GOOGLE_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
    refresh_token = os.environ["BLOGGER_REFRESH_TOKEN"]

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )

    service = build(
        "blogger",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    print("Conexão com Blogger: OK")
    return service


def buscar_posts(service, status):
    blog_id = os.environ["BLOGGER_BLOG_ID"]

    try:
        resposta = (
            service.posts()
            .list(
                blogId=blog_id,
                status=status,
                maxResults=100,
            )
            .execute()
        )

        return resposta.get("items", [])

    except Exception as erro:
        print(f"Erro ao buscar posts {status}: {erro}")
        return []


def noticia_ja_existe(service, titulo, url):
    titulo_normalizado = normalizar_texto(titulo)
    url_limpa = limpar_url(url)

    for status in ["LIVE", "DRAFT"]:
        posts = buscar_posts(service, status)

        for post in posts:
            titulo_existente = normalizar_texto(
                post.get("title", "")
            )

            conteudo = post.get("content", "")
            url_existente = limpar_url(url)

            if titulo_normalizado and titulo_normalizado == titulo_existente:
                print("Notícia já existe pelo título.")
                return True

            if url_limpa and url_limpa in conteudo:
                print("Notícia já existe pela URL.")
                return True

    return False


# ============================================================
# ACESSO ÀS FONTES
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def acessar_fonte(fonte):
    try:
        resposta = requests.get(
            fonte["url"],
            headers=HEADERS,
            timeout=TIMEOUT,
        )

        print(f"HTTP: {resposta.status_code}")

        if resposta.status_code != 200:
            return None

        return resposta.text

    except Exception as erro:
        print(f"Erro ao acessar fonte: {erro}")
        return None


def acessar_url(url):
    try:
        print(f"Abrindo notícia:")
        print(url)

        resposta = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
        )

        print(f"HTTP: {resposta.status_code}")

        if resposta.status_code != 200:
            return None

        return resposta.text

    except Exception as erro:
        print(f"Erro ao abrir notícia: {erro}")
        return None


# ============================================================
# FILTROS DE LINKS
# ============================================================

CAMINHOS_BLOQUEADOS = {
    "",
    "home",
    "inicio",
    "ultimas-noticias",
    "quem-somos",
    "fale-conosco",
    "contato",
    "contact",
    "politica-editorial",
    "politica-de-privacidade",
    "politica-de-cookies",
    "termos-de-uso",
    "termos",
    "privacy-policy",
    "cookies",
    "login",
    "autor",
    "author",
    "tags",
    "tag",
    "categoria",
    "categorias",
    "category",
    "search",
    "buscar",
    "feed",
    "rss",
    "sitemap",
    "videos",
    "video",
    "podcast",
    "expediente",
    "anuncie",
    "sobre",
    "sobre-nos",
    "sobre-o-site",
}


def pertence_ao_site(url, fonte):
    try:
        host_url = urlparse(url).hostname or ""
        host_fonte = urlparse(fonte["url"]).hostname or ""

        host_url = host_url.lower().removeprefix("www.")
        host_fonte = host_fonte.lower().removeprefix("www.")

        return host_url == host_fonte

    except Exception:
        return False


def link_valido(url, fonte):
    if not url:
        return False

    url = limpar_url(url)

    if not pertence_ao_site(url, fonte):
        return False

    try:
        p = urlparse(url)
        caminho = p.path.strip("/")

        if not caminho:
            return False

        partes = [
            x.lower()
            for x in caminho.split("/")
            if x
        ]

        partes_normalizadas = [
            normalizar_texto(x).replace(" ", "-")
            for x in partes
        ]

        # Arquivos que não são notícias
        extensoes_bloqueadas = (
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".svg",
            ".pdf",
            ".mp4",
            ".mp3",
        )

        if caminho.lower().endswith(extensoes_bloqueadas):
            return False

        # ====================================================
        # NEWS GOSPEL
        # Formato típico:
        # /2026/08/nome-da-noticia.html
        # ====================================================

        if "newsgospel.com.br" in (
            p.hostname or ""
        ).lower():

            if re.match(
                r"^\d{4}/\d{2}/[^/]+\.html$",
                caminho,
                re.IGNORECASE,
            ):
                return True

            return False

        # ====================================================
        # FUXICO GOSPEL
        # Normalmente notícias ficam dentro de categorias.
        # Exemplo:
        # /pastor/nome-da-noticia
        # /brasil/nome-da-noticia
        # ====================================================

        if "fuxicogospel.com.br" in (
            p.hostname or ""
        ).lower():

            if len(partes) < 2:
                return False

            if any(
                parte in CAMINHOS_BLOQUEADOS
                for parte in partes_normalizadas
            ):
                return False

            ultimo = partes_normalizadas[-1]

            if ultimo in CAMINHOS_BLOQUEADOS:
                return False

            return True

        # ====================================================
        # UAU GOSPEL
        # Notícias podem usar slug diretamente na raiz.
        # ====================================================

        if "uaugospel.com.br" in (
            p.hostname or ""
        ).lower():

            ultimo = partes_normalizadas[-1]

            if ultimo in CAMINHOS_BLOQUEADOS:
                return False

            # Bloqueia páginas claramente institucionais
            bloqueios = {
                "quem-somos",
                "fale-conosco",
                "contato",
                "politica-editorial",
                "politica-de-privacidade",
                "termos-de-uso",
                "login",
            }

            if ultimo in bloqueios:
                return False

            return True

        return False

    except Exception:
        return False


def encontrar_links(fonte, html_texto):
    soup = BeautifulSoup(html_texto, "html.parser")

    encontrados = []
    vistos = set()

    def adicionar_links(container):
        for a in container.find_all("a", href=True):
            href = a.get("href", "").strip()

            if not href:
                continue

            if href.startswith((
                "javascript:",
                "mailto:",
                "tel:",
            )):
                continue

            url = urljoin(fonte["url"], href)
            url = limpar_url(url)

            if not link_valido(url, fonte):
                continue

            if url in vistos:
                continue

            vistos.add(url)
            encontrados.append(url)

    # Primeiro tentamos links dentro de <article>.
    # Isso ajuda a priorizar notícias reais.
    artigos = soup.find_all("article")

    for artigo in artigos:
        adicionar_links(artigo)

    # Depois procuramos no restante da página.
    adicionar_links(soup)

    return encontrados


# ============================================================
# JSON-LD
# ============================================================

def percorrer_jsonld(obj):
    if isinstance(obj, dict):
        yield obj

        for valor in obj.values():
            yield from percorrer_jsonld(valor)

    elif isinstance(obj, list):
        for item in obj:
            yield from percorrer_jsonld(item)


def extrair_jsonld(soup):
    dados_artigo = None
    data_publicacao = None
    imagem_jsonld = None

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):
        texto = script.string or script.get_text()

        if not texto.strip():
            continue

        try:
            dados = json.loads(texto)
        except Exception:
            continue

        for obj in percorrer_jsonld(dados):
            if not isinstance(obj, dict):
                continue

            tipo = obj.get("@type", "")

            if isinstance(tipo, list):
                tipos = [
                    str(x).lower()
                    for x in tipo
                ]
            else:
                tipos = [str(tipo).lower()]

            eh_artigo = any(
                x in tipos
                for x in [
                    "article",
                    "newsarticle",
                    "blogposting",
                    "reportage",
                ]
            )

            if eh_artigo:
                dados_artigo = obj

                if obj.get("datePublished"):
                    data_publicacao = obj.get(
                        "datePublished"
                    )

                imagem = obj.get("image")

                if isinstance(imagem, str):
                    imagem_jsonld = imagem

                elif isinstance(imagem, dict):
                    imagem_jsonld = (
                        imagem.get("url")
                        or imagem.get("contentUrl")
                    )

                elif isinstance(imagem, list):
                    for item in imagem:
                        if isinstance(item, str):
                            imagem_jsonld = item
                            break

                        if isinstance(item, dict):
                            imagem_jsonld = (
                                item.get("url")
                                or item.get("contentUrl")
                            )
                            if imagem_jsonld:
                                break

                break

        if dados_artigo:
            break

    return dados_artigo, data_publicacao, imagem_jsonld


# ============================================================
# DATA DA NOTÍCIA
# ============================================================

def extrair_data(soup, url, dados_artigo=None, data_jsonld=None):
    # JSON-LD
    if data_jsonld:
        data = converter_data(data_jsonld)
        if data:
            return data

    # Meta tags
    metas = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"property": "article:published"}),
        ("meta", {"name": "date"}),
        ("meta", {"name": "pubdate"}),
        ("meta", {"name": "publish_date"}),
        ("meta", {"itemprop": "datePublished"}),
    ]

    for tag, atributos in metas:
        encontrado = soup.find(tag, atributos)

        if encontrado:
            valor = (
                encontrado.get("content")
                or encontrado.get("datetime")
            )

            data = converter_data(valor)

            if data:
                return data

    # <time>
    for time_tag in soup.find_all("time"):
        valor = (
            time_tag.get("datetime")
            or time_tag.get_text(" ", strip=True)
        )

        data = converter_data(valor)

        if data:
            return data

    # News Gospel usa data na URL
    if "newsgospel.com.br" in url:
        match = re.search(
            r"/(\d{4})/(\d{2})/",
            url
        )

        if match:
            try:
                return datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    1,
                )
            except Exception:
                pass

    return None


def noticia_recente(data):
    if not data:
        return False

    limite = datetime.now() - timedelta(
        days=MAX_AGE_DAYS
    )

    if data > datetime.now() + timedelta(days=2):
        return False

    return data >= limite


# ============================================================
# PÁGINAS INSTITUCIONAIS
# ============================================================

TITULOS_BLOQUEADOS = [
    "politica editorial",
    "padroes eticos",
    "padroes de etica",
    "politica de correcoes",
    "politica de privacidade",
    "politica de cookies",
    "quem somos",
    "fale conosco",
    "fale com a gente",
    "contato",
    "termos de uso",
    "termos de servico",
    "ultimas noticias",
    "sobre nos",
    "sobre o site",
    "expediente",
    "anuncie",
    "mapa do site",
    "politica de publicidade",
]


def titulo_bloqueado(titulo):
    normalizado = normalizar_texto(titulo)

    for frase in TITULOS_BLOQUEADOS:
        if frase in normalizado:
            return True

    return False


# ============================================================
# IMAGEM
# ============================================================

def imagem_valida(url):
    if not url:
        return False

    url = url.strip()

    if not url.startswith(("http://", "https://")):
        return False

    bloqueios = [
        "logo",
        "favicon",
        "avatar",
        "icon",
        "sprite",
        "emoji",
        "gravatar",
    ]

    url_normalizada = normalizar_texto(url)

    for palavra in bloqueios:
        if palavra in url_normalizada:
            return False

    return True


def extrair_imagem(soup, url_pagina, imagem_jsonld=None):
    # 1. Imagem do JSON-LD
    if imagem_valida(imagem_jsonld):
        return urljoin(url_pagina, imagem_jsonld)

    # 2. og:image
    og_image = soup.find(
        "meta",
        property="og:image"
    )

    if og_image:
        imagem = og_image.get("content")

        if imagem_valida(imagem):
            return urljoin(
                url_pagina,
                imagem
            )

    # 3. twitter:image
    twitter_image = soup.find(
        "meta",
        attrs={"name": "twitter:image"}
    )

    if twitter_image:
        imagem = twitter_image.get("content")

        if imagem_valida(imagem):
            return urljoin(
                url_pagina,
                imagem
            )

    # 4. Imagem dentro do artigo
    artigos = soup.find_all("article")

    if artigos:
        container = max(
            artigos,
            key=lambda x: len(
                x.get_text(" ", strip=True)
            )
        )

        imagem = container.find("img")

        if imagem:
            src = (
                imagem.get("src")
                or imagem.get("data-src")
                or imagem.get("data-lazy-src")
            )

            if imagem_valida(src):
                return urljoin(
                    url_pagina,
                    src
                )

    # 5. Primeira imagem grande da página
    for img in soup.find_all("img"):
        src = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-lazy-src")
        )

        if imagem_valida(src):
            largura = img.get("width", "")
            altura = img.get("height", "")

            # Se não houver dimensão, ainda aceitamos.
            if largura and altura:
                try:
                    if int(largura) < 200 or int(altura) < 150:
                        continue
                except Exception:
                    pass

            return urljoin(
                url_pagina,
                src
            )

    return None


# ============================================================
# EXTRAÇÃO DA NOTÍCIA
# ============================================================

def escolher_container(soup):
    candidatos = []

    for artigo in soup.find_all("article"):
        texto = artigo.get_text(
            " ",
            strip=True
        )

        if len(texto) >= 500:
            candidatos.append(artigo)

    if candidatos:
        return max(
            candidatos,
            key=lambda x: len(
                x.get_text(" ", strip=True)
            )
        )

    seletores = [
        ".entry-content",
        ".post-content",
        ".article-content",
        ".single-post-content",
        ".td-post-content",
        ".content-post",
        "main",
    ]

    candidatos = []

    for seletor in seletores:
        for elemento in soup.select(seletor):
            texto = elemento.get_text(
                " ",
                strip=True
            )

            if len(texto) >= 500:
                candidatos.append(elemento)

    if candidatos:
        return max(
            candidatos,
            key=lambda x: len(
                x.get_text(" ", strip=True)
            )
        )

    return None


def extrair_noticia(fonte, url, html_texto):
    soup = BeautifulSoup(
        html_texto,
        "html.parser"
    )

    dados_artigo, data_jsonld, imagem_jsonld = (
        extrair_jsonld(soup)
    )

    # Título
    titulo = ""

    h1 = soup.find("h1")

    if h1:
        titulo = h1.get_text(
            " ",
            strip=True
        )

    if not titulo and dados_artigo:
        titulo = dados_artigo.get(
            "headline",
            ""
        )

    if not titulo:
        og_title = soup.find(
            "meta",
            property="og:title"
        )

        if og_title:
            titulo = og_title.get(
                "content",
                ""
            )

    if not titulo:
        titulo_tag = soup.find("title")

        if titulo_tag:
            titulo = titulo_tag.get_text(
                " ",
                strip=True
            )

    titulo = re.sub(
        r"\s+",
        " ",
        titulo
    ).strip()

    if not titulo:
        print("Título não encontrado.")
        return None

    print(f"Título encontrado: {titulo}")

    # Bloqueio imediato de páginas institucionais
    if titulo_bloqueado(titulo):
        print(
            "Página institucional detectada pelo título. "
            "Pulando."
        )
        return None

    data = extrair_data(
        soup,
        url,
        dados_artigo,
        data_jsonld,
    )

    if data:
        print(
            "Data encontrada:",
            data.strftime("%Y-%m-%d")
        )

        if not noticia_recente(data):
            print("Notícia antiga. Pulando.")
            return None
    else:
        print("Data não identificada.")

    # Seleciona a área principal
    container = escolher_container(soup)

    if container:
        elementos_remover = container.find_all(
            [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "form",
                "aside",
                "noscript",
                "iframe",
            ]
        )
    else:
        elementos_remover = soup.find_all(
            [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "form",
                "aside",
                "noscript",
                "iframe",
            ]
        )

    for elemento in elementos_remover:
        elemento.decompose()

    if container:
        paragrafos = container.find_all("p")
    else:
        paragrafos = soup.find_all("p")

    textos = []
    vistos = set()

    for p in paragrafos:
        texto = p.get_text(
            " ",
            strip=True
        )

        texto = re.sub(
            r"\s+",
            " ",
            texto
        ).strip()

        if len(texto) < 40:
            continue

        normalizado = normalizar_texto(texto)

        if normalizado in vistos:
            continue

        vistos.add(normalizado)
        textos.append(texto)

    texto_final = "\n\n".join(textos)

    if len(texto_final) < 500:
        print(
            f"Texto insuficiente: "
            f"{len(texto_final)} caracteres."
        )
        return None

    # Segurança adicional contra páginas institucionais
    if len(textos) < 4:
        print(
            "Poucos parágrafos para caracterizar "
            "uma notícia. Pulando."
        )
        return None

    # Fontes que exigem características de artigo
    tem_schema_artigo = dados_artigo is not None
    tem_container_artigo = container is not None

    if (
        not data
        and not tem_schema_artigo
        and not tem_container_artigo
        and "newsgospel.com.br" not in url
    ):
        print(
            "Página sem data, schema ou estrutura "
            "de artigo. Pulando."
        )
        return None

    imagem = extrair_imagem(
        soup,
        url,
        imagem_jsonld,
    )

    if imagem:
        print("Imagem encontrada:")
        print(imagem)
    else:
        print(
            "Nenhuma imagem encontrada. "
            "A postagem será criada sem imagem."
        )

    print(
        f"Notícia encontrada: {titulo}"
    )

    print(
        f"Texto extraído: "
        f"{len(texto_final)} caracteres"
    )

    return {
        "fonte": fonte["nome"],
        "titulo_original": titulo,
        "url": url,
        "data": data,
        "texto": texto_final[:12000],
        "imagem": imagem,
    }


# ============================================================
# GEMINI
# ============================================================

def criar_cliente_gemini():
    chave = os.environ["GEMINI_API_KEY"]

    return genai.Client(
        api_key=chave
    )


def limpar_resposta_gemini(texto):
    if not texto:
        return ""

    texto = texto.strip()

    # Remove cercas de Markdown caso o modelo use.
    texto = re.sub(
        r"^```(?:html)?\s*",
        "",
        texto,
        flags=re.IGNORECASE,
    )

    texto = re.sub(
        r"\s*```$",
        "",
        texto,
        flags=re.IGNORECASE,
    )

    return texto.strip()


def gerar_noticia_com_gemini(noticia):
    print(
        "Gerando notícia com Gemini..."
    )

    client = criar_cliente_gemini()

    prompt = f"""
Você é jornalista de um portal de notícias gospel brasileiro.

Reescreva a notícia abaixo de maneira ORIGINAL,
clara, natural e jornalística para publicação no
blog Rádio Luz Gospel.

REGRAS IMPORTANTES:

- Não copie frases longas literalmente.
- Não invente informações.
- Não invente nomes, números, datas, locais ou declarações.
- Use somente as informações fornecidas na notícia.
- Produza aproximadamente 400 a 600 palavras.
- Escreva em português brasileiro.
- Crie subtítulos quando fizer sentido.
- Não use Markdown.
- Entregue HTML simples.
- Pode usar <p>, <h2>, <strong> e <blockquote>
  quando realmente necessário.
- Não coloque <html>, <head> ou <body>.
- Não escreva introduções como "Aqui está a notícia".
- O texto deve estar pronto para ser colocado no Blogger.
- Ao final, não coloque uma lista de referências.
- A fonte será adicionada automaticamente.

FONTE:
{noticia["fonte"]}

TÍTULO ORIGINAL:
{noticia["titulo_original"]}

CONTEÚDO ORIGINAL:
{noticia["texto"]}
"""

    try:
        resposta = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )

        texto = limpar_resposta_gemini(
            resposta.text
        )

        print(
            f"Texto gerado: {len(texto)} chars"
        )

        if len(texto) < 500:
            print(
                "Texto gerado pelo Gemini é muito curto."
            )
            return None

        return texto

    except Exception as erro:
        print(
            f"Erro no Gemini: {erro}"
        )
        return None


def gerar_titulo(noticia, texto):
    print("Gerando título...")

    client = criar_cliente_gemini()

    prompt = f"""
Crie um título jornalístico para uma notícia gospel.

REGRAS:
- Português brasileiro.
- Natural.
- Atrativo sem sensacionalismo.
- Não invente informação.
- Não use aspas se não forem necessárias.
- Não coloque ponto final.
- Entre aproximadamente 50 e 100 caracteres.
- Responda somente com o título.

Título original:
{noticia["titulo_original"]}

Texto:
{texto[:6000]}
"""

    try:
        resposta = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )

        titulo = (
            resposta.text
            .strip()
            .replace('"', "")
            .replace("“", "")
            .replace("”", "")
        )

        titulo = re.sub(
            r"\s+",
            " ",
            titulo
        ).strip()

        if len(titulo) < 15:
            return noticia["titulo_original"]

        print(
            f"Título novo: {titulo}"
        )

        return titulo

    except Exception as erro:
        print(
            f"Erro ao gerar título: {erro}"
        )

        return noticia["titulo_original"]


# ============================================================
# BLOGGER - PUBLICAÇÃO
# ============================================================

def publicar_no_blogger(
    service,
    titulo,
    conteudo,
    noticia,
):
    blog_id = os.environ["BLOGGER_BLOG_ID"]

    imagem = noticia.get("imagem")

    bloco_imagem = ""

    if imagem:
        imagem_segura = html.escape(
            imagem,
            quote=True
        )

        bloco_imagem = f"""
<p>
  <img
    src="{imagem_segura}"
    alt="{html.escape(titulo, quote=True)}"
    style="max-width:100%;height:auto;"
  />
</p>
"""

    fonte_html = html.escape(
        noticia["fonte"]
    )

    url_html = html.escape(
        noticia["url"],
        quote=True
    )

    conteudo_final = f"""
{bloco_imagem}

{conteudo}

<hr>

<p>
<strong>Fonte:</strong> {fonte_html}
</p>

<p>
<strong>Notícia original:</strong>
<a href="{url_html}" target="_blank" rel="noopener noreferrer">
{url_html}
</a>
</p>
"""

    postagem = {
        "kind": "blogger#post",
        "title": titulo,
        "content": conteudo_final.strip(),
    }

    print(
        "Enviando notícia para Blogger..."
    )

    try:
        resultado = (
            service.posts()
            .insert(
                blogId=blog_id,
                body=postagem,
                isDraft=BLOGGER_DRAFT,
            )
            .execute()
        )

        post_id = resultado.get(
            "id",
            "desconhecido"
        )

        post_url = resultado.get(
            "url",
            "URL não retornada"
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
            f"Título: {titulo}"
        )

        print(
            f"ID: {post_id}"
        )

        print(
            f"URL: {post_url}"
        )

        if imagem:
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
            f"Erro ao publicar no Blogger: {erro}"
        )
        return False


# ============================================================
# PROCESSAMENTO
# ============================================================

def processar_fonte(
    service,
    fonte,
):
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

    html_fonte = acessar_fonte(
        fonte
    )

    if not html_fonte:
        print(
            "Não foi possível acessar a fonte."
        )
        return False

    links = encontrar_links(
        fonte,
        html_fonte
    )

    print(
        f"Links de possíveis notícias: "
        f"{len(links)}"
    )

    candidatos = links[
        :MAX_LINKS_PER_SOURCE
    ]

    print(
        f"Analisando {len(candidatos)} candidatos..."
    )

    for url in candidatos:
        print()
        print(
            "-" * 50
        )

        html_noticia = acessar_url(
            url
        )

        if not html_noticia:
            continue

        noticia = extrair_noticia(
            fonte,
            url,
            html_noticia,
        )

        if not noticia:
            continue

        print(
            "Verificando duplicidade..."
        )

        if noticia_ja_existe(
            service,
            noticia["titulo_original"],
            noticia["url"],
        ):
            print(
                "Notícia já publicada. Pulando."
            )
            continue

        print(
            "Notícia nova."
        )

        texto_gerado = (
            gerar_noticia_com_gemini(
                noticia
            )
        )

        if not texto_gerado:
            continue

        titulo = gerar_titulo(
            noticia,
            texto_gerado,
        )

        sucesso = publicar_no_blogger(
            service,
            titulo,
            texto_gerado,
            noticia,
        )

        if sucesso:
            return True

    return False


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print(
        "RÁDIO LUZ GOSPEL - "
        f"ROBÔ DE NOTÍCIAS {VERSAO}"
    )

    print(
        "Modo:",
        "RASCUNHO" if BLOGGER_DRAFT
        else "PUBLICAÇÃO AUTOMÁTICA"
    )

    print(
        "Fontes configuradas:",
        len(FONTES)
    )

    try:
        service = conectar_blogger()
    except Exception as erro:
        print(
            f"Erro ao conectar ao Blogger: {erro}"
        )
        return

    for fonte in FONTES:
        try:
            sucesso = processar_fonte(
                service,
                fonte,
            )

            if sucesso:
                print()
                print(
                    "ROBÔ FINALIZADO COM SUCESSO."
                )
                return

        except Exception as erro:
            print(
                f"Erro processando "
                f"{fonte['nome']}: {erro}"
            )

    print()
    print(
        "Nenhuma notícia nova foi publicada."
    )

    print(
        "ROBÔ FINALIZADO."
    )


if __name__ == "__main__":
    main()
