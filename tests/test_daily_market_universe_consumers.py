from ui_qt.research_universe_presentation import research_universe_text


def test_legacy_source_does_not_infer_original_population():
    text, detail = research_universe_text(None, published_count=2, declared_count=2)
    assert "來源未知" in text
    assert "原始母體分母未知" in detail
    assert "原排名未知" in detail


def test_unknown_population_and_configuration_exclusions_remain_distinct():
    binding = {"universe_id": "bounded", "version": "v1", "as_of_date": "2026-10-05",
               "included_stock_codes": ["1477", "2330", "2382"],
               "excluded_stock_codes": [{"stock_code": "2317", "reason": "明確研究批次排除"}],
               "population_count": None, "source_ref": "config.json", "source_sha256": "a" * 64}
    text, detail = research_universe_text(binding, published_count=2, declared_count=3)
    assert "設定分母 未知" in text
    assert "發布涵蓋 2/3" in text
    assert "2317：明確研究批次排除" in detail
    assert "設定母體不是資料資格" in detail
    assert "原排名未知" in detail


def test_known_population_is_not_screen_visible_count():
    binding = {"universe_id": "bounded", "version": "v1", "as_of_date": "2026-10-05",
               "included_stock_codes": ["1477", "2330", "2382"],
               "excluded_stock_codes": [{"stock_code": "2317", "reason": "批次排除"}],
               "population_count": 4}
    text, _ = research_universe_text(binding, published_count=3, declared_count=3)
    assert "設定分母 4" in text
    assert "發布涵蓋 3/3" in text


def test_configured_snapshot_manual_update_never_starts_worker():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication
    from ui_qt.views.daily_market_research_view import DailyMarketResearchView
    app = QApplication.instance() or QApplication([])
    calls = []
    service = SimpleNamespace(produce_snapshot=lambda *a, **kw: calls.append((a, kw)))
    view = DailyMarketResearchView(service)
    snapshot = SimpleNamespace(manifest={"research_universe": {"universe_id": "configured"}})
    view._snapshot = snapshot
    view.start_snapshot_update()
    assert calls == []
    assert view._worker is None
    assert view._snapshot is snapshot
    assert "--universe-config" in view.status_label.text()
    view.close()
    app.processEvents()
