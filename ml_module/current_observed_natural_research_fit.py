"""隔離 current-observed natural research-only recommendation fitting。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.purged_walk_forward import MLTimeWindowRow, PurgedWalkForwardSplitter
from ml_module.recommendation_calibration_learning_runner import (
    DEFAULT_DATA_ROOT,
    DailyRecommendationLearningRunner,
)
from ml_module.recommendation_calibration_training import (
    RecommendationCalibrationSample,
    RecommendationCalibrationTrainingConfig,
)
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenario,
    RecommendationCostScenarioError,
    normalize_cost_scenario,
)
from ml_module.recommendation_natural_outcome_service import (
    verify_current_observed_outcome_receipt,
)
from ml_module.recommendation_probability_transform import (
    NULL_BENCHMARK_BASELINE_ID,
    NULL_BENCHMARK_PROBABILITY_BP,
)
from ml_module.recommendation_training_lineage import (
    RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH,
    read_recommendation_training_lineage,
)


CURRENT_OBSERVED_NATURAL_RESEARCH_QUALITY = "current_observed_natural_research"
_OUTCOME_RECEIPT_SCHEMA = "recommendation-current-observed-natural-outcome-receipt.v1"
_OUTCOME_RECEIPT_SCHEMA_V2 = "recommendation-current-observed-natural-outcome-receipt.v2"
_INPUT_CAPTURE_SCHEMA_V2 = "recommendation-current-observed-input-capture.v2"
_FEATURE_SNAPSHOT_SCHEMA_V1 = "recommendation-current-observed-feature-snapshot.v1"
_FEATURE_SNAPSHOT_SCHEMA_V2 = "recommendation-current-observed-feature-snapshot.v2"
_OUTCOME_QUERY_BATCH_SCHEMA = "recommendation-current-observed-outcome-query-batch.v1"
_OUTCOME_QUERY_COMPOSITION_SCHEMA = "recommendation-current-observed-outcome-query-composition.v1"
_CURRENT_OBSERVED_SOURCE_TABLES = frozenset(
    {"daily_prices", "technical_indicators", "market_indices", "industry_indices"}
)
_CURRENT_OBSERVED_MAX_BATCH_SYMBOLS = 16
_CURRENT_OBSERVED_MAX_SYMBOLS = 50
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_VERIFIED_OUTCOME_STATUSES = frozenset(
    {
        "verified",
        "verified_pending",
        "verified_without_matured_rows",
        "verified_blocked_receipt",
    }
)
_TAIPEI = ZoneInfo("Asia/Taipei")


def fit_current_observed_natural_research(
    *,
    learning_output_root: Path,
    samples: Sequence[RecommendationCalibrationSample],
    training_as_of: date,
    evaluation_at: datetime,
    fixed_round_trip_cost_bp: int | None,
    cost_scenario: RecommendationCostScenario,
    outcome_receipts: Sequence[Mapping[str, str]],
    source_identity: Mapping[str, Any],
    data_root: Path | None = None,
) -> Mapping[str, Any]:
    """以已驗證的 current-observed 自然結果訓練隔離研究候選。

    此 lane 不使用 active model probability、不產生 natural promotion evidence，
    也不會把 current-restated 樣本標成歷史 PIT 或正式訓練資格。資料不足時先
    回傳 pending，不建立 runner、candidate、lineage 或 authority pointer。
    """

    fit_started_at = datetime.now(timezone.utc)
    if not isinstance(training_as_of, date) or isinstance(training_as_of, datetime):
        raise ValueError("training_as_of must be a calendar date")
    if (
        not isinstance(evaluation_at, datetime)
        or evaluation_at.tzinfo is None
        or evaluation_at.utcoffset() is None
    ):
        raise ValueError("evaluation_at must be an aware datetime")
    evaluation_utc = evaluation_at.astimezone(timezone.utc)
    if evaluation_utc > fit_started_at:
        raise ValueError("evaluation_at must not follow the actual fit clock")
    if evaluation_at.astimezone(_TAIPEI).date() != training_as_of:
        raise ValueError("evaluation_at Taipei date must equal training_as_of")
    if not isinstance(learning_output_root, Path):
        raise TypeError("learning_output_root must be a Path")
    if not isinstance(cost_scenario, RecommendationCostScenario):
        raise TypeError("cost_scenario must be a RecommendationCostScenario")
    if not isinstance(source_identity, Mapping) or not source_identity:
        raise ValueError("source_identity must be a non-empty JSON mapping")

    feature_names = CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids
    feature_schema = CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema
    feature_registry_hash = CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash
    config = RecommendationCalibrationTrainingConfig()
    if len(feature_names) != 20 or len(feature_schema) != 20:
        raise RuntimeError("canonical recommendation feature registry is not the locked 20-slot schema")

    scenario = _normalize_scenario(
        cost_scenario,
        fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
    )
    sample_rows = tuple(samples)
    if any(not isinstance(row, RecommendationCalibrationSample) for row in sample_rows):
        raise TypeError("samples must contain RecommendationCalibrationSample rows")
    ordered_samples = tuple(
        sorted(sample_rows, key=lambda row: (row.decision_date, row.symbol, row.row_id))
    )
    sample_diagnostics = _validate_samples(
        ordered_samples,
        training_as_of=training_as_of,
        scenario=scenario,
        fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        feature_count=len(feature_names),
    )
    canonical_source_identity = _canonical_mapping(source_identity, "source_identity")
    semantic_ids = [
        sample.row_id.startswith("current-observed-natural-semantic:")
        for sample in ordered_samples
    ]
    if any(semantic_ids) and not all(semantic_ids):
        raise ValueError("mixed semantic and capture sample identities")
    verified_refs, receipt_rows = _verify_receipt_references(
        outcome_receipts, semantic_row_ids=bool(semantic_ids) and all(semantic_ids)
    )
    _verify_sample_receipt_binding(ordered_samples, verified_refs, receipt_rows)
    isolated_output_root = _isolated_output_root(
        learning_output_root,
        data_root=data_root,
    )
    isolated_learning_root = isolated_output_root / "recommendation_learning"

    refs_hash = _hash_payload(list(verified_refs))
    fit_scope = "current_observed_natural_" + refs_hash.removeprefix("sha256:")[:24]
    min_rows = config.minimum_training_rows
    if len(ordered_samples) < min_rows:
        return _pending_result(
            reason="insufficient_current_observed_natural_research_rows",
            samples=ordered_samples,
            outcome_receipt_refs=verified_refs,
            outcome_receipt_refs_sha256=refs_hash,
            run_scope=fit_scope,
            training_as_of=training_as_of,
            evaluation_at=evaluation_at,
            fit_started_at=fit_started_at,
            support={
                **sample_diagnostics,
                "minimum_training_rows": min_rows,
                "observed_sample_count": len(ordered_samples),
            },
            isolated_output_root=isolated_output_root,
            isolated_learning_root=isolated_learning_root,
        )

    support = _training_support(ordered_samples, config=config)
    if not support["ready"]:
        return _pending_result(
            reason=str(support["reason"]),
            samples=ordered_samples,
            outcome_receipt_refs=verified_refs,
            outcome_receipt_refs_sha256=refs_hash,
            run_scope=fit_scope,
            training_as_of=training_as_of,
            evaluation_at=evaluation_at,
            fit_started_at=fit_started_at,
            support={**sample_diagnostics, **support},
            isolated_output_root=isolated_output_root,
            isolated_learning_root=isolated_learning_root,
        )

    decision_date = date.fromisoformat(sample_diagnostics["latest_decision_date"])
    if training_as_of <= decision_date:
        raise ValueError("current-observed research cutoff must follow every sample decision date")
    dataset_quality: dict[str, Any] = {
        "dataset_scope": CURRENT_OBSERVED_NATURAL_RESEARCH_QUALITY,
        "training_data_eligible": True,
        "training_semantics": RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH,
        "historical_research": True,
        "current_restated": True,
        "research_only": True,
        "decision_time_eligible": False,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "formal_candidate_eligible": False,
        "forward_evidence_eligible": False,
        "promotion_credit_created": False,
        "natural_outcome_only": True,
        "active_model_probabilities_used": False,
        "training_as_of_after_sample_decisions": True,
        "evaluation_at": evaluation_at.isoformat(timespec="microseconds"),
        "fit_started_at_utc": fit_started_at.isoformat(timespec="microseconds"),
        "source_contract": {
            "schema_version": "current-observed-natural-research-fit-source.v1",
            "lane": CURRENT_OBSERVED_NATURAL_RESEARCH_QUALITY,
            "source_identity": canonical_source_identity,
            "outcome_receipt_refs": list(verified_refs),
            "outcome_receipt_refs_sha256": refs_hash,
            "evaluation_at": evaluation_at.isoformat(timespec="microseconds"),
            "verified_outcome_row_count": len(receipt_rows),
            "sample_row_count": len(ordered_samples),
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
            "promotion_credit_created": False,
        },
    }
    lineage_sources = {"natural": ordered_samples}
    # Recheck the requested path immediately before the runner can create it.
    isolated_output_root = _isolated_output_root(learning_output_root, data_root=data_root)
    runner = DailyRecommendationLearningRunner(
        output_root=isolated_output_root,
        data_root=data_root,
        feature_names=feature_names,
        feature_schema=feature_schema,
        feature_registry_hash=feature_registry_hash,
        fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        cost_scenario=scenario,
        training_config=config,
    )
    active_pointer_path = runner.root / "recommendation-calibration-active-pointer.json"
    if active_pointer_path.exists():
        raise ValueError("isolated research root already contains a calibration active pointer")

    # training_as_of 通常晚於所有決策日。以真實最新 capture 日作 runner date，
    # 並傳明確 historical-research semantics，避免把後見資料封成當日模型。
    training_context_semantics = RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH
    if not dataset_quality["research_only"]:
        raise RuntimeError("current-observed fit lost its research-only qualification")
    result = runner.run(
        decision_date=decision_date.isoformat(),
        run_scope=fit_scope,
        samples=ordered_samples,
        natural_evidence=None,
        data_dependency_status="observed",
        outcome_dependency_status="observed",
        drift_status="not_checked",
        dataset_quality=dataset_quality,
        training_as_of=training_as_of.isoformat(),
        lineage_sources=lineage_sources,
    )
    fit_completed_at = datetime.now(timezone.utc)
    if active_pointer_path.exists():
        raise RuntimeError("research-only fit must not create an active calibration pointer")
    runner_root = runner.root.resolve()
    candidate_root = Path(result.candidate_root).resolve() if result.candidate_root else None
    if candidate_root is not None and not _is_relative_to(candidate_root, runner_root):
        raise RuntimeError("research candidate escaped its isolated learning root")
    if result.decision not in {"retain_current", "no_change"}:
        raise RuntimeError("research-only fit unexpectedly received a promotion decision")

    run_receipt = _read_json_if_plain(Path(result.receipt_path))
    lineage = None
    if result.training_lineage_manifest_path and result.training_lineage_manifest_hash:
        lineage = read_recommendation_training_lineage(
            result.training_lineage_manifest_path,
            expected_manifest_hash=result.training_lineage_manifest_hash,
            expected_dataset_hash=result.dataset_hash,
            expected_candidate_id=result.candidate_id,
        )
        lineage_quality = lineage.payload.get("dataset_quality")
        lineage_context = lineage.payload.get("training_context")
        lineage_source_group_payload = lineage.payload.get("source_groups")
        groups = (
            lineage_source_group_payload.get("groups")
            if isinstance(lineage_source_group_payload, Mapping)
            else None
        )
        if (
            not isinstance(lineage_quality, Mapping)
            or lineage_quality.get("research_only") is not True
            or lineage_quality.get("current_restated") is not True
            or lineage_quality.get("historical_pit_eligible") is not False
            or lineage_quality.get("formal_training_allowed") is not False
            or lineage_quality.get("formal_candidate_eligible") is not False
            or lineage_quality.get("promotion_credit_created") is not False
            or not isinstance(lineage_context, Mapping)
            or lineage_context.get("semantics")
            != RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH
            or lineage_context.get("decision_time_eligible") is not False
            or not isinstance(groups, Mapping)
            or set(groups) != {"natural"}
        ):
            raise RuntimeError("persisted training lineage lost the current-observed research-only contract")
    if run_receipt is None:
        raise RuntimeError("isolated research runner did not persist a readable run receipt")
    if (
        run_receipt.get("natural_matured_sample_count") not in (0, None)
        or run_receipt.get("decision_time_eligible") is True
        or run_receipt.get("natural_evidence_receipt_hash") is not None
        or run_receipt.get("promotion_credit_created") is True
    ):
        raise RuntimeError("isolated research run receipt contains forbidden evidence credit")
    if result.status == "completed" and run_receipt.get("research_only") is not True:
        raise RuntimeError("completed isolated candidate is missing explicit research-only semantics")
    receipt_sha256 = _sha256_file(Path(result.receipt_path))

    return {
        "status": "fitted_research_only" if result.status == "completed" else result.status,
        "reason": result.reason,
        "run_id": result.run_id,
        "run_scope": fit_scope,
        "decision_date": decision_date.isoformat(),
        "training_as_of": training_as_of.isoformat(),
        "evaluation_at": evaluation_at.isoformat(timespec="microseconds"),
        "training_semantics": training_context_semantics,
        "fit_started_at_utc": fit_started_at.isoformat(timespec="microseconds"),
        "fit_completed_at_utc": fit_completed_at.isoformat(timespec="microseconds"),
        "receipt_path": result.receipt_path,
        "receipt_sha256": receipt_sha256,
        "dataset_id": result.dataset_id,
        "dataset_hash": result.dataset_hash,
        "candidate_id": result.candidate_id,
        "candidate_root": str(candidate_root) if candidate_root is not None else None,
        "candidate_manifest_hash": (
            run_receipt.get("candidate_manifest_hash") if run_receipt is not None else None
        ),
        "candidate_artifact_hash": (
            run_receipt.get("candidate_artifact_hash") if run_receipt is not None else None
        ),
        "decision": result.decision,
        "decision_reason": result.decision_reason,
        "training_lineage": {
            "status": result.training_lineage_status,
            "manifest_hash": result.training_lineage_manifest_hash,
            "manifest_path": result.training_lineage_manifest_path,
            "source_group": "natural",
        },
        "support": {**sample_diagnostics, **support},
        "outcome_receipts": list(verified_refs),
        "outcome_receipt_refs_sha256": refs_hash,
        "source_identity": canonical_source_identity,
        "isolated_output_root": str(isolated_output_root),
        "isolated_learning_root": str(runner_root),
        "active_pointer_created": False,
        "research_only": True,
        "current_restated": True,
        "historical_research": True,
        "decision_time_eligible": False,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "formal_candidate_eligible": False,
        "forward_evidence_eligible": False,
        "promotion_credit_created": False,
        "natural_evidence": None,
        "natural_outcome_only": True,
        "historical_replay_is_natural_evidence": False,
    }


def _normalize_scenario(
    scenario: RecommendationCostScenario,
    *,
    fixed_round_trip_cost_bp: int | None,
) -> RecommendationCostScenario:
    try:
        normalized = normalize_cost_scenario(
            scenario,
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        )
    except RecommendationCostScenarioError as exc:
        raise ValueError(str(exc)) from exc
    if normalized != scenario:
        raise ValueError("cost scenario must already be normalized")
    return normalized


def _validate_samples(
    samples: Sequence[RecommendationCalibrationSample],
    *,
    training_as_of: date,
    scenario: RecommendationCostScenario,
    fixed_round_trip_cost_bp: int | None,
    feature_count: int,
) -> dict[str, Any]:
    row_ids: set[str] = set()
    lane_keys: set[tuple[str, str, str, str]] = set()
    decision_dates: set[date] = set()
    for sample in samples:
        if not isinstance(sample, RecommendationCalibrationSample):
            raise TypeError("samples must contain RecommendationCalibrationSample rows")
        if sample.row_id in row_ids:
            raise ValueError("current-observed research samples contain duplicate row_id")
        row_ids.add(sample.row_id)
        decision = _strict_date(sample.decision_date, "decision_date")
        feature_as_of = _strict_date(sample.feature_as_of_date, "feature_as_of_date")
        feature_available = _strict_date(sample.feature_available_date, "feature_available_date")
        label_end = _strict_date(sample.label_end_date, "label_end_date")
        label_available = _strict_date(sample.label_available_date, "label_available_date")
        if feature_as_of >= decision:
            raise ValueError("feature_as_of_date must precede decision_date")
        if feature_available > decision:
            raise ValueError("feature_available_date must not follow decision_date")
        if decision > training_as_of or label_available > training_as_of:
            raise ValueError("sample decision and label availability must be within training_as_of")
        if label_end < decision or label_available < label_end:
            raise ValueError("sample label dates are incomplete or out of order")
        if len(sample.feature_values) != feature_count:
            raise ValueError("sample must carry all twenty canonical feature slots")
        if any(value is not None and type(value) is not int for value in sample.feature_values):
            raise ValueError("feature values must be exact integers or explicit nulls")
        if sample.rule_baseline_id != NULL_BENCHMARK_BASELINE_ID:
            raise ValueError("current-observed natural research requires the null benchmark baseline")
        if sample.rule_probability_bp != NULL_BENCHMARK_PROBABILITY_BP:
            raise ValueError("current-observed natural research requires the explicit 5000 bp null baseline")
        if (
            sample.rule_after_cost_probability_bp is not None
            or sample.rule_after_cost_baseline_id is not None
        ):
            raise ValueError("current-observed natural research cannot carry after-cost probabilities")
        if sample.after_cost_profit_label is not None:
            raise ValueError("current-observed natural research fits gross upside labels only")
        if sample.source_quality != CURRENT_OBSERVED_NATURAL_RESEARCH_QUALITY:
            raise ValueError("sample does not belong to the current-observed natural research lane")
        if sample.cost_scenario_hash != scenario.scenario_hash:
            raise ValueError("sample cost scenario differs from the requested scenario")
        if (
            sample.cost_scenario_id != scenario.scenario_id
            or sample.cost_scenario_version != scenario.scenario_version
            or sample.cost_basis != scenario.cost_basis
        ):
            raise ValueError("sample cost scenario identity is inconsistent")
        if scenario.is_estimated:
            if sample.fixed_round_trip_cost_bp is not None:
                raise ValueError("estimated current-observed rows cannot carry fixed cost")
        elif (
            isinstance(sample.fixed_round_trip_cost_bp, bool)
            or type(sample.fixed_round_trip_cost_bp) is not int
            or sample.fixed_round_trip_cost_bp != fixed_round_trip_cost_bp
        ):
            raise ValueError("fixed current-observed sample cost differs from the requested cost")
        lane_keys.add(
            (
                sample.source_quality,
                sample.cost_scenario_id,
                sample.cost_scenario_version,
                sample.cost_scenario_hash,
            )
        )
        decision_dates.add(decision)
    if samples and len(lane_keys) != 1:
        raise ValueError("fit samples must use one verified outcome lane and one cost scenario")
    ordered_dates = sorted(decision_dates)
    return {
        "sample_count": len(samples),
        "decision_date_count": len(ordered_dates),
        "earliest_decision_date": ordered_dates[0].isoformat() if ordered_dates else None,
        "latest_decision_date": ordered_dates[-1].isoformat() if ordered_dates else None,
        "training_as_of": training_as_of.isoformat(),
        "training_as_of_after_sample_decisions": bool(ordered_dates)
        and training_as_of > ordered_dates[-1],
        "feature_slot_count": feature_count,
        "source_quality": CURRENT_OBSERVED_NATURAL_RESEARCH_QUALITY,
        "cost_scenario_hash": scenario.scenario_hash,
    }


def _current_observed_capture_semantic_hash(
    *,
    capture_row: Mapping[str, Any],
    outcome_row: Mapping[str, Any],
) -> str:
    """Hash stable source/feature/label meaning across immutable retries.

    ``CurrentObservedFeatureRow.row_sha256`` intentionally includes each
    invocation's local observation clock. That hash remains in each immutable
    receipt and is verified before this function is called, but it is not a
    semantic feature identity. The exact feature values, registry, source
    table hashes, G6 snapshot pins and entry-price pin remain in the signature.
    Outcome receipt/path IDs and re-observation clocks are similarly excluded;
    raw row proofs, dates, source hashes, returns and costs stay bound.
    """

    capture_semantic = {
        key: capture_row[key]
        for key in (
            "symbol",
            "decision_date",
            "feature_as_of_date",
            "feature_available_date",
            "feature_registry_id",
            "feature_registry_hash",
            "feature_schema_hash",
            "feature_ids",
            "feature_values",
            "source_row_sha256_by_table",
            "entry_price_pin",
        )
        if key in capture_row
    }

    def stable_reobserved_proof(value: object) -> object:
        if isinstance(value, Mapping):
            return {
                str(key): stable_reobserved_proof(item)
                for key, item in value.items()
                if key
                not in {
                    "local_observed_at",
                    "observed_at",
                    "validated_at",
                    "evaluation_at",
                    "proof_sha256",
                }
            }
        if isinstance(value, list):
            return [stable_reobserved_proof(item) for item in value]
        if isinstance(value, tuple):
            return [stable_reobserved_proof(item) for item in value]
        return value

    volatile_outcome_keys = {
        "capture_row_id",
        "capture_path",
        "capture_sha256",
        "capture_id",
        "feature_available_at",
        "feature_row_sha256",
        "label_observed_at",
    }
    outcome_semantic = {
        str(key): value
        for key, value in outcome_row.items()
        if key not in volatile_outcome_keys
    }
    for proof_key in (
        "entry_consistency_source_proof",
        "endpoint_price_proof",
        "benchmark_entry_consistency_source_proof",
        "benchmark_endpoint_price_proof",
        "maturity_session_proof",
    ):
        if proof_key in outcome_semantic:
            outcome_semantic[proof_key] = stable_reobserved_proof(
                outcome_semantic[proof_key]
            )
    return _hash_payload(
        {
            "schema_version": "current-observed-natural-sample-semantic-identity.v2",
            "capture_row": capture_semantic,
            "outcome_row": outcome_semantic,
        }
    )


def _verify_receipt_references(
    references: Sequence[Mapping[str, str]],
    *,
    semantic_row_ids: bool = False,
) -> tuple[tuple[dict[str, str], ...], dict[str, Mapping[str, Any]]]:
    if not references:
        raise ValueError("at least one independently verified outcome receipt reference is required")
    normalized_refs: list[dict[str, str]] = []
    receipt_rows: dict[str, Mapping[str, Any]] = {}
    seen_ref_bytes: set[str] = set()
    semantic_hashes: dict[str, str] = {}
    for raw_reference in references:
        if not isinstance(raw_reference, Mapping):
            raise TypeError("outcome_receipts must contain mapping references")
        reference = {str(key): value for key, value in raw_reference.items()}
        if any(type(value) is not str or not value.strip() for value in reference.values()):
            raise ValueError("outcome receipt reference fields must be non-empty strings")
        for field_name in (
            "capture_path",
            "capture_sha256",
            "capture_id",
            "outcome_path",
            "outcome_sha256",
            "outcome_status",
            "verification_status",
        ):
            if not reference.get(field_name):
                raise ValueError(f"outcome receipt reference is missing {field_name}")
        if reference["verification_status"] not in _VERIFIED_OUTCOME_STATUSES:
            raise ValueError("outcome receipt reference was not independently verified")
        if reference["outcome_status"] not in {"matured", "partial", "pending", "blocked"}:
            raise ValueError("outcome receipt status is outside the current-observed lane")
        canonical = _canonical_json(reference)
        if canonical in seen_ref_bytes:
            raise ValueError("duplicate current-observed outcome receipt reference")
        seen_ref_bytes.add(canonical)
        try:
            payload = verify_current_observed_outcome_receipt(
                reference["outcome_path"],
                expected_sha256=reference["outcome_sha256"],
                capture_path=reference["capture_path"],
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ValueError("current-observed outcome receipt failed re-verification") from exc
        receipt_schema = payload.get("schema_version")
        capture: Mapping[str, Any] = {}
        if semantic_row_ids or receipt_schema == _OUTCOME_RECEIPT_SCHEMA_V2:
            try:
                from ml_module.recommendation_calibration_evidence import (
                    verify_current_observed_input_capture,
                )

                capture = verify_current_observed_input_capture(
                    reference["capture_path"],
                    expected_sha256=reference["capture_sha256"],
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise ValueError("outcome capture failed independent re-verification") from exc
            if receipt_schema == _OUTCOME_RECEIPT_SCHEMA_V2:
                _verify_v2_outcome_query_composition(payload, capture)
        if (
            receipt_schema not in {_OUTCOME_RECEIPT_SCHEMA, _OUTCOME_RECEIPT_SCHEMA_V2}
            or payload.get("verification_status") not in _VERIFIED_OUTCOME_STATUSES
            or payload.get("status") != reference["outcome_status"]
            or payload.get("capture_id") != reference["capture_id"]
            or payload.get("capture_sha256") != reference["capture_sha256"]
            or payload.get("current_restated") is not True
            or payload.get("historical_pit_eligible") is not False
            or payload.get("formal_training_allowed") is not False
            or payload.get("research_only") is not True
            or payload.get("natural_outcome_only") is not True
            or payload.get("promotion_credit_created") is not False
            or payload.get("historical_replay_is_natural_evidence") is not False
        ):
            raise ValueError("verified outcome receipt has an invalid current-only qualification")
        outcomes = payload.get("outcomes")
        if not isinstance(outcomes, list):
            raise ValueError("verified outcome receipt has no outcome row list")
        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                raise ValueError("verified outcome receipt contains a malformed row")
            capture_row_id = outcome.get("capture_row_id")
            if type(capture_row_id) is not str or not capture_row_id.strip():
                raise ValueError("verified outcome row has no capture row identity")
            row_id = f"current-observed-natural:{reference['capture_id']}:{capture_row_id}"
            if semantic_row_ids:
                capture_rows = capture.get("rows")
                if not isinstance(capture_rows, list):
                    raise ValueError("semantic identity requires verified capture rows")
                matching = [
                    row for row in capture_rows
                    if isinstance(row, Mapping) and row.get("row_id") == capture_row_id
                ]
                if len(matching) != 1:
                    raise ValueError("outcome row has no unique independently verified capture row")
                semantic_hash = _current_observed_capture_semantic_hash(
                    capture_row=matching[0], outcome_row=outcome
                )
                row_id = "current-observed-natural-semantic:" + semantic_hash.removeprefix("sha256:")[:32]
                if row_id in semantic_hashes:
                    if semantic_hashes[row_id] != semantic_hash:
                        raise ValueError("conflicting semantic identity hash")
                    continue
                semantic_hashes[row_id] = semantic_hash
            elif row_id in receipt_rows:
                raise ValueError("outcome receipt set contains a duplicate matured capture row")
            receipt_rows[row_id] = outcome
        normalized_refs.append(reference)
        normalized_refs.sort(key=_canonical_json)
    return tuple(normalized_refs), receipt_rows


def _verify_v2_outcome_query_composition(
    receipt: Mapping[str, Any],
    capture: Mapping[str, Any],
) -> None:
    """Bind a v2 receipt to a verified full-cohort v2 capture and query shards."""

    if (
        receipt.get("schema_version") != _OUTCOME_RECEIPT_SCHEMA_V2
        or capture.get("schema_version") != _INPUT_CAPTURE_SCHEMA_V2
        or receipt.get("capture_id") != capture.get("capture_id")
        or receipt.get("capture_sha256") != capture.get("_verified_capture_sha256")
        or receipt.get("current_restated") is not True
        or receipt.get("historical_pit_eligible") is not False
        or receipt.get("formal_training_allowed") is not False
        or receipt.get("research_only") is not True
        or receipt.get("natural_outcome_only") is not True
        or receipt.get("promotion_credit_created") is not False
        or receipt.get("historical_replay_is_natural_evidence") is not False
    ):
        raise ValueError("v2 outcome receipt and verified capture identity differ")

    binding = capture.get("source_contract_binding")
    feature_snapshot = (
        binding.get("current_observed_feature_snapshot")
        if isinstance(binding, Mapping)
        else None
    )
    if (
        not isinstance(binding, Mapping)
        or not isinstance(feature_snapshot, Mapping)
        or feature_snapshot.get("schema_version") != _FEATURE_SNAPSHOT_SCHEMA_V2
        or capture.get("scope_mode") != "verified_scheduled_snapshot_cohort"
        or binding.get("scope_mode") != "verified_scheduled_snapshot_cohort"
        or feature_snapshot.get("scope_mode") != "verified_scheduled_snapshot_cohort"
    ):
        raise ValueError("v2 outcome receipt requires a verified scheduled full-cohort capture")

    from ml_module.current_observed_feature_snapshot_composer import (
        verify_current_observed_feature_snapshot_v2,
    )

    try:
        verify_current_observed_feature_snapshot_v2(feature_snapshot)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("v2 outcome feature composition failed re-verification") from exc
    feature_composition_sha256 = feature_snapshot.get("composition_sha256")
    if (
        not _is_sha256_text(feature_composition_sha256)
        or capture.get("composition_sha256") != feature_composition_sha256
        or binding.get("composition_sha256") != feature_composition_sha256
        or capture.get("cohort_hash") != feature_snapshot.get("cohort_hash")
        or binding.get("cohort_hash") != feature_snapshot.get("cohort_hash")
        or capture.get("feature_snapshot_sha256") != feature_snapshot.get("content_sha256")
    ):
        raise ValueError("v2 capture feature composition identity is inconsistent")

    current_snapshot = receipt.get("current_observed_snapshot")
    outcomes = receipt.get("outcomes")
    if current_snapshot is None:
        if receipt.get("status") not in {"pending", "blocked"} or outcomes != []:
            raise ValueError("v2 outcome receipt without a later source snapshot cannot contain labels")
        return
    if not isinstance(current_snapshot, Mapping) or not isinstance(outcomes, list):
        raise ValueError("v2 outcome source snapshot or row list is malformed")
    _verify_v2_later_source_snapshot(current_snapshot)

    symbols_value = capture.get("symbols")
    if (
        not isinstance(symbols_value, list)
        or symbols_value != sorted(set(str(symbol) for symbol in symbols_value))
        or not 17 <= len(symbols_value) <= _CURRENT_OBSERVED_MAX_SYMBOLS
    ):
        raise ValueError("v2 outcome capture symbol scope is invalid")
    symbols = [str(symbol) for symbol in symbols_value]
    chunks = [
        symbols[offset : offset + _CURRENT_OBSERVED_MAX_BATCH_SYMBOLS]
        for offset in range(0, len(symbols), _CURRENT_OBSERVED_MAX_BATCH_SYMBOLS)
    ]
    batches = current_snapshot.get("outcome_query_batches")
    if not isinstance(batches, list) or len(batches) != len(chunks):
        raise ValueError("v2 outcome query batches do not cover the complete captured cohort")
    pins = capture.get("entry_price_pin_by_symbol")
    benchmark_pin = capture.get("benchmark_entry_price_pin")
    if (
        not isinstance(pins, Mapping)
        or not isinstance(benchmark_pin, Mapping)
        or set(pins) != set(symbols)
        or any(not isinstance(pins.get(symbol), Mapping) for symbol in symbols)
    ):
        raise ValueError("v2 outcome capture entry pins do not cover the cohort")

    by_symbol: dict[str, Mapping[str, Any]] = {}
    normalized_batches: list[dict[str, Any]] = []
    for ordinal, (raw_batch, expected_symbols) in enumerate(zip(batches, chunks, strict=True)):
        if not isinstance(raw_batch, Mapping):
            raise ValueError("v2 outcome query descriptor is malformed")
        batch = dict(raw_batch)
        expected_keys = {
            "schema_version",
            "ordinal",
            "symbols",
            "row_count",
            "query_identity_sha256",
            "source_rows_sha256_by_table",
            "input_entry_observation_sha256",
            "batch_sha256",
        }
        table_hashes = batch.get("source_rows_sha256_by_table")
        batch_symbols = batch.get("symbols")
        if (
            set(batch) != expected_keys
            or batch.get("schema_version") != _OUTCOME_QUERY_BATCH_SCHEMA
            or type(batch.get("ordinal")) is not int
            or batch.get("ordinal") != ordinal
            or batch_symbols != expected_symbols
            or batch.get("row_count") != len(expected_symbols)
            or len(expected_symbols) > _CURRENT_OBSERVED_MAX_BATCH_SYMBOLS
            or not isinstance(table_hashes, Mapping)
            or set(table_hashes) != _CURRENT_OBSERVED_SOURCE_TABLES
            or any(not _is_sha256_text(value) for value in table_hashes.values())
            or not _is_sha256_text(batch.get("query_identity_sha256"))
            or not _is_sha256_text(batch.get("input_entry_observation_sha256"))
            or not _is_sha256_text(batch.get("batch_sha256"))
        ):
            raise ValueError("v2 outcome query descriptor fields are invalid")
        expected_query_identity = _hash_payload(
            {"symbols": expected_symbols, "source_rows_sha256_by_table": dict(table_hashes)}
        )
        entry_subset = {
            "entry_price_pin_by_symbol": {
                symbol: dict(pins[symbol])
                for symbol in expected_symbols
            },
            "benchmark_entry_price_pin": dict(benchmark_pin),
        }
        body = {key: value for key, value in batch.items() if key != "batch_sha256"}
        if (
            batch.get("query_identity_sha256") != expected_query_identity
            or batch.get("input_entry_observation_sha256") != _hash_payload(entry_subset)
            or batch.get("batch_sha256") != _hash_payload(body)
        ):
            raise ValueError("v2 outcome query descriptor hash mismatch")
        normalized_batches.append(batch)
        for symbol in expected_symbols:
            if symbol in by_symbol:
                raise ValueError("v2 outcome query batches contain duplicate symbols")
            by_symbol[symbol] = batch
    if set(by_symbol) != set(symbols):
        raise ValueError("v2 outcome query batches do not exactly cover the capture")
    expected_aggregate = _hash_payload(
        {
            "schema_version": _OUTCOME_QUERY_COMPOSITION_SCHEMA,
            "capture_symbols": symbols,
            "batches": normalized_batches,
        }
    )
    if current_snapshot.get("outcome_query_batches_sha256") != expected_aggregate:
        raise ValueError("v2 outcome query composition hash mismatch")

    for outcome in outcomes:
        if not isinstance(outcome, Mapping):
            raise ValueError("v2 outcome receipt contains a malformed row")
        outcome_symbol = outcome.get("symbol")
        source_batch = (
            by_symbol.get(outcome_symbol)
            if type(outcome_symbol) is str
            else None
        )
        if (
            source_batch is None
            or outcome.get("label_source_batch_ordinal") != source_batch.get("ordinal")
            or outcome.get("label_source_batch_sha256") != source_batch.get("batch_sha256")
            or outcome.get("label_source_rows_sha256_by_table")
            != source_batch.get("source_rows_sha256_by_table")
        ):
            raise ValueError("v2 matured outcome row is not bound to its verified query batch")


def _verify_v2_later_source_snapshot(
    current_snapshot: Mapping[str, Any],
) -> None:
    """Validate the independently pinned maturity-day source, not the old capture source.

    Outcome v2 is bound to the immutable input capture by the outer receipt's
    capture id/hash and to the later observation by this source snapshot plus
    its replayed query batches. Those are separate observations by design.
    """

    schema_version = current_snapshot.get("schema_version")
    if schema_version not in {_FEATURE_SNAPSHOT_SCHEMA_V1, _FEATURE_SNAPSHOT_SCHEMA_V2}:
        raise ValueError("v2 outcome later source feature snapshot schema is unsupported")

    for field_name in ("cycle_id", "raw_run_id"):
        value = current_snapshot.get(field_name)
        if type(value) is not str or not value.strip():
            raise ValueError(f"v2 outcome later source is missing {field_name}")
    source_date_value = current_snapshot.get("source_date")
    if type(source_date_value) is not str:
        raise ValueError("v2 outcome later source_date is missing")
    _strict_date(source_date_value, "later source_date")
    if not _is_sha256_text(current_snapshot.get("feature_snapshot_sha256")):
        raise ValueError("v2 outcome later feature snapshot hash is invalid")

    feature_hashes = current_snapshot.get("feature_source_rows_sha256_by_table")
    if schema_version == _FEATURE_SNAPSHOT_SCHEMA_V1:
        if (
            not isinstance(feature_hashes, Mapping)
            or set(feature_hashes) != _CURRENT_OBSERVED_SOURCE_TABLES
            or any(not _is_sha256_text(value) for value in feature_hashes.values())
            or "composition_sha256" in current_snapshot
        ):
            raise ValueError("v2 outcome later v1 source table hashes are invalid")
    elif (
        not _is_sha256_text(current_snapshot.get("composition_sha256"))
        or "feature_source_rows_sha256_by_table" in current_snapshot
    ):
        raise ValueError("v2 outcome later v2 source composition is invalid")


def _verify_sample_receipt_binding(
    samples: Sequence[RecommendationCalibrationSample],
    references: Sequence[Mapping[str, str]],
    receipt_rows: Mapping[str, Mapping[str, Any]],
) -> None:
    if len(samples) != len(receipt_rows):
        raise ValueError("sample rows do not exactly cover the verified matured receipt rows")
    sample_by_id = {sample.row_id: sample for sample in samples}
    if set(sample_by_id) != set(receipt_rows):
        raise ValueError("sample row identities differ from verified outcome receipt rows")
    receipt_ids = {ref["capture_id"] for ref in references}
    for row_id, sample in sample_by_id.items():
        if not row_id.startswith("current-observed-natural-semantic:") and not any(
            row_id.startswith(f"current-observed-natural:{capture_id}:")
            for capture_id in receipt_ids
        ):
            raise ValueError("sample is not scoped to a verified current-observed capture")
        outcome = receipt_rows[row_id]
        required_cost_fields = (
            "observed_liquidity_cost_bp",
            "estimated_round_trip_cost_twd",
            "estimated_round_trip_cost_bp",
            "estimated_buy_cost_twd",
            "estimated_sell_cost_twd",
            "gross_buy_amount_twd",
            "gross_sell_amount_twd",
            "net_profit_twd",
            "after_cost_profit_label",
        )
        if any(field_name not in outcome for field_name in required_cost_fields):
            raise ValueError("verified outcome row is missing required cost contract fields")
        checks = (
            (outcome.get("symbol"), sample.symbol),
            (outcome.get("capture_decision_date"), sample.decision_date),
            (outcome.get("feature_as_of_date"), sample.feature_as_of_date),
            (outcome.get("feature_available_date"), sample.feature_available_date),
            (outcome.get("label_end_date"), sample.label_end_date),
            (outcome.get("label_available_date"), sample.label_available_date),
            (outcome.get("feature_values"), list(sample.feature_values)),
            (outcome.get("stock_return_bp"), sample.stock_return_bp),
            (outcome.get("benchmark_return_bp"), sample.benchmark_return_bp),
            (outcome.get("upside_label"), sample.upside_label),
            (outcome.get("cost_scenario_hash"), sample.cost_scenario_hash),
            (outcome.get("cost_scenario_id"), sample.cost_scenario_id),
            (outcome.get("cost_scenario_version"), sample.cost_scenario_version),
            (outcome.get("cost_basis"), sample.cost_basis),
            (outcome.get("observed_liquidity_cost_bp"), sample.observed_liquidity_cost_bp),
        )
        if any(left != right for left, right in checks):
            raise ValueError("sample payload differs from its independently verified outcome receipt")
        cost_checks = (
            (outcome.get("estimated_round_trip_cost_twd"), sample.estimated_round_trip_cost_twd),
            (outcome.get("estimated_buy_cost_twd"), sample.estimated_buy_cost_twd),
            (outcome.get("estimated_sell_cost_twd"), sample.estimated_sell_cost_twd),
            (outcome.get("gross_buy_amount_twd"), sample.gross_buy_amount_twd),
            (outcome.get("gross_sell_amount_twd"), sample.gross_sell_amount_twd),
            (outcome.get("net_profit_twd"), sample.net_profit_twd),
        )
        if any(not _same_declared_value(left, right) for left, right in cost_checks):
            raise ValueError("sample payload differs from its independently verified outcome receipt")
        if sample.cost_basis == "fixed_round_trip_bp":
            declared_fixed_bp = outcome.get("estimated_round_trip_cost_bp")
            if (
                type(declared_fixed_bp) is not int
                or declared_fixed_bp != sample.fixed_round_trip_cost_bp
            ):
                raise ValueError("fixed receipt cost differs from the sample fixed-cost contract")
        else:
            declared_estimated_bp = outcome.get("estimated_round_trip_cost_bp")
            if declared_estimated_bp is not None and type(declared_estimated_bp) is not int:
                raise ValueError("estimated receipt basis-point cost must be an exact integer")
            if not _same_declared_value(
                declared_estimated_bp,
                sample.estimated_round_trip_cost_bp,
            ):
                raise ValueError("estimated receipt basis-point cost differs from its sample")
            _verify_estimated_cost_math(outcome)
        declared_after_cost_label = outcome.get("after_cost_profit_label")
        if declared_after_cost_label is not None:
            if type(declared_after_cost_label) is not int or declared_after_cost_label not in (0, 1):
                raise ValueError("outcome receipt after-cost label must be an exact binary integer")
            expected_label = _declared_after_cost_label(outcome)
            if declared_after_cost_label != expected_label:
                raise ValueError("outcome receipt after-cost label differs from its exact cost values")


def _training_support(
    samples: Sequence[RecommendationCalibrationSample],
    *,
    config: RecommendationCalibrationTrainingConfig,
) -> dict[str, Any]:
    """Mirror the fitter's locked split/calibration prerequisites without fitting."""

    if not samples:
        return {
            "ready": False,
            "reason": "insufficient_current_observed_research_rows",
            "minimum_training_rows": config.minimum_training_rows,
            "observed_sample_count": 0,
            "observed_decision_dates": 0,
            "usable_fold_count": 0,
            "required_usable_fold_count": 3,
        }
    by_id = {row.row_id: row for row in samples}
    windows = tuple(
        MLTimeWindowRow(row.row_id, row.decision_date, row.label_end_date) for row in samples
    )
    splitter = PurgedWalkForwardSplitter(
        minimum_train_dates=config.minimum_train_dates,
        test_date_count=config.test_date_count,
        purge_trading_days=config.purge_trading_days,
        embargo_trading_days=config.embargo_trading_days,
    )
    folds = splitter.split(windows)
    usable: list[Any] = []
    for fold in folds:
        train_rows = tuple(
            by_id[row.row_id]
            for row in fold.train_rows
            if row.row_id in by_id and _strict_date(by_id[row.row_id].label_available_date, "label_available_date") < date.fromisoformat(fold.test_start)
        )
        if len(train_rows) >= config.minimum_fold_train_rows and _two_classes(train_rows):
            usable.append(fold)
    if len(usable) < 3:
        return {
            "ready": False,
            "reason": "insufficient_current_observed_research_purged_folds",
            "minimum_training_rows": config.minimum_training_rows,
            "minimum_train_dates": config.minimum_train_dates,
            "observed_decision_dates": len({row.decision_date for row in samples}),
            "usable_fold_count": len(usable),
            "required_usable_fold_count": 3,
        }

    evaluation_cutoff = date.fromisoformat(usable[-1].test_start)
    calibration_folds = usable[:-1]
    oof_rows = tuple(
        by_id[row.row_id]
        for fold in calibration_folds
        for row in fold.test_rows
        if row.row_id in by_id
        and _strict_date(by_id[row.row_id].label_available_date, "label_available_date") < evaluation_cutoff
    )
    oof_fold_ids = {
        fold.fold_id
        for fold in calibration_folds
        if any(
            row.row_id in by_id
            and _strict_date(by_id[row.row_id].label_available_date, "label_available_date") < evaluation_cutoff
            for row in fold.test_rows
        )
    }
    final_train = tuple(
        by_id[row.row_id]
        for row in usable[-1].train_rows
        if row.row_id in by_id
        and _strict_date(by_id[row.row_id].label_available_date, "label_available_date") < evaluation_cutoff
    )
    oof_ready = (
        len(oof_rows) >= config.minimum_calibration_samples
        and len(oof_fold_ids) >= 2
        and _two_classes(oof_rows)
    )
    final_train_ready = (
        len(final_train) >= config.minimum_fold_train_rows
        and _two_classes(final_train)
    )
    if not oof_ready or not final_train_ready:
        return {
            "ready": False,
            "reason": "insufficient_current_observed_research_oof_support",
            "minimum_training_rows": config.minimum_training_rows,
            "minimum_calibration_samples": config.minimum_calibration_samples,
            "usable_fold_count": len(usable),
            "oof_calibration_sample_count": len(oof_rows),
            "oof_calibration_fold_count": len(oof_fold_ids),
            "final_train_row_count": len(final_train),
            "oof_support_ready": oof_ready,
            "final_train_support_ready": final_train_ready,
        }
    return {
        "ready": True,
        "reason": "default_purged_fold_and_oof_support_ready",
        "minimum_training_rows": config.minimum_training_rows,
        "minimum_train_dates": config.minimum_train_dates,
        "minimum_calibration_samples": config.minimum_calibration_samples,
        "observed_decision_dates": len({row.decision_date for row in samples}),
        "usable_fold_count": len(usable),
        "oof_calibration_sample_count": len(oof_rows),
        "oof_calibration_fold_count": len(oof_fold_ids),
        "final_train_row_count": len(final_train),
    }


def _two_classes(rows: Sequence[RecommendationCalibrationSample]) -> bool:
    return len({row.upside_label for row in rows}) == 2


def _pending_result(
    *,
    reason: str,
    samples: Sequence[RecommendationCalibrationSample],
    outcome_receipt_refs: Sequence[Mapping[str, str]],
    outcome_receipt_refs_sha256: str,
    run_scope: str,
    training_as_of: date,
    evaluation_at: datetime,
    fit_started_at: datetime,
    support: Mapping[str, Any],
    isolated_output_root: Path,
    isolated_learning_root: Path,
) -> Mapping[str, Any]:
    latest_decision = max((str(row.decision_date) for row in samples), default=None)
    return {
        "status": "pending",
        "reason": reason,
        "run_id": None,
        "run_scope": run_scope,
        "decision_date": latest_decision,
        "training_as_of": training_as_of.isoformat(),
        "evaluation_at": evaluation_at.isoformat(timespec="microseconds"),
        "training_semantics": RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH,
        "fit_started_at_utc": fit_started_at.isoformat(timespec="microseconds"),
        "fit_completed_at_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "receipt_path": None,
        "receipt_sha256": None,
        "dataset_id": None,
        "dataset_hash": None,
        "candidate_id": None,
        "candidate_root": None,
        "candidate_manifest_hash": None,
        "candidate_artifact_hash": None,
        "decision": "retain_current",
        "decision_reason": "no_candidate_created_for_insufficient_research_support",
        "training_lineage": {"status": "not_created", "source_group": "natural"},
        "support": dict(support),
        "outcome_receipts": [dict(ref) for ref in outcome_receipt_refs],
        "outcome_receipt_refs_sha256": outcome_receipt_refs_sha256,
        "sample_count": len(samples),
        "isolated_output_root": str(isolated_output_root),
        "isolated_learning_root": str(isolated_learning_root),
        "active_pointer_created": False,
        "research_only": True,
        "current_restated": True,
        "decision_time_eligible": False,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "formal_candidate_eligible": False,
        "forward_evidence_eligible": False,
        "promotion_credit_created": False,
        "natural_evidence": None,
        "natural_outcome_only": True,
        "historical_replay_is_natural_evidence": False,
    }


def _isolated_output_root(learning_output_root: Path, *, data_root: Path | None) -> Path:
    if not learning_output_root.is_absolute():
        raise ValueError("learning_output_root must be absolute")
    _reject_reparse_components(learning_output_root)
    base = learning_output_root.resolve()
    requested = base / "current_observed_natural_research"
    _reject_reparse_components(requested)
    isolated = requested.resolve()
    if isolated != requested.absolute():
        raise ValueError("current-observed research root must not resolve through another path")
    if not _is_relative_to(isolated, base) or isolated == base:
        raise ValueError("current-observed research root escaped learning_output_root")
    canonical_root = (base / "recommendation_learning").resolve()
    if _is_relative_to(isolated, canonical_root) or _is_relative_to(canonical_root, isolated):
        raise ValueError("current-observed research root overlaps canonical learning root")
    formal_root = Path(data_root or os.environ.get("DATA_ROOT") or DEFAULT_DATA_ROOT).resolve()
    if _is_relative_to(isolated, formal_root):
        raise ValueError("current-observed research root must remain outside DATA_ROOT")
    _reject_reparse_components(isolated)
    return isolated


def _reject_reparse_components(path: Path) -> None:
    absolute = path.absolute()
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        try:
            details = cursor.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ValueError("cannot verify isolated research path components") from exc
        reparse = bool(getattr(details, "st_file_attributes", 0) & 0x400)
        if stat.S_ISLNK(details.st_mode) or reparse:
            raise ValueError("isolated research paths cannot contain symlinks or reparse points")


def _read_json_if_plain(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _strict_date(value: str, field_name: str) -> date:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be an ISO date string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date string") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must be a complete YYYY-MM-DD date")
    return parsed


def _canonical_mapping(value: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    encoded = _canonical_json(value)
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict) or not decoded:
        raise ValueError(f"{field_name} must be a non-empty JSON object")
    return decoded


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("value is not canonical JSON") from exc


def _hash_payload(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _is_sha256_text(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _same_declared_value(left: Any, right: Any) -> bool:
    """Compare receipt cost scalars without float coercion."""

    if left is None or right is None:
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, str)) and isinstance(right, (int, str)):
        try:
            left_decimal = Decimal(str(left))
            right_decimal = Decimal(str(right))
        except (InvalidOperation, ValueError):
            return left == right
        if left_decimal.is_finite() and right_decimal.is_finite():
            return left_decimal == right_decimal
    return left == right


def _verify_estimated_cost_math(outcome: Mapping[str, Any]) -> None:
    names = (
        "gross_buy_amount_twd",
        "gross_sell_amount_twd",
        "estimated_buy_cost_twd",
        "estimated_sell_cost_twd",
        "estimated_round_trip_cost_twd",
        "net_profit_twd",
    )
    values: dict[str, Decimal] = {}
    for name in names:
        raw = outcome.get(name)
        if raw is None:
            continue
        if isinstance(raw, bool) or isinstance(raw, float):
            raise ValueError("estimated receipt costs must use exact decimal text or integers")
        try:
            parsed = Decimal(str(raw))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("estimated receipt contains malformed decimal cost values") from exc
        if not parsed.is_finite():
            raise ValueError("estimated receipt contains non-finite decimal cost values")
        values[name] = parsed
    if not values:
        if outcome.get("after_cost_profit_label") is not None:
            raise ValueError("estimated receipt declares a cost label without cost values")
        return
    required = set(names)
    if set(values) != required:
        if outcome.get("after_cost_profit_label") is not None:
            raise ValueError("estimated receipt declares a cost label without complete cost values")
        return
    if values["estimated_round_trip_cost_twd"] != (
        values["estimated_buy_cost_twd"] + values["estimated_sell_cost_twd"]
    ):
        raise ValueError("estimated round-trip fee does not equal buy plus sell fees")
    if values["net_profit_twd"] != (
        values["gross_sell_amount_twd"]
        - values["gross_buy_amount_twd"]
        - values["estimated_buy_cost_twd"]
        - values["estimated_sell_cost_twd"]
    ):
        raise ValueError("estimated net profit does not reconcile to gross proceeds and fees")


def _declared_after_cost_label(outcome: Mapping[str, Any]) -> int | None:
    _verify_estimated_cost_math(outcome)
    raw = outcome.get("net_profit_twd")
    if raw is None:
        return None
    try:
        net_profit = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    if not net_profit.is_finite():
        return None
    return int(net_profit > 0)
