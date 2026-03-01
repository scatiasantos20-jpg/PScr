from scrapers.common.extraction_quality import build_quality_snapshot


def test_build_quality_snapshot_counts_missing_and_sessions():
    pd = __import__("pytest").importorskip("pandas")
    df = pd.DataFrame(
        [
            {"Nome da Peça": "A", "Link da Peça": "https://a", "Teatroapp Sessions": [{"x": 1}]},
            {"Nome da Peça": "", "Link da Peça": "https://b", "Teatroapp Sessions": []},
        ]
    )

    out = build_quality_snapshot(platform="ticketline", total_scraped=10, total_to_sync=2, df=df)
    assert out["totals"]["scraped"] == 10
    assert out["totals"]["to_sync"] == 2
    assert out["totals"]["with_sessions"] == 1
    assert out["quality"]["missing_required_fields"] == 1
