# Bonus 8 — Skill de Monitoramento de Equipe

Skill do Codex que monitora atendentes do WhatsApp e devolve **boletim diario** (com tendencias, palavras criticas e distribuicao de carga) e **analise semanal** (sparkline por atendente, heatmap, comparativo 7d vs 7d, alertas de tendencia) — direto no seu privado, automatizado.

> Pensado para operacoes com **2 ou mais pessoas** atendendo no WhatsApp.
> Aceita 3 formatos de input: CSV padrao, `.txt` do WhatsApp Business e JSON da Zappfy.

## O que voce ganha

### Boletim diario (`analisar_equipe.py`)
- **Equipe online agora** (✅ ⚠️ ❌ pelo tempo desde a ultima resposta)
- **Ranking de TPR mediano** com medalha 🥇🥈🥉
- **Volume** com alerta "abaixo da media"
- **Conversas paradas >30min** com TAG inline (🚨 CANCEL, ⚠ RECLAM, ⏰ URG) quando a ultima mensagem do cliente tem keyword critica
- **Mensagens criticas** (cancelamento / reclamacao / concorrente / urgencia) com hora + cliente + trecho
- **Distribuicao real de carga** — quem pegou a primeira mensagem de cada novo cliente (com barra ASCII)
- **Pontos de atencao** + **Proximos passos** priorizados

### Analise semanal (`analisar_semana.py`)
- **Sparkline diario por atendente** (8 niveis ASCII)
- **Heatmap de demanda** hora × dia da semana
- **SLA por janela** — horario comercial vs fora
- **Comparativo 7d vs 7d anteriores** (recebidas, respondidas, TPR — com ▲▼▬)
- **Alertas de tendencia** — quem piorou >50% na segunda metade

## Estrutura

```
08-skill-monitoramento-equipe/
├── SKILL.md                                    ← a skill, formato Codex
├── PLANO-IMPLEMENTACAO.md                      ← passo a passo 14 dias ate producao
├── scripts/
│   ├── analisar_equipe.py                      ← boletim diario
│   └── analisar_semana.py                      ← analise semanal (sparkline + heatmap + comparativo)
├── conversores/
│   ├── converter_whatsapp_export.py            ← .txt do WhatsApp Business → CSV
│   └── converter_zappfy.py                     ← JSON da API Zappfy → CSV
├── envio/
│   └── enviar_boletim.py                       ← envia o resultado no seu privado (Zappfy)
├── exemplos/
│   ├── conversas-exemplo.csv                   ← 1 dia, 36 msgs
│   ├── conversas-14dias.csv                    ← 14 dias, 227 msgs (pra testar analise semanal)
│   ├── whatsapp-export-exemplo.txt             ← formato real
│   └── vips-exemplo.txt
├── 08-skill-monitoramento-equipe.zip
└── README.md
```

## Instalacao

```bash
# para todos os projetos
mkdir -p .agents/skills/
cp -r . .agents/skills/monitoramento-equipe

# OU para um projeto especifico
cp -r . /caminho/do/projeto.agents/skills/monitoramento-equipe
```

> Mantenha as pastas `scripts/`, `conversores/`, `envio/` juntas — os scripts chamam por caminho relativo.

## Dependencias

Python 3.9+ (vem no Mac/Linux). Os scripts de analise usam **apenas biblioteca padrao** — zero `pip install`.

Os conversores e o envio:
- `converter_zappfy.py` precisa de `requests` apenas se voce usar `--url` (puxar direto da API). Pra `--arquivo` (JSON local) nao precisa.
- `enviar_boletim.py` precisa de `requests`.

```bash
pip install requests
```

## Quickstart (5 minutos)

```bash
# 1) Boletim diario com os exemplos
python scripts/analisar_equipe.py exemplos/conversas-exemplo.csv \
    --vip exemplos/vips-exemplo.txt

# 2) Analise semanal (14 dias de dados simulados)
python scripts/analisar_semana.py exemplos/conversas-14dias.csv

# 3) Conversao de export do WhatsApp Business
python conversores/converter_whatsapp_export.py exemplos/whatsapp-export-exemplo.txt \
    --atendentes "Joao Atendente,Maria Atendente,Ana Atendente" \
    --saida /tmp/conversas.csv

# 4) Pipeline ponta a ponta
python scripts/analisar_equipe.py /tmp/conversas.csv --vip exemplos/vips-exemplo.txt
```

## Como usar de verdade (em producao)

Veja **`PLANO-IMPLEMENTACAO.md`** — plano de 14 dias com:
- Escolha da fonte (export manual / Zappfy / Cloud API)
- Setup credencial
- Mapa de atendentes + VIPs
- Validacao manual obrigatoria (antes de automatizar)
- Configuracao de cron (Mac/Linux, com pegadinha de TCC do macOS)
- Treinamento da equipe (sim, eles precisam saber — boletim usado pra punir vira teatro)
- Sinais de sucesso + sinais de falha + acao

## Saida real (testada nos exemplos)

### Boletim diario

```
═══════════════════════════════════════════
BOLETIM DA EQUIPE — 24/05/2026 16:32
═══════════════════════════════════════════

EQUIPE ONLINE AGORA
✅ Maria Atendente — ultima mensagem enviada ha 0s
⚠️ Joao Atendente  — ultima mensagem enviada ha 1h44
❌ Ana Atendente   — ultima mensagem enviada ha 6h58

RANKING — TEMPO DE PRIMEIRA RESPOSTA (mediana)
🥇 Maria Atendente —   2min52s  (4 conversas)
🥈 Joao Atendente  —     10min  (2 conversas)
🥉 Ana Atendente   —     14min  (1 conversas)

CLIENTES ESPERANDO RESPOSTA  (>30min sem retorno)
🌟 Roberto VIP —    5h29 — ultimo atendente: Ana Atendente

MENSAGENS CRITICAS (cancelamento / reclamacao / concorrente / urgencia)
  12:33  Bruno Tech       [reclamacao] [cancelamento]  'Boa tarde, isso aqui esta um lixo, quero cancelar'
  16:23  Mariana Costa    [urgencia]   'Oi, urgente preciso da entrega hoje mesmo'

DISTRIBUICAO DE CARGA  (quem pegou primeira mensagem de cada cliente)
  Maria Atendente    3  (50.0%)  ██████████
  Joao Atendente     2  (33.3%)  ██████
  Ana Atendente      1  (16.7%)  ███

PONTOS DE ATENCAO
- Ana Atendente com TPR 5.1x maior que o lider — sobrecarga ou ausencia
- Cliente VIP (Roberto VIP) aguardando ha 5h29

PROXIMOS PASSOS
1. Resgatar VIP(s) agora: Roberto VIP
═══════════════════════════════════════════
```

### Analise semanal

```
═══════════════════════════════════════════════════════════════
ANALISE SEMANAL — 11/05 a 24/05/2026
═══════════════════════════════════════════════════════════════

TPR DIARIO POR ATENDENTE (sparkline = ouro→ruim)
  Ana     ▁▁▁▄▁▁  ▁▁▃█▁▁   mediana semana: 34min
  Carlos  ▁▁▁▁▁ █▁▁▁▁▁▁▁   mediana semana: 6min
  Joao    ▁▁ ▁▁█ ▁▁ ▁▁     mediana semana: 4min12s
  Maria    ▁ ▁▁ ▁▁▁█▁▁ ▁   mediana semana: 4min31s
          MTWTFSSMTWTFSS

HEATMAP DE DEMANDA (mensagens recebidas)
       00  03  06  09  12  15  18  21
  Seg           ▒▓░░ ▒░··░░    
  Ter          ░▒ ░·░▓▒░░·     
  ...

SLA POR HORARIO
  Horario comercial:   84 recebidas |  85.7% respondidas | TPR mediano 7min
  Fora do horario  :   41 recebidas |  73.2% respondidas | TPR mediano 10min

COMPARATIVO  (2026-05-18 a 2026-05-24  vs  2026-05-11 a 2026-05-17)
  Recebidas              65  ←  60     (+8%)   ▲
  Respondidas            51  ←  51     (+0%)   ▬
  TPR mediano          9min  ←  7min   (+23%)  ▼

ALERTAS DE TENDENCIA
  - Ana: TPR piorou 154% na 2a metade da semana
  - Joao: TPR piorou 173% na 2a metade da semana
```

## Combinacao com outros bonus

- **Bonus 9 — `relatorio-diario`:** essa skill fala do **time** (TPR por pessoa); o Bonus 9 fala do **negocio** (volume, VIPs, grupos). Rode as duas em horarios diferentes.
- **Bonus 10 — Pack de Integracoes:** o `enviar_boletim.py` ja entrega via Zappfy. Pra mandar tambem pro Slack/Discord/Telegram do gestor, use o modulo `slack-discord-telegram/` do Bonus 10.
- **Bonus 6 — Setup FDS:** mesmo padrao de cron, mesmo estilo de orquestracao.

## Boas praticas

- **Privado, nao grupo.** O boletim mostra nome de atendente — expor em grupo vira fofoca, nao gestao.
- **Compare semana com semana.** Salve cada boletim/analise (`semana_2026-05-24.txt`). 4 semanas = vc tem serie temporal pra entender sazonalidade real.
- **VIPs sempre atualizados.** Ganhou cliente grande? Coloca na lista. Perdeu? Tira.
- **Treine o time.** Boletim e ferramenta de ajuda, nao de punicao. Quem entende usa, quem nao entende sabota.
- **Valide manualmente antes de automatizar.** 1 dia conferindo no relogio o que o script disse vale 30 dias de cron rodando errado.

---

*Material criado pela HL.*
