from pathlib import Path

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")

start = s.index("def instagram_art_url(post):")
end = s.index("\ndef instagram_promote", start)

fn = r'''
def instagram_art_url(post):
    """
    Instagram 12.8
    - Imagem original de fundo
    - Faixa escura limpa embaixo
    - Texto branco em negrito
    - Logo Rádio Luz Gospel pequena no canto superior esquerdo (marca d'água)
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
        extra = _instagram_wrap_text(rest, max_chars=30, max_lines=3)
        lines.extend(extra)

    lines = lines[:4]

    text_js = json.dumps(lines, ensure_ascii=False)
    image_js = json.dumps(image_url, ensure_ascii=False)

    # 1) Gera a arte principal (imagem + faixa + texto)
    config = f"""{{
      type: 'bar',
      data: {{
        labels: [''],
        datasets: [{{
          data: [100],
          backgroundColor: 'rgba(0,0,0,0.62)',
          borderWidth: 0,
          barPercentage: 1.0,
          categoryPercentage: 1.0
        }}]
      }},
      options: {{
        responsive: false,
        animation: false,
        maintainAspectRatio: false,
        legend: {{ display: false }},
        layout: {{
          padding: {{
            top: 680,
            right: 0,
            bottom: 0,
            left: 0
          }}
        }},
        scales: {{
          xAxes: [{{
            display: false,
            stacked: true,
            gridLines: {{ display: false }},
            ticks: {{ display: false }}
          }}],
          yAxes: [{{
            display: false,
            stacked: true,
            gridLines: {{ display: false }},
            ticks: {{ min: 0, max: 100, display: false }}
          }}]
        }},
        plugins: {{
          backgroundImageUrl: {image_js}
        }},
        title: {{
          display: true,
          position: 'bottom',
          text: {text_js},
          fontSize: 32,
          fontStyle: 'bold',
          fontColor: '#FFFFFF',
          padding: 36
        }}
      }}
    }}"""

    art_url = (
        "https://quickchart.io/chart"
        "?width=1080"
        "&height=1080"
        "&devicePixelRatio=1"
        "&format=png"
        "&version=2.9.4"
        "&backgroundColor=transparent"
        "&c=" + quote(config)
    )

    # 2) Adiciona a logo pequena no canto superior esquerdo
    logo_url = "https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjOn_KbSB2d3wtQA7oX6Q5S3Qg00w8xBGAdbaBvw-iTtZfPXykSXpDVZAO7xqGnWDT_ZVoVkMAoQEdkksEsG8whpKtu8m6axc3GTkcFALoq787DiXvDLbaoYsOrqgML7euwDQnYwchQA9_4D2eZbXkvU5Rf5rxFKo_xgKDMNHTQfYpGZLqXJ806YWHgtWjq/s320/radio%20luz%20gospel.png"

    final_url = (
        "https://quickchart.io/watermark"
        "?mainImageUrl=" + quote(art_url, safe="")
        + "&markImageUrl=" + quote(logo_url, safe="")
        + "&markRatio=0.18"          # tamanho pequeno
        + "&position=topLeft"
        + "&margin=28"               # afastamento das bordas
        + "&opacity=0.92"
    )

    return final_url
'''

s = s[:start] + fn + s[end:]

# Atualiza versões
for old in ["12.7", "12.6", "12.5", "12.4", "12.3", "12.2", "12.1"]:
    s = s.replace(f"VERSÃO {old}", "VERSÃO 12.8")
    s = s.replace(f"Instagram {old}", "Instagram 12.8")

s = s.replace("VERSÃO 12.1 ATIVA", "VERSÃO 12.8 ATIVA")

p.write_text(s, encoding="utf-8")

print("Patch Instagram 12.8 aplicado com sucesso.")
