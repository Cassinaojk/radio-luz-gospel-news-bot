import sys
import os
# Garante que o Python encontre a pasta bot durante a execução
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import base64
import hashlib
import html
import json
import re
import sqlite3
import socket
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

from config import (
    WP_URL, WP_USERNAME, WP_APP_PASSWORD, GEMINI_API_KEY, GEMINI_MODEL,
    WP_POST_STATUS, ARTICLES_PER_RUN, RSS_FEEDS
)

DB_PATH = "data/news.db"
TIMEOUT = 20

# Força o feedparser e conexões brutas a desistirem se o site demorar mais de 15 segundos
socket.setdefaulttimeout(15)

# Mude para False depois que o primeiro post aparecer no WordPress!
TEST_MODE = True

def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS processed ("
        "fingerprint TEXT PRIMARY KEY, source_url TEXT, title TEXT, "
        "created_at TEXT, wp_post_id INTEGER)"
    )
    return conn

def fingerprint(title, url):
    raw = re.sub(r"\W+", " ", (title or "").lower()).strip() + "|" + (url or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def already_seen(conn, fp):
    if TEST_MODE:
        return False  # Ignora o banco de dados durante os testes de validação
    return conn.execute(
        "SELECT 1 FROM processed WHERE fingerprint=?", (fp,)
    ).fetchone() is not None

def mark_seen(conn, fp, item, post_id=None):
    conn.execute(
        "INSERT OR REPLACE INTO processed VALUES (?,?,?,?,?)",
        (fp, item["url"], item["title"],
         datetime.now(timezone.utc).isoformat(), post_id)
    )
    conn.commit()

def clean_text(value):
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    return re.sub(r"\s+", " ", html.unescape(soup.get_text(" "))).strip()

def collect():
    items = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    for category, feed_url in RSS_FEEDS:
        try:
            print(f"[INFO] Baixando conteúdo do feed: {feed_url}")
            r = requests.get(feed_url, timeout=TIMEOUT, headers=headers)
            if r.status_code >= 400:
                print(f"[WARN] Feed retornou status {r.status_code}. Pulando.")
                continue
                
            feed = feedparser.parse(r.content)
            print(f"[INFO] Sucesso! Encontrados {len(feed.entries)} itens no feed.")
            
            for e in feed.entries[:12]:
                title = clean_text(e.get("title", ""))
                url = e.get("link", "")
                summary = clean_text(e.get("summary", "") or e.get("description", ""))
                if title and url:
                    items.append({
                        "category": category,
                        "title": title,
                        "url": url,
                        "summary": summary[:4000],
                        "published": e.get("published", "") or e.get("updated", "")
                    })
        except Exception as exc:
            print(f"[WARN] Erro ao ler RSS {feed_url}: {exc}")
    return items

def page_extract(url):
    try:
        r = requests.get(
            url, timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        if r.status_code >= 400:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
            tag.decompose()
        target = soup.find("article") or soup.find("main") or soup.body
        if not target:
            return ""
        return re.sub(r"\s+", " ", target.get_text(" ", strip=True))[:12000]
    except Exception as exc:
        print(f"[WARN] Página {url}: {exc}")
        return ""

def gemini(prompt):
    endpoint = (
        f"https://googleapis.com"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }
    r = requests.post(endpoint, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    
    # Sistema de leitura inteligente compatível com a versão antiga e nova da API
    text_response = ""
    try:
        # Tenta o formato padrão (Lista estruturada)
        text_response = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        try:
            # Tenta o formato alternativo simplificado
            text_response = data["candidates"]["content"]["parts"]["text"].strip()
        except Exception:
            raise ValueError(f"Não foi possível ler a estrutura da API do Gemini. Resposta recebida: {data}")
    
    # Limpeza de possíveis formatações de bloco markdown do JSON
    text_response = re.sub(r"^```json\s*", "", text_response, flags=re.IGNORECASE)
    text_response = re.sub(r"^```\s*", "", text_response, flags=re.IGNORECASE)
    text_response = re.sub(r"\s*```$", "", text_response, flags=re.IGNORECASE)
    text_response = text_response.strip()
        
    return json.loads(text_response)

def generate_article(item, source_text):
    material = (
        f"FONTE PRINCIPAL\nTítulo: {item['title']}\nURL: {item['url']}\n"
        f"Categoria: {item['category']}\nResumo RSS: {item['summary']}\n\n"
        f"TEXTO DA PÁGINA:\n{source_text[:12000]}"
    )

    prompt = f'''
Você é editor de um portal chamado Rádio Luz Gospel.
Produza UMA reportagem original em português do Brasil usando somente os fatos
do material abaixo.

REGRAS:
- Não copie frases da fonte.
- Não faça simples troca de sinônimos ou paráfrase linha a linha.
- Não invente nomes, números, datas, declarações ou acontecimentos.
- Não crie citações. Preserve a atribuição de declarações existentes.
- Se o material for insuficiente ou contraditório, use publish=false.
- Crie título próprio.
- Escreva entre 350 e 650 palavras.
- Inclua "Fontes consultadas" com link HTML.
- Não use markdown; content deve ser HTML simples.

Retorne SOMENTE JSON válido, sem blocos de markdown:
{{
  "publish": true,
  "title": "...",
  "excerpt": "...",
  "content": "<p>...</p>",
  "tags": ["tag1","tag2"],
  "category": "Gospel"
}}

Material:
{material}
'''
    return gemini(prompt)

def wp_auth():
    token = base64.b64encode(
        f"{WP_USERNAME}:{WP_APP_PASSWORD}".encode("utf-8")
    ).decode("ascii")
    return {"Authorization": f"Basic {token}"}

def wp_get(path, params=None):
    r = requests.get(
        WP_URL + "/wp-json/wp/v2/" + path,
        headers=wp_auth(), params=params, timeout=TIMEOUT
    )
    r.raise_for_status()
    return r.json()

def wp_post(path, payload):
    r = requests.post(
        WP_URL + "/wp-json/wp/v2/" + path,
        headers={**wp_auth(), "Content-Type": "application/json"},
        json=payload, timeout=TIMEOUT
    )
    if r.status_code >= 400:
        print("[ERROR] WordPress:", r.text[:2000])
    r.raise_for_status()
    return r.json()

def get_or_create_category(name):
    try:
        found = wp_get("categories", {"search": name, "per_page": 20})
        for c in found:
            if c["name"].lower() == name.lower():
                return c["id"]
        return wp_post("categories", {"name": name})["id"]
    except Exception:
        return 1

def get_or_create_tags(names):
    ids = []
    for name in names[:8]:
        name = re.sub(r"\s+", " ", str(name)).strip()
        if not name:
            continue
        try:
            found = wp_get("tags", {"search": name, "per_page": 20})
            exact = next((t for t in found if t["name"].lower() == name.lower()), None)
            ids.append(exact["id"] if exact else wp_post("tags", {"name": name})["id"])
        except Exception:
            continue
    return ids

def publish(article, item):
    category_id = get_or_create_category(article.get("category") or item["category"])
    tag_ids = get_or_create_tags(article.get("tags", []))

    content = article["content"].strip()
    content += (
        f'<p><strong>Fonte de apuração:</strong> '
        f'<a href="{html.escape(item["url"], quote=True)}" '
        f'rel="nofollow noopener" target="_blank">{html.escape(item["url"])}</a></p>'
    )

    payload = {
        "title": article["title"].strip(),
        "content": content,
        "excerpt": article.get("excerpt", "").strip(),
        "status": WP_POST_STATUS,
        "categories": [category_id],
        "tags": tag_ids,
    }
    return wp_post("posts", payload)

def main():
    conn = db()
    candidates = []

    collected_items = collect()
    print(f"[INFO] Total de notícias coletadas nos feeds: {len(collected_items)}")

    for item in collected_items:
        fp = fingerprint(item["title"], item["url"])
        if not already_seen(conn, fp):
            candidates.append((fp, item))

    if not candidates:
        print("[INFO] Nenhuma notícia nova encontrada.")
        return

    print(f"[INFO] {len(candidates)} notícias candidatas prontas para processamento.")
    candidates = candidates[:max(ARTICLES_PER_RUN * 5, 5)]
    published = 0

    for fp, item in candidates:
        if published >= ARTICLES_PER_RUN:
            break

        print(f"[INFO] Analisando: {item['title']}")
        source_text = page_extract(item["url"])
        
        if not source_text:
            print("[WARN] Não foi possível extrair o texto da página original. Pulando.")
            continue

        try:
            article = generate_article(item, source_text)
        except Exception as exc:
            print(f"[ERROR] Geração Gemini: {exc}")
            continue

        if not article.get("publish"):
            print("[INFO] Conteúdo insuficiente segundo o Gemini; não publicar.")
