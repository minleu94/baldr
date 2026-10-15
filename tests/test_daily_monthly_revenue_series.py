from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    build_daily_monthly_revenue_cohort_pin,
    write_daily_monthly_revenue_cohort_pin_create_only,
)
from data_module.daily_monthly_revenue_series import (
    DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES,
    DailyMonthlyRevenueSeriesError,
    DailyMonthlyRevenueSeriesMarketTrustV1,
    DailyMonthlyRevenueSeriesTrustV1,
    select_daily_monthly_revenue_series_v1,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DailySourceBatchValidation,
    DailySourceSnapshotFileReader,
    DailySourceSnapshotRecord,
    DailySourceTransportCapture,
    DailySourceUseAcceptance,
    DailySourceUseScope,
    DailySourceValidationCheck,
    write_daily_source_snapshot,
)


TAIPEI = ZoneInfo("Asia/Taipei")
REPORT_PERIOD = "2026-04"
INTENDED_USE = "recommendation_current_fundamental"
ENDPOINT = "https://mops.twse.com.tw/mops/web/t05st10_ifrs"


def _scope(
    market: str,
    *,
    unit: str = "TWD",
    source_id: str = "mops.monthly_revenue_static_snapshot",
) -> DailySourceUseScope:
    return DailySourceUseScope(
        dataset_id="fundamental_current_observations.monthly_revenue",
        source_id=source_id,
        market=market,
        parser_version="mops-current-revenue-normalizer.v2",
        source_schema_version="mops-static-snapshot.v2",
        unit=unit,
        intended_use=INTENDED_USE,
    )


def _acceptance(
    market: str,
    *,
    unit: str = "TWD",
    source_id: str = "mops.monthly_revenue_static_snapshot",
) -> DailySourceUseAcceptance:
    scope = _scope(market, unit=unit, source_id=source_id)
    return DailySourceUseAcceptance(
        scope=scope,
        acceptance_id=f"synthetic-mops-current-{market}-v1",
        accepted_at=datetime(2026, 10, 1, 8, 0, tzinfo=TAIPEI),
        official_source_endpoint=ENDPOINT,
        document_chain=("synthetic-test-evidence", ENDPOINT),
        acceptance_evidence_ref="test-fixture:explicit-trusted-acceptance",
        authorization_scope=f"{INTENDED_USE} only",
        time_basis_policy=DAILY_SOURCE_TIME_BASIS_POLICY,
    )


def _validation(market: str) -> DailySourceBatchValidation:
    def passed(check_id: str) -> DailySourceValidationCheck:
        return DailySourceValidationCheck(check_id, "pass", f"{check_id}_verified")

    return DailySourceBatchValidation(
        validation_id=f"synthetic-{market}-validation",
        expected_partition_ids=(f"{market}-monthly-revenue",),
        successful_partition_ids=(f"{market}-monthly-revenue",),
        failed_partition_ids=(),
        expected_record_count=1,
        actual_record_count=1,
        source_status_check=passed("source_status"),
        raw_source_hash_check=passed("raw_source_hash"),
        schema_check=passed("schema"),
        unit_check=passed("unit"),
        finite_values_check=passed("finite_values"),
        missing_values_check=passed("missing_values"),
        prior_period_required_check=DailySourceValidationCheck(
            "prior_period_required", "not_required", "prior_period_not_required"
        ),
        official_timestamp_parse_check=DailySourceValidationCheck(
            "official_timestamp_parse",
            "pass",
            "official_timestamp_parsed_by:mops-current-revenue-normalizer.v2",
        ),
    )


def _write_market_batch(
    root: Path,
    market: str,
    *,
    batch_id: str,
    body_hour: int,
    period: str = REPORT_PERIOD,
) -> tuple[DailySourceSnapshotFileReader, DailySourceUseAcceptance]:
    acceptance = _acceptance(market)
    body_completed_at = datetime(2026, 10, 2, body_hour, 5, tzinfo=TAIPEI)
    source_text = (
        '<html><head><meta charset="utf-8"></head><body>'
        f"synthetic official-source fixture {market} {period} {batch_id}"
        "</body></html>"
    )
    source_bytes = source_text.encode("utf-8")
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    stock_code = "2330" if market == "twse" else "6488"
    record = DailySourceSnapshotRecord(
        stock_code=stock_code,
        market=market,
        period=period,
        source_version=(
            f"mops-static-snapshot.v2:{market}:{period}:body_completed_at:"
            f"{body_completed_at.isoformat()}:sha256:{source_sha256}"
        ),
        raw_source_sha256=source_sha256,
        unit="TWD",
        official_timestamp=body_completed_at,
        official_timestamp_original_text=body_completed_at.isoformat(),
        official_timestamp_original_timezone="+08:00",
    )
    capture = DailySourceTransportCapture(
        raw_response_bytes=source_bytes,
        official_source_url=ENDPOINT,
        response_status=200,
        content_type="text/html",
        declared_decoding_encoding="utf-8",
        decoding_basis="html_meta_charset",
        body_completed_at=body_completed_at,
        transport_sha256=source_sha256,
        response_body_complete=True,
        received_body_bytes=len(source_bytes),
        content_length_original_text=str(len(source_bytes)),
        body_completion_evidence_ref=f"eof:synthetic-{market}-{batch_id}",
    )
    clock_values = iter(
        (
            body_completed_at + timedelta(minutes=5),
            body_completed_at + timedelta(minutes=15),
            body_completed_at + timedelta(minutes=20),
            body_completed_at + timedelta(minutes=25),
        )
    )
    write_daily_source_snapshot(
        root,
        batch_id=batch_id,
        scope=acceptance.scope,
        use_acceptance=acceptance,
        source_batch_started_at=body_completed_at - timedelta(minutes=10),
        raw_source_bytes=source_bytes,
        records=(record,),
        validation=_validation(market),
        transport_capture=capture,
        clock=lambda: next(clock_values),
    )
    return DailySourceSnapshotFileReader(root, trusted_acceptance=acceptance), acceptance


def _write_cohort(
    tmp_path: Path,
    *,
    version: str,
    twse_hour: int = 10,
    tpex_hour: int = 11,
    period: str = REPORT_PERIOD,
) -> DailyMonthlyRevenueCohortPin:
    snapshot_roots = {market: tmp_path / "snapshots" / market for market in ("twse", "tpex")}
    readers: dict[str, DailySourceSnapshotFileReader] = {}
    batch_ids = {market: f"{version}-{market}" for market in ("twse", "tpex")}
    for market, body_hour in (("twse", twse_hour), ("tpex", tpex_hour)):
        readers[market], _ = _write_market_batch(
            snapshot_roots[market],
            market,
            batch_id=batch_ids[market],
            body_hour=body_hour,
            period=period,
        )
    pin = build_daily_monthly_revenue_cohort_pin(
        period=period,
        required_markets=("twse", "tpex"),
        batch_ids=batch_ids,
        readers=readers,
    )
    write_daily_monthly_revenue_cohort_pin_create_only(tmp_path / "cohort-pins", pin)
    return pin


def _trust(tmp_path: Path) -> DailyMonthlyRevenueSeriesTrustV1:
    return DailyMonthlyRevenueSeriesTrustV1(
        cohort_pin_root=tmp_path / "cohort-pins",
        market_sources=(
            DailyMonthlyRevenueSeriesMarketTrustV1(
                "twse", tmp_path / "snapshots" / "twse", _acceptance("twse")
            ),
            DailyMonthlyRevenueSeriesMarketTrustV1(
                "tpex", tmp_path / "snapshots" / "tpex", _acceptance("tpex")
            ),
        ),
    )


def _select(
    trust: DailyMonthlyRevenueSeriesTrustV1,
    pins: tuple[DailyMonthlyRevenueCohortPin, ...] | list[DailyMonthlyRevenueCohortPin],
    *,
    cutoff_at: datetime | None = None,
    decision_batch_ids: dict[str, str] | None = None,
    report_period: str = REPORT_PERIOD,
):
    return select_daily_monthly_revenue_series_v1(
        trust=trust,
        expected_trust_configuration_sha256=trust.configuration_sha256,
        report_period=report_period,
        candidate_pins=pins,
        cutoff_at=cutoff_at,
        decision_batch_ids=decision_batch_ids,
    )


def test_selected_real_daily_port_preserves_full_pin_through_snapshot_save(tmp_path: Path) -> None:
    """選版結果實際送入既有 provider／SQLite copy，不以假reader取代。"""
    from data_module.fundamental_read_snapshot_daily_v2 import FundamentalReadSnapshotSessionV2
    from tests.test_selection_fundamental_daily_cohort_v2 import _daily_cohort_environment, _source_db_state
    from tests.test_baldr_completion_p03_sources import CUTOFF

    provider, _, pin, market_readers, _ = _daily_cohort_environment(tmp_path / "real-source")
    pin_root = tmp_path / "real-pins"
    write_daily_monthly_revenue_cohort_pin_create_only(pin_root, pin)
    trust = DailyMonthlyRevenueSeriesTrustV1(
        cohort_pin_root=pin_root,
        market_sources=tuple(
            DailyMonthlyRevenueSeriesMarketTrustV1(market, market_readers[market].root,
                                                  market_readers[market].trusted_acceptance)
            for market in pin.required_markets
        ),
    )
    # 合成 fixture producer 保存外部信任值；consumer 從固定檔讀入，不在呼叫處自算。
    anchor_path = tmp_path / "external-trust.sha256"
    with anchor_path.open("x", encoding="ascii") as anchor:
        anchor.write(trust.configuration_sha256)
    selected = select_daily_monthly_revenue_series_v1(
        trust=trust, expected_trust_configuration_sha256=anchor_path.read_text(encoding="ascii"),
        report_period=pin.period, candidate_pins=(pin,), cutoff_at=CUTOFF,
    )
    provider.daily_source_snapshot_reader = selected.reader
    original_state = _source_db_state(provider.db_file)
    with FundamentalReadSnapshotSessionV2.open(
        provider, snapshot_root=tmp_path / "selected-snapshots", stock_codes=("1101", "2330"),
        cutoff_at=CUTOFF, daily_monthly_cohort_reader=selected.reader,
    ) as session:
        batch = session.load_batch(("1101", "2330"))
        finished = session.finish()
        assert batch.cohort_sha256 == selected.pin.cohort_sha256
        assert finished.source_clock.cohort_pin == selected.pin == pin
        assert session.source_reference.daily_cohort_sha256 == pin.cohort_sha256
        assert finished.source_clock.formal_pit_eligible is False
        assert finished.source_clock.historical_pit_eligible is False
    assert selected.verify_integrity() == pin
    assert session.closed and _source_db_state(provider.db_file) == original_state


def test_external_trust_anchor_and_current_mops_unit_scope_are_required(
    tmp_path: Path,
) -> None:
    pin = _write_cohort(tmp_path, version="anchor")
    trust = _trust(tmp_path)

    with pytest.raises(DailyMonthlyRevenueSeriesError, match="external_trust_hash_mismatch"):
        select_daily_monthly_revenue_series_v1(
            trust=trust,
            expected_trust_configuration_sha256="0" * 64,
            report_period=REPORT_PERIOD,
            candidate_pins=(pin,),
            cutoff_at=pin.available_hour,
        )

    changed_acceptance = replace(
        trust.market_sources[1].trusted_acceptance,
        acceptance_evidence_ref="test-fixture:changed-after-external-approval",
    )
    changed_tpex = replace(
        trust.market_sources[1], trusted_acceptance=changed_acceptance
    )
    changed_trust = replace(
        trust,
        market_sources=(trust.market_sources[0], changed_tpex),
    )
    with pytest.raises(DailyMonthlyRevenueSeriesError, match="external_trust_hash_mismatch"):
        changed_trust.verify_external_anchor(trust.configuration_sha256)

    with pytest.raises(DailyMonthlyRevenueSeriesError, match="scope_not_current_mops"):
        DailyMonthlyRevenueSeriesMarketTrustV1(
            "twse", tmp_path / "snapshots" / "twse", _acceptance("twse", unit="thousand_TWD"),
        )


def test_report_period_is_mandatory_and_cutoff_is_not_ceiled(tmp_path: Path) -> None:
    pin = _write_cohort(tmp_path, version="cutoff")
    trust = _trust(tmp_path)

    with pytest.raises(DailyMonthlyRevenueSeriesError, match="report_period_invalid"):
        _select(trust, (pin,), report_period="2026-13", cutoff_at=pin.available_hour)
    with pytest.raises(
        DailyMonthlyRevenueSeriesError,
        match="series_select_exactly_one_cutoff_or_batch",
    ):
        _select(trust, (pin,))
    with pytest.raises(
        DailyMonthlyRevenueSeriesError,
        match="series_select_exactly_one_cutoff_or_batch",
    ):
        _select(
            trust,
            (pin,),
            cutoff_at=pin.available_hour,
            decision_batch_ids={
                market: pin.for_market(market).batch_id for market in ("twse", "tpex")
            },
        )

    just_before = pin.available_hour - timedelta(minutes=1)
    with pytest.raises(DailyMonthlyRevenueSeriesError, match="no_eligible_complete_candidate"):
        _select(trust, (pin,), cutoff_at=just_before)
    selected = _select(trust, (pin,), cutoff_at=pin.available_hour)
    assert selected.cutoff_at == pin.available_hour
    assert selected.selection_mode == "cutoff"
    assert selected.pin is selected.reader.pin
    assert selected.verify_integrity() == pin
    assert selected.source_qualification == "not_granted"
    assert selected.historical_pit_eligible is False
    assert selected.formal_pit_eligible is False


def test_cutoff_selection_is_deterministic_across_candidate_order_and_freezes_old_pin(
    tmp_path: Path,
) -> None:
    earlier = _write_cohort(tmp_path, version="earlier", twse_hour=10, tpex_hour=11)
    later = _write_cohort(tmp_path, version="later", twse_hour=12, tpex_hour=13)
    trust = _trust(tmp_path)
    cutoff = later.available_hour + timedelta(hours=1)

    selected_forward = _select(trust, (earlier, later), cutoff_at=cutoff)
    selected_reverse = _select(trust, (later, earlier), cutoff_at=cutoff)
    old_selection = _select(trust, (earlier,), cutoff_at=earlier.available_hour)

    assert selected_forward.pin.cohort_sha256 == later.cohort_sha256
    assert selected_reverse.pin.cohort_sha256 == selected_forward.pin.cohort_sha256
    assert old_selection.pin.cohort_sha256 == earlier.cohort_sha256
    assert old_selection.reader.pin is old_selection.pin
    assert old_selection.verify_integrity() is old_selection.pin


def test_exact_batch_selection_has_no_fallback_and_no_cutoff_claim(tmp_path: Path) -> None:
    pin = _write_cohort(tmp_path, version="exact")
    alternative = _write_cohort(tmp_path, version="exact-alternative", twse_hour=12, tpex_hour=13)
    trust = _trust(tmp_path)
    requested = {market: pin.for_market(market).batch_id for market in ("twse", "tpex")}

    selected = _select(trust, (pin, alternative), decision_batch_ids=requested)
    assert selected.selection_mode == "exact_batch"
    assert selected.cutoff_at is None
    assert selected.decision_batch_ids == tuple(requested.items())
    assert selected.verify_integrity() is selected.pin

    no_fallback = {
        "twse": "different-explicit-batch",
        "tpex": pin.for_market("tpex").batch_id,
    }
    with pytest.raises(DailyMonthlyRevenueSeriesError) as error:
        _select(trust, (pin, alternative), decision_batch_ids=no_fallback)
    assert error.value.code == "series_no_eligible_complete_candidate"
    assert any("candidate_exact_batch_not_requested" in item for item in error.value.diagnostics)


def test_mixed_report_period_candidate_is_named_and_never_replaces_requested_period(
    tmp_path: Path,
) -> None:
    april = _write_cohort(tmp_path, version="april", period="2026-04")
    may = _write_cohort(tmp_path, version="may", period="2026-05")
    trust = _trust(tmp_path)

    selected = _select(trust, (may, april), report_period="2026-04", cutoff_at=may.available_hour)
    assert selected.pin.period == "2026-04"
    assert any("candidate_report_period_mismatch" in item for item in selected.candidate_diagnostics)


def test_partial_market_pin_is_rejected_even_when_its_own_hash_is_valid(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshots" / "twse"
    twse_reader, _ = _write_market_batch(
        snapshot_root,
        "twse",
        batch_id="partial-twse-only",
        body_hour=10,
    )
    partial = build_daily_monthly_revenue_cohort_pin(
        period=REPORT_PERIOD,
        required_markets=("twse",),
        batch_ids={"twse": "partial-twse-only"},
        readers={"twse": twse_reader},
    )
    write_daily_monthly_revenue_cohort_pin_create_only(tmp_path / "cohort-pins", partial)
    trust = _trust(tmp_path)

    with pytest.raises(DailyMonthlyRevenueSeriesError) as error:
        _select(trust, (partial,), cutoff_at=partial.available_hour)
    assert error.value.code == "series_no_eligible_complete_candidate"
    assert any("candidate_required_markets_incomplete" in item for item in error.value.diagnostics)


def test_selected_reader_rechecks_both_markets_after_snapshot_mutation(tmp_path: Path) -> None:
    pin = _write_cohort(tmp_path, version="mutation")
    trust = _trust(tmp_path)
    selected = _select(trust, (pin,), cutoff_at=pin.available_hour)
    twse_batch = pin.for_market("twse").batch_id
    manifest = tmp_path / "snapshots" / "twse" / twse_batch / "manifest.json"
    original = manifest.read_bytes()
    manifest.write_bytes(original + b" ")

    with pytest.raises(DailyMonthlyRevenueSeriesError, match="source_recheck_failed"):
        selected.verify_integrity()


def test_selection_token_cannot_be_replaced_to_change_its_cutoff(tmp_path: Path) -> None:
    pin = _write_cohort(tmp_path, version="anchor-token")
    selected = _select(_trust(tmp_path), (pin,), cutoff_at=pin.available_hour)

    with pytest.raises((TypeError, ValueError)):
        replace(selected, cutoff_at=pin.available_hour + timedelta(days=1))
    with pytest.raises(AttributeError):
        setattr(selected, "cutoff_at", pin.available_hour + timedelta(days=1))


def test_candidate_list_is_bounded_and_duplicate_pins_are_rejected(tmp_path: Path) -> None:
    pin = _write_cohort(tmp_path, version="bound")
    trust = _trust(tmp_path)
    oversized = [pin] * (DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES + 1)
    with pytest.raises(DailyMonthlyRevenueSeriesError, match="candidate_count_out_of_bounds"):
        _select(trust, oversized, cutoff_at=pin.available_hour)
    with pytest.raises(DailyMonthlyRevenueSeriesError, match="candidate_pin_duplicate"):
        _select(trust, (pin, pin), cutoff_at=pin.available_hour)


def test_trust_scope_rejects_another_source_before_hash_can_authorize_it(
    tmp_path: Path,
) -> None:
    with pytest.raises(DailyMonthlyRevenueSeriesError, match="scope_not_current_mops"):
        DailyMonthlyRevenueSeriesMarketTrustV1(
            "twse", tmp_path / "snapshots" / "twse",
            _acceptance("twse", source_id="twse.openapi.monthly_revenue"),
        )


def test_candidate_count_requires_exact_tuple_or_list_not_an_unbounded_iterator(
    tmp_path: Path,
) -> None:
    pin = _write_cohort(tmp_path, version="iterable")
    trust = _trust(tmp_path)

    with pytest.raises(DailyMonthlyRevenueSeriesError, match="bounded_list_or_tuple"):
        select_daily_monthly_revenue_series_v1(
            trust=trust,
            expected_trust_configuration_sha256=trust.configuration_sha256,
            report_period=REPORT_PERIOD,
            candidate_pins=iter((pin,)),  # type: ignore[arg-type]
            cutoff_at=pin.available_hour,
        )
