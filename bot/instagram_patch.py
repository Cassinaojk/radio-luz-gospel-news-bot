from pathlib import Path

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")

start = s.index("def instagram_art_url(post):")
end = s.index("\ndef instagram_promote", start)

fn = r'''
def instagram_art_url(post):
    """
    Instagram 12.15
    - Texto amarelo queimado (#E8A317) forçado na parte inferior
    - Fonte maior e nítida
    - Usa backgroundImageUrl (sem watermark – API quebrada)
    - Sem faixa preta e sem logo
    """
    from urllib.parse import quote
    import json

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

    # Quebra inteligente
    words = title.split()
    first = " ".join(words[:5])
    rest = " ".join(words[5:])

    lines = [first]
    if rest:
        extra = _instagram_wrap_text(rest, max_chars=28, max_lines=3)
        lines.extend(extra)

    lines = lines[:4]

    # Chart com a imagem do post como fundo + texto na base
    config = {
        "type": "bar",
        "data": {
            "labels": [""],
            "datasets": [{
                "data": [0],
                "backgroundColor": "rgba(0,0,0,0)",
                "borderWidth": 0
            }]
        },
        "options": {
            "responsive": False,
            "animation": False,
            "maintainAspectRatio": False,
            "legend": {"display": False},
            "layout": {
                "padding": {
                    "top": 720,      # empurra o texto bem para baixo
                    "right": 40,
                    "bottom": 30,
                    "left": 40
                }
            },
            "scales": {
                "xAxes": [{"display": False}],
                "yAxes": [{"display": False}]
            },
            "title": {
                "display": True,
                "position": "bottom",
                "text": lines,
                "fontSize": 34,
                "fontStyle": "bold",
                "fontColor": "#FFF3A3",
                "padding": 12
            },
            "plugins": {
                "backgroundImageUrl": image_url
            }
        }
    }

    config_json = json.dumps(config, ensure_ascii=False, separators=(",", ":"))

    final_url = (
        "https://quickchart.io/chart"
        "?width=1080"
        "&height=1080"
        "&devicePixelRatio=1"
        "&format=png"
        "&version=2.9.4"
        "&backgroundColor=transparent"
        "&c=" + quote(config_json)
    )

    return final_url
'''

s = s[:start] + fn + s[end:]

# Atualiza versões
for old in ["12.14", "12.13", "12.12", "12.11", "12.10", "12.9", "12.8", "12.7", "12.6", "12.5", "12.4", "12.3", "12.2", "12.1"]:
    s = s.replace(f"VERSÃO {old}", "VERSÃO 12.15")
    s = s.replace(f"Instagram {old}", "Instagram 12.15")

s = s.replace("VERSÃO 12.14 ATIVA", "VERSÃO 12.15 ATIVA")
s = s.replace("VERSÃO 12.1 ATIVA", "VERSÃO 12.15 ATIVA")

p.write_text(s, encoding="utf-8")

print("Patch Instagram 12.15 aplicado com sucesso (backgroundImageUrl, sem watermark).")
