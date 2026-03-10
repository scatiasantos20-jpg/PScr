from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scrapers.common.logging_ptpt import configurar_logger, info, aviso
from scrapers.common.utils_scrapper import fetch_page, delay_between_requests, detectar_tipo_pagina

from scrapers.ticket_platforms.Ticketline.single_page import scrape_single_page
from scrapers.ticket_platforms.Ticketline.sessions_calendar import scrape_sessions_calendar

logger = configurar_logger("scrapers.ticketline.multi")


def _url_key(u: str) -> str:
    return (u or "").strip().lower().rstrip("/")


def _parse_int_env(key: str, default: int) -> int:
    raw = (os.getenv(key) or "").strip()
    try:
        v = int(raw)
        return v
    except Exception:
        return default


def _get_multi_limits() -> tuple[int, int]:
    """
    Controlos no .env para multi-pages:
      - TICKETLINE_MULTI_LIMIT: quantos sub-eventos processar por multi (default 5; 0 = todos)
      - TICKETLINE_MULTI_OFFSET: a partir de que índice começar (default 0)
    """
    limit = _parse_int_env("TICKETLINE_MULTI_LIMIT", 5)
    offset = _parse_int_env("TICKETLINE_MULTI_OFFSET", 0)
    if offset < 0:
        offset = 0
    if limit < 0:
        limit = 5
    return limit, offset




def parse_multi_event_urls_from_html(html: str) -> list[str]:
    """Parsing puro: extrai URLs de sub-eventos a partir do HTML de uma página multi."""
    soup = BeautifulSoup(html or "", "html.parser")
    container = (
        soup.select_one("ul.events_list.highlights_list.grid")
        or soup.select_one("ul.events_list")
    )
    if not container:
        return []

    out: list[str] = []
    items = container.select('li[itemtype="http://schema.org/Event"], li[itemtype="https://schema.org/Event"], li[itemtype*="schema.org/Event"]') or container.find_all("li")
    for li in items:
        a_tag = li.find("a", href=True)
        if not a_tag:
            continue
        href = (a_tag.get("href") or "").strip()
        if not href:
            continue
        out.append(urljoin("https://ticketline.sapo.pt", href))

    # dedupe preservando ordem
    seen: set[str] = set()
    unique: list[str] = []
    for u in out:
        k = _url_key(u)
        if not k or k in seen:
            continue
        seen.add(k)
        unique.append(u)
    return unique
def scrape_multi_page(
    url: str,
    known_titles: Optional[set[str]] = None,
    *,
    html: Optional[str] = None,
    session: Optional[requests.Session] = None,
    parent_multi_url: Optional[str] = None,  # para tracking quando há recursão
):
    # Normalizar known_titles (defensivo)
    known_norm: set[str] = set()
    if known_titles:
        try:
            known_norm = {_url_key(x) for x in known_titles if isinstance(x, str) and x.strip()}
        except Exception:
            known_norm = set()

    if html is None:
        html = fetch_page(url)
    if not html:
        aviso(logger, "ticketline.warn.sem_html", url=url)
        return []

    parsed_urls = parse_multi_event_urls_from_html(html)
    if not parsed_urls:
        aviso(logger, "ticketline.warn.sem_lista_eventos", url=url)
        return []

    total_sub_eventos = len(parsed_urls)

    limit, offset = _get_multi_limits()

    if limit == 0:
        items_to_process = parsed_urls[offset:]
    else:
        items_to_process = parsed_urls[offset: offset + limit]

    info(
        logger,
        "ticketline.info.multi_resumo",
        url=url,
        total=total_sub_eventos,
        processar=len(items_to_process),
        offset=offset,
        limit=limit,
    )

    eventos_extraidos = []
    s = session or requests.Session()
    multi_root = parent_multi_url or url

    for idx, event_url in enumerate(items_to_process, start=1):
        event_key = _url_key(event_url)

        if known_norm and event_key in known_norm:
            continue

        info(logger, "ticketline.info.sub_evento", idx=idx, total=len(items_to_process), url=event_url)

        event_html = fetch_page(event_url)
        if not event_html:
            aviso(logger, "ticketline.warn.sem_html", url=event_url)
            continue

        tipo = detectar_tipo_pagina(event_html)
        info(logger, "ticketline.info.tipo_pagina", tipo=tipo)

        dados = None

        if tipo == "single":
            dados = scrape_single_page(event_url, known_titles=known_norm, html=event_html, session=s)
        elif tipo == "calendar":
            dados = scrape_sessions_calendar(event_url, known_titles=known_norm, html=event_html)
        elif tipo == "multi":
            dados = scrape_multi_page(
                event_url,
                known_titles=known_norm,
                html=event_html,
                session=s,
                parent_multi_url=multi_root,
            )
        else:
            aviso(logger, "ticketline.warn.tipo_desconhecido", url=event_url)
            continue

        def _inject_multi_meta(d: dict) -> dict:
            d = dict(d)
            d["Multi Total"] = total_sub_eventos
            d["Multi Processados"] = len(items_to_process)
            d["Multi Fonte"] = multi_root
            return d

        if isinstance(dados, dict):
            eventos_extraidos.append(_inject_multi_meta(dados))
        elif isinstance(dados, list):
            eventos_extraidos.extend([_inject_multi_meta(d) for d in dados if isinstance(d, dict)])

        delay_between_requests(logger_obj=logger, message_key="ticketline.delay.proximo_evento")

    return eventos_extraidos