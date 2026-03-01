# -*- coding: utf-8 -*-
"""
tools/limpar_cache.py

Limpa a cache (CACHE_DIR) mantendo:
- login (TEATROAPP_COOKIES)
- caches de peças já processadas (por defeito: .cache/tickets/* e teatroapp_exists.*)

Remove:
- posters temporários (.cache/poster.* e posters de batch)
- dumps HTML de debug (.cache/teatroapp_debug/*)
- payloads/sessões/overrides gerados (.cache/teatroapp_batch/*)
- ficheiros canónicos de export (teatroapp_payload.json, teatroapp_sessions.json, teatroapp_override.env, etc.)

Uso:
  python tools/limpar_cache.py --dry-run
  python tools/limpar_cache.py --apply

Opcional:
  python tools/limpar_cache.py --apply --keep-extra "teatroapp_batch_results.json"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, List, Set


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────────────

def _pt(msg: str) -> None:
    print(msg, flush=True)


def _is_true(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "sim", "yes", "y")


def _parse_dotenv(path: Path) -> dict:
    if not path.exists():
        return {}
    out: dict = {}
    for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        out[k] = v
    return out


def _env_get(key: str, dotenv: dict, default: str = "") -> str:
    return (os.getenv(key) or dotenv.get(key) or default or "").strip()


def _norm(p: Path) -> Path:
    try:
        return p.expanduser().resolve()
    except Exception:
        return p.expanduser()


def _safe_unlink(p: Path) -> bool:
    try:
        if p.is_file() or p.is_symlink():
            p.unlink(missing_ok=True)  # py>=3.8
            return True
    except Exception:
        return False
    return False


def _safe_rmtree(dir_path: Path) -> int:
    # apaga ficheiros recursivamente sem depender de shutil.rmtree (mais tolerante)
    count = 0
    if not dir_path.exists() or not dir_path.is_dir():
        return 0
    for p in sorted(dir_path.rglob("*"), reverse=True):
        try:
            if p.is_file() or p.is_symlink():
                if _safe_unlink(p):
                    count += 1
            elif p.is_dir():
                try:
                    p.rmdir()
                except Exception:
                    pass
        except Exception:
            pass
    try:
        dir_path.rmdir()
    except Exception:
        pass
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Regras de limpeza
# ─────────────────────────────────────────────────────────────────────────────

def _compute_paths(cache_dir: Path, cookies_path: Path) -> tuple[Set[Path], List[Path], List[Path]]:
    """
    Returns:
      keep: paths a manter (ficheiros e pastas)
      delete_files: ficheiros a apagar
      delete_dirs: pastas a apagar (recursivo)
    """
    keep: Set[Path] = set()

    # Manter cookies (login)
    if cookies_path:
        keep.add(_norm(cookies_path))

    # Manter caches de peças/tickets (já feitas / já vistas)
    tickets_dir = _norm(cache_dir / "tickets")
    if tickets_dir.exists():
        keep.add(tickets_dir)

    # Manter registos de "já existe no teatro.app"
    for name in ("teatroapp_exists.json", "teatroapp_exists.xlsx", "teatroapp_existentes.xlsx"):
        p = _norm(cache_dir / name)
        if p.exists():
            keep.add(p)

    # Mantém também "tickets/*.json" explicitamente (mesmo que a pasta não exista na altura do cálculo)
    keep.add(tickets_dir)

    # O que apagar (padrões)
    delete_files: List[Path] = []
    delete_dirs: List[Path] = []

    # Posters temporários no root
    for ext in ("png", "jpg", "jpeg", "webp"):
        delete_files.append(_norm(cache_dir / f"poster.{ext}"))

    # Teatro.app export canónico (debug)
    delete_files.extend([
        _norm(cache_dir / "teatroapp_payload.json"),
        _norm(cache_dir / "teatroapp_sessions.json"),
        _norm(cache_dir / "teatroapp_overrides.json"),
        _norm(cache_dir / "teatroapp_override.env"),
        _norm(cache_dir / "teatroapp_batch.json"),
        _norm(cache_dir / "teatroapp_batch_results.json"),
    ])

    # Pastas de trabalho temporárias
    delete_dirs.extend([
        _norm(cache_dir / "teatroapp_debug"),
        _norm(cache_dir / "teatroapp_batch"),
    ])

    return keep, delete_files, delete_dirs


def _is_under_keep(path: Path, keep: Set[Path]) -> bool:
    p = _norm(path)
    for k in keep:
        try:
            k = _norm(k)
            if p == k:
                return True
            # se o keep for uma pasta, qualquer coisa lá dentro é keep
            if k.is_dir() and str(p).startswith(str(k) + os.sep):
                return True
        except Exception:
            continue
    return False


def limpar_cache(*, cache_dir: Path, cookies_path: Path, apply: bool, keep_extra: Iterable[str] = ()) -> int:
    cache_dir = _norm(cache_dir)
    cookies_path = _norm(cookies_path) if cookies_path else Path()

    if not cache_dir.exists():
        _pt(f"[ERRO] CACHE_DIR não existe: {cache_dir}")
        return 2

    keep, delete_files, delete_dirs = _compute_paths(cache_dir, cookies_path)

    # keep-extra (ficheiros por nome em CACHE_DIR)
    for name in keep_extra:
        name = (name or "").strip()
        if not name:
            continue
        p = _norm(cache_dir / name)
        if p.exists():
            keep.add(p)

    # Expandir padrões adicionais (dentro de teatroapp_batch)
    batch_dir = _norm(cache_dir / "teatroapp_batch")
    if batch_dir.exists():
        # apagar poster_* (por item), payload_*, sessions_*, override_* etc.
        for p in batch_dir.glob("poster_*.*"):
            delete_files.append(_norm(p))
        for p in batch_dir.glob("payload_*.json"):
            delete_files.append(_norm(p))
        for p in batch_dir.glob("sessions_*.json"):
            delete_files.append(_norm(p))
        for p in batch_dir.glob("override_*.env"):
            delete_files.append(_norm(p))

    # Remover duplicados
    delete_files = list(dict.fromkeys(delete_files))
    delete_dirs = list(dict.fromkeys(delete_dirs))

    # Filtrar keep
    delete_files = [p for p in delete_files if p.exists() and not _is_under_keep(p, keep)]
    delete_dirs = [d for d in delete_dirs if d.exists() and not _is_under_keep(d, keep)]

    # Informação
    _pt("—" * 72)
    _pt(f"[INFO] CACHE_DIR: {cache_dir}")
    _pt(f"[INFO] Manter (keep):")
    for k in sorted(keep):
        _pt(f"  - {k}")

    _pt(f"[INFO] A apagar (ficheiros): {len(delete_files)}")
    for p in delete_files:
        _pt(f"  - {p}")

    _pt(f"[INFO] A apagar (pastas): {len(delete_dirs)}")
    for d in delete_dirs:
        _pt(f"  - {d}")
    _pt("—" * 72)

    if not apply:
        _pt("[INFO] DRY-RUN: nada foi apagado. Usa --apply para executar.")
        return 0

    # Apagar
    deleted_files = 0
    for p in delete_files:
        if _safe_unlink(p):
            deleted_files += 1

    deleted_in_dirs = 0
    for d in delete_dirs:
        deleted_in_dirs += _safe_rmtree(d)

    _pt(f"[OK] Apagado: ficheiros={deleted_files}, ficheiros_em_pastas={deleted_in_dirs}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--apply", action="store_true", help="Executa a limpeza (sem isto é dry-run).")
    ap.add_argument("--dry-run", action="store_true", help="Força dry-run (predefinição).")
    ap.add_argument("--dotenv", default=".env", help="Caminho para .env (opcional).")
    ap.add_argument("--keep-extra", action="append", default=[], help="Nome(s) extra a manter (em CACHE_DIR).")

    args = ap.parse_args(argv)

    dotenv = _parse_dotenv(Path(args.dotenv))
    cache_dir = Path(_env_get("CACHE_DIR", dotenv, ".cache"))
    cookies = Path(_env_get("TEATROAPP_COOKIES", dotenv, str(cache_dir / "teatroapp_cookies.json")))

    apply = bool(args.apply) and not bool(args.dry_run)
    return limpar_cache(cache_dir=cache_dir, cookies_path=cookies, apply=apply, keep_extra=args.keep_extra)


if __name__ == "__main__":
    raise SystemExit(main())
