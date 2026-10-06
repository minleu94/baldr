"""檢視或套用僅限現況的 MOPS 月營收快照。

只接受與同次官方原始 HTML 驗證吻合的 CSV；資料只寫入現況觀測表，
不寫入正式歷史月營收表。
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_module.current_monthly_revenue_materialization import (
    apply_current_revenue,
    plan_current_revenue,
)
from data_module.ml_storage_capacity import (
    acquire_heavy_chain_reservation,
    release_heavy_chain_reservation,
)


CONTRACT = "current-observed-only; no historical announcement evidence"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument(
        "--raw-html-dir",
        type=Path,
        default=None,
        help="verified raw HTML directory; defaults to <snapshot parent>/raw_html",
    )
    parser.add_argument("--db-file", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--lock-path", type=Path, required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    raw_html_dir = args.raw_html_dir or args.snapshot.parent / "raw_html"
    collision_reason = _evidence_path_collision_reason(
        args.evidence_file,
        protected_files=(args.snapshot, args.db_file),
        protected_directory=raw_html_dir,
    )
    if collision_reason is not None:
        collision_result: dict[str, object] = {
            "schema_version": "current-monthly-revenue-cli.v2",
            "status": "blocked",
            "contract": CONTRACT,
            "formal_pit_eligible": False,
            "formal_monthly_table_written": False,
            "database_written": False,
            "evidence_written": False,
            "reason": collision_reason,
        }
        print(json.dumps(collision_result, ensure_ascii=True, indent=2))
        return 2

    try:
        plan = plan_current_revenue(args.snapshot, raw_html_dir=raw_html_dir)
    except (OSError, UnicodeError, ValueError, ArithmeticError) as exc:
        blocked_result: dict[str, object] = {
            "schema_version": "current-monthly-revenue-cli.v2",
            "status": "blocked",
            "snapshot": str(args.snapshot.resolve()),
            "raw_html_dir": str(raw_html_dir.resolve()),
            "contract": CONTRACT,
            "formal_pit_eligible": False,
            "formal_monthly_table_written": False,
            "database_written": False,
            "error_type": type(exc).__name__,
            "reason": str(exc),
        }
        _write_evidence(args.evidence_file, blocked_result)
        print(json.dumps(blocked_result, ensure_ascii=True, indent=2))
        return 2

    revenue_rows = [row for row in plan.records if row["item_code"] == "revenue"]
    comparator_rows = [
        row for row in plan.records if row["item_code"] == "revenue_yoy_comparator"
    ]
    result: dict[str, object] = {
        **plan.custody,
        "schema_version": "current-monthly-revenue-cli.v2",
        "status": "preview",
        "rows": len(revenue_rows),
        "normalized_record_count": len(plan.records),
        "same_report_yoy_comparator_count": len(comparator_rows),
        "coverage": dict(
            Counter(f"{row['period']}/{row['market']}" for row in revenue_rows)
        ),
        "contract": CONTRACT,
        "formal_pit_eligible": False,
        "formal_monthly_table_written": False,
        "database_written": False,
    }

    if args.apply:
        blocked_reason = _apply_preflight_error(args.db_file, args.backup_dir)
        if blocked_reason is not None:
            result.update(status="blocked", reason=blocked_reason)
            _write_evidence(args.evidence_file, result)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 2

        reservation = acquire_heavy_chain_reservation(args.lock_path)
        if reservation is None:
            result.update(
                status="blocked",
                reason="heavy chain active; no database write attempted",
            )
            _write_evidence(args.evidence_file, result)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 2
        try:
            receipt_dir = args.evidence_file.parent / (
                f"{args.evidence_file.stem}_receipts"
            )
            applied = apply_current_revenue(
                plan,
                db_file=args.db_file,
                backup_dir=args.backup_dir,
                receipt_dir=receipt_dir,
            )
            result.update(applied)
            result.update(
                status="applied",
                database_written=True,
                formal_monthly_table_written=False,
                formal_pit_eligible=False,
            )
        except Exception as exc:
            result.update(
                status="apply_failed_readback_required",
                error_type=type(exc).__name__,
                reason=str(exc),
                database_written=None,
                database_write_outcome=(
                    "unknown; read the target current-observation rows before retrying"
                ),
            )
            _write_evidence(args.evidence_file, result)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 2
        finally:
            release_heavy_chain_reservation(reservation)

    _write_evidence(args.evidence_file, result)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


def _apply_preflight_error(db_file: Path, backup_dir: Path) -> str | None:
    if not db_file.is_file():
        return "existing database required"
    if shutil.disk_usage(db_file.parent).free < 200 * 1024**3:
        return "data disk reserve below 200 GiB"
    backup_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(backup_dir).free < db_file.stat().st_size * 2:
        return "insufficient backup space"
    return None


def _evidence_path_collision_reason(
    evidence_file: Path,
    *,
    protected_files: tuple[Path, ...],
    protected_directory: Path,
) -> str | None:
    """Refuse evidence destinations that can overwrite source custody bytes."""

    evidence_path = evidence_file.expanduser().resolve(strict=False)
    normalized_evidence = os.path.normcase(str(evidence_path))
    protected_paths = [*protected_files]
    database_path = next(
        (
            path
            for path in protected_files
            if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}
        ),
        None,
    )
    if database_path is not None:
        protected_paths.extend(
            Path(f"{database_path}{suffix}")
            for suffix in ("-wal", "-shm", "-journal")
        )
    for protected in protected_paths:
        protected_path = protected.expanduser().resolve(strict=False)
        if normalized_evidence == os.path.normcase(str(protected_path)):
            return f"evidence destination collides with protected input: {protected_path}"

    raw_directory = protected_directory.expanduser().resolve(strict=False)
    try:
        evidence_path.relative_to(raw_directory)
    except ValueError:
        return None
    return f"evidence destination is inside protected raw HTML custody: {raw_directory}"


def _write_evidence(path: Path, result: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
