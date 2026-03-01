from __future__ import annotations

import re
from datetime import datetime, date
from typing import Optional

import requests
from bs4 import BeautifulSoup

from scrapers.common.data_models import build_event_dict
from scrapers.common.logging_ptpt import configurar_logger, info, aviso, erro
from scrapers.common.utils_scrapper import fetch_page, format_session_times, download_image

logger = configurar_logger("scrapers.ticketline.single")

_MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def _url_key(u: str) -> str:
    return (u or "").strip().lower().rstrip("/")


def _formatar_data_pt(d: date) -> str:
    return f"{d.day} de {_MESES_PT.get(d.month, str(d.month))} de {d.year}"


def _formatar_intervalo_pt(start_iso: str, end_iso: str) -> str:
    try:
        d1 = datetime.strptime(start_iso, "%Y-%m-%d").date()
        d2 = datetime.strptime(end_iso, "%Y-%m-%d").date()
        if d1 == d2:
            return _formatar_data_pt(d1)
        return f"{_formatar_data_pt(d1)} a {_formatar_data_pt(d2)}"
    except Exception:
        if start_iso == end_iso:
            return start_iso
        return f"{start_iso} a {end_iso}"


def scrape_single_page(
    url: str,
    known_titles: Optional[set[str]] = None,
    event_title: Optional[str] = None,
    known_start_date: Optional[datetime] = None,
    known_end_date: Optional[datetime] = None,
    download_image_flag: bool = True,
    *,
    html: Optional[str] = None,
    session: Optional[requests.Session] = None,
):
    # Normalizar known_titles (defensivo)
    known_norm: set[str] = set()
    if known_titles:
        try:
            known_norm = {_url_key(x) for x in known_titles if isinstance(x, str) and x.strip()}
        except Exception:
            known_norm = set()

    urlk = _url_key(url)

    # 1) dedupe por URL
    if known_norm and urlk in known_norm:
        info(logger, "ticketline.info.ignorado_existente", url=url)
        return None

    # 2) HTML
    if html is None:
        html = fetch_page(url)
    if not html:
        aviso(logger, "ticketline.warn.sem_html", url=url)
        return None

    soup = BeautifulSoup(html, "html.parser")

    # A) Título
    if not event_title:
        title_tag = soup.find("h2", class_="title")
        event_title = title_tag.get_text(strip=True) if title_tag else "Sem título"

    # B) Imagem
    image_url = "N/A"
    thumb_el = soup.find("a", class_="thumb")
    if thumb_el and thumb_el.get("href"):
        img_link = re.sub(r"W=\d+", "W=600", thumb_el["href"])
        if img_link.startswith("//"):
            img_link = "https:" + img_link
        image_url = img_link

    if download_image_flag and image_url != "N/A":
        s = session or requests.Session()
        _ = download_image(s, image_url, event_title, "ticketline")

    # C) Duração
    duration = "N/A"
    dur_el = soup.find("p", class_="duration")
    if dur_el:
        m = re.search(r"(\d+)", dur_el.get_text(strip=True))
        if m:
            duration = f"{m.group(1)} Minutos"

    # D) Local / Concelho
    top_venue = soup.find("p", class_="venue")
    top_dist = soup.find("span", class_="district")
    location = top_venue.get_text(strip=True) if top_venue else "N/A"
    city = top_dist.get_text(strip=True) if top_dist else "N/A"

    # E) Preço
    low_price_tag = soup.find("span", itemprop="lowPrice")
    high_price_tag = soup.find("span", itemprop="highPrice")

    low_price = None
    high_price = None

    if low_price_tag:
        raw_low = re.sub(r"[^\d.,]", "", low_price_tag.get_text(strip=True)).replace(",", ".")
        try:
            low_price = float(raw_low)
        except ValueError:
            low_price = None

    if high_price_tag:
        raw_high = re.sub(r"[^\d.,]", "", high_price_tag.get_text(strip=True)).replace(",", ".")
        try:
            high_price = float(raw_high)
        except ValueError:
            high_price = None

    if low_price is not None and high_price is not None:
        price_str = f"{low_price:.2f}€ a {high_price:.2f}€".replace(".", ",")
    elif low_price is not None:
        price_str = f"Desde {low_price:.2f}€".replace(".", ",")
    else:
        price_str = "N/A"

    # F) Promotor
    promoter = "N/A"
    prom_el = soup.find("h2", string=re.compile(r"Promotor", re.I))
    if prom_el:
        next_p = prom_el.find_next("p")
        promoter = next_p.get_text(strip=True) if next_p else "N/A"

    # G) Sinopse
    synopsis = "N/A"
    sinopse_div = soup.find("div", id="sinopse")
    if sinopse_div:
        text_div = sinopse_div.find("div", class_="text")
        synopsis = text_div.get_text(strip=True) if text_div else "N/A"

    # H) Faixa Etária
    age_rating = "N/A"
    age_el = soup.find("p", class_="age")
    if age_el:
        age_text = age_el.get_text(strip=True).replace("Classificação:", "").strip()
        if age_text:
            age_rating = age_text

    # I) Sessões (datas individuais + horário agrupado por weekday)
    session_dates: list[datetime] = []
    wd_map: dict[str, list[str]] = {}

    session_items = soup.select('ul.sessions_list li[itemprop="Event"], ul.sessions_list li')
    for item in session_items:
        date_div = item.find("div", class_="date")
        if not date_div or not date_div.has_attr("content"):
            continue

        date_content = date_div["content"]  # ex.: 2026-01-10T21:30
        try:
            dt_obj = datetime.strptime(date_content, "%Y-%m-%dT%H:%M")
        except ValueError:
            erro(logger, "ticketline.err.formato_data_desconhecido", data=date_content)
            continue

        if known_start_date and known_end_date and known_start_date <= dt_obj <= known_end_date:
            continue

        session_dates.append(dt_obj)

        weekday_code = dt_obj.strftime("%a").lower()[:3]  # mon/tue/...
        wd_map.setdefault(weekday_code, []).append(dt_obj.strftime("%H:%M"))

    if session_dates:
        session_dates = sorted({d.replace(second=0, microsecond=0) for d in session_dates})

        start_date = session_dates[0].strftime("%Y-%m-%d")
        end_date = session_dates[-1].strftime("%Y-%m-%d")
        schedule = format_session_times(wd_map)
        data_extenso = _formatar_intervalo_pt(start_date, end_date)

        sessoes = [{
            "Nome da Peça": event_title,
            "Link da Peça": url,
            "Imagem": image_url,
            "Local": location,
            "Concelho": city,
            "Origem": "Ticketline.sapo.pt",
            "Preço Formatado": price_str,
            "Data Início": start_date,
            "Data Fim": end_date,
            "Data Extenso": data_extenso,
            "Horários": schedule,
        }]
    else:
        start_date = "N/A"
        end_date = "N/A"
        schedule = "N/A"
        sessoes = []

    event = build_event_dict(
        title=event_title,
        link=url,
        image=image_url,
        start_date=start_date,
        end_date=end_date,
        duration=duration,
        location=location,
        city=city,
        price_str=price_str,
        promoter=promoter,
        synopsis=synopsis,
        credits="N/A",
        age_rating=age_rating,
        origin="ticketline.sapo.pt",
        schedule=schedule,
    )
    event["Sessões"] = sessoes

    # Extras para Teatro.app export (sessões individuais prontas)
    if session_dates:
        venue = location if location != "N/A" else (city if city != "N/A" else "Não indicado")
        event["Teatroapp Sessions"] = [
            {
                "venue": venue,
                "date": dt.strftime("%Y-%m-%d"),
                "hour": dt.hour,
                "minute": dt.minute,
                "ticket_url": url,
            }
            for dt in session_dates
        ]
    else:
        event["Teatroapp Sessions"] = []

    event["Link Sessões"] = url

    return event