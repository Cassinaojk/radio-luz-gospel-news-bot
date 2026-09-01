import os

WP_URL = os.getenv("WP_URL", "https://radioluzgospel.22web.org").rstrip("/")
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

GEMINI_MODEL = os.getenv("GEMINI_MODEL = "gemini-3.6-flash")
WP_POST_STATUS = os.getenv("WP_POST_STATUS", "draft")
ARTICLES_PER_RUN = int(os.getenv("ARTICLES_PER_RUN", "1"))

RSS_FEEDS = [
    ("Brasil", "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml"),
    ("Geral", "https://g1.globo.com/rss/g1/"),
    ("Mundo", "https://feeds.bbci.co.uk/portuguese/rss.xml"),
    ("Gospel", "https://news.google.com/rss/search?q=gospel%20igreja%20crist%C3%A3&hl=pt-BR&gl=BR&ceid=BR:pt-419"),
    ("Música Gospel", "https://news.google.com/rss/search?q=m%C3%BAsica%20gospel%20cantor%20gospel&hl=pt-BR&gl=BR&ceid=BR:pt-419"),
]
