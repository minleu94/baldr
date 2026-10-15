from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import sqlite3
from threading import Thread
from typing import Callable

import pytest

from app_module.daily_market_monthly_revenue_yoy_index_v2 import (
    DailyMarketMonthlyRevenueYoyIndexCancelled,
    DailyMarketMonthlyRevenueYoyIndexError,
    DailyMarketMonthlyRevenueYoyIndexSessionV2,
)
from data_module.daily_market_monthly_revenue_read_session_v2 import (
    DailyMarketMonthlyRevenueReadSessionV2,
)
from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
)
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    FinishedDailyMarketMonthlyRevenueCohortV2,
)
from data_module.fundamental_read_snapshot_cohort_v2 import FundamentalSnapshotSourceClockV2
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    RecommendationCurrentFundamentalProvider,
)
from tests.test_baldr_completion_p03_sources import CUTOFF
from tests.test_selection_fundamental_daily_cohort_v2 import (
    _daily_cohort_environment,
    _source_db_state,
)


_CODES = ("1101", "2330")


def _open_index(
    root: Path,
    *,
    stock_codes: tuple[str, ...] = _CODES,
    delay_availability_hour: bool = False,
    cancel_callback: Callable[[], bool] | None = None,
) -> tuple[
    RecommendationCurrentFundamentalProvider,
    DailyMonthlyRevenueCohortReader,
    DailyMonthlyRevenueCohortPin,
    DailyMarketMonthlyRevenueYoyIndexSessionV2,
]:
    provider, reader, pin, _, _ = _daily_cohort_environment(
        root,
        delay_availability_hour=delay_availability_hour,
    )
    session = DailyMarketMonthlyRevenueYoyIndexSessionV2.open(
        provider,
        daily_monthly_cohort_reader=reader,
        snapshot_root=root / "monthly-revenue-yoy-v2-snapshot",
        stock_codes=stock_codes,
        cutoff_at=CUTOFF,
        cancel_callback=cancel_callback,
    )
    return provider, reader, pin, session


def test_v2_index_projects_full_finished_cohort_with_exact_method_and_v2_clock(
    tmp_path: Path,
) -> None:
    provider, reader, pin, session = _open_index(
        tmp_path,
        stock_codes=tuple(reversed(_CODES)),
    )
    source_state = _source_db_state(provider.db_file)
    try:
        candidate = session.load_batch(_CODES)
        assert candidate.complete is False
        assert candidate.stock_codes == _CODES
        assert candidate.batch_index == 0
        assert len(candidate.result_identity_sha256) == len(_CODES)
        assert len(candidate.source_fact_identity_sha256) == len(_CODES)
        assert len(candidate.projected_fact_identity_sha256) == len(_CODES)
        assert session.processed_stock_codes == _CODES
        assert session.finished is False

        index = session.finish()
        assert index.is_reader_issued is True
        assert index.declared_stock_codes == _CODES
        assert tuple(entry.stock_code for entry in session.validated_entries()) == _CODES
        assert index.source_clock is session.source_clock
        assert type(index.source_clock) is FundamentalSnapshotSourceClockV2
        assert index.source_clock.cohort_pin == pin == reader.pin
        assert index.source_clock.decision_cutoff == CUTOFF
        assert index.source_scope == "current_observed_only"
        assert index.availability_status == "cohort_hour_bound"
        assert index.historical_pit_eligible is False
        assert index.formal_pit_eligible is False
        finished = session._finished_cohort
        assert finished is not None
        assert index.result_identity_by_stock == finished.result_identity_by_stock
        assert index.fact_identity_by_stock == finished.fact_identity_by_stock
        assert index.projected_fact_identity_by_stock == tuple(
            (entry.stock_code, entry.projected_fact.identity_sha256)
            for entry in index.entries
        )
        assert sum(count for _, count in index.reader_result_status_counts) == len(_CODES)
        assert sum(count for _, count in index.fact_state_counts) == len(_CODES)
        assert sum(count for _, count in index.projected_state_counts) == len(_CODES)
        unknown_entry = index.entry_for("1101")
        observed_entry = index.entry_for("2330")
        assert unknown_entry is not None and unknown_entry.projected_fact.state == "unknown"
        assert observed_entry is not None and observed_entry.projected_fact.state == "observed"
        assert observed_entry.projected_fact.growth_percent == Decimal("22.006875")
        serialized = index.to_dict()
        assert serialized["complete"] is True
        assert serialized["availability_status"] == "cohort_hour_bound"
        assert serialized["projected_fact_identity_by_stock"] == [
            list(item) for item in index.projected_fact_identity_by_stock
        ]
        assert serialized["entries"] == [entry.to_dict() for entry in index.entries]
        source_observation = observed_entry.source_fact.result.observations[0]
        assert source_observation.availability_snapshot_batch_id is not None
        assert source_observation.raw_source_sha256
        assert session.closed is True
        assert _source_db_state(provider.db_file) == source_state
    finally:
        session.close()


def test_missing_stock_stays_in_complete_index_denominator_as_unknown(
    tmp_path: Path,
) -> None:
    _, reader, pin, session = _open_index(tmp_path, stock_codes=("9999",))
    try:
        batch = session.load_batch(("9999",))
        assert batch.stock_codes == ("9999",)
        assert session.read_status_counts == (("missing", 1),)
        index = session.finish()
        entry = index.entries[0]
        assert entry.source_fact.status == "missing"
        assert entry.projected_fact.state == "unknown"
        assert entry.projected_fact.growth_percent is None
        assert index.reader_result_status_counts == (("missing", 1),)
        assert index.fact_state_counts == (("blocked", 0), ("observed", 0), ("unknown", 1))
        assert entry.source_fact.cohort_pin == pin == reader.pin
        assert index.declared_stock_codes == ("9999",)
    finally:
        session.close()


def test_invalid_same_report_comparator_remains_unknown_without_changing_formula(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, _, session = _open_index(tmp_path, stock_codes=("2330",))
    original = RecommendationCurrentFundamentalProvider.load_monthly_revenues

    def missing_comparator(
        self: RecommendationCurrentFundamentalProvider,
        *,
        stock_code: str,
        cutoff_at: datetime,
        read_session_connection: sqlite3.Connection | None = None,
        pinned_daily_batch_id: str | None = None,
        pinned_daily_cohort: DailyMonthlyRevenueCohortPin | None = None,
    ) -> CurrentMonthlyRevenueReadResult:
        result = original(
            self,
            stock_code=stock_code,
            cutoff_at=cutoff_at,
            read_session_connection=read_session_connection,
            pinned_daily_batch_id=pinned_daily_batch_id,
            pinned_daily_cohort=pinned_daily_cohort,
        )
        return replace(
            result,
            comparison_baseline=None,
            diagnostics=(*result.diagnostics, "fixture_comparator_not_available"),
        )

    monkeypatch.setattr(
        RecommendationCurrentFundamentalProvider,
        "load_monthly_revenues",
        missing_comparator,
    )
    try:
        entry = session.load_batch(("2330",)).stock_codes
        assert entry == ("2330",)
        index = session.finish()
        projected = index.entries[0].projected_fact
        assert index.entries[0].source_fact.result.status == "ready"
        assert index.entries[0].source_fact.result.observations
        assert index.entries[0].source_fact.result.comparison_baseline is None
        assert projected.state == "unknown"
        assert projected.growth_percent is None
        assert "fixture_comparator_not_available" in projected.provider_diagnostics
        assert index.fact_state_counts == (("blocked", 0), ("observed", 0), ("unknown", 1))
    finally:
        session.close()


def test_incomplete_cohort_closes_source_and_never_publishes_index_or_reference(
    tmp_path: Path,
) -> None:
    _, _, _, session = _open_index(tmp_path)
    session.load_batch((_CODES[0],))
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexError, match="cohort_incomplete"):
        session.finish()
    assert session.closed is True
    assert session.finished is False
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexError, match="index_not_finished"):
        _ = session.index
    with pytest.raises(
        DailyMarketMonthlyRevenueYoyIndexError,
        match="source_reference_requires_finished",
    ):
        _ = session.source_reference


def test_v3_exact_reopen_reissues_same_source_and_projection_ledgers(
    tmp_path: Path,
) -> None:
    provider, reader, pin, original = _open_index(tmp_path / "original")
    source_state = _source_db_state(provider.db_file)
    original.load_batch(_CODES)
    original_index = original.finish()
    reference = original.source_reference
    external_sha = sha256(reference.to_json().encode("utf-8")).hexdigest()

    reopened = DailyMarketMonthlyRevenueYoyIndexSessionV2.open_exact(
        provider,
        daily_monthly_cohort_reader=reader,
        snapshot_root=tmp_path / "exact-reopened",
        source_reference=reference.to_json().encode("utf-8"),
        expected_reference_sha256=external_sha,
        stock_codes=_CODES,
        cutoff_at=CUTOFF,
    )
    try:
        reopened.load_batch(_CODES)
        replay = reopened.finish()
        assert replay.source_content_identity_sha256 == original_index.source_content_identity_sha256
        assert replay.declared_stock_codes == original_index.declared_stock_codes
        assert replay.cohort_pin == pin
        assert replay.result_identity_by_stock == original_index.result_identity_by_stock
        assert replay.fact_identity_by_stock == original_index.fact_identity_by_stock
        assert replay.reader_result_status_counts == original_index.reader_result_status_counts
        assert replay.fact_state_counts == original_index.fact_state_counts
        assert tuple(entry.projected_fact.identity_sha256 for entry in replay.entries) == tuple(
            entry.projected_fact.identity_sha256 for entry in original_index.entries
        )
        assert replay.source_clock.schema_version == "selection-fundamental-source-clock.snapshot.v2"
        assert _source_db_state(provider.db_file) == source_state
    finally:
        reopened.close()
        original.close()


def test_bad_v3_external_sha_is_rejected_before_any_snapshot_copy(
    tmp_path: Path,
) -> None:
    provider, reader, _, original = _open_index(tmp_path / "origin", stock_codes=("9999",))
    original.load_batch(("9999",))
    original.finish()
    reference = original.source_reference
    target = tmp_path / "must-not-copy"
    try:
        with pytest.raises(DailyMarketMonthlyRevenueYoyIndexError, match="source_reference_decode"):
            DailyMarketMonthlyRevenueYoyIndexSessionV2.open_exact(
                provider,
                daily_monthly_cohort_reader=reader,
                snapshot_root=target,
                source_reference=reference,
                expected_reference_sha256="0" * 64,
                stock_codes=("9999",),
                cutoff_at=CUTOFF,
            )
        assert not target.exists()
    finally:
        original.close()


def test_out_of_order_batch_poison_closes_source_without_partial_index(
    tmp_path: Path,
) -> None:
    _, _, _, session = _open_index(tmp_path)
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexError, match="batch_order_or_scope"):
        session.load_batch(("2330",))
    assert session.closed is True
    assert session.finished is False
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexError, match="session_not_open"):
        session.finish()


def test_mutated_batch_receipt_ledger_cannot_publish_index(tmp_path: Path) -> None:
    _, _, _, session = _open_index(tmp_path, stock_codes=("2330",))
    batch = session.load_batch(("2330",))
    object.__setattr__(batch, "result_identity_sha256", ("0" * 64,))
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexError, match="batch_ledger"):
        session.finish()
    assert session.closed is True
    assert session.finished is False


def test_cooperative_cancel_never_issues_index_and_owner_closes_source(
    tmp_path: Path,
) -> None:
    cancel = False
    provider, reader, _, session = _open_index(
        tmp_path,
        stock_codes=("2330",),
        cancel_callback=lambda: cancel,
    )
    assert provider.daily_source_snapshot_reader is reader
    cancel = True
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexCancelled):
        session.load_batch(("2330",))
    assert session.finished is False
    assert session.closed is True


def test_finish_cancel_during_reprojection_stops_before_next_stock(tmp_path, monkeypatch):
    import app_module.daily_market_monthly_revenue_yoy_index_v2 as module
    cancel = False
    provider, _, _, session = _open_index(tmp_path, cancel_callback=lambda: cancel)
    state = _source_db_state(provider.db_file)
    session.load_batch(_CODES)
    original = module.project_selection_monthly_revenue_yoy_v2
    calls = []
    def project(source):
        nonlocal cancel
        calls.append(source.stock_code)
        result = original(source)
        cancel = True
        return result
    monkeypatch.setattr(module, "project_selection_monthly_revenue_yoy_v2", project)
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexCancelled):
        session.finish()
    assert calls == [_CODES[0]] and session.finished is False and session.closed is True
    assert _source_db_state(provider.db_file) == state


def test_cross_thread_calls_are_rejected_without_stealing_owner_cleanup(
    tmp_path: Path,
) -> None:
    _, _, _, session = _open_index(tmp_path, stock_codes=("2330",))
    failures: list[str] = []

    def non_owner_call() -> None:
        try:
            session.load_batch(("2330",))
        except DailyMarketMonthlyRevenueYoyIndexError as exc:
            failures.append(exc.code)

    thread = Thread(target=non_owner_call)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert failures == ["wrong_owner_thread"]
    assert session.processed_stock_codes == ()
    session.load_batch(("2330",))
    index = session.finish()
    assert session.index is index
    session.close()
    assert session.closed is True


def test_context_exit_closes_source_when_cohort_is_left_incomplete(
    tmp_path: Path,
) -> None:
    _, _, _, session = _open_index(tmp_path)
    with session as managed:
        managed.load_batch((_CODES[0],))
        assert managed.finished is False
        assert managed.closed is False
    assert session.closed is True
    assert session.finished is False


def test_future_cohort_hour_is_rejected_before_copy_even_for_all_missing_codes(
    tmp_path: Path,
) -> None:
    provider, reader, pin, _, _ = _daily_cohort_environment(
        tmp_path,
        delay_availability_hour=True,
    )
    target = tmp_path / "future-pin-no-copy"
    source_state = _source_db_state(provider.db_file)
    early_cutoff = datetime(2026, 10, 4, 0, 45, tzinfo=timezone.utc)
    assert pin.available_hour.astimezone(timezone.utc) > early_cutoff
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexError, match="source_open_failed"):
        DailyMarketMonthlyRevenueYoyIndexSessionV2.open(
            provider,
            daily_monthly_cohort_reader=reader,
            snapshot_root=target,
            stock_codes=("9999",),
            cutoff_at=early_cutoff,
        )
    assert not target.exists()
    assert _source_db_state(provider.db_file) == source_state


def test_mutated_finished_fact_ledger_cannot_become_yoy_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, _, session = _open_index(tmp_path, stock_codes=("2330",))
    session.load_batch(("2330",))
    original_finish = DailyMarketMonthlyRevenueReadSessionV2.finish

    def finish_then_mutate(
        source_session: DailyMarketMonthlyRevenueReadSessionV2,
    ) -> FinishedDailyMarketMonthlyRevenueCohortV2:
        finished = original_finish(source_session)
        object.__setattr__(finished.facts[0], "result_identity_sha256", "0" * 64)
        return finished

    monkeypatch.setattr(
        DailyMarketMonthlyRevenueReadSessionV2,
        "finish",
        finish_then_mutate,
    )
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexError):
        session.finish()
    assert session.closed is True
    assert session.finished is False
    assert session._finished_index is None


def test_dataclass_replace_cannot_reuse_reader_issued_v2_index_seal(
    tmp_path: Path,
) -> None:
    from dataclasses import replace as dataclass_replace

    _, _, _, session = _open_index(tmp_path, stock_codes=("2330",))
    try:
        session.load_batch(("2330",))
        index = session.finish()
        with pytest.raises((TypeError, ValueError)):
            dataclass_replace(index, declared_stock_codes=("1101",))
        assert index.is_reader_issued is True
    finally:
        session.close()
