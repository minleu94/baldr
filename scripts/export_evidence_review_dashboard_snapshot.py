"""Export one read-only Evidence Review weekly-history dashboard page."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.evidence_operations_history_dashboard_dtos import (
    EvidenceOperationsHistoryCursor,
    EvidenceOperationsHistoryDashboardRequest,
)
from app_module.evidence_operations_history_dashboard_service import (
    create_evidence_operations_history_dashboard_service,
)
from data_module.config import TWStockConfig
from runtime.console_encoding import configure_utf8_console
from runtime.sqlite_file_set_fingerprint import (
    SQLITE_FILE_SET_FINGERPRINT_METHOD,
    fingerprint_sqlite_file_set,
)


SCHEMA_VERSION = "baldr-weekly-runbook-artifact.v1"
ARTIFACT_ROLE = "evidence_review_dashboard"
SQLITE_SUFFIXES = ("", "-journal", "-wal", "-shm")
MAX_PAGE_SIZE = 50


def _iso_date(value: str | None, argument: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{argument} must use YYYY-MM-DD") from exc
    if normalized != text:
        raise ValueError(f"{argument} must use canonical YYYY-MM-DD")
    return normalized


def _fingerprint_sqlite_file_set(db_path: Path) -> str:
    """取得共用 SQLite 主檔與 sidecar 指紋。"""

    return str(fingerprint_sqlite_file_set(db_path)["sha256"])


def _page_payload(result: Any) -> dict[str, Any]:
    return {
        "request": asdict(result.request),
        "cards": asdict(result.cards),
        "rows": [asdict(row) for row in result.rows],
        "source_available": bool(result.source_available),
        "has_more_rows": bool(result.has_more_rows),
        "next_cursor": asdict(result.next_cursor) if result.next_cursor is not None else None,
        "empty_state_message": str(result.empty_state_message),
        "limitations": list(result.limitations),
        "diagnostics": (
            [str(result.empty_state_message)]
            if not result.source_available and result.empty_state_message
            else []
        ),
    }


def build_snapshot(
    *,
    db_path: Path,
    output_path: Path,
    period_start: str | None = None,
    period_end: str | None = None,
    limit: int = MAX_PAGE_SIZE,
    cursor: EvidenceOperationsHistoryCursor | None = None,
    config: Any | None = None,
) -> dict[str, Any]:
    """Read one dashboard page and write a hash-pinned, non-approving envelope."""

    if not 1 <= int(limit) <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    normalized_start = _iso_date(period_start, "--period-start")
    normalized_end = _iso_date(period_end, "--period-end")
    if normalized_start and normalized_end and normalized_start > normalized_end:
        raise ValueError("--period-start must not be later than --period-end")

    resolved_db = db_path.expanduser().resolve(strict=False)
    resolved_output = output_path.expanduser().resolve(strict=False)
    protected_paths = {resolved_db, *(Path(f"{resolved_db}{suffix}") for suffix in SQLITE_SUFFIXES[1:])}
    if resolved_output in protected_paths:
        raise ValueError("output path must not overlap the selected SQLite file set")

    fingerprint_before: str | None = None
    fingerprint_after: str | None = None
    stable_during_read = False
    source_available = False
    diagnostics: list[str] = []
    page: dict[str, Any] | None = None
    try:
        selected_config = config if config is not None else TWStockConfig()
        service = create_evidence_operations_history_dashboard_service(
            selected_config,
            db_path=resolved_db,
        )
        fingerprint_before = _fingerprint_sqlite_file_set(resolved_db)
        result = service.load_dashboard(
            EvidenceOperationsHistoryDashboardRequest(
                start_date=normalized_start,
                end_date=normalized_end,
                limit=int(limit),
                cursor=cursor,
            )
        )
        page = _page_payload(result)
        source_available = bool(result.source_available)
        diagnostics.extend(page["diagnostics"])
        fingerprint_after = _fingerprint_sqlite_file_set(resolved_db)
        stable_during_read = fingerprint_before == fingerprint_after
        if not stable_during_read:
            diagnostics.append("sqlite_file_set_changed_during_read")
    except Exception as exc:  # CLI should emit a diagnostic artifact for guarded/missing sources.
        diagnostics.append(f"{type(exc).__name__}: {exc}")
        if fingerprint_before is not None:
            try:
                fingerprint_after = _fingerprint_sqlite_file_set(resolved_db)
                stable_during_read = fingerprint_before == fingerprint_after
            except (OSError, ValueError):
                fingerprint_after = None

    period_bound = normalized_start is not None and normalized_end is not None
    if not period_bound:
        diagnostics.append("dashboard_weekly_period_unbound")
    dashboard_verified = bool(
        source_available and page is not None and stable_during_read and period_bound
    )
    payload = page or {
        "request": {
            "start_date": normalized_start,
            "end_date": normalized_end,
            "limit": int(limit),
            "cursor": asdict(cursor) if cursor is not None else None,
        },
        "cards": None,
        "rows": [],
        "source_available": False,
        "has_more_rows": False,
        "next_cursor": None,
        "empty_state_message": "Dashboard source unavailable; see diagnostics.",
        "limitations": [],
        "diagnostics": list(diagnostics),
    }
    payload["dashboard_verified"] = dashboard_verified
    payload["weekly_period_bound"] = period_bound
    payload["pagination_complete"] = not bool(payload.get("has_more_rows"))
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "artifact_role": ARTIFACT_ROLE,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "period_start": normalized_start,
        "period_end": normalized_end,
        "database_identity": {
            "role": "review_store",
            "path": str(resolved_db),
            "fingerprint_method": SQLITE_FILE_SET_FINGERPRINT_METHOD,
            "fingerprint_before": fingerprint_before,
            "fingerprint_after": fingerprint_after,
            "stable_during_read": stable_during_read,
        },
        "safety": {
            "write_performed": False,
            "source_write_performed": False,
            "snapshot_output_written": True,
            "write_scope": "no review_store, formal_db, scheduler, or history mutation",
            "formal_credit_authorized": False,
            "production_scheduler_allowed": False,
        },
        "payload": payload,
        "diagnostics": list(dict.fromkeys(diagnostics)),
    }
    serialized = json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with resolved_output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)
    return envelope


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export one read-only Evidence Review dashboard page from an explicit working-copy DB."
    )
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--period-start")
    parser.add_argument("--period-end")
    parser.add_argument("--limit", type=int, default=MAX_PAGE_SIZE)
    parser.add_argument("--cursor-period-end")
    parser.add_argument("--cursor-period-start")
    parser.add_argument("--cursor-review-id")
    args = parser.parse_args(argv)
    cursor_values = (
        args.cursor_period_end,
        args.cursor_period_start,
        args.cursor_review_id,
    )
    if any(cursor_values) and not all(cursor_values):
        parser.error("all three cursor fields are required together")
    args.cursor = (
        EvidenceOperationsHistoryCursor(
            period_end=str(args.cursor_period_end),
            period_start=str(args.cursor_period_start),
            review_id=str(args.cursor_review_id),
        )
        if all(cursor_values)
        else None
    )
    return args


def main(argv: list[str] | None = None) -> int:
    configure_utf8_console()
    args = parse_args(argv)
    build_snapshot(
        db_path=args.db_path,
        output_path=args.output_json,
        period_start=args.period_start,
        period_end=args.period_end,
        limit=args.limit,
        cursor=args.cursor,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
