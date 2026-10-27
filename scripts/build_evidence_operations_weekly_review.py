from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
import sys
from pathlib import Path
from typing import Any
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.evidence_operations_service import EvidenceOperationsService
from app_module.evidence_operations_history_repository import (
    EvidenceOperationsHistoryReadOnlyError,
    EvidenceOperationsHistoryRepository,
)
from app_module.evidence_weekly_history_decision_bridge import (
    load_and_validate_weekly_review_decision_artifact,
)
from data_module.config import TWStockConfig
from app_module.personal_store_selection import resolve_personal_store_selection
from app_module.personal_store_routes import PersonalStoreMode
from app_module.weekly_review_history_source import is_production_like_weekly_db_path
from runtime.console_encoding import configure_utf8_console
from runtime.sqlite_file_set_fingerprint import (
    SQLITE_FILE_SET_FINGERPRINT_METHOD,
    fingerprint_sqlite_file_set,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only V1.3 evidence operations weekly review.")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--db-path")
    parser.add_argument("--data-root")
    parser.add_argument("--output-root")
    parser.add_argument("--personal-store-root")
    parser.add_argument("--personal-store-mode", choices=("personal", "legacy_read_only"))
    parser.add_argument("--smoke-report-path")
    parser.add_argument("--result-id")
    parser.add_argument("--plan-action-items", action="store_true")
    parser.add_argument("--confirm-action-items", action="store_true")
    parser.add_argument("--save-history", action="store_true")
    parser.add_argument("--candidate-review-artifact")
    parser.add_argument("--candidate-review-sidecar-path")
    parser.add_argument("--candidate-review-authorized-receipt-root")
    parser.add_argument("--list-history", action="store_true")
    parser.add_argument("--history-limit", type=int, default=20)
    parser.add_argument("--action-owner", default="human")
    parser.add_argument("--json-output", action="store_true")
    parser.add_argument("--markdown-output")
    parser.add_argument("--receipt-output", help="Write an exclusive-create dry-run runbook receipt.")
    return parser.parse_args()


def _sqlite_file_set_fingerprint(db_path: Path) -> str | None:
    """取得共用 SQLite 檔案組指紋；資料庫主檔不存在時回傳 None。"""
    base = Path(os.path.abspath(db_path)).resolve(strict=False)
    if not base.is_file():
        return None
    return str(fingerprint_sqlite_file_set(base)["sha256"])


def _canonical_date(value: str, field: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO calendar date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be canonical YYYY-MM-DD")
    return parsed.isoformat()


def _write_runbook_receipt(output_path: str | Path, payload: dict[str, Any], *,
                           start_date: str, end_date: str, db_path: Path,
                           fingerprint_before: str | None, fingerprint_after: str | None,
                           confirm_action_items: bool = False, save_history: bool = False) -> Path:
    if fingerprint_before is None or fingerprint_after is None:
        raise ValueError("dry-run receipt requires an existing SQLite working-copy file")
    if fingerprint_before != fingerprint_after:
        raise ValueError("dry-run receipt refused because the SQLite file set changed during review")
    lifecycle = payload.get("manual_lifecycle_candidates")
    signal_decay = payload.get("signal_decay")
    candidate_count = None
    if isinstance(signal_decay, dict):
        demote_count = signal_decay.get("demote_candidate_count")
        retire_count = signal_decay.get("retire_candidate_count")
        if (
            isinstance(demote_count, int)
            and not isinstance(demote_count, bool)
            and isinstance(retire_count, int)
            and not isinstance(retire_count, bool)
            and demote_count >= 0
            and retire_count >= 0
        ):
            candidate_count = demote_count + retire_count
    lifecycle_safe = (
        isinstance(lifecycle, list)
        and candidate_count == len(lifecycle)
        and all(
            isinstance(item, dict)
            and "apply_action" in item
            and item["apply_action"] is False
            for item in lifecycle
        )
    )
    report_period_matches = (
        payload.get("start_date") == start_date
        and payload.get("end_date") == end_date
    )
    safety = {
        "write_performed": payload.get("write_performed") is False,
        "confirm_action_items": confirm_action_items is False,
        "save_history": save_history is False,
        "production_scheduler_allowed": (
            payload.get("manual_approval", {}).get("production_scheduler_allowed") is False
        ),
        "lifecycle_apply_action_all_false": lifecycle_safe,
        "report_period_matches_receipt": report_period_matches,
    }
    if not all(safety.values()):
        failed = ",".join(key for key, passed in safety.items() if not passed)
        raise ValueError(f"dry-run receipt safety assertions failed: {failed}")
    output = Path(output_path).expanduser().resolve()
    canonical_db = Path(os.path.abspath(db_path)).resolve()
    if output in {canonical_db, Path(str(canonical_db) + "-wal").resolve(),
                  Path(str(canonical_db) + "-shm").resolve(), Path(str(canonical_db) + "-journal").resolve()}:
        raise ValueError("receipt output must not overwrite the working-copy SQLite file set")
    if not output.parent.is_dir():
        raise ValueError("receipt output parent must already exist")
    receipt = {
        "schema_version": "baldr-weekly-runbook-artifact.v1",
        "artifact_role": "weekly_review_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period_start": start_date,
        "period_end": end_date,
        "decision_date": end_date,
        "database_identity": {
            "role": "working_copy",
            "path": str(canonical_db),
            "fingerprint_method": SQLITE_FILE_SET_FINGERPRINT_METHOD,
            "fingerprint_before": fingerprint_before,
            "fingerprint_after": fingerprint_after,
            "stable": True,
        },
        "report_payload": payload,
        "safety_flags_verified": safety,
        "production_scheduler_allowed": False,
    }
    serialized = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
    except FileExistsError as exc:
        raise ValueError("receipt output already exists; refusing replacement") from exc
    return output


def _config(args: argparse.Namespace) -> TWStockConfig:
    kwargs: dict[str, Any] = {}
    if args.data_root is not None:
        kwargs["data_root"] = args.data_root
    if args.output_root is not None:
        kwargs["output_root"] = args.output_root
    for field in ("personal_store_root", "personal_store_mode"):
        value = getattr(args, field, None)
        if value is not None:
            kwargs[field] = value
    config = TWStockConfig(**kwargs)
    if args.db_path:
        config.db_file = Path(args.db_path)
    config.use_sqlite = True
    return config


_DEFAULT_PRODUCTION_DATA_ROOT = Path("F:/Min/Python/Project/FA_Data")


def _production_like(
    path: Path,
    config: TWStockConfig,
    *,
    explicit_data_root: str | Path | None = None,
) -> bool:
    if is_production_like_weekly_db_path(path, config):
        return True
    if explicit_data_root is None:
        return False
    try:
        actual_db_path = path.expanduser().resolve()
        raw_root = Path(explicit_data_root).expanduser().resolve()
    except (OSError, RuntimeError):
        return True
    return actual_db_path == (raw_root / "sqlite" / "twstock.db").resolve()


def _read_only_history_db_path(args: argparse.Namespace) -> Path:
    if args.db_path:
        return Path(args.db_path)
    data_root = Path(args.data_root) if args.data_root is not None else Path(
        os.environ.get("DATA_ROOT", _DEFAULT_PRODUCTION_DATA_ROOT)
    )
    return data_root / "sqlite" / "twstock.db"


def _list_history(args: argparse.Namespace) -> int:
    diagnostics: list[str] = []
    data_root = Path(args.data_root) if args.data_root is not None else Path(
        os.environ.get("DATA_ROOT", _DEFAULT_PRODUCTION_DATA_ROOT))
    config = SimpleNamespace(data_root=data_root,
        output_root=Path(args.output_root) if args.output_root is not None else data_root / "output",
        db_file=_read_only_history_db_path(args),
        personal_store_root=(getattr(args, "personal_store_root", None)
            if getattr(args, "personal_store_root", None) is not None else os.environ.get("PERSONAL_STORE_ROOT")),
        personal_store_mode=(getattr(args, "personal_store_mode", None)
            if getattr(args, "personal_store_mode", None) is not None else os.environ.get("PERSONAL_STORE_MODE")))
    selection = resolve_personal_store_selection(config)
    try:
        records = EvidenceOperationsHistoryRepository(
            config,
            db_path=config.db_file if selection.mode is PersonalStoreMode.LEGACY_COMPAT else None,
            read_only=True,
        ).list_weekly_reviews(
            start_date=args.start_date,
            end_date=args.end_date,
            limit=args.history_limit,
        )
    except EvidenceOperationsHistoryReadOnlyError as exc:
        records = []
        diagnostics.append(str(exc))
    history_payload: dict[str, Any] = {
        "history_records": [record.to_dict() for record in records],
        "diagnostics": diagnostics,
        "write_performed": False,
    }
    if args.json_output:
        print(json.dumps(history_payload, ensure_ascii=False, sort_keys=True))
    else:
        for record in history_payload["history_records"]:
            print(
                f"{record['period_start']}..{record['period_end']} "
                f"{record['review_status']} {record['review_id']}"
            )
    return 0


def main() -> int:
    configure_utf8_console()
    args = parse_args()
    if args.receipt_output and (
        args.confirm_action_items or args.save_history or args.list_history or args.markdown_output
    ):
        print(
            "--receipt-output is dry-run only and cannot be combined with write, history-list, or markdown-output flags",
            file=sys.stderr,
        )
        return 2
    if args.candidate_review_artifact and not args.save_history:
        print("candidate review artifact requires --save-history", file=sys.stderr)
        return 2
    if args.candidate_review_artifact and args.confirm_action_items:
        print(
            "candidate review artifact cannot be combined with action-item confirmation; save and approve history first",
            file=sys.stderr,
        )
        return 2
    if args.candidate_review_artifact and not args.candidate_review_sidecar_path:
        print("candidate review artifact requires --candidate-review-sidecar-path", file=sys.stderr)
        return 2
    if args.list_history:
        return _list_history(args)
    config = _config(args)
    if args.save_history and not args.db_path:
        print("save history requires explicit --db-path", file=sys.stderr)
        return 2
    if args.confirm_action_items and not args.db_path:
        print("confirm action items requires explicit --db-path", file=sys.stderr)
        return 2
    if (args.confirm_action_items or args.save_history) and _production_like(
        Path(config.db_file), config, explicit_data_root=args.data_root
    ):
        print("production-like DB is not permitted for action confirmation or history saving; use an approved working-copy DB", file=sys.stderr)
        return 2
    receipt_db_path = Path(config.db_file)
    receipt_fingerprint_before = (
        _sqlite_file_set_fingerprint(receipt_db_path) if args.receipt_output else None
    )
    service = EvidenceOperationsService(
        config,
        db_path=Path(config.db_file),
        read_only=not args.confirm_action_items,
    )
    report = service.build_weekly_review(
        start_date=args.start_date,
        end_date=args.end_date,
        smoke_report_path=args.smoke_report_path,
        result_id=args.result_id,
    )
    payload = report.to_dict()
    if service.source_lineage:
        payload["source_lineage"] = service.source_lineage
    candidate_review_decision = None
    if args.candidate_review_artifact:
        try:
            candidate_review_decision = load_and_validate_weekly_review_decision_artifact(
                args.candidate_review_artifact,
                expected_period_start=report.start_date,
                expected_period_end=report.end_date,
                expected_sidecar_path=args.candidate_review_sidecar_path,
                authorized_receipt_root=args.candidate_review_authorized_receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(f"candidate review artifact refused: {exc}", file=sys.stderr)
            return 2
        payload["candidate_review_decision"] = candidate_review_decision
    if args.plan_action_items or args.confirm_action_items or args.receipt_output:
        action_plan = service.plan_action_items(
            start_date=args.start_date,
            end_date=args.end_date,
            owner=args.action_owner,
            confirm=bool(args.confirm_action_items),
        )
        if action_plan.write_performed:
            report = service.build_weekly_review(
                start_date=args.start_date,
                end_date=args.end_date,
                smoke_report_path=args.smoke_report_path,
                result_id=args.result_id,
            )
            payload = report.to_dict()
            if service.source_lineage:
                payload["source_lineage"] = service.source_lineage
        payload["action_owner"] = args.action_owner
        payload["action_item_plan"] = action_plan.to_dict()
        payload["write_performed"] = payload["write_performed"] or action_plan.write_performed
    if args.save_history:
        if args.candidate_review_artifact:
            try:
                latest_decision = load_and_validate_weekly_review_decision_artifact(
                    args.candidate_review_artifact,
                    expected_period_start=report.start_date,
                    expected_period_end=report.end_date,
                    expected_sidecar_path=args.candidate_review_sidecar_path,
                    authorized_receipt_root=args.candidate_review_authorized_receipt_root,
                )
            except (OSError, ValueError) as exc:
                print(f"candidate review artifact changed before history save: {exc}", file=sys.stderr)
                return 2
            if latest_decision != candidate_review_decision:
                print("candidate review artifact changed before history save", file=sys.stderr)
                return 2
        payload["write_performed"] = True
        selection = resolve_personal_store_selection(config)
        record = EvidenceOperationsHistoryRepository(config,
            db_path=Path(config.db_file) if selection.mode is PersonalStoreMode.LEGACY_COMPAT else None).save_weekly_review(
            report,
            generated_by="build_evidence_operations_weekly_review.py",
            payload_json=payload,
        )
        payload["history_record"] = record.to_dict()
        payload["write_performed"] = True
    if args.markdown_output:
        Path(args.markdown_output).write_text(service.render_markdown(report), encoding="utf-8")
    if args.receipt_output:
        try:
            canonical_start = _canonical_date(args.start_date, "start-date")
            canonical_end = _canonical_date(args.end_date, "end-date")
            if canonical_start > canonical_end:
                raise ValueError("start-date must not be after end-date")
            receipt_path = _write_runbook_receipt(
                args.receipt_output,
                payload,
                start_date=canonical_start,
                end_date=canonical_end,
                db_path=receipt_db_path,
                fingerprint_before=receipt_fingerprint_before,
                fingerprint_after=_sqlite_file_set_fingerprint(receipt_db_path),
                confirm_action_items=args.confirm_action_items,
                save_history=args.save_history,
            )
        except (OSError, ValueError) as exc:
            print(f"weekly runbook receipt refused: {exc}", file=sys.stderr)
            return 2
        payload["runbook_receipt_path"] = str(receipt_path)
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(service.render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
