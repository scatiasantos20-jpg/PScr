from __future__ import annotations

from datetime import datetime
from typing import Any


REQUIRED_SESSION_KEYS = ("venue", "date", "hour", "minute", "ticket_url")


def normalize_ticket_url(ticket_url: Any, fallback_url: Any = "N/A") -> str:
    val = str(ticket_url or "").strip()
    if val and val.upper() != "N/A":
        return val
    fb = str(fallback_url or "").strip()
    return fb if fb else "N/A"


def normalize_teatroapp_sessions(sessions: Any) -> list[dict]:
    """
    Normaliza sessões para o formato esperado pelo teatro.app:
      {venue:str, date:YYYY-MM-DD, hour:int, minute:int, ticket_url:str}
    Entradas inválidas são ignoradas para evitar quebrar export.
    """
    out: list[dict] = []
    if not isinstance(sessions, list):
        return out

    for item in sessions:
        if not isinstance(item, dict):
            continue

        if not all(k in item for k in REQUIRED_SESSION_KEYS):
            continue

        try:
            venue = str(item.get("venue") or "").strip() or "Não indicado"
            date_s = str(item.get("date") or "").strip()
            hour = int(item.get("hour"))
            minute = int(item.get("minute"))
            ticket_url = str(item.get("ticket_url") or "").strip() or "N/A"

            if not date_s:
                continue
            # valida formato YYYY-MM-DD
            datetime.strptime(date_s, "%Y-%m-%d")
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                continue

            out.append(
                {
                    "venue": venue,
                    "date": date_s,
                    "hour": hour,
                    "minute": minute,
                    "ticket_url": ticket_url,
                }
            )
        except Exception:
            continue

    return out


def attach_teatroapp_fields(
    event: dict,
    *,
    ticket_url: Any,
    sessions: Any = None,
) -> dict:
    """
    Aplica campos padrão para integração com teatro.app de forma centralizada.
    """
    event["Link Sessões"] = normalize_ticket_url(ticket_url, event.get("Link da Peça"))
    event["Teatroapp Sessions"] = normalize_teatroapp_sessions(sessions)
    return event


def ensure_teatroapp_fields_dataframe(df):
    """
    Garante colunas `Link Sessões` e `Teatroapp Sessions` num DataFrame de eventos.
    Mantém shape original e devolve cópia normalizada.
    """
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return df

    if not isinstance(df, pd.DataFrame):
        return df

    if df.empty:
        out = df.copy()
        if "Link Sessões" not in out.columns:
            out["Link Sessões"] = pd.Series(dtype=str)
        if "Teatroapp Sessions" not in out.columns:
            out["Teatroapp Sessions"] = pd.Series(dtype=object)
        return out

    rows = []
    for row in df.to_dict(orient="records"):
        ev = dict(row)
        attach_teatroapp_fields(
            ev,
            ticket_url=ev.get("Link Sessões") or ev.get("Link da Peça"),
            sessions=ev.get("Teatroapp Sessions"),
        )
        rows.append(ev)

    return pd.DataFrame(rows)
