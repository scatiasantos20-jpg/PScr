from pathlib import Path

import pytest

pytest.importorskip("requests")
pytest.importorskip("bs4")

from scrapers.common.utils_scrapper import detectar_tipo_pagina


FIXTURES = [
    ("html/ticketline/Lista.html", "multi"),
    ("html/ticketline/2. versão em lista datas.html", "single"),
    ("html/ticketline/2. versão lista do mesmo evento.html", "multi"),
    ("html/ticketline/3. versão calendario.html", "calendar"),
]


def _read(rel_path: str) -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / rel_path).read_text(encoding="utf-8", errors="ignore")


@pytest.mark.parametrize(("fixture", "expected"), FIXTURES)
def test_detectar_tipo_pagina_ticketline_fixtures(fixture: str, expected: str):
    html = _read(fixture)
    got = detectar_tipo_pagina(html)
    assert got == expected
