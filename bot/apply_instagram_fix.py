from pathlib import Path
import re

P = Path(__file__).with_name("main.py")
s = P.read_text(encoding="utf-8")

start = s.find("def instagram_art_url(post):")
end = s.find("\ndef instagram_promote(post, source_name_text):", start)
if start < 0 or end < 0:
    raise SystemExit("instagram_art_url não encontrada")

new_func = r'''def instagram_art_url(post):
    """Gera uma arte 1080x1080 com a foto original e título em faixa discreta."""
    image_url = social_image_url(post)
    title = re.sub(r"\s+", " ", (post.get("title") or "").strip())
    if not image_url or not title:
        return image_url

    words = title.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > 38:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > 3:
        lines = lines[:3]
        lines[-1] = lines[-1][:34].rstrip() + "..."
    title_lines = lines or [title[:38]]

    # QuickChart monta a própria arte final: a foto fica como fundo e uma
    # caixa pequena, branca e levemente transparente fica sobre a parte inferior.
    config = {
        "type": "scatter",
        "data": {"datasets": [{"data": [], "pointRadius": 0}]},
        "options": {
            "responsive": False,
            "animation": False,
            "maintainAspectRatio": False,
            "legend": {"display": False},
            "layout": {"padding": 0},
            "scales": {
                "xAxes": [{"display": False, "ticks": {"min": 0, "max": 1}, "gridLines": {"display": False}}],
                "yAxes": [{"display": False, "ticks": {"min": 0, "max": 1}, "gridLines": {"display": False}}],
            },
            "plugins": {
                "backgroundImageUrl": image_url,
                "annotation": {
                    "annotations": {
                        "titleBox": {
                            "type": "box",
                            "xScaleID": "x-axis-1",
                            "yScaleID": "y-axis-1",
                            "xMin": 0.07,
                            "xMax": 0.93,
                            "yMin": 0.72,
                            "yMax": 0.94,
                            "backgroundColor": "rgba(255,255,255,0.90)",
                            "borderColor": "rgba(22,138,87,0.75)",
                            "borderWidth": 2,
                            "cornerRadius": 28,
                            "label": {
                                "enabled": True,
                                "content": title_lines,
                                "fontSize": 28,
                                "fontStyle": "bold",
                                "fontColor": "#168A57",
                                "position": "center",
                            },
                        }
                    }
                }
            },
        },
    }

    from urllib.parse import quote
    encoded = quote(json.dumps(config, ensure_ascii=False, separators=(",", ":")), safe="")
    return (
        "https://quickchart.io/chart"
        "?width=1080&height=1080&devicePixelRatio=1"
        "&format=jpg&version=2.9.4&backgroundColor=white&c=" + encoded
    )
'''

s = s[:start] + new_func + s[end:]
# Remove somente a antiga linha de banner 10.6. O banner 10.7 permanece.
s = s.replace('\nprint("VERSÃO 10.6 ATIVA: Instagram com arte JPEG + título | Facebook + Telegram preservados")\nselfbot.main()', '\nselfbot.main()')
P.write_text(s, encoding="utf-8")
