from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app_module.daily_market_monthly_revenue_archive_reference_artifact_v4 import (
    DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_REFERENCE_ARTIFACT_V4_SCHEMA,
    DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error,
    DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4,
    UnverifiedDailyMarketMonthlyRevenueArchiveReferenceArtifactV4,
    decode_daily_market_monthly_revenue_archive_reference_artifact_descriptor_v4,
    publish_daily_market_monthly_revenue_archive_reference_artifact_v4,
    read_daily_market_monthly_revenue_archive_reference_artifact_v4,
)
from app_module.daily_market_monthly_revenue_reference_artifact_v3 import (
    publish_daily_market_monthly_revenue_reference_artifact_v3,
)
from tests.test_daily_market_monthly_revenue_yoy_index_v2 import (
    _CODES,
    _open_index,
)


def _roots(tmp_path: Path) -> tuple[Path, Path, Path, Path, tuple[Path, Path]]:
    original_root = tmp_path / "v3-reference-artifacts"
    v4_root = tmp_path / "v4-reference-artifacts"
    archive_parent = tmp_path / "raw-archives"
    protected_data = tmp_path / "configured-data"
    protected_output = tmp_path / "configured-output"
    for directory in (original_root, v4_root, archive_parent, protected_data, protected_output):
        directory.mkdir(parents=True)
    return original_root, v4_root, archive_parent, protected_data, (protected_data, protected_output)


def _published_context(tmp_path: Path):
    original_root, v4_root, archive_parent, _protected_data, protected = _roots(tmp_path)
    provider, reader, _pin, session = _open_index(tmp_path / "fixture")
    for start in range(0, len(_CODES), 16):
        session.load_batch(_CODES[start : start + 16])
    index = session.finish()
    source_reference = session.source_reference
    snapshot_session = session._source_session._snapshot_session
    archive_reference = snapshot_session.archive_monthly_raw_sources(archive_parent)
    original_descriptor = publish_daily_market_monthly_revenue_reference_artifact_v3(
        original_root,
        artifact_id="monthly-source",
        index_session=session,
        protected_roots=protected,
    )
    descriptor = publish_daily_market_monthly_revenue_archive_reference_artifact_v4(
        v4_root,
        artifact_id="monthly-portable",
        index_session=session,
        original_artifact_root=original_root,
        original_descriptor=original_descriptor,
        expected_original_descriptor_sha256=original_descriptor.external_descriptor_sha256,
        raw_archive_reference=archive_reference,
        expected_archive_reference_sha256=hashlib.sha256(
            archive_reference.to_json().encode("utf-8")
        ).hexdigest(),
        monthly_provider=provider,
        daily_monthly_cohort_reader=reader,
        protected_roots=protected,
    )
    return (
        provider,
        reader,
        session,
        source_reference,
        archive_reference,
        original_root,
        original_descriptor,
        v4_root,
        protected,
        descriptor,
    )


def test_v4_envelope_round_trip_is_self_contained_after_v3_files_are_removed(
    tmp_path: Path,
) -> None:
    (
        _provider,
        _reader,
        session,
        source_reference,
        archive_reference,
        original_root,
        original_descriptor,
        v4_root,
        protected,
        descriptor,
    ) = _published_context(tmp_path)
    try:
        envelope_path = v4_root / descriptor.envelope_relative_path
        descriptor_path = v4_root / descriptor.descriptor_relative_path
        envelope_raw = envelope_path.read_bytes()
        descriptor_raw = descriptor_path.read_bytes()
        assert descriptor.to_dict()["original_descriptor_sha256"] == original_descriptor.external_descriptor_sha256
        assert descriptor.to_dict()["reference_sha256"] == original_descriptor.reference_sha256
        assert descriptor.to_dict()["archive_reference_sha256"] == hashlib.sha256(
            archive_reference.to_json().encode("utf-8")
        ).hexdigest()
        assert descriptor.to_dict()["source_reference_identity_sha256"] == source_reference.identity_sha256
        assert descriptor.cohort_pin == source_reference.cohort_pin
        assert descriptor.source_scope == "current_observed_only"
        assert descriptor.availability_status == "cohort_hour_bound"
        assert descriptor.complete is True
        assert descriptor.historical_pit_eligible is False
        assert descriptor.formal_pit_eligible is False

        decoded_descriptor = decode_daily_market_monthly_revenue_archive_reference_artifact_descriptor_v4(
            descriptor_raw,
            descriptor.external_descriptor_sha256,
        )
        assert type(decoded_descriptor) is DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4
        assert decoded_descriptor.is_writer_issued is False
        assert decoded_descriptor.to_bytes() == descriptor_raw

        (original_root / original_descriptor.reference_relative_path).unlink()
        (original_root / original_descriptor.descriptor_relative_path).unlink()
        result = read_daily_market_monthly_revenue_archive_reference_artifact_v4(
            v4_root,
            descriptor=decoded_descriptor,
            expected_descriptor_sha256=descriptor.external_descriptor_sha256,
            protected_roots=protected,
        )
        assert type(result) is UnverifiedDailyMarketMonthlyRevenueArchiveReferenceArtifactV4
        assert result.source_reference.reference == source_reference
        assert result.raw_archive_reference.reference == archive_reference
        assert result.original_descriptor.external_descriptor_sha256 == original_descriptor.external_descriptor_sha256
        assert result.external_descriptor_sha256 == descriptor.external_descriptor_sha256
        assert hashlib.sha256(envelope_raw).hexdigest() == descriptor.envelope_sha256
    finally:
        session.close()


def test_v4_publisher_is_create_only_and_preserves_existing_pair_on_collision(
    tmp_path: Path,
) -> None:
    (
        provider,
        reader,
        session,
        _source_reference,
        archive_reference,
        original_root,
        original_descriptor,
        v4_root,
        protected,
        descriptor,
    ) = _published_context(tmp_path)
    try:
        before = {
            descriptor.envelope_relative_path: (v4_root / descriptor.envelope_relative_path).read_bytes(),
            descriptor.descriptor_relative_path: (v4_root / descriptor.descriptor_relative_path).read_bytes(),
        }
        with pytest.raises(DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error, match="collision"):
            publish_daily_market_monthly_revenue_archive_reference_artifact_v4(
                v4_root,
                artifact_id=descriptor.artifact_id,
                index_session=session,
                original_artifact_root=original_root,
                original_descriptor=original_descriptor,
                expected_original_descriptor_sha256=original_descriptor.external_descriptor_sha256,
                raw_archive_reference=archive_reference,
                expected_archive_reference_sha256=hashlib.sha256(
                    archive_reference.to_json().encode("utf-8")
                ).hexdigest(),
                monthly_provider=provider,
                daily_monthly_cohort_reader=reader,
                protected_roots=protected,
            )
        assert before == {
            name: (v4_root / name).read_bytes() for name in before
        }
    finally:
        session.close()


def test_bad_original_descriptor_sha_is_rejected_without_creating_v4_files(
    tmp_path: Path,
) -> None:
    (
        provider,
        reader,
        session,
        _source_reference,
        archive_reference,
        original_root,
        original_descriptor,
        v4_root,
        protected,
        _descriptor,
    ) = _published_context(tmp_path)
    try:
        with pytest.raises(DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error, match="original_v3_descriptor_external_sha"):
            publish_daily_market_monthly_revenue_archive_reference_artifact_v4(
                v4_root,
                artifact_id="bad-original-anchor",
                index_session=session,
                original_artifact_root=original_root,
                original_descriptor=original_descriptor,
                expected_original_descriptor_sha256="0" * 64,
                raw_archive_reference=archive_reference,
                expected_archive_reference_sha256=hashlib.sha256(
                    archive_reference.to_json().encode("utf-8")
                ).hexdigest(),
                monthly_provider=provider,
                daily_monthly_cohort_reader=reader,
                protected_roots=protected,
            )
        assert not (v4_root / "bad-original-anchor.archive-reference.v4.json").exists()
        assert not (v4_root / "bad-original-anchor.descriptor.v4.json").exists()
    finally:
        session.close()


def test_bad_archive_external_sha_is_rejected_without_v4_publication(tmp_path: Path) -> None:
    (
        provider,
        reader,
        session,
        _source_reference,
        archive_reference,
        original_root,
        original_descriptor,
        v4_root,
        protected,
        _descriptor,
    ) = _published_context(tmp_path)
    try:
        with pytest.raises(DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error, match="raw_archive_reference_external_sha"):
            publish_daily_market_monthly_revenue_archive_reference_artifact_v4(
                v4_root,
                artifact_id="bad-archive-anchor",
                index_session=session,
                original_artifact_root=original_root,
                original_descriptor=original_descriptor,
                expected_original_descriptor_sha256=original_descriptor.external_descriptor_sha256,
                raw_archive_reference=archive_reference,
                expected_archive_reference_sha256="0" * 64,
                monthly_provider=provider,
                daily_monthly_cohort_reader=reader,
                protected_roots=protected,
            )
        assert not (v4_root / "bad-archive-anchor.archive-reference.v4.json").exists()
        assert not (v4_root / "bad-archive-anchor.descriptor.v4.json").exists()
    finally:
        session.close()


def test_bad_v4_external_sha_is_rejected_before_pair_read(tmp_path: Path) -> None:
    (
        _provider,
        _reader,
        session,
        _source_reference,
        _archive_reference,
        _original_root,
        _original_descriptor,
        v4_root,
        protected,
        descriptor,
    ) = _published_context(tmp_path)
    try:
        with pytest.raises(DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error, match="external_descriptor_sha"):
            read_daily_market_monthly_revenue_archive_reference_artifact_v4(
                v4_root,
                descriptor=descriptor.to_bytes(),
                expected_descriptor_sha256="0" * 64,
                protected_roots=protected,
            )
    finally:
        session.close()


def test_rehashed_outer_descriptor_cannot_rebind_embedded_source_identity(
    tmp_path: Path,
) -> None:
    (
        _provider,
        _reader,
        session,
        _source_reference,
        _archive_reference,
        _original_root,
        _original_descriptor,
        v4_root,
        protected,
        descriptor,
    ) = _published_context(tmp_path)
    try:
        descriptor_path = v4_root / descriptor.descriptor_relative_path
        payload = json.loads(descriptor_path.read_bytes().decode("utf-8"))
        payload["source_content_identity_sha256"] = "0" * 64
        forged_raw = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        descriptor_path.write_bytes(forged_raw)
        with pytest.raises(DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error, match="binding_mismatch"):
            read_daily_market_monthly_revenue_archive_reference_artifact_v4(
                v4_root,
                descriptor=forged_raw,
                expected_descriptor_sha256=hashlib.sha256(forged_raw).hexdigest(),
                protected_roots=protected,
            )
    finally:
        session.close()


def test_envelope_tampering_fails_even_when_descriptor_anchor_is_valid(
    tmp_path: Path,
) -> None:
    (
        _provider,
        _reader,
        session,
        _source_reference,
        _archive_reference,
        _original_root,
        _original_descriptor,
        v4_root,
        protected,
        descriptor,
    ) = _published_context(tmp_path)
    try:
        envelope_path = v4_root / descriptor.envelope_relative_path
        descriptor_path = v4_root / descriptor.descriptor_relative_path
        noncanonical_envelope = envelope_path.read_bytes() + b" "
        envelope_path.write_bytes(noncanonical_envelope)
        outer = json.loads(descriptor_path.read_bytes().decode("utf-8"))
        outer["envelope_size_bytes"] = len(noncanonical_envelope)
        outer["envelope_sha256"] = hashlib.sha256(noncanonical_envelope).hexdigest()
        descriptor_raw = json.dumps(
            outer,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        descriptor_path.write_bytes(descriptor_raw)
        with pytest.raises(DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error, match="envelope_not_canonical"):
            read_daily_market_monthly_revenue_archive_reference_artifact_v4(
                v4_root,
                descriptor=descriptor_raw,
                expected_descriptor_sha256=hashlib.sha256(descriptor_raw).hexdigest(),
                protected_roots=protected,
            )
    finally:
        session.close()


def test_immediate_cancel_does_not_publish_and_wrapper_cannot_claim_verified_source(
    tmp_path: Path,
) -> None:
    (
        provider,
        reader,
        session,
        _source_reference,
        archive_reference,
        original_root,
        original_descriptor,
        v4_root,
        protected,
        _descriptor,
    ) = _published_context(tmp_path)
    try:
        with pytest.raises(DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error, match="cancelled"):
            publish_daily_market_monthly_revenue_archive_reference_artifact_v4(
                v4_root,
                artifact_id="cancelled",
                index_session=session,
                original_artifact_root=original_root,
                original_descriptor=original_descriptor,
                expected_original_descriptor_sha256=original_descriptor.external_descriptor_sha256,
                raw_archive_reference=archive_reference,
                expected_archive_reference_sha256=hashlib.sha256(
                    archive_reference.to_json().encode("utf-8")
                ).hexdigest(),
                monthly_provider=provider,
                daily_monthly_cohort_reader=reader,
                protected_roots=protected,
                cancel_callback=lambda: True,
            )
        assert not (v4_root / "cancelled.archive-reference.v4.json").exists()
        assert not (v4_root / "cancelled.descriptor.v4.json").exists()
        assert DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_REFERENCE_ARTIFACT_V4_SCHEMA == _descriptor.artifact_schema_version
        assert _descriptor.is_writer_issued is True
    finally:
        session.close()
