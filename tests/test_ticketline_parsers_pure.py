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


def test_parse_multi_event_urls_accepts_https_itemtype_and_absolute_urls():
    html = """
    <ul class="events_list">
      <li itemtype="https://schema.org/Event"><a href="https://www.ticketline.pt/evento/abc">A</a></li>
      <li itemtype="http://schema.org/Event"><a href="/evento/def">B</a></li>
    </ul>
    """
    urls = parse_multi_event_urls_from_html(html)
    assert urls == [
        "https://www.ticketline.pt/evento/abc",
        "https://ticketline.sapo.pt/evento/def",
    ]


def test_parse_single_page_supports_date_only_with_time_element():
    html = """
    <html><body>
      <h2 class="title">Evento X</h2>
      <div id="sessoes">
        <ul class="sessions_list">
          <li itemprop="Event">
            <div class="date" content="2026-04-10">
              <p class="time">21:30</p>
            </div>
          </li>
        </ul>
      </div>
    </body></html>
    """
    out = parse_single_page_from_html(html)
    assert len(out["session_dates"]) == 1
    assert out["session_dates"][0].strftime("%Y-%m-%d %H:%M") == "2026-04-10 21:30"


def test_parse_single_page_synopsis_fallback_to_itemprop_description():
    html = """
    <html><body>
      <h2 class="title">Evento Y</h2>
      <div itemprop="description">Uma sinopse detalhada do evento.</div>
      <div id="sessoes"><ul class="sessions_list"></ul></div>
    </body></html>
    """
    out = parse_single_page_from_html(html)
    assert out["synopsis"] == "Uma sinopse detalhada do evento."
