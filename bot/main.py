import os, re, json, requests, time, random, io, contextlib, unicodedata, warnings
import builtins

# Log resumido por padrão. Use VERBOSE_LOG=true no GitHub Actions para diagnóstico.
_VERBOSE_LOG = os.getenv("VERBOSE_LOG", "false").lower() in ("1", "true", "yes", "sim")
_original_print = builtins.print

def print(*args, **kwargs):
    if _VERBOSE_LOG:
        return _original_print(*args, **kwargs)

    message = " ".join(str(a) for a in args).strip()
    important = (
        message.startswith("RÁDIO LUZ GOSPEL - ROBÔ")
        or message.startswith("VERSÃO ")
        or message.startswith("Fontes:")
        or message.startswith("Posts existentes no Blogger:")
        or message.startswith("Fontes já registradas:")
        or message.startswith("Fontes encontradas:")
        or message.startswith("Novas matérias:")
        or message.startswith("Puladas:")
        or message.startswith("Duplicadas")
        or message == "RESULTADO"
        or message.startswith("Publicações:")
        or message.startswith("Ignoradas:")
        or message.startswith("Falhas:")
        or message.startswith("✓ Publicada:")
        or message.startswith("✓ Imagem:")
        or message.startswith("✓ SEO:")
        or message.startswith("✓ Labels:")
        or message.startswith("✓ Limpeza:")
        or message.startswith("⚠ Blogger:")
        or message.startswith("⚠ IA:")
        or message.startswith("⚠ Gemini:")
        or message.startswith("⚠ Imagem:")
        or message.startswith("⚠ Pulada:")
        or message.startswith("⚠ Duplicada:")
        or message.startswith("⚠ Notícia antiga:")
        or message.startswith("⚠ Data:")
        or message.startswith("⚠ Conteúdo:")
        or message.startswith("Erro:")
    )
    if important:
        return _original_print(*args, **kwargs)

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
from datetime import datetime, date, timezone, timedelta
from urllib.parse import urlparse, urljoin, quote, urlencode, urlsplit, urlunsplit, parse_qsl
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

print("RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS 14.0 (5 Fontes + Anti-Duplicidade Rígida + Sem Filtro Musical)")

BLOGGER_BLOG_ID = os.environ["BLOGGER_BLOG_ID"]
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# ===== SEO =====
BLOG_NAME = os.getenv("BLOG_NAME", "Rádio Luz Gospel").strip() or "Rádio Luz Gospel"
BLOG_HOME_URL = os.getenv("BLOG_HOME_URL", "https://radioluzgospel.blogspot.com").strip().rstrip("/")
BLOG_LOCALE = os.getenv("BLOG_LOCALE", "pt_BR").strip() or "pt_BR"
BLOG_TWITTER = os.getenv("BLOG_TWITTER", "").strip()
SEO_TITLE_SUFFIX = os.getenv("SEO_TITLE_SUFFIX", f" | {BLOG_NAME}").strip()
SEO_DESCRIPTION_MAX = int(os.getenv("SEO_DESCRIPTION_MAX", "160"))
SEO_KEYWORDS_MAX = int(os.getenv("SEO_KEYWORDS_MAX", "12"))

# Divulgação
PROMO_ENABLED = os.getenv("PROMO_ENABLED", "false").lower() in ("1", "true", "yes", "sim")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
PROMO_UTM_SOURCE = os.getenv("PROMO_UTM_SOURCE", "telegram").strip() or "telegram"
PROMO_UTM_MEDIUM = os.getenv("PROMO_UTM_MEDIUM", "social").strip() or "social"
PROMO_UTM_CAMPAIGN = os.getenv("PROMO_UTM_CAMPAIGN", "noticias").strip() or "noticias"

FACEBOOK_ENABLED = os.getenv("FACEBOOK_ENABLED", "false").lower() in ("1", "true", "yes", "sim")
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "").strip()
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
INSTAGRAM_ENABLED = os.getenv("INSTAGRAM_ENABLED", "false").lower() in ("1", "true", "yes", "sim")
INSTAGRAM_USER_ID = os.getenv("INSTAGRAM_USER_ID", "").strip()
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()

META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v24.0").strip() or "v24.0"

CLEAN_DUPLICATES = os.getenv("CLEAN_DUPLICATES", "false").lower() in ("1", "true", "yes", "sim")

# ===== Sequência de imagens de destaque (GitHub) =====
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

MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "1"))
MAX_GEMINI_TEXT_CALLS_PER_RUN = int(os.getenv("MAX_GEMINI_TEXT_CALLS_PER_RUN", "6"))
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_BASE_SECONDS = 4
MAX_LINKS_PER_SOURCE = 80

# ============================================================
# FILTRO DE DATA FLEXÍVEL: aceita hoje e ontem (fuso horário)
# ============================================================
MAX_AGE_DAYS = int(os.getenv("MAX_AGE_DAYS", "1"))

MIN_SOURCE_CHARS = 400
MIN_SOURCE_PARAGRAPHS = 2
TIMEOUT = 25

GEMINI_MODEL_TEXT = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")

GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip()
AI_PROVIDER_TIMEOUT = int(os.getenv("AI_PROVIDER_TIMEOUT", "90"))

# ===== Fontes (5 fontes) =====
SOURCES = [
    {
        "nome": "News Gospel",
        "url": "https://www.newsgospel.com.br/",
        "feeds": [
            "https://www.newsgospel.com.br/feed/",
            "https://www.newsgospel.com.br/feed",
            "https://newsgospel.com.br/feed/",
        ],
    },
    {
        "nome": "Folha Gospel - Música",
        "url": "https://folhagospel.com/musica/",
        "feeds": [
            "https://folhagospel.com/feed/",
            "https://folhagospel.com/musica/feed/",
        ],
    },
    {
        "nome": "Guiame - Música",
        "url": "https://guiame.com.br/musica",
        "feeds": [
            "https://guiame.com.br/rss.xml",
            "https://guiame.com.br/feed/",
        ],
    },
    {
        "nome": "iGospel",
        "url": "https://www.igospel.org.br/",
        "feeds": [
            "https://www.igospel.org.br/feed/",
            "https://www.igospel.org.br/feed",
            "https://igospel.org.br/feed/",
        ],
    },
    {
        "nome": "Fuxico Gospel",
        "url": "https://www.fuxicogospel.com.br/",
        "feeds": [
            "https://www.fuxicogospel.com.br/feed/",
            "https://www.fuxicogospel.com.br/feed",
        ],
    },
]

BAD_PATHS = (
    "/category/", "/tag/", "/author/", "/page/", "/search/", "/feed/",
    "/wp-json/", "/comments/", "/sobre", "/contato", "/contact",
    "/politica", "/privacidade", "/privacy", "/anuncie", "/publicidade",
    "/advertising", "/login", "/cadastro", "/register", "/sitemap", "/robots.txt",
)

SHARE_DOMAINS = (
    "pinterest.", "reddit.com/submit", "facebook.com/sharer",
    "twitter.com/intent", "x.com/intent", "whatsapp.com/",
    "t.me/share", "linkedin.com/share",
)

VIDEO_HOSTS = (
    "youtube.com/embed/", "youtube.com/watch", "youtube-nocookie.com/embed/",
    "youtu.be/", "player.vimeo.com", "vimeo.com/video",
    "facebook.com/plugins/video", "web.facebook.com/plugins/video",
    "instagram.com/p/", "instagram.com/reel/", "instagram.com/tv/",
    "dailymotion.com/embed", "twitch.tv/", "streamable.com/e/", "rumble.com/embed",
)

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; RadioLuzGospelBot/14.0)"})

gemini_calls = 0
gemini_quota_hit = False
_ai_config_logged = False
_image_url_cache = {}

def normalize_url(u):
    if not u:
        return ""
    u = u.strip().split("#")[0]
    u = u.rstrip("/")
    return u

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
        print(f"Abrindo: {url}\nHTTP: {r.status_code}")
        if r.status_code != 200:
            return None
        if xml:
            try:
                return BeautifulSoup(r.text, "xml")
            except Exception as e:
                print("Parser XML indisponível; usando parser HTML:", e)
        return BeautifulSoup(r.text, "html.parser")
    except requests.exceptions.SSLError:
        return None
    except Exception as e:
        print("Erro:", e)
        return None

def date_parse(v):
    if not v:
        return None
    value = str(v).strip()
    formats = (
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y",
    )
    for f in formats:
        try:
            d = datetime.strptime(value[:32], f)
            return d.replace(tzinfo=None) if d.tzinfo else d
        except Exception:
            pass
    return None

def article_date(x):
    selectors = (
        'meta[property="article:published_time"]',
        'meta[property="og:published_time"]',
        'meta[name="date"]', 'meta[name="publish_date"]',
        'meta[itemprop="datePublished"]',
    )
    for sel in selectors:
        n = x.select_one(sel)
        if n:
            d = date_parse(n.get("content", ""))
            if d:
                return d
    for sc in x.find_all("script", type="application/ld+json"):
        try:
            raw = sc.string or sc.get_text()
            data = json.loads(raw)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                if isinstance(item.get("@graph"), list):
                    for graph_item in item["@graph"]:
                        if isinstance(graph_item, dict):
                            d = date_parse(graph_item.get("datePublished"))
                            if d:
                                return d
                d = date_parse(item.get("datePublished"))
                if d:
                    return d
        except Exception:
            pass
    for sel in ("time.entry-date", "time.published", "time", ".entry-date", ".posted-on"):
        n = x.select_one(sel)
        if n:
            d = date_parse(n.get("datetime") or n.get_text(" ", strip=True))
            if d:
                return d
    return None

def image_original(x):
    for sel in (
        'meta[property="og:image"]',
        'meta[property="og:image:secure_url"]',
        'meta[name="twitter:image"]',
        'meta[name="twitter:image:src"]',
        'meta[itemprop="image"]',
    ):
        n = x.select_one(sel)
        if n:
            u = (n.get("content") or "").strip()
            if u.startswith("//"):
                u = "https:" + u
            if u.startswith(("http://", "https://")):
                return u
    return ""

def videos(x):
    BLOCK_HOSTS = (
        "doubleclick.net", "googlesyndication.com", "googleadservices.com",
        "adservice.google", "taboola.com", "outbrain.com", "criteo.",
        "pubmatic.", "rubiconproject.", "adnxs.com", "amazon-adsystem.",
        "facebook.com/plugins/post", "instagram.com/embed.js",
    )
    out = []
    for n in x.find_all("iframe"):
        u = (n.get("src") or n.get("data-src") or "").strip()
        if u.startswith("//"):
            u = "https:" + u
        if not u.startswith(("http://", "https://")):
            continue
        u_lower = u.lower()
        if any(b in u_lower for b in BLOCK_HOSTS):
            continue
        if not any(host in u_lower for host in VIDEO_HOSTS):
            continue
        style = (n.get("style") or "").lower().replace(" ", "")
        if any(z in style for z in ("display:none", "visibility:hidden", "opacity:0", "width:0", "height:0")):
            continue
        try:
            w = int(re.sub(r"[^\d]", "", (n.get("width") or "")) or "0")
            h = int(re.sub(r"[^\d]", "", (n.get("height") or "")) or "0")
            if (w and w < 100) or (h and h < 100):
                continue
        except Exception:
            pass
        if n.find_parent(style=re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)):
            continue
        if u not in out:
            out.append(u)
    return out[:3]

# ============================================================
# SEQUÊNCIA DE IMAGENS DE DESTAQUE (GitHub)
# ============================================================

def resolve_repo_image_url(relative_path):
    if not relative_path:
        return ""
    if relative_path in _image_url_cache:
        return _image_url_cache[relative_path]

    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    branch = os.getenv("GITHUB_REF_NAME", "").strip() or "main"
    if not repository:
        _image_url_cache[relative_path] = ""
        return ""

    repo_encoded = quote(repository, safe="/")
    branch_encoded = quote(branch, safe="")
    path_encoded = quote(relative_path, safe="/")

    candidates = [
        f"https://cdn.jsdelivr.net/gh/{repo_encoded}@{branch_encoded}/{path_encoded}",
        f"https://raw.githubusercontent.com/{repo_encoded}/{branch_encoded}/{path_encoded}",
    ]

    for candidate in candidates:
        try:
            r = requests.get(candidate, stream=True, timeout=12,
                             headers={"User-Agent": "RadioLuzGospel/14.0"})
            status = r.status_code
            content_type = (r.headers.get("Content-Type") or "").lower()
            r.close()
            if status == 200 and content_type.startswith("image/"):
                print(f"✓ Imagem sequencial: {relative_path} → {candidate}")
                _image_url_cache[relative_path] = candidate
                return candidate
            print(f"⚠ Imagem sequencial indisponível ({status}, {content_type}): {candidate}")
        except Exception as exc:
            print(f"⚠ Imagem sequencial: erro ao validar {candidate}: {exc}")

    _image_url_cache[relative_path] = ""
    return ""

def pick_next_image_url(posts_count):
    if not IMAGE_FILES:
        return "", ""
    total = len(IMAGE_FILES)
    start_idx = posts_count % total
    for offset in range(total):
        idx = (start_idx + offset) % total
        rel = IMAGE_FILES[idx]
        url = resolve_repo_image_url(rel)
        if url:
            return url, rel
    return "", ""

# ============================================================
# ARTIGO
# ============================================================

def get_article(url):
    x = soup(url)
    if not x:
        return None

    n = x.find("h1") or x.find("title")
    title = re.sub(r"\s+", " ", n.get_text(" ", strip=True) if n else "").strip()
    if not title:
        return None

    title_lower = title.lower()
    index_titles = {
        "lançamentos", "notícias", "noticias", "home", "início", "inicio",
        "últimas notícias", "ultimas noticias", "404",
        "página não encontrada", "pagina nao encontrada",
    }
    if title_lower in index_titles:
        print("Página de índice/categoria. Pulando.")
        return None

    d = article_date(x)
    if d:
        age = (datetime.now() - d).total_seconds() / 86400
        if age > MAX_AGE_DAYS:
            print(f"⚠ Notícia antiga (publicada em {d.strftime('%d/%m/%Y')}, {age:.1f} dias). Pulando.")
            return None
        print(f"✓ Data válida: {d.strftime('%d/%m/%Y %H:%M')} (idade: {age:.2f} dias)")
    else:
        print("⚠ Data não identificada. Aceitando para análise.")

    img = image_original(x) or ""

    box = x.find("article") or x.find("main") or x
    paragraphs = []
    for p in box.find_all("p"):
        text = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
        if len(text) >= 35:
            paragraphs.append(text)
    text = "\n\n".join(paragraphs)

    if len(text) < MIN_SOURCE_CHARS or len(paragraphs) < MIN_SOURCE_PARAGRAPHS:
        print(f"⚠ Conteúdo insuficiente: {len(text)} caracteres; {len(paragraphs)} parágrafos")
        return None

    link_count = len(box.find_all("a"))
    if len(text) < 1000 and link_count > len(paragraphs) * 4:
        print("Página parece índice/listagem. Pulando.")
        return None

    vv = videos(x)
    inline_imgs = []
    if img:
        inline_imgs = [{"url": img, "after_paragraph": 2, "is_main": True}]

    print("Notícia encontrada:", title)
    print("Texto extraído:", len(text), "caracteres")
    if vv:
        print(f"Vídeos válidos encontrados: {len(vv)}")

    return {
        "url": normalize_url(url),
        "title": title,
        "date": d,
        "image": img,
        "text": text[:16000],
        "videos": vv,
        "inline_images": inline_imgs,
    }

def links(source):
    out = []
    seen = set()
    source_host = urlparse(source["url"]).netloc.lower()

    def host_matches(u):
        h = urlparse(u).netloc.lower()
        if h == source_host:
            return True
        if h.endswith("." + source_host):
            return True
        h_no_www = h.replace("www.", "", 1)
        s_no_www = source_host.replace("www.", "", 1)
        return h_no_www == s_no_www or h_no_www.endswith("." + s_no_www)

    for feed in source["feeds"]:
        x = soup(feed, True)
        if not x:
            continue
        for item in x.find_all(["item", "entry"]):
            n = item.find("link")
            if not n:
                continue
            u = normalize_url(n.get("href") or n.get_text(strip=True) or "")
            if not u or bad_url(u) or not host_matches(u):
                continue
            if u not in seen:
                seen.add(u)
                out.append(u)

    x = soup(source["url"])
    if x:
        for a in x.find_all("a", href=True):
            u = normalize_url(urljoin(source["url"], a["href"]))
            if bad_url(u) or not host_matches(u):
                continue
            if u not in seen:
                seen.add(u)
                out.append(u)

    print(f"Links encontrados em {source['nome']}: {len(out)}")
    return out[:MAX_LINKS_PER_SOURCE]

def blogger():
    credentials = Credentials(
        None,
        refresh_token=BLOGGER_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/blogger"],
    )
    return build("blogger", "v3", credentials=credentials, cache_discovery=False)

# ============================================================
# EXTRAÇÃO DE CONTEÚDO E FINGERPRINT
# ============================================================

_COMPARE_STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em",
    "um", "uma", "uns", "umas", "para", "por", "com", "no", "na",
    "nos", "nas", "que", "se", "ao", "aos", "sua", "seu", "suas",
    "seus", "mais", "como", "sobre", "entre", "apos", "ate", "ja",
    "nao", "muito", "bem", "ainda", "tambem", "so", "esse", "essa",
    "este", "esta", "isso", "aquilo", "ele", "ela", "eles", "elas",
    "vai", "vem", "foi", "sao", "estao", "tem", "ter", "terao",
    "eh", "ser", "sera", "novo", "nova", "novos", "novas",
    "lanca", "lancou", "lancam", "lancar", "anuncia", "anunciou",
    "divulga", "divulgou", "revela", "revelou", "confirma", "confirmou",
    "veja", "confira", "saiba", "assista", "leia", "chega", "chegou",
    "radio", "luz", "gospel", "noticia", "noticias", "blog", "materia",
    "hoje", "agora", "ultima", "ultimas", "ultimo", "ultimos",
    "video", "videos", "foto", "fotos", "imagem", "imagens",
    "the", "of", "to", "in", "and", "or", "on", "at", "for",
    "with", "from", "by",
}

_GENERIC_ENTITIES = {
    "brasil", "europa", "alemanha", "portugal", "estados", "unidos",
    "africa", "america", "asia", "mundo", "pais", "paises", "cidade",
    "estado", "governo", "igreja", "igrejas", "cristao", "cristaos",
    "evangelico", "evangelicos", "evangelica", "evangelicas",
    "pastor", "pastores", "lider", "lideres", "deus", "jesus", "cristo",
    "biblia", "fe", "evangelho", "missao", "missoes",
    "alianca", "rede", "redes", "comunidade", "comunidades",
    "congregacao", "congregacoes", "nacao", "nacoes", "povo", "povos",
    "grupo", "grupos", "movimento", "projeto", "projetos", "evento",
    "eventos", "encontro", "encontros", "conferencia", "conferencias",
    "ano", "anos", "mes", "meses", "dia", "dias", "semana",
    "noticia", "noticias", "reportagem", "materia",
}

def _compare_normalize(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = [w for w in text.split() if len(w) > 1 and w not in _COMPARE_STOPWORDS]
    return set(words)

def _normalized_full_string(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def _title_similarity(words_a, words_b):
    if not words_a or not words_b:
        return 0.0
    inter = words_a & words_b
    union = words_a | words_b
    return len(inter) / len(union) if union else 0.0

def _extract_entities(text):
    raw = str(text or "").strip()
    if not raw:
        return []

    entities = []
    tokens = re.findall(r"[A-Za-zÀ-ÿ0-9]+", raw)
    if not tokens:
        return []

    def is_cap(tok):
        return tok[:1].isupper() if tok else False

    def is_upper_acronym(tok):
        return 2 <= len(tok) <= 6 and tok.isupper() and tok.isalpha()

    def is_year_or_number(tok):
        return tok.isdigit() and (len(tok) >= 3)

    n = len(tokens)
    i = 0
    while i < n:
        tok = tokens[i]
        if is_cap(tok) and not is_upper_acronym(tok):
            j = i
            while j + 1 < n and is_cap(tokens[j + 1]) and not is_upper_acronym(tokens[j + 1]):
                j += 1
                if j - i + 1 >= 4:
                    break
            seq = tokens[i:j + 1]
            if len(seq) >= 2:
                entities.append(" ".join(seq).lower())
            elif len(seq) == 1 and len(seq[0]) >= 5:
                entities.append(seq[0].lower())
            i = j + 1
            continue
        if is_upper_acronym(tok):
            entities.append(tok.lower())
            i += 1
            continue
        if is_year_or_number(tok) and tok.startswith(("19", "20")):
            entities.append(tok)
            i += 1
            continue
        i += 1

    seen = set()
    out = []
    for e in entities:
        e = re.sub(r"\s+", " ", e).strip()
        if not e or e in seen:
            continue
        seen.add(e)
        out.append(e)
    return out

def _entity_words(entity):
    return set(_compare_normalize(entity))

def _entities_overlap(entities_a, entities_b):
    strong = 0
    weak = 0
    for ea in entities_a:
        wa = _entity_words(ea)
        if not wa or wa.issubset(_GENERIC_ENTITIES):
            continue
        for eb in entities_b:
            wb = _entity_words(eb)
            if not wb or wb.issubset(_GENERIC_ENTITIES):
                continue
            inter = wa & wb
            if not inter:
                continue
            ratio = len(inter) / min(len(wa), len(wb))
            if ratio >= 0.5:
                strong += 1
                break
            else:
                weak += 1
                break
    return strong, weak

def _content_fingerprint(raw_text):
    raw = str(raw_text or "")
    entities = _extract_entities(raw)

    normalized = unicodedata.normalize("NFKD", raw)
    normalized = "".join(c for c in normalized if not unicodedata.combining(c)).lower()
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    tokens = normalized.split()

    rare_words = set()
    for w in tokens:
        if len(w) < 5:
            continue
        if w in _COMPARE_STOPWORDS or w in _GENERIC_ENTITIES:
            continue
        rare_words.add(w)

    return {"entities": entities, "rare_words": rare_words}

def _content_overlap(fp_new, fp_old):
    ent_new = set()
    for e in fp_new.get("entities", []):
        ew = _entity_words(e)
        if ew and not ew.issubset(_GENERIC_ENTITIES):
            ent_new.add(e)
    ent_old = set()
    for e in fp_old.get("entities", []):
        ew = _entity_words(e)
        if ew and not ew.issubset(_GENERIC_ENTITIES):
            ent_old.add(e)

    n_entities = 0
    if ent_new and ent_old:
        strong, _weak = _entities_overlap(list(ent_new), list(ent_old))
        n_entities = strong

    rw_new = fp_new.get("rare_words") or set()
    rw_old = fp_old.get("rare_words") or set()
    if rw_new and rw_old:
        inter = rw_new & rw_old
        ratio = len(inter) / min(len(rw_new), len(rw_old))
    else:
        ratio = 0.0

    return n_entities, ratio

# ============================================================
# BUSCA DE POSTS EXISTENTES (com fingerprint de conteúdo)
# ============================================================

def existing(api, show_log=True):
    blog_urls = set()
    source_urls = set()
    titles = []
    subjects = []
    source_titles = []
    entities_list = []
    content_fingerprints = []
    posts_list = []
    bot_posts_count = 0
    token = None
    try:
        while True:
            kwargs = {
                "blogId": BLOGGER_BLOG_ID,
                "maxResults": 500,
                "fetchBodies": True,
            }
            if token:
                kwargs["pageToken"] = token
            data = api.posts().list(**kwargs).execute()
            for post in data.get("items", []):
                post_id = post.get("id", "")
                post_url = normalize_url(post.get("url", ""))
                title = (post.get("title") or "").strip()
                content = post.get("content", "") or ""
                labels = post.get("labels", []) or []

                if post_url:
                    blog_urls.add(post_url)
                if title:
                    titles.append(title)

                try:
                    visible_text = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
                except Exception:
                    visible_text = ""

                full_text_for_fp = (title + " " + visible_text)[:12000]
                fp = _content_fingerprint(full_text_for_fp)
                content_fingerprints.append({
                    "post_id": post_id,
                    "post_url": post_url,
                    "title": title,
                    "entities": fp["entities"],
                    "rare_words": fp["rare_words"],
                })

                posts_list.append({
                    "id": post_id,
                    "title": title,
                    "url": post_url,
                    "labels": labels,
                    "published": post.get("published", ""),
                })

                for match in re.findall(r'href=["\'](https?://[^"\']+)["\']', content, flags=re.I):
                    source_urls.add(normalize_url(match))
                for match in re.findall(r'RADIO_LUZ_GOSPEL_SOURCE_URL:\s*(https?://[^\s]+?)\s*-->', content, flags=re.I):
                    source_urls.add(normalize_url(match))

                m = re.search(r'RADIO_LUZ_GOSPEL_SUBJECT:\s*([^\n]+?)\s*-->', content, flags=re.I)
                if m and m.group(1).strip():
                    subjects.append(m.group(1).strip())

                m = re.search(r'RADIO_LUZ_GOSPEL_SOURCE_TITLE:\s*([^\n]+?)\s*-->', content, flags=re.I)
                if m and m.group(1).strip():
                    source_titles.append(m.group(1).strip())

                m = re.search(r'RADIO_LUZ_GOSPEL_ENTITIES:\s*([^\n]+?)\s*-->', content, flags=re.I)
                if m and m.group(1).strip():
                    try:
                        ents = json.loads(m.group(1).strip())
                        if isinstance(ents, list):
                            entities_list.append([str(x) for x in ents if str(x).strip()])
                    except Exception:
                        pass

                if re.search(r"RADIO_LUZ_GOSPEL_SOURCE_URL:", content, flags=re.I):
                    bot_posts_count += 1

            token = data.get("nextPageToken")
            if not token:
                break
    except Exception as e:
        print("Erro ao consultar Blogger:", e)
    if show_log:
        print("Posts existentes no Blogger:", len(blog_urls))
        print("Fontes já registradas:", len(source_urls))
        print(f"Posts do robô já publicados: {bot_posts_count}")
    return (
        blog_urls, source_urls, titles, subjects, source_titles,
        entities_list, content_fingerprints, posts_list, bot_posts_count,
    )

# ============================================================
# ANTI-DUPLICIDADE (RÍGIDA)
# ============================================================

def is_duplicate_story(
    article,
    generated,
    existing_titles,
    existing_subjects,
    existing_source_titles,
    existing_entities=None,
    content_fingerprints=None,
):
    existing_entities = existing_entities or []
    content_fingerprints = content_fingerprints or []

    new_gen_title = (generated.get("titulo") or "").strip()
    new_src_title = (article.get("title") or "").strip()
    new_subject = (generated.get("assunto_principal") or "").strip()

    # ----- Camada 0: título original da fonte idêntico -----
    new_src_norm = _normalized_full_string(new_src_title)
    if new_src_norm and len(new_src_norm) >= 20:
        for ex_src in existing_source_titles:
            if _normalized_full_string(ex_src) == new_src_norm:
                return True, "mesma matéria-fonte (título original idêntico)"

    new_gen_words = _compare_normalize(new_gen_title)
    new_src_words = _compare_normalize(new_src_title)

    best_score = 0.0
    best_match = ""

    # ----- Camadas 1 e 2: similaridade de título (threshold reduzido para 0.40) -----
    for existing_title in existing_titles:
        ex_words = _compare_normalize(existing_title)
        if not ex_words:
            continue
        sim = max(
            _title_similarity(new_gen_words, ex_words),
            _title_similarity(new_src_words, ex_words),
        )
        if sim > best_score:
            best_score = sim
            best_match = existing_title

    for existing_src in existing_source_titles:
        ex_words = _compare_normalize(existing_src)
        if not ex_words:
            continue
        sim = max(
            _title_similarity(new_gen_words, ex_words),
            _title_similarity(new_src_words, ex_words),
        )
        if sim > best_score:
            best_score = sim
            best_match = existing_src

    if best_score >= 0.40:
        return True, f"título muito similar a post existente ({best_score:.2f}): {best_match[:80]}"

    # ----- Camada 3: mesmo assunto + título relacionado -----
    if new_subject:
        new_subj_words = _compare_normalize(new_subject)
        if new_subj_words:
            for ex_subj in existing_subjects:
                ex_subj_words = _compare_normalize(ex_subj)
                if not ex_subj_words:
                    continue
                overlap = len(new_subj_words & ex_subj_words) / max(1, len(new_subj_words))
                if overlap >= 0.60 and best_score >= 0.30:
                    return True, f"mesmo assunto ({new_subject[:40]}) e título relacionado (score {best_score:.2f})"

    # ----- Camada 4: entidades fortes em comum (1+ já bloqueia) -----
    new_entities = _extract_entities(new_gen_title) + _extract_entities(new_src_title)
    seen_e = set()
    new_entities_dedup = []
    for e in new_entities:
        if e not in seen_e:
            seen_e.add(e)
            new_entities_dedup.append(e)

    for ex_ents in existing_entities:
        if not ex_ents:
            continue
        strong, weak = _entities_overlap(new_entities_dedup, ex_ents)
        if strong >= 1:
            return True, f"{strong} entidade(s) forte(s) em comum com post existente"

    # ----- Camada 5: fingerprint de conteúdo (threshold reduzido para 0.30) -----
    new_content_text = (
        (new_src_title + ". ") * 2
        + " ".join([new_gen_title, new_subject])
        + "\n" + (article.get("text") or "")[:6000]
    )
    fp_new = _content_fingerprint(new_content_text)

    for fp_old in content_fingerprints:
        if not fp_old:
            continue
        n_entities, ratio = _content_overlap(fp_new, fp_old)
        if n_entities >= 1:
            return True, (
                f"{n_entities} entidade(s) em comum no conteúdo "
                f"(post antigo: {fp_old.get('title','')[:60]})"
            )
        if ratio >= 0.30:
            return True, (
                f"conteúdo muito similar a post existente "
                f"(vocabulário {ratio*100:.0f}% em comum; "
                f"post antigo: {fp_old.get('title','')[:60]})"
            )

    return False, ""

# ============================================================
# VERIFICAÇÃO VIA API DO BLOGGER (RÍGIDA)
# ============================================================

def _tech_norm(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", text).strip()

def check_blogger_for_duplicate(api, article_title):
    """
    Busca no Blogger por palavras-chave do título.
    Usa 3 termos mais longos e compara similaridade >= 0.45.
    """
    keywords = _compare_normalize(article_title)
    if not keywords:
        return False, ""

    search_terms = sorted(list(keywords), key=len, reverse=True)[:3]
    query = " ".join(search_terms)

    try:
        response = api.posts().search(
            blogId=BLOGGER_BLOG_ID,
            q=query,
            fetchBodies=False,
            maxResults=10,
        ).execute()

        for post in response.get("items", []):
            post_title = post.get("title", "")
            sim = _title_similarity(
                _compare_normalize(article_title),
                _compare_normalize(post_title),
            )
            if sim >= 0.45:
                return True, post_title
            post_norm = _tech_norm(post_title)
            if all(term in post_norm for term in search_terms):
                return True, post_title

    except Exception as e:
        print(f"⚠ Busca API: erro ao verificar duplicata: {e}")

    return False, ""

# ============================================================
# LIMPEZA DE DUPLICATAS JÁ PUBLICADAS
# ============================================================

def _clean_existing_duplicates(api, posts_list, content_fingerprints):
    if not posts_list:
        print("✓ Limpeza: nenhum post para analisar.")
        return

    def _pub_ts(p):
        pub = p.get("published", "") or ""
        try:
            return datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    ordered = sorted(posts_list, key=_pub_ts)
    fp_by_id = {fp.get("post_id"): fp for fp in content_fingerprints if fp}

    drafts_marked = 0
    for i, post in enumerate(ordered):
        post_id = post.get("id")
        fp_new = fp_by_id.get(post_id)
        if not fp_new:
            continue

        for j in range(i):
            prev_post = ordered[j]
            prev_id = prev_post.get("id")
            fp_old = fp_by_id.get(prev_id)
            if not fp_old:
                continue

            n_entities, ratio = _content_overlap(fp_new, fp_old)
            dup = False
            reason = ""
            if n_entities >= 1:
                dup = True
                reason = f"{n_entities} entidade(s) em comum"
            elif ratio >= 0.30:
                dup = True
                reason = f"vocabulário {ratio*100:.0f}% em comum"

            if dup:
                try:
                    api.posts().update(
                        blogId=BLOGGER_BLOG_ID,
                        postId=post_id,
                        body={
                            "id": post_id,
                            "title": post.get("title", ""),
                            "content": "",
                            "labels": post.get("labels", []),
                        },
                        isDraft=True,
                    ).execute()
                    drafts_marked += 1
                    print(f"✓ Limpeza: post marcado como rascunho — {post.get('title','')[:70]} ({reason})")
                except Exception as exc:
                    print(f"⚠ Limpeza: falha ao marcar rascunho ({post.get('title','')[:50]}): {str(exc)[:150]}")
                break

    if drafts_marked:
        print(f"✓ Limpeza: {drafts_marked} post(s) duplicado(s) movido(s) para rascunho.")
    else:
        print("✓ Limpeza: nenhuma duplicata detectada nos posts existentes.")

# ============================================================
# IA
# ============================================================

def is_transient_gemini_error(exc):
    msg = str(exc).upper()
    return any(code in msg for code in (
        "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED",
        "500", "502", "504", "TIMEOUT",
    ))

def gemini_request(client, model, prompt):
    last_error = None
    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                return client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
        except Exception as e:
            last_error = e
            msg = str(e).upper()
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                raise
            if not is_transient_gemini_error(e) or attempt >= GEMINI_MAX_RETRIES:
                raise
            delay = GEMINI_RETRY_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 2)
            time.sleep(delay)
    raise last_error

def norm_words(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.findall(r"[a-z0-9]+", text)

def ngrams(words, n=8):
    return {" ".join(words[i:i+n]) for i in range(max(0, len(words)-n+1))}

def longest_common_phrase(src_words, out_words, min_words=15):
    if not src_words or not out_words:
        return 0
    positions = {}
    for i, word in enumerate(src_words):
        positions.setdefault(word, []).append(i)
    best = 0
    for j, word in enumerate(out_words):
        for i in positions.get(word, [])[:20]:
            k = 0
            while i+k < len(src_words) and j+k < len(out_words) and src_words[i+k] == out_words[j+k]:
                k += 1
            best = max(best, k)
            if best >= min_words:
                return best
    return best

def originality_check(source_text, generated_text):
    src = norm_words(source_text)
    out = norm_words(generated_text)
    if len(out) < 100:
        return False, "matéria curta demais"
    src8 = ngrams(src, 8)
    out8 = ngrams(out, 8)
    overlap = len(src8 & out8) / max(1, min(len(src8), len(out8)))
    longest = longest_common_phrase(src, out)
    if longest >= 15:
        return False, f"há sequência de {longest} palavras iguais"
    if overlap > 0.12:
        return False, f"sobreposição 8-gram alta ({overlap:.3f})"
    return True, "OK"

def _ai_extract_text(provider, response):
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return str(content).strip()

def _provider_is_quota_error(status_code, body):
    text = str(body or "").upper()
    return status_code == 429 or any(x in text for x in (
        "RESOURCE_EXHAUSTED", "RATE LIMIT", "RATE_LIMIT", "QUOTA",
        "TOO MANY REQUESTS", "DAILY LIMIT", "LIMIT EXCEEDED",
    ))

def _call_http_provider(provider, api_key, model, prompt):
    endpoint = {
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "mistral": "https://api.mistral.ai/v1/chat/completions",
    }.get(provider)
    if not endpoint:
        raise ValueError(f"Provedor HTTP desconhecido: {provider}")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 5000,
        "response_format": {"type": "json_object"},
    }
    if provider == "groq":
        payload["include_reasoning"] = False
    r = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=AI_PROVIDER_TIMEOUT,
    )
    body = r.text[:1200]
    if _provider_is_quota_error(r.status_code, body):
        raise RuntimeError(f"QUOTA_HTTP_{r.status_code}: {body}")
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP_{r.status_code}: {body}")
    try:
        return r.json()
    except Exception as exc:
        raise RuntimeError(f"Resposta JSON inválida do {provider}: {exc}")

def _build_ai_providers():
    providers = []
    if GEMINI_API_KEY:
        providers.append(("gemini", GEMINI_API_KEY, GEMINI_MODEL_TEXT))
    if GEMINI_API_KEY_2:
        providers.append(("gemini-2", GEMINI_API_KEY_2, GEMINI_FALLBACK_MODEL))
    if GROQ_API_KEY:
        providers.append(("groq", GROQ_API_KEY, GROQ_MODEL))
    if MISTRAL_API_KEY:
        providers.append(("mistral", MISTRAL_API_KEY, MISTRAL_MODEL))
    return providers

def _provider_request(provider, api_key, model, prompt):
    if provider.startswith("gemini"):
        return gemini_request(genai.Client(api_key=api_key), model, prompt)
    return _call_http_provider(provider, api_key, model, prompt)

def _provider_text(provider, response):
    if provider.startswith("gemini"):
        return (getattr(response, "text", None) or "").strip()
    return _ai_extract_text(provider, response)

def _is_quota_exception(exc):
    msg = str(exc).upper()
    return any(x in msg for x in (
        "429", "RESOURCE_EXHAUSTED", "QUOTA", "RATE LIMIT", "RATE_LIMIT",
        "TOO MANY REQUESTS", "DAILY LIMIT", "LIMIT EXCEEDED",
    ))

def gemini(article, client=None):
    global gemini_calls, gemini_quota_hit, _ai_config_logged
    if gemini_calls >= MAX_GEMINI_TEXT_CALLS_PER_RUN:
        print("⚠ IA: limite de chamadas desta execução atingido.")
        return None

    providers = _build_ai_providers()
    if not _ai_config_logged:
        print(
            "IA: "
            f"Gemini={'SIM' if GEMINI_API_KEY else 'NÃO'} | "
            f"Gemini-2={'SIM' if GEMINI_API_KEY_2 else 'NÃO'} | "
            f"Groq={'SIM' if GROQ_API_KEY else 'NÃO'} | "
            f"Mistral={'SIM' if MISTRAL_API_KEY else 'NÃO'}"
        )
        _ai_config_logged = True
    if not providers:
        print("⚠ IA: nenhuma chave configurada.")
        return None

    prompt = f"""
Você é jornalista do Rádio Luz Gospel. Escreva uma matéria NOVA, do zero.
Use SOMENTE os fatos presentes no texto-fonte.
Não invente nomes, datas, números, locais, declarações ou acontecimentos.
Não acrescente informações externas.
Crie título, resumo e matéria em português do Brasil.
A matéria deve ter aproximadamente 700 a 1200 palavras.
Não diga que foi escrita por IA.

CRITÉRIO DE PUBLICAÇÃO (leia com atenção):
Você DEVE marcar publicar=true para QUALQUER notícia que tenha
relevância jornalística e conteúdo gospel/cristão/evangélico, incluindo:
- música gospel, lançamentos, shows, turnês, festivais;
- testemunhos de artistas, pastores e líderes religiosos;
- eventos gospel, conferências, congressos, cultos especiais;
- política religiosa, liberdade religiosa, perseguição a cristãos;
- ações sociais de igrejas, projetos missionários, missões;
- notícias sobre denominações, convenções, alianças;
- entrevistas, declarações, posicionamentos de líderes cristãos;
- prêmios, homenagens, indicações envolvendo artistas gospel;
- qualquer notícia que tenha relação com o universo gospel/cristão.

Marque publicar=false SOMENTE se a notícia for COMPLETAMENTE alheia
ao universo gospel/cristão (ex.: futebol, economia geral, política
partidária sem relação com igrejas, celebridades não-religiosas).

REGRA DE OURO: se houver DÚVIDA, marque publicar=true.

OUTRAS REGRAS:
- título novo e jornalístico;
- resumo de 2 a 3 frases;
- não copiar frases ou parágrafos da fonte;
- não traduzir nem reproduzir a estrutura da matéria original;
- retornar SOMENTE JSON válido, sem Markdown;
- no campo "assunto_principal", informe o NOME DA PESSOA, BANDA, GRUPO
  ou IGREJA mais importante citado na matéria. Se não houver,
  deixe string vazia "".
- no campo "palavras_chave", informe uma lista com 5 a 10 palavras-chave
  de SEO relacionadas ao conteúdo.
- no campo "categoria_seo", informe a categoria principal do assunto:
  "Música Gospel", "Lançamento", "Show", "Entrevista", "Evento",
  "Notícia Gospel", "Testemunho", "Política Religiosa" ou "Missões".

FORMATO:
{{"publicar":true,"titulo":"...","resumo":"...","materia":"...","assunto_principal":"...","palavras_chave":["..."],"categoria_seo":"..."}}

TÍTULO ORIGINAL:
{article['title']}

FONTE:
{article['url']}

TEXTO-FONTE:
{article['text']}
"""

    exhausted = set()
    last_reason = "erro"
    for pass_index in range(2):
        pass_prompt = prompt if pass_index == 0 else prompt + """

ATENÇÃO: a versão anterior foi rejeitada por originalidade. Faça uma nova
redação, reorganizando completamente a ordem das informações e variando as
construções das frases. Não repita sequências da fonte.
"""
        for provider, api_key, model in providers:
            if gemini_calls >= MAX_GEMINI_TEXT_CALLS_PER_RUN:
                break
            if provider in exhausted:
                continue
            try:
                print(f"IA: tentando {provider} / {model}...")
                response = _provider_request(provider, api_key, model, pass_prompt)
                gemini_calls += 1
                raw = _provider_text(provider, response)
                if not raw:
                    last_reason = "resposta vazia"
                    print(f"⚠ {provider}: resposta vazia.")
                    continue
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
                data = json.loads(raw)
                if data.get("publicar") is False:
                    last_reason = "sem informação suficiente"
                    print(f"⚠ {provider}: marcou a matéria como não publicável; tentando próximo provedor.")
                    continue
                titulo = str(data.get("titulo", "")).strip()
                resumo = str(data.get("resumo", "")).strip()
                materia = str(data.get("materia", "")).strip()
                assunto = str(data.get("assunto_principal", "")).strip()
                palavras_chave = data.get("palavras_chave", []) or []
                if isinstance(palavras_chave, str):
                    palavras_chave = [p.strip() for p in palavras_chave.split(",") if p.strip()]
                categoria_seo = str(data.get("categoria_seo", "")).strip()
                if not titulo or not resumo or len(materia) < 700:
                    last_reason = "resposta inválida"
                    print(f"⚠ {provider}: resposta inválida ou curta demais.")
                    continue
                ok, reason = originality_check(article["text"], titulo + "\n" + resumo + "\n" + materia)
                if not ok:
                    last_reason = "originalidade"
                    print(f"⚠ {provider}: matéria recusada por originalidade ({reason}) — tentando outra IA.")
                    continue
                print(f"✓ IA: matéria aprovada ({provider} / {model}, tentativa {pass_index + 1})")
                if assunto:
                    print(f"✓ IA: assunto principal identificado: {assunto}")
                return {
                    "publicar": True,
                    "titulo": titulo,
                    "resumo": resumo,
                    "materia": materia,
                    "assunto_principal": assunto,
                    "palavras_chave": palavras_chave[:SEO_KEYWORDS_MAX],
                    "categoria_seo": categoria_seo,
                }
            except Exception as exc:
                if _is_quota_exception(exc):
                    exhausted.add(provider)
                    last_reason = "quota"
                    print(f"⚠ {provider}: quota/limite atingido — passando para o próximo provedor.")
                else:
                    last_reason = "erro"
                    print(f"⚠ {provider}: erro na geração: {str(exc)[:240]}")

    if last_reason == "quota":
        gemini_quota_hit = True
        print("⚠ IA: provedores disponíveis atingiram quota/limite; restante ficará para a próxima execução")
    elif last_reason == "originalidade":
        print("⚠ IA: todas as tentativas foram recusadas por originalidade")
    elif last_reason == "sem informação suficiente":
        print("⚠ IA: provedores não consideraram a fonte suficiente para publicação")
    elif last_reason in ("resposta inválida", "resposta_invalida"):
        print("⚠ IA: geração retornou formato inválido")
    else:
        print("⚠ IA: nenhum provedor disponível conseguiu gerar a matéria")
    return None

# ============================================================
# SEO AUTOMÁTICO
# ============================================================

def _strip_html(text):
    return re.sub(r"\s+", " ", BeautifulSoup(str(text or ""), "html.parser").get_text(" ", strip=True)).strip()

def _truncate(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_space = cut.rfind(" ")
    if last_space > limit * 0.6:
        cut = cut[:last_space]
    return cut.rstrip(" ,;:-") + "..."

def build_seo_payload(article, generated, final_image="", image_origin=""):
    titulo_base = str(generated.get("titulo", "")).strip()
    resumo = str(generated.get("resumo", "")).strip()
    materia = str(generated.get("materia", "")).strip()
    assunto = str(generated.get("assunto_principal", "")).strip()
    categoria_seo = str(generated.get("categoria_seo", "")).strip()
    palavras = list(generated.get("palavras_chave", []) or [])

    title = titulo_base
    if SEO_TITLE_SUFFIX and not title.lower().endswith(SEO_TITLE_SUFFIX.lower()):
        title = f"{titulo_base}{SEO_TITLE_SUFFIX}"

    base_desc = resumo or _strip_html(materia)[:SEO_DESCRIPTION_MAX]
    description = _truncate(base_desc, SEO_DESCRIPTION_MAX)

    kw = []
    if assunto:
        kw.append(assunto)
    if categoria_seo:
        kw.append(categoria_seo)
    for p in palavras:
        p = str(p).strip()
        if p and p.lower() not in {k.lower() for k in kw}:
            kw.append(p)
    for fallback in ("música gospel", "gospel", "notícias gospel", BLOG_NAME):
        if fallback.lower() not in {k.lower() for k in kw}:
            kw.append(fallback)
    keywords = ", ".join(kw[:SEO_KEYWORDS_MAX])

    labels = ["Notícias", "Rádio Luz Gospel"]
    if categoria_seo:
        cat_clean = re.sub(r"\s+", " ", categoria_seo).strip()
        if cat_clean and cat_clean not in labels:
            labels.append(cat_clean)
    if assunto:
        assunto_clean = re.sub(r"\s+", " ", assunto).strip()
        if assunto_clean and assunto_clean not in labels and len(assunto_clean) <= 40:
            labels.append(assunto_clean)
    if article.get("date"):
        labels.append(str(article["date"].year))

    seen = set()
    labels_final = []
    for l in labels:
        l = str(l).strip()
        if not l:
            continue
        key = l.lower()
        if key in seen:
            continue
        seen.add(key)
        labels_final.append(l)
    labels_final = labels_final[:10]

    image_url = final_image or article.get("image", "")
    canonical = article.get("url", "")

    published = (article.get("date") or datetime.now()).isoformat()
    date_modified = datetime.now().isoformat()

    schema = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "headline": titulo_base[:110],
        "description": description,
        "image": [image_url] if image_url else [],
        "datePublished": published,
        "dateModified": date_modified,
        "author": {"@type": "Organization", "name": BLOG_NAME, "url": BLOG_HOME_URL},
        "publisher": {
            "@type": "Organization",
            "name": BLOG_NAME,
            "url": BLOG_HOME_URL,
            "logo": {"@type": "ImageObject", "url": image_url or f"{BLOG_HOME_URL}/favicon.ico"},
        },
        "articleSection": categoria_seo or "Notícias Gospel",
        "keywords": keywords,
        "inLanguage": "pt-BR",
        "isAccessibleForFree": True,
        "url": canonical,
        "sourceOrganization": {
            "@type": "Organization",
            "name": urlparse(article.get("url", "")).netloc,
            "url": article.get("url", ""),
        },
    }

    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Início", "item": BLOG_HOME_URL},
            {"@type": "ListItem", "position": 2, "name": "Notícias", "item": f"{BLOG_HOME_URL}/search/label/Not%C3%ADcias"},
            {"@type": "ListItem", "position": 3, "name": titulo_base[:80], "item": canonical},
        ],
    }

    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    safe_desc = description.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    safe_keywords = keywords.replace("&", "&amp;").replace('"', "&quot;")
    safe_canonical = canonical.replace("&", "&amp;").replace('"', "&quot;")
    safe_image = (image_url or "").replace("&", "&amp;").replace('"', "&quot;")
    twitter_site = f'<meta name="twitter:site" content="{BLOG_TWITTER}">' if BLOG_TWITTER else ""

    json_ld_article = json.dumps(schema, ensure_ascii=False)
    json_ld_breadcrumb = json.dumps(breadcrumb, ensure_ascii=False)

    html_head = f"""<!-- ===== SEO RÁDIO LUZ GOSPEL ===== -->
<title>{safe_title}</title>
<meta name="description" content="{safe_desc}">
<meta name="keywords" content="{safe_keywords}">
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">
<meta name="author" content="{BLOG_NAME}">
<meta name="language" content="Portuguese">
<meta name="revisit-after" content="1 days">
<meta name="rating" content="general">
<meta name="distribution" content="global">
<link rel="canonical" href="{safe_canonical}">

<!-- Open Graph -->
<meta property="og:type" content="article">
<meta property="og:site_name" content="{BLOG_NAME}">
<meta property="og:title" content="{safe_title}">
<meta property="og:description" content="{safe_desc}">
<meta property="og:url" content="{safe_canonical}">
<meta property="og:locale" content="{BLOG_LOCALE}">
{f'<meta property="og:image" content="{safe_image}">' if safe_image else ''}
{f'<meta property="og:image:width" content="1200">' if safe_image else ''}
{f'<meta property="og:image:height" content="630">' if safe_image else ''}
<meta property="article:published_time" content="{published}">
<meta property="article:modified_time" content="{date_modified}">
<meta property="article:section" content="{schema['articleSection']}">
{f'<meta property="article:tag" content="{assunto}">' if assunto else ''}

<!-- Twitter Card -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{safe_title}">
<meta name="twitter:description" content="{safe_desc}">
{f'<meta name="twitter:image" content="{safe_image}">' if safe_image else ''}
{twitter_site}

<!-- Schema.org NewsArticle -->
<script type="application/ld+json">{json_ld_article}</script>

<!-- Schema.org BreadcrumbList -->
<script type="application/ld+json">{json_ld_breadcrumb}</script>
<!-- ===== FIM SEO ===== -->"""

    return {
        "title": title,
        "titulo_base": titulo_base,
        "description": description,
        "keywords": keywords,
        "labels": labels_final,
        "canonical": canonical,
        "schema": schema,
        "breadcrumb": breadcrumb,
        "html_head": html_head,
        "source_url": article.get("url", ""),
        "assunto": assunto,
        "categoria_seo": categoria_seo,
    }

def build_seo_head_for_blogger(seo):
    return seo.get("html_head", "")

# ============================================================
# HTML DO POST
# ============================================================

def _render_inline_image_html(img_url, alt_text):
    safe_img = (img_url or "").replace("&", "&amp;").replace('"', "&quot;")
    safe_alt = (
        (alt_text or "")
        .replace("&", "&amp;").replace("<", "&lt;")
        .replace(">", "&gt;").replace('"', "&quot;")
    )
    if not safe_img:
        return ""
    return (
        '<p style="text-align:center;margin:24px 0;">'
        f'<img src="{safe_img}" '
        f'alt="{safe_alt}" '
        f'title="{safe_alt}" '
        'style="max-width:100%;height:auto;border-radius:12px;'
        'box-shadow:0 4px 12px rgba(0,0,0,0.10);'
        'display:block;margin-left:auto;margin-right:auto;">'
        '</p>'
    )

def html(article, generated, final_image="", image_origin="", seo=None):
    seo = seo or {}
    titulo_exibicao = seo.get("titulo_base") or generated.get("titulo", "")
    safe_title = (
        titulo_exibicao
        .replace("&", "&amp;").replace("<", "&lt;")
        .replace(">", "&gt;").replace('"', "&quot;")
    )

    image_url = final_image or article["image"]
    safe_image = image_url.replace("&", "&amp;").replace('"', "&quot;")

    safe_source_url = article["url"].replace("&", "&amp;").replace('"', "&quot;")

    seo_head = build_seo_head_for_blogger(seo)

    content = []
    if seo_head:
        content.append(seo_head)

    content.extend([
        f'<p><strong>{generated["resumo"]}</strong></p>',
        (
            f'<p><img src="{safe_image}" '
            f'alt="{safe_title}" '
            f'title="{safe_title}" '
            f'width="1200" height="630" '
            f'style="max-width:100%;height:auto;border-radius:12px;">'
            f'</p>'
        ),
    ])

    article_paragraphs = []
    for paragraph in re.split(r"\n+", generated["materia"]):
        paragraph = paragraph.strip()
        if paragraph:
            article_paragraphs.append(paragraph)

    inline_images = list(article.get("inline_images") or [])[:1]
    inline_images.sort(key=lambda item: item.get("after_paragraph", 9999))

    body_parts = []
    para_idx = 0
    total_paras = len(article_paragraphs)

    for img_info in inline_images:
        target = img_info.get("after_paragraph", 9999)
        try:
            target = int(target)
        except Exception:
            target = 9999
        if target < 0:
            target = 0
        if target > total_paras:
            target = total_paras
        while para_idx < target:
            body_parts.append(f"<p>{article_paragraphs[para_idx]}</p>")
            para_idx += 1
        rendered = _render_inline_image_html(img_info.get("url", ""), titulo_exibicao)
        if rendered:
            body_parts.append(rendered)

    while para_idx < total_paras:
        body_parts.append(f"<p>{article_paragraphs[para_idx]}</p>")
        para_idx += 1

    content.extend(body_parts)

    for video_url in article["videos"]:
        content.append(
            '<div style="margin:24px 0;padding:0;">'
            '<div style="position:relative;width:100%;padding-bottom:56.25%;'
            'height:0;overflow:hidden;border-radius:12px;'
            'box-shadow:0 4px 12px rgba(0,0,0,0.15);">'
            f'<iframe src="{video_url}" '
            'style="position:absolute;top:0;left:0;width:100%;height:100%;'
            'border:0;" '
            'frameborder="0" '
            'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
            'gyroscope; picture-in-picture; web-share" '
            'allowfullscreen loading="lazy" title="Vídeo da matéria">'
            '</iframe></div></div>'
        )

    spotify_block = (
        '<div style="max-width:600px;margin:2rem auto;padding:0 1rem;">'
        '<h3 style="text-align:center;color:#1DB954;font-family:Arial,sans-serif;margin-bottom:1rem;">'
        '🎵 Top 2026 — Rádio Luz Gospel'
        '</h3>'
        '<iframe '
        'style="border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.15);" '
        'src="https://open.spotify.com/embed/playlist/14OteRoEl6CVEsTCpYCYyx?utm_source=generator" '
        'width="100%" height="380" frameborder="0" allowfullscreen="" '
        'allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" '
        'loading="lazy" title="Playlist Rádio Luz Gospel no Spotify"></iframe>'
        '<p style="text-align:center;margin-top:0.8rem;font-size:0.95rem;color:#666;font-family:Arial,sans-serif;">'
        'Ouça a seleção especial da <strong>Rádio Luz Gospel</strong> 📻🙏'
        '</p></div>'
    )
    content.append(spotify_block)

    telegram_channel = os.getenv(
        "TELEGRAM_CHANNEL_URL",
        "https://t.me/radioluzgospelnoticias",
    ).strip() or "https://t.me/radioluzgospelnoticias"

    safe_telegram_channel = telegram_channel.replace("&", "&amp;").replace('"', "&quot;")

    content.append(
        '<div style="margin:24px 0;padding:18px;'
        'border:1px solid #ddd;border-radius:12px;text-align:center;">'
        '<p><strong>📲 Receba as próximas notícias no Telegram</strong></p>'
        '<p>Entre no canal oficial da Rádio Luz Gospel e acompanhe '
        'as novas notícias diretamente no Telegram.</p>'
        f'<p><a href="{safe_telegram_channel}" target="_blank" '
        'rel="noopener" style="display:inline-block;padding:10px 16px;'
        'border-radius:8px;text-decoration:none;font-weight:bold;">'
        '👉 ENTRAR NO CANAL DO TELEGRAM'
        '</a></p></div>'
    )

    source_marker = f"<!-- RADIO_LUZ_GOSPEL_SOURCE_URL: {safe_source_url} -->"

    raw_source_title = (article.get("title") or "").strip()
    safe_source_title = raw_source_title.replace("--", "—").replace("\n", " ")[:300]
    source_title_marker = ""
    if safe_source_title:
        source_title_marker = f"\n<!-- RADIO_LUZ_GOSPEL_SOURCE_TITLE: {safe_source_title} -->"

    raw_subject = (seo.get("assunto") or "").strip()
    safe_subject = raw_subject.replace("--", "—").replace("\n", " ")[:200]
    subject_marker = ""
    if safe_subject:
        subject_marker = f"\n<!-- RADIO_LUZ_GOSPEL_SUBJECT: {safe_subject} -->"

    ents = []
    try:
        ents = _extract_entities(raw_source_title) + _extract_entities(seo.get("titulo_base") or "")
        seen_e = set()
        ents_dedup = []
        for e in ents:
            if e not in seen_e:
                seen_e.add(e)
                ents_dedup.append(e)
        ents = ents_dedup[:40]
    except Exception:
        ents = []
    entities_marker = ""
    if ents:
        try:
            entities_json = json.dumps(ents, ensure_ascii=False).replace("--", "—")
            entities_marker = f"\n<!-- RADIO_LUZ_GOSPEL_ENTITIES: {entities_json} -->"
        except Exception:
            entities_marker = ""

    image_marker = ""
    if image_origin:
        image_marker = f"\n<!-- RADIO_LUZ_GOSPEL_IMAGE_SOURCE: {image_origin} -->"

    seo_marker = ""
    if seo:
        seo_marker = (
            f"\n<!-- RADIO_LUZ_GOSPEL_SEO_DESCRIPTION: {seo.get('description','')[:300]} -->"
            f"\n<!-- RADIO_LUZ_GOSPEL_SEO_KEYWORDS: {seo.get('keywords','')[:300]} -->"
        )

    return (
        "\n".join(content)
        + "\n" + source_marker
        + source_title_marker
        + subject_marker
        + entities_marker
        + image_marker
        + seo_marker
    )

def main():
    print("Fontes: News Gospel + Folha Gospel + Guiame + iGospel + Fuxico Gospel")
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    api = blogger()

    (
        old_blog_urls,
        old_source_urls,
        existing_titles,
        existing_subjects,
        existing_source_titles,
        existing_entities,
        content_fingerprints,
        posts_list,
        posts_count,
    ) = existing(api)

    if CLEAN_DUPLICATES:
        print("✓ Limpeza: CLEAN_DUPLICATES=true — analisando posts existentes...")
        _clean_existing_duplicates(api, posts_list, content_fingerprints)

    candidates = []
    candidate_urls = set()
    source_counts = {}
    prefiltered_out = 0
    pre_duplicates = 0

    for source in SOURCES:
        source_links = links(source)
        source_counts[source["nome"]] = len(source_links)
        for url in source_links:
            normalized = normalize_url(url)
            if normalized in candidate_urls or normalized in old_blog_urls or normalized in old_source_urls:
                continue
            article = get_article(normalized)
            if article:
                # SEM FILTRO MUSICAL — aceita qualquer notícia do dia/ontem
                pre_dup, pre_reason = is_duplicate_story(
                    article,
                    {"titulo": article.get("title", ""), "assunto_principal": ""},
                    existing_titles,
                    existing_subjects,
                    existing_source_titles,
                    existing_entities,
                    content_fingerprints,
                )
                if pre_dup:
                    pre_duplicates += 1
                    print(f"⚠ Duplicada (fonte): {article['title'][:70]} — {pre_reason}")
                    continue

                candidate_urls.add(normalized)
                candidates.append(article)

    source_summary = " | ".join(f"{name}: {count}" for name, count in source_counts.items())
    print(f"Fontes encontradas: {source_summary}")
    print(f"Puladas: {prefiltered_out + pre_duplicates}")
    if pre_duplicates:
        print(f"⚠ Duplicadas por conteúdo (pré-IA): {pre_duplicates}")

    candidates.sort(key=lambda a: a["date"] or datetime.min, reverse=True)
    print(f"Novas matérias de hoje/ontem: {len(candidates)}")

    published = 0
    failed = 0
    ignored = 0
    post_duplicates = 0

    while candidates and published < MAX_POSTS_PER_RUN:
        article = candidates.pop(0)
        normalized = normalize_url(article["url"])
        if normalized in old_source_urls:
            ignored += 1
            continue

        # VERIFICAÇÃO VIA API DO BLOGGER (RÍGIDA)
        is_dup_api, dup_title_api = check_blogger_for_duplicate(api, article["title"])
        if is_dup_api:
            print(f"⚠ Duplicada (API): «{article['title'][:60]}» já existe como «{dup_title_api[:60]}» — pulando.")
            ignored += 1
            continue

        if gemini_calls >= MAX_GEMINI_TEXT_CALLS_PER_RUN:
            print("⚠ Gemini: limite desta execução atingido; restante ficará para a próxima execução")
            break

        generated = gemini(article, gemini_client)
        if not generated:
            ignored += 1
            if gemini_quota_hit:
                break
            continue

        # VERIFICAÇÃO ANTI-DUPLICIDADE APÓS A IA (RÍGIDA)
        dup, dup_reason = is_duplicate_story(
            article,
            generated,
            existing_titles,
            existing_subjects,
            existing_source_titles,
            existing_entities,
            content_fingerprints,
        )
        if dup:
            post_duplicates += 1
            ignored += 1
            print(f"⚠ Duplicada (IA): {generated.get('titulo','')[:70]} — {dup_reason}")
            continue

        final_image, chosen_file = pick_next_image_url(posts_count + published)
        if not final_image:
            print("⚠ Imagem sequencial: nenhuma imagem acessível na pasta bot/Imagens/.")
            ignored += 1
            continue
        image_origin = f"Sequência: {chosen_file}"
        print(f"✓ Imagem final: {image_origin}")

        seo = build_seo_payload(
            article=article,
            generated=generated,
            final_image=final_image,
            image_origin=image_origin,
        )
        print(f"✓ SEO: título final = {seo['title'][:90]}")

        try:
            post_body = {
                "title": seo["title"].strip(),
                "content": html(article, generated, final_image=final_image,
                                image_origin=image_origin, seo=seo),
                "labels": seo["labels"],
            }
            try:
                post_body["customMetaData"] = seo["description"]
            except Exception:
                pass

            response = api.posts().insert(
                blogId=BLOGGER_BLOG_ID,
                body=post_body,
                isDraft=False,
            ).execute()

            published += 1
            old_source_urls.add(normalized)

            if seo.get("title"):
                existing_titles.append(seo["title"])
            if seo.get("titulo_base"):
                existing_titles.append(seo["titulo_base"])
            if article.get("title"):
                existing_source_titles.append(article["title"])
            if seo.get("assunto"):
                existing_subjects.append(seo["assunto"])

            try:
                new_ents = _extract_entities(article.get("title", "")) + _extract_entities(seo.get("titulo_base") or "")
                seen_e = set()
                new_ents_dedup = []
                for e in new_ents:
                    if e not in seen_e:
                        seen_e.add(e)
                        new_ents_dedup.append(e)
                if new_ents_dedup:
                    existing_entities.append(new_ents_dedup)
            except Exception:
                pass

            try:
                fp_new = _content_fingerprint(
                    (article.get("title", "") + " " + generated.get("titulo", "")
                     + " " + generated.get("resumo", "")
                     + " " + generated.get("materia", ""))[:12000]
                )
                content_fingerprints.append({
                    "post_id": response.get("id", ""),
                    "post_url": normalize_url(response.get("url", "")),
                    "title": seo["title"],
                    "entities": fp_new["entities"],
                    "rare_words": fp_new["rare_words"],
                })
            except Exception:
                pass

            if response.get("url"):
                old_blog_urls.add(normalize_url(response["url"]))
                try:
                    new_url = response["url"]
                    if new_url and new_url != seo["canonical"]:
                        updated_content = html(
                            article, generated,
                            final_image=final_image,
                            image_origin=image_origin,
                            seo={**seo, "canonical": new_url},
                        )
                        api.posts().patch(
                            blogId=BLOGGER_BLOG_ID,
                            postId=response["id"],
                            body={"content": updated_content},
                        ).execute()
                        print(f"✓ SEO: canonical atualizado para {new_url}")
                except Exception as canon_exc:
                    print(f"⚠ SEO: não foi possível atualizar canonical: {canon_exc}")

            print(f"✓ Publicada: {seo['title'].strip()}")
        except Exception as exc:
            failed += 1
            print(f"⚠ Blogger: falha ao publicar ({str(exc)[:200]})")

    print("RESULTADO")
    print(f"Publicações: {published}")
    print(f"Ignoradas: {ignored}")
    print(f"Falhas: {failed}")
    if post_duplicates:
        print(f"⚠ Duplicadas detectadas após IA: {post_duplicates}")

print("VERSÃO 14.0 ATIVA: 5 Fontes | Sem Filtro Musical | Anti-Duplicidade Rígida | SEO | Vídeos | Spotify | Telegram")

main()
