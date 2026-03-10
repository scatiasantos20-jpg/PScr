from pathlib import Path

import pytest

bs4 = pytest.importorskip("bs4")
BeautifulSoup = bs4.BeautifulSoup
pytest.importorskip("requests")

from scrapers.ticket_platforms.BOL.bol_scraper import (
    _extract_jsonld_event,
    _extract_listing_event_urls,
    _normalizar_hora_bol,
)


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


def test_extract_listing_event_urls_uses_selector_fallbacks():
    soup = BeautifulSoup(
        """
        <html><body>
            <a class="nome" href="/Comprar/Bilhetes/111/teste-a">A</a>
            <div class="item-montra evento">
                <a class="botao info" href="/Comprar/Bilhetes/222/teste-b">B</a>
            </div>
            <a class="nome" href="https://www.bol.pt/Comprar/Bilhetes/111/teste-a">dup</a>
        </body></html>
        """,
        "html.parser",
    )

    urls = _extract_listing_event_urls(soup)
    assert urls == [
        "https://www.bol.pt/Comprar/Bilhetes/222/teste-b",
        "https://www.bol.pt/Comprar/Bilhetes/111/teste-a",
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("19h", "19:00"),
        ("19h30", "19:30"),
        ("19H30", "19:30"),
        ("19:30", "19:30"),
        ("", ""),
    ],
)
def test_normalizar_hora_bol(raw: str, expected: str):
    assert _normalizar_hora_bol(raw) == expected


def test_extract_listing_event_urls_supports_protocol_relative_href():
    soup = BeautifulSoup(
        """
        <html><body>
            <a class="nome" href="//www.bol.pt/Comprar/Bilhetes/333/teste-c">C</a>
        </body></html>
        """,
        "html.parser",
    )

    urls = _extract_listing_event_urls(soup)
    assert urls == ["https://www.bol.pt/Comprar/Bilhetes/333/teste-c"]


def test_extract_jsonld_event_works_when_script_has_text_node_not_string():
    soup = BeautifulSoup(
        """
        <html><body>
            <script type="application/ld+json">
              {"@context":"https://schema.org","@type":"Event","name":"Evento Teste"}
            </script>
        </body></html>
        """,
        "html.parser",
    )

    data = _extract_jsonld_event(soup)
    assert data is not None
    assert data.get("name") == "Evento Teste"
