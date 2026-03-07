# -*- coding: utf-8 -*-
"""Parte 1 — Folha de Sala (/details).

Compatibilidade:
- O runner histórico faz: `from .part1_details import run as run_part1`
  e pode chamar:
    - run(page, uuid)
    - run(page, cfg, uuid)
    - run(page, cfg)
    - run(page, uuid=..., cfg=...)

Robustez:
- /details por vezes devolve uma página genérica "Lamentamos mas ocorreu um erro." (intermitente).
  Fazemos reload e guardamos HTML de debug.
- Se existirem valores em env e não encontrarmos os inputs, falhamos cedo e guardamos HTML.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.sync_api import Locator, Page


# ─────────────────────────────────────────────────────────────────────────────
# Debug
# ─────────────────────────────────────────────────────────────────────────────

CACHE_DIR = Path(os.getenv("CACHE_DIR", ".cache")).expanduser()
DEBUG_DIR = CACHE_DIR / "teatroapp_uploader_debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


def _is_true(v: Optional[str], default: str = "0") -> bool:
    s = (v if v is not None else default).strip().lower()
    return s in ("1", "true", "yes", "y", "sim")


def _debug_dump_html(page: Page, *, uuid: str, motivo: str) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = DEBUG_DIR / f"details_{uuid}_{motivo}_{ts}.html"
    try:
        out.write_text(page.content(), encoding="utf-8", errors="ignore")
    except Exception:
        out.write_text("(falhou a capturar HTML)", encoding="utf-8", errors="ignore")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Config (lê env; ignora cfg para compatibilidade)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DetailsConfig:
    uuid: str
    title: str
    company: str
    director: str
    playwriter: str
    synopsis: str
    genre: str
    age_rating: str
    duration: str
    release_date: str
    venue: str
    ticket_url: str
    event_url: str
    poster_path: str
    base_url: str


def _get_cfg_from_env(uuid: str) -> DetailsConfig:
    def env(k: str, default: str = "") -> str:
        return (os.getenv(k, default) or "").strip()

    # base_url: tenta env, fallback seguro
    base_url = env("TEATROAPP_BASE_URL", env("BASE_URL", "https://teatro.app")) or "https://teatro.app"

    return DetailsConfig(
        uuid=uuid,
        title=env("TEATROAPP_TITLE"),
        company=env("TEATROAPP_COMPANY"),
        director=env("TEATROAPP_DIRECTOR"),
        playwriter=env("TEATROAPP_PLAYWRITER"),
        synopsis=env("TEATROAPP_SYNOPSIS"),
        genre=env("TEATROAPP_GENRE"),
        age_rating=env("TEATROAPP_AGE_RATING"),
        duration=env("TEATROAPP_DURATION"),
        release_date=env("TEATROAPP_RELEASE_DATE"),
        venue=env("TEATROAPP_VENUE"),
        ticket_url=env("TEATROAPP_TICKET_URL"),
        event_url=env("TEATROAPP_EVENT_URL"),
        poster_path=env("TEATROAPP_POSTER_PATH"),
        base_url=base_url.rstrip("/"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fill_delay_ms() -> int:
    try:
        v = int((os.getenv("TEATROAPP_FILL_DELAY_MS", "120") or "120").strip())
    except Exception:
        v = 120
    return max(0, v)


def robust_fill(locator: Locator, value: str, *, clear: bool = True, timeout_ms: int = 15000) -> None:
    value = (value or "").strip()
    locator.wait_for(state="visible", timeout=timeout_ms)

    def _read() -> str:
        try:
            return (locator.input_value() or "").strip()
        except Exception:
            try:
                return (locator.evaluate("el => el.value") or "").strip()
            except Exception:
                return ""

    if clear:
        try:
            locator.fill("")
        except Exception:
            pass

    try:
        locator.fill(value)
    except Exception:
        pass

    if _read() != value:
        try:
            locator.click()
            locator.press("Control+A")
            locator.type(value, delay=_fill_delay_ms())
        except Exception:
            pass

    for _ in range(12):
        if _read() == value:
            return
        time.sleep(0.2)


def robust_click(locator: Locator, *, timeout_ms: int = 15000) -> None:
    locator.wait_for(state="visible", timeout=timeout_ms)
    locator.click()


def _field_control_by_label(form: Locator, label_re: re.Pattern) -> Locator:
    """Encontra control associado a label (input/textarea/select/combobox)."""
    labels = form.locator("label")
    for i in range(labels.count()):
        lab = labels.nth(i)
        try:
            txt = (lab.inner_text() or "").strip()
        except Exception:
            txt = ""
        if not txt or not label_re.search(txt):
            continue

        # 1) for=...
        try:
            for_attr = (lab.get_attribute("for") or "").strip()
        except Exception:
            for_attr = ""
        if for_attr:
            cand = form.locator(f"#{for_attr}")
            if cand.count() > 0:
                return cand.first

        # 2) label wraps control
        cand = lab.locator("input, textarea, select, button[role='combobox'], [contenteditable='true']")
        if cand.count() > 0:
            return cand.first

        # 3) same block (1–3 níveis acima)
        for xp in ("xpath=..", "xpath=../..", "xpath=../../.."):
            cand = lab.locator(xp).locator("input, textarea, select, button[role='combobox'], [contenteditable='true']").first
            if cand.count() > 0:
                return cand

    # fallback aria-label/placeholder
    cand = form.locator("input[aria-label], textarea[aria-label], select[aria-label], [contenteditable='true'][aria-label]")
    for i in range(cand.count()):
        el = cand.nth(i)
        aria = (el.get_attribute("aria-label") or "").strip()
        if aria and label_re.search(aria):
            return el

    cand = form.locator("input[placeholder], textarea[placeholder], [contenteditable='true'][placeholder]")
    for i in range(cand.count()):
        el = cand.nth(i)
        ph = (el.get_attribute("placeholder") or "").strip()
        if ph and label_re.search(ph):
            return el

    return form.locator("__never__")


def _control_by_attr(form: Locator, *names: str) -> Locator:
    """Fallback por id/name."""
    for n in names:
        n = (n or "").strip()
        if not n:
            continue
        cand = form.locator(f"[id='{n}'], [name='{n}']")
        if cand.count() > 0:
            return cand.first
    return form.locator("__never__")


def _set_control_value(page: Page, control: Locator, value: str) -> None:
    """Preenche input/textarea; se for select, tenta select_option; se for combobox, tenta escolher por texto."""
    value = (value or "").strip()
    if not value:
        return

    try:
        tag = (control.evaluate("el => el.tagName") or "").upper()
    except Exception:
        tag = ""

    # SELECT
    if tag == "SELECT":
        try:
            control.select_option(label=value)
            return
        except Exception:
            pass
        # tenta value
        try:
            control.select_option(value=value)
            return
        except Exception:
            pass
        # fallback: tentar pelo número dentro do texto
        m = re.search(r"(\d+)", value)
        if m:
            try:
                control.select_option(label=m.group(1))
                return
            except Exception:
                pass
        raise RuntimeError(f"PARTE 1: não consegui seleccionar opção no <select>: {value!r}")

    # Combobox (Radix/shadcn)
    if tag == "BUTTON":
        try:
            role = (control.get_attribute("role") or "").lower()
        except Exception:
            role = ""
        if role == "combobox":
            control.click()
            time.sleep(0.25)

            # tenta achar dialog via aria-controls
            try:
                cid = (control.get_attribute("aria-controls") or "").strip()
            except Exception:
                cid = ""
            dlg = page.locator(f"#{cid}") if cid else page.locator("[role='dialog']").last
            try:
                dlg.wait_for(state="visible", timeout=5000)
            except Exception:
                pass

            # procurar opções
            opt = dlg.locator("[role='option']").filter(has_text=re.compile(re.escape(value), re.I)).first
            if opt.count() == 0:
                # tenta número
                m = re.search(r"(\d+)", value)
                if m:
                    opt = dlg.locator("[role='option']").filter(has_text=re.compile(rf"\b{m.group(1)}\b")).first

            if opt.count() == 0:
                raise RuntimeError(f"PARTE 1: não encontrei opção no combobox para {value!r}")

            opt.click()
            time.sleep(0.2)
            # fechar de forma segura (clicar fora)
            try:
                page.mouse.click(5, 5)
            except Exception:
                pass
            return

    # INPUT/TEXTAREA / contenteditable
    if tag in ("DIV", "P", "SPAN"):
        try:
            cedit = (control.get_attribute("contenteditable") or "").lower()
        except Exception:
            cedit = ""
        if cedit == "true":
            try:
                control.click()
                control.press("Control+A")
                control.type(value, delay=_fill_delay_ms())
                return
            except Exception:
                pass

    robust_fill(control, value)


def _is_error_page(page: Page) -> bool:
    try:
        txt = (page.locator("body").inner_text() or "").strip().lower()
    except Exception:
        return False
    return ("lamentamos" in txt) and ("ocorreu um erro" in txt)


def _wait_for_details_form(page: Page, uuid: str, *, timeout_ms: int = 25000) -> Locator:
    start = time.time()
    while (time.time() - start) * 1000 < timeout_ms:
        try:
            if _is_error_page(page):
                _debug_dump_html(page, uuid=uuid, motivo="details_pagina_erro")
                page.reload(wait_until="domcontentloaded")
                time.sleep(1)
        except Exception:
            pass

        form = page.locator("form").first
        try:
            if form.is_visible():
                return form
        except Exception:
            pass

        time.sleep(0.5)

    _debug_dump_html(page, uuid=uuid, motivo="details_form_timeout")
    raise RuntimeError("PARTE 1: timeout a aguardar form no /details")


# ─────────────────────────────────────────────────────────────────────────────
# Core
# ─────────────────────────────────────────────────────────────────────────────

def _before_next_delay_s() -> float:
    try:
        v = float((os.getenv("TEATROAPP_BEFORE_NEXT_DELAY_S", "1.5") or "1.5").strip().replace(",", "."))
    except Exception:
        v = 1.5
    return max(0.0, v)


def run_part1_details(page: Page, *, uuid: str) -> None:
    cfg = _get_cfg_from_env(uuid)
    strict = _is_true(os.getenv("TEATROAPP_AUTORUN_STRICT"), "0")

    # Navegar SEMPRE pelo UUID (evita /media/details, etc.)
    details_url = f"{cfg.base_url}/adicionar/{uuid}/details"
    page.goto(details_url, wait_until="domcontentloaded")

    form = _wait_for_details_form(page, uuid)

    # Título (se existir, tem de colar)
    if cfg.title:
        title_loc = _field_control_by_label(form, re.compile(r"T[ií]tulo|Nome\s+da\s+pe[çc]a|Nome", re.I))
        if title_loc.count() == 0:
            _debug_dump_html(page, uuid=uuid, motivo="titulo_input_nao_encontrado")
            raise RuntimeError("PARTE 1: cfg.title existe mas não encontrei o input de título no /details.")
        _set_control_value(page, title_loc, cfg.title)

    # Obrigatórios: companhia / encenação / argumento
    company = (cfg.company or "").strip()
    director = (cfg.director or "").strip()
    playwriter = (cfg.playwriter or "").strip()

    missing = []
    if not company:
        missing.append("TEATROAPP_COMPANY")
    if not director:
        missing.append("TEATROAPP_DIRECTOR")
    if not playwriter:
        missing.append("TEATROAPP_PLAYWRITER")

    if missing:
        _debug_dump_html(page, uuid=uuid, motivo="campos_obrigatorios_em_falta")
        msg = "PARTE 1: campos obrigatórios em falta no /details: " + ", ".join(missing)
        if strict:
            raise RuntimeError(msg)
        company = company or "Sem info"
        director = director or "Sem info"
        playwriter = playwriter or "Sem info"

    # Companhia
    company_loc = _field_control_by_label(
        form,
        re.compile(r"Companhia\s+de\s+teatro|companhia/grupo|\bCompanhia\b|\bGrupo\b|Produ[çc][aã]o", re.I),
    )
    if company_loc.count() == 0:
        company_loc = _control_by_attr(form, "company", "companyName")
    if company_loc.count() == 0:
        _debug_dump_html(page, uuid=uuid, motivo="companhia_input_nao_encontrado")
        raise RuntimeError("PARTE 1: não encontrei o campo de Companhia no /details.")
    _set_control_value(page, company_loc, company)

    # Encenação / Direção
    director_loc = _field_control_by_label(form, re.compile(r"Encena[çc][aã]o|Dire[çc][aã]o", re.I))
    if director_loc.count() == 0:
        director_loc = _control_by_attr(form, "director")
    if director_loc.count() == 0:
        _debug_dump_html(page, uuid=uuid, motivo="encenacao_input_nao_encontrado")
        raise RuntimeError("PARTE 1: não encontrei o campo de Encenação/Direção no /details.")
    _set_control_value(page, director_loc, director)

    # Argumento / Texto / Autor
    play_loc = _field_control_by_label(form, re.compile(r"Argumento|Texto|Dramaturgia|Autor", re.I))
    if play_loc.count() == 0:
        play_loc = _control_by_attr(form, "playwriter", "author")
    if play_loc.count() == 0:
        _debug_dump_html(page, uuid=uuid, motivo="argumento_input_nao_encontrado")
        raise RuntimeError("PARTE 1: não encontrei o campo de Argumento/Texto/Autor no /details.")
    _set_control_value(page, play_loc, playwriter)

    # Sinopse
    synopsis = (cfg.synopsis or "").strip()
    if synopsis:
        syn_loc = _field_control_by_label(form, re.compile(r"Sinopse|Descri[çc][aã]o", re.I))
        if syn_loc.count() == 0:
            syn_loc = _control_by_attr(form, "synopsis", "description")
        if syn_loc.count() == 0:
            _debug_dump_html(page, uuid=uuid, motivo="sinopse_input_nao_encontrado")
            raise RuntimeError("PARTE 1: TEATROAPP_SYNOPSIS existe mas não encontrei o campo de Sinopse no /details.")
        _set_control_value(page, syn_loc, synopsis)

    # Duração / Idade (se existirem)
    if cfg.duration:
        dur_loc = _field_control_by_label(form, re.compile(r"Dura[çc][aã]o", re.I))
        if dur_loc.count() == 0:
            dur_loc = _control_by_attr(form, "duration", "durationMinutes")
        if dur_loc.count() == 0:
            _debug_dump_html(page, uuid=uuid, motivo="duracao_input_nao_encontrado")
            raise RuntimeError("PARTE 1: TEATROAPP_DURATION existe mas não encontrei o campo de Duração no /details.")
        _set_control_value(page, dur_loc, cfg.duration)

    if cfg.age_rating:
        age_loc = _field_control_by_label(form, re.compile(r"Idade|Classifica[çc][aã]o", re.I))
        if age_loc.count() == 0:
            age_loc = _control_by_attr(form, "ageRating", "age_rating", "age")
        if age_loc.count() == 0:
            _debug_dump_html(page, uuid=uuid, motivo="idade_input_nao_encontrado")
            raise RuntimeError("PARTE 1: TEATROAPP_AGE_RATING existe mas não encontrei o campo de Idade/Classificação no /details.")
        _set_control_value(page, age_loc, cfg.age_rating)

    # Links (se existirem no form)
    if cfg.ticket_url:
        t_loc = _field_control_by_label(form, re.compile(r"Bilhetes|Ticket", re.I))
        if t_loc.count() == 0:
            t_loc = _control_by_attr(form, "ticketUrl", "ticket_url")
        if t_loc.count() > 0:
            _set_control_value(page, t_loc, cfg.ticket_url)

    if cfg.event_url:
        e_loc = _field_control_by_label(form, re.compile(r"Evento|Site|URL", re.I))
        if e_loc.count() == 0:
            e_loc = _control_by_attr(form, "eventUrl", "event_url")
        if e_loc.count() > 0:
            _set_control_value(page, e_loc, cfg.event_url)

    # Avançar
    next_btn = page.locator("button", has_text=re.compile(r"Pr[óo]ximo|Seguinte|Continuar", re.I))
    if next_btn.count() == 0:
        _debug_dump_html(page, uuid=uuid, motivo="botao_proximo_nao_encontrado")
        raise RuntimeError("PARTE 1: botão 'Próximo/Seguinte' não encontrado no /details.")

    delay_s = _before_next_delay_s()
    if delay_s > 0:
        time.sleep(delay_s)
    robust_click(next_btn.first)


# ─────────────────────────────────────────────────────────────────────────────
# Compatibilidade com runner antigo
# ─────────────────────────────────────────────────────────────────────────────

def run(page: Page, *args, **kwargs) -> None:
    """Alias ultra-compatível para o runner."""
    uuid = kwargs.get("uuid")
    cfg_obj = kwargs.get("cfg")

    if not uuid and cfg_obj is not None:
        uuid = getattr(cfg_obj, "uuid", None)

    if not uuid:
        for a in reversed(args):
            if isinstance(a, str) and len(a) >= 32 and "-" in a:
                uuid = a
                break

    if not uuid and args:
        maybe_cfg = args[0]
        uuid = getattr(maybe_cfg, "uuid", None)

    if not uuid:
        _debug_dump_html(page, uuid="sem_uuid", motivo="runner_sem_uuid")
        raise RuntimeError("PARTE 1: runner chamou run(...) sem uuid. Passa uuid explicitamente ou garante cfg.uuid.")

    return run_part1_details(page, uuid=str(uuid))