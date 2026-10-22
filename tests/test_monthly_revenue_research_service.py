"""月營收應用層 facade 的隔離契約測試，不構成來源或金融接受。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json

import pytest

import app_module.monthly_revenue_research_service as research_service_module
from app_module.monthly_revenue_research_service import (
    MonthlyRevenueResearchService,
    QualifiedMonthlyRevenueAmount,
)
import data_module.monthly_revenue_revision_archive as revision_archive_module
from data_module.monthly_revenue_revision_archive import (
    append_monthly_revenue_batch,
    raw_batch_from_openapi,
    read_monthly_revenue_revision_archive,
)
from data_module.monthly_revenue_use_policy import MonthlyRevenueQualificationEvidence
from data_module.opendata_monthly_revenue import (
    OPENAPI_MONTHLY_REVENUE_ENDPOINTS,
    OPENAPI_MONTHLY_REVENUE_SOURCE_IDS,
    OpenApiMonthlyRevenueCapture,
    OpenApiMonthlyRevenueUnitProof,
    build_openapi_unit_field_map_bytes,
    prepare_openapi_monthly_revenue_batch,
)


CAPTURED_AT = datetime(2026, 10, 21, 7, 15, tzinfo=timezone.utc)
CUTOFF = datetime(2026, 10, 22, 0, tzinfo=timezone.utc)


def _batch(*, market: str = "twse", code: str = "2330", yoy: str = "12.5", mom: str = "3.0", amount: str = "10", period: str = "2026-09", captured_at=CAPTURED_AT, extra_codes: tuple[str, ...] = ()):
    year_text, month_text = period.split("-")
    roc_period = f"{int(year_text) - 1911:03d}{int(month_text):02d}"
    first_row = {
        "資料年月": roc_period,
        "公司代號": code,
        "公司名稱": "隔離測試公司",
        "營業收入-當月營收": amount,
        "營業收入-上月營收": "9",
        "營業收入-去年當月營收": "8",
        "營業收入-上月比較增減(%)": mom,
        "營業收入-去年同月增減(%)": yoy,
        "累計營業收入-當月累計營收": "30",
        "累計營業收入-去年累計營收": "25",
        "累計營業收入-前期比較增減(%)": "20",
        "出表日期": "1151010",
        "備註": "隔離fixture，不代表官方接受",
        "產業別": "測試業",
    }
    rows = [first_row, *(
        {**first_row, "公司代號": extra_code} for extra_code in extra_codes
    )]
    body = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    endpoint = OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market]
    capture = OpenApiMonthlyRevenueCapture(
        market=market,
        requested_url=endpoint,
        response_url=endpoint,
        response_status=200,
        content_type_original_text="application/json; charset=utf-8",
        content_encoding_original_text="identity",
        content_length_original_text=str(len(body)),
        response_body_complete=True,
        eof_observed=True,
        received_body_bytes=len(body),
        body_observation_ended_at=captured_at,
        body_completed_at=captured_at,
        raw_response_bytes=body,
    )
    return prepare_openapi_monthly_revenue_batch(
        capture=capture,
        successful_batch_completed_at=captured_at,
    )


def _evidence(batch, uses, *, unit_proof_sha256=None, downstream=(), pit=False):
    return MonthlyRevenueQualificationEvidence(
        source_id=batch.capture.source_id,
        endpoint_url=batch.capture.requested_url,
        batch_sha256=batch.capture.raw_response_sha256,
        available_at=batch.available_hour,
        license_evidence_ref="fixture:license-and-attribution-reference",
        unit_proof_sha256=unit_proof_sha256,
        source_accepted_uses=tuple(uses),
        acceptance_evidence_ref="fixture:explicit-purpose-acceptance",
        downstream_evidence_refs=tuple(downstream),
        source_available_at=(batch.successful_batch_completed_at if pit else None),
        captured_at=batch.successful_batch_completed_at,
        availability_basis="official_announcement" if pit else "captured_observation",
        official_pit_evidence_ref="fixture:official-row-pit-reference" if pit else "",
    )


def _service():
    """只供全合成fixture使用；不代表真實registry接受或來源資格。"""
    return MonthlyRevenueResearchService(qualification_verifier=lambda evidence, cutoff_at: True)


def _unit_proof(market="twse"):
    document = f"隔離fixture單位文件：{market}，仟元；不是官方接受證據".encode("utf-8")
    document_sha256 = hashlib.sha256(document).hexdigest()
    dataset_id = "18420" if market == "twse" else "56510"
    field_map = build_openapi_unit_field_map_bytes(
        market=market,
        official_document_url=f"https://data.gov.tw/dataset/{dataset_id}",
        official_document_sha256=document_sha256,
    )
    return OpenApiMonthlyRevenueUnitProof(
        market=market,
        source_id=OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[market],
        endpoint_url=OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market],
        official_document_url=f"https://data.gov.tw/dataset/{dataset_id}",
        official_document_bytes=document,
        official_document_sha256=document_sha256,
        field_map_bytes=field_map,
        field_map_sha256=hashlib.sha256(field_map).hexdigest(),
        trusted_evidence_scope_id="fixture:exact-unit-field-map",
        source_unit_original_text="仟元",
        conversion_to_twd=Decimal("1000"),
    )


def test_current_percentage_is_direct_and_unknown_amount_never_becomes_zero():
    batch = _batch()
    evidence = _evidence(batch, ("factor_research", "screening", "comparison"))
    service = _service()

    yoy = service.current_openapi_fact(
        batch, stock_code="2330", metric="revenue_yoy_percent",
        evidence=evidence, cutoff_at=CUTOFF,
    )
    amount = service.current_openapi_fact(
        batch, stock_code="2330", metric="revenue_amount_twd",
        evidence=evidence, cutoff_at=CUTOFF,
    )

    assert yoy.value == Decimal("12.5")
    assert yoy.value_kind == "reported_percentage"
    assert yoy.unit == "%"
    assert yoy.allowed
    assert amount.value is None
    assert amount.missing_reason == "verified_amount_unit_proof_missing_or_mismatch"
    assert not amount.decision.allowed


def test_current_openapi_batch_projection_reparses_and_verifies_once(monkeypatch):
    batch = _batch(extra_codes=("2317", "2454"))
    evidence = _evidence(batch, ("factor_research", "screening", "sector_theme"))
    calls = {"prepare": 0, "verify": 0}
    original_prepare = research_service_module.prepare_openapi_monthly_revenue_batch

    def count_prepare(**kwargs):
        calls["prepare"] += 1
        return original_prepare(**kwargs)

    def count_verify(candidate, cutoff_at):
        calls["verify"] += 1
        return candidate is evidence and cutoff_at == CUTOFF

    monkeypatch.setattr(
        research_service_module,
        "prepare_openapi_monthly_revenue_batch",
        count_prepare,
    )
    service = MonthlyRevenueResearchService(qualification_verifier=count_verify)
    facts = service.current_openapi_facts(
        batch,
        metric="revenue_yoy_percent",
        evidence=evidence,
        cutoff_at=CUTOFF,
        stock_codes=None,
    )

    assert len(facts) == len(batch.rows)
    assert tuple(fact.stock_code for fact in facts) == tuple(row.stock_code for row in batch.rows)
    assert all(fact.value == Decimal("12.5") and fact.allowed for fact in facts)
    assert calls == {"prepare": 1, "verify": 1}

    facts_for_screen = service.current_openapi_facts(
        batch,
        metric="revenue_yoy_percent",
        evidence=evidence,
        cutoff_at=CUTOFF,
        stock_codes=None,
    )
    before_screen = calls["verify"]
    screened = service.screen_minimum(
        facts_for_screen, minimum=Decimal("10"), cutoff_at=CUTOFF
    )
    assert len(screened.matched) == len(facts_for_screen)
    assert calls["verify"] - before_screen == 1

    before_shadow = calls["verify"]
    snapshot = service.sector_theme_shadow_snapshot(
        facts_for_screen,
        decision_date=CUTOFF.date(),
        cutoff_at=CUTOFF,
        universe_id="isolated-batch-fixture",
    )
    assert snapshot.row_count == len(facts_for_screen)
    assert calls["verify"] - before_shadow == 1


def test_missing_trusted_qualification_resolver_fails_closed():
    batch = _batch()
    evidence = _evidence(batch, ("factor_research",))
    fact = MonthlyRevenueResearchService().current_openapi_fact(
        batch, stock_code="2330", metric="revenue_yoy_percent",
        evidence=evidence, cutoff_at=CUTOFF,
    )
    assert fact.value == Decimal("12.5")
    assert not fact.allowed
    assert "trusted_qualification_resolver_missing" in fact.decision.reasons


def test_unverified_qualification_fails_closed_and_receives_decision_cutoff():
    batch = _batch()
    evidence = _evidence(batch, ("factor_research",))
    calls = []

    def reject_fixture_evidence(candidate, cutoff_at):
        calls.append((candidate, cutoff_at))
        return False

    fact = MonthlyRevenueResearchService(
        qualification_verifier=reject_fixture_evidence,
    ).current_openapi_fact(
        batch, stock_code="2330", metric="revenue_yoy_percent",
        evidence=evidence, cutoff_at=CUTOFF,
    )
    assert calls == [(evidence, CUTOFF)]
    assert fact.value == Decimal("12.5")
    assert not fact.allowed
    assert "trusted_qualification_evidence_unverified" in fact.decision.reasons


def test_evidence_must_bind_the_exact_batch_and_unknown_screen_rows_do_not_pass():
    batch = _batch()
    evidence = _evidence(batch, ("factor_research", "screening"))
    service = _service()
    with pytest.raises(ValueError, match="does_not_match_openapi_batch"):
        service.current_openapi_fact(
            batch, stock_code="2330", metric="revenue_yoy_percent",
            evidence=MonthlyRevenueQualificationEvidence(
                source_id=evidence.source_id,
                endpoint_url=evidence.endpoint_url,
                batch_sha256="f" * 64,
                available_at=evidence.available_at,
                license_evidence_ref="fixture:license",
            ),
            cutoff_at=CUTOFF,
        )

    missing_batch = _batch(code="2317", yoy="")
    missing_evidence = _evidence(missing_batch, ("factor_research", "screening"))
    missing = service.current_openapi_fact(
        missing_batch, stock_code="2317", metric="revenue_yoy_percent",
        evidence=missing_evidence, cutoff_at=CUTOFF,
    )
    result = service.screen_minimum((missing,), minimum=Decimal("0"), cutoff_at=CUTOFF)
    assert result.matched == ()
    assert result.unknown == (missing,)
    assert result.rejected == ()


def test_comparison_screen_portfolio_and_shadow_market_identity():
    service = _service()
    twse = _batch(market="twse", yoy="12.5")
    tpex = _batch(market="tpex", yoy="7.5")
    uses = ("factor_research", "comparison", "screening", "sector_theme", "portfolio_research")
    twse_fact = service.current_openapi_fact(
        twse, stock_code="2330", metric="revenue_yoy_percent",
        evidence=_evidence(twse, uses), cutoff_at=CUTOFF,
    )
    tpex_fact = service.current_openapi_fact(
        tpex, stock_code="2330", metric="revenue_yoy_percent",
        evidence=_evidence(tpex, uses), cutoff_at=CUTOFF,
    )
    twse_tie_batch = _batch(market="twse", code="2317", yoy="12.5")
    twse_tie_fact = service.current_openapi_fact(
        twse_tie_batch, stock_code="2317", metric="revenue_yoy_percent",
        evidence=_evidence(twse_tie_batch, uses), cutoff_at=CUTOFF,
    )
    prior_period_batch = _batch(market="twse", period="2026-08", yoy="11.0")
    prior_period_fact = service.current_openapi_fact(
        prior_period_batch,
        stock_code="2330",
        metric="revenue_yoy_percent",
        evidence=_evidence(prior_period_batch, uses),
        cutoff_at=CUTOFF,
    )

    compared = service.compare(twse_fact, tpex_fact, cutoff_at=CUTOFF)
    different_period = service.compare(
        twse_fact, prior_period_fact, cutoff_at=CUTOFF
    )
    screened = service.screen_minimum((twse_fact, tpex_fact), minimum=Decimal("10"), cutoff_at=CUTOFF)
    portfolio = service.portfolio_research_summary(
        (twse_fact, twse_tie_fact, tpex_fact), weights_bp={("twse", "2330"): 3000, ("twse", "2317"): 3000, ("tpex", "2330"): 4000}, cutoff_at=CUTOFF,
    )
    snapshots = service.sector_theme_shadow_snapshots(
        (twse_fact, twse_tie_fact, tpex_fact), decision_date=CUTOFF.date(), cutoff_at=CUTOFF,
        universe_id="isolated-fixture",
    )

    assert compared.allowed and compared.delta == Decimal("5.0")
    assert not different_period.allowed
    assert "comparison_period_mismatch" in different_period.reasons
    assert tuple(fact.market for fact in screened.matched) == ("twse",)
    assert portfolio.allowed
    assert {row.market for row in portfolio.rows} == {"twse", "tpex"}
    assert len(snapshots) == 2
    assert {snapshot.universe_id for snapshot in snapshots} == {
        "isolated-fixture:twse", "isolated-fixture:tpex",
    }
    assert all(snapshot.metadata["formal_scoring_engine"] == "false" for snapshot in snapshots)
    twse_snapshot = next(item for item in snapshots if item.universe_id.endswith(":twse"))
    twse_rows = twse_snapshot.rows
    assert len(twse_rows) == 2
    assert twse_rows[0].score_bp == twse_rows[1].score_bp
    assert twse_rows[0].rank == twse_rows[1].rank
    with pytest.raises(ValueError, match="separate_market_snapshots"):
        service.sector_theme_shadow_snapshot(
            (twse_fact, tpex_fact), decision_date=CUTOFF.date(), cutoff_at=CUTOFF,
            universe_id="mixed",
        )


def test_archive_as_of_reopens_captured_historical_observation_but_backtest_stays_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(
        revision_archive_module,
        "_utc_now",
        lambda: datetime(2026, 10, 21, 7, 16, tzinfo=timezone.utc),
    )
    batch = _batch()
    appended = append_monthly_revenue_batch(
        tmp_path / "archive",
        raw_batch_from_openapi(batch),
        archive_sha256=None,
        expected_archive_sha256=None,
    )
    archive = read_monthly_revenue_revision_archive(
        tmp_path / "archive", appended.archive_sha256,
        expected_archive_sha256=appended.archive_sha256,
    )
    evidence = _evidence(
        batch, ("historical_research", "backtest"),
        downstream=(("backtest", "fixture:backtest-gate"),),
    )
    service = _service()
    observed = service.archived_observation_as_of(
        archive, expected_archive_sha256=appended.archive_sha256,
        market="twse", stock_code="2330", period="2026-09",
        metric="revenue_yoy_percent", evidence=evidence, cutoff_at=CUTOFF,
    )
    backtest = service.project_decision_cutoff(
        archive, expected_archive_sha256=appended.archive_sha256,
        market="twse", stock_code="2330", period="2026-09",
        metric="revenue_yoy_percent", evidence=evidence,
        decision_cutoff_at=CUTOFF, purpose="backtest",
    )
    with pytest.raises(ValueError, match="archive_external_hash_mismatch"):
        service.project_pinned_decision_cutoff(
            tmp_path / "archive",
            archive_sha256=appended.archive_sha256,
            expected_archive_sha256="f" * 64,
            market="twse",
            stock_code="2330",
            period="2026-09",
            metric="revenue_yoy_percent",
            evidence=evidence,
            decision_cutoff_at=CUTOFF,
            purpose="backtest",
        )

    assert observed.status == "PASS"
    assert observed.fact is not None and observed.fact.value == Decimal("12.5")
    assert observed.observation_as_of_verified
    assert not observed.formal_pit_eligible
    assert backtest.status == "BLOCKED_WITH_REASON"
    assert backtest.fact is not None and not backtest.fact.allowed
    assert not backtest.formal_pit_eligible
    assert "archive_observation_is_not_formal_pit" in backtest.reasons


def test_late_archived_observation_keeps_batch_evidence_clock_and_archive_visibility_gate(
    tmp_path, monkeypatch,
):
    persisted_at = datetime(2026, 10, 21, 12, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(revision_archive_module, "_utc_now", lambda: persisted_at)
    batch = _batch()
    saved = append_monthly_revenue_batch(
        tmp_path / "late-archive",
        raw_batch_from_openapi(batch),
        archive_sha256=None,
        expected_archive_sha256=None,
    )
    archive = read_monthly_revenue_revision_archive(
        tmp_path / "late-archive",
        saved.archive_sha256,
        expected_archive_sha256=saved.archive_sha256,
    )
    evidence = _evidence(
        batch,
        ("historical_research", "backtest"),
        downstream=(("backtest", "fixture:backtest-gate"),),
    )
    verifier_calls = []

    def provider_like_verifier(candidate, cutoff_at):
        verifier_calls.append((candidate, cutoff_at))
        return (
            candidate is evidence
            and candidate.source_id == batch.capture.source_id
            and candidate.batch_sha256 == batch.capture.raw_response_sha256
            and candidate.available_at == batch.available_hour
            and candidate.captured_at == batch.successful_batch_completed_at
        )

    service = MonthlyRevenueResearchService(
        qualification_verifier=provider_like_verifier,
    )
    before_visibility = service.archived_observation_as_of(
        archive,
        expected_archive_sha256=saved.archive_sha256,
        market="twse",
        stock_code="2330",
        period="2026-09",
        metric="revenue_yoy_percent",
        evidence=evidence,
        cutoff_at=datetime(2026, 10, 21, 12, 59, tzinfo=timezone.utc),
    )
    cutoff_after_visibility = datetime(2026, 10, 21, 13, 0, tzinfo=timezone.utc)
    after_visibility = service.archived_observation_as_of(
        archive,
        expected_archive_sha256=saved.archive_sha256,
        market="twse",
        stock_code="2330",
        period="2026-09",
        metric="revenue_yoy_percent",
        evidence=evidence,
        cutoff_at=cutoff_after_visibility,
    )
    backtest = service.project_decision_cutoff(
        archive,
        expected_archive_sha256=saved.archive_sha256,
        market="twse",
        stock_code="2330",
        period="2026-09",
        metric="revenue_yoy_percent",
        evidence=evidence,
        decision_cutoff_at=cutoff_after_visibility,
        purpose="backtest",
    )
    rebound_evidence = replace(
        evidence,
        available_at=evidence.available_at + timedelta(hours=1),
    )
    rebound = service.archived_observation_as_of(
        archive,
        expected_archive_sha256=saved.archive_sha256,
        market="twse",
        stock_code="2330",
        period="2026-09",
        metric="revenue_yoy_percent",
        evidence=rebound_evidence,
        cutoff_at=cutoff_after_visibility,
    )

    assert before_visibility.status == "not_visible_by_cutoff"
    assert before_visibility.fact is None
    assert after_visibility.status == "PASS"
    assert after_visibility.fact is not None
    assert after_visibility.fact.allowed
    assert after_visibility.fact.evidence is evidence
    assert after_visibility.fact.source_batch_available_at == evidence.available_at
    assert after_visibility.fact.available_at == cutoff_after_visibility
    assert after_visibility.fact.available_at > after_visibility.fact.evidence.available_at
    assert backtest.status == "BLOCKED_WITH_REASON"
    assert backtest.fact is not None and not backtest.fact.allowed
    assert not backtest.formal_pit_eligible
    assert "archive_observation_is_not_formal_pit" in backtest.reasons
    assert rebound.status == "source_evidence_mismatch"
    assert rebound.fact is None
    assert verifier_calls == [
        (evidence, cutoff_after_visibility),
        (evidence, cutoff_after_visibility),
    ]


def test_paper_forward_bridge_is_a_separate_revenue_feature_gate_only():
    batch = _batch()
    service = _service()
    paper_evidence = _evidence(
        batch, ("factor_research", "paper"), downstream=(("paper", "fixture:paper-revenue-gate"),),
    )
    fact = service.current_openapi_fact(
        batch, stock_code="2330", metric="revenue_yoy_percent",
        evidence=paper_evidence, cutoff_at=CUTOFF,
    )
    assert service.paper_forward_revenue_gate(fact, cutoff_at=CUTOFF, purpose="paper").allowed
    assert not service.paper_forward_revenue_gate(fact, cutoff_at=CUTOFF, purpose="forward").allowed


def _qualified_amount(
    period: str,
    value: str,
    *,
    captured_at=CAPTURED_AT,
    pit=False,
    qualification_cutoff=CUTOFF,
):
    unproven = _batch(period=period, amount=value, captured_at=captured_at)
    proof = _unit_proof()
    batch = prepare_openapi_monthly_revenue_batch(
        capture=unproven.capture,
        successful_batch_completed_at=unproven.successful_batch_completed_at,
        unit_proof=proof,
        trusted_unit_proof_sha256=proof.proof_sha256,
    )
    evidence = _evidence(
        batch, ("factor_research",), unit_proof_sha256=proof.proof_sha256, pit=pit,
    )
    return _service().qualified_amount_from_openapi(
        batch,
        stock_code="2330",
        evidence=evidence,
        unit_proof=proof,
        cutoff_at=qualification_cutoff,
    )


def test_ttm_and_three_month_research_windows_require_unique_capture_visible_months():
    service = _service()
    months = tuple(f"2025-{month:02d}" for month in range(1, 13))
    observations = tuple(_qualified_amount(period, str(index)) for index, period in enumerate(months, 1))

    ttm = service.trailing_twelve_month_total(
        observations, market="twse", stock_code="2330", ending_period="2025-12", cutoff_at=CUTOFF,
    )
    trend = service.three_month_amount_trend(
        observations[-3:], market="twse", stock_code="2330", ending_period="2025-12", cutoff_at=CUTOFF,
    )
    missing = service.trailing_twelve_month_total(
        observations[:-1], market="twse", stock_code="2330", ending_period="2025-12", cutoff_at=CUTOFF,
    )
    duplicate = service.three_month_amount_trend(
        (*observations[-3:], observations[-1]), market="twse", stock_code="2330",
        ending_period="2025-12", cutoff_at=CUTOFF,
    )

    assert ttm.allowed and ttm.value == Decimal("78000")
    assert not ttm.formal_pit_eligible
    assert trend.allowed and trend.value == "up"
    assert not missing.allowed and "monthly_window_missing_or_revision_ambiguous" in missing.reasons
    assert not duplicate.allowed and "monthly_window_missing_or_revision_ambiguous" in duplicate.reasons

    with pytest.raises(ValueError, match="qualification_evidence_does_not_match_openapi_batch"):
        _qualified_amount("2025-01", "1", pit=True)


def test_ttm_rejects_capture_after_cutoff_even_when_value_is_otherwise_qualified():
    service = _service()
    observations = tuple(
        _qualified_amount(f"2025-{month:02d}", str(month),
                          captured_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
                          qualification_cutoff=datetime(2026, 10, 24, tzinfo=timezone.utc))
        for month in range(1, 13)
    )
    result = service.trailing_twelve_month_total(
        observations, market="twse", stock_code="2330", ending_period="2025-12", cutoff_at=CUTOFF,
    )
    assert not result.allowed
    assert any("after_cutoff" in reason for reason in result.reasons)


def test_decimal_projection_comparison_ttm_and_portfolio_ignore_ambient_precision():
    service = _service()
    large_amount = "123456789012345678901234567890123.123"
    amount_batch_without_proof = _batch(amount=large_amount)
    proof = _unit_proof()
    amount_batch = prepare_openapi_monthly_revenue_batch(
        capture=amount_batch_without_proof.capture,
        successful_batch_completed_at=amount_batch_without_proof.successful_batch_completed_at,
        unit_proof=proof,
        trusted_unit_proof_sha256=proof.proof_sha256,
    )
    evidence = _evidence(
        amount_batch, ("factor_research",), unit_proof_sha256=proof.proof_sha256,
    )
    with localcontext() as context:
        context.prec = 3
        amount_fact = service.current_openapi_fact(
            amount_batch, stock_code="2330", metric="revenue_amount_twd",
            evidence=evidence, cutoff_at=CUTOFF,
            unit_proof=proof,
        )
    assert amount_fact.value == Decimal("123456789012345678901234567890123123.000")

    left_batch = _batch(code="2330", yoy="12345678901234567890.123")
    right_batch = _batch(code="2317", yoy="0.001")
    comparison_uses = ("factor_research", "comparison", "portfolio_research")
    left = service.current_openapi_fact(
        left_batch, stock_code="2330", metric="revenue_yoy_percent",
        evidence=_evidence(left_batch, comparison_uses), cutoff_at=CUTOFF,
    )
    right = service.current_openapi_fact(
        right_batch, stock_code="2317", metric="revenue_yoy_percent",
        evidence=_evidence(right_batch, comparison_uses), cutoff_at=CUTOFF,
    )
    with localcontext() as context:
        context.prec = 3
        compared = service.compare(left, right, cutoff_at=CUTOFF)
        portfolio = service.portfolio_research_summary(
            (left, right),
            weights_bp={("twse", "2330"): 6000, ("twse", "2317"): 4000},
            cutoff_at=CUTOFF,
        )
    assert compared.delta == Decimal("12345678901234567890.122")
    assert portfolio.allowed
    contributions = {row.stock_code: row.weighted_metric_contribution for row in portfolio.rows}
    assert contributions["2330"] == Decimal("7407407340740740734.0738")
    huge_window = tuple(
        _qualified_amount(f"2025-{month:02d}", "12345678901234567890.123")
        for month in range(1, 13)
    )
    with localcontext() as context:
        context.prec = 3
        ttm = service.trailing_twelve_month_total(
            huge_window, market="twse", stock_code="2330",
            ending_period="2025-12", cutoff_at=CUTOFF,
        )
    assert ttm.value == Decimal("148148146814814814681476")
