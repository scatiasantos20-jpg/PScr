# -*- coding: utf-8 -*-
"""Parte 3 — Sessões (/sessions) — v5.

Correções chave (baseadas nos dumps HTML + logs):
- A falha "sala não colou" acontecia quando o combobox encontrado não era o correcto
  (selector via `following::` podia apanhar um combobox fora do bloco do label) OU
  quando fechávamos o dropdown com ESC (Radix pode reverter/limpar a selecção).

Solução v5:
- Encontrar o combobox da sala dentro do mesmo “bloco” do label (subindo 1–3 níveis e procurando o button).
- Restringir opções ao dialog controlado por `aria-controls` do combobox.
- Após clicar opção, fechar o dropdown clicando no `ticketUrl` (em vez de ESC).
- Validar que o texto do combobox mudou; repetir 1 vez se necessário.
- Se a sala não existir, seleccionar "Não está na lista" (preferindo Lisboa).

Mantém:
- Selecção do dia por td[data-day="YYYY-MM-DD"] button.rdp-day_button.
- Dump HTML em falhas para .cache/teatroapp_debug/*.html.
- Logs PT-PT pré-Acordo.

Playwright: sync.
"""

from __future__ import annotations

import re
import time
import uuid as uuidlib
import unicodedata
from datetime import datetime
from pathlib import Path

from .env import Config, Session
from .logging_ptpt import Logger
from .pw_helpers import wait_dom, dismiss_cookies, robust_fill, robust_select_value
from .utils import sleep_jitter

logger = Logger()

_DEBUG_DIR = Path(".cache") / "teatroapp_debug"


def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "debug"


def _debug_dump_html(page, *, uuid: str, sessao_idx: int | None, motivo: str) -> Path:
    """Guarda o HTML actual em .cache/teatroapp_debug (sem screenshots)."""
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short = (uuid or "")[:8] or uuidlib.uuid4().hex[:8]
    rid = uuidlib.uuid4().hex[:8]
    sidx = f"sessao_{sessao_idx}" if sessao_idx is not None else "sessao"

    fname = f"{ts}_parte3_{short}_{sidx}_{_slug(motivo)}_{rid}.html"
    path = _DEBUG_DIR / fname

    try:
        html = page.content()
        path.write_text(html, encoding="utf-8")
        logger.info("PARTE 3: debug HTML gravado em: %s", str(path))
    except Exception as e:
        logger.error("PARTE 3: falha ao gravar debug HTML (%s): %s", str(path), str(e))

    return path


def _ensure_not_login(page, *, uuid: str, sessao_idx: int | None, contexto: str) -> None:
    url = (page.url or "").lower()
    if "/login" in url or "signin" in url or "auth" in url:
        _debug_dump_html(page, uuid=uuid, sessao_idx=sessao_idx, motivo=f"{contexto}_redirect_login")
        raise RuntimeError(f"PARTE 3: fui parar ao login ({page.url}).")


def _find_add_form(page, uuid: str):
    """Encontra o form correcto de 'Adicionar Sessão' (o que tem input#ticketUrl)."""
    form = page.locator("form").filter(has=page.locator("input#ticketUrl")).first
    if form.count() == 0:
        # fallback defensivo: pelo heading "Adicionar Sessão"
        form = page.locator("form").filter(
            has=page.get_by_role("heading", name=re.compile(r"adicionar\s+sess", re.I))
        ).first
    return form


def _dialog_by_aria_controls(page, btn):
    """Dado um botão (combobox/calendar), tenta devolver o dialog correcto via aria-controls."""
    try:
        cid = (btn.get_attribute("aria-controls") or "").strip()
    except Exception:
        cid = ""

    if cid:
        dlg = page.locator(f"#{cid}")
        try:
            dlg.wait_for(state="visible", timeout=10_000)
        except Exception:
            pass
        return dlg

    dlg = page.locator("[role='dialog']").last
    try:
        dlg.wait_for(state="visible", timeout=10_000)
    except Exception:
        pass
    return dlg


def _pick_venue(form, cfg: Config, venue: str, *, uuid: str, sessao_idx: int) -> None:
    """Selecciona a sala (combobox Radix/shadcn) com validação."""

    target_raw = (venue or "").strip()
    if not target_raw:
        raise RuntimeError("PARTE 3: venue vazio.")

    page = form.page

    # === Encontrar combobox correcto (v5: sem following:: global) ===
    lbl = form.locator("label").filter(has_text=re.compile(r"Sala\s+de\s+Esp", re.I)).first
    cb = form.locator("__never__")

    if lbl.count() > 0:
        # Procurar o combobox no mesmo bloco do label (subindo 1-3 níveis)
        for xp in ("xpath=..", "xpath=../..", "xpath=../../.."):
            cand = lbl.locator(xp).locator("button[role='combobox']").first
            if cand.count() > 0:
                cb = cand
                break

    # Fallback: primeiro combobox dentro do form
    if cb.count() == 0:
        cb = form.locator("button[role='combobox']").first

    if cb.count() == 0:
        _debug_dump_html(page, uuid=uuid, sessao_idx=sessao_idx, motivo="nao_encontrei_combobox_sala")
        raise RuntimeError("PARTE 3: não encontrei o combobox da sala (button[role=combobox]).")

    # Token permissivo (por causa de sufixos/cidade)
    token = re.split(r"\s*\(|\s*-\s*", target_raw, maxsplit=1)[0].strip() or target_raw

    def _strip_accents(s: str) -> str:
        s = s or ""
        return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

    def _norm(s: str) -> str:
        s = _strip_accents(s or "").lower().strip()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[^a-z0-9 ]+", "", s)
        return s.strip()

    target_norm = _norm(target_raw)
    token_norm = _norm(token)

    def _cb_text() -> str:
        try:
            return (cb.inner_text() or "").strip()
        except Exception:
            return ""

    def _selected_ok(strict: bool = True) -> bool:
        txt = _cb_text()
        if not txt:
            return False
        if "escolher a sala" in txt.lower():
            return False
        if not strict:
            return True
        return token_norm in _norm(txt) or target_norm in _norm(txt)

    def _selected_is_nao_lista() -> bool:
        return "nao esta na lista" in _norm(_cb_text())

    def _unique_queries(items: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for it in items:
            it = (it or "").strip()
            if not it:
                continue
            key = _norm(it)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    queries = _unique_queries([target_raw, token, _strip_accents(target_raw), _strip_accents(token)])

    def _find_search_input(dlg):
        # shadcn/Radix "Command" costuma ter input dentro do dialog
        cand = dlg.locator("input[type='text'], input[type='search']").first
        if cand.count() > 0:
            try:
                cand.wait_for(state="visible", timeout=1_500)
                return cand
            except Exception:
                pass

        cand = dlg.locator("input").first
        if cand.count() > 0:
            try:
                cand.wait_for(state="visible", timeout=1_500)
                return cand
            except Exception:
                pass

        return dlg.locator("__never__")

    def _clear_and_type_into_search(search, text: str) -> None:
        try:
            search.click()
        except Exception:
            pass
        try:
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
        except Exception:
            pass

        try:
            search.fill(text)
            return
        except Exception:
            pass

        try:
            page.keyboard.type(text, delay=25)
        except Exception:
            return

    def _options_locator(dlg):
        return dlg.locator("[role='option'], [data-radix-collection-item], [cmdk-item]")

    def _score_option(label: str) -> int:
        ln = _norm(label)
        if not ln:
            return 0
        if ln == target_norm:
            return 100
        if ln == token_norm:
            return 95
        if target_norm and target_norm in ln:
            return 90
        if token_norm and token_norm in ln:
            return 85

        t_words = set(token_norm.split())
        l_words = set(ln.split())
        if not t_words or not l_words:
            return 0
        common = len(t_words & l_words)
        if common == 0:
            return 0
        return min(84, 50 + common * 10)

    def _close_dropdown_safely() -> None:
        # NÃO usar ESC (pode reverter). Preferir clicar num input “neutro”.
        try:
            form.locator("input#ticketUrl").first.click(timeout=500)
            return
        except Exception:
            pass
        try:
            page.mouse.click(5, 5)
        except Exception:
            pass

    def _wait_cb_settled(timeout_s: float = 1.5) -> None:
        # dar tempo ao Radix para aplicar estado/valor
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            try:
                # se o dropdown fechou, melhor (aria-expanded false)
                exp = (cb.get_attribute("aria-expanded") or "").lower()
                if exp == "false":
                    break
            except Exception:
                break
            time.sleep(0.08)

    def _click_best_visible_option(dlg) -> bool:
        opts = _options_locator(dlg)
        try:
            opts.first.wait_for(state="visible", timeout=4_000)
        except Exception:
            return False

        best_i = -1
        best_s = 0

        try:
            n = opts.count()
        except Exception:
            n = 0

        for i in range(min(n, 250)):  # defensivo
            it = opts.nth(i)
            try:
                txt = (it.inner_text() or "").strip()
            except Exception:
                txt = ""
            s = _score_option(txt)
            if s > best_s:
                best_s = s
                best_i = i

        if best_i < 0 or best_s < 50:
            return False

        chosen = opts.nth(best_i)
        try:
            chosen.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            chosen.click()
        except Exception:
            try:
                chosen.click(force=True)
            except Exception:
                return False

        sleep_jitter(cfg.delay_min, cfg.delay_max, "após seleccionar sala (click opção)")
        _close_dropdown_safely()
        _wait_cb_settled()
        return True

    def _scroll_until_match(dlg, max_scrolls: int = 40) -> bool:
        viewport = dlg.locator("[data-radix-scroll-area-viewport], [cmdk-list], [role='listbox']").first
        if viewport.count() == 0:
            return False

        for _ in range(max_scrolls):
            if _click_best_visible_option(dlg):
                return True
            try:
                viewport.evaluate("el => el.scrollBy(0, Math.max(140, el.clientHeight * 0.85))")
            except Exception:
                return False
            sleep_jitter(cfg.delay_min, cfg.delay_max, "a fazer scroll na lista de salas")
        return False

    def _click_nao_esta_na_lista(dlg) -> bool:
        opts = _options_locator(dlg).filter(has_text=re.compile(r"Não\s+está\s+na\s+lista", re.I))

        # fallback por data-value (observado)
        if opts.count() == 0:
            opts = dlg.locator('[data-value="164bbae8-a365-4770-959d-12d38bbe89d8"]')

        if opts.count() == 0:
            return False

        # Preferir Lisboa
        cand = opts.filter(has_text=re.compile(r"\bLisboa\b", re.I)).first
        if cand.count() == 0:
            cand = opts.first

        try:
            cand.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            cand.click()
        except Exception:
            try:
                cand.click(force=True)
            except Exception:
                return False

        sleep_jitter(cfg.delay_min, cfg.delay_max, "após seleccionar 'Não está na lista'")
        _close_dropdown_safely()
        _wait_cb_settled()
        return True

    used_fallback = False

    def _pick_once() -> bool:
        nonlocal used_fallback

        try:
            cb.scroll_into_view_if_needed()
        except Exception:
            pass

        cb.click()
        sleep_jitter(cfg.delay_min, cfg.delay_max, "após abrir dropdown sala")

        dlg = _dialog_by_aria_controls(page, cb)
        search = _find_search_input(dlg)

        if search.count() > 0:
            found = False
            for q in queries:
                _clear_and_type_into_search(search, q)
                sleep_jitter(cfg.delay_min, cfg.delay_max, "após pesquisar sala")
                if _click_best_visible_option(dlg):
                    found = True
                    break

            if not found:
                if _click_nao_esta_na_lista(dlg):
                    logger.warning("PARTE 3: sala %r não encontrada; a usar 'Não está na lista'.", target_raw)
                    used_fallback = True
                    found = True
                else:
                    found = _scroll_until_match(dlg)

            if not found:
                return False

        else:
            if not _scroll_until_match(dlg):
                if _click_nao_esta_na_lista(dlg):
                    logger.warning("PARTE 3: sala %r não encontrada; a usar 'Não está na lista'.", target_raw)
                    used_fallback = True
                else:
                    return False

        # Confirmar que colou
        t0 = time.time()
        while time.time() - t0 < 5.0:
            if _selected_ok(strict=not used_fallback):
                return True
            time.sleep(0.2)

        return _selected_ok(strict=not used_fallback)

    # Se já estiver correcto (por ex. mesma sala repetida), não mexer
    if _selected_ok() or _selected_is_nao_lista():
        return

    if _pick_once():
        return

    # 2.ª tentativa (reabrir + repetir)
    if _pick_once():
        return

    _debug_dump_html(page, uuid=uuid, sessao_idx=sessao_idx, motivo=f"sala_nao_colou_{token}")
    raise RuntimeError(f"PARTE 3: não consegui seleccionar a sala (não colou): {target_raw!r}")


def _find_calendar_button(form):
    """Encontrar o botão que abre o DayPicker (ícone Lucide calendar)."""

    svg = form.locator("svg[class*='lucide-calendar']").first
    if svg.count() > 0:
        btn = svg.locator("xpath=ancestor::button[1]").first
        if btn.count() > 0:
            return btn

    svg = form.locator("svg[class*='calendar']").first
    if svg.count() > 0:
        btn = svg.locator("xpath=ancestor::button[1]").first
        if btn.count() > 0:
            return btn

    btn = form.locator("button[type='button']").filter(has=form.locator("svg[class*='calendar']")).first
    if btn.count() > 0:
        return btn

    return form.locator("__never__")


def _open_calendar(form, cfg: Config):
    btn = _find_calendar_button(form)
    if btn.count() == 0:
        raise RuntimeError(
            "PARTE 3: não encontrei o botão do calendário (procurei svg[class*=lucide-calendar] e svg[class*=calendar])."
        )

    btn.click()
    sleep_jitter(cfg.delay_min, cfg.delay_max, "após abrir calendário")

    return _dialog_by_aria_controls(form.page, btn)


def _goto_month_if_needed(dlg, target_date: str, cfg: Config) -> None:
    """Se o dia ainda não existe no DOM, tenta navegar meses no DayPicker."""

    next_btn = dlg.locator("button[aria-label='Go to the Next Month']").first
    prev_btn = dlg.locator("button[aria-label='Go to the Previous Month']").first

    if next_btn.count() == 0 and prev_btn.count() == 0:
        return

    def _has_day() -> bool:
        return dlg.locator(f"td[data-day='{target_date}'] button.rdp-day_button").count() > 0

    if _has_day():
        return

    for _ in range(24):
        if next_btn.count() == 0:
            break
        try:
            next_btn.click()
        except Exception:
            break
        sleep_jitter(cfg.delay_min, cfg.delay_max, "após avançar mês")
        if _has_day():
            return

    for _ in range(24):
        if prev_btn.count() == 0:
            break
        try:
            prev_btn.click()
        except Exception:
            break
        sleep_jitter(cfg.delay_min, cfg.delay_max, "após recuar mês")
        if _has_day():
            return


def _pick_date(form, cfg: Config, date_yyyy_mm_dd: str, *, uuid: str, sessao_idx: int) -> None:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_yyyy_mm_dd)
    if not m:
        raise RuntimeError(f"PARTE 3: data inválida (esperado YYYY-MM-DD): {date_yyyy_mm_dd!r}")

    dlg = _open_calendar(form, cfg)

    _goto_month_if_needed(dlg, date_yyyy_mm_dd, cfg)

    day_btn = dlg.locator(f"td[data-day='{date_yyyy_mm_dd}'] button.rdp-day_button").first
    if day_btn.count() > 0:
        try:
            day_btn.wait_for(state="visible", timeout=10_000)
        except Exception:
            pass
        day_btn.click()
        sleep_jitter(cfg.delay_min, cfg.delay_max, "após seleccionar dia (data-day)")
        return

    year = int(m.group(1))
    day = int(m.group(3))

    day_btn = dlg.get_by_role(
        "button",
        name=re.compile(rf"\b{day}\w*\b.*\b{year}\b", re.I),
    ).first

    if day_btn.count() > 0:
        day_btn.click()
        sleep_jitter(cfg.delay_min, cfg.delay_max, "após seleccionar dia (aria-label)")
        return

    _debug_dump_html(form.page, uuid=uuid, sessao_idx=sessao_idx, motivo=f"nao_consegui_seleccionar_dia_{date_yyyy_mm_dd}")
    raise RuntimeError(f"PARTE 3: não consegui seleccionar o dia no calendário: {date_yyyy_mm_dd}")


def _set_time(form, cfg: Config, hour: int, minute: int) -> None:
    sels = form.locator("select[aria-hidden='true']").all()
    if len(sels) < 2:
        raise RuntimeError("PARTE 3: não encontrei os <select> escondidos para hora/minuto (select[aria-hidden=true]).")

    h = f"{hour:02d}"
    m = f"{minute:02d}"

    robust_select_value(sels[0], h)
    sleep_jitter(cfg.delay_min, cfg.delay_max, "após seleccionar hora")

    robust_select_value(sels[1], m)
    sleep_jitter(cfg.delay_min, cfg.delay_max, "após seleccionar minuto")


def _click_add(form, cfg: Config, *, uuid: str, sessao_idx: int) -> None:
    add = form.locator("button[type='submit']").filter(has_text=re.compile(r"^\s*adicionar\s*$", re.I)).first
    if add.count() == 0:
        add = form.get_by_role("button", name=re.compile(r"^\s*adicionar\s*$", re.I)).first
    if add.count() == 0:
        _debug_dump_html(form.page, uuid=uuid, sessao_idx=sessao_idx, motivo="nao_encontrei_botao_adicionar")
        raise RuntimeError("PARTE 3: não encontrei o botão 'Adicionar'.")

    t0 = time.time()
    while time.time() - t0 < 20.0:
        try:
            if add.is_enabled():
                break
        except Exception:
            pass
        time.sleep(0.25)

    if not add.is_enabled():
        _debug_dump_html(form.page, uuid=uuid, sessao_idx=sessao_idx, motivo="adicionar_desactivado")
        raise RuntimeError(
            "PARTE 3: botão 'Adicionar' continua desactivado (verifica sala seleccionada, data e URL de bilhetes)."
        )

    add.click()
    sleep_jitter(cfg.delay_min, cfg.delay_max, "após Adicionar sessão")


def _submit(page, cfg: Config, uuid: str) -> None:
    footer_form = page.locator(f'form[action="/adicionar/{uuid}/sessions"][method="post"]').filter(
        has=page.locator('input[name="intent"][value="submitPlay"]')
    ).first
    if footer_form.count() == 0:
        footer_form = page.locator("form").filter(has=page.get_by_text("Submeter peça")).first

    btn = footer_form.locator("button[type='submit']").filter(has_text=re.compile(r"submeter\s+peça", re.I)).first
    if btn.count() == 0:
        btn = page.get_by_role("button", name=re.compile(r"submeter\s+peça", re.I)).first
    if btn.count() == 0:
        _debug_dump_html(page, uuid=uuid, sessao_idx=None, motivo="nao_encontrei_submeter_peca")
        raise RuntimeError("PARTE 3: não encontrei o botão final 'Submeter peça'.")

    if cfg.dryrun:
        logger.info("PARTE 3: DRY-RUN activo — a NÃO submeter a peça.")
        return

    logger.info("PARTE 3: a clicar 'Submeter peça'…")
    btn.click()
    sleep_jitter(cfg.delay_min, cfg.delay_max, "após Submeter peça")


def run(page, cfg: Config, uuid: str, sessions: list[Session]) -> None:
    url = f"{cfg.base_url}/adicionar/{uuid}/sessions"
    logger.info("PARTE 3: Sessões — a abrir: %s", url)

    page.goto(url, wait_until="domcontentloaded")
    wait_dom(page)
    dismiss_cookies(page)

    _ensure_not_login(page, uuid=uuid, sessao_idx=None, contexto="abrir_sessions")

    form = _find_add_form(page, uuid)
    if form.count() == 0:
        _debug_dump_html(page, uuid=uuid, sessao_idx=None, motivo="form_adicionar_inexistente")
        raise RuntimeError("PARTE 3: não encontrei o formulário 'Adicionar Sessão' (input#ticketUrl em falta).")

    for idx, s in enumerate(sessions, start=1):
        logger.info(
            "PARTE 3: sessão #%d/%d — %s | %s %02d:%02d",
            idx,
            len(sessions),
            s.venue,
            s.date,
            s.hour,
            s.minute,
        )

        _ensure_not_login(page, uuid=uuid, sessao_idx=idx, contexto="antes_preencher")

        # 1) Sala (com validação robusta)
        _pick_venue(form, cfg, s.venue, uuid=uuid, sessao_idx=idx)

        # 2) Ticket URL
        ticket = (s.ticket_url or "").strip()
        if not ticket:
            _debug_dump_html(page, uuid=uuid, sessao_idx=idx, motivo="ticket_url_em_falta")
            raise RuntimeError("PARTE 3: Ticket URL é obrigatório (ticket_url vazio na sessão).")

        robust_fill(form.locator("input#ticketUrl").first, ticket)
        sleep_jitter(cfg.delay_min, cfg.delay_max, "após ticket_url")

        # 3) Data
        _pick_date(form, cfg, s.date, uuid=uuid, sessao_idx=idx)

        # 4) Hora/minuto
        _set_time(form, cfg, s.hour, s.minute)

        # 5) Adicionar
        _click_add(form, cfg, uuid=uuid, sessao_idx=idx)

        wait_dom(page)
        dismiss_cookies(page)
        _ensure_not_login(page, uuid=uuid, sessao_idx=idx, contexto="apos_adicionar")

        # re-localizar o form após re-render
        form = _find_add_form(page, uuid)
        if form.count() == 0:
            _debug_dump_html(page, uuid=uuid, sessao_idx=idx, motivo="form_perdido_apos_adicionar")
            raise RuntimeError("PARTE 3: após 'Adicionar', perdi o formulário (input#ticketUrl não encontrado).")

        sleep_jitter(cfg.delay_min, cfg.delay_max, "entre sessões")

    _submit(page, cfg, uuid)