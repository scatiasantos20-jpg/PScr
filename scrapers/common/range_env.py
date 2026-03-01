from __future__ import annotations

from typing import Optional


def parse_global_event_range(raw: str | None) -> range | None:
    """
    Parser canónico para GLOBAL_EVENT_RANGE.

    Aceita:
      - vazio / all / * => None (processar todos)
      - "N" => range(1, N+1)
      - "A-B" ou "A:B" => range(A, B+1)

    Inválido => None.
    """
    raw_norm = (raw or "").strip().lower()
    if not raw_norm or raw_norm in {"all", "*"}:
        return None

    for sep in ("-", ":"):
        if sep in raw_norm:
            a, b = raw_norm.split(sep, 1)
            try:
                start = int(a.strip())
                end = int(b.strip())
            except ValueError:
                return None
            if start < 1 or end < start:
                return None
            return range(start, end + 1)

    try:
        end = int(raw_norm)
    except ValueError:
        return None
    if end < 1:
        return None
    return range(1, end + 1)


def in_range_1based(idx: int, r: Optional[range]) -> bool:
    if r is None:
        return True
    return idx in r
