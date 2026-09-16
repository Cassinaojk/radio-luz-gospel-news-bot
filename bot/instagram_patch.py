def instagram_art_url(post):
    """
    Instagram 12.16
    - Texto dentro de retângulo com cantos arredondados
    - Fundo levemente transparente (azul) + borda azul
    - Texto amarelo queimado (#E8A317) sem cortar
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

    # Quebra inteligente do título (evita cortar palavras)
    words = title.split()
    first = " ".join(words[:5])
    rest = " ".join(words[5:])

    lines = [first]
    if rest:
        extra = _instagram_wrap_text(rest, max_chars=28, max_lines=3)
        lines.extend(extra)
    lines = lines[:4]

    # =========================================================
    # Overlay: retângulo arredondado + borda azul + texto
    # =========================================================
    config = {
        "type": "bar",
        "data": {
            "labels": [""],
            "datasets": [{
                "data": [100],
                "backgroundColor": "rgba(12, 35, 85, 0.58)",   # azul escuro leve transparência
                "borderColor": "#3B82F6",                      # borda azul
                "borderWidth": 4,
                "barPercentage": 0.92,
                "categoryPercentage": 0.92
            }]
        },
        "options": {
            "responsive": False,
            "animation": False,
            "maintainAspectRatio": False,
            "legend": {"display": False},
            "layout": {
                "padding": {
                    "top": 300,      # empurra o retângulo para baixo
                    "right": 48,
                    "bottom": 55,
                    "left": 48
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
            "plugins": {
                "roundedBars": {
                    "cornerRadius": 22,
                    "allCorners": True
                }
            },
            "title": {
                "display": True,
                "position": "bottom",
                "text": lines,
                "fontSize": 32,
                "fontStyle": "bold",
                "fontColor": "#E8A317",
                "padding": 16
            }
        }
    }

    config_json = json.dumps(config, ensure_ascii=False, separators=(",", ":"))

    overlay_url = (
        "https://quickchart.io/chart"
        "?width=1080"
        "&height=540"
        "&devicePixelRatio=1"
        "&format=png"
        "&version=2.9.4"
        "&backgroundColor=rgba(0,0,0,0)"
        "&c=" + quote(config_json)
    )

    LOGO_URL = (
        "https://blogger.googleusercontent.com/img/b/R29vZ2xl/"
        "AVvXsEg3P-t5wYd2jLgZzAE_p2h7p6F20af81jpj436lFfjtX1h3B3P90clzdyG0G5kLTS0bgGsV8q3pcoUgfNHMeeOa_EM6jo21Yj50qBEtLjPq7tlS2Nla7aB4k_PqvTUPYBkn0m2obR4hgGOgP864KuHskzNEjUoBjUpntnwhYMJNVZYThote-ENKHftfGPAl/"
        "w900-h562-p-k-no-nu/1000008407.png"
    )

    # 1) Coloca o retângulo + texto na parte de baixo
    with_text = (
        "https://quickchart.io/watermark"
        "?mainImageUrl=" + quote(image_url, safe="")
        + "&markImageUrl=" + quote(overlay_url, safe="")
        + "&markRatio=1"
        + "&position=bottomMiddle"
        + "&margin=10"
    )

    # 2) Logo bem pequeno abaixo do retângulo
    final_url = (
        "https://quickchart.io/watermark"
        "?mainImageUrl=" + quote(with_text, safe="")
        + "&markImageUrl=" + quote(LOGO_URL, safe="")
        + "&markRatio=0.10"
        + "&position=bottomMiddle"
        + "&margin=6"
    )

    return final_url
