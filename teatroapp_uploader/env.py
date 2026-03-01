# -*- coding: utf-8 -*-
"""Leitura de .env e modelos."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # pasta raiz do projeto
load_dotenv(PROJECT_ROOT / ".env")

slow_mo_ms: int = int(os.getenv("SLOW_MO_MS", "0") or "0")

def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name, "")
    if v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "sim", "on")


def env_float(name: str, default: float) -> float:
    v = os.getenv(name, "")
    if v == "":
        return default
    try:
        return float(v.replace(",", "."))
    except Exception:
        return default


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_int(name: str, default: Optional[int] = None) -> Optional[int]:
    v = os.getenv(name, "").strip()
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def require_env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"variável obrigatória em .env em falta: {name}")
    return v


def parse_paths_list(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    parts = re.split(r"[;,]\s*", raw)
    return [p.strip().strip('"').strip("'") for p in parts if p.strip()]


@dataclass
class Session:
    venue: str
    date: str          # YYYY-MM-DD
    hour: int          # 0-23
    minute: int        # 0-59
    ticket_url: str = ""


@dataclass
class Config:
    base_url: str
    headless: bool
    dryrun: bool
    cookies_path: Path
    delay_min: float
    delay_max: float

    email: str
    password: str

    title: str
    exists_json: Path
    sessions_json: Path

    # Parte 1
    genre: str
    synopsis: str
    age_rating: Optional[int]
    duration: Optional[int]
    release_date: str
    company: str
    director: str
    playwriter: str

    # Parte 2
    poster_path: Path
    gallery_paths: list[Path]


def load_config() -> Config:
    load_dotenv()

    base_url = env_str("TEATROAPP_BASE_URL", "https://teatro.app").rstrip("/")
    headless = env_bool("TEATROAPP_HEADLESS", False)
    dryrun = env_bool("TEATROAPP_DRYRUN", False)

    cookies_path = Path(env_str("TEATROAPP_COOKIES", ".cache/teatroapp_cookies.json"))
    delay_min = env_float("TEATROAPP_DELAY_MIN", 0.5)
    delay_max = env_float("TEATROAPP_DELAY_MAX", 1.5)

    email = require_env("TEATROAPP_EMAIL")
    password = require_env("TEATROAPP_PASSWORD")
    title = require_env("TEATROAPP_TITLE")

    exists_json = Path(env_str("TEATROAPP_EXISTS_JSON", ".cache/teatroapp_exists.json"))
    sessions_json = Path(env_str("TEATROAPP_SESSIONS_JSON", ".cache/teatroapp_sessions.json"))

    genre = env_str("TEATROAPP_GENRE", "other").lower() or "other"
    synopsis = env_str("TEATROAPP_SYNOPSIS", "")
    age_rating = env_int("TEATROAPP_AGE_RATING", None)
    duration = env_int("TEATROAPP_DURATION", None)
    release_date = env_str("TEATROAPP_RELEASE_DATE", "")
    company = env_str("TEATROAPP_COMPANY", "")
    director = env_str("TEATROAPP_DIRECTOR", "")
    playwriter = env_str("TEATROAPP_PLAYWRITER", "")

    poster_path = Path(require_env("TEATROAPP_POSTER_PATH"))
    gallery_paths = [Path(p) for p in parse_paths_list(env_str("TEATROAPP_GALLERY_PATHS", ""))]

    return Config(
        base_url=base_url,
        headless=headless,
        dryrun=dryrun,
        cookies_path=cookies_path,
        delay_min=delay_min,
        delay_max=delay_max,
        email=email,
        password=password,
        title=title,
        exists_json=exists_json,
        sessions_json=sessions_json,
        genre=genre,
        synopsis=synopsis,
        age_rating=age_rating,
        duration=duration,
        release_date=release_date,
        company=company,
        director=director,
        playwriter=playwriter,
        poster_path=poster_path,
        gallery_paths=gallery_paths,
    )
