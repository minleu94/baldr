"""Run one bounded daily recommendation-learning shadow cycle.

The command reads the configured SQLite source in ``mode=ro`` and writes only
versioned research/shadow artifacts under the dedicated recommendation-learning
shadow root.  A challenger is
frozen once, captured on each eligible day, and automatically evaluated from
all matching matured captures before the authority gate runs.  Historical
replay is training data only; it is never accepted as natural forward
evidence.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any, Mapping
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.daily_recommendation_learning_runner import (  # noqa: E402
    DailyRecommendationLearningRunner,
)
from app_module.recommendation_learning_paths import (  # noqa: E402
    RecommendationLearningPathError,
    resolve_recommendation_learning_output_root,
)
from data_module.config import TWStockConfig  # noqa: E402
from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider  # noqa: E402
from data_module.official_trading_calendar import OfficialTradingCalendar  # noqa: E402
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY  # noqa: E402
from ml_module.historical_feature_builder import HistoricalFeatureBuilder  # noqa: E402
from ml_module.recommendation_calibration_authority import (  # noqa: E402
    RecommendationPromotionPolicy,
)
from ml_module.recommendation_calibration_evidence import (  # noqa: E402
    ActiveModelPredictionCaptureService,
    RecommendationPredictionCaptureInput,
    RecommendationPredictionCaptureService,
    _verify_capture_bundle_payload,
    _verify_capture_document,
    _verify_capture_payload,
)
from ml_module.recommendation_calibration_training import (  # noqa: E402
    AFTER_COST_NULL_BENCHMARK_BASELINE_ID,
    AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP,
    RecommendationCalibrationTrainingConfig,
    RecommendationCalibrationSample,
)
from ml_module.recommendation_historical_replay import (  # noqa: E402
    RecommendationHistoricalReplayConfig,
    RecommendationHistoricalReplayService,
)


TAIPEI = ZoneInfo("Asia/Taipei")
from ml_module.recommendation_natural_outcome_service import (  # noqa: E402
    RecommendationNaturalOutcomeService,
    verify_active_model_evidence_payload,
)
from ml_module.recommendation_probability_transform import (  # noqa: E402
    NULL_BENCHMARK_BASELINE_ID,
    NULL_BENCHMARK_PROBABILITY_BP,
)


def _taipei_now() -> datetime:
    """Return the scheduler clock; tests may replace this external clock only."""

    return datetime.now(TAIPEI)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--source-db", type=Path, default=None)
    parser.add_argument(
        "--symbols",
        default=None,
        help=(
            "Comma-separated explicit symbols. If omitted, reuse the same-day "
            "scheduled recommendation snapshot; no universe discovery is performed."
        ),
    )
    parser.add_argument("--history-start-date", default="2014-01-01")
    parser.add_argument("--replay-start-date", default=None)
    parser.add_argument("--replay-end-date", default=None)
    parser.add_argument(
        "--decision-date",
        default=None,
        help="Daily orchestration receipt date (YYYY-MM-DD); defaults to the Asia/Taipei clock.",
    )
    parser.add_argument("--training-as-of", default=None)
    parser.add_argument("--fixed-round-trip-cost-bp", type=int, default=50)
    parser.add_argument("--max-decision-dates", type=int, default=100)
    parser.add_argument(
        "--replay-selection-policy",
        choices=("chronological_first_eligible_date", "latest_eligible_dates"),
        default="latest_eligible_dates",
        help="Bounded replay window policy; scheduled runs use the latest dates so new data can enter.",
    )
    # Kept as a migration-compatible input, but never used as the automatic
    # evidence source.  The daily path always scans immutable captures below.
    parser.add_argument("--natural-evidence-receipt", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--data-status", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--outcome-status", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--drift-status", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--emergency-rollback", action="store_true")
    parser.add_argument(
        "--capture-current",
        dest="capture_current",
        action="store_true",
        default=True,
        help="Capture today's live feature vector; never creates labels (default: enabled).",
    )
    parser.add_argument(
        "--skip-capture-current",
        dest="capture_current",
        action="store_false",
        help="Do not create today's forward capture.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    config_kwargs: dict[str, Any] = {}
    if args.data_root is not None:
        config_kwargs["data_root"] = args.data_root
    config = TWStockConfig(**config_kwargs)
    try:
        learning_output_root = resolve_recommendation_learning_output_root(
            data_root=config.data_root,
            explicit_output_root=args.output_root,
        )
    except RecommendationLearningPathError as exc:
        print(
            json.dumps(
                {
                    "schema_version": "daily-recommendation-learning-cli-result.v3",
                    "status": "failed",
                    "decision": "retain_current",
                    "decision_reason": "recommendation_learning_output_root_invalid",
                    "data_root": str(config.data_root.resolve()),
                    "error": str(exc),
                    "formal_order_allowed": False,
                    "shadow_only": True,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    source_db = args.source_db or config.db_file
    decision_day = (
        date.fromisoformat(str(args.decision_date)[:10])
        if args.decision_date
        else _taipei_now().date()
    )
    try:
        symbols, symbol_source = _resolve_symbols(
            output_root=config.output_root,
            explicit_symbols=args.symbols,
            decision_date=decision_day,
        )
    except ValueError as exc:
        runner = _build_runner(
            learning_output_root,
            args.fixed_round_trip_cost_bp,
            data_root=config.data_root,
        )
        dependencies = _dependency_failure(
            reason=f"symbol_cohort_preflight_failed:{type(exc).__name__}",
            data_status="failed",
            outcome_status="failed",
            drift_status="not_checked",
        )
        run_result = runner.run(
            decision_date=decision_day.isoformat(),
            samples=(),
            natural_evidence=None,
            data_dependency_status="failed",
            outcome_dependency_status="failed",
            drift_status="not_checked",
            emergency_rollback=True,
        )
        print(
            json.dumps(
                _cli_payload(
                    output_root=learning_output_root,
                    decision_day=decision_day,
                    symbols=(),
                    symbol_source="unresolved",
                    replay_result=None,
                    manifest_path=None,
                    dependencies=dependencies,
                    run_result=run_result,
                    natural_result={"status": "not_run", "reason": "symbol_cohort_preflight_failed"},
                    active_natural_result={"status": "not_run", "reason": "symbol_cohort_preflight_failed"},
                    live_capture={"status": "not_run"},
                    error=f"{type(exc).__name__}: {exc}",
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    replay_start_date = (
        str(args.replay_start_date)[:10]
        if args.replay_start_date
        else (decision_day - timedelta(days=max(730, args.max_decision_dates * 4))).isoformat()
    )
    replay_end_date = str(args.replay_end_date)[:10] if args.replay_end_date else decision_day.isoformat()
    training_as_of = (
        date.fromisoformat(str(args.training_as_of)[:10]).isoformat()
        if args.training_as_of
        else decision_day.isoformat()
    )
    replay_config = RecommendationHistoricalReplayConfig(
        history_start_date=args.history_start_date,
        replay_start_date=replay_start_date,
        replay_end_date=replay_end_date,
        symbols=symbols,
        fixed_round_trip_cost_bp=args.fixed_round_trip_cost_bp,
        max_decision_dates=args.max_decision_dates,
        selection_policy=args.replay_selection_policy,
    )
    runner = _build_runner(
        learning_output_root,
        args.fixed_round_trip_cost_bp,
        data_root=config.data_root,
    )
    if args.emergency_rollback:
        dependencies = _dependency_failure(
            reason="explicit_emergency_rollback_requested",
            data_status="failed",
            outcome_status="failed",
            drift_status="drifted",
        )
        run_result = runner.run(
            decision_date=decision_day.isoformat(),
            samples=(),
            natural_evidence=None,
            data_dependency_status=dependencies["data_status"],
            outcome_dependency_status=dependencies["outcome_status"],
            drift_status=dependencies["drift_status"],
            emergency_rollback=True,
        )
        print(
            json.dumps(
                _cli_payload(
                    output_root=learning_output_root,
                    decision_day=decision_day,
                    symbols=symbols,
                    symbol_source=symbol_source,
                    replay_result=None,
                    manifest_path=None,
                    dependencies=dependencies,
                    run_result=run_result,
                    natural_result={"status": "not_run", "reason": "explicit_emergency_rollback"},
                    active_natural_result={"status": "not_run", "reason": "explicit_emergency_rollback"},
                    live_capture={"status": "not_run"},
                    error=None,
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    try:
        provider = MLHistoricalSnapshotProvider(source_db)
        replay_result = RecommendationHistoricalReplayService(provider).build(replay_config)
        manifest_path = replay_result.persist(learning_output_root)
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        dependencies = _dependency_failure(
            reason=f"replay_or_source_preflight_failed:{type(exc).__name__}",
            data_status="failed",
            outcome_status="failed",
            drift_status="not_checked",
        )
        run_result = runner.run(
            decision_date=decision_day.isoformat(),
            samples=(),
            natural_evidence=None,
            data_dependency_status="failed",
            outcome_dependency_status="failed",
            drift_status="not_checked",
            emergency_rollback=True,
        )
        print(
            json.dumps(
                _cli_payload(
                    output_root=learning_output_root,
                    decision_day=decision_day,
                    symbols=symbols,
                    symbol_source=symbol_source,
                    replay_result=None,
                    manifest_path=None,
                    dependencies=dependencies,
                    run_result=run_result,
                    natural_result={"status": "not_run", "reason": "source_preflight_failed"},
                    active_natural_result={"status": "not_run", "reason": "source_preflight_failed"},
                    live_capture={"status": "not_run"},
                    error=f"{type(exc).__name__}: {exc}",
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2

    dependencies = _inspect_dependencies(
        provider=provider,
        output_root=learning_output_root,
        data_root=config.data_root,
        decision_date=decision_day,
        symbols=symbols,
        replay_source_fingerprint=replay_result.source_fingerprint,
        policy=RecommendationPromotionPolicy(),
    )
    challenger_payload = _read_challenger_pointer(learning_output_root)
    challenger_path = _load_frozen_challenger(learning_output_root)
    natural_training_samples = _load_natural_training_samples(
        output_root=learning_output_root,
        challenger_payload=challenger_payload,
        feature_count=len(CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids),
        fixed_round_trip_cost_bp=args.fixed_round_trip_cost_bp,
        training_as_of=training_as_of,
        data_root=config.data_root,
    )
    training_samples = _merge_samples(replay_result.samples, natural_training_samples)
    quality = {
        "training_data_eligible": replay_result.training_data_eligible,
        "forward_evidence_eligible": replay_result.forward_evidence_eligible,
        "formal_candidate_eligible": replay_result.formal_candidate_eligible,
        "candidate_blockers": replay_result.candidate_blockers,
        "replay_dataset_id": replay_result.dataset_id,
        "replay_dataset_manifest_path": str(manifest_path),
        "replay_dataset_hash": replay_result.dataset_hash,
        "source_disclosures": replay_result.source_disclosures,
        "lookahead_checks": replay_result.lookahead_checks,
        "dependency_check": dependencies,
        "probability_baseline_id": NULL_BENCHMARK_BASELINE_ID,
        "symbol_source": symbol_source,
        "natural_training_sample_count": len(natural_training_samples),
        "replay_selection_policy": replay_config.selection_policy,
    }
    emergency_from_preflight = _dependencies_require_emergency(dependencies)
    run_result = runner.run(
        decision_date=decision_day.isoformat(),
        samples=training_samples,
        natural_evidence=None,
        data_dependency_status=dependencies["data_status"],
        outcome_dependency_status=dependencies["outcome_status"],
        drift_status=dependencies["drift_status"],
        dataset_quality=quality,
        training_as_of=training_as_of,
        frozen_candidate_root=challenger_path,
        emergency_rollback=emergency_from_preflight,
    )
    if run_result.candidate_root and run_result.candidate_id:
        challenger_path = _ensure_challenger_pointer(
            output_root=learning_output_root,
            run_result=run_result,
            status="pending",
            natural_result=None,
            retrain_trigger=(
                "source_or_active_model_fault_recovery"
                if emergency_from_preflight
                else "new_candidate_frozen"
            ),
        )

    capture_result = _capture_current_if_requested(
        args=args,
        config=config,
        output_root=learning_output_root,
        source_db=source_db,
        provider=provider,
        symbols=symbols,
        run_result=run_result,
        replay_config=replay_config,
    )

    active_natural_result = _scan_active_model_evidence(
        output_root=learning_output_root,
        data_root=config.data_root,
        provider=provider,
        source_db=source_db,
        decision_date=decision_day,
        active_capture_result=capture_result.get("active_model_monitor")
        if isinstance(capture_result, Mapping)
        else None,
    )

    # The preflight check intentionally runs before today's capture/evidence
    # scan.  Re-read the active monitor after that scan so a newly matured
    # receipt can trigger the same day's fail-closed rollback.  A stale
    # preflight status must never delay a rollback until tomorrow.
    post_scan_active_performance = _inspect_active_model_performance(
        output_root=learning_output_root,
        data_root=config.data_root,
        decision_date=decision_day,
        policy=RecommendationPromotionPolicy(),
    )
    dependencies["model_performance"] = post_scan_active_performance
    dependencies["drift_status"] = str(
        post_scan_active_performance.get("status") or dependencies.get("drift_status", "not_checked")
    )
    post_scan_diagnostics = list(dependencies.get("diagnostics", ()))
    post_scan_diagnostics.extend(
        str(item)
        for item in post_scan_active_performance.get("diagnostics", ())
        if str(item).strip()
    )
    if str(active_natural_result.get("status")) == "failed":
        dependencies["drift_status"] = "failed"
        post_scan_diagnostics.append("active_model_natural_evidence_failed_fail_closed")
    dependencies["diagnostics"] = list(dict.fromkeys(post_scan_diagnostics))
    emergency_after_scan = _dependencies_require_emergency(dependencies)

    natural_result: Any = {
        "status": "not_run",
        "reason": "candidate_not_available",
        "matured_sample_count": 0,
        "evidence": None,
        "diagnostics": [],
    }
    automatic_evidence = None
    if run_result.candidate_id and run_result.candidate_root:
        evidence_path = (
            Path(learning_output_root)
            / "recommendation_learning"
            / "evidence"
            / run_result.candidate_id
            / f"{decision_day.isoformat()}.json"
        )
        natural_result = RecommendationNaturalOutcomeService(
            provider,
            evidence_db_path=source_db,
        ).scan_and_build_evidence(
            output_root=learning_output_root,
            evaluation_date=decision_day.isoformat(),
            output_path=evidence_path,
            candidate_id=run_result.candidate_id,
            candidate_freeze_hash=_candidate_freeze(run_result.candidate_root),
        ).to_dict()
        evidence_payload = natural_result.get("evidence")
        if isinstance(evidence_payload, Mapping):
            automatic_evidence = evidence_payload

    if automatic_evidence is not None or emergency_after_scan != emergency_from_preflight:
        run_result = runner.run(
            decision_date=decision_day.isoformat(),
            samples=training_samples,
            natural_evidence=automatic_evidence,
            data_dependency_status=dependencies["data_status"],
            outcome_dependency_status=dependencies["outcome_status"],
            drift_status=dependencies["drift_status"],
            dataset_quality=quality,
            training_as_of=training_as_of,
            frozen_candidate_root=run_result.candidate_root,
            emergency_rollback=emergency_after_scan,
        )
    if run_result.candidate_id and run_result.candidate_root:
        challenger_status = _challenger_status(run_result, natural_result)
        challenger_path = _ensure_challenger_pointer(
            output_root=learning_output_root,
            run_result=run_result,
            status=challenger_status,
            natural_result=natural_result,
            retrain_trigger=(
                "adopted_active_champion"
                if challenger_status == "active"
                else "retired_after_qualified_no_improvement"
                if challenger_status == "retired"
                else "awaiting_natural_maturity"
            ),
        )

    ignored_inputs = [
        name
        for name, value in (
            ("natural_evidence_receipt", args.natural_evidence_receipt),
            ("data_status", args.data_status),
            ("outcome_status", args.outcome_status),
            ("drift_status", args.drift_status),
        )
        if value is not None
    ]
    payload = _cli_payload(
        output_root=learning_output_root,
        decision_day=decision_day,
        symbols=symbols,
        symbol_source=symbol_source,
        replay_result=replay_result,
        manifest_path=manifest_path,
        dependencies=dependencies,
        run_result=run_result,
        natural_result=natural_result,
        active_natural_result=active_natural_result,
        live_capture=capture_result,
        error=None,
    )
    payload["natural_evidence_supplied"] = automatic_evidence is not None
    payload["ignored_caller_inputs"] = ignored_inputs
    payload["training_sample_count"] = len(training_samples)
    payload["natural_training_sample_count"] = len(natural_training_samples)
    payload["training_as_of"] = training_as_of
    _update_latest_status(
        run_result.latest_status_path,
        payload,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _build_runner(
    output_root: Path,
    fixed_round_trip_cost_bp: int,
    *,
    data_root: Path | None = None,
) -> DailyRecommendationLearningRunner:
    return DailyRecommendationLearningRunner(
        output_root=output_root,
        data_root=data_root,
        feature_names=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids,
        feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        training_config=RecommendationCalibrationTrainingConfig(),
    )


def _inspect_dependencies(
    *,
    provider: MLHistoricalSnapshotProvider,
    output_root: Path,
    data_root: Path | None,
    decision_date: date,
    symbols: tuple[str, ...],
    replay_source_fingerprint: str,
    policy: RecommendationPromotionPolicy,
) -> dict[str, Any]:
    """Perform actual read-only source checks; no caller status becomes truth."""

    diagnostics: list[str] = []
    data_status = "ready"
    outcome_status = "ready"
    drift_status = "clean"
    trading_dates: tuple[str, ...] = ()
    official_trading_day: bool | None = None
    calendar_reason = "not_checked"
    active_performance: dict[str, Any] = {
        "status": "pending",
        "reason": "active_model_performance_not_checked",
    }
    try:
        # The provider validates the complete whitelisted schema and checks
        # source stat stability.  A zero-row date is valid (weekend/holiday),
        # while a query/schema failure is a dependency failure.
        trading_dates = provider.list_trading_dates(
            start_date=decision_date.isoformat(),
            end_date=decision_date.isoformat(),
            symbols=symbols,
        )
        provider.load_forward_price_window(
            start_date=decision_date.isoformat(),
            end_date=decision_date.isoformat(),
            symbols=symbols,
        )
        official_trading_day, calendar_reason = _official_trading_day(
            provider=provider,
            decision_date=decision_date,
        )
        if official_trading_day is None:
            data_status = "failed"
            outcome_status = "failed"
            diagnostics.append(f"official_trading_calendar_unresolved:{calendar_reason}")
        elif official_trading_day is False:
            diagnostics.append(f"official_trading_calendar_closed:{calendar_reason}")
        elif not trading_dates:
            data_status = "failed"
            outcome_status = "failed"
            diagnostics.append("official_trading_day_but_explicit_symbol_rows_missing")
        if not replay_source_fingerprint:
            drift_status = "not_checked"
            diagnostics.append("replay_source_fingerprint_missing")
        else:
            diagnostics.append("source_schema_and_stat_stability_verified")
        if not trading_dates:
            diagnostics.append("non_trading_day_or_no_symbol_rows_live_capture_will_skip")
        active_performance = _inspect_active_model_performance(
            output_root=output_root,
            data_root=data_root,
            decision_date=decision_date,
            policy=policy,
        )
        drift_status = str(active_performance.get("status") or drift_status)
        diagnostics.extend(
            str(item)
            for item in active_performance.get("diagnostics", ())
            if str(item).strip()
        )
    except (OSError, RuntimeError, ValueError) as exc:
        data_status = "failed"
        outcome_status = "failed"
        drift_status = "not_checked"
        diagnostics.append(f"source_preflight_failed:{type(exc).__name__}")
    return {
        "data_status": data_status,
        "outcome_status": outcome_status,
        "drift_status": drift_status,
        "data_source": "MLHistoricalSnapshotProvider:sqlite_mode_ro_query_only",
        "drift_method": "active_model_natural_evidence_metrics_plus_source_health",
        "model_performance": active_performance,
        "decision_calendar": {
            "timezone": "Asia/Taipei",
            "official_calendar_is_trading_day": official_trading_day,
            "official_calendar_reason": calendar_reason,
            "is_trading_day_for_explicit_symbols": bool(trading_dates),
            "trading_dates": list(trading_dates),
        },
        "diagnostics": diagnostics,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _official_trading_day(
    *,
    provider: MLHistoricalSnapshotProvider,
    decision_date: date,
) -> tuple[bool | None, str]:
    """Use the existing official-calendar contract without network guessing."""

    calendar = OfficialTradingCalendar(db_path=provider.database_path)
    return calendar.is_official_trading_day(decision_date, allow_online_probe=False)


def _capture_current_if_requested(
    *,
    args: argparse.Namespace,
    config: TWStockConfig,
    output_root: Path,
    source_db: Path,
    provider: MLHistoricalSnapshotProvider,
    symbols: tuple[str, ...],
    run_result: Any,
    replay_config: RecommendationHistoricalReplayConfig,
) -> dict[str, Any]:
    if not args.capture_current:
        return {"status": "not_requested"}
    decision_day = (
        date.fromisoformat(str(args.decision_date)[:10])
        if args.decision_date
        else _taipei_now().date()
    )
    if decision_day != _taipei_now().date():
        return {
            "status": "skipped",
            "reason": "capture_current_requires_current_asia_taipei_date",
            "decision_timezone": "Asia/Taipei",
        }
    official_trading_day, calendar_reason = _official_trading_day(
        provider=provider,
        decision_date=decision_day,
    )
    if official_trading_day is None:
        return {
            "status": "failed",
            "reason": "official_trading_calendar_unresolved_fail_closed",
            "decision_timezone": "Asia/Taipei",
            "calendar_reason": calendar_reason,
            "trading_calendar_source": "OfficialTradingCalendar:local_market_index_or_official_cache",
        }
    if official_trading_day is False:
        return {
            "status": "skipped",
            "reason": "non_trading_day_official_calendar",
            "decision_timezone": "Asia/Taipei",
            "calendar_reason": calendar_reason,
            "trading_calendar_source": "OfficialTradingCalendar",
        }
    try:
        trading_dates = provider.list_trading_dates(
            start_date=decision_day.isoformat(),
            end_date=decision_day.isoformat(),
            symbols=symbols,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "status": "failed",
            "reason": f"live_capture_calendar_check_failed:{type(exc).__name__}",
            "decision_timezone": "Asia/Taipei",
        }
    if decision_day.isoformat() not in trading_dates:
        return {
            "status": "failed",
            "reason": "official_trading_day_explicit_symbol_rows_missing_fail_closed",
            "decision_timezone": "Asia/Taipei",
            "calendar_reason": calendar_reason,
            "trading_calendar_source": "OfficialTradingCalendar+MLHistoricalSnapshotProvider.daily_prices",
        }
    try:
        snapshot = provider.load(
            decision_date=decision_day.isoformat(),
            history_start_date=replay_config.history_start_date,
            symbols=symbols,
            industry_index_names=(),
        )
        feature_rows = HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY).compute(
            snapshot,
            industry_index_name_by_symbol={},
        )
        inputs = tuple(
            RecommendationPredictionCaptureInput(
                row_id=f"scheduled-live:{decision_day.isoformat()}:{row.symbol}",
                symbol=row.symbol,
                decision_date=decision_day.isoformat(),
                feature_as_of_date=row.feature_as_of_date,
                feature_available_date=row.available_date,
                feature_values=tuple(value for _, value in row.values),
                rule_probability_bp=NULL_BENCHMARK_PROBABILITY_BP,
                # This is only an independent after-cost null baseline.  It
                # does not assert that a future liquidity cost exists; when
                # the trained artifact has no after-cost model the effective
                # value remains None and the outcome path stays missing.
                rule_after_cost_probability_bp=AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP,
                rule_baseline_id=NULL_BENCHMARK_BASELINE_ID,
            )
            for row in feature_rows
        )
        if not inputs:
            return {
                "status": "skipped",
                "reason": "live_capture_feature_rows_missing",
                "candidate": {"status": "skipped", "reason": "live_capture_feature_rows_missing"},
                "active_model_monitor": {"status": "skipped", "reason": "live_capture_feature_rows_missing"},
            }
        capture_at = _taipei_now().isoformat(timespec="seconds")
        candidate_capture: dict[str, Any]
        if not run_result.candidate_root or not run_result.candidate_id:
            candidate_capture = {"status": "skipped", "reason": "candidate_not_available"}
        else:
            capture_path = (
                Path(output_root)
                / "recommendation_learning"
                / "captures"
                / decision_day.isoformat()
                / f"{run_result.candidate_id}.json"
            )
            if capture_path.is_file():
                try:
                    payload = json.loads(capture_path.read_text(encoding="utf-8"))
                    if isinstance(payload, dict):
                        _verify_capture_payload(payload)
                        candidate_capture = {
                            "status": "already_captured",
                            "capture_path": str(capture_path.resolve()),
                            "capture_id": payload.get("capture_id"),
                            "capture_hash": payload.get("capture_hash"),
                            "row_count": len(payload.get("rows", [])),
                            "capture_origin": payload.get("capture_origin"),
                        }
                    else:
                        raise ValueError("candidate capture is not an object")
                except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                    candidate_capture = {
                        "status": "failed",
                        "reason": "existing_capture_invalid_refusing_overwrite",
                    }
            else:
                capture = RecommendationPredictionCaptureService().capture(
                    candidate_root=run_result.candidate_root,
                    feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
                    feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
                    policy_hash=RecommendationPromotionPolicy().policy_hash,
                    decision_date=decision_day.isoformat(),
                    captured_at=capture_at,
                    inputs=inputs,
                    fixed_round_trip_cost_bp=args.fixed_round_trip_cost_bp,
                    data_root=config.data_root,
                    champion_pointer_path=(
                        Path(output_root)
                        / "recommendation_learning"
                        / "recommendation-calibration-active-pointer.json"
                    ),
                    capture_origin="scheduled_live",
                )
                capture.persist(capture_path)
                candidate_capture = {
                    "status": "captured",
                    "capture_path": str(capture_path.resolve()),
                    "capture_id": capture.capture_id,
                    "capture_hash": capture.capture_hash,
                    "row_count": len(capture.rows),
                    "capture_origin": capture.capture_origin,
                    "champion_kind": capture.probability_baseline_kind,
                    "champion_model_id": capture.champion_model_id,
                    "champion_candidate_id": capture.champion_candidate_id,
                    "probability_transform_id": capture.probability_transform_id,
                }
        active_capture = _capture_active_model_monitor(
            output_root=output_root,
            data_root=config.data_root,
            decision_date=decision_day,
            captured_at=capture_at,
            inputs=inputs,
            fixed_round_trip_cost_bp=args.fixed_round_trip_cost_bp,
        )
        statuses = {str(candidate_capture.get("status")), str(active_capture.get("status"))}
        if "captured" in statuses:
            overall_status = "captured"
        elif "already_captured" in statuses:
            overall_status = "already_captured"
        elif "failed" in statuses:
            overall_status = "failed"
        else:
            overall_status = "skipped"
        return {
            "status": overall_status,
            "candidate": candidate_capture,
            "active_model_monitor": active_capture,
            # Keep the old top-level fields for operators/scripts that only
            # inspect the challenger capture, while exposing the full pair.
            **candidate_capture,
        }
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "status": "failed",
            "reason": f"live_capture_failed:{type(exc).__name__}:{exc}",
        }


def _capture_active_model_monitor(
    *,
    output_root: Path,
    data_root: Path,
    decision_date: date,
    captured_at: str,
    inputs: tuple[RecommendationPredictionCaptureInput, ...],
    fixed_round_trip_cost_bp: int,
) -> dict[str, Any]:
    """Capture the actually delivered active output, even without a challenger."""

    pointer_path = Path(output_root).resolve() / "recommendation_learning" / "recommendation-calibration-active-pointer.json"
    pointer_status = "missing"
    try:
        pointer_payload = json.loads(pointer_path.read_text(encoding="utf-8"))
        if isinstance(pointer_payload, Mapping):
            pointer_status = str(pointer_payload.get("status") or "invalid")
    except (OSError, UnicodeError, json.JSONDecodeError):
        if pointer_path.is_file():
            return {
                "status": "failed",
                "reason": "active_pointer_invalid_json_fail_closed",
                "pointer_path": str(pointer_path),
            }
    if pointer_status != "active":
        return {"status": "skipped", "reason": "active_pointer_not_active"}
    try:
        from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer

        consumer = RecommendationCalibrationConsumer(
            pointer_path=pointer_path,
            feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
            feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
            data_root=data_root,
        )
        if consumer.reload(decision_date=decision_date.isoformat()) != "active":
            return {
                "status": "failed",
                "reason": "active_pointer_fault_fail_closed",
                "pointer_path": str(pointer_path),
                "consumer_blocker": str(getattr(consumer, "_blocker", "active_pointer_unavailable")),
            }
        identity = consumer.active_identity(decision_date=decision_date.isoformat())
        if not isinstance(identity, Mapping):
            raise ValueError("active identity unavailable")
        candidate_id = str(identity.get("candidate_id") or "")
        if not candidate_id:
            raise ValueError("active candidate identity missing")
        capture_path = (
            Path(output_root).resolve()
            / "recommendation_learning"
            / "active_captures"
            / decision_date.isoformat()
            / f"{candidate_id}.json"
        )
        if capture_path.is_file():
            from ml_module.recommendation_calibration_evidence import _verify_active_model_capture_payload

            payload = json.loads(capture_path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("active model capture is not an object")
            _verify_active_model_capture_payload(payload)
            return {
                "status": "already_captured",
                "capture_path": str(capture_path.resolve()),
                "capture_id": payload.get("capture_id"),
                "capture_hash": payload.get("capture_hash"),
                "row_count": len(payload.get("rows", [])),
                "active_candidate_id": payload.get("active_candidate_id"),
                "active_identity_hash": payload.get("active_identity_hash"),
                "capture_origin": payload.get("capture_origin"),
            }
        capture = ActiveModelPredictionCaptureService().capture(
            consumer=consumer,
            feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
            feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
            policy_hash=RecommendationPromotionPolicy().policy_hash,
            decision_date=decision_date.isoformat(),
            captured_at=captured_at,
            inputs=inputs,
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        )
        capture.persist(capture_path)
        return {
            "status": "captured",
            "capture_path": str(capture_path.resolve()),
            "capture_id": capture.capture_id,
            "capture_hash": capture.capture_hash,
            "row_count": len(capture.rows),
            "active_candidate_id": capture.active_candidate_id,
            "active_identity_hash": capture.active_identity_hash,
            "active_pointer_version": capture.active_pointer_version,
            "capture_origin": capture.capture_origin,
        }
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "failed",
            "reason": f"active_model_capture_failed:{type(exc).__name__}:{exc}",
            "pointer_path": str(pointer_path),
        }


def _scan_active_model_evidence(
    *,
    output_root: Path,
    data_root: Path,
    provider: MLHistoricalSnapshotProvider,
    source_db: Path,
    decision_date: date,
    active_capture_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Materialize the active model's matured monitoring window for this run."""

    pointer_path = Path(output_root).resolve() / "recommendation_learning" / "recommendation-calibration-active-pointer.json"
    try:
        pointer_payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        if pointer_path.is_file():
            return {
                "schema_version": "recommendation-natural-outcome-result.v1",
                "status": "failed",
                "reason": "active_pointer_invalid_json_fail_closed",
                "capture_path": str(Path(output_root).resolve() / "recommendation_learning" / "active_captures"),
                "capture_paths": [],
                "evaluation_date": decision_date.isoformat(),
                "matured_sample_count": 0,
                "evidence": None,
                "diagnostics": ["active_pointer_invalid_json_fail_closed"],
                "historical_replay_is_natural_evidence": False,
            }
        return {
            "schema_version": "recommendation-natural-outcome-result.v1",
            "status": "pending",
            "reason": "active_pointer_not_available",
            "capture_path": str(Path(output_root).resolve() / "recommendation_learning" / "active_captures"),
            "capture_paths": [],
            "evaluation_date": decision_date.isoformat(),
            "matured_sample_count": 0,
            "evidence": None,
            "diagnostics": ["active_pointer_not_available"],
            "historical_replay_is_natural_evidence": False,
        }
    if not isinstance(pointer_payload, Mapping) or pointer_payload.get("status") != "active":
        return {
            "schema_version": "recommendation-natural-outcome-result.v1",
            "status": "pending",
            "reason": "active_pointer_not_active",
            "capture_path": str(Path(output_root).resolve() / "recommendation_learning" / "active_captures"),
            "capture_paths": [],
            "evaluation_date": decision_date.isoformat(),
            "matured_sample_count": 0,
            "evidence": None,
            "diagnostics": ["active_pointer_not_active"],
            "historical_replay_is_natural_evidence": False,
        }
    try:
        from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer

        consumer = RecommendationCalibrationConsumer(
            pointer_path=pointer_path,
            feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
            feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
            data_root=data_root,
        )
        if consumer.reload(decision_date=decision_date.isoformat()) != "active":
            return {
                "schema_version": "recommendation-natural-outcome-result.v1",
                "status": "failed",
                "reason": "active_pointer_fault_fail_closed",
                "capture_path": str(Path(output_root).resolve() / "recommendation_learning" / "active_captures"),
                "capture_paths": [],
                "evaluation_date": decision_date.isoformat(),
                "matured_sample_count": 0,
                "evidence": None,
                "diagnostics": [str(getattr(consumer, "_blocker", "active_pointer_unavailable"))],
                "historical_replay_is_natural_evidence": False,
            }
        identity = consumer.active_identity(decision_date=decision_date.isoformat())
        if not isinstance(identity, Mapping):
            raise ValueError("active identity unavailable")
        active_candidate_id = str(identity.get("candidate_id") or "")
        active_identity_hash = _hash_payload_for_cli(identity)
        active_effective_date = str(pointer_payload.get("effective_date") or "")[:10]
        if not active_candidate_id or not active_identity_hash or not active_effective_date:
            raise ValueError("active pointer identity is incomplete")
        evidence_path = (
            Path(output_root).resolve()
            / "recommendation_learning"
            / "active_evidence"
            / active_candidate_id
            / f"{decision_date.isoformat()}.json"
        )
        result = RecommendationNaturalOutcomeService(
            provider,
            evidence_db_path=source_db,
        ).scan_and_build_active_model_evidence(
            output_root=output_root,
            evaluation_date=decision_date.isoformat(),
            output_path=evidence_path,
            active_candidate_id=active_candidate_id,
            active_identity_hash=active_identity_hash,
            active_effective_date=active_effective_date,
        )
        payload = result.to_dict()
        if active_capture_result:
            payload["capture_attempt"] = dict(active_capture_result)
        payload["active_identity_hash"] = active_identity_hash
        payload["active_candidate_id"] = active_candidate_id
        payload["monitoring_window_policy"] = "max(active_effective_date, evaluation_date-120 calendar days)"
        return payload
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schema_version": "recommendation-natural-outcome-result.v1",
            "status": "failed",
            "reason": f"active_model_evidence_failed:{type(exc).__name__}:{exc}",
            "capture_path": str(Path(output_root).resolve() / "recommendation_learning" / "active_captures"),
            "capture_paths": [],
            "evaluation_date": decision_date.isoformat(),
            "matured_sample_count": 0,
            "evidence": None,
            "diagnostics": ["active_model_evidence_failed_fail_closed"],
            "historical_replay_is_natural_evidence": False,
        }


def _hash_payload_for_cli(payload: Any) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_frozen_challenger(output_root: Path) -> Path | None:
    payload = _read_challenger_pointer(output_root)
    if not payload or payload.get("status") != "pending":
        return None
    candidate_root = str(payload.get("candidate_root") or "").strip()
    candidate_id = str(payload.get("candidate_id") or "").strip()
    if not candidate_root or not candidate_id:
        return None
    root = Path(candidate_root).resolve()
    try:
        metadata = json.loads((root / "candidate.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(metadata, dict) or str(metadata.get("candidate_id")) != candidate_id:
        return None
    return root


def _ensure_challenger_pointer(
    *,
    output_root: Path,
    run_result: Any,
    status: str,
    natural_result: Mapping[str, Any] | None = None,
    retrain_trigger: str = "",
) -> Path:
    root = Path(str(run_result.candidate_root)).resolve()
    metadata = json.loads((root / "candidate.json").read_text(encoding="utf-8"))
    pointer_path = Path(output_root).resolve() / "recommendation_learning" / "challenger" / "current.json"
    previous = _read_challenger_pointer(output_root) or {}
    evidence = natural_result.get("evidence") if isinstance(natural_result, Mapping) else None
    evidence_payload: Mapping[str, Any] = {}
    if isinstance(evidence, Mapping):
        evidence_path = str(evidence.get("receipt_path") or "")
        if evidence_path:
            try:
                loaded_evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
                if isinstance(loaded_evidence, Mapping):
                    evidence_payload = loaded_evidence
            except (OSError, UnicodeError, json.JSONDecodeError):
                evidence_payload = {}
    comparisons = evidence_payload.get("comparisons")
    evidence_dates = sorted(
        {
            str(row.get("capture_as_of_date"))[:10]
            for row in comparisons
            if isinstance(row, Mapping) and row.get("capture_as_of_date")
        }
        if isinstance(comparisons, list)
        else set()
    )
    previous_candidate = str(previous.get("candidate_id") or "")
    candidate_id = str(run_result.candidate_id)
    training_cycle = int(previous.get("training_cycle", 0) or 0)
    if candidate_id != previous_candidate:
        training_cycle += 1
    payload = {
        "schema_version": "recommendation-calibration-challenger-pointer.v1",
        "status": status,
        "candidate_id": str(run_result.candidate_id),
        "candidate_root": str(root),
        "candidate_freeze_hash": metadata.get("candidate_freeze_hash"),
        "candidate_manifest_hash": metadata.get("manifest_hash"),
        "candidate_artifact_hash": metadata.get("artifact_hash"),
        "dataset_hash": metadata.get("dataset_hash"),
        "frozen_at": metadata.get("candidate_frozen_at"),
        "last_decision": run_result.decision,
        "last_decision_reason": run_result.decision_reason,
        "updated_at": _taipei_now().isoformat(timespec="seconds"),
        "training_cycle": training_cycle,
        "evaluation_window_start_date": evidence_dates[0] if evidence_dates else None,
        "evaluation_window_end_date": evidence_dates[-1] if evidence_dates else None,
        "last_evaluated_evidence_hash": (
            evidence.get("receipt_hash") if isinstance(evidence, Mapping) else None
        ),
        "last_evaluated_matured_sample_count": int(
            natural_result.get("matured_sample_count", 0) if isinstance(natural_result, Mapping) else 0
        ),
        "last_evaluated_decision_date_count": len(evidence_dates),
        "retrain_trigger": retrain_trigger or "awaiting_natural_maturity",
        "shadow_only": True,
        "formal_order_allowed": False,
    }
    _write_json(pointer_path, payload)
    return root


def _resolve_symbols(
    *,
    output_root: Path,
    explicit_symbols: str | None,
    decision_date: date,
) -> tuple[tuple[str, ...], str]:
    if explicit_symbols is not None:
        symbols = tuple(sorted({item.strip() for item in explicit_symbols.split(",") if item.strip()}))
        if symbols:
            return symbols, "caller_explicit_symbols"
        raise ValueError("--symbols must contain at least one explicit symbol")
    runs_root = Path(output_root).resolve() / "recommendation" / "runs"
    if not runs_root.is_dir():
        raise ValueError("--symbols missing and scheduled recommendation snapshot directory is unavailable")
    for path in sorted(runs_root.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        config = payload.get("config")
        if not isinstance(config, Mapping) or config.get("scheduled_snapshot") is not True:
            continue
        snapshot_date = str(config.get("decision_date") or payload.get("created_at") or "")[:10]
        if snapshot_date != decision_date.isoformat():
            continue
        recommendations = payload.get("recommendations")
        if not isinstance(recommendations, list):
            continue
        symbols = tuple(
            sorted(
                {
                    str(item.get("stock_code") or item.get("symbol") or item.get("code"))
                    for item in recommendations
                    if isinstance(item, Mapping)
                    and str(item.get("stock_code") or item.get("symbol") or item.get("code") or "").strip()
                }
            )
        )
        if symbols:
            return symbols, f"scheduled_recommendation_snapshot:{path.name}"
    raise ValueError(
        "--symbols missing and no same-day scheduled recommendation snapshot supplied an explicit symbol cohort"
    )


def _merge_samples(
    replay_samples: tuple[RecommendationCalibrationSample, ...],
    natural_samples: tuple[RecommendationCalibrationSample, ...],
) -> tuple[RecommendationCalibrationSample, ...]:
    # A natural row with the same symbol/date/horizon is the stronger source
    # than a replay row, especially when it carries an observed liquidity
    # cost.  This also prevents duplicate rows from inflating the maturity or
    # training sample count.
    by_key: dict[tuple[str, str, int], RecommendationCalibrationSample] = {
        (row.symbol, row.decision_date, 20): row for row in replay_samples
    }
    for row in natural_samples:
        key = (row.symbol, row.decision_date, 20)
        existing = by_key.get(key)
        if existing is None or (
            existing.observed_liquidity_cost_bp is None
            and row.observed_liquidity_cost_bp is not None
        ):
            by_key[key] = row
    return tuple(sorted(by_key.values(), key=lambda row: (row.decision_date, row.symbol, row.row_id)))


def _load_natural_training_samples(
    *,
    output_root: Path,
    challenger_payload: Mapping[str, Any] | None,
    feature_count: int,
    fixed_round_trip_cost_bp: int,
    training_as_of: str,
    data_root: Path | None,
) -> tuple[RecommendationCalibrationSample, ...]:
    """Recover traceable natural rows from retired and adopted model paths.

    The normal pending challenger remains frozen.  After a qualified natural
    no-improvement result, the next cycle may train on its matured rows.  Rows
    from an adopted model are converted to absolute-label rows with the
    explicit null benchmark as the training baseline; the active model's
    delivered probability is never used as a hidden target or benchmark.
    """

    samples: list[RecommendationCalibrationSample] = []
    seen_keys: set[tuple[str, str, int]] = set()
    seen_rows: set[str] = set()
    cutoff = date.fromisoformat(str(training_as_of)[:10])
    if challenger_payload and challenger_payload.get("status") == "retired":
        candidate_id = str(challenger_payload.get("candidate_id") or "")
        candidate_freeze_hash = str(challenger_payload.get("candidate_freeze_hash") or "")
        evidence_root = Path(output_root).resolve() / "recommendation_learning" / "evidence" / candidate_id
        if candidate_id and candidate_freeze_hash and evidence_root.is_dir():
            for evidence_path in sorted(evidence_root.glob("*.json")):
                try:
                    evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
                    if not isinstance(evidence_payload, Mapping):
                        continue
                    if evidence_payload.get("schema_version") != "recommendation-natural-forward-evidence.v2":
                        continue
                    if evidence_payload.get("candidate_freeze_hash") != candidate_freeze_hash:
                        continue
                    if evidence_payload.get("status") != "matured":
                        continue
                    capture_path = Path(str(evidence_payload.get("capture_path") or "")).resolve()
                    capture_payload = json.loads(capture_path.read_text(encoding="utf-8"))
                    if not isinstance(capture_payload, Mapping):
                        continue
                    _verify_capture_document(capture_payload)
                    capture_rows = {
                        str(row.get("row_id")): row
                        for row in capture_payload.get("rows", [])
                        if isinstance(row, Mapping) and row.get("row_id")
                    }
                    comparisons = evidence_payload.get("comparisons")
                    if not isinstance(comparisons, list):
                        continue
                    for comparison in comparisons:
                        if not isinstance(comparison, Mapping):
                            continue
                        row_id = str(comparison.get("capture_row_id") or "")
                        capture_row = capture_rows.get(row_id)
                        if not row_id or row_id in seen_rows or capture_row is None:
                            continue
                        baseline_id = str(
                            comparison.get("probability_baseline_id")
                            or capture_row.get("probability_baseline_id")
                            or evidence_payload.get("probability_baseline_id")
                            or ""
                        )
                        if baseline_id != NULL_BENCHMARK_BASELINE_ID:
                            continue
                        feature_values = comparison.get("feature_values") or capture_row.get("feature_values")
                        if not isinstance(feature_values, list) or len(feature_values) != feature_count:
                            continue
                        symbol = str(comparison.get("symbol") or capture_row.get("symbol") or "")
                        decision = str(comparison.get("capture_as_of_date") or capture_row.get("decision_date") or "")[:10]
                        key = (symbol, decision, 20)
                        if not symbol or key in seen_keys:
                            continue
                        benchmark = comparison.get("benchmark_return_bp")
                        stock_return = comparison.get("stock_return_bp")
                        label_available = str(comparison.get("label_available_date") or "")[:10]
                        if benchmark is None or stock_return is None or not label_available:
                            continue
                        if date.fromisoformat(label_available) > cutoff:
                            continue
                        liquidity = comparison.get("observed_liquidity_cost_bp")
                        if comparison.get("observed_liquidity_cost_source") is None:
                            liquidity = None
                        sample = RecommendationCalibrationSample.from_forward_return(
                            row_id=f"natural-forward:{candidate_id}:{row_id}",
                            symbol=symbol,
                            decision_date=decision,
                            feature_as_of_date=str(
                                comparison.get("feature_as_of_date")
                                or capture_row.get("feature_as_of_date")
                                or ""
                            )[:10],
                            feature_available_date=str(
                                comparison.get("feature_available_date")
                                or capture_row.get("feature_available_date")
                                or ""
                            )[:10],
                            label_end_date=str(comparison.get("label_end_date") or "")[:10],
                            label_available_date=label_available,
                            feature_values=tuple(
                                None if value is None else int(value) for value in feature_values
                            ),
                            stock_return_bp=int(stock_return),
                            benchmark_return_bp=int(benchmark),
                            fixed_round_trip_cost_bp=int(evidence_payload.get("fixed_round_trip_cost_bp", fixed_round_trip_cost_bp)),
                            observed_liquidity_cost_bp=(int(liquidity) if liquidity is not None else None),
                            rule_probability_bp=NULL_BENCHMARK_PROBABILITY_BP,
                            rule_after_cost_probability_bp=(
                                AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP
                                if liquidity is not None
                                else None
                            ),
                            rule_after_cost_baseline_id=(
                                AFTER_COST_NULL_BENCHMARK_BASELINE_ID
                                if liquidity is not None
                                else None
                            ),
                            rule_baseline_id=NULL_BENCHMARK_BASELINE_ID,
                            source_quality="natural_forward",
                        )
                        samples.append(sample)
                        seen_rows.add(row_id)
                        seen_keys.add(key)
                except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError):
                    continue
    samples.extend(
        _load_active_model_training_samples(
            output_root=output_root,
            feature_count=feature_count,
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
            training_as_of=cutoff.isoformat(),
            data_root=data_root,
            seen_keys=seen_keys,
            seen_rows=seen_rows,
        )
    )
    return tuple(samples)


def _load_active_model_training_samples(
    *,
    output_root: Path,
    feature_count: int,
    fixed_round_trip_cost_bp: int,
    training_as_of: str,
    data_root: Path | None,
    seen_keys: set[tuple[str, str, int]],
    seen_rows: set[str],
) -> tuple[RecommendationCalibrationSample, ...]:
    """Return matured post-adoption rows without leaking active predictions.

    Active monitor receipts contain the feature vector and the independently
    observed outcome.  They are valid future training evidence only after the
    label availability cutoff and only while the same active identity is
    reloadable.  The delivered active probability is deliberately not used as
    a rule baseline: the dataset uses the named null benchmark contract.
    """

    root = Path(output_root).resolve()
    pointer_path = root / "recommendation_learning" / "recommendation-calibration-active-pointer.json"
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if not isinstance(pointer, Mapping) or pointer.get("status") != "active":
            return ()
        candidate_id = str(pointer.get("candidate_id") or "")
        effective_date = date.fromisoformat(str(pointer.get("effective_date") or "")[:10])
        if not candidate_id:
            return ()
        from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer

        consumer = RecommendationCalibrationConsumer(
            pointer_path=pointer_path,
            feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
            feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
            data_root=data_root,
        )
        cutoff = date.fromisoformat(str(training_as_of)[:10])
        if consumer.reload(decision_date=cutoff.isoformat()) != "active":
            return ()
        identity = consumer.active_identity(decision_date=cutoff.isoformat())
        if not isinstance(identity, Mapping) or str(identity.get("candidate_id") or "") != candidate_id:
            return ()
        identity_hash = _hash_payload_for_cli(identity)
        evidence_root = root / "recommendation_learning" / "active_evidence" / candidate_id
        if not evidence_root.is_dir():
            return ()
        samples: list[RecommendationCalibrationSample] = []
        for evidence_path in sorted(evidence_root.glob("*.json")):
            try:
                payload = json.loads(evidence_path.read_text(encoding="utf-8"))
                if not isinstance(payload, Mapping) or payload.get("status") != "matured":
                    continue
                verify_active_model_evidence_payload(
                    payload,
                    active_candidate_id=candidate_id,
                    active_identity_hash=identity_hash,
                    decision_date=cutoff.isoformat(),
                )
                comparisons = payload.get("comparisons")
                if not isinstance(comparisons, list):
                    continue
                for comparison in comparisons:
                    if not isinstance(comparison, Mapping):
                        continue
                    row_id = str(comparison.get("capture_row_id") or "")
                    decision = str(comparison.get("capture_as_of_date") or "")[:10]
                    label_available = str(comparison.get("label_available_date") or "")[:10]
                    if not row_id or row_id in seen_rows or not decision or not label_available:
                        continue
                    if date.fromisoformat(decision) < effective_date:
                        continue
                    if date.fromisoformat(label_available) > cutoff:
                        continue
                    symbol = str(comparison.get("symbol") or "")
                    feature_values = comparison.get("feature_values")
                    benchmark = comparison.get("benchmark_return_bp")
                    stock_return = comparison.get("stock_return_bp")
                    if (
                        not symbol
                        or not isinstance(feature_values, list)
                        or len(feature_values) != feature_count
                        or benchmark is None
                        or stock_return is None
                    ):
                        continue
                    key = (symbol, decision, 20)
                    if key in seen_keys:
                        continue
                    liquidity = comparison.get("observed_liquidity_cost_bp")
                    if comparison.get("observed_liquidity_cost_source") is None:
                        liquidity = None
                    sample = RecommendationCalibrationSample.from_forward_return(
                        row_id=f"natural-active-forward:{candidate_id}:{row_id}",
                        symbol=symbol,
                        decision_date=decision,
                        feature_as_of_date=str(comparison.get("feature_as_of_date") or "")[:10],
                        feature_available_date=str(comparison.get("feature_available_date") or "")[:10],
                        label_end_date=str(comparison.get("label_end_date") or "")[:10],
                        label_available_date=label_available,
                        feature_values=tuple(None if value is None else int(value) for value in feature_values),
                        stock_return_bp=int(stock_return),
                        benchmark_return_bp=int(benchmark),
                        fixed_round_trip_cost_bp=int(
                            payload.get("fixed_round_trip_cost_bp", fixed_round_trip_cost_bp)
                        ),
                        observed_liquidity_cost_bp=(int(liquidity) if liquidity is not None else None),
                        rule_probability_bp=NULL_BENCHMARK_PROBABILITY_BP,
                        rule_after_cost_probability_bp=(
                            AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP
                            if liquidity is not None
                            else None
                        ),
                        rule_after_cost_baseline_id=(
                            AFTER_COST_NULL_BENCHMARK_BASELINE_ID
                            if liquidity is not None
                            else None
                        ),
                        rule_baseline_id=NULL_BENCHMARK_BASELINE_ID,
                        source_quality="natural_forward_active_model",
                    )
                    samples.append(sample)
                    seen_rows.add(row_id)
                    seen_keys.add(key)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError):
                continue
        return tuple(samples)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError):
        return ()


def _inspect_active_model_performance(
    *,
    output_root: Path,
    data_root: Path | None,
    decision_date: date,
    policy: RecommendationPromotionPolicy,
) -> dict[str, Any]:
    pointer_path = Path(output_root).resolve() / "recommendation_learning" / "recommendation-calibration-active-pointer.json"
    if not pointer_path.is_file():
        return {
            "status": "clean",
            "reason": "no_active_model_pointer",
            "diagnostics": ("active_model_performance_not_applicable",),
        }
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {
            "status": "failed",
            "reason": "active_pointer_invalid_json_fail_closed",
            "diagnostics": ("active_model_pointer_fault",),
        }
    if not isinstance(pointer, Mapping):
        return {
            "status": "failed",
            "reason": "active_pointer_invalid_payload_fail_closed",
            "diagnostics": ("active_model_pointer_fault",),
        }
    if pointer.get("status") != "active":
        if pointer.get("status") in {"rule_only", "none", ""}:
            return {
                "status": "clean",
                "reason": "no_active_model_pointer",
                "diagnostics": ("active_model_performance_not_applicable",),
            }
        return {
            "status": "failed",
            "reason": "active_pointer_status_invalid_fail_closed",
            "diagnostics": ("active_model_pointer_fault",),
        }
    try:
        from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer

        consumer = RecommendationCalibrationConsumer(
            pointer_path=pointer_path,
            feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
            feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
            data_root=data_root,
        )
        if consumer.reload(decision_date=decision_date.isoformat()) != "active":
            return {
                "status": "failed",
                "reason": "active_pointer_fault_fail_closed",
                "diagnostics": (str(getattr(consumer, "_blocker", "active_model_pointer_fault")),),
            }
        identity = consumer.active_identity(decision_date=decision_date.isoformat())
        if not isinstance(identity, Mapping):
            raise ValueError("active identity unavailable")
        candidate_id = str(identity.get("candidate_id") or "")
        identity_hash = _hash_payload_for_cli(identity)
        effective_date = date.fromisoformat(str(pointer.get("effective_date") or "")[:10])
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "failed",
            "reason": f"active_pointer_fault_fail_closed:{type(exc).__name__}",
            "diagnostics": ("active_model_pointer_fault",),
        }
    evidence_root = Path(output_root).resolve() / "recommendation_learning" / "active_evidence" / candidate_id
    latest: Mapping[str, Any] | None = None
    latest_path: Path | None = None
    invalid_receipt = False
    for path in sorted(evidence_root.glob("*.json"), reverse=True) if evidence_root.is_dir() else ():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping) or payload.get("status") != "matured":
                continue
            verify_active_model_evidence_payload(
                payload,
                active_candidate_id=candidate_id,
                active_identity_hash=identity_hash,
                decision_date=decision_date.isoformat(),
            )
            if date.fromisoformat(str(payload.get("window_start_date") or "")[:10]) < effective_date:
                raise ValueError("active evidence window predates active adoption")
            if date.fromisoformat(str(payload.get("as_of_date") or "")[:10]) > decision_date:
                continue
            if int(payload.get("matured_sample_count", 0)) <= 0:
                continue
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            invalid_receipt = True
            continue
        latest = payload
        latest_path = path
        break
    if latest is None:
        if invalid_receipt:
            return {
                "status": "failed",
                "reason": "active_model_evidence_invalid_fail_closed",
                "diagnostics": ("active_model_evidence_integrity_fault",),
            }
        return {
            "status": "pending",
            "reason": "active_model_performance_has_no_matured_receipt",
            "active_candidate_id": candidate_id,
            "active_identity_hash": identity_hash,
            "diagnostics": ("active_model_performance_pending_natural_time",),
        }
    count = int(latest.get("matured_sample_count", 0))
    date_count = int(latest.get("matured_unique_decision_date_count", 0))
    if count < policy.minimum_natural_matured_samples or date_count < policy.minimum_natural_matured_decision_dates:
        return {
            "status": "pending",
            "reason": "active_model_performance_maturity_insufficient",
            "active_candidate_id": candidate_id,
            "active_identity_hash": identity_hash,
            "evidence_path": str(latest_path) if latest_path else None,
            "matured_sample_count": count,
            "matured_decision_date_count": date_count,
            "diagnostics": ("active_model_performance_pending_threshold",),
        }
    gap = int(latest.get("observed_calibration_gap_bp", 0))
    if gap > policy.maximum_calibration_gap_bp:
        return {
            "status": "drifted",
            "reason": "active_model_natural_performance_breached_threshold",
            "active_candidate_id": candidate_id,
            "active_identity_hash": identity_hash,
            "evidence_path": str(latest_path) if latest_path else None,
            "matured_sample_count": count,
            "matured_decision_date_count": date_count,
            "observed_brier_bp": int(latest.get("observed_brier_bp", 0)),
            "observed_calibration_gap_bp": gap,
            "diagnostics": ("active_model_performance_threshold_breached",),
        }
    return {
        "status": "clean",
        "reason": "active_model_natural_performance_within_threshold",
        "active_candidate_id": candidate_id,
        "active_identity_hash": identity_hash,
        "evidence_path": str(latest_path) if latest_path else None,
        "matured_sample_count": count,
        "matured_decision_date_count": date_count,
        "observed_brier_bp": int(latest.get("observed_brier_bp", 0)),
        "observed_calibration_gap_bp": gap,
        "diagnostics": ("active_model_performance_observed",),
    }


def _challenger_status(run_result: Any, natural_result: Mapping[str, Any]) -> str:
    if run_result.decision == "adopt":
        return "active"
    if run_result.decision != "retain_current":
        return "pending"
    try:
        matured = int(natural_result.get("matured_sample_count", 0))
        evidence = natural_result.get("evidence")
        evidence_path = str(evidence.get("receipt_path") or "") if isinstance(evidence, Mapping) else ""
        payload = json.loads(Path(evidence_path).read_text(encoding="utf-8")) if evidence_path else {}
        comparisons = payload.get("comparisons") if isinstance(payload, Mapping) else None
        dates = {
            str(row.get("capture_as_of_date"))[:10]
            for row in comparisons
            if isinstance(row, Mapping) and row.get("capture_as_of_date")
        } if isinstance(comparisons, list) else set()
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return "pending"
    if (
        matured >= RecommendationPromotionPolicy().minimum_natural_matured_samples
        and len(dates) >= RecommendationPromotionPolicy().minimum_natural_matured_decision_dates
        and run_result.decision_reason
        in {
            "no_predeclared_natural_brier_improvement",
            "natural_calibration_gap_exceeds_threshold",
        }
    ):
        return "retired"
    return "pending"


def _dependencies_require_emergency(dependencies: Mapping[str, Any]) -> bool:
    """Return whether actual post-scan health requires a fail-closed rollback."""

    blocked = {"failed", "missing", "unavailable", "degraded", "drifted"}
    return any(
        str(dependencies.get(field_name, "not_checked")).lower() in blocked
        for field_name in ("data_status", "outcome_status", "drift_status")
    )


def _dependency_failure(
    *,
    reason: str,
    data_status: str,
    outcome_status: str,
    drift_status: str,
) -> dict[str, Any]:
    return {
        "data_status": data_status,
        "outcome_status": outcome_status,
        "drift_status": drift_status,
        "data_source": "MLHistoricalSnapshotProvider:sqlite_mode_ro_query_only",
        "drift_method": "active_model_natural_evidence_metrics_plus_source_health",
        "model_performance": {"status": drift_status, "reason": reason},
        "decision_calendar": {"timezone": "Asia/Taipei", "is_trading_day_for_explicit_symbols": False},
        "diagnostics": [reason],
        "checked_at": _taipei_now().isoformat(timespec="seconds"),
    }


def _cli_payload(
    *,
    output_root: Path,
    decision_day: date,
    symbols: tuple[str, ...],
    symbol_source: str,
    replay_result: Any,
    manifest_path: Path | None,
    dependencies: Mapping[str, Any],
    run_result: Any,
    natural_result: Mapping[str, Any],
    active_natural_result: Mapping[str, Any],
    live_capture: Mapping[str, Any],
    error: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "daily-recommendation-learning-cli-result.v3",
        "decision_date": decision_day.isoformat(),
        "decision_timezone": "Asia/Taipei",
        "symbols": list(symbols),
        "symbol_source": symbol_source,
        "replay": replay_result.to_dict() if replay_result is not None else None,
        "replay_manifest_path": str(manifest_path) if manifest_path is not None else None,
        "dependencies": dict(dependencies),
        "run": {
            "run_id": run_result.run_id,
            "status": run_result.status,
            "reason": run_result.reason,
            "receipt_path": run_result.receipt_path,
            "latest_status_path": run_result.latest_status_path,
            "dataset_id": run_result.dataset_id,
            "dataset_hash": run_result.dataset_hash,
            "candidate_id": run_result.candidate_id,
            "candidate_root": run_result.candidate_root,
            "decision": run_result.decision,
            "decision_reason": run_result.decision_reason,
            "idempotent_replay": run_result.idempotent_replay,
        },
        "challenger": _read_challenger_pointer(output_root),
        "active_pointer": _read_active_pointer(output_root),
        "natural_evidence": dict(natural_result),
        "active_model_natural_evidence": dict(active_natural_result or {}),
        "live_capture": dict(live_capture),
        "error": error,
        "formal_order_allowed": False,
        "shadow_only": True,
    }
    return payload


def _read_challenger_pointer(output_root: Path) -> dict[str, Any] | None:
    path = Path(output_root).resolve() / "recommendation_learning" / "challenger" / "current.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_active_pointer(output_root: Path) -> dict[str, Any] | None:
    path = Path(output_root).resolve() / "recommendation_learning" / "recommendation-calibration-active-pointer.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _candidate_freeze(candidate_root: str | Path) -> str | None:
    try:
        payload = json.loads((Path(candidate_root) / "candidate.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return str(payload.get("candidate_freeze_hash")) if payload.get("candidate_freeze_hash") else None


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _update_latest_status(path_text: str, cli_payload: Mapping[str, Any]) -> None:
    """Append CLI observability to the runner receipt without changing its contract."""

    path = Path(path_text).resolve()
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    for field_name in (
        "schema_version",
        "decision_date",
        "decision_timezone",
        "symbols",
        "symbol_source",
        "dependencies",
        "challenger",
        "active_pointer",
        "natural_evidence",
        "active_model_natural_evidence",
        "live_capture",
        "training_as_of",
        "training_sample_count",
        "natural_training_sample_count",
        "natural_evidence_supplied",
        "ignored_caller_inputs",
        "formal_order_allowed",
        "shadow_only",
        "error",
    ):
        if field_name in cli_payload:
            existing[f"cli_{field_name}" if field_name == "schema_version" else field_name] = cli_payload[field_name]
    existing["active_model_performance"] = (
        cli_payload.get("dependencies", {}).get("model_performance", {})
        if isinstance(cli_payload.get("dependencies"), Mapping)
        else {}
    )
    existing["cli_result_updated_at"] = _taipei_now().isoformat(timespec="seconds")
    _write_json(path, existing)


if __name__ == "__main__":
    raise SystemExit(main())
