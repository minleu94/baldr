from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from app_module.decision_presentation import (
    PositionHealthReadModel,
    format_position_health_presentation,
    format_position_health_read_model,
)
from app_module.position_health_source_providers import PositionThesisRegistryWriter
from app_module.position_health_transition_evaluator import evaluate_baseline_file
from app_module.position_health_transition_read_service import (
    PositionHealthTransitionReadService,
)
from app_module.position_thesis_contract import (
    PositionInvalidationRule,
    PositionThesisContract,
)
from data_module.official_trading_calendar_cache import build_twse_calendar_cache


DECISION_DATE = "2026-09-15"
OBSERVED_AT = datetime(2026, 9, 15, 7, 0, tzinfo=timezone.utc)
POSITION_ID = "paper:2330:entry-20260901"
ROWS_HASH = "sha256:" + "3" * 64


def _canonical_hash(payload: object) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _write_hashed(path: Path, payload: dict[str, Any]) -> None:
    content = dict(payload)
    content["content_sha256"] = _canonical_hash(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(content, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


# 本測試覆蓋 OBSERVED_AT 當下 cache 有效的 as-of 情境，不涵蓋今日時鐘回溯評估。
# 正式執行仍依當前時鐘檢查 cache 有效期；過期時保持 fail-closed。
class _FixedCalendarClock(datetime):
    """將日曆快取檢核固定在測試 evaluator 的觀察時間。"""

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        if tz is None:
            return OBSERVED_AT.replace(tzinfo=None)
        return OBSERVED_AT.astimezone(tz)


def _contract(action: str = "exit") -> PositionThesisContract:
    return PositionThesisContract(
        position_id=POSITION_ID,
        stock_code="2330",
        entry_date="2026-09-01",
        decision_date=DECISION_DATE,
        available_date="2026-09-07",
        entry_thesis="由人工輸入且可追溯的測試論點",
        holding_horizon_trading_days=20,
        next_review_date="2026-09-30",
        source_trace=("human:review-20260907",),
        invalidation_rules=(
            PositionInvalidationRule(
                metric_id="drawdown_bp",
                operator="gte",
                threshold=Decimal("1200"),
                action=action,
            ),
        ),
    )


def _write_calendar_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """建立合成年度日曆快取與隔離的 QA 資料庫。"""

    # 合成測試時間早於 OBSERVED_AT，不代表官方日曆實際發布時間。
    captured_at = datetime(2026, 9, 14, 23, 0, tzinfo=timezone.utc)
    raw_response = json.dumps(
        [
            {
                "Date": "1150101",
                "Description": "依規定放假1日。",
                "Name": "測試年度休市",
                "Weekday": "四",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    payload = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=raw_response,
        requested_at=captured_at,
        captured_at=captured_at,
        response_status=200,
        max_age=timedelta(days=7),
    )
    path = tmp_path / "calendar_cache" / "twse_holiday_schedule_2026_fixture.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    qa_db_path = tmp_path / "qa_db" / "market.sqlite3"
    qa_db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(qa_db_path):
        pass
    return path.parent, qa_db_path


def _write_source_fixture(tmp_path: Path, *, action: str, metric_value: str) -> Path:
    registry = tmp_path / "sources" / "thesis.json"
    PositionThesisRegistryWriter(
        registry,
            now_provider=lambda: datetime(2026, 9, 15, 6, 30, tzinfo=timezone.utc),
    ).append(
        contract=_contract(action),
        entry_lineage_id=POSITION_ID,
        version_id=f"thesis-{action}-v1",
        authored_by="reviewer:test",
            authored_at="2026-09-15T05:50:00+08:00",
            available_at="2026-09-15T06:00:00+08:00",
    )

    condition = tmp_path / "sources" / "condition.json"
    _write_hashed(
        condition,
        {
            "schema_version": "position-health-condition-source.v1",
            "source_id": "paper-condition:test",
            "source_snapshot_hash": "sha256:" + "1" * 64,
            "as_of_date": DECISION_DATE,
            "available_at": "2026-09-15T08:20:00+08:00",
            "positions": [
                {
                    "position_id": POSITION_ID,
                    "entry_lineage_id": POSITION_ID,
                    "stock_code": "2330",
                    "quality": "verified",
                    "result": {
                        "status": "valid",
                        "label": "仍符合",
                        "source_label": "test",
                        "reasons": ["regime_stable"],
                        "details": {},
                    },
                    "current_snapshot": {
                        "current_regime": "Trend",
                        "current_total_score": "12.0",
                        "current_price": "100.00",
                    },
                }
            ],
        },
    )

    metrics = tmp_path / "sources" / "metrics.json"
    _write_hashed(
        metrics,
        {
            "schema_version": "position-health-metrics-source.v1",
            "source_id": "paper-metric:test",
            "source_snapshot_hash": "sha256:" + "2" * 64,
            "available_at": "2026-09-15T08:20:00+08:00",
            "metrics": [
                {
                    "position_id": POSITION_ID,
                    "entry_lineage_id": POSITION_ID,
                    "stock_code": "2330",
                    "metric_id": "drawdown_bp",
                    "value": metric_value,
                    "available_date": DECISION_DATE,
                }
            ],
        },
    )

    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "schema_version": "position-health-baseline.v1",
                    "source_snapshot_id": "paper-main-20260915",
                "source_snapshot_rows_sha256": ROWS_HASH,
                "portfolio_id": "paper-main",
                "decision_date": DECISION_DATE,
                "as_of_date": DECISION_DATE,
                "positions": [
                    {
                        "position_id": POSITION_ID,
                        "entry_lineage_id": POSITION_ID,
                        "stock_code": "2330",
                        "state": "HEALTHY",
                        "entry_lineage_status": "same_snapshot_verified",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "position_health_transition"
    calendar_cache, calendar_db = _write_calendar_fixture(tmp_path)
    from data_module import official_trading_calendar

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(official_trading_calendar, "datetime", _FixedCalendarClock)
        result = evaluate_baseline_file(
            baseline_path=baseline,
            output_dir=output,
            observed_at=OBSERVED_AT,
            decision_date=DECISION_DATE,
            thesis_registry_path=registry,
            condition_source_path=condition,
            metrics_source_path=metrics,
            calendar_cache_path=calendar_cache,
            calendar_db_path=calendar_db,
        )
    assert result["status"] == "passed", result.get("blockers")
    return output


def _reader(output: Path) -> PositionHealthTransitionReadService:
    return PositionHealthTransitionReadService(
        output,
        now_provider=lambda: datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    ("action", "metric_value", "expected_state", "expected_action"),
    (
        ("exit", "0", "HEALTHY", "HOLD"),
        ("reduce", "1200", "REDUCE_CANDIDATE", "REDUCE_CANDIDATE"),
        ("exit", "1200", "EXIT_CANDIDATE", "EXIT_CANDIDATE"),
    ),
)
def test_reader_projects_real_evaluator_receipt_with_shared_action_semantics(
    tmp_path: Path,
    action: str,
    metric_value: str,
    expected_state: str,
    expected_action: str,
) -> None:
    output = _write_source_fixture(
        tmp_path,
        action=action,
        metric_value=metric_value,
    )

    model = _reader(output).read_latest(
        expected_decision_date=DECISION_DATE,
        expected_position_ids=(POSITION_ID,),
    )

    assert model.status == "passed"
    assert model.source_status == "verified"
    assert model.cohort_key == f"paper-main|paper-main-20260915|{ROWS_HASH}|{DECISION_DATE}"
    assert model.research_only is True
    assert model.auto_action_allowed is False
    assert model.broker_execution is False
    assert model.formal_credit is False
    row = model.for_position(POSITION_ID)
    assert row is not None
    assert row.proposed_state == expected_state
    assert row.raw_proposed_state == expected_state
    assert row.action_suitability == expected_action
    assert row.decision_date == DECISION_DATE
    assert row.available_at == "2026-09-15T00:20:00+00:00"
    assert dict(row.availability_by_source)["condition"] == row.available_at
    source_hashes = dict(row.source_hashes)
    assert source_hashes["condition"] == "sha256:" + "1" * 64
    assert source_hashes["metrics"] == "sha256:" + "2" * 64
    assert row.entry_lineage_status == "same_snapshot_verified"
    assert row.review_required is True


def test_missing_receipt_is_reported_as_real_gap_not_fake_success(tmp_path: Path) -> None:
    model = _reader(tmp_path / "missing").read_latest(
        expected_decision_date=DECISION_DATE,
    )

    assert model.status == "blocked"
    assert model.source_status == "missing"
    assert model.positions == ()
    assert any("position_health_receipt_unavailable" in item for item in model.blockers)


def test_corrupt_result_hash_is_blocked_and_has_no_positive_projection(tmp_path: Path) -> None:
    output = _write_source_fixture(tmp_path, action="exit", metric_value="0")
    status = json.loads((output / "latest_status.json").read_text(encoding="utf-8"))
    result_path = Path(status["result_path"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["warnings"] = ["tampered"]
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    model = _reader(output).read_latest(expected_decision_date=DECISION_DATE)

    assert model.status == "blocked"
    assert model.positions == ()
    assert any("result_hash_mismatch" in item for item in model.blockers)


def _rewrite_result(output: Path, mutate) -> None:
    status_path = output / "latest_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    result_path = Path(status["result_path"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    mutate(result)
    encoded = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    result_path.write_bytes(encoded)
    latest_path = Path(status["latest_path"])
    latest_path.write_bytes(encoded)
    status["result_sha256"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    status_path.write_text(
        json.dumps(status, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def test_same_day_available_at_after_evaluator_observed_at_is_blocked(tmp_path: Path) -> None:
    output = _write_source_fixture(tmp_path, action="exit", metric_value="0")

    def mutate(result: dict[str, Any]) -> None:
        result["positions"][0]["available_at"] = "2026-09-15T08:00:00+00:00"
        result["positions"][0]["available_at_by_source"]["condition"] = (
            "2026-09-15T08:00:00+00:00"
        )

    _rewrite_result(output, mutate)
    model = _reader(output).read_latest(expected_decision_date=DECISION_DATE)

    assert model.status == "blocked"
    assert model.positions == ()
    assert any("source_available_at_after_observed" in item for item in model.blockers)


def test_stale_requested_date_revokes_raw_hold_candidate_to_watch(tmp_path: Path) -> None:
    output = _write_source_fixture(tmp_path, action="exit", metric_value="0")
    model = _reader(output).read_latest(expected_decision_date="2026-09-16")

    assert model.status == "stale"
    assert any("stale_artifact" in item for item in model.blockers)
    row = model.for_position(POSITION_ID)
    assert row is not None
    assert row.raw_proposed_state == "HEALTHY"
    assert row.proposed_state == "WATCH"
    assert row.action_suitability == "WATCH"
    assert row.source_status == "stale"


def test_reader_max_age_revokes_old_receipt_to_watch(tmp_path: Path) -> None:
    output = _write_source_fixture(tmp_path, action="exit", metric_value="0")
    model = PositionHealthTransitionReadService(
        output,
        now_provider=lambda: datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
    ).read_latest(max_age_days=1)

    assert model.status == "stale"
    assert "position_health_stale_artifact" in model.blockers
    row = model.for_position(POSITION_ID)
    assert row is not None
    assert row.raw_proposed_state == "HEALTHY"
    assert row.proposed_state == "WATCH"
    assert row.action_suitability == "WATCH"


def test_position_health_formatter_keeps_technical_scope_out_of_the_short_summary(
    tmp_path: Path,
) -> None:
    output = _write_source_fixture(tmp_path, action="exit", metric_value="0")
    model = _reader(output).read_latest(expected_decision_date=DECISION_DATE)
    summary = format_position_health_read_model(model)
    detail = format_position_health_presentation(model.positions[0])

    assert "cohort" not in summary
    assert ROWS_HASH not in summary
    assert "需要確認：1/1 筆" in summary
    assert "尚無持倉健康評估資料" not in summary
    assert f"{POSITION_ID}" in detail
    assert "狀態穩定" in detail
    assert "尚未觸發失效條件" in detail
    assert "regime_stable" in detail

    missing = PositionHealthTransitionReadService(tmp_path / "missing").read_latest()
    missing_summary = format_position_health_read_model(missing)
    assert missing_summary.startswith("尚無持倉健康評估資料")
    assert "下一步：" in missing_summary
    assert "[Errno" not in missing_summary
    assert "latest_status.json" not in missing_summary


def test_identity_scope_mismatch_is_fail_closed_without_stock_code_fallback(
    tmp_path: Path,
) -> None:
    output = _write_source_fixture(tmp_path, action="exit", metric_value="1200")
    model = _reader(output).read_latest(
        expected_decision_date=DECISION_DATE,
        expected_position_ids=("paper:2330:another-entry",),
    )

    assert model.status == "blocked"
    assert any("identity_scope_mismatch" in item for item in model.blockers)
    row = model.for_position(POSITION_ID)
    assert row is not None
    assert row.raw_proposed_state == "EXIT_CANDIDATE"
    assert row.proposed_state == "WATCH"
    assert row.action_suitability == "WATCH"


def test_cohort_scope_mismatch_revokes_the_paper_projection(tmp_path: Path) -> None:
    output = _write_source_fixture(tmp_path, action="exit", metric_value="1200")
    model = _reader(output).read_latest(
        expected_cohort_key=(
            f"paper-main|paper-main-other|{ROWS_HASH}|{DECISION_DATE}"
        ),
    )

    assert model.status == "blocked"
    assert "position_health_cohort_scope_mismatch" in model.blockers
    row = model.for_position(POSITION_ID)
    assert row is not None
    assert row.raw_proposed_state == "EXIT_CANDIDATE"
    assert row.proposed_state == "WATCH"
    assert row.action_suitability == "WATCH"


def test_row_source_snapshot_mismatch_is_rejected(tmp_path: Path) -> None:
    output = _write_source_fixture(tmp_path, action="exit", metric_value="0")

    def mutate(result: dict[str, Any]) -> None:
        result["positions"][0]["source_snapshot_id"] = "paper-other-20260915"

    _rewrite_result(output, mutate)
    model = _reader(output).read_latest(expected_decision_date=DECISION_DATE)

    assert model.status == "blocked"
    assert model.positions == ()
    assert any("source_snapshot_scope_mismatch" in item for item in model.blockers)


class _RecordingHealthReader:
    def __init__(self, model: PositionHealthReadModel) -> None:
        self.model = model
        self.calls: list[dict[str, object]] = []

    def read_latest(self, **kwargs: object) -> PositionHealthReadModel:
        self.calls.append(dict(kwargs))
        return self.model


def test_portfolio_and_workbench_render_the_same_typed_projection(
    tmp_path: Path,
) -> None:
    output = _write_source_fixture(tmp_path, action="exit", metric_value="0")
    model = _reader(output).read_latest(expected_decision_date=DECISION_DATE)
    assert model.status == "passed"

    reader = _RecordingHealthReader(model)
    from app_module.dtos.portfolio_dtos import PortfolioDTO, PositionDTO
    from PySide6.QtWidgets import QApplication
    from ui_qt.views.portfolio_view import PortfolioView
    from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView

    app = QApplication.instance() or QApplication([])

    class Config:
        output_root = tmp_path
        data_dir = tmp_path
        broker_branch_registry_file = tmp_path / "missing.csv"

        def resolve_output_path(self, relative_path: str) -> Path:
            return tmp_path / relative_path

    class PortfolioService:
        config = Config()

        def get_portfolio(self) -> PortfolioDTO:
            return PortfolioDTO(
                portfolio_id="default",
                portfolio_name="Default",
                total_positions=1,
                active_positions=1,
                positions=(
                    PositionDTO(
                        position_id="default:2330",
                        portfolio_id="default",
                        stock_code="2330",
                        stock_name="台積電",
                        quantity=1000,
                        average_cost=100,
                        invested_amount=100000,
                        current_price=101,
                        source_summary={"current_price_date": "2026-09-14"},
                    ),
                ),
                total_invested_amount=100000,
                total_realized_pnl=0,
            )

        def list_trades(self):
            return []

        def get_current_price(self, _stock_code: str):
            return 101

    class JournalService:
        def list_journal_entries(self, _stock_code: str = ""):
            return []

    portfolio = PortfolioView(
        portfolio_service=PortfolioService(),
        journal_service=JournalService(),
        position_health_read_service=reader,
    )
    assert reader.calls
    assert portfolio._position_health_read_model is model
    assert "expected_decision_date" not in reader.calls[-1]
    assert reader.calls[-1]["max_age_days"] == 1
    assert portfolio.positions_model is not None
    frame = portfolio.positions_model.getDataFrame()
    assert frame.iloc[0]["Position Health"] == "觀察／未知"
    assert frame.iloc[0]["動作適合度"] == "觀察／未知"
    assert portfolio._health_for_position(portfolio._last_portfolio_dto.positions[0]) is None
    assert portfolio.position_health_model.rowCount() == 1
    assert portfolio.position_health_model.row_at(0) is model.positions[0]
    assert portfolio.position_health_table.model() is portfolio.position_health_model
    assert "Paper Position Health：已驗證" in portfolio.position_health_summary_label.text()
    portfolio.position_health_table.selectRow(0)
    portfolio._show_position_health_row(portfolio.position_health_model.index(0, 0))
    assert POSITION_ID in portfolio.position_health_detail_label.text()
    assert "來源 hash" in portfolio.position_health_detail_label.text()

    from tests.test_ui_qt_workbench_view import _dashboard_with_replay

    dashboard = _dashboard_with_replay()
    dashboard = dashboard.__class__(
        **{**dashboard.__dict__, "position_health": model}
    )
    workbench = UnifiedDecisionWorkbenchView(dashboard=dashboard, auto_refresh=False)
    assert workbench.position_health_model.rowCount() == 1
    assert workbench.position_health_model.row_at(0) is model.positions[0]
    assert "已驗證" in workbench.position_health_summary_label.text()
    workbench.position_health_table.selectRow(0)
    workbench._show_position_health_row(workbench.position_health_model.index(0, 0))
    assert POSITION_ID in workbench.position_health_detail_label.text()
    assert "來源 hash" in workbench.position_health_detail_label.text()

    del workbench, portfolio, app


def test_real_portfolio_service_keeps_paper_health_out_of_manual_identity(
    tmp_path: Path,
) -> None:
    """The real manual PortfolioService id must not steal a Paper receipt row."""

    from app_module.journal_service import JournalService
    from app_module.portfolio_service import PortfolioService
    from data_module.config import TWStockConfig
    from PySide6.QtWidgets import QApplication
    from ui_qt.views.portfolio_view import PortfolioView

    output = _write_source_fixture(tmp_path / "health", action="exit", metric_value="0")
    model = _reader(output).read_latest(expected_decision_date=DECISION_DATE)
    assert model.status == "passed"

    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "portfolio-output",
    )
    service = PortfolioService(config)
    service.record_trade(
        stock_code="2330",
        stock_name="台積電",
        side="buy",
        quantity=1000,
        price=100,
        trade_date=DECISION_DATE,
        portfolio_id="default",
    )
    manual_portfolio = service.get_portfolio()
    assert manual_portfolio.positions[0].position_id == "default:2330"
    assert manual_portfolio.positions[0].position_id != POSITION_ID

    reader = _RecordingHealthReader(model)
    app = QApplication.instance() or QApplication([])
    portfolio = PortfolioView(
        portfolio_service=service,
        journal_service=JournalService(config),
        position_health_read_service=reader,
    )

    manual_position = portfolio._last_portfolio_dto.positions[0]
    assert portfolio._health_for_position(manual_position) is None
    assert portfolio.position_health_model.rowCount() == 1
    assert portfolio.position_health_model.row_at(0) is model.positions[0]
    assert portfolio.positions_model is not None
    frame = portfolio.positions_model.getDataFrame()
    assert frame.iloc[0]["動作適合度"] == "觀察／未知"
    assert frame.iloc[0]["Health 來源"] == "未精確對應"
    assert "expected_decision_date" not in reader.calls[-1]
    assert reader.calls[-1]["max_age_days"] == 1

    del portfolio, app


def test_workbench_source_service_refresh_reads_the_shared_health_projection(
    tmp_path: Path,
) -> None:
    """The real Workbench refresh caller must inject the same typed read model."""

    from app_module.workbench_source_service import WorkbenchSourceService
    from data_module.config import TWStockConfig

    output = _write_source_fixture(tmp_path / "health", action="exit", metric_value="0")
    model = _reader(output).read_latest(expected_decision_date=DECISION_DATE)
    assert model.status == "passed"

    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "workbench-output",
    )
    config.db_file = tmp_path / "missing-evidence.db"
    config.research_run_db_file = tmp_path / "missing-research-runs.db"
    multi_day_path = tmp_path / "multi-day.md"
    multi_day_path.write_text("", encoding="utf-8")
    reader = _RecordingHealthReader(model)

    dashboard = WorkbenchSourceService(
        config,
        position_health_read_service=reader,
    ).inspect(
        decision_date=DECISION_DATE,
        multi_day_record_path=multi_day_path,
    )

    assert dashboard.position_health is model
    assert reader.calls[-1]["expected_decision_date"] == dashboard.as_of_date.isoformat()
