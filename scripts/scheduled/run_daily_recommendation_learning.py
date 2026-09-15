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
from dataclasses import replace
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Mapping
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
from data_module.config import TWStockConfig  # noqa: E402
from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider  # noqa: E402
from data_module.official_trading_calendar import OfficialTradingCalendar  # noqa: E402
from data_module.recommendation_calibration_source_contract import (  # noqa: E402
    inspect_source_contract,
    write_source_contract,
)
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
    candidate_freeze_hash,
    recommendation_cost_contract_hash,
    recommendation_label_registry_hash,
)
from ml_module.recommendation_historical_replay import (  # noqa: E402
    RecommendationHistoricalReplayConfig,
    RecommendationHistoricalReplayService,
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


TAIPEI = ZoneInfo("Asia/Taipei")

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
        "--snapshot-output-root",
        type=Path,
        default=None,
        help=(
            "同日 scheduled recommendation snapshot 的唯讀來源根目錄；"
            "省略時沿用 OUTPUT_ROOT／learning output root。"
        ),
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


def _stored_cost_scenario(
    payload: Mapping[str, Any],
    *,
    source_path: Path,
) -> tuple[RecommendationCostScenario | None, str | None]:
    """Resolve one shared-root marker without ever inventing a new lane.

    Early challenger pointers predate the cost-scenario fields.  They can be
    read only when their candidate identity points to a candidate document
    whose immutable hashes and cost contract agree; an unanchored marker is
    unverifiable and remains fail-closed.
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
        )

    try:
        fixed_value = _metadata_int_or_none(payload.get("fixed_round_trip_cost_bp"))
        scenario = cost_scenario_from_metadata(
            payload,
            fixed_round_trip_cost_bp=fixed_value,
        )
    except (TypeError, ValueError, RecommendationCostScenarioError) as exc:
        return None, f"{source_path}:invalid_cost_scenario:{type(exc).__name__}:{exc}"
    anchored_identity_keys = (
        "candidate_root",
        "candidate_id",
        "candidate_freeze_hash",
        "candidate_manifest_hash",
        "candidate_artifact_hash",
        "dataset_hash",
    )
    if all(payload.get(key) not in (None, "") for key in anchored_identity_keys):
        candidate_scenario, error = _stored_cost_scenario_from_candidate_root(
            payload,
            source_path=source_path,
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
) -> tuple[RecommendationCostScenario | None, str | None]:
    """Recover a legacy pointer's lane from verified candidate artifacts.

    A pointer without scenario fields is only a historical metadata shape; it
    is not itself authority.  The candidate root must therefore provide a
    complete identity anchor and pass the same canonical manifest, artifact,
    freeze, and cost-contract checks used by the consumer contract.
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
    if missing_identity:
        return (
            None,
            f"{source_path}:unverifiable_cost_scenario:incomplete_candidate_identity:"
            f"{','.join(missing_identity)}",
        )
    for marker_key in (
        "candidate_freeze_hash",
        "candidate_manifest_hash",
        "candidate_artifact_hash",
        "dataset_hash",
    ):
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
    the reverse).
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
    verified_markers: list[tuple[Path, RecommendationCostScenario]] = []
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
        scenario, error = _stored_cost_scenario(payload, source_path=marker_path)
        if error is not None or scenario is None:
            return f"cost_scenario_root_conflict:{error or marker_path}"
        if marker_path == root / "latest_status.json":
            receipt_error = _verify_latest_status_receipt_anchor(
                payload,
                scenario=scenario,
                source_path=marker_path,
            )
            if receipt_error is not None:
                return f"cost_scenario_root_conflict:{receipt_error}"
        verified_markers.append((marker_path, scenario))
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
            for _, scenario in verified_markers
        ):
            return (
                "cost_scenario_root_conflict:legacy_decision_receipt_has_no_"
                "verified_same_lane_anchor:"
                f"{unverified_legacy_markers[0]}"
            )
    return None


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


def _verify_latest_status_receipt_anchor(
    payload: Mapping[str, Any],
    *,
    scenario: RecommendationCostScenario,
    source_path: Path,
) -> str | None:
    """Ensure latest-status lane metadata is backed by its immutable receipt."""

    if payload.get("schema_version") != "daily-recommendation-learning-receipt.v1":
        return None
    receipt_value = payload.get("receipt_path")
    if not isinstance(receipt_value, str) or not receipt_value.strip():
        return f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_missing"
    receipt_path = Path(receipt_value).expanduser().resolve()
    try:
        receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return (
            f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_unreadable:"
            f"{type(exc).__name__}"
        )
    if not isinstance(receipt_payload, Mapping):
        return f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_invalid"
    if str(receipt_payload.get("receipt_path") or "") != str(receipt_path):
        return f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_identity_mismatch"
    receipt_scenario, error = _stored_cost_scenario(
        receipt_payload,
        source_path=receipt_path,
    )
    if error is not None or receipt_scenario is None:
        return error or f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_lane_missing"
    if receipt_scenario.scenario_hash != scenario.scenario_hash:
        return f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_lane_mismatch"
    if receipt_payload.get("formal_order_allowed") is not False:
        return f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_formal_flag_invalid"
    if receipt_payload.get("shadow_only") is not True:
        return f"{source_path}:unverifiable_cost_scenario:latest_status_receipt_shadow_flag_invalid"
    return None


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
    source_artifact_root = (
        args.source_artifact_root or config.output_root
    ).expanduser().resolve()
    snapshot_cohort: dict[str, Any] | None = None
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
        else _taipei_now().date()
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
    if root_conflict is not None:
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
        symbols, symbol_source = _resolve_symbols(
            output_root=scheduled_snapshot_output_root,
            explicit_symbols=args.symbols,
            decision_date=decision_day,
        )
        if args.symbols is None:
            snapshot_cohort = _load_snapshot_cohort(
                output_root=scheduled_snapshot_output_root,
                decision_date=decision_day,
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
            experiment_scope = _explicit_experiment_scope(
                symbols,
                fixed_round_trip_cost_bp=effective_fixed_cost,
                cost_scenario=cost_scenario,
                policy=RecommendationPromotionPolicy(),
                feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
            )
            capture_scope = _capture_scope_token(None, symbols)
    except ValueError as exc:
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
        availability_cutoff_at=_taipei_now().isoformat(timespec="seconds"),
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
    try:
        provider = MLHistoricalSnapshotProvider(source_db)
        replay_result = RecommendationHistoricalReplayService(provider).build(replay_config)
        manifest_path = replay_result.persist(learning_output_root)
    except (OSError, RuntimeError, ValueError, TypeError, sqlite3.Error) as exc:
        preflight_reason = f"replay_or_source_preflight_failed:{type(exc).__name__}"
        emergency_from_preflight = _preflight_requires_emergency(exc)
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
    )
    capture_failure, capture_recoverable = _capture_dependency_failure(capture_result)

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
            required_source_contract=source_contract_audit,
        ).to_dict()
        evidence_payload = natural_result.get("evidence")
        if isinstance(evidence_payload, Mapping):
            automatic_evidence = evidence_payload

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
    if run_result.candidate_id and run_result.candidate_root:
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
    )
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
    technical = contract.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
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
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        data_status = "failed"
        outcome_status = "failed"
        drift_status = "not_checked"
        recovery_policy = (
            "fail_closed_emergency_rollback"
            if _preflight_requires_emergency(exc)
            else "recoverable_attempt"
        )
        diagnostics.append(f"source_preflight_failed:{type(exc).__name__}")
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
) -> tuple[bool | None, str]:
    """Use the existing official-calendar contract without network guessing."""

    calendar = OfficialTradingCalendar(db_path=provider.database_path)
    return calendar.is_official_trading_day(decision_date, allow_online_probe=False)


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
        capture_at = _taipei_now().isoformat(timespec="seconds")
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
            cost_scenario=cost_scenario,
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
    snapshot = _find_same_day_snapshot(
        output_root=output_root,
        decision_date=decision_date,
    )
    if snapshot is None:
        raise ValueError("--symbols missing and scheduled recommendation snapshot directory is unavailable")
    path, payload = snapshot
    config = payload.get("config")
    config = config if isinstance(config, Mapping) else {}
    snapshot_cohort = config.get("snapshot_cohort")
    if isinstance(snapshot_cohort, Mapping):
        cohort_symbols = snapshot_cohort.get("eligible_symbols")
        symbols = tuple(
            sorted(
                {
                    str(item).strip()
                    for item in cohort_symbols
                    if str(item).strip()
                }
            )
            if isinstance(cohort_symbols, (list, tuple, set))
            else ()
        )
        if symbols:
            return symbols, f"scheduled_recommendation_snapshot:{path.name}:eligible"

    recommendations = payload.get("recommendations")
    if isinstance(recommendations, list):
        symbols = tuple(
            sorted(
                {
                    str(
                        item.get("stock_code")
                        or item.get("symbol")
                        or item.get("code")
                        or item.get("證券代號")
                    )
                    for item in recommendations
                    if isinstance(item, Mapping)
                    and str(
                        item.get("stock_code")
                        or item.get("symbol")
                        or item.get("code")
                        or item.get("證券代號")
                        or ""
                    ).strip()
                }
            )
        )
        if symbols:
            return symbols, f"scheduled_recommendation_snapshot:{path.name}"
    raise ValueError(
        "--symbols missing and no same-day scheduled recommendation snapshot supplied an explicit symbol cohort"
    )


def _find_same_day_snapshot(
    *,
    output_root: Path,
    decision_date: date,
) -> tuple[Path, Mapping[str, Any]] | None:
    runs_root = Path(output_root).resolve() / "recommendation" / "runs"
    if not runs_root.is_dir():
        return None
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
        if snapshot_date == decision_date.isoformat():
            return path, payload
    return None


def _load_snapshot_cohort(
    *,
    output_root: Path,
    decision_date: date,
) -> dict[str, Any] | None:
    snapshot = _find_same_day_snapshot(
        output_root=output_root,
        decision_date=decision_date,
    )
    if snapshot is None:
        return None
    _, payload = snapshot
    config = payload.get("config")
    if not isinstance(config, Mapping):
        return None
    cohort = config.get("snapshot_cohort")
    return dict(cohort) if isinstance(cohort, Mapping) else None


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
        "run_scope",
        "capture_scope",
        "experiment_scope",
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
