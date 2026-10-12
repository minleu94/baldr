from __future__ import annotations

from datetime import date, datetime, timezone
import copy
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

import app_module.position_health_daily_refresh_service as daily_refresh_module

from app_module.paper_position_identity_provider import PaperPositionIdentityProvider
from app_module.position_health_daily_refresh_service import PositionHealthDailyRefreshService
from app_module.position_health_transition_evaluator import evaluate_baseline_file
from app_module.position_health_market_source_producer import PositionHealthMarketSourceProducer


def _make_state(path: Path, snapshots: list[tuple[str, str, dict[str, int]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE paper_portfolio_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                source_result_id TEXT NOT NULL,
                cash TEXT NOT NULL,
                total_value TEXT NOT NULL
            );
            CREATE TABLE paper_portfolio_positions (
                snapshot_id TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                mark_price TEXT NOT NULL,
                market_value TEXT NOT NULL,
                weight_bp INTEGER NOT NULL,
                PRIMARY KEY (snapshot_id, stock_code)
            );
            """
        )
        for snapshot_id, decision_date, quantities in snapshots:
            connection.execute(
                "INSERT INTO paper_portfolio_snapshots VALUES (?, ?, ?, ?, ?, ?)",
                (snapshot_id, "paper-main", decision_date, f"source-{decision_date}", "100000.00", "200000.00"),
            )
            for stock_code, quantity in sorted(quantities.items()):
                connection.execute(
                    "INSERT INTO paper_portfolio_positions VALUES (?, ?, ?, ?, ?, ?)",
                    (snapshot_id, stock_code, quantity, "10.00", str(quantity * 10), 1000 if quantity else 0),
                )


def _make_ledger(path: Path, rows: list[tuple[object, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE paper_trade_ledger (
                schema_version TEXT NOT NULL,
                fill_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                portfolio_id TEXT NOT NULL,
                event_date TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                side TEXT NOT NULL,
                requested_quantity INTEGER NOT NULL,
                filled_quantity INTEGER NOT NULL,
                reference_price TEXT NOT NULL,
                fill_price TEXT,
                commission TEXT NOT NULL,
                tax TEXT NOT NULL,
                slippage_cost TEXT NOT NULL,
                turnover_bp INTEGER,
                execution_gap_bp INTEGER,
                status TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                override_reason TEXT,
                source_type TEXT NOT NULL,
                research_only INTEGER NOT NULL,
                broker_order_allowed INTEGER NOT NULL,
                auto_rebalance_allowed INTEGER NOT NULL
            )
            """
        )
        if rows:
            connection.executemany(
                "INSERT INTO paper_trade_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )


def _ledger_row(
    *,
    token: str,
    event_date: str,
    stock_code: str,
    side: str,
    quantity: int,
    status: str = "filled",
) -> tuple[object, ...]:
    fill_price: str | None = "10.00" if quantity else None
    return (
        "paper-trade-ledger.v1",
        f"fill-{token}",
        f"order-{token}",
        "paper-main",
        event_date,
        stock_code,
        side,
        quantity,
        quantity,
        "10.00",
        fill_price,
        "0.00",
        "0.00",
        "0.00",
        100,
        0 if quantity else None,
        status,
        f"event-{token}",
        None,
        "paper_daily_execution_delayed_eod_replay_v1",
        1,
        0,
        0,
    )


def _write_status(
    path: Path,
    *,
    state_db: Path,
    ledger_db: Path,
    snapshot_id: str,
    decision_date: str,
    transitions: int,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "paper-portfolio-daily-status.v1",
                "isolated_scope_schema_version": "paper-portfolio-daily-isolated-scope.v1",
                "producer": "scripts.scheduled.run_paper_portfolio_daily_isolated",
                "status": "passed",
                "candidate_only": True,
                "formal_credit": False,
                "writes_D_source": False,
                "writes_market_database": False,
                "decision_at": f"{decision_date}T08:30:00+08:00",
                "decision_date": decision_date,
                "snapshot_id": snapshot_id,
                "portfolio_id": "paper-main",
                "state_db": str(state_db.resolve()),
                "paper_ledger_db": str(ledger_db.resolve()),
                "snapshot_appended": True,
                "paper_ledger_transitions_applied": transitions,
                "trading_calendar_validated": True,
                "writes_market_db": False,
                "auto_rebalance_allowed": False,
                "changes_advice": False,
                "broker_execution": False,
                "isolated_scope": {
                    "repository_state_scope": "repository_output_only",
                    "formal_credit": False,
                    "writes_D_source": False,
                    "writes_market_database": False,
                    "broker_execution": False,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_non_trading_status(
    path: Path,
    *,
    state_db: Path,
    ledger_db: Path,
    decision_date: str,
    state_hash: str | None = None,
) -> None:
    resolved_state_hash = state_hash or (
        "sha256:" + hashlib.sha256(state_db.read_bytes()).hexdigest()
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": "paper-portfolio-daily-status.v1",
                "isolated_scope_schema_version": "paper-portfolio-daily-isolated-scope.v1",
                "producer": "scripts.scheduled.run_paper_portfolio_daily_isolated",
                "status": "skipped_non_trading_day",
                "decision_at": f"{decision_date}T08:30:00+08:00",
                "decision_date": decision_date,
                "state_db": str(state_db.resolve()),
                "snapshot_appended": False,
                "trading_calendar_validated": True,
                "trading_calendar_is_open": False,
                "writes_market_db": False,
                "auto_rebalance_allowed": False,
                "changes_advice": False,
                "broker_execution": False,
                "isolated_scope": {
                    "ledger_db": str(ledger_db.resolve()),
                    "state_head": {"target_file_sha256": resolved_state_hash},
                    "formal_credit": False,
                    "writes_D_source": False,
                    "writes_market_database": False,
                    "broker_execution": False,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _provider(
    state_db: Path,
    ledger_db: Path,
    status_path: Path,
) -> PaperPositionIdentityProvider:
    return PaperPositionIdentityProvider(
        state_db_path=state_db,
        ledger_db_path=ledger_db,
        coverage_status_path=status_path,
    )


def test_provider_reuses_hash_verified_snapshot_after_non_trading_skip(
    tmp_path: Path,
) -> None:
    state_db = tmp_path / "paper.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    status_path = tmp_path / "status.json"
    _make_state(
        state_db,
        [
            ("paper-main-20260910", "2026-09-10", {"2330": 0}),
            ("paper-main-20260911", "2026-09-11", {"2330": 1000}),
        ],
    )
    _make_ledger(
        ledger_db,
        [
            _ledger_row(
                token="entry-2330",
                event_date="2026-09-10",
                stock_code="2330",
                side="buy",
                quantity=1000,
            )
        ],
    )
    _write_non_trading_status(
        status_path,
        state_db=state_db,
        ledger_db=ledger_db,
        decision_date="2026-09-12",
    )

    result = _provider(state_db, ledger_db, status_path).resolve(
        snapshot_id="paper-main-20260911",
        snapshot_date="2026-09-11",
        observed_at=datetime(2026, 9, 12, 1, 0, tzinfo=timezone.utc),
    )

    assert result.blockers == ()
    assert result.provenance["coverage"]["status"] == "reused_non_trading_day"
    assert result.identities["2330"]["status"] == "natural_entry_verified"
    assert (
        "paper_position_identity_coverage_reused_non_trading_day"
        in result.warnings
    )


def test_provider_blocks_non_trading_skip_when_state_hash_changed(
    tmp_path: Path,
) -> None:
    state_db = tmp_path / "paper.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    status_path = tmp_path / "status.json"
    _make_state(
        state_db,
        [("paper-main-20260911", "2026-09-11", {"2330": 1000})],
    )
    _make_ledger(ledger_db, [])
    _write_non_trading_status(
        status_path,
        state_db=state_db,
        ledger_db=ledger_db,
        decision_date="2026-09-12",
        state_hash="sha256:" + ("0" * 64),
    )

    result = _provider(state_db, ledger_db, status_path).resolve(
        snapshot_id="paper-main-20260911",
        snapshot_date="2026-09-11",
        observed_at=datetime(2026, 9, 12, 1, 0, tzinfo=timezone.utc),
    )

    assert result.identities == {}
    assert any(
        "paper_position_identity_non_trading_state_hash_mismatch" in blocker
        for blocker in result.blockers
    )


def test_provider_derives_new_natural_entry_and_keeps_old_identity_unknown(
    tmp_path: Path,
) -> None:
    state_db = tmp_path / "paper.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    status_path = tmp_path / "status.json"
    _make_state(
        state_db,
        [
            ("paper-main-20260907", "2026-09-07", {"1418": 1000, "2330": 0}),
            ("paper-main-20260908", "2026-09-08", {"1418": 1000, "2330": 1000}),
        ],
    )
    _make_ledger(
        ledger_db,
        [
            _ledger_row(
                token="entry-2330",
                event_date="2026-09-07",
                stock_code="2330",
                side="buy",
                quantity=1000,
            )
        ],
    )
    _write_status(
        status_path,
        state_db=state_db,
        ledger_db=ledger_db,
        snapshot_id="paper-main-20260908",
        decision_date="2026-09-08",
        transitions=1,
    )
    state_before = state_db.read_bytes()
    ledger_before = ledger_db.read_bytes()

    result = _provider(state_db, ledger_db, status_path).resolve(
        snapshot_id="paper-main-20260908",
        snapshot_date="2026-09-08",
        observed_at=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc),
    )
    assert result.blockers == ()
    assert result.provenance["status"] == "degraded"
    identity = result.identities["2330"]
    assert identity["status"] == "natural_entry_verified"
    assert identity["entry_fill_id"] == "fill-entry-2330"
    assert str(identity["position_id"]).startswith("paper:paper-main:2330:entry-")
    assert "1418" not in result.identities
    assert "paper_position_identity_unproven:1418" in result.warnings
    repeated = _provider(state_db, ledger_db, status_path).resolve(
        snapshot_id="paper-main-20260908",
        snapshot_date="2026-09-08",
        observed_at=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc),
    )
    assert repeated.identities["2330"]["position_id"] == identity["position_id"]

    legacy_status = json.loads(status_path.read_text(encoding="utf-8"))
    legacy_status["schema_version"] = "paper-portfolio-daily-isolated-scope.v1"
    legacy_status.pop("isolated_scope_schema_version")
    status_path.write_text(json.dumps(legacy_status), encoding="utf-8")
    legacy = _provider(state_db, ledger_db, status_path).resolve(
        snapshot_id="paper-main-20260908",
        snapshot_date="2026-09-08",
        observed_at=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc),
    )
    assert legacy.blockers == ()
    assert legacy.identities["2330"]["position_id"] == identity["position_id"]
    assert state_db.read_bytes() == state_before
    assert ledger_db.read_bytes() == ledger_before


def test_provider_reentry_gets_new_identity_instead_of_closed_prior_identity(
    tmp_path: Path,
) -> None:
    state_db = tmp_path / "paper.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    status_path = tmp_path / "status.json"
    _make_state(
        state_db,
        [
            ("paper-main-20260907", "2026-09-07", {"1418": 1000}),
            ("paper-main-20260909", "2026-09-09", {"1418": 1000}),
        ],
    )
    _make_ledger(
        ledger_db,
        [
            _ledger_row(token="exit", event_date="2026-09-07", stock_code="1418", side="sell", quantity=1000),
            _ledger_row(token="reentry", event_date="2026-09-08", stock_code="1418", side="buy", quantity=1000),
        ],
    )
    _write_status(
        status_path,
        state_db=state_db,
        ledger_db=ledger_db,
        snapshot_id="paper-main-20260909",
        decision_date="2026-09-09",
        transitions=2,
    )
    result = _provider(state_db, ledger_db, status_path).resolve(
        snapshot_id="paper-main-20260909",
        snapshot_date="2026-09-09",
        observed_at=datetime(2026, 9, 9, 1, 0, tzinfo=timezone.utc),
        previous_baseline={
            "1418": {
                "stock_code": "1418",
                "position_id": "paper:paper-main:1418:entry-old",
                "entry_lineage_id": "paper:paper-main:1418:entry-old",
                "entry_lineage_status": "ledger_continuous_no_trade",
                "state": "CLOSED",
            }
        },
    )
    assert result.blockers == ()
    identity = result.identities["1418"]
    assert identity["status"] == "natural_entry_verified"
    assert identity["entry_fill_id"] == "fill-reentry"
    assert identity["position_id"] != "paper:paper-main:1418:entry-old"


def test_provider_blocks_quantity_mismatch_before_identity_output(tmp_path: Path) -> None:
    state_db = tmp_path / "paper.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    status_path = tmp_path / "status.json"
    _make_state(
        state_db,
        [
            ("paper-main-20260907", "2026-09-07", {"2330": 0}),
            ("paper-main-20260908", "2026-09-08", {"2330": 999}),
        ],
    )
    _make_ledger(
        ledger_db,
        [_ledger_row(token="entry", event_date="2026-09-07", stock_code="2330", side="buy", quantity=1000)],
    )
    _write_status(
        status_path,
        state_db=state_db,
        ledger_db=ledger_db,
        snapshot_id="paper-main-20260908",
        decision_date="2026-09-08",
        transitions=1,
    )
    result = _provider(state_db, ledger_db, status_path).resolve(
        snapshot_id="paper-main-20260908",
        snapshot_date="2026-09-08",
        observed_at=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc),
    )
    assert result.identities == {}
    assert result.blockers
    assert any("quantity_mismatch:2330" in item for item in result.blockers)


def test_provider_uses_last_entry_after_multi_day_flat_interval(tmp_path: Path) -> None:
    state_db = tmp_path / "paper.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    status_path = tmp_path / "status.json"
    _make_state(
        state_db,
        [
            ("paper-main-20260907", "2026-09-07", {"1418": 0}),
            ("paper-main-20260910", "2026-09-10", {"1418": 1000}),
        ],
    )
    _make_ledger(
        ledger_db,
        [
            _ledger_row(token="entry-a", event_date="2026-09-07", stock_code="1418", side="buy", quantity=1000),
            _ledger_row(token="exit", event_date="2026-09-08", stock_code="1418", side="sell", quantity=1000),
            _ledger_row(token="entry-b", event_date="2026-09-09", stock_code="1418", side="buy", quantity=1000),
        ],
    )
    _write_status(
        status_path,
        state_db=state_db,
        ledger_db=ledger_db,
        snapshot_id="paper-main-20260910",
        decision_date="2026-09-10",
        transitions=3,
    )

    result = _provider(state_db, ledger_db, status_path).resolve(
        snapshot_id="paper-main-20260910",
        snapshot_date="2026-09-10",
        observed_at=datetime(2026, 9, 10, 1, 0, tzinfo=timezone.utc),
    )

    assert result.blockers == ()
    identity = result.identities["1418"]
    assert identity["status"] == "natural_entry_verified"
    assert identity["entry_fill_id"] == "fill-entry-b"
    assert "entry-a" not in str(identity["position_id"])


def test_provider_rejects_same_day_fills_without_sequence_or_time(tmp_path: Path) -> None:
    state_db = tmp_path / "paper.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    status_path = tmp_path / "status.json"
    _make_state(
        state_db,
        [
            ("paper-main-20260907", "2026-09-07", {"1418": 0}),
            ("paper-main-20260908", "2026-09-08", {"1418": 1000}),
        ],
    )
    _make_ledger(
        ledger_db,
        [
            _ledger_row(token="buy-a", event_date="2026-09-07", stock_code="1418", side="buy", quantity=1000),
            _ledger_row(token="sell", event_date="2026-09-07", stock_code="1418", side="sell", quantity=1000),
            _ledger_row(token="buy-b", event_date="2026-09-07", stock_code="1418", side="buy", quantity=1000),
        ],
    )
    _write_status(
        status_path,
        state_db=state_db,
        ledger_db=ledger_db,
        snapshot_id="paper-main-20260908",
        decision_date="2026-09-08",
        transitions=3,
    )

    result = _provider(state_db, ledger_db, status_path).resolve(
        snapshot_id="paper-main-20260908",
        snapshot_date="2026-09-08",
        observed_at=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc),
    )

    assert result.identities == {}
    assert any(
        item.startswith("paper_position_identity_event_order_ambiguous:1418:2026-09-07:")
        for item in result.blockers
    )


def test_daily_refresh_and_evaluator_consume_derived_entry_identity(tmp_path: Path) -> None:
    state_db = tmp_path / "paper.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    status_path = tmp_path / "status.json"
    output = tmp_path / "health"
    _make_state(
        state_db,
        [
            ("paper-main-20260907", "2026-09-07", {"2330": 0}),
            ("paper-main-20260908", "2026-09-08", {"2330": 1000}),
        ],
    )
    _make_ledger(
        ledger_db,
        [_ledger_row(token="entry", event_date="2026-09-07", stock_code="2330", side="buy", quantity=1000)],
    )
    _write_status(
        status_path,
        state_db=state_db,
        ledger_db=ledger_db,
        snapshot_id="paper-main-20260908",
        decision_date="2026-09-08",
        transitions=1,
    )
    previous = output / "baseline_20260908.json"
    previous.parent.mkdir(parents=True)
    previous.write_text(
        json.dumps(
            {
                "decision_date": "2026-09-08",
                "source_snapshot_id": "paper-main-20260907",
                "research_only": True,
                "auto_action_allowed": False,
                "positions": [],
            }
        ),
        encoding="utf-8",
    )
    service = PositionHealthDailyRefreshService(
        state_db_path=state_db,
        status_path=status_path,
        ledger_db_path=ledger_db,
        coverage_status_path=status_path,
        position_identity_provider=_provider(state_db, ledger_db, status_path),
    )
    receipt = service.refresh(
        as_of_date=datetime(2026, 9, 8, tzinfo=timezone.utc).date(),
        output_dir=output,
        previous_baseline_path=previous,
        observed_at=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc),
    )
    assert receipt["status"] == "passed", receipt
    baseline = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    assert baseline["position_identity_verified_codes"] == ["2330"]
    assert baseline["positions"][0]["position_id"].startswith("paper:paper-main:2330:entry-")
    assert baseline["positions"][0]["entry_lineage_status"] == "natural_entry_verified"

    evaluation = evaluate_baseline_file(
        baseline_path=output / "latest.json",
        output_dir=tmp_path / "evaluation",
        observed_at=datetime.now(timezone.utc),
        transition_repository_path=tmp_path / "evaluation" / "proposals.sqlite",
        calendar_cache_path=Path("output/paper_execution_eod_replay/calendar_cache"),
    )
    assert evaluation["status"] == "degraded"
    assert evaluation["positions"][0]["position_id"].startswith("paper:paper-main:2330:entry-")
    assert "thesis_contract_missing" in " ".join(
        evaluation["positions"][0]["reasons"]
    )


def test_daily_refresh_carries_original_nested_entry_to_market_consumer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_clock = datetime(2026, 9, 8, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(daily_refresh_module, "_utc_now", lambda: capture_clock)
    state_db = tmp_path / "paper.sqlite"
    ledger_db = tmp_path / "ledger.sqlite"
    status_path = tmp_path / "status.json"
    _make_state(state_db, [
        ("paper-main-20260907", "2026-09-07", {"2330": 0}),
        ("paper-main-20260908", "2026-09-08", {"2330": 1000}),
    ])
    _make_ledger(ledger_db, [_ledger_row(
        token="entry", event_date="2026-09-07", stock_code="2330", side="buy", quantity=1000,
    )])
    _write_status(status_path, state_db=state_db, ledger_db=ledger_db,
                  snapshot_id="paper-main-20260908", decision_date="2026-09-08", transitions=1)
    service = PositionHealthDailyRefreshService(
        state_db_path=state_db, status_path=status_path, ledger_db_path=ledger_db,
        coverage_status_path=status_path,
        position_identity_provider=_provider(state_db, ledger_db, status_path),
    )
    first = service.refresh(as_of_date=date(2026, 9, 8), output_dir=tmp_path / "first",
                            observed_at=datetime(2026, 9, 8, 1, tzinfo=timezone.utc))
    assert first["status"] == "passed", first
    first_path = Path(first["baseline_path"])
    first_baseline = json.loads(first_path.read_text(encoding="utf-8"))
    original = first_baseline["positions"][0]["position_identity_source"]
    assert "entry_date" not in first_baseline["positions"][0]

    with sqlite3.connect(state_db) as connection:
        connection.execute("INSERT INTO paper_portfolio_snapshots VALUES (?, ?, ?, ?, ?, ?)",
                           ("paper-main-20260909", "paper-main", "2026-09-09", "source-2026-09-09",
                            "100000.00", "200000.00"))
        connection.execute("INSERT INTO paper_portfolio_positions VALUES (?, ?, ?, ?, ?, ?)",
                           ("paper-main-20260909", "2330", 1000, "10.00", "10000", 1000))
    _write_status(status_path, state_db=state_db, ledger_db=ledger_db,
                  snapshot_id="paper-main-20260909", decision_date="2026-09-09", transitions=0)
    state_before, ledger_before = state_db.read_bytes(), ledger_db.read_bytes()
    capture_clock = datetime(2026, 9, 9, 1, tzinfo=timezone.utc)
    second = service.refresh(as_of_date=date(2026, 9, 9), output_dir=tmp_path / "second",
                             previous_baseline_path=first_path,
                             observed_at=datetime(2026, 9, 9, 1, tzinfo=timezone.utc))
    second_path = Path(second["baseline_path"])
    # 同 snapshot 再讀保存 baseline，不能在第二次 carry 再遺失 entry 時鐘。
    capture_clock = datetime(2026, 9, 9, 2, tzinfo=timezone.utc)
    repeated = service.refresh(as_of_date=date(2026, 9, 9), output_dir=tmp_path / "repeated",
                               previous_baseline_path=second_path,
                               observed_at=datetime(2026, 9, 9, 2, tzinfo=timezone.utc))
    baseline_path = Path(repeated["baseline_path"])
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    carried = baseline["positions"][0]["position_identity_source"]
    assert carried["status"] == "carried_verified"
    assert baseline["position_identity_verified_codes"] == ["2330"]
    for field in ("position_id", "entry_lineage_id", "entry_date", "entry_fill_id",
                  "entry_source_event_id", "entry_evidence_hash", "available_at",
                  "coverage_status_file_sha256"):
        assert carried[field] == original[field]

    market_db = tmp_path / "market.sqlite"
    with sqlite3.connect(market_db) as connection:
        connection.execute('CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 收盤價 TEXT, '
                           '開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, 成交股數 INTEGER)')
        connection.execute("INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?)",
                           ("20260909", "2330", "10", "10", "11", "9", 100000))
        connection.execute('CREATE TABLE technical_indicators (日期 TEXT, 證券代號 TEXT, '
                           'RSI TEXT, MACD TEXT, MACD_signal TEXT, MACD_hist TEXT, '
                           'MA5 TEXT, MA10 TEXT, MA20 TEXT, MA60 TEXT, ATR TEXT, ADX TEXT)')
        connection.execute("INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           ("20260909", "2330", "50", "1", "1", "0", "10", "10", "10", "10", "1", "20"))
    quick, freshness = tmp_path / "quick.json", tmp_path / "freshness.json"
    quick.write_text(json.dumps({"status": "passed", "writes_market_data_db": True,
                                 "end_date": "2026-09-09", "completed_at": "2026-09-09T12:30:00Z"}), encoding="utf-8")
    freshness.write_text(json.dumps({"status": "passed", "checked_at": "2026-09-09T13:00:00Z",
                                     "checks": {"daily_prices_latest_date_key": "20260909",
                                                "technical_indicators_latest_date": "20260909"}}), encoding="utf-8")
    observed = datetime(2026, 9, 9, 13, 5, tzinfo=timezone.utc)
    result = PositionHealthMarketSourceProducer(
        market_db_path=market_db, quick_status_path=quick, freshness_status_path=freshness,
        now_provider=lambda: observed,
    ).produce(baseline_path=baseline_path, output_dir=tmp_path / "sources",
              decision_date="2026-09-09", decision_at=observed, observed_at=observed)
    assert result["status"] == "passed"
    assert result["condition_row_count"] == 1
    assert state_db.read_bytes() == state_before
    assert ledger_db.read_bytes() == ledger_before


@pytest.mark.parametrize("field,value", [
    ("entry_date", None), ("entry_date", "2026-09-09"),
    ("available_at", None), ("available_at", "2026-09-09T02:00:00Z"),
    ("available_at", "2026-09-08T08:30:00"),
    ("stock_code", "1418"), ("position_id", "other-entry"),
    ("entry_lineage_id", "other-lineage"), ("status", "unproven"),
    ("current_snapshot_date", "2099-01-01"),
    ("entry_fill_id", None), ("entry_source_event_id", None), ("entry_evidence_hash", None),
])
def test_provider_does_not_promote_incomplete_or_future_prior_entry(
    tmp_path: Path, field: str, value: object,
) -> None:
    state_db, ledger_db, status_path = (tmp_path / name for name in ("paper.sqlite", "ledger.sqlite", "status.json"))
    _make_state(state_db, [
        ("paper-main-20260908", "2026-09-08", {"2330": 1000}),
        ("paper-main-20260909", "2026-09-09", {"2330": 1000}),
    ])
    _make_ledger(ledger_db, [])
    _write_status(status_path, state_db=state_db, ledger_db=ledger_db,
                  snapshot_id="paper-main-20260909", decision_date="2026-09-09", transitions=0)
    prior = {
        "stock_code": "2330", "state": "WATCH", "position_id": "entry-2330",
        "entry_lineage_id": "entry-2330", "entry_lineage_status": "natural_entry_verified",
        "position_identity_source": {
            "stock_code": "2330", "position_id": "entry-2330", "entry_lineage_id": "entry-2330",
            "status": "natural_entry_verified", "entry_date": "2026-09-07",
            "entry_fill_id": "fill-entry", "entry_source_event_id": "event-entry",
            "entry_evidence_hash": "sha256:" + "a" * 64, "available_at": "2026-09-08T00:30:00Z",
            "current_snapshot_id": "paper-main-20260908", "current_snapshot_date": "2026-09-08",
        },
    }
    prior["position_identity_source"][field] = value
    original = copy.deepcopy(prior)
    result = _provider(state_db, ledger_db, status_path).resolve(
        snapshot_id="paper-main-20260909", snapshot_date="2026-09-09",
        observed_at=datetime(2026, 9, 9, 1, tzinfo=timezone.utc), previous_baseline={"2330": prior},
    )
    assert result.identities == {}
    assert result.provenance["status"] == "degraded"
    assert result.provenance["unknown_codes"] == ["2330"]
    assert "paper_position_identity_unproven:2330" in result.warnings
    assert prior == original
