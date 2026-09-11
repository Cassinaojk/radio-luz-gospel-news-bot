from pathlib import Path
import re

p = Path("bot/main.py")
s = p.read_text(encoding="utf-8")

# Mantém o log enxuto: a alteração da arte não precisa aparecer como uma
# versão extra no início da execução.
s = s.replace('print("VERSÃO 10.6 ATIVA: Instagram com arte JPEG + título | Facebook + Telegram preservados")\n', '')
s = s.replace('print("VERSÃO 10.7 ATIVA: Instagram com arte JPEG via Watermark API + título | Facebook + Telegram preservados")\n', '')

start = s.index("def instagram_art_url(post):")
end = s.index("\ndef instagram_promote", start)

fn = r'''def instagram_art_url(post):
    """Mantém a foto original e acrescenta apenas a faixa arredondada com título."""
    image_url = social_image_url(post)
    title = re.sub(r"\s+", " ", (post.get("title") or "").strip())
    if not image_url or not title:
        return image_url

    # Quebra o título em até três linhas, como no modelo aprovado.
    words = title.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > 34:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)

    if len(lines) > 3:
        lines = lines[:3]
        lines[-1] = lines[-1][:30].rstrip() + "..."

    title_text = "\\n".join(lines or [title[:34]])

    # Uma única renderização do QuickChart: a foto original fica como fundo
    # e o plugin de data labels desenha somente o elemento arredondado sobre ela.
    # Não usamos Watermark API encadeada, pois isso adicionava outra etapa de
    # carregamento e era a origem dos HTTP 400/timeout em alguns casos.
    from urllib.parse import quote
    image_js = json.dumps(image_url, ensure_ascii=False)
    title_js = json.dumps(title_text, ensure_ascii=False)

    chart_config = (
        "{type:'scatter',"
        "data:{datasets:[{data:[{x:50,y:14}],pointRadius:0,"
        "pointBackgroundColor:'transparent',borderWidth:0}]},"
        "options:{responsive:false,animation:false,maintainAspectRatio:false,"
        "legend:{display:false},tooltips:{enabled:false},"
        "scales:{"
        "xAxes:[{display:false,ticks:{min:0,max:100},gridLines:{display:false}}],"
        "yAxes:[{display:false,ticks:{min:0,max:100},gridLines:{display:false}}]"
        "},"
        "plugins:{"
        "backgroundImageUrl:" + image_js + ","
        "datalabels:{"
        "display:true,"
        "formatter:function(){return " + title_js + ";},"
        "color:'#0B4F34',"
        "font:{size:28,weight:'bold'},"
        "backgroundColor:'rgba(255,255,255,0.88)',"
        "borderColor:'#168A57',"
        "borderWidth:3,"
        "borderRadius:38,"
        "padding:{top:18,bottom:18,left:30,right:30},"
        "anchor:'center',align:'center',offset:0,clip:false"
        "}"
        "}"
        "}"
        "}"
    )

    return (
        "https://quickchart.io/chart"
        "?width=1080&height=1080&devicePixelRatio=1"
        "&format=jpg&version=2.9.4&backgroundColor=white&c="
        + quote(chart_config, safe="")
    )
'''

s = s[:start] + fn + s[end:]
p.write_text(s, encoding="utf-8")
