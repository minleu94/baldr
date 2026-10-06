from __future__ import annotations

import os
from dataclasses import replace
from types import SimpleNamespace
from threading import Event
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from tests.test_daily_market_research_screener import (
    _produce,
    _seed_database,
    _service,
)
from tests.test_original_stock_ranking import (
    _publish as _publish_original_ranking,
    market as _ranked_market,
)
from app_module.daily_market_research_screener import DailyMarketResearchScreenerService
from ui_qt.original_ranking_presentation import ranking_rows_by_code, ranking_window_text
from ui_qt.shared_market_research_consumer import (
    SharedMarketResearchConsumer,
    shared_market_research_frame,
)
from ui_qt.views.market_regime_view import MarketRegimeView
from ui_qt.views.strong_stocks_view import StrongStocksView
from ui_qt.views.weak_stocks_view import WeakStocksView


class _SnapshotSource(QObject):
    snapshotAccepted = Signal(object)
    snapshotCleared = Signal()

    def __init__(self, service: object, snapshot: object) -> None:
        super().__init__()
        self.service = service
        self._snapshot = snapshot


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _wait_for(qapp: QApplication, predicate, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    qapp.processEvents()
    return bool(predicate())


def test_actual_four_mode_reads_preserve_original_labels_windows_and_exclusions(
    tmp_path, qapp, monkeypatch
) -> None:
    market = _ranked_market.__wrapped__(tmp_path, monkeypatch)
    modes = (("day", "strong"), ("day", "weak"), ("week", "strong"), ("week", "weak"))
    for period, direction in modes:
        _publish_original_ranking(market, period, direction)
    service = DailyMarketResearchScreenerService(
        SimpleNamespace(db_file=market["db_path"]),
        snapshot_root=market["snapshot_root"],
        original_ranking_root=market["ranking_root"],
    )
    pinned = market["snapshot"]
    snapshot = service.read_snapshot(
        pinned.cohort_id,
        pinned.decision_date,
        pinned.manifest_sha256,
    )
    source = _SnapshotSource(service, snapshot)
    consumer = SharedMarketResearchConsumer()
    reads = []
    failures = []
    consumer.resultReady.connect(reads.append)
    consumer.failed.connect(failures.append)
    consumer.set_source(source)

    for period, direction in modes:
        prior_count = len(reads)
        consumer.request(period=period, direction=direction)
        assert _wait_for(qapp, lambda: len(reads) > prior_count or bool(failures)), failures
        assert not failures
        assert _wait_for(qapp, lambda: consumer._worker is None)
        read = reads[-1]
        assert read.snapshot.decision_date == snapshot.decision_date
        assert (read.period, read.direction) == (period, direction)
        assert read.ranking is not None
        assert read.projection.source_snapshot_hash == read.snapshot.manifest_sha256
        assert read.projection.source_snapshot_id == read.snapshot.manifest_identity_sha256
        assert read.projection.method_contracts_sha256 == read.snapshot.manifest[
            "method_contracts_sha256"
        ]
        frame = shared_market_research_frame(read)
        ranking_codes = tuple(str(row["stock_code"]) for row in read.ranking.rows)
        assert tuple(frame["證券代號"][: len(ranking_codes)]) == ranking_codes
        assert tuple(frame["證券代號"][len(ranking_codes) :]) == tuple(
            read.ranking.missing_rank_stock_codes
        )
        assert "1101" in read.ranking.missing_rank_stock_codes
        assert "原引擎排除" in frame.loc[
            frame["證券代號"] == "1101", "原排名資格"
        ].iloc[0]
        indexed = ranking_rows_by_code(read.ranking)
        assert indexed is not None
        for stock_code, row in indexed.items():
            displayed = frame.loc[frame["證券代號"] == stock_code].iloc[0]
            assert displayed["原引擎標籤"] == row["score_label"]
            assert displayed["原始比較窗"] == ranking_window_text(row)

    class _ForbiddenLegacyProducer:
        calls = 0

        def get_strong_stocks(self, **_kwargs):
            self.calls += 1
            raise AssertionError("shared mode must not call the legacy producer")

        def get_weak_stocks(self, **_kwargs):
            self.calls += 1
            raise AssertionError("shared mode must not call the legacy producer")

    legacy_service = _ForbiddenLegacyProducer()
    strong_view = StrongStocksView(legacy_service)
    weak_view = WeakStocksView(legacy_service)
    source = _SnapshotSource(service, snapshot)
    strong_view.set_shared_research_source(source)
    weak_view.set_shared_research_source(source)
    strong_view.shared_research_mode_selector.setCurrentIndex(1)
    weak_view.shared_research_mode_selector.setCurrentIndex(1)
    expected_rankings = {
        mode: service.read_original_ranking(
            snapshot,
            period=mode[0],
            direction=mode[1],
        )
        for mode in modes
    }

    def view_has_ranked_rows(view, period: str, direction: str) -> bool:
        if view.shared_research_consumer._worker is not None:
            return False
        frame = view.stocks_model.getDataFrame()
        if frame.empty or snapshot.manifest_sha256 not in view.source_scope_label.text():
            return False
        ranking = expected_rankings[(period, direction)]
        row = ranking.rows[0]
        shown = frame.loc[frame["證券代號"] == row["stock_code"]].iloc[0]
        return (
            shown["原始名次"] == str(row["rank"])
            and shown["原引擎標籤"] == row["score_label"]
            and shown["原始比較窗"] == ranking_window_text(row)
        )

    assert _wait_for(
        qapp,
        lambda: view_has_ranked_rows(strong_view, "day", "strong")
        and view_has_ranked_rows(weak_view, "day", "weak"),
    )
    strong_view.period_btn_day.click()
    weak_view.period_btn_day.click()
    assert strong_view.period_btn_day.isChecked() and not strong_view.period_btn_week.isChecked()
    assert weak_view.period_btn_day.isChecked() and not weak_view.period_btn_week.isChecked()
    assert _wait_for(
        qapp,
        lambda: view_has_ranked_rows(strong_view, "day", "strong")
        and view_has_ranked_rows(weak_view, "day", "weak"),
    )
    strong_view.period_btn_week.setChecked(True)
    weak_view.period_btn_week.setChecked(True)
    strong_view._on_period_changed("week")
    weak_view._on_period_changed("week")
    assert _wait_for(
        qapp,
        lambda: view_has_ranked_rows(strong_view, "week", "strong")
        and view_has_ranked_rows(weak_view, "week", "weak"),
    )
    assert legacy_service.calls == 0

    first = reads[0]
    wrong_rank = replace(first.ranking, direction="weak")
    wrong_read = replace(
        first,
        ranking=wrong_rank,
        ranking_rows=ranking_rows_by_code(wrong_rank),
    )
    generation = consumer._generation + 1
    consumer._generation = generation
    consumer._on_finished(
        generation,
        consumer._cache_key(first.snapshot, first.period, first.direction),
        wrong_read,
    )
    assert "原排名 mode" in failures[-1]

    source.snapshotCleared.emit()
    assert _wait_for(qapp, lambda: strong_view.stocks_model.rowCount() == 0)
    assert weak_view.stocks_model.rowCount() == 0
    consumer.begin_shutdown()
    assert _wait_for(qapp, lambda: consumer._worker is None)
    assert strong_view.begin_shutdown()
    assert weak_view.begin_shutdown()


def test_source_change_cancels_an_inflight_pinned_read_without_stale_result(
    tmp_path, qapp, monkeypatch
) -> None:
    database, _codes, decision_date = _seed_database(tmp_path)
    service = _service(database, tmp_path / "published")
    _produce(monkeypatch, service, decision_date)
    snapshot = service.read_snapshot("controlled-daily-market", decision_date)
    source = _SnapshotSource(service, snapshot)
    original_read = service.read_snapshot
    entered = Event()
    release = Event()

    def delayed_read(
        cohort_id,
        decision_date,
        manifest_sha256=None,
        *,
        cancel_callback=None,
    ):
        entered.set()
        release.wait(timeout=5)
        return original_read(
            cohort_id,
            decision_date,
            manifest_sha256,
            cancel_callback=cancel_callback,
        )

    service.read_snapshot = delayed_read
    consumer = SharedMarketResearchConsumer()
    reads = []
    consumer.resultReady.connect(reads.append)
    consumer.set_source(source)
    consumer.request(period="day", direction="strong")
    assert entered.wait(timeout=5)

    source.snapshotCleared.emit()
    release.set()

    assert _wait_for(qapp, lambda: consumer._worker is None)
    assert consumer.snapshot is None
    assert reads == []
    consumer.begin_shutdown()


def test_invalid_external_mode_is_rejected_without_worker_or_cache_entry() -> None:
    consumer = SharedMarketResearchConsumer()
    failures = []
    consumer.failed.connect(failures.append)
    consumer.request(period="month", direction="strong")
    assert failures
    assert consumer._worker is None
    assert consumer._cache == {}
    consumer.begin_shutdown()


def test_real_consumer_views_default_to_their_existing_sources(qapp) -> None:
    class _UnusedService:
        pass

    strong = StrongStocksView(_UnusedService())
    weak = WeakStocksView(_UnusedService())
    regime = MarketRegimeView(_UnusedService())
    assert strong.shared_research_mode_selector.currentData() == "full_market"
    assert weak.shared_research_mode_selector.currentData() == "full_market"
    assert "原全市場" in strong.source_scope_label.text()
    assert "原全市場" in weak.source_scope_label.text()
    assert "大盤指數判斷分開" in regime.shared_research_summary_label.text()
    assert strong.begin_shutdown()
    assert weak.begin_shutdown()
    assert regime.begin_shutdown()
