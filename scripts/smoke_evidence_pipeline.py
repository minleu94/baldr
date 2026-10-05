from __future__ import annotations

import argparse
from collections.abc import Callable
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.evidence_capture_service import EvidenceCaptureService
from app_module.evidence_event_importer_dtos import EvidenceCaptureRequest
from app_module.evidence_event_importers import RecommendationEvidenceImporter
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.evidence_event_service import EvidenceEventService
from app_module.forward_outcome_context import build_official_maturity_calendar
from app_module.forward_performance_service import ForwardPerformanceService
from app_module.paper_portfolio_time import TAIWAN_MARKET_TIMEZONE
from app_module.saved_recommendation_queries import build_recommendation_execution_queries
from data_module.config import TWStockConfig


def _enum_value(value: Any) -> str:
    raw_value = getattr(value, "value", value)
    return str(raw_value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an evidence pipeline smoke on an isolated SQLite database.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--recommendation-result-id", required=True)
    parser.add_argument("--decision-date", required=True)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--windows", default="5,10,20,60")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run. This is the default without --confirm.")
    parser.add_argument("--confirm", action="store_true", help="Write to the selected DB. Without this flag, no events or outcomes are written.")
    parser.add_argument("--json-output", action="store_true", help="Emit JSON summary. JSON is the default output.")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    return parser


def _parse_windows(value: str) -> tuple[int, ...]:
    windows = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not windows:
        raise ValueError("--windows must include at least one integer")
    return windows


def _config_from_args(args: argparse.Namespace) -> TWStockConfig:
    kwargs: dict[str, Any] = {}
    if args.data_root is not None:
        kwargs["data_root"] = args.data_root
    if args.output_root is not None:
        kwargs["output_root"] = args.output_root
    canonical_config = TWStockConfig()
    config = TWStockConfig(**kwargs)
    selected_db = Path(args.db_path).expanduser()
    if _same_database_path(selected_db, Path(canonical_config.db_file)):
        raise ValueError(
            "smoke evidence pipeline refuses the configured canonical database; "
            "provide an isolated --db-path"
        )
    config.db_file = selected_db
    config.db_file.parent.mkdir(parents=True, exist_ok=True)
    return config


def _same_database_path(candidate: Path, canonical: Path) -> bool:
    try:
        candidate_resolved = candidate.resolve(strict=False)
        canonical_resolved = canonical.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("database path cannot be resolved safely") from exc
    if os.path.normcase(str(candidate_resolved)) == os.path.normcase(str(canonical_resolved)):
        return True
    try:
        return candidate_resolved.exists() and canonical_resolved.exists() and os.path.samefile(
            candidate_resolved,
            canonical_resolved,
        )
    except OSError:
        return False


def _sample_events(repository: EvidenceEventRepository, *, limit: int = 5) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "event_id": event.event_id,
            "event_hash": event.event_hash,
            "event_type": _enum_value(event.event_type),
            "symbol": event.symbol,
            "source_id": event.source_id,
        }
        for event in repository.list_events(limit=limit)
    )


def _sample_outcomes(repository: EvidenceEventRepository, *, limit: int = 5) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "outcome_id": outcome.outcome_id,
            "event_id": outcome.event_id,
            "window_days": outcome.window_days,
            "outcome_status": _enum_value(outcome.outcome_status),
            "return_basis": outcome.return_basis,
            "forward_return_bp": outcome.forward_return_bp,
            "benchmark_excess_bp": outcome.benchmark_excess_bp,
            "industry_excess_bp": outcome.industry_excess_bp,
        }
        for outcome in repository.list_outcomes()[:limit]
    )


def _quality_counts(repository: EvidenceEventRepository) -> dict[str, int]:
    event_counts = Counter(_enum_value(event.data_quality) for event in repository.list_events())
    outcome_counts = Counter(_enum_value(outcome.data_quality) for outcome in repository.list_outcomes())
    combined = event_counts + outcome_counts
    return dict(sorted(combined.items()))


def run_smoke(
    args: argparse.Namespace,
    *,
    _calendar_cache_path: str | Path | None = None,
    _temporary_closure_path: str | Path | None = None,
    _now_provider: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    config = _config_from_args(args)
    windows = _parse_windows(args.windows)
    dry_run = bool(args.dry_run or not args.confirm)
    repository = EvidenceEventRepository(config, read_only=dry_run)
    capture_service = EvidenceCaptureService(
        EvidenceEventService(repository),
        {
            "recommendation": RecommendationEvidenceImporter(
                build_recommendation_execution_queries(config)
            ),
        },
    )
    capture = capture_service.capture(
        EvidenceCaptureRequest(
            source="recommendation",
            decision_date=args.decision_date,
            start_date=args.start_date,
            end_date=args.end_date,
            result_id=args.recommendation_result_id,
            limit=args.limit,
            dry_run=dry_run,
            confirm=bool(args.confirm),
        )
    )

    outcome_summary = None
    if not dry_run:
        invocation_at = (
            _now_provider()
            if _now_provider is not None
            else datetime.now(TAIWAN_MARKET_TIMEZONE)
        )
        maturity_calendar = build_official_maturity_calendar(
            config=config,
            observed_at=invocation_at,
            calendar_cache_path=_calendar_cache_path,
            temporary_closure_path=_temporary_closure_path,
        )
        outcome_summary = ForwardPerformanceService(
            config,
            repository,
            maturity_calendar=maturity_calendar,
        ).calculate(
            windows=windows,
            dry_run=False,
            decision_date=args.decision_date,
            start_date=args.start_date,
            end_date=args.end_date,
            event_type="recommendation_included",
            limit=args.limit,
            data_as_of_date=invocation_at.date().isoformat(),
        )

    outcomes = repository.list_outcomes()
    outcome_status_counts = dict(sorted(Counter(_enum_value(item.outcome_status) for item in outcomes).items()))
    event_type_counts = (
        capture.event_type_counts
        if dry_run
        else dict(sorted(Counter(_enum_value(event.event_type) for event in repository.list_events()).items()))
    )
    summary = {
        "dry_run": dry_run,
        "db_path": str(config.db_file),
        "source": "recommendation",
        "recommendation_result_id": args.recommendation_result_id,
        "decision_date": args.decision_date,
        "events_seen": capture.events_seen,
        "events_inserted": capture.events_inserted,
        "events_skipped_duplicate": capture.events_skipped_duplicate,
        "events_failed": capture.events_failed,
        "outcomes_attempted": 0 if outcome_summary is None else outcome_summary.events_ready * len(windows),
        "outcomes_created": 0 if outcome_summary is None else outcome_summary.outcomes_created,
        "outcomes_updated": 0 if outcome_summary is None else outcome_summary.outcomes_updated,
        "outcomes_pending": 0 if outcome_summary is None else outcome_summary.pending_insufficient_future_data,
        "missing_event_price": 0 if outcome_summary is None else outcome_summary.missing_event_price,
        "missing_outcome_price": 0 if outcome_summary is None else outcome_summary.missing_outcome_price,
        "missing_benchmark": 0 if outcome_summary is None else outcome_summary.missing_benchmark,
        "missing_industry_benchmark": 0 if outcome_summary is None else outcome_summary.missing_industry_benchmark,
        "outcomes_blocked_time_contract": (
            0 if outcome_summary is None else outcome_summary.blocked_time_contract_count
        ),
        "warnings_count": capture.warnings_count + (0 if outcome_summary is None else outcome_summary.warnings_count),
        "event_type_counts": dict(sorted(event_type_counts.items())),
        "outcome_status_counts": outcome_status_counts,
        "quality_counts": capture.quality_counts if dry_run else _quality_counts(repository),
        "sample_events": list(capture.sample_events if dry_run else _sample_events(repository)),
        "sample_outcomes": list(_sample_outcomes(repository)),
        "return_basis": "close_to_close_event_date",
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        summary = run_smoke(args)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

