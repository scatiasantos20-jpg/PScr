# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from scrapers.common.logging_ptpt import configurar_logger, info, aviso, erro, flush_erros  # type: ignore


LOGGER = configurar_logger("teatroapp.batch")

def _is_true(name: str, default: str = "0") -> bool:
    v = (os.getenv(name, default) or "").strip().lower()
    return v in ("1", "true", "sim", "yes", "y")


def _norm_path_env(p: str) -> str:
    return (p or "").replace("\\", "/")


def _load_override_env(path: Path) -> Dict[str, str]:
    """
    Parser simples para ficheiros override_*.env.
    Evita interpretações/escapes de backslashes típicos de parsers dotenv em Windows.
    """
    if not path.exists():
        return {}

    out: Dict[str, str] = {}
    for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        out[k] = v
    return out

def _safe_ext(p: Path) -> str:
    ext = (p.suffix or "").lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp"):
        return ext
    return ".jpg"

def _copy_poster_to_cache(cache_dir: Path, poster_path: Path, *, idx: int) -> Path:
    if not poster_path.exists():
        raise FileNotFoundError(f"cartaz origem não existe: {poster_path}")

    posters_dir = cache_dir / "teatroapp_posters"
    posters_dir.mkdir(parents=True, exist_ok=True)

    ext = _safe_ext(poster_path)
    dst = posters_dir / f"{idx:03d}{ext}"  # ex.: 001.png

    dst.write_bytes(poster_path.read_bytes())

    if not dst.exists() or dst.stat().st_size == 0:
        raise FileNotFoundError(f"cartaz destino não foi criado: {dst}")

    return dst

def main(argv: list[str] | None = None) -> int:
    cache_dir = Path(os.getenv("CACHE_DIR", ".cache")).expanduser()
    batch_path = Path(os.getenv("TEATROAPP_BATCH_JSON", str(cache_dir / "teatroapp_batch.json"))).expanduser()
    results_path = Path(os.getenv("TEATROAPP_BATCH_RESULTS_JSON", str(cache_dir / "teatroapp_batch_results.json"))).expanduser()

    if not batch_path.exists():
        erro(LOGGER, "cache.info.inexistente", cache_key="teatroapp:batch:missing", label="teatro.app batch", ficheiro=str(batch_path))
        return 2

    try:
        batch = json.loads(batch_path.read_text(encoding="utf-8") or "[]")
    except Exception as e:
        erro(LOGGER, "cache.err.carregar", e, cache_key="teatroapp:batch:read", label="teatro.app batch", ficheiro=str(batch_path))
        return 2

    if not isinstance(batch, list) or not batch:
        erro(LOGGER, "cache.err.carregar", cache_key="teatroapp:batch:empty", label="teatro.app batch", ficheiro=str(batch_path))
        return 2

    strict = _is_true("TEATROAPP_AUTORUN_STRICT", "0")
    out: list[dict] = []

    LOGGER.info("teatro.app batch: início (%d itens) | %s", len(batch), str(batch_path))

    for i, item in enumerate(batch, start=1):
        title = (item.get("title") or "").strip() or "Sem título"
        override_env = Path(item.get("override_env") or "").expanduser()

        env = os.environ.copy()

        # overrides do item
        overrides = _load_override_env(override_env)
        if overrides:
            env.update(overrides)
        else:
            aviso(LOGGER, "cache.info.inexistente", label="teatro.app override", ficheiro=str(override_env))

        # garantir cartaz por item
        try:
            payload_path = Path(item.get("payload_path") or "").expanduser()
            if payload_path.exists():
                payload = json.loads(payload_path.read_text(encoding="utf-8") or "{}")
                poster_raw = ((payload.get("media") or {}).get("poster_path") or "").strip()
                if poster_raw:
                    psrc = Path(poster_raw)
                    if psrc.exists():
                       # pdst = _copy_poster_to_cache(cache_dir, psrc)
                       # env["TEATROAPP_POSTER_PATH"] = _norm_path_env(str(pdst))
                        pdst = _copy_poster_to_cache(cache_dir, psrc, idx=i)
                        env["TEATROAPP_POSTER_PATH"] = _norm_path_env(str(pdst))
                    else:
                        aviso(LOGGER, "cache.info.inexistente", label="teatro.app cartaz", ficheiro=str(psrc))
                else:
                    aviso(LOGGER, "cache.info.inexistente", label="teatro.app cartaz", ficheiro=str(payload_path))
            else:
                aviso(LOGGER, "cache.info.inexistente", label="teatro.app payload", ficheiro=str(payload_path))
        except Exception as e:
            aviso(LOGGER, "cache.err.carregar", label="teatro.app cartaz", ficheiro=str(e))

        LOGGER.info("teatro.app batch: [%d/%d] a correr uploader: %s", i, len(batch), title)

        try:
           # proc = subprocess.run([sys.executable, "-m", "teatroapp_uploader"], env=env)
            project_root = Path(__file__).resolve().parents[2]  # .../scrapers/common -> .../scrapers -> raiz
            env["PYTHONUNBUFFERED"] = "1"

            # Se quiseres forçar o launcher do Windows, define TEATROAPP_PY=py no .env
            py_cmd = (os.getenv("TEATROAPP_PY", "") or "").strip()
            if py_cmd:
                cmd = [py_cmd, "-u", "-m", "teatroapp_uploader"]
            else:
                cmd = [sys.executable, "-u", "-m", "teatroapp_uploader"]

            LOGGER.info("teatro.app batch: python=%s | cwd=%s", cmd[0], str(project_root))

            proc = subprocess.run(cmd, env=env, cwd=str(project_root))
            ok = proc.returncode == 0
            out.append({"idx": i, "title": title, "ok": ok, "returncode": proc.returncode})

            if ok:
                LOGGER.info("teatro.app batch: [%d/%d] OK: %s", i, len(batch), title)
            else:
                erro(LOGGER, "runner.sync_registo_falhou", cache_key=f"teatroapp:batch:item:{i}", origem="teatro.app uploader")
                if strict:
                    break

        except Exception as e:
            out.append({"idx": i, "title": title, "ok": False, "erro": str(e)})
            erro(LOGGER, "runner.sync_registo_falhou", e, cache_key=f"teatroapp:batch:item_exc:{i}", origem="teatro.app uploader")
            if strict:
                break

    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    ok_count = sum(1 for x in out if x.get("ok"))
    LOGGER.info("teatro.app batch: fim | ok=%d/%d | resultados=%s", ok_count, len(out), str(results_path))

    flush_erros(LOGGER)
    return 0 if out and all(x.get("ok") for x in out) else 1


if __name__ == "__main__":
    raise SystemExit(main())
