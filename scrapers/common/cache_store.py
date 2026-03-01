from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from scrapers.common.df_utils import norm_str, ensure_cols
from scrapers.common.logging_ptpt import info, aviso, erro


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _parse_iso(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _get_cache_root() -> Path:
    cache_dir = os.getenv("CACHE_DIR", "").strip()
    if cache_dir:
        root = Path(cache_dir).expanduser().resolve()
    else:
        base_dir = (os.getenv("BASE_DIRECTORY", "").strip() or ".")
        root = (Path(base_dir).expanduser().resolve() / ".cache")
    return root / "tickets"


def cache_path(platform: str) -> Path:
    return _get_cache_root() / f"{platform}.json"


def cache_exists(platform: str) -> bool:
    return cache_path(platform).exists()


def _event_key(row: dict) -> str:
    link = norm_str(row.get("Link da Peça")).lower()
    if link and link != "n/a":
        return f"link::{link}"
    nome = norm_str(row.get("Nome da Peça")).lower()
    return f"nome::{nome}"


def load_existing_df_from_cache(*, platform: str, logger, label: str) -> pd.DataFrame:
    path = cache_path(platform)
    if not path.exists():
        aviso(logger, "cache.info.inexistente", label=label, ficheiro=str(path))
        return pd.DataFrame(columns=["Nome da Peça", "Data Fim", "Link da Peça", "Horários", "Preço Formatado"])

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("items", {})
        rows = list(items.values())
        df = pd.DataFrame(rows)
        df = ensure_cols(df, ["Nome da Peça", "Data Fim", "Link da Peça", "Horários", "Preço Formatado"])
        info(logger, "cache.info.carregado", label=label, n=len(df), ficheiro=str(path))
        return df
    except Exception as e:
        erro(logger, "cache.err.carregar", e, cache_key=f"cache:load:{platform}", label=label, ficheiro=str(path))
        return pd.DataFrame(columns=["Nome da Peça", "Data Fim", "Link da Peça", "Horários", "Preço Formatado"])


def update_cache_from_df(
    *,
    platform: str,
    logger,
    label: str,
    df_new: pd.DataFrame,
    merge: bool = True,
) -> None:
    path = cache_path(platform)
    path.parent.mkdir(parents=True, exist_ok=True)

    ttl_days_raw = os.getenv("CACHE_TTL_DAYS", "").strip()
    ttl_days: Optional[int] = None
    if ttl_days_raw:
        try:
            ttl_days = int(ttl_days_raw)
        except ValueError:
            ttl_days = None

    base: Dict[str, Any] = {
        "version": 1,
        "platform": platform,
        "updated_at": _now_iso(),
        "items": {},
    }

    if merge and path.exists():
        try:
            base = json.loads(path.read_text(encoding="utf-8"))
            if "items" not in base or not isinstance(base["items"], dict):
                base["items"] = {}
        except Exception:
            base["items"] = {}

    items: Dict[str, Any] = base.get("items", {})
    now = _now_iso()

    df_new = ensure_cols(df_new, ["Nome da Peça", "Data Fim", "Link da Peça", "Horários", "Preço Formatado"])

    for _, r in df_new.iterrows():
        row = r.to_dict()
        k = _event_key(row)
        items[k] = {
            "Nome da Peça": norm_str(row.get("Nome da Peça")),
            "Link da Peça": norm_str(row.get("Link da Peça")),
            "Data Fim": norm_str(row.get("Data Fim")) or "N/A",
            "Horários": norm_str(row.get("Horários")) or "N/A",
            "Preço Formatado": norm_str(row.get("Preço Formatado")) or "N/A",
            "last_seen": now,
        }

    # Limpeza por TTL (opcional)
    if ttl_days is not None:
        cutoff = datetime.utcnow() - timedelta(days=ttl_days)
        to_del = []
        for k, v in items.items():
            ls = _parse_iso(str(v.get("last_seen", "")))
            if ls is None:
                continue
            if ls.tzinfo is not None:
                ls_utc = ls.astimezone(tz=None).replace(tzinfo=None)
            else:
                ls_utc = ls
            if ls_utc < cutoff:
                to_del.append(k)
        for k in to_del:
            del items[k]

    base["items"] = items
    base["updated_at"] = now

    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        info(logger, "cache.info.gravado", label=label, n=len(items), ficheiro=str(path))
    except Exception as e:
        erro(logger, "cache.err.gravar", e, cache_key=f"cache:save:{platform}", label=label, ficheiro=str(path))
