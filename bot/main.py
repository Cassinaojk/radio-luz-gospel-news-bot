import os, re, json, requests, io, contextlib, unicodedata, warnings, builtins
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from datetime import datetime
from urllib.parse import urlparse, urljoin, quote, urlencode, parse_qsl
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

_VERBOSE = os.getenv("VERBOSE_LOG", "false").lower() in ("1", "true", "yes", "sim")
_orig_print = builtins.print

def print(*a, **k):
    if _VERBOSE:
        return _orig_print(*a, **k)
    m = " ".join(str(x) for x in a).strip()
    keep = ("RÁDIO", "VERSÃO", "Fontes:", "RESULTADO", "Publicações:", "Ignoradas:",
            "Falhas:", "Divulgação:", "MAX_AGE_DAYS", "🎵", "📰", "---")
    if any(m.startswith(p) for p in keep):
        _orig_print(*a, **k)

BLOGGER_BLOG_ID = os.environ["BLOGGER_BLOG_ID"]
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

BLOG_NAME = os.getenv("BLOG_NAME", "Rádio Luz Gospel").strip()
BLOG_HOME_URL = os.getenv("BLOG_HOME_URL", "https://radioluzgospel.blogspot.com").rstrip("/")
SEO_TITLE_SUFFIX = os.getenv("SEO_TITLE_SUFFIX", f" | {BLOG_NAME}").strip()
SEO_DESCRIPTION_MAX = int(os.getenv("SEO_DESCRIPTION_MAX", "160"))
SEO_KEYWORDS_MAX = int(os.getenv("SEO_KEYWORDS_MAX", "12"))

PROMO_ENABLED = os.getenv("PROMO_ENABLED", "false").lower() in ("1","true","yes","sim")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "2"))
MAX_GEMINI_TEXT_CALLS_PER_RUN = int(os.getenv("MAX_GEMINI_TEXT_CALLS_PER_RUN", "6"))
MAX_LINKS_PER_SOURCE = 120
MAX_AGE_DAYS = int(os.getenv("MAX_AGE_DAYS", "4"))
MIN_SOURCE_CHARS = 250
TIMEOUT = 25

GEMINI_MODEL_TEXT = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip()
AI_PROVIDER_TIMEOUT = int(os.getenv("AI_PROVIDER_TIMEOUT", "90"))

IMAGE_FILES = [f"bot/Imagens/radioluzgospel{i}.{ext}" for i, ext in
               [(1,"png")]+[(n,"jpg") for n in range(2,13)]]

SOURCES = [
    {"nome":"News Gospel","url":"https://www.newsgospel.com.br/",
     "feeds":["https://www.newsgospel.com.br/feed/","https://www.newsgospel.com.br/rss.xml","https://newsgospel.com.br/feed/"]},
    {"nome":"Folha Gospel - Música","url":"https://folhagospel.com/musica/",
     "feeds":["https://folhagospel.com/feed/","https://folhagospel.com/musica/feed/"]},
    {"nome":"Guiame - Música","url":"https://guiame.com.br/musica",
     "feeds":["https://guiame.com.br/rss.xml","https://guiame.com.br/feed/"]},
    {"nome":"iGospel","url":"https://www.igospel.org.br/",
     "feeds":["https://www.igospel.org.br/feed/","https://www.igospel.org.br/feed","https://igospel.org.br/feed/"]},
    {"nome":"Fuxico Gospel","url":"https://www.fuxicogospel.com.br/",
     "feeds":["https://www.fuxicogospel.com.br/feed/","https://www.fuxicogospel.com.br/feed"]},
]

BAD_PATHS = (
    "/category/","/tag/","/author/","/page/","/search/","/feed/","/wp-json/",
    "/comments/","/sobre","/contato","/contact","/politica/","/privacidade/",
    "/privacy/","/anuncie/","/publicidade/","/advertising/","/login/",
    "/cadastro/","/register/","/sitemap/","/robots.txt","/institucional",
    "/fale-conosco","/quem-somos","/colunistas/","/autores/","/autor/",
    "/terms","/termos","/cookies","/seguranca","/segurança","/newsletter",
    "/rss","/amp/","/equipe/",
)

BAD_TITLES = {
    "israel","notícias","noticias","mundo cristão","mundo cristao",
    "missões","missoes","testemunhos","família","familia",
    "vídeos gospel","videos gospel","livros gospel","agenda gospel",
    "música gospel nacional","musica gospel nacional",
    "música gospel internacional","musica gospel internacional",
    "gastronomia","moda e beleza","turismo","saúde","saude",
    "política de segurança e privacidade","institucional","fale conosco",
    "home","início","inicio","últimas notícias","ultimas noticias",
    "404","página não encontrada","política de privacidade",
}

SHARE_DOMAINS = ("pinterest.","reddit.com/submit","facebook.com/sharer",
    "twitter.com/intent","x.com/intent","whatsapp.com/","t.me/share","linkedin.com/share")

VIDEO_HOSTS = ("youtube.com/embed/","youtube.com/watch","youtube-nocookie.com/embed/",
    "youtu.be/","player.vimeo.com","vimeo.com/video","facebook.com/plugins/video",
    "instagram.com/p/","instagram.com/reel/","dailymotion.com/embed","twitch.tv/")

s = requests.Session()
s.headers.update({"User-Agent":"Mozilla/5.0 (compatible; RadioLuzGospelBot/15.3)"})

gemini_calls = 0
_image_url_cache = {}

# ===== util =====
def normalize_url(u): return (u or "").strip().split("#")[0].rstrip("/")

def bad_url(u):
    u = normalize_url(u).lower()
    if not u.startswith(("http://","https://")): return True
    if any(x in u for x in SHARE_DOMAINS): return True
    p = urlparse(u).path
    if any(x in p for x in BAD_PATHS): return True
    if re.search(r"\.(pdf|jpe?g|png|gif|webp|svg|xml|zip)$", p): return True
    return False

def soup(url, xml=False):
    try:
        r = s.get(url, timeout=TIMEOUT)
        if r.status_code != 200: return None
        return BeautifulSoup(r.text, "xml" if xml else "html.parser")
    except Exception:
        return None

def date_parse(v):
    if not v: return None
    for f in ("%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S.%f%z","%Y-%m-%dT%H:%M:%S","%Y-%m-%d","%d/%m/%Y"):
        try:
            d = datetime.strptime(str(v).strip()[:32], f)
            return d.replace(tzinfo=None) if d.tzinfo else d
        except Exception: pass
    return None

def article_date(x):
    for sel in ('meta[property="article:published_time"]','meta[property="og:published_time"]','meta[name="date"]','meta[itemprop="datePublished"]'):
        n = x.select_one(sel)
        if n:
            d = date_parse(n.get("content",""))
            if d: return d
    for sc in x.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(sc.string or sc.get_text())
            for it in (data if isinstance(data,list) else [data]):
                if isinstance(it,dict):
                    for g in (it.get("@graph") or [it]):
                        d = date_parse(g.get("datePublished") if isinstance(g,dict) else None)
                        if d: return d
        except Exception: pass
    return None

def image_original(x):
    for sel in ('meta[property="og:image"]','meta[property="og:image:secure_url"]','meta[name="twitter:image"]'):
        n = x.select_one(sel)
        if n:
            u = (n.get("content") or "").strip()
            if u.startswith("//"): u = "https:"+u
            if u.startswith(("http://","https://")): return u
    return ""

def videos(x):
    out = []
    for n in x.find_all("iframe"):
        u = (n.get("src") or n.get("data-src") or "").strip()
        if u.startswith("//"): u = "https:"+u
        if u.startswith(("http://","https://")) and any(h in u.lower() for h in VIDEO_HOSTS) and u not in out:
            out.append(u)
    return out[:3]

def resolve_repo_image_url(rel):
    if not rel: return ""
    if rel in _image_url_cache: return _image_url_cache[rel]
    repo = os.getenv("GITHUB_REPOSITORY","").strip()
    branch = os.getenv("GITHUB_REF_NAME","").strip() or "main"
    if not repo:
        _image_url_cache[rel] = ""; return ""
    r_e, b_e, p_e = quote(repo,safe="/"), quote(branch,safe=""), quote(rel,safe="/")
    for cand in (f"https://cdn.jsdelivr.net/gh/{r_e}@{b_e}/{p_e}", f"https://raw.githubusercontent.com/{r_e}/{b_e}/{p_e}"):
        try:
            r = requests.get(cand, stream=True, timeout=12)
            if r.status_code==200 and (r.headers.get("Content-Type","").lower().startswith("image/")):
                _image_url_cache[rel] = cand; return cand
            r.close()
        except Exception: pass
    _image_url_cache[rel] = ""
    return ""

def pick_next_image_url(n):
    if not IMAGE_FILES: return "", ""
    total = len(IMAGE_FILES); start = n % total
    for i in range(total):
        rel = IMAGE_FILES[(start+i)%total]
        u = resolve_repo_image_url(rel)
        if u: return u, rel
    return "", ""

def get_article(url):
    x = soup(url)
    if not x: return None
    n = x.find("h1") or x.find("title")
    title = re.sub(r"\s+"," ", n.get_text(" ",strip=True) if n else "").strip()
    if not title: return None
    tl = title.lower().strip()
    if tl in BAD_TITLES or any(tl.startswith(b) for b in BAD_TITLES):
        return None
    d = article_date(x)
    if d and (datetime.now()-d).total_seconds()/86400 > MAX_AGE_DAYS:
        return None
    img = image_original(x) or ""
    box = x.find("article") or x.find("main") or x
    ps = [re.sub(r"\s+"," ",p.get_text(" ",strip=True)) for p in box.find_all("p")]
    ps = [p for p in ps if len(p)>=35]
    text = "\n\n".join(ps)
    if len(text) < MIN_SOURCE_CHARS: return None
    inline = [{"url":img,"after_paragraph":2,"is_main":True}] if img else []
    return {"url":normalize_url(url),"title":title,"date":d,"image":img,
            "text":text[:16000],"videos":videos(x),"inline_images":inline}

def links(source):
    out, seen = [], set()
    src_host = urlparse(source["url"]).netloc.lower()
    def match(u):
        h = urlparse(u).netloc.lower()
        return h==src_host or h.replace("www.","",1)==src_host.replace("www.","",1)
    for feed in source["feeds"]:
        x = soup(feed, True)
        if not x: continue
        for it in x.find_all(["item","entry"]):
            n = it.find("link")
            if not n: continue
            u = normalize_url(n.get("href") or n.get_text(strip=True) or "")
            if u and not bad_url(u) and match(u) and u not in seen:
                seen.add(u); out.append(u)
    x = soup(source["url"])
    if x:
        for a in x.find_all("a", href=True):
            u = normalize_url(urljoin(source["url"], a["href"]))
            if u and not bad_url(u) and match(u) and u not in seen:
                p = urlparse(u).path.strip("/")
                if p.count("/")>=1 and len(p)>10:
                    seen.add(u); out.append(u)
    return out[:MAX_LINKS_PER_SOURCE]

def blogger():
    creds = Credentials(None, refresh_token=BLOGGER_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/blogger"])
    return build("blogger","v3",credentials=creds,cache_discovery=False)

_STOP = {"a","o","as","os","de","da","do","das","dos","e","em","um","uma","para","por",
         "com","no","na","nos","nas","que","se","ao","aos","sua","seu","suas","seus",
         "mais","como","sobre","entre","apos","ate","ja","nao","muito","bem","ainda",
         "tambem","so","esse","essa","este","esta","isso","ele","ela","eles","elas",
         "vai","vem","foi","sao","estao","tem","ter","eh","ser","sera","novo","nova"}

def _cmp_norm(t):
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9\s]"," ", t)
    return set(w for w in t.split() if len(w)>1 and w not in _STOP)

def _sim(a,b):
    if not a or not b: return 0.0
    return len(a&b)/len(a|b) if (a|b) else 0.0

def existing(api):
    blog_urls, source_urls, titles = set(), set(), []
    token, bot = None, 0
    try:
        while True:
            kw = {"blogId":BLOGGER_BLOG_ID,"maxResults":500,"fetchBodies":False}
            if token: kw["pageToken"] = token
            data = api.posts().list(**kw).execute()
            for p in data.get("items",[]):
                u = normalize_url(p.get("url",""))
                t = (p.get("title") or "").strip()
                if u: blog_urls.add(u)
                if t: titles.append(t)
                c = p.get("content","") or ""
                for m in re.findall(r"RADIO_LUZ_GOSPEL_SOURCE_URL:\s*(https?://[^\s]+?)\s*-->", c, flags=re.I):
                    source_urls.add(normalize_url(m))
                if re.search(r"RADIO_LUZ_GOSPEL_SOURCE_URL:", c, flags=re.I): bot += 1
            token = data.get("nextPageToken")
            if not token: break
    except Exception as e:
        print("Blogger:", e)
    print(f"Posts no Blogger: {len(blog_urls)} | Fontes: {len(source_urls)} | Robô: {bot}")
    return blog_urls, source_urls, titles, bot

def is_dup(api, title, existing_titles):
    nw = _cmp_norm(title)
    if not nw: return False, ""
    for et in existing_titles:
        if _sim(nw, _cmp_norm(et)) >= 0.60: return True, et
    try:
        q = " ".join(sorted(nw, key=len, reverse=True)[:2])
        r = api.posts().search(blogId=BLOGGER_BLOG_ID, q=q, fetchBodies=False, maxResults=10).execute()
        for p in r.get("items",[]):
            if _sim(nw, _cmp_norm(p.get("title",""))) >= 0.60:
                return True, p.get("title","")
    except Exception: pass
    return False, ""

# ===== música =====
_M_STRONG = {"lança","lançou","lançamento","lancamento","lanca","lancou","estreia",
    "estreou","single","singles","álbum","album","álbuns","albuns","ep","eps",
    "mixtape","disco","cd","vinil","videoclipe","clipe","faixa","faixas","track",
    "grava","gravou","gravação","gravacao","cantor","cantora","banda","grupo musical",
    "música","musica","musical","canção","cancao","louvor","louvores","worship",
    "turnê","turne","tour","shows","show","festival","spotify","deezer",
    "streaming","playlist","gravadora","selo"}
_M_WEAK = {"artista","artistas","voz","vocal","melodia","harmonia","arranjo",
    "compositor","compositora","letra","letras","refrão","refrao","hits","hit",
    "billboard","grammy","rádio","radio"}
_M_NEG = {"livro","livros","filme","filmes","série","serie","documentário",
    "documentario","podcast","entrevista","polêmica","polemica","morte","morreu",
    "faleceu","doença","doenca","hospital","política","politica","eleição",
    "eleicao","governo","escândalo","escandalo","crime","prisão","prisao",
    "casamento","divórcio","divorcio","namoro","aniversário","aniversario"}

def _s(t):
    t = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()

def music_score(a):
    ti, tx = _s(a.get("title","")), _s((a.get("text") or "")[:4000])
    sc = 0
    st = sum(1 for k in _M_STRONG if re.search(r"\b"+re.escape(_s(k))+r"\b", ti))
    wt = sum(1 for k in _M_WEAK if re.search(r"\b"+re.escape(_s(k))+r"\b", ti))
    sc += st*25 + wt*8
    sb = sum(1 for k in _M_STRONG if _s(k) in (ti+" "+tx))
    wb = sum(1 for k in _M_WEAK if _s(k) in (ti+" "+tx))
    sc += min(sb*5,30) + min(wb*2,10)
    if re.match(r"^(lanca|lancou|lancam|estreia|estreou|grava|gravou|artista|cantor|cantora|banda|grupo|dupla)\b", ti): sc += 15
    if re.search(r"\b(single|album|ep|videoclipe|clipe|faixa|track|mixtape)\b", ti): sc += 20
    sc -= sum(1 for n in _M_NEG if re.search(r"\b"+re.escape(_s(n))+r"\b", ti)) * 20
    return max(0, min(sc, 100))

# ===== limpeza de fonte =====
_SRC_VEH = ["Fuxico Gospel","fuxicogospel","News Gospel","newsgospel",
    "Folha Gospel","folhagospel","Guiame","guiame","iGospel","igospel",
    "UAU Gospel","uaugospel","Gospel Prime","gospelprime","Super Gospel","supergospel",
    "Comunhão","comunhao","Portal do Trono","portaldotrono","Gospel Mais","gospelmais"]

_SRC_PAT = [
    r"(?:confirmad[oa]s?|divulgad[oa]s?|revelad[oa]s?|informad[oa]s?|publicad[oa]s?|noticiad[oa]s?|reportad[oa]s?)\s+(?:pelo|pela|pelo portal|pela equipe|pelo site|pelo blog|pelo jornal|pela revista)\s+[^.!\n]{1,80}[.!]?",
    r"(?:segundo|conforme|de acordo com|como informou|como noticiou|como divulgou|como revelou|como publicou|como reportou)\s+(?:o|a|os|as)?\s*(?:portal|site|blog|jornal|revista|coluna)?\s*[^.!\n]{1,80}[.!]?",
    r"(?:fonte|via|cr[eé]ditos?|imagem|foto)\s*[:\-–]\s*[^.!\n]{1,100}[.!]?",
    r"a\s+reportagem\s+foi\s+baseada[^.!\n]{0,200}[.!]?",
    r"caso\s+haja\s+qualquer\s+corre[çc][ãa]o[^.!\n]{0,200}[.!]?",
    r"a\s+reda[çc][ãa]o\s+pode\s+ser\s+contatada[^.!\n]{0,200}[.!]?",
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    r"https?://[^\s<>\"]+",
    r"(?:leia|continue|veja|confira)\s+(?:mais|a\s+mat[eé]ria\s+completa)\s+(?:em|no|na)\s+[^.!\n]{1,120}[.!]?",
    r"publicad[oa]\s+originalmente[^.!\n]{0,120}[.!]?",
    r"com\s+informa[çc][õo]es\s+(?:de|do|da)\s+[^.!\n]{1,120}[.!]?",
    r"\((?:foto|imagem|divulga[çc][ãa]o)\s*:[^)]{0,120}\)",
]

def clean_src(text):
    if not text: return text
    for p in _SRC_PAT:
        text = re.sub(p, "", text, flags=re.I|re.S)
    for v in _SRC_VEH:
        text = re.sub(r"\b(?:o|a|os|as|do|da|dos|das|no|na|nos|nas|pelo|pela)?\s*"+re.escape(v)+r"\b", "", text, flags=re.I)
    text = re.sub(r"[ \t]{2,}"," ", text)
    text = re.sub(r"\n{3,}","\n\n", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"\.\s*\.", ".", text)
    return text.strip()

def clean_title_resumo(t, r):
    t = re.sub(r"https?://\S+","", t); t = re.sub(r"\S+@\S+\.\S+","", t)
    t = re.sub(r"\s{2,}"," ", t).strip(" -–—|:.,")
    return t, clean_src(r)

# ===== IA =====
def gemini(article):
    global gemini_calls
    if gemini_calls >= MAX_GEMINI_TEXT_CALLS_PER_RUN: return None
    provs = []
    if GEMINI_API_KEY: provs.append(("gemini", GEMINI_API_KEY, GEMINI_MODEL_TEXT))
    if GEMINI_API_KEY_2: provs.append(("gemini-2", GEMINI_API_KEY_2, GEMINI_FALLBACK_MODEL))
    if GROQ_API_KEY: provs.append(("groq", GROQ_API_KEY, GROQ_MODEL))
    if MISTRAL_API_KEY: provs.append(("mistral", MISTRAL_API_KEY, MISTRAL_MODEL))
    if not provs: return None

    mh = ""
    if article.get("_music_score", 0) >= 60:
        mh = "⚠ ESTA MATÉRIA É UM LANÇAMENTO MUSICAL. Destaque artista, música/álbum, data, plataformas e gravadora.\n\n"

    prompt = f"""Você é jornalista do Rádio Luz Gospel. Escreva uma matéria NOVA, autoral.
Use SOMENTE os fatos do texto-fonte. Não invente.

REGRAS ABSOLUTAS:
1. NUNCA mencione o veículo de origem (site, portal, jornal, blog).
2. NUNCA escreva "segundo o X", "conforme o X", "fonte: X", "via X",
   "com informações de X", "publicado originalmente em X".
3. NUNCA inclua e-mails, URLs, "a reportagem foi baseada…",
   "caso haja correção…", "a redação pode ser contatada…".
4. NUNCA copie frases literais — reescreva.
5. Escreva como se o Rádio Luz Gospel tivesse apurado diretamente.
6. Mantenha nomes de pessoas, igrejas, artistas e eventos (são fatos).

{mh}FOCO: destaque LANÇAMENTOS MUSICAIS quando houver.

CRITÉRIO: publicar=true para QUALQUER notícia gospel/cristã.
publicar=false só se for COMPLETAMENTE alheia.

FORMATO JSON:
{{"publicar":true,"titulo":"...","resumo":"...","materia":"...","assunto_principal":"...","palavras_chave":["..."],"categoria_seo":"..."}}

TÍTULO DE REFERÊNCIA (não cite): {article['title']}
TEXTO-FONTE (não cite):
{article['text']}
"""
    for provider, key, model in provs:
        if gemini_calls >= MAX_GEMINI_TEXT_CALLS_PER_RUN: break
        try:
            print(f"IA: {provider}/{model}...")
            if provider.startswith("gemini"):
                with contextlib.redirect_stderr(io.StringIO()):
                    _c = genai.Client(api_key=key)
                    try:
                        resp = _c.models.generate_content(
                            model=model, contents=prompt,
                            config={"response_mime_type":"application/json"})
                    finally:
                        try: _c.close()
                        except Exception: pass
                raw = (getattr(resp, "text", None) or "").strip()
            else:
                ep = {"groq":"https://api.groq.com/openai/v1/chat/completions",
                      "mistral":"https://api.mistral.ai/v1/chat/completions"}[provider]
                r = requests.post(ep, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                    json={"model":model,"messages":[{"role":"user","content":prompt}],
                          "temperature":0.2,"max_tokens":5000,
                          "response_format":{"type":"json_object"}},
                    timeout=AI_PROVIDER_TIMEOUT)
                j = r.json()
                if "choices" not in j:
                    raise Exception(f"{provider}: {str(j)[:160]}")
                raw = j["choices"][0]["message"]["content"].strip()
            gemini_calls += 1
            raw = re.sub(r"^```(?:json)?\s*|\s*```$","",raw).strip()
            data = json.loads(raw)
            if data.get("publicar") is False: continue
            ti = str(data.get("titulo","")).strip()
            rs = str(data.get("resumo","")).strip()
            mt = str(data.get("materia","")).strip()
            ti, rs = clean_title_resumo(ti, rs)
            mt = clean_src(mt)
            if not ti or not rs or len(mt) < 700: continue
            print(f"✓ IA: {provider}")
            return {"publicar":True,"titulo":ti,"resumo":rs,"materia":mt,
                    "assunto_principal":str(data.get("assunto_principal","")).strip(),
                    "palavras_chave":data.get("palavras_chave",[])[:SEO_KEYWORDS_MAX],
                    "categoria_seo":str(data.get("categoria_seo","")).strip()}
        except Exception as exc:
            print(f"⚠ {provider}: {str(exc)[:160]}")
    return None

# ===== SEO =====
def build_seo(article, gen, final_img=""):
    tb = str(gen.get("titulo","")).strip()
    rs = str(gen.get("resumo","")).strip()
    mt = str(gen.get("materia","")).strip()
    asu = str(gen.get("assunto_principal","")).strip()
    cat = str(gen.get("categoria_seo","")).strip()
    pal = list(gen.get("palavras_chave",[]) or [])
    title = f"{tb}{SEO_TITLE_SUFFIX}" if SEO_TITLE_SUFFIX and not tb.lower().endswith(SEO_TITLE_SUFFIX.lower()) else tb
    desc = (rs or BeautifulSoup(mt,"html.parser").get_text(" ",strip=True)[:SEO_DESCRIPTION_MAX])[:SEO_DESCRIPTION_MAX]
    kw = [x for x in [asu,cat]+[str(p).strip() for p in pal if str(p).strip()] if x]
    for fb in ("música gospel","gospel","notícias gospel",BLOG_NAME):
        if fb.lower() not in {k.lower() for k in kw}: kw.append(fb)
    keywords = ", ".join(kw[:SEO_KEYWORDS_MAX])
    labels = ["Notícias","Rádio Luz Gospel"]
    if cat: labels.append(re.sub(r"\s+"," ",cat).strip())
    if asu and len(asu)<=40: labels.append(re.sub(r"\s+"," ",asu).strip())
    if article.get("date"): labels.append(str(article["date"].year))
    seen, lf = set(), []
    for l in labels:
        if l and l.lower() not in seen: seen.add(l.lower()); lf.append(l)
    img = final_img or article.get("image","")
    can = article.get("url","")
    pub = (article.get("date") or datetime.now()).isoformat()
    sch = {"@context":"https://schema.org","@type":"NewsArticle",
        "mainEntityOfPage":{"@type":"WebPage","@id":can},
        "headline":tb[:110],"description":desc,
        "image":[img] if img else [],"datePublished":pub,
        "dateModified":datetime.now().isoformat(),
        "author":{"@type":"Organization","name":BLOG_NAME,"url":BLOG_HOME_URL},
        "publisher":{"@type":"Organization","name":BLOG_NAME,"url":BLOG_HOME_URL,
                     "logo":{"@type":"ImageObject","url":img or f"{BLOG_HOME_URL}/favicon.ico"}},
        "articleSection":cat or "Notícias Gospel","keywords":keywords,
        "inLanguage":"pt-BR","url":can}
    bc = {"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
        {"@type":"ListItem","position":1,"name":"Início","item":BLOG_HOME_URL},
        {"@type":"ListItem","position":2,"name":"Notícias","item":f"{BLOG_HOME_URL}/search/label/Not%C3%ADcias"},
        {"@type":"ListItem","position":3,"name":tb[:80],"item":can}]}
    esc = lambda x: (x or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
    head = f"""<!-- SEO -->
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="keywords" content="{esc(keywords)}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{esc(can)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(can)}">
<meta property="og:image" content="{esc(img)}">
<meta property="article:published_time" content="{pub}">
<meta property="article:section" content="{esc(sch['articleSection'])}">
<script type="application/ld+json">{json.dumps(sch, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(bc, ensure_ascii=False)}</script>
<!-- FIM SEO -->"""
    return {"title":title,"titulo_base":tb,"labels":lf[:10],"html_head":head}

def html_render(article, gen, final_img="", seo=None):
    seo = seo or {}
    ti = seo.get("titulo_base") or gen.get("titulo","")
    esc = lambda x: (x or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
    img = final_img or article["image"]
    c = [seo.get("html_head",""),
         f'<p><strong>{gen["resumo"]}</strong></p>',
         f'<p><img src="{esc(img)}" alt="{esc(ti)}" title="{esc(ti)}" style="max-width:100%;height:auto;border-radius:12px;"></p>']
    paras = [p.strip() for p in re.split(r"\n+", gen["materia"]) if p.strip()]
    inline = sorted(list(article.get("inline_images") or [])[:1], key=lambda x:x.get("after_paragraph",9999))
    body, idx = [], 0
    for im in inline:
        try: tgt = max(0, min(int(im.get("after_paragraph",9999)), len(paras)))
        except Exception: tgt = len(paras)
        while idx < tgt: body.append(f"<p>{paras[idx]}</p>"); idx += 1
        u = im.get("url","")
        if u:
            body.append(f'<p style="text-align:center;margin:24px 0;"><img src="{esc(u)}" alt="{esc(ti)}" title="{esc(ti)}" style="max-width:100%;height:auto;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,.10);display:block;margin:auto;"></p>')
    while idx < len(paras): body.append(f"<p>{paras[idx]}</p>"); idx += 1
    c.extend(body)
    for v in article["videos"]:
        c.append(f'<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:12px;margin:24px 0;"><iframe src="{v}" style="position:absolute;inset:0;width:100%;height:100%;border:0;" allowfullscreen loading="lazy"></iframe></div>')
    c.append('<div style="max-width:600px;margin:2rem auto;text-align:center;"><h3 style="color:#1DB954;">🎵 Top 2026 — Rádio Luz Gospel</h3><iframe style="border-radius:12px;" src="https://open.spotify.com/embed/playlist/14OteRoEl6CVEsTCpYCYyx?utm_source=generator" width="100%" height="380" frameborder="0" allowfullscreen loading="lazy"></iframe></div>')
    c.append('<div style="margin:24px 0;padding:18px;border:1px solid #ddd;border-radius:12px;text-align:center;"><p><strong>📲 Receba as próximas notícias no Telegram</strong></p><p><a href="https://t.me/radioluzgospelnoticias" target="_blank">👉 ENTRAR NO CANAL</a></p></div>')
    marker = f"<!-- RADIO_LUZ_GOSPEL_SOURCE_URL: {esc(article['url'])} -->"
    return clean_src("\n".join(c)) + "\n" + marker

def promo_url(u):
    try:
        p = urlparse(u); q = dict(parse_qsl(p.query))
        q.update({"utm_source":"telegram","utm_medium":"social","utm_campaign":"noticias"})
        return p._replace(query=urlencode(q)).geturl()
    except Exception: return u

def promote(title, url, summary=""):
    if not (PROMO_ENABLED and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID): return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id":TELEGRAM_CHAT_ID,"parse_mode":"HTML",
                  "text":f"📰 <b>{title}</b>\n\n{summary[:300]}\n\n👉 Leia mais: {promo_url(url)}",
                  "disable_web_page_preview":False}, timeout=20)
        if r.status_code==200 and r.json().get("ok"): return True
    except Exception: pass
    return False

def main():
    print("Fontes: News Gospel + Folha Gospel + Guiame + iGospel + Fuxico Gospel")
    print(f"Divulgação: Telegram={'ON' if PROMO_ENABLED and TELEGRAM_BOT_TOKEN else 'OFF'}")
    api = blogger()
    old_blog, old_src, old_titles, count = existing(api)

    cands, seen, src_counts, skip = [], set(), {}, 0
    for src in SOURCES:
        src_links = links(src)
        src_counts[src["nome"]] = len(src_links)
        for u in src_links:
            nu = normalize_url(u)
            if nu in seen or nu in old_blog or nu in old_src: continue
            a = get_article(nu)
            if a: seen.add(nu); cands.append(a)
            else: skip += 1

    print("Fontes: " + " | ".join(f"{k}: {v}" for k,v in src_counts.items()) + f" | Puladas: {skip}")

    for a in cands:
        a["_music_score"] = music_score(a)
        a["_is_music"] = a["_music_score"] >= 60
    cands.sort(key=lambda a: (0 if a["_is_music"] else 1, -a["_music_score"],
                              -(a["date"] or datetime.min).timestamp() if a["date"] else 0))

    mc = sum(1 for a in cands if a["_is_music"])
    print(f"Novas matérias: {len(cands)} (🎵 {mc} | 📰 {len(cands)-mc})")
    if cands:
        print("--- Fila (top 5) ---")
        for i,a in enumerate(cands[:5],1):
            tag = "🎵" if a["_is_music"] else "📰"
            print(f"  {i}. [{tag} score={a['_music_score']:3d}] {a['title'][:70]}")
        print("---")

    pub = fail = ign = 0
    while cands and pub < MAX_POSTS_PER_RUN:
        a = cands.pop(0)
        nu = normalize_url(a["url"])
        if nu in old_src: ign += 1; continue
        d, dt = is_dup(api, a["title"], old_titles)
        if d: ign += 1; continue
        if gemini_calls >= MAX_GEMINI_TEXT_CALLS_PER_RUN: break
        if a["_is_music"]: print(f"🎵 Prioridade: {a['title'][:70]}")
        g = gemini(a)
        if not g: ign += 1; continue
        d2, dt2 = is_dup(api, g.get("titulo",""), old_titles)
        if d2: ign += 1; continue
        fi, cf = pick_next_image_url(count + pub)
        if not fi: ign += 1; continue
        seo = build_seo(a, g, fi)
        try:
            resp = api.posts().insert(blogId=BLOGGER_BLOG_ID,
                body={"title":seo["title"].strip(),
                      "content":html_render(a,g,fi,seo),
                      "labels":seo["labels"]}, isDraft=False).execute()
            pub += 1
            old_src.add(nu)
            old_titles += [seo["title"], seo["titulo_base"], a["title"]]
            purl = resp.get("url","")
            if purl: old_blog.add(normalize_url(purl)); promote(seo["title"], purl, g.get("resumo",""))
            print(f"✓ {seo['title'].strip()[:80]}")
        except Exception as e:
            fail += 1
            print(f"⚠ falha: {str(e)[:160]}")

    print("RESULTADO")
    print(f"Publicações: {pub}")
    print(f"Ignoradas: {ign}")
    print(f"Falhas: {fail}")

print(f"MAX_AGE_DAYS configurado: {MAX_AGE_DAYS}")
main()
