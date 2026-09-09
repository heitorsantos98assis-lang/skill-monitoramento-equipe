---
name: skill-monitoramento-equipe-monitoramento-equipe
description: "Monitora atendentes do WhatsApp em tempo real e gera boletim diario/semanal da equipe."
---

## Compatibilidade Codex

Leia primeiro as instruções `AGENTS.md` aplicáveis e inspecione a stack real do projeto. Preserve escolhas explícitas do usuário e convenções existentes. As tecnologias citadas abaixo são preferências do material de origem, não autorização para substituir a stack atual.

Use as ferramentas disponíveis no Codex. Não presuma nomes de ferramentas do Codex, não exponha segredos e não execute publicação, envio, exclusão ou mudanças externas sem a autorização apropriada.

# Skill — Monitoramento de Equipe

Le o historico de mensagens do WhatsApp da operacao e devolve:

1. **Boletim diario** — quem ta online, ranking de TPR, paradas, mensagens criticas, distribuicao de carga, proximos passos.
2. **Analise semanal** — sparkline diario por atendente, heatmap de demanda hora×dia, SLA por janela horaria, comparativo 7d vs 7d anteriores, alertas de tendencia.

Desenhado para **operacoes com 2+ atendentes** dividindo um numero (ou mais) de WhatsApp.

## O que diferencia essa skill

- **Mediana, nao media** — um pico de 3h nao envenena o TPR de quem teve 90% das respostas em 2min.
- **Detecta palavras criticas** — "cancelar", "lixo", "concorrente", "urgente" — e marca a conversa parada com tag inline.
- **SLA por janela** — separa o que aconteceu em horario comercial (9-18 dia util) do resto.
- **Distribuicao real de carga** — quem efetivamente pegou a primeira mensagem de cada novo cliente (e nao so quem respondeu mais).
- **Heatmap ASCII** — pico de demanda em dia/hora, util pra escalar turno.
- **Alerta de tendencia** — se um atendente piorou ≥50% na 2a metade da semana, voce ve isso antes do cliente reclamar.
- **Aceita 3 formatos de input** — CSV, .txt do WhatsApp Business, JSON da Zappfy. Tem conversor pra cada um.
- **Fecha o ciclo** — script de envio Zappfy ja incluido. Cron pronto.

## Quando usar

- **Gestor manha:** rodar `analisar_semana` antes da reuniao semanal.
- **Gestor meio-dia / final de tarde:** rodar `analisar_equipe` (boletim do dia).
- **Dono manha do dia seguinte:** combinar com a skill `relatorio-diario` (Bonus 9) — uma fala do time, outra fala do negocio.
- **Pos-evento (lancamento, BF):** rodar comparativo dia-D vs dia-comum, ver onde o time gargalou.

## Estrutura

```
monitoramento-equipe/
├── SKILL.md
├── scripts/
│   ├── analisar_equipe.py     ← boletim do dia (ate o "agora")
│   └── analisar_semana.py     ← analise rolling 7d/14d (tendencia)
├── conversores/
│   ├── converter_whatsapp_export.py  ← .txt export → CSV
│   └── converter_zappfy.py           ← JSON Zappfy API → CSV
├── envio/
│   └── enviar_boletim.py      ← manda o resultado no seu privado
├── exemplos/
│   ├── conversas-exemplo.csv          ← 1 dia (~36 msgs)
│   ├── conversas-14dias.csv           ← 14 dias (~227 msgs), pra testar semanal
│   ├── whatsapp-export-exemplo.txt    ← formato real do WhatsApp Business
│   └── vips-exemplo.txt
├── PLANO-IMPLEMENTACAO.md     ← plano 14 dias pra subir em producao
└── README.md
```

## Formato de input

### Opcao 1 — CSV padrao (recomendado)

```csv
data_hora,atendente,cliente,direcao,mensagem
2026-05-24 09:12:03,,Pedro Fulano,recebida,"Bom dia, queria saber preço"
2026-05-24 09:14:47,Joao,Pedro Fulano,enviada,"Oi Pedro! Vou te passar agora"
```

### Opcao 2 — Export .txt do WhatsApp Business

```
[24/05/2026, 09:12:03] Pedro Fulano: Bom dia, queria saber preço
[24/05/2026, 09:14:47] Joao Atendente: Oi Pedro! Vou te passar agora
```

Converta com:
```bash
python conversores/converter_whatsapp_export.py chat.txt \
    --atendentes "Joao Atendente,Maria Atendente,Ana Atendente" \
    --saida conversas.csv
```

### Opcao 3 — API Zappfy (JSON)

```bash
# salva resposta da API em mensagens.json e converte
python conversores/converter_zappfy.py --arquivo mensagens.json --saida conversas.csv

# OU puxa direto da API
python conversores/converter_zappfy.py \
    --url https://api.zappfy.io --token $ZAPPFY_TOKEN --dias 1 \
    --saida conversas.csv
```

## Passos de execucao

### Rodando o boletim diario

1. **Garanta o CSV.** Se voce so tem export do WhatsApp ou JSON da Zappfy, rode o conversor antes.
2. **Rode:**
   ```bash
   python scripts/analisar_equipe.py conversas.csv \
       --vip vips.txt \
       --horario-corte 18:00
   ```
3. **Leia o output.** O boletim tem 7 secoes em ordem: Online → Ranking TPR → Volume → Paradas → Mensagens Criticas → Distribuicao → Pontos de Atencao → Proximos Passos.
4. **Envie pro seu privado** (opcional, mas e o ponto):
   ```bash
   python scripts/analisar_equipe.py conversas.csv --vip vips.txt | \
       python envio/enviar_boletim.py
   ```

### Rodando a analise semanal

```bash
python scripts/analisar_semana.py conversas.csv

# customizando o horario comercial (default 09:00-18:00)
python scripts/analisar_semana.py conversas.csv --horario-comercial 08:30-18:30

# filtrando periodo
python scripts/analisar_semana.py conversas.csv --inicio 2026-05-11 --fim 2026-05-24
```

A analise semanal:
- **Sparkline por atendente** mostra TPR dia a dia em 8 niveis (▁▂▃▄▅▆▇█).
- **Heatmap** revela pico de demanda fora do horario comercial — se o pico bate as 20h, voce precisa de plantao.
- **Comparativo 7d vs 7d** mostra se a operacao ta melhorando, piorando ou estavel.
- **Alertas de tendencia** disparam se algum atendente piorou ≥50% na 2a metade da janela.

## Metricas calculadas

| Metrica | Definicao | Benchmark BR 2026 |
|---|---|---|
| **Status online** | Tempo desde a ultima mensagem enviada | ✅ <15min ⚠️ 15min-2h ❌ >2h |
| **TPR mediano** | Mediana do tempo entre recebida e primeira resposta | 🥇 <5min 🥈 5-15min 🥉 15-60min ❌ >60min |
| **Taxa de resposta** | respondidas / recebidas | Saudavel >80%, alvo >90% |
| **Conversas paradas** | Cliente mandou >30min atras, sem resposta | Alvo: zero >2h |
| **Distribuicao de primeiras** | % das conversas novas cada atendente pegou | Idealmente proximo a 1/N |
| **SLA comercial** | TPR e taxa em horario comercial | TPR <10min, taxa >85% |
| **SLA fora** | TPR e taxa fora do horario | TPR <30min OU mensagem automatica |

## Restricoes — o que a skill NUNCA faz

- **Nunca envia mensagem ao cliente.** So pra voce (privado).
- **Nunca inventa atendente** que nao apareceu no arquivo. Omite e sinaliza.
- **Nunca acusa atendente.** Descreve o dado, deixa a interpretacao com o gestor.
- **Nunca expoe boletim em grupo.** O boletim e pro privado do gestor — mostrar em grupo desmoraliza.

## Combinacoes poderosas

```
Toda quinta 17h: rode analisar_semana e me mande o resumo no privado.
Se algum atendente piorou >50%, abra uma task no ClickUp "1:1 com [nome]" pra sexta.
```

```
Diariamente 18h: rode analisar_equipe + envie no privado.
Se houver mensagem critica de cancelamento sem resposta, dispare alerta
URGENTE no meu WhatsApp.
```

(Tudo isso e plumbing simples com o **Bonus 10 — Pack de Integracoes**.)

---

*Skill criada pela HL.*
