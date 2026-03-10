import pytest
pytest.importorskip("requests")

import json
from pathlib import Path

from scrapers.common import teatroapp_export as exp


def _setup_tmp_paths(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(exp, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(exp, "DEBUG_DIR", tmp_path / "debug")
    monkeypatch.setattr(exp, "BATCH_DIR", tmp_path / "batch")
    monkeypatch.setattr(exp, "BATCH_JSON", tmp_path / "teatroapp_batch.json")
    monkeypatch.setattr(exp, "PAYLOAD_JSON", tmp_path / "teatroapp_payload.json")
    monkeypatch.setattr(exp, "SESSIONS_JSON", tmp_path / "teatroapp_sessions.json")
    monkeypatch.setattr(exp, "OVERRIDE_ENV", tmp_path / "teatroapp_override.env")
    monkeypatch.setattr(exp, "OVERRIDES_JSON", tmp_path / "teatroapp_overrides.json")

    exp.DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    exp.BATCH_DIR.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(exp, "_find_existing_poster", lambda *_a, **_k: None)
    monkeypatch.setattr(exp, "_find_downloaded_poster", lambda *_a, **_k: None)
    monkeypatch.setattr(exp, "_download_poster", lambda *_a, **_k: None)


def test_export_uses_link_sessoes_and_descricao(monkeypatch, tmp_path):
    _setup_tmp_paths(monkeypatch, tmp_path)

    sample_sessions = [{"venue": "Sala X", "date": "2026-03-04", "hour": 21, "minute": 0, "ticket_url": "https://t/1"}]
    monkeypatch.setattr(exp, "_fetch_sessions_exact", lambda *_a, **_k: sample_sessions)

    row = {
        "Título": "Peça Teste",
        "URL": "https://www.bol.pt/Comprar/Bilhetes/123/peca",
        "Link Sessões": "https://www.bol.pt/Comprar/Bilhetes/123/peca/Sessoes",
        "Descrição": "Sinopse vinda de Descrição",
        "Local": "Sala X",
    }

    item = exp._export_one_row(row, idx=1)
    assert item["n_sessions"] == 1

    payload = json.loads(Path(item["payload_path"]).read_text(encoding="utf-8"))
    assert payload["details"]["synopsis"] == "Sinopse vinda de Descrição"


def test_export_parses_prebuilt_sessions_json_string(monkeypatch, tmp_path):
    _setup_tmp_paths(monkeypatch, tmp_path)

    prebuilt = json.dumps(
        [{"venue": "Sala Y", "date": "2026-03-05", "hour": 20, "minute": 30, "ticket_url": "https://t/2"}]
    )
    row = {
        "Título": "Peça Ticketline",
        "URL": "https://ticketline.sapo.pt/evento/abc",
        "Sinopse": "Texto",
        "Teatroapp Sessions": prebuilt,
        "Local": "Sala Y",
    }

    item = exp._export_one_row(row, idx=2)
    sessions = json.loads(Path(item["sessions_path"]).read_text(encoding="utf-8"))
    assert len(sessions) == 1
    assert sessions[0]["venue"] == "Sala Y"
