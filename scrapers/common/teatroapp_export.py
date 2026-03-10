# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scrapers.common.logging_ptpt import configurar_logger, info, aviso, erro  # type: ignore

LOGGER = configurar_logger("teatroapp.export")

# ─────────────────────────────────────────────────────────────────────────────
# ENV / Paths
# ─────────────────────────────────────────────────────────────────────────────

CACHE_DIR = Path(os.getenv("CACHE_DIR", ".cache")).expanduser()
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEBUG_DIR = CACHE_DIR / "teatroapp_debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

BATCH_DIR = CACHE_DIR / "teatroapp_batch"
BATCH_DIR.mkdir(parents=True, exist_ok=True)

BATCH_JSON = CACHE_DIR / "teatroapp_batch.json"
BATCH_RESULTS_JSON = CACHE_DIR / "teatroapp_batch_results.json"

PAYLOAD_JSON = CACHE_DIR / "teatroapp_payload.json"
SESSIONS_JSON = CACHE_DIR / "teatroapp_sessions.json"
OVERRIDE_ENV = CACHE_DIR / "teatroapp_override.env"
OVERRIDES_JSON = CACHE_DIR / "teatroapp_overrides.json"

BASE_DIRECTORY = Path(os.getenv("BASE_DIRECTORY", ".")).expanduser()
POSTERS_SUBDIR = os.getenv("POSTERS_SUBDIR", "Cartazes").strip() or "Cartazes"
POSTERS_DIR = BASE_DIRECTORY / POSTERS_SUBDIR

DEFAULT_GENRE = os.getenv("TEATROAPP_GENRE", "other").strip() or "other"
DEFAULT_SYNOPSIS = os.getenv("TEATROAPP_SYNOPSIS", "Sem sinopse.").strip() or "Sem sinopse."
DEFAULT_AGE = os.getenv("TEATROAPP_AGE_RATING", "12").strip() or "12"
DEFAULT_DURATION = os.getenv("TEATROAPP_DURATION", "90").strip() or "90"
DEFAULT_RELEASE = os.getenv("TEATROAPP_RELEASE_DATE", "").strip()
DEFAULT_COMPANY = os.getenv("TEATROAPP_COMPANY", "").strip()
DEFAULT_DIRECTOR = os.getenv("TEATROAPP_DIRECTOR", "").strip()
DEFAULT_PLAYWRITER = os.getenv("TEATROAPP_PLAYWRITER", "").strip()
DEFAULT_VENUE = os.getenv("TEATROAPP_VENUE_DEFAULT", "").strip()

REQUESTS_TIMEOUT = int(os.getenv("REQUESTS_TIMEOUT", "30"))
IMAGE_TIMEOUT = int(os.getenv("IMAGE_TIMEOUT", "30"))


# ─────────────────────────────────────────────────────────────────────────────
# Utils
# ─────────────────────────────────────────────────────────────────────────────

def _clean(s: Any) -> str:
    return (str(s) if s is not None else "").strip()


def _first(*vals: Any, default: str = "") -> str:
    for v in vals:
        s = _clean(v)
        if s and s.upper() != "N/A":
            return s
    return default


def _key_norm(s: str) -> str:
    """Normaliza keys para lookup robusto (acentos/casing/pontuação leve)."""
    s = s or ""
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    return s


def _row_get(row: Dict[str, Any], *candidates: str, default: str = "") -> str:
    """Obtém valor de um row dict tolerando acentos/casing e variações de nome."""
    # 1) match direto
    for c in candidates:
        if c in row:
            s = _clean(row.get(c))
            if s and s.upper() != "N/A":
                return s

    # 2) match por normalização
    wanted = {_key_norm(c) for c in candidates}
    for k, v in row.items():
        if _key_norm(str(k)) in wanted:
            s = _clean(v)
            if s and s.upper() != "N/A":
                return s

    return default


def _slug_filename(name: str) -> str:
    s = _clean(name).lower()
    s = re.sub(r"[^\w\- ]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s or "item"


def _parse_iso(d: str) -> Optional[date]:
    s = _clean(d)
    if not s or s.upper() == "N/A":
        return None
    if "T" in s:
        s = s.split("T", 1)[0].strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_minutes(duration_str: str) -> Optional[int]:
    s = _clean(duration_str)
    m = re.search(r"(\d+)", s)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _domain_from_url(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower().replace("www.", "")
        return netloc or "misc"
    except Exception:
        return "misc"


def _dump_debug_html(prefix: str, html: str) -> Path:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = DEBUG_DIR / f"{prefix}_{ts}.html"
    out.write_text(html or "", encoding="utf-8", errors="ignore")
    return out


def _env_quote(v: str) -> str:
    """
    Escreve valores para ficheiro .env de forma segura em Windows:
    - normaliza barras para '/' (evita escapes \\U)
    - colapsa \r/\n/\t (um par chave=valor por linha)
    - coloca aspas se houver espaços / caracteres sensíveis
    """
    v = (v or "").replace("\\", "/")
    v = v.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    v = re.sub(r"\s{2,}", " ", v).strip()
    if not v:
        return v
    if any(ch in v for ch in (" ", "#", "=", '"', "'")):
        v = v.replace('"', '\\"')
        return f"\"{v}\""
    return v


def _norm_txt(s: str) -> str:
    s = s or ""
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _inject_separators(s: str) -> str:
    labels = [
        r"encena[çc][aã]o",
        r"dire[çc][aã]o(?:\s+art[ií]stica)?",
        r"argumento",
        r"texto",
        r"dramaturgia",
        r"autor(?:ia)?",
        r"cria[çc][aã]o",
        r"produ[çc][aã]o",
        r"co-?produ[çc][aã]o",
        r"companhia",
        r"grupo",
    ]
    out = s or ""
    for lab in labels:
        out = re.sub(rf"(?i)\b({lab})\b\s*[:\-]", r"\n\1:", out)
    return out


def _split_chunks(s: str) -> list[str]:
    s = (s or "").replace("\r", "\n")
    s = re.sub(r"[•·]", "\n", s)
    s = _inject_separators(s)
    parts = re.split(r"[\n;|]+", s)
    return [p.strip() for p in parts if p and p.strip()]


def _pick_value(lines: list[str], label_regexes: list[str]) -> str:
    for ln in lines:
        if ":" not in ln and "-" not in ln:
            continue
        if ":" in ln:
            k, v = ln.split(":", 1)
        else:
            k, v = ln.split("-", 1)
        k_n = _norm_txt(k)
        v = v.strip()
        for lab in label_regexes:
            if re.search(rf"^{lab}$", k_n, flags=re.I):
                return v.strip(" -:;|").strip()
    return ""


def _infer_details_from_credits(credits: str, synopsis: str, *, company0: str, director0: str, playwright0: str) -> tuple[str, str, str]:
    blob = (credits or "") + "\n" + (synopsis or "")
    lines = _split_chunks(blob)

    director = director0.strip() or _pick_value(lines, [r"encenacao", r"direcao artistica", r"direcao"])
    playwright = playwright0.strip() or _pick_value(lines, [r"argumento", r"texto", r"dramaturgia", r"autor", r"autoria"])
    company = company0.strip() or _pick_value(lines, [r"companhia", r"grupo", r"producao", r"co-producao", r"coproducao"])

    return company.strip(), director.strip(), playwright.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Posters
# ─────────────────────────────────────────────────────────────────────────────

def _copy_poster(src: Path, *, out_base: Path) -> Path:
    out_path = out_base.with_suffix(src.suffix.lower())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(src.read_bytes())
    return out_path


def _find_existing_poster(out_base: Path) -> Optional[Path]:
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = out_base.with_suffix(ext)
        try:
            if p.exists() and p.stat().st_size > 0:
                return p
        except Exception:
            continue
    return None


def _download_poster(img_url: str, *, out_base: Path) -> Optional[Path]:
    img_url = _clean(img_url)
    if not img_url:
        return None

    try:
        r = requests.get(img_url, timeout=IMAGE_TIMEOUT)
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        ext = ".jpg"
        if "png" in ctype:
            ext = ".png"
        elif "webp" in ctype:
            ext = ".webp"
        elif "jpeg" in ctype or "jpg" in ctype:
            ext = ".jpg"

        out_path = out_base.with_suffix(ext)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(r.content)
        return out_path
    except Exception:
        return None


def _find_downloaded_poster(title: str, event_url: str) -> Optional[Path]:
    title = _clean(title)
    event_url = _clean(event_url)
    if not title and not event_url:
        return None

    domain = _domain_from_url(event_url)
    folder = POSTERS_DIR / domain
    if not folder.exists():
        return None

    slug = _slug_filename(title)

    for ext in ("jpg", "jpeg", "png", "webp"):
        for p in folder.glob(f"*.{ext}"):
            if slug and slug in p.stem.lower():
                return p

    if (os.getenv("TEATROAPP_POSTER_FALLBACK_FIRST", "0") or "").strip().lower() in ("1", "true", "sim", "yes", "y"):
        for ext in ("jpg", "jpeg", "png", "webp"):
            files = list(folder.glob(f"*.{ext}"))
            if files:
                return files[0]

    return None


# ─────────────────────────────────────────────────────────────────────────────
# BOL Sessions (exact)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_html(url: str) -> str:
    r = requests.get(url, timeout=REQUESTS_TIMEOUT)
    r.raise_for_status()
    return r.text


def _parse_bol_sessions_page(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, Any]] = []

    for a in soup.select("a[href*='Comprar']"):
        href = (a.get("href") or "").strip()
        txt = _clean(a.get_text(" ", strip=True))
        if not href or not txt:
            continue
        m = re.search(r"(\d{2})/(\d{2})/(\d{4}).*?(\d{2}):(\d{2})", txt)
        if not m:
            continue
        dd, mm, yyyy, HH, MM = m.groups()
        try:
            dt = datetime(int(yyyy), int(mm), int(dd), int(HH), int(MM))
        except Exception:
            continue

        out.append(
            {
                "datetime": dt.isoformat(timespec="minutes"),
                "ticket_url": href if href.startswith("http") else f"https://www.bol.pt{href}",
            }
        )

    seen = set()
    dedup: List[Dict[str, Any]] = []
    for s in out:
        k = (s.get("datetime"), s.get("ticket_url"))
        if k in seen:
            continue
        seen.add(k)
        dedup.append(s)

    return dedup


def _fetch_sessions_exact(
    sessions_url: str,
    *,
    venue: str,
    ticket_url: str,
    fallback_start_date: Optional[date],
    debug_prefix: str,
) -> List[Dict[str, Any]]:
    html = _fetch_html(sessions_url)
    if "html" in (os.getenv("TEATROAPP_DEBUG_BOL", "0") or "").lower():
        _dump_debug_html(debug_prefix, html)

    raw = _parse_bol_sessions_page(html)
    out: List[Dict[str, Any]] = []
    for item in raw:
        dt = item.get("datetime")
        if not dt:
            continue
        out.append(
            {
                "datetime": dt,
                "venue": venue,
                "ticket_url": item.get("ticket_url") or ticket_url,
            }
        )

    if not out and fallback_start_date:
        pass

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Generic sessions expansion from "Horários" (date range + weekdays)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_horarios(h: str) -> List[str]:
    h = _clean(h)
    if not h or h.upper() == "N/A":
        return []
    parts = re.split(r"\s*\|\s*|\s{2,}|\s*;\s*", h)
    return [p.strip() for p in parts if p and p.strip()]


def _weekday_from_pt(tok: str) -> Optional[int]:
    tok_n = _norm_txt(tok)
    map_pt = {
        "seg": 0,
        "segunda": 0,
        "ter": 1,
        "terça": 1,
        "terca": 1,
        "qua": 2,
        "quarta": 2,
        "qui": 3,
        "quinta": 3,
        "sex": 4,
        "sexta": 4,
        "sab": 5,
        "sábado": 5,
        "sabado": 5,
        "dom": 6,
        "domingo": 6,
    }
    for k, v in map_pt.items():
        if tok_n.startswith(k):
            return v
    return None


def _time_from_token(tok: str) -> Optional[Tuple[int, int]]:
    m = re.search(r"(\d{1,2})[:h](\d{2})", tok)
    if not m:
        return None
    try:
        return int(m.group(1)), int(m.group(2))
    except Exception:
        return None


def _expand_sessions_from_horarios(
    *,
    horarios: str,
    date_start: date,
    date_end: date,
    venue: str,
    ticket_url: str,
) -> List[Dict[str, Any]]:
    tokens = _parse_horarios(horarios)
    if not tokens:
        return []

    rules: List[Tuple[int, Tuple[int, int]]] = []
    for tok in tokens:
        wd = _weekday_from_pt(tok)
        tm = _time_from_token(tok)
        if wd is None or tm is None:
            continue
        rules.append((wd, tm))

    if not rules:
        return []

    out: List[Dict[str, Any]] = []
    d = date_start
    while d <= date_end:
        for wd, (HH, MM) in rules:
            if d.weekday() == wd:
                dt = datetime(d.year, d.month, d.day, HH, MM)
                out.append(
                    {
                        "datetime": dt.isoformat(timespec="minutes"),
                        "venue": venue,
                        "ticket_url": ticket_url,
                    }
                )
        d += timedelta(days=1)

    out = sorted({(x["datetime"], x["venue"], x["ticket_url"]): x for x in out}.values(), key=lambda x: x["datetime"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null")
    except Exception:
        return None


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_env(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_overrides_template() -> None:
    if OVERRIDES_JSON.exists():
        return
    template = {
        "global": {
            "company": DEFAULT_COMPANY,
            "director": DEFAULT_DIRECTOR,
            "playwriter": DEFAULT_PLAYWRITER,
            "venue_default": DEFAULT_VENUE,
        },
        "items": {},
    }
    try:
        OVERRIDES_JSON.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _coerce_genre(g: str) -> str:
    g = _clean(g).lower()
    allowed = {"drama", "comedy", "musical", "dance", "opera", "circus", "kids", "other"}
    return g if g in allowed else DEFAULT_GENRE


def _coerce_age(a: str) -> str:
    a = _clean(a)
    m = re.search(r"(\d+)", a)
    if m:
        return m.group(1)
    return DEFAULT_AGE


def _coerce_release(d: str) -> str:
    d = _clean(d)
    if not d:
        return DEFAULT_RELEASE
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return d
    return DEFAULT_RELEASE


def _extract_details_fallback(row: Dict[str, Any]) -> Tuple[str, str, str]:
    synopsis = _row_get(row, "Sinopse", "Synopsis", "Descrição", "Descricao", "Description", default="")
    credits = _row_get(row, "Ficha técnica", "Creditos", "Créditos", "Credits", default="")

    company0 = _row_get(row, "Companhia", "Company", default=DEFAULT_COMPANY)
    director0 = _row_get(row, "Encenação", "Direção", "Director", default=DEFAULT_DIRECTOR)
    playwright0 = _row_get(row, "Argumento", "Texto", "Autor", "Playwright", default=DEFAULT_PLAYWRITER)

    company, director, playwright = _infer_details_from_credits(credits, synopsis, company0=company0, director0=director0, playwright0=playwright0)

    company = company or company0
    director = director or director0
    playwright = playwright or playwright0

    return company, director, playwright


def _export_one_row(row: Dict[str, Any], *, idx: int) -> Dict[str, Any]:
    title = _row_get(
        row,
        "Título",
        "Titulo",
        "Title",
        "title",
        "Nome",
        "name",
        "Nome da peça",
        "Nome da peca",
        "Peça",
        "Peca",
        default="(Sem título)",
    )

    event_url = _row_get(row, "URL", "Url", "Link", "Event URL", "event_url", default="")
    sessions_url = _row_get(
        row,
        "Sessoes URL",
        "Sessões URL",
        "Sessions URL",
        "Link Sessões",
        "Link Sessoes",
        "sessions_url",
        default="",
    )
    ticket_url = _row_get(row, "Bilhetes", "Tickets", "Ticket URL", "ticket_url", default="") or event_url
    img_url = _row_get(row, "Imagem", "Cartaz", "Image", "Poster", "poster_url", "image_url", default="")

    # fallback BOL: se não vier sessions_url, deriva a partir do event_url
    if event_url and not sessions_url:
        try:
            dom = _domain_from_url(event_url)
            if "bol.pt" in dom and "/Bilhetes/" in event_url:
                sessions_url = event_url.rstrip("/") + "/Sessoes"
        except Exception:
            pass

    genre = _coerce_genre(_row_get(row, "Género", "Genero", "Genre", default=DEFAULT_GENRE))
    synopsis = _row_get(
        row,
        "Sinopse",
        "Synopsis",
        "Descrição",
        "Descricao",
        "Description",
        default=DEFAULT_SYNOPSIS,
    )

    date_start = _parse_iso(_row_get(row, "Data início", "Data Inicio", "Start Date", default=""))
    date_end = _parse_iso(_row_get(row, "Data fim", "Data Fim", "End Date", default=""))

    horarios = _row_get(row, "Horários", "Horarios", "Schedule", default="")
    age = _coerce_age(_row_get(row, "Idade", "Age", default=DEFAULT_AGE))

    duration = _row_get(row, "Duração", "Duracao", "Duration", default=DEFAULT_DURATION)
    duration_min = _parse_minutes(duration) or _parse_minutes(DEFAULT_DURATION) or 90

    release_date = _coerce_release(_row_get(row, "Estreia", "Release", "Release Date", default=DEFAULT_RELEASE))

    venue = _row_get(row, "Sala", "Local", default=DEFAULT_VENUE)

    slug = _slug_filename(title)
    prefix = f"{idx:03d}_{slug}"

    payload_path = (BATCH_DIR / f"payload_{prefix}.json").resolve()
    sessions_path = (BATCH_DIR / f"sessions_{prefix}.json").resolve()
    override_env_path = (BATCH_DIR / f"override_{prefix}.env").resolve()
    poster_out_base = (BATCH_DIR / f"poster_{prefix}").resolve()

    reuse = (os.getenv("TEATROAPP_EXPORT_REUSE", "0") or "").strip().lower() in ("1", "true", "sim", "yes", "y")
    if reuse and payload_path.exists() and sessions_path.exists() and override_env_path.exists():
        try:
            sessions_cached = json.loads(sessions_path.read_text(encoding="utf-8") or "[]")
            if isinstance(sessions_cached, list):
                payload_cached = json.loads(payload_path.read_text(encoding="utf-8") or "{}")
                title_cached = (payload_cached.get("title") or title).strip() or title
                return {
                    "idx": idx,
                    "title": title_cached,
                    "payload_path": str(payload_path),
                    "sessions_path": str(sessions_path),
                    "override_env": str(override_env_path),
                    "event_url": event_url,
                    "sessions_url": sessions_url,
                    "n_sessions": len(sessions_cached),
                }
        except Exception:
            pass

    sessions: List[Dict[str, Any]] = []
    prebuilt = (
        row.get("Teatroapp Sessions")
        or row.get("Sessões Teatroapp")
        or row.get("Sessions Teatroapp")
        or row.get("teatroapp_sessions")
    )
    if isinstance(prebuilt, str):
        raw = prebuilt.strip()
        if raw.startswith("[") and raw.endswith("]"):
            try:
                prebuilt = json.loads(raw)
            except Exception:
                prebuilt = None
    if isinstance(prebuilt, list) and prebuilt:
        sessions = prebuilt

    poster_path: Optional[Path] = _find_existing_poster(poster_out_base)
    if not poster_path:
        try:
            poster_src = _find_downloaded_poster(title, event_url) if event_url else None
            if poster_src and poster_src.exists():
                poster_path = _copy_poster(poster_src, out_base=poster_out_base)
            else:
                poster_path = _download_poster(img_url, out_base=poster_out_base)
        except Exception as e:
            erro(LOGGER, "utils.imagem.falha_excepcao", cache_key=f"teatroapp:poster:{idx}", titulo=title, erro=str(e))

    if not sessions and sessions_url and venue and ticket_url:
        try:
            domain = _domain_from_url(sessions_url or event_url)
            if "bol.pt" in domain or domain.startswith("bol.") or "bol" == domain.split(".")[0]:
                debug_prefix = f"bol_sessoes_{prefix}"
                sessions = _fetch_sessions_exact(
                    sessions_url,
                    venue=venue,
                    ticket_url=ticket_url,
                    fallback_start_date=date_start,
                    debug_prefix=debug_prefix,
                )
        except Exception as e:
            erro(LOGGER, "bol.warn.horarios_erro", e, cache_key=f"teatroapp:sessoes:{idx}", url=sessions_url)

    if not sessions:
        if date_start and date_end and horarios and venue and ticket_url:
            sessions = _expand_sessions_from_horarios(
                horarios=horarios,
                date_start=date_start,
                date_end=date_end,
                venue=venue,
                ticket_url=ticket_url,
            )

    company, director, playwright = _extract_details_fallback(row)

    payload: Dict[str, Any] = {
        "title": title,
        "details": {
            "company": company or DEFAULT_COMPANY,
            "director": director or DEFAULT_DIRECTOR,
            "playwriter": playwright or DEFAULT_PLAYWRITER,
            "synopsis": synopsis or DEFAULT_SYNOPSIS,
            "genre": genre,
            "age_rating": age,
            "duration_minutes": duration_min,
            "release_date": release_date,
            "venue": venue,
            "ticket_url": ticket_url,
            "event_url": event_url,
        },
        "media": {
            "poster_path": str(poster_path) if poster_path else "",
            "image_url": img_url,
        },
        "sources": {
            "platform": _row_get(row, "Plataforma", "Platform", default=_domain_from_url(event_url)),
            "sessions_url": sessions_url,
        },
    }

    _write_json(payload_path, payload)
    _write_json(sessions_path, sessions)

    lines = [
        f"TEATROAPP_TITLE={_env_quote(title)}",
        f"TEATROAPP_COMPANY={_env_quote(payload['details']['company'])}",
        f"TEATROAPP_DIRECTOR={_env_quote(payload['details']['director'])}",
        f"TEATROAPP_PLAYWRITER={_env_quote(payload['details']['playwriter'])}",
        f"TEATROAPP_SYNOPSIS={_env_quote(payload['details']['synopsis'])}",
        f"TEATROAPP_GENRE={_env_quote(payload['details']['genre'])}",
        f"TEATROAPP_AGE_RATING={_env_quote(payload['details']['age_rating'])}",
        f"TEATROAPP_DURATION={_env_quote(str(payload['details']['duration_minutes']))}",
        f"TEATROAPP_RELEASE_DATE={_env_quote(payload['details']['release_date'])}",
        f"TEATROAPP_VENUE={_env_quote(payload['details']['venue'])}",
        f"TEATROAPP_TICKET_URL={_env_quote(payload['details']['ticket_url'])}",
        f"TEATROAPP_EVENT_URL={_env_quote(payload['details']['event_url'])}",
        f"TEATROAPP_POSTER_PATH={_env_quote(payload['media']['poster_path'])}",
        f"TEATROAPP_PAYLOAD_JSON={_env_quote(str(payload_path))}",
        f"TEATROAPP_SESSIONS_JSON={_env_quote(str(sessions_path))}",
    ]

    _write_env(override_env_path, lines)

    return {
        "idx": idx,
        "title": title,
        "payload_path": str(payload_path),
        "sessions_path": str(sessions_path),
        "override_env": str(override_env_path),
        "event_url": event_url,
        "sessions_url": sessions_url,
        "n_sessions": len(sessions),
    }


def export_teatroapp_batch(
    items: List[Dict[str, Any]],
    *,
    out_path: Path = BATCH_JSON,
) -> List[Dict[str, Any]]:
    info(LOGGER, "teatroapp.export.inicio")

    batch: List[Dict[str, Any]] = []
    for i, row in enumerate(items, start=1):
        try:
            batch.append(_export_one_row(row, idx=i))
        except Exception as e:
            erro(LOGGER, "runner.sync_registo_falhou", e)

    if not batch:
        raise RuntimeError("export: não consegui exportar nenhum espectáculo (batch vazio).")

    _write_json(out_path, batch)
    info(LOGGER, "teatroapp.export.ok", total=len(batch), ficheiro=str(out_path))
    return batch


def export_teatroapp_from_df(df) -> Dict[str, Any]:
    """Exporta um DataFrame/lista normalizado(a) de qualquer plataforma para batch do Teatro.app."""
    try:
        rows = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)
    except Exception:
        rows = list(df)

    if not rows:
        raise RuntimeError("export: DF vazio; nada para exportar.")

    _write_overrides_template()

    batch: List[Dict[str, Any]] = []
    falhas: List[Dict[str, Any]] = []

    for idx, row in enumerate(rows, start=1):
        try:
            item = _export_one_row(row, idx=idx)
            batch.append(item)
            LOGGER.info("teatro.app export: [%d/%d] preparado: %s (sessões=%d)", idx, len(rows), item["title"], item["n_sessions"])
        except Exception as e:
            falhas.append({"idx": idx, "erro": str(e)})
            erro(LOGGER, "runner.sync_registo_falhou", e, cache_key=f"teatroapp:export:item:{idx}", origem="teatro.app export")

    if not batch:
        raise RuntimeError("export: não consegui exportar nenhum espectáculo (batch vazio).")

    BATCH_JSON.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info("teatro.app export: batch gravado em %s (itens=%d)", str(BATCH_JSON), len(batch))

    last = batch[-1]
    try:
        PAYLOAD_JSON.write_text(Path(last["payload_path"]).read_text(encoding="utf-8"), encoding="utf-8")
        SESSIONS_JSON.write_text(Path(last["sessions_path"]).read_text(encoding="utf-8"), encoding="utf-8")
        OVERRIDE_ENV.write_text(Path(last["override_env"]).read_text(encoding="utf-8"), encoding="utf-8")
        try:
            payload = json.loads(PAYLOAD_JSON.read_text(encoding="utf-8") or "{}")
            pp = ((payload.get("media") or {}).get("poster_path") or "").strip()
            if pp:
                psrc = Path(pp)
                if psrc.exists():
                    dst = (CACHE_DIR / "poster").with_suffix(psrc.suffix.lower())
                    dst.write_bytes(psrc.read_bytes())
        except Exception:
            pass
    except Exception:
        pass

    return {"batch_count": len(batch), "batch_path": str(BATCH_JSON), "failures": falhas}


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    src_path = Path(os.getenv("TEATROAPP_SOURCE_JSON", ""))
    if not src_path.exists():
        raise SystemExit("Define TEATROAPP_SOURCE_JSON com o JSON da plataforma (scraper cache).")

    items = _load_json(src_path)
    if not isinstance(items, list):
        raise SystemExit("Input JSON inválido: esperado lista de eventos.")

    export_teatroapp_batch(items)


# Compatibilidade retroativa
export_teatroapp_from_bol_df = export_teatroapp_from_df

if __name__ == "__main__":
    main()
