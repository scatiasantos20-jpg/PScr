# -*- coding: utf-8 -*-
"""Wizard /adicionar (Step 1 + Step 2) — JSON-only.

Objectivo:
- Validar se a peça já existe no teatro.app.
- Se já existir: NÃO criar novamente e registar APENAS em JSON:
  - título
  - link de bilhetes (quando disponível)
  - url teatro.app (quando possível)

Notas:
- Se TEATROAPP_PIECES_LIST_URL (ou TEATROAPP_LIST_URL) estiver definido, tenta
  primeiro validar na lista do manager (/manager/plays?search=...).
- Mantém o fallback do fluxo /adicionar (Step 1 -> Validar -> detectar Step 2).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from .env import Config
from .logging_ptpt import Logger
from .pw_helpers import wait_dom, dismiss_cookies, robust_fill, wait_for_uuid
from .utils import sleep_jitter, append_json_array

logger = Logger()


def _first_ticket_url_from_sessions_json(path: Path) -> str:
    """Extrai o primeiro ticket_url não-vazio do TEATROAPP_SESSIONS_JSON."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(data, list):
        return ""
    for item in data:
        if not isinstance(item, dict):
            continue
        u = str(item.get("ticket_url") or "").strip()
        if u:
            return u
    return ""


def _extract_ticket_url(cfg: Config) -> str:
    """Tenta obter o link de bilhetes a partir do JSON de sessões (quando disponível)."""
    try:
        if hasattr(cfg, "sessions_json") and cfg.sessions_json and Path(cfg.sessions_json).exists():
            return _first_ticket_url_from_sessions_json(Path(cfg.sessions_json))
    except Exception:
        return ""
    return ""


def _record_exists(
    *,
    cfg: Config,
    title: str,
    ticket_url: str,
    page_url: str,
    reason: str,
) -> None:
    """Registo JSON-only (append em array)."""
    payload = {
        "queried_title": title,
        "exists": True,
        "ticket_url": ticket_url,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "page_url": page_url,
        "reason": reason,
    }
    append_json_array(cfg.exists_json, payload)
    logger.info("WIZARD: registo gravado em JSON: %s", str(cfg.exists_json))


def step1_validate(page, cfg: Config) -> str:
    """Preenche nome e valida. Retorna 'exists' ou 'not_exists'."""

    # 0) Verificação robusta via lista do manager (se configurada)
    exists_url: Optional[str] = None
    try:
        from .existing_checker import check_exists_in_list

        exists_url = check_exists_in_list(page, base_url=cfg.base_url, title=cfg.title)
    except Exception as e:
        logger.warning("WIZARD: check_exists_in_list indisponível/falhou: %s", str(e))
        exists_url = None

    if exists_url:
        logger.info("WIZARD: peça encontrada na lista (já existe): %s", exists_url)
        ticket_url = _extract_ticket_url(cfg)
        _record_exists(
            cfg=cfg,
            title=cfg.title,
            ticket_url=ticket_url,
            page_url=exists_url,
            reason="Já existia no teatro.app (manager list) — skip",
        )
        return "exists"

    # 1) Fallback no fluxo /adicionar
    logger.info("WIZARD: Step 1 — a preencher nome e a validar…")
    page.goto(f"{cfg.base_url}/adicionar", wait_until="domcontentloaded")
    wait_dom(page)
    dismiss_cookies(page)

    form = page.locator('form[action="/adicionar?index"][method="post"]').filter(
        has=page.locator('input[name="intent"][value="search"]')
    ).first
    if form.count() == 0:
        raise RuntimeError("WIZARD: não encontrei o form do Step 1 (intent=search).")

    title_input = form.locator('input[name="title"]').first
    if title_input.count() == 0:
        raise RuntimeError("WIZARD: não encontrei input name=title no Step 1.")

    logger.info("WIZARD: Step 1 — a escrever: %s", cfg.title)
    robust_fill(title_input, cfg.title)

    btn = form.locator("button[type='submit']").filter(has_text=re.compile(r"^validar$", re.I)).first
    if btn.count() == 0:
        btn = form.locator("button[type='submit']").first

    dismiss_cookies(page)
    logger.info("WIZARD: Step 1 — a clicar 'Validar'…")
    btn.click()
    wait_dom(page)
    sleep_jitter(cfg.delay_min, cfg.delay_max, "após Validar")

    step2 = page.locator('form[action="/adicionar?index"][method="post"]').filter(
        has=page.locator('input[name="intent"][value="create"]')
    ).first
    if step2.count() > 0:
        logger.info("WIZARD: Step 2 detectado (a peça não existe).")
        return "not_exists"

    logger.info("WIZARD: a assumir que a peça já existe. não vou adicionar novamente.")

    # tentar obter um URL real da peça (se a lista estiver configurada, repetir a tentativa)
    if not exists_url:
        try:
            from .existing_checker import check_exists_in_list

            exists_url = check_exists_in_list(page, base_url=cfg.base_url, title=cfg.title)
        except Exception:
            exists_url = None

    ticket_url = _extract_ticket_url(cfg)
    _record_exists(
        cfg=cfg,
        title=cfg.title,
        ticket_url=ticket_url,
        page_url=(exists_url or page.url or ""),
        reason="Já existia no teatro.app (skip)",
    )
    return "exists"


def step2_create(page, cfg: Config) -> str:
    logger.info("WIZARD: Step 2 — a clicar 'Adicionar nova peça'…")
    form = page.locator('form[action="/adicionar?index"][method="post"]').filter(
        has=page.locator('input[name="intent"][value="create"]')
    ).first
    if form.count() == 0:
        raise RuntimeError("WIZARD: não encontrei o form do Step 2 (intent=create).")

    btn = form.locator("button[type='submit']").filter(has_text=re.compile(r"adicionar\s+nova\s+peça", re.I)).first
    if btn.count() == 0:
        btn = form.locator("button[type='submit']").first

    dismiss_cookies(page)
    btn.click()
    wait_dom(page)
    sleep_jitter(cfg.delay_min, cfg.delay_max, "após criar peça")

    # 1) Preferência: URL /adicionar/<uuid>/details (navegação real)
    uid = None
    try:
        page.wait_for_url(re.compile(r".*/adicionar/[0-9a-f\-]{36}/(details|media|sessions).*", re.I), timeout=20_000)
        uid = wait_for_uuid(page, timeout_s=2.0)
    except Exception:
        uid = None

    # 2) Fallback: procurar link /adicionar/<uuid>/details associado ao título (se existir na página)
    if not uid:
        try:
            a = page.locator("a[href*='/adicionar/'][href*='/details']").filter(
                has_text=re.compile(re.escape(cfg.title), re.I)
            ).first
            if a.count() > 0:
                href = a.get_attribute("href") or ""
                m = re.search(r"/adicionar/([0-9a-f\-]{36})/", href, re.I)
                if m:
                    uid = m.group(1)
        except Exception:
            uid = None

    # 3) Último recurso: extractor robusto (apenas /adicionar/<uuid>/... e não UUIDs soltos)
    if not uid:
        uid = wait_for_uuid(page, timeout_s=20.0)

    logger.info("WIZARD: UUID obtido: %s", uid)
    return uid