from pathlib import Path

from teatroapp_uploader.selectors import all_critical_tokens


FIXTURES = {
    "part1": "html/teatro.app/4. Folha de Sala.htm",
    "part2": "html/teatro.app/5.Cartaz e fotos.htm",
    "part3": "html/teatro.app/6.Sessões.htm",
}


def _load(rel_path: str) -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / rel_path).read_text(encoding="utf-8", errors="ignore").lower()


def test_teatroapp_critical_tokens_still_present_in_fixtures():
    tokens = all_critical_tokens()
    missing: list[str] = []

    for part, fixture in FIXTURES.items():
        html = _load(fixture)
        for token in tokens.get(part, []):
            if token.lower() not in html:
                missing.append(f"{part}:{token}")

    assert not missing, f"Tokens críticos ausentes nos fixtures: {missing}"
