"""MA 研究樣本的唯讀就緒投影；完整控制組不授 PIT／訓練資格。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter, RuleResearchCapture, RuleSampleCaptureError,
    read_rule_research_capture,
)


def project_rule_sample_readiness(capture: RuleResearchCapture, *, saved: bool = False) -> dict[str, Any]:
    """只呈現完整已聲明單批；不推算日曆、成熟標籤或全市場母體。"""
    body = capture.to_dict()
    return {
        "status": "saved_verified" if saved else "projection_only",
        "capture_identity_sha256": body["capture_identity_sha256"],
        "decision_date": body["decision_date"], "as_of": body["as_of"],
        "cohort_id": body["cohort_id"], "snapshot_sha256": body["snapshot_sha256"],
        "completeness": body["completeness"],
        "included_denominator": body["included_denominator"],
        "represented_denominator": body["represented_denominator"],
        "population_count": body["population_count"],
        "population_status": body["population_status"],
        "method_counts": body["method_counts"],
        "selected_count": 0, "selection_status": "unknown",
        "source_availability": "unknown", "market_calendar": "unknown",
        "outcome_maturity": "unknown", "mature_outcomes": None,
        "historical_pit_eligible": False, "natural_authority": False,
        "formal_eligible": False, "training_eligible": False,
        "batch_status": "single_bounded_batch_no_parent_manifest",
        "max_included_per_batch": 16,
    }


def read_saved_rule_sample_readiness(
    writer: BoundedRuleResearchCaptureWriter, repository: DailyMarketSnapshotRepository, *,
    identity_sha256: str, manifest_sha256: str, cohort_id: str, decision_date: date,
    as_of: datetime,
) -> dict[str, Any]:
    """驗 receipt 後重讀明示 source pin；不接受 latest 或不同母體／時點。"""
    package = writer.read(identity_sha256)
    body = package["capture"]
    source = read_rule_research_capture(repository, manifest_sha256=manifest_sha256,
        cohort_id=cohort_id, decision_date=decision_date, as_of=as_of,
        observed_at=datetime.fromisoformat(body["observed_at"]))
    if source.identity_sha256 != identity_sha256:
        raise RuleSampleCaptureError("saved_source_binding_mismatch")
    result = project_rule_sample_readiness(source, saved=True)
    result["receipt"] = package["receipt"]
    return result
