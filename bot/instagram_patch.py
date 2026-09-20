"""Validação da arte do Instagram.
A lógica definitiva fica em bot/main.py; este arquivo não altera o código.
"""
from pathlib import Path

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")
required = (
    "def instagram_art_url(post):",
    "def instagram_promote(post, source_name_text):",
)
missing = [item for item in required if item not in s]
if missing:
    raise SystemExit("Instagram: estrutura ausente: " + ", ".join(missing))
print("Instagram: lógica consolidada em bot/main.py; nenhum patch aplicado.")
