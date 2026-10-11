from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

def _child_environment() -> dict[str, str]:
    child_env = dict(os.environ)
    child_env.pop("PYTHONPATH", None)
    child_env["PYTHONNOUSERSITE"] = "1"
    return child_env

from app_module.position_health_saved_archive import (
    SavedHealthArchiveError,
    PositionHealthExactScope,
    PositionHealthPositionScope,
    SavedHealthReceiptSelector,
    publish_saved_health_receipt,
)
import app_module.position_health_daily_refresh_service as daily_refresh_module
from app_module.paper_position_identity_provider import PaperPositionIdentityProvider
from app_module.position_health_daily_refresh_service import (
    PositionHealthDailyRefreshService,
)
from app_module.position_health_transition_evaluator import evaluate_baseline_file
from app_module.position_health_transition_read_service import (
    PositionHealthTransitionReadService,
)

DECISION_DATE = date(2026, 10, 8)
SNAPSHOT_ID = "paper-main-20261008"
ROWS_HASH = "sha256:" + "4" * 64
POSITION_ID = "paper:2330:entry-20261001"


def _write_baseline(
    path: Path,
    *,
    thesis: str,
    daily_witness: bool = False,
    source_type: str = "paper_snapshot_read_only",
    omit_shares: bool = False,
) -> None:
    position: dict[str, object] = {
        "position_id": POSITION_ID,
        "entry_lineage_id": POSITION_ID,
        "stock_code": "2330",
        "state": "WATCH",
        "entry_thesis": thesis,
        "entry_lineage_status": "same_snapshot_verified",
    }
    if not omit_shares:
        position["paper_shares"] = 100
    payload = {
        "schema_version": (
            "position-health-daily-refresh.v2"
            if daily_witness
            else "position-health-baseline.v1"
        ),
        "status": "fresh" if daily_witness else "passed",
        "decision_date": DECISION_DATE.isoformat(),
        "as_of_date": DECISION_DATE.isoformat(),
        "source_snapshot_id": SNAPSHOT_ID,
        "source_snapshot_rows_sha256": ROWS_HASH,
        "portfolio_id": "paper-main",
        "positions": [position],
        "research_only": True,
        "writes_positions_db": False,
        "auto_action_allowed": False,
        "broker_execution": False,
        "formal_credit": False,
    }
    if daily_witness:
        # 這是結構驗證 fixture，並不宣稱已由真實 Paper snapshot writer 產生。
        payload.update(
            {
                "producer": "app_module.position_health_daily_refresh_service",
                "source_type": source_type,
                "source_read_mode": "sqlite_uri_mode_ro_and_query_only",
                "source_snapshot_date": DECISION_DATE.isoformat(),
                "source_result_id": "paper-result-20261008",
                "source_decision_boundary": "paper-main-preopen",
                "source_decision_at": "2026-10-08T00:30:00+00:00",
                "source_observed_at": (
                    datetime.now(timezone.utc) - timedelta(minutes=2)
                ).isoformat(),
                # 來源目前沒有自己的 immutable availability clock，不借 refresh 或 archive 時鐘。
                "source_available_at": None,
                "source_path": "fixture-only-paper.sqlite",
                "paper_status_path": "fixture-only-status.json",
                "paper_status_sha256": "sha256:" + "5" * 64,
                "diagnostics": ["fixture_not_a_source_authority"],
                "warnings": [],
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    baseline_raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    path.write_bytes(baseline_raw)
    if daily_witness and not omit_shares:
        baseline_sha256 = "sha256:" + hashlib.sha256(baseline_raw).hexdigest()
        position_rows = [
            {
                "position_id": POSITION_ID,
                "stock_code": "2330",
                "paper_shares": 100,
            }
        ]
        witness = {
            "schema_version": "position-health-daily-baseline-witness.v2",
            "producer": "app_module.position_health_daily_refresh_service",
            "status": "structurally_valid",
            "reason": "",
            "baseline_name": path.name,
            "baseline_sha256": baseline_sha256,
            "portfolio_id": "paper-main",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_date": DECISION_DATE.isoformat(),
            "source_result_id": "paper-result-20261008",
            "source_decision_boundary": "paper-main-preopen",
            "source_decision_at": payload["source_decision_at"],
            "source_snapshot_rows_sha256": ROWS_HASH,
            "source_observed_at": payload["source_observed_at"],
            "source_available_at": None,
            "positions": position_rows,
            "research_only": True,
            "writes_positions_db": False,
            "auto_action_allowed": False,
            "broker_execution": False,
            "formal_credit": False,
            "saved_available_at": datetime.now(timezone.utc).isoformat(
                timespec="microseconds"
            ),
        }
        witness_raw = json.dumps(
            witness, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        witness_dir = path.parent / "saved_baseline_witnesses"
        witness_dir.mkdir(parents=True, exist_ok=True)
        (witness_dir / f"{hashlib.sha256(baseline_raw).hexdigest()}.json").write_bytes(
            witness_raw
        )


def _rewrite_daily_baseline_with_matching_witness(
    path: Path,
    payload: dict[str, object],
) -> None:
    """改動合成 daily baseline 後，重封完整且一致的 source witness。"""

    baseline_raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    path.write_bytes(baseline_raw)
    positions = payload.get("positions")
    if not isinstance(positions, list):
        raise AssertionError("daily baseline fixture positions must be a list")
    witness = {
        "schema_version": "position-health-daily-baseline-witness.v2",
        "producer": "app_module.position_health_daily_refresh_service",
        "status": "structurally_valid",
        "reason": "",
        "baseline_name": path.name,
        "baseline_sha256": "sha256:" + hashlib.sha256(baseline_raw).hexdigest(),
        "portfolio_id": payload["portfolio_id"],
        "snapshot_id": payload["source_snapshot_id"],
        "snapshot_date": payload["source_snapshot_date"],
        "source_result_id": payload["source_result_id"],
        "source_decision_boundary": payload["source_decision_boundary"],
        "source_decision_at": payload["source_decision_at"],
        "source_snapshot_rows_sha256": payload[
            "source_snapshot_rows_sha256"
        ],
        "source_observed_at": payload["source_observed_at"],
        "source_available_at": payload["source_available_at"],
        "positions": [
            {
                "position_id": row["position_id"],
                "stock_code": row["stock_code"],
                "paper_shares": row["paper_shares"],
            }
            for row in positions
            if isinstance(row, dict)
        ],
        "research_only": True,
        "writes_positions_db": False,
        "auto_action_allowed": False,
        "broker_execution": False,
        "formal_credit": False,
        "saved_available_at": datetime.now(timezone.utc).isoformat(
            timespec="microseconds"
        ),
    }
    if len(witness["positions"]) != len(positions):
        raise AssertionError("daily baseline fixture position rows must be objects")
    witness_raw = json.dumps(
        witness, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    witness_dir = path.parent / "saved_baseline_witnesses"
    witness_dir.mkdir(parents=True, exist_ok=True)
    witness_path = witness_dir / f"{hashlib.sha256(baseline_raw).hexdigest()}.json"
    witness_path.write_bytes(witness_raw)


def _evaluate(
    baseline: Path,
    output: Path,
    *,
    decision_date: date = DECISION_DATE,
) -> dict[str, object]:
    return evaluate_baseline_file(
        baseline_path=baseline,
        output_dir=output,
        observed_at=datetime.now(timezone.utc),
        decision_date=decision_date.isoformat(),
    )


def _scope(
    *,
    cutoff: datetime | None = None,
    portfolio_id: str = "paper-main",
    snapshot_id: str = SNAPSHOT_ID,
    position_id: str = POSITION_ID,
    stock_code: str = "2330",
    shares: int = 100,
    decision_date: date = DECISION_DATE,
) -> PositionHealthExactScope:
    return PositionHealthExactScope(
        portfolio_id=portfolio_id,
        snapshot_id=snapshot_id,
        decision_date=decision_date,
        decision_cutoff=cutoff or datetime.now(timezone.utc),
        positions=(
            PositionHealthPositionScope(
                position_id=position_id,
                stock_code=stock_code,
                shares=shares,
            ),
        ),
    )


def _refresh_at_controlled_preopen_clock(
    monkeypatch: pytest.MonkeyPatch,
    refresh: PositionHealthDailyRefreshService,
    *,
    as_of_date: date,
    output_dir: Path,
    source_observed_at: datetime | None = None,
    previous_baseline_path: Path | None = None,
) -> dict[str, object]:
    """只控制隔離測試中的 writer clock，固定決策日盤前因果順序。"""

    taipei = timezone(timedelta(hours=8))
    source_clock = source_observed_at or datetime(
        as_of_date.year,
        as_of_date.month,
        as_of_date.day,
        8,
        45,
        tzinfo=taipei,
    )
    refresh_clock = datetime(
        as_of_date.year,
        as_of_date.month,
        as_of_date.day,
        8,
        40,
        tzinfo=taipei,
    )
    if source_clock.tzinfo is None or source_clock.utcoffset() is None:
        raise AssertionError("controlled source observation clock must be aware")
    if source_clock.astimezone(timezone.utc) < refresh_clock.astimezone(timezone.utc):
        raise AssertionError("source observation must follow refresh start")
    with monkeypatch.context() as scoped:
        scoped.setattr(
            daily_refresh_module,
            "_utc_now",
            lambda: source_clock.astimezone(timezone.utc),
        )
        return refresh.refresh(
            as_of_date=as_of_date,
            output_dir=output_dir,
            previous_baseline_path=previous_baseline_path,
            observed_at=refresh_clock,
        )


def _receipt_payload(output: Path, receipt_id: str) -> tuple[Path, dict[str, object]]:
    path = output / "saved_health" / "receipts" / f"{receipt_id}.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def _tree_bytes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_preopen_status(
    path: Path,
    *,
    state_db: Path,
    ledger_db: Path,
    snapshot_id: str,
    decision_date: str,
    transitions: int = 1,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _create_preopen_paper_source(
    state_db: Path,
    ledger_db: Path,
    *,
    snapshots: tuple[tuple[str, str, int], ...],
) -> None:
    state_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(state_db) as connection:
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
        for snapshot_id, decision_date, quantity in snapshots:
            connection.execute(
                "INSERT INTO paper_portfolio_snapshots VALUES (?, ?, ?, ?, ?, ?)",
                (
                    snapshot_id,
                    "paper-main",
                    decision_date,
                    f"paper-result-{decision_date}",
                    f"{10000 - quantity * 10}.00",
                    "10000.00",
                ),
            )
            connection.execute(
                "INSERT INTO paper_portfolio_positions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    snapshot_id,
                    "2330",
                    quantity,
                    "10.00",
                    str(quantity * 10),
                    1000 if quantity else 0,
                ),
            )
    ledger_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ledger_db) as connection:
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
        connection.execute(
            "INSERT INTO paper_trade_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "paper-trade-ledger.v1",
                "fill-entry-2330",
                "order-entry-2330",
                "paper-main",
                "2026-10-07",
                "2330",
                "buy",
                100,
                100,
                "10.00",
                "10.00",
                "0.00",
                "0.00",
                "0.00",
                100,
                0,
                "filled",
                "event-entry-2330",
                None,
                "paper_daily_execution_delayed_eod_replay_v1",
                1,
                0,
                0,
            ),
        )


def _append_preopen_snapshot(
    state_db: Path,
    *,
    snapshot_id: str,
    decision_date: str,
    quantity: int,
) -> None:
    with sqlite3.connect(state_db) as connection:
        connection.execute(
            "INSERT INTO paper_portfolio_snapshots VALUES (?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                "paper-main",
                decision_date,
                f"paper-result-{decision_date}",
                f"{10000 - quantity * 10}.00",
                "10000.00",
            ),
        )
        connection.execute(
            "INSERT INTO paper_portfolio_positions VALUES (?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                "2330",
                quantity,
                "10.00",
                str(quantity * 10),
                1000 if quantity else 0,
            ),
        )


def test_real_preopen_refresh_archive_latest_independence_and_new_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_db = tmp_path / "paper" / "paper_portfolio.sqlite"
    ledger_db = tmp_path / "paper" / "paper_trade_ledger.sqlite"
    status_path = tmp_path / "paper" / "latest_status.json"
    daily_output = tmp_path / "daily_health"
    health_output = tmp_path / "saved_health"
    first_date = date(2026, 10, 8)
    first_snapshot_id = "paper-main-20261008"
    second_date = date(2026, 10, 9)
    second_snapshot_id = "paper-main-20261009"

    _create_preopen_paper_source(
        state_db,
        ledger_db,
        snapshots=(
            ("paper-main-20261006", "2026-10-06", 0),
            (first_snapshot_id, first_date.isoformat(), 100),
        ),
    )
    _write_preopen_status(
        status_path,
        state_db=state_db,
        ledger_db=ledger_db,
        snapshot_id=first_snapshot_id,
        decision_date=first_date.isoformat(),
        transitions=1,
    )
    identity_provider = PaperPositionIdentityProvider(
        state_db_path=state_db,
        ledger_db_path=ledger_db,
        coverage_status_path=status_path,
    )
    refresh = PositionHealthDailyRefreshService(
        state_db_path=state_db,
        status_path=status_path,
        ledger_db_path=ledger_db,
        coverage_status_path=status_path,
        position_identity_provider=identity_provider,
    )
    state_hash_before = hashlib.sha256(state_db.read_bytes()).hexdigest()
    ledger_hash_before = hashlib.sha256(ledger_db.read_bytes()).hexdigest()
    status_hash_before = hashlib.sha256(status_path.read_bytes()).hexdigest()
    first_refresh = _refresh_at_controlled_preopen_clock(
        monkeypatch,
        refresh,
        as_of_date=first_date,
        output_dir=daily_output,
    )
    assert first_refresh["status"] == "passed", first_refresh
    assert hashlib.sha256(state_db.read_bytes()).hexdigest() == state_hash_before
    assert hashlib.sha256(ledger_db.read_bytes()).hexdigest() == ledger_hash_before
    assert hashlib.sha256(status_path.read_bytes()).hexdigest() == status_hash_before

    first_baseline_path = Path(str(first_refresh["baseline_path"]))
    first_baseline = json.loads(first_baseline_path.read_text(encoding="utf-8"))
    assert first_baseline["portfolio_id"] == "paper-main"
    assert first_baseline["source_snapshot_id"] == first_snapshot_id
    assert first_baseline["source_snapshot_date"] == first_date.isoformat()
    assert first_baseline["source_decision_boundary"] == "paper-main-preopen"
    assert first_baseline["source_available_at"] is None
    assert first_baseline["position_identity_verified_codes"] == ["2330"]
    assert len(first_baseline["positions"]) == 1
    first_position = first_baseline["positions"][0]
    first_position_id = str(first_position["position_id"])
    assert first_position_id
    assert first_position["stock_code"] == "2330"
    assert first_position["paper_shares"] == 100

    baseline_hash = hashlib.sha256(first_baseline_path.read_bytes()).hexdigest()
    baseline_witness_path = (
        first_baseline_path.parent
        / "saved_baseline_witnesses"
        / f"{baseline_hash}.json"
    )
    baseline_witness = json.loads(baseline_witness_path.read_text(encoding="utf-8"))
    assert baseline_witness["status"] == "structurally_valid"
    assert baseline_witness["source_available_at"] is None
    first_evaluation = _evaluate(
        first_baseline_path,
        health_output,
        decision_date=first_date,
    )
    first_selector = SavedHealthReceiptSelector(
        str(first_evaluation["saved_receipt_id"])
    )
    requested_cutoff = datetime.now(timezone.utc)
    first_scope = _scope(
        snapshot_id=first_snapshot_id,
        position_id=first_position_id,
        decision_date=first_date,
        cutoff=requested_cutoff,
    )
    reader = PositionHealthTransitionReadService(health_output)
    first_read = reader.read_saved_exact(first_selector, first_scope)
    assert first_read.source_witness_status == "structurally_valid"
    assert first_read.status == "degraded"
    assert first_read.positions[0].action_suitability == "WATCH"
    assert first_read.source_available_at is None
    assert first_read.health_source_available_at is None
    assert first_read.portfolio_id == "paper-main"
    assert first_read.source_snapshot_id == first_snapshot_id
    assert first_read.source_snapshot_rows_sha256 == first_baseline[
        "source_snapshot_rows_sha256"
    ]
    source_observed = datetime.fromisoformat(str(first_read.source_observed_at))
    baseline_saved = datetime.fromisoformat(
        str(first_read.baseline_saved_available_at)
    )
    health_observed = datetime.fromisoformat(str(first_read.observed_at))
    archive_saved = datetime.fromisoformat(
        str(first_read.saved_receipt_available_at)
    )
    source_decision = datetime.fromisoformat(
        str(first_baseline["source_decision_at"])
    )
    assert (
        source_decision
        <= source_observed
        <= baseline_saved
        <= health_observed
        <= archive_saved
        <= requested_cutoff
    )

    _append_preopen_snapshot(
        state_db,
        snapshot_id=second_snapshot_id,
        decision_date=second_date.isoformat(),
        quantity=100,
    )
    _write_preopen_status(
        status_path,
        state_db=state_db,
        ledger_db=ledger_db,
        snapshot_id=second_snapshot_id,
        decision_date=second_date.isoformat(),
        transitions=0,
    )
    second_state_hash = hashlib.sha256(state_db.read_bytes()).hexdigest()
    second_ledger_hash = hashlib.sha256(ledger_db.read_bytes()).hexdigest()
    second_status_hash = hashlib.sha256(status_path.read_bytes()).hexdigest()
    second_refresh = _refresh_at_controlled_preopen_clock(
        monkeypatch,
        refresh,
        as_of_date=second_date,
        output_dir=daily_output,
        previous_baseline_path=first_baseline_path,
    )
    assert second_refresh["status"] == "passed", second_refresh
    assert hashlib.sha256(state_db.read_bytes()).hexdigest() == second_state_hash
    assert hashlib.sha256(ledger_db.read_bytes()).hexdigest() == second_ledger_hash
    assert hashlib.sha256(status_path.read_bytes()).hexdigest() == second_status_hash
    second_baseline_path = Path(str(second_refresh["baseline_path"]))
    second_baseline = json.loads(second_baseline_path.read_text(encoding="utf-8"))
    assert second_baseline["positions"][0]["position_id"] == first_position_id
    assert second_baseline["positions"][0]["paper_shares"] == 100
    second_evaluation = _evaluate(
        second_baseline_path,
        health_output,
        decision_date=second_date,
    )
    assert second_evaluation["saved_receipt_id"] != first_evaluation[
        "saved_receipt_id"
    ]
    latest = json.loads((health_output / "latest.json").read_text(encoding="utf-8"))
    assert latest["provenance"]["snapshot_id"] == second_snapshot_id
    second_position_id = str(second_baseline["positions"][0]["position_id"])
    second_selector = SavedHealthReceiptSelector(
        str(second_evaluation["saved_receipt_id"])
    )
    second_scope = _scope(
        snapshot_id=second_snapshot_id,
        position_id=second_position_id,
        decision_date=second_date,
    )
    second_read = reader.read_saved_exact(second_selector, second_scope)
    assert second_read.source_witness_status == "structurally_valid"
    assert second_read.source_snapshot_id == second_snapshot_id

    old_again = reader.read_saved_exact(first_selector, first_scope)
    assert old_again.to_dict() == first_read.to_dict()

    child = r"""
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from app_module.position_health_saved_archive import (
    PositionHealthExactScope, PositionHealthPositionScope, SavedHealthReceiptSelector,
)
from app_module.position_health_transition_read_service import PositionHealthTransitionReadService
scope = PositionHealthExactScope(
    portfolio_id="paper-main", snapshot_id=sys.argv[3],
    decision_date=date.fromisoformat(sys.argv[4]),
    decision_cutoff=datetime.now(timezone.utc),
    positions=(PositionHealthPositionScope(sys.argv[5], "2330", int(sys.argv[6])),),
)
model = PositionHealthTransitionReadService(sys.argv[1]).read_saved_exact(
    SavedHealthReceiptSelector(sys.argv[2]), scope,
)
print(json.dumps(model.to_dict(), sort_keys=True))
"""
    child_run = subprocess.run(
        [
            sys.executable,
            "-c",
            child,
            str(health_output),
            first_selector.receipt_id,
            first_snapshot_id,
            first_date.isoformat(),
            first_position_id,
            "100",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=_child_environment(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert child_run.returncode == 0, child_run.stderr
    assert json.loads(child_run.stdout) == first_read.to_dict()


def test_preopen_exact_reader_rejects_late_source_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_db = tmp_path / "paper" / "paper_portfolio.sqlite"
    ledger_db = tmp_path / "paper" / "paper_trade_ledger.sqlite"
    status_path = tmp_path / "paper" / "latest_status.json"
    daily_output = tmp_path / "daily_health"
    health_output = tmp_path / "saved_health"
    decision_date = date(2026, 10, 8)
    snapshot_id = "paper-main-20261008"
    _create_preopen_paper_source(
        state_db,
        ledger_db,
        snapshots=(
            ("paper-main-20261006", "2026-10-06", 0),
            (snapshot_id, decision_date.isoformat(), 100),
        ),
    )
    _write_preopen_status(
        status_path,
        state_db=state_db,
        ledger_db=ledger_db,
        snapshot_id=snapshot_id,
        decision_date=decision_date.isoformat(),
        transitions=1,
    )
    identity_provider = PaperPositionIdentityProvider(
        state_db_path=state_db,
        ledger_db_path=ledger_db,
        coverage_status_path=status_path,
    )
    refresh = PositionHealthDailyRefreshService(
        state_db_path=state_db,
        status_path=status_path,
        ledger_db_path=ledger_db,
        coverage_status_path=status_path,
        position_identity_provider=identity_provider,
    )
    late_observation = datetime(
        2026, 10, 9, 8, 45, tzinfo=timezone(timedelta(hours=8))
    )
    refresh_result = _refresh_at_controlled_preopen_clock(
        monkeypatch,
        refresh,
        as_of_date=decision_date,
        output_dir=daily_output,
        source_observed_at=late_observation,
    )
    assert refresh_result["status"] == "passed", refresh_result
    baseline_path = Path(str(refresh_result["baseline_path"]))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert baseline["source_observed_at"] == late_observation.astimezone(
        timezone.utc
    ).isoformat()

    evaluation = _evaluate(
        baseline_path,
        health_output,
        decision_date=decision_date,
    )
    baseline_positions = baseline["positions"]
    assert len(baseline_positions) == 1
    late_position = baseline_positions[0]
    assert late_position["stock_code"] == "2330"
    assert late_position["paper_shares"] == 100
    # 這個負例只測來源時間因果；使用真 refresh 寫出的 position id，
    # 先排除另一條獨立 scope 身分錯誤路徑。
    late_scope = PositionHealthExactScope(
        portfolio_id="paper-main",
        snapshot_id=snapshot_id,
        decision_date=decision_date,
        decision_cutoff=datetime.now(timezone.utc),
        positions=(
            PositionHealthPositionScope(
                position_id=str(late_position["position_id"]),
                stock_code="2330",
                shares=100,
            ),
        ),
    )
    late_read = PositionHealthTransitionReadService(health_output).read_saved_exact(
        SavedHealthReceiptSelector(str(evaluation["saved_receipt_id"])),
        late_scope,
    )
    assert late_read.status == "blocked"
    assert "saved_health_scope_position_identity_mismatch" not in late_read.blockers
    assert (
        "position_health_source_future_dated:"
        "provenance.position_identity_source.observed_at"
    ) in late_read.blockers


def test_real_evaluator_archive_latest_independence_retry_and_new_process(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "source" / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(baseline, thesis="first saved evaluation")
    first = _evaluate(baseline, output)
    selector = SavedHealthReceiptSelector(str(first["saved_receipt_id"]))
    reader = PositionHealthTransitionReadService(output)

    before_read = _tree_bytes(output)
    first_read = reader.read_saved_exact(selector, _scope())
    after_read = _tree_bytes(output)
    assert before_read == after_read
    assert first_read.status == "degraded"
    assert first_read.source_witness_status == "unqualified"
    assert first_read.receipt_path == first["saved_receipt_path"]
    assert first_read.receipt_sha256 == first["saved_receipt_sha256"]
    assert first_read.saved_receipt_available_at == first["saved_receipt_available_at"]
    assert first_read.source_available_at is None
    assert first_read.health_source_available_at is None
    assert first_read.source_observed_at is None
    assert first_read.baseline_saved_available_at is None
    assert first_read.source_available_at is None
    assert first_read.positions[0].proposed_state == "WATCH"
    assert first_read.positions[0].action_suitability == "WATCH"

    receipt_path, receipt = _receipt_payload(output, selector.receipt_id)
    initial_archive_clock = str(receipt["available_at"])
    retry = publish_saved_health_receipt(
        output_dir=output,
        result_path=first["result_path"],
    )
    assert retry["available_at"] == initial_archive_clock
    assert retry["receipt_sha256"] == first["saved_receipt_sha256"]

    _write_baseline(baseline, thesis="later evaluation changed latest")
    second = _evaluate(baseline, output)
    assert second["saved_receipt_id"] != first["saved_receipt_id"]
    latest = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    assert latest["provenance"]["positions"][0]["entry_thesis"] == "later evaluation changed latest"
    # latest_status 損壞也不影響 exact selector 讀回已封存的舊 result。
    (output / "latest_status.json").write_text("{broken latest pointer", encoding="utf-8")
    old_again = reader.read_saved_exact(selector, _scope())
    assert old_again.to_dict() == first_read.to_dict()
    assert receipt_path.read_text(encoding="utf-8") == json.dumps(
        receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )

    child = r"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from app_module.position_health_saved_archive import (
    PositionHealthExactScope, PositionHealthPositionScope, SavedHealthReceiptSelector,
)
from app_module.position_health_transition_read_service import PositionHealthTransitionReadService
scope = PositionHealthExactScope(
    portfolio_id="paper-main", snapshot_id="paper-main-20261008",
    decision_date=date(2026, 10, 8), decision_cutoff=datetime.now(timezone.utc),
    positions=(PositionHealthPositionScope("paper:2330:entry-20261001", "2330", 100),),
)
model = PositionHealthTransitionReadService(sys.argv[1]).read_saved_exact(
    SavedHealthReceiptSelector(sys.argv[2]), scope,
)
assert model.status == "degraded", model.to_dict()
assert model.positions[0].proposed_state == "WATCH"
print(model.receipt_sha256)
"""
    child_run = subprocess.run(
        [sys.executable, "-c", child, str(output), selector.receipt_id],
        cwd=Path(__file__).resolve().parents[1],
        env=_child_environment(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert child_run.returncode == 0, child_run.stderr
    assert first_read.receipt_sha256 in child_run.stdout


def test_resealed_future_baseline_saved_clock_is_rejected_after_all_hashes_match(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "source" / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(baseline, thesis="future saved source witness", daily_witness=True)
    evaluated = _evaluate(baseline, output)
    receipt_path, receipt = _receipt_payload(
        output, str(evaluated["saved_receipt_id"])
    )
    result_path = output / Path(str(receipt["result_path"]))
    result_raw = result_path.read_bytes()
    assert "sha256:" + hashlib.sha256(result_raw).hexdigest() == receipt["result_sha256"]

    baseline_hash_hex = hashlib.sha256(baseline.read_bytes()).hexdigest()
    sidecar_path = (
        baseline.parent / "saved_baseline_witnesses" / f"{baseline_hash_hex}.json"
    )
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    result_observed = datetime.fromisoformat(str(receipt["observed_at"]))
    future_saved = result_observed + timedelta(days=1)
    sidecar["saved_available_at"] = future_saved.isoformat(timespec="microseconds")
    sidecar_raw = json.dumps(
        sidecar, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    sidecar_path.write_bytes(sidecar_raw)

    old_composite_path = output / Path(str(receipt["source_witness_path"]))
    composite = json.loads(old_composite_path.read_text(encoding="utf-8"))
    composite["baseline_witness"] = sidecar
    composite["baseline_witness_sha256"] = "sha256:" + hashlib.sha256(
        sidecar_raw
    ).hexdigest()
    composite_raw = json.dumps(
        composite, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    composite_sha = "sha256:" + hashlib.sha256(composite_raw).hexdigest()
    composite_path = output / "saved_health" / "sources" / (
        composite_sha.removeprefix("sha256:") + ".json"
    )
    composite_path.write_bytes(composite_raw)

    # 重新封裝 pair hash 與 Health receipt hash；result bytes/hash仍維持原始精確值。
    receipt["source_witness_path"] = composite_path.relative_to(output).as_posix()
    receipt["source_witness_sha256"] = composite_sha
    archive_available = future_saved + timedelta(seconds=1)
    receipt["available_at"] = archive_available.isoformat(timespec="microseconds")
    receipt_path.write_bytes(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    assert "sha256:" + hashlib.sha256(result_path.read_bytes()).hexdigest() == receipt[
        "result_sha256"
    ]

    selector = SavedHealthReceiptSelector(str(evaluated["saved_receipt_id"]))
    scope = _scope(cutoff=archive_available + timedelta(seconds=1))
    reader = PositionHealthTransitionReadService(
        output, now_provider=lambda: archive_available + timedelta(seconds=2)
    )
    model = reader.read_saved_exact(selector, scope)
    assert model.status == "blocked"
    assert "saved_health_baseline_saved_after_evaluation" in model.blockers


def test_empty_account_keeps_archive_clock_separate_from_missing_source_clock(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "empty-baseline.json"
    output = tmp_path / "health"
    payload = {
        "schema_version": "position-health-baseline.v1",
        "status": "passed",
        "decision_date": DECISION_DATE.isoformat(),
        "as_of_date": DECISION_DATE.isoformat(),
        "source_snapshot_id": SNAPSHOT_ID,
        "source_snapshot_rows_sha256": ROWS_HASH,
        "portfolio_id": "paper-main",
        "positions": [],
        "research_only": True,
        "writes_positions_db": False,
        "auto_action_allowed": False,
        "broker_execution": False,
        "formal_credit": False,
    }
    baseline.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    result = _evaluate(baseline, output)
    scope = PositionHealthExactScope(
        portfolio_id="paper-main",
        snapshot_id=SNAPSHOT_ID,
        decision_date=DECISION_DATE,
        decision_cutoff=datetime.now(timezone.utc),
        positions=(),
    )
    model = PositionHealthTransitionReadService(output).read_saved_exact(
        SavedHealthReceiptSelector(str(result["saved_receipt_id"])), scope
    )
    assert model.saved_receipt_available_at is not None
    assert model.source_available_at is None
    assert model.saved_receipt_available_at != model.source_available_at


@pytest.mark.parametrize(
    ("scope_fields", "expected_blocker"),
    (
        ({"portfolio_id": "another-account"}, "saved_health_scope_portfolio_mismatch"),
        ({"snapshot_id": "another-snapshot"}, "saved_health_scope_snapshot_mismatch"),
        ({"stock_code": "2317"}, "saved_health_scope_stock_code_mismatch"),
        ({"position_id": "paper:2330:other-entry"}, "saved_health_scope_position_identity_mismatch"),
    ),
)
def test_wrong_portfolio_snapshot_and_position_scope_fail_closed(
    tmp_path: Path,
    scope_fields: dict[str, str],
    expected_blocker: str,
) -> None:
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(baseline, thesis="legacy source")
    result = _evaluate(baseline, output)
    selector = SavedHealthReceiptSelector(str(result["saved_receipt_id"]))
    model = PositionHealthTransitionReadService(output).read_saved_exact(
        selector, _scope(**scope_fields)
    )
    assert model.status == "blocked"
    assert expected_blocker in model.blockers


def test_exact_position_scope_requires_positive_integer_shares() -> None:
    with pytest.raises(ValueError, match="saved_health_scope_shares_invalid"):
        _scope(shares=0)
    with pytest.raises(ValueError, match="saved_health_scope_shares_invalid"):
        _scope(shares=-1)
    with pytest.raises(ValueError, match="saved_health_scope_shares_invalid"):
        _scope(shares=True)  # bool 雖是 int 子類別，但不能作為持股數量。


def test_structural_witness_checks_integer_shares_and_refuses_wrong_quantity(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(baseline, thesis="structural source fixture", daily_witness=True)
    result = _evaluate(baseline, output)
    selector = SavedHealthReceiptSelector(str(result["saved_receipt_id"]))
    matching = PositionHealthTransitionReadService(output).read_saved_exact(
        selector, _scope()
    )
    assert matching.source_witness_status == "structurally_valid"
    assert matching.status == "degraded"
    assert matching.positions[0].proposed_state == "WATCH"

    mismatched = PositionHealthTransitionReadService(output).read_saved_exact(
        selector, _scope(shares=101)
    )
    assert mismatched.status == "blocked"
    assert "saved_health_source_scope_shares_mismatch" in mismatched.blockers

    receipt_path, receipt = _receipt_payload(output, selector.receipt_id)
    witness_path = output / Path(str(receipt["source_witness_path"]))
    witness_path.write_bytes(witness_path.read_bytes() + b" ")
    corrupt_witness = PositionHealthTransitionReadService(output).read_saved_exact(
        selector, _scope()
    )
    assert corrupt_witness.status == "blocked"
    assert "saved_health_source_witness_hash_mismatch" in corrupt_witness.blockers


@pytest.mark.parametrize("invalid_shares", (True, 0, -1, 100.0))
def test_daily_witness_rejects_nonpositive_or_noninteger_raw_shares(
    tmp_path: Path,
    invalid_shares: object,
) -> None:
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(baseline, thesis="invalid raw share primitive", daily_witness=True)
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    payload["positions"][0]["paper_shares"] = invalid_shares
    baseline.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    if isinstance(invalid_shares, float):
        with pytest.raises(
            SavedHealthArchiveError,
            match="^saved_health_result_floating_json_number_rejected$",
        ):
            _evaluate(baseline, output)
        assert not (output / "saved_health" / "receipts").exists()
        return

    result = _evaluate(baseline, output)
    model = PositionHealthTransitionReadService(output).read_saved_exact(
        SavedHealthReceiptSelector(str(result["saved_receipt_id"])), _scope()
    )
    assert model.status == "blocked"
    assert model.source_witness_status == "unavailable"
    assert "saved_health_source_witness_invalid" in model.blockers


def test_daily_witness_rejects_wrong_producer_and_extra_position_universe(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(baseline, thesis="wrong source producer", daily_witness=True)
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    payload["producer"] = "tests.untrusted_baseline"
    baseline.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    result = _evaluate(baseline, output)
    wrong_producer = PositionHealthTransitionReadService(output).read_saved_exact(
        SavedHealthReceiptSelector(str(result["saved_receipt_id"])), _scope()
    )
    assert wrong_producer.status == "blocked"
    assert "saved_health_source_witness_invalid" in wrong_producer.blockers

    extra_output = tmp_path / "extra-universe-health"
    _write_baseline(baseline, thesis="extra source row", daily_witness=True)
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    extra = dict(payload["positions"][0])
    extra.update(
        {
            "position_id": "paper:2317:entry-20261001",
            "entry_lineage_id": "paper:2317:entry-20261001",
            "stock_code": "2317",
            "paper_shares": 50,
        }
    )
    payload["positions"].append(extra)
    _rewrite_daily_baseline_with_matching_witness(baseline, payload)
    extra_result = _evaluate(baseline, extra_output)
    _, extra_receipt = _receipt_payload(
        extra_output, str(extra_result["saved_receipt_id"])
    )
    assert extra_receipt["source_witness_status"] == "structurally_valid"
    assert extra_receipt["source_witness_reason"] == ""
    extra_source = json.loads(
        (extra_output / Path(str(extra_receipt["source_witness_path"]))).read_text(
            encoding="utf-8"
        )
    )
    assert len(extra_source["baseline_witness"]["positions"]) == 2
    extra_model = PositionHealthTransitionReadService(extra_output).read_saved_exact(
        SavedHealthReceiptSelector(str(extra_result["saved_receipt_id"])), _scope()
    )
    assert extra_model.status == "blocked"
    assert "saved_health_scope_position_identity_mismatch" in extra_model.blockers


def test_missing_source_shares_degrades_and_wrong_source_is_blocked(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(
        baseline,
        thesis="source lacks share evidence",
        daily_witness=True,
        omit_shares=True,
    )
    result = _evaluate(baseline, output)
    selector = SavedHealthReceiptSelector(str(result["saved_receipt_id"]))
    missing_shares = PositionHealthTransitionReadService(output).read_saved_exact(
        selector, _scope()
    )
    assert missing_shares.status == "degraded"
    assert missing_shares.source_witness_status == "unqualified"
    assert missing_shares.positions[0].action_suitability == "WATCH"

    bad_output = tmp_path / "wrong-source-health"
    _write_baseline(
        baseline,
        thesis="wrong source producer",
        daily_witness=True,
        source_type="caller_supplied_json",
    )
    bad_result = _evaluate(baseline, bad_output)
    bad = PositionHealthTransitionReadService(bad_output).read_saved_exact(
        SavedHealthReceiptSelector(str(bad_result["saved_receipt_id"])), _scope()
    )
    assert bad.status == "blocked"
    assert "saved_health_source_witness_invalid" in bad.blockers


def test_share_alias_is_not_accepted_as_formal_paper_shares(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(baseline, thesis="share alias", daily_witness=True)
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    position = payload["positions"][0]
    position["quantity"] = position.pop("paper_shares")
    baseline.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    result = _evaluate(baseline, output)
    model = PositionHealthTransitionReadService(output).read_saved_exact(
        SavedHealthReceiptSelector(str(result["saved_receipt_id"])), _scope()
    )
    assert model.status == "blocked"
    assert "saved_health_source_witness_invalid" in model.blockers


@pytest.mark.parametrize("cutoff_kind", ("naive", "future", "before_saved"))
def test_naive_future_and_early_cutoffs_are_rejected(
    tmp_path: Path,
    cutoff_kind: str,
) -> None:
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(baseline, thesis="cutoff source")
    result = _evaluate(baseline, output)
    selector = SavedHealthReceiptSelector(str(result["saved_receipt_id"]))
    _path, receipt = _receipt_payload(output, selector.receipt_id)
    saved_at = datetime.fromisoformat(str(receipt["available_at"]))
    if cutoff_kind == "naive":
        cutoff = datetime.now()
        expected = "saved_health_decision_cutoff_invalid_or_naive"
    elif cutoff_kind == "future":
        cutoff = datetime.now(timezone.utc) + timedelta(days=1)
        expected = "saved_health_decision_cutoff_future"
    else:
        cutoff = saved_at - timedelta(microseconds=1)
        expected = "saved_health_receipt_after_requested_cutoff"
    model = PositionHealthTransitionReadService(output).read_saved_exact(
        selector, _scope(cutoff=cutoff)
    )
    assert model.status == "blocked"
    assert expected in model.blockers


def test_partial_duplicate_or_resealed_result_artifacts_are_rejected(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(baseline, thesis="artifact integrity")
    result = _evaluate(baseline, output)
    selector = SavedHealthReceiptSelector(str(result["saved_receipt_id"]))
    receipt_path, receipt = _receipt_payload(output, selector.receipt_id)
    result_path = output / Path(str(receipt["result_path"]))
    reader = PositionHealthTransitionReadService(output)

    original_receipt = receipt_path.read_bytes()
    receipt_path.write_bytes(original_receipt[:-7])
    partial = reader.read_saved_exact(selector, _scope())
    assert partial.status == "blocked"
    receipt_path.write_bytes(original_receipt)

    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    result_payload["positions"][0]["why"] = "tampered but valid JSON"
    result_path.write_text(
        json.dumps(result_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    resealed = reader.read_saved_exact(selector, _scope())
    assert resealed.status == "blocked"
    assert "saved_health_result_hash_mismatch" in resealed.blockers


def test_duplicate_receipt_keys_and_hardlinks_are_rejected(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(baseline, thesis="duplicate and hardlink")
    result = _evaluate(baseline, output)
    selector = SavedHealthReceiptSelector(str(result["saved_receipt_id"]))
    receipt_path, _receipt = _receipt_payload(output, selector.receipt_id)
    reader = PositionHealthTransitionReadService(output)

    receipt_path.write_text(
        '{"schema_version":"bad","schema_version":"bad-again"}',
        encoding="utf-8",
    )
    duplicate = reader.read_saved_exact(selector, _scope())
    assert duplicate.status == "blocked"
    assert "saved_health_receipt_duplicate_json_key" in duplicate.blockers

    # 在可建立硬連結的平台，exact reader 必須拒絕任一 archive hardlink。
    receipt_path.unlink()
    _write_baseline(baseline, thesis="hardlink retry")
    result = _evaluate(baseline, output)
    selector = SavedHealthReceiptSelector(str(result["saved_receipt_id"]))
    receipt_path, _receipt = _receipt_payload(output, selector.receipt_id)
    hardlink = receipt_path.with_name("receipt-hardlink.json")
    try:
        os.link(receipt_path, hardlink)
    except (OSError, NotImplementedError):
        pytest.skip("此平台或工作區不允許建立 hardlink")
    linked = PositionHealthTransitionReadService(output).read_saved_exact(
        selector, _scope()
    )
    assert linked.status == "blocked"
    assert "saved_health_hardlink_rejected" in linked.blockers


def test_receipt_and_result_reparse_points_are_rejected(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(baseline, thesis="reparse point")
    result = _evaluate(baseline, output)
    selector = SavedHealthReceiptSelector(str(result["saved_receipt_id"]))
    receipt_path, receipt = _receipt_payload(output, selector.receipt_id)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    reader = PositionHealthTransitionReadService(output)

    receipt_path.unlink()
    try:
        receipt_path.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("此平台或工作區不允許建立 symlink")
    linked_receipt = reader.read_saved_exact(selector, _scope())
    assert linked_receipt.status == "blocked"
    assert "saved_health_reparse_point_rejected" in linked_receipt.blockers
    receipt_path.unlink()

    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    result_path = output / Path(str(receipt["result_path"]))
    result_path.unlink()
    try:
        result_path.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("此平台或工作區不允許建立 symlink")
    linked_result = reader.read_saved_exact(selector, _scope())
    assert linked_result.status == "blocked"
    assert "saved_health_reparse_point_rejected" in linked_result.blockers


def test_unknown_receipt_alias_and_resealed_result_keep_identity_bound(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "health"
    _write_baseline(baseline, thesis="receipt aliases")
    result = _evaluate(baseline, output)
    selector = SavedHealthReceiptSelector(str(result["saved_receipt_id"]))
    receipt_path, receipt = _receipt_payload(output, selector.receipt_id)
    result_path = output / Path(str(receipt["result_path"]))
    reader = PositionHealthTransitionReadService(output)

    aliased = dict(receipt)
    aliased["caller_available_at"] = aliased["available_at"]
    receipt_path.write_text(
        json.dumps(aliased, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    extra_field = reader.read_saved_exact(selector, _scope())
    assert extra_field.status == "blocked"
    assert "saved_health_receipt_fields_invalid" in extra_field.blockers

    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    primitive = dict(receipt)
    primitive["available_at"] = 1760000000.0
    receipt_path.write_text(
        json.dumps(primitive, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    float_field = reader.read_saved_exact(selector, _scope())
    assert float_field.status == "blocked"
    assert "saved_health_receipt_floating_json_number_rejected" in float_field.blockers

    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    decoded = json.loads(result_path.read_text(encoding="utf-8"))
    decoded["positions"][0]["why"] = "re-encoded and caller re-sealed"
    raw = json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result_path.write_bytes(raw)
    receipt["result_sha256"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    reencoded = reader.read_saved_exact(selector, _scope())
    assert reencoded.status == "blocked"
    assert "saved_health_receipt_hash_identity_mismatch" in reencoded.blockers
