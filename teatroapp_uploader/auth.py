# -*- coding: utf-8 -*-
"""Login / autenticação."""

from __future__ import annotations

import re

from .env import Config
from .logging_ptpt import Logger
from .pw_helpers import wait_dom, dismiss_cookies, is_login_page
from .utils import sleep_jitter

logger = Logger()


def ensure_authenticated(page, cfg: Config) -> None:
    """Garante sessão autenticada (probe em /adicionar)."""
    logger.info("a navegar para: %s", f"{cfg.base_url}/adicionar")
    page.goto(f"{cfg.base_url}/adicionar", wait_until="domcontentloaded")
    wait_dom(page)
    dismiss_cookies(page)

    if not is_login_page(page):
        logger.info("autenticação: OK (já não estou no login em /adicionar).")
        return

    logger.info("probe /adicionar caiu em login. a efectuar login…")

    form = page.locator('form[action="/login"][method="post"]').first
    if form.count() == 0:
        raise RuntimeError("LOGIN: não encontrei o form action=/login.")

    email = form.locator("input#email").first
    password = form.locator("input#password").first
    if email.count() == 0 or password.count() == 0:
        raise RuntimeError("LOGIN: não encontrei input#email e/ou input#password.")

    email.fill(cfg.email)
    password.fill(cfg.password)

    btn = form.locator("button[type='submit']").filter(has_text=re.compile(r"iniciar sessão", re.I)).first
    if btn.count() == 0:
        btn = form.locator("button[type='submit']").first
    if btn.count() == 0:
        raise RuntimeError("LOGIN: não encontrei o botão submit.")

    dismiss_cookies(page)
    logger.info("LOGIN: a submeter…")
    btn.click()
    wait_dom(page)
    sleep_jitter(cfg.delay_min, cfg.delay_max, "após submeter login")

    logger.info("LOGIN: a validar sessão por probe a /adicionar…")
    page.goto(f"{cfg.base_url}/adicionar", wait_until="domcontentloaded")
    wait_dom(page)
    dismiss_cookies(page)

    if is_login_page(page):
        raise RuntimeError("LOGIN: continuo a cair no login após submeter credenciais.")

    logger.info("autenticação: OK (já não estou no login em /adicionar).")
