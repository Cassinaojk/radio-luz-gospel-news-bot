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
        or message == "RESULTADO"
        or message.startswith("Publicações:")
        or message.startswith("Ignoradas:")
        or message.startswith("Falhas:")
        or message.startswith("✓ Publicada:")
        or message.startswith("✓ Imagem:")
        or message.startswith("⚠ Blogger:")
        or message.startswith("⚠ IA:")
        or message.startswith("⚠ Gemini:")
        or message.startswith("⚠ Imagem:")
        or message.startswith("⚠ Divulgação:")
        or message.startswith("✓ Divulgação:")
        or message.startswith("⚠ Instagram:")
        or message.startswith("⚠ Não foi possível")
        or message.startswith("Erro ao consultar Blogger:")
        or message.startswith("Erro:")
    )
    if important:
        return _original_print(*args, **kwargs)

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
from datetime import datetime, date
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, urljoin, quote
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

print("RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS 12.42")

BLOGGER_BLOG_ID = os.environ["BLOGGER_BLOG_ID"]
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

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

X_ENABLED = os.getenv("X_ENABLED", "false").lower() in ("1", "true", "yes", "sim")
X_CLIENT_ID = os.getenv("X_CLIENT_ID", "").strip()
X_CLIENT_SECRET = os.getenv("X_CLIENT_SECRET", "").strip()
X_REFRESH_TOKEN = os.getenv("X_REFRESH_TOKEN", "").strip()
META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v24.0").strip() or "v24.0"

# ===== Geração de imagem por IA (Pollinations) =====
POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"
POLLINATIONS_ENABLED = os.getenv("POLLINATIONS_ENABLED", "true").lower() in ("1", "true", "yes", "sim")
IMAGE_WIDTH = int(os.getenv("IMAGE_WIDTH", "1200"))
IMAGE_HEIGHT = int(os.getenv("IMAGE_HEIGHT", "675"))

# ===== Logo para marca d'água =====
# Caminho do logo dentro do repositório (relativo à raiz do repo)
LOGO_PATH_IN_REPO = os.getenv("LOGO_PATH_IN_REPO", "bot/radio_luz_gospel_logo.png").strip()
LOGO_MARK_RATIO = float(os.getenv("LOGO_MARK_RATIO", "0.08"))   # 8% da largura
LOGO_OPACITY = float(os.getenv("LOGO_OPACITY", "0.85"))
LOGO_MARGIN = int(os.getenv("LOGO_MARGIN", "20"))

# Limites
MAX_POSTS_PER_RUN = 1
MAX_GEMINI_TEXT_CALLS_PER_RUN = 6
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_BASE_SECONDS = 4
MAX_LINKS_PER_SOURCE = 80

MAX_AGE_DAYS = 3650

MIN_SOURCE_CHARS = 700
MIN_SOURCE_PARAGRAPHS = 4
TIMEOUT = 25
IMAGE_TIMEOUT = 60

GEMINI_MODEL_TEXT = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")

GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip()
AI_PROVIDER_TIMEOUT = int(os.getenv("AI_PROVIDER_TIMEOUT", "90"))

# ===== Filtro musical =====
MUSIC_STRONG_TERMS = (
    "lancamento", "lancamento musical", "lancou", "lanca",
    "novo single", "nova musica", "musica nova", "single",
    "album", "ep", "videoclipe", "clipe", "cancao", "faixa",
    "projeto musical", "carreira musical", "gravacao musical",
    "show", "shows", "turne", "festival", "concerto",
    "apresentacao musical", "agenda de shows", "palco",
    "ingressos", "bilheteria", "ao vivo", "feat", "featuring",
    "playlist", "cover musical", "novo projeto musical",
    "cronograma de shows", "turnê", "turnê nacional",
)
MUSIC_SUPPORT_TERMS = (
    "cantor", "cantora", "artista", "banda", "dupla", "musico",
    "musica", "musical", "musicista", "gravadora", "compositor",
    "compositora", "composicao", "instrumental", "vocal", "voz",
    "repertorio", "hit", "producao musical", "produtor musical",
    "worship", "louvor",
)

def _music_norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", value.lower()).strip()

def is_music_related(article=None, generated=None, raw_text=""):
    article = article or {}
    generated = generated or {}
    parts = [
        article.get("title", ""),
        article.get("text", ""),
        generated.get("titulo", ""),
        generated.get("resumo", ""),
        generated.get("materia", ""),
        raw_text,
    ]
    combined = _music_norm(" ".join(str(x or "") for x in parts))
    title = _music_norm(article.get("title", "") or generated.get("titulo", ""))
    if not combined:
        return False

    if any(term in title for term in MUSIC_STRONG_TERMS):
        return True

    strong_hits = sum(1 for term in MUSIC_STRONG_TERMS if term in combined)
    support_hits = sum(1 for term in MUSIC_SUPPORT_TERMS if term in combined)

    if strong_hits >= 1 and support_hits >= 1:
        return True
    if strong_hits >= 2:
        return True
    return False

def is_music_article(article):
    return is_music_related(article=article)

# ===== Fontes (UAU Gospel removida) =====
SOURCES = [
    {
        "nome": "Fuxico Gospel",
        "url": "https://www.fuxicogospel.com.br/",
        "feeds": [
            "https://www.fuxicogospel.com.br/feed/",
            "https://www.fuxicogospel.com.br/feed",
        ],
        "music_page": False,
    },
    {
        "nome": "News Gospel",
        "url": "https://www.newsgospel.com.br/",
        "feeds": [
            "https://www.newsgospel.com.br/feed/",
            "https://www.newsgospel.com.br/feed",
            "https://newsgospel.com.br/feed/",
        ],
        "music_page": True,
    },
    {
        "nome": "Folha Gospel - Música",
        "url": "https://folhagospel.com/musica/",
        "feeds": [
            "https://folhagospel.com/feed/",
            "https://folhagospel.com/musica/feed/",
        ],
        "section_only": True,
        "music_page": True,
        "path_prefix": "",
    },
    {
        "nome": "Guiame - Música",
        "url": "https://guiame.com.br/musica",
        "feeds": [
            "https://guiame.com.br/rss.xml",
            "https://guiame.com.br/feed/",
        ],
        "section_only": True,
        "music_page": True,
        "path_prefix": "/musica",
    },
    {
        "nome": "Gospel Mais",
        "url": "https://gospelmais.com/",
        "feeds": [
            "https://gospelmais.com/feed/",
            "https://gospelmais.com/feed",
            "https://www.gospelmais.com/feed/",
        ],
        "music_page": True,
    },
    {
        "nome": "Exibir Gospel",
        "url": "https://exibirgospel.com.br/",
        "feeds": [
            "https://exibirgospel.com.br/feed/",
            "https://exibirgospel.com.br/feed",
        ],
        "music_page": True,
    },
    {
        "nome": "iGospel",
        "url": "https://www.igospel.org.br/",
        "feeds": [
            "https://www.igospel.org.br/feed/",
            "https://www.igospel.org.br/feed",
            "https://igospel.org.br/feed/",
        ],
        "music_page": True,
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

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; RadioLuzGospelBot/12.42)"})

gemini_calls = 0
gemini_quota_hit = False
_ai_config_logged = False
_image_logo_url_cache = None


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
    except Exception as e:
        print("Erro:", e)
        return None


def date_parse(v):
    if not v:
        return None
    value = str(v).strip()
    formats = (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
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
        'meta[name="date"]',
        'meta[name="publish_date"]',
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
    for sel in ("time.entry-date", "time.published", "time",
                ".entry-date", ".posted-on"):
        n = x.select_one(sel)
        if n:
            d = date_parse(n.get("datetime") or n.get_text(" ", strip=True))
            if d:
                return d
    return None


def image_original(x):
    values = []
    for sel in (
        'meta[property="og:image"]',
        'meta[name="twitter:image"]',
        'meta[itemprop="image"]',
    ):
        n = x.select_one(sel)
        if n and n.get("content"):
            values.append(n["content"])
    for sel in (
        "article img", ".entry-content img", ".post-content img",
        ".td-post-content img", "main img",
    ):
        for n in x.select(sel)[:10]:
            values.append(
                n.get("src") or n.get("data-src") or n.get("data-lazy-src") or ""
            )
    for u in values:
        u = u.strip()
        if u.startswith("//"):
            u = "https:" + u
        if u.startswith(("http://", "https://")) and not any(
            z in u.lower() for z in ("logo", "avatar", "icon", "favicon")
        ):
            return u
    return ""


def videos(x):
    out = []
    for n in x.find_all("iframe"):
        u = n.get("src", "").strip()
        if u.startswith("//"):
            u = "https:" + u
        if u.startswith(("http://", "https://")) and u not in out:
            out.append(u)
    return out[:5]


# ============================================================
# LOGO PARA MARCA D'ÁGUA
# ============================================================

def get_logo_public_url():
    """
    Retorna uma URL pública do logo hospedado no repositório do GitHub.
    Testa jsDelivr e raw.githubusercontent para ver qual responde.
    """
    global _image_logo_url_cache
    if _image_logo_url_cache is not None:
        return _image_logo_url_cache

    explicit = os.getenv("INSTAGRAM_LOGO_URL", "").strip()
    candidates = []
    if explicit:
        candidates.append(explicit)

    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    branch = os.getenv("GITHUB_REF_NAME", "").strip() or "main"
    if repository:
        repo_encoded = quote(repository, safe="/")
        branch_encoded = quote(branch, safe="")
        logo_encoded = quote(LOGO_PATH_IN_REPO, safe="/")
        candidates.append(
            f"https://cdn.jsdelivr.net/gh/{repo_encoded}@{branch_encoded}/{logo_encoded}"
        )
        candidates.append(
            f"https://raw.githubusercontent.com/{repo_encoded}/{branch_encoded}/{logo_encoded}"
        )

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            r = requests.get(
                candidate, stream=True, timeout=12,
                headers={"User-Agent": "RadioLuzGospel/12.42"},
            )
            status = r.status_code
            content_type = (r.headers.get("Content-Type") or "").lower()
            r.close()
            if status == 200 and content_type.startswith("image/"):
                print(f"✓ Logo público encontrado: {candidate}")
                _image_logo_url_cache = candidate
                return candidate
            print(f"⚠ Logo não acessível ({status}, {content_type}): {candidate}")
        except Exception as exc:
            print(f"⚠ Erro ao validar logo: {exc}")

    _image_logo_url_cache = ""
    return ""


# ============================================================
# GERAÇÃO DE IMAGEM POR IA (Pollinations)
# ============================================================

def _build_image_prompt(article, generated):
    """
    Constrói um prompt em inglês para a Pollinations, sempre dentro
    do universo gospel. Usa o prompt sugerido pelo Gemini se disponível.
    """
    base = (generated.get("prompt_imagem", "") or "").strip()
    if not base:
        # Fallback: usa título como referência
        base = article.get("title", "") or generated.get("titulo", "")

    # Garante que o estilo gospel esteja presente
    style_suffix = (
        "photorealistic, cinematic photography, warm golden lighting, "
        "christian gospel atmosphere, church setting, worship mood, "
        "professional news photography, shallow depth of field, "
        "high detail, 16:9 aspect ratio"
    )
    if "photorealistic" not in base.lower() and "photo" not in base.lower():
        prompt = f"{base}, {style_suffix}"
    else:
        prompt = base

    prompt = re.sub(r"\s+", " ", prompt).strip()[:800]
    return prompt


def generate_image_url(prompt):
    """
    Gera URL pública da Pollinations para o prompt dado.
    Retorna URL (string) ou "" se falhar.
    """
    if not POLLINATIONS_ENABLED or not prompt:
        return ""
    try:
        encoded = quote(prompt, safe="")
        seed = random.randint(1, 999999)
        url = (
            f"{POLLINATIONS_BASE}{encoded}"
            f"?width={IMAGE_WIDTH}&height={IMAGE_HEIGHT}"
            f"&seed={seed}&model=flux&nologo=true"
        )
        print(f"Imagem: solicitando geração (Pollinations)...")
        # Valida que a imagem existe e é PNG/JPEG
        r = requests.get(url, stream=True, timeout=IMAGE_TIMEOUT)
        status = r.status_code
        content_type = (r.headers.get("Content-Type") or "").lower()
        r.close()
        if status == 200 and content_type.startswith("image/"):
            print(f"✓ Imagem: gerada com sucesso.")
            return url
        print(f"⚠ Imagem: Pollinations HTTP {status} ({content_type})")
    except Exception as e:
        print(f"⚠ Imagem: erro na geração Pollinations: {e}")
    return ""


def apply_logo_watermark(image_url):
    """
    Aplica o logo pequeno no topo central via QuickChart Watermark.
    Se não houver logo público, devolve a imagem original sem marca.
    """
    if not image_url:
        return image_url
    logo_url = get_logo_public_url()
    if not logo_url:
        print("⚠ Imagem: logo público indisponível; mantendo imagem sem marca.")
        return image_url

    try:
        watermark_url = (
            "https://quickchart.io/watermark?"
            f"mainImageUrl={quote(image_url, safe='')}"
            f"&markImageUrl={quote(logo_url, safe='')}"
            f"&markRatio={LOGO_MARK_RATIO}"
            "&position=topMiddle"
            f"&opacity={LOGO_OPACITY}"
            f"&margin={LOGO_MARGIN}"
        )
        # Valida que o QuickChart gerou o PNG com marca
        r = requests.get(watermark_url, stream=True, timeout=IMAGE_TIMEOUT)
        status = r.status_code
        content_type = (r.headers.get("Content-Type") or "").lower()
        r.close()
        if status == 200 and content_type.split(";", 1)[0].strip() == "image/png":
            print("✓ Imagem: marca d'água aplicada com sucesso.")
            return watermark_url
        print(f"⚠ Imagem: QuickChart watermark HTTP {status} ({content_type})")
    except Exception as e:
        print(f"⚠ Imagem: erro ao aplicar marca d'água: {e}")
    return image_url


def build_final_image(article, generated):
    """
    Pipeline completo:
    1. Gera imagem por IA (Pollinations).
    2. Aplica marca d'água (QuickChart).
    3. Se falhar em qualquer etapa, retorna ("", "fallback") para o chamador
       decidir usar a imagem original.
    Retorna (url_final, origem).
    """
    prompt = _build_image_prompt(article, generated)
    ai_url = generate_image_url(prompt)
    if not ai_url:
        return "", ""
    final_url = apply_logo_watermark(ai_url)
    if final_url:
        return final_url, "Pollinations + QuickChart (logo)"
    return ai_url, "Pollinations (sem logo)"


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
        print("Data encontrada:", d)
        age = (datetime.now() - d).total_seconds() / 86400
        if age > MAX_AGE_DAYS:
            print(f"Notícia muito antiga ({age:.1f} dias). Pulando.")
            return None
    else:
        print("Data não identificada. Aceitando para análise.")

    img = image_original(x)
    if not img:
        print("Imagem original não encontrada. Pulando.")
        return None

    box = x.find("article") or x.find("main") or x
    paragraphs = []
    for p in box.find_all("p"):
        text = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
        if len(text) >= 35:
            paragraphs.append(text)
    text = "\n\n".join(paragraphs)

    if len(text) < MIN_SOURCE_CHARS or len(paragraphs) < MIN_SOURCE_PARAGRAPHS:
        print(f"Conteúdo insuficiente: {len(text)} caracteres; {len(paragraphs)} parágrafos")
        return None

    link_count = len(box.find_all("a"))
    if len(text) < 1000 and link_count > len(paragraphs) * 4:
        print("Página parece índice/listagem. Pulando.")
        return None

    vv = videos(x)
    print("Notícia encontrada:", title)
    print("Texto extraído:", len(text), "caracteres")

    return {
        "url": normalize_url(url),
        "title": title,
        "date": d,
        "image": img,
        "text": text[:16000],
        "videos": vv,
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
            u = n.get("href") or n.get_text(strip=True) or ""
            u = normalize_url(u)
            if not u or bad_url(u):
                continue
            if not host_matches(u):
                continue
            if u not in seen:
                seen.add(u)
                out.append(u)

    x = soup(source["url"])
    if x:
        for a in x.find_all("a", href=True):
            u = urljoin(source["url"], a["href"])
            u = normalize_url(u)
            if bad_url(u):
                continue
            if not host_matches(u):
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


def existing(api, show_log=True):
    blog_urls = set()
    source_urls = set()
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
                post_url = normalize_url(post.get("url", ""))
                if post_url:
                    blog_urls.add(post_url)
                content = post.get("content", "") or ""
                for match in re.findall(
                    r'href=["\'](https?://[^"\']+)["\']', content, flags=re.I
                ):
                    source_urls.add(normalize_url(match))
                for match in re.findall(
                    r'RADIO_LUZ_GOSPEL_SOURCE_URL:\s*(https?://[^\s]+?)\s*-->',
                    content, flags=re.I,
                ):
                    source_urls.add(normalize_url(match))
            token = data.get("nextPageToken")
            if not token:
                break
    except Exception as e:
        print("Erro ao consultar Blogger:", e)
    if show_log:
        print("Posts existentes no Blogger:", len(blog_urls))
        print("Fontes já registradas:", len(source_urls))
    return blog_urls, source_urls


def update_existing_music_labels(api):
    updated = 0
    removed = 0
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
                content = post.get("content", "") or ""
                post_id = post.get("id")
                if not post_id:
                    continue
                labels = list(post.get("labels", []) or [])
                visible_text = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
                should_music = is_music_related(
                    article={"title": post.get("title", ""), "text": visible_text},
                    raw_text=visible_text,
                )
                new_labels = labels[:]
                if should_music and "Músicas" not in new_labels:
                    new_labels.insert(1 if "Notícias" in new_labels else 0, "Músicas")
                elif not should_music and "Músicas" in new_labels:
                    new_labels = [x for x in new_labels if x != "Músicas"]
                if new_labels != labels:
                    api.posts().patch(
                        blogId=BLOGGER_BLOG_ID,
                        postId=post_id,
                        body={"labels": new_labels},
                    ).execute()
                    if should_music:
                        updated += 1
                        print(f"✓ /musicas: classificado por conteúdo — {post.get('title','')}")
                    else:
                        removed += 1
                        print(f"✓ /musicas: removido por não ser conteúdo musical — {post.get('title','')}")
            token = data.get("nextPageToken")
            if not token:
                break
    except Exception as e:
        print("⚠ Não foi possível concluir a atualização dos posts existentes:", e)
    print(f"Posts existentes adicionados a /musicas: {updated}")
    print(f"Posts não musicais retirados de /musicas: {removed}")


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
- Marque publicar=true quando houver QUALQUER elemento musical claro na
  matéria, mesmo que o foco principal seja agenda, cronograma de shows,
  turnê, divulgação de datas, anúncio de apresentações, festival, show
  beneficente, participação em evento musical, lançamento de single,
  álbum, EP, videoclipe, mudança de formação, entrevista com artista
  musical ou qualquer outro assunto diretamente ligado a música.
- Cronogramas de shows, turnês nacionais e divulgação de datas SÃO
  matérias musicais e devem ser publicadas (publicar=true).
- Marque publicar=false SOMENTE quando a matéria NÃO tiver nenhuma
  relação com música (ex.: política, economia, esporte, religião sem
  elemento musical, comportamento, tecnologia, saúde).
- Se a matéria citar uma banda, cantor, cantora, duo, grupo musical,
  festival, show, turnê, álbum, single, EP ou videoclipe, é música.
- Na dúvida entre publicar e não publicar, PREFIRA publicar=true.

OUTRAS REGRAS:
- título novo e jornalístico;
- resumo de 2 a 3 frases;
- não copiar frases ou parágrafos da fonte;
- não traduzir nem reproduzir a estrutura da matéria original;
- retornar SOMENTE JSON válido, sem Markdown;
- no campo "assunto_principal", informe o NOME DA PESSOA, BANDA OU GRUPO
  musical mais importante citado na matéria (ex.: "Banda Catedral",
  "Kim", "Renascer Praise"). Se não houver pessoa ou banda específica,
  deixe string vazia "".
- no campo "prompt_imagem", escreva em INGLÊS uma descrição de CENA para
  gerar uma FOTO realista que ilustre a matéria. A descrição deve:
  * descrever uma cena gospel (palco de igreja, culto, louvor, coral,
    show gospel, estúdio de gravação, microfone, instrumentos, multidão
    com mãos levantadas, iluminação quente, etc.);
  * NÃO citar nomes de pessoas reais (para evitar rostos falsos);
  * NÃO pedir rostos específicos de artistas;
  * usar termos como "photorealistic", "cinematic lighting",
    "professional photography", "shallow depth of field";
  * ter no máximo 60 palavras.

FORMATO:
{{"publicar":true,"titulo":"...","resumo":"...","materia":"...","assunto_principal":"...","prompt_imagem":"..."}}

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
                prompt_imagem = str(data.get("prompt_imagem", "")).strip()
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
                    "prompt_imagem": prompt_imagem,
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
    elif last_reason == "resposta inválida":
        print("⚠ IA: geração retornou formato inválido")
    else:
        print("⚠ IA: nenhum provedor disponível conseguiu gerar a matéria")
    return None


def html(article, generated, final_image="", image_origin=""):
    safe_title = (
        generated["titulo"]
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

    image_url = final_image or article["image"]
    safe_image = image_url.replace("&", "&amp;").replace('"', "&quot;")

    safe_source_url = (
        article["url"]
        .replace("&", "&amp;")
        .replace('"', "&quot;")
    )

    content = [
        f'<p><strong>{generated["resumo"]}</strong></p>',
        (
            f'<p><img src="{safe_image}" '
            f'alt="{safe_title}" '
            f'style="max-width:100%;height:auto;border-radius:12px;">'
            f'</p>'
        ),
    ]

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
        'loading="lazy"></iframe>'
        '<p style="text-align:center;margin-top:0.8rem;font-size:0.95rem;color:#666;font-family:Arial,sans-serif;">'
        'Ouça a seleção especial da <strong>Rádio Luz Gospel</strong> 📻🙏'
        '</p>'
        '</div>'
    )

    article_paragraphs = []
    for paragraph in re.split(r"\n+", generated["materia"]):
        paragraph = paragraph.strip()
        if paragraph:
            article_paragraphs.append(paragraph)

    for index, paragraph in enumerate(article_paragraphs):
        content.append(f"<p>{paragraph}</p>")
        if index == 1:
            content.append(spotify_block)

    telegram_channel = os.getenv(
        "TELEGRAM_CHANNEL_URL",
        "https://t.me/radioluzgospelnoticias",
    ).strip() or "https://t.me/radioluzgospelnoticias"

    safe_telegram_channel = (
        telegram_channel
        .replace("&", "&amp;")
        .replace('"', "&quot;")
    )

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
        '</a></p>'
        '</div>'
    )

    for video_url in article["videos"]:
        content.append(
            '<p><iframe '
            f'src="{video_url}" '
            'width="100%" height="315" '
            'frameborder="0" '
            'allowfullscreen '
            'loading="lazy"></iframe></p>'
        )

    source_marker = f"<!-- RADIO_LUZ_GOSPEL_SOURCE_URL: {safe_source_url} -->"
    image_marker = ""
    if image_origin:
        image_marker = f"\n<!-- RADIO_LUZ_GOSPEL_IMAGE_SOURCE: {image_origin} -->"

    return "\n".join(content) + "\n" + source_marker + image_marker


def main():
    print("Fontes: Fuxico + News Gospel + Folha Gospel Música + Guiame Música + Gospel Mais + Exibir Gospel + iGospel | /musicas por conteúdo")
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    api = blogger()
    old_blog_urls, old_source_urls = existing(api)

    update_existing_music_labels(api)

    candidates = []
    candidate_urls = set()
    source_counts = {}

    for source in SOURCES:
        source_links = links(source)
        source_counts[source["nome"]] = len(source_links)
        for url in source_links:
            normalized = normalize_url(url)
            if normalized in candidate_urls or normalized in old_blog_urls or normalized in old_source_urls:
                continue
            article = get_article(normalized)
            if article:
                if not is_music_related(article=article):
                    continue
                candidate_urls.add(normalized)
                candidates.append(article)

    source_summary = " | ".join(f"{name}: {count}" for name, count in source_counts.items())
    print(f"Fontes encontradas: {source_summary}")

    candidates.sort(key=lambda a: a["date"] or datetime.min, reverse=True)
    print(f"Novas matérias musicais: {len(candidates)}")

    published = 0
    failed = 0
    ignored = 0

    while candidates and published < MAX_POSTS_PER_RUN:
        article = candidates.pop(0)
        normalized = normalize_url(article["url"])
        if normalized in old_source_urls:
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

        # ===== Geração de imagem por IA + marca d'água =====
        final_image, image_origin = build_final_image(article, generated)

        if not final_image:
            # Fallback: imagem original da fonte
            print("⚠ Imagem: IA falhou; usando imagem original da fonte como fallback.")
            final_image = article["image"]
            image_origin = "Fallback: imagem original da fonte"

        print(f"✓ Imagem final: {image_origin}")

        try:
            post_labels = ["Notícias", "Rádio Luz Gospel"]
            if is_music_related(article=article, generated=generated):
                post_labels.insert(1, "Músicas")

            response = api.posts().insert(
                blogId=BLOGGER_BLOG_ID,
                body={
                    "title": generated["titulo"].strip(),
                    "content": html(article, generated, final_image=final_image, image_origin=image_origin),
                    "labels": post_labels,
                },
                isDraft=False,
            ).execute()
            published += 1
            old_source_urls.add(normalized)
            if response.get("url"):
                old_blog_urls.add(normalize_url(response["url"]))
            print(f"✓ Publicada: {generated['titulo'].strip()}")
        except Exception:
            failed += 1
            print("⚠ Blogger: falha ao publicar")

    print("RESULTADO")
    print(f"Publicações: {published}")
    print(f"Ignoradas: {ignored}")
    print(f"Falhas: {failed}")


# ============================================================
# DIVULGAÇÃO SOCIAL
# ============================================================
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

def promotion_url(post_url):
    if not post_url:
        return ""
    try:
        parts = urlsplit(post_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update({
            "utm_source": PROMO_UTM_SOURCE,
            "utm_medium": PROMO_UTM_MEDIUM,
            "utm_campaign": PROMO_UTM_CAMPAIGN,
        })
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    except Exception:
        return post_url


def social_image_url(post):
    content = post.get("content", "") or ""
    m = re.search(r"<img[^>]+src=[\"'](https?://[^\"']+)[\"']", content, flags=re.I)
    if m:
        return m.group(1)
    return ""


def facebook_promote(post, source_name_text):
    if not FACEBOOK_ENABLED:
        return False
    if not FACEBOOK_PAGE_ID or not FACEBOOK_PAGE_ACCESS_TOKEN:
        print("⚠ Divulgação: Facebook não configurado.")
        return False
    url = promotion_url(post.get("url", ""))
    if not url:
        return False
    text = (
        "📰 RÁDIO LUZ GOSPEL\n\n"
        f"{post.get('title', '').strip()}\n\n"
        "🎵 Confira a matéria completa no site:\n"
        f"👉 {url}"
    )
    endpoint = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/{FACEBOOK_PAGE_ID}/feed"
    try:
        r = requests.post(endpoint, data={
            "message": text[:60000],
            "link": url,
            "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
        }, timeout=TIMEOUT)
        if r.ok:
            print("✓ Divulgação: publicada no Facebook")
            return True
        print(f"⚠ Divulgação: Facebook HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print("⚠ Divulgação: erro no Facebook:", e)
    return False


def _instagram_wrap_text(text, max_chars=31, max_lines=4):
    words = re.sub(r"\s+", " ", str(text or "").strip()).split()
    lines = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                lines.append(current)
                current = ""
            chunks = [word[i:i + max_chars] for i in range(0, len(word), max_chars)]
            lines.extend(chunks[:-1])
            current = chunks[-1]
            continue
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:max_lines]


def _instagram_fit_text(text, max_chars=31, max_lines=4):
    for chars, size in (
        (31, 32), (29, 30), (27, 28), (25, 26), (23, 24), (21, 22),
    ):
        lines = _instagram_wrap_text(text, max_chars=chars, max_lines=max_lines)
        if len(lines) <= max_lines:
            return lines, size
    lines = _instagram_wrap_text(text, max_chars=21, max_lines=max_lines)
    if len(lines) > max_lines:
        lines = _instagram_wrap_text(text, max_chars=18, max_lines=max_lines)
    return lines, 20


def _quickchart_social_overlay(title, excerpt, width=1080, height=1350, background_image_url=""):
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    lines, font_size = _instagram_fit_text(title, max_chars=31, max_lines=4)

    normalized_image_url = ""
    if background_image_url:
        normalized_image_url = (
            "https://wsrv.nl/?"
            f"url={quote(background_image_url, safe='')}"
            "&w=1080&h=1350&fit=contain&cbg=111111"
            "&output=jpg&q=90"
        )

    config = {
        "type": "scatter",
        "data": {
            "datasets": [{
                "data": [{"x": 0, "y": 0}],
                "pointRadius": 0,
                "pointHitRadius": 0,
                "showLine": False,
                "backgroundColor": "rgba(0,0,0,0)",
                "borderWidth": 0,
            }],
        },
        "options": {
            "responsive": False,
            "maintainAspectRatio": False,
            "animation": False,
            "layout": {"padding": 0},
            "plugins": {
                "legend": {"display": False},
                "tooltip": {"enabled": False},
                "annotation": {
                    "annotations": {
                        "headline_box": {
                            "type": "box",
                            "xMin": -0.84, "xMax": 0.84,
                            "yMin": -0.89, "yMax": -0.60,
                            "backgroundColor": "rgba(245, 190, 0, 0.82)",
                            "borderColor": "rgba(0, 105, 230, 0.95)",
                            "borderWidth": 3,
                            "borderRadius": 28,
                            "drawTime": "afterDatasetsDraw",
                            "z": 10,
                        },
                        "headline": {
                            "type": "label",
                            "xValue": 0, "yValue": -0.745,
                            "content": lines,
                            "color": "#FFFFFF",
                            "backgroundColor": "rgba(0,0,0,0)",
                            "borderWidth": 0,
                            "font": {"size": font_size, "weight": "bold"},
                            "position": "center",
                            "textAlign": "center",
                            "padding": {"top": 10, "bottom": 10, "left": 26, "right": 26},
                            "drawTime": "afterDatasetsDraw",
                            "z": 20,
                            "callout": {"display": False},
                        },
                    }
                },
            },
            "scales": {
                "x": {"display": False, "min": -1, "max": 1},
                "y": {"display": False, "min": -1, "max": 1},
            },
        },
    }

    if normalized_image_url:
        config["options"]["plugins"]["backgroundImageUrl"] = normalized_image_url

    try:
        encoded = quote(json.dumps(config, ensure_ascii=False, separators=(",", ":")))
        return (
            f"https://quickchart.io/chart?"
            f"width={width}&height={height}"
            f"&devicePixelRatio=1&version=4"
            f"&format=png&c={encoded}"
        )
    except Exception as exc:
        print(f"⚠ QuickChart: erro ao montar arte: {exc}")
        return ""


def instagram_art_url(post):
    image_url = social_image_url(post)
    if not image_url:
        print("⚠ Instagram: matéria sem imagem original; arte não pode ser criada.")
        return ""

    title = str(post.get("title", "")).strip()
    chart_url = _quickchart_social_overlay(
        title, "", width=1080, height=1350, background_image_url=image_url,
    )
    if not chart_url:
        return ""

    for attempt in range(2):
        try:
            warm = requests.get(chart_url, stream=True, timeout=30)
            warm_status = warm.status_code
            warm_type = (warm.headers.get("Content-Type") or "").lower()
            warm_error = warm.headers.get("X-quickchart-error", "")
            warm.close()
            if warm_status == 200 and warm_type.split(";", 1)[0].strip() == "image/png":
                print("✓ Instagram: arte criada sem logo")
                return chart_url
            print(f"⚠ Instagram: arte do QuickChart inválida ({warm_status}, {warm_type}). {warm_error[:300]}")
            return ""
        except Exception as exc:
            if attempt == 1:
                print(f"⚠ Instagram: erro ao validar arte: {exc}")
                return ""
            time.sleep(1)
    return ""


def instagram_promote(post, source_name_text):
    if not INSTAGRAM_ENABLED:
        return False
    if not INSTAGRAM_USER_ID or not INSTAGRAM_ACCESS_TOKEN:
        print("⚠ Divulgação: Instagram não configurado.")
        return False
    original_image_url = social_image_url(post)
    image_url = instagram_art_url(post)
    url = promotion_url(post.get("url", ""))
    if not original_image_url or not image_url or not url:
        print("⚠ Instagram: arte obrigatória não disponível; publicação cancelada para preservar a regra visual.")
        return False
    caption = (
        "📰 RÁDIO LUZ GOSPEL\n\n"
        f"{post.get('title', '').strip()}\n\n"
        "🔗 Leia a matéria completa:\n"
        f"{url}\n\n"
        "#RadioLuzGospel #Gospel #NoticiasGospel #MusicaGospel"
    )

    base = f"https://graph.instagram.com/{META_GRAPH_API_VERSION}/me"
    try:
        try:
            check = requests.get(image_url, stream=True, timeout=25)
            content_type = (check.headers.get("Content-Type") or "").lower()
            status_code = check.status_code
            quickchart_error = check.headers.get("X-quickchart-error", "")
            check.close()
            if status_code != 200 or content_type.split(";", 1)[0].strip() != "image/png":
                print(f"⚠ Divulgação: arte automática inválida ({status_code}, {content_type}); esperado image/png. {quickchart_error[:400]}")
                return False
        except Exception as art_error:
            print(f"⚠ Divulgação: não foi possível validar a arte automática: {art_error}")
            return False

        create = requests.post(
            f"{base}/media",
            data={
                "image_url": image_url,
                "caption": caption[:2200],
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
            timeout=TIMEOUT,
        )
        if not create.ok:
            print(f"⚠ Divulgação: Instagram criação HTTP {create.status_code}: {create.text[:300]}")
            return False
        creation_id = create.json().get("id")
        if not creation_id:
            print("⚠ Divulgação: Instagram não retornou o ID da publicação.")
            return False

        ready = False
        for attempt in range(1, 7):
            time.sleep(5)
            status = requests.get(
                f"{base.rsplit('/me', 1)[0]}/{creation_id}",
                params={"fields": "status_code,status", "access_token": INSTAGRAM_ACCESS_TOKEN},
                timeout=TIMEOUT,
            )
            if not status.ok:
                print(f"⚠ Divulgação: Instagram status HTTP {status.status_code}: {status.text[:300]}")
                return False
            status_code = status.json().get("status_code", "")
            if status_code == "FINISHED":
                ready = True
                break
            if status_code in ("ERROR", "EXPIRED"):
                print(f"⚠ Divulgação: container do Instagram ficou com status {status_code}.")
                return False
            print(f"   Instagram: aguardando processamento do container ({attempt}/6)...")

        if not ready:
            print("⚠ Divulgação: Instagram não deixou o container pronto a tempo.")
            return False

        publish = requests.post(
            f"{base}/media_publish",
            data={"creation_id": creation_id, "access_token": INSTAGRAM_ACCESS_TOKEN},
            timeout=TIMEOUT,
        )
        if publish.ok:
            print("✓ Divulgação: publicada no Instagram com a arte obrigatória")
            return True
        print(f"⚠ Divulgação: Instagram publicação HTTP {publish.status_code}: {publish.text[:300]}")
    except Exception as e:
        print("⚠ Divulgação: erro no Instagram:", e)
    return False


def telegram_promote(post, source_name_text):
    if not PROMO_ENABLED:
        print("Divulgação: desativada (PROMO_ENABLED=false)")
        return False
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Divulgação: Telegram não configurado.")
        return False
    url = promotion_url(post.get("url", ""))
    if not url:
        return False
    text = (
        "📰 RÁDIO LUZ GOSPEL\n\n"
        f"{post.get('title', '').strip()}\n\n"
        "🎵 Confira a matéria completa:\n"
        f"👉 {url}"
    )
    endpoint = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(endpoint, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:3900],
            "disable_web_page_preview": False,
        }, timeout=TIMEOUT)
        if r.status_code == 200:
            print("✓ Divulgação: enviada ao Telegram para leitores inscritos")
            return True
        print(f"⚠ Divulgação: Telegram HTTP {r.status_code}")
    except Exception as e:
        print("⚠ Divulgação: erro no Telegram:", e)
    return False


def x_promote(post, source_name_text):
    print("▶ X: iniciando publicação...")
    if not X_ENABLED:
        print("⚠ Divulgação: X desativado (X_ENABLED=false)")
        return False
    if not X_CLIENT_ID or not X_CLIENT_SECRET or not X_REFRESH_TOKEN:
        print("⚠ Divulgação: X não configurado. Verifique X_CLIENT_ID, X_CLIENT_SECRET e X_REFRESH_TOKEN.")
        return False
    url = promotion_url(post.get("url", ""))
    if not url:
        print("⚠ Divulgação: X não recebeu uma URL válida para a matéria.")
        return False

    title = re.sub(r"\s+", " ", str(post.get("title", "") or "")).strip()
    prefix = "📰 "
    middle = "\n\n🎵 Leia a matéria completa na Rádio Luz Gospel:\n"
    suffix = "\n\n#RadioLuzGospel #NoticiasGospel"
    max_text_len = 280
    available_title = max_text_len - len(prefix) - len(middle) - len(url) - len(suffix)
    if available_title < 1:
        print("⚠ Divulgação: X não conseguiu montar o texto dentro do limite.")
        return False
    if len(title) > available_title:
        title = title[:max(1, available_title - 1)].rstrip() + "…"
    text = f"{prefix}{title}{middle}{url}{suffix}"

    try:
        token_response = requests.post(
            "https://api.x.com/2/oauth2/token",
            data={"refresh_token": X_REFRESH_TOKEN, "grant_type": "refresh_token"},
            auth=(X_CLIENT_ID, X_CLIENT_SECRET),
            timeout=TIMEOUT,
        )
        if not token_response.ok:
            print(f"⚠ Divulgação: falha ao renovar token X HTTP {token_response.status_code}: {token_response.text[:500]}")
            return False
        access_token = token_response.json().get("access_token", "")
        if not access_token:
            print("⚠ Divulgação: X não retornou access_token.")
            return False

        r = requests.post(
            "https://api.x.com/2/tweets",
            json={"text": text},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=TIMEOUT,
        )
        if r.ok:
            tweet_id = ""
            try:
                tweet_id = str(r.json().get("data", {}).get("id", "") or "")
            except Exception:
                pass
            if tweet_id:
                print(f"✓ Divulgação: publicada no X (ID {tweet_id})")
            else:
                print("✓ Divulgação: publicada no X")
            return True
        print(f"⚠ Divulgação: X HTTP {r.status_code}: {r.text[:500]}")
    except Exception as e:
        print("⚠ Divulgação: erro no X:", repr(e))
    return False


def source_name(url):
    host = urlparse(url or "").netloc.lower()
    mapping = (
        ("fuxicogospel.com.br", "Fuxico Gospel"),
        ("newsgospel.com.br", "News Gospel"),
        ("folhagospel.com", "Folha Gospel - Música"),
        ("guiame.com.br", "Guiame - Música"),
        ("gospelmais.com", "Gospel Mais"),
        ("exibirgospel.com.br", "Exibir Gospel"),
        ("igospel.org.br", "iGospel"),
    )
    for host_part, name in mapping:
        if host_part in host:
            return name
    return host.replace("www.", "") or "Rádio Luz Gospel"


def promote_new_posts(before_urls):
    if not PROMO_ENABLED:
        return
    try:
        api_after = blogger()
        after_urls, _ = existing(api_after, show_log=False)
        new_urls = list(after_urls - before_urls)
        if not new_urls:
            print("Divulgação: nenhuma publicação nova nesta execução.")
            return
        posts = api_after.posts().list(
            blogId=BLOGGER_BLOG_ID,
            maxResults=500,
            fetchBodies=True,
        ).execute().get("items", [])
        post_url = new_urls[0]
        post = next(
            (p for p in posts if normalize_url(p.get("url", "")) == normalize_url(post_url)),
            None,
        )
        if not post:
            print("Divulgação: publicação recém-criada não localizada.")
            return
        content = post.get("content", "") or ""
        m = re.search(r"RADIO_LUZ_GOSPEL_SOURCE_URL:\s*(https?://[^\s]+?)\s*-->", content, flags=re.I)
        source_text = source_name(m.group(1)) if m else "Rádio Luz Gospel"
        telegram_promote(post, source_text)
        facebook_promote(post, source_text)
        instagram_promote(post, source_text)
        x_promote(post, source_text)
    except Exception as exc:
        print("⚠ Divulgação: erro na etapa pós-publicação:", exc)


print("VERSÃO 12.42 ATIVA: imagem gerada por IA (Pollinations) + marca d'água (QuickChart) | fallback para imagem original | UAU Gospel removida | prompt IA menos restritivo | Spotify após 2º parágrafo | sem Fonte/link no final")

_before_urls = set()
if PROMO_ENABLED:
    try:
        _before_urls, _ = existing(blogger(), show_log=False)
    except Exception as exc:
        print("⚠ Divulgação: não foi possível capturar o estado anterior do Blogger:", exc)

main()

if PROMO_ENABLED:
    promote_new_posts(_before_urls)
