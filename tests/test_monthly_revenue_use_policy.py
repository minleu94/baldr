"""全用途授權不能取代單位、來源用途、歷史 PIT 或下游 Gate。"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from data_module.monthly_revenue_use_policy import (
    MonthlyRevenueQualificationEvidence, MonthlyRevenueUse,
    evaluate_monthly_revenue_use,
)

NOW = datetime(2026, 10, 22, 0, tzinfo=timezone.utc)


def evidence() -> MonthlyRevenueQualificationEvidence:
    return MonthlyRevenueQualificationEvidence(
        source_id="twse.openapi.t187ap05_L",
        endpoint_url="https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
        batch_sha256="a" * 64, available_at=NOW,
        license_evidence_ref="fixture:license-raw-sha",
    )


@pytest.mark.parametrize("purpose", list(MonthlyRevenueUse))
def test_all_uses_authorized_but_not_automatically_qualified(purpose):
    decision = evaluate_monthly_revenue_use(purpose, evidence=evidence(), cutoff_at=NOW)
    assert decision.owner_authorized
    assert not decision.allowed
    assert "verified_amount_unit_proof_missing" in decision.reasons
    assert "source_use_qualification_missing" in decision.reasons


def test_verified_reported_percentage_does_not_convert_unknown_amount():
    source = replace(evidence(), source_accepted_uses=("current_research",),
                     acceptance_evidence_ref="fixture:reviewed-percentage-scope")
    assert evaluate_monthly_revenue_use("current_research", evidence=source,
                                       cutoff_at=NOW, value_kind="reported_percentage").allowed
    assert not evaluate_monthly_revenue_use("current_research", evidence=source,
                                           cutoff_at=NOW).allowed


@pytest.mark.parametrize("purpose", ["backtest", "ml_training", "ml_validation"])
def test_first_observed_is_not_official_pit(purpose):
    source = replace(evidence(), unit_proof_sha256="b" * 64,
                     source_accepted_uses=(purpose,), acceptance_evidence_ref="fixture:accepted",
                     downstream_evidence_refs=((purpose, "fixture:downstream"),))
    decision = evaluate_monthly_revenue_use(purpose, evidence=source, cutoff_at=NOW)
    assert decision.reasons == ("official_pit_revision_evidence_missing",)


def test_historical_research_not_restricted_to_current_only():
    source = replace(evidence(), source_accepted_uses=("historical_research",),
                     acceptance_evidence_ref="fixture:accepted")
    decision = evaluate_monthly_revenue_use("historical_research", evidence=source,
                                           cutoff_at=NOW, value_kind="reported_percentage", historical=True)
    assert decision.allowed


def test_paper_and_forward_keep_independent_gates():
    for purpose in ("paper", "forward"):
        source = replace(evidence(), unit_proof_sha256="b" * 64,
                         source_accepted_uses=(purpose,), acceptance_evidence_ref="fixture:accepted")
        decision = evaluate_monthly_revenue_use(purpose, evidence=source, cutoff_at=NOW)
        assert decision.reasons == ("downstream_use_gate_missing:" + purpose,)


def test_future_source_and_new_provider_not_authorized():
    source = replace(evidence(), source_id="paid.vendor", available_at=NOW + timedelta(seconds=1))
    decision = evaluate_monthly_revenue_use("current_research", evidence=source, cutoff_at=NOW)
    assert not decision.owner_authorized
    assert "source_outside_named_owner_authorization" in decision.reasons
    assert "source_not_available_at_cutoff" in decision.reasons


def test_missing_license_and_naive_clock_fail_closed():
    source = replace(evidence(), license_evidence_ref="")
    assert "license_evidence_missing" in evaluate_monthly_revenue_use(
        "current_research", evidence=source, cutoff_at=NOW).reasons
    with pytest.raises(ValueError, match="aware"):
        evaluate_monthly_revenue_use("current_research", evidence=source, cutoff_at=NOW.replace(tzinfo=None))
