"""隔離環境中的實際 MainWindow 跨頁決策旅程驗收。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
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
from app_module.portfolio_source_adapter import stable_snapshot_hash
from app_module.recommendation_repository import RecommendationRepository
from app_module.recommendation.contracts import ExecutionStatus
from app_module.saved_recommendation_queries import (
    build_recommendation_execution_queries,
    saved_recommendation_capture_projection,
)
from data_module.config import TWStockConfig
from ui_qt.main import MainWindow, _drain_qt_deferred_deletes
from ui_qt.views.recommendation.execution_coordinator import (
    RecommendationExecutionRequest,
)


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
        # 讓真實 Python worker 取得 GIL；Qt polling 的期限與條件不變。
        time.sleep(0.01)
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


def _canonical_test_hash(value: object) -> str:
    """以測試輸入重算保存的 canonical JSON SHA-256。"""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


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

    rows = []
    for instrument_index, (stock_code, stock_name) in enumerate(
        (("2330", "台積電"), ("2317", "鴻海"))
    ):
        for day_index, day in enumerate(
            pd.date_range("2026-08-22", periods=20, freq="D")
        ):
            rows.append(
                {
                    "日期": day,
                    "available_date": day,
                    "證券代號": stock_code,
                    "證券名稱": stock_name,
                    "收盤價": 1000.0 + instrument_index + day_index,
                    "成交股數": 1_000_000 + instrument_index + day_index,
                    "漲幅%": 1.2,
                    "成交量變化率%": 5.0,
                }
            )
    return pd.DataFrame(rows)


class _CrossPageRecommendationMarketFrameProvider:
    """Named provider keeps the producer source trace readable in the fixture."""

    def __call__(self) -> pd.DataFrame:
        return _recommendation_market_frame()


def _wait_portfolio_ready(window: MainWindow) -> None:
    view = window.portfolio_view
    _wait_for(lambda: getattr(view, "_refresh_worker", None) is None)
    _wait_for(lambda: getattr(view, "positions_model", None) is not None)


def _wait_report_ready(window: MainWindow) -> None:
    dialog = window.stock_research_workspace
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


def _saved_file_paths(
    config: TWStockConfig,
    result_id: str,
    artifact_location: str,
) -> tuple[Path, ...]:
    runs_dir = Path(config.output_root) / "recommendation" / "runs"
    return (
        runs_dir / "execution_artifacts" / artifact_location,
        runs_dir / "recommendation_runs.db",
        runs_dir / "recommendation_runs.db-wal",
        runs_dir / "recommendation_runs.db-shm",
        runs_dir / "recommendation_runs.db-journal",
        runs_dir / f"{result_id}.json",
        Path(config.output_root) / "watchlist" / "default.json",
        Path(config.output_root) / "portfolio" / "trades.jsonl",
    )


def _hash_paths(paths: tuple[Path, ...]) -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.is_file()
    }


def _close_fixture_file_handlers(
    output_root: Path,
    logger: logging.Logger,
) -> None:
    """只關閉 process-visible 且屬於本隔離 fixture 的 FileHandler。"""

    fixture_root = output_root.resolve()
    root_logger = logging.getLogger()
    loggers: dict[int, logging.Logger] = {id(root_logger): root_logger}
    for candidate in logging.Logger.manager.loggerDict.values():
        if isinstance(candidate, logging.Logger):
            loggers.setdefault(id(candidate), candidate)
    loggers.setdefault(id(logger), logger)

    owned_handlers: dict[int, logging.FileHandler] = {}
    for owner in loggers.values():
        for handler in tuple(owner.handlers):
            if not isinstance(handler, logging.FileHandler):
                continue
            try:
                handler_path = Path(handler.baseFilename).resolve()
                is_fixture_owned = handler_path.is_relative_to(fixture_root)
            except (OSError, RuntimeError, ValueError):
                continue
            if is_fixture_owned:
                owned_handlers.setdefault(id(handler), handler)

    for handler in owned_handlers.values():
        for owner in loggers.values():
            if handler in owner.handlers:
                owner.removeHandler(handler)
        handler.close()


def test_fixture_handler_cleanup_deduplicates_owned_handlers_and_keeps_external_open(
    tmp_path: Path,
) -> None:
    class _CountingFileHandler(logging.FileHandler):
        def __init__(self, filename: Path) -> None:
            self.close_calls = 0
            super().__init__(filename, mode="a", encoding="utf-8")

        def close(self) -> None:
            self.close_calls += 1
            super().close()

    output_root = tmp_path / "isolated-output"
    owned_path = (
        output_root / "application_state" / "logs" / "technical_calculation.log"
    )
    external_path = tmp_path / "external.log"
    owned_path.parent.mkdir(parents=True)

    owned_handler = _CountingFileHandler(owned_path)
    external_handler = logging.FileHandler(external_path, mode="a", encoding="utf-8")
    config_logger = logging.getLogger("data_module.config")
    duplicate_logger = logging.getLogger(
        f"tests.fixture_handler_cleanup.{id(owned_handler)}"
    )
    config_logger.addHandler(owned_handler)
    duplicate_logger.addHandler(owned_handler)
    config_logger.addHandler(external_handler)
    try:
        _close_fixture_file_handlers(output_root, config_logger)

        assert owned_handler.close_calls == 1
        assert owned_handler not in config_logger.handlers
        assert owned_handler not in duplicate_logger.handlers
        assert external_handler in config_logger.handlers
        assert external_handler.stream is not None
        external_handler.stream.write("external handler remains writable\n")
        external_handler.flush()
        assert external_path.read_text(encoding="utf-8") == (
            "external handler remains writable\n"
        )
    finally:
        if owned_handler in config_logger.handlers:
            config_logger.removeHandler(owned_handler)
        if owned_handler in duplicate_logger.handlers:
            duplicate_logger.removeHandler(owned_handler)
        if external_handler in config_logger.handlers:
            config_logger.removeHandler(external_handler)
        owned_handler.close()
        external_handler.close()
        logging.Logger.manager.loggerDict.pop(duplicate_logger.name, None)


def test_actual_mainwindow_cross_page_decision_journey_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """真 MainWindow signal／slot route 以 exact result identity 完成一輪。"""

    data_root = tmp_path / "data"
    # Windows canonical readback holds no-follow handles for every ancestor of
    # the legacy runs root; pytest's AppData TEMP may contain an unopenable
    # reparse ancestor, so keep this isolated output tree under the repo.
    isolated_output = TemporaryDirectory(
        prefix=".tmp_cpj_",
        dir=Path.cwd(),
    )
    output_root = Path(isolated_output.name).resolve()

    config_logger: logging.Logger | None = None

    def cleanup_isolated_output() -> None:
        if config_logger is not None:
            _close_fixture_file_handlers(output_root, config_logger)
        isolated_output.cleanup()

    request.addfinalizer(cleanup_isolated_output)
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")

    config = TWStockConfig(data_root=data_root, output_root=output_root)
    config_logger = config.logger
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
    override_reason = "研究後發現原判斷條件已改變。"
    monkeypatch.setattr(
        QInputDialog,
        "getMultiLineText",
        staticmethod(lambda *_args, **_kwargs: (override_reason, True)),
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *_args, **_kwargs: None))
    warning_messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(
            lambda _parent, title, message: warning_messages.append(
                (str(title), str(message))
            )
        ),
    )
    critical_messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(
            lambda _parent, title, message: critical_messages.append(
                (str(title), str(message))
            )
        ),
    )

    def reject_blocking_message_box(_dialog: QMessageBox) -> int:
        pytest.fail("跨頁 Journey 不應進入阻塞式 QMessageBox.exec")

    monkeypatch.setattr(QMessageBox, "exec", reject_blocking_message_box)

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
        _wait_for(lambda: window.stock_research_workspace is not None)
        _wait_report_ready(window)
        industry_context = _context(window)
        assert industry_context.stock_code == "2330"
        assert industry_context.result_id == ""
        assert industry_context.identity_status in {"", "unknown", "unlinked"}
        assert industry_context.source_workspace == "market_explore"
        assert industry_context.source_id == "synthetic.industry.fixture"
        assert industry_context.source_snapshot_id == ""

        # The report return button is a real signal path back to the source.
        window.stock_research_workspace.report_view.return_button.click()
        _wait_for(lambda: window.workspace_stack.currentWidget() is not window.stock_research_workspace)
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
        def score_candidate(stock_df: pd.DataFrame, _config: dict) -> pd.DataFrame:
            score = 91.0 if str(stock_df.iloc[-1]["證券代號"]) == "2330" else 70.0
            return pd.DataFrame(
                {
                    "FinalScore": [score],
                    "TotalScore": [score],
                    "收盤價": [Decimal("1000")],
                    "成交股數": [1_000_000],
                    "IndicatorScore": [score - 60.0],
                    "PatternScore": [30.0],
                    "VolumeScore": [30.0],
                }
            )

        recommendation_service.strategy_configurator.generate_recommendations = (
            score_candidate
        )
        execution_request = RecommendationExecutionRequest(
            dict(producer_context),
            max_stocks=2,
            top_n=1,
        )
        invocation_policy = recommendation_view._personal_policy_for_invocation()
        invocation_service = recommendation_service.with_personal_use_policy(
            invocation_policy
        )
        execution = execution_request.execute(invocation_service)
        assert execution.status is ExecutionStatus.COMPLETED
        assert any(
            event.event_type == "personal_use_policy_snapshot"
            for event in execution.events
        )
        assert len(execution.items) == 1
        assert execution.items[0].stock_code == "2330"
        assert execution.result_id.startswith("rec_")
        universe_identity = execution.context.universe_identity
        assert universe_identity is not None
        universe_snapshot = universe_identity.snapshot
        assert universe_snapshot is not None
        universe_snapshot_spec = json.loads(
            universe_snapshot.universe_snapshot_spec_json
        )
        assert universe_snapshot_spec["selected_codes"] == ["2317", "2330"]
        assert universe_snapshot_spec["selected_count"] == 2
        assert universe_snapshot_spec["decision_date"] == DECISION_DATE
        assert universe_snapshot_spec["source_provider_id"] == (
            "_CrossPageRecommendationMarketFrameProvider"
        )
        assert universe_snapshot.universe_snapshot_source_provider_id == (
            "_CrossPageRecommendationMarketFrameProvider"
        )
        assert universe_snapshot.universe_snapshot_selected_codes_hash == (
            _canonical_test_hash({"selected_codes": ["2317", "2330"]})
        )
        assert universe_snapshot.universe_snapshot_hash == _canonical_test_hash(
            universe_snapshot_spec
        )
        assert universe_snapshot.universe_snapshot_id == (
            "recommendation-universe-snapshot-v1:"
            + universe_snapshot.universe_snapshot_hash.removeprefix("sha256:")
        )
        request_config = json.loads(
            execution.request.config_snapshot.raw_config_json
        )
        assert request_config["source_id"] == (
            universe_snapshot.universe_snapshot_source_provider_id
        )
        assert "source_snapshot_id" not in request_config
        assert "source_snapshot_hash" not in request_config
        canonical_snapshot_id = universe_snapshot.universe_snapshot_id
        canonical_snapshot_hash = universe_snapshot.universe_snapshot_hash
        recommendation_view._on_recommendation_finished(execution)
        assert recommendation_view.save_result_btn.isVisible()
        assert recommendation_view.add_to_watchlist_btn.isHidden() is False
        assert not recommendation_view.add_to_watchlist_btn.isEnabled()
        recommendation_view.results_table.selectRow(0)
        watchlist_service = window.watchlist_service
        before_unsaved_add = watchlist_service.get_default_watchlist()
        assert before_unsaved_add is not None
        before_unsaved_identities = [
            item.decision_identity.to_dict() for item in before_unsaved_add.items
        ]
        # 直接走按鈕共用的 slot；右鍵入口也委派至相同 handler，必須同樣拒絕。
        recommendation_view._add_selected_to_watchlist()
        after_unsaved_add = watchlist_service.get_default_watchlist()
        assert after_unsaved_add is not None
        assert [item.decision_identity.to_dict() for item in after_unsaved_add.items] == (
            before_unsaved_identities
        )
        assert warning_messages[-1][0] == "尚未驗證保存結果"

        recommendation_view.save_result_btn.click()
        saved_id = str(recommendation_view.current_result_id).strip()
        assert saved_id, critical_messages[-1] if critical_messages else recommendation_view.result_status_label.text()
        assert recommendation_view._verified_saved_result_id() == saved_id
        assert recommendation_view.add_to_watchlist_btn.isEnabled()
        assert "尚未執行評估" in recommendation_view.personal_model_assessment_status_label.text()
        saved_queries = build_recommendation_execution_queries(config)
        saved_read_model = saved_queries.get(saved_id)
        assert saved_read_model is not None
        assert saved_read_model.execution == execution
        assert saved_read_model.execution.status is ExecutionStatus.COMPLETED
        assert saved_read_model.result_id == saved_id
        assert saved_read_model.integrity_basis == "canonical_payload_and_index_verified"
        saved_projection = saved_recommendation_capture_projection(saved_read_model)
        assert saved_projection["result_id"] == saved_id
        assert saved_projection["recommendations_count"] == 1
        assert [item.stock_code for item in saved_read_model.execution.items] == ["2330"]
        from scripts.qa_cross_page_mainwindow_readback import _canonical_identity_facts

        assert _canonical_identity_facts(saved_read_model.execution)[
            "universe_snapshot_id"
        ] == canonical_snapshot_id
        tampered_selected_item = replace(
            saved_read_model.execution.items[0],
            stock_code="9999",
        )
        assert saved_read_model.execution.decision is not None
        tampered_execution = replace(
            saved_read_model.execution,
            decision=replace(
                saved_read_model.execution.decision,
                items=(tampered_selected_item,),
            ),
        )
        with pytest.raises(ValueError, match="input universe or execution items"):
            _canonical_identity_facts(tampered_execution)
        legacy_r3_path = (
            Path(config.output_root)
            / "recommendation"
            / "runs"
            / f"{saved_id}.json"
        )
        assert not legacy_r3_path.exists()

        # The real RecommendationView add button writes a typed Watchlist
        # candidate; no stock/date/latest fallback is involved.
        recommendation_view.add_to_watchlist_btn.click()
        stored_watchlist = watchlist_service.get_default_watchlist()
        assert stored_watchlist is not None
        saved_watchlist_items = [
            item
            for item in stored_watchlist.items
            if item.decision_identity.result_id == saved_id
        ]
        assert len(saved_watchlist_items) == 1
        saved_watchlist_identity = saved_watchlist_items[0].decision_identity
        assert saved_watchlist_identity.stock_code == "2330"
        assert saved_watchlist_identity.decision_date == DECISION_DATE
        assert saved_watchlist_identity.source_snapshot_id == canonical_snapshot_id
        assert saved_watchlist_identity.source_snapshot_hash == canonical_snapshot_hash
        recommendation_view.add_to_watchlist_btn.click()
        assert warning_messages[-1][0] == "未新增觀察項目"
        assert "來源連結未變更" in warning_messages[-1][1]
        unchanged_watchlist = watchlist_service.get_default_watchlist()
        assert unchanged_watchlist is not None
        assert [
            item.decision_identity.to_dict() for item in unchanged_watchlist.items
        ].count(saved_watchlist_identity.to_dict()) == 1

        # 沿用 RecommendationView 唯一的 typed choice／Journal writer；三種
        # 決定都綁在這一筆已保存 result 與 exact candidate identity 上。
        choice_controls = recommendation_view.personal_choice_controls
        assert choice_controls.adopt_button.isEnabled(), choice_controls.status_label.text()
        choice_controls.adopt_button.click()
        choice_controls.reject_button.click()
        choice_controls.override_button.click()
        choice_report = recommendation_view._personalization_read_service().read_personal_recommendation_choices(
            saved_id,
            "2330",
        )
        assert choice_report.source_completeness_status == "verified"
        assert [entry.choice.choice for entry in choice_report.choices] == [
            "adopt",
            "reject",
            "override",
        ]
        assert all(
            entry.choice.result_id == saved_id
            and entry.choice.stock_code == "2330"
            and entry.choice.decision_date == DECISION_DATE
            and entry.choice.source_snapshot_id == canonical_snapshot_id
            and entry.choice.source_snapshot_hash == canonical_snapshot_hash
            for entry in choice_report.choices
        )
        assert choice_report.choices[-1].choice.override_reason is not None
        assert choice_report.choices[-1].choice.override_reason.detail == override_reason

        # The saved result's research evidence is the same exact identity
        # carried through Watchlist, Portfolio and the read-only Journey.
        _seed_evidence(
            config,
            saved_id,
            source_snapshot_id=canonical_snapshot_id,
            source_snapshot_hash=canonical_snapshot_hash,
        )
        next_review = _seed_continuity(
            config,
            saved_id,
            snapshot_id=canonical_snapshot_id,
            snapshot_hash=canonical_snapshot_hash,
        )

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
        window.stock_research_workspace.report_view.return_button.click()
        _wait_for(lambda: window.workspace_stack.currentWidget() is not window.stock_research_workspace)
        assert watchlist_view.stocks_table.currentIndex().row() == r2_row

        assert watchlist_view.select_stock("2330", saved_id) is True
        saved_watchlist_row = watchlist_view.stocks_table.currentIndex().row()
        journey_watchlist_identity = watchlist_view._row_decision_identity(
            watch_rows.iloc[saved_watchlist_row],
            "2330",
        )
        assert journey_watchlist_identity.result_id == saved_id
        assert journey_watchlist_identity.source_snapshot_id == canonical_snapshot_id
        assert journey_watchlist_identity.source_snapshot_hash == canonical_snapshot_hash
        watchlist_view.stock_research_btn.click()
        _wait_report_ready(window)
        saved_watch_context = _context(window)
        assert saved_watch_context.result_id == saved_id
        assert saved_watch_context.stock_code == "2330"
        assert saved_watch_context.source_snapshot_id == canonical_snapshot_id
        assert saved_watch_context.source_snapshot_hash == canonical_snapshot_hash
        assert saved_watch_context.source_workspace == "watchlist"
        saved_watch_dialog = window.stock_research_workspace
        assert saved_watch_dialog is not None and saved_watch_dialog.journey_view is not None
        _wait_for(lambda: saved_watch_dialog.journey_view.journey is not None)
        saved_watch_journey = saved_watch_dialog.journey_view
        saved_watch_choice_model = saved_watch_journey.personal_choice_table.model()
        assert saved_watch_choice_model.rowCount() == 3
        saved_watch_choice_rows = tuple(
            tuple(
                str(saved_watch_choice_model.index(row, column).data())
                for column in range(saved_watch_choice_model.columnCount())
            )
            for row in range(saved_watch_choice_model.rowCount())
        )
        assert {row[0] for row in saved_watch_choice_rows} == {f"{saved_id}:2330"}
        assert {row[1] for row in saved_watch_choice_rows} == {
            "個人採用",
            "個人拒絕",
            "推翻原建議",
        }
        assert "尚待結果成熟" in saved_watch_journey.status_label.text()
        window.stock_research_workspace.report_view.return_button.click()
        _wait_for(lambda: window.workspace_stack.currentWidget() is not window.stock_research_workspace)
        assert watchlist_view.stocks_table.currentIndex().row() == saved_watchlist_row

        # 經真實 RecommendationView 導入流程與 canonical source adapter
        # 建立一筆隔離持倉，驗證摘要 checksum 與內層 universe snapshot 的分工。
        portfolio_service = window.portfolio_service

        class _SelectRecommendationPortfolioAction:
            """只控制 Qt 選單選項；保留實際推薦 handler 與 source adapter。"""

            def __init__(self, *_args, **_kwargs):
                self.actions: list[tuple[str, object]] = []

            def addAction(self, label: str) -> object:
                action = object()
                self.actions.append((label, action))
                return action

            def exec(self, *_args, **_kwargs) -> object | None:
                return next(
                    (
                        action
                        for label, action in self.actions
                        if label == "記錄到持倉管理（保留推薦來源）..."
                    ),
                    None,
                )

        trade_dialog_data = {
            "stock_code": "2330",
            "stock_name": "台積電",
            "side": "buy",
            "quantity": 100,
            "price": 1000.0,
            "trade_date": DECISION_DATE,
            "fees": 0.0,
            "taxes": 0.0,
            "notes": "隔離跨頁測試",
        }
        monkeypatch.setattr(
            "ui_qt.views.recommendation_view.QMenu",
            _SelectRecommendationPortfolioAction,
        )
        monkeypatch.setattr(
            "ui_qt.views.portfolio_view.AddTradeDialog.exec",
            lambda _dialog: 1,
        )
        monkeypatch.setattr(
            "ui_qt.views.portfolio_view.AddTradeDialog.get_trade_data",
            lambda _dialog: trade_dialog_data,
        )
        recommendation_view.results_table.selectRow(0)
        recommendation_view._show_results_table_context_menu(None)
        recorded_trades = portfolio_service.list_trades()
        assert len(recorded_trades) == 1
        recommendation_trade = recorded_trades[0]
        assert recommendation_trade.source_id == saved_id
        assert recommendation_trade.source_type == "recommendation_result"
        assert recommendation_trade.source_snapshot_hash == stable_snapshot_hash(
            recommendation_trade.source_summary
        )
        assert (
            recommendation_trade.source_summary["source_snapshot_id"]
            == canonical_snapshot_id
        )
        assert (
            recommendation_trade.source_summary["source_snapshot_hash"]
            == canonical_snapshot_hash
        )
        assert recommendation_trade.source_snapshot_hash != canonical_snapshot_hash

        portfolio_view = window.portfolio_view
        window.left_navigation.button_for_key("portfolio").click()
        _wait_portfolio_ready(window)
        saved_positions = [
            item
            for item in portfolio_service.list_positions()
            if item.source_type == "recommendation_result"
            and item.source_id == saved_id
            and item.stock_code == "2330"
        ]
        assert len(saved_positions) == 1
        saved_position = saved_positions[0]
        assert portfolio_view._validated_recommendation_result_id(
            saved_position,
            "2330",
        ) == saved_id
        for field_name, changed_value in (
            ("total_score", "999999"),
            ("close_price", "999999"),
            (
                "recommendation_reasons",
                str(saved_position.source_summary["recommendation_reasons"])
                + "；未經保存的理由",
            ),
        ):
            edited_summary = dict(saved_position.source_summary)
            assert field_name in edited_summary
            edited_summary[field_name] = changed_value
            edited_position = replace(
                saved_position,
                source_snapshot_hash=stable_snapshot_hash(edited_summary),
                source_summary=edited_summary,
            )
            assert portfolio_view._validated_recommendation_result_id(
                edited_position,
                "2330",
            ) == ""
        assert portfolio_view.select_stock("2330", saved_id) is True
        portfolio_view.btn_stock_research.click()
        _wait_report_ready(window)
        portfolio_context = _context(window)
        assert portfolio_context.result_id == saved_id
        assert portfolio_context.stock_code == "2330"
        assert portfolio_context.decision_date == DECISION_DATE
        assert portfolio_context.source_snapshot_id == canonical_snapshot_id
        assert portfolio_context.source_snapshot_hash == canonical_snapshot_hash
        assert portfolio_context.source_workspace == "portfolio"
        window.stock_research_workspace.report_view.return_button.click()
        _wait_for(lambda: window.workspace_stack.currentWidget() is not window.stock_research_workspace)
        assert portfolio_view.selected_stock_code == "2330"

        # After the result has been saved, append its Evidence and initial
        # continuity head, then refresh the actual Workbench through its button.
        read_only_paths = _saved_file_paths(
            config,
            saved_id,
            saved_read_model.artifact_location,
        )
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
        _wait_for(lambda: window.stock_research_workspace is not None)
        _wait_report_ready(window)
        workbench_context = _context(window)
        assert workbench_context.result_id == saved_id
        assert workbench_context.stock_code == "2330"
        assert workbench_context.source_snapshot_id == canonical_snapshot_id
        assert workbench_context.source_snapshot_hash == canonical_snapshot_hash
        assert workbench_context.source_workspace == "workbench"
        dialog = window.stock_research_workspace
        assert dialog.journey_view is not None
        _wait_for(lambda: dialog.journey_view.journey is not None)
        controls = dialog.journey_view.continuity_controls
        assert controls is not None
        assert controls.identity is not None
        assert controls.identity.candidate_key == (saved_id, "2330")
        assert controls.state is not None
        assert controls.state.next_review_at == next_review
        personal_choice_model = dialog.journey_view.personal_choice_table.model()
        assert personal_choice_model.rowCount() == 3
        personal_choice_rows = tuple(
            tuple(
                str(personal_choice_model.index(row, column).data())
                for column in range(personal_choice_model.columnCount())
            )
            for row in range(personal_choice_model.rowCount())
        )
        assert {row[0] for row in personal_choice_rows} == {f"{saved_id}:2330"}
        assert {row[1] for row in personal_choice_rows} == {
            "個人採用",
            "個人拒絕",
            "推翻原建議",
        }
        override_row = next(row for row in personal_choice_rows if row[1] == "推翻原建議")
        assert override_row[2] == override_reason
        assert {row[4] for row in personal_choice_rows} == {"已連結"}

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
        journal_path = Path(config.output_root) / "portfolio" / "journal_entries.jsonl"
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
        readback_stdout_path = Path(
            os.environ.get(
                "CROSS_PAGE_READBACK_STDOUT_PATH",
                str(tmp_path / "cross_page_mainwindow_readback_stdout.log"),
            )
        ).expanduser().resolve()
        readback_stderr_path = Path(
            os.environ.get(
                "CROSS_PAGE_READBACK_STDERR_PATH",
                str(tmp_path / "cross_page_mainwindow_readback_stderr.log"),
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
            text=False,
            check=False,
            timeout=30,
        )
        readback_stdout_path.parent.mkdir(parents=True, exist_ok=True)
        readback_stdout_path.write_bytes(readback.stdout or b"")
        readback_stderr_path.parent.mkdir(parents=True, exist_ok=True)
        readback_stderr_path.write_bytes(readback.stderr or b"")
        assert readback.returncode == 0, (readback.stderr or b"").decode(
            "utf-8",
            errors="replace",
        )
        readback_payload = json.loads(readback_receipt_path.read_text(encoding="utf-8"))
        assert readback_payload["persisted_readback"] is True
        assert readback_payload["persisted_identity_consistent"] is True
        assert readback_payload["main_window_recreated"] is True
        canonical_projection = readback_payload["canonical_saved_projection"]
        assert canonical_projection["integrity_basis"] == "canonical_payload_and_index_verified"
        assert canonical_projection["execution_status"] == "completed"
        assert canonical_projection["result_id"] == saved_id
        assert canonical_projection["selected_stock_code"] == "2330"
        assert canonical_projection["execution_selected_stock_codes"] == ["2330"]
        assert canonical_projection["execution_selected_count"] == 1
        assert canonical_projection["universe_selected_codes"] == ["2317", "2330"]
        assert canonical_projection["universe_selected_count"] == 2
        assert canonical_projection["request_source_snapshot_id"] == ""
        assert canonical_projection["request_source_snapshot_hash"] == ""
        assert canonical_projection["universe_snapshot_id"] == canonical_snapshot_id
        assert canonical_projection["universe_snapshot_hash"] == canonical_snapshot_hash
        assert canonical_projection["capture"]["result_id"] == saved_id
        assert canonical_projection["capture"]["recommendations_count"] == 1
        assert readback_payload["report_loaded"] is True
        assert readback_payload["journey_loaded"] is True
        assert readback_payload["research_workers_finished"] is True
        assert readback_payload["exact_identity_visible"] is True
        assert readback_payload["idle_close_requests"] == 1
        assert readback_payload["main_window_close_event_count"] == 1
        assert readback_payload["app_exec_returncode"] == 0
        assert readback_payload["process_exit_code"] == 0
        persisted_identity = readback_payload["persisted_identity"]
        assert persisted_identity["result"] == {
            "result_id": saved_id,
            "stock_code": "2330",
            "decision_date": DECISION_DATE,
            "data_date": DATA_DATE,
            "source_snapshot_id": canonical_snapshot_id,
            "source_snapshot_hash": canonical_snapshot_hash,
            "universe_snapshot_id": canonical_snapshot_id,
            "universe_snapshot_hash": canonical_snapshot_hash,
            "recommendation_source_snapshot_id": "",
            "recommendation_source_snapshot_hash": "",
        }
        assert persisted_identity["watchlist"] == {
            "result_id": saved_id,
            "stock_code": "2330",
            "decision_date": DECISION_DATE,
            "source_snapshot_id": canonical_snapshot_id,
            "source_snapshot_hash": canonical_snapshot_hash,
        }
        assert persisted_identity["portfolio_trade"] == {
            "result_id": saved_id,
            "stock_code": "2330",
            "decision_date": DECISION_DATE,
            "source_snapshot_id": canonical_snapshot_id,
            "source_snapshot_hash": canonical_snapshot_hash,
            "summary_checksum": recommendation_trade.source_snapshot_hash,
            "summary_checksum_verified": True,
        }
        assert persisted_identity["continuity"] == {
            "result_id": saved_id,
            "stock_code": "2330",
            "decision_date": DECISION_DATE,
            "source_snapshot_id": canonical_snapshot_id,
            "source_snapshot_hash": canonical_snapshot_hash,
            "next_review_at": second_review.isoformat(),
        }
        assert persisted_identity["candidate_key"] == f"{saved_id}:2330"
        assert persisted_identity["recommendation_source_snapshot"] == {
            "source_snapshot_id": "",
            "source_snapshot_hash": "",
        }
        assert persisted_identity["universe_snapshot"] == {
            "universe_snapshot_id": canonical_snapshot_id,
            "universe_snapshot_hash": canonical_snapshot_hash,
        }
        assert readback_payload["rendered_identity"]["report_context"] == {
            "result_id": saved_id,
            "stock_code": "2330",
            "decision_date": DECISION_DATE,
            "data_date": DATA_DATE,
            "source_snapshot_id": canonical_snapshot_id,
            "source_snapshot_hash": canonical_snapshot_hash,
        }
        assert readback_payload["rendered_identity"]["journey_context"] == {
            "result_id": saved_id,
            "stock_code": "2330",
            "decision_date": DECISION_DATE,
            "data_date": DATA_DATE,
            "source_snapshot_id": canonical_snapshot_id,
            "source_snapshot_hash": canonical_snapshot_hash,
        }
        assert readback_payload["rendered_identity"]["journey"]["candidate_found"] is True
        assert readback_payload["rendered_identity"]["journey"]["portfolio_trade_count"] == 1
        assert readback_payload["rendered_identity"]["journey"]["portfolio_trade_link_statuses"] == [
            "JourneyLinkStatus.LINKED"
        ]
        assert readback_payload["rendered_identity"]["journey"]["source_snapshot_id"] == ""
        assert readback_payload["rendered_identity"]["journey"]["source_snapshot_hash"] == ""
        assert readback_payload["rendered_identity"]["journey"]["universe_snapshot_id"] == canonical_snapshot_id
        assert readback_payload["rendered_identity"]["journey"]["universe_snapshot_hash"] == canonical_snapshot_hash
        assert readback_payload["rendered_identity"]["journey"]["candidate_key"] == [
            saved_id,
            "2330",
        ]
        assert (
            readback_payload["rendered_identity"]["journey"]["result_link_status"]
            == "JourneyLinkStatus.LINKED"
        )
        assert readback_payload["rendered_identity"]["journey_controls"] == {
            "candidate_key": [saved_id, "2330"],
            "identity_status": "linked",
            "next_review_at": second_review.isoformat(),
            "status_text": f"研究狀態：已納入研究｜Journal 紀錄：3 筆｜下次檢視：{second_review.isoformat()}｜歷史：6 筆",
            "accept_enabled": True,
        }

        # 關閉原 MainWindow 後重新建立一個全新 MainWindow，從既有 Journal
        # 只讀讀回三種決定與覆寫理由；後續 outcome 仍按真實資料標示待成熟。
        cold_context = window._coerce_stock_research_context(
            {
                "stock_code": "2330",
                "stock_name": "台積電",
                "result_id": saved_id,
                "source_id": saved_id,
                "decision_date": DECISION_DATE,
                "data_date": DATA_DATE,
                "identity_status": "linked",
                "source_snapshot_id": canonical_snapshot_id,
                "source_snapshot_hash": canonical_snapshot_hash,
                "source_workspace": "recommendation",
            }
        )
        window._select_main_workspace("workbench")
        _wait_for(lambda: _qt_widget_not_visible(window.stock_research_workspace))
        window.close()
        _wait_for(lambda: _qt_widget_not_visible(window))
        _drain_qt_deferred_deletes(app, (window,))

        cold_window = MainWindow()
        cold_window.show()
        cold_window._open_stock_research_context(cold_context)
        _wait_report_ready(cold_window)
        cold_dialog = cold_window.stock_research_workspace
        assert cold_dialog is not None and cold_dialog.journey_view is not None
        _wait_for(lambda: cold_dialog.journey_view.journey is not None)
        cold_journey_view = cold_dialog.journey_view
        cold_choice_model = cold_journey_view.personal_choice_table.model()
        assert cold_choice_model.rowCount() == 3
        cold_choice_rows = tuple(
            tuple(
                str(cold_choice_model.index(row, column).data())
                for column in range(cold_choice_model.columnCount())
            )
            for row in range(cold_choice_model.rowCount())
        )
        assert cold_choice_rows == personal_choice_rows
        assert "尚待結果成熟" in cold_journey_view.status_label.text()

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
                        "source_snapshot_id": canonical_snapshot_id,
                        "source_snapshot_hash": canonical_snapshot_hash,
                    },
                    "recommendation_source_snapshot": {
                        "status": "not_claimed_by_synthetic_provider",
                        "source_provider_id": "_CrossPageRecommendationMarketFrameProvider",
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
                    "personal_choice_rows": [list(row) for row in personal_choice_rows],
                    "cold_mainwindow_choice_rows": [list(row) for row in cold_choice_rows],
                    "readback_process": {
                        "return_code": readback.returncode,
                        "stdout_path": str(readback_stdout_path),
                        "stderr_path": str(readback_stderr_path),
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        assert manifest_path.is_file()
    finally:
        cold_window = locals().get("cold_window")
        if cold_window is not None:
            dialog = cold_window.stock_research_workspace
            if dialog is not None:
                try:
                    cold_window._select_main_workspace("workbench")
                except RuntimeError:
                    dialog = None
                if dialog is not None:
                    _wait_for(lambda: _qt_widget_not_visible(dialog), timeout_ms=12_000)
            try:
                cold_window_visible = cold_window.isVisible()
            except RuntimeError:
                cold_window_visible = False
            if cold_window_visible:
                cold_window.close()
                _wait_for(lambda: _qt_widget_not_visible(cold_window), timeout_ms=12_000)
            _drain_qt_deferred_deletes(app, (cold_window,))
        dialog = window.stock_research_workspace
        if dialog is not None:
            try:
                window._select_main_workspace("workbench")
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
        dialog = window.stock_research_workspace
        if dialog is None:
            return
        try:
            window._select_main_workspace("workbench")
        except RuntimeError:
            return
        _wait_for(lambda: _qt_widget_not_visible(dialog))
        _wait_for(lambda: window.workspace_stack.currentWidget() is not window.stock_research_workspace)

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
        dialog = window.stock_research_workspace
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
        dialog = window.stock_research_workspace
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
        dialog = window.stock_research_workspace
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
        dialog = window.stock_research_workspace
        if dialog is not None:
            try:
                window._select_main_workspace("workbench")
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
    monkeypatch,
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
    from ui_qt.views import portfolio_view as portfolio_view_module
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

        # 右鍵點擊另一列時，必須先更新目前列的 position identity。
        class FakeMenu:
            def __init__(self, *_args) -> None:
                self._actions: list[object] = []

            def addAction(self, _label: str) -> object:  # noqa: N802
                action = object()
                self._actions.append(action)
                return action

            def exec(self, *_args) -> object:
                return self._actions[1]

        monkeypatch.setattr(portfolio_view_module, "QMenu", FakeMenu)
        view.resize(1200, 800)
        view.show()
        app.processEvents()
        view.positions_table.selectRow(0)
        target_rect = view.positions_table.visualRect(
            view.positions_model.index(1, 0)
        )
        assert target_rect.isValid()
        view._show_position_context_menu(target_rect.center())
        assert len(emitted) == 2
        context = emitted[-1]
        assert context.result_id == "R2"
        assert context.stock_name == "台積電 R2"
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
            "decision_date": DECISION_DATE,
            "data_date": DATA_DATE,
            "source_snapshot_id": "snap-r1",
            "source_snapshot_hash": "hash-r1",
        },
    )

    # Existing Chinese-only persisted rows remain compatible.
    assert view._validated_recommendation_result_id(position, "2330") == "R1"

    # Legacy row 不得為未經 canonical query 驗證的 canonical summary claim 背書。
    position.source_summary = {
        "result_id": "R1",
        "stock_code": "2330",
        "integrity_basis": "canonical_payload_and_index_verified",
        "payload_hash": "sha256:" + "1" * 64,
        "artifact_location": "unverified-canonical-artifact.json",
        "candidate_identity": {"stock_code": "2330", "rank": 1},
    }
    assert view._validated_recommendation_result_id(position, "2330") == ""
    position.source_summary = {
        "result_id": "R1",
        "stock_code": "2330",
        "decision_date": DECISION_DATE,
        "data_date": DATA_DATE,
        "source_snapshot_id": "snap-r1",
        "source_snapshot_hash": "hash-r1",
    }

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

    # 同一個精確保存列重複時，source-to-candidate 對應不唯一，必須拒絕。
    payload["recommendations"] = [dict(valid_row), dict(valid_row)]
    saved_result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert view._validated_recommendation_result_id(position, "2330") == ""

    # 兩個股票代號欄位都缺漏時，不能從同股／日期或其他列猜回候選。
    payload["recommendations"] = [
        {
            key: value
            for key, value in valid_row.items()
            if key not in {"stock_code", "證券代號"}
        }
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
