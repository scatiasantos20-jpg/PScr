from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from typing import Iterable


REQUIRED_FIELDS = ("Nome da Peça", "Link da Peça")


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def build_quality_snapshot(*, platform: str, total_scraped: int, total_to_sync: int, df: Any) -> dict[str, Any]:
    missing_required = 0
    with_sessions = 0

    if df is not None and not df.empty:
        for _, row in df.iterrows():
            if any(not str(row.get(col, "")).strip() for col in REQUIRED_FIELDS):
                missing_required += 1

            sessions = row.get("Teatroapp Sessions", [])
            if isinstance(sessions, list) and len(sessions) > 0:
                with_sessions += 1

    without_sessions = max(0, _to_int(total_to_sync) - with_sessions)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform,
        "totals": {
            "scraped": _to_int(total_scraped),
            "to_sync": _to_int(total_to_sync),
            "with_sessions": with_sessions,
            "without_sessions": without_sessions,
        },
        "quality": {
            "missing_required_fields": missing_required,
            "required_fields": list(REQUIRED_FIELDS),
        },
    }


def write_quality_report(*, platform: str, total_scraped: int, total_to_sync: int, df: Any) -> Path:
    cache_dir = Path((os.getenv("CACHE_DIR") or ".cache").strip() or ".cache").expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)

    payload = build_quality_snapshot(
        platform=platform,
        total_scraped=total_scraped,
        total_to_sync=total_to_sync,
        df=df,
    )

    out = cache_dir / f"extraction_quality_{platform}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
