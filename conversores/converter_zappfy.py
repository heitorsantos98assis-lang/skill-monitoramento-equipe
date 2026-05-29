#!/usr/bin/env python3
"""
Conversor de mensagens da API Zappfy → CSV padrao da skill monitoramento-equipe.

A API Zappfy retorna mensagens em JSON. Você pode:
  1. Salvar o retorno em um .json e rodar este script com `--arquivo`.
  2. Passar `--url` + `--token` e o script puxa direto da API.

Suporta os endpoints comuns:
  - /messages?phone=...&days=N    (Zappfy v1)
  - /chats/{phone}/messages       (Zappfy v2)

Formato esperado de cada mensagem (campos comuns):
  {
    "timestamp": "2026-05-24T09:12:03Z" OU 1716540723,
    "from": "5521999999999@c.us"   (remetente)
    "to":   "5521988888888@c.us"   (destinatario)
    "fromMe": true | false           (true = nos enviamos)
    "body": "texto da mensagem",
    "operator": "Joao Atendente"     (opcional - nome do atendente)
  }

Uso:
    python converter_zappfy.py --arquivo mensagens.json --saida conversas.csv
    python converter_zappfy.py --url https://api.zappfy.io --token TKN --dias 1

Criado pela Bravy.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_timestamp(raw) -> str:
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw if raw < 1e12 else raw / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(raw, str):
        # tenta ISO
        s = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    raise ValueError(f"timestamp invalido: {raw!r}")


def normalizar_telefone(jid: str) -> str:
    if not jid:
        return ""
    return jid.split("@")[0]


def conversa_id(msg: dict) -> str:
    """Identifica a conversa pela contraparte (cliente)."""
    if msg.get("fromMe"):
        return normalizar_telefone(msg.get("to") or msg.get("chat") or "")
    return normalizar_telefone(msg.get("from") or msg.get("chat") or "")


def converter(mensagens: list[dict], mapa_contatos: dict[str, str] | None = None) -> list[dict]:
    mapa_contatos = mapa_contatos or {}
    out: list[dict] = []
    for m in mensagens:
        ts = parse_timestamp(m.get("timestamp") or m.get("messageTimestamp") or m.get("t") or 0)
        eh_nosso = bool(m.get("fromMe"))
        cliente_id = conversa_id(m)
        cliente = mapa_contatos.get(cliente_id) or m.get("contactName") or cliente_id
        atendente = m.get("operator") or m.get("agent") or m.get("user") or ""
        if not atendente and eh_nosso:
            atendente = "WhatsApp"  # genérico se a API não trouxe
        out.append(
            {
                "data_hora": ts,
                "atendente": atendente if eh_nosso else "",
                "cliente": cliente,
                "direcao": "enviada" if eh_nosso else "recebida",
                "mensagem": m.get("body") or m.get("text") or m.get("message", {}).get("text", "") or "",
            }
        )
    out.sort(key=lambda x: x["data_hora"])
    return out


def puxar_da_api(url_base: str, token: str, dias: int) -> list[dict]:
    try:
        import requests
    except ImportError:
        sys.exit("erro: instale 'requests' (pip install requests)")
    r = requests.get(
        f"{url_base.rstrip('/')}/messages",
        params={"days": dias},
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if not r.ok:
        sys.exit(f"erro Zappfy {r.status_code}: {r.text[:300]}")
    j = r.json()
    return j.get("messages") if isinstance(j, dict) and "messages" in j else j


def carregar_mapa(arquivo: Path | None) -> dict[str, str]:
    if not arquivo:
        return {}
    if not arquivo.exists():
        return {}
    mapa: dict[str, str] = {}
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        if "," not in linha:
            continue
        telefone, nome = linha.split(",", 1)
        mapa[telefone.strip()] = nome.strip()
    return mapa


def main() -> None:
    parser = argparse.ArgumentParser(description="Zappfy → CSV padrao monitoramento-equipe")
    fonte = parser.add_mutually_exclusive_group(required=True)
    fonte.add_argument("--arquivo", type=Path, help="JSON salvo da resposta da API")
    fonte.add_argument("--url", type=str, help="URL base da API Zappfy")
    parser.add_argument("--token", type=str, default=os.environ.get("ZAPPFY_TOKEN", ""))
    parser.add_argument("--dias", type=int, default=1)
    parser.add_argument("--saida", type=Path, default=Path("conversas.csv"))
    parser.add_argument(
        "--contatos",
        type=Path,
        default=None,
        help="Arquivo opcional 'telefone,nome' (1 por linha) pra dar nome aos clientes",
    )
    args = parser.parse_args()

    if args.arquivo:
        raw = json.loads(args.arquivo.read_text(encoding="utf-8"))
        mensagens = raw if isinstance(raw, list) else raw.get("messages", [])
    else:
        if not args.token:
            sys.exit("erro: passe --token ou defina ZAPPFY_TOKEN")
        mensagens = puxar_da_api(args.url, args.token, args.dias)

    if not mensagens:
        sys.exit("erro: nenhuma mensagem retornada")

    mapa = carregar_mapa(args.contatos)
    eventos = converter(mensagens, mapa)

    with args.saida.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["data_hora", "atendente", "cliente", "direcao", "mensagem"])
        w.writeheader()
        w.writerows(eventos)
    print(f"OK — {len(eventos)} mensagens escritas em {args.saida}")


if __name__ == "__main__":
    main()
