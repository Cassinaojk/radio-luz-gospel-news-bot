from pathlib import Path

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")

start = s.index("def instagram_art_url(post):")
end = s.index("\ndef instagram_promote", start)

fn = '''def instagram_art_url(post):
    """Gera arte 1080x1080 com imagem original e texto sobreposto.

    Não usa backgroundImageUrl do QuickChart, pois essa abordagem estava
    retornando HTTP 400. O QuickChart gera somente a camada transparente
    de texto e o endpoint watermark combina essa camada com a imagem original.
    """
    from urllib.parse import quote

    image_url = social_image_url(post)
    text = re.sub(r"\\s+", " ", (post.get("title") or post.get("resumo") or post.get("summary") or "").strip())
    if not image_url or not text:
        print("⚠ Instagram: imagem ou texto ausente; publicação cancelada.")
        return None

    print(f"🔍 Instagram debug image_url: {image_url}")
    first_lines, remaining_lines = _instagram_text_parts(text, max_lines=4)
    overlay_urls = []
    if remaining_lines:
        overlay_urls.append(_quickchart_overlay(remaining_lines, "#FFFFFF"))
    if first_lines:
        overlay_urls.append(_quickchart_overlay(first_lines, "#FFF3A3"))

    result = image_url
    for overlay_url in overlay_urls:
        result = ("https://quickchart.io/watermark?mainImageUrl=" + quote(result, safe="")
                  + "&markImageUrl=" + quote(overlay_url, safe="")
                  + "&markRatio=1&position=bottomMiddle&margin=0")

    print(f"🔍 Instagram debug final_url: {result[:180]}...")
    return result
'''

s = s[:start] + fn + s[end:]
s = s.replace(
    'print("VERSÃO 12.1 ATIVA: Instagram com texto amarelo/branco sobre imagem original (sem faixa)")',
    'print("VERSÃO 12.18 ATIVA: /musicas por conteúdo + Instagram texto amarelo/branco sobre imagem original")'
)
p.write_text(s, encoding="utf-8")
print("Patch Instagram corrigido aplicado.")
