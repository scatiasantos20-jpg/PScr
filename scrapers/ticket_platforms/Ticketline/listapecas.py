from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional, Iterable, Any

from bs4 import BeautifulSoup
from dotenv import load_dotenv

from scrapers.common.logging_ptpt import configurar_logger, info, aviso, erro, flush_erros, t
from scrapers.common.utils_scrapper import fetch_page, detectar_tipo_pagina, delay_between_requests

from scrapers.ticket_platforms.Ticketline.single_page import scrape_single_page
from scrapers.ticket_platforms.Ticketline.sessions_calendar import scrape_sessions_calendar
from scrapers.ticket_platforms.Ticketline.multi_page import scrape_multi_page

load_dotenv()
logger = configurar_logger("scrapers.ticketline.listapecas")
LABEL = t("tickets.job.ticketline")

_SKIP = object()


def _url_key(u: str) -> str:
    return (u or "").strip().lower().rstrip("/")


def _parse_global_event_range() -> Optional[range]:
    """
    GLOBAL_EVENT_RANGE do .env no formato '10-20' (posições na listagem acumulada).
    Se não existir/ inválido -> None.

    Nota: o intervalo é inclusivo.
    """
    raw = (os.getenv("GLOBAL_EVENT_RANGE") or "").strip()
    if not raw:
        return None

    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", raw)
    if not m:
        return None

    start = int(m.group(1))
    end = int(m.group(2))
    if end < start or start < 1:
        return None

    return range(start, end + 1)


def _parse_int(s: str) -> Optional[int]:
    try:
        return int(str(s).strip())
    except Exception:
        return None


def _parse_csv_ints(raw: str) -> list[int]:
    vals: list[int] = []
    for part in (raw or "").split(","):
        p = _parse_int(part)
        if p is not None:
            vals.append(p)
    # unique + ordenado
    return sorted(set(vals))


def _parse_months_env() -> Optional[list[int]]:
    """
    TICKETLINE_MONTH=1
    ou
    TICKETLINE_MONTHS=1,2,3
    """
    raw_one = (os.getenv("TICKETLINE_MONTH") or "").strip()
    raw_many = (os.getenv("TICKETLINE_MONTHS") or "").strip()

    if raw_one:
        m = _parse_int(raw_one)
        if m and 1 <= m <= 12:
            return [m]
        return None

    if raw_many:
        months = [m for m in _parse_csv_ints(raw_many) if 1 <= m <= 12]
        return months or None

    return None


def _parse_pages_env() -> Optional[list[int]]:
    """
    TICKETLINE_PAGES=1-2  (intervalo inclusivo)
    ou
    TICKETLINE_PAGE=1
    """
    raw_range = (os.getenv("TICKETLINE_PAGES") or "").strip()
    if raw_range:
        m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", raw_range)
        if m:
            a = int(m.group(1))
            b = int(m.group(2))
            if a >= 1 and b >= a:
                return list(range(a, b + 1))
        # se não for intervalo, tenta CSV
        pages = [p for p in _parse_csv_ints(raw_range) if p >= 1]
        return pages or None

    raw_one = (os.getenv("TICKETLINE_PAGE") or "").strip()
    if raw_one:
        p = _parse_int(raw_one)
        if p and p >= 1:
            return [p]

    return None


def _parse_year_env() -> int:
    y = _parse_int(os.getenv("TICKETLINE_YEAR", ""))
    return y if y and y >= 2000 else datetime.now().year


def _parse_categories_env(default: dict[str, str]) -> dict[str, str]:
    raw = (os.getenv("TICKETLINE_CATEGORY_IDS") or "").strip()
    info(logger, "ticketline.info.env_debug", TICKETLINE_CATEGORY_IDS=str(raw))
    if not raw:
        # modo seguro: sem categorias no .env -> não correr
        return {}
    ids = set(_parse_csv_ints(raw))
    filtered = {k: v for k, v in default.items() if _parse_int(k) in ids}
    return filtered


def processar_pagina(url: str, known_titles: Optional[set[str]] = None, *, html: Optional[str] = None):
    # dedupe cedo (sem request)
    if known_titles and _url_key(url) in known_titles:
        info(logger, "ticketline.info.ignorado_existente", url=url)
        return _SKIP

    if html is None:
        html = fetch_page(url)
    if not html:
        aviso(logger, "ticketline.warn.sem_html", url=url)
        return None

    tipo = detectar_tipo_pagina(html)
    info(logger, "ticketline.info.tipo_pagina", tipo=tipo)

    try:
        if tipo == "single":
            return scrape_single_page(url, known_titles=known_titles, html=html)
        if tipo == "calendar":
            return scrape_sessions_calendar(url, known_titles=known_titles, html=html)
        if tipo == "multi":
            return scrape_multi_page(url, known_titles=known_titles, html=html)

        aviso(logger, "ticketline.warn.tipo_desconhecido", url=url)
        return None

    except Exception as e:
        erro(logger, "ticketline.err.processar_pagina", e, cache_key=f"ticketline:processar:{url}", url=url)
        return None


def extrair_parametros_dinamicos(category_id: str, year: int):
    """
    (Opcional) Descobre:
      - meses activos (com <a>)
      - total de páginas (botão 'Último')
    Faz apenas 1 pedido (page=1) por categoria.
    """
    url = f"https://ticketline.sapo.pt/pesquisa/?category={category_id}&year={year}&page=1"

    html = fetch_page(url)
    active_months: list[int] = []
    max_page = 1  # fallback

    if html:
        soup = BeautifulSoup(html, "html.parser")

        meses_ul = soup.find("ul", class_="months")
        if meses_ul:
            for li in meses_ul.find_all("li"):
                a = li.find("a")
                if a and a.get("href") and "month=" in a["href"]:
                    match = re.search(r"month=(\d+)", a["href"])
                    if match:
                        m = int(match.group(1))
                        if 1 <= m <= 12:
                            active_months.append(m)

        active_months = sorted(set(active_months))

        last_page_link = soup.select_one("ul.pager li.last a[href]")
        if last_page_link:
            match = re.search(r"page=(\d+)", last_page_link["href"])
            if match:
                max_page = max(1, int(match.group(1)))
        else:
            pager_pages: list[int] = []
            for a in soup.select("ul.pager a[href]"):
                href = a.get("href") or ""
                m = re.search(r"page=(\d+)", href)
                if m:
                    pager_pages.append(int(m.group(1)))
            if pager_pages:
                max_page = max(1, max(pager_pages))

    return active_months, max_page


def _parse_int_env(key: str, default: int) -> int:
    raw = (os.getenv(key) or "").strip()
    try:
        return int(raw)
    except Exception:
        return default


def extract_events_all_pages(base_url: str, pages: Iterable[int]):
    pages_norm = sorted({int(p) for p in pages if int(p) >= 1})
    cumulative_events = []

    per_page_limit = _parse_int_env("TICKETLINE_EVENTS_PER_PAGE", 0)  # 0 = todos
    per_page_offset = _parse_int_env("TICKETLINE_EVENTS_OFFSET_PER_PAGE", 0)  # 0 = do início
    if per_page_offset < 0:
        per_page_offset = 0
    if per_page_limit < 0:
        per_page_limit = 0

    for page in pages_norm:
        url = f"{base_url}{page}"
        html = fetch_page(url)
        if not html:
            aviso(logger, "ticketline.warn.sem_html", url=url)
            break

        soup = BeautifulSoup(html, "html.parser")
        event_list_container = soup.select_one("ul.events_list")
        if not event_list_container:
            aviso(logger, "ticketline.warn.sem_lista_eventos", url=url)
            break

        page_events = event_list_container.find_all("li", itemtype="http://schema.org/Event")
        if not page_events:
            aviso(logger, "ticketline.warn.sem_eventos", url=url)
            break

        total_na_pagina = len(page_events)

        # aplica limite por página (seguro)
        if per_page_limit == 0:
            selected = page_events[per_page_offset:]
        else:
            selected = page_events[per_page_offset : per_page_offset + per_page_limit]

        info(
            logger,
            "ticketline.info.eventos.pagina_resumo",
            pagina=page,
            total=total_na_pagina,
            seleccionados=len(selected),
            offset=per_page_offset,
            limite=per_page_limit,
        )

        cumulative_events.extend(selected)
        delay_between_requests(logger_obj=logger, message_key="ticketline.delay.proxima_pagina")

    return cumulative_events


def main(known_titles=None):
    eventos_extraidos: list[dict[str, Any]] = []

    # Normalizar known_titles para URL keys (evita mismatch por / final e case)
    known_norm: set[str] = set()
    if known_titles:
        try:
            known_norm = {_url_key(x) for x in known_titles if isinstance(x, str) and x.strip()}
        except Exception:
            known_norm = set()

    desired_range = _parse_global_event_range()

    # Defaults
    categories_default = {
        "102": "Teatro",
        "143": "Musicais",
        "305": "ParaTodos",
    }
    categories = _parse_categories_env(categories_default)

    if not categories:
        aviso(logger, "ticketline.warn.sem_categorias_env")
        return []

    info(logger, "ticketline.info.categorias", categorias=", ".join([f"{k}:{v}" for k, v in categories.items()]))

    year = _parse_year_env()
    months_env = _parse_months_env()
    pages_env = _parse_pages_env()

    # Se não definires no .env, aplicamos fallback seguro (para não varrer o site todo)
    if months_env is None:
        months_env = [datetime.now().month]

    # Sem páginas -> modo seguro (mantém comportamento antigo)
    if pages_env is None:
        aviso(logger, "ticketline.warn.sem_paginas_env")
        return []

    info(logger, "ticketline.info.meses.ativos", meses=months_env)
    info(logger, "ticketline.info.paginas.total", max_page=max(pages_env) if pages_env else 1)

    discover = os.getenv("TICKETLINE_DISCOVER", "0") == "1"

    for cat_id, _cat_nome in categories.items():
        # Descoberta opcional por categoria (apenas informativa; não altera os limites do .env)
        if discover:
            try:
                active_months, max_page_real = extrair_parametros_dinamicos(cat_id, year)
                _ = active_months
                _ = max_page_real
            except Exception:
                pass

        for month in months_env:
            base_url = f"https://ticketline.sapo.pt/pesquisa/?category={cat_id}&month={month}&year={year}&page="

            cumulative = extract_events_all_pages(base_url, pages_env)

            if desired_range:
                selected_events = [ev for idx, ev in enumerate(cumulative, start=1) if idx in desired_range]
                end_inclusive = desired_range.stop - 1
                info(
                    logger,
                    "ticketline.info.eventos.seleccionados",
                    intervalo=f"{desired_range.start}-{end_inclusive}",
                    n=len(selected_events),
                )
            else:
                selected_events = cumulative

            if not selected_events:
                continue

            for idx, event_element in enumerate(selected_events, start=1):
                a_tag = event_element.find("a", href=True)
                if not a_tag:
                    aviso(logger, "ticketline.warn.evento_sem_link")
                    continue

                event_url = f"https://ticketline.sapo.pt{a_tag['href']}"
                event_key = _url_key(event_url)

                # SKIP absoluto: já está na cache/known
                if known_norm and event_key in known_norm:
                    info(logger, "ticketline.info.ignorado_existente", url=event_url)
                    continue

                title_tag = a_tag.find("p", class_="title")
                event_title = title_tag.get_text(strip=True) if title_tag else "Sem título"

                info(logger, "ticketline.info.evento.processar", idx=idx, titulo=event_title, url=event_url)

                dados_evento = processar_pagina(event_url, known_titles=known_norm)

                if dados_evento is _SKIP:
                    continue

                if not dados_evento:
                    aviso(logger, "ticketline.warn.dados_none", url=event_url)
                    continue

                if isinstance(dados_evento, list):
                    for de in dados_evento:
                        if isinstance(de, dict):
                            eventos_extraidos.append(de)
                        else:
                            aviso(logger, "ticketline.warn.dados_tipo_invalido", url=event_url)
                elif isinstance(dados_evento, dict):
                    eventos_extraidos.append(dados_evento)
                else:
                    aviso(logger, "ticketline.warn.dados_tipo_invalido", url=event_url)

                # delay apenas após processar de facto
                delay_between_requests(logger_obj=logger, message_key="ticketline.delay.proximo_evento")

            delay_between_requests(logger_obj=logger, message_key="ticketline.delay.proximo_mes")

        flush_erros(logger)

    return eventos_extraidos


if __name__ == "__main__":
    main()