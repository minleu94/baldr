"""隔離 adapter 在執行失敗、容量不足及殘件時不能發布或清除證據。"""
from pathlib import Path

import pytest

from app_module.rule_research_sample_capture import BoundedRuleResearchCaptureWriter, RuleSampleCaptureError
from app_module.rule_research_shadow_acceptance import build_shadow_acceptance, save_shadow_acceptance
from tests.test_rule_research_forward_isolated import pipeline
from tests.test_rule_research_label_readiness import _saved


def _missing_report(pipeline):
    parent, outcome, _ = _saved(pipeline)
    return build_shadow_acceptance([(parent, outcome)], case_id="safety-fallback",
                                   label_policy=None, split_policy=None)


def test_comparison_execution_error_falls_back_without_partial_metrics(pipeline, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("isolated comparison unavailable")
    monkeypatch.setattr("app_module.rule_research_shadow_acceptance.build_fair_comparison", fail)
    report = _missing_report(pipeline)
    assert report["status"] == "rule_only_fallback"
    assert report["comparison"]["status"] == "comparison_failed"
    assert report["comparison"]["baseline"] is None
    assert report["comparison"]["candidate"] is None
    assert report["safety_flags"]["shadow_enabled"] is False
    assert report["safety_flags"]["qualified_count"] == 0


def test_capacity_refusal_does_not_publish_or_leave_partial(pipeline, tmp_path, monkeypatch):
    report = _missing_report(pipeline)
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter, "_free_bytes", lambda self: 0)
    store = tmp_path / "no-capacity"
    with pytest.raises(RuleSampleCaptureError, match="capacity_reserve"):
        save_shadow_acceptance(report, store, revalidate=lambda: report)
    assert list(store.iterdir()) == []


def test_existing_partial_is_retained_and_blocks_retry(pipeline, tmp_path, monkeypatch):
    report = _missing_report(pipeline)
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter, "_free_bytes", lambda self: 10**12)
    store = tmp_path / "retained-evidence"
    partial = store / ".partial-owned-fixture"
    partial.mkdir(parents=True)
    evidence = partial / "capture.json"
    evidence.write_bytes(b"incomplete fixture evidence")
    before = evidence.read_bytes()
    with pytest.raises(RuleSampleCaptureError, match="store_unknown_or_partial_entry"):
        save_shadow_acceptance(report, store, revalidate=lambda: report)
    assert evidence.read_bytes() == before
    assert not list(store.glob("*/receipt.json"))
    assert not (store / ".writer.lock").exists()
