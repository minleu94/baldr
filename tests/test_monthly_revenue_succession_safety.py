"""接任增量的原件重播、尺度範圍與截面身份回歸。"""

from dataclasses import replace
from datetime import date
from decimal import Decimal
import hashlib

import pytest

from data_module.monthly_revenue_unit_scale_proof import (
    MonthlyRevenueUnitScaleProofError,
    build_mops_monthly_revenue_period_scale_proof,
    build_openapi_mops_cross_source_parity_proof,
    read_mops_monthly_revenue_period_scale_proof,
    write_mops_monthly_revenue_period_scale_proof_create_only,
)
from tests.test_mops_monthly_revenue_history import _capture
from tests.test_monthly_revenue_unit_scale_proof import _table
from tests.test_monthly_revenue_research_service import (
    CUTOFF, _batch, _evidence, _service,
)


def _history(period="2026-07"):
    month = int(period[-2:])
    table = _table("半導體業", "2330")
    for old, new in (("90", "9"), ("80", "8"), ("600", "30"), ("500", "25")):
        table = table.replace(f"<td>{old}</td>", f"<td>{new}</td>")
    html = (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>'
        f"<h1>上市公司115年{month}月份月營業收入彙總表</h1>"
        "<p>出表日期：115/10/23</p>" + table + "</body></html>"
    ).encode("utf-8")
    return _capture(market="twse", period=period, html=html)


def test_period_proof_roundtrip_external_pin_and_create_only(tmp_path):
    cap = _history()
    proof = build_mops_monthly_revenue_period_scale_proof(cap)
    path = tmp_path / "july.scale.json"
    write_mops_monthly_revenue_period_scale_proof_create_only(path, cap)
    result = read_mops_monthly_revenue_period_scale_proof(
        path, expected_sha256=proof.proof_sha256, capture=cap,
    )
    assert result["period"] == "2026-07"
    assert result["currency"] == "unknown"
    assert result["financial_qualification_created"] is False
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="conflict"):
        write_mops_monthly_revenue_period_scale_proof_create_only(path, cap)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="sha256_mismatch"):
        read_mops_monthly_revenue_period_scale_proof(
            path, expected_sha256=proof.proof_sha256, capture=cap,
        )
    forged_pin = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="not_bound_to_capture"):
        read_mops_monthly_revenue_period_scale_proof(
            path, expected_sha256=forged_pin, capture=cap,
        )


def test_parity_raw_replay_and_explicit_common_scope():
    batch = _batch(period="2026-07", amount="100", extra_codes=("2317",))
    result = build_openapi_mops_cross_source_parity_proof(batch, _history())
    assert result["exact_amount_match_stock_count"] == 1
    assert result["compared_stock_codes"] == ["2330"]
    assert result["openapi_only_stock_codes"] == ["2317"]
    assert result["unmatched_rows_unit_verified"] is False
    assert result["historical_pit_eligible"] is False
    changed = replace(batch.rows[0], amount_values_source_unit=(
        ("營業收入-當月營收", Decimal("101")),
    ))
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="raw_revalidation"):
        build_openapi_mops_cross_source_parity_proof(
            replace(batch, rows=(changed, *batch.rows[1:])), _history(),
        )
    with pytest.raises(MonthlyRevenueUnitScaleProofError):
        build_openapi_mops_cross_source_parity_proof(
            replace(batch, rows=(*batch.rows, batch.rows[0])), _history(),
        )


def _fact(*, code="2330", period="2026-09", metric="revenue_yoy_percent"):
    batch = _batch(code=code, period=period)
    evidence = _evidence(
        batch, ("factor_research", "scoring"), downstream=(("scoring", "fixture:gate"),),
    )
    return _service().current_openapi_fact(
        batch, stock_code=code, metric=metric, evidence=evidence, cutoff_at=CUTOFF,
    )


@pytest.mark.parametrize("other", [
    {"metric": "revenue_mom_percent"},
    {"metric": "revenue_amount_twd"},
    {"period": "2026-08"}, {},
])
def test_scoring_rejects_mixed_dimensions_and_duplicate_stock(other):
    first = _fact()
    second = _fact(**other)
    with pytest.raises(ValueError, match="single_factor_period_unit|duplicate_stock"):
        _service().project_scoring_ranking_candidates(
            (first, second), decision_date=date(2026, 10, 22), cutoff_at=CUTOFF,
        )


def test_scoring_single_coherent_cross_section():
    result = _service().project_scoring_ranking_candidates(
        (_fact(), _fact(code="2317")),
        decision_date=date(2026, 10, 22), cutoff_at=CUTOFF,
    )
    assert result.allowed
    assert len(result.qualified_records) == 2
