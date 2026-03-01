# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import re
from datetime import date
from typing import List, Dict, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.common.utils_scrapper import (
    extract_domain,
    download_image,
    delay_between_requests,
    EVENT_RANGE,
)
from scrapers.common.data_models import build_event_dict

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

_MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


def scrape_event_links(df_existentes: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    base_url = "https://imperdivel.pt/categoria/eventos/teatro/"
    headers = {"User-Agent": "Mozilla/5.0"}
    event_list: list[dict] = []

    session = requests.Session()
    session.headers.update(headers)

    if df_existentes is None or df_existentes.empty:
        df_existentes = pd.DataFrame(columns=["Link da Peça"])
    elif "Link da Peça" not in df_existentes.columns:
        df_existentes["Link da Peça"] = pd.Series(dtype=str)

    df_existentes["Link da Peça"] = df_existentes["Link da Peça"].astype(str).str.strip().str.lower()

    total_pages = _get_total_pages(session, base_url)
    logger.info("Número total de páginas: %d", total_pages)

    for page in range(1, total_pages + 1):
        page_url = base_url if page == 1 else f"{base_url}page/{page}/"
        logger.info("Acessando %s", page_url)

        try:
            response = session.get(page_url, timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error("Erro ao acessar %s: %s", page_url, e)
            continue

        soup = BeautifulSoup(response.content, "html.parser")
        products = soup.find_all("li", class_="product")

        for idx, product in enumerate(products, start=1):
            if EVENT_RANGE and idx not in EVENT_RANGE:
                continue

            link_tag = product.find("a", class_="woocommerce-LoopProduct-link")
            url_evento = link_tag["href"].strip() if link_tag and link_tag.get("href") else ""
            url_evento_l = url_evento.lower().strip()

            if (not url_evento_l.startswith("https://imperdivel.pt/evento/")) or (
                url_evento_l in set(df_existentes["Link da Peça"].values)
            ):
                continue

            try:
                event_page_response = session.get(url_evento, timeout=30)
                event_page_response.raise_for_status()
                event_soup = BeautifulSoup(event_page_response.content, "html.parser")
            except Exception as e:
                logger.error("Erro ao acessar página do evento %s: %s", url_evento, e)
                continue

            evento = extrair_detalhes_evento(event_soup, url_evento, session)
            if evento:
                event_list.append(evento)

            delay_between_requests("antes do próximo evento na página")

        delay_between_requests(f"antes de aceder à página {page + 1}")

    return pd.DataFrame(event_list)


def _get_total_pages(session: requests.Session, base_url: str) -> int:
    try:
        response = session.get(base_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        pagination = soup.find("ul", class_="page-numbers")
        if pagination:
            pages = pagination.find_all("a", class_="page-numbers")
            page_numbers = [int(a.get_text()) for a in pages if a.get_text().isdigit()]
            return max(page_numbers) if page_numbers else 1
    except Exception as e:
        logger.error("Erro ao determinar o número total de páginas: %s", e)
    return 1


def _normalize_labels(txt: str) -> str:
    if not txt:
        return ""
    txt = txt.replace("\xa0", " ")
    # normalizar "D ATA:" etc
    for key in ("DATA", "LOCAL", "HORA", "CLASSIFICAÇÃO", "CLASSIFICACAO", "BILHETES", "DURAÇÃO", "DURACAO"):
        pat = r"(?i)" + r"\s*".join(list(key)) + r"\s*:"
        txt = re.sub(pat, key + ":", txt)
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def _extract_field(details_text: str, key: str) -> str:
    if not details_text:
        return "N/A"
    txt = _normalize_labels(details_text)
    m = re.search(rf"(?im)^{re.escape(key)}:\s*(.+?)\s*$", txt)
    if not m:
        return "N/A"
    val = m.group(1).strip(" ;")
    return val or "N/A"


def _parse_time(hora_raw: str) -> Optional[Tuple[int, int]]:
    s = (hora_raw or "").strip().lower()
    if not s or s == "n/a":
        return None

    # 21h / 21h30
    m = re.match(r"^(\d{1,2})h(\d{2})?$", s)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or "00")
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm

    # 21:30
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm

    # às vezes vem "21h00 às 22h00" → pega primeira ocorrência
    m = re.search(r"(\d{1,2})h(\d{2})", s)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm

    return None


def _parse_dates_list(data_field: str) -> List[date]:
    """
    Converte conteúdo do campo DATA: para lista de datas.
    Aguenta:
      - "14 de março de 2026"
      - "17 a 19 de julho de 2026"
      - "26 de fevereiro e 2, 10, 18 e 26 de março de 2026"
    """
    if not data_field or data_field.strip().lower() == "n/a":
        return []

    s = data_field.lower().replace("\xa0", " ").strip()

    # ano explícito
    y_m = re.search(r"\b(20\d{2})\b", s)
    year = int(y_m.group(1)) if y_m else None

    out: list[date] = []

    # 1) padrões completos DD de <mes> de AAAA
    explicit = re.findall(r"(\d{1,2})\s+de\s+([a-zçãõáéíóú]+)\s+de\s+(20\d{2})", s)
    for dd, mes, yy in explicit:
        mnum = _MESES.get(mes)
        if mnum:
            out.append(date(int(yy), mnum, int(dd)))

    if out:
        return sorted(set(out))

    # 2) blocos "<dias> de <mes>" com ano no fim
    if year:
        segs = re.findall(r"([\d,\se]+)\s+de\s+([a-zçãõáéíóú]+)", s)
        for days_part, mes in segs:
            mnum = _MESES.get(mes)
            if not mnum:
                continue

            rng = re.search(r"(\d{1,2})\s*a\s*(\d{1,2})", days_part)
            if rng:
                a, b = int(rng.group(1)), int(rng.group(2))
                for d in range(min(a, b), max(a, b) + 1):
                    out.append(date(year, mnum, d))
                continue

            for d in re.findall(r"\d{1,2}", days_part):
                out.append(date(year, mnum, int(d)))

    return sorted(set(out))


def extrair_link_comprar(soup_details) -> str:
    if not soup_details:
        return "N/A"
    for a in soup_details.find_all("a", href=True):
        href = (a["href"] or "").strip()
        if "ticketline" in href.lower() or "bol.pt" in href.lower():
            return href
    return "N/A"


def extrair_detalhes_evento(soup: BeautifulSoup, url_evento: str, session: requests.Session) -> dict:
    def get_text(selector: str) -> str:
        tag = soup.select_one(selector)
        return tag.get_text(strip=True) if tag else "N/A"

    titulo = get_text("div.page-title-inner h1")
    logger.info("Título extraído: %s", titulo)

    img_tag = soup.select_one("div.event-picture img")
    img_link = img_tag["src"].strip() if img_tag and img_tag.get("src") else "N/A"

    if img_link != "N/A":
        _ = download_image(session, img_link, titulo, extract_domain(url_evento))

    local_nome = get_text("h2.local_evento")

    details_div = soup.select_one("div.event-details")
    details_text = details_div.get_text("\n", strip=True) if details_div else ""
    details_text = _normalize_labels(details_text)

    data_field = _extract_field(details_text, "DATA")
    local_espaco = _extract_field(details_text, "LOCAL")
    hora_field = _extract_field(details_text, "HORA")
    faixa_etaria = _extract_field(details_text, "CLASSIFICAÇÃO")
    if faixa_etaria == "N/A":
        faixa_etaria = _extract_field(details_text, "CLASSIFICACAO")
    preco_formatado = _extract_field(details_text, "BILHETES")

    # separar sinopse vs ficha (linhas com "Encenação:", "Produção:", etc.)
    lines = [ln.strip() for ln in details_text.splitlines() if ln.strip()]
    cut = None
    for i, ln in enumerate(lines):
        if re.match(
            r"(?i)^(encena[çc][aã]o|dire[çc][aã]o|produ[çc][aã]o|co-?produ[çc][aã]o|companhia|grupo|texto|dramaturgia|autoria|argumento)\s*:",
            ln,
        ):
            cut = i
            break

    if cut is None:
        sinopse = "\n".join(lines).strip() or "N/A"
        credits = "N/A"
    else:
        sinopse = "\n".join(lines[:cut]).strip() or "N/A"
        credits = "\n".join(lines[cut:]).strip() or "N/A"

    # datas → lista (e start/end ISO)
    dates = _parse_dates_list(data_field)
    if dates:
        data_inicio = dates[0].isoformat()
        data_fim = dates[-1].isoformat()
    else:
        data_inicio, data_fim = "N/A", "N/A"

    # ticket_url (obrigatório no teu fluxo do teatro.app)
    ticket_url = extrair_link_comprar(details_div)
    if ticket_url == "N/A":
        ticket_url = url_evento  # fallback

    # sessões individuais para o teatro.app
    hm = _parse_time(hora_field)
    sessions_teatroapp: list[dict] = []
    venue = (local_espaco if local_espaco != "N/A" else local_nome) or "N/A"
    if dates and hm and venue != "N/A":
        hh, mm = hm
        for d in dates:
            sessions_teatroapp.append(
                {"venue": venue, "date": d.isoformat(), "hour": hh, "minute": mm, "ticket_url": ticket_url}
            )

    ev = build_event_dict(
        title=titulo,
        link=url_evento,
        image=img_link,
        start_date=data_inicio,
        end_date=data_fim,
        duration="N/A",
        location=(local_espaco if local_espaco != "N/A" else local_nome),
        city=local_nome,
        price_str=preco_formatado,
        promoter="N/A",
        synopsis=sinopse,
        credits=credits,
        age_rating=faixa_etaria,
        origin="imperdivel.pt",
        schedule=hora_field,
    )

    # extras p/ export teatro.app
    ev["Link Sessões"] = ticket_url
    ev["Teatroapp Sessions"] = sessions_teatroapp

    return ev