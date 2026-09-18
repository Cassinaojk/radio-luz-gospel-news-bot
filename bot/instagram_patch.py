from pathlib import Path

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")

start = s.index("def instagram_art_url(post):")
end = s.index("\ndef instagram_promote", start)

fn = r'''
def instagram_art_url(post):
    """
    Instagram 12.18
    - Texto amarelo claro (#FFF3A3) dentro de faixa branca semi-transparente
    - Borda fina azulada
    - Faixa se ajusta ao tamanho do texto (altura dinâmica)
    - backgroundImageUrl (watermark API quebrada)
    - Logs de diagnóstico
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

    print(f"🔍 Instagram debug image_url: {image_url}")

    # Quebra inteligente
    words = title.split()
    first = " ".join(words[:5])
    rest = " ".join(words[5:])

    lines = [first]
    if rest:
        extra = _instagram_wrap_text(rest, max_chars=26, max_lines=3)
        lines.extend(extra)
    lines = lines[:4]

    num_lines = len(lines)

    # Altura da faixa proporcional ao número de linhas (encaixa o texto)
    # ~38px por linha + padding interno
    faixa_height = 38 * num_lines + 36
    top_padding = 1080 - faixa_height - 20   # deixa a faixa bem embaixo

    config = {
        "type": "bar",
        "data": {
            "labels": [""],
            "datasets": [{
                "data": [1],
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
                    "top": top_padding,
                    "right": 28,
                    "bottom": 12,
                    "left": 28
                }
            },
            "scales": {
                "xAxes": [{
                    "display": False,
                    "ticks": {"min": 0, "max": 1}
                }],
                "yAxes": [{
                    "display": False,
                    "ticks": {"min": 0, "max": 1}
                }]
            },
            "title": {
                "display": True,
                "position": "bottom",
                "text": lines,
                "fontSize": 30,
                "fontStyle": "bold",
                "fontColor": "#FFF3A3",
                "padding": 8
            },
            "annotation": {
                "annotations": [{
                    "type": "box",
                    "drawTime": "beforeDatasetsDraw",
                    "xScaleID": "x-axis-0",
                    "yScaleID": "y-axis-0",
                    "xMin": -0.5,
                    "xMax": 1.5,
                    "yMin": -0.5,
                    "yMax": 1.5,
                    "backgroundColor": "rgba(255, 255, 255, 0.72)",
                    "borderColor": "#5B9BD5",
                    "borderWidth": 2
                }]
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

    print(f"🔍 Instagram debug final_url: {final_url[:180]}...")
    return final_url
'''

s = s[:start] + fn + s[end:]

for old in ["12.17", "12.16", "12.15", "12.14", "12.13", "12.12", "12.11", "12.10", "12.9", "12.8", "12.7", "12.6", "12.5", "12.4", "12.3", "12.2", "12.1"]:
    s = s.replace(f"VERSÃO {old}", "VERSÃO 12.18")
    s = s.replace(f"Instagram {old}", "Instagram 12.18")

s = s.replace("VERSÃO 12.17 ATIVA", "VERSÃO 12.18 ATIVA")
s = s.replace("VERSÃO 12.1 ATIVA", "VERSÃO 12.18 ATIVA")

p.write_text(s, encoding="utf-8")
print("Patch Instagram 12.18 aplicado (faixa branca semi-transparente + borda azul + texto #FFF3A3).")
