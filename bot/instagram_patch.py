from pathlib import Path

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")

start = s.index("def instagram_art_url(post):")
end = s.index("\ndef instagram_promote", start)

fn = r'''
def instagram_art_url(post):
    """
    Instagram 12.11 — versão limpa
    - Imagem original de fundo
    - Sem faixa preta
    - Sem marca d'água / logo
    - Texto todo em amarelo queimado (#E8A317)
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

    config = f"""{{
      type: 'bar',
      data: {{
        labels: [''],
        datasets: [{{
          data: [0],
          backgroundColor: 'rgba(0,0,0,0)',
          borderWidth: 0
        }}]
      }},
      options: {{
        responsive: false,
        animation: false,
        maintainAspectRatio: false,
        legend: {{ display: false }},
        layout: {{
          padding: {{
            top: 0,
            right: 50,
            bottom: 55,
            left: 50
          }}
        }},
        scales: {{
          xAxes: [{{ display: false }}],
          yAxes: [{{ display: false }}]
        }},
        plugins: {{
          backgroundImageUrl: {image_js}
        }},
        title: {{
          display: true,
          position: 'bottom',
          text: {text_js},
          fontSize: 36,
          fontStyle: 'bold',
          fontColor: '#E8A317',
          padding: 32
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

# Atualiza versões
for old in ["12.10", "12.9", "12.8", "12.7", "12.6", "12.5", "12.4", "12.3", "12.2", "12.1"]:
    s = s.replace(f"VERSÃO {old}", "VERSÃO 12.11")
    s = s.replace(f"Instagram {old}", "Instagram 12.11")

s = s.replace("VERSÃO 12.1 ATIVA", "VERSÃO 12.11 ATIVA")

p.write_text(s, encoding="utf-8")

print("Patch Instagram 12.11 aplicado com sucesso.")
