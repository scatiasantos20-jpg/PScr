import pytest

pytest.importorskip("requests")
pytest.importorskip("bs4")

from scrapers.ticket_platforms.Imperdivel.imperdivel_scraper import (
    _extract_field,
    _normalize_labels,
    _parse_dates_list,
    _resolve_image_url,
)


def test_normalize_labels_handles_spaced_keys():
    raw = "D A T A: 14 de março de 2026\nL O C A L: Sala X"
    out = _normalize_labels(raw)
    assert "DATA:" in out
    assert "LOCAL:" in out


@pytest.mark.parametrize(
    ("raw", "expected_count"),
    [
        ("14 de março de 2026", 1),
        ("17 a 19 de julho de 2026", 3),
        ("26 de fevereiro e 2, 10, 18 e 26 de março de 2026", 5),
    ],
)
def test_parse_dates_list_supported_formats(raw: str, expected_count: int):
    out = _parse_dates_list(raw)
    assert len(out) == expected_count


def test_extract_field_reads_normalized_key():
    txt = "D U R A Ç Ã O: 70 min\nH O R A: 21h"
    assert _extract_field(txt, "DURAÇÃO") == "70 min"
    assert _extract_field(txt, "HORA") == "21h"


def test_resolve_image_url_handles_relative_src():
    got = _resolve_image_url("./2. Evento_files/cartaz.jpg", "https://imperdivel.pt/evento/abc/")
    assert got == "https://imperdivel.pt/evento/abc/2. Evento_files/cartaz.jpg"

def test_resolve_image_url_handles_protocol_relative():
    got = _resolve_image_url("//cdn.exemplo.com/cartaz.jpg", "https://imperdivel.pt/evento/abc/")
    assert got == "https://cdn.exemplo.com/cartaz.jpg"
