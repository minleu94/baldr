"""Capture one complete current MOPS monthly-revenue snapshot for the Update tab."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.monthly_revenue_snapshot_harvester import (
    build_mops_monthly_revenue_snapshot,
    create_monthly_revenue_snapshot_capture_directory,
    write_mops_snapshot_csv,
)
from data_module.monthly_revenue_snapshot_selection import (
    expected_latest_monthly_revenue_period,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def _write_receipt(path: Path, payload: dict[str, object]) -> str:
    encoded = (json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    if path.read_bytes() != encoded:
        raise OSError("MOPS candidate receipt readback mismatch")
    return hashlib.sha256(encoded).hexdigest()


def capture_candidate(output_root: Path, *, today: date | None = None) -> dict[str, object]:
    capture_date = today or datetime.now(TAIPEI).date()
    period = expected_latest_monthly_revenue_period(capture_date)
    snapshot_root = Path(output_root) / "monthly_revenue_mops_snapshots"
    capture_dir = create_monthly_revenue_snapshot_capture_directory(
        snapshot_root, fetch_date=capture_date
    )
    _write_receipt(
        capture_dir / "scheduled_capture.json",
        {"schema_version": "mops-scheduled-capture-marker.v1", "managed": True},
    )
    raw_dir = capture_dir / "raw_html"
    result = build_mops_monthly_revenue_snapshot(
        start_period=period,
        end_period=period,
        markets=("twse", "tpex"),
        fetch_date=capture_date,
        save_html_dir=raw_dir,
        sleep_seconds=0.5,
    )

    raw_sources: dict[str, dict[str, object]] = {}
    for market in ("twse", "tpex"):
        raw_path = raw_dir / f"{market}_{period}.html"
        if raw_path.is_file():
            raw_bytes = raw_path.read_bytes()
            market_rows = [row for row in result.rows if row.get("market") == market]
            raw_sources[market] = {
                "path": str(raw_path),
                "bytes": len(raw_bytes),
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "source_version": market_rows[0].get("source_version") if market_rows else None,
                "fetched_at": market_rows[0].get("fetched_at") if market_rows else None,
            }

    market_counts = {
        market: sum(1 for row in result.rows if row.get("market") == market)
        for market in ("twse", "tpex")
    }
    keys = [
        (row.get("market", ""), row.get("stock_code", ""), row.get("period", ""))
        for row in result.rows
    ]
    complete = (
        result.requested_periods == (period,)
        and result.fetched_periods == (period,)
        and not result.cancelled
        and not result.diagnostics
        and all(market_counts.values())
        and len(keys) == len(set(keys))
        and all(row.get("current_month_revenue", "") != "" for row in result.rows)
        and set(raw_sources) == {"twse", "tpex"}
    )
    candidate_path: Path | None = None
    candidate_sha256: str | None = None
    if complete:
        candidate_path = capture_dir / (
            f"mops_monthly_revenue_snapshot_{period}_{period}_{capture_date.isoformat()}.csv"
        )
        write_mops_snapshot_csv(candidate_path, result.rows)
        candidate_bytes = candidate_path.read_bytes()
        candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()

    diagnostics = [
        {"code": item.code, "market": item.market, "message": item.message}
        for item in result.diagnostics
    ]
    if not complete and not diagnostics:
        diagnostics.append(
            {
                "code": "mops_candidate_incomplete",
                "market": None,
                "message": "雙市場期別、列數、欄位或原始回應未通過完整性檢查",
            }
        )
    receipt: dict[str, object] = {
        "schema_version": "mops-monthly-revenue-scheduled-candidate.v1",
        "status": "candidate_prepared" if complete else "rejected",
        "candidate_only": True,
        "period": period,
        "capture_date_taipei": capture_date.isoformat(),
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_markets": ["twse", "tpex"],
        "fetched_periods": list(result.fetched_periods),
        "row_count": len(result.rows),
        "market_row_counts": market_counts,
        "raw_sources": raw_sources,
        "candidate_csv": str(candidate_path) if candidate_path else None,
        "candidate_csv_sha256": candidate_sha256,
        "diagnostics": diagnostics,
        "formal_pit_eligible": False,
        "availability_mapping_emitted": False,
        "formal_apply_authorized": False,
        "formal_database_written": False,
        "receipt_path": str(capture_dir / "capture_receipt.json"),
    }
    receipt_hash = _write_receipt(capture_dir / "capture_receipt.json", receipt)
    if complete and candidate_path is not None and candidate_sha256 is not None:
        _write_receipt(
            capture_dir / "capture_complete.json",
            {
                "schema_version": "mops-scheduled-capture-complete.v1",
                "status": "captured",
                "candidate_file": candidate_path.name,
                "candidate_sha256": candidate_sha256,
                "receipt_sha256": receipt_hash,
            },
        )
        receipt["status"] = "captured"
    receipt["receipt_sha256"] = receipt_hash
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture one complete MOPS SII/OTC snapshot; never writes formal data."
    )
    parser.add_argument("--output-root", type=Path, default=Path(os.environ.get("OUTPUT_ROOT", "output")))
    parser.add_argument("--date", help="Taipei capture date, for deterministic operation")
    args = parser.parse_args(argv)
    try:
        capture_date = date.fromisoformat(args.date) if args.date else None
        result = capture_candidate(args.output_root, today=capture_date)
    except (OSError, RuntimeError, ValueError) as exc:
        result = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "formal_database_written": False,
        }
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0 if result.get("status") == "captured" else 2


if __name__ == "__main__":
    raise SystemExit(main())
