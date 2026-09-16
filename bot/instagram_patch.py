from pathlib import Path

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")

start = s.index("def instagram_art_url(post):")
end = s.index("\ndef instagram_promote", start)

fn = r'''
def instagram_art_url(post):
    """
    Instagram 12.15
    - Texto dentro de retângulo com cantos arredondados
    - Fundo levemente transparente + bordas azuladas
    - Texto amarelo queimado (#E8A317)
    - Logo pequeno da rádio abaixo do retângulo
    - Tudo na parte inferior da imagem
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

    # Quebra inteligente do título
    words = title.split()
    first = " ".join(words[:5])
    rest = " ".join(words[5:])

    lines = [first]
    if rest:
        extra = _instagram_wrap_text(rest, max_chars=26, max_lines=3)
        lines.extend(extra)
    lines = lines[:4]

    # =========================================================
    # 1) Overlay do texto com fundo semi-transparente
    #    (simula o retângulo arredondado)
    # =========================================================
    config = {
        "type": "bar",
        "data": {
            "labels": [""],
            "datasets": [{
                "data": [100],
                "backgroundColor": "rgba(15, 40, 90, 0.55)",  # azul escuro semi-transparente
                "borderWidth": 0,
                "barPercentage": 1.0,
                "categoryPercentage": 1.0
            }]
        },
        "options": {
            "responsive": False,
            "animation": False,
            "maintainAspectRatio": False,
            "legend": {"display": False},
            "layout": {
                "padding": {
                    "top": 280,
                    "right": 55,
                    "bottom": 70,
                    "left": 55
                }
            },
            "scales": {
                "xAxes": [{"display": False, "stacked": True}],
                "yAxes": [{
                    "display": False,
                    "stacked": True,
                    "ticks": {"min": 0, "max": 100}
                }]
            },
            "title": {
                "display": True,
                "position": "bottom",
                "text": lines,
                "fontSize": 34,
                "fontStyle": "bold",
                "fontColor": "#E8A317",
                "padding": 18
            }
        }
    }

    config_json = json.dumps(config, ensure_ascii=False, separators=(",", ":"))

    overlay_url = (
        "https://quickchart.io/chart"
        "?width=1080"
        "&height=520"
        "&devicePixelRatio=1"
        "&format=png"
        "&version=2.9.4"
        "&backgroundColor=rgba(0,0,0,0)"
        "&c=" + quote(config_json)
    )

    # =========================================================
    # 2) Logo pequeno da rádio (marque d'água)
    #    Substitua a URL abaixo pela URL pública do seu logo
    # =========================================================
    LOGO_URL = "https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEg3P-t5wYd2jLgZzAE_p2h7p6F20af81jpj436lFfjtX1h3B3P90clzdyG0G5kLTS0bgGsV8q3pcoUgfNHMeeOa_EM6jo21Yj50qBEtLjPq7tlS2Nla7aB4k_PqvTUPYBkn0m2obR4hgGOgP864KuHskzNEjUoBjUpntnwhYMJNVZYThote-ENKHftfGPAl/w900-h562-p-k-no-nu/1000008407.png"
    # Primeiro coloca o texto (retângulo) na parte de baixo
    with_text = (
        "https://quickchart.io/watermark"
        "?mainImageUrl=" + quote(image_url, safe="")
        + "&markImageUrl=" + quote(overlay_url, safe="")
        + "&markRatio=1"
        + "&position=bottomMiddle"
        + "&margin=12"
    )

    # Depois adiciona o logo bem pequeno abaixo do texto
    final_url = (
        "https://quickchart.io/watermark"
        "?mainImageUrl=" + quote(with_text, safe="")
        + "&markImageUrl=" + quote(LOGO_URL, safe="")
        + "&markRatio=0.11"          # tamanho bem pequeno
        + "&position=bottomMiddle"
        + "&margin=8"
    )

    return final_url
'''

s = s[:start] + fn + s[end:]

# Atualiza versões
for old in ["12.14", "12.13", "12.12", "12.11", "12.10", "12.9", "12.8", "12.7", "12.6", "12.5", "12.4", "12.3", "12.2", "12.1"]:
    s = s.replace(f"VERSÃO {old}", "VERSÃO 12.15")
    s = s.replace(f"Instagram {old}", "Instagram 12.15")

s = s.replace("VERSÃO 12.1 ATIVA", "VERSÃO 12.15 ATIVA")

p.write_text(s, encoding="utf-8")

print("Patch Instagram 12.15 aplicado com sucesso.")
