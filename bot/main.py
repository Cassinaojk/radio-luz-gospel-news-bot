import os, re, json, requests, time, random, io, contextlib, unicodedata
from bs4 import BeautifulSoup
from datetime import datetime, date
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, urljoin
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

print("RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS 9.3")

BLOGGER_BLOG_ID = os.environ["BLOGGER_BLOG_ID"]
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# Divulgação para leitores reais (opcional).
# Não gera visitas artificiais nem abre páginas automaticamente.
PROMO_ENABLED = os.getenv("PROMO_ENABLED", "false").lower() in ("1", "true", "yes", "sim")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
PROMO_UTM_SOURCE = os.getenv("PROMO_UTM_SOURCE", "telegram").strip() or "telegram"
PROMO_UTM_MEDIUM = os.getenv("PROMO_UTM_MEDIUM", "social").strip() or "social"
PROMO_UTM_CAMPAIGN = os.getenv("PROMO_UTM_CAMPAIGN", "noticias").strip() or "noticias"

# Divulgação opcional para Facebook e Instagram via Meta Graph API.
FACEBOOK_ENABLED = os.getenv("FACEBOOK_ENABLED", "false").lower() in ("1", "true", "yes", "sim")
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "").strip()
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
INSTAGRAM_ENABLED = os.getenv("INSTAGRAM_ENABLED", "false").lower() in ("1", "true", "yes", "sim")
INSTAGRAM_USER_ID = os.getenv("INSTAGRAM_USER_ID", "").strip()
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v24.0").strip() or "v24.0"

# Limites
MAX_POSTS_PER_RUN = 1
MAX_GEMINI_TEXT_CALLS_PER_RUN = 6
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_BASE_SECONDS = 4
MAX_LINKS_PER_SOURCE = 80

# 3650 dias (~10 anos): a duplicidade passa a ser controlada
# principalmente pela URL da fonte, não por uma janela curta de idade.
MAX_AGE_DAYS = 3650

MIN_SOURCE_CHARS = 700
MIN_SOURCE_PARAGRAPHS = 4
TIMEOUT = 25

GEMINI_MODEL_TEXT = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")

# Filtro editorial: somente notícias relacionadas a música.
# É aplicado antes do Gemini para impedir que notícias políticas, jurídicas,
# religiosas ou de outros assuntos consumam a cota do modelo.
MUSIC_STRONG_TERMS = (
    "cantor", "cantora", "artista", "banda", "dupla", "musico", "musica",
    "album", "single", "ep", "videoclipe", "clipe", "cancao", "faixa",
    "gravadora", "compositor", "compositora", "lancamento musical",
    "lanca single", "lanca album", "lanca musica", "novo single",
    "novo album", "nova musica", "projeto musical", "carreira musical",
    "show", "turne", "festival", "concerto", "worship", "louvor",
    "playlist", "feat", "featuring", "cover musical", "grava seu novo",
)
MUSIC_GENERIC_TERMS = (
    "musical", "musicista", "gravacao", "composicao", "composicoes",
    "instrumental", "vocal", "voz", "palco", "repertorio", "hit",
    "estreia musical", "producao musical", "produtor musical",
)

def _music_norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", value.lower()).strip()

def is_music_article(article):
    """Retorna True somente para conteúdo claramente ligado à música."""
    title = _music_norm(article.get("title", ""))
    text = _music_norm(article.get("text", ""))[:9000]

    # Título claramente musical: aceita imediatamente.
    if any(term in title for term in MUSIC_STRONG_TERMS):
        return True

    combined = title + " " + text
    strong_hits = sum(1 for term in MUSIC_STRONG_TERMS if term in combined)
    generic_hits = sum(1 for term in MUSIC_GENERIC_TERMS if term in combined)

    # No corpo, exige sinais suficientes para evitar falsos positivos.
    return strong_hits >= 2 or (strong_hits >= 1 and generic_hits >= 1)

SOURCES = [
    {
        "nome": "News Gospel",
        "url": "https://www.newsgospel.com.br/",
        "feeds": ["https://www.newsgospel.com.br/feed/"],
    },
    {
        "nome": "UAU Gospel",
        "url": "https://www.uaugospel.com.br/",
        "feeds": ["https://www.uaugospel.com.br/feed/"],
    },
]

# Páginas que nunca devem ser tratadas como matérias.
BAD_PATHS = (
    "/category/",
    "/tag/",
    "/author/",
    "/page/",
    "/search/",
    "/feed/",
    "/wp-json/",
    "/comments/",
    "/sobre",
    "/contato",
    "/contact",
    "/politica",
    "/privacidade",
    "/privacy",
    "/anuncie",
    "/publicidade",
    "/advertising",
    "/login",
    "/cadastro",
    "/register",
    "/sitemap",
    "/robots.txt",
)

SHARE_DOMAINS = (
    "pinterest.",
    "reddit.com/submit",
    "facebook.com/sharer",
    "twitter.com/intent",
    "x.com/intent",
    "whatsapp.com/",
    "t.me/share",
    "linkedin.com/share",
)

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; RadioLuzGospelBot/9.0)"
})

gemini_calls = 0
gemini_quota_hit = False


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

    # Evita arquivos que claramente não são páginas de notícia.
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

                # Article/NewsArticle pode estar dentro de @graph.
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

    for sel in (
        "time.entry-date",
        "time.published",
        "time",
        ".entry-date",
        ".posted-on",
    ):
        n = x.select_one(sel)
        if n:
            d = date_parse(
                n.get("datetime") or n.get_text(" ", strip=True)
            )
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
        "article img",
        ".entry-content img",
        ".post-content img",
        ".td-post-content img",
        "main img",
    ):
        for n in x.select(sel)[:10]:
            values.append(
                n.get("src")
                or n.get("data-src")
                or n.get("data-lazy-src")
                or ""
            )

    for u in values:
        u = u.strip()

        if u.startswith("//"):
            u = "https:" + u

        if (
            u.startswith(("http://", "https://"))
            and not any(
                z in u.lower()
                for z in ("logo", "avatar", "icon", "favicon")
            )
        ):
            return u

    return ""


def videos(x):
    out = []

    for n in x.find_all("iframe"):
        u = n.get("src", "").strip()

        if u.startswith("//"):
            u = "https:" + u

        if (
            u.startswith(("http://", "https://"))
            and u not in out
        ):
            out.append(u)

    return out[:5]


def get_article(url):
    x = soup(url)

    if not x:
        return None

    n = x.find("h1") or x.find("title")
    title = re.sub(
        r"\s+",
        " ",
        n.get_text(" ", strip=True) if n else "",
    ).strip()

    if not title:
        return None

    title_lower = title.lower()

    index_titles = {
        "lançamentos",
        "notícias",
        "noticias",
        "home",
        "início",
        "inicio",
        "últimas notícias",
        "ultimas noticias",
        "404",
        "página não encontrada",
        "pagina nao encontrada",
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
        text = re.sub(
            r"\s+",
            " ",
            p.get_text(" ", strip=True),
        )

        if len(text) >= 35:
            paragraphs.append(text)

    text = "\n\n".join(paragraphs)

    if (
        len(text) < MIN_SOURCE_CHARS
        or len(paragraphs) < MIN_SOURCE_PARAGRAPHS
    ):
        print(
            "Conteúdo insuficiente:",
            len(text),
            "caracteres;",
            len(paragraphs),
            "parágrafos",
        )
        return None

    # Evita páginas que são basicamente listas de links.
    link_count = len(box.find_all("a"))
    if len(text) < 1000 and link_count > len(paragraphs) * 4:
        print("Página parece índice/listagem. Pulando.")
        return None

    vv = videos(x)

    print("Notícia encontrada:", title)
    print("Texto extraído:", len(text), "caracteres")
    print("Imagem encontrada:", img)
    print("Vídeos encontrados:", len(vv))

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

    # Primeiro tenta RSS/Atom, que é a melhor fonte de links.
    for feed in source["feeds"]:
        x = soup(feed, True)

        if not x:
            continue

        for item in x.find_all(["item", "entry"]):
            n = item.find("link")

            if not n:
                continue

            u = (
                n.get("href")
                or n.get_text(strip=True)
                or ""
            )

            u = normalize_url(u)

            if not u or bad_url(u):
                continue

            host = urlparse(u).netloc.lower()

            if host != source_host and not host.endswith("." + source_host):
                continue

            if u not in seen:
                seen.add(u)
                out.append(u)

    # Depois usa a página inicial como complemento.
    x = soup(source["url"])

    if x:
        for a in x.find_all("a", href=True):
            u = urljoin(source["url"], a["href"])
            u = normalize_url(u)

            if bad_url(u):
                continue

            host = urlparse(u).netloc.lower()

            if host != source_host and not host.endswith("." + source_host):
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

    return build(
        "blogger",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def existing(api):
    """
    Retorna:
      - blog_urls: URLs dos posts do próprio Blogger
      - source_urls: URLs das fontes já publicadas

    Isso corrige um problema importante da versão anterior:
    a URL da fonte nunca é igual à URL criada pelo Blogger.
    """

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

                # Posts antigos: procura a URL da fonte em href.
                for match in re.findall(
                    r'href=["\'](https?://[^"\']+)["\']',
                    content,
                    flags=re.I,
                ):
                    source_urls.add(normalize_url(match))

                # Rádio Luz Gospel 9.0: a URL da fonte fica somente em comentário HTML invisível.
                for match in re.findall(
                    r'RADIO_LUZ_GOSPEL_SOURCE_URL:\s*(https?://[^\s]+?)\s*-->',
                    content,
                    flags=re.I,
                ):
                    source_urls.add(normalize_url(match))

            token = data.get("nextPageToken")

            if not token:
                break

    except Exception as e:
        print("Erro ao consultar Blogger:", e)

    print("Posts existentes no Blogger:", len(blog_urls))
    print("Fontes já registradas:", len(source_urls))

    return blog_urls, source_urls


def update_existing_music_labels(api):
    """
    Atualiza posts já existentes no Blogger:
    - fontes News Gospel, UAU Gospel, Folha Gospel e Guiame -> adiciona "Músicas"
    - Fuxico Gospel -> remove "Músicas", se por acaso existir.
    Assim, /musicas fica correto para o acervo antigo e para o futuro.
    """
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

                source_match = re.search(
                    r'RADIO_LUZ_GOSPEL_SOURCE_URL:\s*(https?://[^\s]+?)\s*-->',
                    content,
                    flags=re.I,
                )
                source_url = normalize_url(source_match.group(1)) if source_match else ""

                # Sem marcador da fonte, não altera o post.
                if not source_url:
                    continue

                labels = list(post.get("labels", []) or [])
                is_fuxico = "fuxicogospel.com.br" in urlparse(source_url).netloc.lower()
                should_music = (not is_fuxico) and source_is_music_page(source_url)

                new_labels = labels[:]
                if should_music and "Músicas" not in new_labels:
                    new_labels.insert(1 if "Notícias" in new_labels else 0, "Músicas")
                elif is_fuxico and "Músicas" in new_labels:
                    new_labels = [x for x in new_labels if x != "Músicas"]

                if new_labels != labels:
                    api.posts().patch(
                        blogId=BLOGGER_BLOG_ID,
                        postId=post_id,
                        body={"labels": new_labels},
                    ).execute()

                    if should_music:
                        updated += 1
                        print(f"✓ /musicas: atualizado post existente — {post.get('title','')}")
                    elif is_fuxico:
                        removed += 1
                        print(f"✓ Fuxico removido de /musicas — {post.get('title','')}")

            token = data.get("nextPageToken")
            if not token:
                break

    except Exception as e:
        print("⚠ Não foi possível concluir a atualização dos posts existentes:", e)

    print(f"Posts existentes adicionados a /musicas: {updated}")
    print(f"Posts do Fuxico retirados de /musicas: {removed}")


def is_transient_gemini_error(exc):
    msg = str(exc).upper()

    return any(
        code in msg
        for code in (
            "503",
            "UNAVAILABLE",
            "429",
            "RESOURCE_EXHAUSTED",
            "500",
            "502",
            "504",
            "TIMEOUT",
        )
    )


def gemini_request(client, model, prompt):
    last_error = None

    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        try:
            # Suprime o aviso extenso de AFC emitido pela biblioteca.
            with contextlib.redirect_stderr(io.StringIO()):
                return client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
        except Exception as e:
            last_error = e
            msg = str(e).upper()
            # 429/quota não deve repetir o mesmo modelo.
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                raise
            if not is_transient_gemini_error(e) or attempt >= GEMINI_MAX_RETRIES:
                raise
            delay = GEMINI_RETRY_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 2)
            time.sleep(delay)

    raise last_error


def gemini(article, client):
    global gemini_calls

    if gemini_calls >= MAX_GEMINI_TEXT_CALLS_PER_RUN:
        return None

    prompt = f"""
Você é o editor do Rádio Luz Gospel.

Escreva uma matéria jornalística ORIGINAL em português do Brasil
usando SOMENTE os fatos presentes no texto-fonte.

REGRAS:
- publicar=true somente se a matéria for claramente sobre música, artistas, cantores, bandas, lançamentos, álbuns, singles, videoclipes, shows, turnês, worship, louvor ou outro assunto musical;
- se o assunto principal não for música, use publicar=false;
- criar um título novo, claro e jornalístico;
- criar um resumo de 2 a 3 frases;
- criar matéria com aproximadamente 700 a 1200 palavras;
- não inventar nomes, datas, números, locais, declarações ou acontecimentos;
- não acrescentar fatos que não estejam no texto-fonte;
- não dizer que foi escrita por IA;
- não copiar frases longas do texto-fonte;
- manter tom jornalístico, claro e adequado ao público gospel;
- retornar SOMENTE JSON válido, sem Markdown e sem explicações.

FORMATO EXATO:
{{"publicar":true,"titulo":"Título","resumo":"Resumo","materia":"Matéria completa em parágrafos"}}

Se o texto realmente não tiver informação suficiente para uma matéria,
use publicar=false.

TÍTULO FONTE:
{article["title"]}

URL:
{article["url"]}

TEXTO-FONTE:
{article["text"]}
"""

    models_to_try = [GEMINI_MODEL_TEXT]

    if (
        GEMINI_FALLBACK_MODEL
        and GEMINI_FALLBACK_MODEL not in models_to_try
    ):
        models_to_try.append(GEMINI_FALLBACK_MODEL)

    for model_index, model in enumerate(models_to_try):
        try:
            response = gemini_request(
                client,
                model,
                prompt,
            )

            gemini_calls += 1

            raw = (
                getattr(response, "text", None)
                or ""
            ).strip()

            if not raw:
                raise ValueError(
                    "Gemini retornou resposta vazia."
                )

            raw = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                raw,
            ).strip()

            data = json.loads(raw)

            if data.get("publicar") is False:
                print(
                    "Gemini marcou como não publicável."
                )
                return None

            titulo = str(
                data.get("titulo", "")
            ).strip()

            resumo = str(
                data.get("resumo", "")
            ).strip()

            materia = str(
                data.get("materia", "")
            ).strip()

            if (
                not titulo
                or not resumo
                or len(materia) < 700
            ):
                print(
                    "Resposta do Gemini inválida ou curta demais."
                )

                if (
                    model_index + 1
                    < len(models_to_try)
                ):
                    print(
                        "Tentando modelo alternativo..."
                    )
                    continue

                return None

            print(
                f"Matéria gerada com sucesso usando {model}."
            )

            return {
                "titulo": titulo,
                "resumo": resumo,
                "materia": materia,
            }

        except Exception as e:
            print(
                f"Erro Gemini ({model}): {e}"
            )

            if (
                model_index + 1
                < len(models_to_try)
                and is_transient_gemini_error(e)
            ):
                print(
                    "Tentando modelo alternativo:",
                    models_to_try[model_index + 1],
                )
                continue

            return None

    return None


def html(article, generated):
    safe_title = (
        generated["titulo"]
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

    safe_image = (
        article["image"]
        .replace("&", "&amp;")
        .replace('"', "&quot;")
    )

    safe_source_url = (
        article["url"]
        .replace("&", "&amp;")
        .replace('"', "&quot;")
    )

    safe_source_title = (
        article["title"]
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
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

    for paragraph in re.split(
        r"\n+",
        generated["materia"],
    ):
        paragraph = paragraph.strip()

        if paragraph:
            content.append(
                f"<p>{paragraph}</p>"
            )

    content.append(
        '<p><small>Fonte: '
        f'<a href="{safe_source_url}" '
        'target="_blank" rel="noopener">'
        f"{safe_source_title}"
        "</a></small></p>"
    )

    # Chamada para ação: convida leitores do Blogger a entrar
    # voluntariamente no canal oficial do Telegram.
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

    return "\n".join(content)


def main():
    print("News Gospel + UAU Gospel + Folha Gospel Música + Guiame Música | /musicas sem Fuxico | Versão 9.4")
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    api = blogger()
    old_blog_urls, old_source_urls = existing(api)

    # Corrige também o acervo já publicado para que /musicas contenha
    # somente as outras fontes, nunca Fuxico Gospel.
    update_existing_music_labels(api)

    candidates=[]
    candidate_urls=set()
    source_counts={}

    for source in SOURCES:
        source_links=links(source)
        source_counts[source["nome"]]=len(source_links)
        for url in source_links:
            normalized=normalize_url(url)
            if normalized in candidate_urls or normalized in old_blog_urls or normalized in old_source_urls:
                continue
            article=get_article(normalized)
            if article:
                # Todas as matérias das fontes são elegíveis para publicação.
                # A classificação em /musicas é feita exclusivamente pelos
                # marcadores da fonte: Fuxico Gospel nunca entra em /musicas;
                # News Gospel, UAU Gospel, Folha Gospel e Guiame entram.
                candidate_urls.add(normalized)
                candidates.append(article)

    for name,count in source_counts.items():
        print(f"{name}: {count} encontradas")

    candidates.sort(key=lambda a: a["date"] or datetime.min, reverse=True)
    print(f"Novas matérias: {len(candidates)}")

    published=0
    failed=0
    ignored=0

    while candidates and published < MAX_POSTS_PER_RUN:
        article=candidates.pop(0)
        normalized=normalize_url(article["url"])
        if normalized in old_source_urls:
            ignored+=1
            continue

        if gemini_calls >= MAX_GEMINI_TEXT_CALLS_PER_RUN:
            print("⚠ Gemini: limite desta execução atingido; restante ficará para a próxima execução")
            break

        print("Gemini: gerando matéria...")
        generated=gemini(article,gemini_client)
        if not generated:
            ignored += 1
            if getattr(selfbot, "gemini_quota_hit", False):
                break
            continue

        try:
            post_labels = ["Notícias", "Rádio Luz Gospel"]

            # /musicas recebe somente matérias das outras fontes.
            # Fuxico Gospel fica fora dessa área, tanto agora quanto no futuro.
            if source_is_music_page(article.get("url", "")):
                post_labels.insert(1, "Músicas")

            response=api.posts().insert(
                blogId=BLOGGER_BLOG_ID,
                body={
                    "title":generated["titulo"].strip(),
                    "content":html(article,generated),
                    "labels":post_labels,
                },
                isDraft=False,
            ).execute()
            published+=1
            old_source_urls.add(normalized)
            if response.get("url"):
                old_blog_urls.add(normalize_url(response["url"]))
            print(f"✓ Publicada: {generated['titulo'].strip()}")
        except Exception:
            failed+=1
            print("⚠ Blogger: falha ao publicar")

    print("RESULTADO")
    print(f"Publicações: {published}")
    print(f"Ignoradas: {ignored}")
    print(f"Falhas: {failed}")


# ============================================================
# VERSÃO CONSOLIDADA 9.0
# ============================================================
import sys
import unicodedata
from difflib import SequenceMatcher

selfbot = sys.modules[__name__]

# ============================================================
# VERSÃO 9.0 - coleta, redação original, deduplicação e log enxuto
# ============================================================
MAX_AGE_DAYS = 7
VERSION = "9.2"
CURRENT_TZ = ZoneInfo("America/Sao_Paulo")
TIMEOUT = selfbot.TIMEOUT
SIMILARITY_MAX = 0.60
NGRAM_OVERLAP_MAX = 0.08
MIN_COPIED_WORDS = 15

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; RadioLuzGospelBot/9.0)"})

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
    host = urlparse(url).netloc.lower().replace("www.", "")
    try:
        r = s.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"⚠ {host}: HTTP {r.status_code}")
            return None
        x = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"⚠ {host}: erro ao abrir matéria")
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

    # REGRA DE ATUALIDADE 9.2:
    # Só aceita matérias publicadas no ano atual e dentro da semana
    # do calendário atual (segunda a domingo), considerando São Paulo.
    # Se a fonte não informar a data da matéria, não publica.
    if not d:
        return None

    hoje = datetime.now(CURRENT_TZ).date()
    inicio_semana = hoje.fromordinal(hoje.toordinal() - hoje.weekday())
    fim_semana = date.fromordinal(inicio_semana.toordinal() + 6)

    if d.year != hoje.year:
        return None

    if d.date() < inicio_semana or d.date() > fim_semana:
        return None

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
        return None

    box=next((x.select_one(sel) for sel in (".post-body",".entry-content",".post-content","article","main") if x.select_one(sel)),x)
    ps=[]
    for ptag in box.find_all("p"):
        t=re.sub(r"\s+"," ",ptag.get_text(" ",strip=True))
        if len(t)>=25: ps.append(t)
    text="\n\n".join(ps)

    if len(text) < selfbot.MIN_SOURCE_CHARS or len(ps) < selfbot.MIN_SOURCE_PARAGRAPHS:
        raw_lines=[]
        for line in box.get_text("\n", strip=True).splitlines():
            t=re.sub(r"\s+"," ",line).strip()
            if not t or t.lower() in {"comente","comentários","comentarios","deixe o seu comentário!","deixe o seu comentario!"}:
                continue
            raw_lines.append(t)
        clean_lines=[]
        for t in raw_lines:
            if not clean_lines or t != clean_lines[-1]: clean_lines.append(t)
        fallback_text="\n\n".join(clean_lines)
        if len(fallback_text) > len(text):
            text=fallback_text
            ps=[z for z in clean_lines if len(z)>=25]

    if len(text)<selfbot.MIN_SOURCE_CHARS or len(ps)<selfbot.MIN_SOURCE_PARAGRAPHS:
        return None

    vids=[]
    for n in x.find_all("iframe"):
        u=n.get("src","").strip()
        if u.startswith("//"): u="https:"+u
        if u.startswith(("http://","https://")) and u not in vids: vids.append(u)
    return {"url":url,"title":title,"date":d,"image":img,"text":text[:14000],"videos":vids[:5]}

def links(source):
    """Coleta links respeitando a área permitida de cada fonte.

    Fontes normais: feed + página inicial.
    Fontes de seção: somente os artigos encontrados dentro da URL da seção.
    Isso impede que /musica/ transforme-se em rastreamento do site inteiro.
    """
    out=[]; seen=set()
    base=urlparse(source["url"])
    host0=base.netloc.lower()
    section_only=bool(source.get("section_only"))
    path_prefix=(source.get("path_prefix") or "").rstrip("/").lower()

    def allowed_section_url(u):
        p=urlparse(u)
        if p.netloc.lower()!=host0 and not p.netloc.lower().endswith("."+host0):
            return False
        low=p.path.lower().rstrip("/") or "/"
        if path_prefix:
            return low == path_prefix or low.startswith(path_prefix + "/")
        return True

    def add(u, discovered_date=None):
        u=u.split("#",1)[0].strip()
        if not u.startswith(("http://","https://")): return
        p=urlparse(u)
        host=p.netloc.lower()
        low=u.lower()
        if host != host0 and not host.endswith("."+host0): return
        if any(z in low for z in BAD_TERMS): return
        if re.search(r"\.(jpg|jpeg|png|gif|webp|pdf|xml)(\?|$)",low): return
        if section_only and not allowed_section_url(u): return
        if u in seen: return
        seen.add(u)
        out.append((u, discovered_date))

    # ========================================================
    # FONTES DE SEÇÃO: NÃO percorrem o site inteiro.
    # ========================================================
    if section_only:
        try:
            r=s.get(source["url"],timeout=TIMEOUT)
            if r.status_code != 200:
                print(f"⚠ {source['nome']}: HTTP {r.status_code}")
            if r.status_code==200:
                x=BeautifulSoup(r.text,"html.parser")

                anchors=[]

                # 1) Para a Folha Gospel, o HTML da página /musica/ também
                # contém blocos de notícias da HOME no menu/cabeçalho.
                # Portanto, NÃO podemos varrer a página inteira.
                # Pegamos somente a área principal de conteúdo e ignoramos
                # header/nav/aside/footer.
                if "folhagospel.com" in host0:
                    main = (
                        x.select_one("main")
                        or x.select_one("#main")
                        or x.select_one(".site-main")
                        or x.select_one(".content-area")
                        or x.select_one(".main-content")
                        or x.select_one(".td-main-content")
                        or x.select_one(".jeg_main")
                    )
                    if main:
                        for bad in main.select("header, nav, aside, footer"):
                            bad.decompose()

                        # Somente cartões/blocos de matéria dentro do conteúdo
                        # principal. Não usar seletores genéricos como
                        # [class*='post'] na página inteira, pois eles podem
                        # capturar notícias da HOME que aparecem no menu.
                        for sel in (
                            "article a[href]",
                            ".post a[href]", ".entry a[href]",
                            ".td_module a[href]", ".jeg_post a[href]",
                            ".jeg_postblock a[href]", ".post-item a[href]",
                            ".blog-post a[href]", ".news-item a[href]",
                        ):
                            for a in main.select(sel):
                                anchors.append(a)

                        # Alguns layouts usam divs sem classes de artigo, mas
                        # os títulos da grade continuam dentro do conteúdo main.
                        if not anchors:
                            for a in main.find_all("a", href=True):
                                label=re.sub(r"\s+", " ", a.get_text(" ", strip=True))
                                if len(label) >= 25:
                                    anchors.append(a)
                else:
                    # Outras fontes de seção mantêm o comportamento anterior.
                    for sel in (
                        "article a[href]",
                        ".post a[href]", ".entry a[href]", ".item a[href]",
                        ".card a[href]", ".noticia a[href]", ".news a[href]",
                        ".td_module a[href]", ".jeg_post a[href]",
                        ".jeg_postblock a[href]", ".post-item a[href]",
                        ".blog-post a[href]", ".news-item a[href]",
                        "[class*='post'] a[href]", "[class*='article'] a[href]",
                        "[class*='entry'] a[href]",
                    ):
                        for a in x.select(sel):
                            anchors.append(a)

                    # Fallback opcional apenas para fontes que explicitamente
                    # permitem isso.
                    if not anchors and source.get("allow_main_fallback"):
                        main=x.select_one("main")
                        if main:
                            anchors.extend(main.find_all("a",href=True))

                # remove duplicações preservando a ordem da página
                seen_anchor=set()
                for a in anchors:
                    if id(a) in seen_anchor: continue
                    seen_anchor.add(id(a))
                    u=urljoin(source["url"],a.get("href",""))
                    label=re.sub(r"\s+"," ",a.get_text(" ",strip=True))
                    # Evita links de paginação, navegação e controles.
                    if len(label)<18: continue
                    if label.lower() in {
                        "leia mais","saiba mais","ver mais","próxima","proxima",
                        "anterior","home","início","inicio","menu","buscar","pesquisar",
                        "compartilhar","facebook","instagram","youtube","twitter"
                    }: continue
                    add(u)
        except Exception as e:
            print(f"⚠ {source['nome']}: erro na seção")

        # Não usa feed genérico nem homepage para fontes de seção.
        candidates=out
    else:
        # Feed primeiro.
        feeds=list(source.get("feeds",[]))
        if "newsgospel.com.br" in host0:
            # O /feed/ retorna 404 e múltiplas tentativas de feed podem provocar 429.
            # Mantemos apenas o feed nativo do Blogger, que já fornece as matérias.
            feeds=["https://www.newsgospel.com.br/feeds/posts/default"]
        feeds=list(dict.fromkeys(feeds))
        for feed in feeds:
            try:
                r=s.get(feed,timeout=TIMEOUT)
                if r.status_code != 200:
                    print(f"⚠ {source['nome']}: feed HTTP {r.status_code}")
                if r.status_code==200:
                    x=BeautifulSoup(r.text,"xml")
                    for item in x.find_all(["item","entry"]):
                        n=item.find("link")
                        u=(n.get("href") or n.get_text(strip=True)) if n else ""
                        dv=None
                        for tag in ("pubDate","published","updated","date"):
                            z=item.find(tag)
                            if z:
                                dv=date_parse(z.get_text(" ",strip=True))
                                if dv: break
                        add(u,dv)
            except Exception as e: print(f"⚠ {source['nome']}: erro no feed")

        # Página inicial como complemento apenas para fontes normais.
        try:
            r=s.get(source["url"],timeout=TIMEOUT)
            if r.status_code != 200:
                print(f"⚠ {source['nome']}: HTTP {r.status_code}")
            if r.status_code==200:
                x=BeautifulSoup(r.text,"html.parser")
                for a in x.find_all("a",href=True):
                    add(urljoin(source["url"],a["href"]))
        except Exception as e: print(f"⚠ {source['nome']}: erro na página")

        candidates=out

    # Não limitar antes de ordenar. Testa um conjunto maior.
    candidates=candidates[:max(selfbot.MAX_LINKS_PER_SOURCE,100)]
    scored=[]
    for u,dv in candidates:
        scored.append((dv if dv else datetime.min,u))
    scored.sort(reverse=True)
    result=[u for _,u in scored]
    return result[:max(selfbot.MAX_LINKS_PER_SOURCE,100)]

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
    src8=ngrams(src,8); out8=ngrams(out,8)
    overlap=len(src8 & out8)/max(1,min(len(src8),len(out8)))
    longest=longest_common_phrase(src,out)
    # Similaridade global não é usada para bloquear: em notícias sobre o mesmo
    # acontecimento, nomes, datas, cargos e fatos inevitavelmente se repetem.
    # O bloqueio fica restrito a sinais fortes de reprodução literal.
    if longest>=MIN_COPIED_WORDS:
        return False,f"há sequência de {longest} palavras iguais"
    if overlap>NGRAM_OVERLAP_MAX:
        return False,f"sobreposição 8-gram alta ({overlap:.3f})"
    return True,"OK"

def gemini(a,client):
    if selfbot.gemini_calls >= selfbot.MAX_GEMINI_TEXT_CALLS_PER_RUN:
        return None

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

    models=[selfbot.GEMINI_MODEL_TEXT]
    if selfbot.GEMINI_FALLBACK_MODEL and selfbot.GEMINI_FALLBACK_MODEL not in models:
        models.append(selfbot.GEMINI_FALLBACK_MODEL)

    last_reason="erro"
    for index, model in enumerate(models):
        try:
            r=selfbot.gemini_request(client,model,prompt)
            selfbot.gemini_calls += 1
            raw=(getattr(r,"text",None) or "").strip()
            raw=re.sub(r"^```(?:json)?\s*|\s*```$","",raw).strip()
            d=json.loads(raw)

            if d.get("publicar") is False:
                last_reason="sem informação suficiente"
                continue

            titulo=str(d.get("titulo","")).strip()
            resumo=str(d.get("resumo","")).strip()
            materia=str(d.get("materia","")).strip()
            if not titulo or not resumo or len(materia)<700:
                last_reason="resposta inválida"
                continue

            ok,reason=originality_check(a["text"],titulo+"\n"+resumo+"\n"+materia)
            if not ok:
                print("⚠ Gemini: matéria recusada por originalidade")
                last_reason="originalidade"
                # Tenta o modelo alternativo sem gerar outro aviso detalhado.
                continue

            d.update(titulo=titulo,resumo=resumo,materia=materia)
            print("✓ Gemini: matéria aprovada")
            return d

        except Exception as e:
            msg=str(e).upper()
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                last_reason="quota"
                break
            last_reason="erro"
            continue

    if last_reason == "quota":
        print("⚠ Gemini: quota/limite; restante ficará para a próxima execução")
        selfbot.gemini_quota_hit = True
    elif last_reason not in ("originalidade", "sem informação suficiente"):
        print("⚠ Gemini: geração não disponível")
    return None


_original_html = selfbot.html

def source_name(url):
    host=urlparse(url or "").netloc.lower()
    if "fuxicogospel.com.br" in host:return "Fuxico Gospel"
    if "newsgospel.com.br" in host:return "News Gospel"
    if "uaugospel.com.br" in host:return "UAU Gospel"
    if "folhagospel.com" in host:return "Folha Gospel - Música"
    if "guiame.com.br" in host:return "Guiame - Música"
    return host.replace("www.","") or "fonte original"

def source_is_music_page(url):
    """Fuxico nunca entra em /musicas; as demais fontes musicais entram."""
    host=urlparse(url or "").netloc.lower()
    if "fuxicogospel.com.br" in host:
        return False
    return any(
        key in host
        for key in ("newsgospel.com.br", "uaugospel.com.br", "folhagospel.com", "guiame.com.br")
    )

def html(a,d):
    out=_original_html(a,d)
    out=re.sub(r'<p><small>Fonte:\s*<a\s+href="[^"]*"[^>]*>.*?</a></small></p>',"",out,count=1,flags=re.I|re.S)
    out=re.sub(r'<p><small>Fonte:.*?</small></p>',"",out,count=1,flags=re.I|re.S)
    name=source_name(a.get("url",""))
    attribution=f'<p><small>Fonte de apuração: {name}</small></p>'
    source_url=str(a.get("url","")).strip()
    marker='<!-- RADIO_LUZ_GOSPEL_SOURCE_URL: '+source_url+' -->'
    return out.rstrip()+"\n"+attribution+"\n"+marker


# ============================================================
# NOVAS FONTES 9.0
# Folha Gospel: SOMENTE a seção /musica/
# Guiame: SOMENTE a seção /musica
# ============================================================
selfbot.SOURCES = [
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
        "feeds": ["https://www.newsgospel.com.br/feed/"],
        "music_page": True,
    },
    {
        "nome": "UAU Gospel",
        "url": "https://www.uaugospel.com.br/",
        "feeds": ["https://www.uaugospel.com.br/feed/"],
        "music_page": True,
    },
    {
        "nome": "Folha Gospel - Música",
        "url": "https://folhagospel.com/musica/",
        "feeds": [],
        "section_only": True,
        "music_page": True,
        # IMPORTANTE: a única página usada para descobrir matérias é
        # https://folhagospel.com/musica/ . Não usa a home nem outras seções.
        # Os links das matérias podem ter URL própria fora de /musica/.
        "path_prefix": "",
    },
    {
        "nome": "Guiame - Música",
        "url": "https://guiame.com.br/musica",
        "feeds": [],
        "section_only": True,
        "music_page": True,
        "path_prefix": "/musica",
    },
]

selfbot.get_article=get_article
selfbot.links=links
selfbot.gemini=gemini
selfbot.html=html
selfbot.MAX_AGE_DAYS=MAX_AGE_DAYS
selfbot.MAX_POSTS_PER_DAY=3
selfbot.MAX_GEMINI_TEXT_CALLS_PER_RUN=6

# ============================================================
# DIVULGAÇÃO 10.0 — leitores reais
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
    """Extrai a primeira imagem pública do HTML do post do Blogger."""
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
        f"👉 {url}\n\n"
        f"Fonte de apuração: {source_name_text}"
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


def instagram_art_url(post):
    """Gera uma imagem JPEG pública com a foto original + faixa branca + título.

    Usa o plugin de imagem de fundo e o plugin de anotação do QuickChart.
    A faixa branca é uma única annotation do tipo "box" com "label" interno,
    evitando o formato de annotation "label" separado que o QuickChart rejeita.
    """
    image_url = social_image_url(post)
    title = re.sub(r"\s+", " ", str(post.get("title", "")).strip())
    if not image_url or not title:
        return image_url

    # Quebra o título em até 3 linhas.
    words = title.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > 34:
            lines.append(current)
            current = word
        else:
            current = candidate
        if len(lines) >= 2:
            break
    if current and len(lines) < 3:
        lines.append(current)

    # Se ainda houver título, compacta a terceira linha.
    joined = " ".join(lines)
    if len(joined) < len(title) and lines:
        last = lines[-1]
        if len(last) > 30:
            lines[-1] = last[:27].rsplit(" ", 1)[0] + "..."
        elif len(lines) < 3:
            remaining = title[len(joined):].strip()
            if remaining:
                lines.append((remaining[:30].rsplit(" ", 1)[0] + "...") if len(remaining) > 30 else remaining)

    title_lines = lines[:3] or [title[:34]]

    config = {
        "type": "line",
        "data": {
            "labels": ["", ""],
            "datasets": [{
                "data": [0, 0],
                "borderWidth": 0,
                "pointRadius": 0,
                "borderColor": "rgba(255,255,255,0)",
                "backgroundColor": "rgba(255,255,255,0)",
            }],
        },
        "options": {
            "responsive": False,
            "animation": False,
            "legend": {"display": False},
            "layout": {"padding": 0},
            "scales": {
                "xAxes": [{
                    "display": False,
                    "ticks": {"min": 0, "max": 1},
                    "gridLines": {"display": False},
                }],
                "yAxes": [{
                    "display": False,
                    "ticks": {"min": 0, "max": 1},
                    "gridLines": {"display": False},
                }],
            },
            "plugins": {
                "backgroundImageUrl": image_url,
            },
            "annotation": {
                "annotations": [{
                    "type": "box",
                    "xScaleID": "x-axis-0",
                    "yScaleID": "y-axis-0",
                    "xMin": 0,
                    "xMax": 1,
                    "yMin": 0,
                    "yMax": 0.30,
                    "backgroundColor": "#FFFFFF",
                    "borderWidth": 0,
                    "label": {
                        "enabled": True,
                        "content": "\n".join(title_lines),
                        "position": "center",
                        "backgroundColor": "rgba(255,255,255,0)",
                        "fontColor": "#168A57",
                        "fontSize": 30,
                        "fontStyle": "bold",
                        "padding": 10,
                    },
                }],
            },
        },
    }

    from urllib.parse import quote
    encoded = quote(json.dumps(config, ensure_ascii=False, separators=(",", ":")), safe="")
    return (
        "https://quickchart.io/chart"
        "?width=1080&height=1080&devicePixelRatio=1"
        "&format=jpg&version=2.9.4&backgroundColor=white&c=" + encoded
    )


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
        print("⚠ Divulgação: Instagram sem imagem pública ou URL da matéria.")
        return False
    caption = (
        "📰 RÁDIO LUZ GOSPEL\n\n"
        f"{post.get('title', '').strip()}\n\n"
        "🔗 Leia a matéria completa:\n"
        f"{url}\n\n"
        f"Fonte de apuração: {source_name_text}\n\n"
        "#RadioLuzGospel #Gospel #NoticiasGospel #MusicaGospel"
    )

    # Esta é a autenticação do Instagram que já foi validada no robô.
    base = f"https://graph.instagram.com/{META_GRAPH_API_VERSION}/me"
    used_art = image_url != original_image_url
    try:
        if used_art:
            try:
                check = requests.get(image_url, stream=True, timeout=25)
                content_type = (check.headers.get("Content-Type") or "").lower()
                check.close()
                if check.status_code != 200 or not content_type.startswith("image/"):
                    print(f"⚠ Divulgação: arte automática não retornou imagem ({check.status_code}, {content_type}); usando imagem original.")
                    image_url = original_image_url
                    used_art = False
            except Exception as art_error:
                print(f"⚠ Divulgação: não foi possível validar a arte automática ({art_error}); usando imagem original.")
                image_url = original_image_url
                used_art = False

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

        # Aguarda o Instagram terminar de processar a arte antes de publicar.
        ready = False
        for attempt in range(1, 7):
            time.sleep(5)
            # O container é consultado diretamente pelo ID. Não use /me/{id}:
            # nessa rota o Instagram interpreta o ID como nome de campo.
            status = requests.get(
                f"{base.rsplit('/me', 1)[0]}/{creation_id}",
                params={
                    "fields": "status_code,status",
                    "access_token": INSTAGRAM_ACCESS_TOKEN,
                },
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
            data={
                "creation_id": creation_id,
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
            timeout=TIMEOUT,
        )
        if publish.ok:
            print("✓ Divulgação: publicada no Instagram com arte + título" if used_art else "✓ Divulgação: publicada no Instagram com imagem original (arte indisponível)")
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
        f"👉 {url}\n\n"
        f"Fonte de apuração: {source_name_text}"
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

# Mantém o robô original intacto e acrescenta uma etapa pós-publicação.
_original_main = selfbot.main

def main_with_real_reader_promotion():
    if not PROMO_ENABLED:
        _original_main()
        return

    api_before = blogger()
    before_urls, _ = existing(api_before)

    _original_main()

    try:
        api_after = blogger()
        after_urls, _ = existing(api_after)
        new_urls = list(after_urls - before_urls)
        if not new_urls:
            print("Divulgação: nenhuma publicação nova nesta execução.")
            return

        post_url = new_urls[0]
        posts = api_after.posts().list(
            blogId=BLOGGER_BLOG_ID,
            maxResults=500,
            fetchBodies=True
        ).execute().get("items", [])

        post = next(
            (p for p in posts
             if normalize_url(p.get("url", "")) == normalize_url(post_url)),
            None
        )
        if not post:
            print("Divulgação: publicação recém-criada não localizada.")
            return

        content = post.get("content", "") or ""
        m = re.search(
            r"RADIO_LUZ_GOSPEL_SOURCE_URL:\s*(https?://[^\s]+?)\s*-->",
            content,
            flags=re.I
        )
        source_text = source_name(m.group(1)) if m else "Rádio Luz Gospel"
        telegram_promote(post, source_text)
        facebook_promote(post, source_text)
        instagram_promote(post, source_text)

    except Exception as e:
        print("⚠ Divulgação: erro na etapa pós-publicação:", e)

selfbot.main = main_with_real_reader_promotion

print("VERSÃO 10.6 ATIVA: Instagram com arte JPEG + título | Facebook + Telegram preservados")
selfbot.main()
