from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

import pandas as pd
from dotenv import load_dotenv

from scrapers.common.cache_store import cache_exists, load_existing_df_from_cache, update_cache_from_df
from scrapers.common.df_compare import filter_new_or_changed_with_logs
from scrapers.common.df_utils import build_known_links, to_df
from scrapers.common.logging_ptpt import configurar_logger, erro, flush_erros, info, t
from scrapers.common.export_schema import ensure_export_schema
from scrapers.common.teatroapp_fields import ensure_teatroapp_fields_dataframe
from scrapers.common.selector_env import read_scrapers_from_env
from scrapers.common.utils_scrapper import delay_between_requests

load_dotenv()

logger = configurar_logger("scrapers.tickets")


def _is_true_env(name: str, default: str = "0") -> bool:
    v = (os.getenv(name, default) or "").strip().lower()
    return v in ("1", "true", "sim", "yes", "y")


@dataclass(frozen=True)
class Job:
    key: str
    label_key: str
    scrape_fn: Callable[..., Any]
    compare_fields: Tuple[str, ...] = ("Data Fim", "Link da Peça")
    uses_known_links: bool = True
    needs_compare: bool = True


def _label(job: Job) -> str:
    return t(job.label_key)


# ──────────────────────────────────────────────────────────────────────────────
# Scrapers
# ──────────────────────────────────────────────────────────────────────────────
def _scrape_bol(existing_df: pd.DataFrame, known_links: set[str]) -> pd.DataFrame:
    from scrapers.ticket_platforms.BOL import bol_scraper

    res = bol_scraper.scrape_theatre_info(known_titles=known_links)
    return to_df(res)


def _scrape_ticketline(existing_df: pd.DataFrame, known_links: set[str]) -> pd.DataFrame:
    from scrapers.ticket_platforms.Ticketline import listapecas

    res = listapecas.main(known_titles=known_links) or []
    return to_df(res)


def _scrape_imperdivel(existing_df: pd.DataFrame, known_links: set[str]) -> pd.DataFrame:
    # Imperdível usa existing_df para dedupe por Link da Peça
    from scrapers.ticket_platforms.Imperdivel import imperdivel_scraper

    res = imperdivel_scraper.scrape_event_links(existing_df)
    return to_df(res)


def _scrape_teatrovariedades(existing_df: pd.DataFrame, known_links: set[str]) -> pd.DataFrame:
    from scrapers.theaters.teatrovariedades import teatrovariedades_scraper

    res = teatrovariedades_scraper.scrape_teatro_variedades()
    return to_df(res)


JOBS: Dict[str, Job] = {
    "bol": Job(
        key="bol",
        label_key="tickets.job.bol",
        scrape_fn=_scrape_bol,
        uses_known_links=True,
        needs_compare=True,
    ),
    "ticketline": Job(
        key="ticketline",
        label_key="tickets.job.ticketline",
        scrape_fn=_scrape_ticketline,
        uses_known_links=True,
        needs_compare=True,
    ),
    # Imperdível já devolve “novos” por dedupe interno usando existing_df
    "imperdivel": Job(
        key="imperdivel",
        label_key="tickets.job.imperdivel",
        scrape_fn=_scrape_imperdivel,
        uses_known_links=False,
        needs_compare=False,
    ),
    "teatrovariedades": Job(
        key="teatrovariedades",
        label_key="tickets.job.teatrovariedades",
        scrape_fn=_scrape_teatrovariedades,
        uses_known_links=False,
        needs_compare=True,
    ),
}


def available() -> list[str]:
    return list(JOBS.keys())


# ──────────────────────────────────────────────────────────────────────────────
# Existing (cache → vazio)
# ──────────────────────────────────────────────────────────────────────────────
def _empty_existing_df() -> pd.DataFrame:
    # Colunas mínimas esperadas pelos helpers (build_known_links/diff)
    return pd.DataFrame(columns=["Nome da Peça", "Data Fim", "Link da Peça", "Horários", "Preço Formatado"])


def _load_existing_for_job(job: Job, label: str) -> pd.DataFrame:
    # 1) cache (preferencial)
    if cache_exists(job.key):
        df = load_existing_df_from_cache(platform=job.key, logger=logger, label=label)
        return to_df(df)

    # 2) sem Notion: baseline vazio
    return _empty_existing_df()


# ──────────────────────────────────────────────────────────────────────────────
# Teatro.app export + autorun
# ──────────────────────────────────────────────────────────────────────────────
def _teatroapp_sources() -> set[str]:
    """Fontes autorizadas para export para Teatro.app.

    - vazio/"all"/"todos" => todas as plataformas registadas em JOBS
    - csv explícito => apenas as plataformas listadas
    """
    raw = (os.getenv("TEATROAPP_EXPORT_SOURCES", "all") or "all").strip().lower()
    if raw in ("", "all", "todos"):
        return set(JOBS.keys())

    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return set(parts) if parts else set(JOBS.keys())


def _emit_scraper_metrics(*, job_key: str, label: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        info(logger, "tickets.metrics.resumo", label=label, total=0, com_sessions=0, sem_sessions=0)
        return

    total = len(df)
    with_sessions = 0
    if "Teatroapp Sessions" in df.columns:
        with_sessions = sum(1 for x in df["Teatroapp Sessions"].tolist() if isinstance(x, list) and len(x) > 0)
    without_sessions = max(0, total - with_sessions)

    info(
        logger,
        "tickets.metrics.resumo",
        label=label,
        total=total,
        com_sessions=with_sessions,
        sem_sessions=without_sessions,
    )


def _maybe_export_and_autorun_teatroapp(*, job: Job, label: str, df_to_sync: pd.DataFrame, new_df: pd.DataFrame) -> int:
    if job.key not in _teatroapp_sources():
        return 0
    if not _is_true_env("TEATROAPP_EXPORT", "1"):
        return 0

    # Export
    try:
        # Mantém nome por compatibilidade (mesmo que a fonte não seja BOL)
        from scrapers.common.teatroapp_export import BATCH_JSON, export_teatroapp_from_df  # type: ignore

        info(logger, "teatroapp.export.inicio", label=label)
        export_input = df_to_sync if not df_to_sync.empty else new_df
        export_input = ensure_teatroapp_fields_dataframe(export_input)
        ensure_export_schema(job.key, export_input)
        _emit_scraper_metrics(job_key=job.key, label=label, df=export_input)
        export_teatroapp_from_df(export_input)
        info(logger, "teatroapp.export.ok", label=label)

    except Exception as e:
        erro(logger, "teatroapp.export.falhou", e, cache_key=f"teatroapp:export:{job.key}", label=label)
        if _is_true_env("TEATROAPP_EXPORT_STRICT", "0"):
            flush_erros(logger)
            return 1
        return 0

    # Autorun batch runner
    if not _is_true_env("TEATROAPP_AUTORUN", "0"):
        return 0

    try:
        import subprocess as _subprocess

        from scrapers.common.teatroapp_export import BATCH_JSON  # type: ignore

        env = os.environ.copy()
        env["TEATROAPP_BATCH_JSON"] = str(BATCH_JSON)

        # Garantir cwd na raiz do projeto (para .env e paths relativos)
        project_root = Path(__file__).resolve().parents[1]  # .../scrapers/main_tickets.py -> raiz

        info(logger, "teatroapp.autorun.inicio", label=label)

        cmd = [sys.executable, "-u", "-m", "scrapers.common.teatroapp_batch_runner"]

        if _is_true_env("TEATROAPP_AUTORUN_BLOCKING", "0"):
            proc = _subprocess.run(cmd, env=env, cwd=str(project_root))
            if proc.returncode != 0:
                raise RuntimeError(f"teatroapp_batch_runner devolveu código {proc.returncode}")
        else:
            _subprocess.Popen(cmd, env=env, cwd=str(project_root))

        info(logger, "teatroapp.autorun.ok", label=label)

    except Exception as e:
        erro(logger, "teatroapp.autorun.falhou", e, cache_key=f"teatroapp:autorun:{job.key}", label=label)
        if _is_true_env("TEATROAPP_AUTORUN_STRICT", "0"):
            flush_erros(logger)
            return 1

    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────────────
def run_one(key: str) -> int:
    k = (key or "").strip().lower()
    if k not in JOBS:
        erro(
            logger,
            "tickets.err.scraper_desconhecido",
            cache_key="tickets:job_unknown",
            key=key,
            opcoes=", ".join(available()),
        )
        return 2

    job = JOBS[k]
    label = _label(job)

    info(logger, "tickets.info.inicio_job", label=label)

    # 1) existentes (cache -> vazio se cache não existir)
    existing_df = _load_existing_for_job(job, label)
    known_links = build_known_links(existing_df) if job.uses_known_links else set()

    # 2) scrape
    try:
        new_df = job.scrape_fn(existing_df, known_links)
    except Exception as e:
        erro(logger, "tickets.err.scrape", e, cache_key=f"tickets:scrape:{job.key}", label=label)
        flush_erros(logger)
        return 1

    new_df = to_df(new_df)
    if new_df.empty:
        info(logger, "tickets.info.sem_dados", label=label)
        flush_erros(logger)
        return 0

    # 3) delay anti-bot
    delay_between_requests(logger_obj=logger, message_key="tickets.delay.antes_processar", label=label)

    # 4) filtrar novos/alterados
    if job.needs_compare:
        df_to_sync = filter_new_or_changed_with_logs(
            new_df,
            existing_df,
            logger=logger,
            label=label,
            fields=job.compare_fields,
        )
        if df_to_sync.empty:
            info(logger, "tickets.info.sem_alteracoes", label=label)
            update_cache_from_df(platform=job.key, logger=logger, label=label, df_new=new_df, merge=True)
            flush_erros(logger)
            return 0
    else:
        # ex.: Imperdível: o próprio scraper já devolve “novos”
        df_to_sync = new_df

    info(logger, "tickets.info.para_sincronizar", label=label, n=len(df_to_sync))

    # 4.5) Teatro.app export + autorun (se configurado)
    rc = _maybe_export_and_autorun_teatroapp(job=job, label=label, df_to_sync=df_to_sync, new_df=new_df)
    if rc != 0:
        return rc

    # 6) actualizar cache por plataforma (sempre)
    update_cache_from_df(platform=job.key, logger=logger, label=label, df_new=new_df, merge=True)

    info(logger, "tickets.info.concluido_job", label=label)
    flush_erros(logger)
    return 0


def run_many(keys: list[str]) -> int:
    ok = True
    for k in keys:
        if run_one(k) != 0:
            ok = False
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if "--listar" in argv:
        info(logger, "tickets.info.disponiveis", lista=", ".join(available()))
        return 0

    keys = read_scrapers_from_env()
    if not keys:
        erro(logger, "tickets.err.env_vazio", cache_key="tickets:env_empty", opcoes=", ".join(available()))
        return 2

    if keys == ["all"]:
        keys = available()

    invalidos = [k for k in keys if k not in JOBS]
    if invalidos:
        erro(
            logger,
            "tickets.err.env_desconhecidos",
            cache_key="tickets:env_unknown",
            invalidos=", ".join(invalidos),
            opcoes=", ".join(available()),
        )
        return 2

    info(logger, "tickets.info.inicio_run", n=len(keys), lista=", ".join(keys))

    ok = True
    for k in keys:
        if run_one(k) != 0:
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))