import os
import re
import html

import requests
from bs4 import BeautifulSoup

from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BLOGGER_BLOG_ID = os.environ["BLOGGER_BLOG_ID"]

GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# Primeiro teste como RASCUNHO
BLOGGER_DRAFT = True

SITE_URL = "https://www.fuxicogospel.com.br"
ULTIMAS_NOTICIAS_URL = (
    "https://www.fuxicogospel.com.br/ultimas-noticias/"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "Chrome/128.0 Safari/537.36"
    )
}


# ============================================================
# GEMINI
# ============================================================

client = genai.Client(api_key=GEMINI_API_KEY)


# ============================================================
# BLOGGER
# ============================================================

def criar_servico_blogger():

    credentials = Credentials(
        token=None,
        refresh_token=BLOGGER_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/blogger"],
    )

    if not credentials.valid:
        credentials.refresh(Request())

    service = build(
        "blogger",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    return service


# ============================================================
# LIMPAR TEXTO
# ============================================================

def limpar_texto(texto):

    texto = html.unescape(texto)
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


# ============================================================
# BUSCAR ÚLTIMA NOTÍCIA
# ============================================================

def buscar_noticias():

    print("Acessando Fuxico Gospel...")
    print(ULTIMAS_NOTICIAS_URL)

    resposta = requests.get(
        ULTIMAS_NOTICIAS_URL,
        headers=HEADERS,
        timeout=30,
    )

    resposta.raise_for_status()

    print(f"Página acessada. HTTP {resposta.status_code}")

    soup = BeautifulSoup(
        resposta.text,
        "html.parser",
    )

    noticias = []

    # Procuramos links internos que levam para matérias.
    for link in soup.find_all("a", href=True):

        href = link.get("href", "").strip()

        titulo = link.get_text(
            " ",
            strip=True,
        )

        if not titulo:
            continue

        # Somente links do próprio site
        if not href.startswith(SITE_URL):
            continue

        # Ignorar páginas que não são notícias
        ignorar = [
            "/ultimas-noticias/",
            "/politica-editorial/",
            "/politica-de-privacidade/",
            "/expediente/",
            "/quem-somos/",
            "/contato/",
            "/termos-de-uso/",
            "/autor/",
            "/categoria/",
            "/tag/",
            "/tudo-sobre/",
        ]

        if any(item in href for item in ignorar):
            continue

        # Links de matéria normalmente têm caminho próprio
        caminho = href.replace(SITE_URL, "").strip("/")

        if not caminho:
            continue

        # Evita duplicados
        if any(n["link"] == href for n in noticias):
            continue

        noticias.append(
            {
                "title": limpar_texto(titulo),
                "link": href,
            }
        )

    print(f"Links encontrados: {len(noticias)}")

    return noticias[:10]


# ============================================================
# PEGAR CONTEÚDO DA NOTÍCIA
# ============================================================

def abrir_noticia(url):

    print("Abrindo notícia:")
    print(url)

    resposta = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    resposta.raise_for_status()

    soup = BeautifulSoup(
        resposta.text,
        "html.parser",
    )

    # Título
    titulo_tag = soup.find("h1")

    titulo = ""

    if titulo_tag:
        titulo = limpar_texto(
            titulo_tag.get_text(" ", strip=True)
        )

    # Subtítulo
    subtitulo = ""

    h1 = soup.find("h1")

    if h1:
        proximo = h1.find_next()

        if proximo:
            texto = limpar_texto(
                proximo.get_text(" ", strip=True)
            )

            if texto and texto != titulo:
                subtitulo = texto

    # Corpo da notícia
    conteudo = []

    # Procuramos parágrafos relevantes
    for p in soup.find_all("p"):

        texto = limpar_texto(
            p.get_text(" ", strip=True)
        )

        if len(texto) < 40:
            continue

        conteudo.append(texto)

    # Limitar tamanho enviado ao Gemini
    conteudo = conteudo[:40]

    texto_completo = "\n\n".join(conteudo)

    print(f"Título encontrado: {titulo}")
    print(
        f"Texto encontrado: "
        f"{len(texto_completo)} caracteres"
    )

    return {
        "title": titulo,
        "summary": subtitulo,
        "content": texto_completo,
        "link": url,
    }


# ============================================================
# GERAR MATÉRIA
# ============================================================

def gerar_materia(noticia):

    prompt = f"""
Você é jornalista de um portal de notícias gospel brasileiro.

Crie uma matéria ORIGINAL para o blog Rádio Luz Gospel
a partir das informações da notícia abaixo.

REGRAS IMPORTANTES:

- Não copie frases longas da fonte.
- Reescreva a informação com suas próprias palavras.
- Não invente fatos.
- Não invente declarações.
- Preserve nomes, datas e informações importantes.
- Use linguagem jornalística clara.
- Não faça propaganda política.
- Não dê opinião pessoal.
- Não use emojis.
- Crie um título jornalístico.
- Produza aproximadamente 400 a 600 palavras.
- Use subtítulos HTML quando forem úteis.
- Retorne SOMENTE o HTML da matéria.
- Não use <html>, <head> ou <body>.
- Não inclua observações sobre o processo de geração.

TÍTULO DA FONTE:
{noticia["title"]}

SUBTÍTULO:
{noticia["summary"]}

CONTEÚDO DA FONTE:
{noticia["content"]}

LINK DA FONTE:
{noticia["link"]}
"""

    print("Gerando matéria com Gemini...")

    resposta = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    texto = resposta.text.strip()

    return texto


# ============================================================
# VERIFICAR DUPLICATA NO BLOGGER
# ============================================================

def noticia_ja_publicada(service, titulo, link):

    print("Verificando duplicata no Blogger...")

    try:

        resultado = (
            service.posts()
            .list(
                blogId=BLOGGER_BLOG_ID,
                fetchBodies=True,
                maxResults=50,
            )
            .execute()
        )

        posts = resultado.get(
            "items",
            [],
        )

        titulo_normalizado = (
            titulo.lower().strip()
        )

        for post in posts:

            titulo_existente = (
                post.get("title", "")
                .lower()
                .strip()
            )

            conteudo_existente = (
                post.get("content", "")
            )

            # Verifica pelo título
            if titulo_existente == titulo_normalizado:

                print(
                    "Notícia já existe pelo título."
                )

                return True

            # Verifica pelo link da fonte
            if link in conteudo_existente:

                print(
                    "Notícia já existe pelo link."
                )

                return True

    except Exception as erro:

        print(
            "Aviso ao verificar duplicata:"
        )

        print(erro)

    return False


# ============================================================
# PUBLICAR NO BLOGGER
# ============================================================

def publicar_no_blogger(
    service,
    titulo,
    conteudo,
    link_fonte,
):

    print("Criando postagem no Blogger...")

    # Acrescenta a fonte ao final
    conteudo_final = f"""
{conteudo}

<hr>

<p><strong>Fonte:</strong>
<a href="{link_fonte}" target="_blank" rel="noopener">
O Fuxico Gospel
</a>
</p>
"""

    post = {
        "title": titulo,
        "content": conteudo_final,
        "labels": [
            "Notícias Gospel",
            "Rádio Luz Gospel",
        ],
    }

    resultado = (
        service.posts()
        .insert(
            blogId=BLOGGER_BLOG_ID,
            body=post,
            isDraft=BLOGGER_DRAFT,
        )
        .execute()
    )

    print()
    print("=" * 50)
    print("POSTAGEM CRIADA COM SUCESSO")
    print("=" * 50)

    print(
        f"Título: {resultado.get('title')}"
    )

    print(
        f"ID: {resultado.get('id')}"
    )

    print(
        f"URL: {resultado.get('url')}"
    )

    print(
        f"Rascunho: {BLOGGER_DRAFT}"
    )

    print("=" * 50)


# ============================================================
# PRINCIPAL
# ============================================================

def main():

    print("=" * 50)
    print("RÁDIO LUZ GOSPEL - BOT DE NOTÍCIAS")
    print("=" * 50)

    # --------------------------------------------------------
    # Blogger
    # --------------------------------------------------------

    service = criar_servico_blogger()

    print("Conexão com Blogger: OK")

    # --------------------------------------------------------
    # Notícias
    # --------------------------------------------------------

    noticias = buscar_noticias()

    if not noticias:

        print(
            "Nenhuma notícia encontrada."
        )

        return

    print(
        f"Notícias encontradas: "
        f"{len(noticias)}"
    )

    # --------------------------------------------------------
    # Tentar encontrar uma notícia nova
    # --------------------------------------------------------

    for item in noticias:

        try:

            noticia = abrir_noticia(
                item["link"]
            )

            if not noticia["title"]:
                continue

            if len(noticia["content"]) < 100:

                print(
                    "Conteúdo insuficiente. "
                    "Pulando notícia."
                )

                continue

            if noticia_ja_publicada(
                service,
                noticia["title"],
                noticia["link"],
            ):

                continue

            # ------------------------------------------------
            # Gerar
            # ------------------------------------------------

            conteudo = gerar_materia(
                noticia
            )

            if not conteudo:

                print(
                    "Gemini não retornou conteúdo."
                )

                continue

            # ------------------------------------------------
            # Publicar
            # ------------------------------------------------

            publicar_no_blogger(
                service,
                noticia["title"],
                conteudo,
                noticia["link"],
            )

            return

        except Exception as erro:

            print()
            print(
                "Erro ao processar notícia:"
            )
            print(erro)
            print()

    print(
        "Nenhuma notícia nova pôde ser publicada."
    )


# ============================================================
# EXECUTAR
# ============================================================

if __name__ == "__main__":
    main()
