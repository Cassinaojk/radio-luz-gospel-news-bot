import os, re, json, requests, time, random
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

print("RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS 4.1")

BLOGGER_BLOG_ID=os.environ["BLOGGER_BLOG_ID"]
GOOGLE_CLIENT_ID=os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET=os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN=os.environ["BLOGGER_REFRESH_TOKEN"]
GEMINI_API_KEY=os.environ["GEMINI_API_KEY"]

MAX_POSTS_PER_DAY=3
MAX_GEMINI_TEXT_CALLS_PER_RUN=1
GEMINI_MAX_RETRIES=3
GEMINI_RETRY_BASE_SECONDS=4
MAX_LINKS_PER_SOURCE=50
MAX_AGE_DAYS=60
MIN_SOURCE_CHARS=700
MIN_SOURCE_PARAGRAPHS=4
TIMEOUT=25
GEMINI_MODEL_TEXT=os.getenv("GEMINI_MODEL","gemini-3.6-flash")
GEMINI_FALLBACK_MODEL=os.getenv("GEMINI_FALLBACK_MODEL","gemini-3.5-flash-lite")

SOURCES=[
 {"nome":"News Gospel","url":"https://www.newsgospel.com.br/","feeds":["https://www.newsgospel.com.br/feed/"]},
 {"nome":"UAU Gospel","url":"https://www.uaugospel.com.br/","feeds":["https://www.uaugospel.com.br/feed/"]},
]

BAD=("/category/","/tag/","/author/","/page/","/search/","/feed/","/wp-json/","/comments/",
     "/sobre","/contato","/contact","/politica-de-privacidade","/privacy-policy")
s=requests.Session()
s.headers.update({"User-Agent":"Mozilla/5.0 (compatible; RadioLuzGospelBot/4.1)"})
gemini_calls=0

def bad_url(u):
    u=(u or "").split("#")[0].strip().lower()
    if not u.startswith(("http://","https://")):
        return True
    share = (
        "pinterest." in u or
        "reddit.com/submit" in u or
        "facebook.com/sharer" in u or
        "twitter.com/intent" in u or
        "x.com/intent" in u or
        "whatsapp.com/" in u or
        "t.me/share" in u or
        "linkedin.com/share" in u
    )
    return share or any(x in u for x in BAD)

def soup(url,xml=False):
    try:
        r=s.get(url,timeout=TIMEOUT)
        print(f"Abrindo: {url}\nHTTP: {r.status_code}")
        if r.status_code!=200:return None
        return BeautifulSoup(r.text,"xml" if xml else "html.parser")
    except Exception as e:
        print("Erro:",e); return None

def date_parse(v):
    if not v:return None
    for f in ("%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S.%f%z",
              "%Y-%m-%dT%H:%M:%S","%Y-%m-%d","%d/%m/%Y"):
        try:
            d=datetime.strptime(str(v)[:32],f)
            return d.replace(tzinfo=None) if d.tzinfo else d
        except: pass
    return None

def article_date(x):
    for sel in ('meta[property="article:published_time"]','meta[property="og:published_time"]',
                'meta[name="date"]','meta[name="publish_date"]','meta[itemprop="datePublished"]'):
        n=x.select_one(sel)
        if n:
            d=date_parse(n.get("content",""))
            if d:return d
    for sc in x.find_all("script",type="application/ld+json"):
        try:
            d=json.loads(sc.string or sc.get_text())
            for item in d if isinstance(d,list) else [d]:
                if isinstance(item,dict):
                    z=date_parse(item.get("datePublished"))
                    if z:return z
        except:pass
    for sel in ("time.entry-date","time.published","time",".entry-date",".posted-on"):
        n=x.select_one(sel)
        if n:
            d=date_parse(n.get("datetime") or n.get_text(" ",strip=True))
            if d:return d
    return None

def image_original(x):
    vals=[]
    for sel in ('meta[property="og:image"]','meta[name="twitter:image"]','meta[itemprop="image"]'):
        n=x.select_one(sel)
        if n and n.get("content"):vals.append(n["content"])
    for sel in ("article img",".entry-content img",".post-content img",".td-post-content img","main img"):
        for n in x.select(sel)[:10]:
            vals.append(n.get("src") or n.get("data-src") or n.get("data-lazy-src") or "")
    for u in vals:
        u=u.strip()
        if u.startswith("//"):u="https:"+u
        if u.startswith(("http://","https://")) and not any(z in u.lower() for z in ("logo","avatar","icon","favicon")):
            return u
    return ""

def videos(x):
    out=[]
    for n in x.find_all("iframe"):
        u=n.get("src","").strip()
        if u.startswith("//"):u="https:"+u
        if u.startswith(("http://","https://")) and u not in out:out.append(u)
    return out[:5]

def get_article(url):
    x=soup(url)
    if not x:return None
    n=x.find("h1") or x.find("title")
    title=re.sub(r"\s+"," ",n.get_text(" ",strip=True) if n else "").strip()
    if not title:return None
    if title.lower() in {"lançamentos","notícias","noticias","home","início","inicio","últimas notícias","ultimas noticias"}:
        print("Página de índice/categoria. Pulando.");return None

    d=article_date(x)
    if d:
        print("Data encontrada:",d)
        if (datetime.now()-d).days>MAX_AGE_DAYS:
            print("Notícia antiga. Pulando.");return None
    else:
        print("Data não identificada. Aceitando para análise.")

    img=image_original(x)
    if not img:
        print("Imagem original não encontrada. Pulando.");return None

    box=x.find("article") or x.find("main") or x
    ps=[]
    for p in box.find_all("p"):
        t=re.sub(r"\s+"," ",p.get_text(" ",strip=True))
        if len(t)>=35:ps.append(t)
    text="\n\n".join(ps)
    if len(text)<MIN_SOURCE_CHARS or len(ps)<MIN_SOURCE_PARAGRAPHS:
        print("Conteúdo insuficiente:",len(text),"caracteres");return None

    vv=videos(x)
    print("Notícia encontrada:",title)
    print("Texto extraído:",len(text),"caracteres")
    print("Imagem encontrada:",img)
    print("Vídeos encontrados:",len(vv))
    return {"url":url,"title":title,"date":d,"image":img,"text":text[:14000],"videos":vv}

def links(source):
    out=[];seen=set()
    for feed in source["feeds"]:
        x=soup(feed,True)
        if x:
            for item in x.find_all(["item","entry"]):
                n=item.find("link")
                u=(n.get("href") or n.get_text(strip=True)) if n else ""
                u=u.split("#")[0].strip()
                if u and not bad_url(u) and u not in seen:
                    seen.add(u);out.append(u)
    x=soup(source["url"])
    if x:
        for a in x.find_all("a",href=True):
            u=a["href"].split("#")[0].strip()
            if u.startswith("/"):u=source["url"].rstrip("/")+u
            if bad_url(u):continue
            src_host=urlparse(source["url"]).netloc.lower()
            host=urlparse(u).netloc.lower()
            if not (host==src_host or host.endswith("." + src_host)):continue
            if u not in seen:seen.add(u);out.append(u)
    return out[:MAX_LINKS_PER_SOURCE]

def blogger():
    c=Credentials(None,refresh_token=BLOGGER_REFRESH_TOKEN,token_uri="https://oauth2.googleapis.com/token",
                  client_id=GOOGLE_CLIENT_ID,client_secret=GOOGLE_CLIENT_SECRET,
                  scopes=["https://www.googleapis.com/auth/blogger"])
    return build("blogger","v3",credentials=c,cache_discovery=False)

def existing(api):
    out=set();token=None
    try:
        while True:
            kw={"blogId":BLOGGER_BLOG_ID,"maxResults":500,"fetchBodies":False}
            if token:kw["pageToken"]=token
            d=api.posts().list(**kw).execute()
            out.update(p["url"].rstrip("/") for p in d.get("items",[]) if p.get("url"))
            token=d.get("nextPageToken")
            if not token:break
    except Exception as e:print("Erro Blogger:",e)
    return out

def _is_transient_gemini_error(exc):
    """Identifica erros temporários que justificam nova tentativa."""
    msg = str(exc).upper()
    return any(code in msg for code in (
        "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED",
        "500", "502", "504", "TIMEOUT"
    ))


def _gemini_request(client, model, prompt):
    """Chama o Gemini com retry exponencial e pequeno jitter."""
    last_error = None

    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        try:
            print(f"Gemini: modelo={model} tentativa={attempt}/{GEMINI_MAX_RETRIES}")
            return client.models.generate_content(
                model=model,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
        except Exception as e:
            last_error = e

            if not _is_transient_gemini_error(e) or attempt >= GEMINI_MAX_RETRIES:
                raise

            delay = GEMINI_RETRY_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 2)
            print(f"Gemini temporariamente indisponível: {e}")
            print(f"Nova tentativa em {delay:.1f}s...")
            time.sleep(delay)

    raise last_error


def gemini(a, client):
    global gemini_calls

    if gemini_calls >= MAX_GEMINI_TEXT_CALLS_PER_RUN:
        return None

    prompt=f"""
Você é o editor do Rádio Luz Gospel.

Escreva uma matéria jornalística ORIGINAL em português do Brasil usando SOMENTE os fatos presentes no texto-fonte.

REGRAS:
- publicar=true se houver informação suficiente;
- criar um título novo, claro e jornalístico;
- criar um resumo de 2 a 3 frases;
- criar matéria com aproximadamente 700 a 1200 palavras;
- não inventar nomes, datas, números, locais, declarações ou acontecimentos;
- não acrescentar fatos que não estejam no texto-fonte;
- não dizer que foi escrita por IA;
- não copiar frases longas do texto-fonte;
- retornar SOMENTE JSON válido, sem Markdown e sem explicações.

FORMATO EXATO:
{{"publicar":true,"titulo":"Título","resumo":"Resumo","materia":"Matéria completa em parágrafos"}}

Se o texto realmente não tiver informação suficiente para uma matéria, use publicar=false.

TÍTULO FONTE:
{a["title"]}

URL:
{a["url"]}

TEXTO-FONTE:
{a["text"]}
"""

    models_to_try = [GEMINI_MODEL_TEXT]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL not in models_to_try:
        models_to_try.append(GEMINI_FALLBACK_MODEL)

    for model_index, model in enumerate(models_to_try):
        try:
            r = _gemini_request(client, model, prompt)
            gemini_calls += 1

            raw = (getattr(r, "text", None) or "").strip()
            print("Resposta do Gemini:", len(raw), "caracteres")

            if not raw:
                raise ValueError("Gemini retornou resposta vazia.")

            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
            d = json.loads(raw)

            materia = str(d.get("materia", "")).strip()

            if d.get("publicar") is False:
                print("Gemini marcou como não publicável.")
                return None

            if not d.get("titulo") or not d.get("resumo") or len(materia) < 700:
                print("Resposta do Gemini inválida ou curta demais.")
                if model_index + 1 < len(models_to_try):
                    print("Tentando modelo alternativo...")
                    continue
                return None

            d["titulo"] = str(d["titulo"]).strip()
            d["resumo"] = str(d["resumo"]).strip()
            d["materia"] = materia

            print(f"Matéria gerada com sucesso usando {model}.")
            return d

        except Exception as e:
            print(f"Erro Gemini ({model}): {e}")

            if model_index + 1 < len(models_to_try) and _is_transient_gemini_error(e):
                print(f"Modelo {model} indisponível. Tentando {models_to_try[model_index + 1]}...")
                continue

            return None

    return None

def html(a,g):
    h=[f'<p><strong>{g["resumo"]}</strong></p>',
       f'<p><img src="{a["image"]}" alt="{g["titulo"]}" style="max-width:100%;height:auto;border-radius:12px;"></p>']
    h += [f"<p>{p.strip()}</p>" for p in re.split(r"\n+",g["materia"]) if p.strip()]
    h.append(f'<p><small>Fonte: <a href="{a["url"]}" target="_blank" rel="noopener">{a["title"]}</a></small></p>')
    for u in a["videos"]:
        h.append(f'<p><iframe src="{u}" width="100%" height="315" frameborder="0" allowfullscreen loading="lazy"></iframe></p>')
    return "\n".join(h)

def main():
    print("Somente News Gospel + UAU Gospel | Janela 60 dias")
    gemini_client=genai.Client(api_key=GEMINI_API_KEY)
    api=blogger();print("Blogger OK")
    old=existing(api)
    candidates=[]

    for source in SOURCES:
        print("\n=====",source["nome"],"=====")
        for u in links(source):
            if u.rstrip("/") in old:
                print("Já publicado:",u);continue
            a=get_article(u)
            if a:candidates.append(a)

    candidates.sort(key=lambda a:a["date"] or datetime.min,reverse=True)
    print("\nCandidatos válidos:",len(candidates))

    published=0
    while candidates and published<MAX_POSTS_PER_DAY:
        a=candidates.pop(0)
        print("\nVerificando duplicidade:",a["url"])
        if a["url"].rstrip("/") in old:continue
        print("Notícia nova.")
        print("Gerando título e matéria com Gemini...")
        g=gemini(a,gemini_client)
        if not g:
            print("Não foi possível gerar a matéria.")
            if gemini_calls>=MAX_GEMINI_TEXT_CALLS_PER_RUN:
                print("Limite de chamadas do Gemini atingido nesta execução.")
                break
            continue
        try:
            r=api.posts().insert(
                blogId=BLOGGER_BLOG_ID,
                body={"title":g["titulo"].strip(),"content":html(a,g),"labels":["Notícias","Rádio Luz Gospel"]},
                isDraft=False).execute()
            print("PUBLICADO:",r.get("url"))
            old.add(a["url"].rstrip("/"))
            published+=1
        except Exception as e:print("Erro ao publicar:",e)

    print("ROBÔ FINALIZADO. Publicações:",published)

if __name__=="__main__":main()
