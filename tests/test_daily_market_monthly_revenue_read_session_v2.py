"""真 fundamental snapshot V2 上的雙市場月營收 full-cohort consumer 反例。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from threading import Thread

import pytest

from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortReader,
    DailyMonthlyRevenueCohortError,
)
from data_module.daily_source_snapshot import DailySourceSnapshotError
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    DailyMarketMonthlyRevenueFactV2,
    DailyMarketMonthlyRevenueSourceReferenceV3,
    FinishedDailyMarketMonthlyRevenueCohortV2,
)
from data_module.daily_market_monthly_revenue_read_session_v2 import (
    DailyMarketMonthlyRevenueReadCancelledV2,
    DailyMarketMonthlyRevenueReadIncompleteV2,
    DailyMarketMonthlyRevenueReadSessionV2,
    DailyMarketMonthlyRevenueReadSessionV2Error,
)
from data_module.fundamental_read_snapshot import FundamentalReadSnapshotError
from data_module.fundamental_read_snapshot_daily_v2 import (
    FundamentalReadSnapshotSessionV2,
)
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    RecommendationCurrentFundamentalProvider,
)
from tests.test_selection_fundamental_daily_cohort_v2 import (
    _daily_cohort_environment,
    _source_db_state,
)
from tests.test_baldr_completion_p03_sources import CUTOFF


_CODES = ("1101", "2330")


def _open(tmp_path: Path, *, stock_codes: tuple[str, ...] = _CODES):
    provider, reader, pin, market_readers, market_roots = _daily_cohort_environment(tmp_path)
    source_state = _source_db_state(provider.db_file)
    session = DailyMarketMonthlyRevenueReadSessionV2.open(
        provider,
        daily_monthly_cohort_reader=reader,
        snapshot_root=tmp_path / "snapshot-v2",
        stock_codes=stock_codes,
        cutoff_at=CUTOFF,
    )
    return provider, reader, pin, market_readers, market_roots, source_state, session


def _finish_source_reference(tmp_path: Path):
    provider, reader, pin, market_readers, market_roots, source_state, session = _open(tmp_path)
    session.load_batch(_CODES)
    finished = session.finish()
    reference = session.source_reference
    return (
        provider, reader, pin, market_readers, market_roots, source_state,
        session, finished, reference,
    )


def test_real_v2_reader_emits_full_pinned_monthly_facts_and_exact_status_denominators(
    tmp_path: Path,
) -> None:
    provider, reader, pin, _, _, source_state, session = _open(tmp_path)
    try:
        batch = session.load_batch(_CODES)
        assert batch.complete is False
        assert batch.stock_codes == _CODES
        assert tuple(fact.stock_code for fact in batch.facts) == _CODES
        finished = session.finish()
        assert type(finished) is FinishedDailyMarketMonthlyRevenueCohortV2
        assert finished.declared_stock_codes == _CODES
        assert tuple(fact.stock_code for fact in finished.facts) == _CODES
        assert finished.cohort_pin == pin == reader.pin
        assert finished.source_clock.availability_status == "cohort_hour_bound"
        assert finished.source_clock.source_scope == "current_observed_only"
        assert finished.source_clock.formal_pit_eligible is False
        assert finished.source_clock.historical_pit_eligible is False
        assert sum(count for _, count in finished.reader_result_status_counts) == len(_CODES)
        assert sum(count for _, count in finished.fact_state_counts) == len(_CODES)
        assert finished.fact_state_counts == (("blocked", 0), ("observed", 1), ("unknown", 1))
        for fact in finished.facts:
            assert type(fact) is DailyMarketMonthlyRevenueFactV2
            assert fact.source_kind == "daily_monthly_revenue_cohort"
            assert fact.result.stock_code == fact.stock_code
            assert fact.result.cutoff_at == CUTOFF
            assert fact.result_identity_sha256 == dict(finished.result_identity_by_stock)[fact.stock_code]
            assert all(
                observation.unit == "TWD"
                and observation.period_basis == "monthly_flow"
                and observation.formal_pit_eligible is False
                for observation in fact.result.observations
            )
        assert session.finished and session.closed
        assert provider.daily_source_snapshot_reader is reader
        assert _source_db_state(provider.db_file) == source_state
    finally:
        session.close()


def test_future_cohort_hour_is_rejected_before_snapshot_copy_for_missing_stock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, reader, pin, _, _ = _daily_cohort_environment(
        tmp_path,
        delay_availability_hour=True,
    )
    source_state = _source_db_state(provider.db_file)
    cutoff = datetime(2026, 10, 4, 0, 45, tzinfo=timezone.utc)
    assert pin.available_hour.astimezone(timezone.utc) > cutoff
    target = tmp_path / "future-hour-must-not-copy"
    upstream_open_called = False

    def forbidden_snapshot_open(*args: object, **kwargs: object) -> FundamentalReadSnapshotSessionV2:
        nonlocal upstream_open_called
        upstream_open_called = True
        raise AssertionError("future cohort must be rejected before snapshot open")

    monkeypatch.setattr(FundamentalReadSnapshotSessionV2, "open", forbidden_snapshot_open)
    with pytest.raises(
        DailyMarketMonthlyRevenueReadSessionV2Error,
        match="available_hour_after_cutoff",
    ):
        DailyMarketMonthlyRevenueReadSessionV2.open(
            provider,
            daily_monthly_cohort_reader=reader,
            snapshot_root=target,
            stock_codes=("9999",),
            cutoff_at=cutoff,
        )
    assert not upstream_open_called
    assert not target.exists()
    assert _source_db_state(provider.db_file) == source_state


def test_exact_open_rejects_future_hour_before_recopy_for_missing_stock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, reader, pin, _, _ = _daily_cohort_environment(tmp_path / "origin")
    source_state = _source_db_state(provider.db_file)
    original = DailyMarketMonthlyRevenueReadSessionV2.open(
        provider,
        daily_monthly_cohort_reader=reader,
        snapshot_root=tmp_path / "origin" / "original-snapshot",
        stock_codes=("9999",),
        cutoff_at=CUTOFF,
    )
    original.load_batch(("9999",))
    finished = original.finish()
    assert finished.facts[0].status == "missing"
    reference = original.source_reference
    earlier_cutoff = datetime(2026, 10, 3, 23, 45, tzinfo=timezone.utc)
    assert pin.available_hour.astimezone(timezone.utc) > earlier_cutoff
    target = tmp_path / "future-hour-exact-must-not-copy"
    upstream_exact_open_called = False

    def forbidden_snapshot_open_exact(
        *args: object,
        **kwargs: object,
    ) -> FundamentalReadSnapshotSessionV2:
        nonlocal upstream_exact_open_called
        upstream_exact_open_called = True
        raise AssertionError("future cohort must be rejected before exact snapshot open")

    monkeypatch.setattr(
        FundamentalReadSnapshotSessionV2,
        "open_exact",
        forbidden_snapshot_open_exact,
    )
    try:
        with pytest.raises(
            DailyMarketMonthlyRevenueReadSessionV2Error,
            match="available_hour_after_cutoff",
        ):
            DailyMarketMonthlyRevenueReadSessionV2.open_exact(
                provider,
                daily_monthly_cohort_reader=reader,
                snapshot_root=target,
                source_reference=reference,
                expected_reference_sha256=reference.external_reference_sha256,
                stock_codes=("9999",),
                cutoff_at=earlier_cutoff,
            )
        assert not upstream_exact_open_called
        assert not target.exists()
        assert _source_db_state(provider.db_file) == source_state
    finally:
        original.close()


def test_exact_v3_reopen_reissues_same_fact_and_result_ledgers_without_source_write(
    tmp_path: Path,
) -> None:
    provider, reader, pin, _, _, source_state, session, original, reference = (
        _finish_source_reference(tmp_path / "original")
    )
    raw_reference = reference.to_json().encode("utf-8")
    external_sha = sha256(raw_reference).hexdigest()
    nested_raw = reference.upstream_reference.to_json().encode("utf-8")
    assert reference.upstream_reference_sha256 == sha256(nested_raw).hexdigest()
    reopened = DailyMarketMonthlyRevenueReadSessionV2.open_exact(
        provider,
        daily_monthly_cohort_reader=reader,
        snapshot_root=tmp_path / "reopened",
        source_reference=raw_reference,
        expected_reference_sha256=external_sha,
        stock_codes=_CODES,
        cutoff_at=CUTOFF,
    )
    try:
        reopened.load_batch(_CODES)
        fresh = reopened.finish()
        assert fresh.source_content_identity_sha256 == original.source_content_identity_sha256
        assert fresh.cohort_pin == pin
        assert fresh.result_identity_by_stock == original.result_identity_by_stock
        assert tuple((fact.stock_code, fact.identity_sha256) for fact in fresh.facts) == (
            reference.fact_identity_by_stock
        )
        assert fresh.reader_result_status_counts == reference.reader_result_status_counts
        assert fresh.fact_state_counts == reference.fact_state_counts
        assert reopened.source_reference.source_content_identity_sha256 == reference.source_content_identity_sha256
        assert _source_db_state(provider.db_file) == source_state
    finally:
        reopened.close()
        session.close()


def test_v3_external_digest_mismatch_is_rejected_before_snapshot_copy(tmp_path: Path) -> None:
    provider, reader, _, _, _, _, session, _, reference = _finish_source_reference(
        tmp_path / "origin"
    )
    target = tmp_path / "must-not-copy"
    try:
        with pytest.raises(ValueError, match="external_reference_sha_mismatch"):
            DailyMarketMonthlyRevenueReadSessionV2.open_exact(
                provider,
                daily_monthly_cohort_reader=reader,
                snapshot_root=target,
                source_reference=reference,
                expected_reference_sha256="0" * 64,
                stock_codes=_CODES,
                cutoff_at=CUTOFF,
            )
        assert not target.exists()
    finally:
        session.close()


@pytest.mark.parametrize("mismatch", ["codes", "cutoff"])
def test_v3_exact_reopen_rejects_caller_clock_or_codes_before_copy(
    tmp_path: Path,
    mismatch: str,
) -> None:
    provider, reader, _, _, _, _, session, _, reference = _finish_source_reference(
        tmp_path / "origin"
    )
    target = tmp_path / "must-not-copy"
    codes = ("2330",) if mismatch == "codes" else _CODES
    cutoff = CUTOFF + timedelta(days=1) if mismatch == "cutoff" else CUTOFF
    try:
        with pytest.raises(DailyMarketMonthlyRevenueReadSessionV2Error, match="exact_clock_codes"):
            DailyMarketMonthlyRevenueReadSessionV2.open_exact(
                provider,
                daily_monthly_cohort_reader=reader,
                snapshot_root=target,
                source_reference=reference,
                expected_reference_sha256=sha256(reference.to_json().encode("utf-8")).hexdigest(),
                stock_codes=codes,
                cutoff_at=cutoff,
            )
        assert not target.exists()
    finally:
        session.close()


def test_provider_must_retain_the_exact_daily_reader_before_snapshot_copy(tmp_path: Path) -> None:
    provider, reader, pin, market_readers, _, _, session = _open(tmp_path)
    session.close()
    wrong_reader = DailyMonthlyRevenueCohortReader(
        pin=pin,
        market_readers=market_readers,
        expected_cohort_sha256=pin.cohort_sha256,
    )
    target = tmp_path / "wrong-reader-copy"
    with pytest.raises(DailyMarketMonthlyRevenueReadSessionV2Error, match="reader_identity"):
        DailyMarketMonthlyRevenueReadSessionV2.open(
            provider,
            daily_monthly_cohort_reader=wrong_reader,
            snapshot_root=target,
            stock_codes=_CODES,
            cutoff_at=CUTOFF,
        )
    assert provider.daily_source_snapshot_reader is reader
    assert not target.exists()


def test_partial_declared_cohort_closes_and_never_issues_finished_or_reference(
    tmp_path: Path,
) -> None:
    _, _, _, _, _, _, session = _open(tmp_path)
    session.load_batch((_CODES[0],))
    with pytest.raises(DailyMarketMonthlyRevenueReadIncompleteV2):
        session.finish()
    assert session.closed and not session.finished
    with pytest.raises(DailyMarketMonthlyRevenueReadSessionV2Error, match="requires_finished"):
        _ = session.source_reference


def test_batch_must_match_next_ordered_slice_and_uses_cohort_bound_identity(
    tmp_path: Path,
) -> None:
    _, _, pin, _, _, _, session = _open(tmp_path)
    try:
        with pytest.raises(ValueError, match="next_declared_codes"):
            session.load_batch((_CODES[1],))
        batch = session.load_batch((_CODES[0],))
        assert batch.batch_index == 0
        assert batch.cohort_sha256 == pin.cohort_sha256
        assert batch.complete is False
        with pytest.raises(ValueError, match="next_declared_codes"):
            session.load_batch((_CODES[0],))
        last = session.load_batch((_CODES[1],))
        assert last.batch_index == 1
        assert tuple(fact.stock_code for fact in last.facts) == (_CODES[1],)
        session.finish()
    finally:
        session.close()


def test_missing_provider_result_is_retained_as_unknown_fact_not_dropped(tmp_path: Path) -> None:
    provider, reader, pin, _, _, _, session = _open(tmp_path, stock_codes=("9999",))
    try:
        batch = session.load_batch(("9999",))
        fact = batch.facts[0]
        assert fact.result.status == "missing"
        assert fact.state == "unknown"
        assert fact.result.observations == ()
        assert fact.result.comparison_baseline is None
        finished = session.finish()
        assert finished.fact_state_counts == (("blocked", 0), ("observed", 0), ("unknown", 1))
        assert finished.cohort_pin == pin == reader.pin
    finally:
        session.close()


def test_invalid_comparator_diagnostic_remains_unknown_and_is_not_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, reader, _, _, _, _, session = _open(tmp_path, stock_codes=("2330",))
    original = RecommendationCurrentFundamentalProvider.load_monthly_revenues

    def invalid_comparator(self, **kwargs):
        result = original(self, **kwargs)
        return replace(
            result,
            comparison_baseline=None,
            diagnostics=tuple(result.diagnostics) + (
                "current_monthly_revenue_comparison_value_nonpositive:2026-04",
            ),
        )

    monkeypatch.setattr(
        RecommendationCurrentFundamentalProvider,
        "load_monthly_revenues",
        invalid_comparator,
    )
    try:
        fact = session.load_batch(("2330",)).facts[0]
        assert fact.result.status == "ready"
        assert fact.result.observations
        assert fact.result.comparison_baseline is None
        assert fact.state == "unknown"
        assert any("comparison_value_nonpositive" in item for item in fact.result.diagnostics)
        finished = session.finish()
        assert finished.fact_state_counts == (("blocked", 0), ("observed", 0), ("unknown", 1))
    finally:
        session.close()


def test_unavailable_provider_result_is_preserved_as_blocked_fact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, reader, pin, _, _, _, session = _open(tmp_path, stock_codes=("2330",))

    def unavailable(self, *, stock_code, cutoff_at, **kwargs):
        return CurrentMonthlyRevenueReadResult(
            status="unavailable",
            stock_code=stock_code,
            cutoff_at=cutoff_at,
            latest_period=None,
            diagnostics=("fixture_provider_unavailable",),
        )

    monkeypatch.setattr(
        RecommendationCurrentFundamentalProvider,
        "load_monthly_revenues",
        unavailable,
    )
    try:
        fact = session.load_batch(("2330",)).facts[0]
        assert fact.result.status == "unavailable"
        assert fact.state == "blocked"
        assert fact.result.diagnostics == ("fixture_provider_unavailable",)
        finished = session.finish()
        assert finished.fact_state_counts == (("blocked", 1), ("observed", 0), ("unknown", 0))
        assert finished.cohort_pin == pin == reader.pin
    finally:
        session.close()


def test_cancel_after_upstream_snapshot_publication_prevents_monthly_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancelled = False
    provider, reader, _, _, _, _, session = _open(tmp_path)
    # 使用新的 session，令 upstream finish 後月營收 publication 前收到晚取消。
    session.close()
    provider, reader, _, _, _, _, session = _open(tmp_path / "late-cancel")
    session._cancel_callback = lambda: cancelled
    session.load_batch(_CODES)
    original_finish = FundamentalReadSnapshotSessionV2.finish

    def finish_then_cancel(snapshot):
        nonlocal cancelled
        finished = original_finish(snapshot)
        cancelled = True
        return finished

    monkeypatch.setattr(FundamentalReadSnapshotSessionV2, "finish", finish_then_cancel)
    with pytest.raises(DailyMarketMonthlyRevenueReadCancelledV2):
        session.finish()
    manifest = session.snapshot_root / "finished_source_clock.json"
    assert '"manifest_state":"complete"' in manifest.read_text(encoding="utf-8")
    assert session.closed and not session.finished


def test_second_market_mutation_after_upstream_finish_prevents_monthly_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, reader, _, _, market_roots, _, session = _open(tmp_path)
    session.load_batch(_CODES)
    original_finish = FundamentalReadSnapshotSessionV2.finish

    def finish_then_mutate(snapshot):
        finished = original_finish(snapshot)
        receipt = next(market_roots["tpex"].rglob("receipt.json"))
        receipt.write_bytes(b"{}")
        return finished

    monkeypatch.setattr(FundamentalReadSnapshotSessionV2, "finish", finish_then_mutate)
    with pytest.raises((DailyMonthlyRevenueCohortError, FundamentalReadSnapshotError, DailySourceSnapshotError)):
        session.finish()
    manifest = session.snapshot_root / "finished_source_clock.json"
    assert '"manifest_state":"complete"' in manifest.read_text(encoding="utf-8")
    assert session.closed and not session.finished


def test_cross_thread_cancel_signals_and_owner_closes_reader(tmp_path: Path) -> None:
    _, _, _, _, _, _, session = _open(tmp_path)
    outcomes: list[object] = []

    def cancel_from_foreign_thread() -> None:
        outcomes.append(session.cancel())
        try:
            session.close()
        except DailyMarketMonthlyRevenueReadSessionV2Error:
            outcomes.append("foreign-close-refused")

    worker = Thread(target=cancel_from_foreign_thread)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert outcomes == [True, "foreign-close-refused"]
    session.close()
    assert session.closed
