from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from app_module.daily_market_monthly_revenue_reference_artifact_v3 import (
    DailyMarketMonthlyRevenueReferenceArtifactV3Error,
    UnverifiedDailyMarketMonthlyRevenueReferenceArtifactV3,
    publish_daily_market_monthly_revenue_reference_artifact_v3,
    read_daily_market_monthly_revenue_reference_artifact_v3,
)
from tests.test_daily_market_monthly_revenue_yoy_index_v2 import _CODES, _open_index


def _artifact_roots(tmp_path: Path) -> tuple[Path, tuple[Path, Path]]:
    root = tmp_path / "reference-artifacts"
    root.mkdir(parents=True)
    data_root = tmp_path / "configured-data"
    output_root = tmp_path / "configured-output"
    data_root.mkdir(parents=True)
    output_root.mkdir(parents=True)
    return root, (data_root, output_root)


def _finished_session(tmp_path: Path):
    provider, reader, pin, session = _open_index(tmp_path / "source")
    session.load_batch(_CODES)
    index = session.finish()
    return provider, reader, pin, session, index


def _publish(
    tmp_path: Path,
    *,
    artifact_id: str = "daily-monthly-01",
):
    root, protected = _artifact_roots(tmp_path)
    _provider, _reader, pin, session, index = _finished_session(tmp_path / "fixture")
    descriptor = publish_daily_market_monthly_revenue_reference_artifact_v3(
        root,
        artifact_id=artifact_id,
        index_session=session,
        protected_roots=protected,
    )
    return root, protected, pin, session, index, descriptor


def test_writer_persists_canonical_reference_and_reader_requires_external_descriptor_sha(
    tmp_path: Path,
) -> None:
    root, protected, pin, session, index, descriptor = _publish(tmp_path)
    try:
        reference_path = root / descriptor.reference_relative_path
        descriptor_path = root / descriptor.descriptor_relative_path
        reference_raw = reference_path.read_bytes()
        descriptor_raw = descriptor_path.read_bytes()
        assert reference_raw == session.source_reference.to_json().encode("utf-8")
        assert hashlib.sha256(reference_raw).hexdigest() == descriptor.reference_sha256
        assert descriptor_raw == descriptor.to_bytes()
        assert hashlib.sha256(descriptor_raw).hexdigest() == descriptor.external_descriptor_sha256
        assert descriptor.index_identity_sha256 == index.index_identity_sha256
        assert descriptor.cohort_sha256 == pin.cohort_sha256

        artifact = read_daily_market_monthly_revenue_reference_artifact_v3(
            root,
            descriptor=descriptor_raw,
            expected_descriptor_sha256=descriptor.external_descriptor_sha256,
            protected_roots=protected,
        )
        assert type(artifact) is UnverifiedDailyMarketMonthlyRevenueReferenceArtifactV3
        assert artifact.external_descriptor_sha256 == descriptor.external_descriptor_sha256
        assert artifact.source_reference.reference == session.source_reference
        assert artifact.source_reference.external_reference_sha256 == descriptor.reference_sha256
        assert artifact.source_reference.reference.formal_pit_eligible is False
        assert artifact.source_reference.reference.historical_pit_eligible is False
        assert artifact.descriptor.is_writer_issued is False
        reference_path.unlink()
        descriptor_path.unlink()
    finally:
        session.close()


def test_writer_refuses_unfinished_session_without_creating_files(tmp_path: Path) -> None:
    root, protected = _artifact_roots(tmp_path)
    _provider, _reader, _pin, session = _open_index(tmp_path / "source")
    try:
        with pytest.raises(DailyMarketMonthlyRevenueReferenceArtifactV3Error, match="not_finished"):
            publish_daily_market_monthly_revenue_reference_artifact_v3(
                root,
                artifact_id="unfinished",
                index_session=session,
                protected_roots=protected,
            )
        assert tuple(root.iterdir()) == ()
    finally:
        session.close()


def test_writer_refuses_incomplete_cohort_without_publishing_artifacts(tmp_path: Path) -> None:
    root, protected = _artifact_roots(tmp_path)
    _provider, _reader, _pin, session = _open_index(tmp_path / "source")
    session.load_batch((_CODES[0],))
    try:
        with pytest.raises(DailyMarketMonthlyRevenueReferenceArtifactV3Error, match="not_finished"):
            publish_daily_market_monthly_revenue_reference_artifact_v3(
                root,
                artifact_id="partial",
                index_session=session,
                protected_roots=protected,
            )
        assert tuple(root.iterdir()) == ()
        assert session.finished is False
    finally:
        session.close()


def test_create_only_collision_preserves_both_original_files(tmp_path: Path) -> None:
    root, protected, _pin, session, _index, descriptor = _publish(tmp_path)
    try:
        before = {
            descriptor.reference_relative_path: (root / descriptor.reference_relative_path).read_bytes(),
            descriptor.descriptor_relative_path: (root / descriptor.descriptor_relative_path).read_bytes(),
        }
        with pytest.raises(DailyMarketMonthlyRevenueReferenceArtifactV3Error, match="collision"):
            publish_daily_market_monthly_revenue_reference_artifact_v3(
                root,
                artifact_id=descriptor.artifact_id,
                index_session=session,
                protected_roots=protected,
            )
        assert {
            name: (root / name).read_bytes() for name in before
        } == before
    finally:
        session.close()


def test_reader_rejects_wrong_external_descriptor_hash_before_opening_artifacts(
    tmp_path: Path,
) -> None:
    root, protected, _pin, session, _index, descriptor = _publish(tmp_path)
    try:
        with pytest.raises(DailyMarketMonthlyRevenueReferenceArtifactV3Error, match="external_descriptor_sha"):
            read_daily_market_monthly_revenue_reference_artifact_v3(
                root,
                descriptor=descriptor.to_bytes(),
                expected_descriptor_sha256="0" * 64,
                protected_roots=protected,
            )
    finally:
        session.close()


def test_rehashed_self_filled_descriptor_cannot_bind_a_different_source_reference(
    tmp_path: Path,
) -> None:
    root, protected, _pin, session, _index, descriptor = _publish(tmp_path)
    try:
        payload = json.loads(descriptor.to_bytes())
        payload["source_reference_identity_sha256"] = "0" * 64
        changed = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        (root / descriptor.descriptor_relative_path).write_bytes(changed)
        with pytest.raises(DailyMarketMonthlyRevenueReferenceArtifactV3Error, match="descriptor_and_source_reference"):
            read_daily_market_monthly_revenue_reference_artifact_v3(
                root,
                descriptor=changed,
                expected_descriptor_sha256=hashlib.sha256(changed).hexdigest(),
                protected_roots=protected,
            )
        assert (root / descriptor.descriptor_relative_path).read_bytes() == changed
    finally:
        session.close()


def test_reader_rejects_reference_mutation_even_when_descriptor_file_is_untouched(
    tmp_path: Path,
) -> None:
    root, protected, _pin, session, _index, descriptor = _publish(tmp_path)
    try:
        reference_path = root / descriptor.reference_relative_path
        raw = reference_path.read_bytes()
        reference_path.write_bytes(raw[:-1] + (b" " if raw[-1:] != b" " else b"\n"))
        with pytest.raises(DailyMarketMonthlyRevenueReferenceArtifactV3Error, match="size_or_sha"):
            read_daily_market_monthly_revenue_reference_artifact_v3(
                root,
                descriptor=descriptor.to_bytes(),
                expected_descriptor_sha256=descriptor.external_descriptor_sha256,
                protected_roots=protected,
            )
    finally:
        session.close()


def test_reader_rejects_hardlinked_reference_bytes(tmp_path: Path) -> None:
    root, protected, _pin, session, _index, descriptor = _publish(tmp_path)
    try:
        reference_path = root / descriptor.reference_relative_path
        alias_path = root / "unexpected-hardlink.json"
        try:
            os.link(reference_path, alias_path)
        except OSError as exc:
            pytest.skip(f"此檔案系統無法建立 hardlink fixture: {exc}")
        with pytest.raises(DailyMarketMonthlyRevenueReferenceArtifactV3Error, match="hardlink"):
            read_daily_market_monthly_revenue_reference_artifact_v3(
                root,
                descriptor=descriptor.to_bytes(),
                expected_descriptor_sha256=descriptor.external_descriptor_sha256,
                protected_roots=protected,
            )
    finally:
        session.close()


def test_writer_rejects_reparse_artifact_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "root-alias"
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"此Windows環境未授予symlink fixture權限: {exc}")
    with pytest.raises(DailyMarketMonthlyRevenueReferenceArtifactV3Error, match="reparse"):
        publish_daily_market_monthly_revenue_reference_artifact_v3(
            alias,
            artifact_id="reparse",
            index_session=object(),
            protected_roots=(tmp_path / "data", tmp_path / "output"),
        )


def test_reader_rejects_duplicate_unknown_and_deep_descriptor_payloads(tmp_path: Path) -> None:
    root, protected = _artifact_roots(tmp_path)
    cases = (
        b'{"schema_version":"x","schema_version":"x"}',
        b'{"unknown":{"nested":true}}',
        b'{"nested":' + (b"[" * 26) + b"0" + (b"]" * 26) + b"}",
    )
    for raw in cases:
        with pytest.raises(DailyMarketMonthlyRevenueReferenceArtifactV3Error):
            read_daily_market_monthly_revenue_reference_artifact_v3(
                root,
                descriptor=raw,
                expected_descriptor_sha256=hashlib.sha256(raw).hexdigest(),
                protected_roots=protected,
            )


def test_writer_rejects_root_overlapping_configured_data_root_before_source_access(
    tmp_path: Path,
) -> None:
    _provider, _reader, _pin, session = _open_index(tmp_path / "source")
    protected = (tmp_path, tmp_path / "output")
    try:
        with pytest.raises(DailyMarketMonthlyRevenueReferenceArtifactV3Error, match="overlaps"):
            publish_daily_market_monthly_revenue_reference_artifact_v3(
                tmp_path,
                artifact_id="overlap",
                index_session=session,
                protected_roots=protected,
            )
    finally:
        session.close()


def test_cancel_and_json_float_do_not_publish_or_decode_as_receipts(tmp_path: Path) -> None:
    root, protected, _pin, session, _index, descriptor = _publish(tmp_path / "published")
    try:
        with pytest.raises(DailyMarketMonthlyRevenueReferenceArtifactV3Error, match="cancelled"):
            publish_daily_market_monthly_revenue_reference_artifact_v3(
                root,
                artifact_id="cancelled",
                index_session=session,
                protected_roots=protected,
                cancel_callback=lambda: True,
            )
        assert not (root / "cancelled.source-reference.v3.json").exists()
        float_receipt = b'{"schema_version":1.5}'
        with pytest.raises(DailyMarketMonthlyRevenueReferenceArtifactV3Error, match="float"):
            read_daily_market_monthly_revenue_reference_artifact_v3(
                root,
                descriptor=float_receipt,
                expected_descriptor_sha256=hashlib.sha256(float_receipt).hexdigest(),
                protected_roots=protected,
            )
    finally:
        session.close()
