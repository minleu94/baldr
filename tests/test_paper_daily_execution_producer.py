from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioPositionSnapshot,
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotRepository,
)
from data_module import paper_daily_execution_producer as paper_producer
from app_module.paper_portfolio_policy import PaperPortfolioPolicyConfig
from data_module.portfolio_ml_dataset_assembler import (
    SECTOR_MEMBERSHIP_MANIFEST_SCHEMA_VERSION,
    SECTOR_MEMBERSHIP_SIDECAR_SCHEMA_VERSION,
)
from data_module.paper_daily_execution_producer import (
    PaperExecutionPaths,
    _QueueReceipt,
    _Position,
    _State,
    _append_and_read_back,
    _apply_prior_paper_fills,
    _build_fills,
    _effective_queue_receipts,
    ensure_paper_ledger_schema,
    persist_operational_receipt,
    resolve_pending_recommendation,
    run_paper_execution_daily_from_queue,
    run_paper_execution_daily,
)
from data_module.official_trading_calendar import OfficialTradingCalendar
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)
from app_module.paper_trade_ledger import PaperTradeFill, PaperTradeLedgerRepository


TAIPEI = ZoneInfo("Asia/Taipei")
DECISION_DATE = "2026-09-04"
EXECUTION_DATE = "2026-09-07"
NOW = datetime(2026, 9, 7, 10, 0, tzinfo=TAIPEI)
EOD_REPLAY_NOW = datetime(2026, 9, 7, 15, 0, tzinfo=TAIPEI)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_sector_sidecar(path: Path) -> str:
    rows = [
        {
            "symbol": "2330",
            "sector_id": "SEMICONDUCTOR",
            "available_at": "2026-01-01T00:00:00+00:00",
            "effective_from": "2026-01-01",
            "effective_to": None,
            "status": "accepted",
            "source_id": "official:twse:t187ap03_L",
            "license_id": "twse-open-data-license-v1",
            "source_hash": "sha256:" + ("1" * 64),
        }
    ]
    canonical = lambda value: json.dumps(  # noqa: E731 - fixture canonicalizer
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    rows_hash = "sha256:" + hashlib.sha256(canonical(rows)).hexdigest()
    manifest_body = {
        "schema_version": SECTOR_MEMBERSHIP_MANIFEST_SCHEMA_VERSION,
        "row_count": len(rows),
        "rows_hash": rows_hash,
    }
    manifest = {
        **manifest_body,
        "canonical_hash": "sha256:" + hashlib.sha256(
            canonical(
                {
                    "sidecar_schema_version": SECTOR_MEMBERSHIP_SIDECAR_SCHEMA_VERSION,
                    "manifest": manifest_body,
                }
            )
        ).hexdigest(),
    }
    payload = {
        "schema_version": SECTOR_MEMBERSHIP_SIDECAR_SCHEMA_VERSION,
        "manifest": manifest,
        "rows": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(payload) + b"\n")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class _Calendar:
    def __init__(self, open_dates: set[str]) -> None:
        self.open_dates = open_dates

    def is_official_trading_day(
        self,
        target_date: date,
        allow_online_probe: bool = True,
    ) -> tuple[bool, str]:
        del allow_online_probe
        key = target_date.isoformat()
        return (
            key in self.open_dates,
            "test_official_schedule_open" if key in self.open_dates else "test_closed",
        )


class _UnknownCalendar:
    def is_official_trading_day(
        self,
        _target_date: date,
        allow_online_probe: bool = True,
    ) -> tuple[None, str]:
        del allow_online_probe
        return None, "twse_holiday_schedule_unavailable"


def _recommendation(
    path: Path,
    *,
    created_at: str = "2026-09-04T20:00:00+08:00",
    decision_date: str = DECISION_DATE,
    price: str = "10.00",
) -> None:
    path.write_text(
        json.dumps(
            {
                "result_id": "scheduled_rec_20260904_200000",
                "created_at": created_at,
                "config": {
                    "research_only": True,
                    "decision_date": decision_date,
                    "top_n": 8,
                    "profile_id": "scheduled_daily_research_default_v1",
                    "safety_boundary": {
                        "confirm": False,
                        "writes_evidence_db": False,
                        "auto_trading": False,
                        "lifecycle_action": False,
                    },
                },
                "recommendations": [
                    {
                        "證券代號": "2330",
                        "證券名稱": "測試公司",
                        "總分": "100.00",
                        "收盤價": price,
                        "產業": "半導體",
                        "eligible_universe_date": decision_date,
                    }
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _state(
    path: Path,
    *,
    decision_date: str = DECISION_DATE,
    quantity: int = 0,
) -> None:
    repository = PaperPortfolioSnapshotRepository(path)
    repository.append(
        PaperPortfolioSnapshot(
            snapshot_id=f"snapshot-{decision_date.replace('-', '')}",
            portfolio_id="paper-main",
            decision_date=decision_date,
            source_result_id="scheduled_rec_prior",
            cash=Decimal("100000.00"),
            total_value=Decimal("100000.00"),
            positions=(
                PaperPortfolioPositionSnapshot(
                    stock_code="2330",
                    quantity=quantity,
                    mark_price=Decimal("10.00"),
                    market_value=(
                        Decimal("0.00")
                        if quantity == 0
                        else Decimal("10.00") * quantity
                    ),
                    weight_bp=0,
                ),
            ),
        )
    )


def _market(
    path: Path,
    *,
    recommendation_close: str = "10.00",
    execution_open: str = "10.20",
    execution_close: str = "10.50",
    recommendation_volume: int = 90000,
    execution_volume: int | None = 100000,
    with_calendar: bool = False,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE daily_prices ("
            "日期 TEXT, 證券代號 TEXT, 證券名稱 TEXT, "
            "開盤價 TEXT, 收盤價 TEXT, 成交股數 INTEGER)"
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?)",
            (
                (
                    "20260904",
                    "2330",
                    "測試公司",
                    "9.80",
                    recommendation_close,
                    recommendation_volume,
                ),
                (
                    "20260907",
                    "2330",
                    "測試公司",
                    execution_open,
                    execution_close,
                    execution_volume,
                ),
            ),
        )
        if with_calendar:
            connection.execute("CREATE TABLE market_indices (日期 TEXT, 指數名稱 TEXT)")
            connection.execute(
                "INSERT INTO market_indices VALUES (?, ?)",
                ("20260904", "TAIEX"),
            )
            connection.execute(
                "INSERT INTO market_indices VALUES (?, ?)",
                ("20260907", "TAIEX"),
            )


def _paths(
    tmp_path: Path,
    *,
    with_calendar: bool = False,
    recommendation_close: str = "10.00",
    execution_open: str = "10.20",
    execution_close: str = "10.50",
    recommendation_volume: int = 90000,
    execution_volume: int | None = 100000,
) -> PaperExecutionPaths:
    recommendation = tmp_path / "recommendation.json"
    _recommendation(recommendation, price=recommendation_close)
    state = tmp_path / "state.sqlite"
    _state(state)
    market = tmp_path / "market.sqlite"
    _market(
        market,
        recommendation_close=recommendation_close,
        execution_open=execution_open,
        execution_close=execution_close,
        recommendation_volume=recommendation_volume,
        execution_volume=execution_volume,
        with_calendar=with_calendar,
    )
    ledger = tmp_path / "paper-ledger.sqlite"
    PaperTradeLedgerRepository(ledger)
    sector_path = tmp_path / "sector-membership.json"
    sector_hash = _write_sector_sidecar(sector_path)
    return PaperExecutionPaths(
        recommendation_json=recommendation,
        state_db=state,
        market_db=market,
        output_root=tmp_path / "candidate",
        ledger_db=ledger,
        sector_membership_path=sector_path,
        sector_membership_file_hash=sector_hash,
    )


def _legacy_eight_row_ledger(path: Path) -> None:
    """建立僅有舊 fill table 的 bounded fixture，不創造 transition 歷史。"""

    repository = PaperTradeLedgerRepository(path)
    for index in range(8):
        repository.append(
            PaperTradeFill(
                fill_id=f"legacy-rejected-{index}",
                order_id=f"legacy-order-{index}",
                portfolio_id="paper-main",
                event_date=DECISION_DATE,
                stock_code="2330",
                side="buy",
                requested_quantity=1000,
                filled_quantity=0,
                reference_price=Decimal("10.00"),
                fill_price=None,
                commission=Decimal("0.00"),
                tax=Decimal("0.00"),
                slippage_cost=Decimal("0.00"),
                turnover_bp=0,
                execution_gap_bp=None,
                status="rejected",
                source_event_id=f"legacy-source-{index}",
                source_type="paper_daily_execution_delayed_eod_replay_v1",
            )
        )
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE paper_trade_transitions")


def test_policy_history_keeps_eight_rows_before_latest_snapshot(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    _legacy_eight_row_ledger(ledger)
    before = ledger.read_bytes()
    start = paper_producer._policy_ledger_history_start(
        ledger, portfolio_id="paper-main", snapshot_date=date(2026, 9, 8),
        decision_date=date(2026, 10, 7),
    )
    assert start == date(2026, 9, 4)
    assert ledger.read_bytes() == before
    assert paper_producer._policy_ledger_history_start(
        ledger, portfolio_id="another-account", snapshot_date=date(2026, 9, 8),
        decision_date=date(2026, 10, 7),
    ) == date(2026, 9, 8)


def test_policy_history_excludes_future_and_rejects_invalid_dates(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    _legacy_eight_row_ledger(ledger)
    with sqlite3.connect(ledger) as connection:
        connection.execute("UPDATE paper_trade_ledger SET event_date = '2026-10-08'")
    kwargs = dict(portfolio_id="paper-main", snapshot_date=date(2026, 9, 8),
                  decision_date=date(2026, 10, 7))
    assert paper_producer._policy_ledger_history_start(ledger, **kwargs) == date(2026, 9, 8)
    with sqlite3.connect(ledger) as connection:
        connection.execute("UPDATE paper_trade_ledger SET event_date = 'invalid'")
    with pytest.raises(paper_producer.PaperExecutionProducerError):
        paper_producer._policy_ledger_history_start(ledger, **kwargs)


def _set_fixture_state_to_existing_target(path: Path) -> None:
    """將 fixture 持倉調到 recommendation 的 board-lot target。"""

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE paper_portfolio_positions "
            "SET quantity = 1000, market_value = '10000.00', weight_bp = 1000"
        )
        connection.execute(
            "UPDATE paper_portfolio_snapshots SET cash = '90000.00'"
        )


def _open_calendar() -> _Calendar:
    return _Calendar({DECISION_DATE, EXECUTION_DATE})


def _queue_paths_for_fixture(
    tmp_path: Path,
    input_paths: PaperExecutionPaths,
    *,
    output_name: str = "queue-candidate",
) -> PaperExecutionPaths:
    return PaperExecutionPaths(
        recommendation_json=tmp_path / "unused-placeholder.json",
        state_db=input_paths.state_db,
        market_db=input_paths.market_db,
        output_root=tmp_path / output_name,
        ledger_db=input_paths.ledger_db,
        sector_membership_path=input_paths.sector_membership_path,
        sector_membership_file_hash=input_paths.sector_membership_file_hash,
    )


def _receipt_payload(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_receipt_payload(
    path: Path,
    payload: dict[str, object],
    *,
    refresh_content_hash: bool = True,
) -> None:
    payload.pop("content_sha256", None)
    if refresh_content_hash:
        payload["content_sha256"] = paper_producer._payload_hash(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _queue_fixture_with_calendar_failure_and_processed_receipt(
    tmp_path: Path,
) -> dict[str, object]:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    queued_recommendation = recommendation_root / "scheduled_rec_20260904_200000.json"
    queued_recommendation.write_bytes(input_paths.recommendation_json.read_bytes())
    receipt_root = tmp_path / "receipts"

    failed = run_paper_execution_daily(
        input_paths,
        now=NOW,
        calendar=_UnknownCalendar(),
    )
    assert failed["status"] == "blocked"
    assert failed["blockers"] == [
        "official_calendar_not_proven:twse_holiday_schedule_unavailable"
    ]
    failed_with_receipt = persist_operational_receipt(
        failed,
        receipt_root,
        observed=NOW,
    )
    failed_operational_receipt = failed_with_receipt["operational_receipt"]
    assert isinstance(failed_operational_receipt, dict)
    failed_receipt_path = Path(str(failed_operational_receipt["path"]))
    failed_receipt_bytes = failed_receipt_path.read_bytes()

    queue_paths = _queue_paths_for_fixture(tmp_path, input_paths)
    processed = run_paper_execution_daily_from_queue(
        queue_paths,
        recommendation_root=recommendation_root,
        receipt_root=receipt_root,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert processed["status"] == "machine_verified_candidate"
    processed_operational_receipt = processed["operational_receipt"]
    assert isinstance(processed_operational_receipt, dict)
    assert processed_operational_receipt["queue_state"] == "processed"
    processed_receipt_path = Path(str(processed_operational_receipt["path"]))
    processed_receipt_bytes = processed_receipt_path.read_bytes()

    return {
        "input_paths": input_paths,
        "recommendation_root": recommendation_root,
        "queued_recommendation": queued_recommendation,
        "receipt_root": receipt_root,
        "queue_paths": queue_paths,
        "failed_receipt_path": failed_receipt_path,
        "failed_receipt_bytes": failed_receipt_bytes,
        "processed_receipt_path": processed_receipt_path,
        "processed_receipt_bytes": processed_receipt_bytes,
    }


def test_t1_next_session_uses_official_open_and_prior_close_binding(
    tmp_path: Path,
) -> None:
    result = run_paper_execution_daily(
        _paths(tmp_path),
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
    )

    assert result["status"] == "machine_verified_candidate"
    assert result["decision_date"] == DECISION_DATE
    assert result["execution_date"] == EXECUTION_DATE
    assert result["execution_contract"] == "t_plus_one_next_official_session_open"
    assert result["snapshot_semantics"] == "preopen_t_minus_one_mark_to_market"
    assert result["fill_count"] == 1
    fill = result["fills"][0]
    assert fill["event_date"] == EXECUTION_DATE
    assert fill["reference_price"] == "10.20"
    assert fill["fill_price"] == "10.25"
    assert result["recommendation"]["decision_date"] == DECISION_DATE
    assert result["market_source"]["execution_price_field"] == "開盤價"
    assert result["market_source"]["recommendation_reference_price_field"] == "收盤價"
    assert result["market_source"]["liquidity_volume_date"] == DECISION_DATE
    assert result["market_source"]["execution_data_availability"] == (
        "delayed_eod_replay_after_session_close"
    )
    assert result["market_source"]["realtime_execution_allowed"] is False
    assert result["cash_settlement_semantics"] == (
        "gross_amount_plus_commission_plus_tax_v1"
    )
    assert result["cost_attribution_semantics"] == (
        "commission_plus_tax_plus_slippage_attribution_v1"
    )
    assert result["fills"][0]["source_type"] == (
        "paper_daily_execution_delayed_eod_replay_v1"
    )


def test_recommendation_from_prior_natural_day_is_allowed_for_t1(
    tmp_path: Path,
) -> None:
    result = run_paper_execution_daily(
        _paths(tmp_path),
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
    )
    assert result["status"] == "machine_verified_candidate"


def test_sunday_decision_binds_previous_official_reference_session(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _recommendation(
        paths.recommendation_json,
        created_at="2026-09-06T20:00:00+08:00",
        decision_date="2026-09-06",
    )
    result = run_paper_execution_daily(
        paths,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
    )

    assert result["status"] == "machine_verified_candidate"
    assert result["decision_date"] == "2026-09-06"
    assert result["execution_date"] == EXECUTION_DATE
    assert result["market_reference_date"] == DECISION_DATE
    market_source = result["market_source"]
    assert isinstance(market_source, dict)
    assert market_source["decision_date"] == "2026-09-06"
    assert market_source["recommendation_reference_date"] == DECISION_DATE
    assert market_source["execution_date"] == EXECUTION_DATE
    assert market_source["recommendation_reference_date_basis"] == (
        "latest_proven_official_session_on_or_before_decision_date"
    )


def test_before_next_session_open_waits_without_reading_market_or_state(
    tmp_path: Path,
) -> None:
    result = run_paper_execution_daily(
        _paths(tmp_path),
        now=datetime(2026, 9, 7, 8, 59, tzinfo=TAIPEI),
        calendar=_open_calendar(),
    )

    assert result["status"] == "waiting_for_execution_session"
    assert result["execution_date"] == EXECUTION_DATE
    assert "fill_count" not in result


def test_before_delayed_eod_source_waits_without_reading_market_or_state(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    early_paths = PaperExecutionPaths(
        recommendation_json=paths.recommendation_json,
        state_db=tmp_path / "state-not-read.sqlite",
        market_db=tmp_path / "market-not-read.sqlite",
        output_root=tmp_path / "early-candidate",
    )
    result = run_paper_execution_daily(
        early_paths,
        now=NOW,
        calendar=_open_calendar(),
    )

    assert result["status"] == "waiting_for_execution_source"
    assert result["execution_date"] == EXECUTION_DATE
    assert result["execution_source_available_after"] == (
        "2026-09-07T15:00:00+08:00"
    )
    assert "fill_count" not in result
    assert not early_paths.state_db.exists()
    assert not early_paths.market_db.exists()


def test_late_next_session_is_not_historically_backfilled(tmp_path: Path) -> None:
    result = run_paper_execution_daily(
        _paths(tmp_path),
        now=datetime(2026, 9, 8, 10, 0, tzinfo=TAIPEI),
        calendar=_open_calendar(),
    )

    assert result["status"] == "blocked"
    assert any("session was missed" in item for item in result["blockers"])


def test_preopen_snapshot_is_reused_as_t1_state_without_overwrite(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _state(paths.state_db, decision_date=EXECUTION_DATE)
    state_before = _sha256(paths.state_db)
    result = run_paper_execution_daily(
        paths,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
    )

    assert result["status"] == "machine_verified_candidate"
    assert result["state_source"]["execution_snapshot_exists"] is True
    assert result["state_source"]["snapshot_transition_policy"] == (
        "preopen_snapshot_reused_append_only_postfill_transition"
    )
    assert result["ledger"]["appended"] is False
    assert _sha256(paths.state_db) == state_before


def test_existing_preopen_snapshot_can_append_after_candidate_and_retry_once(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _state(paths.state_db, decision_date=EXECUTION_DATE)
    ledger = paths.ledger_db
    assert ledger is not None
    state_before = _sha256(paths.state_db)

    candidate = run_paper_execution_daily(
        PaperExecutionPaths(**{**paths.__dict__, "output_root": tmp_path / "candidate"}),
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=False,
    )
    assert candidate["status"] == "machine_verified_candidate"
    assert candidate["ledger"]["appended"] is False
    assert _sha256(paths.state_db) == state_before
    assert PaperTradeLedgerRepository(ledger).list() == ()

    appended = run_paper_execution_daily(
        PaperExecutionPaths(**{**paths.__dict__, "output_root": tmp_path / "appended"}),
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert appended["status"] == "machine_verified_candidate"
    assert appended["ledger"]["appended"] is True
    assert appended["state_source"]["execution_snapshot_exists"] is True
    assert _sha256(paths.state_db) == state_before
    with sqlite3.connect(f"file:{ledger.resolve().as_posix()}?mode=ro", uri=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM paper_trade_ledger").fetchone()[0] == 1


def test_explicit_append_is_exactly_idempotent_after_preopen_snapshot_exists(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    ledger = paths.ledger_db
    assert ledger is not None
    first = run_paper_execution_daily(
        paths,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert first["status"] == "machine_verified_candidate"
    assert first["ledger"]["appended"] is True
    assert first["ledger"]["idempotent_replay"] is False

    _state(paths.state_db, decision_date=EXECUTION_DATE)
    retry_paths = PaperExecutionPaths(
        recommendation_json=paths.recommendation_json,
        state_db=paths.state_db,
        market_db=paths.market_db,
        output_root=tmp_path / "retry-candidate",
        ledger_db=ledger,
        sector_membership_path=paths.sector_membership_path,
        sector_membership_file_hash=paths.sector_membership_file_hash,
    )
    second = run_paper_execution_daily(
        retry_paths,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert second["status"] == "machine_verified_candidate"
    assert second["ledger"]["appended"] is True
    assert second["ledger"]["idempotent_replay"] is True
    with sqlite3.connect(f"file:{ledger.resolve().as_posix()}?mode=ro", uri=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM paper_trade_ledger").fetchone()[0] == 1


def test_eod_schema_readback_preserves_legacy_fills_and_is_idempotent(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "legacy-paper-ledger.sqlite"
    _legacy_eight_row_ledger(ledger)

    first_hash = _sha256(ledger)
    first = ensure_paper_ledger_schema(ledger)
    after_first_hash = _sha256(ledger)
    second = ensure_paper_ledger_schema(ledger)

    assert first["readback_verified"] is True
    assert first["row_counts"] == {
        "paper_trade_ledger": 8,
        "paper_trade_transitions": 0,
    }
    assert first["historical_transition_evidence_inferred"] is False
    assert second["row_counts"] == first["row_counts"]
    assert after_first_hash != first_hash
    assert _sha256(ledger) == after_first_hash
    with sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        assert connection.execute(
            "SELECT COUNT(*) FROM paper_trade_ledger"
        ).fetchone()[0] == 8
        assert connection.execute(
            "SELECT COUNT(*) FROM paper_trade_transitions"
        ).fetchone()[0] == 0


def test_eod_schema_readback_rejects_malformed_existing_transition_table(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "malformed-paper-ledger.sqlite"
    PaperTradeLedgerRepository(ledger)
    with sqlite3.connect(ledger) as connection:
        connection.execute("DROP TABLE paper_trade_transitions")
        connection.execute(
            "CREATE TABLE paper_trade_transitions ("
            "transition_id TEXT PRIMARY KEY, portfolio_id TEXT, event_date TEXT)"
        )

    with pytest.raises(ValueError, match="schema columns are missing"):
        ensure_paper_ledger_schema(ledger)


def test_candidate_without_append_confirmation_does_not_initialize_missing_transition_table(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    assert paths.ledger_db is not None
    _set_fixture_state_to_existing_target(paths.state_db)
    _legacy_eight_row_ledger(paths.ledger_db)
    before_hash = _sha256(paths.ledger_db)

    result = run_paper_execution_daily(
        paths,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=False,
    )

    assert result["status"] == "no_trade_required_candidate"
    assert result["fill_count"] == 0
    assert result["append_requested"] is False
    assert _sha256(paths.ledger_db) == before_hash
    with sqlite3.connect(paths.ledger_db.as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'paper_trade_transitions'"
        ).fetchone()[0] == 0


def test_missing_append_confirmation_does_not_create_ledger(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    result = run_paper_execution_daily(
        paths,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
    )

    assert result["status"] == "machine_verified_candidate"
    assert result["append_requested"] is False
    assert result["ledger"]["appended"] is False
    assert paths.ledger_db is not None
    assert PaperTradeLedgerRepository(paths.ledger_db).list() == ()


def test_zero_liquidity_cap_is_order_level_rejection(
    tmp_path: Path,
) -> None:
    result = run_paper_execution_daily(
        _paths(tmp_path, recommendation_volume=1000, execution_volume=999999),
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
    )

    assert result["status"] == "machine_verified_candidate"
    assert result["fill_count"] == 1
    fill = result["fills"][0]
    assert isinstance(fill, dict)
    assert fill["status"] == "rejected"
    assert fill["requested_quantity"] == 1000
    assert fill["filled_quantity"] == 0
    assert fill["remaining_quantity"] == 1000
    assert fill["execution_reason"] == "liquidity_cap_zero"
    projection = result["post_execution_projection"]
    assert isinstance(projection, dict)
    assert projection["positions"] == []


def test_partial_liquidity_continues_other_orders_and_carries_remaining_on_retry(
    tmp_path: Path,
) -> None:
    """低流動性只影響單筆委託，append/retry 與下一日 projection 均守恆。"""

    state = _State(
        snapshot_id="snapshot-partial",
        portfolio_id="paper-main",
        decision_date=date(2026, 9, 4),
        source_result_id="partial-test",
        cash=Decimal("70000.00"),
        total_value=Decimal("100000.00"),
        positions=(
            _Position(
                stock_code="2330",
                quantity=3000,
                mark_price=Decimal("10.00"),
                market_value=Decimal("30000.00"),
            ),
        ),
        content_hash="sha256:" + "1" * 64,
        file_hash="sha256:" + "2" * 64,
    )
    fills, projection = _build_fills(
        state=state,
        target={"2317": 3000, "2330": 0},
        prices={"2317": Decimal("10.00"), "2330": Decimal("10.00")},
        # 2330 的 5% 只有 1,500 股，向下取整後只能成交一張；
        # 2317 仍有足夠流動性，應繼續完成三張買入。
        volumes={"2317": 100000, "2330": 30000},
        execution_date=date(2026, 9, 7),
        policy=PaperPortfolioPolicyConfig(),
        recommendation_hash="sha256:" + "3" * 64,
    )

    assert [(fill.stock_code, fill.side, fill.status) for fill in fills] == [
        ("2330", "sell", "partially_filled"),
        ("2317", "buy", "filled"),
    ]
    outcomes = projection["order_outcomes"]
    assert isinstance(outcomes, list)
    assert outcomes[0]["requested_quantity"] == 3000
    assert outcomes[0]["filled_quantity"] == 1000
    assert outcomes[0]["remaining_quantity"] == 2000
    assert outcomes[0]["reason"] == "liquidity_cap_partial"
    assert outcomes[1]["requested_quantity"] == 3000
    assert outcomes[1]["filled_quantity"] == 3000
    assert outcomes[1]["remaining_quantity"] == 0

    # 獨立按每筆 fill 的結算費用重算，slippage_cost 只存在於 total_cost
    # 歸因，不可再從 gross 重扣。
    expected_cash = state.cash
    for fill in fills:
        if fill.side == "sell":
            expected_cash += fill.gross_amount - fill.cash_settlement_cost
        else:
            expected_cash -= fill.gross_amount + fill.cash_settlement_cost
    expected_cash = expected_cash.quantize(Decimal("0.01"))
    # 70000 + (9950 - 20 - 29.85) - (30150 + 45.23) = 49704.92。
    # 這個固定常數獨立於 property，避免 cash settlement property 本身錯誤時
    # 測試仍用同一錯誤公式得到綠燈。
    assert expected_cash == Decimal("49704.92")
    assert Decimal(str(projection["cash_after"])) == Decimal("49704.92")
    assert any(fill.total_cost > fill.cash_settlement_cost for fill in fills)
    positions = projection["positions"]
    assert isinstance(positions, list)
    assert {(item["stock_code"], item["quantity"]) for item in positions} == {
        ("2317", 3000),
        ("2330", 2000),
    }

    ledger = tmp_path / "partial-ledger.sqlite"
    assert _append_and_read_back(ledger, fills) is False
    assert _append_and_read_back(ledger, fills) is True
    assert len(PaperTradeLedgerRepository(ledger).list()) == 2

    projected_cash, _, projected_positions, event_ids, _ = _apply_prior_paper_fills(
        ledger,
        portfolio_id=state.portfolio_id,
        after_date=date(2026, 9, 7),
        before_date=date(2026, 9, 8),
        initial_cash=state.cash,
        initial_total=state.total_value,
        initial_positions=state.positions,
    )
    assert projected_cash == expected_cash
    assert event_ids == tuple(sorted(fill.fill_id for fill in fills))
    assert {item.stock_code: item.quantity for item in projected_positions} == {
        "2317": 3000,
        "2330": 2000,
    }


def test_low_cash_does_not_block_multiple_legal_sell_orders() -> None:
    """保留現金只限制買入，賣出可先增加現金再供後續委託使用。"""

    state = _State(
        snapshot_id="snapshot-low-cash",
        portfolio_id="paper-main",
        decision_date=date(2026, 9, 4),
        source_result_id="low-cash-test",
        cash=Decimal("1.00"),
        total_value=Decimal("20001.00"),
        positions=(
            _Position("2317", 1000, Decimal("10.00"), Decimal("10000.00")),
            _Position("2330", 1000, Decimal("10.00"), Decimal("10000.00")),
        ),
        content_hash="sha256:" + "4" * 64,
        file_hash="sha256:" + "5" * 64,
    )
    fills, projection = _build_fills(
        state=state,
        target={"2317": 0, "2330": 0},
        prices={"2317": Decimal("10.00"), "2330": Decimal("10.00")},
        volumes={"2317": 100000, "2330": 100000},
        execution_date=date(2026, 9, 7),
        policy=PaperPortfolioPolicyConfig(),
        recommendation_hash="sha256:" + "6" * 64,
    )

    assert len(fills) == 2
    assert all(fill.status == "filled" for fill in fills)
    assert all(fill.filled_quantity == 1000 for fill in fills)
    assert Decimal(str(projection["cash_after"])) > Decimal("1.00")


def test_execution_day_eod_volume_cannot_change_frozen_open_fill_or_cap(
    tmp_path: Path,
) -> None:
    normal_root = tmp_path / "normal"
    changed_root = tmp_path / "changed"
    normal_root.mkdir()
    changed_root.mkdir()
    normal = run_paper_execution_daily(
        _paths(
            normal_root,
            recommendation_volume=90000,
            execution_volume=100000,
        ),
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
    )
    changed = run_paper_execution_daily(
        _paths(
            changed_root,
            recommendation_volume=90000,
            execution_volume=1,
        ),
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
    )

    assert normal["status"] == "machine_verified_candidate"
    assert changed["status"] == "machine_verified_candidate"
    normal_fill = normal["fills"][0]
    changed_fill = changed["fills"][0]
    assert isinstance(normal_fill, dict)
    assert isinstance(changed_fill, dict)
    for field in (
        "reference_price",
        "fill_price",
        "requested_quantity",
        "filled_quantity",
    ):
        assert changed_fill[field] == normal_fill[field]
    normal_projection = normal["post_execution_projection"]
    changed_projection = changed["post_execution_projection"]
    assert isinstance(normal_projection, dict)
    assert isinstance(changed_projection, dict)
    assert changed_projection["volume_cap_shares"] == normal_projection["volume_cap_shares"]
    assert changed["market_source"]["liquidity_volume_date"] == DECISION_DATE


def test_queue_selects_due_frozen_recommendation_and_persists_processed_receipt(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    queued_recommendation = recommendation_root / "scheduled_rec_20260904.json"
    queued_recommendation.write_bytes(input_paths.recommendation_json.read_bytes())
    receipts = tmp_path / "receipts"
    ledger = tmp_path / "paper-ledger.sqlite"
    PaperTradeLedgerRepository(ledger)
    queue_paths = PaperExecutionPaths(
        recommendation_json=tmp_path / "unused-placeholder.json",
        state_db=input_paths.state_db,
        market_db=input_paths.market_db,
        output_root=tmp_path / "queue-candidate",
        ledger_db=ledger,
        sector_membership_path=input_paths.sector_membership_path,
        sector_membership_file_hash=input_paths.sector_membership_file_hash,
    )
    PaperTradeLedgerRepository(queue_paths.ledger_db)

    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipts,
    )
    assert selected == queued_recommendation
    assert reason == "next_official_session_due"

    result = run_paper_execution_daily_from_queue(
        queue_paths,
        recommendation_root=recommendation_root,
        receipt_root=receipts,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )

    assert result["status"] == "machine_verified_candidate"
    assert result["ledger"]["appended"] is True
    receipt = result["operational_receipt"]
    assert isinstance(receipt, dict)
    assert receipt["queue_state"] == "processed"
    receipt_path = Path(str(receipt["path"]))
    assert receipt_path.is_file()
    receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt_payload["source_file_hash"] == result["recommendation"]["file_hash"]
    assert receipt_payload["queue_state"] == "processed"
    selected_again, reason_again = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipts,
    )
    assert selected_again is None
    assert reason_again == "no_pending_recommendation_already_processed"
    selected_without_market_db, reason_without_market_db = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        receipt_root=receipts,
    )
    assert selected_without_market_db is None
    assert reason_without_market_db == "no_pending_recommendation"


def test_scoped_frozen_queue_ignores_legacy_invalid_sources_and_hashes_policy(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    frozen_path = recommendation_root / "paper_frozen_current.json"
    frozen_payload = json.loads(input_paths.recommendation_json.read_text(encoding="utf-8"))
    frozen_payload["result_id"] = "canonical-result-current"
    frozen_path.write_text(
        json.dumps(frozen_payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    legacy_invalid = recommendation_root / "scheduled_rec_20260105_165133.json"
    legacy_payload = dict(frozen_payload)
    legacy_payload["result_id"] = "legacy-naive-clock"
    legacy_payload["created_at"] = "2026-09-04T20:00:00"
    legacy_invalid.write_text(
        json.dumps(legacy_payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt_root = tmp_path / "receipts"
    paths = _queue_paths_for_fixture(tmp_path, input_paths)

    result = run_paper_execution_daily_from_queue(
        paths,
        recommendation_root=recommendation_root,
        receipt_root=receipt_root,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
        recommendation_pattern="paper_frozen_*.json",
    )

    assert result["status"] == "machine_verified_candidate"
    assert result["recommendation"]["path"] == str(frozen_path.resolve())
    assert result["ledger"]["readback_verified"] is True
    selection = result["queue_selection"]
    assert selection["policy"] == "fixed_recommendation_filename_pattern.v1"
    assert selection["recommendation_pattern"] == "paper_frozen_*.json"
    assert selection["scope"] == "paper_frozen_recommendation_exports_only"
    assert "legacy_pending_source_fallbacks" not in selection

    candidate_path = Path(str(result["candidate_path"]))
    candidate = _receipt_payload(candidate_path)
    candidate_hash = candidate.pop("content_sha256")
    assert candidate_hash == paper_producer._payload_hash(candidate)
    assert candidate["queue_selection"] == selection

    operational = result["operational_receipt"]
    assert isinstance(operational, dict)
    operational_path = Path(str(operational["path"]))
    operational_payload = _receipt_payload(operational_path)
    assert operational_payload["queue_state"] == "processed"
    assert operational_payload["result"]["queue_selection"] == selection
    assert paper_producer._validate_queue_receipt(
        operational_path,
        operational_payload,
    ) is None
    assert legacy_invalid.is_file()


def _scoped_pending_fallback_fixture(
    tmp_path: Path,
    *,
    source_name: str = "legacy-source.json",
    initial_pattern: str = "*.json",
) -> dict[str, object]:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    legacy_source = recommendation_root / source_name
    legacy_source.write_bytes(input_paths.recommendation_json.read_bytes())
    receipt_root = tmp_path / "receipts"
    queue_paths = _queue_paths_for_fixture(tmp_path, input_paths)
    with sqlite3.connect(input_paths.market_db) as connection:
        connection.execute(
            "DELETE FROM daily_prices WHERE 日期=? AND 證券代號=?",
            ("20260907", "2330"),
        )
    pending = run_paper_execution_daily_from_queue(
        queue_paths,
        recommendation_root=recommendation_root,
        receipt_root=receipt_root,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
        recommendation_pattern=initial_pattern,
    )
    assert pending["status"] == "blocked"
    pending_receipt = pending["operational_receipt"]
    assert isinstance(pending_receipt, dict)
    assert pending_receipt["queue_state"] == "pending_execution"
    pending_receipt_path = Path(str(pending_receipt["path"]))
    pending_receipt_bytes = pending_receipt_path.read_bytes()

    newer_payload = json.loads(legacy_source.read_text(encoding="utf-8"))
    newer_payload["result_id"] = "scheduled_rec_20260904_210000"
    newer_payload["created_at"] = "2026-09-04T21:00:00+08:00"
    frozen_source = recommendation_root / "paper_frozen_newer.json"
    frozen_source.write_text(
        json.dumps(newer_payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with sqlite3.connect(input_paths.market_db) as connection:
        connection.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?)",
            ("20260907", "2330", "測試公司", "10.20", "10.50", 100000),
        )
    return {
        "input_paths": input_paths,
        "recommendation_root": recommendation_root,
        "receipt_root": receipt_root,
        "queue_paths": queue_paths,
        "legacy_source": legacy_source,
        "frozen_source": frozen_source,
        "pending_receipt_path": pending_receipt_path,
        "pending_receipt_bytes": pending_receipt_bytes,
    }


def test_scoped_queue_retries_pinned_scoped_source_with_writer_readback(
    tmp_path: Path,
) -> None:
    fixture = _scoped_pending_fallback_fixture(
        tmp_path,
        source_name="paper_frozen_pinned.json",
        initial_pattern="paper_frozen_*.json",
    )
    input_paths = fixture["input_paths"]
    assert isinstance(input_paths, PaperExecutionPaths)
    pinned_source = Path(str(fixture["legacy_source"]))
    newer_source = Path(str(fixture["frozen_source"]))
    pending_receipt_path = Path(str(fixture["pending_receipt_path"]))
    pending_receipt_bytes = bytes(fixture["pending_receipt_bytes"])

    retry = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            **{
                **fixture["queue_paths"].__dict__,
                "output_root": tmp_path / "scoped-pinned-retry-candidate",
            }
        ),
        recommendation_root=Path(str(fixture["recommendation_root"])),
        receipt_root=Path(str(fixture["receipt_root"])),
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
        recommendation_pattern="paper_frozen_*.json",
    )

    assert retry["status"] == "machine_verified_candidate"
    assert retry["recommendation"]["path"] == str(pinned_source.resolve())
    assert retry["ledger"]["readback_verified"] is True
    assert retry["operational_receipt"]["queue_state"] == "processed"
    selection = retry["queue_selection"]
    assert selection["recommendation_pattern"] == "paper_frozen_*.json"
    assert "legacy_pending_source_fallbacks" not in selection

    candidate_path = Path(str(retry["candidate_path"]))
    candidate = _receipt_payload(candidate_path)
    candidate_hash = candidate.pop("content_sha256")
    assert candidate_hash == paper_producer._payload_hash(candidate)
    assert candidate["queue_selection"] == selection

    operational = retry["operational_receipt"]
    assert isinstance(operational, dict)
    operational_path = Path(str(operational["path"]))
    operational_payload = _receipt_payload(operational_path)
    assert operational_payload["result"]["recommendation"]["path"] == str(
        pinned_source.resolve()
    )
    assert paper_producer._validate_queue_receipt(
        operational_path,
        operational_payload,
    ) is None
    assert pending_receipt_path.read_bytes() == pending_receipt_bytes
    assert newer_source.is_file()


@pytest.mark.parametrize("source_change", ("tampered", "missing"))
def test_scoped_pending_source_cannot_be_replaced_after_integrity_failure(
    tmp_path: Path,
    source_change: str,
) -> None:
    fixture = _scoped_pending_fallback_fixture(
        tmp_path,
        source_name="paper_frozen_pinned.json",
        initial_pattern="paper_frozen_*.json",
    )
    pinned_source = Path(str(fixture["legacy_source"]))
    replacement_source = Path(str(fixture["frozen_source"]))
    if source_change == "missing":
        pinned_source.unlink()
    else:
        pinned_payload = json.loads(pinned_source.read_text(encoding="utf-8"))
        pinned_payload["recommendations"][0]["收盤價"] = "9.99"
        pinned_source.write_text(
            json.dumps(pinned_payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    result = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            **{
                **fixture["queue_paths"].__dict__,
                "output_root": tmp_path / "scoped-invalid-pinned-retry",
            }
        ),
        recommendation_root=Path(str(fixture["recommendation_root"])),
        receipt_root=Path(str(fixture["receipt_root"])),
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
        recommendation_pattern="paper_frozen_*.json",
    )

    assert result["status"] == "blocked"
    assert result["blockers"][0].startswith("pending_execution_receipt_invalid:")
    assert result.get("recommendation") is None
    assert "ledger" not in result
    assert replacement_source.is_file()


def test_future_invalid_pending_receipt_does_not_change_current_queue_state(
    tmp_path: Path,
) -> None:
    fixture = _scoped_pending_fallback_fixture(
        tmp_path,
        source_name="paper_frozen_pinned.json",
        initial_pattern="paper_frozen_*.json",
    )
    pinned_source = Path(str(fixture["legacy_source"]))
    pinned_payload = json.loads(pinned_source.read_text(encoding="utf-8"))
    pinned_payload["recommendations"][0]["收盤價"] = "9.99"
    pinned_source.write_text(
        json.dumps(pinned_payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    pending_receipt_path = Path(str(fixture["pending_receipt_path"]))
    pending_receipt = _receipt_payload(pending_receipt_path)
    pending_receipt["recorded_at"] = "2026-09-08T03:00:00+00:00"
    _write_receipt_payload(pending_receipt_path, pending_receipt)
    input_paths = fixture["input_paths"]
    assert isinstance(input_paths, PaperExecutionPaths)

    selected, reason = resolve_pending_recommendation(
        Path(str(fixture["recommendation_root"])),
        observed=EOD_REPLAY_NOW,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=Path(str(fixture["receipt_root"])),
        recommendation_pattern="paper_frozen_*.json",
    )

    assert selected == Path(str(fixture["frozen_source"]))
    assert reason == "next_official_session_due"


@pytest.mark.parametrize(
    ("source_name", "initial_pattern"),
    (
        ("paper_frozen_pinned.json", "paper_frozen_*.json"),
        ("legacy-pinned.json", "*.json"),
    ),
    ids=("scoped-pending", "legacy-pending-fallback"),
)
def test_queue_selection_pins_bytes_until_producer_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_name: str,
    initial_pattern: str,
) -> None:
    fixture = _scoped_pending_fallback_fixture(
        tmp_path,
        source_name=source_name,
        initial_pattern=initial_pattern,
    )
    pinned_source = Path(str(fixture["legacy_source"]))
    input_paths = fixture["input_paths"]
    assert isinstance(input_paths, PaperExecutionPaths)
    with sqlite3.connect(input_paths.ledger_db) as connection:
        fill_count_before = int(
            connection.execute("SELECT COUNT(*) FROM paper_trade_ledger").fetchone()[0]
        )

    original_resolver = paper_producer.resolve_pending_recommendation

    def resolve_then_replace_selected_source(*args: object, **kwargs: object):
        selected, reason = original_resolver(*args, **kwargs)
        if selected is not None:
            replacement = json.loads(selected.read_text(encoding="utf-8"))
            replacement["result_id"] = "replacement_after_queue_selection"
            replacement["recommendations"][0]["總分"] = "99.00"
            selected.write_text(
                json.dumps(replacement, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return selected, reason

    monkeypatch.setattr(
        paper_producer,
        "resolve_pending_recommendation",
        resolve_then_replace_selected_source,
    )
    result = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            **{
                **fixture["queue_paths"].__dict__,
                "output_root": tmp_path / "source-changed-after-selection",
            }
        ),
        recommendation_root=Path(str(fixture["recommendation_root"])),
        receipt_root=Path(str(fixture["receipt_root"])),
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
        recommendation_pattern="paper_frozen_*.json",
    )

    assert result["status"] == "blocked"
    assert result["blockers"] == ["selected source identity changed after selection"]
    selection = result["queue_selection"]
    assert selection["selected_source_identity"]["recommendation_path"] == str(
        pinned_source.resolve()
    )
    assert selection["selected_source_identity"]["source_result_id"] != (
        "replacement_after_queue_selection"
    )
    candidate_path = Path(str(result["candidate_path"]))
    candidate = _receipt_payload(candidate_path)
    candidate_hash = candidate.pop("content_sha256")
    assert candidate_hash == paper_producer._payload_hash(candidate)
    assert candidate["queue_selection"] == selection
    with sqlite3.connect(input_paths.ledger_db) as connection:
        fill_count_after = int(
            connection.execute("SELECT COUNT(*) FROM paper_trade_ledger").fetchone()[0]
        )
    assert fill_count_after == fill_count_before


def test_scoped_queue_retries_exact_legacy_pending_and_reads_back_fallback_proof(
    tmp_path: Path,
) -> None:
    fixture = _scoped_pending_fallback_fixture(tmp_path)
    input_paths = fixture["input_paths"]
    assert isinstance(input_paths, PaperExecutionPaths)
    legacy_source = Path(str(fixture["legacy_source"]))
    frozen_source = Path(str(fixture["frozen_source"]))
    pending_receipt_path = Path(str(fixture["pending_receipt_path"]))
    pending_receipt_bytes = bytes(fixture["pending_receipt_bytes"])

    retry = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            **{
                **fixture["queue_paths"].__dict__,
                "output_root": tmp_path / "scoped-retry-candidate",
            }
        ),
        recommendation_root=Path(str(fixture["recommendation_root"])),
        receipt_root=Path(str(fixture["receipt_root"])),
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
        recommendation_pattern="paper_frozen_*.json",
    )

    assert retry["status"] == "machine_verified_candidate"
    assert retry["recommendation"]["path"] == str(legacy_source.resolve())
    assert retry["ledger"]["readback_verified"] is True
    selection = retry["queue_selection"]
    fallbacks = selection["legacy_pending_source_fallbacks"]
    assert len(fallbacks) == 1
    proof = fallbacks[0]
    assert proof["recommendation_path"] == str(legacy_source.resolve())
    assert proof["source_file_hash"] == retry["recommendation"]["file_hash"]
    assert proof["source_result_id"] == retry["recommendation"]["result_id"]
    assert proof["decision_date"] == DECISION_DATE
    assert proof["execution_date"] == EXECUTION_DATE
    assert proof["source_created_at"] <= proof["pending_recorded_at"]
    assert proof["pending_receipt_path"] == str(pending_receipt_path.resolve())
    assert frozen_source.is_file()

    candidate_path = Path(str(retry["candidate_path"]))
    candidate = _receipt_payload(candidate_path)
    candidate_hash = candidate.pop("content_sha256")
    assert candidate_hash == paper_producer._payload_hash(candidate)
    assert candidate["queue_selection"] == selection
    operational = retry["operational_receipt"]
    assert isinstance(operational, dict)
    operational_path = Path(str(operational["path"]))
    operational_payload = _receipt_payload(operational_path)
    assert operational_payload["result"]["queue_selection"] == selection
    assert paper_producer._validate_queue_receipt(
        operational_path,
        operational_payload,
    ) is None
    assert pending_receipt_path.read_bytes() == pending_receipt_bytes


@pytest.mark.parametrize(
    ("tamper", "expected_reason"),
    (
        ("source_hash", "pending_execution_receipt_invalid"),
        ("wrong_portfolio", "pending_execution_receipt_invalid"),
        ("wrong_result_id", "pending_execution_receipt_invalid"),
        ("future_source_clock", "pending_execution_receipt_invalid"),
        ("duplicate_source", "pending_execution_source_duplicate"),
    ),
)
def test_scoped_pending_fallback_fails_closed_without_switching_sources(
    tmp_path: Path,
    tamper: str,
    expected_reason: str,
) -> None:
    fixture = _scoped_pending_fallback_fixture(tmp_path)
    legacy_source = Path(str(fixture["legacy_source"]))
    payload = json.loads(legacy_source.read_text(encoding="utf-8"))
    if tamper == "source_hash":
        payload["recommendations"][0]["收盤價"] = "9.99"
        legacy_source.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    elif tamper == "wrong_portfolio":
        payload["config"]["portfolio_id"] = "paper-other"
        legacy_source.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    elif tamper == "wrong_result_id":
        payload["result_id"] = "different-result"
        legacy_source.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    elif tamper == "future_source_clock":
        payload["created_at"] = "2026-09-07T15:00:01+08:00"
        legacy_source.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    elif tamper == "duplicate_source":
        duplicate = Path(str(fixture["recommendation_root"])) / "duplicate-copy.json"
        duplicate.write_bytes(legacy_source.read_bytes())

    result = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            **{
                **fixture["queue_paths"].__dict__,
                "output_root": tmp_path / "blocked-scoped-retry",
            }
        ),
        recommendation_root=Path(str(fixture["recommendation_root"])),
        receipt_root=Path(str(fixture["receipt_root"])),
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
        recommendation_pattern="paper_frozen_*.json",
    )

    assert result["status"] == "blocked"
    assert str(result["blockers"][0]).startswith(expected_reason)
    assert "ledger" not in result
    assert result.get("recommendation") is None
    assert Path(str(fixture["frozen_source"])).is_file()


def test_scoped_queue_still_validates_every_queue_receipt_and_pattern_is_fixed(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    frozen_path = recommendation_root / "paper_frozen_current.json"
    frozen_payload = json.loads(input_paths.recommendation_json.read_text(encoding="utf-8"))
    frozen_payload["result_id"] = "canonical-result-current"
    frozen_payload["created_at"] = "2026-09-03T20:00:00+08:00"
    frozen_payload["config"]["decision_date"] = "2026-09-03"
    frozen_payload["recommendations"][0]["eligible_universe_date"] = "2026-09-03"
    frozen_path.write_text(
        json.dumps(frozen_payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt_root = tmp_path / "receipts"
    receipt_root.mkdir()
    (receipt_root / "unrelated-corrupt-receipt.json").write_text(
        "{invalid", encoding="utf-8"
    )
    frozen_path.unlink()

    blocked = run_paper_execution_daily_from_queue(
        _queue_paths_for_fixture(tmp_path, input_paths, output_name="bad-receipt"),
        recommendation_root=recommendation_root,
        receipt_root=receipt_root,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        recommendation_pattern="paper_frozen_*.json",
    )
    assert blocked["status"] == "blocked"
    assert "no_pending_recommendation_invalid_receipt" in blocked["blockers"][0]
    assert not Path(str(blocked["operational_receipt"]["path"])).name.startswith(
        "unrelated-corrupt"
    )

    with pytest.raises(paper_producer.PaperExecutionProducerError):
        resolve_pending_recommendation(
            recommendation_root,
            observed=EOD_REPLAY_NOW,
            market_db=input_paths.market_db,
            calendar=_open_calendar(),
            receipt_root=None,
            recommendation_pattern="**/*.json",
        )


def test_later_processed_source_resolves_old_calendar_failure_with_auditable_noop(
    tmp_path: Path,
) -> None:
    fixture = _queue_fixture_with_calendar_failure_and_processed_receipt(tmp_path)
    recommendation_root = Path(str(fixture["recommendation_root"]))
    receipt_root = Path(str(fixture["receipt_root"]))
    queued_recommendation = Path(str(fixture["queued_recommendation"]))
    input_paths = fixture["input_paths"]
    assert isinstance(input_paths, PaperExecutionPaths)
    failed_receipt_path = Path(str(fixture["failed_receipt_path"]))
    processed_receipt_path = Path(str(fixture["processed_receipt_path"]))
    failed_receipt_bytes = bytes(fixture["failed_receipt_bytes"])
    processed_receipt_bytes = bytes(fixture["processed_receipt_bytes"])

    failed_receipt = _receipt_payload(failed_receipt_path)
    processed_receipt = _receipt_payload(processed_receipt_path)
    assert paper_producer._validate_queue_receipt(
        failed_receipt_path,
        failed_receipt,
    ) == "execution_date_missing"
    assert paper_producer._validate_queue_receipt(
        processed_receipt_path,
        processed_receipt,
    ) is None
    assert processed_receipt["ledger"]["readback_verified"] is True

    resolved_diagnostics: list[dict[str, str]] = []
    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipt_root,
        _resolved_historical_receipt_diagnostics=resolved_diagnostics,
    )
    assert selected is None
    assert reason == "no_pending_recommendation_already_processed"
    assert len(resolved_diagnostics) == 1
    proof = resolved_diagnostics[0]
    assert proof["issue"] == f"{failed_receipt_path.name}:execution_date_missing"
    assert proof["source_file_hash"] == processed_receipt["source_file_hash"]
    assert proof["source_result_id"] == processed_receipt["source_result_id"]
    assert proof["portfolio_id"] == processed_receipt["portfolio_id"]
    assert proof["resolved_by_processed_receipt"] == str(processed_receipt_path.resolve())
    assert proof["processed_recorded_at"] > proof["issue_recorded_at"]
    assert proof["processed_execution_date"] == EXECUTION_DATE
    assert proof["processed_receipt_content_sha256"] == processed_receipt["content_sha256"]

    def ledger_fill_count(path: Path) -> int:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            return int(
                connection.execute("SELECT COUNT(*) FROM paper_trade_ledger").fetchone()[0]
            )

    ledger_count_before = ledger_fill_count(input_paths.ledger_db)
    no_op_paths = _queue_paths_for_fixture(
        tmp_path,
        input_paths,
        output_name="already-processed-noop",
    )
    no_op = run_paper_execution_daily_from_queue(
        no_op_paths,
        recommendation_root=recommendation_root,
        receipt_root=receipt_root,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert no_op["status"] == "skipped_no_pending_recommendation"
    assert no_op["blockers"] == ["no_pending_recommendation_already_processed"]
    queue = no_op["queue"]
    assert isinstance(queue, dict)
    assert queue["resolved_historical_receipts"] == resolved_diagnostics
    assert ledger_fill_count(input_paths.ledger_db) == ledger_count_before

    candidate_path = Path(str(no_op["candidate_path"]))
    candidate = _receipt_payload(candidate_path)
    candidate_content_hash = candidate.pop("content_sha256")
    assert candidate_content_hash == no_op["content_sha256"]
    assert candidate_content_hash == paper_producer._payload_hash(candidate)
    assert paper_producer._file_sha256(candidate_path) == no_op["candidate_file_hash"]

    no_op_operational_receipt = no_op["operational_receipt"]
    assert isinstance(no_op_operational_receipt, dict)
    no_op_receipt_path = Path(str(no_op_operational_receipt["path"]))
    no_op_receipt = _receipt_payload(no_op_receipt_path)
    no_op_receipt_hash = no_op_receipt.pop("content_sha256")
    assert no_op_receipt_hash == paper_producer._payload_hash(no_op_receipt)
    assert no_op_receipt["result"]["queue"]["resolved_historical_receipts"] == (
        resolved_diagnostics
    )

    assert queued_recommendation.is_file()
    assert failed_receipt_path.read_bytes() == failed_receipt_bytes
    assert processed_receipt_path.read_bytes() == processed_receipt_bytes


def test_selected_queue_candidate_hashes_resolved_historical_receipt_proof(
    tmp_path: Path,
) -> None:
    fixture = _queue_fixture_with_calendar_failure_and_processed_receipt(tmp_path)
    input_paths = fixture["input_paths"]
    assert isinstance(input_paths, PaperExecutionPaths)
    recommendation_root = Path(str(fixture["recommendation_root"]))
    new_recommendation = recommendation_root / "paper_frozen_next_session.json"
    _recommendation(
        new_recommendation,
        created_at="2026-09-07T20:00:00+08:00",
        decision_date="2026-09-07",
        price="10.50",
    )
    new_payload = _receipt_payload(new_recommendation)
    new_payload["result_id"] = "scheduled_rec_20260907_200000"
    new_recommendation.write_text(
        json.dumps(new_payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with sqlite3.connect(input_paths.market_db) as connection:
        connection.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?)",
            ("20260908", "2330", "測試公司", "10.50", "10.60", 100000),
        )

    result = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            **{
                **fixture["queue_paths"].__dict__,
                "output_root": tmp_path / "selected-with-history-proof",
            }
        ),
        recommendation_root=recommendation_root,
        receipt_root=Path(str(fixture["receipt_root"])),
        now=datetime(2026, 9, 8, 15, 0, tzinfo=TAIPEI),
        calendar=_Calendar({DECISION_DATE, EXECUTION_DATE, "2026-09-08"}),
        confirm_append=False,
    )

    assert result["recommendation"]["path"] == str(new_recommendation.resolve())
    selection = result["queue_selection"]
    resolved = selection["resolved_historical_receipts"]
    assert len(resolved) == 1
    assert resolved[0]["source_result_id"] == "scheduled_rec_20260904_200000"
    candidate_path = Path(str(result["candidate_path"]))
    candidate = _receipt_payload(candidate_path)
    candidate_hash = candidate.pop("content_sha256")
    assert candidate_hash == paper_producer._payload_hash(candidate)
    assert candidate["queue_selection"] == selection


@pytest.mark.parametrize(
    "invalid_change",
    (
        "wrong_source_hash",
        "wrong_portfolio",
        "wrong_result_id",
        "other_blocker",
        "tampered_issue_hash",
        "invalid_processed_readback",
    ),
)
def test_nonmatching_or_invalid_queue_receipts_remain_blocking(
    tmp_path: Path,
    invalid_change: str,
) -> None:
    fixture = _queue_fixture_with_calendar_failure_and_processed_receipt(tmp_path)
    recommendation_root = Path(str(fixture["recommendation_root"]))
    receipt_root = Path(str(fixture["receipt_root"]))
    input_paths = fixture["input_paths"]
    assert isinstance(input_paths, PaperExecutionPaths)
    failed_receipt_path = Path(str(fixture["failed_receipt_path"]))
    processed_receipt_path = Path(str(fixture["processed_receipt_path"]))

    if invalid_change == "invalid_processed_readback":
        processed_receipt = _receipt_payload(processed_receipt_path)
        ledger = processed_receipt["ledger"]
        result = processed_receipt["result"]
        assert isinstance(ledger, dict)
        assert isinstance(result, dict)
        result_ledger = result["ledger"]
        assert isinstance(result_ledger, dict)
        ledger["readback_verified"] = False
        result_ledger["readback_verified"] = False
        _write_receipt_payload(processed_receipt_path, processed_receipt)
        assert paper_producer._validate_queue_receipt(
            processed_receipt_path,
            _receipt_payload(processed_receipt_path),
        ) == "processed_ledger_readback_not_verified"
    else:
        failed_receipt = _receipt_payload(failed_receipt_path)
        if invalid_change == "wrong_source_hash":
            failed_receipt["source_file_hash"] = "sha256:" + ("f" * 64)
            _write_receipt_payload(failed_receipt_path, failed_receipt)
        elif invalid_change == "wrong_portfolio":
            failed_receipt["portfolio_id"] = "paper-other"
            _write_receipt_payload(failed_receipt_path, failed_receipt)
        elif invalid_change == "wrong_result_id":
            failed_receipt["source_result_id"] = "different-result"
            _write_receipt_payload(failed_receipt_path, failed_receipt)
        elif invalid_change == "other_blocker":
            result = failed_receipt["result"]
            assert isinstance(result, dict)
            result["blockers"] = ["paper_market_data_missing"]
            _write_receipt_payload(failed_receipt_path, failed_receipt)
        else:
            result = failed_receipt["result"]
            assert isinstance(result, dict)
            result["blockers"] = ["different_blocker"]
            _write_receipt_payload(
                failed_receipt_path,
                failed_receipt,
                refresh_content_hash=False,
            )

    resolved_diagnostics: list[dict[str, str]] = []
    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipt_root,
        _resolved_historical_receipt_diagnostics=resolved_diagnostics,
    )
    if invalid_change == "invalid_processed_readback":
        assert selected == Path(str(fixture["queued_recommendation"]))
        assert reason == "next_official_session_due"
        assert resolved_diagnostics == []
        return
    assert selected is None
    assert reason.startswith("pending_execution_receipt_invalid:")
    assert resolved_diagnostics == []


def test_processed_receipt_before_calendar_failure_does_not_resolve_it(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    queued_recommendation = recommendation_root / "scheduled_rec_20260904_200000.json"
    queued_recommendation.write_bytes(input_paths.recommendation_json.read_bytes())
    receipt_root = tmp_path / "receipts"
    queue_paths = _queue_paths_for_fixture(tmp_path, input_paths)

    processed = run_paper_execution_daily_from_queue(
        queue_paths,
        recommendation_root=recommendation_root,
        receipt_root=receipt_root,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert processed["operational_receipt"]["queue_state"] == "processed"

    later_failure_time = datetime(2026, 9, 7, 15, 1, tzinfo=TAIPEI)
    failed = run_paper_execution_daily(
        input_paths,
        now=later_failure_time,
        calendar=_UnknownCalendar(),
    )
    failed_with_receipt = persist_operational_receipt(
        failed,
        receipt_root,
        observed=later_failure_time,
    )
    failed_operational_receipt = failed_with_receipt["operational_receipt"]
    assert isinstance(failed_operational_receipt, dict)
    failed_receipt_path = Path(str(failed_operational_receipt["path"]))
    assert paper_producer._validate_queue_receipt(
        failed_receipt_path,
        _receipt_payload(failed_receipt_path),
    ) == "execution_date_missing"

    resolved_diagnostics: list[dict[str, str]] = []
    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=later_failure_time,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipt_root,
        _resolved_historical_receipt_diagnostics=resolved_diagnostics,
    )
    assert selected is None
    assert reason.startswith("no_pending_recommendation_already_processed_invalid_receipt:")
    assert resolved_diagnostics == []


def test_future_processed_receipt_does_not_resolve_calendar_failure_yet(
    tmp_path: Path,
) -> None:
    fixture = _queue_fixture_with_calendar_failure_and_processed_receipt(tmp_path)
    recommendation_root = Path(str(fixture["recommendation_root"]))
    receipt_root = Path(str(fixture["receipt_root"]))
    input_paths = fixture["input_paths"]
    assert isinstance(input_paths, PaperExecutionPaths)
    queued_recommendation = Path(str(fixture["queued_recommendation"]))
    observed_before_terminal = datetime(2026, 9, 7, 14, 59, tzinfo=TAIPEI)

    resolved_diagnostics: list[dict[str, str]] = []
    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=observed_before_terminal,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipt_root,
        _resolved_historical_receipt_diagnostics=resolved_diagnostics,
    )
    assert selected == queued_recommendation
    assert reason == "next_official_session_due"
    assert resolved_diagnostics == []


def test_superseded_receipt_does_not_resolve_calendar_failure(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    queued_recommendation = recommendation_root / "scheduled_rec_20260904_200000.json"
    queued_recommendation.write_bytes(input_paths.recommendation_json.read_bytes())
    receipt_root = tmp_path / "receipts"

    failed = run_paper_execution_daily(
        input_paths,
        now=NOW,
        calendar=_UnknownCalendar(),
    )
    failed_with_receipt = persist_operational_receipt(
        failed,
        receipt_root,
        observed=NOW,
    )
    failed_operational_receipt = failed_with_receipt["operational_receipt"]
    assert isinstance(failed_operational_receipt, dict)
    failed_receipt_path = Path(str(failed_operational_receipt["path"]))

    recommendation = paper_producer._load_recommendation(
        queued_recommendation,
        observed=EOD_REPLAY_NOW,
    )
    paper_producer._write_superseded_receipt(
        recommendation,
        execution_date=date.fromisoformat(EXECUTION_DATE),
        selected_source_file_hash="sha256:" + ("e" * 64),
        receipt_root=receipt_root,
        observed=EOD_REPLAY_NOW,
    )
    superseded_path = next(receipt_root.glob("paper_execution_superseded_*.json"))
    assert paper_producer._validate_queue_receipt(
        superseded_path,
        _receipt_payload(superseded_path),
    ) is None
    assert paper_producer._validate_queue_receipt(
        failed_receipt_path,
        _receipt_payload(failed_receipt_path),
    ) == "execution_date_missing"

    resolved_diagnostics: list[dict[str, str]] = []
    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipt_root,
        _resolved_historical_receipt_diagnostics=resolved_diagnostics,
    )
    assert selected is None
    assert reason == "no_pending_recommendation_due_for_current_session"
    assert resolved_diagnostics == []


def test_effective_queue_receipts_are_observed_and_identity_scoped() -> None:
    observed = datetime(2026, 9, 8, 2, 0, tzinfo=timezone.utc)
    source_hash = "sha256:" + "a" * 64
    other_hash = "sha256:" + "b" * 64

    def receipt(
        *,
        state: str,
        portfolio: str,
        execution_day: str,
        source: str,
        recorded_at: str,
        name: str,
    ) -> _QueueReceipt:
        return _QueueReceipt(
            path=Path(name),
            state=state,
            source_file_hash=source,
            source_result_id="result",
            portfolio_id=portfolio,
            execution_date=date.fromisoformat(execution_day),
            recorded_at=datetime.fromisoformat(recorded_at),
        )

    effective, conflicts = _effective_queue_receipts(
        (
            receipt(
                state="pending_execution",
                portfolio="paper-main",
                execution_day="2026-09-07",
                source=source_hash,
                recorded_at="2026-09-07T02:00:00+00:00",
                name="pending.json",
            ),
            receipt(
                state="processed",
                portfolio="paper-main",
                execution_day="2026-09-07",
                source=source_hash,
                recorded_at="2026-09-07T07:00:00+00:00",
                name="processed.json",
            ),
            receipt(
                state="pending_execution",
                portfolio="paper-main",
                execution_day="2026-09-07",
                source=source_hash,
                recorded_at="2026-09-07T08:00:00+00:00",
                name="late-pending.json",
            ),
            receipt(
                state="processed",
                portfolio="paper-other",
                execution_day="2026-09-07",
                source=source_hash,
                recorded_at="2026-09-07T09:00:00+00:00",
                name="other-portfolio.json",
            ),
            receipt(
                state="processed",
                portfolio="paper-main",
                execution_day="2026-09-08",
                source=source_hash,
                recorded_at="2026-09-07T09:00:00+00:00",
                name="other-session.json",
            ),
            receipt(
                state="processed",
                portfolio="paper-main",
                execution_day="2026-09-07",
                source=other_hash,
                recorded_at="2026-09-08T03:00:00+00:00",
                name="future-terminal.json",
            ),
        ),
        observed_at=observed,
    )

    assert conflicts == ()
    assert effective[("paper-main", date(2026, 9, 7), source_hash)].state == "processed"
    assert ("paper-other", date(2026, 9, 7), source_hash) in effective
    assert ("paper-main", date(2026, 9, 8), source_hash) in effective
    assert ("paper-main", date(2026, 9, 7), other_hash) not in effective


def test_processed_receipt_closes_historical_pending_for_next_session_selection(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    original = recommendation_root / "original.json"
    original.write_bytes(input_paths.recommendation_json.read_bytes())
    receipt_root = tmp_path / "receipts"
    queue_paths = PaperExecutionPaths(
        recommendation_json=tmp_path / "unused-placeholder.json",
        state_db=input_paths.state_db,
        market_db=input_paths.market_db,
        output_root=tmp_path / "waiting-candidate",
        ledger_db=tmp_path / "paper-ledger.sqlite",
        sector_membership_path=input_paths.sector_membership_path,
        sector_membership_file_hash=input_paths.sector_membership_file_hash,
    )
    PaperTradeLedgerRepository(queue_paths.ledger_db)

    waiting = run_paper_execution_daily_from_queue(
        queue_paths,
        recommendation_root=recommendation_root,
        receipt_root=receipt_root,
        now=NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert waiting["operational_receipt"]["queue_state"] == "pending_execution"
    processed = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            **{**queue_paths.__dict__, "output_root": tmp_path / "processed-candidate"}
        ),
        recommendation_root=recommendation_root,
        receipt_root=receipt_root,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert processed["operational_receipt"]["queue_state"] == "processed", processed.get(
        "blockers"
    )

    next_session = recommendation_root / "next-session.json"
    _recommendation(
        next_session,
        created_at="2026-09-07T20:00:00+08:00",
        decision_date="2026-09-07",
    )
    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=datetime(2026, 9, 8, 10, 0, tzinfo=TAIPEI),
        market_db=input_paths.market_db,
        calendar=_Calendar({DECISION_DATE, EXECUTION_DATE, "2026-09-08"}),
        receipt_root=receipt_root,
    )

    assert selected == next_session
    assert reason == "next_official_session_due"


def test_future_processed_receipt_does_not_close_stale_pending_execution(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    queued = recommendation_root / "queued.json"
    queued.write_bytes(input_paths.recommendation_json.read_bytes())
    receipt_root = tmp_path / "receipts"
    queue_paths = PaperExecutionPaths(
        recommendation_json=tmp_path / "unused-placeholder.json",
        state_db=input_paths.state_db,
        market_db=input_paths.market_db,
        output_root=tmp_path / "waiting-candidate",
        ledger_db=tmp_path / "paper-ledger.sqlite",
        sector_membership_path=input_paths.sector_membership_path,
        sector_membership_file_hash=input_paths.sector_membership_file_hash,
    )
    PaperTradeLedgerRepository(queue_paths.ledger_db)
    waiting = run_paper_execution_daily_from_queue(
        queue_paths,
        recommendation_root=recommendation_root,
        receipt_root=receipt_root,
        now=NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    processed = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            **{**queue_paths.__dict__, "output_root": tmp_path / "processed-candidate"}
        ),
        recommendation_root=recommendation_root,
        receipt_root=receipt_root,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert waiting["operational_receipt"]["queue_state"] == "pending_execution"
    assert processed["operational_receipt"]["queue_state"] == "processed", processed.get(
        "blockers"
    )

    terminal_path = Path(str(processed["operational_receipt"]["path"]))
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["recorded_at"] = "2026-09-08T03:00:00+00:00"
    unsigned = dict(terminal)
    unsigned.pop("content_sha256")
    terminal["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    terminal_path.write_text(
        json.dumps(terminal, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=datetime(2026, 9, 8, 10, 0, tzinfo=TAIPEI),
        market_db=input_paths.market_db,
        calendar=_Calendar({DECISION_DATE, EXECUTION_DATE, "2026-09-08"}),
        receipt_root=receipt_root,
    )

    assert selected is None
    assert reason == "pending_execution_session_missed:2026-09-07"


def test_two_processed_hashes_for_one_session_fail_closed(tmp_path: Path) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    first = input_paths.recommendation_json
    second = tmp_path / "second-recommendation.json"
    _recommendation(second, created_at="2026-09-04T21:00:00+08:00")
    receipt_root = tmp_path / "receipts"
    for index, recommendation in enumerate((first, second)):
        ledger_path = tmp_path / f"ledger-{index}.sqlite"
        PaperTradeLedgerRepository(ledger_path)
        result = run_paper_execution_daily(
            PaperExecutionPaths(
                recommendation_json=recommendation,
                state_db=input_paths.state_db,
                market_db=input_paths.market_db,
                output_root=tmp_path / f"candidate-{index}",
                ledger_db=ledger_path,
                sector_membership_path=input_paths.sector_membership_path,
                sector_membership_file_hash=input_paths.sector_membership_file_hash,
            ),
            now=EOD_REPLAY_NOW,
            calendar=_open_calendar(),
            confirm_append=True,
        )
        assert result["status"] == "machine_verified_candidate", result.get("blockers")
        assert result["ledger"]["readback_verified"] is True
        persist_operational_receipt(result, receipt_root, observed=EOD_REPLAY_NOW)

    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipt_root,
    )

    assert selected is None
    assert reason == "processed_execution_source_conflict:paper-main:2026-09-07"


def test_same_day_retry_keeps_first_pending_recommendation_when_newer_source_arrives(
    tmp_path: Path,
) -> None:
    """EOD retry must keep the durable frozen decision for one session."""

    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    original = recommendation_root / "original.json"
    original.write_bytes(input_paths.recommendation_json.read_bytes())
    receipts = tmp_path / "receipts"
    queue_paths = PaperExecutionPaths(
        recommendation_json=tmp_path / "unused-placeholder.json",
        state_db=input_paths.state_db,
        market_db=input_paths.market_db,
        output_root=tmp_path / "waiting-candidate",
        ledger_db=tmp_path / "paper-ledger.sqlite",
        sector_membership_path=input_paths.sector_membership_path,
        sector_membership_file_hash=input_paths.sector_membership_file_hash,
    )
    PaperTradeLedgerRepository(queue_paths.ledger_db)

    waiting = run_paper_execution_daily_from_queue(
        queue_paths,
        recommendation_root=recommendation_root,
        receipt_root=receipts,
        now=NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert waiting["status"] == "waiting_for_execution_source"
    waiting_receipt = waiting["operational_receipt"]
    assert isinstance(waiting_receipt, dict)
    assert waiting_receipt["queue_state"] == "pending_execution"

    newer = recommendation_root / "newer.json"
    _recommendation(newer, created_at="2026-09-04T21:00:00+08:00")
    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipts,
    )
    assert selected == original
    assert reason == "pending_execution_retry"
    assert not any(
        json.loads(path.read_text(encoding="utf-8")).get("queue_state") == "superseded"
        for path in receipts.glob("*.json")
    )

    retry = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            **{
                **queue_paths.__dict__,
                "output_root": tmp_path / "retry-candidate",
            }
        ),
        recommendation_root=recommendation_root,
        receipt_root=receipts,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert retry["status"] == "machine_verified_candidate"
    assert retry["recommendation"]["path"] == str(original)
    assert retry["ledger"]["readback_verified"] is True


@pytest.mark.parametrize("missing_open_only", [False, True])
def test_retryable_missing_execution_source_is_pinned_until_market_row_arrives(
    tmp_path: Path,
    missing_open_only: bool,
) -> None:
    """A 15:05 source miss remains a legal same-day retry at 21:00."""

    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    queued = recommendation_root / "queued.json"
    queued.write_bytes(input_paths.recommendation_json.read_bytes())
    with sqlite3.connect(input_paths.market_db) as connection:
        if missing_open_only:
            connection.execute("UPDATE daily_prices SET 開盤價 = NULL WHERE 日期 = ? AND 證券代號 = ?", ("20260907", "2330"))
        else:
            connection.execute("DELETE FROM daily_prices WHERE 日期 = ? AND 證券代號 = ?", ("20260907", "2330"))
    receipts = tmp_path / "receipts"
    queue_paths = PaperExecutionPaths(
        recommendation_json=tmp_path / "unused-placeholder.json",
        state_db=input_paths.state_db,
        market_db=input_paths.market_db,
        output_root=tmp_path / "failed-candidate",
        ledger_db=tmp_path / "paper-ledger.sqlite",
        sector_membership_path=input_paths.sector_membership_path,
        sector_membership_file_hash=input_paths.sector_membership_file_hash,
    )
    PaperTradeLedgerRepository(queue_paths.ledger_db)
    failed = run_paper_execution_daily_from_queue(
        queue_paths,
        recommendation_root=recommendation_root,
        receipt_root=receipts,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert failed["status"] == "blocked"
    assert failed["retryable"] is True
    failed_receipt = failed["operational_receipt"]
    assert isinstance(failed_receipt, dict)
    assert failed_receipt["queue_state"] == "pending_execution"
    # Simulate a receipt written by the pre-pending producer: keep the original
    # immutable source/candidate payload, but retain its legacy ``failed``
    # queue state and omit the newer retryable marker.
    failed_receipt_path = Path(str(failed_receipt["path"]))
    legacy = json.loads(failed_receipt_path.read_text(encoding="utf-8"))
    legacy["queue_state"] = "failed"
    legacy["result"].pop("retryable", None)
    unsigned_legacy = dict(legacy)
    unsigned_legacy.pop("content_sha256")
    legacy["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(
            unsigned_legacy,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    failed_receipt_path.write_text(
        json.dumps(legacy, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    legacy_bytes_before_retry = failed_receipt_path.read_bytes()

    with sqlite3.connect(input_paths.market_db) as connection:
        if missing_open_only:
            connection.execute("DELETE FROM daily_prices WHERE 日期 = ? AND 證券代號 = ?", ("20260907", "2330"))
        connection.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?)",
            ("20260907", "2330", "測試公司", "10.20", "10.50", 100000),
        )
    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=datetime(2026, 9, 7, 21, 0, tzinfo=TAIPEI),
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipts,
    )
    assert selected == queued
    assert reason == "pending_execution_retry"
    assert failed_receipt_path.read_bytes() == legacy_bytes_before_retry

    retried = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            **{
                **queue_paths.__dict__,
                "output_root": tmp_path / "retried-candidate",
            }
        ),
        recommendation_root=recommendation_root,
        receipt_root=receipts,
        now=datetime(2026, 9, 7, 21, 0, tzinfo=TAIPEI),
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert retried["status"] == "machine_verified_candidate"
    assert retried["operational_receipt"]["queue_state"] == "processed"


def test_legacy_pending_adoption_rejects_mixed_source_and_identity_blockers(
    tmp_path: Path,
) -> None:
    """A missing row cannot mask a clock/identity violation in a receipt."""

    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    queued = recommendation_root / "queued.json"
    queued.write_bytes(input_paths.recommendation_json.read_bytes())
    with sqlite3.connect(input_paths.market_db) as connection:
        connection.execute(
            "DELETE FROM daily_prices WHERE 日期 = ? AND 證券代號 = ?",
            ("20260907", "2330"),
        )
    receipts = tmp_path / "receipts"
    result = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            recommendation_json=tmp_path / "unused-placeholder.json",
            state_db=input_paths.state_db,
            market_db=input_paths.market_db,
            output_root=tmp_path / "candidate",
            ledger_db=tmp_path / "paper-ledger.sqlite",
        ),
        recommendation_root=recommendation_root,
        receipt_root=receipts,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    receipt = result["operational_receipt"]
    assert isinstance(receipt, dict)
    receipt_path = Path(str(receipt["path"]))
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["queue_state"] = "failed"
    payload["result"].pop("retryable", None)
    payload["result"]["blockers"].append("clock identity mismatch")
    unsigned = dict(payload)
    unsigned.pop("content_sha256")
    payload["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    receipt_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipts,
    )
    assert selected is None
    assert reason.startswith("pending_execution_receipt_invalid:")


def test_pending_execution_session_missed_blocks_cross_day_source_switch(
    tmp_path: Path,
) -> None:
    """A late pending session is explicit no-credit, never silently replaced."""

    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    original = recommendation_root / "original.json"
    original.write_bytes(input_paths.recommendation_json.read_bytes())
    receipts = tmp_path / "receipts"
    queue_paths = PaperExecutionPaths(
        recommendation_json=tmp_path / "unused-placeholder.json",
        state_db=input_paths.state_db,
        market_db=input_paths.market_db,
        output_root=tmp_path / "waiting-candidate",
        ledger_db=tmp_path / "paper-ledger.sqlite",
    )
    waiting = run_paper_execution_daily_from_queue(
        queue_paths,
        recommendation_root=recommendation_root,
        receipt_root=receipts,
        now=NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    waiting_receipt = waiting["operational_receipt"]
    assert isinstance(waiting_receipt, dict)
    receipt_path = Path(str(waiting_receipt["path"]))
    receipt_bytes = receipt_path.read_bytes()

    # A later decision maps to the next official session.  The stale 9/7
    # pending source must stop queue selection before that new source can win.
    newer = recommendation_root / "next-session.json"
    _recommendation(
        newer,
        created_at="2026-09-07T20:00:00+08:00",
        decision_date="2026-09-07",
    )
    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=datetime(2026, 9, 8, 10, 0, tzinfo=TAIPEI),
        market_db=input_paths.market_db,
        calendar=_Calendar({DECISION_DATE, EXECUTION_DATE, "2026-09-08"}),
        receipt_root=receipts,
    )
    assert selected is None
    assert reason == "pending_execution_session_missed:2026-09-07"
    assert receipt_path.read_bytes() == receipt_bytes


def test_missing_queue_root_is_blocked_and_persists_failed_receipt(
    tmp_path: Path,
) -> None:
    receipt_root = tmp_path / "receipts"
    result = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            recommendation_json=tmp_path / "unused-placeholder.json",
            state_db=tmp_path / "state.sqlite",
            market_db=tmp_path / "market.sqlite",
            output_root=tmp_path / "candidate",
            ledger_db=tmp_path / "ledger.sqlite",
        ),
        recommendation_root=tmp_path / "missing-recommendation-root",
        receipt_root=receipt_root,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )

    assert result["status"] == "blocked"
    assert result["blockers"] == ["recommendation_root_missing"]
    receipt = result["operational_receipt"]
    assert isinstance(receipt, dict)
    assert receipt["queue_state"] == "failed"
    assert Path(str(receipt["path"])).is_file()
    assert not (tmp_path / "ledger.sqlite").exists()


@pytest.mark.parametrize(
    ("reason", "expected_status", "expected_queue_state"),
    [
        ("no_pending_recommendation", "skipped_no_pending_recommendation", "skipped"),
        (
            "no_pending_recommendation_already_processed",
            "skipped_no_pending_recommendation",
            "skipped",
        ),
        (
            "no_pending_recommendation_due_for_current_session",
            "skipped_no_pending_recommendation",
            "skipped",
        ),
        ("recommendation_root_missing", "blocked", "failed"),
        (
            "no_pending_recommendation_invalid_source:broken.json:invalid identity",
            "blocked",
            "failed",
        ),
        (
            "no_pending_recommendation_invalid_receipt:receipt.json:hash mismatch",
            "blocked",
            "failed",
        ),
        ("queue_terminal_state_conflict:paper-main:2026-09-07:sha256:abc", "blocked", "failed"),
        ("processed_execution_source_conflict:paper-main:2026-09-07", "blocked", "failed"),
        ("pending_execution_source_conflict:2026-09-07", "blocked", "failed"),
        ("pending_execution_source_missing:2026-09-07", "blocked", "failed"),
        ("pending_execution_session_missed:2026-09-07", "blocked", "failed"),
        ("unrecognized_future_queue_reason", "blocked", "failed"),
    ],
    ids=[
        "empty-queue",
        "already-processed",
        "no-source-due-today",
        "missing-root",
        "invalid-source",
        "invalid-receipt",
        "terminal-conflict",
        "processed-conflict",
        "pending-conflict",
        "pinned-source-missing",
        "missed-pending",
        "unknown-reason-fails-closed",
    ],
)
def test_queue_selection_status_is_safe_allowlist_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
    expected_status: str,
    expected_queue_state: str,
) -> None:
    monkeypatch.setattr(
        paper_producer,
        "resolve_pending_recommendation",
        lambda *args, **kwargs: (None, reason),
    )
    receipt_root = tmp_path / "receipts"
    result = run_paper_execution_daily_from_queue(
        PaperExecutionPaths(
            recommendation_json=tmp_path / "unused-placeholder.json",
            state_db=tmp_path / "state.sqlite",
            market_db=tmp_path / "market.sqlite",
            output_root=tmp_path / "candidate",
            ledger_db=tmp_path / "ledger.sqlite",
        ),
        recommendation_root=tmp_path / "recommendation-root",
        receipt_root=receipt_root,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )

    assert result["status"] == expected_status
    assert result["blockers"] == [reason]
    receipt = result["operational_receipt"]
    assert isinstance(receipt, dict)
    assert receipt["queue_state"] == expected_queue_state
    assert not (tmp_path / "ledger.sqlite").exists()


def test_queue_freezes_one_latest_recommendation_per_execution_session(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    older = recommendation_root / "older.json"
    newer = recommendation_root / "newer.json"
    _recommendation(older, created_at="2026-09-04T20:00:00+08:00")
    _recommendation(newer, created_at="2026-09-04T21:00:00+08:00")
    receipts = tmp_path / "receipts"
    queue_paths = PaperExecutionPaths(
        recommendation_json=tmp_path / "unused-placeholder.json",
        state_db=input_paths.state_db,
        market_db=input_paths.market_db,
        output_root=tmp_path / "queue-candidate",
        ledger_db=tmp_path / "paper-ledger.sqlite",
        sector_membership_path=input_paths.sector_membership_path,
        sector_membership_file_hash=input_paths.sector_membership_file_hash,
    )
    PaperTradeLedgerRepository(queue_paths.ledger_db)

    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipts,
    )
    assert selected == newer
    assert reason == "next_official_session_due"
    superseded = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in receipts.glob("*.json")
        if json.loads(path.read_text(encoding="utf-8")).get("queue_state") == "superseded"
    ]
    assert len(superseded) == 1
    assert superseded[0]["result"]["recommendation"]["path"] == str(older)

    result = run_paper_execution_daily_from_queue(
        queue_paths,
        recommendation_root=recommendation_root,
        receipt_root=receipts,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    assert result["status"] == "machine_verified_candidate"
    assert result["recommendation"]["path"] == str(newer)
    selected_again, reason_again = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipts,
    )
    assert selected_again is None
    assert reason_again == "no_pending_recommendation_already_processed"
    states = {
        json.loads(path.read_text(encoding="utf-8"))["queue_state"]
        for path in receipts.glob("*.json")
    }
    assert {"superseded", "processed"}.issubset(states)


def test_rehashed_processed_receipt_with_false_ledger_readback_does_not_skip(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    input_paths = _paths(input_root)
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    queued_recommendation = recommendation_root / "queued.json"
    queued_recommendation.write_bytes(input_paths.recommendation_json.read_bytes())
    receipts = tmp_path / "receipts"
    queue_paths = PaperExecutionPaths(
        recommendation_json=tmp_path / "unused-placeholder.json",
        state_db=input_paths.state_db,
        market_db=input_paths.market_db,
        output_root=tmp_path / "queue-candidate",
        ledger_db=tmp_path / "paper-ledger.sqlite",
        sector_membership_path=input_paths.sector_membership_path,
        sector_membership_file_hash=input_paths.sector_membership_file_hash,
    )
    PaperTradeLedgerRepository(queue_paths.ledger_db)
    result = run_paper_execution_daily_from_queue(
        queue_paths,
        recommendation_root=recommendation_root,
        receipt_root=receipts,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
        confirm_append=True,
    )
    receipt = result["operational_receipt"]
    assert isinstance(receipt, dict)
    receipt_path = Path(str(receipt["path"]))
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["ledger"]["readback_verified"] = False
    payload["result"]["ledger"]["readback_verified"] = False
    unsigned = dict(payload)
    unsigned.pop("content_sha256")
    encoded = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload["content_sha256"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    receipt_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        market_db=input_paths.market_db,
        calendar=_open_calendar(),
        receipt_root=receipts,
    )
    assert selected == queued_recommendation
    assert reason == "next_official_session_due"

    payload["schema_version"] = "paper-execution-receipt-unknown"
    unsigned = dict(payload)
    unsigned.pop("content_sha256")
    payload["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    receipt_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    selected_after_schema_tamper, reason_after_schema_tamper = (
        resolve_pending_recommendation(
            recommendation_root,
            observed=EOD_REPLAY_NOW,
            market_db=input_paths.market_db,
            calendar=_open_calendar(),
            receipt_root=receipts,
        )
    )
    assert selected_after_schema_tamper == queued_recommendation
    assert reason_after_schema_tamper == "next_official_session_due"


def test_invalid_queue_source_is_reported_instead_of_no_pending(
    tmp_path: Path,
) -> None:
    recommendation_root = tmp_path / "recommendation-queue"
    recommendation_root.mkdir()
    (recommendation_root / "broken.json").write_text("{not-json", encoding="utf-8")

    selected, reason = resolve_pending_recommendation(
        recommendation_root,
        observed=EOD_REPLAY_NOW,
        market_db=tmp_path / "unused-market.sqlite",
        calendar=_open_calendar(),
    )

    assert selected is None
    assert reason.startswith("no_pending_recommendation_invalid_source:broken.json:")


def test_recommendation_close_must_match_prior_official_close(tmp_path: Path) -> None:
    paths = _paths(tmp_path, recommendation_close="10.01")
    with sqlite3.connect(paths.market_db) as connection:
        connection.execute(
            "UPDATE daily_prices SET 收盤價 = ? WHERE 日期 = ?",
            ("10.00", "20260904"),
        )
    result = run_paper_execution_daily(
        paths,
        now=EOD_REPLAY_NOW,
        calendar=_open_calendar(),
    )

    assert result["status"] == "blocked"
    assert any("market-reference-date close" in item for item in result["blockers"])


def test_unknown_calendar_keeps_next_session_blocked(tmp_path: Path) -> None:
    result = run_paper_execution_daily(
        _paths(tmp_path),
        now=EOD_REPLAY_NOW,
        calendar=_UnknownCalendar(),
    )

    assert result["status"] == "blocked"
    assert result["next_proven_trading_day"]["status"] == "blocked"
    assert result["next_proven_trading_day"]["date"] is None


def test_calendar_falls_back_to_local_market_indices_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path, with_calendar=True)
    monkeypatch.setattr(
        "data_module.official_trading_calendar.safe_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    result = run_paper_execution_daily(
        paths,
        now=EOD_REPLAY_NOW,
    )

    assert result["status"] == "machine_verified_candidate"
    calendar = result["official_calendar"]
    assert calendar["is_trading_day"] is True
    assert calendar["reason_code"] == "twstock_db_market_indices_evidence"
    assert calendar["fallback_evidence"]["mode"] == "read_only_market_indices_date_evidence"


def test_real_paper_consumer_reads_hash_bound_calendar_cache(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    cache_dir = tmp_path / "calendar-cache"
    cache_path = cache_dir / "twse_holiday_schedule_2026.json"
    raw = json.dumps(
        [
            {
                "Name": "中華民國開國紀念日",
                "Date": "1150101",
                "Description": "依規定放假1日。",
            },
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    captured = EOD_REPLAY_NOW.astimezone(timezone.utc) - timedelta(minutes=1)
    cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=raw,
        requested_at=captured - timedelta(seconds=1),
        captured_at=captured,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
    )
    cache_dir.mkdir()
    write_twse_calendar_cache(cache_path, cache, allowed_root=tmp_path)
    calendar = OfficialTradingCalendar(
        paths.market_db,
        calendar_cache_path=cache_dir,
    )

    with (
        patch("data_module.official_trading_calendar.datetime") as clock,
        patch(
            "data_module.official_trading_calendar.safe_request",
            side_effect=AssertionError("valid cache must be consumed before network"),
        ),
    ):
        clock.now.return_value = EOD_REPLAY_NOW.astimezone(timezone.utc)
        result = run_paper_execution_daily(
            paths,
            now=EOD_REPLAY_NOW,
            calendar=calendar,
        )

    assert result["status"] == "machine_verified_candidate"
    assert result["official_calendar"]["source_evidence"]["mode"] == (
        "hash_bound_official_calendar_cache"
    )
    assert result["official_calendar"]["source_evidence"]["source_hash"] == (
        cache["source"]["response_sha256"]
    )


def test_schedule_snapshots_before_t1_candidate_handoff() -> None:
    text = Path("scripts/scheduled/run_paper_portfolio_daily.cmd").read_text(
        encoding="utf-8"
    ).lower()
    valuation = text.index("run_paper_portfolio_daily_isolated.py")
    execution = text.index("run_paper_execution_daily.py")
    assert valuation < execution
    assert "--confirm-append-paper-ledger" not in text


def test_queue_resolves_sector_using_verified_frozen_identity(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    source = json.loads(paths.recommendation_json.read_text(encoding="utf-8"))
    calls = []

    def resolve_sector(identity):
        calls.append(dict(identity))
        return paths.sector_membership_path, paths.sector_membership_file_hash

    result = run_paper_execution_daily_from_queue(
        paths, recommendation_root=paths.recommendation_json.parent,
        now=EOD_REPLAY_NOW, calendar=_open_calendar(), sector_source_resolver=resolve_sector,
    )
    assert result["status"] == "machine_verified_candidate"
    assert len(calls) == 1
    assert calls[0]["source_file_hash"] == "sha256:" + _sha256(paths.recommendation_json)
    assert datetime.fromisoformat(calls[0]["created_at"]) == datetime.fromisoformat(source["created_at"])


@pytest.mark.parametrize("tamper", [False, True])
@pytest.mark.parametrize("expired_capture", [False, True])
@pytest.mark.parametrize("secondary_fills_error", [False, True])
def test_nonretryable_policy_rejection_closes_only_verified_old_source(tmp_path: Path, tamper: bool, expired_capture: bool, secondary_fills_error: bool) -> None:
    """舊政策拒絕可結束 queue，但任何 candidate 異動仍需阻擋。"""
    paths = _paths(tmp_path)
    result = run_paper_execution_daily(paths, now=EOD_REPLAY_NOW, calendar=_open_calendar())
    candidate_path = Path(str(result["candidate_path"]))
    body = json.loads(candidate_path.read_text(encoding="utf-8"))
    body.pop("content_sha256", None)
    body.update(status="blocked", retryable=False, ledger=None, formal_credit=False,
                blockers=["paper policy sector archive rejected:PITArchiveConsumerError:archive was not persisted before consumer decision",
                          "paper_event_source_capture_missing_durable_manifest"])
    if expired_capture:
        body.update(broker_execution=False, late_replay_policy="no_historical_backfill_pending_session_missed",
                    blockers=["paper policy adapter blocked:ledger row predates declared history:fixture-fill", "paper_event_source_capture_missing_durable_manifest"])
    elif secondary_fills_error:
        body["blockers"] = [body["blockers"][0], "paper_event_source_binding_failed:PaperEventSourceCaptureError:Paper result fills missing"]
    body["content_sha256"] = paper_producer._payload_hash(body)
    candidate_path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    result.update(body, candidate_path=str(candidate_path), candidate_file_hash=paper_producer._file_sha256(candidate_path))
    saved = persist_operational_receipt(result, tmp_path / "receipts", observed=EOD_REPLAY_NOW)
    receipt_path = Path(saved["operational_receipt"]["path"])
    before = receipt_path.read_bytes()
    if tamper:
        candidate_path.write_bytes(candidate_path.read_bytes() + b" ")
    diagnostics = []
    selected, reason = resolve_pending_recommendation(
        paths.recommendation_json.parent, observed=EOD_REPLAY_NOW + timedelta(days=1),
        market_db=paths.market_db, calendar=_open_calendar(), receipt_root=tmp_path / "receipts",
        _resolved_historical_receipt_diagnostics=diagnostics,
    )
    assert selected is None
    if tamper:
        assert reason.startswith("pending_execution_receipt_invalid:")
    else:
        assert not reason.startswith("pending_execution_receipt_invalid:")
        assert diagnostics[0]["status"] == "rejected_nonretryable_policy"
    assert receipt_path.read_bytes() == before
