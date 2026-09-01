import os

# Configurações do WordPress puxadas dos Secrets
WP_URL = os.getenv("WP_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

# Configurações do Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Configurações de Postagem
WP_POST_STATUS = "draft"  # Salva como rascunho.
ARTICLES_PER_RUN = 3

# Usando apenas uma fonte estável para o teste definitivo
RSS_FEEDS = [
    ("Gospel", "https://uaugospel.com.br")
]
