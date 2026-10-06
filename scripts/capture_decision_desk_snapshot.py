from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.decision_desk_dtos import (
    DecisionDeskQuality,
    DecisionDeskSnapshot,
    MarketBreadthSummary,
    MarketRegimeSummary,
    PortfolioAlertSummary,
    RelativeStrengthLiquiditySummary,
    SectorRotationSummary,
    DecisionDeskRiskPromptSummary,
    WatchlistTriggerSummary,
)
from app_module.decision_desk_builder_factory import build_service_backed_decision_desk_snapshot_builder
from app_module.decision_desk_snapshot_repository import DecisionDeskSnapshotRepository
from app_module.decision_desk_snapshot_storage_dtos import build_stored_decision_desk_snapshot
from app_module.evidence_event_importer_dtos import (
    EvidenceCaptureRequest,
    capture_context_identity,
    capture_context_is_valid,
)
from app_module.paper_portfolio_time import taiwan_market_today
from data_module.config import TWStockConfig


SECTION_NAMES = (
    "market_regime",
    "market_breadth",
    "sector_rotation",
    "relative_strength_liquidity",
    "watchlist_trigger",
    "portfolio_alert",
    "risk_prompt",
)
TAIPEI = ZoneInfo("Asia/Taipei")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture a durable Daily Decision Desk snapshot.")
    parser.add_argument("--decision-date", required=True)
    parser.add_argument(
        "--as-of",
        "--as-of-date",
        dest="as_of",
        help="Explicit source as-of date. Omit for legacy date-only capture.",
    )
    parser.add_argument(
        "--decision-at",
        help="Explicit aware decision/evaluation timestamp; after-close values remain research-only.",
    )
    parser.add_argument(
        "--captured-at",
        help="Explicit aware capture timestamp. No timestamp is inferred for legacy date-only calls.",
    )
    parser.add_argument(
        "--capture-mode",
        help="Explicit research capture mode, e.g. eod_research.",
    )
    parser.add_argument("--db-path")
    parser.add_argument("--dry-run", action="store_true", help="Preview only. This is also the default.")
    parser.add_argument("--confirm", action="store_true", help="Persist the snapshot.")
    parser.add_argument("--json-output", action="store_true", help="Emit JSON summary. JSON is the default output.")
    parser.add_argument("--limit-sections", help="Comma-separated section names to include.")
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


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _parse_aware_datetime(value: str | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"--{field_name.replace('_', '-')} 必須是含時區 ISO timestamp")
    return parsed.astimezone(TAIPEI)


def _limited_sections(value: str | None) -> set[str] | None:
    if not value:
        return None
    return {item.strip() for item in value.split(",") if item.strip()}


def _limit_snapshot(snapshot: DecisionDeskSnapshot, included: set[str] | None) -> DecisionDeskSnapshot:
    if included is None:
        return snapshot
    as_of = snapshot.as_of_date
    return DecisionDeskSnapshot(
        as_of_date=snapshot.as_of_date,
        generated_at=snapshot.generated_at,
        schema_version=snapshot.schema_version,
        overall_quality=DecisionDeskQuality.DEGRADED,
        warnings=tuple(snapshot.warnings) + tuple(
            f"section_limited_out:{section}" for section in SECTION_NAMES if section not in included
        ),
        market_regime=snapshot.market_regime
        if "market_regime" in included
        else MarketRegimeSummary(as_of, DecisionDeskQuality.MISSING, ("section_limited_out",)),
        market_breadth=snapshot.market_breadth
        if "market_breadth" in included
        else MarketBreadthSummary(as_of, DecisionDeskQuality.MISSING, ("section_limited_out",)),
        sector_rotation=snapshot.sector_rotation
        if "sector_rotation" in included
        else SectorRotationSummary(as_of, DecisionDeskQuality.MISSING, ("section_limited_out",)),
        relative_strength_liquidity=snapshot.relative_strength_liquidity
        if "relative_strength_liquidity" in included
        else RelativeStrengthLiquiditySummary(as_of, DecisionDeskQuality.MISSING, ("section_limited_out",)),
        watchlist_triggers=snapshot.watchlist_triggers
        if "watchlist_trigger" in included
        else WatchlistTriggerSummary(as_of, DecisionDeskQuality.MISSING, ("section_limited_out",), trigger_count=0),
        portfolio_alerts=snapshot.portfolio_alerts
        if "portfolio_alert" in included
        else PortfolioAlertSummary(as_of, DecisionDeskQuality.MISSING, ("section_limited_out",), alert_count=0),
        risk_prompts=snapshot.risk_prompts
        if "risk_prompt" in included
        else DecisionDeskRiskPromptSummary(as_of, DecisionDeskQuality.MISSING, ("section_limited_out",)),
    )


def _section_quality(payload: dict[str, Any]) -> str:
    return str(payload.get("quality") or "missing")


def _summary(
    snapshot: DecisionDeskSnapshot,
    stored: Any,
    *,
    dry_run: bool,
    saved: bool,
    skipped_duplicate: bool,
    temporal: dict[str, Any],
) -> dict[str, Any]:
    section_payloads = {
        "market_regime": stored.market_regime_json,
        "market_breadth": stored.market_breadth_json,
        "sector_rotation": stored.sector_rotation_json,
        "relative_strength_liquidity": stored.relative_strength_liquidity_json,
        "watchlist_trigger": stored.watchlist_trigger_json,
        "portfolio_alert": stored.portfolio_alert_json,
        "risk_prompt": stored.risk_prompt_json,
    }
    sections_missing = [name for name, payload in section_payloads.items() if _section_quality(payload) == "missing"]
    sections_seen = [name for name in section_payloads if name not in sections_missing]
    return {
        "dry_run": dry_run,
        "decision_date": stored.decision_date,
        "snapshot_id": stored.snapshot_id,
        "snapshot_hash": stored.snapshot_hash,
        "sections_seen": sections_seen,
        "sections_missing": sections_missing,
        "quality": snapshot.overall_quality.value,
        "warnings_count": len(snapshot.warnings),
        "event_candidate_counts": {
            "watchlist_trigger": len(snapshot.watchlist_triggers.triggered_codes),
            "portfolio_alert": len(snapshot.portfolio_alerts.attributions),
            "risk_prompt": len(snapshot.risk_prompts.prompts),
        },
        "saved": saved,
        "skipped_duplicate": skipped_duplicate,
        "persisted_capture_context": (
            dict(stored.metadata_json.get("capture_context"))
            if not dry_run and isinstance(stored.metadata_json.get("capture_context"), dict)
            else None
        ),
        **temporal,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = _config_from_args(args)
    decision_date = _parse_date(args.decision_date)
    as_of_date = _parse_date(args.as_of or args.decision_date)
    today = taiwan_market_today()
    if decision_date > today:
        raise ValueError(
            "decision_date cannot be future-dated: "
            f"{decision_date.isoformat()} (today={today.isoformat()})"
        )
    if as_of_date > today:
        raise ValueError(
            "as_of cannot be future-dated: "
            f"{as_of_date.isoformat()} (today={today.isoformat()})"
        )
    dry_run = bool(args.dry_run or not args.confirm)
    decision_at = _parse_aware_datetime(args.decision_at, field_name="decision_at")
    captured_at = _parse_aware_datetime(args.captured_at, field_name="captured_at")
    if decision_at is not None and captured_at is not None and captured_at < decision_at:
        raise ValueError("captured_at 不得早於 decision_at")
    capture_request = EvidenceCaptureRequest(
        source="decision-desk",
        decision_date=decision_date,
        as_of=args.as_of,
        decision_at=decision_at,
        captured_at=captured_at,
        capture_mode=args.capture_mode,
    )
    capture_clock = captured_at or decision_at or datetime.now(TAIPEI)
    capture_metadata = (
        {"capture_context": capture_request.capture_context}
        if capture_request.capture_context is not None
        else None
    )

    builder = build_service_backed_decision_desk_snapshot_builder(
        config,
        clock=lambda: capture_clock,
    )
    snapshot = builder.build_snapshot(as_of_date)
    snapshot = _limit_snapshot(snapshot, _limited_sections(args.limit_sections))
    stored = build_stored_decision_desk_snapshot(
        snapshot,
        decision_date=decision_date,
        metadata=capture_metadata,
    )

    saved = False
    skipped_duplicate = False
    if not dry_run:
        repository = DecisionDeskSnapshotRepository(config)
        skipped_duplicate = repository.get_snapshot_by_hash(stored.snapshot_hash) is not None
        stored = repository.save_snapshot(stored)
        persisted_context = stored.metadata_json.get("capture_context")
        expected_context = capture_request.capture_context
        if expected_context is not None and persisted_context is None:
            raise ValueError("persisted snapshot capture_context missing")
        if persisted_context is not None and not capture_context_is_valid(persisted_context):
            raise ValueError("persisted snapshot capture_context hash mismatch")
        if (
            persisted_context is not None
            and expected_context is not None
            and capture_context_identity(persisted_context)
            != capture_context_identity(expected_context)
        ):
            raise ValueError("persisted snapshot capture_context identity mismatch")
        saved = not skipped_duplicate

    print(
        json.dumps(
            _summary(
                snapshot,
                stored,
                dry_run=dry_run,
                saved=saved,
                skipped_duplicate=skipped_duplicate,
                temporal=capture_request.temporal_summary,
            ),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
