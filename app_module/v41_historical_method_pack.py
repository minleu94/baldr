"""V4.1 A 線第二輪的歷史資料 manifest 與候選方法包。

本模組把既有 ``EvidenceEvent``／``EvidenceOutcome`` 的 read-only 研究輸入
展開成逐列、逐 horizon 的可重現 manifest。它的目的不是重建歷史事件，而是
讓「缺少什麼、哪一列為何不能進研究、哪個候選仍未接線」都能以 machine-
readable 形式交給 B 線 shadow consumer。

所有金融數值沿用既有校準模組的整數 bp 契約。這裡不開啟正式 SQLite
writer、不改 Recommendation／ScoringEngine、不補歷史 PIT 欄位，也不把
deterministic sample 或 historical replay 當成自然 forward evidence。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from app_module.evidence_event_dtos import (
    EvidenceEvent,
    EvidenceEventType,
    EvidenceOutcome,
    EvidenceOutcomeStatus,
    normalize_event_type,
    normalize_outcome_status,
)
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.recommendation_calibration import (
    AUXILIARY_HORIZON_DAYS,
    DEFAULT_UNIVERSE_POLICY_ID,
    PRIMARY_HORIZON_DAYS,
    RecommendationCalibrationConfig,
    RecommendationCalibrationDataset,
    build_recommendation_calibration_dataset,
    evaluate_recommendation_calibration,
    sample_evidence_rows,
)


HISTORICAL_METHOD_PACK_SCHEMA_VERSION = "v41-historical-method-pack.v1"
HISTORICAL_DATASET_MANIFEST_SCHEMA_VERSION = "v41-historical-dataset-manifest.v1"
FROZEN_CANDIDATE_ARTIFACT_SCHEMA_VERSION = "v41-frozen-candidate-artifact.v1"
DEFAULT_RETURN_BASIS = "close_to_close_event_date"
DEFAULT_MANIFEST_FILE = "historical_dataset_manifest.json"
DEFAULT_REPORT_FILE = "historical_calibration_report.json"
DEFAULT_ARTIFACT_FILE = "frozen_candidate_artifact.json"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload_hash(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _date_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _text(value: object) -> str | None:
    if value is None or isinstance(value, (bool, Mapping, list, tuple)):
        return None
    text = str(value).strip()
    return text or None


def _enum_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def _metadata(event: EvidenceEvent) -> Mapping[str, Any]:
    return event.metadata if isinstance(event.metadata, Mapping) else {}


def _outcome_metadata(outcome: EvidenceOutcome | None) -> Mapping[str, Any]:
    if outcome is None or not isinstance(outcome.metadata, Mapping):
        return {}
    return outcome.metadata


def _lineage_hash(outcome: EvidenceOutcome | None) -> str | None:
    metadata = _outcome_metadata(outcome)
    lineage = metadata.get("evidence_lineage")
    if isinstance(lineage, Mapping):
        return _text(lineage.get("event_hash"))
    return _text(metadata.get("source_hash"))


def _int_value(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed


def _date_gate(
    *,
    value: object,
    decision_date: str | None,
    field_name: str,
    gaps: list[str],
) -> str | None:
    parsed = _date_text(value)
    if parsed is None:
        gaps.append(f"{field_name}_missing_or_invalid")
        return None
    if decision_date is not None and parsed > decision_date:
        gaps.append(f"{field_name}_after_decision")
    return parsed


def _availability_gate(
    *,
    metadata: Mapping[str, Any],
    prefix: str,
    decision_date: str | None,
    gaps: list[str],
) -> str | None:
    """讀取候選欄位的 available-at，不把缺少 timestamp 猜成可得。"""

    value = metadata.get(f"{prefix}_available_at")
    if value in (None, ""):
        value = metadata.get(f"{prefix}_available_date")
    if value in (None, ""):
        gaps.append(f"{prefix}_available_at_missing")
        return None
    parsed_date = _date_text(value)
    if parsed_date is None:
        gaps.append(f"{prefix}_available_at_invalid")
        return _text(value)
    if decision_date is not None and parsed_date > decision_date:
        gaps.append(f"{prefix}_available_at_after_decision")
    return _text(value)


def _source_hash_gate(
    *,
    metadata: Mapping[str, Any],
    prefix: str,
    gaps: list[str],
) -> str | None:
    for key in (f"{prefix}_source_hash", f"{prefix}_payload_hash", f"{prefix}_hash"):
        value = _text(metadata.get(key))
        if value:
            return value
    gaps.append(f"{prefix}_source_hash_missing")
    return None


def _candidate_feature_status(
    event: EvidenceEvent,
    *,
    decision_date: str | None,
) -> dict[str, Any]:
    metadata = _metadata(event)
    result: dict[str, Any] = {}

    has_score = event.score_percentile_bp is not None or event.score_bp is not None
    result["current_score_v1"] = {
        "status": "ready" if has_score else "blocked",
        "present_fields": [
            field
            for field, value in (
                ("score_percentile_bp", event.score_percentile_bp),
                ("score_bp", event.score_bp),
            )
            if value is not None
        ],
        "gap_codes": [] if has_score else ["ranking_score_missing"],
    }

    price_volume_fields = {
        "indicator_score_bp": _int_value(metadata.get("indicator_score_bp")),
        "volume_score_bp": _int_value(metadata.get("volume_score_bp")),
    }
    price_volume_gaps = [
        f"decision_time_{field}_missing"
        for field, value in price_volume_fields.items()
        if value is None
    ]
    result["price_volume_v1"] = {
        "status": "ready" if not price_volume_gaps else "blocked",
        "present_fields": [field for field, value in price_volume_fields.items() if value is not None],
        "gap_codes": price_volume_gaps,
        "feature_values_bp": {
            field: value for field, value in price_volume_fields.items() if value is not None
        },
    }

    chip_keys = (
        "chip_score_bp",
        "institutional_flow_score_bp",
        "tdcc_dispersion_index_bp",
    )
    funding_keys = (
        "funding_score_bp",
        "credit_score_bp",
        "margin_score_bp",
    )
    chip_field = next((key for key in chip_keys if _int_value(metadata.get(key)) is not None), None)
    funding_field = next((key for key in funding_keys if _int_value(metadata.get(key)) is not None), None)
    chip_funding_gaps: list[str] = []
    if chip_field is None:
        chip_funding_gaps.append("decision_time_chip_feature_missing")
    if funding_field is None:
        chip_funding_gaps.append("decision_time_funding_feature_missing")
    chip_available_at = None
    funding_available_at = None
    chip_source_hash = None
    funding_source_hash = None
    if chip_field is not None:
        chip_available_at = _availability_gate(
            metadata=metadata,
            prefix="chip",
            decision_date=decision_date,
            gaps=chip_funding_gaps,
        )
        chip_source_hash = _source_hash_gate(
            metadata=metadata,
            prefix="chip",
            gaps=chip_funding_gaps,
        )
    if funding_field is not None:
        funding_available_at = _availability_gate(
            metadata=metadata,
            prefix="funding",
            decision_date=decision_date,
            gaps=chip_funding_gaps,
        )
        funding_source_hash = _source_hash_gate(
            metadata=metadata,
            prefix="funding",
            gaps=chip_funding_gaps,
        )
    result["chip_funding_v1"] = {
        "status": "ready" if not chip_funding_gaps else "blocked",
        "present_fields": [field for field in (chip_field, funding_field) if field is not None],
        "gap_codes": sorted(set(chip_funding_gaps)),
        "available_at": {
            "chip": chip_available_at,
            "funding": funding_available_at,
        },
        "source_hashes": {
            "chip": chip_source_hash,
            "funding": funding_source_hash,
        },
    }

    industry_gaps: list[str] = []
    industry_field = next(
        (
            key
            for key in ("industry_score_bp", "industry_relative_score_bp")
            if _int_value(metadata.get(key)) is not None
        ),
        None,
    )
    if industry_field is None:
        industry_gaps.append("decision_time_industry_feature_missing")
    industry_available_at = None
    industry_source_hash = None
    if industry_field is not None:
        industry_available_at = _availability_gate(
            metadata=metadata,
            prefix="industry",
            decision_date=decision_date,
            gaps=industry_gaps,
        )
        industry_source_hash = _source_hash_gate(
            metadata=metadata,
            prefix="industry",
            gaps=industry_gaps,
        )
    if not _text(event.industry_benchmark_id):
        industry_gaps.append("industry_benchmark_identity_missing")
    result["industry_relative_v1"] = {
        "status": "ready" if not industry_gaps else "blocked",
        "present_fields": [field for field in (industry_field,) if field is not None],
        "gap_codes": sorted(set(industry_gaps)),
        "available_at": industry_available_at,
        "source_hash": industry_source_hash,
        "industry_benchmark_id": _text(event.industry_benchmark_id),
    }

    theme_gaps: list[str] = []
    membership_id = _text(
        metadata.get("pit_membership_id") or metadata.get("pit_theme_membership_id")
    )
    membership_as_of = _date_text(
        metadata.get("pit_membership_as_of_date") or metadata.get("membership_as_of_date")
    )
    membership_available_at = _text(
        metadata.get("pit_membership_available_at") or metadata.get("membership_available_at")
    )
    membership_source_hash = _text(
        metadata.get("pit_membership_source_hash") or metadata.get("membership_source_hash")
    )
    if not _text(event.concept_basket):
        theme_gaps.append("theme_label_missing")
    if not membership_id:
        theme_gaps.append("pit_membership_identity_missing")
    if membership_as_of is None:
        theme_gaps.append("pit_membership_as_of_date_missing_or_invalid")
    elif decision_date is not None and str(membership_as_of) > decision_date:
        theme_gaps.append("pit_membership_as_of_date_after_decision")
    if not membership_available_at:
        theme_gaps.append("pit_membership_available_at_missing")
    elif _date_text(membership_available_at) is None:
        theme_gaps.append("pit_membership_available_at_invalid")
    elif decision_date is not None and str(_date_text(membership_available_at)) > decision_date:
        theme_gaps.append("pit_membership_available_at_after_decision")
    if not membership_source_hash:
        theme_gaps.append("pit_membership_source_hash_missing")
    result["pit_theme_v1"] = {
        "status": "ready" if not theme_gaps else "blocked",
        "present_fields": [
            field
            for field, value in (
                ("concept_basket", _text(event.concept_basket)),
                ("pit_membership_id", membership_id),
                ("pit_membership_as_of_date", membership_as_of),
                ("pit_membership_available_at", membership_available_at),
                ("pit_membership_source_hash", membership_source_hash),
            )
            if value
        ],
        "gap_codes": sorted(set(theme_gaps)),
        "membership_id": membership_id,
        "membership_as_of_date": membership_as_of,
        "membership_available_at": membership_available_at,
        "source_hash": membership_source_hash,
    }
    return result


def _label_maturity(
    outcome: EvidenceOutcome | None,
    *,
    expected_return_basis: str,
    gaps: list[str],
) -> str:
    if outcome is None:
        gaps.append("outcome_missing")
        return "missing_outcome"
    try:
        status = normalize_outcome_status(outcome.outcome_status)
    except ValueError:
        gaps.append("outcome_status_invalid")
        return "invalid_outcome_status"
    if str(outcome.return_basis or "") != expected_return_basis:
        gaps.append("return_basis_mismatch")
        return "return_basis_mismatch"
    if status == EvidenceOutcomeStatus.READY:
        if outcome.forward_return_bp is None or _date_text(outcome.outcome_price_date) is None:
            gaps.append("mature_outcome_fields_missing")
            return "mature_but_incomplete"
        return "mature"
    if status == EvidenceOutcomeStatus.INSUFFICIENT_FUTURE_DATA:
        gaps.append("label_waiting_for_future_data")
        return "insufficient_future_data"
    if status == EvidenceOutcomeStatus.PENDING:
        gaps.append("label_pending")
        return "pending"
    if status == EvidenceOutcomeStatus.MISSING_PRICE:
        gaps.append("event_price_missing")
        return "missing_price"
    gaps.append("outcome_not_ready")
    return status.value


def _stable_report_hash(report: Mapping[str, Any]) -> str:
    payload = dict(report)
    payload.pop("generated_at", None)
    return _payload_hash(payload)


def _method_specs() -> tuple[dict[str, Any], ...]:
    return (
        {
            "method_id": "current_score_v1",
            "kind": "current_baseline",
            "feature_set_id": "score_percentile_v1",
            "description": "既有 ranking score／score percentile 的研究基線；不替換正式 ranking。",
        },
        {
            "method_id": "price_volume_v1",
            "kind": "simple_challenger",
            "feature_set_id": "price_volume_v1",
            "description": "決策當下已保存的 indicator／volume component；只作消融候選。",
        },
        {
            "method_id": "chip_funding_v1",
            "kind": "deferred_candidate",
            "feature_set_id": None,
            "description": "三大法人／信用交易候選；必須有決策時可得日、source hash 與雙欄位。",
        },
        {
            "method_id": "industry_relative_v1",
            "kind": "deferred_candidate",
            "feature_set_id": None,
            "description": "產業相對強弱候選；必須有 decision-time source 與 industry benchmark。",
        },
        {
            "method_id": "pit_theme_v1",
            "kind": "deferred_candidate",
            "feature_set_id": None,
            "description": "主題候選；只接受 decision-time PIT membership，不使用 current snapshot。",
        },
    )


def _source_row_hash(event: EvidenceEvent, outcome: EvidenceOutcome | None) -> str:
    return _payload_hash(
        {
            "event_id": event.event_id,
            "event_hash": event.event_hash,
            "outcome_id": None if outcome is None else outcome.outcome_id,
            "outcome_status": None
            if outcome is None
            else str(outcome.outcome_status),
            "window_days": None if outcome is None else outcome.window_days,
        }
    )


def _build_row(
    event: EvidenceEvent,
    outcome: EvidenceOutcome | None,
    *,
    horizon_days: int,
    config: RecommendationCalibrationConfig,
    source_file_hash: str,
    eligible_row_ids: set[str],
) -> dict[str, Any]:
    gaps: list[str] = []
    decision_date = _date_text(event.decision_date)
    if decision_date is None:
        gaps.append("decision_date_missing_or_invalid")
    event_date = _date_gate(
        value=event.event_date,
        decision_date=decision_date,
        field_name="event_date",
        gaps=gaps,
    )
    as_of_date = _date_gate(
        value=event.as_of_date,
        decision_date=decision_date,
        field_name="as_of_date",
        gaps=gaps,
    )
    available_date = _date_gate(
        value=event.available_date,
        decision_date=decision_date,
        field_name="available_date",
        gaps=gaps,
    )
    metadata = _metadata(event)
    explicit_available_at = _text(metadata.get("available_at"))
    available_at = explicit_available_at or available_date
    available_at_precision = "timestamp" if explicit_available_at and "T" in explicit_available_at else "date"
    available_at_date = _date_text(available_at)
    if available_at is None:
        gaps.append("available_at_missing")
    elif available_at_date is None:
        gaps.append("available_at_invalid")
    elif decision_date is not None and available_at_date > decision_date:
        gaps.append("available_at_after_decision")

    strategy_version_id = _text(event.strategy_version_id) or _text(metadata.get("strategy_version_id"))
    strategy_config_id = _text(metadata.get("strategy_config_id"))
    strategy_config_hash = _text(metadata.get("strategy_config_hash"))
    strategy_config_schema = _text(metadata.get("strategy_config_schema"))
    if not strategy_version_id:
        gaps.append("strategy_version_id_missing")
    if not strategy_config_id:
        gaps.append("strategy_config_id_missing")
    if strategy_config_schema and not strategy_config_id:
        gaps.append("strategy_config_identity_incomplete")

    universe_policy_id = _text(metadata.get("universe_policy_id"))
    universe_policy_hash = _text(metadata.get("universe_policy_hash"))
    universe_snapshot_id = _text(metadata.get("universe_snapshot_id"))
    universe_snapshot_hash = _text(metadata.get("universe_snapshot_hash"))
    if not universe_policy_id:
        gaps.append("universe_policy_id_missing")
    if universe_policy_id and not universe_policy_hash:
        gaps.append("universe_policy_hash_missing")
    if universe_policy_id and not universe_snapshot_id:
        gaps.append("universe_snapshot_id_missing")
    if universe_policy_id and not universe_snapshot_hash:
        gaps.append("universe_snapshot_hash_missing")

    outcome_metadata = _outcome_metadata(outcome)
    outcome_return_basis = None if outcome is None else _text(outcome.return_basis)
    return_basis = outcome_return_basis or _text(metadata.get("return_basis")) or DEFAULT_RETURN_BASIS
    benchmark_id = (
        _text(event.benchmark_id)
        or _text(outcome_metadata.get("benchmark_id"))
        or _text(metadata.get("benchmark_id"))
    )
    cost_model_id = (
        _text(event.cost_model_id)
        or _text(outcome_metadata.get("cost_model_id"))
        or _text(metadata.get("cost_model_id"))
    )
    if not benchmark_id:
        gaps.append("benchmark_id_missing")
    if not cost_model_id:
        gaps.append("cost_model_id_missing")

    label_gaps: list[str] = []
    label_maturity = _label_maturity(
        outcome,
        expected_return_basis=DEFAULT_RETURN_BASIS,
        gaps=label_gaps,
    )
    gaps.extend(label_gaps)
    if label_maturity == "mature" and outcome is not None:
        if outcome.benchmark_return_bp is None or outcome.benchmark_excess_bp is None:
            gaps.append("benchmark_return_or_excess_missing")
        if outcome.liquidity_cost_bp is None:
            gaps.append("observed_liquidity_cost_missing")

    source_hash = _text(event.event_hash) or _lineage_hash(outcome)
    if not source_hash:
        gaps.append("source_hash_missing")
    feature_status = _candidate_feature_status(event, decision_date=decision_date)
    for candidate in feature_status.values():
        gaps.extend(str(item) for item in candidate.get("gap_codes", ()))

    row_id = f"{event.event_id}:{horizon_days}"
    if row_id in eligible_row_ids:
        row_status = "eligible_mature_observation"
    elif label_maturity in {"missing_outcome", "pending", "insufficient_future_data"}:
        row_status = "not_matured"
    elif gaps:
        row_status = "blocked"
    else:
        row_status = "excluded"
    return {
        "row_id": row_id,
        "event_id": event.event_id,
        "outcome_id": None if outcome is None else outcome.outcome_id,
        "symbol": event.symbol,
        "decision_date": decision_date,
        "event_date": event_date,
        "available_at": available_at,
        "available_at_precision": available_at_precision,
        "as_of_date": as_of_date,
        "available_date": available_date,
        "label_end_date": None if outcome is None else _date_text(outcome.outcome_price_date),
        "label_maturity": label_maturity,
        "label_maturity_available_at": None
        if outcome is None
        else (_text(outcome.data_as_of_date) or _text(outcome.outcome_price_date)),
        "label_remaining_trading_days": _int_value(
            outcome_metadata.get("remaining_trading_days")
        ),
        "horizon_days": horizon_days,
        "strategy_version_id": strategy_version_id,
        "strategy_config_id": strategy_config_id,
        "strategy_config_hash": strategy_config_hash,
        "strategy_config_schema": strategy_config_schema,
        "profile_id": _text(event.profile_id) or _text(metadata.get("profile_id")),
        "universe_policy_id": universe_policy_id,
        "universe_policy_hash": universe_policy_hash,
        "universe_snapshot_id": universe_snapshot_id,
        "universe_snapshot_hash": universe_snapshot_hash,
        "universe_policy_status": (
            "complete"
            if universe_policy_id
            and universe_policy_hash
            and universe_snapshot_id
            and universe_snapshot_hash
            else "incomplete"
        ),
        "return_basis": return_basis,
        "expected_return_basis": DEFAULT_RETURN_BASIS,
        "benchmark_id": benchmark_id,
        "benchmark_return_bp": None if outcome is None else outcome.benchmark_return_bp,
        "benchmark_excess_bp": None if outcome is None else outcome.benchmark_excess_bp,
        "cost_model_id": cost_model_id,
        "fixed_round_trip_cost_bp": config.fixed_round_trip_cost_bp,
        "liquidity_cost_bp": None if outcome is None else outcome.liquidity_cost_bp,
        "forward_return_bp": None if outcome is None else outcome.forward_return_bp,
        "event_hash": _text(event.event_hash),
        "outcome_source_hash": _lineage_hash(outcome),
        "source_hash": source_hash,
        "source_row_hash": _source_row_hash(event, outcome),
        "source_file_hash": source_file_hash,
        "event_data_quality": _enum_value(event.data_quality),
        "outcome_data_quality": None if outcome is None else _enum_value(outcome.data_quality),
        "row_status": row_status,
        "eligible_for_calibration": row_id in eligible_row_ids,
        "candidate_features": feature_status,
        "gap_codes": sorted(set(gaps)),
    }


def build_historical_dataset_manifest(
    events: Iterable[EvidenceEvent],
    outcomes: Iterable[EvidenceOutcome],
    *,
    config: RecommendationCalibrationConfig | None = None,
    source_mode: str = "read_only_sqlite",
    source_file_hash: str | None = None,
    source_path: Path | None = None,
) -> tuple[RecommendationCalibrationDataset, dict[str, Any]]:
    """建立逐列 evidence manifest，並保留所有缺口，不做歷史回填。"""

    cfg = config or RecommendationCalibrationConfig()
    event_rows = tuple(events)
    outcome_rows = tuple(outcomes)
    dataset = build_recommendation_calibration_dataset(
        event_rows,
        outcome_rows,
        source_mode=source_mode,
        universe_policy_id=cfg.universe_policy_id,
        horizons=cfg.horizons,
    )
    eligible_row_ids = {row.row_id for row in dataset.observations}
    if source_file_hash is None:
        source_file_hash = _payload_hash(
            {
                "event_ids": sorted(event.event_id for event in event_rows),
                "outcome_ids": sorted(outcome.outcome_id for outcome in outcome_rows),
            }
        )
    rows_by_id: dict[str, dict[str, Any]] = {}
    for event in sorted(event_rows, key=lambda item: (str(item.decision_date), item.event_id)):
        try:
            if normalize_event_type(event.event_type) != EvidenceEventType.RECOMMENDATION_INCLUDED:
                continue
        except ValueError:
            continue
        for horizon_days in cfg.horizons:
            matching = [
                outcome
                for outcome in outcome_rows
                if outcome.event_id == event.event_id and outcome.window_days == horizon_days
            ]
            outcome = matching[0] if len(matching) == 1 else None
            row = _build_row(
                event,
                outcome,
                horizon_days=horizon_days,
                config=cfg,
                source_file_hash=source_file_hash,
                eligible_row_ids=eligible_row_ids,
            )
            if len(matching) > 1:
                row["row_status"] = "blocked"
                row["gap_codes"] = sorted(set([*row["gap_codes"], "duplicate_outcome_identity"]))
            rows_by_id[row["row_id"]] = row

    rows = [rows_by_id[key] for key in sorted(rows_by_id)]
    gap_counts: Counter[str] = Counter()
    maturity_counts: Counter[str] = Counter()
    row_status_counts: Counter[str] = Counter()
    for row in rows:
        gap_counts.update(row["gap_codes"])
        maturity_counts[row["label_maturity"]] += 1
        row_status_counts[row["row_status"]] += 1

    candidate_coverage: dict[str, Any] = {}
    for spec in _method_specs():
        method_id = str(spec["method_id"])
        statuses = [row["candidate_features"][method_id] for row in rows]
        ready_count = sum(item["status"] == "ready" for item in statuses)
        method_gaps: Counter[str] = Counter()
        for item in statuses:
            method_gaps.update(item.get("gap_codes", ()))
        candidate_coverage[method_id] = {
            "status": "ready" if ready_count else "blocked",
            "ready_row_count": ready_count,
            "blocked_row_count": len(statuses) - ready_count,
            "gap_counts": dict(sorted(method_gaps.items())),
        }

    manifest_core: dict[str, Any] = {
        "schema_version": HISTORICAL_DATASET_MANIFEST_SCHEMA_VERSION,
        "source_mode": source_mode,
        "source_path": None if source_path is None else str(source_path.resolve()),
        "source_file_hash": source_file_hash,
        "source_tables": ["evidence_events", "evidence_outcomes"],
        "input_event_count": len(event_rows),
        "input_outcome_count": len(outcome_rows),
        "row_count": len(rows),
        "observation_row_count": len(dataset.observations),
        "decision_date_min": min((row["decision_date"] for row in rows if row["decision_date"]), default=None),
        "decision_date_max": max((row["decision_date"] for row in rows if row["decision_date"]), default=None),
        "horizons": list(cfg.horizons),
        "strategy_config": {
            "calibration_config": cfg.to_dict(),
            "strategy_identity_policy": "preserve_event_identity; missing_identity_is_gap",
        },
        "universe_policy": {
            "requested_policy_id": cfg.universe_policy_id,
            "missing_policy_is_gap": True,
            "current_universe_used": False,
            "historical_backfill_performed": False,
        },
        "return_cost_benchmark_contract": {
            "return_basis": DEFAULT_RETURN_BASIS,
            "benchmark_source": "event_or_outcome_persisted_benchmark; missing_is_gap",
            "cost_model": "fixed_round_trip_plus_observed_liquidity_v1",
            "fixed_round_trip_cost_bp": cfg.fixed_round_trip_cost_bp,
            "missing_liquidity_cost_policy": "exclude_after_cost_label; never_zero_fill",
        },
        "row_classification": {
            "row_status_counts": dict(sorted(row_status_counts.items())),
            "label_maturity_counts": dict(sorted(maturity_counts.items())),
            "gap_counts": dict(sorted(gap_counts.items())),
        },
        "candidate_coverage": candidate_coverage,
        "rows": rows,
        "reproducibility": {
            "canonical_row_order": "row_id_ascending",
            "manifest_hash_excludes": ["manifest_hash"],
            "source_hash_required": True,
            "database_open_mode": "read_only" if source_mode == "read_only_sqlite" else "not_applicable",
        },
    }
    manifest = dict(manifest_core)
    manifest["manifest_hash"] = _payload_hash(manifest_core)
    return dataset, manifest


def _feature_metrics(report: Mapping[str, Any], feature_set_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    targets = report.get("oos", {}).get("targets", {})
    if not isinstance(targets, Mapping):
        return result
    for target_name, target_payload in targets.items():
        if not isinstance(target_payload, Mapping):
            continue
        feature_sets = target_payload.get("feature_sets", {})
        if not isinstance(feature_sets, Mapping):
            continue
        feature_payload = feature_sets.get(feature_set_id)
        if isinstance(feature_payload, Mapping):
            result[str(target_name)] = feature_payload
    return result


def _method_evaluations(
    report: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    coverage = manifest.get("candidate_coverage", {})
    evaluations: list[dict[str, Any]] = []
    for spec in _method_specs():
        method_id = str(spec["method_id"])
        method_coverage = coverage.get(method_id, {}) if isinstance(coverage, Mapping) else {}
        feature_set_id = spec.get("feature_set_id")
        metrics = _feature_metrics(report, str(feature_set_id)) if feature_set_id else {}
        if metrics:
            status = "measured" if any(
                payload.get("calibrated", {}).get("status") == "measured"
                for payload in metrics.values()
                if isinstance(payload, Mapping)
            ) else "not_evaluable"
            reason = None if status == "measured" else "no_matched_calibrated_oos"
        else:
            status = "ready_not_integrated" if method_coverage.get("ready_row_count", 0) else "blocked"
            reason = (
                "candidate_feature_not_integrated_into_calibration"
                if status == "ready_not_integrated"
                else "missing_decision_time_feature_or_pit_contract"
            )
        evaluations.append(
            {
                **spec,
                "status": status,
                "reason": reason,
                "coverage": method_coverage,
                "metrics": metrics,
            }
        )
    return evaluations


def _selection_decision(report: Mapping[str, Any], config: RecommendationCalibrationConfig) -> dict[str, Any]:
    target = report.get("oos", {}).get("targets", {}).get("upside_20d", {})
    feature_sets = target.get("feature_sets", {}) if isinstance(target, Mapping) else {}
    current = feature_sets.get("score_percentile_v1", {}) if isinstance(feature_sets, Mapping) else {}
    challenger = feature_sets.get("price_volume_v1", {}) if isinstance(feature_sets, Mapping) else {}
    current_metric = current.get("calibrated", {}) if isinstance(current, Mapping) else {}
    challenger_metric = challenger.get("calibrated", {}) if isinstance(challenger, Mapping) else {}
    current_brier = _int_value(current_metric.get("brier_score_bp"))
    challenger_brier = _int_value(challenger_metric.get("brier_score_bp"))
    current_n = _int_value(current_metric.get("sample_count")) or 0
    challenger_n = _int_value(challenger_metric.get("sample_count")) or 0
    same_evaluable = (
        current_metric.get("status") == "measured"
        and challenger_metric.get("status") == "measured"
        and current_brier is not None
        and challenger_brier is not None
        and current_n >= config.minimum_test_samples
        and challenger_n >= config.minimum_test_samples
    )
    if same_evaluable and challenger_brier is not None and current_brier is not None and challenger_brier < current_brier:
        decision = "price_volume_descriptive_improvement_not_promoted"
    elif same_evaluable:
        decision = "retain_current_method_no_oos_improvement"
    else:
        decision = "retain_current_method_insufficient_matched_oos"
    return {
        "research_decision": decision,
        "selected_method_for_shadow": "current_score_v1",
        "current_method": "current_score_v1",
        "challenger_method": "price_volume_v1",
        "primary_target": "upside_20d",
        "current_calibrated_brier_bp": current_brier,
        "challenger_calibrated_brier_bp": challenger_brier,
        "matched_oos_comparison_available": same_evaluable,
        "pre_fix_rules": [
            "只有相同 primary horizon、相同 split、兩方法皆有成熟 calibrated OOS 才能比較。",
            "Brier、辨識力或成本後報酬單一改善不自動 promotion；需經 B 線 shadow review。",
            "缺 source hash、available-at、PIT membership 或 label maturity 時維持 blocked/not_evaluable。",
            "無 matched OOS improvement 或樣本不足時 retain current method。",
        ],
    }


def _natural_time_insufficiency(manifest: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    maturity = manifest.get("row_classification", {}).get("label_maturity_counts", {})
    natural_pending_rows = sum(
        int(maturity.get(status, 0)) for status in ("pending", "insufficient_future_data")
    )
    missing_outcome_rows = int(maturity.get("missing_outcome", 0))
    pending_rows = natural_pending_rows + missing_outcome_rows
    if natural_pending_rows:
        status = "waiting_for_natural_maturity"
    elif missing_outcome_rows:
        status = "blocked_missing_outcome"
    else:
        status = "not_waiting"
    return {
        "status": status,
        "pending_or_missing_label_row_count": pending_rows,
        "natural_pending_row_count": natural_pending_rows,
        "missing_outcome_row_count": missing_outcome_rows,
        "primary_mature_row_count": sum(
            1
            for row in manifest.get("rows", [])
            if row.get("horizon_days") == PRIMARY_HORIZON_DAYS and row.get("label_maturity") == "mature"
        ),
        "auxiliary_mature_row_count": sum(
            1
            for row in manifest.get("rows", [])
            if row.get("horizon_days") == AUXILIARY_HORIZON_DAYS and row.get("label_maturity") == "mature"
        ),
        "fold_count": report.get("fold_count", 0),
        "no_backfill": True,
        "next_action": "待自然 forward outcome 成熟後重跑同一 source hash／contract；不以 fixture 補入。",
    }


def build_v41_historical_method_pack(
    events: Iterable[EvidenceEvent],
    outcomes: Iterable[EvidenceOutcome],
    *,
    config: RecommendationCalibrationConfig | None = None,
    source_mode: str = "read_only_sqlite",
    source_file_hash: str | None = None,
    source_path: Path | None = None,
) -> dict[str, Any]:
    """建立完整 V4.1 research pack；輸出本身不會寫入任何資料來源。"""

    cfg = config or RecommendationCalibrationConfig()
    dataset, manifest = build_historical_dataset_manifest(
        events,
        outcomes,
        config=cfg,
        source_mode=source_mode,
        source_file_hash=source_file_hash,
        source_path=source_path,
    )
    report = evaluate_recommendation_calibration(dataset, config=cfg)
    method_evaluations = _method_evaluations(report, manifest)
    selection = _selection_decision(report, cfg)
    insufficiency = _natural_time_insufficiency(manifest, report)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    artifact_core: dict[str, Any] = {
        "schema_version": FROZEN_CANDIDATE_ARTIFACT_SCHEMA_VERSION,
        "artifact_kind": "v41_historical_candidate",
        "artifact_version": "v1",
        "frozen": True,
        "shadow_only": True,
        "read_only_source": True,
        "dataset_manifest_hash": manifest["manifest_hash"],
        "calibration_report_hash": _stable_report_hash(report),
        "source_file_hash": manifest["source_file_hash"],
        "selected_method_for_shadow": selection["selected_method_for_shadow"],
        "research_decision": selection["research_decision"],
        "candidate_method_ids": [str(item["method_id"]) for item in method_evaluations],
        "b_shadow_consumer_contract": {
            "must_verify_manifest_hash": True,
            "must_verify_source_file_hash": True,
            "must_replay_read_only": True,
            "may_change_formal_recommendation": False,
            "may_write_formal_sqlite": False,
            "promotion_requires_named_review": True,
        },
        "access_boundary": {
            "production_eligible": False,
            "promotion_eligible": False,
            "natural_forward_evidence_credit": False,
            "recommendation_weights_changed": False,
            "scheduler_enabled": False,
            "formal_oos": False,
        },
    }
    artifact = dict(artifact_core)
    artifact["artifact_hash"] = _payload_hash(artifact_core)
    return {
        "schema_version": HISTORICAL_METHOD_PACK_SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": report.get("status", "not_evaluable"),
        "source": {
            "mode": source_mode,
            "path": manifest["source_path"],
            "file_hash": manifest["source_file_hash"],
            "database_open_mode": "read_only" if source_mode == "read_only_sqlite" else "not_applicable",
        },
        "dataset_manifest": manifest,
        "calibration_report": report,
        "candidate_methods": method_evaluations,
        "selection": selection,
        "natural_time_insufficiency": insufficiency,
        "frozen_candidate_artifact": artifact,
        "access_boundary": artifact["access_boundary"],
    }


def load_formal_evidence_rows(db_path: Path) -> tuple[tuple[EvidenceEvent, ...], tuple[EvidenceOutcome, ...]]:
    """以 SQLite URI mode=ro 讀取正式 evidence；repository 不會建立 schema。"""

    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"找不到 evidence SQLite：{path}")
    repository = EvidenceEventRepository(None, db_path=path)
    events = tuple(
        repository.list_events(event_type=EvidenceEventType.RECOMMENDATION_INCLUDED)
    )
    outcomes = tuple(repository.list_outcomes())
    return events, outcomes


def build_formal_v41_historical_method_pack(
    db_path: Path,
    *,
    config: RecommendationCalibrationConfig | None = None,
) -> dict[str, Any]:
    path = Path(db_path).expanduser().resolve()
    events, outcomes = load_formal_evidence_rows(path)
    return build_v41_historical_method_pack(
        events,
        outcomes,
        config=config,
        source_mode="read_only_sqlite",
        source_file_hash=_file_hash(path),
        source_path=path,
    )


def build_sample_v41_historical_method_pack(
    *,
    config: RecommendationCalibrationConfig | None = None,
) -> dict[str, Any]:
    events, outcomes = sample_evidence_rows()
    return build_v41_historical_method_pack(
        events,
        outcomes,
        config=config,
        source_mode="sample_only",
        source_file_hash=None,
        source_path=None,
    )


def write_frozen_method_pack(pack: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    """以 create-only 寫出 manifest／report／artifact；既有檔案一律 fail-closed。"""

    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    payloads = {
        DEFAULT_MANIFEST_FILE: pack["dataset_manifest"],
        DEFAULT_REPORT_FILE: pack["calibration_report"],
        DEFAULT_ARTIFACT_FILE: pack["frozen_candidate_artifact"],
    }
    paths: dict[str, str] = {}
    for filename, payload in payloads.items():
        path = root / filename
        if path.exists():
            raise FileExistsError(f"frozen research artifact 已存在，拒絕覆寫：{path}")
        content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        paths[filename] = str(path)
    return paths


def compact_pack_summary(pack: Mapping[str, Any], paths: Mapping[str, str] | None = None) -> dict[str, Any]:
    manifest = pack["dataset_manifest"]
    report = pack["calibration_report"]
    artifact = pack["frozen_candidate_artifact"]
    return {
        "schema_version": pack["schema_version"],
        "status": pack["status"],
        "source": pack["source"],
        "manifest_hash": manifest["manifest_hash"],
        "artifact_hash": artifact["artifact_hash"],
        "row_count": manifest["row_count"],
        "observation_row_count": manifest["observation_row_count"],
        "row_status_counts": manifest["row_classification"]["row_status_counts"],
        "label_maturity_counts": manifest["row_classification"]["label_maturity_counts"],
        "gap_counts": manifest["row_classification"]["gap_counts"],
        "candidate_coverage": manifest["candidate_coverage"],
        "fold_count": report["fold_count"],
        "research_decision": pack["selection"]["research_decision"],
        "natural_time_insufficiency": pack["natural_time_insufficiency"],
        "frozen": artifact["frozen"],
        "production_eligible": artifact["access_boundary"]["production_eligible"],
        "promotion_eligible": artifact["access_boundary"]["promotion_eligible"],
        "output_paths": dict(paths or {}),
    }
