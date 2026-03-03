# -*- coding: utf-8 -*-
"""teatroapp_uploader.existing_checker

Detecção robusta de peças já existentes no teatro.app (com pesquisa na lista do manager).

Suporta a lista:
- https://teatro.app/manager/plays  (GET com ?search=...&status=...)

Ordem:
1) Se TEATROAPP_PIECES_LIST_URL (ou TEATROAPP_LIST_URL) estiver definido:
   - se for /manager/plays, usa pesquisa por querystring (mais fiável, evita paginação)
   - caso contrário, tenta pesquisa por input/Enter e varre links
2) Fallback no /adicionar: heurística de “já existe” (texto + correspondência do título)

Sem screenshots; sem web externa.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Optional, Tuple
from urllib.parse import urlencode, urlparse, urlunparse


_EXISTE_RE = re.compile(r"\bjá\s+existe\b|\bjá\s+foi\s+adicionad\w*\b|\bexistente\b|\bduplicad\w*\b|\be?n?contramos\s+estas\s+pe[cç]as\b", re.I)


def normalizar_texto(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9\s\-:_]", "", s)
    return s.strip()


def comparar_titulos(a: str, b: str) -> Tuple[bool, int]:
    """Devolve (match, score). Score maior = melhor."""
    na = normalizar_texto(a)
    nb = normalizar_texto(b)
    if not na or not nb:
        return (False, 0)
    if na == nb:
        return (True, 100)
    if na in nb or nb in na:
        return (True, 85)
    ta = set(na.split())
    tb = set(nb.split())
    inter = len(ta.intersection(tb))
    if inter >= max(2, min(len(ta), len(tb))):
        return (True, 50 + inter)
    return (False, 0)


def get_list_url(base_url: str) -> str:
    return (os.getenv("TEATROAPP_PIECES_LIST_URL") or os.getenv("TEATROAPP_LIST_URL") or "").strip()


def get_status_filter() -> str:
    # opcional: "ok", "draft", etc. vazio = All Statuses
    return (os.getenv("TEATROAPP_PIECES_STATUS") or "").strip()


def _find_search_input(page):
    locs = [
        page.locator('form[action="/manager/plays"][method="get"] input[name="search"]'),
        page.get_by_role("searchbox"),
        page.locator("input[type='search']"),
        page.locator("input[placeholder*='Search']"),
        page.locator("input[placeholder*='search']"),
        page.locator("input[placeholder*='Pesquis']"),
        page.locator("input[name*='search']"),
    ]
    for loc in locs:
        try:
            if loc.count() > 0:
                return loc.first
        except Exception:
            continue
    return None


def _candidate_links(page, *, href_prefixes: Tuple[str, ...] = ("/manager/plays/", "/adicionar/", "/plays/")):
    try:
        anchors = page.locator("a")
        n = min(anchors.count(), 800)
    except Exception:
        return []

    out = []
    for i in range(n):
        try:
            a = anchors.nth(i)
            href = (a.get_attribute("href") or "").strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            if href_prefixes and not any(href.startswith(p) for p in href_prefixes):
                # não é link de peça / manager
                continue
            txt = (a.inner_text() or "").strip()
            if not txt:
                continue
            out.append((txt, href))
        except Exception:
            continue
    return out


def _abs_url(base_url: str, href: str) -> str:
    if href.startswith("/"):
        return base_url.rstrip("/") + href
    return href


def _goto_manager_search(page, *, url: str, title: str, status: str) -> None:
    # constrói URL com querystring (GET) para evitar paginação
    parts = urlparse(url)
    qs = {}
    if title:
        qs["search"] = title
    if status:
        qs["status"] = status
    # manter outros params existentes (se houver)
    final_qs = urlencode(qs, doseq=True)
    new_parts = parts._replace(query=final_qs)
    qurl = urlunparse(new_parts)
    page.goto(qurl, wait_until="domcontentloaded")


def check_exists_in_list(page, *, base_url: str, title: str) -> Optional[str]:
    url = get_list_url(base_url)
    if not url:
        return None

    status = get_status_filter()

    # Caso específico: /manager/plays (tem pesquisa GET)
    if "/manager/plays" in url:
        _goto_manager_search(page, url=url, title=title, status=status)

        # se for redireccionado para login, não dá para validar
        try:
            cur = (page.url or "").lower()
            if "login" in cur or "entrar" in cur:
                return None
        except Exception:
            pass

        best_href = None
        best_score = 0
        for txt, href in _candidate_links(page, href_prefixes=("/manager/plays/", "/adicionar/")):
            ok, score = comparar_titulos(txt, title)
            if ok and score > best_score:
                best_score = score
                best_href = href

        if best_href and best_score >= 85:
            return _abs_url(base_url, best_href)

        # fallback: se a UI tiver cards com título em h2/h3, tenta por texto e link ancestral
        try:
            # encontra um elemento com texto exacto (normalizado) e procura link pai
            locator = page.get_by_text(title, exact=False)
            if locator.count() > 0:
                el = locator.first
                # procurar link mais próximo
                a = el.locator("xpath=ancestor-or-self::a[1]")
                if a.count() > 0:
                    href = (a.first.get_attribute("href") or "").strip()
                    if href:
                        return _abs_url(base_url, href)
        except Exception:
            pass

        return None

    # Genérico: abre a página e tenta pesquisar por input
    page.goto(url, wait_until="domcontentloaded")
    try:
        cur = (page.url or "").lower()
        if "login" in cur or "entrar" in cur:
            return None
    except Exception:
        pass

    s = _find_search_input(page)
    if s is not None:
        try:
            s.click()
            s.fill("")
            s.fill(title)
            # se houver botão Filter, clicar
            btn = page.locator('form[action="/manager/plays"][method="get"] button[type="submit"]').first
            if btn.count() > 0:
                btn.click()
            else:
                s.press("Enter")
            page.wait_for_timeout(600)
        except Exception:
            pass

    best_href = None
    best_score = 0
    for txt, href in _candidate_links(page):
        ok, score = comparar_titulos(txt, title)
        if ok and score > best_score:
            best_score = score
            best_href = href

    if best_href and best_score >= 85:
        return _abs_url(base_url, best_href)

    return None


def exists_hint_on_add_page(page, title: str) -> bool:
    """Heurística no /adicionar depois do Validar."""
    try:
        body = page.locator("body").inner_text()
    except Exception:
        body = ""

    if body and _EXISTE_RE.search(body):
        return True

    best_score = 0
    for txt, _href in _candidate_links(page, href_prefixes=("/manager/plays/", "/adicionar/", "/plays/")):
        ok, score = comparar_titulos(txt, title)
        if ok and score > best_score:
            best_score = score

    return best_score >= 85
