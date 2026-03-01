# -*- coding: utf-8 -*-
"""BOL -> .cache/teatroapp_sessions.json

Uso:
  py -m teatroapp_uploader.sessions_from_bol --event-url "https://www.bol.pt/..." --venue "Teatro Armando Cortez"

Notas:
- event-url: URL da página do evento na BOL (não precisa ser /Sessoes).
- venue: tem de ser EXACTO como existe no dropdown do teatro.app.
- ticket_url gravado por defeito: Link Sessões (purchase_url).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

from scrapers.ticket_platforms.BOL import bol_scraper

from .logging_ptpt import Logger
from .utils import ensure_parent_dir

logger = Logger()


def build_teatroapp_sessions_from_bol_event(*, event_url: str, venue: str) -> list[dict]:
    """Resolve purchase_url e devolve sessões no formato do teatroapp_uploader."""
    with requests.Session() as session:
        details = bol_scraper.get_event_details(session, event_url, known_titles=None)
        if not details:
            raise RuntimeError("BOL: não consegui obter detalhes do evento (get_event_details devolveu None).")

        purchase_url = (details.get("Link Sessões") or "").strip()
        if not purchase_url:
            raise RuntimeError("BOL: não encontrei 'Link Sessões' no detalhe do evento.")

        fallback_iso = (details.get("Data Início") or "").strip()
        fallback_iso = fallback_iso[:10] if fallback_iso else None

        sessoes = bol_scraper.get_sessoes_individuais_por_purchase_url(
            session,
            purchase_url,
            fallback_iso_date=fallback_iso,
        )

        if not sessoes:
            raise RuntimeError("BOL: não encontrei sessões individuais na página /Sessoes.")

        out: list[dict] = []
        for s in sessoes:
            out.append(
                {
                    "venue": venue,
                    "date": s["date"],
                    "hour": int(s["hour"]),
                    "minute": int(s["minute"]),
                    "ticket_url": purchase_url,
                }
            )

        return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="BOL -> .cache/teatroapp_sessions.json")
    p.add_argument("--event-url", required=True, help="URL do evento na BOL (não /Sessoes)")
    p.add_argument("--venue", required=True, help="Nome da sala EXACTO como existe no teatro.app")
    p.add_argument("--out", default=".cache/teatroapp_sessions.json", help="Caminho de saída")

    args = p.parse_args(argv)

    out_path = Path(args.out)
    ensure_parent_dir(out_path)

    data = build_teatroapp_sessions_from_bol_event(event_url=args.event_url, venue=args.venue)

    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("BOL: sessões gravadas em: %s (%d)", str(out_path), len(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())