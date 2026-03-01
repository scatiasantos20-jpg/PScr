from pathlib import Path

import pytest

pytest.importorskip("requests")
pytest.importorskip("bs4")
pytest.importorskip("selenium")

from scrapers.ticket_platforms.Ticketline.multi_page import parse_multi_event_urls_from_html
from scrapers.ticket_platforms.Ticketline.single_page import parse_single_page_from_html
from scrapers.ticket_platforms.Ticketline.sessions_calendar import parse_calendar_static_from_html


def _read(rel_path: str) -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / rel_path).read_text(encoding="utf-8", errors="ignore")


def test_parse_multi_event_urls_from_fixture():
    html = _read("html/ticketline/Lista.html")
    urls = parse_multi_event_urls_from_html(html)
    assert urls
    assert urls[0].startswith("https://ticketline.sapo.pt")


def test_parse_single_page_from_fixture():
    html = _read("html/ticketline/2. versão em lista datas.html")
    out = parse_single_page_from_html(html)
    assert out["title"]
    assert out["location"]


def test_parse_calendar_static_from_fixture():
    html = _read("html/ticketline/3. versão calendario.html")
    out = parse_calendar_static_from_html(html)
    assert out["title"]
    assert isinstance(out["session_dates"], list)
