# -*- coding: utf-8 -*-
"""Runner principal (sync) — versão robusta.

Objectivo desta revisão:
- Diagnosticar e mitigar o erro intermitente:
  "Locator.wait_for: Target page, context or browser has been closed"

Estratégia:
- Anexar listeners (page.close / page.crash / browser.disconnected) para logging.
- Guardar last_url via framenavigated.
- Recriar a page e re-autenticar automaticamente (1 retry) quando detectar page fechada.
- Não fechar context/browser antes de gravar cookies/estado.

Notas:
- Mantém Playwright sync.
- Logs PT-PT pré-Acordo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from playwright.sync_api import sync_playwright  # type: ignore

from .auth import ensure_authenticated
from .env import Config
from .logging_ptpt import Logger
from .part1_details import run as run_part1
from .part2_media import run as run_part2
from .part3_sessions import run as run_part3
from .utils import ensure_parent_dir, load_sessions, sleep_jitter
from .wizard import step1_validate, step2_create

logger = Logger()


@dataclass
class RuntimeState:
    last_url: str = ""
    last_event: str = ""


def _attach_listeners(page, context, browser, state: RuntimeState) -> None:
    """Listeners de diagnóstico (não alteram o comportamento)."""

    def _on_nav(frame) -> None:
        try:
            if frame == page.main_frame:
                state.last_url = page.url or state.last_url
        except Exception:
            pass

    def _on_close() -> None:
        state.last_event = "page.close"
        logger.error("PLAYWRIGHT: a página foi fechada. last_url=%s", state.last_url)

    def _on_crash() -> None:
        state.last_event = "page.crash"
        logger.error("PLAYWRIGHT: a página crashou. last_url=%s", state.last_url)

    def _on_disconnected() -> None:
        state.last_event = "browser.disconnected"
        logger.error("PLAYWRIGHT: o browser desconectou. last_url=%s", state.last_url)

    try:
        page.on("framenavigated", _on_nav)
    except Exception:
        pass

    try:
        page.on("close", lambda: _on_close())
    except Exception:
        pass

    try:
        page.on("crash", lambda: _on_crash())
    except Exception:
        pass

    try:
        browser.on("disconnected", lambda: _on_disconnected())
    except Exception:
        pass


def _new_page(context, cfg: Config, state: RuntimeState):
    page = context.new_page()
    _attach_listeners(page, context, context.browser, state)  # type: ignore[attr-defined]
    ensure_authenticated(page, cfg)
    return page


def _ensure_live_page(page, context, cfg: Config, state: RuntimeState):
    try:
        if page is None:
            logger.warning("RUNNER: page=None; a criar nova página.")
            return _new_page(context, cfg, state)
        if page.is_closed():
            logger.warning("RUNNER: page fechada; a criar nova página.")
            return _new_page(context, cfg, state)
    except Exception:
        # se não conseguimos avaliar, recriar por segurança
        logger.warning("RUNNER: não consegui validar page; a criar nova página.")
        return _new_page(context, cfg, state)

    return page


def _run_step(name: str, fn: Callable[[], None], *, context, cfg: Config, state: RuntimeState, page_ref: dict) -> None:
    """Executa um passo com 1 retry automático se a page/context fechar."""
    for tentativa in (1, 2):
        page_ref["page"] = _ensure_live_page(page_ref.get("page"), context, cfg, state)
        try:
            logger.info("%s: início (tentativa %d) | url=%s", name, tentativa, getattr(page_ref["page"], "url", ""))
        except Exception:
            pass

        try:
            fn()
            try:
                logger.info("%s: fim | url=%s", name, getattr(page_ref["page"], "url", ""))
            except Exception:
                pass
            return
        except Exception as e:
            msg = str(e).lower()
            closed = "has been closed" in msg or "target page" in msg
            try:
                is_closed = page_ref["page"].is_closed()
            except Exception:
                is_closed = True

            if tentativa == 1 and (closed or is_closed):
                logger.error(
                    "%s: detectada página/context fechados; vou recriar e repetir 1 vez. last_url=%s | last_event=%s",
                    name,
                    state.last_url,
                    state.last_event,
                )
                # força nova page
                try:
                    page_ref["page"] = _new_page(context, cfg, state)
                except Exception:
                    pass
                continue

            raise


def run(cfg: Config) -> int:
    ensure_parent_dir(cfg.cookies_path)
    ensure_parent_dir(cfg.exists_json)
    ensure_parent_dir(cfg.sessions_json)

    sessions = load_sessions(cfg.sessions_json)

    logger.info("config: base_url=%s | headless=%s | dryrun=%s", cfg.base_url, cfg.headless, cfg.dryrun)
    logger.info("sessões: %d", len(sessions))

    with sync_playwright() as p:
        launch_opts = {"headless": cfg.headless}
        if getattr(cfg, "slow_mo_ms", 0):
            launch_opts["slow_mo"] = int(cfg.slow_mo_ms)

        browser = p.chromium.launch(**launch_opts)

        context_opts = {}
        if cfg.cookies_path.exists():
            context_opts["storage_state"] = str(cfg.cookies_path)
            logger.info("a carregar cookies/estado: %s", str(cfg.cookies_path))

        context = browser.new_context(**context_opts)
        state = RuntimeState()

        page_ref: dict = {"page": context.new_page()}
        _attach_listeners(page_ref["page"], context, browser, state)

        try:
            # garantir auth
            ensure_authenticated(page_ref["page"], cfg)
            sleep_jitter(cfg.delay_min, cfg.delay_max, "após autenticação")

            def _step1():
                return step1_validate(page_ref["page"], cfg)

            sleep_jitter(cfg.delay_min, cfg.delay_max, "após Step 1 (Validar)")

            res = _step1()
            if res == "exists":
                context.storage_state(path=str(cfg.cookies_path))
                logger.info("cookies/estado gravados em: %s", str(cfg.cookies_path))
                logger.info("terminado: peça já existia (registada em JSON).")
                return 0

            uuid = step2_create(page_ref["page"], cfg)

            sleep_jitter(cfg.delay_min, cfg.delay_max, "após criar peça (Step 2)")

            _run_step(
                "PARTE 1",
                lambda: run_part1(page_ref["page"], cfg, uuid),
                context=context,
                cfg=cfg,
                state=state,
                page_ref=page_ref,
            )

            _run_step(
                "PARTE 2",
                lambda: run_part2(page_ref["page"], cfg, uuid),
                context=context,
                cfg=cfg,
                state=state,
                page_ref=page_ref,
            )

            _run_step(
                "PARTE 3",
                lambda: run_part3(page_ref["page"], cfg, uuid, sessions),
                context=context,
                cfg=cfg,
                state=state,
                page_ref=page_ref,
            )

            context.storage_state(path=str(cfg.cookies_path))
            logger.info("cookies/estado gravados em: %s", str(cfg.cookies_path))
            logger.info("terminado: Parte 3 concluída.")
            return 0

        except Exception as e:
            logger.error("falha no run: %s", str(e))
            try:
                context.storage_state(path=str(cfg.cookies_path))
                logger.info("cookies/estado gravados em: %s", str(cfg.cookies_path))
            except Exception:
                pass
            return 2

        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass