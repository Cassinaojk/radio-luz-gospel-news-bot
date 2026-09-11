from pathlib import Path
import re

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")
s = s.replace('print("VERSÃO 10.6 ATIVA: Instagram com arte JPEG + título | Facebook + Telegram preservados")\n', '')

start = s.index("def instagram_art_url(post):")
end = s.index("\ndef instagram_promote", start)

fn = r'''def instagram_art_url(post):
    """Gera a arte 1080x1080 com a foto original e uma faixa discreta no rodapé."""
    image_url = social_image_url(post)
    title = re.sub(r"\s+", " ", (post.get("title") or "").strip())
    if not image_url or not title:
        return image_url

    words = title.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > 36:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > 3:
        lines = lines[:3]
        lines[-1] = lines[-1][:33].rstrip() + "..."
    title_lines = lines or [title[:36]]

    config = {
        "type": "bar",
        "data": {
            "labels": [""],
            "datasets": [{"data": [0], "backgroundColor": "rgba(0,0,0,0)"}],
        },
        "options": {
            "responsive": False,
            "animation": False,
            "maintainAspectRatio": False,
            "legend": {"display": False},
            "layout": {"padding": 0},
            "scales": {
                "xAxes": [{
                    "display": False,
                    "ticks": {"min": 0, "max": 100},
                    "gridLines": {"display": False},
                }],
                "yAxes": [{
                    "display": False,
                    "ticks": {"min": 0, "max": 100},
                    "gridLines": {"display": False},
                }],
            },
            "annotation": {
                "annotations": [{
                    "type": "box",
                    "drawTime": "afterDatasetsDraw",
                    "xScaleID": "x-axis-0",
                    "yScaleID": "y-axis-0",
                    "xMin": 7,
                    "xMax": 93,
                    "yMin": 7,
                    "yMax": 31,
                    "backgroundColor": "rgba(255,255,255,0.90)",
                    "borderColor": "rgba(22,138,87,0.95)",
                    "borderWidth": 3,
                    "label": {
                        "enabled": True,
                        "content": title_lines,
                        "position": "center",
                        "backgroundColor": "rgba(255,255,255,0)",
                        "fontColor": "#168A57",
                        "fontSize": 28,
                        "fontStyle": "bold",
                        "padding": 8,
                    },
                }],
            },
            "plugins": {
                "backgroundImageUrl": image_url,
            },
        },
    }

    from urllib.parse import quote
    config_json = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
    return (
        "https://quickchart.io/chart"
        "?width=1080&height=1080&devicePixelRatio=1"
        "&format=jpg&version=2.9.4&backgroundColor=white&c="
        + quote(config_json, safe="")
    )
'''

s = s[:start] + fn + s[end:]
p.write_text(s, encoding="utf-8")
