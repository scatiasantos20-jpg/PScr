from __future__ import annotations

import os
import time
import random
import re
from urllib.parse import urlparse
import urllib.request

import requests
from bs4 import BeautifulSoup

from scrapers.common.logging_ptpt import configurar_logger, info, aviso, erro
from scrapers.common.range_env import parse_global_event_range

logger = configurar_logger("scrapers.utils")


# ──────────────────────────────────────────────────────────────────────────────
# Configuração via .env
# ──────────────────────────────────────────────────────────────────────────────
def _parse_range(raw: str, default_start: int = 10, default_end: int = 20) -> range:
    raw = (raw or "").strip()
    if not raw:
        return range(default_start, default_end)

    # formatos aceites: "10-20" ou "10:20"
    for sep in ("-", ":"):
        if sep in raw:
            a, b = raw.split(sep, 1)
            try:
                start = int(a.strip())
                end = int(b.strip())
                return range(start, end)
            except ValueError:
                return range(default_start, default_end)

    # se vier só um número, interpreta como "0-n"
    try:
        end = int(raw)
        return range(0, end)
    except ValueError:
        return range(default_start, default_end)


BASE_DIRECTORY = os.getenv("BASE_DIRECTORY", ".").strip() or "."
POSTERS_DIRECTORY = os.path.join(BASE_DIRECTORY, "Cartazes")

# Mantém compatibilidade com imports antigos (listapecas/bol_scraper/etc.)
GLOBAL_EVENT_RANGE = parse_global_event_range(os.getenv("GLOBAL_EVENT_RANGE"))
EVENT_RANGE = GLOBAL_EVENT_RANGE
EVENT_RANGE_TL = GLOBAL_EVENT_RANGE


# ──────────────────────────────────────────────────────────────────────────────
# User-Agents
# ──────────────────────────────────────────────────────────────────────────────
_DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
]

USER_AGENTS: list[str] = []


def _load_user_agents() -> list[str]:
    agents: list[str] = []

    raw = (os.getenv("USER_AGENTS", "") or "").strip()
    if raw:
        # permite separar por | ou por novas linhas
        parts = []
        if "|" in raw:
            parts = [p.strip() for p in raw.split("|")]
        else:
            parts = [p.strip() for p in raw.splitlines()]
        agents = [p for p in parts if p]
        if agents:
            info(logger, "utils.ua.lidos_env", n=len(agents))
            return agents

    file_path = (os.getenv("USER_AGENTS_FILE", "") or "").strip()
    if file_path:
        if not os.path.exists(file_path):
            aviso(logger, "utils.ua.ficheiro_inexistente", ficheiro=file_path)
        else:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    agents = [ln.strip() for ln in f.readlines() if ln.strip()]
                if agents:
                    info(logger, "utils.ua.lidos_ficheiro", n=len(agents), ficheiro=file_path)
                    return agents
            except Exception:
                pass

    aviso(logger, "utils.ua.fallback")
    return _DEFAULT_USER_AGENTS.copy()


USER_AGENTS = _load_user_agents()


def get_random_headers() -> dict:
    return {"User-Agent": random.choice(USER_AGENTS)}


# ──────────────────────────────────────────────────────────────────────────────
# Delay genérico anti-bot (range via .env)
# ──────────────────────────────────────────────────────────────────────────────
def delay_between_requests(
    description: str = "",
    *,
    logger_obj=None,
    message_key: str | None = None,
    **kwargs,
) -> float:
    """
    Delay aleatório entre pedidos. Controlos:
      REQUEST_DELAY_MIN (default 60)
      REQUEST_DELAY_MAX (default 120)

    - Se message_key for indicado, usa-o (ex.: tickets.delay.antes_processar).
    - Caso contrário, usa utils.delay.geral ou utils.delay.com_descricao.
    """
    lg = logger_obj or logger

    try:
        mn = float(os.getenv("REQUEST_DELAY_MIN", "60"))
        mx = float(os.getenv("REQUEST_DELAY_MAX", "120"))
    except ValueError:
        mn, mx = 60.0, 120.0

    if mx < mn:
        mn, mx = mx, mn

    seconds = random.uniform(mn, mx)

    if message_key:
        info(lg, message_key, segundos=seconds, **kwargs)
    else:
        if description:
            info(lg, "utils.delay.com_descricao", segundos=seconds, descricao=description)
        else:
            info(lg, "utils.delay.geral", segundos=seconds)

    time.sleep(seconds)
    return seconds


# ──────────────────────────────────────────────────────────────────────────────
# Fetch utilitário
# ──────────────────────────────────────────────────────────────────────────────
def fetch_page(url: str) -> str:
    headers = get_random_headers()
    req = urllib.request.Request(url, headers=headers)
    try:
        info(logger, "utils.fetch.iniciar", url=url)
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read()
            return content.decode("utf-8", errors="replace")
    except Exception as e:
        erro(logger, "utils.fetch.erro", e, cache_key=f"utils:fetch:{url}", url=url)
        return ""


def detectar_tipo_pagina(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # 1) Calendar: sinais fortes
    if soup.find("script", {"type": "text/json", "data-name": "calendar-data"}):
        return "calendar"
    if soup.find(id="calendar"):
        return "calendar"
    if soup.select_one("#ui-datepicker-div") or soup.select_one("table.ui-datepicker-calendar") or soup.select_one(".ui-datepicker-calendar"):
        return "calendar"

    # 2) Single: lista de sessões
    if soup.select_one('ul.sessions_list li[itemprop="Event"]') or soup.select_one("ul.sessions_list"):
        return "single"

    # 3) Multi: listas de eventos
    if soup.select_one("ul.events_list") and soup.select_one('li[itemtype="http://schema.org/Event"]'):
        return "multi"
    if soup.select_one("ul.events_list.highlights_list") or soup.find(id="eventList"):
        return "multi"
    return "desconhecido"

# ──────────────────────────────────────────────────────────────────────────────
# Funções auxiliares (mantidas)
# ──────────────────────────────────────────────────────────────────────────────
def clean_json_string(json_string: str) -> str:
    return re.sub(r"[\x00-\x1F\x7F-\x9F]", "", json_string)


def extract_domain(url: str) -> str:
    parsed = urlparse(url)
    parts = parsed.netloc.split(".")
    return parts[-2] if len(parts) >= 2 else parsed.netloc


def extract_numeric_values(prices: list[str]) -> list[float]:
    values = []
    for price in prices:
        match = re.search(r"\d+(?:[.,]\d+)?", price)
        if match:
            values.append(float(match.group(0).replace(",", ".")))
    return values


def extract_session_times(soup: BeautifulSoup) -> list[str]:
    session_times = []
    sessions = soup.find_all("li", class_="session")

    for session in sessions:
        time_div = session.find("div", class_="session_time")
        if time_div:
            session_times.append(time_div.text.strip())

    return session_times


def extract_price(soup: BeautifulSoup) -> list[str]:
    price_list = []
    price_element = soup.find("h5", string="Preços")
    if not price_element:
        return price_list
    for sibling in price_element.find_next_siblings():
        if sibling.name in ["h3", "h4", "h5"]:
            break
        text = sibling.get_text(strip=True)
        price_list.extend(re.findall(r"\d+[.,]?\d*€", text))
    return price_list


def extract_age_rating(soup: BeautifulSoup) -> str:
    age_element = soup.find("h5", string="Classificação Etária")
    if age_element:
        span = age_element.find_next("span")
        age_text = span.get_text(strip=True) if span else "N/A"
        match = re.search(r"Maiores de (\d+)", age_text)
        return match.group(1) if match else age_text
    return "N/A"

def download_image(*args, **kwargs) -> str:
    """
    Compatível com duas assinaturas:
      1) download_image(img_url, title)
      2) download_image(session, img_url, title, domain)
    """
    import os
    import requests

    session = None
    domain = None

    if len(args) >= 4 and isinstance(args[0], requests.Session):
        session, img_url, title, domain = args[0], args[1], args[2], args[3]
    elif len(args) >= 2:
        img_url, title = args[0], args[1]
    else:
        return "N/A"

    if not img_url or img_url == "N/A":
        return "N/A"

    try:
        # domínio (se não vier, tenta inferir da URL)
        if not domain:
            try:
                domain = extract_domain(str(img_url))
            except Exception:
                domain = "misc"

        # garantir pasta
        dir_path = os.path.join(POSTERS_DIRECTORY, str(domain))
        os.makedirs(dir_path, exist_ok=True)

        title_fmt = "".join(e for e in str(title) if e.isalnum() or e in (" ", "-")).replace(" ", "_")
        filename = f"{title_fmt}.jpg"
        full_path = os.path.join(dir_path, filename)

        headers = get_random_headers()

        if session is not None:
            # usa sessão existente
            session.headers.update(headers)
            resp = session.get(img_url, stream=True, timeout=20)
        else:
            resp = requests.get(img_url, headers=headers, stream=True, timeout=20)

        if resp.status_code != 200:
            aviso(logger, "utils.imagem.falha_status", url=img_url, status=resp.status_code)
            return "N/A"

        with open(full_path, "wb") as f:
            for chunk in resp.iter_content(1024):
                if chunk:
                    f.write(chunk)

        return full_path

    except Exception as e:
        aviso(logger, "utils.imagem.falha_excepcao", titulo=str(title), erro=str(e))
        return "N/A"

def truncate_text_utf8(text: str, *, max_bytes: int = 2000, suffix: str = "…") -> str:
    if text is None:
        return ""

    s = str(text)
    b = s.encode("utf-8")
    if len(b) <= max_bytes:
        return s

    suf_b = suffix.encode("utf-8")
    budget = max_bytes - len(suf_b)
    if budget <= 0:
        # limite demasiado baixo; devolve o que couber do sufixo
        return suffix.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")

    cut = b[:budget].decode("utf-8", errors="ignore")
    return cut + suffix

# ──────────────────────────────────────────────────────────────────────────────
# Formatação de datas e horários (para Data Extenso / Horários)
# ──────────────────────────────────────────────────────────────────────────────

_WEEKDAY_MAP = {
    # EN abreviado (BOL)
    "mon": "seg", "tue": "ter", "wed": "qua", "thu": "qui", "fri": "sex", "sat": "sáb", "sun": "dom",
    # EN completo
    "monday": "seg", "tuesday": "ter", "wednesday": "qua", "thursday": "qui", "friday": "sex", "saturday": "sáb", "sunday": "dom",
    # PT abreviado
    "seg": "seg", "ter": "ter", "qua": "qua", "qui": "qui", "sex": "sex", "sab": "sáb", "sáb": "sáb", "dom": "dom",
    # PT completo (alguns scrapers podem gerar)
    "segunda": "seg", "segundas": "seg",
    "terça": "ter", "terca": "ter", "terças": "ter", "tercas": "ter",
    "quarta": "qua", "quartas": "qua",
    "quinta": "qui", "quintas": "qui",
    "sexta": "sex", "sextas": "sex",
    "sábado": "sáb", "sabado": "sáb", "sábados": "sáb", "sabados": "sáb",
    "domingo": "dom", "domingos": "dom",
}

_WEEKDAY_ORDER = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
_WEEKDAY_LABEL = {"seg": "Seg", "ter": "Ter", "qua": "Qua", "qui": "Qui", "sex": "Sex", "sáb": "Sáb", "dom": "Dom"}


def format_date_range(start_date: str | None, end_date: str | None) -> str:
    """
    Formata a propriedade 'Data Extenso' sem dependências (mantém ISO).
    Exemplos:
      - "2026-01-10" (se só houver uma data ou se forem iguais)
      - "2026-01-10 a 2026-01-12"
      - "N/A" (se não houver datas)
    """
    def _norm(x: str | None) -> str | None:
        if x is None:
            return None
        s = str(x).strip()
        if not s or s.upper() == "N/A":
            return None
        # se vier ISO com hora, corta
        if "T" in s:
            s = s.split("T", 1)[0].strip()
        return s or None

    s = _norm(start_date)
    e = _norm(end_date)

    if s and e:
        return s if s == e else f"{s} a {e}"
    if s:
        return s
    if e:
        return e
    return "N/A"


def _normalizar_hora(h: str) -> str:
    """
    Normaliza horas como:
      - '21h' -> '21:00'
      - '21h30' -> '21:30'
      - '21:30' -> '21:30'
    Se não reconhecer, devolve o original limpo.
    """
    s = (h or "").strip()
    if not s:
        return s

    m = re.match(r"^(\d{1,2})h(\d{2})?$", s, flags=re.IGNORECASE)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or "00")
        return f"{hh:02d}:{mm:02d}"

    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        return f"{hh:02d}:{mm:02d}"

    return s


def _hora_sort_key(h: str) -> tuple[int, int, str]:
    s = _normalizar_hora(h)
    m = re.match(r"^(\d{2}):(\d{2})$", s)
    if m:
        return (int(m.group(1)), int(m.group(2)), s)
    return (99, 99, s)


def format_session_times(schedule) -> str:
    """
    Aceita:
      - dict[str, list[str] | set[str]] (BOL: mon/tue..., Ticketline: seg/ter..., etc.)
      - string já formatada
    Devolve string estável, ex.:
      'Qui: 21:00; Sex: 21:00; Sáb: 16:00, 21:00'
    """
    if schedule is None:
        return "N/A"

    if isinstance(schedule, str):
        s = schedule.strip()
        return s if s else "N/A"

    if not isinstance(schedule, dict):
        # fallback conservador
        try:
            s = str(schedule).strip()
            return s if s else "N/A"
        except Exception:
            return "N/A"

    normalizado: dict[str, set[str]] = {k: set() for k in _WEEKDAY_ORDER}

    for raw_day, raw_times in schedule.items():
        day_key = (str(raw_day).strip().lower() if raw_day is not None else "")
        day = _WEEKDAY_MAP.get(day_key, None)
        if not day:
            continue

        if raw_times is None:
            continue

        if isinstance(raw_times, (set, list, tuple)):
            times_iter = raw_times
        else:
            times_iter = [raw_times]

        for t0 in times_iter:
            t1 = _normalizar_hora(str(t0))
            if t1:
                normalizado[day].add(t1)

    parts: list[str] = []
    for d in _WEEKDAY_ORDER:
        times = sorted(normalizado[d], key=_hora_sort_key)
        if times:
            parts.append(f"{_WEEKDAY_LABEL[d]}: {', '.join(times)}")

    return "; ".join(parts) if parts else "N/A"