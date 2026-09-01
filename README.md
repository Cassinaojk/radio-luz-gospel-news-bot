# Rádio Luz Gospel — Robô de Notícias

Coleta notícias por RSS, evita duplicações, gera matérias originais com IA e publica no WordPress pela REST API.

Fluxo: RSS → filtro → IA → validação → WordPress.

O GitHub Actions executa 3 vezes por dia no horário de São Paulo.

## Configuração inicial

Por segurança, `WP_POST_STATUS` deve começar como `draft`. Faça 1 ou 2 testes e depois altere para `publish`.

### Secrets do GitHub

Em Settings → Secrets and variables → Actions:

- `WP_URL` = https://radioluzgospel.22web.org
- `WP_USERNAME` = seu usuário WordPress
- `WP_APP_PASSWORD` = Application Password do robô
- `GEMINI_API_KEY` = chave da API Gemini

### Variables opcionais

- `GEMINI_MODEL` = modelo disponível na sua conta (padrão: gemini-2.5-flash)
- `WP_POST_STATUS` = draft ou publish

## Horários

08:00, 14:00 e 20:00 em `America/Sao_Paulo`.

## Instalação

1. Crie um repositório no GitHub.
2. Envie estes arquivos.
3. Configure os Secrets.
4. Execute o workflow manualmente.
5. Confira o rascunho no WordPress.
6. Depois defina `WP_POST_STATUS=publish`.

Nunca coloque a senha principal do WordPress ou a chave Gemini dentro do código.
