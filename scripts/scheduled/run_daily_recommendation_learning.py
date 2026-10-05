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
import base64
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
from typing import Any, Mapping, cast
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml_module.recommendation_calibration_learning_runner import (  # noqa: E402
    DailyRecommendationLearningRunner,
)
from app_module.recommendation_learning_paths import (  # noqa: E402
    RecommendationLearningPathError,
    resolve_recommendation_learning_output_root,
)
from app_module.saved_recommendation_queries import (  # noqa: E402
    build_recommendation_execution_queries,
    execution_result_config,
)
from app_module.recommendation.contracts import (  # noqa: E402
    ExecutionStatus,
    SUPPORTED_EXECUTION_SCHEMA_REVISIONS,
    SnapshotCohort,
    SnapshotCohortCoverage,
    SnapshotCohortCoverageStatus,
    schema_version as RECOMMENDATION_EXECUTION_SCHEMA_VERSION,
)
from app_module.recommendation.persistence import ExecutionPersistenceError  # noqa: E402
from app_module.recommendation.queries import _read_regular_file_no_follow  # noqa: E402
from data_module.config import TWStockConfig  # noqa: E402
from data_module.current_observed_capacity_eligibility import (  # noqa: E402
    classify_current_observed_raw_status,
    current_stock_research_capacity_passed,
)
from data_module.ml_historical_snapshot_provider import (  # noqa: E402
    MLHistoricalSnapshotProvider,
)
from data_module.ml_daily_price_revision_gate import (  # noqa: E402
    DailyPriceSourceRevisionError,
)
from data_module.natural_maturity_session_resolver import (  # noqa: E402
    NATURAL_MATURITY_SESSION_RESOLVER_ID,
    NATURAL_MATURITY_SESSION_RESOLVER_VERSION,
    NaturalMaturitySessionResolver,
)
from data_module.official_trading_calendar import OfficialTradingCalendar  # noqa: E402
from scripts.scheduled.current_observed_raw_cycle_dependency import (  # noqa: E402
    expected_current_observed_source_date,
)
from data_module.twse_quote_observation_capture import (  # noqa: E402
    SESSION_CLOSE as _CURRENT_RESEARCH_MARKET_CLOSE,
)
from data_module.recommendation_calibration_source_contract import (  # noqa: E402
    _hash_payload as _source_contract_hash_payload,
    inspect_source_contract,
    write_source_contract,
)
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY  # noqa: E402
from ml_module.current_observed_feature_snapshot_composer import (  # noqa: E402
    FEATURE_SNAPSHOT_V1 as CURRENT_OBSERVED_FEATURE_SNAPSHOT_V1,
    FEATURE_SNAPSHOT_V2 as CURRENT_OBSERVED_FEATURE_SNAPSHOT_V2,
    compose_current_observed_feature_snapshot_v2,
    partition_current_observed_symbols,
    verify_current_observed_feature_snapshot_v2,
)
from ml_module.historical_feature_builder import HistoricalFeatureBuilder  # noqa: E402
from ml_module.recommendation_calibration_authority import (  # noqa: E402
    RecommendationPromotionPolicy,
)
from ml_module.recommendation_calibration_evidence import (  # noqa: E402
    ActiveModelPredictionCaptureService,
    RecommendationPredictionCaptureInput,
    RecommendationPredictionCaptureService,
    _current_observed_raw_status_is_eligible,
    load_current_observed_context_from_pinned_snapshot,
    verify_current_observed_cycle_reuse,
    _verify_capture_bundle_payload,
    _verify_capture_document,
    _verify_capture_payload,
    _write_json_once,
    _normalized_sha256_hex,
    verify_current_observed_input_capture,
    verify_current_observed_official_calendar_evidence,
)
from ml_module.recommendation_calibration_training import (  # noqa: E402
    AFTER_COST_NULL_BENCHMARK_BASELINE_ID,
    AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP,
    RecommendationCalibrationTrainingConfig,
    RecommendationCalibrationSample,
    candidate_freeze_hash,
    recommendation_cost_contract_hash,
    recommendation_label_registry_hash,
)
from ml_module.recommendation_historical_replay import (  # noqa: E402
    RecommendationHistoricalReplayConfig,
    RecommendationHistoricalReplayService,
)
from ml_module.current_observed_natural_research_fit import (  # noqa: E402
    fit_current_observed_natural_research,
    _current_observed_capture_semantic_hash,
)
from ml_module.recommendation_training_lineage import (  # noqa: E402
    RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH,
)
from ml_module.recommendation_cost_scenario import (  # noqa: E402
    RecommendationCostScenario,
    RecommendationCostScenarioError,
    build_banktaiwan_cost_scenario,
    build_legacy_cost_scenario,
    cost_scenario_from_metadata,
    normalize_cost_scenario,
)
from ml_module.model_artifact_manifest import ModelArtifactManifest  # noqa: E402
from ml_module.current_restated_research_bridge import (  # noqa: E402
    CurrentRestatedResearchError,
    add_current_restated_research_arguments,
    parse_current_restated_research_invocation,
    run_current_restated_research_sidecar,
)
from data_module.ml_research_output_boundary import (  # noqa: E402
    get_ml_research_root,
    resolve_ml_research_output_path,
)


TAIPEI = ZoneInfo("Asia/Taipei")
_MAX_SNAPSHOT_INVOCATION_STDOUT_BYTES = 8 * 1024 * 1024
_SNAPSHOT_INVOCATION_STDOUT_NAME = "recommendation_snapshot.stdout.bin"

_HISTORICAL_REPLAY_SOURCE_BLOCKERS = frozenset(
    {
        "technical_publication_time_unverified",
        "corporate_action_source_or_adjustment_unverified",
        "observed_liquidity_cost_missing_after_cost_target_unavailable",
        "observed_liquidity_cost_partial_after_cost_target_unavailable",
    }
)


def _clean_blockers(value: object) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return list(dict.fromkeys(str(item) for item in value if str(item).strip()))


def _metadata_int_or_none(value: object) -> int | None:
    """Read JSON integer metadata without coercing malformed values."""

    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _capture_dependency_failure(
    live_capture: Mapping[str, Any] | None,
) -> tuple[str | None, bool]:
    """Classify capture custody failures without treating natural skips as errors."""

    if not isinstance(live_capture, Mapping):
        return None, False
    status = str(live_capture.get("status") or "").strip().lower()
    if status not in {"blocked", "failed"}:
        return None, False
    reason = str(live_capture.get("reason") or "capture_dependency_unavailable").strip()
    return f"live_capture_{status}:{reason}", status == "blocked"


def _replay_sample_count(replay_result: Any) -> int:
    value = getattr(replay_result, "sample_count", None)
    if isinstance(value, int):
        return value
    samples = getattr(replay_result, "samples", ())
    try:
        return len(samples)
    except TypeError:
        return 0


def _should_expand_historical_bootstrap(result: Any) -> bool:
    """Return true only for a causal OOF class-coverage training failure."""

    if str(getattr(result, "status", "")) != "failed_training":
        return False
    reason = str(getattr(result, "reason", "")).lower()
    return "oof calibration" in reason or "calibration target requires two classes" in reason


def _build_training_quality(
    *,
    replay_result: Any,
    source_contract: Mapping[str, Any],
    manifest_path: Path,
    symbol_source: str,
    natural_training_sample_count: int,
    replay_selection_policy: str,
    dependency_check: Mapping[str, Any],
) -> dict[str, Any]:
    """Separate historical replay notes from prospective promotion lanes.

    Historical replay is intentionally never relabeled as forward evidence.
    The price-up lane can nevertheless become eligible for later authority
    promotion when the immutable prospective input contract is ready.  Cost
    and broker-actual lanes remain independent and visible blockers.
    """

    lanes_value = source_contract.get("lanes")
    lanes = lanes_value if isinstance(lanes_value, Mapping) else {}
    price_up_value = lanes.get("price_up_calibration")
    price_up = price_up_value if isinstance(price_up_value, Mapping) else {}
    after_cost_value = lanes.get("after_cost_calibration")
    after_cost = after_cost_value if isinstance(after_cost_value, Mapping) else {}
    actual_value = lanes.get("actual_execution")
    actual = actual_value if isinstance(actual_value, Mapping) else {}

    price_up_prospective_blockers = _clean_blockers(price_up.get("prospective_blockers"))
    price_up_prospective_ready = (
        price_up.get("prospective_status") == "ready"
        and not price_up_prospective_blockers
    )
    historical_replay_blockers = _clean_blockers(
        getattr(replay_result, "candidate_blockers", ())
    )
    # These are historical-contract explanations, not blockers for a new
    # source-bound price-up capture.  Keep them under the explicit historical
    # fields so they remain inspectable and cannot be mistaken for proof.
    candidate_gate_blockers = [
        blocker
        for blocker in historical_replay_blockers
        if blocker not in _HISTORICAL_REPLAY_SOURCE_BLOCKERS
    ]
    if not price_up_prospective_ready:
        candidate_gate_blockers.extend(
            ["prospective_price_up_source_not_ready", *price_up_prospective_blockers]
        )
    candidate_gate_blockers = list(dict.fromkeys(candidate_gate_blockers))

    after_cost_blockers = _clean_blockers(
        after_cost.get("prospective_blockers") or after_cost.get("blockers")
    )
    actual_execution_blockers = _clean_blockers(actual.get("blockers"))
    lane_status = {
        "price_up_calibration": {
            "status": price_up.get("status"),
            "prospective_status": price_up.get("prospective_status"),
            "prospective_blockers": price_up_prospective_blockers,
            "promotion_target": "price_up_calibration",
            "promotion_source_bound": price_up_prospective_ready,
        },
        "after_cost_calibration": {
            "status": after_cost.get("status"),
            "prospective_status": after_cost.get("prospective_status"),
            "blockers": after_cost_blockers,
            "requires_observed_cost": after_cost.get("requires_observed_cost") is True,
            "estimated_cost_is_not_observed": after_cost.get("estimated_cost_is_not_observed") is True,
            "promotion_target": "after_cost_calibration",
        },
        "actual_execution": {
            "status": actual.get("status"),
            "blockers": actual_execution_blockers,
            "requires_broker_fill_custody": actual.get("requires_broker_fill_custody") is True,
            "promotion_target": "actual_execution",
        },
    }
    replay_coverage = getattr(replay_result, "coverage", {})
    replay_coverage = replay_coverage if isinstance(replay_coverage, Mapping) else {}
    source_disclosures = getattr(replay_result, "source_disclosures", {})
    source_disclosures = source_disclosures if isinstance(source_disclosures, Mapping) else {}
    lookahead_checks = getattr(replay_result, "lookahead_checks", {})
    lookahead_checks = lookahead_checks if isinstance(lookahead_checks, Mapping) else {}
    return {
        "training_data_eligible": replay_result.training_data_eligible,
        # These two fields retain the historical-replay semantics.  A replay
        # result is never promoted to forward evidence by setting them true.
        "forward_evidence_eligible": replay_result.forward_evidence_eligible,
        "formal_candidate_eligible": replay_result.formal_candidate_eligible,
        "historical_replay_forward_evidence_eligible": replay_result.forward_evidence_eligible,
        "historical_replay_formal_candidate_eligible": replay_result.formal_candidate_eligible,
        "historical_replay_candidate_blockers": historical_replay_blockers,
        "candidate_blockers": candidate_gate_blockers,
        "prospective_source_contract_ready": price_up_prospective_ready,
        "prospective_price_up_promotion_ready": price_up_prospective_ready,
        "prospective_price_up_blockers": price_up_prospective_blockers,
        "after_cost_blockers": after_cost_blockers,
        "actual_execution_blockers": actual_execution_blockers,
        "lane_status": lane_status,
        "promotion_target": "price_up_calibration",
        "replay_dataset_id": replay_result.dataset_id,
        "replay_dataset_manifest_path": str(manifest_path),
        "replay_dataset_hash": replay_result.dataset_hash,
        "replay_sample_count": _replay_sample_count(replay_result),
        "replay_decision_date_count": len(replay_result.decision_dates),
        "replay_coverage": dict(replay_coverage),
        "source_disclosures": source_disclosures,
        "lookahead_checks": lookahead_checks,
        "dependency_check": dependency_check,
        "probability_baseline_id": NULL_BENCHMARK_BASELINE_ID,
        "symbol_source": symbol_source,
        "natural_training_sample_count": natural_training_sample_count,
        "replay_selection_policy": replay_selection_policy,
        "source_contract": dict(source_contract),
    }


from ml_module.recommendation_natural_outcome_service import (  # noqa: E402
    RecommendationNaturalOutcomeService,
    verify_active_model_evidence_payload,
    verify_current_observed_outcome_receipt,
)
from ml_module.recommendation_probability_transform import (  # noqa: E402
    NULL_BENCHMARK_BASELINE_ID,
    NULL_BENCHMARK_PROBABILITY_BP,
)


def _taipei_now() -> datetime:
    """Return the scheduler clock; tests may replace this external clock only."""

    return datetime.now(TAIPEI)


DEFAULT_NATURAL_MATURITY_CALENDAR_CACHE_PATH = (
    ROOT / "output" / "paper_execution_eod_replay" / "calendar_cache"
)
NATURAL_MATURITY_CALENDAR_CACHE_ENV = "NATURAL_MATURITY_CALENDAR_CACHE_PATH"
NATURAL_MATURITY_TEMPORARY_CLOSURE_ENV = "NATURAL_MATURITY_TEMPORARY_CLOSURE_PATH"


def _configured_path(value: object) -> Path | None:
    if isinstance(value, Path):
        return value.expanduser().resolve()
    if isinstance(value, str) and value.strip():
        return Path(value.strip()).expanduser().resolve()
    return None


def _natural_maturity_calendar_paths(
    *,
    calendar_cache_path: Path | None,
    temporary_closure_path: Path | None,
) -> tuple[Path, Path | None]:
    """解析明確或既有操作日曆來源，不在 caller 內觸發網路 fallback。"""

    calendar_path = _configured_path(calendar_cache_path)
    if calendar_path is None:
        for name in (
            NATURAL_MATURITY_CALENDAR_CACHE_ENV,
            "ML_FORWARD_CALENDAR_CACHE_ROOT",
        ):
            calendar_path = _configured_path(os.environ.get(name))
            if calendar_path is not None:
                break
    if calendar_path is None:
        calendar_path = DEFAULT_NATURAL_MATURITY_CALENDAR_CACHE_PATH.resolve()

    temporary_path = _configured_path(temporary_closure_path)
    if temporary_path is None:
        temporary_path = _configured_path(
            os.environ.get(NATURAL_MATURITY_TEMPORARY_CLOSURE_ENV)
        )
    return calendar_path, temporary_path


def _natural_maturity_context(
    *,
    source_db: Path,
    calendar_cache_path: Path,
    temporary_closure_path: Path | None,
    evaluation_at: datetime,
    evaluation_date: date,
) -> dict[str, Any]:
    """把每日收據中的唯讀成熟度來源與實際檢查時鐘固定下來。"""

    if evaluation_at.tzinfo is None or evaluation_at.utcoffset() is None:
        raise ValueError("natural maturity evaluation clock must be timezone-aware")
    return {
        "schema_version": "natural-maturity-caller-context.v1",
        "resolver_id": NATURAL_MATURITY_SESSION_RESOLVER_ID,
        "resolver_version": NATURAL_MATURITY_SESSION_RESOLVER_VERSION,
        "source_db_path": str(source_db.expanduser().resolve()),
        "calendar_cache_path": str(calendar_cache_path.expanduser().resolve()),
        "temporary_closure_path": (
            str(temporary_closure_path.expanduser().resolve())
            if temporary_closure_path is not None
            else None
        ),
        "evaluation_at": evaluation_at.isoformat(),
        "evaluation_clock_source": "scheduler_checked_aware_clock",
        "evaluation_date": evaluation_date.isoformat(),
        "evaluation_date_matches_checked_clock": (
            evaluation_date == evaluation_at.astimezone(TAIPEI).date()
        ),
    }


def _annotate_natural_result(
    result: Mapping[str, Any] | None,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    """在 candidate／active 結果旁保留 resolver custody 與 clock 診斷。"""

    payload = dict(result) if isinstance(result, Mapping) else {}
    payload["natural_maturity_context"] = dict(context)
    return payload


def _build_natural_outcome_service(
    *,
    provider: MLHistoricalSnapshotProvider,
    source_db: Path,
    session_resolver: NaturalMaturitySessionResolver,
    evaluation_at: datetime,
) -> RecommendationNaturalOutcomeService:
    """以相同 source DB 與 checked clock 建立兩個 natural consumer。"""

    return RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=source_db,
        session_resolver=session_resolver,
        evaluation_at=evaluation_at,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--source-db", type=Path, default=None)
    parser.add_argument(
        "--calendar-cache-path",
        type=Path,
        default=None,
        help=(
            "唯讀官方 annual calendar cache；省略時沿用既有 repository "
            "output/paper_execution_eod_replay/calendar_cache 或環境設定。"
        ),
    )
    parser.add_argument(
        "--temporary-closure-cache-path",
        type=Path,
        default=None,
        help=(
            "唯讀官方 temporary-closure cache；省略時不假設 annual cache "
            "涵蓋事件，僅接受 NATURAL_MATURITY_TEMPORARY_CLOSURE_PATH。"
        ),
    )
    parser.add_argument(
        "--snapshot-output-root",
        type=Path,
        default=None,
        help=(
            "同日 scheduled recommendation snapshot 的唯讀來源根目錄；"
            "省略時沿用 OUTPUT_ROOT／learning output root。"
        ),
    )
    parser.add_argument(
        "--current-observed-source-output-root",
        type=Path,
        default=None,
        help=(
            "Canonical output root containing the raw-run status used only by the "
            "current-observed G6 research lane. Defaults to DATA_ROOT/output."
        ),
    )
    parser.add_argument("--current-observed-expected-raw-run-id", default=None)
    parser.add_argument("--current-observed-expected-cycle-terminal", type=Path, default=None)
    parser.add_argument("--current-observed-expected-cycle-terminal-sha256", default=None)
    parser.add_argument(
        "--snapshot-result-id",
        default=None,
        help="本次 scheduled snapshot child 回傳的 opaque result id；未指定 symbols 時必填。",
    )
    parser.add_argument(
        "--snapshot-cohort-hash",
        default=None,
        help="本次 snapshot child 回傳的 snapshot_cohort SHA-256 binding；未指定 symbols 時必填。",
    )
    parser.add_argument(
        "--snapshot-invocation-output-sha256",
        default=None,
        help="本次 snapshot child 原始 stdout 收據的 SHA-256；未指定 symbols 時必填。",
    )
    parser.add_argument(
        "--snapshot-invocation-output-path",
        default=None,
        help="本次 pipeline run create-only 保存的 snapshot child 原始 stdout bytes 路徑。",
    )
    parser.add_argument(
        "--source-artifact-root",
        type=Path,
        default=None,
        help=(
            "已驗證 technical／official／corporate source custody 的唯讀根目錄；"
            "省略時沿用 learning output root。"
        ),
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help=(
            "Comma-separated explicit symbols for a controlled run. If omitted, "
            "the caller must provide this invocation's snapshot result id and cohort hash."
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
    parser.add_argument(
        "--cost-scenario",
        choices=("legacy_fixed_bp", "banktaiwan_estimated_research"),
        default="legacy_fixed_bp",
        help="成本 contract；預設維持既有 fixed 50bp，臺銀情境僅供 research/shadow。",
    )
    parser.add_argument(
        "--cost-policy-estimate-date",
        default="2026-01-01",
        help="臺銀 policy estimate date；與 market replay date 分開記錄。",
    )
    parser.add_argument(
        "--research-order-amount-twd",
        default=None,
        help="臺銀研究訂單金額（Decimal-safe text）；與股數擇一。",
    )
    parser.add_argument("--research-order-quantity-shares", type=int, default=None)
    parser.add_argument(
        "--research-order-lot-type",
        choices=("full_lot", "odd_lot"),
        default="full_lot",
    )
    parser.add_argument(
        "--research-instrument-type",
        choices=("ordinary_stock", "equity_etf"),
        default="ordinary_stock",
    )
    parser.add_argument("--max-decision-dates", type=int, default=100)
    parser.add_argument(
        "--replay-selection-policy",
        choices=(
            "chronological_first_eligible_date",
            "latest_eligible_dates",
            "time_stratified_eligible_dates",
        ),
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
    add_current_restated_research_arguments(parser)
    return parser


def _cost_scenario_from_args(
    args: argparse.Namespace,
) -> tuple[int | None, RecommendationCostScenario]:
    if args.cost_scenario == "legacy_fixed_bp":
        fixed = 50 if args.fixed_round_trip_cost_bp is None else int(args.fixed_round_trip_cost_bp)
        return fixed, build_legacy_cost_scenario(fixed)
    if args.fixed_round_trip_cost_bp not in (None, 50):
        raise ValueError(
            "banktaiwan_estimated_research 不可與非預設 fixed_round_trip_cost_bp 混用"
        )
    scenario = build_banktaiwan_cost_scenario(
        policy_estimate_date=str(args.cost_policy_estimate_date),
        research_order_amount_twd=args.research_order_amount_twd,
        research_order_quantity_shares=args.research_order_quantity_shares,
        lot_type=str(args.research_order_lot_type),
        instrument_type=str(args.research_instrument_type),
    )
    return None, scenario


def _run_current_restated_research_entry(
    args: argparse.Namespace,
    *,
    invocation: Any,
    actual_invocation: list[str],
) -> int:
    """只重驗現有 A/B/模型 pins 並輸出 Legacy research terminal。"""

    try:
        if (
            args.cost_scenario != "legacy_fixed_bp"
            or args.fixed_round_trip_cost_bp != 50
            or args.research_order_amount_twd is not None
            or args.research_order_quantity_shares is not None
        ):
            raise CurrentRestatedResearchError(
                "Legacy current-restated lane requires fixed 50 bp and no BankTaiwan sizing"
            )
        cost_scenario = build_legacy_cost_scenario(50)
        result = run_current_restated_research_sidecar(
            invocation,
            lane="legacy",
            cost_scenario=cost_scenario,
            actual_invocation=actual_invocation,
            repository_root=ROOT,
        )
    except (CurrentRestatedResearchError, RecommendationCostScenarioError, OSError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "daily-recommendation-learning-research-only.v1",
                    "status": "blocked",
                    "reason": "current_restated_research_sidecar_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "model_training_performed": False,
                    "verified_model_reused": False,
                    "formal_calibration_performed": False,
                    "formal_order_allowed": False,
                    "shadow_only": True,
                    "historical_pit_eligible": False,
                    "decision_time_eligible": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2

    print(
        json.dumps(
            {
                "schema_version": "daily-recommendation-learning-research-only.v1",
                "status": result.status,
                "terminal": True,
                "lane": "legacy",
                "mode": "source_row_outcome_research",
                "receipt_path": str(result.receipt_path),
                "receipt_sha256": result.receipt_sha256,
                "binding_sha256": result.binding_sha256,
                "sample_cohort_sha256": result.sample_cohort_sha256,
                "core19_numeric_vector_sha256_by_symbol": dict(
                    result.core19_numeric_vector_sha256_by_symbol
                ),
                "model_training_performed": False,
                "verified_model_reused": True,
                "formal_calibration_performed": False,
                "formal_order_allowed": False,
                "shadow_only": True,
                "historical_pit_eligible": False,
                "decision_time_eligible": False,
                "recommendation_cohort_status": "not_a_daily_recommendation_cohort",
                "full_allocation_status": "blocked_full_allocation_teacher_unavailable",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _stored_cost_scenario(
    payload: Mapping[str, Any],
    *,
    source_path: Path,
    allow_legacy_marker_missing_freeze: bool = False,
) -> tuple[RecommendationCostScenario | None, str | None]:
    """Resolve one shared-root marker without ever inventing a new lane.

    Early challenger pointers predate the cost-scenario fields.  They can be
    read only when their candidate identity points to a candidate document
    whose immutable hashes and cost contract agree; an unanchored marker is
    unverifiable and remains fail-closed.  The narrowly scoped compatibility
    flag permits only a missing marker-level freeze field; the root guard
    still requires a same-cohort full-freeze peer before accepting it.
    """

    marker_has_cost_metadata = any(
        (
            isinstance(payload.get(key), Mapping)
            and bool(payload.get(key))
            if key == "cost_scenario"
            else payload.get(key) not in (None, "")
        )
        for key in (
            "cost_scenario",
            "cost_scenario_id",
            "cost_scenario_version",
            "cost_scenario_hash",
            "cost_basis",
            "fixed_round_trip_cost_bp",
            "cost_policy_id",
            "cost_policy_version",
            "policy_estimate_date",
            "research_order_amount_twd",
            "research_order_quantity_shares",
            "lot_type",
            "instrument_type",
        )
    )
    if not marker_has_cost_metadata:
        if _is_unverifiable_legacy_decision_receipt(payload):
            return (
                None,
                f"{source_path}:unverifiable_cost_scenario:legacy_decision_requires_verified_anchor",
            )
        return _stored_cost_scenario_from_candidate_root(
            payload,
            source_path=source_path,
            allow_missing_candidate_freeze_hash=allow_legacy_marker_missing_freeze,
        )

    try:
        fixed_value = _metadata_int_or_none(payload.get("fixed_round_trip_cost_bp"))
        scenario = cost_scenario_from_metadata(
            payload,
            fixed_round_trip_cost_bp=fixed_value,
        )
    except (TypeError, ValueError, RecommendationCostScenarioError) as exc:
        return None, f"{source_path}:invalid_cost_scenario:{type(exc).__name__}:{exc}"
    dataset_marker_key = (
        "candidate_dataset_hash"
        if payload.get("candidate_dataset_hash") not in (None, "")
        else "dataset_hash"
    )
    anchored_identity_keys = (
        "candidate_root",
        "candidate_id",
        "candidate_freeze_hash",
        "candidate_manifest_hash",
        "candidate_artifact_hash",
        dataset_marker_key,
    )
    anchored_keys_missing = [
        key for key in anchored_identity_keys if payload.get(key) in (None, "")
    ]
    if not anchored_keys_missing or (
        allow_legacy_marker_missing_freeze
        and anchored_keys_missing == ["candidate_freeze_hash"]
    ):
        candidate_scenario, error = _stored_cost_scenario_from_candidate_root(
            payload,
            source_path=source_path,
            allow_missing_candidate_freeze_hash=allow_legacy_marker_missing_freeze,
        )
        if error is not None or candidate_scenario is None:
            return None, error or f"{source_path}:unverifiable_cost_scenario:candidate_missing"
        if candidate_scenario.scenario_hash != scenario.scenario_hash:
            return (
                None,
                f"{source_path}:unverifiable_cost_scenario:candidate_cost_scenario_mismatch",
            )
    return scenario, None


def _stored_cost_scenario_from_candidate_root(
    payload: Mapping[str, Any],
    *,
    source_path: Path,
    allow_missing_candidate_freeze_hash: bool = False,
) -> tuple[RecommendationCostScenario | None, str | None]:
    """Recover a legacy pointer's lane from verified candidate artifacts.

    A pointer without scenario fields is only a historical metadata shape; it
    is not itself authority.  The candidate root must therefore provide a
    complete identity anchor and pass the same canonical manifest, artifact,
    freeze, and cost-contract checks used by the consumer contract.  A
    compatibility caller may omit only the marker-level freeze field; the
    candidate document's own freeze remains mandatory and is recomputed.
    """

    candidate_root_value = payload.get("candidate_root")
    if not isinstance(candidate_root_value, (str, Path)) or not str(candidate_root_value).strip():
        return None, f"{source_path}:unverifiable_cost_scenario:no_candidate_root"
    dataset_marker_key = (
        "candidate_dataset_hash"
        if payload.get("candidate_dataset_hash") not in (None, "")
        else "dataset_hash"
    )
    identity_pairs = (
        ("candidate_id", "candidate_id"),
        ("candidate_freeze_hash", "candidate_freeze_hash"),
        ("candidate_manifest_hash", "manifest_hash"),
        ("candidate_artifact_hash", "artifact_hash"),
        (dataset_marker_key, "dataset_hash"),
    )
    missing_identity = [
        marker_key
        for marker_key, _ in identity_pairs
        if payload.get(marker_key) in (None, "")
    ]
    if missing_identity and not (
        allow_missing_candidate_freeze_hash
        and missing_identity == ["candidate_freeze_hash"]
    ):
        return (
            None,
            f"{source_path}:unverifiable_cost_scenario:incomplete_candidate_identity:"
            f"{','.join(missing_identity)}",
        )
    hash_marker_keys = (
        "candidate_freeze_hash",
        "candidate_manifest_hash",
        "candidate_artifact_hash",
        dataset_marker_key,
    )
    for marker_key in hash_marker_keys:
        if (
            marker_key == "candidate_freeze_hash"
            and allow_missing_candidate_freeze_hash
            and payload.get(marker_key) in (None, "")
        ):
            continue
        if not _is_sha256_digest(payload.get(marker_key)):
            return (
                None,
                f"{source_path}:unverifiable_cost_scenario:invalid_candidate_identity:"
                f"{marker_key}",
            )
    try:
        candidate_root = Path(str(candidate_root_value)).expanduser().resolve()
        candidate_path = candidate_root / "candidate.json"
        manifest_path = candidate_root / "manifest.json"
        candidate_metadata = json.loads(candidate_path.read_text(encoding="utf-8"))
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as exc:
        return (
            None,
            f"{source_path}:unverifiable_cost_scenario:candidate_metadata_unreadable:"
            f"{type(exc).__name__}",
        )
    if not isinstance(candidate_metadata, Mapping):
        return None, f"{source_path}:unverifiable_cost_scenario:candidate_metadata_invalid"
    if not isinstance(manifest_payload, Mapping):
        return None, f"{source_path}:unverifiable_cost_scenario:candidate_manifest_invalid"
    for marker_key, candidate_key in identity_pairs:
        expected = payload.get(marker_key)
        actual = candidate_metadata.get(candidate_key)
        if (
            marker_key == "candidate_freeze_hash"
            and allow_missing_candidate_freeze_hash
            and expected in (None, "")
        ):
            continue
        if actual in (None, "") or str(actual) != str(expected):
            return (
                None,
                f"{source_path}:unverifiable_cost_scenario:"
                f"candidate_identity_mismatch:{marker_key}",
            )

    try:
        manifest = ModelArtifactManifest.from_dict(manifest_payload)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return (
            None,
            f"{source_path}:unverifiable_cost_scenario:candidate_manifest_invalid:"
            f"{type(exc).__name__}:{exc}",
        )
    if not _is_sha256_digest(candidate_metadata.get("candidate_freeze_hash")):
        return (
            None,
            f"{source_path}:unverifiable_cost_scenario:invalid_candidate_metadata:"
            "candidate_freeze_hash",
        )
    if not _is_sha256_digest(candidate_metadata.get("manifest_hash")):
        return (
            None,
            f"{source_path}:unverifiable_cost_scenario:invalid_candidate_metadata:"
            "manifest_hash",
        )
    if not _is_sha256_digest(candidate_metadata.get("artifact_hash")):
        return (
            None,
            f"{source_path}:unverifiable_cost_scenario:invalid_candidate_metadata:"
            "artifact_hash",
        )
    if not _is_sha256_digest(candidate_metadata.get("dataset_hash")):
        return (
            None,
            f"{source_path}:unverifiable_cost_scenario:invalid_candidate_metadata:"
            "dataset_hash",
        )
    if str(candidate_metadata.get("model_id") or "") != str(candidate_metadata.get("candidate_id") or ""):
        return None, f"{source_path}:unverifiable_cost_scenario:candidate_model_identity_mismatch"
    if str(manifest.model_id) != str(candidate_metadata.get("candidate_id") or ""):
        return None, f"{source_path}:unverifiable_cost_scenario:manifest_candidate_id_mismatch"
    if str(candidate_metadata.get("dataset_id") or "") != str(manifest.dataset_id):
        return None, f"{source_path}:unverifiable_cost_scenario:manifest_dataset_id_mismatch"
    if str(candidate_metadata.get("manifest_hash") or "") != manifest.manifest_hash:
        return None, f"{source_path}:unverifiable_cost_scenario:manifest_hash_mismatch"
    if str(candidate_metadata.get("artifact_hash") or "") != manifest.artifact_hash:
        return None, f"{source_path}:unverifiable_cost_scenario:artifact_hash_manifest_mismatch"

    artifact_path = (candidate_root / manifest.artifact_filename).resolve()
    if artifact_path.parent != candidate_root or not artifact_path.is_file():
        return None, f"{source_path}:unverifiable_cost_scenario:artifact_missing_or_uncontrolled"
    try:
        actual_artifact_hash = _sha256_file(artifact_path)
    except OSError as exc:
        return (
            None,
            f"{source_path}:unverifiable_cost_scenario:artifact_unreadable:"
            f"{type(exc).__name__}",
        )
    if actual_artifact_hash != manifest.artifact_hash:
        return None, f"{source_path}:unverifiable_cost_scenario:artifact_hash_mismatch"

    evaluation = candidate_metadata.get("evaluation")
    if not isinstance(evaluation, Mapping):
        return None, f"{source_path}:unverifiable_cost_scenario:candidate_evaluation_missing"
    expected_freeze_hash = candidate_freeze_hash(
        candidate_id=str(candidate_metadata.get("candidate_id") or ""),
        dataset_hash=str(candidate_metadata.get("dataset_hash") or ""),
        manifest_hash=str(candidate_metadata.get("manifest_hash") or ""),
        artifact_hash=str(candidate_metadata.get("artifact_hash") or ""),
        evaluation=evaluation,
    )
    if expected_freeze_hash != candidate_metadata.get("candidate_freeze_hash"):
        return None, f"{source_path}:unverifiable_cost_scenario:candidate_freeze_hash_mismatch"

    try:
        fixed_value = _metadata_int_or_none(candidate_metadata.get("fixed_round_trip_cost_bp"))
        scenario = cost_scenario_from_metadata(
            candidate_metadata,
            fixed_round_trip_cost_bp=fixed_value,
        )
    except (TypeError, ValueError, RecommendationCostScenarioError) as exc:
        return (
            None,
            f"{source_path}:unverifiable_cost_scenario:"
            f"candidate_cost_scenario_invalid:{type(exc).__name__}:{exc}",
        )
    expected_flat_metadata = {
        "cost_scenario_id": scenario.scenario_id,
        "cost_scenario_version": scenario.scenario_version,
        "cost_scenario_hash": scenario.scenario_hash,
        "cost_basis": scenario.cost_basis,
        "fixed_round_trip_cost_bp": scenario.fixed_round_trip_cost_bp,
        "cost_policy_id": scenario.policy_id,
        "cost_policy_version": scenario.policy_version,
        "policy_estimate_date": scenario.policy_estimate_date,
        "research_order_amount_twd": (
            str(scenario.research_order_amount_twd)
            if scenario.research_order_amount_twd is not None
            else None
        ),
        "research_order_quantity_shares": scenario.research_order_quantity_shares,
        "lot_type": scenario.lot_type,
        "instrument_type": scenario.instrument_type,
    }
    if scenario.is_estimated:
        required_cost_keys = ("cost_scenario", *expected_flat_metadata)
        missing_cost_keys = [
            key for key in required_cost_keys if key not in candidate_metadata
        ]
        if missing_cost_keys:
            return (
                None,
                f"{source_path}:unverifiable_cost_scenario:incomplete_candidate_cost_metadata:"
                f"{','.join(missing_cost_keys)}",
            )
        expected_nested = scenario.metadata()
        if candidate_metadata.get("cost_scenario") != expected_nested:
            return None, f"{source_path}:unverifiable_cost_scenario:nested_cost_scenario_mismatch"
    elif "fixed_round_trip_cost_bp" not in candidate_metadata:
        return None, f"{source_path}:unverifiable_cost_scenario:legacy_fixed_cost_missing"
    for key, expected in expected_flat_metadata.items():
        if key in candidate_metadata and candidate_metadata.get(key) != expected:
            return (
                None,
                f"{source_path}:unverifiable_cost_scenario:flat_cost_metadata_mismatch:{key}",
            )
    expected_cost_contract_hash = recommendation_cost_contract_hash(
        scenario.fixed_round_trip_cost_bp,
        cost_scenario=scenario if scenario.is_estimated else None,
    )
    if candidate_metadata.get("cost_contract_hash") != expected_cost_contract_hash:
        return None, f"{source_path}:unverifiable_cost_scenario:cost_contract_hash_mismatch"
    expected_label_registry_hash = recommendation_label_registry_hash(
        cost_scenario=scenario if scenario.is_estimated else None
    )
    if candidate_metadata.get("label_registry_hash") != expected_label_registry_hash:
        return None, f"{source_path}:unverifiable_cost_scenario:label_registry_hash_mismatch"
    return scenario, None


def _is_sha256_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value[len("sha256:") :]
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _cost_scenario_root_conflict(
    output_root: Path,
    requested_scenario: RecommendationCostScenario,
) -> str | None:
    """Reject a second cost lane from reusing shared authority state.

    Run/dataset scopes already include the scenario identity, but the active
    pointer, challenger pointer, decision receipts, and latest status are
    intentionally shared legacy paths.  A mismatched lane must therefore use
    another explicit output root; silently replacing those files would make a
    fixed-cost champion appear to belong to an estimated-cost experiment (or
    the reverse).  A legacy marker missing only its marker-level freeze hash
    is accepted only after a same-cohort full-freeze anchor and the immutable
    latest-status receipt agree on candidate identity and path.
    """

    root = Path(output_root).resolve() / "recommendation_learning"
    marker_paths: list[Path] = [
        root / "recommendation-calibration-active-pointer.json",
        root / "challenger" / "current.json",
        root / "latest_status.json",
    ]
    decisions_root = root / "decisions"
    if decisions_root.is_dir():
        marker_paths.extend(sorted(decisions_root.glob("recommendation-calibration-*.json"))[:256])
    seen: set[str] = set()
    unverified_legacy_markers: list[Path] = []
    verified_markers: list[
        tuple[
            Path,
            RecommendationCostScenario,
            tuple[str, str, str, str, str, str] | None,
            bool,
        ]
    ] = []
    for marker_path in marker_paths:
        if not marker_path.is_file():
            continue
        try:
            raw = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return (
                "cost_scenario_root_conflict:existing_marker_unreadable:"
                f"{marker_path}:{type(exc).__name__}"
            )
        if not isinstance(raw, Mapping):
            return f"cost_scenario_root_conflict:existing_marker_invalid:{marker_path}"
        payload = dict(raw)
        if _is_unverifiable_legacy_decision_receipt(payload) or (
            marker_path == root / "recommendation-calibration-active-pointer.json"
            and _is_unverifiable_rule_only_pointer(payload)
        ):
            unverified_legacy_markers.append(marker_path)
            continue
        receipt_anchor_payload: Mapping[str, Any] | None = None
        receipt_anchor_path: Path | None = None
        receipt_anchor_scenario: RecommendationCostScenario | None = None
        scenario, error = _stored_cost_scenario(
            payload,
            source_path=marker_path,
            allow_legacy_marker_missing_freeze=True,
        )
        if error is not None or scenario is None:
            return f"cost_scenario_root_conflict:{error or marker_path}"
        if marker_path == root / "latest_status.json":
            (
                receipt_anchor_path,
                receipt_anchor_payload,
                receipt_anchor_scenario,
                receipt_error,
            ) = _load_latest_status_receipt_anchor(
                payload,
                scenario=scenario,
                source_path=marker_path,
            )
            if receipt_error is not None:
                return f"cost_scenario_root_conflict:{receipt_error}"
        marker_missing_freeze = (
            payload.get("candidate_freeze_hash") in (None, "")
            and payload.get("candidate_root") not in (None, "")
        )
        marker_anchor, anchor_error = _candidate_marker_anchor(
            payload,
            source_path=marker_path,
            require_cohort=marker_missing_freeze,
        )
        if anchor_error is not None:
            return f"cost_scenario_root_conflict:{anchor_error}"
        verified_markers.append(
            (marker_path, scenario, marker_anchor, marker_missing_freeze)
        )
        if (
            receipt_anchor_path is not None
            and receipt_anchor_payload is not None
            and receipt_anchor_scenario is not None
        ):
            receipt_missing_freeze = (
                receipt_anchor_payload.get("candidate_freeze_hash") in (None, "")
                and receipt_anchor_payload.get("candidate_root") not in (None, "")
            )
            receipt_anchor, receipt_anchor_error = _candidate_marker_anchor(
                receipt_anchor_payload,
                source_path=receipt_anchor_path,
                require_cohort=receipt_missing_freeze,
            )
            if receipt_anchor_error is not None:
                return f"cost_scenario_root_conflict:{receipt_anchor_error}"
            if marker_anchor != receipt_anchor:
                return (
                    "cost_scenario_root_conflict:latest_status_receipt_anchor_"
                    f"mismatch:{marker_path}:{receipt_anchor_path}"
                )
            marker_freeze = payload.get("candidate_freeze_hash")
            receipt_freeze = receipt_anchor_payload.get("candidate_freeze_hash")
            if (
                marker_freeze not in (None, "")
                and receipt_freeze not in (None, "")
                and str(marker_freeze) != str(receipt_freeze)
            ):
                return (
                    "cost_scenario_root_conflict:latest_status_receipt_candidate_"
                    f"freeze_hash_mismatch:{marker_path}:{receipt_anchor_path}"
                )
            verified_markers.append(
                (
                    receipt_anchor_path,
                    receipt_anchor_scenario,
                    receipt_anchor,
                    receipt_missing_freeze,
                )
            )
        marker_identity = scenario.scenario_hash
        if marker_identity in seen:
            continue
        seen.add(marker_identity)
        if marker_identity != requested_scenario.scenario_hash:
            return (
                "cost_scenario_root_conflict:shared_authority_state_belongs_to_"
                f"{scenario.scenario_id}:{scenario.scenario_hash}; requested="
                f"{requested_scenario.scenario_id}:{requested_scenario.scenario_hash}; "
                "use a different --output-root for an isolated cost lane"
            )
    for marker_path, scenario, marker_anchor, needs_cross_anchor in verified_markers:
        if not needs_cross_anchor:
            continue
        if marker_anchor is None or not any(
            peer_path != marker_path
            and not peer_needs_cross_anchor
            and peer_anchor is not None
            and peer_anchor == marker_anchor
            and peer_scenario.scenario_hash == scenario.scenario_hash
            for peer_path, peer_scenario, peer_anchor, peer_needs_cross_anchor in verified_markers
        ):
            return (
                "cost_scenario_root_conflict:legacy_marker_missing_candidate_"
                "freeze_hash_requires_verified_same_cohort_anchor:"
                f"{marker_path}"
            )
    if unverified_legacy_markers:
        if requested_scenario.is_estimated:
            return (
                "cost_scenario_root_conflict:legacy_decision_receipt_is_unverifiable_"
                "and_may_belong_to_legacy_fixed_lane:"
                f"{unverified_legacy_markers[0]}"
            )
        if not verified_markers:
            return (
                "cost_scenario_root_conflict:legacy_decision_receipt_requires_"
                "verified_same_lane_anchor:"
                f"{unverified_legacy_markers[0]}"
            )
        if not any(
            scenario.scenario_hash == requested_scenario.scenario_hash
            for _, scenario, _, _ in verified_markers
        ):
            return (
                "cost_scenario_root_conflict:legacy_decision_receipt_has_no_"
                "verified_same_lane_anchor:"
                f"{unverified_legacy_markers[0]}"
            )
    return None


def _is_rule_only_pointer_capture_lane_conflict(
    output_root: Path,
    requested_scenario: RecommendationCostScenario,
    conflict: str | None,
) -> bool:
    """Allow only current-observed collection beside a lone legacy rule pointer.

    This does not establish a formal cost-lane anchor.  It only permits the
    isolated G9 observation path; callers must keep historical training and
    promotion blocked for the invocation.
    """

    prefix = (
        "cost_scenario_root_conflict:legacy_decision_receipt_requires_"
        "verified_same_lane_anchor:"
    )
    if conflict is None or not conflict.startswith(prefix) or requested_scenario.is_estimated:
        return False

    output = Path(output_root).resolve()
    learning_root = output / "recommendation_learning"
    pointer_path = learning_root / "recommendation-calibration-active-pointer.json"
    reported_marker = conflict[len(prefix) :]
    try:
        if Path(reported_marker).resolve(strict=False) != pointer_path.resolve(strict=False):
            return False
        if pointer_path.is_symlink() or not pointer_path.is_file():
            return False
        # Any other authority or decision marker makes this broader than the
        # specifically authorized rule-only bootstrap case.
        if (learning_root / "challenger" / "current.json").exists():
            return False
        if (learning_root / "latest_status.json").exists():
            return False
        decisions_root = learning_root / "decisions"
        if decisions_root.is_symlink():
            return False
        if decisions_root.is_dir() and next(decisions_root.iterdir(), None) is not None:
            return False
        pointer_bytes = _read_regular_file_no_follow(
            pointer_path,
            output,
            max_bytes=256 * 1024,
        )
        payload = json.loads(pointer_bytes.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(payload, Mapping) and _is_unverifiable_rule_only_pointer(payload)


def _candidate_marker_anchor(
    payload: Mapping[str, Any],
    *,
    source_path: Path,
    require_cohort: bool,
) -> tuple[tuple[str, str, str, str, str, str] | None, str | None]:
    """Return the identity/cohort anchor used for legacy compatibility.

    A missing-freeze marker may only be accepted when the remaining candidate
    identity and its run scope can be compared with a separate full-freeze
    marker.  Full historical pointers may omit ``run_scope`` and therefore
    return no cross-anchor value; their existing candidate-root validation
    remains unchanged.
    """

    candidate_id = payload.get("candidate_id")
    candidate_root_value = payload.get("candidate_root")
    candidate_manifest_hash = payload.get("candidate_manifest_hash")
    candidate_artifact_hash = payload.get("candidate_artifact_hash")
    dataset_marker_key = (
        "candidate_dataset_hash"
        if payload.get("candidate_dataset_hash") not in (None, "")
        else "dataset_hash"
    )
    candidate_dataset_hash = payload.get(dataset_marker_key)
    missing = [
        key
        for key, value in (
            ("candidate_id", candidate_id),
            ("candidate_root", candidate_root_value),
            ("candidate_manifest_hash", candidate_manifest_hash),
            ("candidate_artifact_hash", candidate_artifact_hash),
            (dataset_marker_key, candidate_dataset_hash),
        )
        if value in (None, "")
    ]
    run_scope = payload.get("run_scope")
    if require_cohort and run_scope in (None, ""):
        missing.append("run_scope")
    if missing:
        if require_cohort:
            return (
                None,
                f"{source_path}:unverifiable_cost_scenario:incomplete_candidate_anchor:"
                f"{','.join(missing)}",
            )
        return None, None
    if run_scope in (None, ""):
        return None, None
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        return None, f"{source_path}:unverifiable_cost_scenario:invalid_candidate_anchor:candidate_id"
    if not isinstance(candidate_root_value, (str, Path)) or not str(candidate_root_value).strip():
        return None, f"{source_path}:unverifiable_cost_scenario:invalid_candidate_anchor:candidate_root"
    if not _is_sha256_digest(candidate_manifest_hash):
        return None, (
            f"{source_path}:unverifiable_cost_scenario:invalid_candidate_anchor:"
            "candidate_manifest_hash"
        )
    if not _is_sha256_digest(candidate_artifact_hash):
        return None, (
            f"{source_path}:unverifiable_cost_scenario:invalid_candidate_anchor:"
            "candidate_artifact_hash"
        )
    if not _is_sha256_digest(candidate_dataset_hash):
        return None, (
            f"{source_path}:unverifiable_cost_scenario:invalid_candidate_anchor:"
            f"{dataset_marker_key}"
        )
    if not isinstance(run_scope, str) or not run_scope.strip():
        return None, f"{source_path}:unverifiable_cost_scenario:invalid_candidate_anchor:run_scope"
    try:
        canonical_candidate_root = str(Path(str(candidate_root_value)).expanduser().resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        return (
            None,
            f"{source_path}:unverifiable_cost_scenario:invalid_candidate_anchor:"
            f"candidate_root:{type(exc).__name__}",
        )
    return (
        (
            candidate_id,
            canonical_candidate_root,
            str(candidate_manifest_hash),
            str(candidate_artifact_hash),
            str(candidate_dataset_hash),
            run_scope,
        ),
        None,
    )


def _is_unverifiable_legacy_decision_receipt(payload: Mapping[str, Any]) -> bool:
    """Identify the pre-cost decision shape without treating it as authority."""

    if payload.get("schema_version") != "recommendation-calibration-decision-receipt.v2":
        return False
    if payload.get("candidate_root"):
        return False
    return not any(
        payload.get(key) not in (None, "")
        for key in (
            "cost_scenario",
            "cost_scenario_id",
            "cost_scenario_version",
            "cost_scenario_hash",
            "cost_basis",
            "fixed_round_trip_cost_bp",
            "cost_policy_id",
            "cost_policy_version",
            "policy_estimate_date",
            "research_order_amount_twd",
            "research_order_quantity_shares",
            "lot_type",
            "instrument_type",
        )
    )


def _is_unverifiable_rule_only_pointer(payload: Mapping[str, Any]) -> bool:
    """Identify an old rule-only pointer that carries no lane identity."""

    if payload.get("schema_version") != "recommendation-calibration-active-pointer.v2":
        return False
    if payload.get("status") != "rule_only" or payload.get("candidate_root"):
        return False
    return not any(
        payload.get(key) not in (None, "")
        for key in (
            "cost_scenario",
            "cost_scenario_id",
            "cost_scenario_version",
            "cost_scenario_hash",
            "cost_basis",
            "fixed_round_trip_cost_bp",
            "cost_policy_id",
            "cost_policy_version",
            "policy_estimate_date",
            "research_order_amount_twd",
            "research_order_quantity_shares",
            "lot_type",
            "instrument_type",
        )
    )


def _load_latest_status_receipt_anchor(
    payload: Mapping[str, Any],
    *,
    scenario: RecommendationCostScenario,
    source_path: Path,
) -> tuple[
    Path | None,
    Mapping[str, Any] | None,
    RecommendationCostScenario | None,
    str | None,
]:
    """Load and validate the immutable receipt referenced by latest status."""

    if payload.get("schema_version") != "daily-recommendation-learning-receipt.v1":
        return None, None, None, None
    receipt_value = payload.get("receipt_path")
    if not isinstance(receipt_value, str) or not receipt_value.strip():
        return (
            None,
            None,
            None,
            f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_missing",
        )
    receipt_path = Path(receipt_value).expanduser().resolve()
    try:
        receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return (
            None,
            None,
            None,
            f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_unreadable:"
            f"{type(exc).__name__}",
        )
    if not isinstance(receipt_payload, Mapping):
        return (
            None,
            None,
            None,
            f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_invalid",
        )
    if str(receipt_payload.get("receipt_path") or "") != str(receipt_path):
        return (
            None,
            None,
            None,
            f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_identity_mismatch",
        )
    receipt_scenario, error = _stored_cost_scenario(
        receipt_payload,
        source_path=receipt_path,
        allow_legacy_marker_missing_freeze=True,
    )
    if error is not None or receipt_scenario is None:
        return (
            receipt_path,
            receipt_payload,
            None,
            error or f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_lane_missing",
        )
    if receipt_scenario.scenario_hash != scenario.scenario_hash:
        return (
            receipt_path,
            receipt_payload,
            receipt_scenario,
            f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_lane_mismatch",
        )
    if receipt_payload.get("formal_order_allowed") is not False:
        return (
            receipt_path,
            receipt_payload,
            receipt_scenario,
            f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_formal_flag_invalid",
        )
    if receipt_payload.get("shadow_only") is not True:
        return (
            receipt_path,
            receipt_payload,
            receipt_scenario,
            f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_shadow_flag_invalid",
        )
    return receipt_path, receipt_payload, receipt_scenario, None


def _verify_latest_status_receipt_anchor(
    payload: Mapping[str, Any],
    *,
    scenario: RecommendationCostScenario,
    source_path: Path,
) -> str | None:
    """Ensure latest-status lane metadata is backed by its immutable receipt."""

    _, _, _, error = _load_latest_status_receipt_anchor(
        payload,
        scenario=scenario,
        source_path=source_path,
    )
    return error


def _scenario_cli_metadata(scenario: RecommendationCostScenario) -> dict[str, Any]:
    """Expose the requested lane in preflight failures without extra writes."""

    return {
        "cost_scenario": scenario.metadata(),
        "cost_scenario_id": scenario.scenario_id,
        "cost_scenario_version": scenario.scenario_version,
        "cost_scenario_hash": scenario.scenario_hash,
        "cost_basis": scenario.cost_basis,
        "fixed_round_trip_cost_bp": scenario.fixed_round_trip_cost_bp,
        "cost_policy_id": scenario.policy_id,
        "cost_policy_version": scenario.policy_version,
        "policy_estimate_date": scenario.policy_estimate_date,
        "research_order_amount_twd": (
            str(scenario.research_order_amount_twd)
            if scenario.research_order_amount_twd is not None
            else None
        ),
        "research_order_quantity_shares": scenario.research_order_quantity_shares,
        "lot_type": scenario.lot_type,
        "instrument_type": scenario.instrument_type,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        research_invocation = parse_current_restated_research_invocation(args)
    except (CurrentRestatedResearchError, OSError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "daily-recommendation-learning-research-only.v1",
                    "status": "blocked",
                    "reason": "current_restated_research_input_invalid",
                    "error": f"{type(exc).__name__}: {exc}",
                    "model_training_performed": False,
                    "verified_model_reused": False,
                    "formal_calibration_performed": False,
                    "formal_order_allowed": False,
                    "shadow_only": True,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    if research_invocation is not None:
        return _run_current_restated_research_entry(
            args,
            invocation=research_invocation,
            actual_invocation=list(sys.argv if argv is None else [sys.argv[0], *argv]),
        )
    checked_clock = _taipei_now()
    config_kwargs: dict[str, Any] = {}
    if args.data_root is not None:
        config_kwargs["data_root"] = args.data_root
    if args.output_root is not None:
        # Keep the operational source-contract audit and the learning shadow
        # on the same explicitly selected root.  Without this binding, the
        # CLI could write learning artifacts to one root while auditing the
        # default formal output root.
        config_kwargs["output_root"] = args.output_root
    config = TWStockConfig(**config_kwargs)
    # A generic OUTPUT_ROOT may still own the scheduled recommendation
    # snapshot used for symbol resolution.  Keep that snapshot input and the
    # source-custody input separate from the selected learning output root;
    # an explicit --symbols bypasses snapshot lookup entirely.
    scheduled_snapshot_output_root = (
        args.snapshot_output_root
        or Path(os.environ.get("OUTPUT_ROOT", str(config.output_root)))
    ).expanduser().resolve()
    current_observed_source_output_root = (
        args.current_observed_source_output_root
        or Path(
            os.environ.get(
                "CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT",
                str(config.data_root / "output"),
            )
        )
    ).expanduser().resolve()
    source_artifact_root = (
        args.source_artifact_root or config.output_root
    ).expanduser().resolve()
    snapshot_cohort: dict[str, Any] | None = None
    snapshot_source_binding: dict[str, Any] | None = None
    run_scope: str | None = None
    capture_scope: str | None = None
    experiment_scope: str | None = None
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
        else checked_clock.date()
    )
    try:
        effective_fixed_cost, cost_scenario = _cost_scenario_from_args(args)
    except (TypeError, ValueError, RecommendationCostScenarioError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "daily-recommendation-learning-cli-result.v3",
                    "status": "failed",
                    "decision": "retain_current",
                    "decision_reason": "cost_scenario_invalid",
                    "decision_date": decision_day.isoformat(),
                    "error": f"{type(exc).__name__}: {exc}",
                    "formal_order_allowed": False,
                    "shadow_only": True,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    root_conflict = _cost_scenario_root_conflict(
        learning_output_root,
        cost_scenario,
    )
    capture_only_legacy_rule_pointer = False
    if root_conflict is not None:
        capture_only_legacy_rule_pointer = (
            decision_day == checked_clock.astimezone(TAIPEI).date()
            and _is_rule_only_pointer_capture_lane_conflict(
                learning_output_root,
                cost_scenario,
                root_conflict,
            )
        )
        if not capture_only_legacy_rule_pointer:
            print(
                json.dumps(
                    {
                        "schema_version": "daily-recommendation-learning-cli-result.v3",
                        "status": "failed",
                        "decision": "retain_current",
                        "decision_reason": "cost_scenario_root_conflict",
                        "decision_date": decision_day.isoformat(),
                        "output_root": str(learning_output_root),
                        "error": root_conflict,
                        **_scenario_cli_metadata(cost_scenario),
                        "formal_order_allowed": False,
                        "shadow_only": True,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 2
    try:
        if args.symbols is None:
            symbols, snapshot_cohort, snapshot_source_binding = (
                _resolve_same_run_snapshot_input(
                    output_root=scheduled_snapshot_output_root,
                    decision_date=decision_day,
                    result_id=args.snapshot_result_id,
                    expected_cohort_hash=args.snapshot_cohort_hash,
                    expected_invocation_output_sha256=(
                        args.snapshot_invocation_output_sha256
                    ),
                    invocation_output_path=args.snapshot_invocation_output_path,
                )
            )
            symbol_source = (
                "scheduled_recommendation_snapshot:"
                f"{snapshot_source_binding['result_id']}:eligible"
            )
            effective_policy = RecommendationPromotionPolicy()
            experiment_scope = _scheduled_experiment_scope(
                fixed_round_trip_cost_bp=effective_fixed_cost,
                cost_scenario=cost_scenario,
                policy=effective_policy,
                feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
            )
            run_scope = _scheduled_run_scope(
                symbols=symbols,
                snapshot_cohort=snapshot_cohort,
                fixed_round_trip_cost_bp=effective_fixed_cost,
                cost_scenario=cost_scenario,
                policy=effective_policy,
                feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
            )
            capture_scope = _scheduled_capture_scope(
                symbols=symbols,
                snapshot_cohort=snapshot_cohort,
                cost_scenario=cost_scenario,
            )
        else:
            symbols, symbol_source = _resolve_symbols(
                output_root=scheduled_snapshot_output_root,
                explicit_symbols=args.symbols,
                decision_date=decision_day,
            )
            experiment_scope = _explicit_experiment_scope(
                symbols,
                fixed_round_trip_cost_bp=effective_fixed_cost,
                cost_scenario=cost_scenario,
                policy=RecommendationPromotionPolicy(),
                feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
            )
            capture_scope = _capture_scope_token(None, symbols)
    except (ValueError, ExecutionPersistenceError) as exc:
        runner = _build_runner(
            learning_output_root,
            effective_fixed_cost,
            cost_scenario=cost_scenario,
            data_root=config.data_root,
        )
        dependencies = _dependency_failure(
            reason=f"symbol_cohort_preflight_failed:{type(exc).__name__}",
            data_status="failed",
            outcome_status="failed",
            drift_status="not_checked",
            recovery_policy="recoverable_attempt",
        )
        run_result = runner.run(
            decision_date=decision_day.isoformat(),
            samples=(),
            natural_evidence=None,
            data_dependency_status="failed",
            outcome_dependency_status="failed",
            drift_status="not_checked",
            emergency_rollback=False,
            dependency_failure_reason=f"symbol_cohort_preflight_failed:{type(exc).__name__}",
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
                    symbol_coverage=None,
                    run_scope=None,
                    cost_scenario=cost_scenario,
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
        fixed_round_trip_cost_bp=effective_fixed_cost,
        cost_scenario=cost_scenario,
        max_decision_dates=args.max_decision_dates,
        selection_policy=args.replay_selection_policy,
    )
    current_observed_feature_snapshot = _current_observed_feature_snapshot_for_learning(
        canonical_output_root=current_observed_source_output_root,
        config=config,
        decision_date=decision_day,
        history_start_date=replay_config.history_start_date,
        symbols=symbols,
        observed_at=checked_clock,
        expected_raw_run_id=args.current_observed_expected_raw_run_id,
        expected_cycle_terminal_path=args.current_observed_expected_cycle_terminal,
        expected_cycle_terminal_sha256=args.current_observed_expected_cycle_terminal_sha256,
        calendar_cache_path=args.calendar_cache_path,
        temporary_closure_path=args.temporary_closure_cache_path,
        snapshot_cohort=snapshot_cohort,
        snapshot_source_binding=snapshot_source_binding,
    )
    source_contract_audit = _audit_source_contract(
        data_root=config.data_root,
        output_root=source_artifact_root,
        source_db=source_db,
        learning_output_root=learning_output_root,
        decision_date=decision_day,
        symbols=symbols,
        fixed_round_trip_cost_bp=effective_fixed_cost,
        cost_scenario=cost_scenario,
        history_start_date=replay_config.history_start_date,
        replay_start_date=replay_config.replay_start_date,
        replay_end_date=replay_config.replay_end_date,
        availability_cutoff_at=checked_clock.isoformat(timespec="seconds"),
        current_observed_snapshot=current_observed_feature_snapshot,
    )
    runner = _build_runner(
        learning_output_root,
        effective_fixed_cost,
        cost_scenario=cost_scenario,
        data_root=config.data_root,
    )
    if args.emergency_rollback:
        dependencies = _dependency_failure(
            reason="explicit_emergency_rollback_requested",
            data_status="failed",
            outcome_status="failed",
            drift_status="drifted",
            recovery_policy="explicit_emergency_rollback",
        )
        dependencies.update(source_contract_audit)
        run_result = runner.run(
            decision_date=decision_day.isoformat(),
            run_scope=run_scope,
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
                    symbol_coverage=snapshot_cohort,
                    run_scope=run_scope,
                    cost_scenario=cost_scenario,
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if capture_only_legacy_rule_pointer:
        rule_only_current_input_capture = _persist_current_observed_input_capture(
            output_root=learning_output_root,
            source_contract_audit=source_contract_audit,
            decision_date=decision_day,
            captured_at=checked_clock,
            cost_scenario=cost_scenario,
            fixed_round_trip_cost_bp=effective_fixed_cost,
        )
        rule_only_current_natural_research: dict[str, Any] = {
            "status": "pending",
            "reason": "current_observed_research_not_run",
            "scope": "current_observed_natural_research_only",
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
            "promotion_credit_created": False,
        }
        try:
            calendar_cache_path, temporary_closure_path = _natural_maturity_calendar_paths(
                calendar_cache_path=args.calendar_cache_path,
                temporary_closure_path=args.temporary_closure_cache_path,
            )
            current_only_resolver = NaturalMaturitySessionResolver(
                db_path=source_db,
                calendar_cache_path=calendar_cache_path,
                temporary_closure_path=temporary_closure_path,
            )
            rule_only_current_natural_research = _current_observed_natural_research_fit(
                learning_output_root=learning_output_root,
                data_root=config.data_root,
                source_db=source_db,
                source_contract_audit=source_contract_audit,
                current_feature_snapshot=current_observed_feature_snapshot,
                decision_date=decision_day,
                evaluation_at=checked_clock,
                fixed_round_trip_cost_bp=effective_fixed_cost,
                cost_scenario=cost_scenario,
                session_resolver=current_only_resolver,
            )
        except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
            rule_only_current_natural_research = {
                **rule_only_current_natural_research,
                "status": "blocked",
                "reason": f"current_observed_natural_research_failed:{type(exc).__name__}",
            }
        dependencies = _dependency_failure(
            reason=root_conflict or "legacy_rule_only_pointer_capture_lane",
            data_status="failed",
            outcome_status="failed",
            drift_status="not_checked",
            recovery_policy="recoverable_attempt",
        )
        dependencies.update(source_contract_audit)
        dependencies.update(
            {
                "formal_cost_lane_status": "blocked_legacy_rule_only_pointer_has_no_cost_anchor",
                "formal_training_allowed": False,
                "historical_pit_eligible": False,
                "current_observed_capture_only": True,
                "current_observed_input_capture": rule_only_current_input_capture,
                "current_observed_natural_research": rule_only_current_natural_research,
            }
        )
        run_result = runner.run(
            decision_date=decision_day.isoformat(),
            run_scope=run_scope,
            samples=(),
            natural_evidence=None,
            data_dependency_status="failed",
            outcome_dependency_status="failed",
            drift_status="not_checked",
            emergency_rollback=False,
            dependency_failure_reason=root_conflict,
        )
        payload = _cli_payload(
            output_root=learning_output_root,
            decision_day=decision_day,
            symbols=symbols,
            symbol_source=symbol_source,
            replay_result=None,
            manifest_path=None,
            dependencies=dependencies,
            run_result=run_result,
            natural_result={
                "status": "not_run",
                "reason": "formal_cost_lane_conflict_keeps_historical_training_blocked",
                "matured_sample_count": 0,
                "historical_replay_is_natural_evidence": False,
            },
            active_natural_result={
                "status": "not_run",
                "reason": "legacy_rule_only_pointer_has_no_active_model",
            },
            live_capture={
            "status": rule_only_current_input_capture.get("status", "pending"),
            "feature_source_mode": "current_observed",
            "current_observed_input_capture": rule_only_current_input_capture,
            "current_observed_natural_research": rule_only_current_natural_research,
                "historical_pit_training": "blocked",
                "training_run": "not_run",
            },
            error=root_conflict,
            recoverable=True,
            symbol_coverage=snapshot_cohort,
            run_scope=run_scope,
            capture_scope=capture_scope,
            experiment_scope=experiment_scope,
            cost_scenario=cost_scenario,
        )
        payload["current_observed_capture_only_due_to_legacy_rule_pointer"] = True
        payload["formal_cost_lane_status"] = "blocked"
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2
    try:
        provider = MLHistoricalSnapshotProvider(source_db)
        replay_result = RecommendationHistoricalReplayService(provider).build(replay_config)
        manifest_path = replay_result.persist(learning_output_root)
    except (OSError, RuntimeError, ValueError, TypeError, sqlite3.Error) as exc:
        preflight_reason = f"replay_or_source_preflight_failed:{type(exc).__name__}"
        emergency_from_preflight = _preflight_requires_emergency(exc)
        if isinstance(exc, DailyPriceSourceRevisionError):
            # Historical PIT and current natural evidence are separate lanes.
            # A market revision blocks replay/training, but it does not make
            # immutable active-model receipts unreadable.  Inspect those
            # receipts and any due natural evidence before returning; never
            # feed natural samples into training on this branch.
            is_current_evaluation = (
                decision_day == checked_clock.astimezone(TAIPEI).date()
            )
            live_capture: dict[str, Any] = {
                "status": "pending",
                "reason": "current_observed_feature_source_not_verified",
                "capture_eligible": False,
            }
            current_observed_input_capture: dict[str, Any] = {
                "status": "pending",
                "reason": "current_observed_feature_source_not_verified",
                "capture_eligible": False,
            }
            if is_current_evaluation:
                current_observed_input_capture = _persist_current_observed_input_capture(
                    output_root=learning_output_root,
                    source_contract_audit=source_contract_audit,
                    decision_date=decision_day,
                    captured_at=checked_clock,
                    cost_scenario=cost_scenario,
                    fixed_round_trip_cost_bp=effective_fixed_cost,
                )
                current_binding, current_binding_reason = _capture_source_contract_binding(
                    source_contract_audit
                )
                current_inputs = _current_observed_capture_inputs(
                    current_observed_feature_snapshot,
                    decision_date=decision_day,
                )
                if current_binding is not None and current_inputs:
                    live_capture = _capture_active_model_monitor(
                        output_root=learning_output_root,
                        data_root=config.data_root,
                        decision_date=decision_day,
                        captured_at=checked_clock.isoformat(),
                        inputs=current_inputs,
                        fixed_round_trip_cost_bp=effective_fixed_cost,
                        cost_scenario=cost_scenario,
                        source_contract_binding=current_binding,
                    )
                    live_capture["current_observed_input_capture"] = current_observed_input_capture
                    live_capture["feature_source_mode"] = "current_observed"
                    live_capture["cycle_id"] = current_observed_feature_snapshot.get("cycle_id")
                    live_capture["feature_snapshot_sha256"] = current_observed_feature_snapshot.get(
                        "content_sha256"
                    )
                else:
                    live_capture = {
                        "status": "pending",
                        "reason": current_binding_reason
                        or str(current_observed_feature_snapshot.get("reason") or "current_observed_features_missing"),
                        "capture_eligible": False,
                        "feature_source_mode": "current_observed",
                        "feature_snapshot_status": current_observed_feature_snapshot.get("status"),
                        "current_observed_input_capture": current_observed_input_capture,
                    }
                calendar_cache_path, temporary_closure_path = _natural_maturity_calendar_paths(
                    calendar_cache_path=args.calendar_cache_path,
                    temporary_closure_path=args.temporary_closure_cache_path,
                )
                revision_maturity_resolver = NaturalMaturitySessionResolver(
                    db_path=source_db,
                    calendar_cache_path=calendar_cache_path,
                    temporary_closure_path=temporary_closure_path,
                )
                active_natural_result = _scan_active_model_evidence(
                    output_root=learning_output_root,
                    data_root=config.data_root,
                    provider=provider,
                    source_db=source_db,
                    decision_date=decision_day,
                    active_capture_result=None,
                    session_resolver=revision_maturity_resolver,
                    evaluation_at=checked_clock,
                )
                active_performance = _inspect_active_model_performance(
                    output_root=learning_output_root,
                    data_root=config.data_root,
                    decision_date=decision_day,
                    policy=RecommendationPromotionPolicy(),
                    source_db=source_db,
                )
                current_observed_natural_research: dict[str, Any] = {
                    "status": "pending",
                    "reason": "current_evaluation_date_required",
                    "scope": "current_observed_natural_research_only",
                    "historical_pit_eligible": False,
                    "formal_training_allowed": False,
                    "promotion_credit_created": False,
                }
                if is_current_evaluation:
                    try:
                        current_observed_natural_research = _current_observed_natural_research_fit(
                            learning_output_root=learning_output_root,
                            data_root=config.data_root,
                            source_db=source_db,
                            source_contract_audit=source_contract_audit,
                            current_feature_snapshot=current_observed_feature_snapshot,
                            decision_date=decision_day,
                            evaluation_at=checked_clock,
                            fixed_round_trip_cost_bp=effective_fixed_cost,
                            cost_scenario=cost_scenario,
                            session_resolver=revision_maturity_resolver,
                        )
                    except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as fit_exc:
                        current_observed_natural_research = {
                            "status": "blocked",
                            "reason": f"current_observed_natural_research_failed:{type(fit_exc).__name__}",
                            "scope": "current_observed_natural_research_only",
                            "historical_pit_eligible": False,
                            "formal_training_allowed": False,
                            "promotion_credit_created": False,
                        }
                if str(active_natural_result.get("status")) == "failed":
                    active_performance = {
                        **active_performance,
                        "status": "failed",
                        "reason": "active_model_natural_evidence_integrity_failure",
                        "diagnostics": tuple(active_performance.get("diagnostics", ()))
                        + ("active_model_natural_evidence_failed_fail_closed",),
                    }
            else:
                active_natural_result = {
                    "schema_version": "recommendation-natural-outcome-result.v1",
                    "status": "pending",
                    "reason": "natural_maturity_evaluation_date_mismatch",
                    "capture_paths": [],
                    "evaluation_date": decision_day.isoformat(),
                    "matured_sample_count": 0,
                    "evidence": None,
                    "diagnostics": [
                        "historical_decision_date_natural_lane_skipped_to_avoid_future_clock"
                    ],
                    "historical_replay_is_natural_evidence": False,
                }
                active_performance = {
                    "status": "pending",
                    "reason": "natural_maturity_evaluation_date_mismatch",
                    "diagnostics": (
                        "historical_decision_date_natural_lane_skipped_to_avoid_future_clock",
                    ),
                }
                current_observed_natural_research = {
                    "status": "pending",
                    "reason": "current_evaluation_date_required",
                    "scope": "current_observed_natural_research_only",
                    "historical_pit_eligible": False,
                    "formal_training_allowed": False,
                    "promotion_credit_created": False,
                }
            dependencies = _dependency_failure(
                reason=preflight_reason,
                data_status="failed",
                outcome_status="failed",
                drift_status=str(active_performance.get("status") or "not_checked"),
                recovery_policy=(
                    "fail_closed_emergency_rollback"
                    if emergency_from_preflight
                    else "recoverable_attempt"
                ),
            )
            dependencies.update(source_contract_audit)
            dependencies["model_performance"] = active_performance
            dependencies["active_natural_result"] = active_natural_result
            dependencies["current_observed_input_capture"] = current_observed_input_capture
            dependencies["current_observed_natural_research"] = current_observed_natural_research
            dependencies["diagnostics"] = list(
                dict.fromkeys(
                    [
                        preflight_reason,
                        "historical_pit_blocked_training_not_run",
                        "active_natural_evidence_checked_without_training",
                    ]
                    + [
                        str(item)
                        for item in active_performance.get("diagnostics", ())
                        if str(item).strip()
                    ]
                )
            )
            run_result = runner.run(
                decision_date=decision_day.isoformat(),
                run_scope=run_scope,
                samples=(),
                natural_evidence=None,
                data_dependency_status="failed",
                outcome_dependency_status="failed",
                drift_status=str(active_performance.get("status") or "not_checked"),
                emergency_rollback=(
                    emergency_from_preflight
                    or str(active_performance.get("status")) in {"failed", "missing", "unavailable", "degraded", "drifted"}
                ),
                dependency_failure_reason=preflight_reason,
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
                        natural_result={
                            "status": "pending",
                            "reason": "historical_pit_blocked_training_not_run",
                            "matured_sample_count": 0,
                            "historical_replay_is_natural_evidence": False,
                        },
                        active_natural_result=active_natural_result,
                        live_capture={
                            **live_capture,
                            "current_observed_natural_research": current_observed_natural_research,
                            "historical_pit_training": "blocked",
                            "training_run": "not_run",
                        },
                        error=f"{type(exc).__name__}: {exc}",
                        recoverable=not emergency_from_preflight,
                        symbol_coverage=snapshot_cohort,
                        run_scope=run_scope,
                        cost_scenario=cost_scenario,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 2
        dependencies = _dependency_failure(
            reason=preflight_reason,
            data_status="failed",
            outcome_status="failed",
            drift_status="not_checked",
            recovery_policy=(
                "fail_closed_emergency_rollback"
                if emergency_from_preflight
                else "recoverable_attempt"
            ),
        )
        dependencies.update(source_contract_audit)
        run_result = runner.run(
            decision_date=decision_day.isoformat(),
            run_scope=run_scope,
            samples=(),
            natural_evidence=None,
            data_dependency_status="failed",
            outcome_dependency_status="failed",
            drift_status="not_checked",
            emergency_rollback=emergency_from_preflight,
            dependency_failure_reason=preflight_reason,
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
                    symbol_coverage=snapshot_cohort,
                    run_scope=run_scope,
                    cost_scenario=cost_scenario,
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
        source_contract_audit=source_contract_audit,
        checked_clock=checked_clock,
        calendar_cache_path=args.calendar_cache_path,
        temporary_closure_path=args.temporary_closure_cache_path,
    )
    challenger_payload = _read_challenger_pointer(learning_output_root)
    challenger_path = _load_frozen_challenger(learning_output_root)
    # The experiment scope controls the frozen challenger.  Daily cohort
    # changes only affect the receipt/capture scope, so a scheduled challenger
    # can accumulate natural observations across different symbol sets while
    # a manual trial can never be reused by the normal lane.
    if experiment_scope is not None:
        challenger_scope = (
            str(challenger_payload.get("experiment_scope") or "")
            if isinstance(challenger_payload, Mapping)
            else ""
        )
        if challenger_scope != experiment_scope:
            challenger_path = None
    natural_training_samples = _load_natural_training_samples(
        output_root=learning_output_root,
        challenger_payload=challenger_payload,
        feature_count=len(CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids),
        fixed_round_trip_cost_bp=effective_fixed_cost,
        cost_scenario=cost_scenario,
        training_as_of=training_as_of,
        data_root=config.data_root,
        source_db=source_db,
    )
    training_samples = _merge_samples(replay_result.samples, natural_training_samples)
    training_lineage_sources = {
        "replay": tuple(replay_result.samples),
        "natural": tuple(natural_training_samples),
    }
    source_contract = dependencies.get("source_contract")
    source_contract = source_contract if isinstance(source_contract, Mapping) else {}
    quality = _build_training_quality(
        replay_result=replay_result,
        source_contract=source_contract,
        manifest_path=manifest_path,
        symbol_source=symbol_source,
        natural_training_sample_count=len(natural_training_samples),
        replay_selection_policy=replay_config.selection_policy,
        dependency_check=dependencies,
    )
    emergency_from_preflight = _dependencies_require_emergency(dependencies)
    historical_bootstrap: dict[str, Any] = {
        "status": "not_triggered",
        "policy": "no label-aware date selection",
    }
    run_result = runner.run(
        decision_date=decision_day.isoformat(),
        run_scope=run_scope,
        samples=training_samples,
        natural_evidence=None,
        data_dependency_status=dependencies["data_status"],
        outcome_dependency_status=dependencies["outcome_status"],
        drift_status=dependencies["drift_status"],
        dataset_quality=quality,
        training_as_of=training_as_of,
        frozen_candidate_root=challenger_path,
        emergency_rollback=emergency_from_preflight,
        lineage_sources=training_lineage_sources,
    )
    if args.symbols is None and _should_expand_historical_bootstrap(run_result):
        bootstrap_max_dates = min(max(args.max_decision_dates * 3, 300), 500)
        initial_seen_decision_dates = tuple(
            sorted({str(value)[:10] for value in replay_result.decision_dates if str(value).strip()})
        )
        bootstrap_config = replace(
            replay_config,
            max_decision_dates=bootstrap_max_dates,
            selection_policy="time_stratified_eligible_dates",
        )
        historical_bootstrap = {
            "status": "attempted",
            "trigger": str(run_result.reason),
            "initial_max_decision_dates": args.max_decision_dates,
            "bootstrap_max_decision_dates": bootstrap_max_dates,
            "selection_policy": bootstrap_config.selection_policy,
            "selection_basis": (
                "date-only evenly spaced maturable trading dates; no labels or holdout metrics used"
            ),
            "initial_replay_dataset_id": replay_result.dataset_id,
            "initial_replay_sample_count": _replay_sample_count(replay_result),
            "initial_seen_decision_date_count": len(initial_seen_decision_dates),
            "initial_seen_decision_date_start": (
                initial_seen_decision_dates[0] if initial_seen_decision_dates else None
            ),
            "initial_seen_decision_date_end": (
                initial_seen_decision_dates[-1] if initial_seen_decision_dates else None
            ),
        }
        try:
            if not initial_seen_decision_dates:
                raise RuntimeError("historical_bootstrap_requires_initial_seen_decision_dates")
            initial_boundary = date.fromisoformat(initial_seen_decision_dates[0])
            boundary_candidates = tuple(
                str(value)[:10]
                for value in provider.list_trading_dates(
                    start_date=replay_config.replay_start_date,
                    end_date=(initial_boundary - timedelta(days=1)).isoformat(),
                    symbols=replay_config.symbols,
                )
            )
            embargo_date_count = replay_config.horizon_trading_days
            if len(boundary_candidates) <= embargo_date_count:
                raise RuntimeError("historical_bootstrap_has_no_causal_pre_boundary_window")
            bootstrap_end_date = boundary_candidates[-(embargo_date_count + 1)]
            bootstrap_config = replace(
                bootstrap_config,
                replay_end_date=bootstrap_end_date,
            )
            historical_bootstrap.update(
                {
                    "bootstrap_replay_end_date": bootstrap_end_date,
                    "untouched_boundary_policy": (
                        "bootstrap uses only dates strictly before the initial observed replay window; "
                        "a 20-trading-day causal label/embargo gap is reserved before that boundary"
                    ),
                    "reserved_causal_embargo_trading_days": embargo_date_count,
                    "boundary_candidate_trading_date_count": len(boundary_candidates),
                }
            )
            bootstrap_replay_result = RecommendationHistoricalReplayService(provider).build(
                bootstrap_config
            )
            bootstrap_seen_decision_dates = tuple(
                sorted({str(value)[:10] for value in bootstrap_replay_result.decision_dates})
            )
            date_overlap = sorted(
                set(initial_seen_decision_dates).intersection(bootstrap_seen_decision_dates)
            )
            initial_seen_rows = {
                (str(row.symbol).strip(), str(row.decision_date)[:10], str(row.label_end_date)[:10])
                for row in replay_result.samples
            }
            bootstrap_seen_rows = {
                (str(row.symbol).strip(), str(row.decision_date)[:10], str(row.label_end_date)[:10])
                for row in bootstrap_replay_result.samples
            }
            row_overlap = sorted(initial_seen_rows.intersection(bootstrap_seen_rows))
            crossing_rows = sorted(
                {
                    (str(row.symbol).strip(), str(row.decision_date)[:10], str(row.label_end_date)[:10])
                    for row in bootstrap_replay_result.samples
                    if str(row.label_end_date)[:10] >= initial_seen_decision_dates[0]
                }
            )
            if date_overlap or row_overlap or crossing_rows:
                raise RuntimeError(
                    "historical_bootstrap_seen_data_overlap:"
                    f"dates={len(date_overlap)}:rows={len(row_overlap)}:crossing_labels={len(crossing_rows)}"
                )
            historical_bootstrap.update(
                {
                    "initial_bootstrap_decision_date_overlap_count": len(date_overlap),
                    "initial_bootstrap_row_overlap_count": len(row_overlap),
                    "bootstrap_rows_crossing_initial_boundary_count": len(crossing_rows),
                    "bootstrap_seen_decision_date_count": len(bootstrap_seen_decision_dates),
                    "bootstrap_seen_decision_date_start": (
                        bootstrap_seen_decision_dates[0] if bootstrap_seen_decision_dates else None
                    ),
                    "bootstrap_seen_decision_date_end": (
                        bootstrap_seen_decision_dates[-1] if bootstrap_seen_decision_dates else None
                    ),
                }
            )
            bootstrap_manifest_path = bootstrap_replay_result.persist(learning_output_root)
            bootstrap_quality = _build_training_quality(
                replay_result=bootstrap_replay_result,
                source_contract=source_contract,
                manifest_path=bootstrap_manifest_path,
                symbol_source=symbol_source,
                natural_training_sample_count=len(natural_training_samples),
                replay_selection_policy=bootstrap_config.selection_policy,
                dependency_check=dependencies,
            )
            bootstrap_quality["historical_bootstrap"] = dict(historical_bootstrap)
            bootstrap_training_samples = _merge_samples(
                bootstrap_replay_result.samples,
                natural_training_samples,
            )
            bootstrap_run_result = runner.run(
                decision_date=decision_day.isoformat(),
                run_scope=run_scope,
                samples=bootstrap_training_samples,
                natural_evidence=None,
                data_dependency_status=dependencies["data_status"],
                outcome_dependency_status=dependencies["outcome_status"],
                drift_status=dependencies["drift_status"],
                dataset_quality=bootstrap_quality,
                training_as_of=training_as_of,
                frozen_candidate_root=challenger_path,
                emergency_rollback=emergency_from_preflight,
                lineage_sources={
                    "bootstrap_replay": tuple(bootstrap_replay_result.samples),
                    "natural": tuple(natural_training_samples),
                },
            )
            replay_result = bootstrap_replay_result
            replay_config = bootstrap_config
            manifest_path = bootstrap_manifest_path
            training_samples = bootstrap_training_samples
            training_lineage_sources = {
                "bootstrap_replay": tuple(bootstrap_replay_result.samples),
                "natural": tuple(natural_training_samples),
            }
            quality = bootstrap_quality
            run_result = bootstrap_run_result
            historical_bootstrap.update(
                {
                    "status": "completed",
                    "replay_dataset_id": bootstrap_replay_result.dataset_id,
                    "replay_sample_count": _replay_sample_count(bootstrap_replay_result),
                    "replay_decision_date_count": len(bootstrap_replay_result.decision_dates),
                    "replay_date_start": (
                        bootstrap_replay_result.decision_dates[0]
                        if bootstrap_replay_result.decision_dates
                        else None
                    ),
                    "replay_date_end": (
                        bootstrap_replay_result.decision_dates[-1]
                        if bootstrap_replay_result.decision_dates
                        else None
                    ),
                    "replay_coverage": dict(bootstrap_replay_result.coverage),
                    "replay_diagnostics": list(bootstrap_replay_result.diagnostics),
                    "training_status": bootstrap_run_result.status,
                    "training_reason": bootstrap_run_result.reason,
                    "replay_manifest_path": str(bootstrap_manifest_path),
                    "training_receipt_path": bootstrap_run_result.receipt_path,
                }
            )
        except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
            historical_bootstrap.update(
                {
                    "status": "failed",
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
    if run_result.candidate_root and run_result.candidate_id:
        challenger_path = _ensure_challenger_pointer(
            output_root=learning_output_root,
            run_result=run_result,
            cost_scenario=cost_scenario,
            status="pending",
            natural_result=None,
            retrain_trigger=(
                "source_or_active_model_fault_recovery"
                if emergency_from_preflight
                else "new_candidate_frozen"
            ),
            run_scope=run_scope,
            experiment_scope=experiment_scope,
        )

    capture_result = _capture_current_if_requested(
        args=args,
        config=config,
        output_root=learning_output_root,
        source_db=source_db,
        provider=provider,
        symbols=symbols,
        run_result=run_result,
        run_scope=run_scope,
        capture_scope=capture_scope,
        replay_config=replay_config,
        source_contract_audit=source_contract_audit,
        cost_scenario=cost_scenario,
        observed_at=checked_clock,
    )
    capture_failure, capture_recoverable = _capture_dependency_failure(capture_result)
    current_observed_natural_lane = _run_current_observed_natural_research_lane(
        learning_output_root=learning_output_root,
        data_root=config.data_root,
        source_db=source_db,
        source_contract_audit=source_contract_audit,
        current_feature_snapshot=current_observed_feature_snapshot,
        decision_date=decision_day,
        evaluation_at=checked_clock,
        fixed_round_trip_cost_bp=effective_fixed_cost,
        cost_scenario=cost_scenario,
        capture_requested=args.capture_current,
        calendar_cache_path=args.calendar_cache_path,
        temporary_closure_path=args.temporary_closure_cache_path,
    )
    capture_result = dict(capture_result)
    capture_result["current_observed_input_capture"] = current_observed_natural_lane[
        "current_observed_input_capture"
    ]
    capture_result["current_observed_natural_research"] = current_observed_natural_lane[
        "current_observed_natural_research"
    ]

    calendar_cache_path, temporary_closure_path = _natural_maturity_calendar_paths(
        calendar_cache_path=args.calendar_cache_path,
        temporary_closure_path=args.temporary_closure_cache_path,
    )
    natural_maturity_resolver = NaturalMaturitySessionResolver(
        db_path=source_db,
        calendar_cache_path=calendar_cache_path,
        temporary_closure_path=temporary_closure_path,
    )
    natural_maturity_context = _natural_maturity_context(
        source_db=source_db,
        calendar_cache_path=calendar_cache_path,
        temporary_closure_path=temporary_closure_path,
        evaluation_at=checked_clock,
        evaluation_date=decision_day,
    )

    natural_maturity_date_matches = (
        decision_day == checked_clock.astimezone(TAIPEI).date()
    )
    if natural_maturity_date_matches:
        active_natural_result = _scan_active_model_evidence(
            output_root=learning_output_root,
            data_root=config.data_root,
            provider=provider,
            source_db=source_db,
            decision_date=decision_day,
            active_capture_result=capture_result.get("active_model_monitor")
            if isinstance(capture_result, Mapping)
            else None,
            session_resolver=natural_maturity_resolver,
            evaluation_at=checked_clock,
        )
    else:
        active_natural_result = {
            "schema_version": "recommendation-natural-outcome-result.v1",
            "status": "pending",
            "reason": "natural_maturity_evaluation_date_mismatch",
            "capture_path": str(
                Path(learning_output_root).resolve()
                / "recommendation_learning"
                / "active_captures"
            ),
            "capture_paths": [],
            "evaluation_date": decision_day.isoformat(),
            "matured_sample_count": 0,
            "evidence": None,
            "diagnostics": [
                "historical_decision_date_natural_lane_skipped_to_avoid_future_clock"
            ],
            "historical_replay_is_natural_evidence": False,
        }
    active_natural_result = _annotate_natural_result(
        active_natural_result,
        natural_maturity_context,
    )

    # The preflight check intentionally runs before today's capture/evidence
    # scan.  Re-read the active monitor after that scan so a newly matured
    # receipt can trigger the same day's fail-closed rollback.  A stale
    # preflight status must never delay a rollback until tomorrow.
    if natural_maturity_date_matches:
        post_scan_active_performance = _inspect_active_model_performance(
            output_root=learning_output_root,
            data_root=config.data_root,
            decision_date=decision_day,
            policy=RecommendationPromotionPolicy(),
            source_db=source_db,
        )
    else:
        post_scan_active_performance = {
            "status": "pending",
            "reason": "natural_maturity_evaluation_date_mismatch",
            "diagnostics": (
                "historical_decision_date_natural_lane_skipped_to_avoid_future_clock",
            ),
        }
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
        "status": "not_run" if natural_maturity_date_matches else "pending",
        "reason": (
            "candidate_not_available"
            if natural_maturity_date_matches
            else "natural_maturity_evaluation_date_mismatch"
        ),
        "matured_sample_count": 0,
        "evidence": None,
        "diagnostics": [],
    }
    automatic_evidence = None
    if (
        natural_maturity_date_matches
        and run_result.candidate_id
        and run_result.candidate_root
    ):
        evidence_path = (
            Path(learning_output_root)
            / "recommendation_learning"
            / "evidence"
            / run_result.candidate_id
            / f"{decision_day.isoformat()}.json"
        )
        natural_result = _build_natural_outcome_service(
            provider=provider,
            source_db=source_db,
            session_resolver=natural_maturity_resolver,
            evaluation_at=checked_clock,
        ).scan_and_build_evidence(
            output_root=learning_output_root,
            evaluation_date=decision_day.isoformat(),
            output_path=evidence_path,
            candidate_id=run_result.candidate_id,
            candidate_freeze_hash=_candidate_freeze(run_result.candidate_root),
            required_source_contract=source_contract_audit,
        ).to_dict()
        evidence_payload = natural_result.get("evidence")
        if isinstance(evidence_payload, Mapping):
            automatic_evidence = evidence_payload
    natural_result = _annotate_natural_result(
        natural_result,
        natural_maturity_context,
    )

    if automatic_evidence is not None or emergency_after_scan != emergency_from_preflight:
        run_result = runner.run(
            decision_date=decision_day.isoformat(),
            run_scope=run_scope,
            samples=training_samples,
            natural_evidence=automatic_evidence,
            data_dependency_status=dependencies["data_status"],
            outcome_dependency_status=dependencies["outcome_status"],
            drift_status=dependencies["drift_status"],
            dataset_quality=quality,
            training_as_of=training_as_of,
            frozen_candidate_root=run_result.candidate_root,
            emergency_rollback=emergency_after_scan,
            lineage_sources=training_lineage_sources,
        )
    if args.symbols is None and historical_bootstrap.get("status") == "not_triggered":
        recovered_bootstrap = _recover_historical_bootstrap_metadata(
            learning_output_root=learning_output_root,
            decision_day=decision_day,
            run_scope=run_scope,
            initial_replay_result=replay_result,
            run_result=run_result,
        )
        if recovered_bootstrap is not None:
            historical_bootstrap = recovered_bootstrap
    if (
        natural_maturity_date_matches
        and run_result.candidate_id
        and run_result.candidate_root
    ):
        challenger_status = _challenger_status(run_result, natural_result)
        challenger_path = _ensure_challenger_pointer(
            output_root=learning_output_root,
            run_result=run_result,
            cost_scenario=cost_scenario,
            status=challenger_status,
            natural_result=natural_result,
            retrain_trigger=(
                "adopted_active_champion"
                if challenger_status == "active"
                else "retired_after_qualified_no_improvement"
                if challenger_status == "retired"
                else "awaiting_natural_maturity"
            ),
            run_scope=run_scope,
            experiment_scope=experiment_scope,
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
        error=capture_failure,
        symbol_coverage=snapshot_cohort,
        run_scope=run_scope,
        capture_scope=capture_scope,
        experiment_scope=experiment_scope,
        recoverable=capture_recoverable,
        cost_scenario=cost_scenario,
        natural_maturity_context=natural_maturity_context,
    )
    payload["snapshot_source_binding"] = snapshot_source_binding
    payload["current_observed_natural_lane"] = current_observed_natural_lane
    payload["natural_evidence_supplied"] = automatic_evidence is not None
    payload["ignored_caller_inputs"] = ignored_inputs
    payload["training_sample_count"] = len(training_samples)
    if historical_bootstrap.get("status") in {"completed", "recovered_completed"}:
        bootstrap_sample_count = historical_bootstrap.get("replay_sample_count")
        if isinstance(bootstrap_sample_count, int):
            payload["training_sample_count"] = bootstrap_sample_count + len(natural_training_samples)
    payload["natural_training_sample_count"] = len(natural_training_samples)
    payload["training_as_of"] = training_as_of
    payload["historical_bootstrap"] = historical_bootstrap
    _update_latest_status(
        run_result.latest_status_path,
        payload,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 2 if capture_failure is not None else 0


def _build_runner(
    output_root: Path,
    fixed_round_trip_cost_bp: int | None,
    *,
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
    data_root: Path | None = None,
) -> DailyRecommendationLearningRunner:
    return DailyRecommendationLearningRunner(
        output_root=output_root,
        data_root=data_root,
        feature_names=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids,
        feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        cost_scenario=cost_scenario,
        training_config=RecommendationCalibrationTrainingConfig(),
    )


def _resolve_current_observed_learning_dates(
    *,
    decision_date: date,
    observed_at: datetime,
    source_db: Path,
    calendar_cache_path: Path,
    temporary_closure_path: Path | None,
) -> tuple[str, str, Mapping[str, Any] | None]:
    """Resolve the G6 source cycle separately from the prior feature session."""

    source_cycle_date = expected_current_observed_source_date(
        decision_date=decision_date,
        observed_at=observed_at,
        source_db=source_db,
        calendar_cache_path=calendar_cache_path,
        temporary_closure_path=temporary_closure_path,
    )
    if date.fromisoformat(source_cycle_date) > decision_date:
        raise ValueError("current-observed raw source date is after the decision date")

    calendar = OfficialTradingCalendar(
        db_path=source_db,
        calendar_cache_path=calendar_cache_path,
        temporary_closure_path=temporary_closure_path,
    )
    feature_session = calendar.get_recent_official_trading_days(
        decision_date - timedelta(days=1),
        1,
        include_reference=True,
        allow_online_probe=False,
    )[-1]
    feature_as_of = str(feature_session["date_str"])
    if date.fromisoformat(feature_as_of) >= decision_date:
        raise ValueError("current-observed feature date is not strictly before decision date")

    decision_session = calendar.get_recent_official_trading_days(
        decision_date,
        1,
        include_reference=True,
        allow_online_probe=False,
    )[-1]
    decision_session_evidence: Mapping[str, Any] | None = None
    if (
        source_cycle_date == decision_date.isoformat()
        and str(decision_session.get("date_str") or "") == decision_date.isoformat()
    ):
        evidence = decision_session.get("evidence")
        if isinstance(evidence, Mapping):
            decision_session_evidence = evidence
    return source_cycle_date, feature_as_of, decision_session_evidence


def _current_observed_raw_cycle_discovery_problem(
    payload: Mapping[str, Any],
    *,
    canonical_output_root: Path,
    expected_source_date: str,
    expected_raw_run_id: str | None = None,
    expected_cycle_terminal_path: Path | None = None,
    expected_cycle_terminal_sha256: str | None = None,
) -> str | None:
    """Validate a blocked formal raw run with an independently completed G6 child."""

    output_root = canonical_output_root.resolve()
    if (
        payload.get("schema_version") != "ml-raw-pit-refresh-status.v1"
        or not _current_observed_raw_status_is_eligible(payload)
        or str(payload.get("output_root") or "") != str(output_root)
    ):
        return "canonical_raw_status_schema_status_or_root_mismatch"
    raw_run_id = payload.get("run_id")
    child = payload.get("current_stock_research_cycle")
    if not isinstance(raw_run_id, str) or not raw_run_id.strip() or not isinstance(child, Mapping):
        return "canonical_raw_status_has_no_exact_current_stock_cycle"
    supplied_identity = (
        expected_raw_run_id,
        expected_cycle_terminal_path,
        expected_cycle_terminal_sha256,
    )
    supplied_count = sum(item is not None for item in supplied_identity)
    if supplied_count not in {0, 3}:
        return "expected_current_stock_cycle_identity_is_incomplete"
    if supplied_count == 3:
        assert expected_raw_run_id is not None
        assert expected_cycle_terminal_path is not None
        assert expected_cycle_terminal_sha256 is not None
        if raw_run_id != expected_raw_run_id:
            return "canonical_raw_status_run_differs_from_expected_run"
        reported_terminal = child.get("terminal_receipt_path")
        reported_sha256 = child.get("terminal_receipt_sha256")
        if (
            not isinstance(reported_terminal, str)
            or not reported_terminal.strip()
            or not isinstance(reported_sha256, str)
            or not _is_sha256_digest(reported_sha256)
            or not _is_sha256_digest(expected_cycle_terminal_sha256)
        ):
            return "expected_current_stock_cycle_terminal_pin_is_invalid"
        try:
            reported_path = Path(reported_terminal).expanduser().resolve(strict=True)
            expected_path = expected_cycle_terminal_path.expanduser().resolve(strict=True)
        except (OSError, RuntimeError, TypeError, ValueError):
            return "expected_current_stock_cycle_terminal_path_is_unreadable"
        if reported_path != expected_path:
            return "canonical_raw_status_terminal_path_differs_from_expected_terminal"
        if reported_sha256 != expected_cycle_terminal_sha256:
            return "canonical_raw_status_terminal_sha_differs_from_expected_terminal"
    child_status = str(child.get("status") or "")
    if (
        child_status not in {"completed", "skipped_same_inputs"}
        or child.get("raw_run_id") != raw_run_id
        or child.get("source_date") != expected_source_date
        or payload.get("latest_core_date") != expected_source_date
        or payload.get("source_date") not in (None, expected_source_date)
    ):
        return "current_stock_cycle_is_not_the_expected_successful_or_verified_reuse_raw_run"
    return None


def _partition_current_observed_learning_scope(
    symbols: tuple[str, ...],
    *,
    snapshot_cohort: Mapping[str, Any] | None,
    snapshot_source_binding: Mapping[str, Any] | None,
) -> tuple[tuple[str, ...], ...]:
    """Partition a bounded scope and require exact saved cohort identity above 16."""

    partitions = partition_current_observed_symbols(symbols)
    ordered_symbols = tuple(symbol for batch in partitions for symbol in batch)
    if ordered_symbols != symbols:
        raise ValueError("current-observed symbols must be sorted and unique")
    if len(symbols) <= 16:
        return partitions
    if not isinstance(snapshot_cohort, Mapping) or not isinstance(snapshot_source_binding, Mapping):
        raise ValueError("17..50 symbols require a verified scheduled snapshot cohort")
    cohort_symbols = snapshot_cohort.get("eligible_symbols")
    cohort_hash = snapshot_cohort.get("cohort_hash")
    source_root = snapshot_source_binding.get("snapshot_output_root")
    if (
        snapshot_cohort.get("schema_version") != "scheduled-recommendation-snapshot-cohort.v1"
        or cohort_symbols != list(symbols)
        or snapshot_cohort.get("eligible_count") != len(symbols)
        or type(cohort_hash) is not str
        or not _is_sha256_text(cohort_hash)
        or snapshot_source_binding.get("cohort_hash") != cohort_hash
    ):
        raise ValueError("verified scheduled snapshot cohort does not match the full symbol scope")
    if type(source_root) is not str or not source_root.strip():
        raise ValueError("verified snapshot binding lacks its exact artifact output root")
    root_path = Path(source_root)
    if not root_path.is_absolute() or str(root_path.resolve()) != source_root:
        raise ValueError("verified snapshot artifact root is not a canonical absolute path")
    return partitions


def _current_observed_feature_snapshot_for_learning(
    *,
    canonical_output_root: Path,
    config: TWStockConfig,
    decision_date: date,
    history_start_date: str,
    symbols: tuple[str, ...],
    observed_at: datetime,
    expected_raw_run_id: str | None = None,
    expected_cycle_terminal_path: Path | None = None,
    expected_cycle_terminal_sha256: str | None = None,
    calendar_cache_path: Path | None = None,
    temporary_closure_path: Path | None = None,
    snapshot_cohort: Mapping[str, Any] | None = None,
    snapshot_source_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a current-only feature snapshot from one exact successful G6 cycle.

    This lane is a dated research observation. It never upgrades historical PIT
    or formal-training eligibility. Its feature date is strictly before the
    decision date; the exact G6 raw-cycle date follows the shared publication
    cutoff and is resolved separately.
    """

    def pending(reason: str, **details: Any) -> dict[str, Any]:
        return {
            "schema_version": "recommendation-current-observed-feature-snapshot.v1",
            "status": "pending",
            "verified": False,
            "reason": reason,
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
            "research_only": True,
            **details,
        }

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        return pending("current_observation_clock_not_timezone_aware")
    if (
        not isinstance(expected_raw_run_id, str)
        or not expected_raw_run_id.strip()
        or expected_cycle_terminal_path is None
        or not isinstance(expected_cycle_terminal_sha256, str)
        or not _is_sha256_digest(expected_cycle_terminal_sha256)
    ):
        return pending("current_stock_cycle_exact_waited_identity_missing")
    observed_utc = observed_at.astimezone(timezone.utc)
    if observed_utc > datetime.now(timezone.utc):
        return pending("current_observation_clock_is_future")
    if observed_at.astimezone(TAIPEI).date() != decision_date:
        return pending("current_observation_date_differs_from_decision_date")
    raw_symbols = tuple(str(item).strip() for item in symbols if str(item).strip())
    normalized_symbols = tuple(sorted(set(raw_symbols)))
    if len(raw_symbols) != len(normalized_symbols):
        return pending("current_observed_symbol_scope_contains_duplicates")
    try:
        symbol_batches = _partition_current_observed_learning_scope(
            normalized_symbols,
            snapshot_cohort=snapshot_cohort,
            snapshot_source_binding=snapshot_source_binding,
        )
    except (TypeError, ValueError) as exc:
        return pending(
            "current_observed_symbol_scope_or_snapshot_binding_invalid",
            requested_symbol_count=len(normalized_symbols),
            error_type=type(exc).__name__,
            diagnostic=str(exc),
        )

    calendar_path, closure_path = _natural_maturity_calendar_paths(
        calendar_cache_path=calendar_cache_path,
        temporary_closure_path=temporary_closure_path,
    )
    try:
        source_cycle_date, expected_feature_as_of, decision_session_evidence = (
            _resolve_current_observed_learning_dates(
                decision_date=decision_date,
                observed_at=observed_at,
                source_db=Path(getattr(config, "db_file")),
                calendar_cache_path=calendar_path,
                temporary_closure_path=closure_path,
            )
        )
    except (IndexError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return pending(
            "official_calendar_could_not_resolve_current_and_prior_sessions",
            error_type=type(exc).__name__,
        )

    output_root = canonical_output_root.resolve()
    status_path = output_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"
    try:
        status_bytes = _read_regular_file_no_follow(
            status_path,
            output_root,
            max_bytes=8 * 1024 * 1024,
        )
        status_payload = json.loads(status_bytes.decode("utf-8"))
    except (OSError, RuntimeError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return pending(
            "canonical_raw_status_missing_or_unreadable",
            status_path=str(status_path),
            error_type=type(exc).__name__,
        )
    if not isinstance(status_payload, Mapping):
        return pending("canonical_raw_status_root_is_not_an_object", status_path=str(status_path))
    status_sha256 = "sha256:" + hashlib.sha256(status_bytes).hexdigest()
    discovery_problem = _current_observed_raw_cycle_discovery_problem(
        status_payload,
        canonical_output_root=output_root,
        expected_source_date=source_cycle_date,
        expected_raw_run_id=expected_raw_run_id,
        expected_cycle_terminal_path=expected_cycle_terminal_path,
        expected_cycle_terminal_sha256=expected_cycle_terminal_sha256,
    )
    if discovery_problem is not None:
        return pending(
            discovery_problem,
            status_path=str(status_path),
            discovery_status_sha256=status_sha256,
        )
    raw_run_id = status_payload.get("run_id")
    child = status_payload.get("current_stock_research_cycle")
    assert isinstance(raw_run_id, str) and isinstance(child, Mapping)
    child_status = str(child.get("status") or "")
    capacity_block_exception = (
        classify_current_observed_raw_status(status_payload) == "blocked_insufficient_storage"
    )
    formal_output_root = status_payload.get("output_root")
    if capacity_block_exception and (
        not isinstance(formal_output_root, str) or not formal_output_root.strip()
    ):
        return pending("formal_capacity_exception_output_root_missing")

    discovery_terminal_path_value = child.get("terminal_receipt_path")
    discovery_terminal_sha256 = child.get("terminal_receipt_sha256")
    if not isinstance(discovery_terminal_path_value, str) or not discovery_terminal_path_value:
        return pending("current_stock_cycle_terminal_path_missing")
    if not _is_sha256_text(discovery_terminal_sha256):
        return pending("current_stock_cycle_terminal_sha256_invalid")
    try:
        discovery_terminal_path = resolve_ml_research_output_path(
            Path(discovery_terminal_path_value),
            repository_root=ROOT,
            access="read",
        )
        accepted_research_roots = (
            get_ml_research_root(repository_root=ROOT),
            resolve_ml_research_output_path(
                ROOT / "output" / "ml_research",
                repository_root=ROOT,
                access="read",
            ),
        )
        research_root = next(
            root
            for root in accepted_research_roots
            if discovery_terminal_path.is_relative_to(root)
        )
        discovery_terminal_bytes = _read_regular_file_no_follow(
            discovery_terminal_path,
            research_root,
            max_bytes=8 * 1024 * 1024,
        )
        actual_discovery_terminal_sha256 = "sha256:" + hashlib.sha256(discovery_terminal_bytes).hexdigest()
        discovery_terminal_payload = json.loads(discovery_terminal_bytes.decode("utf-8"))
    except (OSError, RuntimeError, TypeError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return pending(
            "current_stock_cycle_discovery_terminal_missing_or_unverifiable",
            terminal_path=discovery_terminal_path_value,
            error_type=type(exc).__name__,
        )
    if (
        actual_discovery_terminal_sha256 != discovery_terminal_sha256
        or not isinstance(discovery_terminal_payload, Mapping)
        or discovery_terminal_payload.get("schema_version") != "current-stock-research-cycle-terminal.v1"
        or discovery_terminal_payload.get("status") != child_status
        or discovery_terminal_payload.get("raw_run_id") != raw_run_id
        or discovery_terminal_payload.get("cycle_id") != raw_run_id
        or discovery_terminal_payload.get("source_date") != source_cycle_date
    ):
        return pending(
            "current_stock_cycle_discovery_terminal_identity_or_hash_mismatch",
            terminal_path=str(discovery_terminal_path),
            expected_terminal_sha256=discovery_terminal_sha256,
            actual_terminal_sha256=actual_discovery_terminal_sha256,
        )

    reuse_source_identity: Mapping[str, Any] | None = None
    terminal_research_root: Path | None = None
    if child_status == "skipped_same_inputs":
        try:
            reuse_source_identity = verify_current_observed_cycle_reuse(
                reuse_terminal_path=discovery_terminal_path,
                reuse_terminal_sha256=str(discovery_terminal_sha256),
                expected_raw_run_id=str(raw_run_id),
                expected_source_date=source_cycle_date,
                require_original_capacity=capacity_block_exception,
                formal_output_root=(formal_output_root if capacity_block_exception else None),
            )
            terminal_path = Path(str(reuse_source_identity["original_terminal_path"]))
            terminal_sha256 = str(reuse_source_identity["original_terminal_sha256"])
            original_research_root = next(
                (
                    root
                    for root in accepted_research_roots
                    if terminal_path.is_relative_to(root)
                ),
                None,
            )
            if original_research_root is None:
                raise ValueError("verified original terminal is outside approved research roots")
            terminal_research_root = original_research_root
            terminal_bytes = _read_regular_file_no_follow(
                terminal_path,
                original_research_root,
                max_bytes=8 * 1024 * 1024,
            )
            actual_terminal_sha256 = "sha256:" + hashlib.sha256(terminal_bytes).hexdigest()
            terminal_payload = json.loads(terminal_bytes.decode("utf-8"))
            if (
                actual_terminal_sha256 != terminal_sha256
                or not isinstance(terminal_payload, Mapping)
                or terminal_payload.get("status") != "completed"
            ):
                raise ValueError("verified reuse did not resolve to its exact completed source cycle")
        except (OSError, RuntimeError, TypeError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            return pending(
                "current_stock_cycle_reuse_chain_revalidation_failed",
                error_type=type(exc).__name__,
            )
    else:
        terminal_path = discovery_terminal_path
        terminal_research_root = research_root
        terminal_sha256 = str(discovery_terminal_sha256)
        actual_terminal_sha256 = actual_discovery_terminal_sha256
        terminal_bytes = discovery_terminal_bytes
        terminal_payload = discovery_terminal_payload

    if terminal_research_root is None:
        return pending("current_stock_cycle_terminal_has_no_approved_research_root")

    if capacity_block_exception and child_status == "completed":
        if not current_stock_research_capacity_passed(
            terminal_payload,
            expected_raw_run_id=raw_run_id,
            expected_source_date=source_cycle_date,
            formal_output_root=str(formal_output_root),
            expected_research_root=terminal_research_root,
        ):
            return pending("current_stock_cycle_capacity_proof_invalid_under_formal_block")

    if (
        terminal_payload.get("status") != "completed"
        or terminal_payload.get("source_date") != source_cycle_date
        or terminal_payload.get("raw_run_id") != terminal_payload.get("cycle_id")
        or (
            reuse_source_identity is None
            and terminal_payload.get("raw_run_id") != raw_run_id
        )
        or (
            reuse_source_identity is not None
            and (
                terminal_payload.get("raw_run_id") != reuse_source_identity.get("original_raw_run_id")
                or terminal_payload.get("cycle_id") != reuse_source_identity.get("original_cycle_id")
            )
        )
    ):
        return pending("current_stock_cycle_source_terminal_identity_mismatch")

    pins = terminal_payload.get("same_run_pins")
    if not isinstance(pins, Mapping):
        return pending("current_stock_cycle_terminal_exact_snapshot_pins_missing")
    source_cycle_id = str(terminal_payload.get("cycle_id") or "")
    source_raw_run_id = str(terminal_payload.get("raw_run_id") or "")
    if not source_cycle_id or not source_raw_run_id:
        return pending("current_stock_cycle_source_terminal_run_identity_missing")
    required_pin_fields = (
        "snapshot_database_path",
        "snapshot_database_sha256",
        "snapshot_receipt_path",
        "snapshot_receipt_sha256",
        "source_context_envelope_path",
        "source_context_envelope_sha256",
        "snapshot_completed_at",
        "revision_dependencies_verified_at",
        "current_restated_training_as_of",
    )
    if any(pins.get(field) in (None, "") for field in required_pin_fields):
        return pending("current_stock_cycle_terminal_exact_snapshot_pins_incomplete")
    context_snapshot_pins = {
        "cycle_id": source_cycle_id,
        "raw_run_id": source_raw_run_id,
        "cycle_source_date": source_cycle_date,
        "cycle_terminal_path": str(terminal_path),
        "cycle_terminal_sha256": terminal_sha256,
        **dict(pins),
        "observed_at": observed_at.isoformat(),
    }
    try:
        context = load_current_observed_context_from_pinned_snapshot(context_snapshot_pins)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return pending(
            "current_stock_cycle_source_context_revalidation_failed",
            error_type=type(exc).__name__,
        )
    context_database_sha = _normalized_sha256_hex(context.snapshot_database_sha256)
    terminal_database_sha = _normalized_sha256_hex(pins.get("snapshot_database_sha256"))
    context_receipt_sha = _normalized_sha256_hex(context.snapshot_receipt_sha256)
    terminal_receipt_sha = _normalized_sha256_hex(pins.get("snapshot_receipt_sha256"))
    context_envelope_sha = _normalized_sha256_hex(pins.get("source_context_envelope_sha256"))
    if any(
        digest is None
        for digest in (
            context_database_sha,
            terminal_database_sha,
            context_receipt_sha,
            terminal_receipt_sha,
            context_envelope_sha,
        )
    ):
        return pending("current_stock_cycle_terminal_snapshot_hash_invalid")
    try:
        snapshot_completed_at = datetime.fromisoformat(
            str(pins["snapshot_completed_at"]).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        terminal_training_as_of = datetime.fromisoformat(
            str(pins["current_restated_training_as_of"]).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        terminal_revision_verified_at = datetime.fromisoformat(
            str(pins["revision_dependencies_verified_at"]).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return pending("current_stock_cycle_terminal_clock_pin_invalid")
    if (
        Path(str(context.snapshot_database_path)).resolve()
        != Path(str(pins["snapshot_database_path"])).resolve()
        or context_database_sha != terminal_database_sha
        or Path(str(context.snapshot_receipt_path)).resolve()
        != Path(str(pins["snapshot_receipt_path"])).resolve()
        or context_receipt_sha != terminal_receipt_sha
        or context.training_as_of.astimezone(timezone.utc) != terminal_training_as_of
        or context.revision_dependencies_verified_at.astimezone(timezone.utc)
        != terminal_revision_verified_at
        or terminal_revision_verified_at < snapshot_completed_at
        or terminal_training_as_of < terminal_revision_verified_at
        or terminal_training_as_of < snapshot_completed_at
    ):
        return pending("current_stock_cycle_source_context_pins_conflict_with_terminal")
    if (
        observed_utc < context.training_as_of.astimezone(timezone.utc)
        or observed_utc < snapshot_completed_at
    ):
        return pending("current_observation_predates_verified_snapshot_freeze")

    snapshot_database = Path(str(context.snapshot_database_path)).resolve(strict=True)
    child_snapshots: list[dict[str, Any]] = []
    try:
        provider = MLHistoricalSnapshotProvider(snapshot_database)
        feature_builder = HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY)
        for batch_index, batch_symbols in enumerate(symbol_batches):
            raw_snapshot = provider.load_current_observed(
                decision_date=decision_date.isoformat(),
                history_start_date=history_start_date,
                symbols=batch_symbols,
                source_context=context,
                local_current_observed_at=observed_at,
                expected_feature_as_of_date=expected_feature_as_of,
                cycle_id=source_cycle_id,
                cycle_terminal_path=terminal_path,
                cycle_terminal_sha256=terminal_sha256,
                source_context_envelope_path=str(pins["source_context_envelope_path"]),
                source_context_envelope_sha256="sha256:" + str(context_envelope_sha),
            )
            feature_rows = feature_builder.compute_current_observed(
                raw_snapshot,
                industry_index_name_by_symbol={},
            )
            rows = [
                {
                    "symbol": row.symbol,
                    "decision_date": row.decision_date,
                    "feature_as_of_date": row.feature_as_of_date,
                    "feature_available_date": decision_date.isoformat(),
                    "local_current_observed_at": row.local_current_observed_at.isoformat(),
                    "feature_registry_id": row.feature_registry_id,
                    "feature_registry_hash": row.feature_registry_hash,
                    "feature_schema_hash": row.feature_schema_hash,
                    "feature_ids": list(row.feature_ids),
                    "feature_values": [value for _, value in row.values],
                    "missing_feature_ids": list(row.missing_feature_ids),
                    "source_row_sha256_by_table": [
                        list(item) for item in row.source_row_sha256_by_table
                    ],
                    "row_sha256": row.row_sha256,
                    "historical_pit_eligible": False,
                    "formal_training_allowed": False,
                }
                for row in feature_rows
            ]
            if tuple(str(row["symbol"]) for row in rows) != batch_symbols:
                return pending(
                    "current_observed_feature_symbol_coverage_mismatch",
                    batch_ordinal=batch_index,
                    expected_symbols=list(batch_symbols),
                    observed_symbols=[str(row["symbol"]) for row in rows],
                )
            child = _current_observed_feature_child_snapshot(
                rows=rows,
                source_rows_sha256_by_table=raw_snapshot.source_rows_sha256_by_table,
                batch_symbols=batch_symbols,
                decision_date=decision_date,
                expected_feature_as_of=expected_feature_as_of,
                history_start_date=history_start_date,
                observed_at=observed_at,
                source_cycle_date=source_cycle_date,
                source_cycle_id=source_cycle_id,
                source_raw_run_id=source_raw_run_id,
                discovery_raw_run_id=str(raw_run_id),
                discovery_terminal_path=discovery_terminal_path,
                discovery_terminal_sha256=str(discovery_terminal_sha256),
                child_status=child_status,
                reuse_source_identity=reuse_source_identity,
                status_path=status_path,
                status_sha256=status_sha256,
                status_bytes=status_bytes,
                terminal_path=terminal_path,
                terminal_sha256=terminal_sha256,
                snapshot_database=snapshot_database,
                context=context,
                pins=pins,
                feature_builder=feature_builder,
            )
            child_snapshots.append(child)
    except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
        return pending(
            "current_observed_snapshot_or_feature_build_failed",
            error_type=type(exc).__name__,
            expected_feature_as_of_date=expected_feature_as_of,
            cycle_source_date=source_cycle_date,
            failed_batch_ordinal=len(child_snapshots),
            failed_batch_symbols=list(symbol_batches[len(child_snapshots)]),
            completed_batch_count=len(child_snapshots),
        )
    full_entry_observation = _read_current_observed_entry_prices(
        snapshot_database=snapshot_database,
        expected_database_sha256=str(context.snapshot_database_sha256),
        decision_date=decision_date,
        cycle_source_date=source_cycle_date,
        decision_session_evidence=(
            decision_session_evidence
            if source_cycle_date == decision_date.isoformat()
            else None
        ),
        symbols=normalized_symbols,
        source_pins={
            "cycle_id": source_cycle_id,
            "raw_run_id": source_raw_run_id,
            "cycle_terminal_path": str(terminal_path),
            "cycle_terminal_sha256": str(terminal_sha256),
            "snapshot_database_path": str(snapshot_database),
            "snapshot_database_sha256": str(context.snapshot_database_sha256),
            "snapshot_receipt_path": str(context.snapshot_receipt_path),
            "snapshot_receipt_sha256": str(context.snapshot_receipt_sha256),
            "source_context_envelope_path": str(pins["source_context_envelope_path"]),
            "source_context_envelope_sha256": "sha256:" + str(context_envelope_sha),
            "local_observed_at": str(pins["snapshot_completed_at"]),
        },
    )
    if len(symbol_batches) > 1:
        for batch_index, (batch_symbols, child_snapshot) in enumerate(
            zip(symbol_batches, child_snapshots, strict=True)
        ):
            child_snapshot["entry_observation"] = _slice_current_observed_entry_observation(
                full_entry_observation,
                batch_symbols,
            )
            child_snapshot["content_sha256"] = _source_contract_hash_payload(
                {key: value for key, value in child_snapshot.items() if key != "content_sha256"}
            )
            child_snapshots[batch_index] = child_snapshot
        if snapshot_cohort is None or snapshot_source_binding is None:
            return pending("current_observed_full_cohort_snapshot_binding_missing")
        try:
            composed = compose_current_observed_feature_snapshot_v2(
                batch_snapshots=child_snapshots,
                full_cohort=snapshot_cohort,
                snapshot_source_binding=snapshot_source_binding,
            )
            verify_current_observed_feature_snapshot_v2(composed)
        except (TypeError, ValueError) as exc:
            return pending(
                "current_observed_feature_composition_verification_failed",
                error_type=type(exc).__name__,
                diagnostic=str(exc),
                completed_batch_count=len(child_snapshots),
                expected_batch_count=len(symbol_batches),
            )
        return dict(composed)

    body = child_snapshots[0]
    body["entry_observation"] = full_entry_observation
    body["content_sha256"] = _source_contract_hash_payload(
        {key: value for key, value in body.items() if key != "content_sha256"}
    )
    return body


def _slice_current_observed_entry_observation(
    observation: Mapping[str, Any],
    symbols: tuple[str, ...],
) -> dict[str, Any]:
    """Project one exact full-cohort entry proof to an immutable child batch."""

    sliced = dict(observation)
    raw_pins = observation.get("entry_price_pin_by_symbol")
    if not isinstance(raw_pins, Mapping):
        raise ValueError("current-observed full entry observation has no pin map")
    pins = {symbol: raw_pins[symbol] for symbol in symbols if symbol in raw_pins}
    sliced["entry_price_pin_by_symbol"] = pins
    missing = observation.get("missing_symbols")
    missing_symbols = (
        [symbol for symbol in symbols if symbol in set(str(item) for item in missing)]
        if isinstance(missing, list)
        else []
    )
    if observation.get("status") == "captured":
        if set(pins) != set(symbols) or missing_symbols:
            raise ValueError("captured entry observation does not cover its exact feature batch")
    else:
        if not missing_symbols:
            missing_symbols = [symbol for symbol in symbols if symbol not in pins]
        sliced["missing_symbols"] = missing_symbols
    return sliced


def _current_observed_feature_child_snapshot(
    *,
    rows: list[dict[str, Any]],
    source_rows_sha256_by_table: Mapping[str, str],
    batch_symbols: tuple[str, ...],
    decision_date: date,
    expected_feature_as_of: str,
    history_start_date: str,
    observed_at: datetime,
    source_cycle_date: str,
    source_cycle_id: str,
    source_raw_run_id: str,
    discovery_raw_run_id: str,
    discovery_terminal_path: Path,
    discovery_terminal_sha256: str,
    child_status: str,
    reuse_source_identity: Mapping[str, Any] | None,
    status_path: Path,
    status_sha256: str,
    status_bytes: bytes,
    terminal_path: Path,
    terminal_sha256: str,
    snapshot_database: Path,
    context: Any,
    pins: Mapping[str, Any],
    feature_builder: HistoricalFeatureBuilder,
) -> dict[str, Any]:
    """Create one hash-bound v1 snapshot for a <=16-symbol provider call."""

    if tuple(str(row["symbol"]) for row in rows) != batch_symbols:
        raise ValueError("current-observed feature child symbols differ from its batch")
    source_context_envelope_digest = _normalized_sha256_hex(
        pins.get("source_context_envelope_sha256")
    )
    if source_context_envelope_digest is None:
        raise ValueError("current-observed source-context envelope SHA-256 is invalid")
    entry_observation: dict[str, Any] = {
        "status": "pending",
        "reason": "entry_observation_not_attached",
    }
    body: dict[str, Any] = {
        "schema_version": CURRENT_OBSERVED_FEATURE_SNAPSHOT_V1,
        "status": "captured",
        "verified": True,
        "decision_date": decision_date.isoformat(),
        "feature_as_of_date": expected_feature_as_of,
        "history_start_date": history_start_date,
        "observed_at": observed_at.isoformat(),
        "cycle_source_date": source_cycle_date,
        "cycle_id": source_cycle_id,
        "raw_run_id": source_raw_run_id,
        "discovery_raw_run_id": discovery_raw_run_id,
        "discovery_cycle_terminal_path": str(discovery_terminal_path),
        "discovery_cycle_terminal_sha256": str(discovery_terminal_sha256),
        "discovery_cycle_terminal_status": child_status,
        "reuse_source_identity": (
            dict(reuse_source_identity) if isinstance(reuse_source_identity, Mapping) else None
        ),
        "discovery_status_path": str(status_path.resolve()),
        "discovery_status_sha256": status_sha256,
        "discovery_status_bytes_base64": base64.b64encode(status_bytes).decode("ascii"),
        "cycle_terminal_path": str(terminal_path),
        "cycle_terminal_sha256": terminal_sha256,
        "snapshot_database_path": str(snapshot_database),
        "snapshot_database_sha256": str(context.snapshot_database_sha256),
        "snapshot_receipt_path": str(context.snapshot_receipt_path),
        "snapshot_receipt_sha256": str(context.snapshot_receipt_sha256),
        "source_context_envelope_path": str(pins["source_context_envelope_path"]),
        "source_context_envelope_sha256": "sha256:" + source_context_envelope_digest,
        "source_rows_sha256_by_table": {name: value for name, value in source_rows_sha256_by_table.items()},
        "feature_registry_id": CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_id,
        "feature_registry_hash": CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        "feature_schema_hash": HistoricalFeatureBuilder(
            CORE_LONG_HISTORY_FEATURE_REGISTRY
        ).load_contract.schema_hash,
        "symbols": list(batch_symbols),
        "rows": rows,
        "row_count": len(rows),
        "rows_sha256": _source_contract_hash_payload({"rows": rows}),
        "entry_observation": entry_observation,
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
        "reason": "verified_current_observation_not_historical_pit",
    }
    body["content_sha256"] = _source_contract_hash_payload(body)
    return body


def _read_current_observed_entry_prices(
    *,
    snapshot_database: Path,
    expected_database_sha256: str,
    decision_date: date,
    cycle_source_date: str,
    decision_session_evidence: Mapping[str, Any] | None,
    symbols: tuple[str, ...],
    source_pins: Mapping[str, Any],
) -> dict[str, Any]:
    """Pin exact same-date stock and TAIEX closes from the frozen G6 snapshot.

    ``local_observed_at`` records when the immutable local snapshot completed;
    no source-availability clock is inferred from its later verification time.
    """

    base: dict[str, Any] = {
        "schema_version": "recommendation-current-observed-entry-observation.v1",
        "decision_date": decision_date.isoformat(),
        "cycle_source_date": cycle_source_date,
        "source_database_path": str(snapshot_database.resolve()),
        "source_database_sha256": expected_database_sha256,
        "local_observed_at": source_pins.get("local_observed_at"),
        "source_available_at": None,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "current_restated": True,
        "research_only": True,
    }
    if cycle_source_date != decision_date.isoformat():
        return {
            **base,
            "status": "pending",
            "reason": "same_date_entry_session_missing",
            "missing_symbols": list(symbols),
            "entry_price_pin_by_symbol": {},
            "benchmark_entry_price_pin": None,
        }
    try:
        observed_at = datetime.fromisoformat(
            str(source_pins.get("local_observed_at") or "").replace("Z", "+00:00")
        )
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("snapshot local observation clock is not timezone-aware")
        try:
            session_proof = _build_current_observed_entry_session_proof(
                decision_date=decision_date,
                observed_at=observed_at,
                calendar_evidence=decision_session_evidence,
            )
        except ValueError:
            return {
                **base,
                "status": "pending",
                "reason": "official_entry_session_calendar_unverified",
                "missing_symbols": list(symbols),
                "entry_price_pin_by_symbol": {},
                "benchmark_entry_price_pin": None,
            }
        scheduled_close_at = datetime.fromisoformat(
            str(session_proof["scheduled_market_close_at"])
        )
        if observed_at.astimezone(timezone.utc) < scheduled_close_at.astimezone(timezone.utc):
            return {
                **base,
                "status": "pending",
                "reason": "entry_source_observation_before_scheduled_market_close",
                "scheduled_market_close_at": session_proof["scheduled_market_close_at"],
                "entry_session_proof": session_proof,
                "missing_symbols": list(symbols),
                "entry_price_pin_by_symbol": {},
                "benchmark_entry_price_pin": None,
            }
        if not _is_sha256_text(expected_database_sha256):
            raise ValueError("snapshot database SHA-256 is invalid")
        database = snapshot_database.resolve(strict=True)
        before = database.stat()
        if _sha256_file(database) != expected_database_sha256:
            raise ValueError("snapshot database hash differs from verified context")
        connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=10)
        try:
            connection.execute("PRAGMA query_only=ON")
            stock_pins: dict[str, dict[str, Any]] = {}
            for symbol in symbols:
                result = connection.execute(
                    'SELECT "\u8b49\u5238\u4ee3\u865f", "\u65e5\u671f", '
                    'CAST("\u6536\u76e4\u50f9" AS TEXT) '
                    'FROM daily_prices WHERE "\u65e5\u671f" IN (?, ?) '
                    'AND "\u8b49\u5238\u4ee3\u865f"=?',
                    (decision_date.strftime("%Y%m%d"), decision_date.isoformat(), symbol),
                ).fetchall()
                if len(result) != 1:
                    return {
                        **base,
                        "status": "pending",
                        "reason": "same_date_stock_close_missing_or_ambiguous",
                        "missing_symbols": [symbol],
                        "entry_price_pin_by_symbol": {},
                        "benchmark_entry_price_pin": None,
                    }
                raw_symbol, raw_date, raw_close = result[0]
                if str(raw_symbol).strip() != symbol or str(raw_date)[:10] not in {
                    decision_date.isoformat(),
                    decision_date.strftime("%Y%m%d"),
                }:
                    raise ValueError("same-date stock row identity mismatch")
                close = _strict_positive_decimal(raw_close)
                source_values = {
                    "table": "daily_prices",
                    "symbol": symbol,
                    "source_date": decision_date.isoformat(),
                    "raw_close_value": str(raw_close).strip(),
                }
                stock_pins[symbol] = _build_current_observed_entry_price_pin(
                    row_id=(
                        f"current-observed:{decision_date.isoformat()}:{source_pins.get('cycle_id')}:{symbol}"
                    ),
                    symbol=symbol,
                    source_date=decision_date.isoformat(),
                    close=close,
                    source_values=source_values,
                    source_pins=source_pins,
                    session_proof=session_proof,
                )
            benchmark_rows = connection.execute(
                'SELECT "\u65e5\u671f", CAST(COALESCE("\u6536\u76e4\u50f9", "\u6536\u76e4\u6307\u6578") AS TEXT) '
                'FROM market_indices WHERE "\u65e5\u671f" IN (?, ?)',
                (decision_date.strftime("%Y%m%d"), decision_date.isoformat()),
            ).fetchall()
            if len(benchmark_rows) != 1:
                return {
                    **base,
                    "status": "pending",
                    "reason": "same_date_taiex_close_missing_or_ambiguous",
                    "missing_symbols": ["TAIEX"],
                    "entry_price_pin_by_symbol": stock_pins,
                    "benchmark_entry_price_pin": None,
                }
            raw_date, raw_close = benchmark_rows[0]
            if str(raw_date)[:10] not in {
                decision_date.isoformat(),
                decision_date.strftime("%Y%m%d"),
            }:
                raise ValueError("same-date TAIEX row identity mismatch")
            benchmark_close = _strict_positive_decimal(raw_close)
            benchmark_source_values = {
                "table": "market_indices",
                "symbol": "TAIEX",
                "source_date": decision_date.isoformat(),
                "raw_close_value": str(raw_close).strip(),
            }
            benchmark_pin = _build_current_observed_entry_price_pin(
                row_id=f"current-observed:{decision_date.isoformat()}:{source_pins.get('cycle_id')}:TAIEX",
                symbol="TAIEX",
                source_date=decision_date.isoformat(),
                close=benchmark_close,
                source_values=benchmark_source_values,
                source_pins=source_pins,
                session_proof=session_proof,
            )
        finally:
            connection.close()
        after = database.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError("frozen snapshot changed during entry-price read")
        if _sha256_file(database) != expected_database_sha256:
            raise RuntimeError("frozen snapshot hash changed during entry-price read")
    except (OSError, RuntimeError, sqlite3.Error, TypeError, ValueError, InvalidOperation) as exc:
        return {
            **base,
            "status": "blocked",
            "reason": f"same_date_entry_source_unverifiable:{type(exc).__name__}",
            "missing_symbols": list(symbols),
            "entry_price_pin_by_symbol": {},
            "benchmark_entry_price_pin": None,
        }
    return {
        **base,
        "status": "captured",
        "reason": "same_date_entry_prices_exactly_pinned",
        "scheduled_market_close_at": session_proof["scheduled_market_close_at"],
        "entry_session_proof": session_proof,
        "missing_symbols": [],
        "entry_price_pin_by_symbol": stock_pins,
        "benchmark_entry_price_pin": benchmark_pin,
    }


def _build_current_observed_entry_session_proof(
    *,
    decision_date: date,
    observed_at: datetime,
    calendar_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Bind the exact official open-session decision and regular market close."""

    if (
        not isinstance(calendar_evidence, Mapping)
        or calendar_evidence.get("target_date") != decision_date.isoformat()
        or calendar_evidence.get("is_trading_day") is not True
        or calendar_evidence.get("mode") != "hash_bound_official_calendar_cache"
    ):
        raise ValueError("official decision-date session evidence is unresolved")
    verify_current_observed_official_calendar_evidence(
        calendar_evidence,
        decision_date=decision_date,
        observed_at=observed_at,
    )
    calendar_sha256 = _source_contract_hash_payload(dict(calendar_evidence))
    scheduled_close = datetime.combine(
        decision_date,
        _CURRENT_RESEARCH_MARKET_CLOSE,
        tzinfo=TAIPEI,
    ).isoformat()
    body: dict[str, Any] = {
        "schema_version": "recommendation-current-observed-entry-session-proof.v1",
        "decision_date": decision_date.isoformat(),
        "exchange": "TWSE_TAIWAN_EQUITIES",
        "timezone": "Asia/Taipei",
        "scheduled_market_close_time": _CURRENT_RESEARCH_MARKET_CLOSE.isoformat(),
        "scheduled_market_close_at": scheduled_close,
        "calendar_evidence": dict(calendar_evidence),
        "calendar_evidence_sha256": calendar_sha256,
        "local_observed_at": observed_at.isoformat(),
        "source_available_at": None,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
    }
    body["proof_sha256"] = _source_contract_hash_payload(body)
    return body


def _strict_positive_decimal(value: object) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError("price value is missing")
    parsed = Decimal(str(value).strip())
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("price value must be a finite positive Decimal")
    return parsed


def _build_current_observed_entry_price_pin(
    *,
    row_id: str,
    symbol: str,
    source_date: str,
    close: Decimal,
    source_values: Mapping[str, str],
    source_pins: Mapping[str, Any],
    session_proof: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "recommendation-current-observed-entry-price-pin.v1",
        "row_id": row_id,
        "symbol": symbol,
        "source_date": source_date,
        "close_price_twd": format(close, "f"),
        "raw_close_value": str(source_values["raw_close_value"]),
        "source_table": str(source_values["table"]),
        "source_row_values": dict(source_values),
        "source_row_sha256": _source_contract_hash_payload(dict(source_values)),
        "cycle_id": source_pins.get("cycle_id"),
        "raw_run_id": source_pins.get("raw_run_id"),
        "cycle_terminal_path": source_pins.get("cycle_terminal_path"),
        "cycle_terminal_sha256": source_pins.get("cycle_terminal_sha256"),
        "snapshot_database_path": source_pins.get("snapshot_database_path"),
        "snapshot_database_sha256": source_pins.get("snapshot_database_sha256"),
        "snapshot_receipt_path": source_pins.get("snapshot_receipt_path"),
        "snapshot_receipt_sha256": source_pins.get("snapshot_receipt_sha256"),
        "source_context_envelope_path": source_pins.get("source_context_envelope_path"),
        "source_context_envelope_sha256": source_pins.get("source_context_envelope_sha256"),
        "local_observed_at": source_pins.get("local_observed_at"),
        "scheduled_market_close_at": session_proof.get("scheduled_market_close_at"),
        "entry_session_proof_sha256": session_proof.get("proof_sha256"),
        "source_available_at": None,
        "current_restated": True,
        "research_only": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
    }


def _audit_source_contract(
    *,
    data_root: Path,
    output_root: Path,
    source_db: Path,
    learning_output_root: Path,
    decision_date: date,
    symbols: tuple[str, ...],
    fixed_round_trip_cost_bp: int | None,
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
    history_start_date: str,
    replay_start_date: str,
    replay_end_date: str,
    availability_cutoff_at: str | None = None,
    current_observed_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a read-only source audit and persist its shadow receipt."""

    try:
        scenario = normalize_cost_scenario(
            cost_scenario,
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        )
        estimated_lane = scenario.is_estimated
        contract = inspect_source_contract(
            data_root=data_root,
            output_root=output_root,
            source_db=source_db,
            decision_date=decision_date,
            symbols=symbols,
            # The source contract's ``estimated`` lane is only a readiness
            # diagnostic.  For the BankTaiwan lane it must not receive a
            # fabricated fixed-bp fallback; the exact fee/tax label is owned
            # by the versioned cost policy in the replay/evidence path.
            estimated_cost_bp=(
                None
                if estimated_lane
                else int(scenario.fixed_round_trip_cost_bp or 0)
            ),
            cost_scenario=(scenario.metadata() if estimated_lane else None),
            history_start_date=history_start_date,
            replay_start_date=replay_start_date,
            replay_end_date=replay_end_date,
            availability_cutoff_at=availability_cutoff_at,
        )
        if isinstance(current_observed_snapshot, Mapping):
            contract = dict(contract)
            technical_value = contract.get("technical")
            technical = dict(technical_value) if isinstance(technical_value, Mapping) else {}
            technical["current_observed_feature_snapshot"] = dict(current_observed_snapshot)
            contract["technical"] = technical
            contract["contract_sha256"] = _source_contract_hash_payload(
                {
                    key: value
                    for key, value in contract.items()
                    if key not in {"contract_sha256", "checked_at"}
                }
            )
        receipt = write_source_contract(
            contract,
            learning_output_root=learning_output_root,
        )
        result: dict[str, Any] = {
            "source_contract": contract,
            "source_contract_receipt": receipt,
        }
        if estimated_lane:
            result["cost_scenario"] = scenario.metadata()
        return result
    except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
        return {
            "source_contract": {
                "schema_version": "recommendation-calibration-source-contract.v1",
                "status": "blocked",
                "decision_date": decision_date.isoformat(),
                "symbols": list(symbols),
                "reason": f"source_contract_audit_failed:{type(exc).__name__}",
                "error": str(exc),
            },
            "source_contract_receipt": {
                "status": "blocked",
                "reason": f"source_contract_audit_failed:{type(exc).__name__}",
                "error": str(exc),
            },
        }


def _capture_source_contract_binding(
    audit: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Build the immutable prospective-input binding for a live capture."""

    if not isinstance(audit, Mapping):
        return None, "prospective_source_contract_audit_missing"
    contract = audit.get("source_contract")
    receipt = audit.get("source_contract_receipt")
    if not isinstance(contract, Mapping) or not isinstance(receipt, Mapping):
        return None, "prospective_source_contract_receipt_missing"
    technical = contract.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
    current_snapshot = technical.get("current_observed_feature_snapshot")
    if isinstance(current_snapshot, Mapping) and current_snapshot.get("status") == "captured":
        if (
            current_snapshot.get("verified") is not True
            or current_snapshot.get("current_restated") is not True
            or current_snapshot.get("historical_pit_eligible") is not False
            or current_snapshot.get("formal_training_allowed") is not False
            or current_snapshot.get("research_only") is not True
        ):
            return None, "current_observed_feature_snapshot_flags_invalid"
        contract_path = str(receipt.get("contract_path") or "")
        content_hash = str(receipt.get("contract_content_sha256") or "")
        file_hash = str(receipt.get("contract_file_sha256") or "")
        feature_snapshot_hash = str(current_snapshot.get("content_sha256") or "")
        if not (
            contract_path
            and _is_sha256_text(content_hash)
            and _is_sha256_text(file_hash)
            and _is_sha256_text(feature_snapshot_hash)
        ):
            return None, "current_observed_binding_receipt_hash_missing"
        binding = {
            "schema_version": "recommendation-calibration-capture-source-binding.v2",
            "binding_mode": "current_observed",
            "contract_path": contract_path,
            "contract_content_sha256": content_hash,
            "contract_file_sha256": file_hash,
            "decision_date": contract.get("decision_date"),
            "symbols": list(contract.get("symbols", []))
            if isinstance(contract.get("symbols"), list)
            else [],
            "current_observed_feature_snapshot": dict(current_snapshot),
            "current_observed_feature_snapshot_sha256": feature_snapshot_hash,
            "feature_snapshot_content_sha256": feature_snapshot_hash,
            "cycle_id": current_snapshot.get("cycle_id"),
            "raw_run_id": current_snapshot.get("raw_run_id"),
            "cycle_source_date": current_snapshot.get("cycle_source_date"),
            "discovery_status_path": current_snapshot.get("discovery_status_path"),
            "discovery_status_sha256": current_snapshot.get("discovery_status_sha256"),
            "cycle_terminal_path": current_snapshot.get("cycle_terminal_path"),
            "cycle_terminal_sha256": current_snapshot.get("cycle_terminal_sha256"),
            "discovery_raw_run_id": current_snapshot.get("discovery_raw_run_id"),
            "discovery_cycle_terminal_path": current_snapshot.get(
                "discovery_cycle_terminal_path"
            ),
            "discovery_cycle_terminal_sha256": current_snapshot.get(
                "discovery_cycle_terminal_sha256"
            ),
            "discovery_cycle_terminal_status": current_snapshot.get(
                "discovery_cycle_terminal_status"
            ),
            "reuse_source_identity": current_snapshot.get("reuse_source_identity"),
            "snapshot_database_path": current_snapshot.get("snapshot_database_path"),
            "snapshot_database_sha256": current_snapshot.get("snapshot_database_sha256"),
            "snapshot_receipt_path": current_snapshot.get("snapshot_receipt_path"),
            "snapshot_receipt_sha256": current_snapshot.get("snapshot_receipt_sha256"),
            "source_context_envelope_path": current_snapshot.get(
                "source_context_envelope_path"
            ),
            "source_context_envelope_sha256": current_snapshot.get(
                "source_context_envelope_sha256"
            ),
            "feature_as_of_date": current_snapshot.get("feature_as_of_date"),
            "observed_at": current_snapshot.get("observed_at"),
            "feature_registry_id": current_snapshot.get("feature_registry_id"),
            "feature_registry_hash": current_snapshot.get("feature_registry_hash"),
            "feature_schema_hash": current_snapshot.get("feature_schema_hash"),
            "rows_sha256": current_snapshot.get("rows_sha256"),
            "row_count": current_snapshot.get("row_count"),
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
            "current_restated": True,
            "research_only": True,
            "source_semantics": "current_observed_after_actual_capture;not_historical_PIT",
        }
        if current_snapshot.get("schema_version") == CURRENT_OBSERVED_FEATURE_SNAPSHOT_V2:
            composition = current_snapshot.get("batch_composition")
            if not isinstance(composition, Mapping):
                return None, "current_observed_v2_composition_missing"
            binding.update(
                {
                    "scope_mode": "verified_scheduled_snapshot_cohort",
                    "composition_sha256": current_snapshot.get("composition_sha256"),
                    "cohort_hash": current_snapshot.get("cohort_hash"),
                }
            )
        return binding, None
    lanes = contract.get("lanes")
    lanes = lanes if isinstance(lanes, Mapping) else {}
    price_up = lanes.get("price_up_calibration")
    price_up = price_up if isinstance(price_up, Mapping) else {}
    if price_up.get("prospective_status") != "ready":
        blockers = price_up.get("prospective_blockers") or price_up.get("blockers") or []
        detail = ",".join(str(item) for item in blockers if str(item).strip())
        return None, "prospective_price_up_source_not_ready" + (f":{detail}" if detail else "")
    contract_path = str(receipt.get("contract_path") or "")
    content_hash = str(
        receipt.get("contract_content_sha256")
        or contract.get("contract_sha256")
        or ""
    )
    file_hash = str(
        receipt.get("contract_file_sha256")
        or receipt.get("contract_sha256")
        or ""
    )
    if not contract_path or not content_hash.startswith("sha256:") or not file_hash.startswith("sha256:"):
        return None, "prospective_source_contract_receipt_hash_missing"
    technical_receipt = technical.get("publication_receipt")
    technical_receipt = technical_receipt if isinstance(technical_receipt, Mapping) else {}
    feature_snapshot = technical.get("prospective_feature_snapshot")
    feature_snapshot = feature_snapshot if isinstance(feature_snapshot, Mapping) else {}
    feature_snapshot_hash = str(feature_snapshot.get("content_sha256") or "")
    if not feature_snapshot_hash.startswith("sha256:"):
        return None, "prospective_feature_snapshot_missing"
    corporate = contract.get("corporate_actions")
    corporate = corporate if isinstance(corporate, Mapping) else {}
    adjustment_custody = corporate.get("adjustment_custody")
    adjustment_custody = adjustment_custody if isinstance(adjustment_custody, Mapping) else {}
    binding = {
        "schema_version": "recommendation-calibration-capture-source-binding.v1",
        "contract_path": contract_path,
        "contract_content_sha256": content_hash,
        "contract_file_sha256": file_hash,
        "decision_date": contract.get("decision_date"),
        "symbols": list(contract.get("symbols", [])) if isinstance(contract.get("symbols"), list) else [],
        "price_up_prospective_status": price_up.get("prospective_status"),
        "price_up_prospective_blockers": list(price_up.get("prospective_blockers", [])),
        "technical_publication_receipt_file_sha256": technical_receipt.get("sha256"),
        "technical_publication_content_sha256": (
            technical_receipt.get("payload", {}).get("content_sha256")
            if isinstance(technical_receipt.get("payload"), Mapping)
            else None
        ),
        "technical_publication_available_at": technical.get("publication_available_at"),
        "technical_source_available_ats": list(technical.get("source_receipt_available_ats") or []),
        "feature_snapshot_content_sha256": feature_snapshot_hash,
        "feature_snapshot_rows_sha256": feature_snapshot.get("rows_sha256"),
        "feature_snapshot_captured_at": feature_snapshot.get("captured_at"),
        "corporate_adjustment_manifest_hash": adjustment_custody.get("manifest_hash"),
        "corporate_adjustment_available_at": adjustment_custody.get("available_at"),
        "official_event_available_at": (
            (corporate.get("event_publication") or {}).get("source_publication_available_at")
            if isinstance(corporate.get("event_publication"), Mapping)
            else None
        ),
        "historical_pit_eligible": False,
        "source_semantics": "prospective_input_only;not_historical_backfill",
    }
    return binding, None


def _current_observed_capture_inputs(
    snapshot: Mapping[str, Any],
    *,
    decision_date: date,
) -> tuple[RecommendationPredictionCaptureInput, ...]:
    """Project one verified v1 or composed v2 observation into inference rows."""

    schema_version = snapshot.get("schema_version")
    if (
        schema_version not in {
            CURRENT_OBSERVED_FEATURE_SNAPSHOT_V1,
            CURRENT_OBSERVED_FEATURE_SNAPSHOT_V2,
        }
        or snapshot.get("status") != "captured"
        or snapshot.get("verified") is not True
        or snapshot.get("current_restated") is not True
        or snapshot.get("historical_pit_eligible") is not False
        or snapshot.get("formal_training_allowed") is not False
        or snapshot.get("research_only") is not True
        or str(snapshot.get("decision_date") or "") != decision_date.isoformat()
    ):
        return ()
    if schema_version == CURRENT_OBSERVED_FEATURE_SNAPSHOT_V2:
        try:
            verify_current_observed_feature_snapshot_v2(snapshot)
        except (TypeError, ValueError):
            return ()
        composition = snapshot.get("batch_composition")
        if (
            snapshot.get("scope_mode") != "verified_scheduled_snapshot_cohort"
            or
            not isinstance(composition, Mapping)
            or composition.get("scope_mode") != "verified_scheduled_snapshot_cohort"
        ):
            return ()
    try:
        observed_at = datetime.fromisoformat(
            str(snapshot.get("observed_at") or "").replace("Z", "+00:00")
        )
        feature_as_of = date.fromisoformat(str(snapshot.get("feature_as_of_date") or ""))
    except (TypeError, ValueError, OverflowError):
        return ()
    if (
        observed_at.tzinfo is None
        or observed_at.utcoffset() is None
        or observed_at.astimezone(TAIPEI).date() != decision_date
        or feature_as_of >= decision_date
    ):
        return ()
    rows = snapshot.get("rows")
    symbols = snapshot.get("symbols")
    if not isinstance(rows, list) or not isinstance(symbols, list) or not rows:
        return ()
    normalized_symbols = tuple(sorted({str(symbol).strip() for symbol in symbols if str(symbol).strip()}))
    rows_by_symbol = {
        str(row.get("symbol") or ""): row
        for row in rows
        if isinstance(row, Mapping) and str(row.get("symbol") or "")
    }
    if set(rows_by_symbol) != set(normalized_symbols) or len(rows_by_symbol) != len(rows):
        return ()
    max_symbols = 16 if schema_version == CURRENT_OBSERVED_FEATURE_SNAPSHOT_V1 else 50
    if not normalized_symbols or len(normalized_symbols) > max_symbols:
        return ()
    feature_registry = CORE_LONG_HISTORY_FEATURE_REGISTRY
    inputs: list[RecommendationPredictionCaptureInput] = []
    for symbol in normalized_symbols:
        row = rows_by_symbol[symbol]
        feature_ids = row.get("feature_ids")
        raw_values = row.get("feature_values")
        if (
            feature_ids != list(feature_registry.canonical_ids)
            or not isinstance(raw_values, list)
            or len(raw_values) != len(feature_registry.canonical_ids)
        ):
            return ()
        if any(value is not None and (type(value) is not int) for value in raw_values):
            return ()
        row_feature_as_of = str(row.get("feature_as_of_date") or "")
        row_available_date = str(row.get("feature_available_date") or "")
        if (
            row.get("decision_date") != decision_date.isoformat()
            or row_feature_as_of != feature_as_of.isoformat()
            or row_available_date != decision_date.isoformat()
        ):
            return ()
        inputs.append(
            RecommendationPredictionCaptureInput(
                row_id=(
                    f"current-observed:{decision_date.isoformat()}:{snapshot.get('cycle_id')}:{symbol}"
                ),
                symbol=symbol,
                decision_date=decision_date.isoformat(),
                feature_as_of_date=row_feature_as_of,
                feature_available_date=row_available_date,
                feature_values=tuple(raw_values),
                rule_probability_bp=NULL_BENCHMARK_PROBABILITY_BP,
                rule_after_cost_probability_bp=AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP,
                rule_baseline_id=NULL_BENCHMARK_BASELINE_ID,
            )
        )
    return tuple(inputs)


def _persist_current_observed_input_capture(
    *,
    output_root: Path,
    source_contract_audit: Mapping[str, Any],
    decision_date: date,
    captured_at: datetime,
    cost_scenario: RecommendationCostScenario,
    fixed_round_trip_cost_bp: int | None,
) -> dict[str, Any]:
    """Persist a no-model feature/entry observation for future natural labels."""

    binding, reason = _capture_source_contract_binding(source_contract_audit)
    if binding is None or binding.get("binding_mode") != "current_observed":
        return {
            "status": "pending",
            "reason": reason or "current_observed_source_binding_unavailable",
            "capture_eligible": False,
        }
    feature_snapshot = binding.get("current_observed_feature_snapshot")
    if not isinstance(feature_snapshot, Mapping):
        return {"status": "blocked", "reason": "current_observed_feature_snapshot_missing"}
    feature_schema_version = feature_snapshot.get("schema_version")
    if feature_schema_version == CURRENT_OBSERVED_FEATURE_SNAPSHOT_V2:
        try:
            verify_current_observed_feature_snapshot_v2(feature_snapshot)
        except (TypeError, ValueError) as exc:
            return {
                "status": "blocked",
                "reason": "current_observed_v2_feature_snapshot_invalid",
                "diagnostic": str(exc),
                "capture_eligible": False,
            }
        composition = feature_snapshot.get("batch_composition")
        if (
            feature_snapshot.get("scope_mode") != "verified_scheduled_snapshot_cohort"
            or
            not isinstance(composition, Mapping)
            or composition.get("scope_mode") != "verified_scheduled_snapshot_cohort"
        ):
            return {"status": "blocked", "reason": "current_observed_v2_scope_mode_invalid"}
    elif feature_schema_version != CURRENT_OBSERVED_FEATURE_SNAPSHOT_V1:
        return {"status": "blocked", "reason": "current_observed_feature_snapshot_schema_unsupported"}
    entry_observation = feature_snapshot.get("entry_observation")
    if not isinstance(entry_observation, Mapping):
        return {"status": "blocked", "reason": "same_date_entry_observation_missing"}
    if entry_observation.get("status") != "captured":
        return {
            "status": "pending",
            "reason": str(entry_observation.get("reason") or "same_date_entry_observation_pending"),
            "capture_eligible": False,
            "feature_snapshot_status": feature_snapshot.get("status"),
            "entry_observation_status": entry_observation.get("status"),
            "missing_symbols": list(entry_observation.get("missing_symbols", [])),
            "cycle_id": feature_snapshot.get("cycle_id"),
        }
    if (
        captured_at.tzinfo is None
        or captured_at.utcoffset() is None
        or captured_at.astimezone(TAIPEI).date() != decision_date
    ):
        return {"status": "blocked", "reason": "current_input_capture_clock_invalid"}
    capture_rows = feature_snapshot.get("rows")
    entry_by_symbol = entry_observation.get("entry_price_pin_by_symbol")
    benchmark_pin = entry_observation.get("benchmark_entry_price_pin")
    symbols = feature_snapshot.get("symbols")
    if (
        not isinstance(capture_rows, list)
        or not capture_rows
        or not isinstance(entry_by_symbol, Mapping)
        or not isinstance(benchmark_pin, Mapping)
        or not isinstance(symbols, list)
    ):
        return {"status": "blocked", "reason": "current_input_capture_rows_or_entry_pins_invalid"}
    scenario_metadata = cost_scenario.metadata()
    normalized_scenario = normalize_cost_scenario(
        scenario_metadata,
        fixed_round_trip_cost_bp=None if cost_scenario.is_estimated else fixed_round_trip_cost_bp,
    )
    if normalized_scenario.scenario_hash != cost_scenario.scenario_hash:
        return {"status": "blocked", "reason": "current_input_capture_cost_scenario_identity_mismatch"}
    capture_body: dict[str, Any] = {
        "schema_version": (
            "recommendation-current-observed-input-capture.v2"
            if feature_schema_version == CURRENT_OBSERVED_FEATURE_SNAPSHOT_V2
            else "recommendation-current-observed-input-capture.v1"
        ),
        "status": "captured",
        "decision_date": decision_date.isoformat(),
        "captured_at": captured_at.isoformat(),
        "cycle_id": str(feature_snapshot.get("cycle_id") or ""),
        "raw_run_id": str(feature_snapshot.get("raw_run_id") or ""),
        "cycle_source_date": str(feature_snapshot.get("cycle_source_date") or ""),
        "feature_snapshot_sha256": str(feature_snapshot.get("content_sha256") or ""),
        "feature_registry_id": feature_snapshot.get("feature_registry_id"),
        "feature_registry_hash": feature_snapshot.get("feature_registry_hash"),
        "feature_schema_hash": feature_snapshot.get("feature_schema_hash"),
        "symbols": list(symbols),
        "rows": [],
        "entry_price_pin_by_symbol": dict(entry_by_symbol),
        "benchmark_entry_price_pin": dict(benchmark_pin),
        "source_contract_binding": dict(binding),
        "cost_status": "verified",
        "cost_scenario": scenario_metadata,
        "cost_scenario_id": normalized_scenario.scenario_id,
        "cost_scenario_version": normalized_scenario.scenario_version,
        "cost_scenario_hash": normalized_scenario.scenario_hash,
        "cost_scenario_basis": normalized_scenario.cost_basis,
        "cost_basis": normalized_scenario.cost_basis,
        "fixed_round_trip_cost_bp": (
            None if normalized_scenario.is_estimated else normalized_scenario.fixed_round_trip_cost_bp
        ),
        "cost_contract_hash": recommendation_cost_contract_hash(
            normalized_scenario.fixed_round_trip_cost_bp,
            cost_scenario=normalized_scenario if normalized_scenario.is_estimated else None,
        ),
        "label_registry_hash": recommendation_label_registry_hash(
            cost_scenario=normalized_scenario if normalized_scenario.is_estimated else None,
        ),
        "current_restated": True,
        "research_only": True,
        "natural_outcome_only": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "prediction_output_present": False,
    }
    if feature_schema_version == CURRENT_OBSERVED_FEATURE_SNAPSHOT_V2:
        capture_body.update(
            {
                "scope_mode": "verified_scheduled_snapshot_cohort",
                "composition_sha256": feature_snapshot.get("composition_sha256"),
                "cohort_hash": feature_snapshot.get("cohort_hash"),
            }
        )
    for raw_row in capture_rows:
        if not isinstance(raw_row, Mapping):
            return {"status": "blocked", "reason": "current_input_capture_feature_row_invalid"}
        symbol = str(raw_row.get("symbol") or "")
        entry_pin = entry_by_symbol.get(symbol)
        if not symbol or not isinstance(entry_pin, Mapping):
            return {"status": "blocked", "reason": "current_input_capture_entry_symbol_mismatch"}
        raw_values = raw_row.get("feature_values")
        feature_ids = raw_row.get("feature_ids")
        row_sha = str(raw_row.get("row_sha256") or "")
        source_row_hashes = raw_row.get("source_row_sha256_by_table")
        if (
            raw_row.get("decision_date") != decision_date.isoformat()
            or feature_ids != list(CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids)
            or not isinstance(raw_values, list)
            or len(raw_values) != len(CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids)
            or any(value is not None and type(value) is not int for value in raw_values)
            or not _is_sha256_text(row_sha)
            or not isinstance(source_row_hashes, list)
            or len(source_row_hashes) != 4
            or any(
                not isinstance(item, list)
                or len(item) != 2
                or type(item[0]) is not str
                or not _is_sha256_text(item[1])
                for item in source_row_hashes
            )
        ):
            return {"status": "blocked", "reason": "current_input_capture_feature_row_contract_invalid"}
        capture_body["rows"].append(
            {
                "row_id": str(entry_pin.get("row_id") or ""),
                "symbol": symbol,
                "decision_date": decision_date.isoformat(),
                "feature_as_of_date": str(raw_row.get("feature_as_of_date") or ""),
                "feature_available_date": str(raw_row.get("feature_available_date") or ""),
                "feature_available_at": str(raw_row.get("local_current_observed_at") or ""),
                "feature_registry_id": raw_row.get("feature_registry_id"),
                "feature_registry_hash": raw_row.get("feature_registry_hash"),
                "feature_schema_hash": raw_row.get("feature_schema_hash"),
                "feature_ids": list(feature_ids),
                "feature_values": list(raw_values),
                "source_row_sha256_by_table": [list(item) for item in source_row_hashes],
                "feature_row_sha256": row_sha,
                "entry_price_pin": dict(entry_pin),
            }
        )
    if {str(row["symbol"]) for row in capture_body["rows"]} != {
        str(symbol) for symbol in symbols
    } or len(capture_body["rows"]) != len(symbols):
        return {"status": "blocked", "reason": "current_input_capture_scope_is_not_unique"}
    content_sha256 = _source_contract_hash_payload(capture_body)
    capture_body["capture_id"] = (
        f"current-observed:{decision_date.isoformat()}:{capture_body['cycle_id']}:{content_sha256[7:]}"
    )
    capture_body["content_sha256"] = content_sha256
    try:
        verified = verify_current_observed_input_capture(capture_body)
        cycle_token = hashlib.sha256(str(capture_body["cycle_id"]).encode("utf-8")).hexdigest()[:20]
        capture_path = (
            Path(output_root).resolve()
            / "recommendation_learning"
            / "current_observed_captures"
            / decision_date.isoformat()
            / cycle_token
            / f"{content_sha256[7:]}.json"
        )
        _write_json_once(capture_path, verified)
        persisted = verify_current_observed_input_capture(
            capture_path,
            expected_sha256=_sha256_file(capture_path),
        )
    except (OSError, RuntimeError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
        return {
            "status": "blocked",
            "reason": f"current_input_capture_verification_failed:{type(exc).__name__}",
            "diagnostic": str(exc),
            "capture_eligible": False,
        }
    return {
        "status": "captured",
        "reason": "immutable_no_model_current_observation_saved",
        "capture_id": persisted.get("capture_id"),
        "capture_path": str(capture_path),
        "capture_sha256": _sha256_file(capture_path),
        "content_sha256": persisted.get("content_sha256"),
        "cycle_id": persisted.get("cycle_id"),
        "decision_date": persisted.get("decision_date"),
        "symbol_count": len(persisted.get("rows", [])),
        "cost_scenario_hash": persisted.get("cost_scenario_hash"),
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
        "prediction_output_present": False,
    }


def _path_is_plain(path: Path, *, directory: bool) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    if stat.S_ISLNK(info.st_mode) or attributes & 0x400:
        return False
    return stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)


def _current_observed_outcome_samples(
    *,
    capture: Mapping[str, Any],
    outcome: Mapping[str, Any],
    training_as_of: date,
    feature_count: int,
) -> tuple[RecommendationCalibrationSample, ...]:
    """Convert only independently verified mature current-observed rows to research samples."""

    if (
        outcome.get("verification_status") != "verified"
        or outcome.get("status") not in {"matured", "partial"}
        or outcome.get("current_restated") is not True
        or outcome.get("historical_pit_eligible") is not False
        or outcome.get("formal_training_allowed") is not False
        or outcome.get("research_only") is not True
        or outcome.get("natural_outcome_only") is not True
        or outcome.get("promotion_credit_created") is not False
        or outcome.get("historical_replay_is_natural_evidence") is not False
        or outcome.get("capture_id") != capture.get("capture_id")
        or outcome.get("capture_sha256") != capture.get("capture_sha256")
    ):
        raise ValueError("current-observed outcome/capture identity or qualification differs")
    raw_outcomes = outcome.get("outcomes")
    capture_rows_raw = capture.get("rows")
    if not isinstance(raw_outcomes, list) or not isinstance(capture_rows_raw, list):
        raise ValueError("current-observed outcome or capture rows are malformed")
    if type(outcome.get("matured_sample_count")) is not int or outcome["matured_sample_count"] != len(raw_outcomes):
        raise ValueError("current-observed matured row count differs from verified rows")
    rows_by_id = {
        str(row.get("row_id") or ""): row
        for row in capture_rows_raw
        if isinstance(row, Mapping) and str(row.get("row_id") or "")
    }
    if len(rows_by_id) != len(capture_rows_raw):
        raise ValueError("current-observed capture has duplicate or missing row identities")
    fixed_cost = capture.get("fixed_round_trip_cost_bp")
    if fixed_cost is not None and (type(fixed_cost) is not int or fixed_cost < 0):
        raise ValueError("current-observed capture fixed cost is invalid")
    scenario_value = capture.get("cost_scenario")
    if not isinstance(scenario_value, Mapping):
        raise ValueError("current-observed capture cost scenario metadata is missing")
    scenario = normalize_cost_scenario(
        scenario_value,
        fixed_round_trip_cost_bp=fixed_cost,
    )
    if (
        capture.get("cost_status") != "verified"
        or capture.get("cost_scenario_id") != scenario.scenario_id
        or capture.get("cost_scenario_version") != scenario.scenario_version
        or capture.get("cost_scenario_hash") != scenario.scenario_hash
        or capture.get("cost_basis") != scenario.cost_basis
    ):
        raise ValueError("current-observed capture cost scenario identity differs")

    samples: list[RecommendationCalibrationSample] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_row in raw_outcomes:
        if not isinstance(raw_row, Mapping):
            raise ValueError("current-observed mature row is not an object")
        row = dict(raw_row)
        capture_row_id = row.get("capture_row_id")
        capture_row = rows_by_id.get(str(capture_row_id or ""))
        if capture_row is None:
            raise ValueError("current-observed mature row has no exact capture feature row")
        symbol = row.get("symbol")
        decision_text = row.get("capture_decision_date")
        feature_as_of = row.get("feature_as_of_date")
        feature_available = row.get("feature_available_date")
        label_end = row.get("label_end_date")
        label_available = row.get("label_available_date")
        values = row.get("feature_values")
        stock_return = row.get("stock_return_bp")
        benchmark_return = row.get("benchmark_return_bp")
        upside_label = row.get("upside_label")
        if (
            not isinstance(symbol, str)
            or not symbol.strip()
            or decision_text != capture.get("decision_date")
            or decision_text != capture_row.get("decision_date")
            or feature_as_of != capture_row.get("feature_as_of_date")
            or feature_available != capture_row.get("feature_available_date")
            or row.get("feature_row_sha256") != capture_row.get("feature_row_sha256")
            or values != capture_row.get("feature_values")
            or not isinstance(values, list)
            or len(values) != feature_count
            or any(value is not None and type(value) is not int for value in values)
            or type(stock_return) is not int
            or type(benchmark_return) is not int
            or type(upside_label) is not int
            or upside_label not in (0, 1)
            or upside_label != int(stock_return > 0)
            or type(decision_text) is not str
            or type(feature_as_of) is not str
            or type(feature_available) is not str
            or type(label_end) is not str
            or type(label_available) is not str
            or row.get("source_available_at") is not None
            or row.get("current_restated") is not True
            or row.get("historical_pit_eligible") is not False
            or row.get("formal_training_allowed") is not False
            or row.get("research_only") is not True
            or row.get("cost_scenario_hash") != scenario.scenario_hash
            or row.get("cost_scenario_id") != scenario.scenario_id
            or row.get("cost_scenario_version") != scenario.scenario_version
            or row.get("cost_basis") != scenario.cost_basis
        ):
            raise ValueError("current-observed mature row differs from its frozen capture identity")
        decision_day = date.fromisoformat(decision_text)
        feature_day = date.fromisoformat(feature_as_of)
        feature_available_day = date.fromisoformat(feature_available)
        label_end_day = date.fromisoformat(label_end)
        label_available_day = date.fromisoformat(label_available)
        if (
            feature_day >= decision_day
            or feature_available_day > decision_day
            or label_end_day < decision_day
            or label_available_day < label_end_day
            or label_available_day > training_as_of
        ):
            raise ValueError("current-observed mature row violates feature or label cutoff")
        observed_at_value = row.get("label_observed_at")
        if type(observed_at_value) is not str or not observed_at_value.strip():
            raise ValueError("current-observed label observation clock is missing")
        try:
            observed_at = datetime.fromisoformat(observed_at_value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("current-observed label observation clock is invalid") from exc
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("current-observed label observation clock must be aware")
        if observed_at.astimezone(TAIPEI).date() != label_available_day:
            raise ValueError("current-observed label date differs from its local observation clock")

        estimated_cost_values: dict[str, str | int | None] = {}
        estimated_cost_bp = row.get("estimated_round_trip_cost_bp")
        if estimated_cost_bp is not None and (type(estimated_cost_bp) is not int or estimated_cost_bp < 0):
            raise ValueError("current-observed estimated round-trip cost bp is invalid")
        for field_name in (
            "estimated_buy_cost_twd",
            "estimated_sell_cost_twd",
            "estimated_round_trip_cost_twd",
            "gross_buy_amount_twd",
            "gross_sell_amount_twd",
            "net_profit_twd",
        ):
            raw_value = row.get(field_name)
            if raw_value is not None:
                if type(raw_value) is not str or not raw_value.strip():
                    raise ValueError(f"current-observed {field_name} must be exact decimal text or null")
                try:
                    parsed_value = Decimal(raw_value)
                except InvalidOperation as exc:
                    raise ValueError(f"current-observed {field_name} is not decimal text") from exc
                if not parsed_value.is_finite():
                    raise ValueError(f"current-observed {field_name} must be finite")
                if field_name != "net_profit_twd" and parsed_value < 0:
                    raise ValueError(f"current-observed {field_name} cannot be negative")
                estimated_cost_values[field_name] = raw_value
            else:
                estimated_cost_values[field_name] = None
        if scenario.is_estimated:
            cost_estimate_status = row.get("cost_estimate_status")
            if cost_estimate_status not in {"estimated", "unavailable"}:
                raise ValueError("current-observed estimated cost status is missing or unsupported")

        identity = (symbol, decision_text, scenario.scenario_hash)
        if identity in seen:
            raise ValueError("current-observed outcome contains duplicate symbol/date/cost rows")
        seen.add(identity)
        row_id = f"current-observed-natural:{capture.get('capture_id')}:{capture_row_id}"
        sample = RecommendationCalibrationSample.from_forward_return(
            row_id=row_id,
            symbol=symbol,
            decision_date=decision_text,
            feature_as_of_date=feature_as_of,
            feature_available_date=feature_available,
            label_end_date=label_end,
            label_available_date=label_available,
            feature_values=tuple(values),
            stock_return_bp=stock_return,
            benchmark_return_bp=benchmark_return,
            fixed_round_trip_cost_bp=None if scenario.is_estimated else fixed_cost,
            observed_liquidity_cost_bp=None,
            rule_probability_bp=NULL_BENCHMARK_PROBABILITY_BP,
            rule_baseline_id=NULL_BENCHMARK_BASELINE_ID,
            source_quality="current_observed_natural_research",
            cost_scenario=scenario if scenario.is_estimated else None,
            cost_estimate=(
                {
                    **estimated_cost_values,
                    "estimated_round_trip_cost_bp": estimated_cost_bp,
                    "market_replay_date": decision_text,
                }
                if scenario.is_estimated
                else None
            ),
            estimated_round_trip_cost_bp=(estimated_cost_bp if scenario.is_estimated else None),
            estimated_round_trip_cost_twd=(
                cast(str | None, estimated_cost_values["estimated_round_trip_cost_twd"])
                if scenario.is_estimated
                else None
            ),
            estimated_buy_cost_twd=(
                cast(str | None, estimated_cost_values["estimated_buy_cost_twd"])
                if scenario.is_estimated
                else None
            ),
            estimated_sell_cost_twd=(
                cast(str | None, estimated_cost_values["estimated_sell_cost_twd"])
                if scenario.is_estimated
                else None
            ),
            net_profit_twd=(
                cast(str | None, estimated_cost_values["net_profit_twd"])
                if scenario.is_estimated
                else None
            ),
            market_replay_date=decision_text if scenario.is_estimated else None,
        )
        # This bootstrap lane has no model prediction for either target.  The
        # verified outcome receipt may retain a legitimate fee/tax-derived
        # after-cost label, but the calibration sample is deliberately limited
        # to the gross-upside label and named null benchmark baseline.  Clear
        # the factory's compatibility baseline when it inferred one from the
        # after-cost label; never let that baseline masquerade as a forecast.
        if (
            sample.after_cost_profit_label is not None
            or sample.rule_after_cost_probability_bp is not None
            or sample.rule_after_cost_baseline_id is not None
        ):
            sample = replace(
                sample,
                after_cost_profit_label=None,
                rule_after_cost_probability_bp=None,
                rule_after_cost_baseline_id=None,
            )
        if (
            sample.rule_after_cost_probability_bp is not None
            or sample.rule_after_cost_baseline_id is not None
            or sample.after_cost_profit_label is not None
        ):
            raise ValueError("current-observed no-model sample contains an after-cost prediction")
        samples.append(sample)
    return tuple(samples)


def _deduplicate_current_observed_samples(
    samples: list[tuple[RecommendationCalibrationSample, str]],
) -> tuple[RecommendationCalibrationSample, ...]:
    """Reuse identical verified captures, but block any source or label conflict."""

    unique_samples: dict[
        tuple[str, str, str], tuple[RecommendationCalibrationSample, str]
    ] = {}
    for sample, semantic_hash in samples:
        if not _is_sha256_text(semantic_hash):
            raise ValueError("current-observed semantic identity hash is invalid")
        key = (sample.symbol, sample.decision_date, sample.cost_scenario_hash)
        prior = unique_samples.get(key)
        if prior is not None and (
            prior[1] != semantic_hash
            or replace(prior[0], row_id="semantic-identity-comparison")
            != replace(sample, row_id="semantic-identity-comparison")
        ):
            raise ValueError("conflicting immutable current-observed rows")
        if prior is None:
            stable_row_id = (
                "current-observed-natural-semantic:"
                f"{semantic_hash.removeprefix('sha256:')[:32]}"
            )
            unique_samples[key] = (replace(sample, row_id=stable_row_id), semantic_hash)
    return tuple(
        sorted(
            (item[0] for item in unique_samples.values()),
            key=lambda row: (row.decision_date, row.symbol, row.row_id),
        )
    )


def _current_observed_natural_research_fit(
    *,
    learning_output_root: Path,
    data_root: Path,
    source_db: Path,
    source_contract_audit: Mapping[str, Any],
    current_feature_snapshot: Mapping[str, Any],
    decision_date: date,
    evaluation_at: datetime,
    fixed_round_trip_cost_bp: int | None,
    cost_scenario: RecommendationCostScenario,
    session_resolver: NaturalMaturitySessionResolver,
) -> dict[str, Any]:
    """Build and consume exact current-observed outcome receipts in an isolated shadow root."""

    base_status = {
        "scope": "current_observed_natural_research_only",
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "promotion_credit_created": False,
        "formal_lane_status": "blocked_by_historical_source_revision",
    }
    if (
        evaluation_at.tzinfo is None
        or evaluation_at.utcoffset() is None
        or evaluation_at.astimezone(TAIPEI).date() != decision_date
    ):
        return {**base_status, "status": "pending", "reason": "current_evaluation_clock_mismatch"}
    binding, binding_reason = _capture_source_contract_binding(source_contract_audit)
    snapshot_status = current_feature_snapshot.get("status")
    if (
        binding is None
        or binding.get("binding_mode") != "current_observed"
        or snapshot_status != "captured"
    ):
        return {
            **base_status,
            "status": "pending",
            "reason": binding_reason or "verified_current_g6_snapshot_unavailable",
            "snapshot_status": snapshot_status,
        }

    capture_root = (
        learning_output_root.resolve()
        / "recommendation_learning"
        / "current_observed_captures"
    )
    if not capture_root.exists():
        return {**base_status, "status": "pending", "reason": "no_current_observed_input_captures"}
    if not _path_is_plain(capture_root, directory=True):
        return {**base_status, "status": "blocked", "reason": "capture_root_is_not_a_plain_directory"}
    capture_paths: list[Path] = []
    try:
        for date_entry in sorted(capture_root.iterdir(), key=lambda item: item.name):
            if not _path_is_plain(date_entry, directory=True):
                return {**base_status, "status": "blocked", "reason": "unsafe_capture_date_entry"}
            try:
                capture_day = date.fromisoformat(date_entry.name)
            except ValueError:
                return {**base_status, "status": "blocked", "reason": "unrecognized_capture_date_directory"}
            if capture_day > decision_date:
                continue
            for cycle_entry in sorted(date_entry.iterdir(), key=lambda item: item.name):
                if not _path_is_plain(cycle_entry, directory=True):
                    return {**base_status, "status": "blocked", "reason": "unsafe_capture_cycle_entry"}
                for capture_entry in sorted(cycle_entry.iterdir(), key=lambda item: item.name):
                    if not _path_is_plain(capture_entry, directory=False) or capture_entry.suffix.lower() != ".json":
                        return {**base_status, "status": "blocked", "reason": "unsafe_or_unrecognized_capture_entry"}
                    capture_paths.append(capture_entry)
                    if len(capture_paths) > 512:
                        return {**base_status, "status": "blocked", "reason": "capture_scan_bound_exceeded"}
    except OSError as exc:
        return {
            **base_status,
            "status": "blocked",
            "reason": f"capture_scan_failed:{type(exc).__name__}",
        }
    if not capture_paths:
        return {**base_status, "status": "pending", "reason": "no_current_observed_input_captures"}

    service = _build_natural_outcome_service(
        provider=MLHistoricalSnapshotProvider(source_db),
        source_db=source_db,
        session_resolver=session_resolver,
        evaluation_at=evaluation_at,
    )
    outcome_root = capture_root.parent / "current_observed_outcomes"
    evaluation_token = evaluation_at.astimezone(timezone.utc).isoformat(timespec="microseconds")
    evaluation_date = evaluation_at.astimezone(TAIPEI).date().isoformat()
    outcome_refs: list[dict[str, str]] = []
    samples: list[tuple[RecommendationCalibrationSample, str]] = []
    pending_count = 0
    diagnostics: list[str] = []
    current_terminal_token = str(current_feature_snapshot.get("discovery_cycle_terminal_sha256") or "")
    current_snapshot_token = str(current_feature_snapshot.get("content_sha256") or "")
    if not _is_sha256_text(current_terminal_token) or not _is_sha256_text(current_snapshot_token):
        return {**base_status, "status": "blocked", "reason": "current_g6_terminal_or_snapshot_hash_missing"}
    for capture_path in capture_paths:
        try:
            capture_sha256 = _sha256_file(capture_path)
            capture = verify_current_observed_input_capture(
                capture_path,
                expected_sha256=capture_sha256,
            )
            capture_date = str(capture.get("decision_date") or "")
            if capture_date != capture_path.parent.parent.name:
                raise ValueError("capture path date does not match capture payload")
            token_body = {
                "capture_sha256": capture_sha256,
                "current_terminal_sha256": current_terminal_token,
                "current_snapshot_sha256": current_snapshot_token,
                "evaluation_at": evaluation_token,
            }
            token = hashlib.sha256(
                json.dumps(token_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            cycle_token = hashlib.sha256(
                str(capture.get("cycle_id") or "").encode("utf-8")
            ).hexdigest()[:20]
            receipt_path = (
                outcome_root
                / capture_date
                / cycle_token
                / evaluation_date
                / current_terminal_token.removeprefix("sha256:")[:20]
                / f"{token}.json"
            )
            outcome_unverified = service.build_current_observed_outcomes_for_capture(
                capture_path,
                required_source_contract=source_contract_audit,
                evaluation_at=evaluation_at,
                output_path=receipt_path,
                max_rows=1_000,
            )
            outcome_file_sha = outcome_unverified.get("receipt_file_sha256")
            if type(outcome_file_sha) is not str or not _is_sha256_text(outcome_file_sha):
                raise ValueError("outcome service returned no exact receipt file hash")
            outcome = verify_current_observed_outcome_receipt(
                receipt_path,
                expected_sha256=outcome_file_sha,
                capture_path=capture_path,
            )
            outcome_path = Path(str(outcome.get("receipt_path") or ""))
            if (
                outcome_path.resolve() != receipt_path.resolve()
                or outcome.get("receipt_file_sha256") != outcome_file_sha
                or outcome.get("verification_status") not in {
                    "verified",
                    "verified_pending",
                    "verified_without_matured_rows",
                    "verified_blocked_receipt",
                }
            ):
                raise ValueError("outcome receipt verifier identity or status differs")
            outcome_refs.append(
                {
                    "capture_path": str(capture_path.resolve()),
                    "capture_sha256": capture_sha256,
                    "capture_id": str(capture.get("capture_id") or ""),
                    "outcome_path": str(receipt_path.resolve()),
                    "outcome_sha256": outcome_file_sha,
                    "outcome_status": str(outcome.get("status") or ""),
                    "verification_status": str(outcome.get("verification_status") or ""),
                }
            )
            if outcome.get("status") not in {"matured", "partial"}:
                pending_count += int(outcome.get("pending_sample_count") or 0)
                diagnostics.extend(
                    str(item) for item in outcome.get("diagnostics", ()) if isinstance(item, str)
                )
                continue
            mapped_samples = _current_observed_outcome_samples(
                capture=capture,
                outcome=outcome,
                training_as_of=decision_date,
                feature_count=len(CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids),
            )
            capture_rows = capture.get("rows")
            outcome_rows = outcome.get("outcomes")
            if not isinstance(capture_rows, list) or not isinstance(outcome_rows, list):
                raise ValueError("verified current-observed rows are missing for semantic deduplication")
            capture_id = str(capture.get("capture_id") or "")
            sample_prefix = f"current-observed-natural:{capture_id}:"
            for sample in mapped_samples:
                if not sample.row_id.startswith(sample_prefix):
                    raise ValueError("current-observed sample row identity is not capture-bound")
                capture_row_id = sample.row_id[len(sample_prefix) :]
                capture_row = next(
                    (
                        item
                        for item in capture_rows
                        if isinstance(item, Mapping) and item.get("row_id") == capture_row_id
                    ),
                    None,
                )
                outcome_row = next(
                    (
                        item
                        for item in outcome_rows
                        if isinstance(item, Mapping)
                        and item.get("capture_row_id") == capture_row_id
                    ),
                    None,
                )
                if not isinstance(capture_row, Mapping) or not isinstance(outcome_row, Mapping):
                    raise ValueError("verified current-observed semantic row proof is missing")
                semantic_hash = _current_observed_capture_semantic_hash(
                    capture_row=capture_row,
                    outcome_row=outcome_row,
                )
                samples.append((sample, semantic_hash))
            pending_count += int(outcome.get("pending_sample_count") or 0)
        except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
            diagnostics.append(f"capture_or_outcome_rejected:{capture_path.name}:{type(exc).__name__}")

    try:
        final_samples = _deduplicate_current_observed_samples(samples)
    except ValueError:
        return {
            **base_status,
            "status": "blocked",
            "reason": "conflicting_immutable_current_observed_rows_for_symbol_date_cost",
            "outcome_receipt_count": len(outcome_refs),
            "matured_row_count": len(samples),
            "diagnostics": diagnostics,
        }
    base_status.update(
        {
            "outcome_receipts": outcome_refs,
            "outcome_receipt_count": len(outcome_refs),
            "matured_row_count": len(final_samples),
            "pending_row_count": pending_count,
            "diagnostics": list(dict.fromkeys(diagnostics)),
            "current_snapshot_cycle_id": current_feature_snapshot.get("cycle_id"),
            "current_snapshot_raw_run_id": current_feature_snapshot.get("raw_run_id"),
            "current_snapshot_terminal_path": current_feature_snapshot.get("cycle_terminal_path"),
            "current_snapshot_terminal_sha256": current_feature_snapshot.get("cycle_terminal_sha256"),
            "current_snapshot_observed_at": current_feature_snapshot.get("observed_at"),
            "training_as_of": evaluation_token,
        }
    )
    if not final_samples:
        return {**base_status, "status": "pending", "reason": "no_matured_current_observed_rows"}

    source_contract_receipt = source_contract_audit.get("source_contract_receipt")
    source_contract_receipt = (
        source_contract_receipt if isinstance(source_contract_receipt, Mapping) else {}
    )
    discovery_status_bytes = current_feature_snapshot.get("discovery_status_bytes_base64")
    source_identity = {
        "schema_version": "current-observed-natural-research-source-identity.v1",
        "evaluation_at": evaluation_token,
        "training_as_of": decision_date.isoformat(),
        "formal_lane": {
            "status": "blocked_source_revision",
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
        },
        "discovery": {
            "raw_status_path": current_feature_snapshot.get("discovery_status_path"),
            "raw_status_sha256": current_feature_snapshot.get("discovery_status_sha256"),
            "raw_status_bytes_base64": discovery_status_bytes,
            "discovery_raw_run_id": current_feature_snapshot.get("discovery_raw_run_id"),
            "cycle_terminal_path": current_feature_snapshot.get("discovery_cycle_terminal_path"),
            "cycle_terminal_sha256": current_feature_snapshot.get("discovery_cycle_terminal_sha256"),
            "cycle_terminal_status": current_feature_snapshot.get("discovery_cycle_terminal_status"),
        },
        "source_cycle": {
            "raw_run_id": current_feature_snapshot.get("raw_run_id"),
            "cycle_id": current_feature_snapshot.get("cycle_id"),
            "source_date": current_feature_snapshot.get("cycle_source_date"),
            "terminal_path": current_feature_snapshot.get("cycle_terminal_path"),
            "terminal_sha256": current_feature_snapshot.get("cycle_terminal_sha256"),
            "reuse_source_identity": current_feature_snapshot.get("reuse_source_identity"),
        },
        "snapshot": {
            "database_path": current_feature_snapshot.get("snapshot_database_path"),
            "database_sha256": current_feature_snapshot.get("snapshot_database_sha256"),
            "receipt_path": current_feature_snapshot.get("snapshot_receipt_path"),
            "receipt_sha256": current_feature_snapshot.get("snapshot_receipt_sha256"),
            "context_envelope_path": current_feature_snapshot.get("source_context_envelope_path"),
            "context_envelope_sha256": current_feature_snapshot.get(
                "source_context_envelope_sha256"
            ),
            "source_rows_sha256_by_table": current_feature_snapshot.get(
                "source_rows_sha256_by_table"
            ),
            "observed_at": current_feature_snapshot.get("observed_at"),
            "feature_as_of_date": current_feature_snapshot.get("feature_as_of_date"),
            "symbols": current_feature_snapshot.get("symbols"),
            "rows_sha256": current_feature_snapshot.get("rows_sha256"),
            "content_sha256": current_feature_snapshot.get("content_sha256"),
            "feature_registry_hash": current_feature_snapshot.get("feature_registry_hash"),
            "feature_schema_hash": current_feature_snapshot.get("feature_schema_hash"),
        },
        "source_contract": {
            "binding_mode": binding.get("binding_mode"),
            "path": binding.get("contract_path"),
            "content_sha256": binding.get("contract_content_sha256"),
            "file_sha256": binding.get("contract_file_sha256"),
            "receipt_path": source_contract_receipt.get("receipt_path"),
            "receipt_file_sha256": source_contract_receipt.get("receipt_file_sha256"),
        },
        "outcome_receipts": outcome_refs,
    }
    fit_result = fit_current_observed_natural_research(
        learning_output_root=learning_output_root,
        samples=final_samples,
        training_as_of=decision_date,
        evaluation_at=evaluation_at,
        fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        cost_scenario=cost_scenario,
        outcome_receipts=outcome_refs,
        source_identity=source_identity,
        data_root=data_root,
    )
    return {
        **base_status,
        **dict(fit_result),
        "matured_training_row_count": len(final_samples),
        "formal_training_allowed": False,
        "historical_pit_eligible": False,
        "promotion_credit_created": False,
    }


def _run_current_observed_natural_research_lane(
    *,
    learning_output_root: Path,
    data_root: Path,
    source_db: Path,
    source_contract_audit: Mapping[str, Any],
    current_feature_snapshot: Mapping[str, Any],
    decision_date: date,
    evaluation_at: datetime,
    fixed_round_trip_cost_bp: int | None,
    cost_scenario: RecommendationCostScenario,
    capture_requested: bool,
    calendar_cache_path: Path | None,
    temporary_closure_path: Path | None,
) -> dict[str, Any]:
    """Capture prospective no-model observations and scan their natural labels.

    This lane is deliberately independent from historical replay and the
    formal calibration runner.  A missing same-day entry is a pending capture,
    but does not stop the scan of older immutable captures which may have
    matured since the previous run.
    """

    base_status: dict[str, Any] = {
        "scope": "current_observed_natural_research_only",
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "promotion_credit_created": False,
    }
    local_evaluation_date: date | None = None
    if evaluation_at.tzinfo is not None and evaluation_at.utcoffset() is not None:
        local_evaluation_date = evaluation_at.astimezone(TAIPEI).date()
    if local_evaluation_date != decision_date:
        pending = {
            **base_status,
            "status": "pending",
            "reason": "current_evaluation_date_required",
        }
        return {
            **base_status,
            "status": "pending",
            "reason": "current_evaluation_date_required",
            "current_observed_input_capture": {
                "status": "pending",
                "reason": "current_evaluation_date_required",
                "capture_eligible": False,
            },
            "current_observed_natural_research": pending,
        }
    if not capture_requested:
        input_capture = {
            "status": "not_requested",
            "reason": "current_capture_disabled_by_caller",
            "capture_eligible": False,
        }
    else:
        try:
            input_capture = _persist_current_observed_input_capture(
                output_root=learning_output_root,
                source_contract_audit=source_contract_audit,
                decision_date=decision_date,
                captured_at=evaluation_at,
                cost_scenario=cost_scenario,
                fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
            )
        except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
            input_capture = {
                "status": "blocked",
                "reason": f"current_observed_input_capture_failed:{type(exc).__name__}",
                "capture_eligible": False,
            }

    try:
        calendar_cache_path, temporary_closure_path = _natural_maturity_calendar_paths(
            calendar_cache_path=calendar_cache_path,
            temporary_closure_path=temporary_closure_path,
        )
        session_resolver = NaturalMaturitySessionResolver(
            db_path=source_db,
            calendar_cache_path=calendar_cache_path,
            temporary_closure_path=temporary_closure_path,
        )
        natural_research = _current_observed_natural_research_fit(
            learning_output_root=learning_output_root,
            data_root=data_root,
            source_db=source_db,
            source_contract_audit=source_contract_audit,
            current_feature_snapshot=current_feature_snapshot,
            decision_date=decision_date,
            evaluation_at=evaluation_at,
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
            cost_scenario=cost_scenario,
            session_resolver=session_resolver,
        )
    except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
        natural_research = {
            **base_status,
            "status": "blocked",
            "reason": f"current_observed_natural_research_failed:{type(exc).__name__}",
        }

    research_status = str(natural_research.get("status") or "pending")
    status = research_status if research_status in {"completed", "fitted_research_only", "pending", "blocked", "failed"} else "pending"
    return {
        **base_status,
        "status": status,
        "decision_date": decision_date.isoformat(),
        "evaluation_at": evaluation_at.isoformat(),
        "current_observed_input_capture": input_capture,
        "current_observed_natural_research": natural_research,
    }


def _inspect_dependencies(
    *,
    provider: MLHistoricalSnapshotProvider,
    output_root: Path,
    data_root: Path | None,
    decision_date: date,
    symbols: tuple[str, ...],
    replay_source_fingerprint: str,
    policy: RecommendationPromotionPolicy,
    source_contract_audit: Mapping[str, Any] | None = None,
    checked_clock: datetime | None = None,
    calendar_cache_path: Path | None = None,
    temporary_closure_path: Path | None = None,
) -> dict[str, Any]:
    """Perform actual read-only source checks; no caller status becomes truth."""

    diagnostics: list[str] = []
    data_status = "ready"
    outcome_status = "ready"
    drift_status = "clean"
    recovery_policy = "normal"
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
            calendar_cache_path=calendar_cache_path,
            temporary_closure_path=temporary_closure_path,
        )
        if official_trading_day is None:
            data_status = "failed"
            outcome_status = "failed"
            recovery_policy = "recoverable_attempt"
            diagnostics.append(f"official_trading_calendar_unresolved:{calendar_reason}")
        elif official_trading_day is False:
            diagnostics.append(f"official_trading_calendar_closed:{calendar_reason}")
        elif not trading_dates:
            data_status = "failed"
            outcome_status = "failed"
            recovery_policy = "recoverable_attempt"
            diagnostics.append("official_trading_day_but_explicit_symbol_rows_missing")
        if not replay_source_fingerprint:
            drift_status = "not_checked"
            diagnostics.append("replay_source_fingerprint_missing")
        else:
            diagnostics.append("source_schema_and_stat_stability_verified")
        if not trading_dates:
            diagnostics.append("non_trading_day_or_no_symbol_rows_live_capture_will_skip")
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        data_status = "failed"
        outcome_status = "failed"
        recovery_policy = (
            "fail_closed_emergency_rollback"
            if _preflight_requires_emergency(exc)
            else "recoverable_attempt"
        )
        diagnostics.append(f"source_preflight_failed:{type(exc).__name__}")
    # Active performance evidence is an immutable-receipt read.  It has its
    # own source boundary and must still be inspected when the historical
    # replay provider rejects revised PIT data above.
    if (
        checked_clock is not None
        and decision_date != checked_clock.astimezone(TAIPEI).date()
    ):
        active_performance = {
            "status": "pending",
            "reason": "natural_maturity_evaluation_date_mismatch",
            "diagnostics": (
                "historical_decision_date_natural_lane_skipped_to_avoid_future_clock",
            ),
        }
    else:
        try:
            active_performance = _inspect_active_model_performance(
                output_root=output_root,
                data_root=data_root,
                decision_date=decision_date,
                policy=policy,
                source_db=provider.database_path,
            )
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            active_performance = {
                "status": "failed",
                "reason": f"active_model_performance_check_failed:{type(exc).__name__}",
                "diagnostics": ("active_model_performance_receipt_check_failed",),
            }
    drift_status = str(active_performance.get("status") or drift_status)
    diagnostics.extend(
        str(item)
        for item in active_performance.get("diagnostics", ())
        if str(item).strip()
    )
    return {
        "data_status": data_status,
        "outcome_status": outcome_status,
        "drift_status": drift_status,
        "recovery_policy": recovery_policy,
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
        "source_contract": dict((source_contract_audit or {}).get("source_contract") or {}),
        "source_contract_receipt": dict(
            (source_contract_audit or {}).get("source_contract_receipt") or {}
        ),
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _official_trading_day(
    *,
    provider: MLHistoricalSnapshotProvider,
    decision_date: date,
    calendar_cache_path: Path | None = None,
    temporary_closure_path: Path | None = None,
) -> tuple[bool | None, str]:
    """Use the existing official-calendar contract without network guessing."""

    resolved_calendar_path, resolved_temporary_path = _natural_maturity_calendar_paths(
        calendar_cache_path=calendar_cache_path,
        temporary_closure_path=temporary_closure_path,
    )
    calendar = OfficialTradingCalendar(
        db_path=provider.database_path,
        calendar_cache_path=resolved_calendar_path,
        temporary_closure_path=resolved_temporary_path,
    )
    return calendar.is_official_trading_day(decision_date, allow_online_probe=False)


def _verified_current_capture_session_proof(
    *,
    provider: MLHistoricalSnapshotProvider,
    decision_date: date,
    observed_at: datetime,
    calendar_cache_path: Path | None,
    temporary_closure_path: Path | None,
) -> dict[str, Any]:
    """Return the hash-bound official session proof without a live lookup."""

    resolved_calendar_path, resolved_temporary_path = _natural_maturity_calendar_paths(
        calendar_cache_path=calendar_cache_path,
        temporary_closure_path=temporary_closure_path,
    )
    calendar = OfficialTradingCalendar(
        db_path=provider.database_path,
        calendar_cache_path=resolved_calendar_path,
        temporary_closure_path=resolved_temporary_path,
    )
    is_trading_day, reason = calendar.is_official_trading_day(
        decision_date,
        allow_online_probe=False,
    )
    if is_trading_day is not True:
        raise ValueError(f"official session is unresolved or closed: {reason}")
    schedule_evidence_by_year = getattr(calendar, "_schedule_evidence", None)
    schedule_evidence = (
        schedule_evidence_by_year.get(decision_date.year)
        if isinstance(schedule_evidence_by_year, Mapping)
        else None
    )
    if (
        not isinstance(schedule_evidence, Mapping)
        or schedule_evidence.get("mode") != "hash_bound_official_calendar_cache"
    ):
        # A local market-index row can also resolve a trading day, but it is
        # insufficient for a close-time proof. Never replace the official
        # cache with a weekday or database-presence assumption.
        raise ValueError("hash-bound official annual calendar cache is required")
    evidence = calendar.evidence_for(decision_date)
    return _build_current_observed_entry_session_proof(
        decision_date=decision_date,
        observed_at=observed_at,
        calendar_evidence=evidence,
    )


def _capture_scope_token(scope: str | None, symbols: tuple[str, ...]) -> str:
    """Return a stable, filesystem-safe scope for immutable daily captures."""

    raw = str(scope or "").strip()
    if not raw:
        raw = "explicit-" + hashlib.sha256(
            json.dumps(sorted(set(symbols)), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
    safe = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in raw
    )
    return safe[:120] or "unspecified"


def _capture_row_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    """Identity of a point-in-time feature row, excluding model outputs."""

    return {
        "symbol": str(row.get("symbol") or "").strip(),
        "decision_date": str(row.get("decision_date") or "")[:10],
        "feature_as_of_date": str(row.get("feature_as_of_date") or "")[:10],
        "feature_available_date": str(row.get("feature_available_date") or "")[:10],
        "feature_values": list(row.get("feature_values") or []),
    }


def _capture_input_identity(item: RecommendationPredictionCaptureInput) -> dict[str, Any]:
    return _capture_row_identity(
        {
            "symbol": item.symbol,
            "decision_date": item.decision_date,
            "feature_as_of_date": item.feature_as_of_date,
            "feature_available_date": item.feature_available_date,
            "feature_values": list(item.feature_values),
        }
    )


def _capture_source_identity(binding: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(binding, Mapping):
        return None
    return {
        "decision_date": str(binding.get("decision_date") or "")[:10],
        "symbols": sorted(
            str(item).strip()
            for item in binding.get("symbols", [])
            if str(item).strip()
        ),
        "contract_path": str(binding.get("contract_path") or ""),
        "contract_file_sha256": str(binding.get("contract_file_sha256") or ""),
        "contract_content_sha256": str(binding.get("contract_content_sha256") or ""),
        "feature_snapshot_content_sha256": str(
            binding.get("feature_snapshot_content_sha256") or ""
        ),
        "price_up_prospective_status": str(
            binding.get("price_up_prospective_status") or ""
        ),
    }


def _capture_request_fingerprint(
    *,
    candidate_metadata: Mapping[str, Any],
    decision_date: str,
    inputs: tuple[RecommendationPredictionCaptureInput, ...],
    source_contract_binding: Mapping[str, Any] | None,
) -> str:
    body = {
        "candidate_id": str(candidate_metadata.get("candidate_id") or ""),
        "candidate_freeze_hash": str(candidate_metadata.get("candidate_freeze_hash") or ""),
        "candidate_manifest_hash": str(candidate_metadata.get("manifest_hash") or ""),
        "candidate_artifact_hash": str(candidate_metadata.get("artifact_hash") or ""),
        "dataset_hash": str(candidate_metadata.get("dataset_hash") or ""),
        "capture_as_of_date": str(decision_date)[:10],
        "rows": sorted(
            (_capture_input_identity(item) for item in inputs),
            key=lambda row: row["symbol"],
        ),
        "source_contract": _capture_source_identity(source_contract_binding),
    }
    candidate_cost_basis = str(candidate_metadata.get("cost_basis") or "")
    declared_cost_scenario_hash = str(candidate_metadata.get("cost_scenario_hash") or "")
    if candidate_cost_basis == "estimated_research_only" and declared_cost_scenario_hash:
        # The request identity is scenario-scoped for the new lane.  Legacy
        # captures intentionally keep the historical fingerprint body.
        body["cost_scenario_hash"] = declared_cost_scenario_hash
    return "sha256:" + hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _read_verified_candidate_capture(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("capture is not an object")
        _verify_capture_payload(payload)
        return payload, None
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return None, f"{type(exc).__name__}:{exc}"


def _capture_matches_request(
    payload: Mapping[str, Any],
    *,
    candidate_metadata: Mapping[str, Any],
    candidate_root: Path,
    decision_date: str,
    inputs: tuple[RecommendationPredictionCaptureInput, ...],
    source_contract_binding: Mapping[str, Any] | None,
) -> bool:
    expected_by_symbol = {
        str(item.symbol).strip(): _capture_input_identity(item)
        for item in inputs
    }
    actual_rows = [row for row in payload.get("rows", []) if isinstance(row, Mapping)]
    actual_by_symbol = {
        str(row.get("symbol") or "").strip(): row for row in actual_rows
    }
    if str(payload.get("candidate_id") or "") != str(candidate_metadata.get("candidate_id") or ""):
        return False
    if str(payload.get("candidate_freeze_hash") or "") != str(
        candidate_metadata.get("candidate_freeze_hash") or ""
    ):
        return False
    if Path(str(payload.get("candidate_root") or "")).resolve() != candidate_root.resolve():
        return False
    candidate_cost_basis = str(candidate_metadata.get("cost_basis") or "")
    candidate_cost_scenario_hash = str(candidate_metadata.get("cost_scenario_hash") or "")
    payload_cost_scenario_hash = str(payload.get("cost_scenario_hash") or "")
    if candidate_cost_basis == "estimated_research_only" or payload_cost_scenario_hash:
        if not candidate_cost_scenario_hash or payload_cost_scenario_hash != candidate_cost_scenario_hash:
            return False
    if str(payload.get("capture_as_of_date") or "")[:10] != str(decision_date)[:10]:
        return False
    if set(actual_by_symbol) != set(expected_by_symbol):
        return False
    if any(
        _capture_row_identity(row) != expected_by_symbol[symbol]
        for symbol, row in actual_by_symbol.items()
    ):
        return False
    return _capture_source_identity(payload.get("source_contract_binding")) == _capture_source_identity(
        source_contract_binding
    )


def _scan_cross_capture_identity(
    *,
    capture_root: Path,
    destination: Path,
    candidate_id: str,
    decision_date: str,
    inputs: tuple[RecommendationPredictionCaptureInput, ...],
    source_contract_binding: Mapping[str, Any] | None,
    cost_scenario_hash: str | None = None,
) -> dict[str, Any]:
    """Audit same-day rows before writing a new immutable scope capture."""

    expected_by_symbol = {
        str(item.symbol).strip(): _capture_input_identity(item)
        for item in inputs
    }
    exact_symbols: set[str] = set()
    source_conflicts: set[str] = set()
    feature_conflicts: set[str] = set()
    source_paths: set[str] = set()
    paths = sorted(capture_root.rglob("*.json")) if capture_root.is_dir() else ()
    for path in paths:
        if path.resolve() == destination.resolve():
            continue
        payload, _ = _read_verified_candidate_capture(path)
        if not isinstance(payload, Mapping):
            continue
        if str(payload.get("candidate_id") or "") != candidate_id:
            continue
        if str(payload.get("capture_as_of_date") or "")[:10] != str(decision_date)[:10]:
            continue
        if cost_scenario_hash and str(
            payload.get("cost_scenario_hash") or payload.get("scenario_hash") or ""
        ) != cost_scenario_hash:
            continue
        for row in payload.get("rows", []):
            if not isinstance(row, Mapping):
                continue
            symbol = str(row.get("symbol") or "").strip()
            if symbol not in expected_by_symbol:
                continue
            source_paths.add(str(path.resolve()))
            if _capture_row_identity(row) != expected_by_symbol[symbol]:
                feature_conflicts.add(symbol)
            elif _capture_source_identity(payload.get("source_contract_binding")) == _capture_source_identity(
                source_contract_binding
            ):
                exact_symbols.add(symbol)
            else:
                source_conflicts.add(symbol)
    return {
        "exact_symbols": sorted(exact_symbols),
        "source_conflict_symbols": sorted(source_conflicts),
        "feature_conflict_symbols": sorted(feature_conflicts),
        "source_capture_paths": sorted(source_paths),
    }


def _capture_current_if_requested(
    *,
    args: argparse.Namespace,
    config: TWStockConfig,
    output_root: Path,
    source_db: Path,
    provider: MLHistoricalSnapshotProvider,
    symbols: tuple[str, ...],
    run_result: Any,
    run_scope: str | None = None,
    capture_scope: str | None = None,
    replay_config: RecommendationHistoricalReplayConfig,
    source_contract_audit: Mapping[str, Any] | None = None,
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    if not args.capture_current:
        return {"status": "not_requested"}
    resolved_scenario = normalize_cost_scenario(
        cost_scenario,
        fixed_round_trip_cost_bp=(
            int(args.fixed_round_trip_cost_bp)
            if cost_scenario is None and args.fixed_round_trip_cost_bp is not None
            else None
        ),
    )
    effective_fixed_cost = resolved_scenario.fixed_round_trip_cost_bp
    capture_clock = observed_at or _taipei_now()
    if capture_clock.tzinfo is None or capture_clock.utcoffset() is None:
        return {
            "status": "failed",
            "reason": "current_capture_clock_must_be_timezone_aware",
        }
    decision_day = (
        date.fromisoformat(str(args.decision_date)[:10])
        if args.decision_date
        else capture_clock.astimezone(TAIPEI).date()
    )
    if decision_day != capture_clock.astimezone(TAIPEI).date():
        return {
            "status": "skipped",
            "reason": "capture_current_requires_current_asia_taipei_date",
            "decision_timezone": "Asia/Taipei",
        }
    official_trading_day, calendar_reason = _official_trading_day(
        provider=provider,
        decision_date=decision_day,
        calendar_cache_path=args.calendar_cache_path,
        temporary_closure_path=args.temporary_closure_cache_path,
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
        entry_session_proof = _verified_current_capture_session_proof(
            provider=provider,
            decision_date=decision_day,
            observed_at=capture_clock,
            calendar_cache_path=args.calendar_cache_path,
            temporary_closure_path=args.temporary_closure_cache_path,
        )
        scheduled_close_at = datetime.fromisoformat(
            str(entry_session_proof["scheduled_market_close_at"])
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "status": "failed",
            "reason": "official_trading_calendar_evidence_unverified_fail_closed",
            "calendar_diagnostic": f"{type(exc).__name__}:{exc}",
            "decision_timezone": "Asia/Taipei",
        }
    if capture_clock.astimezone(scheduled_close_at.tzinfo) < scheduled_close_at:
        return {
            "status": "pending",
            "reason": "official_session_not_closed_yet_wait_for_scheduled_close",
            "decision_timezone": "Asia/Taipei",
            "scheduled_market_close_at": scheduled_close_at.isoformat(),
            "observed_at": capture_clock.isoformat(),
            "same_day_rows_consulted": False,
        }
    source_contract_binding, source_contract_reason = _capture_source_contract_binding(
        source_contract_audit
    )
    if source_contract_binding is None:
        return {
            "status": "blocked",
            "reason": source_contract_reason or "prospective_source_contract_not_ready",
            "source_contract": dict((source_contract_audit or {}).get("source_contract") or {}),
            "capture_eligible": False,
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
        capture_at = capture_clock.isoformat(timespec="seconds")
        scope_token = _capture_scope_token(capture_scope, symbols)
        candidate_capture: dict[str, Any]
        if not run_result.candidate_root or not run_result.candidate_id:
            candidate_capture = {"status": "skipped", "reason": "candidate_not_available"}
        else:
            candidate_root = Path(str(run_result.candidate_root)).resolve()
            candidate_metadata = json.loads(
                (candidate_root / "candidate.json").read_text(encoding="utf-8")
            )
            if not isinstance(candidate_metadata, Mapping):
                raise ValueError("candidate metadata is not an object")
            capture_root = (
                Path(output_root).resolve()
                / "recommendation_learning"
                / "captures"
                / decision_day.isoformat()
            )
            request_fingerprint = _capture_request_fingerprint(
                candidate_metadata=candidate_metadata,
                decision_date=decision_day.isoformat(),
                inputs=inputs,
                source_contract_binding=source_contract_binding,
            )
            scoped_root = capture_root / scope_token
            scoped_path = scoped_root / (
                f"{run_result.candidate_id}-{request_fingerprint.split(':', 1)[1][:24]}.json"
            )
            legacy_path = capture_root / f"{run_result.candidate_id}.json"
            capture_path = scoped_path
            legacy_reuse = False
            if run_scope is None and legacy_path.is_file():
                legacy_payload, legacy_error = _read_verified_candidate_capture(legacy_path)
                if legacy_payload is not None and _capture_matches_request(
                    legacy_payload,
                    candidate_metadata=candidate_metadata,
                    candidate_root=candidate_root,
                    decision_date=decision_day.isoformat(),
                    inputs=inputs,
                    source_contract_binding=source_contract_binding,
                ):
                    capture_path = legacy_path
                    legacy_reuse = True
                elif legacy_error is not None:
                    # A legacy artifact is immutable.  A malformed or
                    # mismatched file cannot be repaired in place; the new
                    # scope path below is the only safe retry destination.
                    pass

            cross_capture = _scan_cross_capture_identity(
                capture_root=capture_root,
                destination=capture_path,
                candidate_id=str(run_result.candidate_id),
                decision_date=decision_day.isoformat(),
                inputs=inputs,
                source_contract_binding=source_contract_binding,
                cost_scenario_hash=(
                    str(candidate_metadata.get("cost_scenario_hash") or "") or None
                    if str(candidate_metadata.get("cost_basis") or "")
                    == "estimated_research_only"
                    else None
                ),
            )
            if capture_path.is_file():
                payload, error = _read_verified_candidate_capture(capture_path)
                if payload is not None and _capture_matches_request(
                    payload,
                    candidate_metadata=candidate_metadata,
                    candidate_root=candidate_root,
                    decision_date=decision_day.isoformat(),
                    inputs=inputs,
                    source_contract_binding=source_contract_binding,
                ):
                    candidate_capture = {
                        "status": "already_captured",
                        "reuse_mode": "legacy_exact_identity" if legacy_reuse else "exact_scope_identity",
                        "capture_path": str(capture_path.resolve()),
                        "capture_id": payload.get("capture_id"),
                        "capture_hash": payload.get("capture_hash"),
                        "row_count": len(payload.get("rows", [])),
                        "capture_origin": payload.get("capture_origin"),
                        "capture_scope": scope_token,
                        "requested_symbols": sorted({str(item.symbol) for item in inputs}),
                        "captured_symbols": sorted(
                            str(row.get("symbol"))
                            for row in payload.get("rows", [])
                            if isinstance(row, Mapping)
                        ),
                        "capture_request_fingerprint": request_fingerprint,
                        "deduplicated_symbols": cross_capture["exact_symbols"],
                        "cross_capture_source_paths": cross_capture["source_capture_paths"],
                    }
                elif error is not None:
                    candidate_capture = {
                        "status": "failed",
                        "reason": "existing_capture_invalid_or_identity_conflict_refusing_overwrite",
                        "capture_path": str(capture_path.resolve()),
                        "capture_scope": scope_token,
                        "capture_request_fingerprint": request_fingerprint,
                        "existing_capture_error": error,
                    }
                else:
                    candidate_capture = {
                        "status": "failed",
                        "reason": "existing_capture_identity_conflict_refusing_overwrite",
                        "capture_path": str(capture_path.resolve()),
                        "capture_scope": scope_token,
                        "capture_request_fingerprint": request_fingerprint,
                    }
            else:
                from app_module.recommendation_calibration_consumer import (
                    RecommendationCalibrationConsumer,
                )

                champion_pointer_path = (
                    Path(output_root)
                    / "recommendation_learning"
                    / "recommendation-calibration-active-pointer.json"
                )
                champion_inference = RecommendationCalibrationConsumer(
                    pointer_path=champion_pointer_path,
                    feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
                    feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
                    data_root=config.data_root,
                )
                capture = RecommendationPredictionCaptureService().capture(
                    candidate_root=candidate_root,
                    feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
                    feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
                    policy_hash=RecommendationPromotionPolicy().policy_hash,
                    decision_date=decision_day.isoformat(),
                    captured_at=capture_at,
                    inputs=inputs,
                    fixed_round_trip_cost_bp=effective_fixed_cost,
                    cost_scenario=resolved_scenario,
                    data_root=config.data_root,
                    champion_pointer_path=champion_pointer_path,
                    champion_inference=champion_inference,
                    capture_origin="scheduled_live",
                    source_contract_binding=source_contract_binding,
                )
                capture.persist(capture_path)
                candidate_capture = {
                    "status": "captured",
                    "reuse_mode": "new_immutable_scope_capture",
                    "capture_path": str(capture_path.resolve()),
                    "capture_id": capture.capture_id,
                    "capture_hash": capture.capture_hash,
                    "row_count": len(capture.rows),
                    "capture_origin": capture.capture_origin,
                    "capture_scope": scope_token,
                    "requested_symbols": sorted({str(item.symbol) for item in inputs}),
                    "captured_symbols": sorted(str(row["symbol"]) for row in capture.rows),
                    "capture_request_fingerprint": request_fingerprint,
                    "deduplicated_symbols": cross_capture["exact_symbols"],
                    "cross_capture_source_paths": cross_capture["source_capture_paths"],
                    "cross_capture_source_conflict_symbols": cross_capture["source_conflict_symbols"],
                    "cross_capture_feature_conflict_symbols": cross_capture["feature_conflict_symbols"],
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
            fixed_round_trip_cost_bp=effective_fixed_cost,
            cost_scenario=resolved_scenario,
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
            "capture_scope": scope_token,
            "requested_symbols": sorted({str(item.symbol) for item in inputs}),
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
    fixed_round_trip_cost_bp: int | None,
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
    source_contract_binding: Mapping[str, Any] | None = None,
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
        current_binding_hash = (
            _source_contract_hash_payload(dict(source_contract_binding))
            if source_contract_binding is not None
            else ""
        )
        capture_name = (
            f"{candidate_id}-{current_binding_hash.split(':', 1)[-1][:20]}.json"
            if source_contract_binding is not None
            else f"{candidate_id}.json"
        )
        capture_path = (
            Path(output_root).resolve()
            / "recommendation_learning"
            / "active_captures"
            / decision_date.isoformat()
            / capture_name
        )
        if capture_path.is_file():
            from ml_module.recommendation_calibration_evidence import _verify_active_model_capture_payload

            payload = json.loads(capture_path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("active model capture is not an object")
            _verify_active_model_capture_payload(payload)
            if source_contract_binding is not None and _capture_source_identity(
                payload.get("source_contract_binding")
            ) != _capture_source_identity(source_contract_binding):
                return {
                    "status": "failed",
                    "reason": "active_capture_exists_with_different_source_identity",
                    "capture_path": str(capture_path.resolve()),
                    "active_candidate_id": payload.get("active_candidate_id"),
                }
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
            cost_scenario=cost_scenario,
            source_contract_binding=source_contract_binding,
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
    session_resolver: NaturalMaturitySessionResolver,
    evaluation_at: datetime,
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
        result = _build_natural_outcome_service(
            provider=provider,
            source_db=source_db,
            session_resolver=session_resolver,
            evaluation_at=evaluation_at,
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
    except DailyPriceSourceRevisionError as exc:
        # A valid capture may have matured while the formal historical
        # revision gate is closed.  Keep that observation pending; do not
        # convert source qualification into an active-model failure or roll
        # back a model solely because the PIT-only label reader cannot use the
        # revised source yet.
        return {
            "schema_version": "recommendation-natural-outcome-result.v1",
            "status": "pending",
            "reason": "natural_outcome_waiting_for_revision_qualified_source",
            "capture_path": str(Path(output_root).resolve() / "recommendation_learning" / "active_captures"),
            "capture_paths": [],
            "evaluation_date": decision_date.isoformat(),
            "matured_sample_count": 0,
            "evidence": None,
            "diagnostics": [
                "formal_historical_source_revision_blocks_outcome_read",
                f"source_revision_reason:{type(exc).__name__}",
            ],
            "historical_replay_is_natural_evidence": False,
        }
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
    cost_scenario: RecommendationCostScenario,
    status: str,
    natural_result: Mapping[str, Any] | None = None,
    retrain_trigger: str = "",
    run_scope: str | None = None,
    experiment_scope: str | None = None,
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
        **_scenario_cli_metadata(cost_scenario),
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
        "run_scope": run_scope,
        "experiment_scope": experiment_scope,
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
    raise ValueError(
        "--symbols missing; same-run --snapshot-result-id and --snapshot-cohort-hash are required"
    )


def _read_snapshot_invocation_stdout(
    *,
    output_root: Path,
    invocation_output_path: str | None,
    expected_sha256: str | None,
) -> tuple[bytes, dict[str, Any], str]:
    """只讀驗證 pipeline 本次 create-only stdout artifact 與其 invocation scope。"""

    if type(invocation_output_path) is not str or not invocation_output_path.strip():
        raise ValueError("本次 scheduled snapshot invocation stdout 路徑缺失")
    if not _is_sha256_text(expected_sha256):
        raise ValueError("本次 scheduled snapshot invocation stdout SHA-256 缺失或格式錯誤")

    snapshot_root = Path(output_root).resolve()
    allowed_runs_root = (
        snapshot_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "runs"
    )
    supplied_path = Path(invocation_output_path)
    if not supplied_path.is_absolute():
        raise ValueError("本次 scheduled snapshot invocation stdout 路徑必須是絕對路徑")
    try:
        canonical_runs_root = allowed_runs_root.resolve(strict=True)
        canonical_path = supplied_path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("本次 scheduled snapshot invocation stdout artifact 不存在") from exc
    lexical_path = Path(os.path.abspath(supplied_path))
    if lexical_path != canonical_path:
        raise ValueError("本次 scheduled snapshot invocation stdout 不可經過 symlink/reparse path")
    if (
        canonical_path.name != _SNAPSHOT_INVOCATION_STDOUT_NAME
        or canonical_path.parent.parent != canonical_runs_root
    ):
        raise ValueError("本次 scheduled snapshot invocation stdout 超出允許的 run root")

    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)

    def directory_identity(path: Path) -> tuple[int, int, int, int]:
        info = path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & reparse_flag
        ):
            raise ValueError("本次 stdout run/root component 必須是一般目錄")
        return (
            int(info.st_dev),
            int(info.st_ino),
            int(info.st_mode),
            int(getattr(info, "st_file_attributes", 0)),
        )

    def file_identity(path: Path) -> tuple[int, int, int, int, int, int, int]:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & reparse_flag
        ):
            raise ValueError("本次 scheduled snapshot invocation stdout 必須是一般檔案")
        if info.st_size < 0 or info.st_size > _MAX_SNAPSHOT_INVOCATION_STDOUT_BYTES:
            raise ValueError("本次 scheduled snapshot invocation stdout 超過大小上限")
        return (
            int(info.st_dev),
            int(info.st_ino),
            int(info.st_mode),
            int(info.st_size),
            int(info.st_mtime_ns),
            int(info.st_ctime_ns),
            int(getattr(info, "st_file_attributes", 0)),
        )

    try:
        root_before = directory_identity(canonical_runs_root)
        run_dir_before = directory_identity(canonical_path.parent)
        file_before = file_identity(canonical_path)
        raw_stdout = _read_regular_file_no_follow(
            canonical_path,
            canonical_runs_root,
            max_bytes=_MAX_SNAPSHOT_INVOCATION_STDOUT_BYTES,
        )
        file_after = file_identity(canonical_path)
        run_dir_after = directory_identity(canonical_path.parent)
        root_after = directory_identity(canonical_runs_root)
    except ExecutionPersistenceError as exc:
        raise ValueError("本次 scheduled snapshot invocation stdout no-follow read 失敗") from exc
    except OSError as exc:
        raise ValueError("本次 scheduled snapshot invocation stdout artifact 讀取失敗") from exc
    if (
        len(raw_stdout) != file_before[3]
        or file_after != file_before
        or run_dir_after != run_dir_before
        or root_after != root_before
    ):
        raise ValueError("本次 scheduled snapshot invocation stdout/root 在讀取期間改變")
    actual_sha256 = "sha256:" + hashlib.sha256(raw_stdout).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError("本次 scheduled snapshot invocation stdout SHA-256 不符")

    try:
        stdout_text = raw_stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("本次 scheduled snapshot invocation stdout 不是 UTF-8") from exc
    decoder = json.JSONDecoder()
    position = 0
    matches: list[dict[str, Any]] = []
    while position < len(stdout_text):
        start = stdout_text.find("{", position)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(stdout_text, start)
        except json.JSONDecodeError:
            position = start + 1
            continue
        position = end
        if (
            isinstance(value, dict)
            and value.get("task") == "baldr-recommendation-snapshot-daily"
        ):
            matches.append(value)
    if len(matches) != 1:
        raise ValueError("本次 scheduled snapshot invocation stdout 收據缺失或不唯一")
    return raw_stdout, matches[0], actual_sha256


def _resolve_same_run_snapshot_input(
    *,
    output_root: Path,
    decision_date: date,
    result_id: str | None,
    expected_cohort_hash: str | None,
    expected_invocation_output_sha256: str | None,
    invocation_output_path: str | None,
) -> tuple[tuple[str, ...], dict[str, Any], dict[str, Any]]:
    """只讀解析 caller 明示的本次 snapshot identity，不以 latest 或 glob 猜選。"""

    if type(result_id) is not str or not result_id.strip():
        raise ValueError("本次 scheduled snapshot result_id 缺失")
    if (
        type(expected_cohort_hash) is not str
        or len(expected_cohort_hash) != 71
        or not expected_cohort_hash.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in expected_cohort_hash[7:])
    ):
        raise ValueError("本次 scheduled snapshot cohort hash 格式錯誤")
    _raw_stdout, invocation_payload, actual_invocation_sha256 = (
        _read_snapshot_invocation_stdout(
            output_root=output_root,
            invocation_output_path=invocation_output_path,
            expected_sha256=expected_invocation_output_sha256,
        )
    )
    invocation_cohort = invocation_payload.get("snapshot_cohort")
    if (
        invocation_payload.get("result_id") != result_id
        or invocation_payload.get("decision_date") != decision_date.isoformat()
        or not isinstance(invocation_cohort, Mapping)
        or invocation_cohort.get("cohort_hash") != expected_cohort_hash
    ):
        raise ValueError("本次 snapshot stdout result/date/cohort hash identity 與 CLI binding 不符")

    runs_dir = Path(output_root).resolve() / "recommendation" / "runs"
    queries = build_recommendation_execution_queries(None, runs_dir=runs_dir)
    # Query seam 會驗證 canonical index、payload hash 與 artifact 原始 bytes。
    # 完整性錯誤直接向上傳遞，不 catch 後改讀 legacy file。
    read_model = queries.get(result_id)
    if read_model is None:
        raise ValueError("本次 scheduled snapshot result_id 未讀到保存 artifact")
    if read_model.result_id != result_id:
        raise ValueError("saved snapshot result_id 與本次 child identity 不符")
    if read_model.integrity_basis != "canonical_payload_and_index_verified":
        raise ValueError("scheduled learning snapshot 必須是 canonical verified artifact")
    if read_model.execution is None:
        raise ValueError("legacy saved result 缺少可驗證的 scheduled typed context")
    if read_model.schema_version != RECOMMENDATION_EXECUTION_SCHEMA_VERSION:
        raise ValueError("saved snapshot execution schema_version 不支援")
    if read_model.schema_revision not in SUPPORTED_EXECUTION_SCHEMA_REVISIONS:
        raise ValueError("saved snapshot execution schema_revision 不支援")
    if not _is_sha256_text(read_model.raw_artifact_sha256):
        raise ValueError("saved snapshot raw artifact SHA-256 缺失或格式錯誤")
    if not _is_sha256_text(read_model.payload_hash):
        raise ValueError("saved snapshot payload hash 缺失或格式錯誤")

    execution = read_model.execution
    if execution.status is not ExecutionStatus.COMPLETED or execution.decision is None:
        raise ValueError("saved scheduled snapshot execution 未完成或缺少 decision")
    context = execution.context
    result_config_snapshot = context.result_config_snapshot
    if result_config_snapshot is None:
        raise ValueError("saved scheduled snapshot 缺少 result config snapshot")
    result_config = execution_result_config(execution)
    if result_config.get("scheduled_snapshot") is not True:
        raise ValueError("saved result config 不是 scheduled snapshot")
    saved_decision_text = result_config.get("decision_date")
    if saved_decision_text != decision_date.isoformat():
        raise ValueError("saved snapshot decision_date 與本次 learning decision date 不符")
    data_date_text = result_config.get("data_as_of_date")
    if type(data_date_text) is not str:
        raise ValueError("saved snapshot result config 缺少 data_as_of_date")
    try:
        data_date = date.fromisoformat(data_date_text)
    except ValueError as exc:
        raise ValueError("saved snapshot data_as_of_date 格式錯誤") from exc
    if data_date.isoformat() != data_date_text:
        raise ValueError("saved snapshot data_as_of_date 必須為 YYYY-MM-DD")
    if execution.request.as_of_date != data_date or context.as_of_date != data_date:
        raise ValueError("saved snapshot request/context data date 不一致")
    if data_date > decision_date:
        raise ValueError("saved snapshot data date 晚於 decision date")

    decision_at = context.decision_at
    if (
        not isinstance(decision_at, datetime)
        or decision_at.tzinfo is None
        or decision_at.utcoffset() is None
        or decision_at.astimezone(TAIPEI).date() != decision_date
    ):
        raise ValueError("saved snapshot decision_at 不足以證明本次 decision date")
    available_at = context.available_at
    if available_at is not None and (
        not isinstance(available_at, datetime)
        or available_at.tzinfo is None
        or available_at.utcoffset() is None
    ):
        raise ValueError("saved snapshot available_at 若存在必須有時區")

    cohort_payload = result_config.get("snapshot_cohort")
    if not isinstance(cohort_payload, Mapping):
        raise ValueError("saved result config 缺少 typed snapshot_cohort")
    cohort = _snapshot_cohort_from_payload(cohort_payload)
    if context.snapshot_cohort != cohort:
        raise ValueError("saved result config 與 typed context snapshot_cohort 不一致")
    if cohort.cohort_hash != expected_cohort_hash:
        raise ValueError("saved snapshot cohort hash 與本次 child binding 不符")
    if invocation_cohort != cohort_payload:
        raise ValueError("本次 snapshot stdout cohort 與 canonical saved artifact 不一致")
    if not cohort.eligible_symbols:
        raise ValueError("本次 saved snapshot cohort 沒有 eligible symbols")
    decision_symbols = tuple(
        sorted(
            str(item.stock_code).strip()
            for item in execution.decision.items
            if str(item.stock_code).strip()
        )
    )
    if decision_symbols != cohort.eligible_symbols:
        raise ValueError("saved snapshot decision rows 與 eligible cohort 不一致")

    cohort_value = dict(cohort_payload)
    binding: dict[str, Any] = {
        "result_id": result_id,
        "snapshot_output_root": str(Path(output_root).resolve()),
        "schema_version": read_model.schema_version,
        "schema_revision": read_model.schema_revision,
        "integrity_basis": read_model.integrity_basis,
        "raw_artifact_sha256": read_model.raw_artifact_sha256,
        "payload_hash": read_model.payload_hash,
        "cohort_hash": cohort.cohort_hash,
        "invocation_output_path": str(Path(cast(str, invocation_output_path)).resolve()),
        "invocation_output_size": len(_raw_stdout),
        "invocation_output_sha256": actual_invocation_sha256,
        "decision_date": decision_date.isoformat(),
        "data_as_of_date": data_date.isoformat(),
        "decision_at": decision_at.isoformat(),
        "available_at": available_at.isoformat() if available_at is not None else None,
    }
    return cohort.eligible_symbols, cohort_value, binding


def _snapshot_cohort_from_payload(payload: Mapping[str, Any]) -> SnapshotCohort:
    coverage_payload = payload.get("coverage_by_symbol")
    if not isinstance(coverage_payload, Mapping):
        raise ValueError("snapshot_cohort.coverage_by_symbol 必須是 object")
    coverage: dict[str, SnapshotCohortCoverage] = {}
    for symbol, row in coverage_payload.items():
        if type(symbol) is not str or not isinstance(row, Mapping):
            raise ValueError("snapshot_cohort.coverage_by_symbol 含無效列")
        reasons = row.get("reason_codes", ())
        warnings = row.get("warnings", ())
        if not isinstance(reasons, (list, tuple)) or not isinstance(warnings, (list, tuple)):
            raise ValueError("snapshot_cohort coverage reason/warning 必須是清單")
        coverage[symbol] = SnapshotCohortCoverage(
            status=row.get("status"),
            quality=row.get("quality"),
            stage=row.get("stage"),
            reason_codes=tuple(reasons),
            warnings=tuple(warnings),
        )
    try:
        return SnapshotCohort(
            cohort_hash=str(payload["cohort_hash"]),
            requested_symbols=tuple(payload["requested_symbols"]),
            eligible_symbols=tuple(payload["eligible_symbols"]),
            missing_symbols=tuple(payload["missing_symbols"]),
            degraded_symbols=tuple(payload["degraded_symbols"]),
            excluded_symbols=tuple(payload["excluded_symbols"]),
            requested_count=payload["requested_count"],
            eligible_count=payload["eligible_count"],
            missing_count=payload["missing_count"],
            degraded_count=payload["degraded_count"],
            excluded_count=payload["excluded_count"],
            coverage_status=SnapshotCohortCoverageStatus(payload["coverage_status"]),
            coverage_by_symbol=coverage,
            eligible_definition=payload["eligible_definition"],
            missing_definition=payload["missing_definition"],
            degraded_definition=payload["degraded_definition"],
            excluded_definition=payload["excluded_definition"],
            schema_version=payload["schema_version"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("saved snapshot cohort contract 不完整或無效") from exc


def _is_sha256_text(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def _scheduled_run_scope(
    *,
    symbols: tuple[str, ...],
    snapshot_cohort: Mapping[str, Any] | None,
    fixed_round_trip_cost_bp: int | None = 50,
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
    policy: RecommendationPromotionPolicy | None = None,
    feature_registry_hash: str | None = None,
) -> str:
    """Return a daily receipt scope bound to the immutable experiment version."""

    cohort_hash = str((snapshot_cohort or {}).get("cohort_hash") or "")
    if not cohort_hash.startswith("sha256:"):
        cohort_hash = "sha256:" + hashlib.sha256(
            json.dumps(
                {"symbols": sorted(set(symbols)), "cohort": dict(snapshot_cohort or {})},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    experiment_hash = _scheduled_experiment_scope(
        fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        cost_scenario=cost_scenario,
        policy=policy,
        feature_registry_hash=feature_registry_hash,
    ).rsplit("-", 1)[-1]
    return "scheduled-snapshot-" + cohort_hash.split(":", 1)[1][:16] + "-e" + experiment_hash[:6]


def _scheduled_experiment_scope(
    *,
    fixed_round_trip_cost_bp: int | None = 50,
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
    policy: RecommendationPromotionPolicy | None = None,
    feature_registry_hash: str | None = None,
) -> str:
    """Stable identity shared by all scheduled days and symbol cohorts."""

    effective_policy = policy or RecommendationPromotionPolicy()
    scenario = cost_scenario
    if scenario is None:
        scenario = build_legacy_cost_scenario(
            50 if fixed_round_trip_cost_bp is None else fixed_round_trip_cost_bp
        )
    else:
        scenario = normalize_cost_scenario(
            scenario,
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        )
    body: dict[str, Any] = {
        "experiment_version": "scheduled-daily-recommendation-learning-v1",
        "strategy_profile": "scheduled_daily_research_default_v1",
        "target": "price_up_20d_after_cost_separate_lanes",
        "feature_registry_hash": feature_registry_hash or CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        "policy_hash": effective_policy.policy_hash,
        "fixed_round_trip_cost_bp": scenario.fixed_round_trip_cost_bp,
    }
    if scenario.is_estimated:
        body["cost_scenario"] = scenario.metadata()
        body["cost_scenario_hash"] = scenario.scenario_hash
    digest = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()[:24]
    return "scheduled-experiment-" + digest


def _explicit_experiment_scope(
    symbols: tuple[str, ...],
    *,
    fixed_round_trip_cost_bp: int | None = 50,
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
    policy: RecommendationPromotionPolicy | None = None,
    feature_registry_hash: str | None = None,
) -> str:
    effective_policy = policy or RecommendationPromotionPolicy()
    scenario = cost_scenario
    if scenario is None:
        scenario = build_legacy_cost_scenario(
            50 if fixed_round_trip_cost_bp is None else fixed_round_trip_cost_bp
        )
    else:
        scenario = normalize_cost_scenario(
            scenario,
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        )
    body: dict[str, Any] = {
        "experiment_version": "explicit-recommendation-learning-trial-v1",
        "symbols": sorted(set(symbols)),
        "feature_registry_hash": feature_registry_hash or CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        "policy_hash": effective_policy.policy_hash,
        "fixed_round_trip_cost_bp": scenario.fixed_round_trip_cost_bp,
    }
    if scenario.is_estimated:
        body["cost_scenario"] = scenario.metadata()
        body["cost_scenario_hash"] = scenario.scenario_hash
    digest = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()[:24]
    return "explicit-experiment-" + digest


def _scheduled_capture_scope(
    *,
    symbols: tuple[str, ...],
    snapshot_cohort: Mapping[str, Any] | None,
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
) -> str:
    cohort_hash = str((snapshot_cohort or {}).get("cohort_hash") or "")
    if not cohort_hash.startswith("sha256:"):
        cohort_hash = "sha256:" + hashlib.sha256(
            json.dumps(
                {"symbols": sorted(set(symbols)), "cohort": dict(snapshot_cohort or {})},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    token = "scheduled-capture-" + cohort_hash.split(":", 1)[1][:16]
    if cost_scenario is not None:
        scenario = normalize_cost_scenario(cost_scenario, fixed_round_trip_cost_bp=None)
        if scenario.is_estimated:
            token += "-c" + scenario.scenario_hash.split(":", 1)[1][:12]
    return token


def _merge_samples(
    replay_samples: tuple[RecommendationCalibrationSample, ...],
    natural_samples: tuple[RecommendationCalibrationSample, ...],
) -> tuple[RecommendationCalibrationSample, ...]:
    # A natural row with the same symbol/date/horizon is the stronger source
    # than a replay row, especially when it carries an observed liquidity
    # cost.  This also prevents duplicate rows from inflating the maturity or
    # training sample count.
    by_key: dict[tuple[str, str, int, str], RecommendationCalibrationSample] = {
        _sample_identity_key(row): row for row in replay_samples
    }
    for row in natural_samples:
        key = _sample_identity_key(row)
        existing = by_key.get(key)
        if existing is None or (
            existing.observed_liquidity_cost_bp is None
            and row.observed_liquidity_cost_bp is not None
        ):
            by_key[key] = row
    return tuple(sorted(by_key.values(), key=lambda row: (row.decision_date, row.symbol, row.row_id)))


def _sample_identity_key(
    row: RecommendationCalibrationSample,
) -> tuple[str, str, int, str]:
    """Keep replay/natural deduplication isolated by immutable cost lane."""

    return (
        row.symbol,
        row.decision_date,
        20,
        str(getattr(row, "cost_scenario_hash", None) or "legacy-fixed-round-trip-bp-v1"),
    )


def _load_natural_training_samples(
    *,
    output_root: Path,
    challenger_payload: Mapping[str, Any] | None,
    feature_count: int,
    fixed_round_trip_cost_bp: int | None,
    training_as_of: str,
    data_root: Path | None,
    source_db: Path,
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
) -> tuple[RecommendationCalibrationSample, ...]:
    """Recover traceable natural rows from retired and adopted model paths.

    The normal pending challenger remains frozen.  After a qualified natural
    no-improvement result, the next cycle may train on its matured rows.  Rows
    from an adopted model are converted to absolute-label rows with the
    explicit null benchmark as the training baseline; the active model's
    delivered probability is never used as a hidden target or benchmark.
    """

    expected_scenario = normalize_cost_scenario(
        cost_scenario,
        fixed_round_trip_cost_bp=(
            fixed_round_trip_cost_bp if cost_scenario is None else None
        ),
    )
    expected_scenario_hash = (
        expected_scenario.scenario_hash if expected_scenario.is_estimated else ""
    )
    samples: list[RecommendationCalibrationSample] = []
    seen_keys: set[tuple[str, str, int, str]] = set()
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
                    if evidence_payload.get("schema_version") not in {
                        "recommendation-natural-forward-evidence.v2",
                        "recommendation-natural-forward-evidence.v3",
                    }:
                        continue
                    if evidence_payload.get("candidate_freeze_hash") != candidate_freeze_hash:
                        continue
                    if evidence_payload.get("status") != "matured":
                        continue
                    evidence_scenario = cost_scenario_from_metadata(
                        evidence_payload,
                        fixed_round_trip_cost_bp=_metadata_int_or_none(
                            evidence_payload.get("fixed_round_trip_cost_bp")
                        ),
                    )
                    if evidence_scenario.is_estimated != expected_scenario.is_estimated:
                        continue
                    if expected_scenario_hash and evidence_scenario.scenario_hash != expected_scenario_hash:
                        continue
                    if not expected_scenario_hash and evidence_scenario.scenario_hash != expected_scenario.scenario_hash:
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
                        row_seen_key = f"{evidence_scenario.scenario_hash}:{row_id}"
                        capture_row = capture_rows.get(row_id)
                        if not row_id or row_seen_key in seen_rows or capture_row is None:
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
                        key = (
                            symbol,
                            decision,
                            20,
                            evidence_scenario.scenario_hash,
                        )
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
                        estimated = evidence_scenario.is_estimated
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
                            fixed_round_trip_cost_bp=(
                                None
                                if estimated
                                else int(
                                    evidence_payload.get(
                                        "fixed_round_trip_cost_bp",
                                        fixed_round_trip_cost_bp,
                                    )
                                )
                            ),
                            cost_scenario=(evidence_scenario if estimated else None),
                            cost_estimate=(
                                {
                                    "estimated_buy_cost_twd": comparison.get("estimated_buy_cost_twd"),
                                    "estimated_sell_cost_twd": comparison.get("estimated_sell_cost_twd"),
                                    "estimated_round_trip_cost_twd": comparison.get(
                                        "estimated_round_trip_cost_twd"
                                    ),
                                    "estimated_round_trip_cost_bp": comparison.get(
                                        "estimated_round_trip_cost_bp"
                                    ),
                                    "gross_buy_amount_twd": comparison.get("gross_buy_amount_twd"),
                                    "gross_sell_amount_twd": comparison.get("gross_sell_amount_twd"),
                                    "net_profit_twd": comparison.get("net_profit_twd"),
                                    "market_replay_date": comparison.get("market_replay_date") or decision,
                                }
                                if estimated
                                else None
                            ),
                            estimated_buy_cost_twd=(
                                comparison.get("estimated_buy_cost_twd") if estimated else None
                            ),
                            estimated_sell_cost_twd=(
                                comparison.get("estimated_sell_cost_twd") if estimated else None
                            ),
                            estimated_round_trip_cost_twd=(
                                comparison.get("estimated_round_trip_cost_twd") if estimated else None
                            ),
                            estimated_round_trip_cost_bp=(
                                comparison.get("estimated_round_trip_cost_bp") if estimated else None
                            ),
                            net_profit_twd=(
                                comparison.get("net_profit_twd") if estimated else None
                            ),
                            market_replay_date=(
                                str(comparison.get("market_replay_date") or decision)[:10]
                                if estimated
                                else None
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
                            source_quality="natural_forward",
                        )
                        samples.append(sample)
                        seen_rows.add(row_seen_key)
                        seen_keys.add(key)
                except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError):
                    continue
    samples.extend(
        _load_active_model_training_samples(
            output_root=output_root,
            feature_count=feature_count,
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
            cost_scenario=expected_scenario,
            training_as_of=cutoff.isoformat(),
            data_root=data_root,
            source_db=source_db,
            seen_keys=seen_keys,
            seen_rows=seen_rows,
        )
    )
    return tuple(samples)


def _load_active_model_training_samples(
    *,
    output_root: Path,
    feature_count: int,
    fixed_round_trip_cost_bp: int | None,
    training_as_of: str,
    data_root: Path | None,
    source_db: Path,
    seen_keys: set[tuple[str, str, int, str]],
    seen_rows: set[str],
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
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
        expected_scenario = normalize_cost_scenario(
            cost_scenario,
            fixed_round_trip_cost_bp=(
                fixed_round_trip_cost_bp if cost_scenario is None else None
            ),
        )
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if not isinstance(pointer, Mapping) or pointer.get("status") != "active":
            return ()
        candidate_id = str(pointer.get("candidate_id") or "")
        effective_date = date.fromisoformat(str(pointer.get("effective_date") or "")[:10])
        if not candidate_id:
            return ()
        pointer_scenario = cost_scenario_from_metadata(
            pointer,
            fixed_round_trip_cost_bp=_metadata_int_or_none(
                pointer.get("fixed_round_trip_cost_bp")
            ),
        )
        if pointer_scenario.is_estimated != expected_scenario.is_estimated:
            return ()
        if pointer_scenario.scenario_hash != expected_scenario.scenario_hash:
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
                    expected_db_path=source_db,
                )
                payload_scenario = cost_scenario_from_metadata(
                    payload,
                    fixed_round_trip_cost_bp=_metadata_int_or_none(
                        payload.get("fixed_round_trip_cost_bp")
                    ),
                )
                if payload_scenario.scenario_hash != expected_scenario.scenario_hash:
                    continue
                comparisons = payload.get("comparisons")
                if not isinstance(comparisons, list):
                    continue
                for comparison in comparisons:
                    if not isinstance(comparison, Mapping):
                        continue
                    row_id = str(comparison.get("capture_row_id") or "")
                    decision = str(comparison.get("capture_as_of_date") or "")[:10]
                    label_available = str(comparison.get("label_available_date") or "")[:10]
                    row_seen_key = f"{payload_scenario.scenario_hash}:{row_id}"
                    if not row_id or row_seen_key in seen_rows or not decision or not label_available:
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
                    key = (symbol, decision, 20, payload_scenario.scenario_hash)
                    if key in seen_keys:
                        continue
                    liquidity = comparison.get("observed_liquidity_cost_bp")
                    if comparison.get("observed_liquidity_cost_source") is None:
                        liquidity = None
                    estimated = payload_scenario.is_estimated
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
                        fixed_round_trip_cost_bp=(
                            None
                            if estimated
                            else int(payload.get("fixed_round_trip_cost_bp", fixed_round_trip_cost_bp))
                        ),
                        cost_scenario=(payload_scenario if estimated else None),
                        cost_estimate=(
                            {
                                "estimated_buy_cost_twd": comparison.get("estimated_buy_cost_twd"),
                                "estimated_sell_cost_twd": comparison.get("estimated_sell_cost_twd"),
                                "estimated_round_trip_cost_twd": comparison.get(
                                    "estimated_round_trip_cost_twd"
                                ),
                                "estimated_round_trip_cost_bp": comparison.get(
                                    "estimated_round_trip_cost_bp"
                                ),
                                "gross_buy_amount_twd": comparison.get("gross_buy_amount_twd"),
                                "gross_sell_amount_twd": comparison.get("gross_sell_amount_twd"),
                                "net_profit_twd": comparison.get("net_profit_twd"),
                                "market_replay_date": comparison.get("market_replay_date") or decision,
                            }
                            if estimated
                            else None
                        ),
                        estimated_buy_cost_twd=(
                            comparison.get("estimated_buy_cost_twd") if estimated else None
                        ),
                        estimated_sell_cost_twd=(
                            comparison.get("estimated_sell_cost_twd") if estimated else None
                        ),
                        estimated_round_trip_cost_twd=(
                            comparison.get("estimated_round_trip_cost_twd") if estimated else None
                        ),
                        estimated_round_trip_cost_bp=(
                            comparison.get("estimated_round_trip_cost_bp") if estimated else None
                        ),
                        net_profit_twd=(comparison.get("net_profit_twd") if estimated else None),
                        market_replay_date=(
                            str(comparison.get("market_replay_date") or decision)[:10]
                            if estimated
                            else None
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
                    seen_rows.add(row_seen_key)
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
    source_db: Path,
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
                expected_db_path=source_db,
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
    recovery_policy = str(dependencies.get("recovery_policy", "normal")).lower()
    if recovery_policy == "fail_closed_emergency_rollback":
        return True
    if recovery_policy == "recoverable_attempt":
        return str(dependencies.get("drift_status", "not_checked")).lower() in blocked
    return any(
        str(dependencies.get(field_name, "not_checked")).lower() in blocked
        for field_name in ("data_status", "outcome_status", "drift_status")
    )


def _preflight_requires_emergency(exc: BaseException) -> bool:
    """Classify source-integrity faults separately from temporarily unavailable data."""

    message = str(exc).strip().lower()
    integrity_markers = (
        "changed during",
        "immutable historical replay dataset conflict",
        "required table is missing",
        "required columns are missing",
        "source whitelist mismatch",
        "query_only could not be enabled",
        "database disk image is malformed",
        "file is encrypted or is not a database",
        "integrity check failed",
        "corrupt",
    )
    return any(marker in message for marker in integrity_markers)


def _dependency_failure(
    *,
    reason: str,
    data_status: str,
    outcome_status: str,
    drift_status: str,
    recovery_policy: str,
) -> dict[str, Any]:
    return {
        "data_status": data_status,
        "outcome_status": outcome_status,
        "drift_status": drift_status,
        "recovery_policy": recovery_policy,
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
    recoverable: bool = False,
    symbol_coverage: Mapping[str, Any] | None = None,
    run_scope: str | None = None,
    capture_scope: str | None = None,
    experiment_scope: str | None = None,
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
    natural_maturity_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "daily-recommendation-learning-cli-result.v3",
        "decision_date": decision_day.isoformat(),
        "decision_timezone": "Asia/Taipei",
        "symbols": list(symbols),
        "symbol_source": symbol_source,
        "symbol_coverage": dict(symbol_coverage) if isinstance(symbol_coverage, Mapping) else None,
        "run_scope": run_scope,
        "capture_scope": capture_scope,
        "experiment_scope": experiment_scope,
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
            "training_lineage_manifest_hash": run_result.training_lineage_manifest_hash,
            "training_lineage_manifest_path": run_result.training_lineage_manifest_path,
            "training_lineage_status": run_result.training_lineage_status,
            "decision": run_result.decision,
            "decision_reason": run_result.decision_reason,
            "idempotent_replay": run_result.idempotent_replay,
        },
        "challenger": _read_challenger_pointer(output_root),
        "active_pointer": _read_active_pointer(output_root),
        "natural_evidence": dict(natural_result),
        "active_model_natural_evidence": dict(active_natural_result or {}),
        "natural_maturity_context": (
            dict(natural_maturity_context)
            if isinstance(natural_maturity_context, Mapping)
            else None
        ),
        "live_capture": dict(live_capture),
        "error": error,
        "recoverable": bool(recoverable),
        "formal_order_allowed": False,
        "shadow_only": True,
    }
    if cost_scenario is not None:
        scenario = normalize_cost_scenario(cost_scenario, fixed_round_trip_cost_bp=None)
        if scenario.is_estimated:
            payload.update(
                {
                    "cost_scenario": scenario.metadata(),
                    "cost_scenario_id": scenario.scenario_id,
                    "cost_scenario_version": scenario.scenario_version,
                    "cost_scenario_hash": scenario.scenario_hash,
                    "cost_basis": scenario.cost_basis,
                    "cost_policy_id": scenario.policy_id,
                    "cost_policy_version": scenario.policy_version,
                    "policy_estimate_date": scenario.policy_estimate_date,
                    "research_order_amount_twd": (
                        str(scenario.research_order_amount_twd)
                        if scenario.research_order_amount_twd is not None
                        else None
                    ),
                    "research_order_quantity_shares": scenario.research_order_quantity_shares,
                    "lot_type": scenario.lot_type,
                    "instrument_type": scenario.instrument_type,
                    "cost_estimate_source": "BankTaiwanElectronicCostPolicy:research_only",
                    "liquidity_cost_role": "diagnostic_only_not_in_fees_tax_only_label",
                    "formal_order_allowed": False,
                    "shadow_only": True,
                }
            )
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


def _recover_historical_bootstrap_metadata(
    *,
    learning_output_root: Path,
    decision_day: date,
    run_scope: str | None,
    initial_replay_result: Any,
    run_result: Any,
) -> dict[str, Any] | None:
    """Recover bootstrap observability when a same-day rerun is idempotent.

    The first normal run records the causal trigger in its failed-training
    attempt and persists the replay manifest before the final candidate is
    written.  A later same-day retry returns the completed receipt without
    retraining, so this read-only recovery keeps the final status disclosure
    intact instead of replacing it with ``not_triggered``.
    """

    if not run_scope or str(getattr(run_result, "status", "")) != "completed":
        return None
    run_dir = (
        Path(learning_output_root).resolve()
        / "recommendation_learning"
        / "runs"
        / decision_day.isoformat()
        / str(run_scope)
    )
    try:
        receipt = json.loads((run_dir / "run_receipt.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(receipt, Mapping) or receipt.get("status") != "completed":
        return None

    trigger_payload: Mapping[str, Any] | None = None
    attempts_dir = run_dir / "attempts"
    for attempt_path in sorted(
        attempts_dir.glob("*.json"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
    ):
        try:
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(attempt, Mapping) or attempt.get("status") != "failed_training":
            continue
        reason = str(attempt.get("reason") or "").lower()
        if "oof calibration" in reason or "calibration target requires two classes" in reason:
            trigger_payload = attempt
            break
    if trigger_payload is None:
        return None
    diagnostics = trigger_payload.get("training_diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, Mapping) else {}
    selection = diagnostics.get("bootstrap_selection")
    selection = selection if isinstance(selection, Mapping) else {}
    initial_dates = tuple(
        sorted({str(value)[:10] for value in getattr(initial_replay_result, "decision_dates", ())})
    )
    initial_start = str(diagnostics.get("eligible_decision_date_start") or (initial_dates[0] if initial_dates else ""))[:10]
    if not initial_start:
        return None

    datasets_root = Path(learning_output_root).resolve() / "recommendation_learning" / "datasets"
    selected_manifest: tuple[Path, Mapping[str, Any]] | None = None
    for dataset_dir in sorted(
        (path for path in datasets_root.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    ) if datasets_root.is_dir() else ():
        manifest_path = dataset_dir / "dataset.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, Mapping):
            continue
        coverage = manifest.get("coverage")
        coverage = coverage if isinstance(coverage, Mapping) else {}
        if coverage.get("selection_policy") != "time_stratified_eligible_dates":
            continue
        dates = tuple(sorted({str(value)[:10] for value in manifest.get("decision_dates", ())}))
        if not dates or dates[-1] >= initial_start:
            continue
        selected_manifest = (manifest_path, manifest)
        break
    if selected_manifest is None:
        return None

    manifest_path, manifest = selected_manifest
    bootstrap_dates = tuple(sorted({str(value)[:10] for value in manifest.get("decision_dates", ())}))
    initial_date_set = set(initial_dates)
    date_overlap = sorted(initial_date_set.intersection(bootstrap_dates))

    def row_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
        return (
            str(row.get("symbol") or "").strip(),
            str(row.get("decision_date") or "")[:10],
            str(row.get("label_end_date") or "")[:10],
        )

    initial_rows = {
        (
            str(getattr(row, "symbol", "") or "").strip(),
            str(getattr(row, "decision_date", "") or "")[:10],
            str(getattr(row, "label_end_date", "") or "")[:10],
        )
        for row in getattr(initial_replay_result, "samples", ())
    }
    bootstrap_rows = {
        row_key(row)
        for row in manifest.get("samples", ())
        if isinstance(row, Mapping)
    }
    row_overlap = sorted(initial_rows.intersection(bootstrap_rows))
    crossing_labels = sorted(
        row
        for row in bootstrap_rows
        if row[2] >= initial_start
    )
    coverage = manifest.get("coverage")
    coverage = dict(coverage) if isinstance(coverage, Mapping) else {}
    source_contract = coverage.get("source_contract")
    source_contract = source_contract if isinstance(source_contract, Mapping) else {}
    return {
        "status": "recovered_completed",
        "recovered_from_existing_artifacts": True,
        "trigger": str(trigger_payload.get("reason") or ""),
        "initial_max_decision_dates": selection.get("replay_max_decision_dates"),
        "bootstrap_max_decision_dates": coverage.get("max_decision_dates"),
        "selection_policy": coverage.get("selection_policy"),
        "selection_basis": "date-only evenly spaced maturable trading dates; no labels or holdout metrics used",
        "initial_replay_dataset_id": getattr(initial_replay_result, "dataset_id", None),
        "initial_replay_sample_count": getattr(initial_replay_result, "sample_count", None),
        "initial_seen_decision_date_count": len(initial_dates),
        "initial_seen_decision_date_start": initial_dates[0] if initial_dates else None,
        "initial_seen_decision_date_end": initial_dates[-1] if initial_dates else None,
        "bootstrap_replay_dataset_id": manifest.get("dataset_id"),
        "replay_dataset_id": manifest.get("dataset_id"),
        "replay_sample_count": manifest.get("sample_count"),
        "replay_decision_date_count": len(bootstrap_dates),
        "replay_date_start": bootstrap_dates[0] if bootstrap_dates else None,
        "replay_date_end": bootstrap_dates[-1] if bootstrap_dates else None,
        "bootstrap_replay_end_date": source_contract.get("replay_end_date"),
        "untouched_boundary_policy": (
            "bootstrap uses only dates strictly before the initial observed replay window; "
            "a 20-trading-day causal label/embargo gap is reserved before that boundary"
        ),
        "reserved_causal_embargo_trading_days": 20,
        "initial_bootstrap_decision_date_overlap_count": len(date_overlap),
        "initial_bootstrap_row_overlap_count": len(row_overlap),
        "bootstrap_rows_crossing_initial_boundary_count": len(crossing_labels),
        "replay_coverage": coverage,
        "replay_diagnostics": list(manifest.get("diagnostics", ())),
        "replay_manifest_path": str(manifest_path),
        "training_status": receipt.get("status"),
        "training_reason": receipt.get("reason"),
        "training_receipt_path": str(run_dir / "run_receipt.json"),
    }


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
        "symbol_coverage",
        "snapshot_source_binding",
        "run_scope",
        "capture_scope",
        "experiment_scope",
        "dependencies",
        "challenger",
        "active_pointer",
        "natural_evidence",
        "active_model_natural_evidence",
        "natural_maturity_context",
        "live_capture",
        "training_as_of",
        "training_sample_count",
        "natural_training_sample_count",
        "natural_evidence_supplied",
        "ignored_caller_inputs",
        "historical_bootstrap",
        "formal_order_allowed",
        "shadow_only",
        "error",
        "recoverable",
    ):
        if field_name in cli_payload:
            existing[
                f"cli_{field_name}"
                if field_name in {"schema_version", "recoverable"}
                else field_name
            ] = cli_payload[field_name]
    existing["active_model_performance"] = (
        cli_payload.get("dependencies", {}).get("model_performance", {})
        if isinstance(cli_payload.get("dependencies"), Mapping)
        else {}
    )
    existing["cli_result_updated_at"] = _taipei_now().isoformat(timespec="seconds")
    _write_json(path, existing)


if __name__ == "__main__":
    raise SystemExit(main())
