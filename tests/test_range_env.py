from scrapers.common.range_env import parse_global_event_range, in_range_1based


def test_parse_global_event_range_all_modes():
    assert parse_global_event_range(None) is None
    assert parse_global_event_range("") is None
    assert parse_global_event_range("all") is None
    assert parse_global_event_range("*") is None


def test_parse_global_event_range_numeric_and_interval():
    r = parse_global_event_range("3")
    assert r is not None
    assert list(r) == [1, 2, 3]

    r2 = parse_global_event_range("2-4")
    assert r2 is not None
    assert list(r2) == [2, 3, 4]


def test_in_range_1based_behaviour():
    assert in_range_1based(5, None)
    r = parse_global_event_range("2-3")
    assert r is not None
    assert not in_range_1based(1, r)
    assert in_range_1based(2, r)
