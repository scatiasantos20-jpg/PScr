# -*- coding: utf-8 -*-
"""Utilitários sem Playwright."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from .env import Session
from .logging_ptpt import Logger

logger = Logger()

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.I,
)


def sleep_jitter(min_s: float, max_s: float, motivo: str = "") -> None:
    import random
    t = random.uniform(min_s, max_s)
    if motivo:
        logger.info("a aguardar %.2f segundos (%s).", t, motivo)
    time.sleep(t)


def ensure_parent_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def append_json_array(path: Path, payload: dict) -> None:
    ensure_parent_dir(path)
    arr = []
    if path.exists():
        try:
            arr = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(arr, list):
                arr = []
        except Exception:
            arr = []
    arr.append(payload)
    path.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding="utf-8")


def load_sessions(path: Path) -> list[Session]:
    """
    Lê TEATROAPP_SESSIONS_JSON.
    Se não existir, cria um ficheiro de exemplo e falha com mensagem clara.
    """
    ensure_parent_dir(path)
    if not path.exists():
        exemplo = [
            {"venue": "Teatro Armando Cortez", "date": "2026-02-10", "hour": 21, "minute": 30, "ticket_url": "https://exemplo.pt/bilhetes"},
            {"venue": "Teatro Armando Cortez", "date": "2026-02-11", "hour": 21, "minute": 30, "ticket_url": "https://exemplo.pt/bilhetes1"},
        ]
        path.write_text(json.dumps(exemplo, ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(f"não encontro o JSON de sessões: {str(path)}. criei um ficheiro de exemplo; edita-o e volta a executar.")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"JSON de sessões inválido: {str(path)} ({e})")

    if not isinstance(data, list):
        raise RuntimeError("JSON de sessões: esperado um array/lista no topo.")

    out: list[Session] = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"JSON de sessões: item #{i} não é objecto.")
        venue = str(item.get("venue", "")).strip()
        date = str(item.get("date", "")).strip()
        hour = item.get("hour", None)
        minute = item.get("minute", None)
        ticket_url = str(item.get("ticket_url", "")).strip()

        if not venue:
            raise RuntimeError(f"JSON de sessões: item #{i} sem 'venue'.")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            raise RuntimeError(f"JSON de sessões: item #{i} 'date' inválida (esperado YYYY-MM-DD): {date!r}")
        if not isinstance(hour, int) or hour < 0 or hour > 23:
            raise RuntimeError(f"JSON de sessões: item #{i} 'hour' inválida (0-23): {hour!r}")
        if not isinstance(minute, int) or minute < 0 or minute > 59:
            raise RuntimeError(f"JSON de sessões: item #{i} 'minute' inválido (0-59): {minute!r}")

        out.append(Session(venue=venue, date=date, hour=hour, minute=minute, ticket_url=ticket_url))
    return out


def extract_uuid_from_url_or_html(url: str, html: str) -> Optional[str]:
    m = UUID_RE.search(url or "")
    if m:
        return m.group(0)
    m2 = UUID_RE.search(html or "")
    if m2:
        return m2.group(0)
    return None
