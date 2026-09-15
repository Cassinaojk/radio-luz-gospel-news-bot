from pathlib import Path

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")

start = s.index("def instagram_art_url(post):")
end = s.index("\ndef instagram_promote", start)

fn = r'''
def instagram_art_url(post):
    """
    Instagram 12.12 — versão estável
    - Imagem original
    - Sem faixa preta
    - Sem marca d'água / logo
    - Texto em amarelo queimado (#E8A317)
    - Usa overlay + 1 watermark (muito mais estável)
    """
    from urllib.parse import quote

    image_url = social_image_url(post)

    title = re.sub(
        r"\s+",
        " ",
        (
            post.get("title")
            or post.get("resumo")
            or post.get("summary")
            or ""
        ).strip()
    )

    if not image_url or not title:
        print("⚠ Instagram: imagem ou texto ausente; publicação cancelada.")
        return None

    # Quebra o título
    words = title.split()
    first = " ".join(words[:5])
    rest = " ".join(words[5:])

    lines = [first]
    if rest:
        extra = _instagram_wrap_text(rest, max_chars=30, max_lines=3)
        lines.extend(extra)

    lines = lines[:4]

    # Cria a camada de texto (amarelo queimado)
    overlay_url = _quickchart_overlay(
        lines,
        color="#E8A317",
        background="rgba(0,0,0,0)",
        height=420
    )

    # Coloca o texto embaixo da imagem original
    final_url = (
        "https://quickchart.io/watermark"
        "?mainImageUrl=" + quote(image_url, safe="")
        + "&markImageUrl=" + quote(overlay_url, safe="")
        + "&markRatio=1"
        + "&position=bottomMiddle"
        + "&margin=0"
    )

    return final_url
'''

s = s[:start] + fn + s[end:]

# Atualiza versões
for old in ["12.11", "12.10", "12.9", "12.8", "12.7", "12.6", "12.5", "12.4", "12.3", "12.2", "12.1"]:
    s = s.replace(f"VERSÃO {old}", "VERSÃO 12.12")
    s = s.replace(f"Instagram {old}", "Instagram 12.12")

s = s.replace("VERSÃO 12.1 ATIVA", "VERSÃO 12.12 ATIVA")

p.write_text(s, encoding="utf-8")

print("Patch Instagram 12.12 aplicado com sucesso.")
