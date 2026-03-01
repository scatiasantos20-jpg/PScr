# -*- coding: utf-8 -*-
"""Helpers Playwright (sync).

Patch: UUID correcto após criar peça
- O wait_for_uuid anterior fazia regex a QUALQUER UUID no HTML => podia apanhar um UUID antigo.
- Agora só aceita UUID no contexto de /adicionar/<uuid>/... (URL, hrefs/actions, etc.)
"""

from __future__ import annotations

import re
import time
from typing import Optional

from .logging_ptpt import Logger
from .utils import UUID_RE

logger = Logger()

# UUID específico do fluxo teatro.app (/adicionar/<uuid>/...)
_ADICIONAR_RE = re.compile(
    r"/adicionar/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:/|$)",
    re.I,
)
_ADICIONAR_STEP_RE = re.compile(
    r"/adicionar/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/(details|media|sessions)(?:\b|/|$)",
    re.I,
)


def wait_dom(page, timeout_ms: int = 15_000):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass


def dismiss_cookies(page):
    try:
        btn = page.get_by_role("button", name=re.compile(r"aceitar\s+e\s+continuar", re.I)).first
        if btn.count() > 0 and btn.is_visible():
            btn.click(timeout=2_000)
            logger.info("cookies: banner aceite/fechado.")
    except Exception:
        return


def is_login_page(page) -> bool:
    try:
        u = (page.url or "").lower()
    except Exception:
        u = ""
    if "/login" in u:
        return True
    try:
        return (
            page.locator('form[action="/login"][method="post"]').count() > 0
            and page.locator("input#password").count() > 0
        )
    except Exception:
        return False


def robust_fill(locator, value: str):
    value = (value or "").strip()
    locator.wait_for(state="visible", timeout=15_000)

    def read() -> str:
        try:
            return (locator.input_value() or "").strip()
        except Exception:
            try:
                return (locator.evaluate("el => el.value") or "").strip()
            except Exception:
                return ""

    try:
        locator.fill("")
    except Exception:
        pass
    try:
        locator.fill(value)
    except Exception:
        pass

    if read() != value:
        try:
            locator.click()
            locator.press("Control+A")
            locator.type(value, delay=35)
        except Exception:
            pass

    if read() != value:
        try:
            locator.evaluate(
                """(el, val) => {
                    const proto = Object.getPrototypeOf(el);
                    const desc = Object.getOwnPropertyDescriptor(proto, 'value');
                    if (desc && desc.set) { desc.set.call(el, val); } else { el.value = val; }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                value,
            )
        except Exception:
            pass

    for _ in range(10):
        time.sleep(0.2)
        if read() == value:
            return
    raise RuntimeError(f"não consegui preencher o input (ficou {read()!r}, esperado {value!r}).")


def robust_select_value(select_locator, value: str):
    value = (value or "").strip()
    if not value:
        return
    try:
        select_locator.select_option(value=value)
        return
    except Exception:
        pass
    try:
        select_locator.select_option(value=value, force=True)
        return
    except Exception:
        pass
    select_locator.evaluate(
        """(el, val) => {
            el.value = val;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        value,
    )


def _extract_uuid_from_adicionar_text(text: str) -> Optional[str]:
    if not text:
        return None
    m = _ADICIONAR_RE.search(text)
    if m:
        return m.group(1)
    return None


def extract_uuid(page) -> Optional[str]:
    """Extrai UUID com prioridade para /adicionar/<uuid>/..."""
    try:
        url = page.url or ""
    except Exception:
        url = ""
    uid = _extract_uuid_from_adicionar_text(url)
    if uid:
        return uid

    # tentar descobrir por href/action no DOM (mais fiável que varrer UUIDs soltos)
    try:
        a = page.locator(
            "a[href*='/adicionar/'][href*='/details'], a[href*='/adicionar/'][href*='/media'], a[href*='/adicionar/'][href*='/sessions']"
        ).first
        if a.count() > 0:
            href = a.get_attribute("href") or ""
            uid2 = _extract_uuid_from_adicionar_text(href)
            if uid2:
                return uid2
    except Exception:
        pass

    try:
        f = page.locator(
            "form[action*='/adicionar/'][action*='/details'], form[action*='/adicionar/'][action*='/media'], form[action*='/adicionar/'][action*='/sessions']"
        ).first
        if f.count() > 0:
            act = f.get_attribute("action") or ""
            uid2 = _extract_uuid_from_adicionar_text(act)
            if uid2:
                return uid2
    except Exception:
        pass

    # fallback: HTML inteiro, mas apenas no contexto /adicionar/<uuid>/
    try:
        html = page.content()
    except Exception:
        html = ""
    uid = _extract_uuid_from_adicionar_text(html or "")
    if uid:
        return uid

    return None


def wait_for_uuid(page, timeout_s: float = 20.0) -> str:
    """Espera por um URL /adicionar/<uuid>/... e devolve o UUID correcto."""
    # 1) preferir transição real de URL após "Adicionar nova peça"
    try:
        page.wait_for_url(_ADICIONAR_STEP_RE, timeout=int(timeout_s * 1000))
        m = _ADICIONAR_STEP_RE.search(page.url or "")
        if m:
            return m.group(1)
    except Exception:
        pass

    # 2) tentativas curtas a extrair do URL/DOM/HTML (apenas /adicionar/<uuid>/)
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        uid = extract_uuid(page)
        if uid:
            return uid
        time.sleep(0.25)

    # 3) último recurso: se existir só 1 UUID no HTML, aceita; se houver vários, falha (para não escolher errado)
    try:
        html = page.content() or ""
    except Exception:
        html = ""
    uuids = UUID_RE.findall(html)
    if len(uuids) == 1:
        return uuids[0]
    raise RuntimeError(
        f"não consegui obter o UUID correcto após criar a peça (encontrei {len(uuids)} UUID(s) no HTML)."
    )
