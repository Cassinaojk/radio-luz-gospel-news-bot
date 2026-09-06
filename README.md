# Rádio Luz Gospel — Robô de Notícias 9.0

Robô de coleta, redação e publicação automática de notícias no Blogger.

## Fontes
- News Gospel
- UAU Gospel
- Folha Gospel — somente Música
- Guiame — somente Música

## Publicação
- Até 3 matérias por execução
- Execuções automáticas às 08:00, 14:00 e 20:00 (horário de Brasília)
- Rótulos: `Notícias` e `Rádio Luz Gospel`

## Gemini
- Principal: `gemini-3.5-flash-lite`
- Alternativo: `gemini-3.6-flash`
- Limite de 6 chamadas de texto por execução
- Ao detectar quota/429, encerra a execução do Gemini sem repetir o mesmo modelo

## Originalidade
A matéria é verificada antes da publicação. O bloqueio prioriza cópia literal de sequências longas e sobreposição de 8-gramas; a similaridade global é usada apenas como sinal complementar, para evitar bloquear notícias legítimas sobre o mesmo fato.

## Fonte da apuração
O post publicado mostra apenas `Fonte de apuração: Nome da fonte`. A URL da matéria de origem fica em comentário HTML invisível para permitir deduplicação nas próximas execuções.
