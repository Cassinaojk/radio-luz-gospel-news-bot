# Rádio Luz Gospel — Robô de Notícias 15.0

Robô GitHub Actions para coletar notícias de fontes gospel, gerar matérias originais em português do Brasil com IA e publicar no Blogger.

## Principais mudanças da versão 15.0

- **Divulgação via Telegram**: O robô envia as notícias publicadas diretamente para o canal do Telegram. O suporte ao Instagram e Facebook foi temporariamente removido.
- **Filtro de data flexível**: o robô aceita notícias publicadas nos últimos **4 dias**, o que cobre fusos horários e feeds com atraso.
- **Anti-duplicidade via API**: consulta a API de busca do Blogger para verificar se já existe um post com título muito similar antes de publicar.
- **Scraping HTML**: além dos feeds RSS, o robô lê a página inicial dos sites para capturar notícias que não aparecem no feed.

## Fontes ativas (5)

| Fonte | URL base |
|---|---|
| News Gospel | https://www.newsgospel.com.br/ |
| Folha Gospel — Música | https://folhagospel.com/musica/ |
| Guiame — Música | https://guiame.com.br/musica |
| iGospel | https://www.igospel.org.br/ |
| Fuxico Gospel | https://www.fuxicogospel.com.br/ |

## IA (provedores em ordem de fallback)
1. **Gemini** — modelo principal `gemini-3.5-flash-lite`
2. **Gemini-2** — modelo fallback `gemini-3.6-flash`
3. **Groq** — modelo `openai/gpt-oss-20b`
4. **Mistral** — modelo `mistral-small-latest`

- Até **6 chamadas de texto por execução** (`MAX_GEMINI_TEXT_CALLS_PER_RUN=6`).
- Ao detectar quota/limite em um provedor, o robô passa automaticamente para o próximo.

## Publicação
- Até **2 matérias por execução** (`MAX_POSTS_PER_RUN=2`).
- Imagem do post vem de uma **sequência cíclica de 12 imagens** em `bot/Imagens/`.
- Canal do Telegram divulgado ao final do post.

## Divulgação social
Controlada por variáveis de ambiente. Quando ativada, o robô divulga automaticamente no:
- **Telegram** (`PROMO_ENABLED=true`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)
