from pathlib import Path

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")

start = s.index("def instagram_art_url(post):")
end = s.index("\ndef instagram_promote", start)

fn = r'''
def instagram_art_url(post):
    """
    Instagram 12.3
    Uma única renderização QuickChart.
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
            or ""
        ).strip()
    )

    if not image_url or not title:
        return image_url

    words = title.split()

    first_line = " ".join(words[:4])
    remaining = " ".join(words[4:])

    lines = [first_line]

    if remaining:
        extra = _instagram_wrap_text(
            remaining,
            max_chars=26,
            max_lines=3
        )
        lines.extend(extra)

    text_js = json.dumps(lines, ensure_ascii=False)
    image_js = json.dumps(image_url, ensure_ascii=False)

    config = f"""{{
      type:'bar',
      data:{{
        labels:[''],
        datasets:[{{data:[0]}}]
      }},
      options:{{
        responsive:false,
        animation:false,
        maintainAspectRatio:false,
        legend:{{display:false}},
        scales:{{
          xAxes:[{{display:false}}],
          yAxes:[{{display:false}}]
        }},
        plugins:{{
          backgroundImageUrl:{image_js}
        }},
        title:{{
          display:true,
          position:'bottom',
          text:{text_js},
          fontSize:30,
          fontStyle:'bold',
          fontColor:'#FFFFFF',
          padding:35
        }}
      }}
    }}"""

    return (
        "https://quickchart.io/chart"
        "?width=1080"
        "&height=1080"
        "&devicePixelRatio=1"
        "&format=png"
        "&version=2.9.4"
        "&backgroundColor=transparent"
        "&c=" + quote(config)
    )
'''

s = s[:start] + fn + s[end:]

s = s.replace("VERSÃO 12.2", "VERSÃO 12.3")

p.write_text(s, encoding="utf-8")

print("Patch Instagram 12.3 aplicado com sucesso.")