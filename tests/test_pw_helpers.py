import pytest

pytest.importorskip("dotenv")



def test_fill_delay_env(monkeypatch):
    from teatroapp_uploader.pw_helpers import _fill_delay_ms

    monkeypatch.setenv("TEATROAPP_FILL_DELAY_MS", "120")
    assert _fill_delay_ms() == 120


def test_fill_delay_env_invalid(monkeypatch):
    from teatroapp_uploader.pw_helpers import _fill_delay_ms

    monkeypatch.setenv("TEATROAPP_FILL_DELAY_MS", "abc")
    assert _fill_delay_ms() == 80