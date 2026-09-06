# Rádio Luz Gospel — Robô de Notícias 9.1 FINAL

Robô GitHub Actions para coletar notícias de fontes gospel, gerar matérias originais em português do Brasil com Gemini e publicar no Blogger.

## Fontes
- News Gospel
- UAU Gospel
- Folha Gospel — Música
- Guiame — Música

## Gemini
- Modelo principal: `gemini-3.5-flash-lite`
- Fallback: `gemini-3.6-flash`
- Até 6 chamadas de texto por execução.
- Ao detectar quota/limite, a execução para sem repetir chamadas inúteis.

## Originalidade
A 9.1 não usa similaridade global como motivo isolado para bloquear uma matéria. O bloqueio ocorre somente quando há sinais fortes de reprodução literal: uma sequência longa de palavras idênticas ou sobreposição elevada de blocos de 8 palavras.

## Publicação
- Até 3 matérias por execução.
- Deduplicação por fonte/URL.
- A fonte aparece no artigo como `Fonte de apuração: ...`, sem URL visível.
- A URL fica registrada em comentário HTML invisível para controle interno.

## Agendamento
08:00, 14:00 e 20:00 no horário de Brasília (America/Sao_Paulo), usando cron UTC: 11:00, 17:00 e 23:00.

## Secrets necessários
`BLOGGER_BLOG_ID`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `BLOGGER_REFRESH_TOKEN`, `GEMINI_API_KEY`.
