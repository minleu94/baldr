from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from app_module.rule_research_fair_comparison import build_fair_comparison
from app_module.rule_research_label_readiness import build_label_readiness_batch
from app_module.rule_research_shadow_acceptance import (
    _AcceptanceCaptureWriter,
    _validate_report,
    build_shadow_acceptance,
    read_shadow_acceptance,
    save_shadow_acceptance,
)
from app_module.rule_research_sample_capture import RuleSampleCaptureError
from tests.test_rule_research_fair_comparison import _bundle_for, _prepared
from tests.test_rule_research_forward_isolated import pipeline
from tests.test_rule_research_label_readiness import _saved


def _inputs(pipeline):
    receipts, labels, split, comparison_policy = _prepared(pipeline)
    labels_report = build_label_readiness_batch(receipts, labels, split)
    bundle = _bundle_for(labels_report, comparison_policy)
    fair = build_fair_comparison(receipts, labels, split, comparison_policy, bundle)
    assert fair["status"] == "research_only_comparison"
    model_pin = fair["candidate"]["model_pin"]
    return receipts, labels, split, comparison_policy, bundle, model_pin


def _lifecycle(model_pin, events=None):
    return {
        "schema_version": "rule-research-shadow-lifecycle-export.v1",
        "model_id": model_pin["model_id"],
        "dataset_id": model_pin["dataset_id"],
        "artifact_hash": model_pin["artifact_hash"],
        "events": [] if events is None else events,
        "metadata": dict(model_pin),
    }


def _event(model_pin, kind, created_at=None):
    return {
        "event_id": f"event-{kind}",
        "model_id": model_pin["model_id"],
        "event_type": kind,
        "created_at": created_at or (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        "reason": "synthetic lifecycle export for isolated research review",
    }


def _build(inputs, *, lifecycle=None, **kwargs):
    receipts, labels, split, policy, bundle, _pin = inputs
    return build_shadow_acceptance(
        receipts, case_id="ux23-test-case", label_policy=labels, split_policy=split,
        comparison_policy=policy, bundle=bundle, lifecycle_export=lifecycle, **kwargs,
    )


def test_valid_export_is_research_engineering_only_and_three_axes_stay_closed(pipeline):
    inputs = _inputs(pipeline)
    report = _build(inputs, lifecycle=_lifecycle(inputs[-1]))

    assert report["status"] == "shadow_engineering_executable_research_only"
    assert report["engineering_status"] == "shadow_engineering_executable"
    assert report["data_effect_status"] == "not_qualified_research_only"
    assert report["activation_status"] == "not_enabled"
    assert report["comparison"]["common_cohort_count"] == 2
    assert "member_ledger" not in report["comparison"]
    assert report["lifecycle"]["status"] == "validated"
    assert report["safety_flags"] == {
        "research_only": True, "shadow_enabled": False, "production_enabled": False,
        "formal_eligible": False, "production_action_allowed": False,
        "formal_rule_unchanged": True, "training_eligible": False,
        "historical_pit_eligible": False, "natural_authority": False,
        "execution_eligible": False, "production_blend_alpha_bp": 0,
        "selection_status": "unknown", "qualified_count": 0,
    }
    assert "工程軸" in report["summary_text"] and "資料／效果軸" in report["summary_text"]
    assert "啟用軸" in report["summary_text"]


def test_missing_candidate_and_invalid_lifecycle_fall_back_without_qualification(pipeline):
    inputs = _inputs(pipeline)
    receipts, labels, split, policy, bundle, pin = inputs
    candidate_payload = deepcopy(bundle["candidate"])
    bundle["candidate"] = None
    missing = build_shadow_acceptance(
        receipts, case_id="missing-candidate", label_policy=labels, split_policy=split,
        comparison_policy=policy, bundle=bundle,
        lifecycle_export=_lifecycle(pin),
    )
    assert missing["status"] == "rule_only_fallback"
    assert missing["comparison"]["status"] == "not_comparable_missing_candidate"
    assert missing["comparison"]["candidate"] is None
    assert missing["safety_flags"]["qualified_count"] == 0

    invalid = _build(inputs, lifecycle={**_lifecycle(pin), "schema_version": "future.v2"})
    assert invalid["status"] == "rule_only_fallback"
    assert invalid["lifecycle"]["status"] == "invalid"
    bundle["candidate"] = candidate_payload


@pytest.mark.parametrize("events", [
    [_event({"model_id": "test"}, "disabled")],
    [_event({"model_id": "test"}, "activated_for_shadow"),
     _event({"model_id": "test"}, "review_required")],
])
def test_lifecycle_bad_chain_or_nonprojectable_state_falls_back(pipeline, events):
    inputs = _inputs(pipeline)
    pin = inputs[-1]
    fixed_events = [{**event, "model_id": pin["model_id"]} for event in events]
    report = _build(inputs, lifecycle=_lifecycle(pin, fixed_events))
    assert report["status"] == "rule_only_fallback"
    assert report["lifecycle"]["status"] in {"invalid", "stopped"}
    assert report["safety_flags"]["shadow_enabled"] is False


def test_explicit_stop_still_validates_comparison_and_lifecycle(pipeline):
    inputs = _inputs(pipeline)
    report = _build(inputs, lifecycle=_lifecycle(inputs[-1]), stop_reason="operator pause")
    assert report["status"] == "stopped"
    assert report["comparison"]["status"] == "research_only_comparison"
    assert report["lifecycle"]["status"] == "validated"
    assert report["diagnostics"]["stop_reason"] == "operator pause"
    assert report["safety_flags"]["shadow_enabled"] is False


@pytest.mark.parametrize("callback", [lambda: True, lambda: (_ for _ in ()).throw(RuntimeError("cancel probe"))])
def test_cancelled_report_has_no_partial_comparison_and_is_not_publishable(pipeline, tmp_path, callback):
    inputs = _inputs(pipeline)
    report = _build(inputs, lifecycle=_lifecycle(inputs[-1]), cancel_callback=callback)
    assert report["status"] == "cancelled"
    assert report["comparison"]["baseline"] is None
    assert report["comparison"]["candidate"] is None
    with pytest.raises(RuleSampleCaptureError, match="cancelled_report_not_publishable"):
        save_shadow_acceptance(report, tmp_path / "cancelled", revalidate=lambda: report)


def test_callback_error_in_comparison_falls_back_and_retry_is_deterministic(pipeline, monkeypatch):
    inputs = _inputs(pipeline)
    calls = 0

    def raises_midflight():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("cancel probe")
        return False

    report = _build(inputs, lifecycle=_lifecycle(inputs[-1]), cancel_callback=raises_midflight)
    assert report["status"] == "cancelled"
    retry = _build(inputs, lifecycle=_lifecycle(inputs[-1]))
    retry_again = _build(inputs, lifecycle=_lifecycle(inputs[-1]))
    assert retry["capture_identity_sha256"] == retry_again["capture_identity_sha256"]


def test_save_revalidate_exact_read_and_tamper_rejection(pipeline, tmp_path, monkeypatch):
    inputs = _inputs(pipeline)
    report = _build(inputs, lifecycle=_lifecycle(inputs[-1]))
    monkeypatch.setattr(_AcceptanceCaptureWriter, "_free_bytes", lambda self: 10**12)
    store = tmp_path / "ux23-captures"
    saved = save_shadow_acceptance(report, store, revalidate=lambda: report)
    identity = saved["receipt"]["capture_identity_sha256"]
    reopened = read_shadow_acceptance(store, identity)
    assert reopened["capture"]["capture_identity_sha256"] == identity
    assert reopened["capture"]["status"] == report["status"]
    assert saved["status"] == "published"

    capture_path = Path(saved["directory"]) / "capture.json"
    raw = json.loads(capture_path.read_text(encoding="utf-8"))
    raw["safety_flags"]["shadow_enabled"] = True
    capture_path.write_text(json.dumps(raw, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")), encoding="utf-8")
    with pytest.raises(RuleSampleCaptureError):
        read_shadow_acceptance(store, identity)


def test_revalidation_revision_is_rejected_and_failed_write_leaves_no_success_receipt(pipeline, tmp_path,
                                                                                      monkeypatch):
    inputs = _inputs(pipeline)
    report = _build(inputs, lifecycle=_lifecycle(inputs[-1]))
    monkeypatch.setattr(_AcceptanceCaptureWriter, "_free_bytes", lambda self: 10**12)
    changed = deepcopy(report)
    changed["case_id"] = "changed-between-preview-and-save"
    changed.pop("capture_identity_sha256")
    # Re-seal through the documented identity contract to ensure the writer
    # rejects a coherent but different recomputation, not just a malformed one.
    import hashlib

    unsigned = {key: value for key, value in changed.items()
                if key not in {"capture_identity_sha256", "observed_at"}}
    changed["capture_identity_sha256"] = hashlib.sha256(json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    store = tmp_path / "ux23-revision"
    with pytest.raises(RuleSampleCaptureError, match="source_revision_during_capture"):
        save_shadow_acceptance(report, store, revalidate=lambda: changed)
    assert not list(store.glob("*/receipt.json"))


def test_source_pin_changes_acceptance_identity_even_on_fallback(pipeline):
    parent, outcome, _ = _saved(pipeline)
    first = build_shadow_acceptance(
        [(parent, outcome)], case_id="source-pinned-fallback", label_policy=None,
        split_policy=None,
    )
    other = build_shadow_acceptance(
        [(parent, Path(outcome).with_name("different-outcome-receipt.json"))],
        case_id="source-pinned-fallback", label_policy=None, split_policy=None,
    )
    assert first["status"] == other["status"] == "rule_only_fallback"
    assert first["capture_identity_sha256"] != other["capture_identity_sha256"]


def test_bounded_receipts_and_json_context_are_explicitly_rejected(pipeline):
    parent, outcome, _ = _saved(pipeline)
    pair = (parent, outcome)
    with pytest.raises(ValueError, match="shadow_receipt_count_bound"):
        build_shadow_acceptance([pair] * 33, case_id="too-many", label_policy=None,
                                split_policy=None)
    with pytest.raises(ValueError, match="shadow_input_context_not_json"):
        build_shadow_acceptance([pair], case_id="not-json", label_policy=None,
                                split_policy=None, bundle={"bad": object()})


def test_rehashed_flag_type_or_lifecycle_state_tampering_is_rejected(pipeline):
    inputs = _inputs(pipeline)
    report = _build(inputs, lifecycle=_lifecycle(inputs[-1]))

    def reseal(value):
        import hashlib

        unsigned = {key: item for key, item in value.items()
                    if key not in {"capture_identity_sha256", "observed_at"}}
        value["capture_identity_sha256"] = hashlib.sha256(json.dumps(
            unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        return value

    wrong_flag_type = deepcopy(report)
    wrong_flag_type["safety_flags"]["qualified_count"] = False
    with pytest.raises(ValueError, match="acceptance_safety_flags_invalid"):
        _validate_report(reseal(wrong_flag_type))

    wrong_lifecycle_state = deepcopy(report)
    wrong_lifecycle_state["lifecycle"]["current_status"] = "disabled"
    wrong_lifecycle_state["lifecycle"]["event_count"] = 1
    with pytest.raises(ValueError, match="acceptance_lifecycle_projection_state_invalid"):
        _validate_report(reseal(wrong_lifecycle_state))
