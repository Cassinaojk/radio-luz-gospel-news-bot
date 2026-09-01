import os

# Configurações do WordPress puxadas dos Secrets
WP_URL = os.getenv("WP_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

# Configurações do Gemini (Usando o modelo estável mais recente de 2026)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Configurações de Postagem
WP_POST_STATUS = "draft"  # Salva como rascunho. Mude para "publish" para postar direto.
ARTICLES_PER_RUN = 3

# Lista de fontes de notícias corrigida no formato (categoria, url) esperado pelo robô
RSS_FEEDS = [
    ("Tecnologia", "https://globo.com"),
    ("Mundo", "https://globo.com")
]
