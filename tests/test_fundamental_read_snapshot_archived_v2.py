"""以真 SQLite provider 驗證 V2 snapshot/raw archive 的自包含重開契約。"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import stat
from typing import Callable

import pytest

from data_module.fundamental_read_snapshot import (
    FundamentalReadSnapshotCancelled,
    FundamentalReadSnapshotError,
    FundamentalReadSnapshotRawArchiveReferenceV1,
    FundamentalReadSnapshotSession,
)
from data_module.fundamental_read_snapshot_cohort_v2 import (
    FinishedFundamentalSnapshotReadCohortV2,
    FundamentalReadSnapshotReferenceV2,
)
from data_module.fundamental_read_snapshot_daily_v2 import (
    FundamentalReadSnapshotSessionV2,
)
from data_module.fundamental_read_snapshot_raw_archive_v2 import (
    FundamentalReadSnapshotArchiveStoredFileV2,
    FundamentalReadSnapshotRawArchiveFileV2,
    FundamentalReadSnapshotRawArchiveReferenceV2,
)
from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
)
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)
from data_module.selection_fact_readers import (
    FundamentalReadBatchCandidateV2,
    FundamentalReadSessionError,
    FundamentalReadSessionIncomplete,
)
from tests.test_baldr_completion_p03_sources import CUTOFF, REPORT_PERIOD
from tests.test_selection_fundamental_daily_cohort_v2 import (
    _daily_cohort_environment,
    _source_db_state,
)


_CODES = ("2330", "6488", "9999")


def _archive_fixture(
    tmp_path: Path,
    *,
    delay_availability_hour: bool = False,
) -> tuple[
    RecommendationCurrentFundamentalProvider,
    DailyMonthlyRevenueCohortReader,
    DailyMonthlyRevenueCohortPin,
    tuple[bytes, int, tuple[bool, bool]],
    FundamentalReadSnapshotSessionV2,
    FundamentalReadBatchCandidateV2,
    FinishedFundamentalSnapshotReadCohortV2,
    FundamentalReadSnapshotRawArchiveReferenceV2,
    bytes,
]:
    """建立真雙市場 reader、真 SQLite V2 snapshot，再封存其原件。"""

    provider, reader, pin, _, _ = _daily_cohort_environment(
        tmp_path / "source",
        delay_availability_hour=delay_availability_hour,
    )
    source_db_state = _source_db_state(provider.db_file)
    session = FundamentalReadSnapshotSessionV2.open(
        provider,
        snapshot_root=tmp_path / "original-snapshot",
        stock_codes=_CODES,
        cutoff_at=CUTOFF,
        daily_monthly_cohort_reader=reader,
    )
    batch = session.load_batch(_CODES)
    finished = session.finish()
    archive_reference = session.archive_monthly_raw_sources(
        tmp_path / "raw-archives"
    )
    assert type(archive_reference) is FundamentalReadSnapshotRawArchiveReferenceV2
    assert type(archive_reference.snapshot_reference) is FundamentalReadSnapshotReferenceV2
    raw_reference = archive_reference.to_json().encode("utf-8")
    return (
        provider,
        reader,
        pin,
        source_db_state,
        session,
        batch,
        finished,
        archive_reference,
        raw_reference,
    )


def _open_exact_archived(
    provider: RecommendationCurrentFundamentalProvider,
    reader: DailyMonthlyRevenueCohortReader,
    *,
    snapshot_root: Path,
    archive_reference: FundamentalReadSnapshotRawArchiveReferenceV2 | str | bytes,
    expected_sha256: str,
    stock_codes: tuple[str, ...] = _CODES,
    cutoff_at: datetime = CUTOFF,
    cancel_callback: Callable[[], bool] | None = None,
):
    """以 caller 固定的 archive bytes SHA 開啟全 cohort exact replay。"""

    return FundamentalReadSnapshotSessionV2.open_exact_archived(
        provider,
        raw_archive_reference=archive_reference,
        expected_archive_reference_sha256=expected_sha256,
        daily_monthly_cohort_reader=reader,
        snapshot_root=snapshot_root,
        stock_codes=stock_codes,
        cutoff_at=cutoff_at,
        cancel_callback=cancel_callback,
    )


def _batch_payload(batch: FundamentalReadBatchCandidateV2) -> tuple[object, ...]:
    """保留狀態、結果識別碼與精確 Decimal observations。"""

    return tuple(
        (
            result.stock_code,
            result.status,
            result.latest_period,
            result.diagnostics,
            result.blocked_periods,
            batch.result_identity_sha256[index],
            tuple(
                (
                    observation.period,
                    observation.revenue,
                    observation.unit,
                    observation.source_version,
                    observation.raw_source_sha256,
                    observation.available_at,
                    observation.formal_pit_eligible,
                )
                for observation in result.observations
            ),
        )
        for index, result in enumerate(batch.results)
    )


def _archive_file_path(
    reference: FundamentalReadSnapshotRawArchiveReferenceV2,
    relative_path: str,
) -> Path:
    return Path(reference.archive_root).joinpath(*relative_path.split("/"))


def _make_fixture_archive_file_writable(path: Path) -> None:
    """只解除測試指定 archive 成員的唯讀位元，供後續篡改反例使用。"""

    path.chmod(path.stat().st_mode | stat.S_IREAD | stat.S_IWRITE)


def _one_raw_html(
    reference: FundamentalReadSnapshotRawArchiveReferenceV2,
) -> FundamentalReadSnapshotRawArchiveFileV2:
    return next(
        item
        for item in reference.files
        if item.historical_pin.role == "monthly_html"
    )


def _one_stored_database(
    reference: FundamentalReadSnapshotRawArchiveReferenceV2,
) -> FundamentalReadSnapshotArchiveStoredFileV2:
    return next(
        item
        for item in reference.snapshot_files
        if Path(item.relative_path).suffix.lower() in {".sqlite", ".db"}
    )


def test_archived_v2_reopens_after_live_db_capture_and_original_snapshot_move(
    tmp_path: Path,
) -> None:
    (
        provider,
        reader,
        pin,
        original_db_state,
        original_session,
        original_batch,
        original_finished,
        archive_reference,
        archive_raw,
    ) = _archive_fixture(tmp_path)
    source_capture = (
        provider.monthly_source_root
        / "monthly_revenue_mops_snapshots"
        / "raw_html"
        / f"twse_{REPORT_PERIOD}.html"
    )
    original_capture = source_capture.read_bytes()
    original_reference = original_session.source_reference
    preserved_snapshot = tmp_path / "preserved-original-snapshot"
    old_snapshot_root = original_session.snapshot_root
    assert old_snapshot_root.exists()

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
    source_capture.write_bytes(original_capture + b"\n<!-- fixture revision -->\n")
    old_snapshot_root.rename(preserved_snapshot)

    assert preserved_snapshot.exists()
    assert _source_db_state(provider.db_file) != original_db_state
    assert source_capture.read_bytes() != original_capture
    assert Path(archive_reference.archived_snapshot_root).exists()
    assert archive_reference.snapshot_reference == original_reference

    reopened_provider = RecommendationCurrentFundamentalProvider(
        db_file=provider.db_file,
        output_root=provider.output_root,
        monthly_source_root=provider.monthly_source_root,
        daily_source_snapshot_reader=reader,
    )
    reopened = _open_exact_archived(
        reopened_provider,
        reader,
        snapshot_root=tmp_path / "archived-replay-operation",
        archive_reference=archive_raw,
        expected_sha256=sha256(archive_raw).hexdigest(),
    )
    try:
        replay_batch = reopened.load_batch(_CODES)
        replay_finished = reopened.finish()
        assert replay_batch.result_identity_sha256 == original_batch.result_identity_sha256
        assert replay_finished.result_identity_by_stock == original_finished.result_identity_by_stock
        assert replay_finished.result_status_counts == original_finished.result_status_counts
        assert replay_finished.processed_stock_codes == _CODES
        assert _batch_payload(replay_batch) == _batch_payload(original_batch)
        observed_values = tuple(
            observation.revenue
            for result in replay_batch.results
            for observation in result.observations
        )
        assert observed_values
        assert all(type(value) is Decimal for value in observed_values)
        assert replay_finished.source_clock.cohort_pin == pin
        assert replay_finished.source_clock.cohort_pin == reader.pin
        assert (
            replay_finished.source_clock.cohort_pin.available_hour
            == original_finished.source_clock.cohort_pin.available_hour
        )
        assert replay_finished.source_clock.availability_status == "cohort_hour_bound"
        assert replay_finished.source_clock.source_scope == "current_observed_only"
        assert replay_finished.source_clock.declared_stock_codes == _CODES
        assert replay_finished.source_clock.decision_cutoff == CUTOFF
        assert sum(count for _, count in replay_finished.result_status_counts) == len(_CODES)
        assert replay_finished.source_clock.source_content_identity_sha256 == (
            original_finished.source_clock.source_content_identity_sha256
        )
        assert replay_finished.source_clock.formal_pit_eligible is False
        assert replay_finished.source_clock.historical_pit_eligible is False
        assert reopened.closed and reopened.finished
    finally:
        reopened.close()
        original_session.close()


def test_archived_v2_requires_the_external_archive_reference_sha_before_copy(
    tmp_path: Path,
) -> None:
    provider, reader, _, _, session, _, _, reference, raw = _archive_fixture(tmp_path)
    target = tmp_path / "wrong-external-sha-operation"
    try:
        with pytest.raises(FundamentalReadSnapshotError):
            _open_exact_archived(
                provider,
                reader,
                snapshot_root=target,
                archive_reference=raw,
                expected_sha256="0" * 64,
            )
        assert not target.exists()
        assert session.finished and session.closed
    finally:
        session.close()


def test_archived_v2_does_not_fallback_from_unarchived_snapshot_reference(
    tmp_path: Path,
) -> None:
    provider, reader, _, _, session, _, _, archive_reference, _ = _archive_fixture(tmp_path)
    target = tmp_path / "unarchived-reference-must-not-copy"
    raw_snapshot_reference = archive_reference.snapshot_reference.to_json().encode("utf-8")
    try:
        with pytest.raises((FundamentalReadSnapshotError, TypeError, ValueError)):
            _open_exact_archived(
                provider,
                reader,
                snapshot_root=target,
                archive_reference=archive_reference.snapshot_reference,
                expected_sha256=sha256(raw_snapshot_reference).hexdigest(),
            )
        assert not target.exists()
    finally:
        session.close()


@pytest.mark.parametrize("component", ["raw_monthly", "saved_sqlite", "manifest"])
def test_archived_v2_rejects_tampered_raw_snapshot_or_manifest(
    tmp_path: Path,
    component: str,
) -> None:
    provider, reader, _, _, session, _, _, reference, raw = _archive_fixture(tmp_path)
    if component == "raw_monthly":
        target_file = _archive_file_path(reference, _one_raw_html(reference).relative_path)
    elif component == "saved_sqlite":
        target_file = _archive_file_path(reference, _one_stored_database(reference).relative_path)
    else:
        target_file = Path(reference.archive_root) / "raw_archive.json"
    _make_fixture_archive_file_writable(target_file)
    target_file.write_bytes(target_file.read_bytes() + b"tampered")
    target_operation = tmp_path / f"tampered-{component}-operation"
    try:
        with pytest.raises(FundamentalReadSnapshotError):
            _open_exact_archived(
                provider,
                reader,
                snapshot_root=target_operation,
                archive_reference=raw,
                expected_sha256=sha256(raw).hexdigest(),
            )
        assert not (target_operation / "finished_source_clock.json").exists()
    finally:
        session.close()


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_archived_v2_rejects_incomplete_or_unlisted_archive_members(
    tmp_path: Path,
    mutation: str,
) -> None:
    provider, reader, _, _, session, _, _, reference, raw = _archive_fixture(tmp_path)
    if mutation == "missing":
        member = _archive_file_path(reference, _one_raw_html(reference).relative_path)
        _make_fixture_archive_file_writable(member)
        member.unlink()
    else:
        (Path(reference.archive_root) / "unlisted-extra.fixture").write_bytes(b"extra")
    target = tmp_path / f"{mutation}-member-operation"
    try:
        with pytest.raises(FundamentalReadSnapshotError):
            _open_exact_archived(
                provider,
                reader,
                snapshot_root=target,
                archive_reference=raw,
                expected_sha256=sha256(raw).hexdigest(),
            )
        assert not (target / "finished_source_clock.json").exists()
    finally:
        session.close()


def test_archived_v2_rejects_hardlinked_archive_member(tmp_path: Path) -> None:
    provider, reader, _, _, session, _, _, reference, raw = _archive_fixture(tmp_path)
    member = _archive_file_path(reference, _one_raw_html(reference).relative_path)
    anchor = tmp_path / "hardlink-anchor.html"
    anchor.write_bytes(member.read_bytes())
    _make_fixture_archive_file_writable(member)
    member.unlink()
    try:
        os.link(anchor, member)
    except OSError as exc:
        session.close()
        pytest.skip(f"此平台/檔案系統不支援 fixture hardlink：{type(exc).__name__}")
    assert member.stat().st_nlink >= 2
    target = tmp_path / "hardlink-operation"
    try:
        with pytest.raises(FundamentalReadSnapshotError):
            _open_exact_archived(
                provider,
                reader,
                snapshot_root=target,
                archive_reference=raw,
                expected_sha256=sha256(raw).hexdigest(),
            )
        assert not (target / "finished_source_clock.json").exists()
    finally:
        session.close()


def test_archived_v2_rejects_reparse_archive_member_when_platform_allows_creation(
    tmp_path: Path,
) -> None:
    provider, reader, _, _, session, _, _, reference, raw = _archive_fixture(tmp_path)
    member = _archive_file_path(reference, _one_raw_html(reference).relative_path)
    anchor = tmp_path / "reparse-anchor.html"
    anchor.write_bytes(member.read_bytes())
    _make_fixture_archive_file_writable(member)
    member.unlink()
    try:
        member.symlink_to(anchor)
    except (OSError, NotImplementedError) as exc:
        session.close()
        pytest.skip(f"此平台不允許建立 fixture reparse link：{type(exc).__name__}")
    assert member.is_symlink()
    target = tmp_path / "reparse-operation"
    try:
        with pytest.raises(FundamentalReadSnapshotError):
            _open_exact_archived(
                provider,
                reader,
                snapshot_root=target,
                archive_reference=raw,
                expected_sha256=sha256(raw).hexdigest(),
            )
        assert not (target / "finished_source_clock.json").exists()
    finally:
        session.close()


def test_archived_v2_rejects_a_different_daily_cohort_pin(tmp_path: Path) -> None:
    provider, reader, _, _, session, _, _, reference, raw = _archive_fixture(tmp_path)
    _, prior_reader, prior_pin, _, _ = _daily_cohort_environment(
        tmp_path / "different-cohort",
        delay_availability_hour=True,
    )
    assert prior_pin != reference.source_clock.cohort_pin
    provider.daily_source_snapshot_reader = prior_reader
    target = tmp_path / "wrong-daily-pin-operation"
    try:
        with pytest.raises(FundamentalReadSnapshotError):
            _open_exact_archived(
                provider,
                prior_reader,
                snapshot_root=target,
                archive_reference=raw,
                expected_sha256=sha256(raw).hexdigest(),
            )
        assert not target.exists()
    finally:
        provider.daily_source_snapshot_reader = reader
        session.close()


@pytest.mark.parametrize("scope_error", ["future_cutoff", "declared_codes"])
def test_archived_v2_rejects_future_cutoff_or_wrong_declared_codes_before_finish(
    tmp_path: Path,
    scope_error: str,
) -> None:
    provider, reader, _, _, session, _, _, _, raw = _archive_fixture(tmp_path)
    target = tmp_path / f"{scope_error}-operation"
    if scope_error == "future_cutoff":
        codes = _CODES
        cutoff = CUTOFF - timedelta(hours=2)
    else:
        codes = ("2330", "6488")
        cutoff = CUTOFF
    try:
        with pytest.raises(FundamentalReadSnapshotError):
            _open_exact_archived(
                provider,
                reader,
                snapshot_root=target,
                archive_reference=raw,
                expected_sha256=sha256(raw).hexdigest(),
                stock_codes=codes,
                cutoff_at=cutoff,
            )
        assert not (target / "finished_source_clock.json").exists()
    finally:
        session.close()


def test_archived_v2_cancellation_never_publishes_a_finished_snapshot(
    tmp_path: Path,
) -> None:
    provider, reader, _, _, session, _, _, _, raw = _archive_fixture(tmp_path)
    target = tmp_path / "cancelled-archive-replay"
    try:
        with pytest.raises(FundamentalReadSnapshotCancelled):
            _open_exact_archived(
                provider,
                reader,
                snapshot_root=target,
                archive_reference=raw,
                expected_sha256=sha256(raw).hexdigest(),
                cancel_callback=lambda: True,
            )
        assert not (target / "finished_source_clock.json").exists()
    finally:
        session.close()


def test_archived_v2_finish_rejects_capture_tamper_after_full_batch(
    tmp_path: Path,
) -> None:
    provider, reader, _, _, original_session, _, _, reference, raw = _archive_fixture(
        tmp_path
    )
    replay = _open_exact_archived(
        provider,
        reader,
        snapshot_root=tmp_path / "finish-after-archive-tamper",
        archive_reference=raw,
        expected_sha256=sha256(raw).hexdigest(),
    )
    try:
        assert type(replay) is FundamentalReadSnapshotSessionV2
        batch = replay.load_batch(_CODES)
        assert type(batch) is FundamentalReadBatchCandidateV2
        assert batch.stock_codes == _CODES

        archived_html = _archive_file_path(
            reference,
            _one_raw_html(reference).relative_path,
        )
        _make_fixture_archive_file_writable(archived_html)
        archived_html.write_bytes(archived_html.read_bytes() + b"tampered after batch")

        with pytest.raises(FundamentalReadSessionError) as caught:
            replay.finish()
        assert caught.type is FundamentalReadSessionError
        assert replay.closed
        assert not (replay.snapshot_root / "finished_source_clock.json").exists()
    finally:
        replay.close()
        original_session.close()


def test_archived_v2_finish_rejects_incomplete_declared_stock_ledger(
    tmp_path: Path,
) -> None:
    provider, reader, _, _, original_session, _, _, _, raw = _archive_fixture(
        tmp_path
    )
    replay = _open_exact_archived(
        provider,
        reader,
        snapshot_root=tmp_path / "finish-with-partial-declared-cohort",
        archive_reference=raw,
        expected_sha256=sha256(raw).hexdigest(),
    )
    try:
        assert type(replay) is FundamentalReadSnapshotSessionV2
        batch = replay.load_batch(_CODES[:1])
        assert type(batch) is FundamentalReadBatchCandidateV2
        assert batch.stock_codes == _CODES[:1]

        with pytest.raises(FundamentalReadSessionIncomplete) as caught:
            replay.finish()
        assert caught.type is FundamentalReadSessionIncomplete
        assert replay.closed
        assert not (replay.snapshot_root / "finished_source_clock.json").exists()
    finally:
        replay.close()
        original_session.close()


@pytest.mark.parametrize("representation", ["typed", "canonical_json"])
def test_v1_raw_archive_reference_is_rejected_by_v2_archived_opener(
    tmp_path: Path,
    representation: str,
) -> None:
    provider, reader, _, _, v2_session, _, _, _, _ = _archive_fixture(tmp_path / "v2")
    legacy_provider = RecommendationCurrentFundamentalProvider(
        db_file=provider.db_file,
        output_root=provider.output_root,
        monthly_source_root=provider.monthly_source_root,
    )
    legacy = FundamentalReadSnapshotSession.open(
        legacy_provider,
        snapshot_root=tmp_path / "legacy-snapshot",
        stock_codes=("2330",),
        cutoff_at=CUTOFF,
    )
    legacy.load_batch(("2330",))
    legacy.finish()
    v1_archive = legacy.archive_monthly_raw_sources(tmp_path / "legacy-archives")
    assert type(v1_archive) is FundamentalReadSnapshotRawArchiveReferenceV1
    v1_raw = v1_archive.to_json().encode("utf-8")
    supplied_reference = v1_archive if representation == "typed" else v1_raw
    target = tmp_path / f"v1-{representation}-must-not-reopen"
    try:
        with pytest.raises((FundamentalReadSnapshotError, TypeError, ValueError)):
            _open_exact_archived(
                provider,
                reader,
                snapshot_root=target,
                archive_reference=supplied_reference,
                expected_sha256=sha256(v1_raw).hexdigest(),
            )
        assert not target.exists()
    finally:
        legacy.close()
        v2_session.close()

