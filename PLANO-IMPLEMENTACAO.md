# Plano de Implementacao — 14 dias

Como sair do zero ate o boletim chegando no seu privado **todo dia automaticamente**.

## Dia 1 — Decidir a fonte de dados

Escolha uma:

| Fonte | Pros | Contras | Quando faz sentido |
|---|---|---|---|
| **Export .txt do WhatsApp Business** | Zero custo, funciona ja | Manual — voce exporta a cada rodada | Operacao 1 numero, 1-2 atendentes |
| **API Zappfy** | Automatico 24/7, multi-numero | Custo Zappfy ~R$ 30-50/mes | Operacao 2+ atendentes ou 2+ numeros |
| **WhatsApp Cloud API (Meta)** | Oficial, robusto, gratuito ate 1k convs/mes | Setup chato (Business Manager + Phone Number ID + Webhook) | Operacao 200+ conversas/mes |

**Decisao do dia:** anote qual fonte vai usar.

## Dia 2-3 — Setup tecnico

### Cenario A: Export manual

1. No WhatsApp Business: `⋮` → `Mais` → `Exportar conversa` → `Sem midia`.
2. Mande o `.txt` por email pra voce mesmo.
3. Salve em `/Users/SEU_USUARIO/equipe/chats/`.
4. Liste os nomes EXATOS dos atendentes como aparecem no export (sem typo!).

### Cenario B: Zappfy

1. Logue no painel Zappfy → API → gere o token.
2. Crie `~/.credentials/zappfy.env`:
   ```
   ZAPPFY_TOKEN=seu_token
   ZAPPFY_URL=https://api.zappfy.io
   ZAPPFY_URL_ENVIO=https://api.zappfy.io/v2/messages
   WHATSAPP_DESTINO=5521999999999
   ```
3. Teste:
   ```bash
   export $(cat ~/.credentials/zappfy.env | xargs)
   python conversores/converter_zappfy.py --url $ZAPPFY_URL --token $ZAPPFY_TOKEN --dias 1
   ```

### Cenario C: Cloud API

Veja a documentacao oficial Meta — fora do escopo desta skill, mas o `converter_zappfy.py` aceita qualquer JSON com os campos `timestamp`, `from`, `to`, `fromMe`, `body`. Adapte o seu webhook pra gravar JSON nesse formato.

## Dia 4 — Mapa de atendentes + VIPs

1. Crie `vips.txt` (1 cliente por linha):
   ```
   Roberto Construtora ACME
   Mariana Costa
   Empresa Cicrano LTDA
   ```
2. Se for Zappfy/Cloud API, crie `contatos.txt` (1 por linha, `telefone,nome`):
   ```
   5521988887777,Pedro Fulano
   5521977776666,Sandra Cicrano
   ```

## Dia 5-6 — Primeira rodada manual

```bash
# 1) Converte dados de hoje
python conversores/converter_whatsapp_export.py chat-hoje.txt \
    --atendentes "Joao,Maria,Ana" --saida conversas.csv

# 2) Roda boletim
python scripts/analisar_equipe.py conversas.csv --vip vips.txt

# 3) Le. Faz sentido? Os atendentes batem com a operacao real?
```

**Validacao manual obrigatoria.** Olhe 1 conversa do dia, conte o TPR no relogio, confirme que o script bate. Se nao bater, ajuste antes de automatizar — automatizar dado errado e amplificar problema.

## Dia 7 — Configurar envio pro seu privado

```bash
# Teste end-to-end
python scripts/analisar_equipe.py conversas.csv --vip vips.txt | \
    python envio/enviar_boletim.py
```

Deve chegar no seu WhatsApp em <10 segundos. Se nao chegar:
- Cheque `ZAPPFY_URL_ENVIO` e `WHATSAPP_DESTINO`.
- Veja o response do curl: `curl -v -X POST $ZAPPFY_URL_ENVIO ...`.

## Dia 8 — Cron diario

Mac/Linux — abra `crontab -e` e cole:

```cron
# 12h - boletim parcial pro gestor
0 12 * * 1-5  cd /Users/SEU/equipe && \
    python conversores/converter_zappfy.py --url $ZAPPFY_URL --token $ZAPPFY_TOKEN --dias 1 --saida hoje.csv && \
    python scripts/analisar_equipe.py hoje.csv --vip vips.txt | \
    python envio/enviar_boletim.py

# 18h - boletim final pro gestor
0 18 * * 1-5  (mesmo comando acima)

# Sexta 17h - analise semanal
0 17 * * 5    cd /Users/SEU/equipe && \
    python conversores/converter_zappfy.py --url $ZAPPFY_URL --token $ZAPPFY_TOKEN --dias 14 --saida semana.csv && \
    python scripts/analisar_semana.py semana.csv | \
    python envio/enviar_boletim.py --prefixo "📊 Analise semanal\n\n"
```

> **macOS:** o cron precisa de permissao "Acesso Total ao Disco" (Ajustes > Privacidade > Acesso total ao disco > `/usr/sbin/cron`).
>
> **Servidor Linux:** sem essa pegadinha, funciona direto.

## Dia 9-10 — Validar 2 dias de cron

Deixe rodar 2 dias uteis. Cheque:
- Chegou no seu privado nos 2 dias? Em ambos os horarios?
- O conteudo bate com o que voce sabe da operacao?
- Algum atendente foi marcado errado? (typo no nome).

## Dia 11 — Tunings finos

Ajuste se necessario:

- **Horario comercial real do seu nicho.** Se voce vende ate 22h, mude `--horario-comercial 09:00-22:00`.
- **Limite de conversa parada.** Se sua operacao e B2B com ciclo longo, talvez 60min (em vez do default 30min) seja mais util: `--limite-min 60`.
- **Lista de VIPs.** Adicione/remova clientes conforme ganha/perde contas.
- **Palavras criticas customizadas.** Edite `KEYWORDS_CRITICAS` no `analisar_equipe.py` pra incluir termos do seu nicho (ex: pra clinica, "alergia"; pra ecommerce, "nao chegou").

## Dia 12-13 — Treinar a equipe (sim, a equipe precisa saber)

Abra com a equipe (transparencia gera confianca, nao pressao):

> "Galera, comecei a olhar o boletim diario da equipe. Foco: identificar gargalos pra eu ajudar — nao pra cobrar. Voces vao ver:
> - quem ta sobrecarregado (a gente redistribui),
> - cliente parado >30min (a gente cobre),
> - mensagem critica que escapou (a gente resgata).
>
> 1 vez por semana eu compartilho a tendencia da semana com voces. Se algum nome cair no alerta, conversamos no 1:1 sem julgamento."

**Por que isso importa:** boletim usado pra punir cria gaming (atendente responde "oi" so pra marcar TPR baixo e some). Boletim usado pra ajudar cria operacao saudavel.

## Dia 14 — Revisao + ritual

1. Cheque a tendencia de 14 dias com `analisar_semana`.
2. Defina **ritual semanal:**
   - Sexta 17h: receba analise da semana.
   - Domingo 19h: revise sozinho, decida 1-2 acoes pra segunda.
   - Segunda 9h: comunique a 1-2 acoes no daily.
3. **Marco do dia 14:** voce nao olha mais conversa por conversa. Confia no boletim. Olha so quando o boletim pede sua atencao.

## Sinais de sucesso depois de 30 dias

- TPR mediano caiu (compara o `analisar_semana` do dia 1 com o do dia 30).
- Conversas paradas >2h foram a quase zero.
- Nenhuma mensagem critica passou sem resposta no mesmo dia.
- VIP nao espera mais que 15 minutos.
- Voce nao precisa "abrir o WhatsApp pra ver como ta" — o boletim te diz.

## Sinais de falha (e o que fazer)

| Sintoma | Causa provavel | Acao |
|---|---|---|
| Boletim chega vazio | Cron rodou antes de ter dados / fuso errado | Reveja horario do cron, teste manual |
| TPR muito alto sempre | Atendente tem horario diferente do esperado (ex: vespertino) | Ajuste `--horario-corte` ou rode 2 vezes ao dia |
| Aparece atendente fantasma | Erro de digitacao do nome no app vs lista | Padronize nome com "@atendente" no WhatsApp Business |
| Cliente VIP no boletim sem espera | VIP esta com nome diferente no contato | Atualize `vips.txt` com o nome exato que aparece nos contatos |
| Mensagens criticas com falso-positivo | Keyword muito generica (ex: "agora") | Edite `KEYWORDS_CRITICAS` |

---

*Material criado pela Bravy.*
