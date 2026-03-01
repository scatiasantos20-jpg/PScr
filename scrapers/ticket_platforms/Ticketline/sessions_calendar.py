from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime, date
from typing import Optional, Tuple

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from scrapers.common.data_models import build_event_dict
from scrapers.common.teatroapp_fields import attach_teatroapp_fields
from scrapers.common.logging_ptpt import configurar_logger, info, aviso, erro
from scrapers.common.utils_scrapper import fetch_page, format_session_times, get_random_headers

logger = configurar_logger("scrapers.ticketline.calendar")

WEEKDAY_KEYS_PT = {
    0: "seg", 1: "ter", 2: "qua", 3: "qui", 4: "sex", 5: "sáb", 6: "dom"
}

_MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


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


def _url_key(u: str) -> str:
    return (u or "").strip().lower().rstrip("/")


def _try_float_pt(txt: str) -> float | None:
    try:
        return float(txt.replace("€", "").replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _extract_static_json(
    calendar_data: list,
    session_dates: list[datetime],
    prices: set[float],
    times_by_weekday: defaultdict[str, set[str]],
) -> tuple[str | None, str | None]:
    location = city = None

    for session in calendar_data:
        venue = session.get("venue", {}) or {}
        if not location:
            location = venue.get("name")
        if not city:
            city = venue.get("municipalityName")

        ts = session.get("startDate")
        if ts:
            dt = datetime.fromtimestamp(int(ts))
            session_dates.append(dt)
            times_by_weekday[WEEKDAY_KEYS_PT[dt.weekday()]].add(dt.strftime("%H:%M"))

        for key in ("lowestPrice", "highestPrice"):
            p = session.get(key)
            if p is not None:
                try:
                    prices.add(float(p))
                except ValueError:
                    pass

        for zone in venue.get("zones", []) or []:
            for disc in zone.get("discounts", []) or []:
                dstr = (disc.get("sessionDate", {}) or {}).get("date")
                if dstr:
                    try:
                        dt = datetime.strptime(dstr, "%Y-%m-%d %H:%M:%S.%f")
                        session_dates.append(dt)
                        times_by_weekday[WEEKDAY_KEYS_PT[dt.weekday()]].add(dt.strftime("%H:%M"))
                    except ValueError:
                        pass

            p = (zone.get("seats_price", {}) or {}).get("total_amount")
            if p is not None:
                try:
                    prices.add(float(p))
                except ValueError:
                    pass

    return location, city


def _crawl_interactive_calendar(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    session_dates: list[datetime],
    prices: set[float],
    times_by_weekday: defaultdict[str, set[str]],
) -> Tuple[str | None, str | None]:
    visited = set()
    location = city = None

    while True:
        while True:
            anchor = None
            anchor_td = None
            anchor_key = None

            for a in driver.find_elements(By.CSS_SELECTOR, "table.ui-datepicker-calendar td.available a"):
                td = a.find_element(By.XPATH, "..")
                key = (td.get_attribute("data-year"), td.get_attribute("data-month"), a.text)
                if key not in visited:
                    anchor, anchor_key, anchor_td = a, key, td
                    break

            if anchor is None:
                break

            visited.add(anchor_key)

            year = int(anchor_td.get_attribute("data-year"))
            month = int(anchor_td.get_attribute("data-month")) + 1
            day = int(anchor.text)

            driver.execute_script("arguments[0].click();", anchor)

            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.events_list")))

            # Extrair local/cidade
            if not location:
                try:
                    venue_el = driver.find_element(By.CSS_SELECTOR, "p.venue")
                    location = venue_el.text.strip()
                except Exception:
                    pass

            if not city:
                try:
                    dist_el = driver.find_element(By.CSS_SELECTOR, "span.district")
                    city = dist_el.text.strip()
                except Exception:
                    pass

            # Extrair preços e sessões
            for row in driver.find_elements(By.CSS_SELECTOR, "div.events_list div.row"):
                try:
                    time_el = row.find_element(By.CSS_SELECTOR, "span.time")
                    time_txt = time_el.text.strip()
                except Exception:
                    time_txt = ""

                # hora
                t_m = re.search(r"(\d{1,2}:\d{2})", time_txt)
                hhmm = t_m.group(1) if t_m else None

                # preço
                try:
                    price_el = row.find_element(By.CSS_SELECTOR, "span.price")
                    p = _try_float_pt(price_el.text.strip())
                    if p is not None:
                        prices.add(p)
                except Exception:
                    pass

                if hhmm:
                    try:
                        dt = datetime.strptime(f"{year:04d}-{month:02d}-{day:02d}T{hhmm}", "%Y-%m-%dT%H:%M")
                        session_dates.append(dt)
                        times_by_weekday[WEEKDAY_KEYS_PT[dt.weekday()]].add(dt.strftime("%H:%M"))
                    except Exception:
                        pass

        # Tentar avançar mês
        try:
            next_btn = driver.find_element(By.CSS_SELECTOR, "a.ui-datepicker-next")
            cls = (next_btn.get_attribute("class") or "")
            if "ui-state-disabled" in cls:
                break
            driver.execute_script("arguments[0].click();", next_btn)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.ui-datepicker-calendar")))
        except Exception:
            break

    return location, city




def parse_calendar_static_from_html(html: str, *, event_title: str | None = None) -> dict:
    """Parsing puro da calendar page (sem Selenium)."""
    soup = BeautifulSoup(html or "", "html.parser")

    title = event_title or (
        soup.find("h2", class_="title").get_text(strip=True)
        if soup.find("h2", class_="title") else "Sem título"
    )

    image_url = "N/A"
    img_el = soup.find("a", class_="thumb")
    if img_el and img_el.get("href"):
        image_url = "https:" + re.sub(r"W=\d+", "W=600", img_el["href"])

    dur = "N/A"
    d_el = soup.find("p", class_="duration")
    if d_el:
        m = re.search(r"(\d+)", d_el.get_text(strip=True))
        if m:
            dur = f"{m.group(1)} Minutos"

    age_el = soup.find("p", class_="age")
    age_rating = (
        age_el.get_text(strip=True).replace("Classificação:", "").strip()
        if age_el else "N/A"
    ) or "N/A"

    prom_el = soup.find("h2", string=re.compile(r"Promotor", re.I))
    promoter = prom_el.find_next("p").get_text(strip=True) if prom_el else "N/A"

    syn = "N/A"
    sin_div = soup.find("div", id="sinopse")
    if sin_div:
        txt_div = sin_div.find("div", class_="text")
        syn = txt_div.get_text(strip=True) if txt_div else "N/A"

    session_dates: list[datetime] = []
    prices: set[float] = set()
    times_by_weekday: defaultdict[str, set[str]] = defaultdict(set)
    location = city = None

    script = soup.find("script", {"type": "text/json", "data-name": "calendar-data"})
    if script and script.string:
        try:
            cal_json = json.loads(script.string)
            location, city = _extract_static_json(cal_json, session_dates, prices, times_by_weekday)
        except Exception:
            session_dates.clear()
            prices.clear()
            times_by_weekday.clear()

    return {
        "title": title,
        "image_url": image_url,
        "dur": dur,
        "age_rating": age_rating,
        "promoter": promoter,
        "syn": syn,
        "session_dates": session_dates,
        "prices": prices,
        "times_by_weekday": times_by_weekday,
        "location": location,
        "city": city,
    }
def scrape_sessions_calendar(
    link: str,
    known_titles: Optional[set[str]] = None,
    *,
    html: Optional[str] = None,
    chrome_driver_path: str | None = None,
    headless: bool = True,
    event_title: str | None = None,
):
    known_norm: set[str] = set()
    if known_titles:
        try:
            known_norm = {_url_key(x) for x in known_titles if isinstance(x, str) and x.strip()}
        except Exception:
            known_norm = set()

    if known_norm and _url_key(link) in known_norm:
        info(logger, "ticketline.info.ignorado_existente", url=link)
        return None

    if html is None:
        html = fetch_page(link)
    if not html:
        aviso(logger, "ticketline.warn.sem_html", url=link)
        return None

    parsed = parse_calendar_static_from_html(html, event_title=event_title)
    title = parsed["title"]
    image_url = parsed["image_url"]
    dur = parsed["dur"]
    age_rating = parsed["age_rating"]
    promoter = parsed["promoter"]
    syn = parsed["syn"]
    session_dates: list[datetime] = list(parsed["session_dates"])
    prices: set[float] = set(parsed["prices"])
    times_by_weekday: defaultdict[str, set[str]] = parsed["times_by_weekday"]
    location = parsed["location"]
    city = parsed["city"]

    def _build_result() -> dict:
        session_dates.sort()
        start_date = session_dates[0].strftime("%Y-%m-%d") if session_dates else "N/A"
        end_date = session_dates[-1].strftime("%Y-%m-%d") if session_dates else "N/A"

        price_str = "N/A"
        if prices:
            lo, hi = min(prices), max(prices)
            price_str = (f"{lo:.2f}€" if lo == hi else f"{lo:.2f}€ a {hi:.2f}€").replace(".", ",")

        schedule = format_session_times(times_by_weekday) if session_dates else "N/A"
        data_extenso = _formatar_intervalo_pt(start_date, end_date) if session_dates else "N/A"

        ev = build_event_dict(
            title=title,
            link=link,
            image=image_url,
            start_date=start_date,
            end_date=end_date,
            duration=dur,
            location=location or "N/A",
            city=city or "N/A",
            price_str=price_str,
            promoter=promoter,
            synopsis=syn,
            credits="N/A",
            age_rating=age_rating,
            origin="ticketline.sapo.pt",
            schedule=schedule,
        )

        if session_dates:
            ev["Sessões"] = [{
                "Nome da Peça": title,
                "Link da Peça": link,
                "Imagem": image_url,
                "Local": location or "N/A",
                "Concelho": city or "N/A",
                "Origem": "Ticketline.sapo.pt",
                "Preço Formatado": price_str,
                "Data Início": start_date,
                "Data Fim": end_date,
                "Data Extenso": data_extenso,
                "Horários": schedule,
            }]
        else:
            ev["Sessões"] = []

        sessions_teatroapp = []
        if session_dates:
            uniq = sorted({d.replace(second=0, microsecond=0) for d in session_dates})
            venue = (location or "").strip() or (city or "").strip() or "Não indicado"
            sessions_teatroapp = [
                {"venue": venue, "date": dt.strftime("%Y-%m-%d"), "hour": dt.hour, "minute": dt.minute, "ticket_url": link}
                for dt in uniq
            ]

        return attach_teatroapp_fields(ev, ticket_url=link, sessions=sessions_teatroapp)

    # 2) Se já há sessões via JSON, não usa Selenium
    if session_dates:
        return _build_result()

    # 3) Selenium (fallback)
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")

    ua = (get_random_headers() or {}).get("User-Agent")
    if ua:
        opts.add_argument(f"--user-agent={ua}")

    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    service = Service(chrome_driver_path) if chrome_driver_path and os.path.exists(chrome_driver_path) else Service()
    driver = webdriver.Chrome(service=service, options=opts)
    wait = WebDriverWait(driver, 15)

    try:
        driver.get(link)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        location, city = _crawl_interactive_calendar(driver, wait, session_dates, prices, times_by_weekday)
        return _build_result()

    except TimeoutException as e:
        erro(logger, "ticketline.err.calendar.timeout", e, cache_key="ticketline:calendar:timeout", url=link)
    except Exception as e:
        erro(logger, "ticketline.err.calendar.falha", e, cache_key="ticketline:calendar:falha", url=link)
    finally:
        driver.quit()

    return None