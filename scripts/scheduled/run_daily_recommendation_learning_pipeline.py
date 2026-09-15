"""Run the normal daily recommendation-to-learning shadow pipeline.

This is the 05:45 entrypoint.  It keeps the official event refresh,
technical/source custody, recommendation snapshot, and calibration learning
on one durable output root.  Optional MoneyDJ broker pages remain outside the
core lane; every other dependency is reported explicitly and the learning
step never receives caller-supplied symbols unless the operator asks for it.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
TAIPEI = ZoneInfo("Asia/Taipei")
TASK_NAME = "baldr-recommendation-calibration-learning-daily"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--source-db", type=Path)
    parser.add_argument("--max-stocks", type=int, default=200)
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--history-start-date", default="2014-01-01")
    parser.add_argument("--max-decision-dates", type=int, default=100)
    parser.add_argument("--fixed-round-trip-cost-bp", type=int, default=50)
    parser.add_argument(
        "--cost-scenario",
        choices=("legacy_fixed_bp", "banktaiwan_estimated_research"),
        default="legacy_fixed_bp",
        help="成本 contract；預設維持既有 fixed 50bp，臺銀情境僅供 research/shadow。",
    )
    parser.add_argument("--cost-policy-estimate-date", default="2026-01-01")
    parser.add_argument("--research-order-amount-twd", default=None)
    parser.add_argument("--research-order-quantity-shares", type=int, default=None)
    parser.add_argument(
        "--research-order-lot-type",
        choices=("full_lot", "odd_lot"),
        default="full_lot",
    )
    parser.add_argument(
        "--research-instrument-type",
        choices=("ordinary_stock", "equity_etf"),
        default="ordinary_stock",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="optional explicit cohort for a controlled trial; omitted for the normal snapshot cohort",
    )
    parser.add_argument("--official-timeout-seconds", type=int, default=30)
    parser.add_argument("--official-max-attempts", type=int, default=4)
    parser.add_argument("--official-retry-delay-seconds", type=int, default=2)
    parser.add_argument("--official-request-delay-seconds", type=int, default=1)
    parser.add_argument("--window-weekdays", type=int, default=10)
    parser.add_argument("--daily-delay-seconds", type=float, default=0.5)
    parser.add_argument("--tpex-delay-seconds", type=float, default=0.5)
    parser.add_argument("--broker-delay-seconds", type=float, default=0.5)
    parser.add_argument(
        "--child-timeout-seconds",
        type=float,
        default=3600.0,
        help="hard timeout for each subprocess; a timeout leaves durable receipts untouched",
    )
    parser.add_argument(
        "--pipeline-timeout-seconds",
        type=float,
        default=7200.0,
        help="hard wall-clock budget for all subprocesses in this daily run",
    )
    parser.add_argument(
        "--skip-technical-refresh",
        action="store_true",
        help="only for an already verified same-day technical receipt; status records the skip",
    )
    return parser


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _status_path(output_root: Path, name: str) -> Path:
    if name == "recommendation_learning":
        return output_root / "recommendation_learning" / "latest_status.json"
    return output_root / "scheduled" / name / "latest_status.json"


def _tail(text: str, limit: int = 6000) -> str:
    return text[-limit:] if len(text) > limit else text


def _run_child(
    *,
    name: str,
    script: str,
    arguments: Sequence[str],
    environment: Mapping[str, str],
    log_handle: Any,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    command = [sys.executable, str(ROOT / script), *arguments]
    status_file = _status_path(Path(environment["RECOMMENDATION_LEARNING_OUTPUT_ROOT"]), name)
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            env=dict(environment),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        combined = (str(stdout) + str(stderr)).strip()
        log_handle.write(
            f"\n===== {name} TIMED OUT =====\n"
            f"timeout_seconds={timeout_seconds}\n{combined}\n"
        )
        return {
            "name": name,
            "script": script,
            "command": command,
            "returncode": None,
            "status": "timed_out",
            "status_path": str(status_file),
            "child_status": None,
            "child_warnings": [],
            "child_blockers": [f"subprocess_timeout:{name}"],
            "stdout_stderr_tail": _tail(combined),
            "timeout_seconds": timeout_seconds,
            "recoverable": True,
        }
    combined = ((completed.stdout or "") + (completed.stderr or "")).strip()
    log_handle.write(f"\n===== {name} =====\n{combined}\n")
    child_status = _read_json(status_file)
    child_status_name = (
        str(child_status.get("status") or "")
        if isinstance(child_status, Mapping)
        else ""
    )
    failed_child_statuses = {
        "failed",
        "blocked",
        "failed_training",
        "failed_dependency",
        "skipped_insufficient_evidence",
        "skipped_no_data",
        "error",
        "timed_out",
    }
    warning_child_statuses = {"passed_with_warnings", "warning", "degraded"}
    nested_blockers: list[str] = []
    nested_recoverable = False
    if name == "recommendation_learning" and isinstance(child_status, Mapping):
        live_capture = child_status.get("live_capture")
        if isinstance(live_capture, Mapping):
            capture_status = str(live_capture.get("status") or "").strip().lower()
            if capture_status in {"blocked", "failed"}:
                capture_reason = str(
                    live_capture.get("reason") or "capture_dependency_unavailable"
                ).strip()
                nested_blockers.append(
                    f"live_capture_{capture_status}:{capture_reason}"
                )
                nested_recoverable = (
                    capture_status == "blocked"
                    or child_status.get("cli_recoverable") is True
                )
    child_blockers = list(child_status.get("blockers") or []) if isinstance(child_status, Mapping) else []
    child_blockers.extend(nested_blockers)
    if nested_blockers or completed.returncode != 0 or child_status_name in failed_child_statuses:
        step_status = "failed"
    elif child_status_name in warning_child_statuses:
        step_status = child_status_name
    elif child_status_name in {"passed", "published", "completed", "ready"}:
        step_status = "passed"
    elif not child_status_name:
        step_status = "failed"
    else:
        # Fail closed for a newly introduced child status.  The pipeline must
        # not report success while silently ignoring a child failure mode.
        step_status = "failed"
    return {
        "name": name,
        "script": script,
        "command": command,
        "returncode": completed.returncode,
        "status": step_status,
        "status_path": str(status_file),
        "child_status": child_status,
        "child_warnings": list(child_status.get("warnings") or [])
        if isinstance(child_status, Mapping)
        else [],
        "child_blockers": list(dict.fromkeys(str(item) for item in child_blockers)),
        "stdout_stderr_tail": _tail(combined),
        "timeout_seconds": timeout_seconds,
        "recoverable": nested_recoverable,
    }


def _base_payload(*, output_root: Path, status_path: Path, decision_date: str) -> dict[str, Any]:
    return {
        "schema_version": "daily-recommendation-learning-pipeline.v1",
        "task": TASK_NAME,
        "status": "running",
        "decision_date": decision_date,
        "decision_timezone": "Asia/Taipei",
        "output_root": str(output_root),
        "status_path": str(status_path),
        "steps": {},
        "warnings": [],
        "blockers": [],
        "snapshot_warnings": [],
        "venue_date_source_gaps": [],
        "requested_symbols": [],
        "eligible_symbols": [],
        "missing_symbols": [],
        "degraded_symbols": [],
        "excluded_symbols": [],
        "moneydj_broker_branch": {
            "status": "skipped",
            "policy": "optional_source_outside_recommendation_learning_core_lane",
        },
        "formal_order_allowed": False,
        "shadow_only": True,
        "timeout_policy": {
            "child_timeout_is_recoverable": True,
            "durable_receipts_are_not_deleted_on_timeout": True,
        },
    }


def _snapshot_coverage(snapshot_status: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(snapshot_status, Mapping):
        return None
    value = snapshot_status.get("snapshot_cohort")
    return dict(value) if isinstance(value, Mapping) else None


def _apply_coverage(payload: dict[str, Any], coverage: Mapping[str, Any] | None) -> None:
    if not isinstance(coverage, Mapping):
        return
    payload["snapshot_cohort"] = dict(coverage)
    payload["requested_symbols"] = list(coverage.get("requested_symbols") or [])
    payload["eligible_symbols"] = list(coverage.get("eligible_symbols") or [])
    payload["missing_symbols"] = list(coverage.get("missing_symbols") or [])
    payload["degraded_symbols"] = list(coverage.get("degraded_symbols") or [])
    payload["excluded_symbols"] = list(coverage.get("excluded_symbols") or [])


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.child_timeout_seconds <= 0 or args.pipeline_timeout_seconds <= 0:
        raise ValueError("timeout budgets must be positive")
    data_root = args.data_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    source_db = (args.source_db or data_root / "sqlite" / "twstock.db").expanduser().resolve()
    decision_date = datetime.now(TAIPEI).date().isoformat()
    run_root = output_root / "scheduled" / "recommendation_calibration_learning"
    status_path = run_root / "latest_status.json"
    log_path = run_root / f"{decision_date.replace('-', '')}_pipeline.log"
    run_root.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    environment.update(
        {
            "OUTPUT_ROOT": str(output_root),
            "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(output_root),
            "DB_PATH": str(source_db),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    payload = _base_payload(
        output_root=output_root,
        status_path=status_path,
        decision_date=decision_date,
    )
    _write_json(status_path, payload)

    pipeline_deadline = time.monotonic() + args.pipeline_timeout_seconds

    def run_child_bounded(**kwargs: Any) -> dict[str, Any]:
        remaining = pipeline_deadline - time.monotonic()
        if remaining <= 0:
            name = str(kwargs["name"])
            script = str(kwargs["script"])
            status_file = _status_path(output_root, name)
            log_handle = kwargs["log_handle"]
            log_handle.write(
                f"\n===== {name} TIMED OUT =====\n"
                "pipeline_timeout_seconds_exhausted\n"
            )
            return {
                "name": name,
                "script": script,
                "command": [sys.executable, str(ROOT / script), *kwargs["arguments"]],
                "returncode": None,
                "status": "timed_out",
                "status_path": str(status_file),
                "child_status": None,
                "child_warnings": [],
                "child_blockers": [f"pipeline_timeout:{name}"],
                "stdout_stderr_tail": "",
                "timeout_seconds": 0.0,
                "recoverable": True,
            }
        timeout_seconds = min(args.child_timeout_seconds, remaining)
        return _run_child(timeout_seconds=timeout_seconds, **kwargs)

    try:
        with log_path.open("a", encoding="utf-8") as log_handle:
            if args.skip_technical_refresh:
                technical_step = {
                    "name": "data_update_quick",
                    "status": "skipped",
                    "reason": "caller_declared_existing_same_day_technical_receipt",
                    "status_path": str(_status_path(output_root, "data_update_quick")),
                }
            else:
                technical_step = run_child_bounded(
                    name="data_update_quick",
                    script="scripts/scheduled/run_daily_data_update_quick.py",
                    arguments=[
                        "--data-root", str(data_root),
                        "--output-root", str(output_root),
                        "--start-date", decision_date,
                        "--end-date", decision_date,
                        "--window-weekdays", str(args.window_weekdays),
                        "--daily-delay-seconds", str(args.daily_delay_seconds),
                        "--tpex-delay-seconds", str(args.tpex_delay_seconds),
                        "--broker-delay-seconds", str(args.broker_delay_seconds),
                        "--skip-broker-branch",
                    ],
                    environment=environment,
                    log_handle=log_handle,
                )
            payload["steps"]["data_update_quick"] = technical_step
            if technical_step.get("status") in {"failed", "timed_out"}:
                payload["warnings"].append("technical_source_refresh_failed_or_partial")
            if technical_step.get("status") == "timed_out":
                payload["blockers"].append("technical_source_refresh_timed_out")
            technical_warnings = list(technical_step.get("child_warnings") or [])
            payload["warnings"].extend(technical_warnings)
            payload["venue_date_source_gaps"] = [
                warning
                for warning in technical_warnings
                if "TPEX" in str(warning).upper() or "TPEx" in str(warning)
            ]

            official_step = run_child_bounded(
                name="official_market_events",
                script="scripts/scheduled/run_official_market_event_backfill.py",
                arguments=[
                    "--output-root", str(output_root),
                    "--as-of-date", decision_date,
                    "--publication-scope", "prospective_bounded",
                    "--start-year", decision_date[:4],
                    "--end-year", decision_date[:4],
                    "--timeout-seconds", str(args.official_timeout_seconds),
                    "--max-attempts", str(args.official_max_attempts),
                    "--retry-delay-seconds", str(args.official_retry_delay_seconds),
                    "--request-delay-seconds", str(args.official_request_delay_seconds),
                ],
                environment=environment,
                log_handle=log_handle,
            )
            payload["steps"]["official_market_events"] = official_step
            official_status = _read_json(_status_path(output_root, "official_market_events"))
            last_good = official_status.get("last_known_good_publication") if isinstance(official_status, Mapping) else None
            if official_step.get("status") == "timed_out":
                payload["blockers"].append("official_refresh_timed_out")
            elif official_step.get("status") == "failed":
                if isinstance(last_good, Mapping) and last_good.get("validation_status") == "verified":
                    payload["warnings"].append("official_refresh_failed_verified_last_good_preserved")
                else:
                    payload["blockers"].append("official_refresh_failed_without_verified_last_good")

            snapshot_step = run_child_bounded(
                name="recommendation_snapshot",
                script="scripts/scheduled/run_scheduled_recommendation_snapshot.py",
                arguments=[
                    "--data-root", str(data_root),
                    "--output-root", str(output_root),
                    "--max-stocks", str(args.max_stocks),
                    "--top-n", str(args.top_n),
                ],
                environment=environment,
                log_handle=log_handle,
            )
            payload["steps"]["recommendation_snapshot"] = snapshot_step
            snapshot_status = _read_json(_status_path(output_root, "recommendation_snapshot"))
            coverage = _snapshot_coverage(snapshot_status)
            _apply_coverage(payload, coverage)
            snapshot_warnings = list(snapshot_status.get("warnings") or []) if isinstance(snapshot_status, Mapping) else []
            payload["snapshot_warnings"] = snapshot_warnings
            payload["warnings"].extend(snapshot_warnings)
            if coverage and coverage.get("missing_symbols"):
                payload["warnings"].append("recommendation_snapshot_missing_symbols")
            acceptable_snapshot_statuses = {"passed", "passed_with_warnings", "warning", "degraded"}
            if (
                snapshot_step.get("status") not in acceptable_snapshot_statuses
                or not isinstance(snapshot_status, Mapping)
                or snapshot_status.get("status") not in acceptable_snapshot_statuses
            ):
                payload["blockers"].append("same_day_recommendation_snapshot_unavailable")
                payload["steps"]["recommendation_learning"] = {
                    "status": "blocked",
                    "reason": "same_day_recommendation_snapshot_unavailable",
                }
            else:
                learning_arguments = [
                    "--data-root", str(data_root),
                    "--output-root", str(output_root),
                    "--source-db", str(source_db),
                    "--history-start-date", str(args.history_start_date),
                    "--fixed-round-trip-cost-bp", str(args.fixed_round_trip_cost_bp),
                    "--max-decision-dates", str(args.max_decision_dates),
                    "--replay-selection-policy", "latest_eligible_dates",
                    "--decision-date", decision_date,
                    "--training-as-of", decision_date,
                ]
                if args.cost_scenario == "banktaiwan_estimated_research":
                    learning_arguments.extend(
                        [
                            "--cost-scenario", args.cost_scenario,
                            "--cost-policy-estimate-date", str(args.cost_policy_estimate_date),
                            "--research-order-lot-type", str(args.research_order_lot_type),
                            "--research-instrument-type", str(args.research_instrument_type),
                        ]
                    )
                    if args.research_order_amount_twd is not None:
                        learning_arguments.extend(
                            ["--research-order-amount-twd", str(args.research_order_amount_twd)]
                        )
                    if args.research_order_quantity_shares is not None:
                        learning_arguments.extend(
                            [
                                "--research-order-quantity-shares",
                                str(args.research_order_quantity_shares),
                            ]
                        )
                if args.symbols:
                    learning_arguments.extend(["--symbols", str(args.symbols)])
                learning_step = run_child_bounded(
                    name="recommendation_learning",
                    script="scripts/scheduled/run_daily_recommendation_learning.py",
                    arguments=learning_arguments,
                    environment=environment,
                    log_handle=log_handle,
                )
                payload["steps"]["recommendation_learning"] = learning_step
                payload["warnings"].extend(list(learning_step.get("child_warnings") or []))
                payload["blockers"].extend(list(learning_step.get("child_blockers") or []))
                learning_status = _read_json(output_root / "recommendation_learning" / "latest_status.json")
                if isinstance(learning_status, Mapping):
                    payload["learning_latest_status"] = {
                        "status": learning_status.get("status"),
                        "decision": learning_status.get("decision"),
                        "decision_reason": learning_status.get("decision_reason"),
                        "symbol_source": learning_status.get("symbol_source"),
                        "symbols": learning_status.get("symbols"),
                        "symbol_coverage": learning_status.get("symbol_coverage"),
                        "run_scope": learning_status.get("run_scope"),
                        "live_capture": learning_status.get("live_capture"),
                    }
                if learning_step.get("status") not in {"passed", "passed_with_warnings"}:
                    payload["blockers"].append("recommendation_learning_failed")

    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        payload["blockers"].append(f"pipeline_exception:{type(exc).__name__}")
        payload["error"] = str(exc)

    payload["warnings"] = list(dict.fromkeys(str(item) for item in payload["warnings"]))
    payload["blockers"] = list(dict.fromkeys(str(item) for item in payload["blockers"]))
    learning_step = payload["steps"].get("recommendation_learning")
    if not payload["blockers"] and isinstance(learning_step, Mapping) and learning_step.get("status") in {"passed", "passed_with_warnings"}:
        payload["status"] = "passed_with_warnings" if payload["warnings"] else "passed"
    else:
        payload["status"] = "failed"
    payload["completed_at"] = datetime.now(TAIPEI).isoformat(timespec="seconds")
    _write_json(status_path, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] in {"passed", "passed_with_warnings"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
