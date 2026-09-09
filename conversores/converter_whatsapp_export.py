#!/usr/bin/env python3
"""
Conversor de export do WhatsApp (.txt) → CSV padrão da skill monitoramento-equipe.

O WhatsApp Business / Web exporta o chat num .txt no formato:

    [24/05/2026, 09:12:03] Pedro Fulano: Bom dia, queria saber o preco
    [24/05/2026, 09:14:47] Joao Atendente: Oi Pedro! Vou te passar agora
    [24/05/2026, 09:14:50] Joao Atendente: O plano basico fica R$ 297

O export NÃO diferencia "atendente" de "cliente" automaticamente. Você passa o mapa.

Uso:
    python converter_whatsapp_export.py chat-export.txt \\
        --atendentes "Joao Atendente,Maria Atendente,Carlos Suporte" \\
        --saida conversas.csv

Tudo que não estiver na lista de atendentes vira "cliente".

Criado pela HL.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path


# Formato com data brasileira [DD/MM/YYYY, HH:MM:SS] Nome: msg
#   também tolera [DD/MM/YY HH:MM:SS]  (alguns Androids)
#   e DD/MM/YYYY HH:MM - Nome: msg     (iOS antigo)
LINHA_REGEX = re.compile(
    r"^\s*\[?(?P<dia>\d{1,2})/(?P<mes>\d{1,2})/(?P<ano>\d{2,4})[,\s]+"
    r"(?P<hora>\d{1,2}):(?P<min>\d{2})(?::(?P<seg>\d{2}))?\]?\s*[-]?\s*"
    r"(?P<remetente>[^:]+?):\s*(?P<msg>.*)$"
)

SISTEMA_REGEX = re.compile(
    r"(messages and calls are end-to-end encrypted|mensagens e ligacoes sao protegidas"
    r"|created group|added|left|removed|changed the group)",
    re.IGNORECASE,
)


def parse_arquivo(caminho: Path, atendentes: set[str]) -> list[dict]:
    if not caminho.exists():
        sys.exit(f"erro: arquivo nao encontrado — {caminho}")
    linhas_brutas = caminho.read_text(encoding="utf-8", errors="replace").splitlines()

    eventos: list[dict] = []
    buffer: dict | None = None

    for raw in linhas_brutas:
        m = LINHA_REGEX.match(raw)
        if not m:
            # continuação de mensagem anterior (multilinha)
            if buffer is not None:
                buffer["mensagem"] += "\n" + raw.strip()
            continue

        # flush do anterior
        if buffer is not None:
            eventos.append(buffer)
            buffer = None

        if SISTEMA_REGEX.search(m.group("msg") or ""):
            continue  # mensagem do sistema

        ano = int(m.group("ano"))
        if ano < 100:
            ano += 2000

        try:
            dt = datetime(
                ano,
                int(m.group("mes")),
                int(m.group("dia")),
                int(m.group("hora")),
                int(m.group("min")),
                int(m.group("seg") or 0),
            )
        except ValueError:
            continue

        remetente = m.group("remetente").strip()
        eh_atendente = remetente in atendentes

        buffer = {
            "data_hora": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "atendente": remetente if eh_atendente else "",
            "cliente": _cliente_implicito(remetente, eh_atendente, eventos),
            "direcao": "enviada" if eh_atendente else "recebida",
            "mensagem": m.group("msg") or "",
        }

    if buffer is not None:
        eventos.append(buffer)

    return eventos


def _cliente_implicito(remetente: str, eh_atendente: bool, eventos: list[dict]) -> str:
    """
    Numa conversa 1-a-1, o cliente é sempre o que NÃO é atendente.
    Numa conversa de grupo, isso quebra — mas o caso típico do WhatsApp Business é 1-a-1.

    Estratégia: se o remetente é atendente, o cliente é o último remetente NÃO-atendente
    visto. Se for o primeiro evento, deixamos em branco e o usuário ajusta.
    """
    if not eh_atendente:
        return remetente
    for e in reversed(eventos):
        if e["direcao"] == "recebida":
            return e["cliente"]
    return ""


def escrever_csv(eventos: list[dict], saida: Path) -> None:
    if not eventos:
        sys.exit("erro: nenhuma mensagem extraida (confira atendentes)")
    with saida.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["data_hora", "atendente", "cliente", "direcao", "mensagem"],
        )
        w.writeheader()
        for e in eventos:
            w.writerow(e)
    print(f"OK — {len(eventos)} mensagens escritas em {saida}")

    # estatistica rapida
    enviadas = sum(1 for e in eventos if e["direcao"] == "enviada")
    recebidas = len(eventos) - enviadas
    nomes_atendentes = sorted({e["atendente"] for e in eventos if e["atendente"]})
    print(f"  recebidas: {recebidas}  |  enviadas: {enviadas}")
    print(f"  atendentes identificados: {', '.join(nomes_atendentes) or '(nenhum)'}")
    sem_cliente = sum(1 for e in eventos if not e["cliente"])
    if sem_cliente:
        print(f"  aviso: {sem_cliente} linhas sem cliente identificado — revise manualmente")


def main() -> None:
    parser = argparse.ArgumentParser(description="WhatsApp .txt export -> CSV padrao")
    parser.add_argument("entrada", type=Path, help="Arquivo .txt exportado do WhatsApp")
    parser.add_argument(
        "--atendentes",
        required=True,
        help="Lista de nomes EXATOS dos atendentes (como aparecem no export), separados por vírgula",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("conversas.csv"),
        help="CSV de saída (default: conversas.csv)",
    )
    args = parser.parse_args()
    atendentes = {a.strip() for a in args.atendentes.split(",") if a.strip()}
    if not atendentes:
        sys.exit("erro: passe pelo menos um nome em --atendentes")
    eventos = parse_arquivo(args.entrada, atendentes)
    escrever_csv(eventos, args.saida)


if __name__ == "__main__":
    main()
