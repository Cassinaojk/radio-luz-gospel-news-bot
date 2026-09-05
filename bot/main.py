import os, re, json, requests, time, random
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse, urljoin
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

print("RÁDIO LUZ GOSPEL - ROBÔ DE NOTÍCIAS 5.0")

BLOGGER_BLOG_ID = os.environ["BLOGGER_BLOG_ID"]
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# Limites
MAX_POSTS_PER_RUN = 3
MAX_GEMINI_TEXT_CALLS_PER_RUN = 3
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_BASE_SECONDS = 4
MAX_LINKS_PER_SOURCE = 80

# 3650 dias (~10 anos): a duplicidade passa a ser controlada
# principalmente pela URL da fonte, não por uma janela curta de idade.
MAX_AGE_DAYS = 3650

MIN_SOURCE_CHARS = 700
MIN_SOURCE_PARAGRAPHS = 4
TIMEOUT = 25

GEMINI_MODEL_TEXT = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")

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
    "User-Agent": "Mozilla/5.0 (compatible; RadioLuzGospelBot/5.0)"
})

gemini_calls = 0


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

        return BeautifulSoup(r.text, "xml" if xml else "html.parser")

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

                # Procura a URL registrada como fonte no final da matéria.
                for match in re.findall(
                    r'href=["\'](https?://[^"\']+)["\']',
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
            print(
                f"Gemini: modelo={model} "
                f"tentativa={attempt}/{GEMINI_MAX_RETRIES}"
            )

            return client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                },
            )

        except Exception as e:
            last_error = e

            if (
                not is_transient_gemini_error(e)
                or attempt >= GEMINI_MAX_RETRIES
            ):
                raise

            delay = (
                GEMINI_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                + random.uniform(0, 2)
            )

            print("Gemini temporariamente indisponível:", e)
            print(f"Nova tentativa em {delay:.1f}s...")
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
- publicar=true se houver informação suficiente;
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

            print(
                "Resposta do Gemini:",
                len(raw),
                "caracteres",
            )

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
    print(
        "Somente News Gospel + UAU Gospel | "
        "Sem janela curta de 60 dias"
    )

    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    api = blogger()
    print("Blogger OK")

    old_blog_urls, old_source_urls = existing(api)

    candidates = []
    candidate_urls = set()

    for source in SOURCES:
        print(
            "\n=====",
            source["nome"],
            "====="
        )

        for url in links(source):
            normalized = normalize_url(url)

            # Evita duplicação dentro da própria execução.
            if normalized in candidate_urls:
                continue

            # URL do próprio Blogger.
            if normalized in old_blog_urls:
                print(
                    "Já existe como URL do Blogger:",
                    normalized,
                )
                continue

            # URL original já registrada em uma matéria publicada.
            if normalized in old_source_urls:
                print(
                    "Fonte já publicada:",
                    normalized,
                )
                continue

            article = get_article(normalized)

            if article:
                candidate_urls.add(normalized)
                candidates.append(article)

    candidates.sort(
        key=lambda a: a["date"] or datetime.min,
        reverse=True,
    )

    print(
        "\nCandidatos válidos:",
        len(candidates),
    )

    published = 0

    while candidates and published < MAX_POSTS_PER_RUN:
        article = candidates.pop(0)

        normalized = normalize_url(
            article["url"]
        )

        print(
            "\nVerificando duplicidade:",
            normalized,
        )

        if normalized in old_source_urls:
            print("Já publicado. Pulando.")
            continue

        print("Notícia nova.")
        print(
            "Gerando título e matéria com Gemini..."
        )

        generated = gemini(
            article,
            gemini_client,
        )

        if not generated:
            print(
                "Não foi possível gerar a matéria."
            )

            if (
                gemini_calls
                >= MAX_GEMINI_TEXT_CALLS_PER_RUN
            ):
                print(
                    "Limite de chamadas do Gemini "
                    "atingido nesta execução."
                )
                break

            continue

        try:
            response = (
                api.posts()
                .insert(
                    blogId=BLOGGER_BLOG_ID,
                    body={
                        "title": generated["titulo"].strip(),
                        "content": html(
                            article,
                            generated,
                        ),
                        "labels": [
                            "Notícias",
                            "Rádio Luz Gospel",
                        ],
                    },
                    isDraft=False,
                )
                .execute()
            )

            print(
                "PUBLICADO:",
                response.get("url"),
            )

            old_source_urls.add(normalized)

            if response.get("url"):
                old_blog_urls.add(
                    normalize_url(
                        response["url"]
                    )
                )

            published += 1

        except Exception as e:
            print(
                "Erro ao publicar:",
                e,
            )

    print(
        "ROBÔ FINALIZADO. Publicações:",
        published,
    )


if __name__ == "__main__":
    main()
