from pathlib import Path

import pytest

bs4 = pytest.importorskip("bs4")
BeautifulSoup = bs4.BeautifulSoup

from scrapers.ticket_platforms.BOL.bol_scraper import _extract_jsonld_event, _extract_listing_event_urls


def _load_soup(rel_path: str) -> BeautifulSoup:
    root = Path(__file__).resolve().parents[1]
    html = (root / rel_path).read_text(encoding="utf-8", errors="ignore")
    return BeautifulSoup(html, "html.parser")


def test_extract_listing_event_urls_from_fixture():
    soup = _load_soup("html/bol/1. Lista.htm")
    urls = _extract_listing_event_urls(soup)

    assert urls
    assert urls[0].startswith("https://www.bol.pt/Comprar/Bilhetes/")
    assert len(urls) == len(set(urls))


def test_extract_jsonld_event_prefers_complete_event_fixture():
    soup = _load_soup("html/bol/2. detalhe do evento.htm")
    data = _extract_jsonld_event(soup)

    assert data is not None
    assert data.get("@type") == "Event"
    assert data.get("name")
