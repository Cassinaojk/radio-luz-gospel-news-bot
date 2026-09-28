# Rádio Luz Gospel — Robô de Notícias 12.50

Robô GitHub Actions para coletar notícias de fontes gospel, gerar matérias originais em português do Brasil com IA e publicar no Blogger.

## Fontes ativas (8)

| Fonte | URL base | Feed principal |
|---|---|---|
| Fuxico Gospel | https://www.fuxicogospel.com.br/ | `feed/` |
| News Gospel | https://www.newsgospel.com.br/ | `feed/` |
| Folha Gospel — Música | https://folhagospel.com/musica/ | `feed/` |
| Guiame — Música | https://guiame.com.br/musica | `rss.xml` |
| Gospel Mais | https://gospelmais.com/ | `feed/` |
| Exibir Gospel | https://exibirgospel.com.br/ | `feed/` |
| iGospel | https://www.igospel.org.br/ | `feed/` |
| NT Gospel | https://ntgospel.com/ | `feed/` |

## IA (provedores em ordem de fallback)
1. **Gemini** — modelo principal `gemini-3.5-flash-lite`
2. **Gemini-2** — modelo fallback `gemini-3.6-flash`
3. **Groq** — modelo `openai/gpt-oss-20b`
4. **Mistral** — modelo `mistral-small-latest`

- Até **6 chamadas de texto por execução** (`MAX_GEMINI_TEXT_CALLS_PER_RUN=6`).
- Ao detectar quota/limite em um provedor, o robô passa automaticamente para o próximo.
- Se todos os provedores atingirem quota, a execução para e o restante fica para a próxima.

## Publicação
- Até **1 matéria por execução** (`MAX_POSTS_PER_RUN=1`).
- Deduplicação por URL da fonte e por URL do blog.
- Imagem do post vem de uma **sequência cíclica de 12 imagens** em `bot/Imagens/` (`radioluzgospel1` a `radioluzgospel12`), escolhida com base no total de posts já publicados pelo robô.
- A fonte fica registrada em comentário HTML invisível (`RADIO_LUZ_GOSPEL_SOURCE_URL`) para controle interno.
- Spotify embed aparece após o 2º parágrafo da matéria.

## Filtro musical
O robô usa uma lista de **termos fortes** (`lancamento`, `single`, `álbum`, `show`, `turnê`, `louvor`, `worship`, etc.) e **termos de suporte** (`cantor`, `banda`, `gravadora`, `compositor`, etc.) para decidir se uma notícia é musical.
- Se houver dúvida, a regra é **publicar**.
- Posts musicais recebem a label `Músicas`; os demais ficam apenas com `Notícias` e `Rádio Luz Gospel`.

## Originalidade
A verificação bloqueia apenas sinais fortes de reprodução literal:
- sequência de **15 palavras ou mais** idênticas à fonte;
- sobreposição de **8-grams acima de 12%**.

## Divulgação social
Controlada por variáveis de ambiente. Quando ativada, o robô divulga automaticamente no:
- **Telegram** (`PROMO_ENABLED=true`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)
- **Facebook** (`FACEBOOK_ENABLED=true`, `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN`)
- **Instagram** (`INSTAGRAM_ENABLED=true`, `INSTAGRAM_USER_ID`, `INSTAGRAM_ACCESS_TOKEN`)

O Instagram exige uma **arte obrigatória** gerada via QuickChart com a imagem da matéria; se a arte não estiver disponível, a publicação é cancelada para preservar a regra visual.

## Secrets necessários
- `BLOGGER_BLOG_ID`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `BLOGGER_REFRESH_TOKEN`
- `GEMINI_API_KEY`

### Secrets opcionais
- `GEMINI_API_KEY_2` (segunda chave Gemini)
- `GROQ_API_KEY`
- `MISTRAL_API_KEY`
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
- `FACEBOOK_PAGE_ID` / `FACEBOOK_PAGE_ACCESS_TOKEN`
- `INSTAGRAM_USER_ID` / `INSTAGRAM_ACCESS_TOKEN`

## Variáveis de ambiente opcionais
- `VERBOSE_LOG=true` — ativa log detalhado
- `MAX_POSTS_PER_RUN` — padrão `1`
- `MAX_GEMINI_TEXT_CALLS_PER_RUN` — padrão `6`
- `GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL`
- `GROQ_MODEL` / `MISTRAL_MODEL`
- `PROMO_ENABLED=true` — ativa divulgação social
- `TELEGRAM_CHANNEL_URL` — URL do canal exibido no post
