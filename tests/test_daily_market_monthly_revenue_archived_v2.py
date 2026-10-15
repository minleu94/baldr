"""月營收與 YoY V2 在 live source 漂移後以自含 archive exact 重開。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
import sqlite3

import pytest

from app_module.daily_market_monthly_revenue_yoy_index_v2 import (
    DailyMarketMonthlyRevenueYoyIndexSessionV2,
)
from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
)
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    DailyMarketMonthlyRevenueSourceReferenceV3,
    _fact_ledger_identity_sha256,
    _reference_finished_identity,
    _source_content_identity,
)
from data_module.daily_market_monthly_revenue_read_session_v2 import (
    DailyMarketMonthlyRevenueReadCancelledV2,
    DailyMarketMonthlyRevenueReadIncompleteV2,
    DailyMarketMonthlyRevenueReadSessionV2,
    DailyMarketMonthlyRevenueReadSessionV2Error,
)
from data_module.fundamental_read_snapshot import FundamentalReadSnapshotError
from data_module.fundamental_read_snapshot_raw_archive_v2 import (
    FundamentalReadSnapshotRawArchiveReferenceV2,
)
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)
from tests.test_baldr_completion_p03_sources import CUTOFF, REPORT_PERIOD
from tests.test_selection_fundamental_daily_cohort_v2 import (
    _daily_cohort_environment,
    _source_db_state,
)


_CODES = ("1101", "2330", "9999")


def _open_monthly(
    root: Path,
    *,
    stock_codes: tuple[str, ...] = _CODES,
    cutoff_at: datetime = CUTOFF,
) -> tuple[
    RecommendationCurrentFundamentalProvider,
    DailyMonthlyRevenueCohortReader,
    DailyMarketMonthlyRevenueReadSessionV2,
]:
    provider, reader, _, _, _ = _daily_cohort_environment(root / "source")
    session = DailyMarketMonthlyRevenueReadSessionV2.open(
        provider,
        daily_monthly_cohort_reader=reader,
        snapshot_root=root / "snapshot-v2",
        stock_codes=stock_codes,
        cutoff_at=cutoff_at,
    )
    return provider, reader, session


def _finished_monthly_archive(
    root: Path,
) -> tuple[
    RecommendationCurrentFundamentalProvider,
    DailyMonthlyRevenueCohortReader,
    DailyMarketMonthlyRevenueReadSessionV2,
    DailyMarketMonthlyRevenueSourceReferenceV3,
    FundamentalReadSnapshotRawArchiveReferenceV2,
]:
    provider, reader, session = _open_monthly(root)
    session.load_batch(_CODES)
    session.finish()
    source_reference = session.source_reference
    archive_reference = session.archive_monthly_raw_sources(root / "archives")
    return provider, reader, session, source_reference, archive_reference


def _open_index_archive(
    root: Path,
) -> tuple[
    RecommendationCurrentFundamentalProvider,
    DailyMonthlyRevenueCohortReader,
    DailyMarketMonthlyRevenueYoyIndexSessionV2,
    DailyMarketMonthlyRevenueSourceReferenceV3,
    FundamentalReadSnapshotRawArchiveReferenceV2,
]:
    provider, reader, _, _, _ = _daily_cohort_environment(root / "source")
    session = DailyMarketMonthlyRevenueYoyIndexSessionV2.open(
        provider,
        daily_monthly_cohort_reader=reader,
        snapshot_root=root / "snapshot-index-v2",
        stock_codes=_CODES,
        cutoff_at=CUTOFF,
    )
    session.load_batch(_CODES)
    session.finish()
    source_reference = session.source_reference
    archive_reference = session.archive_monthly_raw_sources(root / "archives")
    return provider, reader, session, source_reference, archive_reference


def _source_json_and_sha(
    reference: DailyMarketMonthlyRevenueSourceReferenceV3,
) -> tuple[bytes, str]:
    raw = reference.to_json().encode("utf-8")
    return raw, sha256(raw).hexdigest()


def _archive_json_and_sha(
    reference: FundamentalReadSnapshotRawArchiveReferenceV2,
) -> tuple[bytes, str]:
    raw = reference.to_json().encode("utf-8")
    return raw, sha256(raw).hexdigest()


def test_monthly_archive_reopen_ignores_live_db_raw_source_and_original_snapshot(
    tmp_path: Path,
) -> None:
    provider, reader, original, source_reference, archive_reference = (
        _finished_monthly_archive(tmp_path)
    )
    source_state = _source_db_state(provider.db_file)
    capture_path = (
        provider.monthly_source_root
        / "monthly_revenue_mops_snapshots"
        / "raw_html"
        / f"twse_{REPORT_PERIOD}.html"
    )
    original_capture = capture_path.read_bytes()
    original_snapshot_root = original.snapshot_root
    moved_snapshot_root = tmp_path / "moved-original-snapshot"
    archive_raw, archive_sha = _archive_json_and_sha(archive_reference)
    source_raw, source_sha = _source_json_and_sha(source_reference)
    original.close()

    connection = sqlite3.connect(provider.db_file)
    try:
        cursor = connection.execute(
            "UPDATE fundamental_current_observations SET value=? "
            "WHERE stock_code=? AND kind='monthly_revenue' AND item_code='revenue' "
            "AND period=?",
            ("999999999999", "2330", REPORT_PERIOD),
        )
        assert cursor.rowcount == 1
        connection.commit()
    finally:
        connection.close()
    capture_path.write_bytes(original_capture + b"\n<!-- fixture revision -->\n")
    original_snapshot_root.rename(moved_snapshot_root)

    assert _source_db_state(provider.db_file) != source_state
    assert capture_path.read_bytes() != original_capture
    assert moved_snapshot_root.exists()
    assert Path(archive_reference.archived_snapshot_root).exists()

    replay = DailyMarketMonthlyRevenueReadSessionV2.open_exact_archived(
        provider,
        daily_monthly_cohort_reader=reader,
        snapshot_root=tmp_path / "archive-replay-operation",
        source_reference=source_raw,
        expected_reference_sha256=source_sha,
        raw_archive_reference=archive_raw,
        expected_archive_reference_sha256=archive_sha,
        stock_codes=_CODES,
        cutoff_at=CUTOFF,
    )
    try:
        batch = replay.load_batch(_CODES)
        finished = replay.finish()
        assert batch.stock_codes == _CODES
        assert tuple(zip(_CODES, batch.result_identity_sha256, strict=True)) == (
            source_reference.result_identity_by_stock
        )
        assert finished.declared_stock_codes == _CODES
        assert finished.result_identity_by_stock == source_reference.result_identity_by_stock
        assert finished.fact_identity_by_stock == source_reference.fact_identity_by_stock
        assert finished.reader_result_status_counts == source_reference.reader_result_status_counts
        assert finished.fact_state_counts == source_reference.fact_state_counts
        assert finished.fact_state_counts == (
            ("blocked", 0),
            ("observed", 1),
            ("unknown", 2),
        )
        assert sum(count for _, count in finished.reader_result_status_counts) == len(_CODES)
        assert sum(count for _, count in finished.fact_state_counts) == len(_CODES)
        assert finished.source_clock.cohort_pin == reader.pin
        assert finished.source_clock.decision_cutoff == CUTOFF
        assert finished.source_clock.formal_pit_eligible is False
        assert finished.source_clock.historical_pit_eligible is False
        assert replay.finished and replay.closed
        assert _source_db_state(provider.db_file) != source_state
        with pytest.raises(FundamentalReadSnapshotError, match="rearchive"):
            replay.archive_monthly_raw_sources(tmp_path / "rearchive-must-fail")
        assert not (tmp_path / "rearchive-must-fail").exists()
    finally:
        replay.close()


def test_yoy_index_archive_reopen_preserves_projected_and_source_denominators(
    tmp_path: Path,
) -> None:
    provider, reader, original, source_reference, archive_reference = _open_index_archive(
        tmp_path
    )
    source_raw, source_sha = _source_json_and_sha(source_reference)
    archive_raw, archive_sha = _archive_json_and_sha(archive_reference)
    original_index = original._finished_index
    assert original_index is not None
    original.close()

    replay = DailyMarketMonthlyRevenueYoyIndexSessionV2.open_exact_archived(
        provider,
        daily_monthly_cohort_reader=reader,
        snapshot_root=tmp_path / "index-archive-replay",
        source_reference=source_raw,
        expected_reference_sha256=source_sha,
        raw_archive_reference=archive_raw,
        expected_archive_reference_sha256=archive_sha,
        stock_codes=_CODES,
        cutoff_at=CUTOFF,
    )
    try:
        candidate = replay.load_batch(_CODES)
        index = replay.finish()
        assert candidate.stock_codes == _CODES
        assert tuple(zip(_CODES, candidate.result_identity_sha256, strict=True)) == (
            original_index.result_identity_by_stock
        )
        assert index.declared_stock_codes == _CODES
        assert index.result_identity_by_stock == original_index.result_identity_by_stock
        assert index.fact_identity_by_stock == original_index.fact_identity_by_stock
        assert index.projected_fact_identity_by_stock == (
            original_index.projected_fact_identity_by_stock
        )
        assert index.reader_result_status_counts == (("missing", 2), ("ready", 1))
        assert index.fact_state_counts == (("blocked", 0), ("observed", 1), ("unknown", 2))
        assert index.projected_state_counts == (("observed", 1), ("unknown", 2))
        assert sum(count for _, count in index.reader_result_status_counts) == len(_CODES)
        assert sum(count for _, count in index.fact_state_counts) == len(_CODES)
        assert sum(count for _, count in index.projected_state_counts) == len(_CODES)
        assert replay.closed and replay.finished
        with pytest.raises(FundamentalReadSnapshotError, match="rearchive"):
            replay.archive_monthly_raw_sources(tmp_path / "index-rearchive-must-fail")
        assert not (tmp_path / "index-rearchive-must-fail").exists()
    finally:
        replay.close()


def test_monthly_archived_open_rejects_wrong_external_sha_and_cutoff_before_copy(
    tmp_path: Path,
) -> None:
    provider, reader, original, source_reference, archive_reference = (
        _finished_monthly_archive(tmp_path)
    )
    source_raw, source_sha = _source_json_and_sha(source_reference)
    archive_raw, archive_sha = _archive_json_and_sha(archive_reference)
    original.close()

    bad_archive_target = tmp_path / "bad-archive-anchor-operation"
    with pytest.raises((DailyMarketMonthlyRevenueReadSessionV2Error, ValueError)):
        DailyMarketMonthlyRevenueReadSessionV2.open_exact_archived(
            provider,
            daily_monthly_cohort_reader=reader,
            snapshot_root=bad_archive_target,
            source_reference=source_raw,
            expected_reference_sha256=source_sha,
            raw_archive_reference=archive_raw,
            expected_archive_reference_sha256="0" * 64,
            stock_codes=_CODES,
            cutoff_at=CUTOFF,
        )
    assert not bad_archive_target.exists()

    bad_source_target = tmp_path / "bad-source-anchor-operation"
    with pytest.raises((DailyMarketMonthlyRevenueReadSessionV2Error, ValueError)):
        DailyMarketMonthlyRevenueReadSessionV2.open_exact_archived(
            provider,
            daily_monthly_cohort_reader=reader,
            snapshot_root=bad_source_target,
            source_reference=source_raw,
            expected_reference_sha256="0" * 64,
            raw_archive_reference=archive_raw,
            expected_archive_reference_sha256=archive_sha,
            stock_codes=_CODES,
            cutoff_at=CUTOFF,
        )
    assert not bad_source_target.exists()

    bad_cutoff_target = tmp_path / "bad-cutoff-operation"
    with pytest.raises(DailyMarketMonthlyRevenueReadSessionV2Error):
        DailyMarketMonthlyRevenueReadSessionV2.open_exact_archived(
            provider,
            daily_monthly_cohort_reader=reader,
            snapshot_root=bad_cutoff_target,
            source_reference=source_raw,
            expected_reference_sha256=source_sha,
            raw_archive_reference=archive_raw,
            expected_archive_reference_sha256=archive_sha,
            stock_codes=_CODES,
            cutoff_at=CUTOFF + timedelta(minutes=1),
        )
    assert not bad_cutoff_target.exists()


def test_monthly_archive_reference_cannot_be_cross_paired_with_another_source(
    tmp_path: Path,
) -> None:
    provider, reader, first_session, first_reference, archive_reference = (
        _finished_monthly_archive(tmp_path / "first")
    )
    second_provider, second_reader, second_session = _open_monthly(tmp_path / "second")
    try:
        second_session.load_batch(_CODES)
        second_session.finish()
        second_reference = second_session.source_reference
        assert second_reference.upstream_reference != first_reference.upstream_reference
        source_raw, source_sha = _source_json_and_sha(second_reference)
        archive_raw, archive_sha = _archive_json_and_sha(archive_reference)
        target = tmp_path / "cross-paired-operation"
        with pytest.raises(DailyMarketMonthlyRevenueReadSessionV2Error):
            DailyMarketMonthlyRevenueReadSessionV2.open_exact_archived(
                provider,
                daily_monthly_cohort_reader=reader,
                snapshot_root=target,
                source_reference=source_raw,
                expected_reference_sha256=source_sha,
                raw_archive_reference=archive_raw,
                expected_archive_reference_sha256=archive_sha,
                stock_codes=_CODES,
                cutoff_at=CUTOFF,
            )
        assert not target.exists()
        assert second_provider.daily_source_snapshot_reader is second_reader
    finally:
        first_session.close()
        second_session.close()


def test_monthly_archive_exact_open_rejects_a_different_daily_full_pin(
    tmp_path: Path,
) -> None:
    provider, reader, pin, market_readers, _ = _daily_cohort_environment(
        tmp_path / "source"
    )
    original = DailyMarketMonthlyRevenueReadSessionV2.open(
        provider,
        daily_monthly_cohort_reader=reader,
        snapshot_root=tmp_path / "snapshot-v2",
        stock_codes=_CODES,
        cutoff_at=CUTOFF,
    )
    original.load_batch(_CODES)
    original.finish()
    source_reference = original.source_reference
    archive_reference = original.archive_monthly_raw_sources(tmp_path / "archives")

    changed_tpex_pin = replace(
        pin.for_market("tpex"),
        batch_id="different-pinned-batch",
    )
    changed_pin = DailyMonthlyRevenueCohortPin(
        period=pin.period,
        required_markets=pin.required_markets,
        market_pins=(pin.for_market("twse"), changed_tpex_pin),
        available_hour=pin.available_hour,
        time_basis_policy=pin.time_basis_policy,
    )
    other_reader = DailyMonthlyRevenueCohortReader(
        pin=changed_pin,
        market_readers=market_readers,
        expected_cohort_sha256=changed_pin.cohort_sha256,
    )
    source_raw, source_sha = _source_json_and_sha(source_reference)
    archive_raw, archive_sha = _archive_json_and_sha(archive_reference)
    original.close()
    provider.daily_source_snapshot_reader = other_reader
    target = tmp_path / "wrong-full-pin-operation"
    try:
        with pytest.raises(DailyMarketMonthlyRevenueReadSessionV2Error):
            DailyMarketMonthlyRevenueReadSessionV2.open_exact_archived(
                provider,
                daily_monthly_cohort_reader=other_reader,
                snapshot_root=target,
                source_reference=source_raw,
                expected_reference_sha256=source_sha,
                raw_archive_reference=archive_raw,
                expected_archive_reference_sha256=archive_sha,
                stock_codes=_CODES,
                cutoff_at=CUTOFF,
            )
        assert not target.exists()
        assert changed_pin.available_hour == pin.available_hour
        assert changed_pin.cohort_sha256 != pin.cohort_sha256
    finally:
        provider.daily_source_snapshot_reader = reader


def test_monthly_archive_exact_open_observes_cancellation_before_copy(
    tmp_path: Path,
) -> None:
    provider, reader, original, source_reference, archive_reference = (
        _finished_monthly_archive(tmp_path)
    )
    source_raw, source_sha = _source_json_and_sha(source_reference)
    archive_raw, archive_sha = _archive_json_and_sha(archive_reference)
    original.close()
    target = tmp_path / "cancelled-archive-operation"
    with pytest.raises(DailyMarketMonthlyRevenueReadCancelledV2):
        DailyMarketMonthlyRevenueReadSessionV2.open_exact_archived(
            provider,
            daily_monthly_cohort_reader=reader,
            snapshot_root=target,
            source_reference=source_raw,
            expected_reference_sha256=source_sha,
            raw_archive_reference=archive_raw,
            expected_archive_reference_sha256=archive_sha,
            stock_codes=_CODES,
            cutoff_at=CUTOFF,
            cancel_callback=lambda: True,
        )
    assert not target.exists()


def test_unfinished_monthly_session_cannot_archive_a_partial_cohort(
    tmp_path: Path,
) -> None:
    _, _, session = _open_monthly(tmp_path)
    try:
        session.load_batch(_CODES[:2])
        with pytest.raises(DailyMarketMonthlyRevenueReadSessionV2Error):
            session.archive_monthly_raw_sources(tmp_path / "partial-archives")
        assert not (tmp_path / "partial-archives").exists()
        with pytest.raises(DailyMarketMonthlyRevenueReadIncompleteV2):
            session.finish()
    finally:
        session.close()


def test_archived_monthly_reference_with_self_consistent_wrong_fact_ledger_is_rejected(
    tmp_path: Path,
) -> None:
    provider, reader, original, source_reference, archive_reference = (
        _finished_monthly_archive(tmp_path)
    )
    original.close()
    changed_fact_ledger = list(source_reference.fact_identity_by_stock)
    changed_fact_ledger[-1] = (changed_fact_ledger[-1][0], "f" * 64)
    frozen_fact_ledger = tuple(changed_fact_ledger)
    changed_content_identity = _source_content_identity(
        source_clock=archive_reference.source_clock,
        declared_stock_codes=source_reference.declared_stock_codes,
        result_identity_by_stock=source_reference.result_identity_by_stock,
        fact_identity_by_stock=frozen_fact_ledger,
        reader_result_status_counts=source_reference.reader_result_status_counts,
        fact_state_counts=source_reference.fact_state_counts,
    )
    changed_finished_identity = _reference_finished_identity(
        upstream_reference=source_reference.upstream_reference,
        upstream_reference_sha256=source_reference.upstream_reference_sha256,
        source_content_identity_sha256=changed_content_identity,
        result_identity_by_stock=source_reference.result_identity_by_stock,
        fact_identity_by_stock=frozen_fact_ledger,
        reader_result_status_counts=source_reference.reader_result_status_counts,
        fact_state_counts=source_reference.fact_state_counts,
    )
    forged_reference = replace(
        source_reference,
        fact_identity_by_stock=frozen_fact_ledger,
        fact_ledger_identity_sha256=_fact_ledger_identity_sha256(frozen_fact_ledger),
        source_content_identity_sha256=changed_content_identity,
        finished_cohort_identity_sha256=changed_finished_identity,
    )
    source_raw, source_sha = _source_json_and_sha(forged_reference)
    archive_raw, archive_sha = _archive_json_and_sha(archive_reference)
    assert source_sha != source_reference.external_reference_sha256

    replay = DailyMarketMonthlyRevenueReadSessionV2.open_exact_archived(
        provider,
        daily_monthly_cohort_reader=reader,
        snapshot_root=tmp_path / "forged-ledger-operation",
        source_reference=source_raw,
        expected_reference_sha256=source_sha,
        raw_archive_reference=archive_raw,
        expected_archive_reference_sha256=archive_sha,
        stock_codes=_CODES,
        cutoff_at=CUTOFF,
    )
    try:
        replay.load_batch(_CODES)
        with pytest.raises(DailyMarketMonthlyRevenueReadSessionV2Error, match="fact_or_source_ledger"):
            replay.finish()
        assert replay.closed
        assert not replay.finished
    finally:
        replay.close()
