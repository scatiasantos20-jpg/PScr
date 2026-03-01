from __future__ import annotations

import os
from typing import Iterable


def read_scrapers_from_env(
    env_var: str = "SCRAPERS",
    fallback_var: str = "SCRAPER",
    all_tokens: Iterable[str] = ("all", "todos"),
) -> list[str]:
    raw = (os.getenv(env_var) or os.getenv(fallback_var) or "").strip()
    if not raw:
        return []

    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    out: list[str] = []
    seen: set[str] = set()

    for p in parts:
        if p in all_tokens:
            return ["all"]
        if p not in seen:
            seen.add(p)
            out.append(p)

    return out