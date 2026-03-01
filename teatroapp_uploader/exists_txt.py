# -*- coding: utf-8 -*-
from __future__ import annotations
import time
from pathlib import Path
from typing import Tuple

def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def _key(title: str, ticket_url: str) -> Tuple[str, str]:
    return ((title or "").strip().lower(), (ticket_url or "").strip().lower())

def append_exists_txt(
    path: Path,
    *,
    title: str,
    ticket_url: str,
    page_url: str = "",
    note: str = "Já existia no teatro.app",
) -> bool:
    """
    Apende linha TSV: Data/Hora \t Peça \t Bilhetes \t URL teatro.app \t Observações
    Evita duplicados por (título + bilhetes).
    """
    _ensure_parent_dir(path)
    wanted = _key(title, ticket_url)

    if path.exists():
        for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = ln.split("\t")
            if len(parts) >= 3:
                t = parts[1]
                u = parts[2]
                if _key(t, u) == wanted:
                    return False

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "\t".join([ts, title, ticket_url, page_url, note]).rstrip() + "\n"
    path.write_text((path.read_text(encoding="utf-8", errors="ignore") if path.exists() else "") + line, encoding="utf-8")
    return True