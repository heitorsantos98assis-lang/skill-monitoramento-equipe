#!/usr/bin/env python3
"""
Dispara o boletim no seu privado via Zappfy (ou qualquer endpoint compativel).

Le o boletim de stdin (ou de um arquivo) e manda mensagem.

Uso:
    cat boletim.txt | python enviar_boletim.py
    python enviar_boletim.py --arquivo boletim.txt

Variaveis de ambiente:
    ZAPPFY_URL_ENVIO  — endpoint completo (ex: https://api.zappfy.io/v2/messages)
    ZAPPFY_TOKEN      — bearer token
    WHATSAPP_DESTINO  — numero alvo no formato 55DDDNUMERO (sem +, sem espacos)

Cron exemplo:
    0 18 * * 1-5  cd /opt/equipe && \\
        python scripts/analisar_equipe.py conversas.csv --vip vips.txt | \\
        python envio/enviar_boletim.py

Criado pela HL.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def enviar(texto: str, url: str, token: str, destino: str) -> dict:
    try:
        import requests
    except ImportError:
        sys.exit("erro: instale 'requests' (pip install requests)")
    if not texto.strip():
        sys.exit("erro: texto vazio — nada pra enviar")
    if len(texto) > 4096:
        # WhatsApp tem limite de 4096 caracteres por mensagem
        texto = texto[:4090] + "\n[...]"
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"phone": destino, "message": texto},
        timeout=30,
    )
    if not r.ok:
        sys.exit(f"erro Zappfy {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else {"ok": True}


def main() -> None:
    parser = argparse.ArgumentParser(description="Enviar boletim via Zappfy")
    parser.add_argument("--arquivo", type=Path, help="Arquivo com o boletim (default: stdin)")
    parser.add_argument("--url", type=str, default=os.environ.get("ZAPPFY_URL_ENVIO", ""))
    parser.add_argument("--token", type=str, default=os.environ.get("ZAPPFY_TOKEN", ""))
    parser.add_argument("--destino", type=str, default=os.environ.get("WHATSAPP_DESTINO", ""))
    parser.add_argument("--prefixo", type=str, default="📊 Boletim da equipe\n\n")
    args = parser.parse_args()

    if not (args.url and args.token and args.destino):
        sys.exit(
            "erro: defina ZAPPFY_URL_ENVIO, ZAPPFY_TOKEN e WHATSAPP_DESTINO "
            "(via env ou --url/--token/--destino)"
        )

    if args.arquivo:
        texto = args.arquivo.read_text(encoding="utf-8")
    else:
        texto = sys.stdin.read()

    resp = enviar(args.prefixo + texto, args.url, args.token, args.destino)
    print(f"OK enviado para {args.destino}", file=sys.stderr)


if __name__ == "__main__":
    main()
