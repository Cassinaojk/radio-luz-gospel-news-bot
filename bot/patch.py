import os
import sys
import re
import json
import unicodedata
from datetime import datetime
from urllib.parse import urlparse, urljoin
from difflib import SequenceMatcher
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import bot.main as legacy

# ============================================================
# CORREÇÃO 7.0 - coleta recente + ordenação + redação original
# ============================================================
MAX_AGE_DAYS = 30
TIMEOUT = legacy.TIMEOUT
SIMILARITY_MAX = 0.30
NGRAM_OVERLAP_MAX = 0.08
MIN_COPIED_WORDS = 9

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; RadioLuzGospelBot/7.0)"})

BAD_TERMS = (
    "/category/", "/tag/", "/author/", "/page/", "/search", "/feed",
    "/wp-json", "/comments", "/sobre", "/contato", "/contact",
    "/politica", "/privacidade", "/privacy", "/anuncie", "/publicidade",
    "/advertising", "/login", "/cadastro", "/register", "sitemap", "robots.txt"
)

def date_parse(v):
    if not v:
        return None
    t = re.sub(r"\s+", " ", str(v).strip())
    t = re.sub(r"^(segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)-feira,?\s*", "", t, flags=re.I)
    for f in ("%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S.%f%z",
              "%Y-%m-%dT%H:%M:%S","%Y-%m-%d","%d/%m/%Y",
              "%A, %B %d, %Y","%B %d, %Y","%A, %d %B %Y"):
        try:
            d = datetime.strptime(t[:40], f)
            return d.replace(tzinfo=None) if d.tzinfo else d
        except Exception:
            pass
    months = {"janeiro":1,"fevereiro":2,"março":3,"marco":3,"abril":4,"maio":5,
              "junho":6,"julho":7,"agosto":8,"setembro":9,"outubro":10,
              "novembro":11,"dezembro":12}
    m = re.search(r"([a-zç]+)\s+(\d{1,2}),?\s+(\d{4})", t, re.I)
    if m and m.group(1).lower() in months:
        return datetime(int(m.group(3)), months[m.group(1).lower()], int(m.group(2)))
    return None

def get_article(url):
    try:
        r = s.get(url, timeout=TIMEOUT)
        print(f"Abrindo: {url}\nHTTP: {r.status_code}")
        if r.status_code != 200:
            return None
        x = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print("Erro:", e)
        return None

    title = ""
    for sel in ("h1","h2.post-title","h3.post-title",".post-title",
                'meta[property="og:title"]',"title"):
        n = x.select_one(sel)
        if n:
            title = n.get("content","") if n.name == "meta" else n.get_text(" ", strip=True)
            title = re.sub(r"\s+"," ",title).strip()
            if title: break
    if not title or title.lower() in {"home","início","inicio","notícias","noticias","lançamentos"}:
        return None

    d = None
    for sel in ('meta[property="article:published_time"]','meta[property="og:published_time"]',
                'meta[name="date"]','meta[name="publish_date"]','meta[itemprop="datePublished"]',
                "time",".entry-date",".posted-on",".post-timestamp",".date-header"):
        n = x.select_one(sel)
        if n:
            d = date_parse(n.get("content") or n.get("datetime") or n.get_text(" ",strip=True))
            if d: break
    if not d:
        for sc in x.find_all("script", type="application/ld+json"):
            try:
                data=json.loads(sc.string or sc.get_text())
                for item in (data if isinstance(data,list) else [data]):
                    if isinstance(item,dict):
                        d=date_parse(item.get("datePublished"))
                        if d: break
            except Exception:
                pass
            if d: break

    if d:
        age=(datetime.now()-d).total_seconds()/86400
        print(f"Data encontrada: {d}")
        if age > MAX_AGE_DAYS:
            print(f"Notícia antiga ({age:.1f} dias). Pulando.")
            return None
        if age < -1:
            print("Data futura suspeita. Pulando.")
            return None
    else:
        print("Data não identificada. Aceitando para análise.")

    img=""
    for sel in ('meta[property="og:image"]','meta[name="twitter:image"]',
                'meta[itemprop="image"]','.post-body img','.entry-content img',
                '.post-content img','article img','main img'):
        n=x.select_one(sel)
        if n:
            img=n.get("content") if n.name=="meta" else (n.get("src") or n.get("data-src") or n.get("data-lazy-src"))
            if img and img.startswith("//"): img="https:"+img
            if img and img.startswith(("http://","https://")) and not any(z in img.lower() for z in ("logo","avatar","icon","favicon")):
                break
            img=""

    if not img:
        print("Imagem original não encontrada. Pulando.")
        return None

    box=next((x.select_one(sel) for sel in (".post-body",".entry-content",".post-content","article","main") if x.select_one(sel)),x)
    ps=[]
    for p in box.find_all("p"):
        t=re.sub(r"\s+"," ",p.get_text(" ",strip=True))
        if len(t)>=35: ps.append(t)
    text="\n\n".join(ps)
    if len(text)<legacy.MIN_SOURCE_CHARS or len(ps)<legacy.MIN_SOURCE_PARAGRAPHS:
        print("Conteúdo insuficiente:",len(text),"caracteres")
        return None

    vids=[]
    for n in x.find_all("iframe"):
        u=n.get("src","").strip()
        if u.startswith("//"): u="https:"+u
        if u.startswith(("http://","https://")) and u not in vids: vids.append(u)

    print("Notícia encontrada:",title)
    print("Texto extraído:",len(text),"caracteres")
    print("Imagem encontrada:",img)
    print("Vídeos encontrados:",len(vids))
    return {"url":url,"title":title,"date":d,"image":img,"text":text[:14000],"videos":vids[:5]}

def links(source):
    out=[]; seen=set()
    host0=urlparse(source["url"]).netloc.lower()

    def add(u, discovered_date=None):
        u=u.split("#",1)[0].strip()
        if not u.startswith(("http://","https://")): return
        host=urlparse(u).netloc.lower()
        low=u.lower()
        if host != host0 and not host.endswith("."+host0): return
        if any(z in low for z in BAD_TERMS): return
        if re.search(r"\.(jpg|jpeg|png|gif|webp|pdf|xml)(\?|$)",low): return
        if u in seen: return
        seen.add(u)
        out.append((u, discovered_date))

    # Feed primeiro: ele normalmente fornece os itens mais recentes.
    for feed in source.get("feeds",[]):
        try:
            r=s.get(feed,timeout=TIMEOUT)
            print(f"Abrindo: {feed}\nHTTP: {r.status_code}")
            if r.status_code==200:
                x=BeautifulSoup(r.text,"xml")
                for item in x.find_all(["item","entry"]):
                    n=item.find("link")
                    u=(n.get("href") or n.get_text(strip=True)) if n else ""
                    dv=None
                    for tag in ("pubDate","published","updated","date"):
                        z=item.find(tag)
                        if z:
                            dv=date_parse(z.get_text(" ",strip=True)); 
                            if dv: break
                    add(u,dv)
        except Exception as e: print("Erro feed:",e)

    # Página inicial como complemento.
    try:
        r=s.get(source["url"],timeout=TIMEOUT)
        print(f"Abrindo: {source['url']}\nHTTP: {r.status_code}")
        if r.status_code==200:
            x=BeautifulSoup(r.text,"html.parser")
            for a in x.find_all("a",href=True):
                add(urljoin(source["url"],a["href"]))
    except Exception as e: print("Erro fonte:",e)

    # Não limitar antes de ordenar. Testa um conjunto maior.
    candidates=out[:max(legacy.MAX_LINKS_PER_SOURCE,100)]
    scored=[]
    for u,dv in candidates:
        if dv: scored.append((dv,u))
        else: scored.append((datetime.min,u))
    scored.sort(reverse=True)
    result=[u for _,u in scored]
    print(f"Links coletados e ordenados: {len(result)}")
    return result[:max(legacy.MAX_LINKS_PER_SOURCE,100)]

def norm_words(text):
    text=unicodedata.normalize("NFKD",text or "")
    text="".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.findall(r"[a-z0-9]+",text)

def ngrams(words,n=8):
    return {" ".join(words[i:i+n]) for i in range(max(0,len(words)-n+1))}

def longest_common_phrase(src_words,out_words,min_words=MIN_COPIED_WORDS):
    if not src_words or not out_words: return 0
    positions={}
    for i,w in enumerate(src_words): positions.setdefault(w,[]).append(i)
    best=0
    for j,w in enumerate(out_words):
        for i in positions.get(w,[])[:20]:
            k=0
            while i+k<len(src_words) and j+k<len(out_words) and src_words[i+k]==out_words[j+k]:
                k+=1
            best=max(best,k)
            if best>=min_words:return best
    return best

def originality_check(source_text,generated_text):
    src=norm_words(source_text); out=norm_words(generated_text)
    if len(out)<100:return False,"matéria curta demais"
    ratio=SequenceMatcher(None,src,out,autojunk=False).ratio()
    src8=ngrams(src,8); out8=ngrams(out,8)
    overlap=len(src8 & out8)/max(1,min(len(src8),len(out8)))
    longest=longest_common_phrase(src,out)
    print(f"Verificação de originalidade: similaridade={ratio:.3f} sobreposição_8gram={overlap:.3f} maior_frase={longest} palavras")
    if longest>=MIN_COPIED_WORDS:return False,f"há sequência de {longest} palavras iguais"
    if overlap>NGRAM_OVERLAP_MAX:return False,f"sobreposição 8-gram alta ({overlap:.3f})"
    if ratio>SIMILARITY_MAX:return False,f"similaridade global alta ({ratio:.3f})"
    return True,"OK"

def gemini(a,client):
    if legacy.gemini_calls>=legacy.MAX_GEMINI_TEXT_CALLS_PER_RUN:return None
    prompt=f"""
Você é jornalista do Rádio Luz Gospel. Escreva uma matéria NOVA, do zero.
Não resuma, não traduza e não parafraseie frase por frase. Extraia somente os fatos da fonte e reorganize-os em estrutura jornalística própria.
Não copie frases ou parágrafos. Não invente fatos. Crie título, resumo e matéria com vocabulário natural em português do Brasil.
Matéria: aproximadamente 700 a 1200 palavras.
Retorne SOMENTE JSON válido:
{{"publicar":true,"titulo":"...","resumo":"...","materia":"..."}}
Se não houver informação suficiente, publicar=false.

TÍTULO ORIGINAL (somente referência factual):
{a['title']}

FONTE:
{a['url']}

TEXTO:
{a['text']}
"""
    models=[legacy.GEMINI_MODEL_TEXT]
    if legacy.GEMINI_FALLBACK_MODEL and legacy.GEMINI_FALLBACK_MODEL not in models: models.append(legacy.GEMINI_FALLBACK_MODEL)
    for model in models:
        try:
            r=legacy._gemini_request(client,model,prompt); legacy.gemini_calls+=1
            raw=(getattr(r,"text",None) or "").strip()
            print("Resposta do Gemini:",len(raw),"caracteres")
            raw=re.sub(r"^```(?:json)?\s*|\s*```$","",raw).strip()
            d=json.loads(raw)
            if d.get("publicar") is False:return None
            titulo=str(d.get("titulo","")).strip(); resumo=str(d.get("resumo","")).strip(); materia=str(d.get("materia","")).strip()
            if not titulo or not resumo or len(materia)<700:
                print("Resposta do Gemini inválida ou curta demais"); continue
            ok,reason=originality_check(a["text"],titulo+"\n"+resumo+"\n"+materia)
            if not ok:
                print("PUBLICAÇÃO BLOQUEADA:",reason); continue
            d.update(titulo=titulo,resumo=resumo,materia=materia)
            print(f"Matéria original aprovada usando {model}.")
            return d
        except Exception as e:
            print(f"Erro Gemini ({model}): {e}")
            if not legacy._is_transient_gemini_error(e): return None
    return None

def source_name(url):
    host=urlparse(url or "").netloc.lower()
    if "newsgospel.com.br" in host:return "News Gospel"
    if "uaugospel.com.br" in host:return "UAU Gospel"
    return host.replace("www.","") or "fonte original"

def html(a,d):
    # Mantém a URL original em atributo para o detector de duplicatas.
    out=legacy.html(a,d)
    name=source_name(a.get("url",""))
    attribution=f'<p><small>Fonte de apuração: <a href="{a.get("url","")}" rel="nofollow noopener" target="_blank">{name}</a></small></p>'
    out=re.sub(r'<p><small>Fonte:\s*<a\s+href="[^"]*"[^>]*>.*?</a></small></p>',attribution,out,count=1,flags=re.I|re.S)
    out=re.sub(r'<p><small>Fonte:.*?</small></p>',attribution,out,count=1,flags=re.I|re.S)
    return out

legacy.get_article=get_article
legacy.links=links
legacy.gemini=gemini
legacy.html=html
legacy.MAX_AGE_DAYS=MAX_AGE_DAYS
legacy.MAX_POSTS_PER_DAY=3
legacy.MAX_GEMINI_TEXT_CALLS_PER_RUN=3

print("CORREÇÃO 7.0 ATIVA: notícias recentes ordenadas + News Gospel/UAU Gospel + redação original")
legacy.main()
