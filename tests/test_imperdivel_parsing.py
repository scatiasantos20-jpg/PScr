import pytest

pytest.importorskip("requests")
pytest.importorskip("bs4")

from scrapers.ticket_platforms.Imperdivel.imperdivel_scraper import (
    _extract_field,
    _normalize_labels,
    _parse_dates_list,
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
