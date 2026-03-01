# -*- coding: utf-8 -*-
"""sessions_from_schedule.py — gerar *dias individuais* a partir de "Horários" + intervalo.

Objectivo
- Converter um texto do tipo:
    "Qui: 21:30; Sex: 21:30; Sáb: 16:30, 21:30; Dom: 16:30, 21:30"
  num conjunto de sessões *individuais* (uma por data/hora) no formato esperado pelo teatroapp_uploader:
    {"venue": "...", "date": "YYYY-MM-DD", "hour": 21, "minute": 30, "ticket_url": "..."}

Regras
- Sem pesquisa online.
- Logs PT-PT pré-Acordo.

Notas
- Requer Data Início e Data Fim.
- Interpreta abreviaturas PT comuns: Seg, Ter, Qua, Qui, Sex, Sáb, Dom.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple


_DIAS_MAP = {
    "seg": 0,
    "ter": 1,
    "qua": 2,
    "qui": 3,
    "sex": 4,
    "sab": 5,
    "sáb": 5,
    "dom": 6,
}


def _parse_iso_date(s: str) -> date:
    s = (s or "").strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        raise RuntimeError(f"sessões: data inválida (esperado YYYY-MM-DD): {s!r}")


def _parse_time_token(tok: str) -> Tuple[int, int]:
    tok = (tok or "").strip()
    m = re.match(r"^([0-9]{1,2}):([0-9]{2})$", tok)
    if not m:
        raise RuntimeError(f"sessões: hora inválida (esperado HH:MM): {tok!r}")
    h = int(m.group(1))
    mi = int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        raise RuntimeError(f"sessões: hora fora do intervalo: {tok!r}")
    return h, mi


def parse_horarios_semanais(horarios: str) -> Dict[int, List[Tuple[int, int]]]:
    """Parse do texto "Horários" -> mapa weekday -> lista de (h, m)."""
    s = (horarios or "").strip()
    if not s or s.upper() == "N/A":
        return {}

    out: Dict[int, List[Tuple[int, int]]] = {}

    # Divide por ';' (blocos por dia)
    blocks = [b.strip() for b in s.split(";") if b.strip()]
    for b in blocks:
        # Ex.: "Sáb: 16:30, 21:30" ou "Qui: 21:30"
        if ":" not in b:
            continue
        day_part, times_part = b.split(":", 1)
        day_key = day_part.strip().lower()

        # Normaliza dia (aceita "Sáb"/"Sab")
        day_key = day_key.replace("á", "a")
        day_key = re.sub(r"[.]$", "", day_key)  # remove ponto final

        wd = _DIAS_MAP.get(day_key)
        if wd is None:
            # tenta só 3 letras
            wd = _DIAS_MAP.get(day_key[:3])
        if wd is None:
            continue

        # horas separadas por vírgula
        times = [t.strip() for t in times_part.split(",") if t.strip()]
        parsed: List[Tuple[int, int]] = []
        for t in times:
            parsed.append(_parse_time_token(t))

        if parsed:
            out[wd] = parsed

    # ordena horas por dia
    for wd in list(out.keys()):
        out[wd] = sorted(out[wd])

    return out


def expandir_dias_individuais(
    *,
    data_inicio: str,
    data_fim: str,
    horarios: str,
    venue: str,
    ticket_url: str,
) -> List[dict]:
    """Expande para sessões individuais (inclusive)."""

    start = _parse_iso_date(data_inicio)
    end = _parse_iso_date(data_fim)
    if end < start:
        raise RuntimeError(f"sessões: Data Fim < Data Início ({data_fim} < {data_inicio}).")

    weekly = parse_horarios_semanais(horarios)
    if not weekly:
        return []

    v = (venue or "").strip()
    if not v:
        raise RuntimeError("sessões: venue vazio.")

    t = (ticket_url or "").strip()
    if not t:
        raise RuntimeError("sessões: ticket_url vazio (no vosso fluxo é obrigatório).")

    out: List[dict] = []
    d = start
    while d <= end:
        wd = d.weekday()
        if wd in weekly:
            for (h, mi) in weekly[wd]:
                out.append(
                    {
                        "venue": v,
                        "date": d.isoformat(),
                        "hour": int(h),
                        "minute": int(mi),
                        "ticket_url": t,
                    }
                )
        d += timedelta(days=1)

    # dedupe mantendo ordem
    seen = set()
    uniq: List[dict] = []
    for s in out:
        k = (s["venue"], s["date"], s["hour"], s["minute"], s["ticket_url"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(s)

    return uniq
