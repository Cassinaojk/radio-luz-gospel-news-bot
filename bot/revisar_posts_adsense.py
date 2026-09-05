import os
import re
import json
import requests
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

BLOGGER_BLOG_ID = os.environ["BLOGGER_BLOG_ID"]
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BOT_LABEL = "Radio Luz Gospel Bot"
TIMEOUT = 25
MAX_GEMINI_CALLS = 1


def conectar():
    cred = Credentials(
        token=None,
        refresh_token=BLOGGER_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/blogger"],
    )
    return build("blogger", "v3", credentials=cred)


def normalizar(t):
    return re.sub(r"\s+", " ", (t or "")).strip().lower()


def acessar(url):
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            },
            timeout=TIMEOUT,
        )
        print(f"HTTP {r.status_code}: {url}")
        return r.text if r.status_code == 200 else None
    except Exception as e:
        print(f"Erro ao acessar fonte: {e}")
        return None


def extrair_url_original(content):
    soup = BeautifulSoup(content or "", "html.parser")
    for a in soup.find_all("a", href=True):
        texto = a.get_text(" ", strip=True).lower()
        href = a.get("href", "").strip()
        if "notícia original" in texto and href.startswith("http"):
            return href
    m = re.search(r'https?://[^\s"<>]+', content or "")
    return m.group(0) if m else None


def extrair_fonte(content):
    texto = BeautifulSoup(content or "", "html.parser").get_text(" ", strip=True)
    m = re.search(r"Fonte:\s*([^\n]+?)(?:Notícia original|$)", texto, re.I)
    return m.group(1).strip() if m else "Fonte jornalística externa"


def extrair_texto_fonte(url):
    html = acessar(url)
    if not html:
        return None, [], []
    soup = BeautifulSoup(html, "html.parser")
    titulo = ""
    h1 = soup.find("h1")
    if h1:
        titulo = h1.get_text(" ", strip=True)
    if not titulo and soup.title:
        titulo = soup.title.get_text(" ", strip=True)

    videos = []
    vistos = set()
    def add(url):
        if not url: return
        pats = [
            r"youtube\.com/embed/([A-Za-z0-9_-]{6,})",
            r"youtube-nocookie\.com/embed/([A-Za-z0-9_-]{6,})",
            r"youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})",
            r"youtu\.be/([A-Za-z0-9_-]{6,})",
            r"youtube\.com/shorts/([A-Za-z0-9_-]{6,})",
        ]
        for p in pats:
            m = re.search(p, url, re.I)
            if m:
                vid = m.group(1)
                if vid not in vistos:
                    vistos.add(vid)
                    videos.append(f"https://www.youtube.com/embed/{vid}")
                return

    for iframe in soup.find_all("iframe"):
        add(iframe.get("src") or iframe.get("data-src"))
    for a in soup.find_all("a", href=True):
        add(a.get("href"))

    for x in soup(["script", "style", "nav", "footer", "header", "form", "aside", "noscript", "iframe"]):
        x.decompose()
    ps = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(" ", strip=True)) >= 40]
    texto = "\n\n".join(ps)
    return (titulo, texto, videos)


def ngrams(texto, n=6):
    p = re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", normalizar(texto))
    return set(" ".join(p[i:i+n]) for i in range(max(0, len(p)-n+1)))


def overlap(a, b):
    aa, bb = ngrams(a), ngrams(b)
    return len(aa & bb) / max(1, len(aa))


def gerar(noticia, fonte, url, contexto):
    prompt = f"""
Você é editor de uma redação jornalística gospel brasileira. Reescreva a matéria para o site Rádio Luz Gospel seguindo este fluxo: fonte → pesquisa → apuração → redação própria → revisão.

Retorne SOMENTE JSON válido:
{{"publicar": true, "titulo": "...", "conteudo": "<p>...</p>..."}}

REGRAS:
- Crie título e introdução totalmente próprios.
- Reescreva a matéria de forma estruturalmente diferente, sem tradução, sinônimos ou paráfrase frase a frase.
- Não copie frases longas da fonte.
- Preserve somente fatos verificáveis.
- Não invente nomes, datas, números, declarações ou contexto.
- Use o contexto secundário apenas se for claramente relacionado e verificável.
- Acrescente contexto útil quando houver informação suficiente.
- Produza 450–650 palavras e pelo menos 5 parágrafos substanciais.
- Se não houver informação suficiente para uma matéria realmente útil e original, use "publicar": false.
- Não inclua links no corpo.
- Não inclua seção de fonte; ela será adicionada pelo sistema.
- HTML simples com <p> e, quando necessário, <h2>.

FONTE: {fonte}
URL: {url}
TÍTULO ORIGINAL: {noticia['titulo']}

TEXTO DA FONTE:
{noticia['texto']}

CONTEXTO SECUNDÁRIO:
{contexto or 'Nenhum contexto secundário disponível.'}
"""
    client = genai.Client(api_key=GEMINI_API_KEY)
    r = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
    bruto = (r.text or "").strip()
    bruto = re.sub(r"^```(?:json)?\s*|\s*```$", "", bruto, flags=re.I).strip()
    a, b = bruto.find("{"), bruto.rfind("}")
    if a < 0 or b <= a:
        return None
    d = json.loads(bruto[a:b+1])
    if d.get("publicar") is False:
        return None
    titulo = str(d.get("titulo", "")).strip()
    conteudo = str(d.get("conteudo", "")).strip()
    texto = BeautifulSoup(conteudo, "html.parser").get_text(" ", strip=True)
    if not titulo or len(texto) < 1000:
        return None
    if SequenceMatcher(None, normalizar(titulo), normalizar(noticia['titulo'])).ratio() >= 0.82:
        print("Revisão recusada: título ainda muito parecido.")
        return None
    ov = overlap(texto, noticia["texto"])
    print(f"Sobreposição com fonte: {ov:.3f}")
    if ov > 0.12:
        print("Revisão recusada: possível cópia/reformulação mecânica.")
        return None
    return titulo, conteudo


def main():
    service = conectar()
    posts = service.posts().list(blogId=BLOGGER_BLOG_ID, status="LIVE", maxResults=100).execute().get("items", [])
    candidatos = [p for p in posts if BOT_LABEL in p.get("labels", [])]
    if not candidatos:
        print("Nenhuma postagem do robô encontrada.")
        return

    # Uma postagem por execução para proteger a cota do Gemini.
    for post in candidatos:
        content = post.get("content", "")
        if "Revisado editorialmente" in content:
            continue
        url = extrair_url_original(content)
        if not url:
            print(f"Sem URL original: {post.get('title')}")
            continue
        titulo_fonte, texto_fonte, videos = extrair_texto_fonte(url)
        if not texto_fonte or len(texto_fonte) < 700:
            print(f"Fonte insuficiente para revisão: {post.get('title')}")
            continue

        noticia = {"titulo": titulo_fonte or post.get("title", ""), "texto": texto_fonte}
        fonte = extrair_fonte(content)
        try:
            resultado = gerar(noticia, fonte, url, "")
        except Exception as e:
            print(f"Erro no Gemini: {e}")
            return
        if not resultado:
            print(f"Não foi possível revisar: {post.get('title')}")
            return

        novo_titulo, novo_conteudo = resultado
        old_soup = BeautifulSoup(content, "html.parser")
        partes = []
        for img in old_soup.find_all("img"):
            src = img.get("src")
            if src:
                partes.append(f'<p><img src="{src}" alt="{novo_titulo}" style="max-width:100%;height:auto;" loading="lazy"></p>')
                break
        for iframe in old_soup.find_all("iframe"):
            src = iframe.get("src")
            if src and ("youtube.com" in src or "youtube-nocookie.com" in src):
                partes.append(f'<p><iframe src="{src}" width="560" height="315" style="max-width:100%;width:100%;border:0;border-radius:12px;" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen loading="lazy"></iframe></p>')

        final = "\n".join(partes) + "\n" + novo_conteudo + f'''\n<hr>\n<p><strong>Fonte:</strong> {fonte}</p>\n<p><strong>Notícia original:</strong> <a href="{url}" target="_blank" rel="noopener">{url}</a></p>\n<p><em>Revisado editorialmente pela Rádio Luz Gospel.</em></p>'''

        service.posts().update(
            blogId=BLOGGER_BLOG_ID,
            postId=post["id"],
            body={"kind":"blogger#post", "id":post["id"], "title":novo_titulo, "content":final, "labels":post.get("labels", [])},
        ).execute()
        print("POSTAGEM REVISADA COM SUCESSO")
        print(novo_titulo)
        return

    print("Nenhuma postagem elegível para revisão nesta execução.")

if __name__ == "__main__":
    main()
