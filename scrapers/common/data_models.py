from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .utils_scrapper import format_date_range, format_session_times

def _parse_iso_date(value: Any) -> Optional[str]:
    """
    Aceita:
      - 'YYYY-MM-DD'
      - ISO com hora (ex.: 'YYYY-MM-DDTHH:MM:SS' / com timezone)
      - datetime
    Devolve 'YYYY-MM-DD' ou None.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()

    if not isinstance(value, str):
        return None

    s = value.strip()
    if not s or s.upper() == "N/A":
        return None

    s_norm = s.replace("Z", "+00:00")

    try:
        dt = datetime.fromisoformat(s_norm)
        return dt.date().isoformat()
    except Exception:
        try:
            dt = datetime.strptime(s, "%Y-%m-%d")
            return dt.date().isoformat()
        except Exception:
            return None


def is_valid_iso_date(date_str: Any) -> bool:
    return _parse_iso_date(date_str) is not None


def build_event_dict(
    title,
    link,
    image=None,
    start_date=None,
    end_date=None,
    duration=None,
    location=None,
    city=None,
    price_str=None,
    promoter=None,
    synopsis=None,
    credits=None,
    age_rating=None,
    origin=None,
    schedule=None,
):
    # Horários: se vier um dict, converte para string (Ticketline/BOL podem gerar estruturas)
    if isinstance(schedule, dict):
        schedule = format_session_times(schedule)

    # Normalizar datas para YYYY-MM-DD quando possível
    start_norm = _parse_iso_date(start_date) or (start_date if start_date not in (None, "", "N/A") else None)
    end_norm = _parse_iso_date(end_date) or (end_date if end_date not in (None, "", "N/A") else None)

    # Defaults consistentes (evita None a entrar no pipeline)
    return {
        "Nome da Peça": title or "Sem título",
        "Link da Peça": link or "N/A",
        "Imagem": image or "N/A",
        "Data Início": start_norm or "N/A",
        "Data Fim": end_norm or "N/A",
        "Data Extenso": format_date_range(start_norm, end_norm),
        "Duração (minutos)": duration or "N/A",
        "Local": location or "N/A",
        "Concelho": city or "N/A",
        "Preço Formatado": price_str or "N/A",
        "Promotor": promoter or "N/A",
        "Sinopse": synopsis or "N/A",
        "Ficha Artística": credits or "N/A",
        "Faixa Etária": age_rating or "N/A",
        "Origem": origin or "N/A",
        "Horários": schedule or "N/A",
    }