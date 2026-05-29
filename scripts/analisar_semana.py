#!/usr/bin/env python3
"""
Análise semanal — consolida 7 dias rolling e detecta tendência.

Mostra:
  • TPR por atendente a cada dia (sparkline ASCII)
  • Heatmap de demanda hora x dia da semana
  • Comparação semana atual vs semana anterior (precisa de 14 dias no CSV)
  • Alertas de tendência (atendente piorando, dia mais cheio)
  • SLA por horário (comercial 9h-18h vs fora) — taxa de atendimento

Uso:
    python analisar_semana.py conversas.csv
    python analisar_semana.py conversas.csv --inicio 2026-05-19 --fim 2026-05-25
    python analisar_semana.py conversas.csv --horario-comercial 09:00-18:00

Criado pela Bravy.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import median


DIAS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]


# ---------------------------------------------------------------------------
# Modelo + IO
# ---------------------------------------------------------------------------

@dataclass
class Msg:
    dt: datetime
    atendente: str
    cliente: str
    direcao: str
    texto: str


def carregar(caminho: Path) -> list[Msg]:
    if not caminho.exists():
        sys.exit(f"erro: nao encontrado — {caminho}")
    msgs: list[Msg] = []
    with caminho.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                dt = datetime.strptime(row["data_hora"], "%Y-%m-%d %H:%M:%S")
            except (ValueError, KeyError):
                continue
            d = (row.get("direcao") or "").strip().lower()
            if d not in {"recebida", "enviada"}:
                continue
            msgs.append(
                Msg(
                    dt=dt,
                    atendente=(row.get("atendente") or "").strip(),
                    cliente=(row.get("cliente") or "").strip(),
                    direcao=d,
                    texto=row.get("mensagem") or "",
                )
            )
    msgs.sort(key=lambda m: m.dt)
    return msgs


# ---------------------------------------------------------------------------
# Cálculos
# ---------------------------------------------------------------------------

def tpr_por_dia_e_atendente(msgs: list[Msg]) -> dict[tuple[date, str], list[float]]:
    """Retorna {(dia, atendente): [tpr_segundos, ...]}."""
    aguardando: dict[str, datetime] = {}
    out: dict[tuple[date, str], list[float]] = defaultdict(list)
    for m in msgs:
        if m.direcao == "recebida":
            aguardando.setdefault(m.cliente, m.dt)
            continue
        if not m.atendente:
            continue
        primeira = aguardando.pop(m.cliente, None)
        if primeira is not None:
            delta = (m.dt - primeira).total_seconds()
            if delta >= 0:
                out[(m.dt.date(), m.atendente)].append(delta)
    return out


def heatmap_hora_dia(msgs: list[Msg]) -> list[list[int]]:
    """Matriz 7 dias x 24 horas com volume de mensagens RECEBIDAS."""
    grade = [[0] * 24 for _ in range(7)]
    for m in msgs:
        if m.direcao != "recebida":
            continue
        wd = m.dt.weekday()  # 0=seg .. 6=dom
        grade[wd][m.dt.hour] += 1
    return grade


def sla_horario(msgs: list[Msg], comercial_inicio: time, comercial_fim: time) -> dict:
    """
    Calcula:
      - recebidas dentro do horário comercial e fora
      - taxa de resposta em cada janela
      - TPR mediano em cada janela
    """
    aguardando: dict[str, datetime] = {}
    janelas = {"comercial": {"recebidas": 0, "tprs": []}, "fora": {"recebidas": 0, "tprs": []}}

    def janela_de(dt: datetime) -> str:
        t = dt.time()
        eh_semana = dt.weekday() < 5
        if eh_semana and comercial_inicio <= t <= comercial_fim:
            return "comercial"
        return "fora"

    for m in msgs:
        if m.direcao == "recebida":
            j = janela_de(m.dt)
            janelas[j]["recebidas"] += 1
            aguardando.setdefault(m.cliente, m.dt)
            continue
        primeira = aguardando.pop(m.cliente, None)
        if primeira is not None:
            j = janela_de(primeira)
            janelas[j]["tprs"].append((m.dt - primeira).total_seconds())

    for j, v in janelas.items():
        v["respondidas"] = len(v["tprs"])
        v["tpr_mediana_s"] = median(v["tprs"]) if v["tprs"] else None
        v["taxa_resposta"] = (
            round(v["respondidas"] / v["recebidas"] * 100, 1) if v["recebidas"] else 0
        )
    return janelas


def comparar_semanas(msgs: list[Msg]) -> dict | None:
    """Compara últimos 7 dias vs 7 anteriores. None se não houver 14 dias."""
    if not msgs:
        return None
    fim = msgs[-1].dt.date()
    inicio_recente = fim - timedelta(days=6)
    inicio_passada = inicio_recente - timedelta(days=7)
    fim_passada = inicio_recente - timedelta(days=1)

    recente = [m for m in msgs if inicio_recente <= m.dt.date() <= fim]
    passada = [m for m in msgs if inicio_passada <= m.dt.date() <= fim_passada]
    if not passada:
        return None

    def kpis(m: list[Msg]) -> dict:
        recebidas = sum(1 for x in m if x.direcao == "recebida")
        # TPR mediano consolidado
        aguardando, tprs = {}, []
        for x in m:
            if x.direcao == "recebida":
                aguardando.setdefault(x.cliente, x.dt)
            else:
                p = aguardando.pop(x.cliente, None)
                if p is not None:
                    tprs.append((x.dt - p).total_seconds())
        return {
            "recebidas": recebidas,
            "respondidas": len(tprs),
            "tpr_mediana_s": median(tprs) if tprs else None,
        }

    return {
        "semana_atual": kpis(recente),
        "semana_anterior": kpis(passada),
        "periodo_atual": f"{inicio_recente} a {fim}",
        "periodo_anterior": f"{inicio_passada} a {fim_passada}",
    }


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------

def fmt_seg(s: float | None) -> str:
    if s is None:
        return "—"
    s = int(s)
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    if h:
        return f"{h}h{m:02d}"
    if m:
        return f"{m}min{sec:02d}s" if m < 5 and sec else f"{m}min"
    return f"{sec}s"


def sparkline(valores: list[float]) -> str:
    """Sparkline ASCII de 8 níveis."""
    if not valores or all(v is None for v in valores):
        return "—" * len(valores)
    blocos = "▁▂▃▄▅▆▇█"
    vmin = min(v for v in valores if v is not None)
    vmax = max(v for v in valores if v is not None)
    if vmax == vmin:
        return blocos[3] * len(valores)
    out = []
    for v in valores:
        if v is None:
            out.append(" ")
            continue
        idx = int((v - vmin) / (vmax - vmin) * (len(blocos) - 1))
        out.append(blocos[idx])
    return "".join(out)


def setinha(delta_pct: float, baixo_eh_bom: bool = False) -> str:
    if abs(delta_pct) < 1:
        return "▬"
    bom = delta_pct < 0 if baixo_eh_bom else delta_pct > 0
    return "▲" if bom else "▼"


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def renderizar(
    msgs: list[Msg],
    tprs: dict,
    grade: list[list[int]],
    sla: dict,
    comparativo: dict | None,
) -> str:
    L: list[str] = []
    if not msgs:
        return "(sem dados)"

    dia_inicio = msgs[0].dt.date()
    dia_fim = msgs[-1].dt.date()

    L.append("═══════════════════════════════════════════════════════════════")
    L.append(f"ANALISE SEMANAL — {dia_inicio.strftime('%d/%m')} a {dia_fim.strftime('%d/%m/%Y')}")
    L.append("═══════════════════════════════════════════════════════════════")
    L.append("")

    # ---------- TPR DIARIO POR ATENDENTE (sparkline) ----------
    atendentes = sorted({a for (_, a) in tprs.keys()})
    dias = []
    d = dia_inicio
    while d <= dia_fim:
        dias.append(d)
        d += timedelta(days=1)

    if atendentes:
        L.append("TPR DIARIO POR ATENDENTE (sparkline = ouro→ruim)")
        nome_w = max(len(a) for a in atendentes)
        for a in atendentes:
            serie = [median(tprs.get((d, a), [])) if tprs.get((d, a)) else None for d in dias]
            spk = sparkline(serie)
            med_geral = median([v for v in serie if v is not None]) if any(v is not None for v in serie) else None
            L.append(f"  {a.ljust(nome_w)}  {spk}   mediana semana: {fmt_seg(med_geral)}")
        L.append("  " + " " * nome_w + "  " + "".join(d.strftime("%a")[0] for d in dias))
        L.append("")

    # ---------- HEATMAP DEMANDA HORA x DIA ----------
    if any(any(linha) for linha in grade):
        L.append("HEATMAP DE DEMANDA (mensagens recebidas)")
        L.append("       00  03  06  09  12  15  18  21")
        max_val = max(max(linha) for linha in grade) or 1
        chars = " ·░▒▓█"
        for i, linha in enumerate(grade):
            visual = ""
            for h in range(0, 24, 1):
                v = linha[h]
                idx = int(v / max_val * (len(chars) - 1))
                visual += chars[idx]
            L.append(f"  {DIAS_PT[i]}  {visual}")
        L.append("  → pico fora de horario comercial = oportunidade ou perda")
        L.append("")

    # ---------- SLA POR JANELA ----------
    L.append("SLA POR HORARIO")
    for j in ("comercial", "fora"):
        v = sla[j]
        rotulo = "Horario comercial" if j == "comercial" else "Fora do horario  "
        L.append(
            f"  {rotulo}: {v['recebidas']:>4} recebidas | "
            f"{v['taxa_resposta']:>5.1f}% respondidas | TPR mediano {fmt_seg(v['tpr_mediana_s'])}"
        )
    L.append("")

    # ---------- COMPARATIVO SEMANAL ----------
    if comparativo:
        a = comparativo["semana_atual"]
        b = comparativo["semana_anterior"]
        L.append(f"COMPARATIVO  ({comparativo['periodo_atual']}  vs  {comparativo['periodo_anterior']})")

        def linha(label, va, vb, baixo_eh_bom=False, formatador=str):
            if va is None or vb is None:
                return None
            pct = (va - vb) / vb * 100 if vb else 0
            return f"  {label:<22} {formatador(va):>10}  ←  {formatador(vb):<10}  ({pct:+.0f}%)  {setinha(pct, baixo_eh_bom)}"

        l = linha("Recebidas", a["recebidas"], b["recebidas"])
        if l:
            L.append(l)
        l = linha("Respondidas", a["respondidas"], b["respondidas"])
        if l:
            L.append(l)
        l = linha("TPR mediano", a["tpr_mediana_s"], b["tpr_mediana_s"], baixo_eh_bom=True, formatador=fmt_seg)
        if l:
            L.append(l)
        L.append("")

    # ---------- ALERTAS DE TENDENCIA ----------
    alertas = _alertas(tprs, atendentes, dias)
    L.append("ALERTAS DE TENDENCIA")
    if not alertas:
        L.append("  ✅ semana sem outliers")
    else:
        for a in alertas:
            L.append(f"  - {a}")
    L.append("")
    L.append("═══════════════════════════════════════════════════════════════")
    return "\n".join(L)


def _alertas(tprs, atendentes, dias) -> list[str]:
    out: list[str] = []
    metade = len(dias) // 2 or 1
    for a in atendentes:
        primeira_metade = [v for d in dias[:metade] for v in tprs.get((d, a), [])]
        segunda_metade = [v for d in dias[metade:] for v in tprs.get((d, a), [])]
        if len(primeira_metade) < 3 or len(segunda_metade) < 3:
            continue
        m1, m2 = median(primeira_metade), median(segunda_metade)
        if m1 == 0:
            continue
        delta = (m2 - m1) / m1 * 100
        if delta > 50:
            out.append(f"{a}: TPR piorou {delta:.0f}% na 2a metade da semana")
        elif delta < -30:
            out.append(f"{a}: TPR melhorou {abs(delta):.0f}% na 2a metade — manter")

    # dia mais cheio
    volume_dia: dict[date, int] = defaultdict(int)
    for (d, _), tprs_lista in tprs.items():
        volume_dia[d] += len(tprs_lista)
    if volume_dia:
        d_pico, qtd = max(volume_dia.items(), key=lambda x: x[1])
        if qtd > 0:
            out.append(f"Dia mais cheio: {DIAS_PT[d_pico.weekday()]} {d_pico.strftime('%d/%m')} ({qtd} respostas)")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_horario(s: str) -> tuple[time, time]:
    a, b = s.split("-")
    h1, m1 = a.split(":"); h2, m2 = b.split(":")
    return time(int(h1), int(m1)), time(int(h2), int(m2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Analise semanal — tendencia, heatmap, SLA")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--inicio", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--fim", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--horario-comercial", type=str, default="09:00-18:00")
    args = parser.parse_args()

    msgs = carregar(args.csv)
    if args.inicio:
        d = datetime.strptime(args.inicio, "%Y-%m-%d").date()
        msgs = [m for m in msgs if m.dt.date() >= d]
    if args.fim:
        d = datetime.strptime(args.fim, "%Y-%m-%d").date()
        msgs = [m for m in msgs if m.dt.date() <= d]
    if not msgs:
        sys.exit("erro: sem mensagens no periodo")

    ci, cf = parse_horario(args.horario_comercial)
    tprs = tpr_por_dia_e_atendente(msgs)
    grade = heatmap_hora_dia(msgs)
    sla = sla_horario(msgs, ci, cf)
    comp = comparar_semanas(msgs)

    print(renderizar(msgs, tprs, grade, sla, comp))


if __name__ == "__main__":
    main()
