import os
import re
import html
import feedparser
import google.generativeai as genai

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

# Por segurança, o primeiro teste será como RASCUNHO.
BLOGGER_DRAFT = True

# Fonte de notícias
RSS_URL = "https://fuxicogospel.com.br/feed/"


# ============================================================
# GEMINI
# ============================================================

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-2.5-flash")


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
# LIMPAR HTML
# ============================================================

def limpar_html(texto):
    texto = html.unescape(texto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


# ============================================================
# BUSCAR NOTÍCIAS
# ============================================================

def buscar_noticias():
    print("Buscando notícias...")

    feed = feedparser.parse(RSS_URL)

    noticias = []

    for item in feed.entries[:5]:
        titulo = item.get("title", "").strip()
        link = item.get("link", "").strip()
        resumo = limpar_html(
            item.get("summary", item.get("description", ""))
        )

        if titulo and link:
            noticias.append(
                {
                    "title": titulo,
                    "link": link,
                    "summary": resumo,
                }
            )

    print(f"Notícias encontradas: {len(noticias)}")

    return noticias


# ============================================================
# GERAR MATÉRIA
# ============================================================

def gerar_materia(noticia):
    prompt = f"""
Você é um jornalista especializado em notícias do meio gospel brasileiro.

Escreva uma matéria jornalística original para o blog Rádio Luz Gospel.

IMPORTANTE:
- Não copie o texto da fonte.
- Reescreva com linguagem jornalística natural.
- Não invente informações.
- Não crie declarações que não estejam na fonte.
- Use título jornalístico atraente, mas sem exageros.
- A matéria deve ter aproximadamente 400 a 600 palavras.
- Organize o texto com subtítulos quando fizer sentido.
- Não use emojis.
- Retorne somente HTML simples para o conteúdo da matéria.
- Não coloque <html>, <head> ou <body>.

Notícia original:

Título:
{noticia["title"]}

Resumo:
{noticia["summary"]}

Fonte:
{noticia["link"]}
"""

    print("Gerando matéria com Gemini...")

    response = model.generate_content(prompt)

    texto = response.text.strip()

    return texto


# ============================================================
# VERIFICAR DUPLICATA
# ============================================================

def noticia_ja_publicada(service, titulo):
    print("Verificando se a notícia já existe...")

    try:
        resultado = (
            service.posts()
            .list(
                blogId=BLOGGER_BLOG_ID,
                fetchBodies=False,
                maxResults=50,
            )
            .execute()
        )

        posts = resultado.get("items", [])

        titulo_normalizado = titulo.lower().strip()

        for post in posts:
            titulo_existente = post.get("title", "").lower().strip()

            if titulo_existente == titulo_normalizado:
                print("Notícia já publicada. Ignorando.")
                return True

    except Exception as erro:
        print(f"Erro ao verificar duplicata: {erro}")

    return False


# ============================================================
# PUBLICAR NO BLOGGER
# ============================================================

def publicar_no_blogger(service, titulo, conteudo):
    print("Criando postagem no Blogger...")

    post = {
        "title": titulo,
        "content": conteudo,
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

    print("==========================================")
    print("POSTAGEM CRIADA COM SUCESSO")
    print("==========================================")
    print(f"Título: {resultado.get('title')}")
    print(f"ID: {resultado.get('id')}")
    print(f"URL: {resultado.get('url')}")
    print(f"Rascunho: {BLOGGER_DRAFT}")
    print("==========================================")

    return resultado


# ============================================================
# PRINCIPAL
# ============================================================

def main():
    print("==========================================")
    print("RÁDIO LUZ GOSPEL - BOT DE NOTÍCIAS")
    print("==========================================")

    # Conecta ao Blogger
    service = criar_servico_blogger()

    print("Conexão com Blogger: OK")

    # Busca notícias
    noticias = buscar_noticias()

    if not noticias:
        print("Nenhuma notícia encontrada.")
        return

    # Processa somente a primeira notícia
    noticia = noticias[0]

    titulo = noticia["title"]

    # Verifica duplicata
    if noticia_ja_publicada(service, titulo):
        return

    # Gera matéria
    conteudo = gerar_materia(noticia)

    if not conteudo:
        print("Gemini não retornou conteúdo.")
        return

    # Publica como rascunho
    publicar_no_blogger(
        service,
        titulo,
        conteudo,
    )


if __name__ == "__main__":
    main()
