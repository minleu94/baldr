"""在隔離 scratch 中演練 Gate 2 weekly-review DB／projection 備份與還原。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.approved_weekly_history_projection import SCHEMA_VERSION


DEFAULT_DATA_ROOT = Path(os.environ.get("DATA_ROOT", "F:/Min/Python/Project/FA_Data"))
DEFAULT_OUTPUT_ROOT = Path(
    os.environ.get("OUTPUT_ROOT", str(DEFAULT_DATA_ROOT / "output"))
)
HISTORY_TABLE = "evidence_operations_weekly_reviews"
RECEIPT_SCHEMA = "baldr.weekly_review_recovery_rehearsal.v1"


def run_rehearsal(
    *,
    source_db_path: Path,
    source_projection_path: Path,
    scratch_root: Path,
    data_root: Path = DEFAULT_DATA_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    """唯讀來源檔，只在全新 scratch 複本注入故障並還原。"""

    source_db = _existing_regular_file(source_db_path, "source_db")
    source_projection = _existing_regular_file(source_projection_path, "source_projection")
    scratch = _canonical_path(Path(scratch_root).expanduser())
    protected_roots = (
        _canonical_path(Path(data_root).expanduser()),
        _canonical_path(Path(output_root).expanduser()),
    )
    if scratch.exists():
        raise ValueError("scratch_root_must_not_exist")
    if not scratch.parent.is_dir():
        raise ValueError("scratch_parent_must_exist")
    _reject_reparse_ancestors(scratch.parent, "scratch_parent")
    if any(_paths_overlap(scratch, root) for root in protected_roots):
        raise ValueError("scratch_root_overlaps_data_or_output_root")
    if _paths_overlap(scratch, source_db) or _paths_overlap(scratch, source_projection):
        raise ValueError("scratch_root_overlaps_source")
    if source_db == source_projection:
        raise ValueError("source_paths_must_be_distinct")
    if _is_production_db_path(source_db, data_root):
        raise ValueError("weekly_review_formal_db_forbidden")

    _validate_projection(source_projection)
    wal_path = Path(str(source_db) + "-wal")
    if wal_path.exists() and wal_path.stat().st_size:
        raise ValueError("source_db_has_nonempty_wal_copy_a_stable_working_copy_first")
    journal_path = Path(str(source_db) + "-journal")
    if journal_path.exists() and journal_path.stat().st_size:
        raise ValueError("source_db_has_nonempty_journal_copy_a_stable_working_copy_first")

    source_db_before = _sha256_file(source_db)
    source_wal_before = _optional_sha256_file(wal_path)
    source_journal_before = _optional_sha256_file(journal_path)
    source_projection_before = _sha256_file(source_projection)
    scratch.mkdir(parents=False, exist_ok=False)
    receipt_path = scratch / "recovery-rehearsal.json"
    payload: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "running",
        "engineering_only": True,
        "owner_review_performed": False,
        "formal_credit_authorized": False,
        "production_data_written": False,
        "task_scheduler_modified": False,
        "task_scheduler_api_called": False,
        "disable_first": {
            "required": True,
            "verified_in_scratch_simulation": False,
            "actual_scheduler_touched": False,
        },
        "source_db_path": str(source_db),
        "source_db_sha256_before": source_db_before,
        "source_projection_path": str(source_projection),
        "source_projection_sha256_before": source_projection_before,
        "scratch_root": str(scratch),
        "recovery": {},
        "errors": [],
    }
    try:
        # 先在 scratch 記錄 disable-first 狀態；不查詢或操作 Windows Task Scheduler。
        scheduler_state = scratch / "scheduler-state.simulated.json"
        _write_json(scheduler_state, {"enabled": False, "simulation_only": True})
        payload["disable_first"]["verified_in_scratch_simulation"] = (
            json.loads(scheduler_state.read_text(encoding="utf-8")).get("enabled") is False
        )

        db_work = scratch / "weekly-review-working-copy.sqlite"
        db_backup = scratch / "weekly-review-working-copy.backup.sqlite"
        db_restored = scratch / "weekly-review-working-copy.restored.sqlite"
        shutil.copy2(source_db, db_work)
        _assert_unchanged(source_db, source_db_before)
        if _optional_sha256_file(wal_path) != source_wal_before:
            raise ValueError("source_db_wal_changed_during_copy")
        if _optional_sha256_file(journal_path) != source_journal_before:
            raise ValueError("source_db_journal_changed_during_copy")
        db_identity_before = _weekly_history_identity(db_work)
        db_quick_check_before = _quick_check(db_work)
        if db_quick_check_before != "ok":
            raise ValueError("source_working_copy_quick_check_failed")
        shutil.copy2(db_work, db_backup)
        db_backup_hash = _sha256_file(db_backup)
        db_backup_identity = _weekly_history_identity(db_backup)
        if db_backup_identity != db_identity_before:
            raise ValueError("weekly_history_backup_identity_mismatch")

        # 故障只破壞剛建立的 scratch 副本；正式來源檔完全不開啟 SQLite writer。
        db_work.write_bytes(b"controlled recovery fault injection\n")
        db_fault_hash = _sha256_file(db_work)
        _restore_backup_to_new_file(db_backup, db_restored)
        db_restored_hash = _sha256_file(db_restored)
        db_quick_check_after = _quick_check(db_restored)
        db_identity_after = _weekly_history_identity(db_restored)

        projection_work = scratch / "weekly-approval-projection.json"
        projection_backup = scratch / "weekly-approval-projection.backup.json"
        projection_restored = scratch / "weekly-approval-projection.restored.json"
        shutil.copy2(source_projection, projection_work)
        _assert_unchanged(source_projection, source_projection_before)
        shutil.copy2(projection_work, projection_backup)
        projection_backup_hash = _sha256_file(projection_backup)
        projection_work.write_text(
            '{"schema_version":"injected-fault","records":[]}\n',
            encoding="utf-8",
        )
        projection_fault_hash = _sha256_file(projection_work)
        _restore_backup_to_new_file(projection_backup, projection_restored)
        projection_restored_hash = _sha256_file(projection_restored)
        projection_after = _validate_projection(projection_restored)

        _assert_unchanged(source_db, source_db_before)
        _assert_unchanged(source_projection, source_projection_before)
        db_recovery_ok = (
            db_fault_hash != db_backup_hash
            and db_restored_hash == db_backup_hash
            and db_quick_check_after == "ok"
            and db_identity_after == db_identity_before
        )
        projection_recovery_ok = (
            projection_fault_hash != projection_backup_hash
            and projection_restored_hash == projection_backup_hash
            and projection_after["records_count"]
            == _validate_projection(projection_backup)["records_count"]
        )
        payload["recovery"] = {
            "database": {
                "backup_sha256": db_backup_hash,
                "fault_injection_sha256": db_fault_hash,
                "restored_sha256": db_restored_hash,
                "quick_check_before": db_quick_check_before,
                "quick_check_after": db_quick_check_after,
                "weekly_review_identity_before": db_identity_before,
                "weekly_review_identity_after": db_identity_after,
                "restored": db_recovery_ok,
            },
            "approval_projection": {
                "backup_sha256": projection_backup_hash,
                "fault_injection_sha256": projection_fault_hash,
                "restored_sha256": projection_restored_hash,
                "records_count_after_restore": projection_after["records_count"],
                "formal_credit_authorized": projection_after["formal_credit_authorized"],
                "restored": projection_recovery_ok,
            },
        }
        payload["source_db_sha256_after"] = _sha256_file(source_db)
        payload["source_db_wal_sha256_after"] = _optional_sha256_file(wal_path)
        payload["source_db_journal_sha256_after"] = _optional_sha256_file(journal_path)
        payload["source_projection_sha256_after"] = _sha256_file(source_projection)
        payload["source_files_unchanged"] = (
            payload["source_db_sha256_after"] == source_db_before
            and payload["source_db_wal_sha256_after"] == source_wal_before
            and payload["source_db_journal_sha256_after"] == source_journal_before
            and payload["source_projection_sha256_after"] == source_projection_before
        )
        payload["source_db_wal_sha256_before"] = source_wal_before
        payload["source_db_journal_sha256_before"] = source_journal_before
        payload["passed"] = bool(
            payload["disable_first"]["verified_in_scratch_simulation"]
            and db_recovery_ok
            and projection_recovery_ok
            and payload["source_files_unchanged"]
        )
        payload["status"] = "passed" if payload["passed"] else "failed"
    except Exception as exc:  # noqa: BLE001 - leave an auditable scratch receipt on any failure.
        payload["status"] = "failed"
        payload["passed"] = False
        payload["errors"].append(f"{type(exc).__name__}:{exc}")
        payload["source_db_sha256_after"] = _sha256_file(source_db)
        payload["source_db_wal_sha256_after"] = _optional_sha256_file(wal_path)
        payload["source_db_journal_sha256_after"] = _optional_sha256_file(journal_path)
        payload["source_projection_sha256_after"] = _sha256_file(source_projection)
        payload["source_files_unchanged"] = (
            payload["source_db_sha256_after"] == source_db_before
            and payload["source_db_wal_sha256_after"] == source_wal_before
            and payload["source_db_journal_sha256_after"] == source_journal_before
            and payload["source_projection_sha256_after"] == source_projection_before
        )
        payload["source_db_wal_sha256_before"] = source_wal_before
        payload["source_db_journal_sha256_before"] = source_journal_before
    payload["completed_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload["receipt_path"] = str(receipt_path)
    _write_json(receipt_path, payload)
    return payload


def _existing_regular_file(path: Path, name: str) -> Path:
    unresolved = Path(path).expanduser().absolute()
    info = unresolved.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"{name}_must_be_regular_file")
    return _canonical_path(unresolved)


def _canonical_path(path: Path) -> Path:
    """以絕對、大小寫正規化路徑比對，避免探查 Windows reparse target。"""

    return Path(os.path.normcase(os.path.abspath(path)))


def _paths_overlap(left: Path, right: Path) -> bool:
    left = _canonical_path(left)
    right = _canonical_path(right)
    return left == right or left in right.parents or right in left.parents


def _reject_reparse_ancestors(path: Path, name: str) -> None:
    for component in (path, *path.parents):
        if not component.exists():
            continue
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"{name}_reparse_point_forbidden")


def _is_production_db_path(path: Path, data_root: Path) -> bool:
    roots = {
        _canonical_path(Path(data_root).expanduser()),
        _canonical_path(Path(os.environ.get("DATA_ROOT", str(DEFAULT_DATA_ROOT))).expanduser()),
        _canonical_path(Path("F:/Min/Python/Project/FA_Data")),
    }
    for root in roots:
        production_path = _canonical_path(root / "sqlite" / "twstock.db")
        if path == production_path:
            return True
        if production_path.exists():
            try:
                if os.path.samefile(path, production_path):
                    return True
            except OSError as exc:
                raise ValueError("production_db_identity_unverifiable") from exc
    return False


def _validate_projection(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("approval_projection_must_be_object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("approval_projection_schema_unsupported")
    if payload.get("formal_credit_authorized") is not False:
        raise ValueError("approval_projection_must_not_authorize_formal_credit")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("approval_projection_records_must_be_array")
    return {"records_count": len(records), "formal_credit_authorized": False}


def _weekly_history_identity(path: Path) -> dict[str, Any]:
    with sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        present = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (HISTORY_TABLE,),
        ).fetchone()
        if present is None:
            raise ValueError("weekly_history_table_missing")
        rows = connection.execute(
            f'SELECT review_id, review_hash, period_start, period_end FROM "{HISTORY_TABLE}" '
            "ORDER BY review_id"
        ).fetchall()
    identity = [[str(value) for value in row] for row in rows]
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"record_count": len(identity), "identity_sha256": f"sha256:{digest}"}


def _quick_check(path: Path) -> str:
    with sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        row = connection.execute("PRAGMA quick_check").fetchone()
    return str(row[0]) if row else "missing_result"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _optional_sha256_file(path: Path) -> str | None:
    return _sha256_file(path) if path.is_file() else None


def _assert_unchanged(path: Path, expected_hash: str) -> None:
    if _sha256_file(path) != expected_hash:
        raise ValueError(f"source_changed_during_rehearsal:{path.name}")


def _restore_backup_to_new_file(source: Path, target: Path) -> None:
    """將備份還原為新檔，保留故障注入檔供稽核且不覆寫任何來源。"""

    if target.exists():
        raise FileExistsError("restore_target_already_exists")
    shutil.copyfile(source, target)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db-path", type=Path, required=True)
    parser.add_argument("--source-projection-path", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_rehearsal(
            source_db_path=args.source_db_path,
            source_projection_path=args.source_projection_path,
            scratch_root=args.scratch_root,
            data_root=args.data_root,
            output_root=args.output_root,
        )
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "rejected", "error": f"{type(exc).__name__}:{exc}"}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
