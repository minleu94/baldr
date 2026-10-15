"""每日月營收 V2 facts、完成 ledger 與 V3 參照的純型別反例。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from data_module.current_fundamental_snapshots import MONTHLY_SNAPSHOT_SOURCE
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY,
    DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND,
    DAILY_MARKET_MONTHLY_REVENUE_SOURCE_REFERENCE_V3_SCHEMA,
    DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE,
    DailyMarketMonthlyRevenueCohortV2Error,
    DailyMarketMonthlyRevenueFactV2,
    DailyMarketMonthlyRevenueSourceReferenceV3,
    FinishedDailyMarketMonthlyRevenueCohortV2,
    UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3,
    _issue_finished_daily_market_monthly_revenue_cohort_v2,
    _reference_finished_identity,
    decode_daily_market_monthly_revenue_source_reference_v3,
)
from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueMarketSnapshotPin,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DailySourceUseScope,
)
from data_module.fundamental_read_snapshot import (
    FundamentalFilePin,
    FundamentalReadSnapshotBinding,
    FundamentalReadSnapshotFileReference,
    FundamentalSnapshotSourceClock,
)
from data_module.fundamental_read_snapshot_cohort_v2 import (
    FinishedFundamentalSnapshotReadCohortV2,
    FundamentalReadSnapshotReferenceV2,
    FundamentalSnapshotSourceClockV2,
    make_finished_snapshot_manifest_v2,
    make_snapshot_reference_v2,
    encode_snapshot_reference_v2,
    parse_finished_snapshot_cohort_v2,
)
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    CurrentObservedMonthlyRevenueInput,
)
from data_module.selection_fact_readers import _result_identity_sha256_v2


_TAIPEI = ZoneInfo("Asia/Taipei")
_RAW_HASH = "a" * 64
_COMPARATOR_HASH = "b" * 64
_BATCH_BASIS = "successful_batch_completion_fallback"


def _sha(char: str) -> str:
    return char * 64


def _file_pin(role: str, path: Path, *, digest: str, size: int = 9) -> FundamentalFilePin:
    return FundamentalFilePin(
        role=role,
        path=str(path),
        present=True,
        device=1,
        inode=2,
        size_bytes=size,
        mtime_ns=3,
        mode=0o100600,
        sha256=digest,
    )


def _daily_pin(batch_suffix: str = "a") -> DailyMonthlyRevenueCohortPin:
    market = "twse"
    scope = DailySourceUseScope(
        dataset_id="monthly_revenue",
        source_id="mops.monthly_revenue",
        market=market,
        parser_version="mops-html.v2",
        source_schema_version="monthly-revenue-table.v2",
        unit="TWD",
        intended_use="research.monthly_revenue",
    )
    finished_at = datetime(2026, 10, 14, 10, 45, tzinfo=_TAIPEI)
    market_pin = DailyMonthlyRevenueMarketSnapshotPin(
        market=market,
        period="2026-09",
        batch_id=f"twse-20261014-{batch_suffix}",
        scope=scope,
        acceptance_id="acceptance-twse",
        acceptance_sha256=_sha("1"),
        time_basis_policy=DAILY_SOURCE_TIME_BASIS_POLICY,
        manifest_sha256=_sha("2"),
        receipt_sha256=_sha("3"),
        raw_source_sha256=_sha("4"),
        transport_sha256=_sha("5"),
        record_count=1,
        available_hour=datetime(2026, 10, 14, 11, 0, tzinfo=_TAIPEI),
        availability_basis=(_BATCH_BASIS,),
        source_batch_started_at=datetime(2026, 10, 14, 10, 0, tzinfo=_TAIPEI),
        first_persisted_at=datetime(2026, 10, 14, 10, 30, tzinfo=_TAIPEI),
        successful_batch_completed_at=finished_at,
    )
    return DailyMonthlyRevenueCohortPin(
        period="2026-09",
        required_markets=(market,),
        market_pins=(market_pin,),
        available_hour=market_pin.available_hour,
    )


def _future_daily_pin() -> DailyMonthlyRevenueCohortPin:
    base_pin = _daily_pin()
    future_market_pin = replace(
        base_pin.market_pins[0],
        available_hour=datetime(2026, 10, 14, 22, 0, tzinfo=_TAIPEI),
        source_batch_started_at=datetime(2026, 10, 14, 20, 0, tzinfo=_TAIPEI),
        first_persisted_at=datetime(2026, 10, 14, 20, 30, tzinfo=_TAIPEI),
        successful_batch_completed_at=datetime(2026, 10, 14, 21, 5, tzinfo=_TAIPEI),
    )
    return DailyMonthlyRevenueCohortPin(
        period=base_pin.period,
        required_markets=base_pin.required_markets,
        market_pins=(future_market_pin,),
        available_hour=future_market_pin.available_hour,
        time_basis_policy=base_pin.time_basis_policy,
    )


def _snapshot_clock(
    tmp_path: Path,
    pin: DailyMonthlyRevenueCohortPin,
    *,
    stock_codes: tuple[str, ...] = ("2330",),
    snapshot_id: str = "a" * 32,
) -> FundamentalSnapshotSourceClockV2:
    root = tmp_path / snapshot_id
    source_db = tmp_path / "fundamental.sqlite"
    reader_db = root / "reader" / "fundamental.sqlite"
    manifest_path = root / "capture_manifest.json"
    digest = _sha("6")
    source_pins = (_file_pin("sqlite_main", source_db, digest=digest),)
    captured_ref = FundamentalReadSnapshotFileReference(
        role="sqlite_main",
        relative_path="captured/fundamental.sqlite",
        size_bytes=9,
        sha256=digest,
    )
    reader_ref = FundamentalReadSnapshotFileReference(
        role="sqlite_main",
        relative_path="reader/fundamental.sqlite",
        size_bytes=9,
        sha256=digest,
    )
    captured_pin = _file_pin(
        "sqlite_main", tmp_path / "monthly" / "source.html", digest=digest
    )
    reader_pin = _file_pin("sqlite_main", reader_db, digest=digest)
    manifest_pin = _file_pin("capture_manifest", manifest_path, digest=_sha("7"), size=128)
    binding = FundamentalReadSnapshotBinding(
        snapshot_id=snapshot_id,
        snapshot_root=str(root),
        source_database_path=str(source_db),
        reader_database_path=str(reader_db),
        source_file_pins_start=source_pins,
        source_file_pins_after_copy=source_pins,
        source_file_pins_finish=source_pins,
        captured_files=(captured_ref,),
        captured_file_pins_start=(captured_pin,),
        captured_file_pins_finish=(captured_pin,),
        capture_manifest_pin_start=manifest_pin,
        capture_manifest_pin_finish=manifest_pin,
        reader_files=(reader_ref,),
        reader_file_pins_finish=(reader_pin,),
        sqlite_journal_mode="rollback",
        wal_sidecar_state="not_applicable",
        source_snapshot_sha256=_sha("8"),
        source_copy_bytes=9,
        reader_only_sidecar_bytes=0,
        duplicated_disk_bytes=18,
    )
    base = FundamentalSnapshotSourceClock(
        database_path=str(source_db),
        decision_cutoff=datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc),
        declared_stock_codes=stock_codes,
        schema_identity_sha256=_sha("9"),
        schema_descriptor=((0, "monthly_revenue", "stock_code", 0, None, 0),),
        database_file_pins_start=source_pins,
        database_file_pins_finish=source_pins,
        capture_file_pins_start=(captured_pin,),
        capture_file_pins_finish=(captured_pin,),
        snapshot_binding=binding,
    )
    return FundamentalSnapshotSourceClockV2.from_base_clock(
        base,
        cohort_pin=pin,
        verified_markets=pin.required_markets,
    )


def _current(
    pin: DailyMonthlyRevenueCohortPin,
    *,
    revenue: Decimal = Decimal("123.450"),
    unit: str = "TWD",
) -> CurrentObservedMonthlyRevenueInput:
    raw_version = f"mops-static-twse-2026-09-sha256-{_RAW_HASH}"
    return CurrentObservedMonthlyRevenueInput(
        stock_code="2330",
        period="2026-09",
        revenue=revenue,
        observed_at=datetime(2026, 10, 14, 11, 15, tzinfo=_TAIPEI),
        source_available_at=datetime(2026, 10, 14, 10, 25, tzinfo=_TAIPEI),
        available_at=datetime(2026, 10, 14, 11, 0, tzinfo=_TAIPEI),
        source=MONTHLY_SNAPSHOT_SOURCE,
        source_version=(
            "mops-current-revenue-normalizer.v2:twse:2026-09:raw:"
            f"{raw_version}:derived:sha256:{_COMPARATOR_HASH}"
        ),
        market="twse",
        raw_source_version=raw_version,
        raw_source_sha256=_RAW_HASH,
        unit=unit,
        period_basis="monthly_flow",
        basis_verified=True,
        aggregate_feature_eligible=False,
        formal_pit_eligible=False,
        availability_basis=_BATCH_BASIS,
        input_role="reported_period_value",
        availability_snapshot_batch_id=pin.for_market("twse").batch_id,
        availability_first_persisted_at=pin.for_market("twse").first_persisted_at,
    )


def _comparator(
    pin: DailyMonthlyRevenueCohortPin,
    current: CurrentObservedMonthlyRevenueInput,
) -> CurrentObservedMonthlyRevenueInput:
    return CurrentObservedMonthlyRevenueInput(
        stock_code="2330",
        period="2025-09",
        revenue=Decimal("100.000"),
        observed_at=current.observed_at,
        source_available_at=current.source_available_at,
        available_at=current.available_at,
        source=current.source,
        source_version=(
            "mops-current-revenue-yoy-comparator.v1:twse:2025-09:"
            "from:2026-09:raw:"
            f"{current.raw_source_version}:derived:sha256:{_sha('c')}"
        ),
        market="twse",
        raw_source_version=current.raw_source_version,
        raw_source_sha256=current.raw_source_sha256,
        unit="TWD",
        period_basis="monthly_flow",
        basis_verified=True,
        aggregate_feature_eligible=False,
        formal_pit_eligible=False,
        availability_basis=current.availability_basis,
        input_role="same_report_prior_year_comparison_baseline",
        parent_report_period="2026-09",
        availability_snapshot_batch_id=pin.for_market("twse").batch_id,
        availability_first_persisted_at=pin.for_market("twse").first_persisted_at,
    )


def _result(
    pin: DailyMonthlyRevenueCohortPin,
    *,
    status: str = "ready",
    with_comparator: bool = True,
    cutoff: datetime = datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc),
) -> CurrentMonthlyRevenueReadResult:
    if status == "missing":
        return CurrentMonthlyRevenueReadResult(
            status="missing",
            stock_code="2330",
            cutoff_at=cutoff,
            latest_period=None,
            diagnostics=("current_monthly_revenue_missing",),
            diagnostic_source_row_count=0,
        )
    if status in {"invalid", "ambiguous", "unavailable"}:
        return CurrentMonthlyRevenueReadResult(
            status=status,
            stock_code="2330",
            cutoff_at=cutoff,
            latest_period="2026-09",
            diagnostics=(f"current_monthly_revenue_provider_{status}",),
            blocked_periods=("2026-09",) if status == "invalid" else (),
            diagnostic_source_row_count=1,
        )
    current = _current(pin)
    return CurrentMonthlyRevenueReadResult(
        status="ready",
        stock_code="2330",
        cutoff_at=cutoff,
        latest_period="2026-09",
        observations=(current,),
        diagnostics=(
            ("current_monthly_revenue_yoy_comparator_missing",)
            if not with_comparator
            else ("current_monthly_revenue_same_report_yoy_baseline_verified:2025-09",)
        ),
        comparison_baseline=_comparator(pin, current) if with_comparator else None,
        comparison_snapshot_sha256=_sha("d") if with_comparator else None,
        diagnostic_source_row_count=1,
        diagnostic_comparator_row_count=1 if with_comparator else 0,
    )


def _finished(
    tmp_path: Path,
    *,
    result: CurrentMonthlyRevenueReadResult | None = None,
    pin: DailyMonthlyRevenueCohortPin | None = None,
) -> tuple[
    FinishedDailyMarketMonthlyRevenueCohortV2,
    FundamentalReadSnapshotReferenceV2,
    DailyMarketMonthlyRevenueFactV2,
]:
    selected_pin = pin if pin is not None else _daily_pin()
    selected_result = result if result is not None else _result(selected_pin)
    result_identity = _result_identity_sha256_v2(
        selected_result,
        cohort_pin=selected_pin,
    )
    clock = _snapshot_clock(tmp_path, selected_pin)
    manifest = make_finished_snapshot_manifest_v2(
        session_id=_sha("e"),
        reader_session_id=_sha("f"),
        source_clock=clock,
        processed_stock_codes=("2330",),
        result_identity_by_stock=(("2330", result_identity),),
        result_status_counts=((selected_result.status, 1),),
        manifest_state="complete",
    )
    snapshot_finished = parse_finished_snapshot_cohort_v2(manifest, clock)
    upstream_reference = make_snapshot_reference_v2(
        snapshot_finished,
        snapshot_root=clock.snapshot_binding.snapshot_root,
        snapshot_id=clock.snapshot_binding.snapshot_id,
    )
    fact = DailyMarketMonthlyRevenueFactV2(
        result=selected_result,
        result_identity_sha256=result_identity,
        cohort_pin=selected_pin,
    )
    finished = _issue_finished_daily_market_monthly_revenue_cohort_v2(
        snapshot_finished=snapshot_finished,
        upstream_reference=upstream_reference,
        facts=(fact,),
    )
    return finished, upstream_reference, fact


def test_fact_keeps_decimal_twd_comparator_roles_and_daily_pin(tmp_path: Path) -> None:
    pin = _daily_pin()
    result = _result(pin)
    result_identity = _result_identity_sha256_v2(result, cohort_pin=pin)
    fact = DailyMarketMonthlyRevenueFactV2(result, result_identity, pin)

    assert fact.result is result
    assert fact.current is result.observations[0]
    assert fact.current.revenue == Decimal("123.450")
    assert fact.current.unit == "TWD"
    assert fact.current.input_role == "reported_period_value"
    assert fact.comparator is result.comparison_baseline
    assert fact.comparator.input_role == "same_report_prior_year_comparison_baseline"
    assert fact.state == "observed"
    assert fact.source_kind == DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND
    assert fact.to_dict()["availability_status"] == DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY
    assert fact.to_dict()["formal_pit_eligible"] is False


def test_fact_classifies_missing_comparator_as_unknown_without_losing_diagnostics() -> None:
    pin = _daily_pin()
    result = _result(pin, with_comparator=False)
    identity = _result_identity_sha256_v2(result, cohort_pin=pin)
    fact = DailyMarketMonthlyRevenueFactV2(result, identity, pin)

    assert fact.state == "unknown"
    assert fact.comparator is None
    assert fact.reason_codes == ("same_report_yoy_comparator_missing_or_unverified",)
    assert fact.result.diagnostics == result.diagnostics


def test_finished_counts_provider_status_and_v1_fact_state_denominators_separately(
    tmp_path: Path,
) -> None:
    finished, _reference, _fact = _finished(
        tmp_path,
        result=_result(_daily_pin(), with_comparator=False),
    )

    assert finished.reader_result_status_counts == (("ready", 1),)
    assert finished.fact_state_counts == (("blocked", 0), ("observed", 0), ("unknown", 1))
    assert sum(count for _state, count in finished.fact_state_counts) == 1
    assert finished.availability_status == "cohort_hour_bound"
    assert finished.source_scope == "current_observed_only"
    assert finished.historical_pit_eligible is False
    assert finished.formal_pit_eligible is False


def test_invalid_provider_status_and_blocked_period_remain_blocked(tmp_path: Path) -> None:
    pin = _daily_pin()
    result = _result(pin, status="invalid")
    identity = _result_identity_sha256_v2(result, cohort_pin=pin)
    fact = DailyMarketMonthlyRevenueFactV2(result, identity, pin)

    assert fact.state == "blocked"
    assert fact.reason_codes == (
        "current_monthly_revenue_period_blocked_by_unverified_revision",
    )
    assert fact.result.blocked_periods == ("2026-09",)


def test_fact_rejects_wrong_unit_and_nonfinite_values() -> None:
    pin = _daily_pin()
    original = _result(pin)
    for changes, reason in (
        ({"unit": "USD"}, "source_unit_or_basis_invalid"),
        ({"revenue": Decimal("NaN")}, "finite_decimal"),
    ):
        row = replace(original.observations[0], **changes)
        result = replace(original, observations=(row,))
        identity = _result_identity_sha256_v2(result, cohort_pin=pin)
        with pytest.raises(DailyMarketMonthlyRevenueCohortV2Error, match=reason):
            DailyMarketMonthlyRevenueFactV2(result, identity, pin)


def test_fact_rejects_materialization_or_persist_clock_after_cutoff() -> None:
    pin = _daily_pin()
    original = _result(pin)
    late_cutoff = datetime(2026, 10, 14, 11, 10, tzinfo=_TAIPEI)
    result = replace(original, cutoff_at=late_cutoff)
    identity = _result_identity_sha256_v2(result, cohort_pin=pin)

    with pytest.raises(DailyMarketMonthlyRevenueCohortV2Error, match="clock_after_cutoff"):
        DailyMarketMonthlyRevenueFactV2(result, identity, pin)

    future_pin = _future_daily_pin()
    for status in ("missing", "unavailable"):
        no_row_result = _result(future_pin, status=status)
        no_row_identity = _result_identity_sha256_v2(
            no_row_result,
            cohort_pin=future_pin,
        )
        with pytest.raises(
            DailyMarketMonthlyRevenueCohortV2Error,
            match="cohort_hour_after_cutoff",
        ):
            DailyMarketMonthlyRevenueFactV2(
                no_row_result,
                no_row_identity,
                future_pin,
            )


def test_fact_rejects_another_batch_even_when_result_hash_is_recomputed() -> None:
    pin = _daily_pin()
    result = _result(pin)
    other_pin = _daily_pin("other")
    identity = _result_identity_sha256_v2(result, cohort_pin=other_pin)

    with pytest.raises(DailyMarketMonthlyRevenueCohortV2Error, match="batch_binding_mismatch"):
        DailyMarketMonthlyRevenueFactV2(result, identity, other_pin)


def test_finished_issuer_requires_exact_result_ledger_and_complete_order(tmp_path: Path) -> None:
    finished, reference, fact = _finished(tmp_path)
    assert finished.declared_stock_codes == ("2330",)

    with pytest.raises(DailyMarketMonthlyRevenueCohortV2Error, match="private_issuer"):
        FinishedDailyMarketMonthlyRevenueCohortV2(
            snapshot_finished=finished.snapshot_finished,
            upstream_reference=reference,
            facts=(fact,),
            result_identity_by_stock=finished.result_identity_by_stock,
            fact_identity_by_stock=finished.fact_identity_by_stock,
            reader_result_status_counts=finished.reader_result_status_counts,
            fact_state_counts=finished.fact_state_counts,
            source_content_identity_sha256=finished.source_content_identity_sha256,
            finished_cohort_identity_sha256=finished.finished_cohort_identity_sha256,
            _issuer=None,
        )
    with pytest.raises(DailyMarketMonthlyRevenueCohortV2Error, match="fact_coverage"):
        _issue_finished_daily_market_monthly_revenue_cohort_v2(
            snapshot_finished=finished.snapshot_finished,
            upstream_reference=reference,
            facts=(),
        )

    object.__setattr__(fact, "result", _result(_daily_pin(), with_comparator=False))
    with pytest.raises(
        DailyMarketMonthlyRevenueCohortV2Error,
        match="fact_result_identity_mismatch",
    ):
        _issue_finished_daily_market_monthly_revenue_cohort_v2(
            snapshot_finished=finished.snapshot_finished,
            upstream_reference=reference,
            facts=(fact,),
        )

    valid_pin = _daily_pin()
    missing_result = _result(valid_pin, status="missing")
    missing_finished, _old_reference, missing_fact = _finished(
        tmp_path,
        result=missing_result,
        pin=valid_pin,
    )
    future_pin = _future_daily_pin()
    future_clock = missing_finished.snapshot_finished.source_clock
    object.__setattr__(future_clock, "cohort_pin", future_pin)
    future_reference = make_snapshot_reference_v2(
        missing_finished.snapshot_finished,
        snapshot_root=future_clock.snapshot_binding.snapshot_root,
        snapshot_id=future_clock.snapshot_binding.snapshot_id,
    )
    with pytest.raises(
        DailyMarketMonthlyRevenueCohortV2Error,
        match="finished_cohort_hour_after_cutoff",
    ):
        _issue_finished_daily_market_monthly_revenue_cohort_v2(
            snapshot_finished=missing_finished.snapshot_finished,
            upstream_reference=future_reference,
            facts=(missing_fact,),
        )


def test_v3_reference_round_trip_requires_external_anchor_and_stays_unverified(
    tmp_path: Path,
) -> None:
    finished, upstream_reference, _fact = _finished(tmp_path)
    reference = DailyMarketMonthlyRevenueSourceReferenceV3.from_finished(
        finished,
        upstream_reference=upstream_reference,
    )
    raw = reference.to_json().encode("utf-8")
    external_sha = sha256(raw).hexdigest()

    restored = decode_daily_market_monthly_revenue_source_reference_v3(
        raw,
        expected_reference_sha256=external_sha,
    )
    assert type(restored) is UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3
    assert restored.reference == reference
    assert restored.external_reference_sha256 == external_sha
    assert restored.reference.cohort_pin == finished.cohort_pin
    assert restored.reference.fact_identity_by_stock == finished.fact_identity_by_stock
    assert restored.reference.result_identity_by_stock == finished.result_identity_by_stock
    assert restored.reference.fact_state_counts == finished.fact_state_counts
    assert restored.reference.finished_cohort_identity_sha256 == finished.identity_sha256
    assert not hasattr(restored, "verified")


def test_v3_reference_rejects_untrusted_outer_and_nested_upstream_hashes(
    tmp_path: Path,
) -> None:
    finished, upstream_reference, _fact = _finished(tmp_path)
    reference = DailyMarketMonthlyRevenueSourceReferenceV3.from_finished(
        finished,
        upstream_reference=upstream_reference,
    )
    raw = reference.to_json().encode("utf-8")
    with pytest.raises(DailyMarketMonthlyRevenueCohortV2Error, match="external_reference_sha_mismatch"):
        decode_daily_market_monthly_revenue_source_reference_v3(
            raw,
            expected_reference_sha256=_sha("f"),
        )

    payload = reference.to_dict()
    payload["upstream_reference_sha256"] = _sha("f")
    tampered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    with pytest.raises(ValueError, match="external_sha_mismatch"):
        decode_daily_market_monthly_revenue_source_reference_v3(
            tampered,
            expected_reference_sha256=sha256(tampered).hexdigest(),
        )

    future_pin = _future_daily_pin()
    future_upstream = replace(
        upstream_reference,
        daily_cohort_sha256=future_pin.cohort_sha256,
    )
    future_upstream_raw = encode_snapshot_reference_v2(future_upstream)
    future_upstream_sha = sha256(future_upstream_raw).hexdigest()
    future_payload = reference.to_dict()
    future_payload["upstream_reference"] = future_upstream.to_dict()
    future_payload["upstream_reference_sha256"] = future_upstream_sha
    future_payload["cohort_pin"] = future_pin.to_dict()
    future_result_ledger = reference.result_identity_by_stock
    future_fact_ledger = reference.fact_identity_by_stock
    future_content_identity = sha256(
        json.dumps(
            {
                "schema_version": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_REFERENCE_V3_SCHEMA,
                "source_kind": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_KIND,
                "source_scope": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE,
                "availability_status": DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY,
                "historical_pit_eligible": False,
                "formal_pit_eligible": False,
                "decision_cutoff": reference.decision_cutoff,
                "upstream_source_content_identity_sha256": (
                    future_upstream.source_content_identity_sha256
                ),
                "daily_cohort_pin": future_pin.to_dict(),
                "declared_stock_codes": list(reference.declared_stock_codes),
                "result_identity_by_stock": [list(item) for item in future_result_ledger],
                "fact_identity_by_stock": [list(item) for item in future_fact_ledger],
                "reader_result_status_counts": [
                    list(item) for item in reference.reader_result_status_counts
                ],
                "fact_state_counts": [list(item) for item in reference.fact_state_counts],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    future_payload["source_content_identity_sha256"] = future_content_identity
    future_payload["finished_cohort_identity_sha256"] = _reference_finished_identity(
        upstream_reference=future_upstream,
        upstream_reference_sha256=future_upstream_sha,
        source_content_identity_sha256=future_content_identity,
        result_identity_by_stock=future_result_ledger,
        fact_identity_by_stock=future_fact_ledger,
        reader_result_status_counts=reference.reader_result_status_counts,
        fact_state_counts=reference.fact_state_counts,
    )
    future_identity_payload = {
        key: value
        for key, value in future_payload.items()
        if key != "identity_sha256"
    }
    future_payload["identity_sha256"] = sha256(
        json.dumps(
            future_identity_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    future_raw = json.dumps(
        future_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    with pytest.raises(
        DailyMarketMonthlyRevenueCohortV2Error,
        match="cohort_hour_after_cutoff",
    ):
        decode_daily_market_monthly_revenue_source_reference_v3(
            future_raw,
            expected_reference_sha256=sha256(future_raw).hexdigest(),
        )


def test_v3_reference_rejects_count_or_fact_ledger_tampering_under_old_anchor(
    tmp_path: Path,
) -> None:
    finished, upstream_reference, _fact = _finished(tmp_path)
    reference = DailyMarketMonthlyRevenueSourceReferenceV3.from_finished(
        finished,
        upstream_reference=upstream_reference,
    )
    payload = reference.to_dict()
    payload["fact_state_counts"] = [["blocked", 1], ["observed", 0], ["unknown", 0]]
    tampered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    with pytest.raises(DailyMarketMonthlyRevenueCohortV2Error, match="external_reference_sha_mismatch"):
        decode_daily_market_monthly_revenue_source_reference_v3(
            tampered,
            expected_reference_sha256=reference.external_reference_sha256,
        )


def test_v3_codec_rejects_v1_unknown_duplicate_and_deep_payloads(
    tmp_path: Path,
) -> None:
    finished, upstream_reference, _fact = _finished(tmp_path)
    reference = DailyMarketMonthlyRevenueSourceReferenceV3.from_finished(
        finished,
        upstream_reference=upstream_reference,
    )
    canonical = reference.to_json().encode("utf-8")
    payload = reference.to_dict()
    payload["schema_version"] = "daily-market-monthly-revenue-source-reference.v1"
    v1_raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    extra_payload = reference.to_dict()
    extra_payload["latest"] = "must-not-be-inferred"
    extra_raw = json.dumps(
        extra_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    duplicate_raw = b'{"schema_version":"bad",' + canonical[1:]
    depth = 25
    deep_raw = b"[" * depth + b"0" + b"]" * depth

    for raw in (v1_raw, extra_raw, duplicate_raw, deep_raw):
        with pytest.raises(DailyMarketMonthlyRevenueCohortV2Error):
            decode_daily_market_monthly_revenue_source_reference_v3(
                raw,
                expected_reference_sha256=sha256(raw).hexdigest(),
            )
