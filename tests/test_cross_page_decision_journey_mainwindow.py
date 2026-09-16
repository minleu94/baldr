"""隔離環境中的實際 MainWindow 跨頁決策旅程驗收。"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, QDateTime, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog

from app_module.continuity_review_projection import ContinuityReviewProjectionService
from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.decision_outcome_journey import DecisionOutcomeJourneyService
from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.dtos.decision_continuity_dtos import DecisionIdentity
from app_module.evidence_event_dtos import (
    EvidenceDataQuality,
    EvidenceEvent,
    EvidenceEventType,
    EvidenceOutcome,
    EvidenceOutcomeStatus,
)
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.journal_service import JournalService
from app_module.portfolio_service import PortfolioService
from app_module.recommendation_repository import RecommendationRepository
from data_module.config import TWStockConfig
from ui_qt.main import MainWindow, _drain_qt_deferred_deletes


ROOT = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")
DECISION_DATE = "2026-09-10"
DATA_DATE = "2026-09-10"


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _wait_for(predicate, timeout_ms: int = 12_000) -> None:
    instance = _app()
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        instance.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    instance.processEvents()
    assert predicate()


def _qt_widget_not_visible(widget: object) -> bool:
    """Treat an already deferred-deleted Qt wrapper as safely closed."""

    try:
        return not bool(widget.isVisible())  # type: ignore[attr-defined]
    except RuntimeError:
        return True


def _config(tmp_path: Path) -> TWStockConfig:
    return TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
    )


def _recommendation(
    result_id: str,
    *,
    decision_date: str,
    source_snapshot_id: str,
    source_snapshot_hash: str,
) -> RecommendationResultDTO:
    candidate = RecommendationDTO(
        stock_code="2330",
        stock_name="台積電",
        # RecommendationDTO's persisted/production UI contract normalizes
        # these score fields to float before presenter rendering.  Keep the
        # fixture aligned with that boundary; close_price remains Decimal as
        # required by the price/value contract.
        close_price=Decimal("1000"),
        price_change=1.2,
        total_score=90.0,
        indicator_score=30.0,
        pattern_score=30.0,
        volume_score=30.0,
        recommendation_reasons="synthetic research fixture；不可轉為交易指令",
        industry="半導體",
        regime_match=True,
        eligible_universe_date=decision_date,
    )
    lineage = {
        "as_of_date": decision_date,
        "data_date": DATA_DATE,
        "source_id": f"synthetic.recommendation.{result_id}",
        "source_kind": "synthetic_research_fixture",
        "source_snapshot_id": source_snapshot_id,
        "source_snapshot_hash": source_snapshot_hash,
        "profile_id": "cross-page-fixture",
        "profile_version": "fixture-v1",
    }
    return RecommendationResultDTO(
        result_id=result_id,
        result_name=f"Cross page fixture {result_id}",
        config={
            **lineage,
            "strategy_version_id": "cross-page-strategy-v1",
            "strategy_config_id": "cross-page-config-v1",
        },
        recommendations=[candidate],
        regime="Trend",
        created_at=f"{decision_date}T09:00:00+08:00",
        run_context=lineage,
    )


def _seed_saved_results(config: TWStockConfig) -> None:
    repository = RecommendationRepository(config)
    assert repository.save_result(
        _recommendation(
            "R1",
            decision_date="2026-09-10",
            source_snapshot_id="snap-r1",
            source_snapshot_hash="hash-r1",
        )
    ) == "R1"
    assert repository.save_result(
        _recommendation(
            "R2",
            decision_date="2026-09-11",
            source_snapshot_id="snap-r2",
            source_snapshot_hash="hash-r2",
        )
    ) == "R2"


def _seed_watchlist_candidates(config: TWStockConfig) -> None:
    from app_module.watchlist_service import WatchlistService

    service = WatchlistService(config)
    added = service.add_stocks(
        [
            {
                "stock_code": "2330",
                "stock_name": "台積電",
                "source_id": "synthetic.recommendation.R1",
                "result_id": "R1",
                "decision_date": "2026-09-10",
                "source_snapshot_id": "snap-r1",
                "source_snapshot_hash": "hash-r1",
            },
            {
                "stock_code": "2330",
                "stock_name": "台積電",
                "source_id": "synthetic.recommendation.R2",
                "result_id": "R2",
                "decision_date": "2026-09-11",
                "source_snapshot_id": "snap-r2",
                "source_snapshot_hash": "hash-r2",
            },
        ],
        source="recommendation",
    )
    assert added == 2


def _seed_evidence(
    config: TWStockConfig,
    result_id: str,
    *,
    source_snapshot_id: str,
    source_snapshot_hash: str,
    five_day_outcome_status: EvidenceOutcomeStatus = (
        EvidenceOutcomeStatus.INSUFFICIENT_FUTURE_DATA
    ),
) -> None:
    repository = EvidenceEventRepository(config, db_path=config.db_file)
    event_id = f"evt-{result_id}-2330"
    event = repository.insert_event(
        EvidenceEvent(
            event_id=event_id,
            event_hash=f"sha256:{event_id}",
            event_date=DECISION_DATE,
            decision_date=DECISION_DATE,
            symbol="2330",
            event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
            event_family="recommendation",
            source_type="recommendation_result",
            source_id=result_id,
            source_snapshot_id=source_snapshot_id,
            strategy_version_id="cross-page-strategy-v1",
            profile_id="cross-page-fixture",
            data_quality=EvidenceDataQuality.OBSERVED,
            as_of_date=DECISION_DATE,
            available_date=f"{DECISION_DATE}T09:01:00+08:00",
            source_version="cross-page-fixture-v1",
            metadata={
                "source_result_id": result_id,
                "source_snapshot_hash": source_snapshot_hash,
                "is_execution_pnl": False,
                "fixture_boundary": "synthetic_research_only",
            },
            created_at=f"{DECISION_DATE}T09:01:00+08:00",
        )
    )
    repository.upsert_outcome(
        EvidenceOutcome(
            outcome_id=f"out-{event_id}-5",
            event_id=event.event_id,
            window_days=5,
            forward_return_bp=120,
            outcome_status=five_day_outcome_status,
            data_quality=EvidenceDataQuality.OBSERVED,
            event_price_date=DECISION_DATE,
            outcome_price_date=(
                "2026-09-17"
                if five_day_outcome_status == EvidenceOutcomeStatus.READY
                else None
            ),
            data_as_of_date=(
                "2026-09-17"
                if five_day_outcome_status == EvidenceOutcomeStatus.READY
                else None
            ),
            calculated_at="2026-09-17T18:00:00+08:00",
            metadata={"is_execution_pnl": False},
        )
    )
    repository.upsert_outcome(
        EvidenceOutcome(
            outcome_id=f"out-{event_id}-10",
            event_id=event.event_id,
            window_days=10,
            outcome_status=EvidenceOutcomeStatus.PENDING,
            data_quality=EvidenceDataQuality.OBSERVED,
            calculated_at="2026-09-17T18:00:00+08:00",
            metadata={"is_execution_pnl": False},
        )
    )


def _seed_continuity(config: TWStockConfig, result_id: str, *, snapshot_id: str, snapshot_hash: str) -> str:
    controller = DecisionContinuityController(JournalService(config))
    identity = DecisionIdentity(
        result_id=result_id,
        stock_code="2330",
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot_hash,
        decision_date=DECISION_DATE,
        identity_status="linked",
    )
    accepted = controller.accept(identity, request_id=f"accept-{result_id}")
    assert accepted.success is True
    next_review = (datetime.now(TAIPEI) + timedelta(hours=2)).isoformat(timespec="seconds")
    scheduled = controller.schedule_review(
        identity,
        next_review_at=next_review,
        request_id=f"schedule-{result_id}",
    )
    assert scheduled.success is True
    return next_review


def _industry_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "排名": 1,
                "產業名稱": "半導體",
                "產業層級": "leaf",
                "5日漲幅%": 3.2,
                "20日漲幅%": 8.4,
                "5日超額%": 2.1,
                "20日超額%": 4.7,
                "5日覆蓋率%": 0.82,
                "20日覆蓋率%": 0.76,
                "代表股票": "2330 台積電",
                "代表股票代號": "2330",
                "代表股票名稱": "台積電",
                "資料品質": "observed",
                "資料日": DECISION_DATE,
                "資料來源": "synthetic.industry.fixture",
                "資料版本": "fixture-v1",
                "映射來源": "synthetic.mapping.fixture",
                "映射版本": "mapping-v1",
                "映射觀測日": DECISION_DATE,
            }
        ]
    )


def _recommendation_market_frame() -> pd.DataFrame:
    """Minimal historical frame for the real RecommendationService producer."""

    return pd.DataFrame(
        [
            {
                "日期": day,
                "available_date": day,
                "證券代號": "2330",
                "證券名稱": "台積電",
                "收盤價": 1000.0 + index,
                "成交股數": 1_000_000 + index,
                "漲幅%": 1.2,
                "成交量變化率%": 5.0,
            }
            for index, day in enumerate(
                pd.date_range("2026-08-22", periods=20, freq="D")
            )
        ]
    )


class _CrossPageRecommendationMarketFrameProvider:
    """Named provider keeps the producer source trace readable in the fixture."""

    def __call__(self) -> pd.DataFrame:
        return _recommendation_market_frame()


def _wait_portfolio_ready(window: MainWindow) -> None:
    view = window.portfolio_view
    _wait_for(lambda: getattr(view, "_refresh_worker", None) is None)
    _wait_for(lambda: getattr(view, "positions_model", None) is not None)


def _wait_report_ready(window: MainWindow) -> None:
    dialog = window._stock_research_report_dialog
    assert dialog is not None
    _wait_for(lambda: not dialog.is_busy())


def _click_table_row(table, row: int) -> None:
    index = table.model().index(row, 0)
    table.scrollTo(index)
    rect = table.visualRect(index)
    assert rect.isValid()
    QTest.mouseClick(table.viewport(), Qt.LeftButton, pos=rect.center())


def _context(window: MainWindow):
    snapshot = window.research_session_store.get_snapshot()
    assert snapshot.stock_context is not None
    return snapshot.stock_context


def _saved_file_paths(config: TWStockConfig, result_id: str) -> tuple[Path, ...]:
    return (
        Path(config.output_root) / "recommendation" / "runs" / f"{result_id}.json",
        Path(config.output_root) / "watchlist" / "default.json",
        Path(config.output_root) / "portfolio" / "trades.jsonl",
    )


def _hash_paths(paths: tuple[Path, ...]) -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.is_file()
    }


def test_actual_mainwindow_cross_page_decision_journey_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真 MainWindow signal／slot route 以 exact result identity 完成一輪。"""

    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")

    config = _config(tmp_path)
    _seed_saved_results(config)
    _seed_watchlist_candidates(config)
    _seed_evidence(
        config,
        "R1",
        source_snapshot_id="snap-r1",
        source_snapshot_hash="hash-r1",
    )
    _seed_evidence(
        config,
        "R2",
        source_snapshot_id="snap-r2",
        source_snapshot_hash="hash-r2",
    )
    _seed_continuity(config, "R1", snapshot_id="snap-r1", snapshot_hash="hash-r1")
    _seed_continuity(config, "R2", snapshot_id="snap-r2", snapshot_hash="hash-r2")

    app = _app()
    # The acceptance probes the real user-visible save controls without
    # opening blocking native dialogs in the offscreen process.
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        staticmethod(lambda *_args, **_kwargs: ("UI saved R3", True)),
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *_args, **_kwargs: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *_args, **_kwargs: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *_args, **_kwargs: None))

    window = MainWindow()
    window.resize(1366, 768)
    window.show()
    app.processEvents()
    try:
        # Market／Industry → Stock Research is the real MainWindow connection.
        screening = window.screening_service
        screening.get_strong_industries_dto = None
        screening.get_strong_industries = lambda *, period, top_n: _industry_frame()
        industry_index = next(
            index
            for index in range(window.market_tabs.count())
            if window.market_tabs.tabText(index) == "強勢產業"
        )
        window.left_navigation.button_for_key("market_explore").click()
        window.market_tabs.setCurrentIndex(industry_index)
        industry_view = window.market_tabs.widget(industry_index)
        industry_view.load_btn.click()
        _wait_for(lambda: industry_view.industries_model is not None and industry_view.industries_model.rowCount() == 1)
        _click_table_row(industry_view.industries_table, 0)
        industry_view.open_representative_button.click()
        _wait_for(lambda: window._stock_research_report_dialog is not None)
        _wait_report_ready(window)
        industry_context = _context(window)
        assert industry_context.stock_code == "2330"
        assert industry_context.result_id == ""
        assert industry_context.identity_status in {"", "unknown", "unlinked"}
        assert industry_context.source_workspace == "market_explore"
        assert industry_context.source_id == "synthetic.industry.fixture"
        assert industry_context.source_snapshot_id == ""

        # The report return button is a real signal path back to the source.
        window._stock_research_report_dialog.report_view.return_button.click()
        _wait_for(lambda: window._stock_research_report_dialog is None)
        assert window.left_navigation.current_key() == "market_explore"

        # Recommendation result is produced at the UI boundary and persisted
        # by the real RecommendationView save button/coordinator.
        recommendation_view = window.recommendation_view
        window.left_navigation.button_for_key("recommendation").click()
        producer_context = {
            "as_of_date": DECISION_DATE,
            "data_date": DATA_DATE,
            # RecommendationService records the concrete market-frame
            # provider in run_context.source_id; keep the declared config
            # source aligned so the read-only Journey does not manufacture a
            # source-id conflict from two truthful layers of the same run.
            "source_id": "_CrossPageRecommendationMarketFrameProvider",
            "source_kind": "synthetic_research_fixture",
            "source_snapshot_id": "snap-r3",
            "source_snapshot_hash": "hash-r3",
            "profile_id": "cross-page-fixture",
            "profile_version": "fixture-v1",
            "strategy_version_id": "cross-page-strategy-v1",
            "regime": "Trend",
            "regime_confidence": 0.5,
            "recommendation_ranking": {"threshold_mode": "fixed"},
        }
        recommendation_service = recommendation_view.recommendation_service
        recommendation_service.market_data_provider = _CrossPageRecommendationMarketFrameProvider()
        recommendation_service.industry_mapper.get_stock_industries = lambda _code: []
        recommendation_service.strategy_configurator.generate_recommendations = (
            lambda _stock_df, _config: pd.DataFrame(
                {
                    "FinalScore": [91.0],
                    "TotalScore": [91.0],
                    "收盤價": [Decimal("1000")],
                    "成交股數": [1_000_000],
                    "IndicatorScore": [31.0],
                    "PatternScore": [30.0],
                    "VolumeScore": [30.0],
                }
            )
        )
        produced_recommendations = recommendation_service.run_recommendation(
            dict(producer_context),
            max_stocks=1,
            top_n=1,
            as_of_date=DECISION_DATE,
            universe=["2330"],
        )
        assert len(produced_recommendations) == 1
        assert str(recommendation_service.last_run_context["result_id"]).startswith("rec_")
        recommendation_view.current_config = dict(producer_context)
        recommendation_view.current_regime = "Trend"
        recommendation_view._on_recommendation_finished(produced_recommendations)
        assert recommendation_view.save_result_btn.isVisible()
        recommendation_view.results_table.selectRow(0)
        recommendation_view.save_result_btn.click()
        saved_id = str(recommendation_view.current_result_id).strip()
        assert saved_id
        saved_result_path = output_root / "recommendation" / "runs" / f"{saved_id}.json"
        assert saved_result_path.is_file()
        saved_payload = json.loads(saved_result_path.read_text(encoding="utf-8"))
        assert saved_payload["result_id"] == saved_id
        assert saved_payload["run_context"]["result_id"] == saved_id
        assert saved_payload["config"]["source_snapshot_hash"] == "hash-r3"
        assert saved_payload["recommendations"][0].get("證券代號") == "2330"

        # The real RecommendationView add button writes a typed Watchlist
        # candidate; no stock/date/latest fallback is involved.
        recommendation_view.add_to_watchlist_btn.click()
        watchlist_view = window.watchlist_view
        window.left_navigation.button_for_key("watchlist").click()
        _wait_for(lambda: watchlist_view.stocks_model is not None)
        watch_rows = watchlist_view.stocks_model.getDataFrame()
        assert len(watch_rows) == 3
        assert watchlist_view.select_stock("2330", "R1") is True
        r1_row = watchlist_view.stocks_table.currentIndex().row()
        r1_identity = watchlist_view._row_decision_identity(
            watch_rows.iloc[r1_row],
            "2330",
        )
        assert r1_identity.result_id == "R1"
        assert watchlist_view.select_stock("2330", "R2") is True
        r2_row = watchlist_view.stocks_table.currentIndex().row()
        r2_identity = watchlist_view._row_decision_identity(
            watch_rows.iloc[r2_row],
            "2330",
        )
        assert r2_identity.result_id == "R2"
        assert r1_row != r2_row
        watchlist_view.stock_research_btn.click()
        _wait_report_ready(window)
        watch_context = _context(window)
        assert watch_context.result_id == "R2"
        assert watch_context.stock_code == "2330"
        assert watch_context.decision_date == "2026-09-11"
        assert watch_context.source_snapshot_id == "snap-r2"
        assert watch_context.source_snapshot_hash == "hash-r2"
        assert watch_context.source_workspace == "watchlist"
        window._stock_research_report_dialog.report_view.return_button.click()
        _wait_for(lambda: window._stock_research_report_dialog is None)
        assert watchlist_view.stocks_table.currentIndex().row() == r2_row

        # Add one synthetic recommendation-backed position through the fixture
        # store, then traverse the real PortfolioView button route.
        portfolio_service = window.portfolio_service
        portfolio_service.record_trade(
            stock_code="2330",
            stock_name="台積電",
            side="buy",
            quantity=100,
            price=1000,
            trade_date=DECISION_DATE,
            trade_id="cross-page-trade-r3",
            source_type="recommendation_result",
            source_id=saved_id,
            source_snapshot_hash="hash-r3",
            source_summary={
                "result_id": saved_id,
                "stock_code": "2330",
                "decision_date": DECISION_DATE,
                "source_snapshot_id": "snap-r3",
                "source_snapshot_hash": "hash-r3",
                "fixture_boundary": "synthetic_research_only",
            },
        )
        portfolio_view = window.portfolio_view
        window.left_navigation.button_for_key("portfolio").click()
        _wait_portfolio_ready(window)
        assert portfolio_view.select_stock("2330", saved_id) is True
        portfolio_view.btn_stock_research.click()
        _wait_report_ready(window)
        portfolio_context = _context(window)
        assert portfolio_context.result_id == saved_id
        assert portfolio_context.stock_code == "2330"
        assert portfolio_context.decision_date == DECISION_DATE
        assert portfolio_context.source_snapshot_id == "snap-r3"
        assert portfolio_context.source_snapshot_hash == "hash-r3"
        assert portfolio_context.source_workspace == "portfolio"
        window._stock_research_report_dialog.report_view.return_button.click()
        _wait_for(lambda: window._stock_research_report_dialog is None)
        assert portfolio_view.selected_stock_code == "2330"

        # After the result has been saved, append its Evidence and initial
        # continuity head, then refresh the actual Workbench through its button.
        _seed_evidence(
            config,
            saved_id,
            source_snapshot_id="snap-r3",
            source_snapshot_hash="hash-r3",
        )
        next_review = _seed_continuity(
            config,
            saved_id,
            snapshot_id="snap-r3",
            snapshot_hash="hash-r3",
        )
        read_only_paths = _saved_file_paths(config, saved_id)
        before_read_only = _hash_paths(read_only_paths)
        workbench_view = window.workbench_view
        window.left_navigation.button_for_key("workbench").click()
        workbench_view.refresh_button.click()
        _wait_for(
            lambda: any(
                getattr(workbench_view.review_model.row_at(row), "candidate_key", "")
                == f"{saved_id}:2330"
                for row in range(workbench_view.review_model.rowCount())
            )
        )
        saved_row = next(
            row
            for row in range(workbench_view.review_model.rowCount())
            if workbench_view.review_model.row_at(row).candidate_key == f"{saved_id}:2330"
        )
        _click_table_row(workbench_view.review_table, saved_row)
        workbench_view._show_model_row_detail(workbench_view.review_model, saved_row)
        assert workbench_view.review_model.row_at(saved_row).candidate_key == f"{saved_id}:2330"
        assert saved_id in workbench_view.detail_body_label.text()
        rect = workbench_view.review_table.visualRect(
            workbench_view.review_model.index(saved_row, 0)
        )
        assert rect.isValid()
        QTest.mouseDClick(
            workbench_view.review_table.viewport(),
            Qt.LeftButton,
            pos=rect.center(),
        )
        _wait_for(lambda: window._stock_research_report_dialog is not None)
        _wait_report_ready(window)
        workbench_context = _context(window)
        assert workbench_context.result_id == saved_id
        assert workbench_context.stock_code == "2330"
        assert workbench_context.source_snapshot_id == "snap-r3"
        assert workbench_context.source_snapshot_hash == "hash-r3"
        assert workbench_context.source_workspace == "workbench"
        dialog = window._stock_research_report_dialog
        assert dialog.journey_view is not None
        _wait_for(lambda: dialog.journey_view.journey is not None)
        controls = dialog.journey_view.continuity_controls
        assert controls is not None
        assert controls.identity is not None
        assert controls.identity.candidate_key == (saved_id, "2330")
        assert controls.state is not None
        assert controls.state.next_review_at == next_review

        # Report/Journey/Workbench/Portfolio reads must not mutate the saved
        # result, watchlist, or portfolio fixture.
        assert _hash_paths(read_only_paths) == before_read_only

        # The only write in this journey is an explicit review action from the
        # shared Journey controls; it remains research-only and never places an order.
        second_review = (datetime.now(TAIPEI) + timedelta(hours=3)).replace(microsecond=0)
        controls.review_datetime.setDateTime(
            QDateTime.fromString(
                second_review.strftime("%Y-%m-%d %H:%M:%S"),
                "yyyy-MM-dd HH:mm:ss",
            )
        )
        journal_path = output_root / "portfolio" / "journal_entries.jsonl"
        journal_before_review = journal_path.read_bytes()
        controls.review_button.click()
        assert controls.state is not None
        assert controls.state.next_review_at == second_review.isoformat()
        assert journal_path.read_bytes() != journal_before_review
        assert _hash_paths(read_only_paths) == before_read_only

        readback_receipt_path = Path(
            os.environ.get(
                "CROSS_PAGE_READBACK_RECEIPT_PATH",
                str(tmp_path / "cross_page_mainwindow_readback_receipt.json"),
            )
        ).expanduser().resolve()
        readback = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "qa_cross_page_mainwindow_readback.py"),
                "--data-root",
                str(data_root),
                "--output-root",
                str(output_root),
                "--result-id",
                saved_id,
                "--receipt",
                str(readback_receipt_path),
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        assert readback.returncode == 0, readback.stderr
        readback_payload = json.loads(readback_receipt_path.read_text(encoding="utf-8"))
        assert readback_payload["persisted_readback"] is True
        assert readback_payload["persisted_identity_consistent"] is True
        assert readback_payload["main_window_recreated"] is True
        assert readback_payload["report_loaded"] is True
        assert readback_payload["journey_loaded"] is True
        assert readback_payload["dialog_finished"] is True
        assert readback_payload["exact_identity_visible"] is True
        persisted_identity = readback_payload["persisted_identity"]
        assert persisted_identity["result"] == {
            "result_id": saved_id,
            "stock_code": "2330",
            "decision_date": DECISION_DATE,
            "data_date": DATA_DATE,
            "source_snapshot_id": "snap-r3",
            "source_snapshot_hash": "hash-r3",
        }
        assert persisted_identity["watchlist"] == {
            "result_id": saved_id,
            "stock_code": "2330",
            "decision_date": DECISION_DATE,
            "source_snapshot_id": "snap-r3",
            "source_snapshot_hash": "hash-r3",
        }
        assert persisted_identity["portfolio_trade"] == {
            "result_id": saved_id,
            "stock_code": "2330",
            "decision_date": DECISION_DATE,
            "source_snapshot_id": "snap-r3",
            "source_snapshot_hash": "hash-r3",
        }
        assert persisted_identity["continuity"] == {
            "result_id": saved_id,
            "stock_code": "2330",
            "decision_date": DECISION_DATE,
            "source_snapshot_id": "snap-r3",
            "source_snapshot_hash": "hash-r3",
            "next_review_at": second_review.isoformat(),
        }
        assert persisted_identity["candidate_key"] == f"{saved_id}:2330"
        assert readback_payload["rendered_identity"]["report_context"] == {
            "result_id": saved_id,
            "stock_code": "2330",
            "decision_date": DECISION_DATE,
            "data_date": DATA_DATE,
            "source_snapshot_id": "snap-r3",
            "source_snapshot_hash": "hash-r3",
        }
        assert readback_payload["rendered_identity"]["journey_context"] == {
            "result_id": saved_id,
            "stock_code": "2330",
            "decision_date": DECISION_DATE,
            "data_date": DATA_DATE,
            "source_snapshot_id": "snap-r3",
            "source_snapshot_hash": "hash-r3",
        }
        assert readback_payload["rendered_identity"]["journey"]["candidate_found"] is True
        assert readback_payload["rendered_identity"]["journey"]["candidate_key"] == [
            saved_id,
            "2330",
        ]
        assert readback_payload["rendered_identity"]["journey"]["source_snapshot_hash"] == "hash-r3"
        assert readback_payload["rendered_identity"]["journey_controls"] == {
            "candidate_key": [saved_id, "2330"],
            "identity_status": "linked",
            "next_review_at": second_review.isoformat(),
            "status_text": f"研究狀態：已納入研究｜筆記：0 筆｜下次檢視：{second_review.isoformat()}｜歷史：3 筆",
            "accept_enabled": True,
        }

        manifest_path = tmp_path / "cross_page_decision_journey_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "fixture_boundary": {
                        "market_industry": "synthetic_research_only",
                        "recommendation": "synthetic UI producer fixture; saved through production RecommendationView",
                        "portfolio": "synthetic research position; no broker order",
                        "paper": "not asserted as formal credit",
                        "user_declared": "not asserted as Recommendation identity",
                    },
                    "identity": {
                        "result_id": saved_id,
                        "stock_code": "2330",
                        "decision_date": DECISION_DATE,
                        "data_date": DATA_DATE,
                        "source_snapshot_id": "snap-r3",
                        "source_snapshot_hash": "hash-r3",
                    },
                    "stages": [
                        "market_industry",
                        "stock_research_unlinked",
                        "recommendation_save",
                        "watchlist_exact_result",
                        "portfolio_exact_result",
                        "workbench_exact_continuity",
                        "journey_review_action",
                        "independent_mainwindow_readback",
                    ],
                    "read_only_hashes_before_review": before_read_only,
                    "readback": readback_payload,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        assert manifest_path.is_file()
    finally:
        dialog = window._stock_research_report_dialog
        if dialog is not None:
            try:
                dialog.close()
            except RuntimeError:
                dialog = None
            if dialog is not None:
                _wait_for(
                    lambda: _qt_widget_not_visible(dialog),
                    timeout_ms=12_000,
                )
        try:
            window_visible = window.isVisible()
        except RuntimeError:
            window_visible = False
        if window_visible:
            window.close()
            _wait_for(lambda: _qt_widget_not_visible(window), timeout_ms=12_000)
        _drain_qt_deferred_deletes(app, (window,))


def test_actual_mainwindow_journey_fail_closed_for_missing_future_and_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真 MainWindow 不以同股替代、未成熟結果或 conflict 允許研究動作。"""

    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("OUTPUT_ROOT", str(output_root))

    config = _config(tmp_path)
    _seed_saved_results(config)
    _seed_evidence(
        config,
        "R1",
        source_snapshot_id="snap-r1",
        source_snapshot_hash="hash-r1",
    )
    _seed_continuity(config, "R1", snapshot_id="snap-r1", snapshot_hash="hash-r1")

    app = _app()
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *_args, **_kwargs: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *_args, **_kwargs: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *_args, **_kwargs: None))

    window = MainWindow()
    window.show()

    def close_dialog() -> None:
        dialog = window._stock_research_report_dialog
        if dialog is None:
            return
        try:
            dialog.close()
        except RuntimeError:
            return
        _wait_for(lambda: _qt_widget_not_visible(dialog))
        _wait_for(lambda: window._stock_research_report_dialog is None)

    try:
        # A saved result for 2330 must not be substituted for a requested
        # 1101 candidate under the same result id.
        window._open_stock_research_context(
            window._coerce_stock_research_context(
                {
                    "stock_code": "1101",
                    "stock_name": "不存在於 R1 的標的",
                    "result_id": "R1",
                    "decision_date": DECISION_DATE,
                    "identity_status": "linked",
                    "source_workspace": "recommendation",
                }
            )
        )
        _wait_report_ready(window)
        dialog = window._stock_research_report_dialog
        assert dialog is not None and dialog.journey_view is not None
        journey_view = dialog.journey_view
        _wait_for(
            lambda: journey_view.journey is not None
            or "沒有 1101 的候選" in journey_view.status_label.text()
        )
        assert journey_view.journey is not None
        assert "沒有 1101 的候選" in journey_view.status_label.text()
        assert journey_view.status_badge.text() == "注意"
        controls = journey_view.continuity_controls
        assert controls is not None
        assert not controls.accept_button.isEnabled()
        assert not controls.skip_button.isEnabled()
        assert not controls.note_button.isEnabled()
        assert not controls.review_button.isEnabled()
        close_dialog()

        # Evidence exists, but its outcome is explicitly not mature because
        # the fixture has no sufficient future observation yet.
        window._open_stock_research_context(
            window._coerce_stock_research_context(
                {
                    "stock_code": "2330",
                    "stock_name": "台積電",
                    "result_id": "R1",
                    "decision_date": DECISION_DATE,
                    "data_date": DATA_DATE,
                    "identity_status": "linked",
                    "source_snapshot_id": "snap-r1",
                    "source_snapshot_hash": "hash-r1",
                    "source_workspace": "recommendation",
                }
            )
        )
        _wait_report_ready(window)
        dialog = window._stock_research_report_dialog
        assert dialog is not None and dialog.journey_view is not None
        journey_view = dialog.journey_view
        _wait_for(lambda: journey_view.journey is not None)
        assert "尚待結果成熟" in journey_view.status_label.text()
        maturity_model = journey_view.maturity_table.model()
        outcome_statuses = {
            maturity_model.index(row, 2).data()
            for row in range(maturity_model.rowCount())
        }
        assert "待成熟（未有足夠未來資料）" in outcome_statuses
        assert "來源已標示 ready" not in outcome_statuses
        controls = journey_view.continuity_controls
        assert controls is not None
        assert controls.identity is not None
        assert controls.identity.candidate_key == ("R1", "2330")
        assert controls.accept_button.isEnabled()
        close_dialog()

        # An explicitly conflicting context never starts a journey join and
        # remains visibly blocked, even though the report itself can load.
        window._open_stock_research_context(
            window._coerce_stock_research_context(
                {
                    "stock_code": "2330",
                    "stock_name": "台積電",
                    "result_id": "R1",
                    "decision_date": DECISION_DATE,
                    "identity_status": "conflict",
                    "source_snapshot_id": "snap-conflict",
                    "source_snapshot_hash": "hash-conflict",
                    "source_workspace": "recommendation",
                }
            )
        )
        _wait_report_ready(window)
        dialog = window._stock_research_report_dialog
        assert dialog is not None and dialog.journey_view is not None
        journey_view = dialog.journey_view
        _wait_for(lambda: "identity 衝突" in journey_view.status_label.text())
        assert journey_view.journey is None
        assert journey_view.status_badge.text() == "衝突"
        controls = journey_view.continuity_controls
        assert controls is not None
        assert not controls.accept_button.isEnabled()
        assert not controls.skip_button.isEnabled()
        assert not controls.note_button.isEnabled()
        assert not controls.review_button.isEnabled()
    finally:
        dialog = window._stock_research_report_dialog
        if dialog is not None:
            try:
                dialog.close()
            except RuntimeError:
                dialog = None
            if dialog is not None:
                _wait_for(
                    lambda: _qt_widget_not_visible(dialog),
                    timeout_ms=12_000,
                )
        try:
            window_visible = window.isVisible()
        except RuntimeError:
            window_visible = False
        if window_visible:
            window.close()
            _wait_for(lambda: _qt_widget_not_visible(window), timeout_ms=12_000)
        _drain_qt_deferred_deletes(app, (window,))


def test_portfolio_exact_route_keeps_same_stock_positions_separate(
    tmp_path: Path,
) -> None:
    """同股多 position 時，真 Portfolio 按鈕不取第一列。"""

    app = _app()
    config = _config(tmp_path)
    repository = RecommendationRepository(config)
    for result_id, date_value, snapshot in (
        ("R1", "2026-09-10", "snap-r1"),
        ("R2", "2026-09-11", "snap-r2"),
    ):
        repository.save_result(
            _recommendation(
                result_id,
                decision_date=date_value,
                source_snapshot_id=snapshot,
                source_snapshot_hash=f"hash-{result_id.lower()}",
            )
        )

    from app_module.dtos.portfolio_dtos import PortfolioDTO, PositionDTO
    from ui_qt.views.portfolio_view import PortfolioView

    class PortfolioFixture:
        def __init__(self) -> None:
            self.config = config
            self.positions = [
                PositionDTO(
                    position_id="position-r1",
                    portfolio_id="default",
                    stock_code="2330",
                    stock_name="台積電 R1",
                    quantity=100,
                    average_cost=1000,
                    invested_amount=100000,
                    source_type="recommendation_result",
                    source_id="R1",
                    source_snapshot_hash="hash-r1",
                    source_summary={
                        "result_id": "R1",
                        "stock_code": "2330",
                        "decision_date": "2026-09-10",
                        "source_snapshot_id": "snap-r1",
                    },
                ),
                PositionDTO(
                    position_id="position-r2",
                    portfolio_id="default",
                    stock_code="2330",
                    stock_name="台積電 R2",
                    quantity=200,
                    average_cost=1000,
                    invested_amount=200000,
                    source_type="recommendation_result",
                    source_id="R2",
                    source_snapshot_hash="hash-r2",
                    source_summary={
                        "result_id": "R2",
                        "stock_code": "2330",
                        "decision_date": "2026-09-11",
                        "source_snapshot_id": "snap-r2",
                    },
                ),
            ]

        def get_portfolio(self):
            return PortfolioDTO(
                portfolio_id="default",
                portfolio_name="fixture",
                total_positions=2,
                active_positions=2,
                positions=list(self.positions),
                updated_at="2026-09-15T10:00:00+08:00",
            )

        def list_trades(self):
            return []

        def get_current_price(self, _stock_code):
            return None

    view = PortfolioView(
        portfolio_service=PortfolioFixture(),
        journal_service=JournalService(config),
        async_refresh=False,
    )
    emitted: list[object] = []
    view.stockResearchRequested.connect(emitted.append)
    try:
        assert view.positions_model is not None
        assert view.select_stock("2330", "R2") is True
        view.btn_stock_research.click()
        assert len(emitted) == 1
        context = emitted[0]
        assert context.result_id == "R2"
        assert context.stock_name == "台積電 R2"
        assert context.decision_date == "2026-09-11"
        assert context.source_snapshot_id == "snap-r2"
    finally:
        view.close()
        view.deleteLater()
        app.processEvents()


def test_portfolio_bilingual_saved_stock_alias_conflict_fails_closed(
    tmp_path: Path,
) -> None:
    """雙語 saved stock alias 缺一可相容，但同列矛盾不得 promotion。"""

    config = _config(tmp_path)
    repository = RecommendationRepository(config)
    assert repository.save_result(
        _recommendation(
            "R1",
            decision_date=DECISION_DATE,
            source_snapshot_id="snap-r1",
            source_snapshot_hash="hash-r1",
        )
    ) == "R1"
    saved_result_path = config.output_root / "recommendation" / "runs" / "R1.json"
    payload = json.loads(saved_result_path.read_text(encoding="utf-8"))
    row = payload["recommendations"][0]
    valid_row = dict(row)

    from ui_qt.views.portfolio_view import PortfolioView

    view = PortfolioView.__new__(PortfolioView)
    view.portfolio_service = SimpleNamespace(config=config)
    position = SimpleNamespace(
        source_type="recommendation_result",
        source_id="R1",
        source_summary={
            "result_id": "R1",
            "stock_code": "2330",
        },
    )

    # Existing Chinese-only persisted rows remain compatible.
    assert view._validated_recommendation_result_id(position, "2330") == "R1"

    # A legacy/alternate English-only row remains compatible as well.
    row.pop("證券代號", None)
    row["stock_code"] = "2330"
    saved_result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert view._validated_recommendation_result_id(position, "2330") == "R1"

    # Both aliases present but disagreeing is ambiguous and must stay unlinked.
    row["證券代號"] = "2330"
    row["stock_code"] = "1101"
    saved_result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert view._validated_recommendation_result_id(position, "2330") == ""

    # A valid 2330 row cannot hide another row whose aliases also claim 2330
    # but disagree; the requested candidate remains ambiguous.
    payload["recommendations"] = [
        dict(valid_row),
        {
            **valid_row,
            "stock_code": "2330",
            "證券代號": "1101",
        },
    ]
    saved_result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert view._validated_recommendation_result_id(position, "2330") == ""

    # A conflicting row for two completely unrelated stocks does not poison
    # the requested 2330 candidate.
    payload["recommendations"] = [
        dict(valid_row),
        {
            **valid_row,
            "stock_code": "2317",
            "證券代號": "1101",
        },
    ]
    saved_result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert view._validated_recommendation_result_id(position, "2330") == "R1"
