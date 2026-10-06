"""Read-only label and fair-comparison readiness for sealed UX21 receipts."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Literal, Sequence

from app_module.rule_research_forward_store import read_forward_receipt
from ml_module.historical_contracts import HistoricalLabelRow, HistoricalLabelSpec


POLICY_SCHEMA = "rule-research-label-policy.v1"
SPLIT_SCHEMA = "rule-research-label-split.v1"
MAX_RECEIPTS = 32
MAX_LABEL_ROWS = 4096
MAX_REPORT_BYTES = 2 * 1024 * 1024
_MEASURES = {"gross", "net", "gross_excess", "net_excess"}
_HORIZONS = {5, 10, 20}
_MEMBER_STATES = ("matched", "notmatched", "excluded", "unknown", "uncaptured")
_SOURCE_AVAILABILITY_UNKNOWN = "source_availability_unknown"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 128:
        raise ValueError(f"{field}_invalid")
    return value


def _iso_date(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field}_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field}_invalid") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{field}_invalid")
    return value


def _normalize_policy(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    keys = {"schema_version", "policy_id", "version", "measure", "horizons"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("label_policy_schema_invalid")
    if value["schema_version"] != POLICY_SCHEMA:
        raise ValueError("label_policy_version_unsupported")
    policy_id = _required_text(value["policy_id"], "label_policy_id")
    version = _required_text(value["version"], "label_policy_version")
    measure = value["measure"]
    if not isinstance(measure, str) or measure not in _MEASURES:
        raise ValueError("label_measure_invalid")
    horizons = value["horizons"]
    if (not isinstance(horizons, list) or not horizons or len(horizons) > 3
            or any(type(item) is not int or item not in _HORIZONS for item in horizons)
            or len(set(horizons)) != len(horizons)):
        raise ValueError("label_horizons_invalid")
    return {"schema_version": POLICY_SCHEMA, "policy_id": policy_id, "version": version,
            "measure": measure, "horizons": sorted(horizons)}


def _normalize_split(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    keys = {"schema_version", "split_id", "version", "train_start", "train_end",
            "evaluation_start", "evaluation_end", "training_as_of"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("label_split_schema_invalid")
    if value["schema_version"] != SPLIT_SCHEMA:
        raise ValueError("label_split_version_unsupported")
    normalized: dict[str, Any] = {
        "schema_version": SPLIT_SCHEMA,
        "split_id": _required_text(value["split_id"], "label_split_id"),
        "version": _required_text(value["version"], "label_split_version"),
    }
    for field in ("train_start", "train_end", "evaluation_start", "evaluation_end", "training_as_of"):
        normalized[field] = _iso_date(value[field], field)
    if not (normalized["train_start"] <= normalized["train_end"]
            <= normalized["training_as_of"] < normalized["evaluation_start"]
            <= normalized["evaluation_end"]):
        raise ValueError("label_split_windows_overlap_or_invalid")
    return normalized


def _cancelled() -> dict[str, Any]:
    report = {
        "schema_version": "rule-research-label-readiness.v1",
        "status": "cancelled",
        "readiness": "cancelled",
        "label_rows": [],
        "receipts": [],
        "training_eligible": False,
        "historical_pit_eligible": False,
        "formal_eligible": False,
        "natural_authority": False,
        "execution_eligible": False,
        "selection_status": "unknown",
    }
    report["report_identity_sha256"] = _sha256(report)
    return report


def _return_bp(container: object, field: str) -> int | None:
    if not isinstance(container, dict):
        return None
    payload = container.get(field)
    if not isinstance(payload, dict):
        return None
    value = payload.get("integer_bp_half_even")
    return value if type(value) is int else None


def _benchmark_status(source_contract: dict[str, Any]) -> str | None:
    result = source_contract.get("benchmark_result")
    if isinstance(result, dict):
        status = result.get("status")
        return status if isinstance(status, str) else None
    status = source_contract.get("benchmark_status")
    return status if isinstance(status, str) else None


def _availability(horizon: dict[str, Any], *, needs_benchmark: bool) -> tuple[str | None, str]:
    inputs = horizon.get("input_availability")
    if not isinstance(inputs, dict):
        return None, "unknown"
    selected = inputs if needs_benchmark else inputs.get("target")
    if not isinstance(selected, dict):
        return None, "unknown"
    available_date = selected.get("aggregate_available_date")
    status = selected.get("as_of_status")
    if not isinstance(available_date, str):
        return None, "unknown"
    try:
        _iso_date(available_date, "label_available_date")
    except ValueError:
        return None, "invalid"
    if status != "known_by_as_of":
        return available_date, "unknown"
    return available_date, "known_research_only"


def _measurement(
    *,
    measure: str,
    horizon: dict[str, Any],
    projection: dict[str, Any],
    source_contract: dict[str, Any],
) -> tuple[int | None, list[str]]:
    reasons: list[str] = []
    if horizon.get("calculation_status") != "ready_research":
        reasons.append(f"outcome_{horizon.get('calculation_status', 'status_missing')}")
        reasons.extend(code for code in horizon.get("reason_codes", []) if isinstance(code, str))
        return None, sorted(set(reasons))
    if horizon.get("maturity_status") != "ready":
        reasons.append(f"outcome_maturity_{horizon.get('maturity_status', 'unknown')}")
        return None, reasons

    target = horizon.get("target")
    benchmark = horizon.get("benchmark")
    comparison = horizon.get("comparison")
    cost_policy = projection.get("cost_policy")
    if measure in {"gross", "net"}:
        if measure == "net":
            if not isinstance(cost_policy, dict):
                return None, ["explicit_cost_policy_missing"]
            if not isinstance(target, dict) or target.get("cost_status") != "explicit":
                return None, ["target_cost_basis_missing_or_unsupported"]
        field = "gross_return" if measure == "gross" else "net_return"
        value = _return_bp(target, field)
        return (value, []) if value is not None else (None, [f"target_{measure}_missing"])

    if projection.get("benchmark") is None:
        return None, ["explicit_benchmark_missing"]
    if _benchmark_status(source_contract) != "qualified_research":
        return None, ["benchmark_source_not_qualified_research"]
    if not isinstance(comparison, dict) or comparison.get("basis_comparable") is not True:
        return None, ["benchmark_basis_incompatible_or_unknown"]
    if measure == "net_excess":
        if not isinstance(cost_policy, dict):
            return None, ["explicit_cost_policy_missing"]
        if (not isinstance(target, dict) or target.get("cost_status") != "explicit"
                or not isinstance(benchmark, dict) or benchmark.get("cost_status") != "explicit"):
            return None, ["target_or_benchmark_cost_basis_missing_or_unsupported"]
    field = "gross_excess_return" if measure == "gross_excess" else "net_excess_return"
    value = _return_bp(comparison, field)
    return (value, []) if value is not None else (None, [f"{measure}_missing"])


def _source_summary(
    *,
    parent_receipt: Path,
    outcome_receipt: Path,
    readback: dict[str, Any],
    projection: dict[str, Any],
) -> dict[str, Any]:
    contract = readback.get("source_contract")
    if not isinstance(contract, dict):
        contract = {}
    benchmark_result = contract.get("benchmark_result")
    benchmark_result = benchmark_result if isinstance(benchmark_result, dict) else {}
    return {
        "parent_receipt_path": str(parent_receipt.resolve()),
        "parent_identity_sha256": projection.get("parent_identity_sha256"),
        "outcome_receipt_path": str(outcome_receipt.resolve()),
        "outcome_identity_sha256": readback.get("saved_identity_sha256"),
        "outcome_capture_sha256": readback.get("input_sha256"),
        "result_identity_sha256": projection.get("result_identity_sha256"),
        "decision_date": projection.get("decision_date"),
        "as_of_date": projection.get("as_of_date"),
        "adapter_version": contract.get("adapter_version"),
        "source_contract_sha256": _sha256(contract),
        "source_mode": contract.get("source_mode"),
        "source_availability": contract.get("source_availability"),
        "price_basis": contract.get("price_basis"),
        "corporate_action_basis": contract.get("corporate_action_basis"),
        "calendar_scope": contract.get("calendar_scope"),
        "temporary_closure_status": contract.get("temporary_closure_status"),
        "target_basis_status": contract.get("target_basis_status"),
        "target_source_pin_sha256": contract.get("target_source_pin_sha256"),
        "benchmark": projection.get("benchmark"),
        "benchmark_source_status": benchmark_result.get("status", contract.get("benchmark_status")),
        "cost_policy": projection.get("cost_policy"),
        "population": projection.get("population"),
    }


def _state_counts(members: list[dict[str, Any]]) -> dict[str, int]:
    return {state: sum(member.get("member_state") == state for member in members)
            for state in _MEMBER_STATES}


def _make_label_row(
    *,
    receipt_index: int,
    source: dict[str, Any],
    member: dict[str, Any],
    horizon: dict[str, Any],
    measure: str,
    label_spec: HistoricalLabelSpec,
    policy_hash: str,
    split_hash: str | None,
    split: dict[str, Any] | None,
    source_contract: dict[str, Any],
    projection: dict[str, Any],
) -> dict[str, Any]:
    value_bp, reasons = _measurement(measure=measure, horizon=horizon, projection=projection,
                                     source_contract=source_contract)
    horizon_end = horizon.get("expected_end_date")
    if isinstance(horizon_end, str):
        try:
            _iso_date(horizon_end, "horizon_end_date")
        except ValueError:
            horizon_end = None
    available_date, availability_status = _availability(
        horizon, needs_benchmark=measure in {"gross_excess", "net_excess"})
    if availability_status == "unknown":
        reasons.append(_SOURCE_AVAILABILITY_UNKNOWN)
    if availability_status == "invalid":
        reasons.append("sealed_availability_date_invalid")
    if value_bp is None:
        status = "missing_or_unqualified"
    elif availability_status == "unknown":
        status = "value_ready_availability_unknown_research_only"
    elif availability_status == "invalid":
        status = "value_ready_availability_invalid_research_only"
    else:
        status = "value_ready_research_only"

    decision_date = projection["decision_date"]
    split_role = "unassigned_split_policy_missing"
    temporal_train_candidate = False
    evaluation_candidate = False
    historical_label: HistoricalLabelRow | None = None
    if (horizon_end is not None and available_date is not None
            and availability_status == "known_research_only"):
        maturity: Literal["ready", "pending"] = "ready" if value_bp is not None else "pending"
        row_value = value_bp if maturity == "ready" else None
        try:
            historical_label = HistoricalLabelRow(
                symbol=member["stock_code"], decision_date=decision_date,
                label_id=label_spec.label_id, value=row_value,
                horizon_end_date=horizon_end, available_date=available_date,
                maturity_status=maturity, quality="research_only")
        except (TypeError, ValueError):
            reasons.append("historical_label_date_or_value_invalid")
    if split is not None:
        if split["train_start"] <= decision_date <= split["train_end"]:
            split_role = "train_window_research_only"
            source_timing_known = (
                source_contract.get("source_mode") != "current_observed"
                and source_contract.get("source_availability") not in {None, "unknown"}
            )
            temporal_train_candidate = bool(
                historical_label is not None
                and historical_label.is_fit_eligible(training_as_of=split["training_as_of"])
                and horizon_end is not None
                and horizon_end < split["evaluation_start"]
                and availability_status == "known_research_only"
                and source_timing_known
            )
            if historical_label is None or available_date is None:
                reasons.append(_SOURCE_AVAILABILITY_UNKNOWN)
            if not source_timing_known:
                reasons.append(_SOURCE_AVAILABILITY_UNKNOWN)
            if horizon_end is None:
                reasons.append("label_horizon_end_missing")
            elif horizon_end >= split["evaluation_start"]:
                reasons.append("training_label_reaches_evaluation_window")
            elif not temporal_train_candidate and historical_label is not None:
                reasons.append("label_not_mature_by_training_as_of")
        elif split["evaluation_start"] <= decision_date <= split["evaluation_end"]:
            split_role = "evaluation_window_research_only"
            evaluation_candidate = value_bp is not None and availability_status != "invalid"
            if value_bp is None:
                reasons.append("evaluation_label_unavailable")
        else:
            split_role = "outside_split_windows"

    benchmark_value = horizon.get("benchmark")
    target_value = horizon.get("target")
    benchmark: dict[str, Any] = benchmark_value if isinstance(benchmark_value, dict) else {}
    target: dict[str, Any] = target_value if isinstance(target_value, dict) else {}
    price_identities = {
        "target_entry": target.get("entry_price_identity"),
        "target_end": target.get("end_price_identity"),
    }
    if measure in {"gross_excess", "net_excess"}:
        price_identities.update({
            "benchmark_entry": benchmark.get("entry_price_identity"),
            "benchmark_end": benchmark.get("end_price_identity"),
        })
    identity_payload = {
        "outcome_identity_sha256": source["outcome_identity_sha256"],
        "result_identity_sha256": source["result_identity_sha256"],
        "policy_sha256": policy_hash,
        "split_policy_sha256": split_hash,
        "decision_date": decision_date,
        "method_id": member["method_id"],
        "stock_code": member["stock_code"],
        "horizon": label_spec.horizon_trading_days,
        "label_id": label_spec.label_id,
    }
    sample_id = _sha256(identity_payload)
    comparison_group_id = _sha256({k: v for k, v in identity_payload.items() if k != "method_id"})
    return {
        "sample_id": sample_id,
        "comparison_group_id": comparison_group_id,
        "receipt_index": receipt_index,
        "outcome_identity_sha256": source["outcome_identity_sha256"],
        "method_id": member["method_id"],
        "stock_code": member["stock_code"],
        "member_state": member["member_state"],
        "selection_status": member.get("selection_status", "unknown"),
        "decision_date": decision_date,
        "horizon": f"H{label_spec.horizon_trading_days}",
        "label_id": label_spec.label_id,
        "measure": measure,
        "value_bp": value_bp,
        "status": status,
        "reason_codes": sorted(set(reasons)),
        "label_end_date": horizon_end,
        "available_date": available_date,
        "availability_status": availability_status,
        "split_role": split_role,
        "temporal_train_candidate": temporal_train_candidate,
        "evaluation_candidate": evaluation_candidate,
        "quality": "research_only",
        "source_label_schema": horizon.get("label_schema"),
        "price_identities": price_identities,
        "historical_label": None if historical_label is None else asdict(historical_label),
    }


def _baseline_readiness(
    *,
    policy: dict[str, Any] | None,
    policy_hash: str | None,
    label_schema_hash: str | None,
    label_specs: list[HistoricalLabelSpec],
    label_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    known_dates = sum(row["availability_status"] == "known_research_only" for row in label_rows)
    unknown_dates = sum(row["availability_status"] == "unknown" for row in label_rows)
    invalid_dates = sum(row["availability_status"] == "invalid" for row in label_rows)
    date_status = (
        "not_configured" if policy is None else
        "no_sealed_point_availability_dates" if known_dates == 0 and invalid_dates == 0 else
        "complete_research_only_dates" if unknown_dates == 0 and invalid_dates == 0 else
        "partial_research_only_dates"
    )
    missing = [
        "actual_downside_label_policy_and_value",
        "pinned_champion_and_challenger_prediction_identities",
        "same_sample_prediction_coverage_and_pinned_k",
        "feature_registry_hash",
        "decision_time_feature_evidence",
        "feature_values_for_historical_training_schema",
    ]
    if policy is None:
        missing.append("explicit_return_measure_policy")
    if known_dates == 0:
        missing.append("label_available_date_evidence")
    elif unknown_dates or invalid_dates:
        missing.append("label_available_date_evidence_for_some_rows")
    return {
        "status": "blocked_missing_comparison_inputs",
        "existing_adapter": "ml_module.drift_champion_comparison.MLChampionComparisonService",
        "adapter_invoked": False,
        "required_adapter_fields": [
            "sample_id", "actual_return_bp", "actual_downside", "champion_score",
            "challenger_score", "challenger_return_prediction_bp",
            "challenger_downside_probability", "pinned_k",
        ],
        "missing": missing,
        "actual_return_binding": None if policy is None else {
            "field": "actual_return_bp",
            "measure": policy["measure"],
            "policy_sha256": policy_hash,
            "label_schema_sha256": label_schema_hash,
            "horizons": policy["horizons"],
        },
        "label_available_date_evidence": {
            "status": date_status,
            "rows_with_declared_dates": known_dates,
            "rows_without_declared_dates": unknown_dates,
            "rows_with_invalid_dates": invalid_dates,
            "dates_are_research_only": True,
            "source_availability_unknown_does_not_become_pit": True,
        },
        "historical_training_sample_missing_fields": [
            "feature_values", "downside_target", "rule_score_bp",
        ],
        "feature_registry_hash": None,
        "decision_time_feature_evidence": None,
        "prediction_identities": None,
        "k": None,
        "selection_status": "unknown",
    }


def build_label_readiness_batch(
    receipts: Sequence[tuple[str | Path, str | Path]],
    policy: dict[str, Any] | None,
    split_policy: dict[str, Any] | None,
    cancel_callback: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Build a bounded, read-only research label and comparison readiness report."""
    cancel = cancel_callback or (lambda: False)
    if cancel():
        return _cancelled()
    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes)):
        raise ValueError("label_receipts_sequence_required")
    if not 1 <= len(receipts) <= MAX_RECEIPTS:
        raise ValueError("label_receipt_count_bound")
    normalized_policy = _normalize_policy(policy)
    normalized_split = _normalize_split(split_policy)
    normalized_receipts: list[tuple[Path, Path]] = []
    exact_paths: set[tuple[str, str]] = set()
    for pair in receipts:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError("label_receipt_pair_invalid")
        parent_path, outcome_path = Path(pair[0]).absolute(), Path(pair[1]).absolute()
        pair_key = (str(parent_path.resolve()), str(outcome_path.resolve()))
        if pair_key in exact_paths:
            raise ValueError("label_duplicate_receipt_input")
        exact_paths.add(pair_key)
        normalized_receipts.append((parent_path, outcome_path))

    loaded: list[dict[str, Any]] = []
    seen_parent_decisions: set[tuple[str, str]] = set()
    for parent_path, outcome_path in normalized_receipts:
        if cancel():
            return _cancelled()
        readback = read_forward_receipt(parent_path, outcome_path, cancel_callback=cancel)
        if readback.get("cancelled"):
            return _cancelled()
        projection = readback.get("projection")
        source_contract = readback.get("source_contract")
        if not isinstance(projection, dict) or not isinstance(source_contract, dict):
            raise ValueError("label_receipt_projection_invalid")
        parent_identity = projection.get("parent_identity_sha256")
        decision_date = projection.get("decision_date")
        if not isinstance(parent_identity, str) or not isinstance(decision_date, str):
            raise ValueError("label_receipt_identity_invalid")
        parent_decision = (parent_identity, decision_date)
        if parent_decision in seen_parent_decisions:
            raise ValueError("label_duplicate_parent_decision_denominator")
        seen_parent_decisions.add(parent_decision)
        loaded.append({"parent_path": parent_path, "outcome_path": outcome_path,
                       "readback": readback, "projection": projection,
                       "source_contract": source_contract})
    if cancel():
        return _cancelled()
    loaded.sort(key=lambda item: (item["projection"]["decision_date"],
                                  item["projection"]["parent_identity_sha256"],
                                  item["readback"]["saved_identity_sha256"]))

    label_specs: list[HistoricalLabelSpec] = []
    if normalized_policy is not None:
        measure = normalized_policy["measure"]
        label_specs = [HistoricalLabelSpec(
            label_id=f"{measure}_h{horizon}_bp", dtype="int", unit="bp",
            horizon_trading_days=horizon,
            missing_policy="missing_is_not_zero_and_excluded",
            availability_policy="sealed_point_available_date_when_declared",
        ) for horizon in normalized_policy["horizons"]]
    policy_hash = None if normalized_policy is None else _sha256(normalized_policy)
    split_hash = None if normalized_split is None else _sha256(normalized_split)
    label_schema_hash = None if not label_specs else _sha256([asdict(spec) for spec in label_specs])
    projected_row_count = (sum(len(item["projection"]["members"]) for item in loaded)
                           * len(label_specs))
    if projected_row_count > MAX_LABEL_ROWS:
        raise ValueError("label_sample_row_bound")

    label_rows: list[dict[str, Any]] = []
    receipt_summaries: list[dict[str, Any]] = []
    member_state_totals = {state: 0 for state in _MEMBER_STATES}
    label_state_totals = {"value_ready": 0, "value_missing": 0,
                          "availability_known_research_only": 0,
                          "availability_unknown": 0, "availability_invalid": 0,
                          "temporal_train_candidate": 0,
                          "evaluation_candidate": 0}
    for receipt_index, item in enumerate(loaded):
        if cancel():
            return _cancelled()
        projection = item["projection"]
        readback = item["readback"]
        source_contract = item["source_contract"]
        members = projection.get("members")
        if not isinstance(members, list) or not members:
            raise ValueError("label_receipt_members_invalid")
        states = _state_counts(members)
        for state, count in states.items():
            member_state_totals[state] += count
        source = _source_summary(parent_receipt=item["parent_path"],
                                 outcome_receipt=item["outcome_path"],
                                 readback=readback, projection=projection)
        method_counts = projection.get("population", {}).get("method_state_counts", {})
        receipt_summaries.append({
            **source,
            "member_row_denominator": len(members),
            "represented_denominator": projection["population"].get("represented_denominator"),
            "included_denominator": projection["population"].get("included_denominator"),
            "member_state_counts": states,
            "method_state_counts": method_counts,
            "selection_status": "unknown",
        })
        if normalized_policy is None:
            continue
        for member in members:
            horizons = member.get("horizons")
            if not isinstance(horizons, list):
                raise ValueError("label_receipt_horizons_invalid")
            horizon_by_sessions = {row.get("sessions"): row for row in horizons if isinstance(row, dict)}
            for spec in label_specs:
                horizon = horizon_by_sessions.get(spec.horizon_trading_days)
                if not isinstance(horizon, dict):
                    raise ValueError("label_receipt_horizon_missing")
                row = _make_label_row(
                    receipt_index=receipt_index, source=source, member=member,
                    horizon=horizon, measure=normalized_policy["measure"],
                    label_spec=spec, policy_hash=policy_hash or "",
                    split_hash=split_hash,
                    split=normalized_split, source_contract=source_contract,
                    projection=projection,
                )
                label_rows.append(row)
                label_state_totals["value_ready" if row["value_bp"] is not None else "value_missing"] += 1
                if row["availability_status"] == "unknown":
                    label_state_totals["availability_unknown"] += 1
                elif row["availability_status"] == "invalid":
                    label_state_totals["availability_invalid"] += 1
                elif row["availability_status"] == "known_research_only":
                    label_state_totals["availability_known_research_only"] += 1
                if row["temporal_train_candidate"]:
                    label_state_totals["temporal_train_candidate"] += 1
                if row["evaluation_candidate"]:
                    label_state_totals["evaluation_candidate"] += 1

    train_dates = sorted({row["decision_date"] for row in label_rows
                          if row["split_role"] == "train_window_research_only"
                          and row["temporal_train_candidate"]})
    evaluation_dates = sorted({row["decision_date"] for row in label_rows
                               if row["split_role"] == "evaluation_window_research_only"
                               and row["evaluation_candidate"]})
    date_overlap = sorted(set(train_dates) & set(evaluation_dates))
    split_status = "not_configured" if normalized_split is None else (
        "research_only_temporal_candidates" if train_dates and evaluation_dates and not date_overlap
        else "blocked_missing_temporal_partition_candidates")
    method_ids = sorted({row["method_id"] for row in label_rows})
    method_partitions = {
        method: {
            "train_window_rows": sum(row["method_id"] == method and row["split_role"] == "train_window_research_only"
                                     for row in label_rows),
            "temporal_train_candidates": sum(row["method_id"] == method and row["temporal_train_candidate"]
                                             for row in label_rows),
            "evaluation_window_rows": sum(row["method_id"] == method and row["split_role"] == "evaluation_window_research_only"
                                           for row in label_rows),
            "evaluation_candidates": sum(row["method_id"] == method and row["evaluation_candidate"]
                                          for row in label_rows),
        }
        for method in method_ids
    }
    missing_configuration: list[str] = []
    if normalized_policy is None:
        missing_configuration.append("label_policy_not_configured")
    if normalized_split is None:
        missing_configuration.append("split_policy_not_configured")
    readiness = "blocked_missing_configuration" if missing_configuration else "research_only"
    report = {
        "schema_version": "rule-research-label-readiness.v1",
        "status": readiness,
        "readiness": readiness,
        "reason_codes": missing_configuration,
        "label_policy": {
            "status": "not_configured" if normalized_policy is None else "configured",
            "reason_codes": ["label_policy_not_configured"] if normalized_policy is None else [],
            "value": normalized_policy,
            "sha256": policy_hash,
            "measure": None if normalized_policy is None else normalized_policy["measure"],
            "horizons": [] if normalized_policy is None else normalized_policy["horizons"],
            "label_specs": [asdict(spec) for spec in label_specs],
            "label_schema_sha256": label_schema_hash,
        },
        "split_policy": {
            "status": "not_configured" if normalized_split is None else split_status,
            "value": normalized_split,
            "sha256": split_hash,
            "method": "explicit_fixed_windows_with_label_end_purge.v1",
            "train_decision_dates": train_dates,
            "evaluation_decision_dates": evaluation_dates,
            "overlap_decision_dates": date_overlap,
            "training_as_of": None if normalized_split is None else normalized_split["training_as_of"],
            "training_label_end_must_precede_evaluation_start": True,
            "training_labels_must_be_available_by_training_as_of": True,
            "evaluation_rows_enter_training": False,
            "method_partitions": method_partitions,
            "reason_codes": missing_configuration if missing_configuration else (
                [] if split_status == "research_only_temporal_candidates"
                else ["one_or_both_temporal_partitions_have_no_qualified_labels"]),
        },
        "source_denominators": {
            "receipt_count": len(receipt_summaries),
            "method_member_rows": sum(item["member_row_denominator"] for item in receipt_summaries),
            "matched": member_state_totals["matched"],
            "notmatched": member_state_totals["notmatched"],
            "excluded": member_state_totals["excluded"],
            "unknown": member_state_totals["unknown"],
            "uncaptured": member_state_totals["uncaptured"],
            "selection_status": "unknown",
            "included_denominator_sum": sum(item["included_denominator"] or 0 for item in receipt_summaries),
            "represented_denominator_sum": sum(item["represented_denominator"] or 0 for item in receipt_summaries),
            "cohort_denominators_counted_once_per_receipt": True,
        },
        "label_denominators": {
            **label_state_totals,
            "row_count": len(label_rows),
            "by_method": method_partitions,
        },
        "receipts": receipt_summaries,
        "label_rows": label_rows,
        "baseline_readiness": _baseline_readiness(
            policy=normalized_policy, policy_hash=policy_hash,
            label_schema_hash=label_schema_hash, label_specs=label_specs,
            label_rows=label_rows),
        "training_eligible": False,
        "historical_pit_eligible": False,
        "formal_eligible": False,
        "natural_authority": False,
        "execution_eligible": False,
        "selection_status": "unknown",
    }
    report["report_identity_sha256"] = _sha256(report)
    if len(json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("label_report_byte_bound")
    return report


def build_label_readiness(
    parent_receipt: str | Path,
    outcome_receipt: str | Path,
    policy: dict[str, Any] | None,
    split_policy: dict[str, Any] | None,
    cancel_callback: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Single-pair convenience wrapper around the batch reader."""
    return build_label_readiness_batch([(parent_receipt, outcome_receipt)], policy,
                                       split_policy, cancel_callback=cancel_callback)
