import os, re, json, requests, time, random, io, contextlib, unicodedata, warnings
import builtins

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
        or message.startswith("🎵")
        or message.startswith("📰")
        or message.startswith("--- Fila")
        or message.startswith("---")
        or message.startswith("Limpeza")
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

print("RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS 15.3 (Autoral + Prioridade Musical)")

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
s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; RadioLuzGospelBot/15.3)"})

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
# PRIORIZAÇÃO DE LANÇAMENTOS MUSICAIS
# ============================================================

_MUSIC_STRONG_KEYWORDS = {
    "lança", "lançou", "lançamento", "lançamentos", "lançam",
    "lancamento", "lancamentos", "lanca", "lancou", "lancam",
    "estreia", "estreou", "estreiam",
    "single", "singles", "álbum", "album", "álbuns", "albuns",
    "ep", "eps", "mixtape", "disco", "cd", "vinil",
    "videoclipe", "clipe", "clipe oficial", "music video",
    "faixa", "faixas", "track", "setlist",
    "grava", "gravou", "gravam", "gravação", "gravacao",
    "compõe", "compôs", "compos", "composição", "composicao",
    "produz", "produziu", "produção musical", "producao musical",
    "regrava", "regravou", "regravação", "regravacao",
    "cantor", "cantora", "cantores", "cantoras",
    "banda", "bandas", "grupo musical",
    "música", "musica", "músicas", "musicas", "musical",
    "som", "canção", "cancao", "canções", "cancoes",
    "hino", "hinos", "louvor", "louvores", "adoracao", "adoração",
    "worship", "gospel music",
    "turnê", "turne", "turnes", "tour", "shows", "show",
    "concerto", "concertos", "apresentação", "apresentacao",
    "festival", "festivais",
    "spotify", "youtube music", "deezer", "apple music",
    "streaming", "playlist",
    "gravadora", "selo", "selo musical",
}

_MUSIC_WEAK_KEYWORDS = {
    "artista", "artistas", "voz", "vocal", "vozes",
    "instrumento", "instrumentos", "melodia", "harmonia",
    "arranjo", "arranjos", "compositor", "compositora",
    "letra", "letras", "refrão", "refrao",
    "gênero musical", "genero musical", "estilo musical",
    "clássico", "classico", "hits", "hit",
    "billboard", "grammy", "latin grammy", "latim grammy",
    "rádio", "radio", "rádios", "radios",
}

_MUSIC_NEGATIVE_HINTS = {
    "livro", "livros", "biografia", "autobiografia",
    "filme", "filmes", "série", "serie", "documentário", "documentario",
    "podcast", "podcasts", "entrevista", "entrevistas",
    "processo", "polêmica", "polemica", "acusação", "acusacao",
    "morte", "morre", "morreu", "faleceu", "óbito", "obito",
    "doença", "doenca", "hospital", "internado",
    "política", "politica", "eleição", "eleicao", "governo",
    "escândalo", "escandalo", "crime", "prisão", "prisao",
    "casamento", "divórcio", "divorcio", "namoro", "noivado",
    "aniversário", "aniversario", "idade",
}


def _strip_accents(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _score_music_release(article):
    titulo = _strip_accents(article.get("title") or "")
    texto = _strip_accents((article.get("text") or "")[:4000])
    bruto = f"{titulo} {texto}"

    score = 0

    strong_in_title = sum(1 for kw in _MUSIC_STRONG_KEYWORDS
                          if re.search(r'\b' + re.escape(_strip_accents(kw)) + r'\b', titulo))
    weak_in_title = sum(1 for kw in _MUSIC_WEAK_KEYWORDS
                        if re.search(r'\b' + re.escape(_strip_accents(kw)) + r'\b', titulo))

    score += strong_in_title * 25
    score += weak_in_title * 8

    strong_in_body = sum(1 for kw in _MUSIC_STRONG_KEYWORDS if _strip_accents(kw) in bruto)
    weak_in_body = sum(1 for kw in _MUSIC_WEAK_KEYWORDS if _strip_accents(kw) in bruto)

    score += min(strong_in_body * 5, 30)
    score += min(weak_in_body * 2, 10)

    if re.match(r'^(lanca|lancou|lancam|estreia|estreou|grava|gravou|'
                r'artista|cantor|cantora|banda|grupo|dupla)\b', titulo):
        score += 15

    if re.search(r'\b(single|album|ep|videoclipe|clipe|'
                 r'faixa|track|mixtape)\b', titulo):
        score += 20

    negative_hits = sum(1 for neg in _MUSIC_NEGATIVE_HINTS
                        if re.search(r'\b' + re.escape(_strip_accents(neg)) + r'\b', titulo))
    score -= negative_hits * 20

    return max(0, min(score, 100))


def _is_music_release(article, threshold=60):
    return _score_music_release(article) >= threshold


# ============================================================
# LIMPEZA DE MENÇÕES À FONTE ORIGINAL
# ============================================================

_SOURCE_VEHICLES = [
    "Fuxico Gospel", "O Fuxico Gospel", "fuxicogospel", "fuxicogospel.com.br",
    "News Gospel", "newsgospel", "newsgospel.com.br",
    "Folha Gospel", "folhagospel", "folhagospel.com",
    "Guiame", "guiame.com.br",
    "iGospel", "igospel", "igospel.org.br",
    "UAU Gospel", "uaugospel", "uaugospel.com.br",
    "Gospel Prime", "gospelprime", "gospelprime.com.br",
    "Portal do Trono", "portaldotrono",
    "Comunhão", "comunhao.com.br",
    "Gospel Mais", "gospelmais",
    "Folha Gospel", "Super Gospel", "supergospel",
]

_SOURCE_ATTRIBUTION_PATTERNS = [
    r"(?:confirmad[oa]s?|divulgad[oa]s?|revelad[oa]s?|informad[oa]s?|publicad[oa]s?|noticiad[oa]s?|reportad[oa]s?)\s+(?:pelo|pela|pelo portal|pela equipe|pelo site|pelo blog|pelo jornal|pela revista)\s+[^.!\n]{1,80}[.!]?",
    r"(?:segundo|conforme|de acordo com|como informou|como noticiou|como divulgou|como revelou|como publicou|como reportou)\s+(?:o|a|os|as)?\s*(?:portal|site|blog|jornal|revista|coluna)?\s*[^.!\n]{1,80}[.!]?",
    r"(?:fonte|via|cr[eé]ditos?|imagem|foto)\s*[:\-–]\s*[^.!\n]{1,100}[.!]?",
    r"a\s+reportagem\s+foi\s+baseada[^.!\n]{0,200}[.!]?",
    r"caso\s+haja\s+qualquer\s+corre[çc][ãa]o[^.!\n]{0,200}[.!]?",
    r"a\s+reda[çc][ãa]o\s+pode\s+ser\s+contatada[^.!\n]{0,200}[.!]?",
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    r"https?://[^\s<>\"]+",
    r"(?:leia|continue|veja|confira)\s+(?:mais|a\s+mat[eé]ria\s+completa|o\s+conte[uú]do\s+completo)\s+(?:em|no|na)\s+[^.!\n]{1,120}[.!]?",
    r"publicad[oa]\s+originalmente[^.!\n]{0,120}[.!]?",
    r"com\s+informa[çc][õo]es\s+(?:de|do|da)\s+[^.!\n]{1,120}[.!]?",
    r"\((?:foto|imagem|divulga[çc][ãa]o)\s*:[^)]{0,120}\)",
    r"\(?\s*cr[eé]ditos?\s*:[^)\n]{0,120}\)?",
]


def _clean_source_mentions(text):
    if not text:
        return text

    original = text

    for pattern in _SOURCE_ATTRIBUTION_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)

    for vehicle in _SOURCE_VEHICLES:
        v = re.escape(vehicle)
        text = re.sub(
            r"\b(?:o|a|os|as|do|da|dos|das
