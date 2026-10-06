"""Capture a prospective official TWSE quote observation for an explicit list.

This bounded one-shot collector is intentionally not the Paper execution
collector and is not a scheduled recommendation task.  The symbol list must
carry its own source reference/date; it is never reinterpreted as today's
recommendation or an order universe.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.twse_quote_observation_capture import (
    TwseQuoteObservationError,
    capture_twse_quote_observation,
    persist_twse_quote_observation,
)
from data_module.tpex_quote_observation_capture import (
    TpexQuoteObservationError,
    capture_tpex_daily_close_observation,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def _venue_symbols(
    *,
    data_root: Path,
    source_date: str,
    symbols: tuple[str, ...],
) -> tuple[dict[str, tuple[str, ...]], dict[str, object]]:
    date_key = str(source_date).strip().replace("-", "").replace("/", "")
    if len(date_key) != 8 or not date_key.isdigit():
        raise ValueError("symbol-source-date must be YYYY-MM-DD or YYYYMMDD")
    requested = set(symbols)
    by_venue: dict[str, set[str]] = {"TWSE": set(), "TPEx": set()}
    evidence: dict[str, object] = {}
    for venue, directory in (("TWSE", "daily_price"), ("TPEx", "daily_price_tpex")):
        path = Path(data_root) / directory / f"{date_key}.csv"
        evidence[venue] = {
            "path": str(path.resolve()),
            "file_sha256": _file_hash(path),
            "exists": path.is_file() and not path.is_symlink(),
        }
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                code = str(
                    row.get("證券代號")
                    or row.get("stock_id")
                    or row.get("SecuritiesCompanyCode")
                    or ""
                ).strip()
                if code in requested:
                    by_venue[venue].add(code)
    conflicts = sorted(by_venue["TWSE"] & by_venue["TPEx"])
    missing = sorted(requested - by_venue["TWSE"] - by_venue["TPEx"])
    if conflicts:
        raise ValueError("venue_mapping_conflict:" + ",".join(conflicts))
    if missing:
        raise ValueError("venue_mapping_missing:" + ",".join(missing))
    return (
        {venue: tuple(sorted(values)) for venue, values in by_venue.items() if values},
        {
            "source_date": date_key,
            "source_data_root": str(Path(data_root).resolve()),
            "venue_evidence": evidence,
        },
    )
def _write_status(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _file_hash(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture prospective official TWSE quote observations.")
    parser.add_argument("--symbols", required=True, help="Comma-separated four-digit TWSE symbols.")
    parser.add_argument("--symbol-source-ref", required=True, help="Reference for the observation symbol list.")
    parser.add_argument("--symbol-source-date", required=True, help="Natural date of the symbol-list source, YYYY-MM-DD.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--data-root",
        default=os.environ.get("DATA_ROOT", r"D:\Min\Python\Project\FA_Data"),
        help="Read-only canonical daily-price root used to prove each symbol venue.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(__import__("sys").stdout, "reconfigure"):
        __import__("sys").stdout.reconfigure(encoding="utf-8")
    output_root = Path(args.output_root).expanduser().resolve()
    status_path = output_root / "scheduled" / "twse_quote_observation" / "latest_status.json"
    now = datetime.now(timezone.utc)
    local_now = now.astimezone(TAIPEI)
    source_ref = Path(args.symbol_source_ref).expanduser()
    source_metadata: dict[str, object] = {
        "kind": "explicit_observation_symbol_list",
        "reference": str(source_ref.resolve()) if source_ref.exists() else str(source_ref),
        "source_date": str(args.symbol_source_date)[:10],
        "source_file_sha256": _file_hash(source_ref),
        "is_today_recommendation": False,
        "is_order_universe": False,
    }
    symbols = tuple(item.strip() for item in str(args.symbols).split(",") if item.strip())
    venue_symbols, venue_evidence = _venue_symbols(
        data_root=Path(args.data_root).expanduser().resolve(),
        source_date=str(args.symbol_source_date),
        symbols=symbols,
    )
    source_metadata["venue_detection"] = venue_evidence
    payload: dict[str, object] = {
        "schema_version": "twse-quote-observation-scheduled.v1",
        "task": "prospective-twse-quote-observation-once",
        "observed_at": now.isoformat(),
        "observation_date": local_now.date().isoformat(),
        "output_root": str(output_root),
        "status_path": str(status_path),
        "symbol_source": source_metadata,
        "symbols": list(symbols),
        "venue_symbols": {key: list(value) for key, value in venue_symbols.items()},
        "quote_only": True,
        "actual_fill_proven": False,
        "execution_event_time_proven": False,
        "historical_backfill_claimed": False,
        "formal_source_contract_eligible": False,
        "observed_liquidity_cost_eligible": False,
        "estimated_cost_eligible": False,
    }
    temporary_root = Path(tempfile.gettempdir()) / (
        f"twse_quote_observation_{local_now.date().isoformat()}_{uuid.uuid4().hex[:12]}"
    )
    try:
        durable_captures: list[dict[str, object]] = []
        if venue_symbols.get("TWSE"):
            capture = capture_twse_quote_observation(
                symbols=venue_symbols["TWSE"],
                observation_date=local_now.date(),
                output_dir=temporary_root,
                symbol_source=source_metadata,
                timeout_seconds=args.timeout_seconds,
            )
            durable_captures.append(
                persist_twse_quote_observation(
                    capture,
                    durable_root=output_root / "paper_execution_eod_replay" / "prospective_quote_observations",
                    allowed_root=output_root,
                )
            )
        if venue_symbols.get("TPEx"):
            durable_captures.append(
                capture_tpex_daily_close_observation(
                    symbols=venue_symbols["TPEx"],
                    requested_date=local_now.date().strftime("%Y%m%d"),
                    output_root=output_root,
                    symbol_source=source_metadata,
                )
            )
        if not durable_captures:
            raise ValueError("venue_mapping_empty")
        all_missing_values: set[str] = set()
        for capture in durable_captures:
            missing_symbols = capture.get("missing_symbols")
            if isinstance(missing_symbols, (list, tuple, set)):
                all_missing_values.update(str(symbol) for symbol in missing_symbols)
        all_missing = sorted(all_missing_values)
        stale_tpex = any(
            capture.get("venue") == "TPEx"
            and str(capture.get("source_date")) != local_now.date().isoformat()
            for capture in durable_captures
        )
        tpex_no_rows = any(
            capture.get("venue") == "TPEx"
            and str(capture.get("coverage_status")) == "no_rows"
            for capture in durable_captures
        )
        tpex_capture_present = any(
            capture.get("venue") == "TPEx" for capture in durable_captures
        )
        capture_statuses = {str(capture.get("status")) for capture in durable_captures}
        overall_status = (
            "durable_partial"
            if all_missing or stale_tpex or "durable_partial" in capture_statuses
            else "durable"
        )
        payload.update(
            {
                "status": overall_status,
                "capture": durable_captures[0],
                "captures": durable_captures,
                "missing_symbols": all_missing,
                "coverage_status": "complete" if not all_missing else "partial",
                "current_session_quote_status": (
                    "tpex_official_response_no_rows"
                    if tpex_no_rows
                    else (
                        "tpex_daily_close_only"
                        if stale_tpex or tpex_capture_present
                        else "venue_routes_captured"
                    )
                ),
            }
        )
        _write_status(status_path, payload)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError, TwseQuoteObservationError, TpexQuoteObservationError) as exc:
        payload.update(
            {
                "status": "blocked",
                "reason": f"quote_observation_failed:{type(exc).__name__}",
                "error": str(exc),
            }
        )
        _write_status(status_path, payload)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "build_parser"]
