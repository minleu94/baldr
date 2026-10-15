from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app_module.market_session_cadence import MarketSessionCadence
from app_module.recommendation.input_preparation import RecommendationInputSession
from app_module.recommendation.source_fact_projection import project_current_monthly_revenue_records
from data_module.current_official_valuation import (
    CurrentOfficialValuationReadProvider,
    capture_current_official_valuation,
)
from data_module.current_fundamental_snapshots import (
    COLUMNS,
    TABLE,
    ensure_current_observation_schema,
    insert_observations,
    monthly_snapshot_rows,
    normalize_current_observation,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DailySourceBatchValidation,
    DailySourceSnapshotFileReader,
    DailySourceSnapshotRecord,
    DailySourceUseAcceptance,
    DailySourceUseScope,
    DailySourceValidationCheck,
    write_daily_source_snapshot,
)
from data_module.official_trading_calendar import CalendarObservation
from data_module.recommendation_current_fundamental_provider import (
    DEFAULT_OFFICIAL_CALENDAR_CACHE_ROOT,
    RecommendationCurrentFundamentalProvider,
)
from data_module.monthly_revenue_snapshot_harvester import (
    parse_mops_monthly_revenue_snapshot_html,
    write_mops_snapshot_csv,
)
from decision_module.recommendation.evaluate import RecommendationEvaluator
from tests.test_monthly_revenue_snapshot_harvester import MOPS_SAMPLE_HTML


UTC = timezone.utc
FROZEN = datetime(2026, 10, 4, 1, 0, tzinfo=UTC)
OBSERVED = datetime(2026, 10, 4, 0, 30, tzinfo=UTC)
RAW_HASH = "a" * 64


def _insert_verified_monthly_row(
    database: Path,
    observed_at: datetime,
    *,
    include_legacy_row: bool = False,
) -> None:
    csv_path = database.with_suffix(".csv")
    raw_version = f"mops-static-twse-2026-04-sha256-{RAW_HASH}"
    csv_path.write_text(
        "stock_code,period,fetched_at,current_month_revenue,previous_year_month_revenue,source_version,market,source\n"
        f"2330,2026-04,{observed_at.isoformat()},123,90,{raw_version},twse,mops.monthly_revenue_static_snapshot\n",
        encoding="utf-8",
    )
    rows = monthly_snapshot_rows(
        csv_path,
        verified_source_versions=frozenset({raw_version}),
    )
    # The fixture represents a verified local normalization with no defensible
    # official body-completion clock. The raw source hash remains bound in v2.
    for row in rows:
        row["observed_at"] = observed_at.isoformat()
    if include_legacy_row:
        revenue_row = next(row for row in rows if row["item_code"] == "revenue")
        legacy = dict(revenue_row)
        legacy["source_version"] = raw_version
        legacy["observed_at"] = (observed_at - timedelta(days=1)).isoformat()
        legacy["period_basis"] = "unknown"
        legacy["basis_verified"] = "0"
        rows.insert(0, legacy)
    with sqlite3.connect(database) as connection:
        ensure_current_observation_schema(connection)
        assert insert_observations(connection, rows) == len(rows)


def _official_monthly_row(
    tmp_path: Path,
    *,
    period: str = "2026-04",
    source_available_at: datetime,
    observed_at: datetime,
    source_hash: str,
    revenue_thousands: int,
) -> dict[str, str]:
    source_version = (
        f"mops-static-snapshot.v2:twse:{period}:body_completed_at:"
        f"{source_available_at.isoformat()}:sha256:{source_hash}"
    )
    csv_path = tmp_path / f"monthly-{source_hash[:8]}.csv"
    csv_path.write_text(
        "stock_code,period,fetched_at,current_month_revenue,previous_year_month_revenue,source_version,market,source\n"
        f"2330,{period},{source_available_at.isoformat()},{revenue_thousands},"
        f"900,{source_version},twse,mops.monthly_revenue_static_snapshot\n",
        encoding="utf-8",
    )
    rows = monthly_snapshot_rows(
        csv_path,
        verified_source_versions=frozenset({source_version}),
    )
    for row in rows:
        row["observed_at"] = observed_at.isoformat()
    return next(row for row in rows if row["item_code"] == "revenue")


def _write_daily_availability_snapshot(
    root: Path,
    *,
    raw_bytes: bytes,
    raw_source_version: str,
    source_available_at: datetime,
    period: str = "2026-04",
    batch_id: str = "provider-batch-2026-10-02",
) -> DailySourceUseAcceptance:
    scope = DailySourceUseScope(
        dataset_id="fundamental_current_observations.monthly_revenue",
        source_id="mops.monthly_revenue_static_snapshot",
        market="twse",
        parser_version="mops-current-revenue-normalizer.v2",
        source_schema_version="mops-static-snapshot.v2",
        unit="TWD",
        intended_use="recommendation_current_fundamental",
    )
    acceptance = DailySourceUseAcceptance(
        scope=scope,
        acceptance_id="provider-test-mops-monthly-acceptance",
        accepted_at=datetime(2026, 10, 2, 8, 0, tzinfo=ZoneInfo("Asia/Taipei")),
        official_source_endpoint="https://mops.twse.com.tw/mops/web/t05st10_ifrs",
        document_chain=("mops-monthly-revenue", "recommendation-current-fundamental"),
        acceptance_evidence_ref="test-fixture:accepted-source-use",
        authorization_scope="recommendation_current_fundamental only",
        time_basis_policy=DAILY_SOURCE_TIME_BASIS_POLICY,
    )
    record = DailySourceSnapshotRecord(
        stock_code="2330",
        market="twse",
        period=period,
        source_version=raw_source_version,
        raw_source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        unit="TWD",
        official_timestamp=source_available_at,
        official_timestamp_original_text=source_available_at.isoformat(),
        official_timestamp_original_timezone=(
            source_available_at.strftime("%z")[:3]
            + ":"
            + source_available_at.strftime("%z")[3:]
        ),
    )

    def passed(check_id: str) -> DailySourceValidationCheck:
        return DailySourceValidationCheck(check_id, "pass", f"{check_id}_verified")

    validation = DailySourceBatchValidation(
        validation_id=f"provider-validation-{batch_id}",
        expected_partition_ids=("twse-monthly-revenue",),
        successful_partition_ids=("twse-monthly-revenue",),
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
    clock_values = iter(
        (
            datetime(2026, 10, 2, 10, 10, tzinfo=ZoneInfo("Asia/Taipei")),
            datetime(2026, 10, 2, 10, 20, tzinfo=ZoneInfo("Asia/Taipei")),
            datetime(2026, 10, 2, 10, 25, tzinfo=ZoneInfo("Asia/Taipei")),
            datetime(2026, 10, 2, 10, 30, tzinfo=ZoneInfo("Asia/Taipei")),
        )
    )
    write_daily_source_snapshot(
        root,
        batch_id=batch_id,
        scope=scope,
        use_acceptance=acceptance,
        source_batch_started_at=datetime(
            2026, 10, 2, 9, 55, tzinfo=ZoneInfo("Asia/Taipei")
        ),
        raw_source_bytes=raw_bytes,
        records=(record,),
        validation=validation,
        clock=lambda: next(clock_values),
    )
    return acceptance


def test_monthly_reader_uses_verified_local_observation_and_is_read_only(tmp_path: Path) -> None:
    database = tmp_path / "fundamentals.db"
    _insert_verified_monthly_row(database, OBSERVED)
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
    )
    result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=FROZEN)

    after = hashlib.sha256(database.read_bytes()).hexdigest()
    assert before == after
    assert result.status == "ready"
    assert result.latest_period == "2026-04"
    assert len(result.observations) == 1
    assert result.diagnostic_source_row_count == 1
    assert result.diagnostic_comparator_row_count == 1
    record = result.observations[0]
    assert record.stock_code == "2330"
    assert record.revenue == Decimal("123000")
    assert record.unit == "TWD"
    assert record.period_basis == "monthly_flow"
    assert record.basis_verified is True
    assert record.aggregate_feature_eligible is False
    assert record.source_available_at is None
    assert record.available_at == OBSERVED
    assert record.availability_basis == "local_verified_observation"
    assert record.raw_source_sha256 == RAW_HASH
    assert result.comparison_baseline is not None
    assert result.comparison_baseline.period == "2025-04"
    assert result.comparison_baseline.revenue == Decimal("90000")
    assert result.comparison_baseline.unit == "TWD"
    assert result.comparison_baseline.formal_pit_eligible is False
    assert result.comparison_baseline.availability_basis == "local_verified_observation"
    assert result.comparison_baseline.input_role == "same_report_prior_year_comparison_baseline"
    assert result.comparison_baseline.parent_report_period == "2026-04"
    assert result.comparison_baseline.observed_at == record.observed_at


def test_pinned_daily_batch_is_the_only_source_of_new_hourly_eligibility(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    taipei = ZoneInfo("Asia/Taipei")
    batch_clock = datetime(2026, 10, 2, 10, 5, tzinfo=taipei)
    selected_raw = b"selected exact MOPS body"
    selected_hash = hashlib.sha256(selected_raw).hexdigest()
    selected_version = (
        "mops-static-snapshot.v2:twse:2026-04:body_completed_at:"
        f"{batch_clock.isoformat()}:sha256:{selected_hash}"
    )
    selected_row = _official_monthly_row(
        tmp_path,
        period="2026-04",
        source_available_at=batch_clock,
        observed_at=datetime(2026, 10, 2, 10, 25, tzinfo=taipei),
        source_hash=selected_hash,
        revenue_thousands=150,
    )
    wrong_same_period = _official_monthly_row(
        tmp_path,
        period="2026-04",
        source_available_at=datetime(2026, 10, 2, 10, 15, tzinfo=taipei),
        observed_at=datetime(2026, 10, 2, 10, 26, tzinfo=taipei),
        source_hash="c" * 64,
        revenue_thousands=999,
    )
    wrong_other_period = _official_monthly_row(
        tmp_path,
        period="2026-03",
        source_available_at=datetime(2026, 10, 2, 9, 45, tzinfo=taipei),
        observed_at=datetime(2026, 10, 2, 10, 24, tzinfo=taipei),
        source_hash="d" * 64,
        revenue_thousands=888,
    )
    with sqlite3.connect(database) as connection:
        ensure_current_observation_schema(connection)
        assert insert_observations(
            connection,
            [selected_row, wrong_same_period, wrong_other_period],
        ) == 3
        connection.execute(
            f"UPDATE {TABLE} SET value='NaN' WHERE source_version=?",
            (wrong_same_period["source_version"],),
        )
    with pytest.raises(ValueError):
        normalize_current_observation({**wrong_same_period, "value": "NaN"})

    snapshot_root = tmp_path / "hourly-source-snapshots"
    trusted_acceptance = _write_daily_availability_snapshot(
        snapshot_root,
        raw_bytes=selected_raw,
        raw_source_version=selected_version,
        source_available_at=batch_clock,
    )
    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
        daily_source_snapshot_reader=DailySourceSnapshotFileReader(
            snapshot_root,
            trusted_acceptance=trusted_acceptance,
        ),
    )
    too_early = provider.load_monthly_revenues(
        stock_code="2330",
        cutoff_at=datetime(2026, 10, 2, 10, 30, tzinfo=taipei),
        pinned_daily_batch_id="provider-batch-2026-10-02",
    )
    available = provider.load_monthly_revenues(
        stock_code="2330",
        cutoff_at=datetime(2026, 10, 2, 11, 0, tzinfo=taipei),
        pinned_daily_batch_id="provider-batch-2026-10-02",
    )

    assert too_early.status == "missing"
    assert any(
        "daily_source_snapshot_not_available_at_cutoff:2026-04" in item
        for item in too_early.diagnostics
    )
    assert any(
        "daily_source_snapshot_record_not_in_pinned_batch:2026-04" in item
        for item in too_early.diagnostics
    )
    assert available.status == "ready"
    assert tuple(item.period for item in available.observations) == ("2026-04",)
    record = available.observations[0]
    assert record.revenue == Decimal("150000")
    assert record.raw_source_version == selected_version
    assert record.raw_source_sha256 == selected_hash
    assert record.available_at == datetime(2026, 10, 2, 11, 0, tzinfo=taipei)
    assert record.availability_basis == "official_timestamp_and_successful_batch_completion"
    assert record.availability_snapshot_batch_id == "provider-batch-2026-10-02"
    assert record.availability_first_persisted_at == datetime(
        2026, 10, 2, 10, 10, tzinfo=taipei
    )
    assert any(
        "daily_source_snapshot_record_not_in_pinned_batch:2026-03" in item
        for item in available.diagnostics
    )


def test_pinned_materialized_comparator_preserves_hour_gate_and_its_later_observation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    taipei = ZoneInfo("Asia/Taipei")
    captured = datetime(2026, 10, 2, 10, 5, tzinfo=taipei)
    observed = datetime(2026, 10, 2, 10, 25, tzinfo=taipei)
    raw = b"selected report with materialized prior-year comparator"
    digest = hashlib.sha256(raw).hexdigest()
    main = _official_monthly_row(
        tmp_path, source_available_at=captured, observed_at=observed,
        source_hash=digest, revenue_thousands=150,
    )
    csv_path = tmp_path / f"monthly-{digest[:8]}.csv"
    raw_version = f"mops-static-snapshot.v2:twse:2026-04:body_completed_at:{captured.isoformat()}:sha256:{digest}"
    rows = monthly_snapshot_rows(csv_path, verified_source_versions={raw_version})
    for row in rows:
        row["observed_at"] = observed.isoformat()
    assert rows[0]["source_version"] == main["source_version"]
    with sqlite3.connect(database) as connection:
        assert insert_observations(connection, rows) == 2
    snapshot_root = tmp_path / "snapshots"
    acceptance = _write_daily_availability_snapshot(
        snapshot_root, raw_bytes=raw, raw_source_version=raw_version, source_available_at=captured,
    )
    provider = RecommendationCurrentFundamentalProvider(
        db_file=database, output_root=tmp_path / "unused",
        daily_source_snapshot_reader=DailySourceSnapshotFileReader(snapshot_root, trusted_acceptance=acceptance),
    )
    gate = datetime(2026, 10, 2, 11, 0, tzinfo=taipei)
    result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=gate, pinned_daily_batch_id="provider-batch-2026-10-02")
    assert result.comparison_baseline is not None
    assert result.comparison_baseline.revenue == Decimal("900000")
    assert result.comparison_baseline.available_at == result.observations[0].available_at == gate
    assert result.comparison_baseline.source_available_at == captured
    assert result.comparison_baseline.observed_at == observed
    assert result.comparison_baseline.availability_snapshot_batch_id == "provider-batch-2026-10-02"
    assert not result.comparison_baseline.formal_pit_eligible
    assert provider.load_monthly_revenues(stock_code="2330", cutoff_at=gate-timedelta(microseconds=1), pinned_daily_batch_id="provider-batch-2026-10-02").comparison_baseline is None
    later = gate + timedelta(minutes=5)
    with sqlite3.connect(database) as connection:
        connection.execute(f"UPDATE {TABLE} SET observed_at=? WHERE item_code='revenue_yoy_comparator'", (later.isoformat(),))
    assert provider.load_monthly_revenues(stock_code="2330", cutoff_at=gate, pinned_daily_batch_id="provider-batch-2026-10-02").comparison_baseline is None
    later_result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=later, pinned_daily_batch_id="provider-batch-2026-10-02")
    assert later_result.comparison_baseline is not None
    assert later_result.comparison_baseline.available_at == later


def test_pinned_batch_never_backdates_late_current_or_comparator_materialization(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    taipei = ZoneInfo("Asia/Taipei")
    batch_clock = datetime(2026, 10, 2, 10, 5, tzinfo=taipei)
    current_observed = datetime(2026, 10, 2, 12, 15, tzinfo=taipei)
    comparator_observed = datetime(2026, 10, 2, 14, 15, tzinfo=taipei)
    raw = b"selected report materialized after its availability batch"
    digest = hashlib.sha256(raw).hexdigest()
    raw_version = (
        "mops-static-snapshot.v2:twse:2026-04:body_completed_at:"
        f"{batch_clock.isoformat()}:sha256:{digest}"
    )
    current = _official_monthly_row(
        tmp_path,
        period="2026-04",
        source_available_at=batch_clock,
        observed_at=current_observed,
        source_hash=digest,
        revenue_thousands=150,
    )
    csv_path = tmp_path / f"monthly-{digest[:8]}.csv"
    rows = monthly_snapshot_rows(
        csv_path,
        verified_source_versions=frozenset({raw_version}),
    )
    current_rows = [row for row in rows if row["item_code"] == "revenue"]
    comparator_rows = [
        row for row in rows if row["item_code"] == "revenue_yoy_comparator"
    ]
    assert len(current_rows) == 1
    assert len(comparator_rows) == 1
    assert current_rows[0]["source_version"] == current["source_version"]
    current_rows[0]["observed_at"] = current_observed.isoformat()
    comparator_rows[0]["observed_at"] = comparator_observed.isoformat()
    with sqlite3.connect(database) as connection:
        ensure_current_observation_schema(connection)
        assert insert_observations(connection, rows) == 2

    snapshot_root = tmp_path / "snapshots"
    acceptance = _write_daily_availability_snapshot(
        snapshot_root,
        raw_bytes=raw,
        raw_source_version=raw_version,
        source_available_at=batch_clock,
    )
    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "unused",
        daily_source_snapshot_reader=DailySourceSnapshotFileReader(
            snapshot_root,
            trusted_acceptance=acceptance,
        ),
    )
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    before_current_materialization = provider.load_monthly_revenues(
        stock_code="2330",
        cutoff_at=current_observed - timedelta(microseconds=1),
        pinned_daily_batch_id="provider-batch-2026-10-02",
    )
    at_current_materialization = provider.load_monthly_revenues(
        stock_code="2330",
        cutoff_at=current_observed,
        pinned_daily_batch_id="provider-batch-2026-10-02",
    )
    before_comparator_materialization = provider.load_monthly_revenues(
        stock_code="2330",
        cutoff_at=comparator_observed - timedelta(microseconds=1),
        pinned_daily_batch_id="provider-batch-2026-10-02",
    )
    at_comparator_materialization = provider.load_monthly_revenues(
        stock_code="2330",
        cutoff_at=comparator_observed,
        pinned_daily_batch_id="provider-batch-2026-10-02",
    )
    after = hashlib.sha256(database.read_bytes()).hexdigest()

    assert before == after
    assert before_current_materialization.status == "missing"
    assert at_current_materialization.status == "ready"
    assert at_current_materialization.comparison_baseline is None
    current_record = at_current_materialization.observations[0]
    assert current_record.revenue == Decimal("150000")
    assert current_record.available_at == current_observed
    assert current_record.available_at >= current_record.observed_at
    assert current_record.available_at >= datetime(
        2026, 10, 2, 11, 0, tzinfo=taipei
    )
    assert current_record.availability_snapshot_batch_id == "provider-batch-2026-10-02"
    assert current_record.availability_first_persisted_at == datetime(
        2026, 10, 2, 10, 10, tzinfo=taipei
    )
    assert before_comparator_materialization.status == "ready"
    assert before_comparator_materialization.comparison_baseline is None
    assert at_comparator_materialization.status == "ready"
    assert at_comparator_materialization.comparison_baseline is not None
    baseline = at_comparator_materialization.comparison_baseline
    assert baseline.revenue == Decimal("900000")
    assert baseline.observed_at == comparator_observed
    assert baseline.available_at == comparator_observed
    assert baseline.available_at >= current_record.available_at
    assert baseline.availability_snapshot_batch_id == "provider-batch-2026-10-02"
    assert not baseline.formal_pit_eligible


def test_pinned_batch_without_reader_fails_closed_and_unpinned_reader_is_not_guessed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    _insert_verified_monthly_row(database, OBSERVED)

    pinned_without_reader = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
    ).load_monthly_revenues(
        stock_code="2330",
        cutoff_at=FROZEN,
        pinned_daily_batch_id="caller-pinned-batch",
    )
    assert pinned_without_reader.status == "unavailable"
    assert pinned_without_reader.diagnostics == (
        "daily_source_snapshot_port_missing_for_pinned_batch",
    )

    class _ReaderThatMustNotBeSelected:
        def read_snapshot(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("un-pinned legacy calls must not guess a daily batch")

    unpinned = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
        daily_source_snapshot_reader=_ReaderThatMustNotBeSelected(),  # type: ignore[arg-type]
    ).load_monthly_revenues(stock_code="2330", cutoff_at=FROZEN)

    assert unpinned.status == "ready"
    assert unpinned.observations[0].availability_basis == "local_verified_observation"
    assert unpinned.observations[0].availability_snapshot_batch_id is None


def test_raw_pair_yoy_fallback_projects_negative_current_observed_growth(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    output_root = tmp_path / "output"
    capture_root = output_root / "monthly_revenue_mops_snapshots"
    html = MOPS_SAMPLE_HTML.replace("195,211,000", "150,000,000")
    raw_sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    raw_source_version = (
        "mops-static-snapshot.v2:twse:2026-04:body_completed_at:"
        f"{OBSERVED.isoformat()}:sha256:{raw_sha256}"
    )
    parsed_rows, diagnostics = parse_mops_monthly_revenue_snapshot_html(
        html,
        market="twse",
        period="2026-04",
        fetched_at=OBSERVED.isoformat(),
        source_version=raw_source_version,
    )
    assert diagnostics == ()
    raw_html_path = capture_root / "raw_html" / "twse_2026-04.html"
    raw_html_path.parent.mkdir(parents=True, exist_ok=True)
    raw_html_path.write_bytes(html.encode("utf-8"))
    csv_path = capture_root / "mops_monthly_revenue_snapshot_fixture.csv"
    write_mops_snapshot_csv(csv_path, parsed_rows)

    normalized = monthly_snapshot_rows(
        csv_path,
        verified_source_versions=frozenset({raw_source_version}),
    )
    current_row = next(row for row in normalized if row["item_code"] == "revenue")
    current_row["observed_at"] = OBSERVED.isoformat()
    with sqlite3.connect(database) as connection:
        ensure_current_observation_schema(connection)
        # Simulate a pre-comparator DB while keeping its exact HTML/CSV source pair.
        assert insert_observations(connection, [current_row]) == 1

    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=output_root,
        monthly_source_root=output_root,
    )
    result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=FROZEN)

    assert result.status == "ready"
    assert result.comparison_baseline is not None
    assert result.comparison_baseline.source_version.startswith(
        "mops-current-revenue-yoy-comparator.v1:twse:2025-04:from:2026-04:raw:"
    )
    assert result.comparison_baseline.source_version.endswith(
        ":verified-csv-sha256:"
        + hashlib.sha256(csv_path.read_bytes()).hexdigest()
    )
    facts = project_current_monthly_revenue_records(
        (*result.observations, result.comparison_baseline), (), stock_code="2330"
    )
    assert [record.input_role for record in facts.records] == [
        "same_report_prior_year_comparison_baseline",
        "reported_period_value",
    ]
    yoy = RecommendationEvaluator._revenue_yoy(
        facts,
        cutoff=date(2026, 10, 4),
        stock_code="2330",
        fundamental_input_scope="natural_current_observation",
        current_observation_cutoff_at=FROZEN,
    )
    assert yoy == Decimal("-6.25")


def test_later_comparator_observation_is_used_only_after_its_own_clock(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    _insert_verified_monthly_row(database, OBSERVED)
    later_clock = FROZEN - timedelta(minutes=15)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE fundamental_current_observations SET observed_at=? "
            "WHERE stock_code='2330' AND item_code='revenue_yoy_comparator'",
            (later_clock.isoformat(),),
        )
    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
    )

    result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=FROZEN)

    assert result.status == "ready"
    assert result.comparison_baseline is not None
    assert result.comparison_baseline.observed_at == later_clock
    assert result.comparison_baseline.observed_at != result.observations[-1].observed_at


def test_late_comparator_is_hidden_before_its_own_observation_clock(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    _insert_verified_monthly_row(database, OBSERVED)
    later_clock = FROZEN + timedelta(minutes=1)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE fundamental_current_observations SET observed_at=? "
            "WHERE stock_code='2330' AND item_code='revenue_yoy_comparator'",
            (later_clock.isoformat(),),
        )
    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
    )

    result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=FROZEN)

    assert result.status == "ready"
    assert result.comparison_baseline is None
    assert any(
        "comparator_observed_after_invocation_freeze" in item
        for item in result.diagnostics
    )
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("fundamental_current_observations",)]


def test_monthly_reader_hides_rows_materialized_after_invocation_freeze(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    _insert_verified_monthly_row(database, FROZEN.replace(minute=1))
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
    )

    result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=FROZEN)

    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert result.status == "missing"
    assert result.observations == ()


def test_monthly_reader_keeps_v1_diagnostic_but_uses_hash_bound_v2_upgrade(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    _insert_verified_monthly_row(database, OBSERVED, include_legacy_row=True)
    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
    )

    result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=FROZEN)

    assert result.status == "ready"
    assert result.latest_period == "2026-04"
    assert len(result.observations) == 1
    assert result.diagnostic_source_row_count == 2
    assert result.diagnostic_comparator_row_count == 1
    assert any(
        "unverified_revision_superseded" in item for item in result.diagnostics
    )
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM fundamental_current_observations "
            "WHERE period='2026-04'"
        ).fetchone()[0] == 2


def test_newer_unverified_monthly_revision_still_blocks_the_period(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    _insert_verified_monthly_row(database, OBSERVED)
    conflict = {
        "stock_code": "2330",
        "kind": "monthly_revenue",
        "period": "2026-04",
        "as_of_date": "2026-04-30",
        "item_code": "revenue",
        "item_name": "monthly revenue",
        "value": "999000",
        "unit": "TWD",
        "observed_at": (FROZEN - timedelta(seconds=1)).isoformat(),
        "source": "mops.monthly_revenue_static_snapshot",
        "source_version": f"mops-static-twse-2026-04-sha256-{'b' * 64}",
        "market": "twse",
        "period_basis": "unknown",
        "basis_verified": "0",
        "aggregate_feature_eligible": "0",
        "source_available_at": "",
    }
    with sqlite3.connect(database) as connection:
        assert insert_observations(connection, [conflict]) == 1
    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
    )

    result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=FROZEN)

    assert result.status == "invalid"
    assert result.latest_period == "2026-04"
    assert any("unverified_revision_blocks_period" in item for item in result.diagnostics)


def test_newer_official_body_supersedes_different_hash_legacy_and_wins_revision_order(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    # The legacy row is unverified and has a different raw hash.  Two verified
    # bodies are then materialized out of source order: the older body was
    # re-normalized later, so available_at alone would incorrectly select it.
    older_body = _official_monthly_row(
        tmp_path,
        source_available_at=FROZEN - timedelta(days=1),
        observed_at=FROZEN - timedelta(seconds=1),
        source_hash="c" * 64,
        revenue_thousands=111,
    )
    newer_body = _official_monthly_row(
        tmp_path,
        source_available_at=FROZEN - timedelta(hours=12),
        observed_at=FROZEN - timedelta(minutes=10),
        source_hash="d" * 64,
        revenue_thousands=222,
    )
    legacy = dict(older_body)
    legacy["value"] = "999000"
    legacy["source_version"] = f"mops-static-twse-2026-04-sha256-{'b' * 64}"
    legacy["observed_at"] = (FROZEN - timedelta(days=2)).isoformat()
    legacy["period_basis"] = "unknown"
    legacy["basis_verified"] = "0"
    legacy["aggregate_feature_eligible"] = "0"
    legacy["source_available_at"] = ""
    legacy["unit"] = "TWD"
    with sqlite3.connect(database) as connection:
        ensure_current_observation_schema(connection)
        assert insert_observations(connection, [legacy, older_body, newer_body]) == 3

    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
    )
    result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=FROZEN)

    assert result.status == "ready"
    assert result.latest_period == "2026-04"
    assert len(result.observations) == 1
    assert result.observations[0].revenue == Decimal("222000")
    assert result.observations[0].source_available_at == FROZEN - timedelta(hours=12)
    assert any("unverified_revision_superseded" in item for item in result.diagnostics)


def test_blocked_prior_year_period_is_not_selected_as_a_yoy_baseline(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    latest = _official_monthly_row(
        tmp_path,
        period="2026-04",
        source_available_at=FROZEN - timedelta(days=1),
        observed_at=FROZEN - timedelta(hours=1),
        source_hash="f" * 64,
        revenue_thousands=150,
    )
    prior_verified = _official_monthly_row(
        tmp_path,
        period="2025-04",
        source_available_at=datetime(2025, 5, 10, 1, 0, tzinfo=UTC),
        observed_at=datetime(2025, 5, 10, 1, 5, tzinfo=UTC),
        source_hash="1" * 64,
        revenue_thousands=100,
    )
    prior_unverified = dict(prior_verified)
    prior_unverified["value"] = "999000"
    prior_unverified["source_version"] = (
        f"mops-static-twse-2025-04-sha256-{'2' * 64}"
    )
    prior_unverified["observed_at"] = (FROZEN - timedelta(days=1)).isoformat()
    prior_unverified["period_basis"] = "unknown"
    prior_unverified["basis_verified"] = "0"
    prior_unverified["aggregate_feature_eligible"] = "0"
    prior_unverified["source_available_at"] = ""
    with sqlite3.connect(database) as connection:
        ensure_current_observation_schema(connection)
        assert (
            insert_observations(
                connection,
                [latest, prior_verified, prior_unverified],
            )
            == 3
        )

    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
    )
    result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=FROZEN)

    assert result.status == "ready"
    assert result.latest_period == "2026-04"
    assert result.blocked_periods == ("2025-04",)
    assert tuple(item.period for item in result.observations) == ("2026-04",)
    assert any("unverified_revision_blocks_period:2025-04" in item for item in result.diagnostics)


def test_monthly_reader_ignores_source_capture_after_freeze_even_if_local_clock_is_before(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    source_time = FROZEN + timedelta(seconds=1)
    row = _official_monthly_row(
        tmp_path,
        source_available_at=source_time,
        observed_at=FROZEN - timedelta(seconds=1),
        source_hash="e" * 64,
        revenue_thousands=123,
    )
    # Model a malformed/out-of-contract row found in an existing store.  The
    # normal insertion validator correctly rejects source time after local
    # observation, but the read path must independently enforce its freeze.
    with sqlite3.connect(database) as connection:
        ensure_current_observation_schema(connection)
        connection.execute(
            f"INSERT INTO {TABLE} ({','.join(COLUMNS)}) "
            f"VALUES ({','.join('?' for _ in COLUMNS)})",
            tuple(row[column] or None for column in COLUMNS),
        )

    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
    )
    result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=FROZEN)

    assert result.status == "missing"
    assert result.observations == ()


class _FakeOfficialValuationProvider:
    expected_market_dates: list[date] = []
    pe_value = Decimal("12.34")

    def __init__(self, output_root: Path, *, clock) -> None:
        self.output_root = output_root
        self.clock = clock
        self.expected_market_date: date | None = None

    def read_current(
        self,
        stock_code: str,
        as_of_date: date,
        *,
        expected_market_date: date,
    ):
        self.expected_market_date = expected_market_date
        self.expected_market_dates.append(expected_market_date)
        observation_date = self.expected_market_date
        observation = SimpleNamespace(
            stock_code=stock_code,
            metric_name="pe",
            value=self.pe_value,
            as_of_date=observation_date,
            available_at=self.clock() - timedelta(seconds=1),
            source="twse.openapi.bwibbu_all",
            source_version="official-current-valuation.v1:run:1",
            market="twse",
            raw_response_sha256="sha256:" + RAW_HASH,
            formal_pit_eligible=False,
        )
        return SimpleNamespace(
            status="ready",
            observations=(observation,),
            diagnostics=(),
        )


class _FakeOfficialTradingCalendar:
    def __init__(self, _database: Path, *, latest_session: date) -> None:
        self.latest_session = latest_session
        self.calls: list[tuple[date, bool]] = []

    def is_official_trading_day(
        self,
        target_date: date,
        allow_online_probe: bool = True,
    ) -> tuple[bool, str]:
        self.calls.append((target_date, allow_online_probe))
        if target_date.weekday() >= 5:
            return False, "weekend_closed"
        if target_date == self.latest_session:
            return True, "twstock_db_market_indices_evidence"
        if target_date < self.latest_session:
            return True, "fixture_prior_session"
        return False, "fixture_no_session"


class _AppOfficialCalendar:
    def __init__(self, sessions: tuple[date, ...]) -> None:
        self.sessions = sessions

    def read_range(
        self,
        *,
        start_date: str,
        end_date: str,
        decision_at: datetime,
        observed_at: datetime,
        observation_clock: CalendarObservation,
    ):
        assert isinstance(observation_clock, CalendarObservation)
        assert observation_clock.effective_at == observed_at
        assert observed_at.utcoffset() is not None
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        dates = tuple(
            item.isoformat()
            for item in self.sessions
            if start <= item <= end
        )
        return SimpleNamespace(
            values={"trading_dates": dates},
            blockers=(),
            provenance={"status": "verified", "source": "test-calendar"},
        )


class _CaptureResponse:
    def __init__(self, content: bytes, url: str, status_code: int = 200) -> None:
        self.content = content
        self.url = url
        self.status_code = status_code
        self.headers = {"Content-Type": "application/json"}


class _CaptureSession:
    def __init__(self, *, report_date: date, pe: str) -> None:
        roc_date = f"{report_date.year - 1911:03d}/{report_date.month:02d}/{report_date.day:02d}"
        self.twse_body = json.dumps(
            [
                {
                    "Date": roc_date,
                    "Code": "2330",
                    "PEratio": pe,
                    "DividendYield": "2.10",
                    "PBratio": "6.25",
                }
            ],
            ensure_ascii=False,
        ).encode("utf-8")

    def get(self, url: str, **_kwargs: object) -> _CaptureResponse:
        if "openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL" in url:
            return _CaptureResponse(self.twse_body, url)
        return _CaptureResponse(b"source unavailable", url, status_code=503)


def _capture_twse_valuation(
    output_root: Path,
    *,
    report_date: date,
    available_at: datetime,
    pe: str,
) -> None:
    capture_current_official_valuation(
        output_root,
        session=_CaptureSession(report_date=report_date, pe=pe),
        wrapper_run_id=f"test-{report_date.isoformat()}-{pe.replace('.', '-')}",
        clock=lambda: available_at,
    )


def _app_market_session(
    *,
    frame: pd.DataFrame,
    current_provider: RecommendationCurrentFundamentalProvider,
    frozen_at: datetime,
    official_sessions: tuple[date, ...],
) -> RecommendationInputSession:
    return RecommendationInputSession(
        config=SimpleNamespace(db_file=Path("unused.db"), use_sqlite=False),
        market_data_provider=lambda: frame.copy(deep=True),
        historical_market_provider=lambda _cutoff: frame.copy(deep=True),
        pit_membership_provider=SimpleNamespace(read=lambda *_args: None),
        fundamental_input_provider=SimpleNamespace(),
        current_fundamental_provider=current_provider,
        market_session_cadence=MarketSessionCadence(
            _AppOfficialCalendar(official_sessions),  # type: ignore[arg-type]
            clock=lambda: frozen_at,
        ),
        invocation_frozen_at=frozen_at,
    )


def test_current_pe_reader_binds_market_date_and_capture_hash(tmp_path: Path) -> None:
    database = tmp_path / "fundamentals.db"
    database.touch()
    factory = _FakeOfficialValuationProvider
    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
        valuation_provider_factory=factory,
        official_calendar_factory=lambda path: _FakeOfficialTradingCalendar(
            path, latest_session=date(2026, 10, 2)
        ),
    )

    observation, diagnostics = provider.load_pe(
        stock_code="2330",
        cutoff_at=FROZEN,
        expected_market_date=date(2026, 10, 2),
    )

    assert diagnostics == ()
    assert observation is not None
    assert factory.expected_market_dates == [date(2026, 10, 2)]
    assert observation.as_of_date == date(2026, 10, 2)
    assert observation.available_at == FROZEN - timedelta(seconds=1)
    assert observation.raw_response_sha256 == RAW_HASH
    assert observation.formal_pit_eligible is False


@pytest.mark.parametrize("raw_pe", (Decimal("-5.25"), Decimal("0")))
def test_current_pe_reader_preserves_nonpositive_source_value_and_lineage(
    tmp_path: Path,
    raw_pe: Decimal,
) -> None:
    database = tmp_path / "fundamentals.db"
    database.touch()

    class _RawPEProvider(_FakeOfficialValuationProvider):
        pe_value = raw_pe

    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
        valuation_provider_factory=_RawPEProvider,
        official_calendar_factory=lambda path: _FakeOfficialTradingCalendar(
            path, latest_session=date(2026, 10, 2)
        ),
    )

    observation, diagnostics = provider.load_pe(
        stock_code="2330",
        cutoff_at=FROZEN,
        expected_market_date=date(2026, 10, 2),
    )

    assert diagnostics == ()
    assert observation is not None
    assert observation.value == raw_pe
    assert observation.source == "twse.openapi.bwibbu_all"
    assert observation.source_version == "official-current-valuation.v1:run:1"
    assert observation.raw_response_sha256 == RAW_HASH
    assert observation.formal_pit_eligible is False


def test_current_pe_rejects_source_date_mismatched_to_market_session(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    database.touch()

    class _StaleProvider(_FakeOfficialValuationProvider):
        def read_current(
            self,
            stock_code: str,
            as_of_date: date,
            *,
            expected_market_date: date,
        ):
            result = super().read_current(
                stock_code,
                as_of_date,
                expected_market_date=expected_market_date,
            )
            result.observations[0].as_of_date = date(2026, 9, 30)
            return result

    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
        valuation_provider_factory=_StaleProvider,
        official_calendar_factory=lambda path: _FakeOfficialTradingCalendar(
            path, latest_session=date(2026, 10, 2)
        ),
    )
    observation, diagnostics = provider.load_pe(
        stock_code="2330",
        cutoff_at=FROZEN,
        expected_market_date=date(2026, 10, 2),
    )
    assert observation is None
    assert diagnostics == ("current_pe_source_date_does_not_match_market_data_date",)


def test_weekend_run_accepts_last_resolved_official_session(tmp_path: Path) -> None:
    database = tmp_path / "fundamentals.db"
    database.touch()
    calendars: list[_FakeOfficialTradingCalendar] = []

    def calendar_factory(path: Path) -> _FakeOfficialTradingCalendar:
        calendar = _FakeOfficialTradingCalendar(
            path, latest_session=date(2026, 10, 2)
        )
        calendars.append(calendar)
        return calendar

    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
        valuation_provider_factory=_FakeOfficialValuationProvider,
        official_calendar_factory=calendar_factory,
    )
    observation, diagnostics = provider.load_pe(
        stock_code="2330",
        cutoff_at=FROZEN,
        expected_market_date=date(2026, 10, 2),
    )

    assert observation is not None
    assert diagnostics == ()
    assert calendars[0].calls == [
        (date(2026, 10, 3), False),
        (date(2026, 10, 2), False),
    ]


def test_pe_uses_shared_project_publication_cutoff_not_intraday_close(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    database.touch()
    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
        valuation_provider_factory=_FakeOfficialValuationProvider,
        official_calendar_factory=lambda path: _FakeOfficialTradingCalendar(
            path, latest_session=date(2026, 10, 2)
        ),
    )
    taipei = ZoneInfo("Asia/Taipei")

    before_project_cutoff, before_diagnostics = provider.load_pe(
        stock_code="2330",
        cutoff_at=datetime(2026, 10, 2, 13, 30, tzinfo=taipei),
        expected_market_date=date(2026, 10, 1),
    )
    at_project_cutoff, cutoff_diagnostics = provider.load_pe(
        stock_code="2330",
        cutoff_at=datetime(2026, 10, 2, 19, 30, tzinfo=taipei),
        expected_market_date=date(2026, 10, 2),
    )

    assert before_project_cutoff is not None
    assert before_diagnostics == ()
    assert before_project_cutoff.market_calendar_session_date == date(2026, 10, 1)
    assert at_project_cutoff is not None
    assert cutoff_diagnostics == ()
    assert at_project_cutoff.market_calendar_session_date == date(2026, 10, 2)


def test_stale_quote_and_matching_stale_pe_are_rejected_by_calendar_gate(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fundamentals.db"
    database.touch()
    source_factory = _FakeOfficialValuationProvider
    source_dates_before = list(source_factory.expected_market_dates)
    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "output",
        valuation_provider_factory=source_factory,
        official_calendar_factory=lambda path: _FakeOfficialTradingCalendar(
            path, latest_session=date(2026, 10, 2)
        ),
    )

    observation, diagnostics = provider.load_pe(
        stock_code="2330",
        cutoff_at=FROZEN,
        expected_market_date=date(2026, 7, 31),
    )

    assert observation is None
    assert diagnostics == (
        "current_market_data_date_not_latest_official_session:2026-07-31:2026-10-02",
    )
    assert source_factory.expected_market_dates == source_dates_before


@pytest.mark.parametrize(
    ("frozen_at", "expected_date", "expected_pe"),
    [
        (
            datetime(2026, 10, 5, 14, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            date(2026, 10, 2),
            Decimal("18.00"),
        ),
        (
            datetime(2026, 10, 5, 20, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            date(2026, 10, 5),
            Decimal("25.00"),
        ),
    ],
)
def test_natural_app_and_real_pe_reader_share_project_session_date(
    tmp_path: Path,
    frozen_at: datetime,
    expected_date: date,
    expected_pe: Decimal,
) -> None:
    output_root = tmp_path / "valuation-output"
    _capture_twse_valuation(
        output_root,
        report_date=date(2026, 10, 2),
        available_at=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        pe="18.00",
    )
    _capture_twse_valuation(
        output_root,
        report_date=date(2026, 10, 5),
        available_at=datetime(2026, 10, 5, 5, 50, tzinfo=UTC),
        pe="25.00",
    )
    current_provider = RecommendationCurrentFundamentalProvider(
        db_file=tmp_path / "read-only-fundamentals.db",
        output_root=output_root,
        valuation_provider_factory=CurrentOfficialValuationReadProvider,
        official_calendar_factory=lambda path: _FakeOfficialTradingCalendar(
            path, latest_session=expected_date
        ),
    )
    date_column = "\u65e5\u671f"
    code_column = "\u8b49\u5238\u4ee3\u865f"
    name_column = "\u8b49\u5238\u540d\u7a31"
    frame = pd.DataFrame(
        [
            {
                date_column: "20261002",
                code_column: "2330",
                name_column: "test",
                "close": "100",
                "available_date": "20261003",
            },
            {
                date_column: "20261002",
                code_column: "2330",
                name_column: "future revision",
                "close": "101",
                "available_date": "20261006",
            },
            {
                date_column: "20261005",
                code_column: "2330",
                name_column: "today",
                "close": "200",
                "available_date": "20261005",
            },
        ]
    )
    session = _app_market_session(
        frame=frame,
        current_provider=current_provider,
        frozen_at=frozen_at,
        official_sessions=(date(2026, 10, 2), date(2026, 10, 5)),
    )

    prepared = session.prepare_market(cutoff=None, source_frame=frame)
    observation, diagnostics = session.load_current_pe(
        stock_code="2330",
        cutoff_at=frozen_at,
        expected_market_date=prepared.expected_market_date or "",
    )

    assert prepared.decision_cutoff == expected_date.isoformat()
    assert prepared.expected_market_date == expected_date.isoformat()
    assert prepared.market_calendar_status == "current"
    assert prepared.data_date == expected_date.isoformat()
    if expected_date == date(2026, 10, 2):
        assert prepared.frame["close"].astype(str).tolist() == ["100"]
    assert diagnostics == ("tpex_capture_missing",)
    assert observation is not None
    assert observation.as_of_date == expected_date
    assert observation.value == expected_pe
    assert observation.available_at <= frozen_at.astimezone(UTC)
    assert observation.raw_response_sha256 == hashlib.sha256(
        next(
            (
                path.parent / "raw_response.bin"
                for path in (output_root / "current_valuation" / "twse").rglob("receipt.json")
                if json.loads(path.read_text(encoding="utf-8"))["source_date"]
                == expected_date.isoformat()
            )
        ).read_bytes()
    ).hexdigest()


def test_provider_calendar_defaults_to_repository_cache_not_output_root(
    tmp_path: Path,
) -> None:
    provider = RecommendationCurrentFundamentalProvider(
        db_file=tmp_path / "fundamentals.db",
        output_root=tmp_path / "shadow-output",
    )

    assert provider.calendar_cache_path == DEFAULT_OFFICIAL_CALENDAR_CACHE_ROOT.resolve(
        strict=False
    )
    assert provider.temporary_closure_path == provider.calendar_cache_path
    output_local_cache = (
        provider.output_root / "paper_execution_eod_replay" / "calendar_cache"
    )
    assert provider.calendar_cache_path != output_local_cache


@pytest.mark.parametrize("cache_is_file", [False, True])
def test_provider_calendar_paths_support_directory_or_single_file(
    tmp_path: Path,
    cache_is_file: bool,
) -> None:
    selected_cache = (
        tmp_path / "annual-cache.json"
        if cache_is_file
        else tmp_path / "annual-cache"
    )
    explicit_closures = tmp_path / "closures" / "events.json"

    provider = RecommendationCurrentFundamentalProvider(
        db_file=tmp_path / "fundamentals.db",
        output_root=tmp_path / "artifact-output",
        calendar_cache_path=selected_cache,
    )
    with_override = RecommendationCurrentFundamentalProvider(
        db_file=tmp_path / "fundamentals.db",
        output_root=tmp_path / "artifact-output",
        calendar_cache_path=selected_cache,
        temporary_closure_path=explicit_closures,
    )

    expected_cache = selected_cache.resolve(strict=False)
    expected_closures = (
        selected_cache.parent if cache_is_file else selected_cache
    ).resolve(strict=False)
    assert provider.calendar_cache_path == expected_cache
    assert provider.temporary_closure_path == expected_closures
    assert with_override.calendar_cache_path == expected_cache
    assert with_override.temporary_closure_path == explicit_closures.resolve(
        strict=False
    )


def test_provider_uses_explicit_hash_bound_calendar_cache_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from data_module.official_trading_calendar_cache import (
        build_twse_calendar_cache,
        write_twse_calendar_cache,
    )

    cache_root = tmp_path / "release_v4" / "calendar-cache"
    cache_path = cache_root / "twse_holiday_schedule_2026_fixture.json"
    cache_root.mkdir(parents=True)
    captured_at = datetime.now(UTC)
    raw_response = json.dumps(
        [
            {
                "Name": "開市日",
                "Date": "1150102",
                "Weekday": "五",
                "Description": "開市日",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=raw_response,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
    )
    write_twse_calendar_cache(cache_path, cache, allowed_root=tmp_path)
    monkeypatch.setattr(
        "data_module.official_trading_calendar.safe_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("offline verified calendar must not call network")
        ),
    )
    provider = RecommendationCurrentFundamentalProvider(
        db_file=tmp_path / "missing-market.sqlite",
        output_root=tmp_path / "shadow-output",
        calendar_cache_path=cache_path,
    )

    # The 2026-01-05 session is resolved from the hash-bound annual cache.
    assert provider._latest_official_session(
        datetime(2026, 1, 5, 13, 0, tzinfo=UTC)
    ) == (date(2026, 1, 5), "twse_holiday_schedule_cache_open")


def test_explicit_missing_calendar_cache_fails_closed_without_default_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_cache = tmp_path / "explicit-missing-calendar.json"
    monkeypatch.setattr(
        "data_module.official_trading_calendar.safe_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("explicit invalid cache must not trigger network access")
        ),
    )
    provider = RecommendationCurrentFundamentalProvider(
        db_file=tmp_path / "missing-market.sqlite",
        output_root=tmp_path / "shadow-output",
        calendar_cache_path=missing_cache,
    )

    assert provider._latest_official_session(
        datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
    ) == (
        None,
        "official_trading_calendar_unresolved:2026-10-12:"
        "lacks_official_evidence",
    )
    assert provider.calendar_cache_path == missing_cache.resolve(strict=False)


@pytest.mark.parametrize(
    ("calendar_cache_path", "temporary_closure_path", "message"),
    [
        ("", None, "calendar_cache_path"),
        ("   ", None, "calendar_cache_path"),
        (None, "", "temporary_closure_path"),
        (None, "   ", "temporary_closure_path"),
        (42, None, "calendar_cache_path"),
        (None, 42, "temporary_closure_path"),
    ],
)
def test_blank_or_invalid_calendar_paths_are_rejected(
    tmp_path: Path,
    calendar_cache_path: object,
    temporary_closure_path: object,
    message: str,
) -> None:
    kwargs: dict[str, object] = {}
    if calendar_cache_path is not None:
        kwargs["calendar_cache_path"] = calendar_cache_path
    if temporary_closure_path is not None:
        kwargs["temporary_closure_path"] = temporary_closure_path

    with pytest.raises(ValueError, match=message):
        RecommendationCurrentFundamentalProvider(
            db_file=tmp_path / "fundamentals.db",
            output_root=tmp_path / "shadow-output",
            **kwargs,  # type: ignore[arg-type]
        )
