from scrapers.common.teatroapp_fields import (
    attach_teatroapp_fields,
    normalize_teatroapp_sessions,
    normalize_ticket_url,
    ensure_teatroapp_fields_dataframe,
)


def test_normalize_ticket_url_uses_fallback():
    assert normalize_ticket_url("", "https://x.pt/e") == "https://x.pt/e"


def test_normalize_teatroapp_sessions_filters_invalid_items():
    sessions = [
        {"venue": "A", "date": "2026-03-04", "hour": 21, "minute": 0, "ticket_url": "https://x"},
        {"venue": "B", "date": "2026-99-04", "hour": 21, "minute": 0, "ticket_url": "https://x"},
        {"venue": "C", "date": "2026-03-04", "hour": 99, "minute": 0, "ticket_url": "https://x"},
        {"venue": "D"},
    ]

    out = normalize_teatroapp_sessions(sessions)
    assert len(out) == 1
    assert out[0]["venue"] == "A"


def test_attach_teatroapp_fields_sets_defaults():
    ev = {"Link da Peça": "https://evento"}
    attach_teatroapp_fields(ev, ticket_url="", sessions=None)

    assert ev["Link Sessões"] == "https://evento"
    assert ev["Teatroapp Sessions"] == []


def test_ensure_teatroapp_fields_dataframe_adds_columns():
    pd = __import__("pytest").importorskip("pandas")

    df = pd.DataFrame([{"Nome da Peça": "X", "Link da Peça": "https://x"}])
    out = ensure_teatroapp_fields_dataframe(df)

    assert "Link Sessões" in out.columns
    assert "Teatroapp Sessions" in out.columns
    assert out.iloc[0]["Link Sessões"] == "https://x"
    assert out.iloc[0]["Teatroapp Sessions"] == []
