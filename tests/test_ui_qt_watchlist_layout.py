import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QGroupBox, QLabel, QMessageBox, QProgressBar,
)

from ui_qt.widgets.info_button import InfoButton, InfoDialog
from ui_qt.views.watchlist_view import WatchlistView
from app_module.dtos.decision_continuity_dtos import DecisionIdentity
from app_module.watchlist_review_state import (
    WatchlistReviewSnapshot,
    WatchlistReviewSnapshotRow,
    WatchlistReviewSourceIdentity,
    WatchlistReviewState,
    ReviewStatus,
)


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _review_snapshot_row(
    position: int,
    stock_code: str,
    source_id: str,
    status: ReviewStatus,
    identity_char: str,
) -> WatchlistReviewSnapshotRow:
    return WatchlistReviewSnapshotRow(
        position=position,
        stock_code=stock_code,
        stock_name=f"測試 {stock_code}",
        added_at="2026-10-24T08:00:00+08:00",
        source="recommendation",
        notes="私人理由不可出現在分布卡",
        tags=(),
        source_id=source_id,
        decision_identity=DecisionIdentity(
            stock_code=stock_code, result_id=source_id,
        ),
        research_bookmark=None,
        source_identity=WatchlistReviewSourceIdentity(
            stock_code=stock_code, item_sha256=identity_char * 64,
        ),
        review_status=status,
    )


class _ReviewSnapshotService(MagicMock):
    def __init__(self, snapshot: object = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.snapshot_value: object = snapshot
        self.review_snapshot_calls: int = 0

    def get_review_snapshot(self) -> object:
        self.review_snapshot_calls += 1
        if isinstance(self.snapshot_value, BaseException):
            raise self.snapshot_value
        return self.snapshot_value


def test_watchlist_desktop_layout_keeps_both_universe_lists_visible(monkeypatch, tmp_path: Path):
    _app()

    class UniverseStub:
        def list_watchlists(self):
            return [{"name": "成長觀察", "count": 3, "watchlist_id": "growth"}]

        def load_watchlist(self, identifier):
            assert identifier == "growth"
            return SimpleNamespace(codes=["2330", "2317", "2454"])

    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: UniverseStub(),
    )
    service = MagicMock()
    service.get_stocks.return_value = [
        {
            "stock_code": "2330",
            "stock_name": "台積電",
            "added_at": "2026-09-08 09:00:00",
            "source": "manual",
            "notes": "",
        }
    ]
    config = SimpleNamespace(output_root=tmp_path)
    view = WatchlistView(service, config=config)
    view.show()
    view.resize(1400, 800)
    _app().processEvents()

    assert view.main_splitter.orientation() == Qt.Horizontal
    assert view.management_splitter.orientation() == Qt.Vertical
    candidate_panel = view.findChild(QGroupBox, "watchlistCandidatePanel")
    universe_panel = view.findChild(QGroupBox, "watchlistUniversePanel")
    assert candidate_panel is not None
    assert universe_panel is not None
    assert view.findChild(QGroupBox, "watchlistOpsGroup") is not None
    assert view.findChild(QGroupBox, "watchlistOpsGroup").parent() is candidate_panel
    distribution_group = view.findChild(QGroupBox, "watchlistReviewDistribution")
    assert distribution_group is not None
    assert candidate_panel.layout().indexOf(distribution_group) < candidate_panel.layout().indexOf(
        view.stocks_table
    )
    assert view.universe_list.height() > 150
    assert view.universe_stock_list.height() > 150
    assert view.universe_stock_list.count() == 0
    assert view.stats_label.text() == "1 筆候選列／1 檔不同代號"
    assert "已更新：1 筆" in view.status_label.text()
    assert "同版查看狀態快照" in view.review_distribution_status.text()
    service.get_stocks.assert_called_once_with()

    view.universe_list.setCurrentRow(0)
    assert view.universe_stock_list.count() == 3
    view.close()


def test_watchlist_narrow_layout_switches_to_vertical_without_losing_controls(monkeypatch, tmp_path: Path):
    _app()

    class UniverseStub:
        def list_watchlists(self):
            return []

    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: UniverseStub(),
    )
    service = MagicMock()
    service.get_stocks.return_value = []
    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))
    view.show()
    view.resize(600, 800)
    _app().processEvents()

    assert view.main_splitter.orientation() == Qt.Vertical
    assert view.management_splitter.orientation() == Qt.Vertical
    assert view.findChild(QGroupBox, "watchlistCandidatePanel") is not None
    assert view.findChild(QGroupBox, "watchlistUniversePanel") is not None
    assert view.findChild(QGroupBox, "watchlistOpsGroup") is not None
    assert view.stats_label.text() == "0 筆候選列／0 檔不同代號（目前沒有候選）"
    assert "0 筆候選列／0 檔不同代號" in view.watchlist_focus_summary.conclusion_label.text()
    view.close()


def test_watchlist_load_failure_keeps_candidate_counts_unknown(monkeypatch, tmp_path: Path):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *_args, **_kwargs: 0)
    service = MagicMock()
    service.get_stocks.side_effect = OSError("candidate store unavailable")

    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))

    assert view.stats_label.text() == "候選列／不同代號數未知（載入失敗）"
    assert "載入失敗" in view.status_label.text()
    assert "查看狀態分布不可用" in view.review_distribution_status.text()
    assert "狀態尚未完成讀取" in view.watchlist_focus_summary.conclusion_label.text()
    assert "0 筆候選列" not in view.stats_label.text()
    view._load_selected_analysis()
    assert "狀態尚未完成讀取" in view.watchlist_focus_summary.conclusion_label.text()
    view.close()


def test_watchlist_navigation_has_no_candidate_hint_popup_and_info_route_still_opens(
    monkeypatch, tmp_path: Path
):
    app = _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    service = MagicMock()
    service.get_stocks.return_value = []
    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))

    view.show()
    for width in (1400, 600, 1400):
        view.resize(width, 800)
        app.processEvents()
        orphan_hints = [
            widget
            for widget in app.topLevelWidgets()
            if isinstance(widget, QLabel)
            and widget.isVisible()
            and widget.text() == "研究候選池，或保存成可重用的選股清單。"
        ]
        assert orphan_hints == []

    view.hide()
    app.processEvents()
    view.show()
    app.processEvents()
    assert not [
        widget
        for widget in app.topLevelWidgets()
        if isinstance(widget, QLabel)
        and widget.isVisible()
        and widget.text() == "研究候選池，或保存成可重用的選股清單。"
    ]

    opened = []

    def fake_exec(dialog):
        opened.append(dialog)
        return 0

    monkeypatch.setattr(InfoDialog, "exec", fake_exec)
    info_button = view.findChild(InfoButton)
    assert info_button is not None
    info_button.click()
    assert [dialog.tab_key for dialog in opened] == ["watchlist"]
    view.close()


def test_candidate_table_hides_raw_identity_but_keeps_exact_source_after_sort(monkeypatch, tmp_path):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    identity = {"result_id": "original-result", "stock_code": "2330"}
    second_identity = {"result_id": "second-result", "stock_code": "2330"}
    service = MagicMock()
    service.get_stocks.return_value = [
        {"stock_code": "2330", "stock_name": "台積電", "decision_identity": identity},
        {"stock_code": "2330", "stock_name": "台積電", "decision_identity": second_identity},
        {"stock_code": "2603", "stock_name": "長榮"},
    ]
    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))
    view._load_watchlist()
    model = view.stocks_model
    headers = [model.headerData(i, Qt.Horizontal) for i in range(model.columnCount())]
    assert "decision_identity" not in headers
    assert "推薦來源" in headers
    model.sort(headers.index("證券代號"), Qt.AscendingOrder)
    frame = model.getDataFrame()
    assert view.stats_label.text() == "3 筆候選列／2 檔不同代號"
    assert model.rowCount() == 3
    assert len(frame[frame["證券代號"] == "2330"]) == 2
    linked_rows = frame[frame["證券代號"] == "2330"]
    assert {row["decision_identity"]["result_id"] for _, row in linked_rows.iterrows()} == {
        "original-result",
        "second-result",
    }
    assert all(row == "已連結原推薦" for row in linked_rows["推薦來源"])
    assert view._row_decision_identity(linked_rows.iloc[0], "2330").is_linked
    assert "3 筆候選列／2 檔不同代號" in view.watchlist_focus_summary.conclusion_label.text()
    assert "不是評分或買賣訊號" in view.source_link_hint.text()
    view.close()


def test_review_snapshot_loads_table_and_counts_distinct_same_stock_rows_once(
    monkeypatch, tmp_path,
):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    rows = (
        _review_snapshot_row(0, "2330", "result-a", "confirmed", "a"),
        _review_snapshot_row(1, "2330", "result-b", "deferred", "b"),
        _review_snapshot_row(2, "2603", "result-c", "pending", "c"),
        _review_snapshot_row(3, "2317", "result-d", "unknown", "d"),
    )
    snapshot = WatchlistReviewSnapshot(status="loaded", revision=12, rows=rows)
    service = _ReviewSnapshotService(snapshot)
    service.get_stocks.side_effect = AssertionError(
        "snapshot path must not perform another Watchlist read"
    )

    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))

    assert service.review_snapshot_calls == 1
    service.get_stocks.assert_not_called()
    assert view.review_distribution_status.text() == (
        "同一讀取 revision 12；依 4 筆候選列統計。"
    )
    assert view.stocks_model.rowCount() == 4
    frame = view.stocks_model.getDataFrame()
    assert len(frame[frame["證券代號"] == "2330"]) == 2
    assert view.review_distribution_counts["pending"].text() == "1 / 4 筆"
    assert view.review_distribution_counts["confirmed"].text() == "1 / 4 筆"
    assert view.review_distribution_counts["deferred"].text() == "1 / 4 筆"
    assert view.review_distribution_counts["unknown"].text() == "1 / 4 筆"
    assert all(not bar.isHidden() and bar.value() == 1 and bar.maximum() == 4
               for bar in view.review_distribution_bars.values())
    chart_text = "\n".join(
        label.text()
        for label in view.review_distribution_group.findChildren(QLabel)
    )
    assert "私人理由不可出現在分布卡" not in chart_text
    assert view.stocks_model.getDataFrame().iloc[0]["備註"] == (
        "私人理由不可出現在分布卡"
    )
    view.close()


def test_review_snapshot_empty_missing_and_unavailable_clear_counts_fail_closed(
    monkeypatch, tmp_path,
):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    loaded = WatchlistReviewSnapshot(
        status="loaded",
        revision=8,
        rows=(_review_snapshot_row(0, "2330", "one", "confirmed", "e"),),
    )
    service = _ReviewSnapshotService(loaded)
    service.get_stocks.side_effect = AssertionError(
        "typed snapshot path must not call get_stocks"
    )
    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))
    assert not view.review_distribution_bars["confirmed"].isHidden()

    service.snapshot_value = WatchlistReviewSnapshot(
        status="loaded", revision=9, rows=(),
    )
    view._load_watchlist()
    assert view.stocks_model.rowCount() == 0
    assert view.review_distribution_status.text() == (
        "同一讀取 revision 9；依 0 筆候選列統計。"
    )
    assert all(
        label.text() == "0 / 0 筆"
        for label in view.review_distribution_counts.values()
    )
    assert all(bar.isHidden() for bar in view.review_distribution_bars.values())

    service.snapshot_value = WatchlistReviewSnapshot(
        status="missing", revision=None,
    )
    view._load_watchlist()
    assert view.stats_label.text() == "候選列／不同代號數未知（清單不存在）"
    assert "尚無已保存清單" in view.review_distribution_status.text()
    assert all(label.text() == "—" for label in view.review_distribution_counts.values())
    assert all(bar.isHidden() for bar in view.review_distribution_bars.values())
    assert not view.remove_btn.isEnabled()
    assert not view.clear_btn.isEnabled()
    assert not view.save_to_universe_btn.isEnabled()
    assert not view.send_to_research_lab_btn.isEnabled()

    service.snapshot_value = WatchlistReviewSnapshot(
        status="unavailable", revision=None, error_code="OSError",
    )
    view._load_watchlist()
    assert view.stats_label.text() == "候選列／不同代號數未知（載入失敗）"
    assert "快照不可用" in view.review_distribution_status.text()
    assert all(label.text() == "—" for label in view.review_distribution_counts.values())
    assert all(bar.isHidden() for bar in view.review_distribution_bars.values())
    service.get_stocks.assert_not_called()
    view.close()


def test_declared_review_snapshot_failure_never_falls_back_to_get_stocks(
    monkeypatch, tmp_path,
):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    for invalid_snapshot in (object(), OSError("storage detail")):
        service = _ReviewSnapshotService(invalid_snapshot)
        service.get_stocks.return_value = [
            {"stock_code": "2330", "stock_name": "不應沿用"}
        ]
        view = WatchlistView(
            service, config=SimpleNamespace(output_root=tmp_path)
        )
        assert service.review_snapshot_calls == 1
        service.get_stocks.assert_not_called()
        assert view.stats_label.text() == "候選列／不同代號數未知（載入失敗）"
        assert "快照不可用" in view.review_distribution_status.text()
        assert all(bar.isHidden() for bar in view.review_distribution_bars.values())
        view.close()


def test_selected_review_revision_mismatch_blocks_save_and_legacy_is_annotated(
    monkeypatch, tmp_path,
):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    row = _review_snapshot_row(0, "2330", "result-a", "confirmed", "f")
    assert row.source_identity is not None
    service = _ReviewSnapshotService(
        WatchlistReviewSnapshot(status="loaded", revision=12, rows=(row,))
    )
    service.get_review_state.return_value = WatchlistReviewState(
        source_identity=row.source_identity,
        reason="單列私人理由",
        state="confirmed",
        revision=13,
        writable=True,
    )
    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))
    selected = view.stocks_model.getDataFrame().iloc[0]
    view._render_observation(selected)
    assert "單列狀態 revision 13" in view.observation_state_label.text()
    assert "候選摘要 revision 12" in view.observation_state_label.text()
    assert view._observation_review is None
    assert not view.confirm_observation_button.isEnabled()
    view._set_observation_state("deferred")
    service.save_review_state.assert_not_called()
    view.close()

    legacy_row = _review_snapshot_row(0, "2317", "legacy", "pending", "1")
    assert legacy_row.source_identity is not None
    legacy_service = _ReviewSnapshotService(
        WatchlistReviewSnapshot(status="loaded", revision=None, rows=(legacy_row,))
    )
    legacy_service.get_review_state.return_value = WatchlistReviewState(
        source_identity=legacy_row.source_identity,
        reason="legacy reason",
        state="pending",
        revision=3,
        writable=True,
    )
    legacy_view = WatchlistView(
        legacy_service, config=SimpleNamespace(output_root=tmp_path)
    )
    legacy_view._render_observation(
        legacy_view.stocks_model.getDataFrame().iloc[0]
    )
    assert "revision 未提供" in legacy_view.review_distribution_status.text()
    assert "可能較新" in legacy_view.observation_state_label.text()
    legacy_view.close()
