#!/usr/bin/env python3
"""
Analisador de equipe — gera o boletim diário a partir de um CSV de conversas.

Uso:
    python analisar_equipe.py conversas.csv
    python analisar_equipe.py conversas.csv --horario-corte 18:00
    python analisar_equipe.py conversas.csv --vip vips.txt

Formato do CSV (cabeçalho obrigatório):
    data_hora,atendente,cliente,direcao,mensagem

    data_hora — ISO ou "YYYY-MM-DD HH:MM:SS"
    atendente — nome do atendente (vazio se for cliente)
    cliente   — nome do cliente / contato
    direcao   — "recebida" (cliente -> empresa) ou "enviada" (atendente -> cliente)
    mensagem  — texto livre

Criado pela Bravy.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

@dataclass
class Mensagem:
    data_hora: datetime
    atendente: str
    cliente: str
    direcao: str  # "recebida" | "enviada"
    mensagem: str


@dataclass
class EstatisticaAtendente:
    nome: str
    ultima_enviada: datetime | None = None
    enviadas: int = 0
    tprs: list[float] = field(default_factory=list)  # em segundos
    conversas_atendidas: set[str] = field(default_factory=set)


# palavras-gatilho de problema que merecem atencao especial
KEYWORDS_CRITICAS = {
    "reclamacao": ["reclamar", "reclamação", "reclamacao", "horrivel", "horrível", "pessimo", "péssimo",
                   "decepcionad", "merda", "lixo", "abusiv", "absurd"],
    "cancelamento": ["cancelar", "cancelamento", "desistir", "estornar", "estorno", "reembolso", "devolver dinheiro"],
    "urgencia": ["urgente", "agora", "imediato", "rapido", "rápido", "hoje mesmo", "ja", "já era pra"],
    "concorrente": ["concorrente", "ja vi mais barato", "no x ta mais barato", "vou comprar no", "fechei com"],
    "elogio": ["obrigad", "muito bom", "excelente", "perfeito", "amei", "show", "parabens", "parabéns"],
}


def detectar_keywords(msg: str) -> list[str]:
    """Retorna as categorias gatilhadas na mensagem."""
    t = (msg or "").lower()
    hits = []
    for categoria, termos in KEYWORDS_CRITICAS.items():
        if any(termo in t for termo in termos):
            hits.append(categoria)
    return hits


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------

def carregar_csv(caminho: Path) -> list[Mensagem]:
    if not caminho.exists():
        sys.exit(f"erro: arquivo nao encontrado — {caminho}")

    mensagens: list[Mensagem] = []
    with caminho.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        obrigatorias = {"data_hora", "atendente", "cliente", "direcao", "mensagem"}
        faltando = obrigatorias - set(reader.fieldnames or [])
        if faltando:
            sys.exit(f"erro: colunas faltando no CSV: {sorted(faltando)}")

        for linha_n, row in enumerate(reader, start=2):
            try:
                dt = _parse_data(row["data_hora"])
            except ValueError as e:
                print(f"aviso: linha {linha_n} ignorada — data invalida ({e})", file=sys.stderr)
                continue

            direcao = (row["direcao"] or "").strip().lower()
            if direcao not in {"recebida", "enviada"}:
                print(f"aviso: linha {linha_n} ignorada — direcao invalida '{row['direcao']}'", file=sys.stderr)
                continue

            mensagens.append(
                Mensagem(
                    data_hora=dt,
                    atendente=(row["atendente"] or "").strip(),
                    cliente=(row["cliente"] or "").strip(),
                    direcao=direcao,
                    mensagem=row["mensagem"] or "",
                )
            )
    if not mensagens:
        sys.exit("erro: nenhuma mensagem valida no CSV")
    mensagens.sort(key=lambda m: m.data_hora)
    return mensagens


def _parse_data(valor: str) -> datetime:
    formatos = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    )
    for fmt in formatos:
        try:
            return datetime.strptime(valor.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"formato nao reconhecido: '{valor}'")


def carregar_vips(caminho: Path | None) -> set[str]:
    if not caminho:
        return set()
    if not caminho.exists():
        print(f"aviso: arquivo de VIPs nao encontrado — {caminho}", file=sys.stderr)
        return set()
    return {linha.strip() for linha in caminho.read_text(encoding="utf-8").splitlines() if linha.strip()}


# ---------------------------------------------------------------------------
# Calculo
# ---------------------------------------------------------------------------

def calcular_estatisticas(mensagens: list[Mensagem]) -> dict[str, EstatisticaAtendente]:
    """Calcula TPR (mediano), última atividade e volume por atendente."""
    stats: dict[str, EstatisticaAtendente] = defaultdict(lambda: EstatisticaAtendente(nome=""))
    # cliente -> primeira "recebida" pendente de resposta
    aguardando: dict[str, datetime] = {}

    for msg in mensagens:
        if msg.direcao == "recebida":
            # so registra se nao houver ja uma pendente
            aguardando.setdefault(msg.cliente, msg.data_hora)
            continue

        # enviada
        if not msg.atendente:
            continue
        s = stats[msg.atendente]
        s.nome = msg.atendente
        s.enviadas += 1
        s.conversas_atendidas.add(msg.cliente)
        if (s.ultima_enviada is None) or (msg.data_hora > s.ultima_enviada):
            s.ultima_enviada = msg.data_hora

        # se havia uma pendente para esse cliente, calcula o TPR
        primeira_pendente = aguardando.pop(msg.cliente, None)
        if primeira_pendente is not None:
            delta = (msg.data_hora - primeira_pendente).total_seconds()
            if delta >= 0:
                s.tprs.append(delta)

    return dict(stats)


def conversas_paradas(mensagens: list[Mensagem], corte: datetime, limite_min: int = 30) -> list[dict]:
    """Encontra conversas onde a última mensagem é "recebida" há mais de `limite_min`."""
    ultima_por_cliente: dict[str, Mensagem] = {}
    ultimo_atendente_por_cliente: dict[str, str] = {}
    for msg in mensagens:
        ultima_por_cliente[msg.cliente] = msg
        if msg.direcao == "enviada" and msg.atendente:
            ultimo_atendente_por_cliente[msg.cliente] = msg.atendente

    paradas = []
    limite = timedelta(minutes=limite_min)
    for cliente, ultima in ultima_por_cliente.items():
        if ultima.direcao != "recebida":
            continue
        espera = corte - ultima.data_hora
        if espera < limite:
            continue
        paradas.append(
            {
                "cliente": cliente,
                "espera": espera,
                "atendente_anterior": ultimo_atendente_por_cliente.get(cliente, "—"),
                "ultima_msg_em": ultima.data_hora,
                "ultima_msg_texto": ultima.mensagem[:80],
                "keywords": detectar_keywords(ultima.mensagem),
            }
        )
    paradas.sort(key=lambda p: p["espera"], reverse=True)
    return paradas


def mensagens_criticas(mensagens: list[Mensagem]) -> list[dict]:
    """Mensagens recebidas com keyword critica (reclamacao, cancelamento, urgencia, concorrente)."""
    out = []
    for m in mensagens:
        if m.direcao != "recebida":
            continue
        hits = detectar_keywords(m.mensagem)
        criticas = [h for h in hits if h in {"reclamacao", "cancelamento", "urgencia", "concorrente"}]
        if criticas:
            out.append(
                {
                    "cliente": m.cliente,
                    "quando": m.data_hora,
                    "categorias": criticas,
                    "trecho": m.mensagem[:120],
                }
            )
    return out


def distribuicao_carga(mensagens: list[Mensagem]) -> dict[str, dict]:
    """
    Quem PEGOU a primeira mensagem de cada novo cliente do dia?
    Quem tem mais conversas DIFERENTES atendidas? (distribuicao real, nao só volume).
    """
    primeira_resposta: dict[str, str] = {}  # cliente -> atendente que respondeu primeiro
    conversas_por_atendente: dict[str, set[str]] = defaultdict(set)

    for m in mensagens:
        if m.direcao == "enviada" and m.atendente:
            primeira_resposta.setdefault(m.cliente, m.atendente)
            conversas_por_atendente[m.atendente].add(m.cliente)

    primeiras_por_atendente: dict[str, int] = defaultdict(int)
    for _, atend in primeira_resposta.items():
        primeiras_por_atendente[atend] += 1

    return {
        atend: {
            "primeiras_atendidas": primeiras_por_atendente.get(atend, 0),
            "conversas_unicas": len(conv),
        }
        for atend, conv in conversas_por_atendente.items()
    }


# ---------------------------------------------------------------------------
# Formatacao
# ---------------------------------------------------------------------------

def fmt_duracao(td: timedelta | float) -> str:
    if isinstance(td, timedelta):
        seg = int(td.total_seconds())
    else:
        seg = int(td)
    seg = max(seg, 0)
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    if h > 0:
        return f"{h}h{m:02d}"
    if m > 0:
        return f"{m}min{s:02d}s" if s and m < 10 else f"{m:>2d}min"
    return f"{s}s"


def status_online(td: timedelta) -> str:
    minutos = td.total_seconds() / 60
    if minutos < 15:
        return "✅"
    if minutos < 120:
        return "⚠️"
    return "❌"


def medalha(pos: int) -> str:
    return {0: "🥇", 1: "🥈", 2: "🥉"}.get(pos, "  ")


def montar_boletim(
    mensagens: list[Mensagem],
    stats: dict[str, EstatisticaAtendente],
    paradas: list[dict],
    vips: set[str],
    corte: datetime,
    criticas: list[dict] | None = None,
    distribuicao: dict[str, dict] | None = None,
) -> str:
    linhas: list[str] = []
    linhas.append("═══════════════════════════════════════════")
    linhas.append(f"BOLETIM DA EQUIPE — {corte.strftime('%d/%m/%Y %H:%M')}")
    linhas.append("═══════════════════════════════════════════")
    linhas.append("")

    # ---- ONLINE ----
    linhas.append("EQUIPE ONLINE AGORA")
    if not stats:
        linhas.append("  (nenhum atendente identificado no periodo)")
    else:
        nome_max = max(len(s.nome) for s in stats.values())
        for nome, s in sorted(stats.items(), key=lambda kv: kv[1].ultima_enviada or datetime.min, reverse=True):
            if s.ultima_enviada is None:
                linhas.append(f"❌ {nome.ljust(nome_max)} — sem mensagens enviadas no periodo")
                continue
            delta = corte - s.ultima_enviada
            linhas.append(
                f"{status_online(delta)} {nome.ljust(nome_max)} — ultima mensagem enviada ha {fmt_duracao(delta)}"
            )
    linhas.append("")

    # ---- RANKING TPR ----
    linhas.append("RANKING — TEMPO DE PRIMEIRA RESPOSTA (mediana)")
    com_tpr = [(n, median(s.tprs), len(s.tprs)) for n, s in stats.items() if s.tprs]
    com_tpr.sort(key=lambda x: x[1])
    if not com_tpr:
        linhas.append("  (sem dados de TPR no periodo — nao houve par recebida->enviada)")
    else:
        nome_max = max(len(t[0]) for t in com_tpr)
        for i, (nome, mediana, n) in enumerate(com_tpr):
            linhas.append(
                f"{medalha(i)} {nome.ljust(nome_max)} — {fmt_duracao(mediana):>9}  ({n} conversas)"
            )
    linhas.append("")

    # ---- VOLUME ----
    linhas.append("VOLUME DE MENSAGENS ENVIADAS NO PERIODO")
    if stats:
        vols = sorted(stats.items(), key=lambda kv: kv[1].enviadas, reverse=True)
        media = sum(s.enviadas for _, s in vols) / len(vols)
        nome_max = max(len(n) for n, _ in vols)
        for nome, s in vols:
            alerta = "   ← bem abaixo da media" if s.enviadas < media * 0.4 else ""
            linhas.append(f"- {nome.ljust(nome_max)}: {s.enviadas:>4} mensagens{alerta}")
    linhas.append("")

    # ---- PARADAS ----
    linhas.append("CLIENTES ESPERANDO RESPOSTA  (>30min sem retorno)")
    if not paradas:
        linhas.append("  ✅ nenhum cliente parado — limpo")
    else:
        nome_max = max(len(p["cliente"]) for p in paradas) + 3
        for p in paradas:
            marcador = "🌟 " if p["cliente"] in vips else "   "
            tag = ""
            if "cancelamento" in p["keywords"]:
                tag = "  🚨 CANCEL"
            elif "reclamacao" in p["keywords"]:
                tag = "  ⚠ RECLAM"
            elif "urgencia" in p["keywords"]:
                tag = "  ⏰ URG"
            linhas.append(
                f"{marcador}{p['cliente'].ljust(nome_max - 3)} — {fmt_duracao(p['espera']):>7} — ultimo atendente: {p['atendente_anterior']}{tag}"
            )
    linhas.append("")

    # ---- MENSAGENS CRITICAS ----
    if criticas:
        linhas.append("MENSAGENS CRITICAS (cancelamento / reclamacao / concorrente / urgencia)")
        for c in criticas[:8]:
            cats = " ".join(f"[{cat}]" for cat in c["categorias"])
            linhas.append(f"  {c['quando'].strftime('%H:%M')}  {c['cliente']:<20}  {cats}  '{c['trecho']}'")
        if len(criticas) > 8:
            linhas.append(f"  (+{len(criticas) - 8} outras)")
        linhas.append("")

    # ---- DISTRIBUICAO DE CARGA ----
    if distribuicao:
        linhas.append("DISTRIBUICAO DE CARGA  (quem pegou primeira mensagem de cada cliente)")
        nome_w = max(len(n) for n in distribuicao.keys()) if distribuicao else 0
        total_primeiras = sum(d["primeiras_atendidas"] for d in distribuicao.values()) or 1
        for atend, d in sorted(distribuicao.items(), key=lambda x: -x[1]["primeiras_atendidas"]):
            pct = d["primeiras_atendidas"] / total_primeiras * 100
            barra = "█" * int(pct / 5) or "▏"
            linhas.append(
                f"  {atend.ljust(nome_w)}  {d['primeiras_atendidas']:>3}  ({pct:>4.1f}%)  {barra}"
            )
        linhas.append("")

    # ---- ATENCAO ----
    linhas.append("PONTOS DE ATENCAO")
    pontos = _gerar_pontos_atencao(stats, paradas, vips)
    if not pontos:
        linhas.append("  ✅ operacao normal — sem outliers")
    else:
        for p in pontos:
            linhas.append(f"- {p}")
    linhas.append("")

    # ---- PROXIMOS PASSOS ----
    linhas.append("PROXIMOS PASSOS")
    passos = _gerar_proximos_passos(stats, paradas, vips)
    for i, p in enumerate(passos, 1):
        linhas.append(f"{i}. {p}")
    linhas.append("═══════════════════════════════════════════")
    return "\n".join(linhas)


def _gerar_pontos_atencao(
    stats: dict[str, EstatisticaAtendente],
    paradas: list[dict],
    vips: set[str],
) -> list[str]:
    pontos: list[str] = []

    # atendentes com volume baixo
    if stats:
        vols = [s.enviadas for s in stats.values()]
        media = sum(vols) / len(vols)
        for nome, s in stats.items():
            if media > 0 and s.enviadas < media * 0.4:
                pontos.append(f"{nome} com volume abaixo de 40% da media — checar disponibilidade")

    # TPR muito acima do líder
    tprs = [(n, median(s.tprs)) for n, s in stats.items() if s.tprs]
    if len(tprs) >= 2:
        tprs.sort(key=lambda x: x[1])
        lider_tpr = tprs[0][1] or 1
        for nome, t in tprs[1:]:
            if t > lider_tpr * 4 and t > 600:  # 4x mais lento E acima de 10min
                pontos.append(f"{nome} com TPR {t/lider_tpr:.1f}x maior que o lider — sobrecarga ou ausencia")

    # paradas com VIP
    vip_paradas = [p for p in paradas if p["cliente"] in vips]
    for p in vip_paradas:
        pontos.append(f"Cliente VIP ({p['cliente']}) aguardando ha {fmt_duracao(p['espera'])}")

    # cluster de paradas no mesmo atendente
    por_atendente: dict[str, int] = defaultdict(int)
    for p in paradas:
        por_atendente[p["atendente_anterior"]] += 1
    for nome, qtd in por_atendente.items():
        if qtd >= 3 and nome != "—":
            pontos.append(f"{nome} com {qtd} conversas paradas — redistribuir")

    # remover duplicatas mantendo ordem
    vistos = set()
    unicos = []
    for p in pontos:
        if p not in vistos:
            vistos.add(p)
            unicos.append(p)
    return unicos


def _gerar_proximos_passos(
    stats: dict[str, EstatisticaAtendente],
    paradas: list[dict],
    vips: set[str],
) -> list[str]:
    passos: list[str] = []

    # 1. VIPs em espera
    vip_paradas = [p for p in paradas if p["cliente"] in vips]
    if vip_paradas:
        nomes = ", ".join(p["cliente"] for p in vip_paradas[:3])
        passos.append(f"Resgatar VIP(s) agora: {nomes}")

    # 2. Maior espera
    if paradas and not vip_paradas:
        p = paradas[0]
        passos.append(f"Resgatar {p['cliente']} (aguardando ha {fmt_duracao(p['espera'])})")

    # 3. Atendentes sumidos
    sumidos = [n for n, s in stats.items() if s.ultima_enviada is None or s.enviadas == 0]
    if sumidos:
        passos.append(f"Checar disponibilidade de {', '.join(sumidos)}")

    # 4. Atendente sobrecarregado
    por_atendente: dict[str, int] = defaultdict(int)
    for p in paradas:
        por_atendente[p["atendente_anterior"]] += 1
    sobrecarregados = [n for n, q in por_atendente.items() if q >= 3 and n != "—"]
    if sobrecarregados:
        passos.append(f"Redistribuir fila de {', '.join(sobrecarregados)}")

    if not passos:
        passos.append("Manter operacao — sem acao urgente")
    return passos[:5]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Boletim da equipe — analisa CSV de conversas WhatsApp")
    parser.add_argument("csv", type=Path, help="Caminho do CSV de conversas")
    parser.add_argument("--horario-corte", type=str, default=None,
                        help="HH:MM do dia da ultima mensagem; default = ultima linha do CSV")
    parser.add_argument("--vip", type=Path, default=None, help="Arquivo texto, um cliente VIP por linha")
    parser.add_argument("--limite-min", type=int, default=30,
                        help="Minutos sem resposta pra considerar cliente parado (default 30)")
    args = parser.parse_args()

    mensagens = carregar_csv(args.csv)
    vips = carregar_vips(args.vip)

    corte_base = mensagens[-1].data_hora
    if args.horario_corte:
        try:
            h, m = args.horario_corte.split(":")
            corte = corte_base.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
        except ValueError:
            sys.exit(f"erro: --horario-corte invalido '{args.horario_corte}' (use HH:MM)")
    else:
        corte = corte_base

    stats = calcular_estatisticas(mensagens)
    paradas = conversas_paradas(mensagens, corte, limite_min=args.limite_min)
    criticas = mensagens_criticas(mensagens)
    distribuicao = distribuicao_carga(mensagens)
    print(montar_boletim(mensagens, stats, paradas, vips, corte, criticas, distribuicao))


if __name__ == "__main__":
    main()
