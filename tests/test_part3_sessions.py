import pytest

pytest.importorskip("dotenv")

from teatroapp_uploader.part3_sessions import _extract_sessions_count_from_text


def test_extract_sessions_count_from_text_en():
    assert _extract_sessions_count_from_text("Sessions (3)") == 3


def test_extract_sessions_count_from_text_pt():
    assert _extract_sessions_count_from_text("Sessões (12)") == 12


def test_extract_sessions_count_from_text_colon_formats():
    assert _extract_sessions_count_from_text("Sessions: 4") == 4
    assert _extract_sessions_count_from_text("Sessoes: 8") == 8
