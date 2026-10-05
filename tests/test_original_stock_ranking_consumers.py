from __future__ import annotations

import os
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app_module.daily_market_cohort_projection import (
    DailyMarketCohortProjectionError,
    project_daily_market_cohort,
)
from app_module.original_stock_ranking import VerifiedOriginalStockRanking
from test_daily_market_cohort_projection import _fixture
from ui_qt.original_ranking_presentation import (
    original_rank_cell,
    ranking_matches_snapshot,
    ranking_rows_by_code,
    ranking_summary_text,
)
from ui_qt.views.daily_market_cohort_view import DailyMarketCohortView
from ui_qt.views.daily_market_research_view import DailyMarketResearchView


def _app() -> QApplication:
    instance = QApplication.instance()
    return instance if instance is not None else QApplication([])


def _ranking(snapshot, *, period: str = "day", direction: str = "strong"):
    declared = tuple(snapshot.manifest["declared_stock_codes"])
    eligible = ("1001", "1002", "1003")
    rows = (
        MappingProxyType(
            {
                "stock_code": "1001",
                "rank": 1,
                "score_label": "Top 100%",
                "price_change_percent": "1.25",
                "volume_change_percent": "10",
                "comparison_date": "2026-10-02",
                "latest_date": "2026-10-05",
            }
        ),
        MappingProxyType(
            {
                "stock_code": "1002",
                "rank": 2,
                "score_label": "Bottom 50%",
                "price_change_percent": "-0.50",
                "volume_change_percent": "-8",
                "comparison_date": "2026-10-02",
                "latest_date": "2026-10-05",
            }
        ),
        MappingProxyType(
            {
                "stock_code": "1003",
                "rank": 3,
                "score_label": "Top 33%",
                "price_change_percent": "0.00",
                "volume_change_percent": "0",
                "comparison_date": "2026-10-02",
                "latest_date": "2026-10-05",
            }
        ),
    )
    return VerifiedOriginalStockRanking(
        period=period,
        direction=direction,
        decision_date=snapshot.decision_date.isoformat(),
        manifest_sha256="b" * 64,
        manifest_identity_sha256="c" * 64,
        readiness="research_only",
        rows=rows,
        eligible_universe_size=len(eligible),
        declared_stock_codes=declared,
        missing_rank_stock_codes=("1004",),
        metadata=MappingProxyType(
            {
                "parent_manifest_sha256": snapshot.manifest_sha256,
                "parent_manifest_identity_sha256": snapshot.manifest_identity_sha256,
                "eligible_stock_codes": eligible,
                "run_id": "r" * 64,
                "engine_method": "legacy-native",
                "engine_version": "1",
                "engine_parameters": {"window": 3},
                "research_universe_id": "universe-test",
                "research_universe_version": "1",
                "research_universe_source_sha256": "d" * 64,
            }
        ),
    )


def _set_data(combo, value: str) -> None:
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


def test_native_ranking_object_is_shared_by_cohort_and_market_views(tmp_path: Path) -> None:
    app = _app()
    root, snapshot, rows, service = _fixture(tmp_path)
    ranking = _ranking(snapshot)
    projection = project_daily_market_cohort(
        snapshot,
        rows,
        expected_snapshot_root=root,
        original_ranking=ranking,
    )
    assert projection.original_rank_state == "verified"
    assert projection.original_ranking is ranking

    market_view = DailyMarketResearchView(service)
    market_view._snapshot = snapshot
    market_view._cohort_projection = projection
    market_view._cohort_members_by_code = {
        member.stock_code: member for member in projection.members
    }
    market_view._original_ranking = ranking
    market_view._all_rows = tuple(reversed(rows))
    market_view._sync_original_rank_sort_controls()
    _set_data(market_view.sort_key_combo, "original_strength_rank")
    app.processEvents()

    assert tuple(row.stock_code for row in market_view._visible_rows) == (
        "1001",
        "1002",
        "1003",
    )
    assert {id(row) for row in market_view._visible_rows} == {id(row) for row in rows}
    rank_column = market_view.results_table.columnCount() - 1
    first_row = next(
        index
        for index in range(market_view.results_table.rowCount())
        if market_view.results_table.item(index, 0).text() == "1001"
    )
    assert market_view.results_table.item(first_row, rank_column).text() == "1 · Top 100%"
    assert original_rank_cell(ranking, "1004") == "未知"
    assert "不可解讀為一般前幾％或勝率" in ranking_summary_text(ranking)

    cohort_view = DailyMarketCohortView(market_view, lambda: None)
    cohort_view.accept_snapshot(snapshot)
    cohort_view.accept_original_ranking(ranking)
    assert cohort_view.original_ranking is ranking
    assert cohort_view.projection is projection
    assert cohort_view.members_table.item(0, 5).text() == "1 · Top 100%"
    assert "manifest_sha256=" + ranking.manifest_sha256 in cohort_view.ranking_label.toolTip()

    market_view.close()
    cohort_view.close()
    app.processEvents()


def test_rank_binding_and_malformed_rows_fail_closed(tmp_path: Path) -> None:
    root, snapshot, rows, _service = _fixture(tmp_path)
    ranking = _ranking(snapshot, period="week", direction="weak")

    assert ranking_matches_snapshot(
        snapshot, ranking, period="week", direction="weak"
    )
    assert not ranking_matches_snapshot(
        snapshot, ranking, period="day", direction="weak"
    )
    assert ranking_rows_by_code(ranking) is not None

    wrong_parent = VerifiedOriginalStockRanking(
        period=ranking.period,
        direction=ranking.direction,
        decision_date=ranking.decision_date,
        manifest_sha256=ranking.manifest_sha256,
        manifest_identity_sha256=ranking.manifest_identity_sha256,
        readiness=ranking.readiness,
        rows=ranking.rows,
        eligible_universe_size=ranking.eligible_universe_size,
        declared_stock_codes=ranking.declared_stock_codes,
        missing_rank_stock_codes=ranking.missing_rank_stock_codes,
        metadata=MappingProxyType(
            {
                **dict(ranking.metadata),
                "parent_manifest_identity_sha256": "e" * 64,
            }
        ),
    )
    assert not ranking_matches_snapshot(
        snapshot, wrong_parent, period="week", direction="weak"
    )
    with pytest.raises(DailyMarketCohortProjectionError):
        project_daily_market_cohort(
            snapshot,
            rows,
            expected_snapshot_root=root,
            original_ranking=wrong_parent,
        )

    duplicate_rank = VerifiedOriginalStockRanking(
        period=ranking.period,
        direction=ranking.direction,
        decision_date=ranking.decision_date,
        manifest_sha256=ranking.manifest_sha256,
        manifest_identity_sha256=ranking.manifest_identity_sha256,
        readiness=ranking.readiness,
        rows=(ranking.rows[0], {**ranking.rows[1], "rank": 1}, ranking.rows[2]),
        eligible_universe_size=ranking.eligible_universe_size,
        declared_stock_codes=ranking.declared_stock_codes,
        missing_rank_stock_codes=ranking.missing_rank_stock_codes,
        metadata=ranking.metadata,
    )
    assert ranking_rows_by_code(duplicate_rank) is None

    incomplete = VerifiedOriginalStockRanking(
        period=ranking.period,
        direction=ranking.direction,
        decision_date=ranking.decision_date,
        manifest_sha256=ranking.manifest_sha256,
        manifest_identity_sha256=ranking.manifest_identity_sha256,
        readiness=ranking.readiness,
        rows=ranking.rows[:2],
        eligible_universe_size=ranking.eligible_universe_size,
        declared_stock_codes=ranking.declared_stock_codes,
        missing_rank_stock_codes=ranking.missing_rank_stock_codes,
        metadata=ranking.metadata,
    )
    assert ranking_rows_by_code(incomplete) is None


def test_source_revision_failure_clears_old_rank_and_disables_rank_sort(
    tmp_path: Path,
) -> None:
    app = _app()
    root, snapshot, rows, service = _fixture(tmp_path)
    ranking = _ranking(snapshot)
    projection = project_daily_market_cohort(
        snapshot,
        rows,
        expected_snapshot_root=root,
        original_ranking=ranking,
    )
    view = DailyMarketResearchView(service)
    view._snapshot = snapshot
    view._cohort_projection = projection
    view._cohort_members_by_code = {
        member.stock_code: member for member in projection.members
    }
    view._original_ranking = ranking
    view._all_rows = rows
    view._sync_original_rank_sort_controls()
    _set_data(view.sort_key_combo, "original_strength_rank")
    app.processEvents()
    assert view.sort_key_combo.currentData() == "original_strength_rank"

    view._fail_original_ranking("來源 revision 已變更")
    app.processEvents()

    assert view._original_ranking is None
    assert view._cohort_projection.original_rank_state == "unknown"
    assert view.sort_key_combo.currentData() == "stock_code"
    rank_index = view.sort_key_combo.findData("original_strength_rank")
    assert not view.sort_key_combo.model().item(rank_index).isEnabled()
    assert "來源不可用或身份不符" in view.original_ranking_label.text()
    view.close()
    app.processEvents()


def test_original_rank_bookmark_is_refused_before_watchlist_write(tmp_path: Path) -> None:
    app = _app()
    root, snapshot, rows, service = _fixture(tmp_path)
    ranking = _ranking(snapshot)

    class WatchlistSpy:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def add_research_bookmark(self, bookmark: object) -> object:
            self.calls.append(bookmark)
            return SimpleNamespace(status="added")

    watchlist = WatchlistSpy()
    view = DailyMarketResearchView(service, watchlist_service=watchlist)
    view._snapshot = snapshot
    view._cohort_projection = project_daily_market_cohort(
        snapshot,
        rows,
        expected_snapshot_root=root,
        original_ranking=ranking,
    )
    view._original_ranking = ranking
    view._all_rows = rows
    view._sync_original_rank_sort_controls()
    _set_data(view.sort_key_combo, "original_strength_rank")

    assert view.bookmark_selected_research() is False
    assert watchlist.calls == []
    assert "書籤格式不保存排名期間、方向與來源身份" in view.status_label.text()
    view.close()
    app.processEvents()


def test_mode_switch_discards_inflight_result_and_reads_selected_mode(tmp_path: Path, monkeypatch) -> None:
    """舊模式讀取未完成時切換，新模式才可共享至盤勢。"""
    import threading
    import time

    app = _app()
    _root, snapshot, _rows, service = _fixture(tmp_path)
    started = threading.Event()
    release = threading.Event()
    calls = []

    def read_rank(source, *, period, direction):
        calls.append((period, direction))
        if len(calls) == 1:
            started.set()
            assert release.wait(3)
        return _ranking(source, period=period, direction=direction)

    monkeypatch.setattr(service, "read_original_ranking", read_rank)
    view = DailyMarketResearchView(service)
    market = DailyMarketCohortView(view, lambda: None)
    accepted = []
    view.originalRankingAccepted.connect(accepted.append)
    try:
        view._accept_snapshot(snapshot, sync_cutoff=True)
        view._request_original_ranking_read()
        deadline = time.monotonic() + 3
        while not started.is_set() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        assert started.is_set()
        _set_data(view.original_rank_period_combo, "week")
        _set_data(view.original_rank_direction_combo, "weak")
        release.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            app.processEvents()
            if view._worker is None and view._original_ranking is not None:
                break
            time.sleep(.005)
        assert accepted and all((rank.period, rank.direction) == ("week", "weak") for rank in accepted)
        assert market.original_ranking is view._original_ranking
        assert calls[0] == ("day", "strong") and calls[-1] == ("week", "weak")
    finally:
        release.set()
        view.close()
        market.close()
        app.processEvents()
