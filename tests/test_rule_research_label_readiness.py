"""Research-only label/readiness checks over isolated sealed UX21 receipts."""
from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import pytest

import app_module.rule_research_label_readiness as label_readiness
from app_module.rule_research_forward_store import run_forward_isolated
from tests.test_rule_research_forward_isolated import pipeline


def _policy(measure: str = "gross", horizons: list[int] | None = None) -> dict[str, object]:
    return {
        "schema_version": label_readiness.POLICY_SCHEMA,
        "policy_id": f"fixture-{measure}",
        "version": "1",
        "measure": measure,
        "horizons": [5, 10, 20] if horizons is None else horizons,
    }


def _split(decision: str, *, include_decision_in: str = "evaluation") -> dict[str, str]:
    current = date.fromisoformat(decision)
    if include_decision_in == "training":
        train_start = current - timedelta(days=30)
        train_end = current
        training_as_of = current + timedelta(days=25)
        evaluation_start = current + timedelta(days=26)
        evaluation_end = current + timedelta(days=60)
    else:
        train_start = current - timedelta(days=30)
        train_end = current - timedelta(days=5)
        training_as_of = current - timedelta(days=2)
        evaluation_start = current
        evaluation_end = current + timedelta(days=30)
    return {
        "schema_version": label_readiness.SPLIT_SCHEMA,
        "split_id": "fixture-time-windows",
        "version": "1",
        "train_start": train_start.isoformat(),
        "train_end": train_end.isoformat(),
        "evaluation_start": evaluation_start.isoformat(),
        "evaluation_end": evaluation_end.isoformat(),
        "training_as_of": training_as_of.isoformat(),
    }


def _saved(pipeline):
    _args, parent, _config, runtime, *_ = pipeline
    result = run_forward_isolated(runtime, execute=True)
    assert result["status"] == "saved", result
    return Path(parent), Path(result["receipt_path"]), result


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_missing_policy_still_reads_exact_sealed_source_and_keeps_full_denominators(pipeline):
    args, _parent, _config, _runtime, *_ = pipeline
    parent, outcome, saved = _saved(pipeline)
    paths = [parent, outcome, Path(args["db_path"])]
    before = {path: _hash(path) for path in paths}

    report = label_readiness.build_label_readiness(parent, outcome, None, None)

    assert report["status"] == "blocked_missing_configuration"
    assert report["label_policy"]["status"] == "not_configured"
    assert report["label_rows"] == []
    assert report["receipts"][0]["outcome_identity_sha256"] == saved["identity_sha256"]
    denominators = report["source_denominators"]
    assert denominators["represented_denominator_sum"] == 3
    assert denominators["cohort_denominators_counted_once_per_receipt"] is True
    assert denominators["method_member_rows"] == 6
    assert sum(denominators[state] for state in ("matched", "notmatched", "excluded", "unknown", "uncaptured")) == 6
    for states in report["receipts"][0]["method_state_counts"].values():
        assert sum(states[state] for state in ("matched", "notmatched", "excluded", "unknown", "uncaptured")) == 3
    assert report["selection_status"] == "unknown"
    assert all(report[key] is False for key in (
        "training_eligible", "historical_pit_eligible", "formal_eligible", "natural_authority", "execution_eligible"))
    assert {path: _hash(path) for path in paths} == before


def test_gross_labels_keep_method_stock_horizon_and_unknown_availability(pipeline):
    parent, outcome, _saved_result = _saved(pipeline)
    decision = _saved_result["projection"]["decision_date"]
    report = label_readiness.build_label_readiness(parent, outcome, _policy(), _split(decision))

    assert report["status"] == "research_only"
    assert report["label_policy"]["value"]["horizons"] == [5, 10, 20]
    assert report["label_policy"]["sha256"] == label_readiness._sha256(report["label_policy"]["value"])
    assert report["baseline_readiness"]["actual_return_binding"] == {
        "field": "actual_return_bp", "measure": "gross",
        "policy_sha256": report["label_policy"]["sha256"],
        "label_schema_sha256": report["label_policy"]["label_schema_sha256"],
        "horizons": [5, 10, 20],
    }
    assert report["split_policy"]["value"]["evaluation_start"] == decision
    rows = report["label_rows"]
    assert len(rows) == 18
    assert len({row["sample_id"] for row in rows}) == len(rows)
    assert len({row["comparison_group_id"] for row in rows}) == 9
    assert {row["horizon"] for row in rows} == {"H5", "H10", "H20"}
    assert all(row["split_role"] == "evaluation_window_research_only" for row in rows)
    assert all(row["selection_status"] == "unknown" for row in rows)
    assert all(row["quality"] == "research_only" for row in rows)
    assert any(row["value_bp"] is not None for row in rows)
    assert all(row["availability_status"] == "unknown" for row in rows)
    assert all("source_availability_unknown" in row["reason_codes"] for row in rows if row["value_bp"] is not None)
    assert report["label_denominators"]["availability_unknown"] == 18
    assert report["split_policy"]["status"] == "blocked_missing_temporal_partition_candidates"
    assert report["split_policy"]["evaluation_decision_dates"] == [decision]
    assert report["split_policy"]["train_decision_dates"] == []
    assert report["baseline_readiness"]["existing_adapter"] == "ml_module.drift_champion_comparison.MLChampionComparisonService"
    assert report["baseline_readiness"]["adapter_invoked"] is False
    assert "actual_downside_label_policy_and_value" in report["baseline_readiness"]["missing"]
    assert report["baseline_readiness"]["feature_registry_hash"] is None
    identity = report.pop("report_identity_sha256")
    assert identity == label_readiness._sha256(report)


@pytest.mark.parametrize(
    ("measure", "required_reason"),
    [
        ("net", "explicit_cost_policy_missing"),
        ("gross_excess", "explicit_benchmark_missing"),
        ("net_excess", "explicit_benchmark_missing"),
    ],
)
def test_missing_cost_or_benchmark_never_becomes_zero(pipeline, measure, required_reason):
    parent, outcome, _saved_result = _saved(pipeline)
    report = label_readiness.build_label_readiness(
        parent, outcome, _policy(measure, [5]), None)
    rows = report["label_rows"]
    assert len(rows) == 6
    assert all(row["value_bp"] is None for row in rows)
    measurable_rows = [row for row in rows if row["member_state"] != "excluded"]
    assert measurable_rows
    assert all(required_reason in row["reason_codes"] for row in measurable_rows)
    assert report["label_denominators"]["value_missing"] == 6
    assert report["training_eligible"] is False


@pytest.mark.parametrize(
    ("measure", "expected_bp"),
    [("gross", 396), ("net", 365), ("gross_excess", 196), ("net_excess", 165)],
)
def test_explicit_cost_and_qualified_benchmark_values_are_read_as_research_only(pipeline, measure, expected_bp):
    from tests.test_rule_research_benchmark_integration import _prepare

    _args, parent, _config, runtime, _benchmark_db = _prepare(pipeline)
    saved = run_forward_isolated(runtime, execute=True)
    assert saved["status"] == "saved", saved
    report = label_readiness.build_label_readiness(
        parent, saved["receipt_path"], _policy(measure, [5]), None)

    assert report["receipts"][0]["benchmark_source_status"] == "qualified_research"
    assert report["receipts"][0]["cost_policy"]["version"] == "fixture-cost-v2"
    rows = report["label_rows"]
    assert report["baseline_readiness"]["actual_return_binding"]["measure"] == measure
    assert any(row["value_bp"] == expected_bp for row in rows)
    assert all(row["quality"] == "research_only" for row in rows)
    assert report["training_eligible"] is False
    assert report["historical_pit_eligible"] is False


def test_synthetic_declared_availability_unit_boundary(pipeline, monkeypatch):
    parent, outcome, saved = _saved(pipeline)
    original = label_readiness.read_forward_receipt

    def fixture_availability(parent_receipt, outcome_receipt, *, cancel_callback=None):
        result = original(parent_receipt, outcome_receipt, cancel_callback=cancel_callback)
        result["source_contract"]["source_mode"] = "pinned_research_fixture"
        result["source_contract"]["source_availability"] = "declared_fixture_dates"
        for member in result["projection"]["members"]:
            for horizon in member["horizons"]:
                end = horizon["expected_end_date"]
                if end is None:
                    continue
                horizon["input_availability"] = {
                    "aggregate_available_date": end,
                    "as_of_status": "known_by_as_of",
                    "target": {"aggregate_available_date": end, "as_of_status": "known_by_as_of"},
                    "benchmark": None,
                }
        return result

    monkeypatch.setattr(label_readiness, "read_forward_receipt", fixture_availability)
    decision = saved["projection"]["decision_date"]
    split = _split(decision, include_decision_in="training")
    report = label_readiness.build_label_readiness(parent, outcome, _policy("gross", [5]), split)

    valued = [row for row in report["label_rows"] if row["value_bp"] is not None]
    assert valued
    assert all(row["historical_label"] is not None for row in valued)
    assert all(row["historical_label"]["quality"] == "research_only" for row in valued)
    assert all(row["temporal_train_candidate"] for row in valued)
    assert report["split_policy"]["status"] == "blocked_missing_temporal_partition_candidates"
    assert report["training_eligible"] is False
    assert report["historical_pit_eligible"] is False
    assert report["baseline_readiness"]["adapter_invoked"] is False


def test_unknown_calendar_endpoint_stays_missing_without_split_type_error(pipeline, monkeypatch):
    parent, outcome, saved = _saved(pipeline)
    original = label_readiness.read_forward_receipt

    def no_calendar_endpoint(parent_receipt, outcome_receipt, *, cancel_callback=None):
        result = original(parent_receipt, outcome_receipt, cancel_callback=cancel_callback)
        for member in result["projection"]["members"]:
            for horizon in member["horizons"]:
                horizon["expected_end_date"] = None
                horizon["maturity_status"] = "unknown"
                horizon["calculation_status"] = "unknown"
                horizon["input_availability"] = {
                    "aggregate_available_date": None, "as_of_status": "unknown", "target": None,
                    "benchmark": None,
                }
        return result

    monkeypatch.setattr(label_readiness, "read_forward_receipt", no_calendar_endpoint)
    decision = saved["projection"]["decision_date"]
    split = _split(decision, include_decision_in="training")
    report = label_readiness.build_label_readiness(parent, outcome, _policy("gross", [5]), split)

    assert len(report["label_rows"]) == 6
    assert all(row["value_bp"] is None for row in report["label_rows"])
    assert all("label_horizon_end_missing" in row["reason_codes"] for row in report["label_rows"])
    assert all(row["historical_label"] is None for row in report["label_rows"])
    assert report["split_policy"]["status"] == "blocked_missing_temporal_partition_candidates"


def test_invalid_sealed_availability_is_counted_and_cannot_become_training_candidate(pipeline, monkeypatch):
    parent, outcome, saved = _saved(pipeline)
    original = label_readiness.read_forward_receipt

    def invalid_availability(parent_receipt, outcome_receipt, *, cancel_callback=None):
        result = original(parent_receipt, outcome_receipt, cancel_callback=cancel_callback)
        horizon = result["projection"]["members"][0]["horizons"][0]
        horizon["input_availability"] = {
            "aggregate_available_date": "2026-99-99",
            "as_of_status": "known_by_as_of",
            "target": {"aggregate_available_date": "2026-99-99", "as_of_status": "known_by_as_of"},
            "benchmark": None,
        }
        return result

    monkeypatch.setattr(label_readiness, "read_forward_receipt", invalid_availability)
    decision = saved["projection"]["decision_date"]
    report = label_readiness.build_label_readiness(parent, outcome, _policy("gross", [5]), _split(decision))

    assert report["label_denominators"]["availability_invalid"] == 1
    assert report["label_denominators"]["availability_unknown"] == 5
    invalid = next(row for row in report["label_rows"] if "sealed_availability_date_invalid" in row["reason_codes"])
    assert invalid["value_bp"] is not None
    assert invalid["availability_status"] == "invalid"
    assert invalid["historical_label"] is None
    assert invalid["temporal_train_candidate"] is False
    assert report["baseline_readiness"]["label_available_date_evidence"]["status"] == "partial_research_only_dates"


def test_policy_and_split_validation_rejects_implicit_or_overlapping_config(pipeline):
    parent, outcome, saved = _saved(pipeline)
    decision = saved["projection"]["decision_date"]
    bad_policy = _policy("gross", [True])
    with pytest.raises(ValueError, match="label_horizons_invalid"):
        label_readiness.build_label_readiness(parent, outcome, bad_policy, None)

    split = _split(decision)
    split["train_end"] = decision
    with pytest.raises(ValueError, match="label_split_windows_overlap_or_invalid"):
        label_readiness.build_label_readiness(parent, outcome, _policy(), split)


def test_cancel_retry_duplicate_receipt_and_exact_reread_are_safe(pipeline, monkeypatch):
    args, _parent, _config, _runtime, *_ = pipeline
    parent, outcome, saved = _saved(pipeline)
    source_files = [parent, outcome, Path(args["db_path"])]
    before = {path: _hash(path) for path in source_files}
    cancelled = label_readiness.build_label_readiness(
        parent, outcome, _policy(), None, cancel_callback=lambda: True)
    assert cancelled["status"] == "cancelled"
    assert cancelled["receipts"] == []

    real_read = label_readiness.read_forward_receipt
    seen = [False]

    def cancel_after_read(parent_receipt, outcome_receipt, *, cancel_callback=None):
        result = real_read(parent_receipt, outcome_receipt, cancel_callback=cancel_callback)
        seen[0] = True
        return result

    monkeypatch.setattr(label_readiness, "read_forward_receipt", cancel_after_read)
    after_read = label_readiness.build_label_readiness(
        parent, outcome, _policy(), None, cancel_callback=lambda: seen[0])
    assert after_read["status"] == "cancelled"

    monkeypatch.setattr(label_readiness, "read_forward_receipt", real_read)
    decision = saved["projection"]["decision_date"]
    first = label_readiness.build_label_readiness(parent, outcome, _policy(), _split(decision))
    again = label_readiness.build_label_readiness(parent, outcome, _policy(), _split(decision))
    assert first == again
    assert first["receipts"][0]["outcome_capture_sha256"] == _hash(outcome.parent / "capture.json")
    identity = first.pop("report_identity_sha256")
    assert identity == label_readiness._sha256(first)
    first["report_identity_sha256"] = identity
    with pytest.raises(ValueError, match="label_duplicate_receipt_input"):
        label_readiness.build_label_readiness_batch(
            [(parent, outcome), (parent, outcome)], _policy(), _split(decision))
    assert {path: _hash(path) for path in source_files} == before


@pytest.mark.parametrize("boundary", ["available_after_cutoff", "end_reaches_evaluation"])
def test_synthetic_future_label_does_not_enter_training(pipeline, monkeypatch, boundary):
    parent, outcome, saved = _saved(pipeline)
    split = _split(saved["projection"]["decision_date"], include_decision_in="training")
    original = label_readiness.read_forward_receipt

    def declared_dates(*args, **kwargs):
        result = original(*args, **kwargs)
        result["source_contract"].update(source_mode="synthetic_unit_boundary",
                                         source_availability="declared_fixture_dates")
        for member in result["projection"]["members"]:
            horizon = member["horizons"][0]
            if boundary == "end_reaches_evaluation":
                horizon["expected_end_date"] = split["evaluation_start"]
            horizon.setdefault("input_availability", {})["target"] = {
                "aggregate_available_date": split["evaluation_start"],
                "as_of_status": "known_by_as_of"}
        return result

    monkeypatch.setattr(label_readiness, "read_forward_receipt", declared_dates)
    report = label_readiness.build_label_readiness(parent, outcome, _policy("gross", [5]), split)
    valued = [row for row in report["label_rows"] if row["value_bp"] is not None]
    assert valued and all(row["historical_label"] is not None for row in valued)
    assert all(row["temporal_train_candidate"] is False for row in valued)
    reason = ("training_label_reaches_evaluation_window" if boundary == "end_reaches_evaluation"
              else "label_not_mature_by_training_as_of")
    assert all(reason in row["reason_codes"] for row in valued)
    assert report["training_eligible"] is False


def test_synthetic_evaluation_labels_never_enter_training(pipeline, monkeypatch):
    parent, outcome, saved = _saved(pipeline)
    original = label_readiness.read_forward_receipt

    def declared_dates(*args, **kwargs):
        result = original(*args, **kwargs)
        result["source_contract"].update(source_mode="synthetic_unit_boundary",
                                         source_availability="declared_fixture_dates")
        for member in result["projection"]["members"]:
            horizon = member["horizons"][0]
            horizon.setdefault("input_availability", {})["target"] = {
                "aggregate_available_date": horizon["expected_end_date"],
                "as_of_status": "known_by_as_of"}
        return result

    monkeypatch.setattr(label_readiness, "read_forward_receipt", declared_dates)
    report = label_readiness.build_label_readiness(parent, outcome, _policy("gross", [5]),
        _split(saved["projection"]["decision_date"]))
    valued = [row for row in report["label_rows"] if row["value_bp"] is not None]
    assert valued and all(row["evaluation_candidate"] for row in valued)
    assert all(row["split_role"] == "evaluation_window_research_only" for row in valued)
    assert all(row["temporal_train_candidate"] is False for row in valued)
    assert report["split_policy"]["evaluation_rows_enter_training"] is False


@pytest.mark.parametrize(("bound", "reason"), [
    ("MAX_LABEL_ROWS", "label_sample_row_bound"),
    ("MAX_REPORT_BYTES", "label_report_byte_bound"),
])
def test_bounded_report_is_rejected_whole_without_changing_saved_receipts(pipeline, monkeypatch, bound, reason):
    parent, outcome, _ = _saved(pipeline)
    before = {path: _hash(path) for path in (parent, outcome, outcome.parent / "capture.json")}
    monkeypatch.setattr(label_readiness, bound, 1)
    with pytest.raises(ValueError, match=reason):
        label_readiness.build_label_readiness(parent, outcome, _policy("gross", [5]), None)
    assert {path: _hash(path) for path in before} == before
