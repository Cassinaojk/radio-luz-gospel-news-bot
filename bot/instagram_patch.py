from pathlib import Path

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")

start = s.index("def instagram_art_url(post):")
end = s.index("\ndef instagram_promote", start)

fn = r'''
def instagram_art_url(post):
    """
    Instagram 12.5
    Visual fiel ao 12.1:
    - Imagem original (sem faixa preta)
    - Primeira linha amarela (#FFB51B)
    - Restante em branco
    - Texto em negrito
    - Máximo 4 linhas
    - Mínimo de requests (2 overlays + 1 watermark)
    """
    from urllib.parse import quote

    image_url = social_image_url(post)

    text = re.sub(
        r"\s+",
        " ",
        (
            post.get("resumo")
            or post.get("summary")
            or post.get("title")
            or ""
        ).strip()
    )

    if not image_url or not text:
        print("⚠ Instagram: imagem ou texto ausente; publicação cancelada.")
        return None

    first_lines, remaining_lines = _instagram_text_parts(text, max_lines=4)

    # Garante no máximo 4 linhas no total
    total_lines = (first_lines or []) + (remaining_lines or [])
    if len(total_lines) > 4:
        remaining_lines = remaining_lines[: max(0, 4 - len(first_lines or []))]

    overlay_urls = []

    # Camada branca (restante)
    if remaining_lines:
        overlay_urls.append(
            _quickchart_overlay(remaining_lines, "#FFFFFF", height=380)
        )

    # Camada amarela (primeira linha) — fica por cima
    if first_lines:
        overlay_urls.append(
            _quickchart_overlay(first_lines, "#FFB51B", height=380)
        )

    if not overlay_urls:
        return image_url

    # Compõe as camadas sobre a imagem original (posição inferior)
    result = image_url
    for overlay_url in overlay_urls:
        result = (
            "https://quickchart.io/watermark"
            "?mainImageUrl=" + quote(result, safe="")
            + "&markImageUrl=" + quote(overlay_url, safe="")
            + "&markRatio=1"
            + "&position=bottomMiddle"
            + "&margin=0"
        )

    return result
'''

s = s[:start] + fn + s[end:]

# Atualiza as strings de versão
s = s.replace("VERSÃO 12.3", "VERSÃO 12.5")
s = s.replace("VERSÃO 12.4", "VERSÃO 12.5")
s = s.replace("VERSÃO 12.2", "VERSÃO 12.5")
s = s.replace("VERSÃO 12.1 ATIVA", "VERSÃO 12.5 ATIVA")
s = s.replace("Instagram 12.3", "Instagram 12.5")
s = s.replace("Instagram 12.4", "Instagram 12.5")

p.write_text(s, encoding="utf-8")

print("Patch Instagram 12.5 aplicado com sucesso.")
