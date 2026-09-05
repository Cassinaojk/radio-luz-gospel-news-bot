# Rádio Luz Gospel — Robô de Notícias

Automação para coletar notícias gospel, gerar uma matéria original com Gemini e publicar no Blogger.

## Funcionamento

O GitHub Actions executa 3 vezes por dia:

- 08:00
- 14:00
- 20:00

Horário de São Paulo (`America/Sao_Paulo`).

Cada execução tenta publicar **uma única notícia**. Assim, o objetivo é até 3 publicações por dia sem gastar três chamadas Gemini na mesma execução.

## Gemini

Modelo principal padrão:

`gemini-3.5-flash-lite`

Fallback:

`gemini-3.6-flash`

O robô não fica repetindo uma chamada quando recebe `429 RESOURCE_EXHAUSTED`; ele tenta o modelo alternativo. Erros temporários 5xx continuam usando retry.

## GitHub Secrets

Em Settings → Secrets and variables → Actions → Secrets:

- `BLOGGER_BLOG_ID`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `BLOGGER_REFRESH_TOKEN`
- `GEMINI_API_KEY`

## GitHub Variables opcionais

Em Settings → Secrets and variables → Actions → Variables:

- `GEMINI_MODEL` — padrão: `gemini-3.5-flash-lite`
- `GEMINI_FALLBACK_MODEL` — padrão: `gemini-3.6-flash`

Não coloque chaves ou tokens no código.
