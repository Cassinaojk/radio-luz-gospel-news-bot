# Rádio Luz Gospel — Robô de Notícias 13.0

Robô GitHub Actions para coletar notícias de fontes gospel, gerar matérias originais em português do Brasil com IA e publicar no Blogger.

## Principais mudanças da versão 13.0

- **Filtro de data rigoroso**: o robô só aceita notícias publicadas **hoje**. Qualquer notícia de ontem ou mais antiga é descartada automaticamente.
- **Anti-duplicidade em duas camadas**:
  1. **Antes da IA**: consulta a API de busca do Blogger para verificar se já existe um post com as palavras-chave da notícia (ex: nome do artista, evento). Se sim, pula para a próxima notícia da fila.
  2. **Depois da IA**: compara o título gerado com os títulos já publicados (similaridade de palavras e entidades).
- **Fingerprint de conteúdo**: para notícias que já estão no blog, o robô extrai entidades (nomes próprios, bandas, versões) e vocabulário raro para comparação profunda.
- **Limpeza opcional** (`CLEAN_DUPLICATES=true`): detecta posts duplicados já publicados e os marca como rascunho, mantendo o mais recente.
- **Divulgação social integrada**: Telegram, Facebook e Instagram agora rodam diretamente no `main.py`, sem necessidade de patch separado.

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
- Canal do Telegram divulgado ao final do post (link configurável via `TELEGRAM_CHANNEL_URL`).

## Filtro musical
O robô usa uma lista de **termos fortes** (`lancamento`, `single`, `álbum`, `show`, `turnê`, `louvor`, `worship`, etc.) e **termos de suporte** (`cantor`, `banda`, `gravadora`, `compositor`, etc.) para decidir se uma notícia é musical.
- Se houver dúvida, a regra é **publicar**.
- Posts musicais recebem a label `Músicas`; os demais ficam apenas com `Notícias` e `Rádio Luz Gospel`.

## Filtro de data
- **`MAX_AGE_DAYS = 0`**: só aceita notícias publicadas **hoje**.
- Notícias antigas são descartadas antes mesmo de chamar a IA, economizando chamadas e evitando publicações fora do prazo.

## Originalidade
A verificação bloqueia apenas sinais fortes de reprodução literal:
- sequência de **15 palavras ou mais** idênticas à fonte;
- sobreposição de **8-grams acima de 12%**.

## Anti-duplicidade
Além da originalidade em relação à fonte, o robô bloqueia publicações repetidas no blog por:

1. **API do Blogger (`check_blogger_for_duplicate`)**: busca no próprio blog se já existe post com as mesmas palavras-chave principais da notícia. Roda **antes** da IA, economizando chamadas e tempo.
2. **Similaridade de título (`is_duplicate_story`)**: depois que a IA gera o título, compara com os títulos já publicados por:
   - Jaccard de palavras (≥ 0.55);
   - Entidades nomeadas em comum (≥ 2 fortes);
   - Fingerprint de vocabulário raro (≥ 40% em comum).

Se qualquer camada detectar duplicata, a notícia é **ignorada** e o robô passa para a próxima da fila.

## Divulgação social
Controlada por variáveis de ambiente. Quando ativada, o robô divulga automaticamente no:
- **Telegram** (`PROMO_ENABLED=true`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)
- **Facebook** (`FACEBOOK_ENABLED=true`, `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN`)
- **Instagram** (`INSTAGRAM_ENABLED=true`, `INSTAGRAM_USER_ID`, `INSTAGRAM_ACCESS_TOKEN`)

O Instagram exige uma **arte obrigatória** gerada via QuickChart com a imagem da matéria; se a arte não estiver disponível, a publicação é cancelada para preservar a regra visual.

## Limpeza de duplicatas já publicadas
Para limpar duplicatas antigas, execute uma vez com:
