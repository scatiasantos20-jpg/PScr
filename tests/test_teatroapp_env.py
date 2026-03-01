import pytest

pytest.importorskip("dotenv")


def test_load_config_requires_poster_path(monkeypatch):
    from teatroapp_uploader.env import load_config

    required = {
        "TEATROAPP_EMAIL": "x@example.com",
        "TEATROAPP_PASSWORD": "secret",
        "TEATROAPP_TITLE": "Titulo Teste",
    }
    for k, v in required.items():
        monkeypatch.setenv(k, v)

    monkeypatch.delenv("TEATROAPP_POSTER_PATH", raising=False)

    with pytest.raises(RuntimeError, match="TEATROAPP_POSTER_PATH"):
        load_config()
