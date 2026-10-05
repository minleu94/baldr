from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.evidence_capture_service import EvidenceCaptureService
from app_module.evidence_event_importer_dtos import EvidenceCaptureRequest
from app_module.evidence_event_importers import (
    MissingSnapshotEvidenceImporter,
    PortfolioAlertEvidenceImporter,
    RecommendationEvidenceImporter,
    RiskPromptEvidenceImporter,
    WatchlistTriggerEvidenceImporter,
)
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.evidence_event_service import EvidenceEventService
from app_module.decision_desk_snapshot_repository import DecisionDeskSnapshotRepository
from app_module.forward_outcome_context import resolve_canonical_evidence_release_root
from app_module.saved_recommendation_queries import build_recommendation_execution_queries
from data_module.config import TWStockConfig
from data_module.ml_storage_capacity import (
    acquire_heavy_chain_reservation,
    heavy_chain_lock_path,
    release_heavy_chain_reservation,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture evidence events from persisted or DTO sources.")
    parser.add_argument(
        "--source",
        choices=("recommendation", "watchlist-trigger", "portfolio-alert", "risk-prompt", "all"),
        required=True,
    )
    parser.add_argument("--decision-date")
    parser.add_argument(
        "--as-of",
        "--as-of-date",
        dest="as_of",
        help="Explicit source as-of date; date-only legacy callers remain temporally unproven.",
    )
    parser.add_argument(
        "--decision-at",
        help="Explicit aware decision/evaluation timestamp; after-close values remain research-only.",
    )
    parser.add_argument(
        "--captured-at",
        help="Explicit aware capture timestamp.",
    )
    parser.add_argument(
        "--capture-mode",
        help="Explicit research capture mode, e.g. eod_research.",
    )
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--result-id")
    parser.add_argument("--symbol")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run. This is also the default.")
    parser.add_argument("--confirm", action="store_true", help="Write events. Without this flag no DB write occurs.")
    parser.add_argument("--db-path")
    parser.add_argument("--json-output", action="store_true", help="Emit JSON summary. JSON is the default output.")
    parser.add_argument("--data-root")
    parser.add_argument("--output-root")
    return parser


def _config_from_args(args: argparse.Namespace) -> TWStockConfig:
    kwargs: dict[str, Any] = {}
    if args.data_root:
        kwargs["data_root"] = Path(args.data_root)
    if args.output_root:
        kwargs["output_root"] = Path(args.output_root)
    config = TWStockConfig(**kwargs)
    if args.db_path:
        config.db_file = Path(args.db_path)
        config.db_file.parent.mkdir(parents=True, exist_ok=True)
    return config


def _parse_aware_datetime(value: str | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"--{field_name.replace('_', '-')} 必須是含時區 ISO timestamp")
    return parsed.astimezone(TAIPEI)


class _DecisionDeskSnapshotSectionProvider:
    def __init__(self, stored_snapshot, section_name: str) -> None:
        self.stored_snapshot = stored_snapshot
        self.section_name = section_name
        self.snapshot_id = stored_snapshot.snapshot_id
        self.metadata = {
            "decision_desk_snapshot_id": stored_snapshot.snapshot_id,
            "decision_desk_snapshot_hash": stored_snapshot.snapshot_hash,
            "decision_desk_snapshot_source": "durable_snapshot",
            "decision_desk_snapshot_generated_at": (
                stored_snapshot.metadata_json.get("generated_at")
                or stored_snapshot.created_at
                or None
            ),
        }

    def build_snapshot(self, as_of_date):
        snapshot = self.stored_snapshot.to_decision_desk_snapshot()
        if self.section_name == "watchlist-trigger":
            return snapshot.watchlist_triggers
        if self.section_name == "portfolio-alert":
            return snapshot.portfolio_alerts
        if self.section_name == "risk-prompt":
            return snapshot.risk_prompts
        raise ValueError(f"unsupported decision desk snapshot section: {self.section_name}")


def _decision_date_for_snapshot(args: argparse.Namespace) -> str:
    if args.decision_date:
        return str(args.decision_date)[:10]
    if args.as_of:
        return str(args.as_of)[:10]
    return datetime.now(TAIPEI).date().isoformat()


def _decision_desk_importers(
    config: TWStockConfig,
    decision_date: str,
    *,
    read_only: bool,
):
    repository = DecisionDeskSnapshotRepository(config, read_only=read_only)
    stored = repository.latest_before_or_on(decision_date) if decision_date else None
    if stored is None:
        reason = "durable decision desk snapshot not found; run capture_decision_desk_snapshot.py first"
        return {
            "watchlist-trigger": MissingSnapshotEvidenceImporter("watchlist-trigger", reason),
            "portfolio-alert": MissingSnapshotEvidenceImporter("portfolio-alert", reason),
            "risk-prompt": MissingSnapshotEvidenceImporter("risk-prompt", reason),
        }
    return {
        "watchlist-trigger": WatchlistTriggerEvidenceImporter(
            _DecisionDeskSnapshotSectionProvider(stored, "watchlist-trigger")
        ),
        "portfolio-alert": PortfolioAlertEvidenceImporter(
            _DecisionDeskSnapshotSectionProvider(stored, "portfolio-alert")
        ),
        "risk-prompt": RiskPromptEvidenceImporter(
            _DecisionDeskSnapshotSectionProvider(stored, "risk-prompt")
        ),
    }


def _run_capture(args: argparse.Namespace, config: TWStockConfig, *, effective_dry_run: bool) -> int:

    decision_at = _parse_aware_datetime(args.decision_at, field_name="decision_at")
    captured_at = _parse_aware_datetime(args.captured_at, field_name="captured_at")
    if decision_at is not None and captured_at is not None and captured_at < decision_at:
        raise ValueError("captured_at 不得早於 decision_at")

    repository = EvidenceEventRepository(config, read_only=effective_dry_run)
    event_service = EvidenceEventService(repository)
    recommendation_queries = build_recommendation_execution_queries(config)
    ddd_importers = _decision_desk_importers(
        config,
        _decision_date_for_snapshot(args),
        read_only=effective_dry_run,
    )
    capture_service = EvidenceCaptureService(
        event_service,
        {
            "recommendation": RecommendationEvidenceImporter(recommendation_queries),
            **ddd_importers,
        },
    )
    resolved_decision_date = args.decision_date or args.as_of
    request = EvidenceCaptureRequest(
        source=args.source,
        decision_date=resolved_decision_date,
        start_date=args.start_date,
        end_date=args.end_date,
        result_id=args.result_id,
        symbol=args.symbol,
        limit=args.limit,
        dry_run=effective_dry_run,
        confirm=bool(args.confirm),
        decision_at=decision_at,
        as_of=args.as_of,
        captured_at=captured_at,
        capture_mode=args.capture_mode,
    )
    summary = capture_service.capture(request)
    print(json.dumps(summary.to_dict(), ensure_ascii=True, sort_keys=True, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = _config_from_args(args)
    effective_dry_run = bool(args.dry_run or not args.confirm)
    reservation = None
    if not effective_dry_run:
        canonical_config = TWStockConfig()
        release_root = resolve_canonical_evidence_release_root(
            canonical_config=canonical_config,
            db_path=config.db_file,
        )
        if release_root is not None:
            lock_path = heavy_chain_lock_path(release_root)
            reservation = acquire_heavy_chain_reservation(lock_path)
            if reservation is None:
                print(
                    json.dumps(
                        {
                            "status": "blocked_writer_busy",
                            "db_path": str(config.db_file.expanduser().resolve()),
                            "lock_path": str(lock_path),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 2
    try:
        return _run_capture(args, config, effective_dry_run=effective_dry_run)
    finally:
        if reservation is not None:
            release_heavy_chain_reservation(reservation)


if __name__ == "__main__":
    raise SystemExit(main())
