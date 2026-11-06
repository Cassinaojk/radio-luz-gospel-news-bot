import os, re, json, requests, time, random, io, contextlib, unicodedata, warnings
import builtins

# Log simplificado para o GitHub Actions
_VERBOSE_LOG = os.getenv("VERBOSE_LOG", "true").lower() in ("1", "true", "yes", "sim")
_original_print = builtins.print

def print(*args, **kwargs):
    if _VERBOSE_LOG:
        return _original_print(*args, **kwargs)
    message = " ".join(str(a) for a in args).strip()
    important = (
        message.startswith("RÁDIO LUZ GOSPEL")
        or message.startswith("VERSÃO")
        or message.startswith("Fontes:")
        or message == "RESULTADO"
        or message.startswith("✓")
        or message.startswith("⚠")
        or message.startswith("Publicações:")
        or message.startswith("Ignoradas:")
        or message.startswith("Falhas:")
        or message.startswith("MAX_AGE_DAYS")
        or message.startswith("Divulgação:")
    )
    if important:
        return _original_print(*args, **kwargs)

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
from datetime import datetime, date, timezone, timedelta
from urllib.parse import urlparse, urljoin, quote, urlencode, parse_qsl
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

print("RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS 15.0")

BLOGGER_BLOG_ID = os.environ["BLOGGER_BLOG_ID"]
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

BLOG_NAME = os.getenv("BLOG_NAME", "Rádio Luz Gospel").strip() or "Rádio Luz Gospel"
BLOG_HOME_URL = os.getenv("BLOG_HOME_URL", "https://radioluzgospel.blogspot.com").strip().rstrip("/")
BLOG_LOCALE = os.getenv("BLOG_LOCALE", "pt_BR").strip() or "pt_BR"
BLOG_TWITTER = os.getenv("BLOG_TWITTER", "").strip()
SEO_TITLE_SUFFIX = os.getenv("SEO_TITLE_SUFFIX", f" | {BLOG_NAME}").strip()
SEO_DESCRIPTION_MAX = int(os.getenv("SEO_DESCRIPTION_MAX", "160"))
SEO_KEYWORDS_MAX = int(os.getenv("SEO_KEYWORDS_MAX", "12"))

# ===== Divulgação social (Apenas Telegram) =====
PROMO_ENABLED = os.getenv("PROMO_ENABLED", "false").lower() in ("1", "true", "yes", "sim")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
PROMO_UTM_SOURCE = os.getenv("PROMO_UTM_SOURCE", "telegram").strip() or "telegram"
PROMO_UTM_MEDIUM = os.getenv("PROMO_UTM_MEDIUM", "social").strip() or "social"
PROMO_UTM_CAMPAIGN = os.getenv("PROMO_UTM_CAMPAIGN", "noticias").strip() or "noticias"

CLEAN_DUPLICATES = os.getenv("CLEAN_DUPLICATES", "false").lower() in ("1", "true", "yes", "sim")

IMAGE_FILES = [
    "bot/Imagens/radioluzgospel1.png",
    "bot/Imagens/radioluzgospel2.jpg",
    "bot/Imagens/radioluzgospel3.jpg",
    "bot/Imagens/radioluzgospel4.jpg",
    "bot/Imagens/radioluzgospel5.jpg",
    "bot/Imagens/radioluzgospel6.jpg",
    "bot/Imagens/radioluzgospel7.jpg",
    "bot/Imagens/radioluzgospel8.jpg",
    "bot/Imagens/radioluzgospel9.jpg",
    "bot/Imagens/radioluzgospel10.jpg",
    "bot/Imagens/radioluzgospel11.jpg",
    "bot/Imagens/radioluzgospel12.jpg",
]

MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "2"))
MAX_GEMINI_TEXT_CALLS_PER_RUN = int(os.getenv("MAX_GEMINI_TEXT_CALLS_PER_RUN", "6"))
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_BASE_SECONDS = 4
MAX_LINKS_PER_SOURCE = 120

MAX_AGE_DAYS = int(os.getenv("MAX_AGE_DAYS", "4"))

MIN_SOURCE_CHARS = 250
MIN_SOURCE_PARAGRAPHS = 1
TIMEOUT = 25

GEMINI_MODEL_TEXT = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")

GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip()
AI_PROVIDER_TIMEOUT = int(os.getenv("AI_PROVIDER_TIMEOUT", "90"))

SOURCES = [
    {
        "nome": "News Gospel",
        "url": "https://www.newsgospel.com.br/",
        "feeds": ["https://www.newsgospel.com.br/feed/", "https://www.newsgospel.com.br/feed", "https://newsgospel.com.br/feed/"],
    },
    {
        "nome": "Folha Gospel - Música",
        "url": "https://folhagospel.com/musica/",
        "feeds": ["https://folhagospel.com/feed/", "https://folhagospel.com/musica/feed/"],
    },
    {
        "nome": "Guiame - Música",
        "url": "https://guiame.com.br/musica",
        "feeds": ["https://guiame.com.br/rss.xml", "https://guiame.com.br/feed/"],
    },
    {
        "nome": "iGospel",
        "url": "https://www.igospel.org.br/",
        "feeds": ["https://www.igospel.org.br/feed/", "https://www.igospel.org.br/feed", "https://igospel.org.br/feed/"],
    },
    {
        "nome": "Fuxico Gospel",
        "url": "https://www.fuxicogospel.com.br/",
        "feeds": ["https://www.fuxicogospel.com.br/feed/", "https://www.fuxicogospel.com.br/feed"],
    },
]

BAD_PATHS = (
    "/category/", "/tag/", "/author/", "/page/", "/search/", "/feed/",
    "/wp-json/", "/comments/", "/sobre", "/contato", "/contact",
    "/politica/", "/privacidade/", "/privacy/", "/anuncie/", "/publicidade/",
    "/advertising/", "/login/", "/cadastro/", "/register/", "/sitemap/", "/robots.txt",
)

SHARE_DOMAINS = ("pinterest.", "reddit.com/submit", "facebook.com/sharer", "twitter.com/intent", "x.com/intent", "whatsapp.com/", "t.me/share", "linkedin.com/share")

VIDEO_HOSTS = ("youtube.com/embed/", "youtube.com/watch", "youtube-nocookie.com/embed/", "youtu.be/", "player.vimeo.com", "vimeo.com/video", "facebook.com/plugins/video", "web.facebook.com/plugins/video", "instagram.com/p/", "instagram.com/reel/", "instagram.com/tv/", "dailymotion.com/embed", "twitch.tv/", "streamable.com/e/", "rumble.com/embed")

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; RadioLuzGospelBot/15.0)"})

gemini_calls = 0
gemini_quota_hit = False
_ai_config_logged = False
_image_url_cache = {}

def normalize_url(u):
    if not u:
        return ""
    return u.strip().split("#")[0].rstrip("/")

def bad_url(u):
    u = normalize_url(u).lower()
    if not u.startswith(("http://", "https://")):
        return True
    if any(x in u for x in SHARE_DOMAINS):
        return True
    path = urlparse(u).path
    if any(x in path for x in BAD_PATHS):
        return True
    if re.search(r"\.(pdf|jpg|jpeg|png|gif|webp|svg|xml|zip)$", path):
        return True
    return False

def soup(url, xml=False):
    try:
        r = s.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        if xml:
            try:
                return BeautifulSoup(r.text, "xml")
            except Exception:
                pass
        return BeautifulSoup(r.text, "html.parser")
    except Exception:
        return None

def date_parse(v):
    if not v:
        return None
    value = str(v).strip()
    formats = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y")
    for f in formats:
        try:
            d = datetime.strptime(value[:32], f)
            return d.replace(tzinfo=None) if d.tzinfo else d
        except Exception:
            pass
    return None

def article_date(x):
    selectors = ('meta[property="article:published_time"]', 'meta[property="og:published_time"]', 'meta[name="date"]', 'meta[name="publish_date"]', 'meta[itemprop="datePublished"]')
    for sel in selectors:
        n = x.select_one(sel)
        if n:
            d = date_parse(n.get("content", ""))
            if d:
                return d
    for sc in x.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(sc.string or sc.get_text())
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    if isinstance(item.get("@graph"), list):
                        for g in item["@graph"]:
                            if isinstance(g, dict):
                                d = date_parse(g.get("datePublished"))
                                if d: return d
                    d = date_parse(item.get("datePublished"))
                    if d: return d
        except Exception:
            pass
    for sel in ("time.entry-date", "time.published", "time", ".entry-date", ".posted-on"):
        n = x.select_one(sel)
        if n:
            d = date_parse(n.get("datetime") or n.get_text(" ", strip=True))
            if d: return d
    return None

def image_original(x):
    for sel in ('meta[property="og:image"]', 'meta[property="og:image:secure_url"]', 'meta[name="twitter:image"]', 'meta[name="twitter:image:src"]', 'meta[itemprop="image"]'):
        n = x.select_one(sel)
        if n:
            u = (n.get("content") or "").strip()
            if u.startswith("//"): u = "https:" + u
            if u.startswith(("http://", "https://")): return u
    return ""

def videos(x):
    out = []
    for n in x.find_all("iframe"):
        u = (n.get("src") or n.get("data-src") or "").strip()
        if u.startswith("//"): u = "https:" + u
        if not u.startswith(("http://", "https://")): continue
        if not any(h in u.lower() for h in VIDEO_HOSTS): continue
        if u not in out: out.append(u)
    return out[:3]

def resolve_repo_image_url(relative_path):
    if not relative_path: return ""
    if relative_path in _image_url_cache: return _image_url_cache[relative_path]
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    branch = os.getenv("GITHUB_REF_NAME", "").strip() or "main"
    if not repository:
        _image_url_cache[relative_path] = ""
        return ""
    repo_enc = quote(repository, safe="/")
    branch_enc = quote(branch, safe="")
    path_enc = quote(relative_path, safe="/")
    candidates = [f"https://cdn.jsdelivr.net/gh/{repo_enc}@{branch_enc}/{path_enc}", f"https://raw.githubusercontent.com/{repo_enc}/{branch_enc}/{path_enc}"]
    for candidate in candidates:
        try:
            r = requests.get(candidate, stream=True, timeout=12)
            if r.status_code == 200 and (r.headers.get("Content-Type") or "").lower().startswith("image/"):
                _image_url_cache[relative_path] = candidate
                return candidate
            r.close()
        except Exception:
            pass
    _image_url_cache[relative_path] = ""
    return ""

def pick_next_image_url(posts_count):
    if not IMAGE_FILES: return "", ""
    total = len(IMAGE_FILES)
    start_idx = posts_count % total
    for offset in range(total):
        idx = (start_idx + offset) % total
        rel = IMAGE_FILES[idx]
        url = resolve_repo_image_url(rel)
        if url: return url, rel
    return "", ""

def get_article(url):
    x = soup(url)
    if not x: return None
    n = x.find("h1") or x.find("title")
    title = re.sub(r"\s+", " ", n.get_text(" ", strip=True) if n else "").strip()
    if not title: return None
    title_lower = title.lower()
    if title_lower in {"lançamentos", "notícias", "noticias", "home", "início", "inicio", "últimas notícias", "ultimas noticias", "404"}:
        print(f"⚠ Pulada (índice): {title[:70]}")
        return None

    d = article_date(x)
    if d:
        age = (datetime.now() - d).total_seconds() / 86400
        if age > MAX_AGE_DAYS:
            print(f"⚠ Notícia antiga: {title[:70]} (publicada {d.strftime('%d/%m/%Y')}, {age:.1f} dias)")
            return None
        print(f"✓ Data OK: {title[:70]} ({age:.2f} dias)")
    else:
        print(f"⚠ Data não identificada: {title[:70]} — aceitando")

    img = image_original(x) or ""
    box = x.find("article") or x.find("main") or x
    paragraphs = [re.sub(r"\s+", " ", p.get_text(" ", strip=True)) for p in box.find_all("p") if len(re.sub(r"\s+", " ", p.get_text(" ", strip=True))) >= 35]
    text = "\n\n".join(paragraphs)

    if len(text) < MIN_SOURCE_CHARS or len(paragraphs) < MIN_SOURCE_PARAGRAPHS:
        print(f"⚠ Conteúdo insuficiente: {title[:70]} ({len(text)} chars, {len(paragraphs)} parágrafos)")
        return None

    vv = videos(x)
    inline_imgs = [{"url": img, "after_paragraph": 2, "is_main": True}] if img else []

    print(f"✓ Notícia válida: {title[:70]} ({len(text)} chars)")
    return {"url": normalize_url(url), "title": title, "date": d, "image": img, "text": text[:16000], "videos": vv, "inline_images": inline_imgs}

def links(source):
    out, seen = [], set()
    source_host = urlparse(source["url"]).netloc.lower()

    def host_matches(u):
        h = urlparse(u).netloc.lower()
        h_no_www = h.replace("www.", "", 1)
        s_no_www = source_host.replace("www.", "", 1)
        return h == source_host or h.endswith("." + source_host) or h_no_www == s_no_www or h_no_www.endswith("." + s_no_www)

    for feed in source["feeds"]:
        x = soup(feed, True)
        if not x:
            continue
        for item in x.find_all(["item", "entry"]):
            n = item.find("link")
            if not n:
                continue
            u = normalize_url(n.get("href") or n.get_text(strip=True) or "")
            if u and not bad_url(u) and host_matches(u) and u not in seen:
                seen.add(u)
                out.append(u)

    rss_count = len(out)

    x = soup(source["url"])
    if x:
        for a in x.find_all("a", href=True):
            u = normalize_url(urljoin(source["url"], a["href"]))
            if not u or bad_url(u) or not host_matches(u):
                continue
            if u in seen:
                continue
            path = urlparse(u).path.strip("/")
            if path.count("/") >= 1 and len(path) > 10:
                seen.add(u)
                out.append(u)

    print(f"Links em {source['nome']}: {len(out)}")
    return out[:MAX_LINKS_PER_SOURCE]

def blogger():
    credentials = Credentials(None, refresh_token=BLOGGER_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET, scopes=["https://www.googleapis.com/auth/blogger"])
    return build("blogger", "v3", credentials=credentials, cache_discovery=False)

_COMPARE_STOPWORDS = {"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "um", "uma", "uns", "umas", "para", "por", "com", "no", "na", "nos", "nas", "que", "se", "ao", "aos", "sua", "seu", "suas", "seus", "mais", "como", "sobre", "entre", "apos", "ate", "ja", "nao", "muito", "bem", "ainda", "tambem", "so", "esse", "essa", "este", "esta", "isso", "aquilo", "ele", "ela", "eles", "elas", "vai", "vem", "foi", "sao", "estao", "tem", "ter", "terao", "eh", "ser", "sera", "novo", "nova", "novos", "novas", "lanca", "lancou", "lancam", "lancar", "anuncia", "anunciou", "divulga", "divulgou", "revela", "revelou", "confirma", "confirmou", "veja", "confira", "saiba", "assista", "leia", "chega", "chegou", "radio", "luz", "gospel", "noticia", "noticias", "blog", "materia", "hoje", "agora", "ultima", "ultimas", "ultimo", "ultimos", "video", "videos", "foto", "fotos", "imagem", "imagens", "the", "of", "to", "in", "and", "or", "on", "at", "for", "with", "from", "by"}

def _compare_normalize(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return set(w for w in text.split() if len(w) > 1 and w not in _COMPARE_STOPWORDS)

def _title_similarity(a, b):
    if not a or not b: return 0.0
    return len(a & b) / len(a | b) if (a | b) else 0.0

def existing(api):
    blog_urls, source_urls, titles = set(), set(), []
    bot_count, token = 0, None
    try:
        while True:
            kwargs = {"blogId": BLOGGER_BLOG_ID, "maxResults": 500, "fetchBodies": False}
            if token: kwargs["pageToken"] = token
            data = api.posts().list(**kwargs).execute()
            for post in data.get("items", []):
                purl = normalize_url(post.get("url", ""))
                title = (post.get("title") or "").strip()
                if purl: blog_urls.add(purl)
                if title: titles.append(title)
                content = post.get("content", "") or ""
                if not content:
                    try:
                        full = api.posts().get(blogId=BLOGGER_BLOG_ID, postId=post.get("id", ""), fetchBody=True).execute()
                        content = full.get("content", "") or ""
                    except Exception:
                        content = ""
                for match in re.findall(r'href=["\'](https?://[^"\']+)["\']', content, flags=re.I):
                    source_urls.add(normalize_url(match))
                for match in re.findall(r'RADIO_LUZ_GOSPEL_SOURCE_URL:\s*(https?://[^\s]+?)\s*-->', content, flags=re.I):
                    source_urls.add(normalize_url(match))
                if re.search(r"RADIO_LUZ_GOSPEL_SOURCE_URL:", content, flags=re.I):
                    bot_count += 1
            token = data.get("nextPageToken")
            if not token: break
    except Exception as e:
        print("Erro ao consultar Blogger:", e)
    print("Posts existentes no Blogger:", len(blog_urls))
    print("Fontes já registradas:", len(source_urls))
    print(f"Posts do robô já publicados: {bot_count}")
    return blog_urls, source_urls, titles, bot_count

def check_blogger_for_duplicate(api, article_title, existing_titles):
    new_words = _compare_normalize(article_title)
    if not new_words:
        return False, ""

    for et in existing_titles:
        et_words = _compare_normalize(et)
        if not et_words:
            continue
        sim = _title_similarity(new_words, et_words)
        if sim >= 0.60:
            return True, et

    search_terms = sorted(new_words, key=len, reverse=True)[:2]
    if not search_terms:
        return False, ""
    query = " ".join(search_terms)
    try:
        response = api.posts().search(blogId=BLOGGER_BLOG_ID, q=query, fetchBodies=False, maxResults=10).execute()
        for post in response.get("items", []):
            pt = post.get("title", "")
            if _title_similarity(new_words, _compare_normalize(pt)) >= 0.60:
                return True, pt
    except Exception as e:
        pass
    return False, ""

# ============================================================
# DIVULGAÇÃO SOCIAL (Apenas Telegram)
# ============================================================

def build_promo_url(url):
    try:
        parsed = urlparse(url)
        q = dict(parse_qsl(parsed.query))
        q.update({"utm_source": PROMO_UTM_SOURCE, "utm_medium": PROMO_UTM_MEDIUM, "utm_campaign": PROMO_UTM_CAMPAIGN})
        return parsed._replace(query=urlencode(q)).geturl()
    except Exception:
        return url

def promote_telegram(title, post_url, summary=""):
    if not PROMO_ENABLED or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        promo_url = build_promo_url(post_url)
        text = f"📰 <b>{title}</b>\n\n{summary[:300]}\n\n👉 Leia mais: {promo_url}"
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=20,
        )
        if r.status_code == 200 and r.json().get("ok"):
            print(f"✓ Telegram: mensagem enviada")
            return True
        print(f"⚠ Telegram: falha ({r.status_code}): {r.text[:150]}")
    except Exception as e:
        print(f"⚠ Telegram: erro {str(e)[:150]}")
    return False

def gemini(article, client=None):
    global gemini_calls, gemini_quota_hit, _ai_config_logged
    if gemini_calls >= MAX_GEMINI_TEXT_CALLS_PER_RUN:
        print("⚠ IA: limite atingido")
        return None
    providers = []
    if GEMINI_API_KEY: providers.append(("gemini", GEMINI_API_KEY, GEMINI_MODEL_TEXT))
    if GEMINI_API_KEY_2: providers.append(("gemini-2", GEMINI_API_KEY_2, GEMINI_FALLBACK_MODEL))
    if GROQ_API_KEY: providers.append(("groq", GROQ_API_KEY, GROQ_MODEL))
    if MISTRAL_API_KEY: providers.append(("mistral", MISTRAL_API_KEY, MISTRAL_MODEL))
    if not providers:
        return None

    prompt = f"""Você é jornalista do Rádio Luz Gospel. Escreva uma matéria NOVA, do zero.
Use SOMENTE os fatos do texto-fonte. Não invente.
Crie título, resumo e matéria em português do Brasil (700-1200 palavras).

CRITÉRIO DE PUBLICAÇÃO: marque publicar=true para QUALQUER notícia gospel/cristã/evangélica.
Marque publicar=false SOMENTE se for COMPLETAMENTE alheia ao universo gospel.

FORMATO JSON:
{{"publicar":true,"titulo":"...","resumo":"...","materia":"...","assunto_principal":"...","palavras_chave":["..."],"categoria_seo":"..."}}

TÍTULO ORIGINAL: {article['title']}
FONTE: {article['url']}
TEXTO-FONTE:
{article['text']}
"""
    exhausted = set()
    for provider, api_key, model in providers:
        if gemini_calls >= MAX_GEMINI_TEXT_CALLS_PER_RUN: break
        if provider in exhausted: continue
        try:
            print(f"IA: {provider}/{model}...")
            if provider.startswith("gemini"):
                with contextlib.redirect_stderr(io.StringIO()):
                    resp = genai.Client(api_key=api_key).models.generate_content(model=model, contents=prompt, config={"response_mime_type": "application/json"})
                raw = (getattr(resp, "text", None) or "").strip()
            else:
                endpoint = {"groq": "https://api.groq.com/openai/v1/chat/completions", "mistral": "https://api.mistral.ai/v1/chat/completions"}[provider]
                r = requests.post(endpoint, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 5000, "response_format": {"type": "json_object"}}, timeout=AI_PROVIDER_TIMEOUT)
                raw = r.json()["choices"][0]["message"]["content"].strip()
            gemini_calls += 1
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
            data = json.loads(raw)
            if data.get("publicar") is False: continue
            titulo, resumo, materia = str(data.get("titulo", "")).strip(), str(data.get("resumo", "")).strip(), str(data.get("materia", "")).strip()
            if not titulo or not resumo or len(materia) < 700: continue
            print(f"✓ IA: matéria aprovada ({provider})")
            return {"publicar": True, "titulo": titulo, "resumo": resumo, "materia": materia, "assunto_principal": str(data.get("assunto_principal", "")).strip(), "palavras_chave": data.get("palavras_chave", [])[:SEO_KEYWORDS_MAX], "categoria_seo": str(data.get("categoria_seo", "")).strip()}
        except Exception as exc:
            if any(x in str(exc).upper() for x in ("429", "RESOURCE_EXHAUSTED", "QUOTA", "RATE LIMIT")):
                exhausted.add(provider)
                print(f"⚠ {provider}: quota")
            else:
                print(f"⚠ {provider}: {str(exc)[:150]}")
    return None

def build_seo_payload(article, generated, final_image="", image_origin=""):
    titulo_base = str(generated.get("titulo", "")).strip()
    resumo = str(generated.get("resumo", "")).strip()
    materia = str(generated.get("materia", "")).strip()
    assunto = str(generated.get("assunto_principal", "")).strip()
    categoria_seo = str(generated.get("categoria_seo", "")).strip()
    palavras = list(generated.get("palavras_chave", []) or [])

    title = f"{titulo_base}{SEO_TITLE_SUFFIX}" if SEO_TITLE_SUFFIX and not titulo_base.lower().endswith(SEO_TITLE_SUFFIX.lower()) else titulo_base
    description = (resumo or BeautifulSoup(materia, "html.parser").get_text(" ", strip=True)[:SEO_DESCRIPTION_MAX])[:SEO_DESCRIPTION_MAX]

    kw = []
    if assunto: kw.append(assunto)
    if categoria_seo: kw.append(categoria_seo)
    kw.extend(str(p).strip() for p in palavras if str(p).strip())
    for fb in ("música gospel", "gospel", "notícias gospel", BLOG_NAME):
        if fb.lower() not in {k.lower() for k in kw}: kw.append(fb)
    keywords = ", ".join(kw[:SEO_KEYWORDS_MAX])

    labels = ["Notícias", "Rádio Luz Gospel"]
    if categoria_seo: labels.append(re.sub(r"\s+", " ", categoria_seo).strip())
    if assunto and len(assunto) <= 40: labels.append(re.sub(r"\s+", " ", assunto).strip())
    if article.get("date"): labels.append(str(article["date"].year))
    seen, labels_final = set(), []
    for l in labels:
        if l and l.lower() not in seen:
            seen.add(l.lower()); labels_final.append(l)

    image_url = final_image or article.get("image", "")
    canonical = article.get("url", "")
    published = (article.get("date") or datetime.now()).isoformat()
    date_modified = datetime.now().isoformat()

    schema = {"@context": "https://schema.org", "@type": "NewsArticle", "mainEntityOfPage": {"@type": "WebPage", "@id": canonical}, "headline": titulo_base[:110], "description": description, "image": [image_url] if image_url else [], "datePublished": published, "dateModified": date_modified, "author": {"@type": "Organization", "name": BLOG_NAME, "url": BLOG_HOME_URL}, "publisher": {"@type": "Organization", "name": BLOG_NAME, "url": BLOG_HOME_URL, "logo": {"@type": "ImageObject", "url": image_url or f"{BLOG_HOME_URL}/favicon.ico"}}, "articleSection": categoria_seo or "Notícias Gospel", "keywords": keywords, "inLanguage": "pt-BR", "isAccessibleForFree": True, "url": canonical}
    breadcrumb = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Início", "item": BLOG_HOME_URL}, {"@type": "ListItem", "position": 2, "name": "Notícias", "item": f"{BLOG_HOME_URL}/search/label/Not%C3%ADcias"}, {"@type": "ListItem", "position": 3, "name": titulo_base[:80], "item": canonical}]}

    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    safe_desc = description.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    safe_kw = keywords.replace("&", "&amp;").replace('"', "&quot;")
    safe_canonical = canonical.replace("&", "&amp;").replace('"', "&quot;")
    safe_image = (image_url or "").replace("&", "&amp;").replace('"', "&quot;")

    html_head = f"""<!-- SEO -->
<title>{safe_title}</title>
<meta name="description" content="{safe_desc}">
<meta name="keywords" content="{safe_kw}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{safe_canonical}">
<meta property="og:type" content="article">
<meta property="og:title" content="{safe_title}">
<meta property="og:description" content="{safe_desc}">
<meta property="og:url" content="{safe_canonical}">
<meta property="og:image" content="{safe_image}">
<meta property="article:published_time" content="{published}">
<meta property="article:section" content="{schema['articleSection']}">
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(breadcrumb, ensure_ascii=False)}</script>
<!-- FIM SEO -->"""
    return {"title": title, "titulo_base": titulo_base, "description": description, "keywords": keywords, "labels": labels_final[:10], "canonical": canonical, "html_head": html_head, "assunto": assunto, "categoria_seo": categoria_seo}

def html(article, generated, final_image="", image_origin="", seo=None):
    seo = seo or {}
    titulo = seo.get("titulo_base") or generated.get("titulo", "")
    safe_titulo = titulo.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    img = final_image or article["image"]
    safe_img = img.replace("&", "&amp;").replace('"', "&quot;")
    safe_src = article["url"].replace("&", "&amp;").replace('"', "&quot;")

    content = [seo.get("html_head", ""), f'<p><strong>{generated["resumo"]}</strong></p>', f'<p><img src="{safe_img}" alt="{safe_titulo}" title="{safe_titulo}" style="max-width:100%;height:auto;border-radius:12px;"></p>']
    for p in re.split(r"\n+", generated["materia"]):
        if p.strip(): content.append(f"<p>{p.strip()}</p>")
    for v in article["videos"]:
        content.append(f'<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:12px;margin:24px 0;"><iframe src="{v}" style="position:absolute;top:0;left:0;width:100%;height:100%;border:0;" allowfullscreen loading="lazy"></iframe></div>')
    content.append('<div style="max-width:600px;margin:2rem auto;text-align:center;"><h3 style="color:#1DB954;">🎵 Top 2026 — Rádio Luz Gospel</h3><iframe style="border-radius:12px;" src="https://open.spotify.com/embed/playlist/14OteRoEl6CVEsTCpYCYyx?utm_source=generator" width="100%" height="380" frameborder="0" allowfullscreen loading="lazy"></iframe></div>')
    content.append(f'<div style="margin:24px 0;padding:18px;border:1px solid #ddd;border-radius:12px;text-align:center;"><p><strong>📲 Receba as próximas notícias no Telegram</strong></p><p><a href="https://t.me/radioluzgospelnoticias" target="_blank">👉 ENTRAR NO CANAL</a></p></div>')

    source_marker = f"<!-- RADIO_LUZ_GOSPEL_SOURCE_URL: {safe_src} -->"
    return "\n".join(content) + "\n" + source_marker

def main():
    print("Fontes: News Gospel + Folha Gospel + Guiame + iGospel + Fuxico Gospel")
    print(f"Divulgação: Telegram={'ON' if PROMO_ENABLED and TELEGRAM_BOT_TOKEN else 'OFF'}")
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    api = blogger()
    old_blog_urls, old_source_urls, existing_titles, posts_count = existing(api)

    candidates, candidate_urls, source_counts, prefiltered = [], set(), {}, 0
    for source in SOURCES:
        source_links = links(source)
        source_counts[source["nome"]] = len(source_links)
        for url in source_links:
            normalized = normalize_url(url)
            if normalized in candidate_urls or normalized in old_blog_urls or normalized in old_source_urls:
                continue
            article = get_article(normalized)
            if article:
                candidate_urls.add(normalized)
                candidates.append(article)
            else:
                prefiltered += 1

    print(f"Fontes encontradas: " + " | ".join(f"{n}: {c}" for n, c in source_counts.items()))
    print(f"Puladas: {prefiltered}")

    candidates.sort(key=lambda a: a["date"] or datetime.min, reverse=True)
    print(f"Novas matérias aceitas: {len(candidates)}")

    published = failed = ignored = 0
    while candidates and published < MAX_POSTS_PER_RUN:
        article = candidates.pop(0)
        normalized = normalize_url(article["url"])
        if normalized in old_source_urls:
            ignored += 1
            continue

        is_dup, dup_title = check_blogger_for_duplicate(api, article["title"], existing_titles)
        if is_dup:
            print(f"⚠ Duplicada (já no blog): «{article['title'][:60]}» ≈ «{dup_title[:60]}»")
            ignored += 1
            continue

        if gemini_calls >= MAX_GEMINI_TEXT_CALLS_PER_RUN:
            print("⚠ Limite de IA atingido")
            break

        generated = gemini(article, gemini_client)
        if not generated:
            ignored += 1
            if gemini_quota_hit: break
            continue

        is_dup2, dup_title2 = check_blogger_for_duplicate(api, generated.get("titulo", ""), existing_titles)
        if is_dup2:
            print(f"⚠ Duplicada pós-IA: «{generated.get('titulo','')[:60]}» ≈ «{dup_title2[:60]}»")
            ignored += 1
            continue

        final_image, chosen_file = pick_next_image_url(posts_count + published)
        if not final_image:
            print("⚠ Imagem não encontrada")
            ignored += 1
            continue
        image_origin = f"Sequência: {chosen_file}"

        seo = build_seo_payload(article, generated, final_image, image_origin)
        print(f"✓ SEO: {seo['title'][:90]}")

        try:
            response = api.posts().insert(blogId=BLOGGER_BLOG_ID, body={"title": seo["title"].strip(), "content": html(article, generated, final_image, image_origin, seo), "labels": seo["labels"]}, isDraft=False).execute()
            published += 1
            old_source_urls.add(normalized)
            existing_titles.extend([seo["title"], seo["titulo_base"], article["title"]])
            post_url = response.get("url", "")
            if post_url:
                old_blog_urls.add(normalize_url(post_url))
            print(f"✓ Publicada: {seo['title'].strip()}")

            # ===== DIVULGAÇÃO SOCIAL =====
            if post_url:
                summary = generated.get("resumo", "")
                promote_telegram(seo["title"], post_url, summary)
        except Exception as exc:
            failed += 1
            print(f"⚠ Blogger: falha ao publicar ({str(exc)[:200]})")

    print("RESULTADO")
    print(f"Publicações: {published}")
    print(f"Ignoradas: {ignored}")
    print(f"Falhas: {failed}")

print(f"MAX_AGE_DAYS configurado: {MAX_AGE_DAYS}")
main()
