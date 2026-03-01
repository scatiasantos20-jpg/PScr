from __future__ import annotations

import html
import json
import os
import re
import unicodedata
from datetime import date
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import pandas as pd
import requests
from bs4 import BeautifulSoup

import time
import random
from requests.exceptions import ConnectionError as ReqConnectionError, Timeout, ChunkedEncodingError

from scrapers.common.data_models import build_event_dict
from scrapers.common.range_env import parse_global_event_range
from scrapers.common.teatroapp_fields import attach_teatroapp_fields
from scrapers.common.logging_ptpt import configurar_logger, info, aviso, erro
from scrapers.common.utils_scrapper import (
    clean_json_string,
    delay_between_requests,
    extract_age_rating,
    extract_domain,
    extract_numeric_values,
    format_session_times,
    get_random_headers,
)

logger = configurar_logger("scrapers.bol")

REQUESTS_TIMEOUT = float(os.getenv("REQUESTS_TIMEOUT", "30"))

_MESES_PT = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,  # março normalizado
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

_MESES_PT_TEXTO = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _url_key(u: str) -> str:
    return (u or "").strip().lower().rstrip("/")

def _parse_global_event_range(raw: str | None) -> range | None:
    return parse_global_event_range(raw)


def _extract_listing_event_urls(soup: BeautifulSoup) -> list[str]:
    """
    Extrai URLs de eventos da listagem BOL com fallback de seletores.
    Devolve URLs absolutas e sem duplicados, mantendo ordem.
    """
    selectors = [
        "div.item-montra.evento a.nome[href]",
        "div.item-montra.evento a.botao.info[href]",
        "a.nome[href*='/Comprar/Bilhetes/']",
    ]

    out: list[str] = []
    seen: set[str] = set()

    for sel in selectors:
        for a in soup.select(sel):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            url = href if href.startswith("http") else f"https://www.bol.pt{href}"
            k = _url_key(url)
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(url)

    return out


def _extract_jsonld_event(soup: BeautifulSoup) -> Optional[dict]:
    def _is_event_dict(d: dict) -> bool:
        t = d.get("@type")
        if isinstance(t, list):
            return any(str(x).lower() == "event" for x in t)
        return str(t).lower() == "event"

    def _find_event_node(node) -> Optional[dict]:
        if isinstance(node, dict):
            if _is_event_dict(node):
                return node
            graph = node.get("@graph")
            if isinstance(graph, list):
                for it in graph:
                    ev = _find_event_node(it)
                    if ev:
                        return ev
            return None

        if isinstance(node, list):
            for it in node:
                ev = _find_event_node(it)
                if ev:
                    return ev
        return None

    candidates: list[dict] = []
    scripts = soup.find_all("script", type="application/ld+json")
    for sc in scripts:
        if not sc or not sc.string:
            continue
        try:
            data = json.loads(clean_json_string(sc.string))
        except Exception:
            continue

        ev = _find_event_node(data)
        if ev:
            candidates.append(ev)

    if not candidates:
        return None

    def _score(ev: dict) -> int:
        score = 0
        if ev.get("name"):
            score += 3
        if ev.get("startDate"):
            score += 2
        if ev.get("location"):
            score += 1
        if ev.get("url"):
            score += 1
        return score

    candidates.sort(key=_score, reverse=True)
    return candidates[0]


def _download_image_compat(session: requests.Session, img_url: str, title: str, domain: str) -> None:
    """
    Compatível com:
      - download_image(img_url, title)
      - download_image(session, img_url, title, domain)
    """
    try:
        from scrapers.common.utils_scrapper import download_image  # import local
    except Exception:
        return

    try:
        download_image(session, img_url, title, domain)  # type: ignore[misc]
    except TypeError:
        try:
            download_image(img_url, title)  # type: ignore[misc]
        except Exception:
            return
    except Exception:
        return


def _norm_categoria(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalizar_hora_bol(s: str) -> str:
    """
    Normaliza:
      - 19h30 / 19H30 / 19:30 -> 19:30
      - 19h -> 19:00
    """
    s = (s or "").strip()
    if not s:
        return ""

    m = re.search(r"\b(\d{1,2})\s*[hH:]\s*(\d{2})\b", s)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        return f"{hh:02d}:{mm:02d}"

    m = re.search(r"\b(\d{1,2})\s*[hH]\b", s)
    if m:
        hh = int(m.group(1))
        return f"{hh:02d}:00"

    return ""


def _inferir_ano_mes(soup: BeautifulSoup, fallback_iso_date: str | None) -> tuple[int, int] | None:
    """
    Tenta inferir "Mês AAAA" no texto da página /Sessoes.
    Fallback: Data Início do master (YYYY-MM-DD).
    """
    txt = _norm_text(soup.get_text(" ", strip=True))
    m = re.search(r"\b(" + "|".join(_MESES_PT.keys()) + r")\b\s+(\d{4})\b", txt)
    if m:
        mes = _MESES_PT.get(m.group(1))
        ano = int(m.group(2))
        if mes:
            return (ano, mes)

    if fallback_iso_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fallback_iso_date):
        return (int(fallback_iso_date[0:4]), int(fallback_iso_date[5:7]))

    return None


def _formatar_data_pt(d: date) -> str:
    mes = _MESES_PT_TEXTO.get(d.month, str(d.month))
    return f"{d.day} de {mes} de {d.year}"


def _formatar_intervalo_pt(d_ini: date, d_fim: date) -> str:
    if d_ini == d_fim:
        return _formatar_data_pt(d_ini)
    return f"{_formatar_data_pt(d_ini)} a {_formatar_data_pt(d_fim)}"


def _get_sessions_soup(session: requests.Session, purchase_url: str) -> BeautifulSoup | None:
    try:
        session.headers.update(get_random_headers())
        resp = _http_get(session, purchase_url, timeout=REQUESTS_TIMEOUT)
        return BeautifulSoup(resp.content, "html.parser")
    except Exception as e:
        erro(logger, "bol.warn.horarios_erro", e, cache_key=f"bol:sessoes:{purchase_url}", url=purchase_url)
        return None


def _extrair_calendario_e_horarios(
    soup: BeautifulSoup,
    *,
    ano_base: int,
    mes_base: int,
) -> tuple[list[date], dict[str, list[str]]]:
    """
    Lê a tabela /Sessoes:
      - devolve lista de datas (date) para calcular min/max
      - devolve schedule (weekday->horas) para construir "Horários" agregados
    """
    dates: list[date] = []
    schedule: dict[str, list[str]] = {}

    table = soup.find("table", class_="Dias")
    tbody = table.find("tbody") if table else None
    if not tbody:
        return dates, schedule

    weekdays = {0: "sun", 1: "mon", 2: "tue", 3: "wed", 4: "thu", 5: "fri", 6: "sat"}

    ano = ano_base
    mes = mes_base
    prev_day: int | None = None

    # percorre por linhas/colunas, preservando ordem do calendário
    for row in tbody.find_all("tr"):
        cols = row.find_all("td")
        for i, col in enumerate(cols):
            if "DiaEvento" not in (col.get("class") or []):
                continue

            # dia do mês (número)
            day_num: int | None = None
            for s in col.stripped_strings:
                if re.fullmatch(r"\d{1,2}", s):
                    day_num = int(s)
                    break
            if not day_num or day_num < 1 or day_num > 31:
                continue

            # detecção simples de transição de mês (ex.: 28 -> 3)
            if prev_day is not None and day_num < prev_day:
                mes += 1
                if mes > 12:
                    mes = 1
                    ano += 1
            prev_day = day_num

            try:
                d = date(ano, mes, day_num)
                dates.append(d)
            except Exception:
                # ignora datas inválidas
                continue

            # horas da célula
            day_key = weekdays.get(i, "N/A")
            times: list[str] = []
            for a in col.find_all("a"):
                t_raw = a.get_text(" ", strip=True)
                t_norm = _normalizar_hora_bol(t_raw) or t_raw
                if t_norm:
                    times.append(t_norm)

            if times and day_key != "N/A":
                schedule.setdefault(day_key, []).extend(times)

    return dates, schedule


def _construir_sessao_agrupada(
    soup: BeautifulSoup,
    purchase_url: str,
    master_details: dict,
) -> tuple[str, list[dict]]:
    """
    Constrói:
      - Horários agregados (dia da semana + horas)
      - 1 sessão agrupada (Data Início/Fim como intervalo; Data Extenso em texto)
    """
    # inferir ano/mês para interpretar os números do calendário
    fallback = (master_details.get("Data Início") or "").strip()
    fallback = fallback[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", fallback[:10]) else None

    ym = _inferir_ano_mes(soup, fallback)
    if not ym:
        return "N/A", []

    ano_base, mes_base = ym

    dates, schedule = _extrair_calendario_e_horarios(soup, ano_base=ano_base, mes_base=mes_base)

    horarios_txt = format_session_times(schedule) if schedule else "N/A"

    if not dates:
        return horarios_txt, []

    d_ini = min(dates)
    d_fim = max(dates)

    sess = {
        "Nome da Peça": master_details.get("Nome da Peça", ""),
        "Link da Peça": master_details.get("Link da Peça", ""),
        "Imagem": master_details.get("Imagem", "N/A"),
        "Local": master_details.get("Local", "N/A"),
        "Concelho": master_details.get("Concelho", "N/A"),
        "Origem": master_details.get("Origem", "BOL.pt"),
        "Preço Formatado": master_details.get("Preço Formatado", "N/A"),
        # IMPORTANTE: datas sem hora (agrupadas)
        "Data Início": d_ini.isoformat(),
        "Data Fim": d_fim.isoformat(),
        # Data Extenso em texto (PT-PT)
        "Data Extenso": _formatar_intervalo_pt(d_ini, d_fim),
        # Horários com dia da semana + horas
        "Horários": horarios_txt,
        "Link Sessões": purchase_url,
    }

    return horarios_txt, [sess]


def _http_get(session: requests.Session, url: str, *, timeout: float = REQUESTS_TIMEOUT) -> requests.Response:
    max_retries = int(os.getenv("HTTP_MAX_RETRIES", "3"))
    backoff_base = float(os.getenv("HTTP_BACKOFF_BASE", "3"))
    backoff_max = float(os.getenv("HTTP_BACKOFF_MAX", "25"))

    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        headers = get_random_headers()
        # Evita reutilizar ligações antigas após delays longos (keep-alive "stale")
        headers["Connection"] = "close"

        try:
            resp = session.get(url, timeout=timeout, headers=headers)

            # Repetir apenas em estados transitórios
            if resp.status_code in (429, 500, 502, 503, 504):
                if attempt == max_retries:
                    # Força erro para ser apanhado e logado, em vez de parsear HTML de erro
                    resp.raise_for_status()

                wait = min(backoff_max, backoff_base * (2 ** (attempt - 1))) + random.uniform(0.0, 1.5)
                aviso(
                    logger,
                    "bol.warn.http_retry_status",
                    url=url,
                    status=resp.status_code,
                    tentativa=attempt,
                    espera=wait,
                )
                time.sleep(wait)
                continue

            return resp

        except (ReqConnectionError, ConnectionResetError, Timeout, ChunkedEncodingError, requests.HTTPError) as e:
            last_exc = e
            if attempt == max_retries:
                raise

            wait = min(backoff_max, backoff_base * (2 ** (attempt - 1))) + random.uniform(0.0, 1.5)
            aviso(
                logger,
                "bol.warn.http_retry_ex",
                url=url,
                tentativa=attempt,
                espera=wait,
                erro=str(e),
            )
            time.sleep(wait)

    if last_exc:
        raise last_exc
    raise RuntimeError("Falha inesperada em _http_get")


# ──────────────────────────────────────────────────────────────────────────────
# Scraping
# ──────────────────────────────────────────────────────────────────────────────

def get_event_details(
    session: requests.Session,
    event_url: str,
    known_titles: Optional[set[str]] = None,
    *,
    categoria_whitelist: Optional[set[str]] = None,
) -> Optional[dict]:
    """
    Vai à página do evento e devolve o dict do evento (master), sem horários/sessões.
    """
    try:
        if known_titles and _url_key(event_url) in known_titles:
            info(logger, "bol.info.ignorar_conhecido", url=event_url)
            return None

        session.headers.update(get_random_headers())
        resp = _http_get(session, event_url, timeout=REQUESTS_TIMEOUT)
        soup = BeautifulSoup(resp.content, "html.parser")

        # Link correcto de sessões (botão Comprar)
        buy_a = soup.select_one("li.comprar a[href*='/Sessoes']")
        purchase_url = (
            f"https://www.bol.pt{buy_a['href']}" if buy_a and buy_a.get("href") else f"{event_url}/Sessoes"
        )

        # Categoria (ex.: "Teatro & Arte | Teatro") — filtro só na família
        categoria_final = "N/A"
        detalhes_div = soup.find("div", class_="detalhes")
        if detalhes_div:
            h3 = detalhes_div.find("h3", id="infoNomeEsp")
            if h3:
                sp = h3.find_next("span")
                if sp:
                    cat_txt = sp.get_text(" ", strip=True) or ""
                    categoria_final = cat_txt.split("|")[-1].strip() if "|" in cat_txt else cat_txt.strip()

        if categoria_whitelist is not None:
            wl = {_norm_categoria(x) for x in categoria_whitelist}
            cat_norm = _norm_categoria(categoria_final)
            if cat_norm not in wl:
                info(logger, "bol.info.ignorar_categoria_familia", categoria=categoria_final or "N/A", url=event_url)
                return None

        event_data = _extract_jsonld_event(soup)
        if not event_data or not isinstance(event_data, dict):
            aviso(logger, "bol.warn.jsonld_nao_encontrado")
            return None

        title = html.unescape(event_data.get("name", "") or "").strip().replace('"', "").replace("'", "")
        if not title:
            aviso(logger, "bol.warn.titulo_nao_encontrado")
            return None

        # Datas (master)
        raw_start = (event_data.get("startDate") or "").strip()
        start_date = raw_start.split("T")[0] if "T" in raw_start else (raw_start or "N/A")

        raw_end = (event_data.get("endDate") or "").strip()
        end_date = raw_end.split("T")[0] if "T" in raw_end else (raw_end or "N/A")

        # Duração ISO (PTxxHxxM) -> minutos (string)
        duration_raw = (event_data.get("duration") or "").strip()
        duration = "N/A"
        if duration_raw.startswith("PT"):
            time_str = duration_raw.replace("PT", "")
            try:
                if "H" in time_str:
                    hours, rest = time_str.split("H", 1)
                    minutes = rest.replace("M", "") if "M" in rest else "0"
                    duration = f"{int(hours) * 60 + int(minutes)} Minutos"
                elif "M" in time_str:
                    minutes = time_str.replace("M", "")
                    duration = f"{int(minutes)} Minutos"
            except Exception:
                duration = "N/A"

        # Local e concelho
        location = (event_data.get("location") or {}).get("name", "N/A")
        city = ((event_data.get("location") or {}).get("address") or {}).get("addressLocality", "N/A")

        # Imagem (download sempre que exista fonte válida)
        domain = extract_domain(event_url)
        img_tag = soup.find("img", id="ImagemEvento")
        img_link = img_tag["src"] if img_tag and img_tag.get("src") else ""
        if not img_link:
            raw_img = event_data.get("image")
            if isinstance(raw_img, list):
                img_link = str(raw_img[0] if raw_img else "").strip()
            else:
                img_link = str(raw_img or "").strip()

        if img_link:
            parts = urlsplit(img_link)
            if not parts.scheme:
                img_link = "https://www.bol.pt" + (img_link if img_link.startswith("/") else f"/{img_link}")
                parts = urlsplit(img_link)
            new_path = re.sub(r"(\.jpg|\.jpeg|\.png)$", r"_grande\1", parts.path, flags=re.IGNORECASE)
            img_link = urlunsplit((parts.scheme, parts.netloc, new_path, parts.query, parts.fragment))
            _download_image_compat(session, img_link, title, domain)
        else:
            img_link = "N/A"

        # Promotor e sinopse
        promoter, synopsis = "N/A", "N/A"
        info_box = soup.find("div", class_="info-restante")
        if info_box:
            paragraphs = info_box.find_all("p")
            if paragraphs:
                promoter = paragraphs[0].get_text(strip=True) or "N/A"
            if len(paragraphs) > 1:
                synopsis = paragraphs[1].get_text(strip=True) or "N/A"

        # Ficha artística (preserva separadores)
        credits = "N/A"
        credits_tag = soup.find("h3", string="Ficha Artística")
        if credits_tag:
            parts = []
            for sib in credits_tag.find_next_siblings():
                if getattr(sib, "name", "") == "h3":
                    break
                txt = sib.get_text("\n", strip=True) if hasattr(sib, "get_text") else ""
                if txt:
                    parts.append(txt)
            if not parts:
                p = credits_tag.find_next("p")
                if p:
                    parts.append(p.get_text("\n", strip=True))
            credits = "\n".join(parts).strip() or "N/A"

        # Preços
        price = "N/A"
        price_el = soup.find("h3", string="Preços")
        price_list: list[str] = []

        if price_el:
            try:
                from scrapers.common import utils_scrapper as U
                if hasattr(U, "extract_prices"):
                    price_list = U.extract_prices(price_el)  # type: ignore[attr-defined]
                elif hasattr(U, "extract_price"):
                    price_list = U.extract_price(soup)  # type: ignore[attr-defined]
            except Exception:
                price_list = []

        values = extract_numeric_values(price_list) if price_list else []
        if values:
            mn, mx = min(values), max(values)
            if mn == mx:
                price = f"{mn:.2f}€".replace(".", ",")
            else:
                price = f"{mn:.2f}€ a {mx:.2f}€".replace(".", ",")

        age_rating = extract_age_rating(soup)

        info(logger, "bol.info.evento_processado", titulo=title)

        ev = build_event_dict(
            title=title,
            link=event_url,
            image=img_link,
            start_date=start_date,
            end_date=end_date,
            duration=duration,
            location=location,
            city=city,
            price_str=price,
            promoter=promoter,
            synopsis=synopsis,
            credits=credits,
            age_rating=age_rating,
            origin="BOL.pt",
            schedule="N/A",
        )

        return attach_teatroapp_fields(ev, ticket_url=purchase_url, sessions=[])

    except Exception as e:
        erro(logger, "bol.err.obter_detalhes", e, cache_key=f"bol:detalhes:{event_url}", url=event_url)
        return None


def scrape_theatre_info(known_titles: Optional[set[str]] = None) -> pd.DataFrame:
   # known_titles = {x.strip().lower() for x in (known_titles or set()) if isinstance(x, str)}
    known_titles = {_url_key(x) for x in (known_titles or set()) if isinstance(x, str)}
    event_range = _parse_global_event_range(os.getenv("GLOBAL_EVENT_RANGE"))

    urls = [
        "https://www.bol.pt/Comprar/pesquisa/1-101-0-0-0-0/bilhetes_de_teatro_arte_teatro",
        "https://www.bol.pt/Comprar/pesquisa/3-3002-0-0-0-0/bilhetes_de_familia",
        "https://www.bol.pt/Comprar/Pesquisa?q=teatro+de+revista&dist=0&e=0",
        "https://www.bol.pt/Comprar/pesquisa/1-106-0-0-0-0/bilhetes_de_teatro_arte_musical",
    ]

    events: list[dict] = []

    with requests.Session() as session:
        session.headers.update(get_random_headers())

        for url in urls:
            is_familia = "bilhetes_de_familia" in url
            familia_whitelist = {"Teatro", "Musical", "Infantil"} if is_familia else None

            delay_between_requests(logger_obj=logger, message_key="utils.delay.antes_sincronizar", origem="BOL")

            session.headers.update(get_random_headers())
            info(logger, "bol.info.carregar_listagem", url=url)

            try:
                resp = _http_get(session, url, timeout=REQUESTS_TIMEOUT)
            except Exception as e:
                erro(logger, "bol.err.listagem_falhou", e, cache_key=f"bol:listagem:{url}", url=url)
                continue

            soup = BeautifulSoup(resp.content, "html.parser")

            all_urls = _extract_listing_event_urls(soup)
            if event_range is None:
                urls_to_process = all_urls
                info(logger, "bol.info.selecao_todos")
            else:
                urls_to_process = [u for i, u in enumerate(all_urls, start=1) if i in event_range]
                info(logger, "bol.info.selecao_range", inicio=event_range.start, fim=event_range.stop - 1)

            for event_url in urls_to_process:
                event_key = _url_key(event_url)

                # SKIP real: já está em cache → não processa e não dorme
                if known_titles and event_key in known_titles:
                    info(logger, "bol.info.ignorar_conhecido", url=event_url)
                    continue

                info(logger, "bol.info.processar_evento", url=event_url)

            
                details = get_event_details(
                    session,
                    event_url,
                    known_titles,
                    categoria_whitelist=familia_whitelist,
                )
                if details:
                    purchase_url = (details.get("Link Sessões") or f"{event_url}/Sessoes").strip()
                    sessoes_soup = _get_sessions_soup(session, purchase_url)

                    if sessoes_soup:
                        horarios_txt, sessoes = _construir_sessao_agrupada(sessoes_soup, purchase_url, details)
                        details["Horários"] = horarios_txt
                        details["Sessões"] = sessoes
                    else:
                        details["Horários"] = "N/A"
                        details["Sessões"] = []

                    events.append(details)

                delay_between_requests(logger_obj=logger, message_key="utils.delay.proximo_registo", origem="BOL")

    df = pd.DataFrame(events)
    if not df.empty:
        if "Data Início" in df.columns and "Data Fim" in df.columns:
            df.sort_values(by=["Data Início", "Data Fim"], inplace=True)
        info(logger, "bol.info.recolhidos", n=len(df))
    else:
        info(logger, "bol.info.nenhum")

    return df
