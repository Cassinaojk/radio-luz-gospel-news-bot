import os
import re
import json
import traceback
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
MODEL = "gemini-3.6-flash"
MIN_SOURCE_CHARS = 700
MIN_GENERATED_CHARS = 1000
MAX_SOURCE_OVERLAP = 0.18

def conectar():
    cred = Credentials(token=None, refresh_token=BLOGGER_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/blogger"])
    return build("blogger", "v3", credentials=cred)

def acessar(url):
    try:
        r = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}, timeout=TIMEOUT)
        print(f"HTTP {r.status_code}: {url}")
        return r.text if r.status_code == 200 else None
    except Exception as e:
        print(f"Erro ao acessar fonte: {type(e).__name__}: {e}")
        return None

def extrair_url_original(content):
    soup = BeautifulSoup(content or "", "html.parser")
    for a in soup.find_all("a", href=True):
        if "notícia original" in a.get_text(" ", strip=True).lower() and a["href"].startswith("http"):
            return a["href"].strip()
    return None

def extrair_fonte(content):
    texto = BeautifulSoup(content or "", "html.parser").get_text(" ", strip=True)
    m = re.search(r"Fonte:\s*(.+?)(?:Notícia original|Revisado editorialmente|$)", texto, re.I)
    return m.group(1).strip() if m else "Fonte jornalística externa"

def extrair_materia(url):
    html = acessar(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    titulo = h1.get_text(" ", strip=True) if h1 else (soup.title.get_text(" ", strip=True) if soup.title else "")
    videos, vistos = [], set()

    def add_video(value):
        if not value:
            return
        patterns = [
            r"(?:youtube\.com|youtube-nocookie\.com)/embed/([A-Za-z0-9_-]{6,})",
            r"youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})",
            r"youtu\.be/([A-Za-z0-9_-]{6,})",
            r"youtube\.com/shorts/([A-Za-z0-9_-]{6,})"]
        for pattern in patterns:
            m = re.search(pattern, value, re.I)
            if m:
                vid = m.group(1)
                if vid not in vistos:
                    vistos.add(vid)
                    videos.append(f"https://www.youtube.com/embed/{vid}")
                return

    for iframe in soup.find_all("iframe"):
        add_video(iframe.get("src") or iframe.get("data-src"))
    for a in soup.find_all("a", href=True):
        add_video(a.get("href"))
    for x in soup(["script","style","nav","footer","header","form","aside","noscript","iframe"]):
        x.decompose()
    ps = [p.get_text(" ", strip=True) for p in soup.find_all("p")
          if len(p.get_text(" ", strip=True)) >= 40]
    return {"titulo": titulo, "texto": "\n\n".join(ps), "videos": videos}

def normalizar(texto):
    return re.sub(r"\s+", " ", (texto or "")).strip().lower()

def ngrams(texto, n=6):
    palavras = re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", normalizar(texto))
    return set(" ".join(palavras[i:i+n]) for i in range(max(0, len(palavras)-n+1)))

def overlap(a, b):
    aa, bb = ngrams(a), ngrams(b)
    return len(aa & bb) / max(1, len(aa))

def limpar_json(bruto):
    bruto = re.sub(r"^```(?:json)?\s*|\s*```$", "", (bruto or "").strip(), flags=re.I).strip()
    a, b = bruto.find("{"), bruto.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("Gemini não retornou JSON válido.")
    return json.loads(bruto[a:b+1])

def gerar_revisao(materia, fonte, url):
    prompt = f"""
Você é editor de uma redação jornalística gospel brasileira.
Reescreva a matéria abaixo para a Rádio Luz Gospel seguindo:
fonte → compreensão → redação própria → contextualização verificável → revisão.

RETORNE SOMENTE JSON:
{{"publicar":true,"titulo":"novo título","conteudo":"<p>...</p>"}}

REGRAS:
- Título e introdução totalmente novos.
- Estrutura diferente da fonte; não faça paráfrase frase a frase.
- Não traduza, não troque apenas sinônimos e não copie frases longas.
- Preserve apenas fatos sustentados pelo material.
- Não invente nomes, datas, números, declarações ou contexto.
- Acrescente contexto somente quando estiver claramente sustentado.
- Português brasileiro natural, 450–650 palavras e pelo menos 5 parágrafos.
- HTML simples com <p> e, se necessário, <h2>.
- Sem links e sem seção de fonte no corpo.
- Se não houver material suficiente para uma matéria útil e original, use "publicar": false.

FONTE: {fonte}
URL: {url}
TÍTULO ORIGINAL: {materia["titulo"]}

TEXTO DA FONTE:
{materia["texto"]}
"""
    print(f"Chamando Gemini ({MODEL})...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    resposta = client.models.generate_content(model=MODEL, contents=prompt)
    bruto = (resposta.text or "").strip()
    print(f"Resposta do Gemini recebida: {len(bruto)} caracteres.")
    dados = limpar_json(bruto)
    if dados.get("publicar") is False:
        print("Gemini marcou a revisão como não publicável.")
        return None
    titulo = str(dados.get("titulo", "")).strip()
    conteudo = str(dados.get("conteudo", "")).strip()
    texto = BeautifulSoup(conteudo, "html.parser").get_text(" ", strip=True)
    if not titulo:
        raise ValueError("Gemini não devolveu título.")
    if len(texto) < MIN_GENERATED_CHARS:
        raise ValueError(f"Texto revisado muito curto: {len(texto)} caracteres.")
    sim = SequenceMatcher(None, normalizar(titulo), normalizar(materia["titulo"])).ratio()
    print(f"Similaridade do título: {sim:.3f}")
    if sim >= 0.82:
        raise ValueError("Título revisado muito parecido com o original.")
    ov = overlap(texto, materia["texto"])
    print(f"Sobreposição textual com a fonte: {ov:.3f}")
    if ov > MAX_SOURCE_OVERLAP:
        raise ValueError(f"Possível cópia/reformulação mecânica (sobreposição {ov:.3f}).")
    return titulo, conteudo

def montar_conteudo(content, titulo, novo, videos_fonte, fonte, url):
    soup = BeautifulSoup(content or "", "html.parser")
    partes = []
    img = soup.find("img", src=True)
    if img:
        partes.append(f'<p><img src="{img["src"]}" alt="{titulo}" style="max-width:100%;height:auto;" loading="lazy"></p>')
    videos = []
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src")
        if src and ("youtube.com" in src or "youtube-nocookie.com" in src) and src not in videos:
            videos.append(src)
    for video in videos_fonte:
        if video not in videos:
            videos.append(video)
    for video in videos:
        partes.append(f'<p><iframe src="{video}" width="560" height="315" style="max-width:100%;width:100%;border:0;border-radius:12px;" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen loading="lazy"></iframe></p>')
    partes.append(novo)
    partes.append(f'<hr><p><strong>Fonte:</strong> {fonte}</p><p><strong>Notícia original:</strong> <a href="{url}" target="_blank" rel="noopener">{url}</a></p><p><em>Revisado editorialmente pela Rádio Luz Gospel.</em></p>')
    return "\n".join(partes)

def main():
    print("=== REVISOR ADSENSE - INÍCIO ===")
    service = conectar()
    posts = service.posts().list(blogId=BLOGGER_BLOG_ID, status="LIVE", maxResults=100).execute().get("items", [])
    candidatos = [p for p in posts if BOT_LABEL in p.get("labels", []) and "Revisado editorialmente" not in p.get("content", "")]
    if not candidatos:
        print("Nenhuma postagem elegível para revisão.")
        return
    post = candidatos[0]
    print(f"Postagem escolhida: {post.get('title','')}")
    content = post.get("content", "")
    url = extrair_url_original(content)
    if not url:
        print("ERRO: a postagem não possui URL da notícia original.")
        return
    materia = extrair_materia(url)
    if not materia:
        print("ERRO: não foi possível obter a matéria original.")
        return
    if len(materia["texto"]) < MIN_SOURCE_CHARS:
        print(f"Fonte insuficiente para revisão: {len(materia['texto'])} caracteres.")
        return
    print(f"Fonte carregada: {len(materia['texto'])} caracteres, {len(materia['videos'])} vídeo(s).")
    try:
        resultado = gerar_revisao(materia, extrair_fonte(content), url)
    except Exception as e:
        print(f"ERRO DURANTE A REVISÃO: {type(e).__name__}: {e}")
        traceback.print_exc()
        print("A postagem NÃO foi alterada.")
        return
    if not resultado:
        print("Revisão recusada. A postagem NÃO foi alterada.")
        return
    novo_titulo, novo_conteudo = resultado
    final = montar_conteudo(content, novo_titulo, novo_conteudo, materia["videos"], extrair_fonte(content), url)
    try:
        service.posts().update(blogId=BLOGGER_BLOG_ID, postId=post["id"],
            body={"kind":"blogger#post","id":post["id"],"title":novo_titulo,
                  "content":final,"labels":post.get("labels",[])}).execute()
    except Exception as e:
        print(f"ERRO AO ATUALIZAR O BLOGGER: {type(e).__name__}: {e}")
        traceback.print_exc()
        print("A postagem NÃO foi alterada com segurança.")
        return
    print("=== POSTAGEM REVISADA COM SUCESSO ===")
    print(f"Novo título: {novo_titulo}")

if __name__ == "__main__":
    main()
