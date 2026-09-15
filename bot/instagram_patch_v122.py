from pathlib import Path

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")

# Corrige a regex antiga
s = s.replace(
    r'match = re.match(r"(.+?\[.!?:\])(?:\\s+\|$)(.\*)$", clean)',
    r'match = re.match(r"(.+?[.!?:])(?:\s+|$)(.*)$", clean)'
)

start = s.index("def instagram_art_url(post):")
end = s.index("\ndef instagram_promote", start)

fn = '''
def instagram_art_url(post):
    """Instagram 12.2 - texto amarelo e branco sem faixa."""

    from urllib.parse import quote

    image_url = social_image_url(post)

    text = re.sub(
        r"\\s+",
        " ",
        (
            post.get("title")
            or post.get("resumo")
            or post.get("summary")
            or ""
        ).strip()
    )

    if not image_url or not text:
        return None

    words = text.split()

    first_line = " ".join(words[:4])

    remaining_text = " ".join(words[4:])

    remaining_lines = _instagram_wrap_text(
        remaining_text,
        max_chars=26,
        max_lines=3
    )

    yellow_overlay = _quickchart_overlay(
        [first_line],
        "#D4A017"
    )

    result = image_url

    if remaining_lines:
        white_overlay = _quickchart_overlay(
            remaining_lines,
            "#FFFFFF"
        )

        result = (
            "https://quickchart.io/watermark?"
            + "mainImageUrl=" + quote(result, safe="")
            + "&markImageUrl=" + quote(white_overlay, safe="")
            + "&position=bottomLeft"
            + "&margin=40"
            + "&markRatio=1"
        )

    result = (
        "https://quickchart.io/watermark?"
        + "mainImageUrl=" + quote(result, safe="")
        + "&markImageUrl=" + quote(yellow_overlay, safe="")
        + "&position=bottomLeft"
        + "&margin=40"
        + "&markRatio=1"
    )

    return result
'''

s = s[:start] + fn + s[end:]

s = s.replace("VERSÃO 12.1", "VERSÃO 12.2")

p.write_text(s, encoding="utf-8")

print("Patch Instagram 12.2 aplicado com sucesso.")