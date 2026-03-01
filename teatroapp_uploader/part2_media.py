# -*- coding: utf-8 -*-
"""Parte 2 — Cartaz e Fotos (/media).

Robustez adicional:
- Confirma que estamos em /media (âncoras do HTML).
- Selecciona de forma determinística o input do cartaz (file, name=poster, SEM multiple).
- Espera por sinais de que o upload foi reconhecido (preview / remover / botão Continuar activo).
- Se falhar: loga url_actual + estado do botão + dump de HTML em .cache/teatroapp_debug/*.html (sem screenshots).
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # type: ignore

from .env import Config
from .logging_ptpt import Logger
from .pw_helpers import dismiss_cookies, wait_dom
from .utils import ensure_parent_dir, sleep_jitter

logger = Logger()


def _slug(s: str, max_len: int = 60) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:max_len] if s else "debug"


def _dump_html(page, *, uuid: str, motivo: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(".cache") / "teatroapp_debug"
    ensure_parent_dir(out_dir / "_noop.txt")

    fname = f"{ts}_parte2_{uuid[:8]}_{_slug(motivo)}.html"
    path = out_dir / fname

    try:
        html = page.content()
    except Exception as e:
        html = f"<!-- falha a obter page.content(): {e} -->"

    path.write_text(html, encoding="utf-8")
    logger.error("PARTE 2: HTML de depuração gravado em: %s", str(path))
    return path


def _find_continue(page):
    """Obtém o CTA da direita no rodapé (link ou botão).

    Importante: durante o upload, o site mostra um botão disabled com texto
    "A guardar..." e só depois aparece/transforma para "Continuar".

    Estratégia:
    1) Procurar link "Continuar".
    2) Procurar botão "Continuar".
    3) Se não existir, devolver o botão da direita do rodapé (mesmo que diga "A guardar...").
    """
    # 1) Link Continuar
    try:
        el = page.get_by_role("link", name="Continuar").first
        if el.count() > 0:
            return el
    except Exception:
        pass

    # 2) Botão Continuar
    try:
        el = page.get_by_role("button", name="Continuar").first
        if el.count() > 0:
            return el
    except Exception:
        pass

    # 3) Botão da direita no rodapé (pode ser "A guardar...")
    footer = page.locator("div.flex.flex-row.justify-between.border-t.pt-4").first
    if footer.count() > 0:
        right_btn = footer.locator("button").last
        if right_btn.count() > 0:
            return right_btn

    # Fallback
    return page.locator("button").filter(has_text=re.compile("continuar|guardar", re.I)).first



def _pick_poster_input(page):
    """Escolhe o input do cartaz (SEM multiple)."""
    # Mais determinístico: file + name=poster + NOT multiple
    loc = page.locator('input[type="file"][name="poster"]:not([multiple])').first
    if loc.count() > 0:
        return loc

    # Fallback: todos os inputs file name=poster e filtrar via JS (multiple === false)
    all_inputs = page.locator('input[type="file"][name="poster"]')
    n = all_inputs.count()
    for i in range(n):
        cand = all_inputs.nth(i)
        try:
            is_multiple = bool(cand.evaluate("el => !!el.multiple"))
        except Exception:
            is_multiple = False
        if not is_multiple:
            return cand

    return page.locator('input[type="file"][name="poster"]').first


def _log_inputs_debug(page) -> None:
    """Loga rapidamente o inventário de inputs file relevantes."""
    inputs = page.locator('input[type="file"]')
    n = inputs.count()
    logger.info("PARTE 2: inputs[type=file] encontrados: %d", n)
    for i in range(min(n, 6)):
        it = inputs.nth(i)
        try:
            name = it.get_attribute("name")
            accept = it.get_attribute("accept")
            multiple = it.evaluate("el => !!el.multiple")
            disabled = it.evaluate("el => !!el.disabled")
        except Exception:
            name, accept, multiple, disabled = None, None, None, None
        logger.info(
            "PARTE 2: input[%d] name=%s accept=%s multiple=%s disabled=%s",
            i,
            str(name),
            str(accept),
            str(multiple),
            str(disabled),
        )


def _wait_upload_recognised(page, cont, timeout_s: float = 60.0) -> bool:
    """Espera por sinais de que o cartaz foi reconhecido.

    No HTML actual há um estado explícito de upload:
    - bloco do cartaz mostra 'A carregar…' com `svg.lucide-loader-circle` em rotação
    - footer mostra botão disabled com texto 'A guardar…'

    Critério de sucesso:
    - desaparece o estado 'A carregar…' E
    - aparece preview/remoção OU o 'Continuar' deixa de estar desactivado / deixa de dizer 'A guardar…'.
    """
    t0 = time.time()

    def _is_uploading() -> bool:
        try:
            if page.locator("svg.lucide-loader-circle.animate-spin").count() > 0:
                return True
            if page.locator("text=A carregar...").count() > 0:
                return True
        except Exception:
            pass
        return False

    def _continue_ready() -> bool:
        # Link "Continuar" (quando o site troca de button para <a>)
        try:
            link = page.get_by_role("link", name=re.compile(r"^\s*continuar\s*$", re.I)).first
            if link.count() > 0:
                return True
        except Exception:
            pass

        # Botão "Continuar" enabled
        try:
            tag = (cont.evaluate("el => el.tagName") or "").upper()
        except Exception:
            tag = ""
        if tag == "BUTTON":
            try:
                if cont.is_enabled():
                    # evitar falso-positivo quando ainda diz "A guardar…"
                    txt = (cont.inner_text() or "").strip().lower()
                    if "guardar" not in txt:
                        return True
            except Exception:
                pass
        return False

    while time.time() - t0 < timeout_s:
        try:
            # Sinais fortes no DOM (preview / icon remover)
            if page.locator("img[alt='Poster preview']").count() > 0:
                return True
            if page.locator("svg.lucide-circle-x").count() > 0:
                return True

            # Se já não estiver a fazer upload e o continuar estiver pronto, ok
            if not _is_uploading() and _continue_ready():
                return True
        except Exception:
            pass

        time.sleep(0.25)

    return False


def run(page, cfg: Config, uuid: str) -> None:
    url = f"{cfg.base_url}/adicionar/{uuid}/media"
    logger.info("PARTE 2: Cartaz e Fotos — a abrir: %s", url)

    page.goto(url, wait_until="domcontentloaded")
    wait_dom(page)
    dismiss_cookies(page)

    # Âncoras do ecrã
    if page.locator("text=Cartaz e Fotos").count() == 0 and page.locator('input[type="file"][name="poster"]').count() == 0:
        _dump_html(page, uuid=uuid, motivo="nao_detectei_media")
        raise RuntimeError("PARTE 2: não detectei o ecrã 'Cartaz e Fotos'.")

    if not cfg.poster_path.exists():
        raise RuntimeError(f"PARTE 2: cartaz não existe no disco: {str(cfg.poster_path)}")

    try:
        size = cfg.poster_path.stat().st_size
        logger.info("PARTE 2: cartaz (%s) — %d bytes.", str(cfg.poster_path), size)
    except Exception:
        pass

    _log_inputs_debug(page)

    poster_input = _pick_poster_input(page)
    if poster_input.count() == 0:
        _dump_html(page, uuid=uuid, motivo="nao_encontrei_input_poster")
        raise RuntimeError("PARTE 2: não encontrei o input do cartaz (name=poster, single).")

    # Garantir attached antes de set_input_files
    try:
        poster_input.wait_for(state="attached", timeout=10_000)
    except PlaywrightTimeoutError:
        _dump_html(page, uuid=uuid, motivo="input_poster_nao_attached")
        raise RuntimeError("PARTE 2: input do cartaz não está attached no DOM.")

    logger.info("PARTE 2: a fazer upload do cartaz: %s", str(cfg.poster_path))
    try:
        poster_input.set_input_files(str(cfg.poster_path))
    except Exception as e:
        logger.warning("PARTE 2: set_input_files no locator falhou (%s). vou tentar via page.set_input_files…", str(e))
        page.set_input_files('input[type="file"][name="poster"]:not([multiple])', str(cfg.poster_path))

    cont = _find_continue(page)
    if cont.count() == 0:
        _dump_html(page, uuid=uuid, motivo="nao_encontrei_continuar")
        raise RuntimeError("PARTE 2: não encontrei 'Continuar' (nem <a> nem <button>).")

    # Esperar reconhecimento do upload
    ok = _wait_upload_recognised(page, cont, timeout_s=30.0)
    if not ok:
        # Diagnóstico extra: se for botão, logar disabled/enabled
        try:
            tag = (cont.evaluate("el => el.tagName") or "").upper()
        except Exception:
            tag = ""
        if tag == "BUTTON":
            try:
                logger.error("PARTE 2: 'Continuar' enabled=%s", str(cont.is_enabled()))
            except Exception:
                pass

        _dump_html(page, uuid=uuid, motivo="upload_nao_reconhecido")
        raise RuntimeError(
            "PARTE 2: upload do cartaz não foi reconhecido no DOM (preview/remoção/continuar activo). "
            "Ver HTML em .cache/teatroapp_debug/."
        )

    sleep_jitter(cfg.delay_min, cfg.delay_max, "após upload cartaz")

    # Galeria opcional
    if cfg.gallery_paths:
        missing = [str(p) for p in cfg.gallery_paths if not p.exists()]
        if missing:
            raise RuntimeError(f"PARTE 2: ficheiros da galeria não existem: {', '.join(missing)}")

        gal_input = page.locator('input[type="file"][name="poster"][multiple]').first
        if gal_input.count() == 0:
            logger.warning("PARTE 2: input de galeria (multiple) não encontrado; a seguir sem galeria.")
        else:
            paths = [str(p) for p in cfg.gallery_paths]
            logger.info("PARTE 2: a fazer upload da galeria (%d ficheiros).", len(paths))
            gal_input.set_input_files(paths)
            sleep_jitter(cfg.delay_min, cfg.delay_max, "após upload galeria")

    # Continuar (button vs link)
    # O HTML de falha mostra que, durante o upload/guardar, o CTA é um botão disabled
    # com texto "A guardar..." — não existe "Continuar" ainda.
    # Portanto: esperar até aparecer "Continuar" (link ou botão) e só depois clicar.

    # 1) Esperar até o estado de upload/guardar terminar
    # (spinner "A carregar..." + botão "A guardar...")

    t0 = time.time()
    while time.time() - t0 < 90.0:
        try:
            uploading = page.locator("svg.lucide-loader-circle.animate-spin").count() > 0 or page.locator("text=A carregar...").count() > 0
        except Exception:
            uploading = False

        # procurar link/botão Continuar
        try:
            link_cont = page.get_by_role("link", name="Continuar").first
        except Exception:
            link_cont = page.locator("a").filter(has_text=re.compile("^Continuar$", re.I)).first

        try:
            btn_cont = page.get_by_role("button", name="Continuar").first
        except Exception:
            btn_cont = page.locator("button").filter(has_text=re.compile("^Continuar$", re.I)).first

        if link_cont.count() > 0:
            cont = link_cont
            break

        if btn_cont.count() > 0:
            cont = btn_cont
            try:
                if cont.is_enabled() and not uploading:
                    break
            except Exception:
                pass

        # se ainda estiver a guardar, continuar a esperar
        time.sleep(0.25)

    # 2) Se ainda não aparecer, dump + erro
    try:
        tag = (cont.evaluate("el => el.tagName") or "").upper()
    except Exception:
        tag = ""

    if cont.count() == 0:
        _dump_html(page, uuid=uuid, motivo="nao_apareceu_continuar")
        raise RuntimeError("PARTE 2: após esperar, o CTA 'Continuar' não apareceu (ainda a guardar ou houve erro).")

    # 3) Clicar
    if tag == "BUTTON":
        try:
            if not cont.is_enabled():
                _dump_html(page, uuid=uuid, motivo="continuar_desactivado")
                raise RuntimeError("PARTE 2: botão 'Continuar' continua desactivado.")
        except Exception:
            pass

    dismiss_cookies(page)
    logger.info("PARTE 2: a clicar 'Continuar'…")
    cont.click()
    wait_dom(page)
    sleep_jitter(cfg.delay_min, cfg.delay_max, "após Continuar (Parte 2)")

    has_sessions = (
        page.locator("text=Sessões").count() > 0
        or page.locator("input#ticketUrl").count() > 0
        or ("/sessions" in (page.url or "").lower())
    )
    if not has_sessions:
        _dump_html(page, uuid=uuid, motivo="nao_detectei_sessions")
        raise RuntimeError("PARTE 2: submeti, mas não detectei a Parte 3 (Sessões).")
