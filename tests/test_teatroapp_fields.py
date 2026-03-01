from scrapers.common.teatroapp_fields import (
    attach_teatroapp_fields,
    normalize_teatroapp_sessions,
    normalize_ticket_url,
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
