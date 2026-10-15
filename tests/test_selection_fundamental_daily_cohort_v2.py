from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
from typing import Callable
from zoneinfo import ZoneInfo

import pytest

from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
    build_daily_monthly_revenue_cohort_pin,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_SNAPSHOT_DATASET_ID,
    DAILY_SOURCE_SNAPSHOT_SOURCE_ID,
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DailySourceBatchValidation,
    DailySourceSnapshot,
    DailySourceSnapshotError,
    DailySourceSnapshotFileReader,
    DailySourceSnapshotRecord,
    DailySourceTransportCapture,
    DailySourceUseAcceptance,
    DailySourceUseScope,
    DailySourceValidationCheck,
    write_daily_source_snapshot,
)
from data_module.current_fundamental_snapshots import MONTHLY_NORMALIZER_VERSION
from data_module.monthly_revenue_snapshot_harvester import (
    parse_mops_monthly_revenue_snapshot_html,
)
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    RecommendationCurrentFundamentalProvider,
)
from data_module.selection_fact_readers import (
    FinishedFundamentalReadCohort,
    FinishedFundamentalReadCohortV2,
    FundamentalReadBatchCandidate,
    FundamentalReadBatchCandidateV2,
    FundamentalReadSessionCancelled,
    FundamentalReadSessionError,
    FundamentalSourceClock,
    FundamentalSourceClockV2,
    SelectionFundamentalReadSession,
)
import data_module.selection_fact_readers as read_session_module
from data_module.fundamental_read_snapshot import FundamentalReadSnapshotError
from tests.test_fundamental_read_snapshot_lifecycle import _open_snapshot
from tests.test_baldr_completion_p03_sources import (
    CUTOFF,
    REPORT_PERIOD,
    SOURCE_AVAILABLE,
    _make_direct_copy_binding,
    _seed_provider,
)
from tests.test_monthly_revenue_snapshot_harvester import MOPS_SAMPLE_HTML


UTC = timezone.utc
TAIPEI = ZoneInfo("Asia/Taipei")
ENDPOINT = "https://mops.twse.com.tw/mops/web/t05st10_ifrs"
INTENDED_USE = "recommendation_current_fundamental"


def _accepted_scope(market: str) -> tuple[DailySourceUseScope, DailySourceUseAcceptance]:
    scope = DailySourceUseScope(
        dataset_id=DAILY_SOURCE_SNAPSHOT_DATASET_ID,
        source_id=DAILY_SOURCE_SNAPSHOT_SOURCE_ID,
        market=market,
        parser_version=MONTHLY_NORMALIZER_VERSION,
        source_schema_version="mops-static-snapshot.v2",
        unit="TWD",
        intended_use=INTENDED_USE,
    )
    acceptance = DailySourceUseAcceptance(
        scope=scope,
        acceptance_id=f"synthetic-selection-v2-{market}",
        accepted_at=datetime(2026, 10, 2, 8, 0, tzinfo=TAIPEI),
        official_source_endpoint=ENDPOINT,
        document_chain=("synthetic selection cohort test", ENDPOINT),
        acceptance_evidence_ref=f"test-fixture:{market}:trusted-acceptance",
        authorization_scope=f"{INTENDED_USE} only",
        time_basis_policy=DAILY_SOURCE_TIME_BASIS_POLICY,
    )
    return scope, acceptance


def _pass_check(check_id: str) -> DailySourceValidationCheck:
    return DailySourceValidationCheck(check_id, "pass", f"{check_id}_synthetic_pass")


def _daily_market_reader(
    root: Path,
    market: str,
    *,
    delay_availability_hour: bool,
) -> tuple[DailySourceSnapshotFileReader, DailySourceUseAcceptance, str]:
    scope, acceptance = _accepted_scope(market)
    source_html = MOPS_SAMPLE_HTML
    if market == "tpex":
        source_html = MOPS_SAMPLE_HTML.replace(
            "<td>2330</td><td>台積電</td>",
            "<td>6488</td><td>合成測試公司</td>",
        )
        assert "<td>6488</td>" in source_html
    canonical_bytes = source_html.encode("utf-8")
    raw_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
    body_completed_at = SOURCE_AVAILABLE
    raw_source_version = (
        f"mops-static-snapshot.v2:{market}:{REPORT_PERIOD}:body_completed_at:"
        f"{body_completed_at.isoformat()}:sha256:{raw_sha256}"
    )
    parsed_rows, diagnostics = parse_mops_monthly_revenue_snapshot_html(
        source_html,
        market=market,
        period=REPORT_PERIOD,
        fetched_at=body_completed_at.isoformat(),
        source_version=raw_source_version,
    )
    assert diagnostics == ()
    records = tuple(
        DailySourceSnapshotRecord(
            stock_code=str(row["stock_code"]),
            market=market,
            period=REPORT_PERIOD,
            source_version=raw_source_version,
            raw_source_sha256=raw_sha256,
            unit="TWD",
        )
        for row in parsed_rows
    )
    partition = f"{market}:{REPORT_PERIOD}:monthly-revenue"
    validation = DailySourceBatchValidation(
        validation_id=f"selection-v2-synthetic-{market}",
        expected_partition_ids=(partition,),
        successful_partition_ids=(partition,),
        failed_partition_ids=(),
        expected_record_count=len(records),
        actual_record_count=len(records),
        source_status_check=_pass_check("source_status"),
        raw_source_hash_check=_pass_check("raw_source_hash"),
        schema_check=_pass_check("schema"),
        unit_check=_pass_check("unit"),
        finite_values_check=_pass_check("finite_values"),
        missing_values_check=_pass_check("missing_values"),
        prior_period_required_check=DailySourceValidationCheck(
            "prior_period_required", "not_required", "prior_period_not_required"
        ),
        official_timestamp_parse_check=DailySourceValidationCheck(
            "official_timestamp_parse",
            "not_required",
            "official_timestamp_not_provided",
        ),
    )
    capture = DailySourceTransportCapture(
        raw_response_bytes=canonical_bytes,
        official_source_url=ENDPOINT,
        response_status=200,
        content_type="text/html; charset=utf-8",
        declared_decoding_encoding="utf-8",
        decoding_basis="http_content_type_charset",
        body_completed_at=body_completed_at,
        transport_sha256=raw_sha256,
        response_body_complete=True,
        received_body_bytes=len(canonical_bytes),
        content_length_original_text=None,
        body_completion_evidence_ref=f"eof:synthetic-selection-v2-{market}",
    )
    offset_minutes = (65, 75, 80, 85) if delay_availability_hour else (5, 15, 20, 25)
    clock_samples = iter(
        body_completed_at + timedelta(minutes=offset) for offset in offset_minutes
    )
    batch_id = f"selection-v2-{market}-20261004"
    write_daily_source_snapshot(
        root,
        batch_id=batch_id,
        scope=scope,
        use_acceptance=acceptance,
        source_batch_started_at=body_completed_at - timedelta(minutes=10),
        raw_source_bytes=canonical_bytes,
        records=records,
        validation=validation,
        transport_capture=capture,
        clock=lambda: next(clock_samples),
    )
    return DailySourceSnapshotFileReader(root, trusted_acceptance=acceptance), acceptance, batch_id


def _daily_cohort_environment(
    tmp_path: Path,
    *,
    delay_availability_hour: bool = False,
) -> tuple[
    RecommendationCurrentFundamentalProvider,
    DailyMonthlyRevenueCohortReader,
    DailyMonthlyRevenueCohortPin,
    dict[str, DailySourceSnapshotFileReader],
    dict[str, Path],
]:
    provider_root = tmp_path / "provider"
    provider = _seed_provider(provider_root)
    market_readers: dict[str, DailySourceSnapshotFileReader] = {}
    market_roots: dict[str, Path] = {}
    batch_ids: dict[str, str] = {}
    for market in ("twse", "tpex"):
        root = tmp_path / f"daily-{market}"
        reader, _, batch_id = _daily_market_reader(
            root,
            market,
            delay_availability_hour=delay_availability_hour,
        )
        market_readers[market] = reader
        market_roots[market] = root
        batch_ids[market] = batch_id
    pin = build_daily_monthly_revenue_cohort_pin(
        period=REPORT_PERIOD,
        required_markets=("twse", "tpex"),
        batch_ids=batch_ids,
        readers=market_readers,
    )
    cohort_reader = DailyMonthlyRevenueCohortReader(
        pin=pin,
        market_readers=market_readers,
        expected_cohort_sha256=pin.cohort_sha256,
    )
    provider.daily_source_snapshot_reader = cohort_reader
    return provider, cohort_reader, pin, market_readers, market_roots


def _open_v2_session(
    provider: RecommendationCurrentFundamentalProvider,
    cohort_reader: DailyMonthlyRevenueCohortReader,
    *,
    label: str,
    stock_codes: tuple[str, ...] = ("1101", "2330"),
    cutoff_at: datetime = CUTOFF,
    cancel_callback: Callable[[], bool] | None = None,
) -> SelectionFundamentalReadSession:
    attempt, reader_provider, copy_binding = _make_direct_copy_binding(
        provider,
        label=label,
        cancel_callback=cancel_callback,
    )
    # Snapshot cloning intentionally does not infer a daily source port; the caller pins it.
    reader_provider.daily_source_snapshot_reader = cohort_reader
    return SelectionFundamentalReadSession.open(
        reader_provider,
        database_path=attempt.reader_database_path,
        copy_binding=copy_binding,
        stock_codes=stock_codes,
        cutoff_at=cutoff_at,
        cancel_callback=cancel_callback,
        daily_monthly_cohort_reader=cohort_reader,
    )


def _source_db_state(path: Path) -> tuple[bytes, int, tuple[bool, bool]]:
    return (
        path.read_bytes(),
        path.stat().st_mtime_ns,
        (Path(f"{path}-wal").exists(), Path(f"{path}-shm").exists()),
    )


@pytest.mark.parametrize("stage", ["batch", "finish"])
def test_v1_snapshot_wrapper_refuses_manually_injected_v2_without_dropping_pin(tmp_path: Path, stage: str) -> None:
    provider, reader, _, _, _ = _daily_cohort_environment(tmp_path / "daily")
    v2_session = _open_v2_session(provider, reader, label="manual-v2-injection")
    wrapper = _open_snapshot(tmp_path / "legacy-provider", tmp_path / "legacy-snapshot")
    wrapper._read_session.close()
    wrapper._read_session = v2_session
    try:
        if stage == "batch":
            with pytest.raises(FundamentalReadSnapshotError, match="v1_refuses_v2_batch"):
                wrapper.load_batch(("1101", "2330"))
        else:
            v2_session.load_batch(("1101", "2330"))
            with pytest.raises(FundamentalReadSnapshotError, match="v1_refuses_v2_finished"):
                wrapper.finish()
        assert v2_session.closed
        assert not (wrapper.snapshot_root / "finished_source_clock.json").exists()
    finally:
        wrapper.close()


def test_clock_v2_rejects_string_subclass_that_spoofs_literal_equality(tmp_path: Path) -> None:
    provider, reader, _, _, _ = _daily_cohort_environment(tmp_path)
    session = _open_v2_session(provider, reader, label="exact-clock-literals")
    session.load_batch(("1101", "2330"))
    finished = session.finish()
    assert type(finished) is FinishedFundamentalReadCohortV2

    class SpoofedString(str):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    with pytest.raises(ValueError, match="schema"):
        replace(finished.source_clock, schema_version=SpoofedString("wrong"))
    with pytest.raises(ValueError, match="verified_markets"):
        replace(finished.source_clock, verified_markets=tuple(SpoofedString(market) for market in reader.pin.required_markets))


def test_opt_in_cohort_v2_hashes_rows_and_keeps_missing_status(tmp_path: Path) -> None:
    provider, cohort_reader, pin, _, _ = _daily_cohort_environment(tmp_path)
    source_state = _source_db_state(provider.db_file)
    session = _open_v2_session(provider, cohort_reader, label="cohort-v2-hash")

    batch = session.load_batch(("1101", "2330"))
    assert type(batch) is FundamentalReadBatchCandidateV2
    assert batch.session_id == session.session_id
    assert batch.cohort_sha256 == pin.cohort_sha256
    assert [result.status for result in batch.results] == ["missing", "ready"]

    current = next(
        row
        for row in batch.results[1].observations
        if row.input_role == "reported_period_value"
    )
    assert current.availability_snapshot_batch_id == pin.for_market("twse").batch_id
    assert current.availability_first_persisted_at == pin.for_market("twse").first_persisted_at
    assert batch.result_identity_sha256[1] == read_session_module._result_identity_sha256_v2(
        batch.results[1], cohort_pin=pin
    )
    assert batch.result_identity_sha256[1] != read_session_module._result_identity_sha256(
        batch.results[1]
    )
    changed_batch_row = replace(
        current,
        availability_snapshot_batch_id="synthetic-different-batch",
    )
    changed_batch_result = replace(
        batch.results[1],
        observations=tuple(
            changed_batch_row if row is current else row
            for row in batch.results[1].observations
        ),
    )
    assert read_session_module._result_identity_sha256_v2(
        changed_batch_result,
        cohort_pin=pin,
    ) != batch.result_identity_sha256[1]
    persisted_at = current.availability_first_persisted_at
    assert persisted_at is not None
    changed_clock_row = replace(
        current,
        availability_first_persisted_at=persisted_at + timedelta(seconds=1),
    )
    changed_clock_result = replace(
        batch.results[1],
        observations=tuple(
            changed_clock_row if row is current else row
            for row in batch.results[1].observations
        ),
    )
    assert read_session_module._result_identity_sha256_v2(
        changed_clock_result,
        cohort_pin=pin,
    ) != batch.result_identity_sha256[1]

    finished = session.finish()
    assert type(finished) is FinishedFundamentalReadCohortV2
    assert not isinstance(finished, FinishedFundamentalReadCohort)
    assert finished.complete is True
    assert finished.processed_stock_codes == ("1101", "2330")
    assert finished.result_status_counts == (("missing", 1), ("ready", 1))
    assert finished.result_identity_by_stock == tuple(
        zip(batch.stock_codes, batch.result_identity_sha256, strict=True)
    )
    assert finished.source_clock.cohort_pin == pin
    assert type(finished.source_clock) is FundamentalSourceClockV2
    assert not isinstance(finished.source_clock, FundamentalSourceClock)
    assert finished.source_clock.to_dict()["cohort_pin"] == pin.to_dict()
    assert finished.source_clock.availability_status == "cohort_hour_bound"
    assert finished.source_clock.source_scope == "current_observed_only"
    assert finished.source_clock.historical_pit_eligible is False
    assert finished.source_clock.formal_pit_eligible is False
    assert finished.source_clock.verified_markets == ("twse", "tpex")
    assert finished.to_dict()["availability_status"] == "cohort_hour_bound"
    assert finished.identity_sha256
    changed_tpex_pin = replace(
        pin.for_market("tpex"),
        available_hour=pin.for_market("tpex").available_hour + timedelta(hours=1),
    )
    changed_pin = replace(
        pin,
        market_pins=(pin.for_market("twse"), changed_tpex_pin),
        available_hour=changed_tpex_pin.available_hour,
    )
    changed_clock = replace(finished.source_clock, cohort_pin=changed_pin)
    assert changed_pin.cohort_sha256 != pin.cohort_sha256
    assert changed_clock.identity_sha256 != finished.source_clock.identity_sha256
    assert session.closed is True
    assert _source_db_state(provider.db_file) == source_state


def test_cohort_v2_reader_must_be_same_provider_port_before_database_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, cohort_reader, pin, market_readers, _ = _daily_cohort_environment(tmp_path)
    other_reader = DailyMonthlyRevenueCohortReader(
        pin=pin,
        market_readers=market_readers,
        expected_cohort_sha256=pin.cohort_sha256,
    )
    attempt, reader_provider, copy_binding = _make_direct_copy_binding(
        provider,
        label="cohort-v2-reader-identity",
    )
    reader_provider.daily_source_snapshot_reader = cohort_reader
    source_state = _source_db_state(provider.db_file)
    connect_calls: list[Path] = []
    original_open = read_session_module._open_readonly_transaction

    def tracked_open(path: Path) -> sqlite3.Connection:
        connect_calls.append(path)
        return original_open(path)

    monkeypatch.setattr(read_session_module, "_open_readonly_transaction", tracked_open)
    with pytest.raises(FundamentalReadSessionError, match="exact supplied reader"):
        SelectionFundamentalReadSession.open(
            reader_provider,
            database_path=attempt.reader_database_path,
            copy_binding=copy_binding,
            stock_codes=("2330",),
            cutoff_at=CUTOFF,
            daily_monthly_cohort_reader=other_reader,
        )

    assert connect_calls == []
    assert _source_db_state(provider.db_file) == source_state


def test_open_rechecks_every_cohort_market_before_sqlite_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, cohort_reader, _, _, _ = _daily_cohort_environment(tmp_path)
    attempt, reader_provider, copy_binding = _make_direct_copy_binding(
        provider,
        label="cohort-v2-open-order",
    )
    reader_provider.daily_source_snapshot_reader = cohort_reader
    events: list[tuple[str, tuple[str, ...] | None]] = []
    original_verify = DailyMonthlyRevenueCohortReader.verify_cohort
    original_open = read_session_module._open_readonly_transaction

    def tracked_verify(
        reader: DailyMonthlyRevenueCohortReader,
    ) -> tuple[DailySourceSnapshot, ...]:
        snapshots = original_verify(reader)
        events.append(("verify", tuple(item.scope.market for item in snapshots)))
        return snapshots

    def tracked_open(path: Path) -> sqlite3.Connection:
        events.append(("connect", None))
        return original_open(path)

    monkeypatch.setattr(DailyMonthlyRevenueCohortReader, "verify_cohort", tracked_verify)
    monkeypatch.setattr(read_session_module, "_open_readonly_transaction", tracked_open)
    session = SelectionFundamentalReadSession.open(
        reader_provider,
        database_path=attempt.reader_database_path,
        copy_binding=copy_binding,
        stock_codes=("2330",),
        cutoff_at=CUTOFF,
        daily_monthly_cohort_reader=cohort_reader,
    )
    session.close()

    verify_indices = [index for index, event in enumerate(events) if event[0] == "verify"]
    connect_index = next(index for index, event in enumerate(events) if event[0] == "connect")
    assert verify_indices
    assert all(index < connect_index for index in verify_indices)
    assert events[verify_indices[0]][1] == ("twse", "tpex")


def test_finish_rechecks_second_market_and_closes_without_v2_token(
    tmp_path: Path,
) -> None:
    provider, cohort_reader, pin, _, market_roots = _daily_cohort_environment(tmp_path)
    session = _open_v2_session(
        provider,
        cohort_reader,
        label="cohort-v2-finish-market-recheck",
        stock_codes=("2330",),
    )
    session.load_batch(("2330",))

    tpex_batch_id = pin.for_market("tpex").batch_id
    receipt = market_roots["tpex"] / tpex_batch_id / "receipt.json"
    receipt.write_bytes(receipt.read_bytes() + b"}")
    with pytest.raises(DailySourceSnapshotError, match="receipt JSON"):
        session.finish()

    assert session.closed is True
    assert session.finished is False


def test_cancel_during_final_cohort_recheck_closes_without_finished_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, cohort_reader, _, _, _ = _daily_cohort_environment(tmp_path)
    cancel_requested = [False]
    recheck_armed = [False]
    source_state = _source_db_state(provider.db_file)
    session = _open_v2_session(
        provider,
        cohort_reader,
        label="cohort-v2-cancel-final-recheck",
        stock_codes=("2330",),
        cancel_callback=lambda: cancel_requested[0],
    )
    session.load_batch(("2330",))
    connection = session._connection
    assert connection is not None

    original_verify = DailyMonthlyRevenueCohortReader.verify_cohort

    def verify_then_cancel(
        reader: DailyMonthlyRevenueCohortReader,
    ) -> tuple[DailySourceSnapshot, ...]:
        snapshots = original_verify(reader)
        if reader is cohort_reader and recheck_armed[0]:
            recheck_armed[0] = False
            cancel_requested[0] = True
        return snapshots

    monkeypatch.setattr(
        DailyMonthlyRevenueCohortReader,
        "verify_cohort",
        verify_then_cancel,
    )
    recheck_armed[0] = True
    with pytest.raises(FundamentalReadSessionCancelled):
        session.finish()

    assert session.finished is False
    assert session.closed is True
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    assert _source_db_state(provider.db_file) == source_state


def test_cutoff_before_pinned_hour_stays_missing_and_clock_is_not_rounded_up(
    tmp_path: Path,
) -> None:
    provider, cohort_reader, pin, _, _ = _daily_cohort_environment(
        tmp_path,
        delay_availability_hour=True,
    )
    cutoff = datetime(2026, 10, 4, 0, 45, tzinfo=UTC)
    assert pin.available_hour == datetime(2026, 10, 4, 9, 0, tzinfo=TAIPEI)
    assert cutoff.astimezone(TAIPEI) < pin.available_hour
    session = _open_v2_session(
        provider,
        cohort_reader,
        label="cohort-v2-cutoff-before-hour",
        stock_codes=("2330",),
        cutoff_at=cutoff,
    )

    batch = session.load_batch(("2330",))
    assert type(batch) is FundamentalReadBatchCandidateV2
    assert batch.results[0].status == "missing"
    assert "daily_source_cohort_not_available_at_cutoff" in batch.results[0].diagnostics
    assert batch.results[0].observations == ()
    finished = session.finish()
    assert type(finished) is FinishedFundamentalReadCohortV2
    assert finished.source_clock.decision_cutoff == cutoff
    assert finished.source_clock.availability_status == "cohort_hour_bound"
    assert finished.result_status_counts == (("missing", 1),)


def test_omitting_cohort_opt_in_preserves_v1_candidate_and_unknown_clock(
    tmp_path: Path,
) -> None:
    provider, cohort_reader, _, _, _ = _daily_cohort_environment(tmp_path)
    attempt, reader_provider, copy_binding = _make_direct_copy_binding(
        provider,
        label="cohort-v2-v1-compatibility",
    )
    reader_provider.daily_source_snapshot_reader = cohort_reader
    session = SelectionFundamentalReadSession.open(
        reader_provider,
        database_path=attempt.reader_database_path,
        copy_binding=copy_binding,
        stock_codes=("2330",),
        cutoff_at=CUTOFF,
    )

    batch = session.load_batch(("2330",))
    assert type(batch) is FundamentalReadBatchCandidate
    finished = session.finish()
    assert type(finished) is FinishedFundamentalReadCohort
    assert finished.source_clock.availability_status == "unknown"
    assert finished.source_clock.historical_pit_eligible is False
    assert finished.source_clock.formal_pit_eligible is False


def test_cohort_v2_preserves_unavailable_provider_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, cohort_reader, pin, _, _ = _daily_cohort_environment(tmp_path)

    def unavailable_result(
        reader_provider: RecommendationCurrentFundamentalProvider,
        *,
        stock_code: str,
        cutoff_at: datetime,
        read_session_connection: sqlite3.Connection | None = None,
        pinned_daily_batch_id: str | None = None,
        pinned_daily_cohort: DailyMonthlyRevenueCohortPin | None = None,
    ) -> CurrentMonthlyRevenueReadResult:
        assert reader_provider.daily_source_snapshot_reader is cohort_reader
        assert read_session_connection is not None
        assert pinned_daily_batch_id is None
        assert pinned_daily_cohort == pin
        return CurrentMonthlyRevenueReadResult(
            status="unavailable",
            stock_code=stock_code,
            cutoff_at=cutoff_at,
            latest_period=None,
            diagnostics=("synthetic_unavailable_input",),
        )

    monkeypatch.setattr(
        RecommendationCurrentFundamentalProvider,
        "load_monthly_revenues",
        unavailable_result,
    )
    session = _open_v2_session(
        provider,
        cohort_reader,
        label="cohort-v2-unavailable-status",
        stock_codes=("2330",),
    )

    batch = session.load_batch(("2330",))
    assert type(batch) is FundamentalReadBatchCandidateV2
    assert batch.results[0].status == "unavailable"
    assert batch.results[0].diagnostics == ("synthetic_unavailable_input",)
    finished = session.finish()
    assert type(finished) is FinishedFundamentalReadCohortV2
    assert finished.result_status_counts == (("unavailable", 1),)
