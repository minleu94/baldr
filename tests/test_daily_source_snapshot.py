from __future__ import annotations

import base64
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import pytest

from data_module.daily_source_snapshot import (
    DAILY_SOURCE_SNAPSHOT_MANIFEST_SCHEMA_V1,
    DAILY_SOURCE_TIME_BASIS_POLICY,
    MAX_DAILY_SOURCE_RECEIPT_BYTES,
    DailySourceBatchValidation,
    DailySourceSnapshot,
    DailySourceSnapshotError,
    DailySourceSnapshotFileReader,
    DailySourceSnapshotRecord,
    DailySourceTransportCapture,
    DailySourceUseAcceptance,
    DailySourceUseScope,
    DailySourceValidationCheck,
    read_daily_source_snapshot as _read_daily_source_snapshot,
    write_daily_source_quarantine_candidate,
    write_daily_source_snapshot,
)


UTC = timezone.utc
TAIPEI = ZoneInfo("Asia/Taipei")


def _scope(*, unit: str = "TWD", market: str = "twse") -> DailySourceUseScope:
    return DailySourceUseScope(
        dataset_id="fundamental_current_observations.monthly_revenue",
        source_id="mops.monthly_revenue_static_snapshot",
        market=market,
        parser_version="mops-current-revenue-normalizer.v2",
        source_schema_version="mops-static-snapshot.v2",
        unit=unit,
        intended_use="recommendation_current_fundamental",
    )


def _acceptance(scope: DailySourceUseScope | None = None) -> DailySourceUseAcceptance:
    selected_scope = scope or _scope()
    return DailySourceUseAcceptance(
        scope=selected_scope,
        acceptance_id="acceptance-mops-monthly-revenue-v1",
        accepted_at=datetime(2026, 10, 2, 8, 0, tzinfo=TAIPEI),
        official_source_endpoint="https://mops.twse.com.tw/mops/web/t05st10_ifrs",
        document_chain=("mops-monthly-revenue", "source-use-policy-v1"),
        acceptance_evidence_ref="docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md#source-policy",
        authorization_scope="recommendation_current_fundamental only",
        time_basis_policy=DAILY_SOURCE_TIME_BASIS_POLICY,
    )


def read_daily_source_snapshot(
    root: Path | str,
    batch_id: str,
    *,
    expected_scope: DailySourceUseScope,
) -> DailySourceSnapshot:
    """測試明示使用 fixture 接受錨點，避免快照自行授權。"""

    return _read_daily_source_snapshot(
        root,
        batch_id,
        expected_scope=expected_scope,
        trusted_acceptance=_acceptance(expected_scope),
    )


def _validation(
    *,
    expected_count: int = 1,
    actual_count: int = 1,
    status_overrides: dict[str, tuple[str, str]] | None = None,
    official_timestamp_present: bool = True,
) -> DailySourceBatchValidation:
    overrides = status_overrides or {}

    def check(check_id: str, *, default: str = "pass") -> DailySourceValidationCheck:
        status, reason = overrides.get(check_id, (default, f"{check_id}_{default}"))
        if check_id == "prior_period_required" and status == "not_required":
            reason = "prior_period_not_required"
        return DailySourceValidationCheck(check_id, status, reason)

    return DailySourceBatchValidation(
        validation_id="validation-2026-10-02-twse-001",
        expected_partition_ids=("twse-monthly-revenue",),
        successful_partition_ids=("twse-monthly-revenue",),
        failed_partition_ids=(),
        expected_record_count=expected_count,
        actual_record_count=actual_count,
        source_status_check=check("source_status"),
        raw_source_hash_check=check("raw_source_hash"),
        schema_check=check("schema"),
        unit_check=check("unit"),
        finite_values_check=check("finite_values"),
        missing_values_check=check("missing_values"),
        prior_period_required_check=check("prior_period_required", default="not_required"),
        official_timestamp_parse_check=(
            DailySourceValidationCheck(
                "official_timestamp_parse",
                "pass",
                "official_timestamp_parsed_by:mops-current-revenue-normalizer.v2",
            )
            if official_timestamp_present
            else DailySourceValidationCheck(
                "official_timestamp_parse",
                "not_required",
                "official_timestamp_not_provided",
            )
        ),
    )


def _record(
    raw_bytes: bytes,
    *,
    official_timestamp: datetime | None = datetime(2026, 10, 2, 2, 5, tzinfo=UTC),
    official_original: str = "2026-10-02T02:05:00+00:00",
    official_timezone: str = "+00:00",
    source_version: str | None = None,
    unit: str = "TWD",
) -> DailySourceSnapshotRecord:
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    return DailySourceSnapshotRecord(
        stock_code="2330",
        market="twse",
        period="2026-04",
        source_version=(
            source_version
            or (
                "mops-static-snapshot.v2:twse:2026-04:body_completed_at:"
                "2026-10-02T10:05:00+08:00:sha256:"
                f"{raw_hash}"
                if official_timestamp is not None
                else f"mops-static-twse-2026-04-sha256-{raw_hash}"
            )
        ),
        raw_source_sha256=raw_hash,
        unit=unit,
        official_timestamp=official_timestamp,
        official_timestamp_original_text=(official_original if official_timestamp else ""),
        official_timestamp_original_timezone=(official_timezone if official_timestamp else ""),
    )


def _big5_transport_fixture(
    *,
    body_completed_at: datetime = datetime(2026, 10, 2, 10, 5, tzinfo=TAIPEI),
) -> tuple[bytes, DailySourceSnapshotRecord, DailySourceTransportCapture]:
    decoded_html = '<meta charset="big5"><html><body>月營收</body></html>'
    response_bytes = decoded_html.encode("big5")
    canonical_bytes = decoded_html.encode("utf-8")
    canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
    source_version = (
        "mops-static-snapshot.v2:twse:2026-04:body_completed_at:"
        f"{body_completed_at.isoformat()}:sha256:{canonical_sha256}"
    )
    record = _record(
        canonical_bytes,
        official_timestamp=body_completed_at,
        official_original=body_completed_at.isoformat(),
        official_timezone="+08:00",
        source_version=source_version,
    )
    capture = DailySourceTransportCapture(
        raw_response_bytes=response_bytes,
        official_source_url="https://mops.twse.com.tw/mops/web/t05st10_ifrs",
        response_status=200,
        content_type="text/html",
        declared_decoding_encoding="big5",
        decoding_basis="html_meta_charset",
        body_completed_at=body_completed_at,
        transport_sha256=hashlib.sha256(response_bytes).hexdigest(),
        response_body_complete=True,
        received_body_bytes=len(response_bytes),
        content_length_original_text=None,
        body_completion_evidence_ref="eof:synthetic-test-response-read-to-end",
    )
    return canonical_bytes, record, capture


def _fixture_json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _rewrite_manifest_and_rebind_receipt(
    batch_root: Path,
    mutate_manifest: Callable[[dict[str, object]], None],
) -> None:
    manifest_path = batch_root / "manifest.json"
    receipt_path = batch_root / "receipt.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate_manifest(manifest)
    manifest_bytes = _fixture_json_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    receipt.pop("receipt_sha256")
    receipt["receipt_sha256"] = hashlib.sha256(_fixture_json_bytes(receipt)).hexdigest()
    receipt_path.write_bytes(_fixture_json_bytes(receipt))


def _write(
    root: Path,
    *,
    batch_id: str = "2026-10-02-twse-001",
    raw_bytes: bytes = b"<html>immutable MOPS response</html>",
    record: DailySourceSnapshotRecord | None = None,
    transport_capture: DailySourceTransportCapture | None = None,
    validation: DailySourceBatchValidation | None = None,
    quarantine_root: Path | None = None,
    check_cancel: Callable[[], None] | None = None,
    times: tuple[datetime, datetime, datetime, datetime] = (
        datetime(2026, 10, 2, 10, 10, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 10, 20, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 10, 25, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 10, 30, tzinfo=TAIPEI),
    ),
) -> Path:
    cursor = iter(times)
    selected_record = record or _record(raw_bytes)
    return write_daily_source_snapshot(
        root,
        batch_id=batch_id,
        scope=_scope(),
        use_acceptance=_acceptance(),
        source_batch_started_at=datetime(2026, 10, 2, 9, 55, tzinfo=TAIPEI),
        raw_source_bytes=raw_bytes,
        records=(selected_record,),
        validation=validation
        or _validation(official_timestamp_present=selected_record.official_timestamp is not None),
        transport_capture=transport_capture,
        clock=lambda: next(cursor),
        quarantine_root=quarantine_root,
        check_cancel=check_cancel,
    )


def test_writer_and_new_reader_round_trip_raw_bytes_and_original_official_clock(
    tmp_path: Path,
) -> None:
    raw_bytes = b"<html>raw body bytes remain available</html>"
    _write(tmp_path, raw_bytes=raw_bytes)

    reader = DailySourceSnapshotFileReader(
        tmp_path,
        trusted_acceptance=_acceptance(),
    )
    snapshot = reader.read_snapshot(
        "2026-10-02-twse-001",
        expected_scope=_scope(),
    )

    assert snapshot.raw_source_bytes == raw_bytes
    assert snapshot.raw_source_sha256 == hashlib.sha256(raw_bytes).hexdigest()
    assert snapshot.records[0].official_timestamp_original_text == "2026-10-02T02:05:00+00:00"
    assert snapshot.records[0].official_timestamp == datetime(
        2026, 10, 2, 10, 5, tzinfo=TAIPEI
    )


def test_big5_http_original_round_trips_separate_transport_and_canonical_hashes(
    tmp_path: Path,
) -> None:
    canonical_bytes, record, capture = _big5_transport_fixture()
    _write(
        tmp_path,
        raw_bytes=canonical_bytes,
        record=record,
        transport_capture=capture,
    )

    snapshot = DailySourceSnapshotFileReader(
        tmp_path,
        trusted_acceptance=_acceptance(),
    ).read_snapshot("2026-10-02-twse-001", expected_scope=_scope())
    stored_capture = snapshot.transport_capture
    assert stored_capture is not None
    assert stored_capture.raw_response_bytes == capture.raw_response_bytes
    assert stored_capture.transport_sha256 == hashlib.sha256(
        capture.raw_response_bytes
    ).hexdigest()
    assert stored_capture.canonical_source_bytes == canonical_bytes
    assert stored_capture.decoded_html == '<meta charset="big5"><html><body>月營收</body></html>'
    assert stored_capture.html_meta_charset_original_text == "big5"
    assert stored_capture.content_type == "text/html"
    assert stored_capture.response_body_complete is True
    assert stored_capture.received_body_bytes == len(capture.raw_response_bytes)
    assert stored_capture.content_length_original_text is None
    assert stored_capture.body_completion_evidence_ref == (
        "eof:synthetic-test-response-read-to-end"
    )
    assert snapshot.raw_source_bytes == canonical_bytes
    assert snapshot.raw_source_sha256 == hashlib.sha256(canonical_bytes).hexdigest()
    assert snapshot.raw_source_sha256 != stored_capture.transport_sha256
    assert snapshot.payload_provenance == "verified_http_response_body"
    assert snapshot.find_record(
        stock_code=record.stock_code,
        market=record.market,
        period=record.period,
        source_version=record.source_version,
        raw_source_sha256=hashlib.sha256(canonical_bytes).hexdigest(),
        unit=record.unit,
    ) == record
    assert snapshot.find_record(
        stock_code=record.stock_code,
        market=record.market,
        period=record.period,
        source_version=record.source_version,
        raw_source_sha256=stored_capture.transport_sha256,
        unit=record.unit,
    ) is None

    header_capture = replace(
        capture,
        content_type="text/html; charset=Big5",
        decoding_basis="http_content_type_charset",
    )
    assert header_capture.decoded_html == stored_capture.decoded_html


def test_v1_manifest_remains_readable_and_identifies_canonical_only_payload(
    tmp_path: Path,
) -> None:
    _write(tmp_path)
    batch_root = tmp_path / "2026-10-02-twse-001"

    def downgrade_manifest(manifest: dict[str, object]) -> None:
        manifest["schema_version"] = DAILY_SOURCE_SNAPSHOT_MANIFEST_SCHEMA_V1
        manifest.pop("transport_capture")

    _rewrite_manifest_and_rebind_receipt(
        batch_root,
        downgrade_manifest,
    )

    snapshot = DailySourceSnapshotFileReader(
        tmp_path,
        trusted_acceptance=_acceptance(),
    ).read_snapshot("2026-10-02-twse-001", expected_scope=_scope())
    assert snapshot.transport_capture is None
    assert snapshot.payload_provenance == "canonical_utf8_payload_only"


def test_content_length_original_text_round_trips_without_normalization(
    tmp_path: Path,
) -> None:
    canonical_bytes, record, capture = _big5_transport_fixture()
    content_length_text = f"00{len(capture.raw_response_bytes)}"
    captured_with_length = replace(
        capture,
        content_length_original_text=content_length_text,
        body_completion_evidence_ref="content-length-and-eof:synthetic-test-response",
    )
    _write(
        tmp_path,
        raw_bytes=canonical_bytes,
        record=record,
        transport_capture=captured_with_length,
    )

    snapshot = DailySourceSnapshotFileReader(
        tmp_path,
        trusted_acceptance=_acceptance(),
    ).read_snapshot("2026-10-02-twse-001", expected_scope=_scope())
    assert snapshot.transport_capture is not None
    assert snapshot.transport_capture.content_length_original_text == content_length_text


def test_v2_manifest_rejects_unrecognized_transport_capture_fields(
    tmp_path: Path,
) -> None:
    canonical_bytes, record, capture = _big5_transport_fixture()
    _write(
        tmp_path,
        raw_bytes=canonical_bytes,
        record=record,
        transport_capture=capture,
    )

    def add_unknown_field(manifest: dict[str, object]) -> None:
        manifest["unknown_capture_field"] = "unexpected"

    _rewrite_manifest_and_rebind_receipt(
        tmp_path / "2026-10-02-twse-001",
        add_unknown_field,
    )

    with pytest.raises(DailySourceSnapshotError, match="manifest 欄位與版本契約不符"):
        read_daily_source_snapshot(
            tmp_path,
            "2026-10-02-twse-001",
            expected_scope=_scope(),
        )


def test_transport_capture_rejects_wrong_encoding_status_and_unaccepted_url(
    tmp_path: Path,
) -> None:
    canonical_bytes, record, capture = _big5_transport_fixture()

    with pytest.raises(DailySourceSnapshotError, match="declared decoding encoding"):
        replace(
            capture,
            declared_decoding_encoding="utf-8",
        )
    with pytest.raises(DailySourceSnapshotError, match="status 必須是 200"):
        replace(capture, response_status=206)
    with pytest.raises(DailySourceSnapshotError, match="必須是無憑證與 fragment 的 HTTPS URL"):
        replace(capture, official_source_url="http://mops.twse.com.tw/mops/web/t05st10_ifrs")

    unaccepted_url_capture = replace(
        capture,
        official_source_url="https://mops.twse.com.tw/mops/web/unaccepted-endpoint",
    )
    with pytest.raises(DailySourceSnapshotError, match="未精確列於可信用途接受"):
        _write(
            tmp_path,
            raw_bytes=canonical_bytes,
            record=record,
            transport_capture=unaccepted_url_capture,
        )


def test_transport_capture_requires_explicit_complete_body_and_length_evidence() -> None:
    _, _, capture = _big5_transport_fixture()

    with pytest.raises(DailySourceSnapshotError, match="必須明示完整"):
        replace(capture, response_body_complete=False)
    with pytest.raises(DailySourceSnapshotError, match="必須明示完整"):
        replace(capture, response_body_complete=1)
    with pytest.raises(DailySourceSnapshotError, match="非 bool 整數"):
        replace(capture, received_body_bytes=True)
    with pytest.raises(DailySourceSnapshotError, match="長度不符"):
        replace(capture, received_body_bytes=len(capture.raw_response_bytes) - 1)
    with pytest.raises(DailySourceSnapshotError, match="具名 EOF 完整性證據"):
        replace(capture, body_completion_evidence_ref="response-finished")
    with pytest.raises(DailySourceSnapshotError, match="ASCII 非負整數原文"):
        replace(capture, content_length_original_text="+" + str(len(capture.raw_response_bytes)))
    with pytest.raises(DailySourceSnapshotError, match="Content-Length 與原始 body 長度不符"):
        replace(capture, content_length_original_text="1")

    content_length_capture = replace(
        capture,
        content_length_original_text=str(len(capture.raw_response_bytes)),
        body_completion_evidence_ref="content-length-and-eof:synthetic-test-response",
    )
    assert content_length_capture.received_body_bytes == int(
        content_length_capture.content_length_original_text or "-1"
    )


def test_v2_reader_requires_completeness_evidence_keys(
    tmp_path: Path,
) -> None:
    canonical_bytes, record, capture = _big5_transport_fixture()
    _write(
        tmp_path,
        raw_bytes=canonical_bytes,
        record=record,
        transport_capture=capture,
    )

    def drop_eof_evidence(manifest: dict[str, object]) -> None:
        capture_value = manifest["transport_capture"]
        assert isinstance(capture_value, dict)
        capture_value.pop("body_completion_evidence_ref")

    _rewrite_manifest_and_rebind_receipt(
        tmp_path / "2026-10-02-twse-001",
        drop_eof_evidence,
    )
    with pytest.raises(DailySourceSnapshotError, match="欄位與版本契約不符"):
        read_daily_source_snapshot(
            tmp_path,
            "2026-10-02-twse-001",
            expected_scope=_scope(),
        )


def test_transport_capture_rejects_source_version_clock_and_late_body_time(
    tmp_path: Path,
) -> None:
    canonical_bytes, record, capture = _big5_transport_fixture()
    mismatched_clock = replace(
        capture,
        body_completed_at=datetime(2026, 10, 2, 10, 6, tzinfo=TAIPEI),
    )
    with pytest.raises(DailySourceSnapshotError, match="body_completed_at 與 transport"):
        _write(
            tmp_path,
            batch_id="clock-mismatch",
            raw_bytes=canonical_bytes,
            record=record,
            transport_capture=mismatched_clock,
        )

    late_body_times = (
        datetime(2026, 10, 2, 10, 4, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 10, 20, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 10, 25, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 10, 30, tzinfo=TAIPEI),
    )
    with pytest.raises(DailySourceSnapshotError, match="晚於首次保存"):
        _write(
            tmp_path,
            batch_id="late-body-batch",
            raw_bytes=canonical_bytes,
            record=record,
            transport_capture=capture,
            times=late_body_times,
        )


def test_reader_detects_transport_original_byte_tampering_after_hash_rebind(
    tmp_path: Path,
) -> None:
    canonical_bytes, record, capture = _big5_transport_fixture()
    _write(
        tmp_path,
        raw_bytes=canonical_bytes,
        record=record,
        transport_capture=capture,
    )

    def alter_transport_body(manifest: dict[str, object]) -> None:
        capture_value = manifest["transport_capture"]
        assert isinstance(capture_value, dict)
        original = capture_value["raw_response_bytes_base64"]
        assert isinstance(original, str) and original
        first_character = "A" if original[0] != "A" else "B"
        capture_value["raw_response_bytes_base64"] = first_character + original[1:]

    _rewrite_manifest_and_rebind_receipt(
        tmp_path / "2026-10-02-twse-001",
        alter_transport_body,
    )
    with pytest.raises(DailySourceSnapshotError, match="transport response bytes 與 transport SHA-256 不符"):
        read_daily_source_snapshot(
            tmp_path,
            "2026-10-02-twse-001",
            expected_scope=_scope(),
        )


def test_reader_requires_a_caller_trusted_acceptance_anchor(tmp_path: Path) -> None:
    _write(tmp_path)

    with pytest.raises(DailySourceSnapshotError, match="可信來源用途接受錨點"):
        _read_daily_source_snapshot(
            tmp_path,
            "2026-10-02-twse-001",
            expected_scope=_scope(),
        )
    untrusted_acceptance = replace(
        _acceptance(),
        acceptance_id="different-caller-acceptance",
    )
    with pytest.raises(DailySourceSnapshotError, match="caller 可信錨點不符"):
        DailySourceSnapshotFileReader(
            tmp_path,
            trusted_acceptance=untrusted_acceptance,
        ).read_snapshot(
            "2026-10-02-twse-001",
            expected_scope=_scope(),
        )


def test_writer_rejects_source_use_acceptance_created_after_batch_start(
    tmp_path: Path,
) -> None:
    raw_bytes = b"<html>acceptance came too late</html>"
    late_acceptance = replace(
        _acceptance(),
        accepted_at=datetime(2026, 10, 2, 10, 0, tzinfo=TAIPEI),
    )

    with pytest.raises(DailySourceSnapshotError, match="來源用途接受晚於每日批次開始"):
        write_daily_source_snapshot(
            tmp_path,
            batch_id="late-acceptance-batch",
            scope=_scope(),
            use_acceptance=late_acceptance,
            source_batch_started_at=datetime(2026, 10, 2, 9, 55, tzinfo=TAIPEI),
            raw_source_bytes=raw_bytes,
            records=(_record(raw_bytes),),
            validation=_validation(),
            clock=lambda: datetime(2026, 10, 2, 10, 10, tzinfo=TAIPEI),
        )

    assert not (
        tmp_path / "late-acceptance-batch" / "manifest.json"
    ).exists()


def test_receipt_round_trips_a_large_multi_record_daily_batch(tmp_path: Path) -> None:
    raw_bytes = b"<html>multi-record MOPS response</html>"
    template = _record(raw_bytes)
    record_count = 1_200
    records = tuple(
        replace(template, stock_code=f"{1000 + index:04d}")
        for index in range(record_count)
    )
    clock_values = iter(
        (
            datetime(2026, 10, 2, 10, 10, tzinfo=TAIPEI),
            datetime(2026, 10, 2, 10, 20, tzinfo=TAIPEI),
            datetime(2026, 10, 2, 10, 25, tzinfo=TAIPEI),
            datetime(2026, 10, 2, 10, 30, tzinfo=TAIPEI),
        )
    )
    write_daily_source_snapshot(
        tmp_path,
        batch_id="multi-record-batch",
        scope=_scope(),
        use_acceptance=_acceptance(),
        source_batch_started_at=datetime(2026, 10, 2, 9, 55, tzinfo=TAIPEI),
        raw_source_bytes=raw_bytes,
        records=records,
        validation=_validation(expected_count=record_count, actual_count=record_count),
        clock=lambda: next(clock_values),
    )

    receipt_size = (tmp_path / "multi-record-batch" / "receipt.json").stat().st_size
    assert receipt_size > 256 * 1024
    assert receipt_size <= MAX_DAILY_SOURCE_RECEIPT_BYTES
    snapshot = DailySourceSnapshotFileReader(
        tmp_path,
        trusted_acceptance=_acceptance(),
    ).read_snapshot("multi-record-batch", expected_scope=_scope())
    assert len(snapshot.records) == record_count
    assert len(snapshot.record_availability) == record_count
    assert snapshot.records[0].official_timestamp_original_timezone == "+00:00"
    assert snapshot.use_acceptance.document_chain == (
        "mops-monthly-revenue",
        "source-use-policy-v1",
    )
    assert snapshot.use_acceptance.authorization_scope == "recommendation_current_fundamental only"


def test_mops_roc_timestamp_round_trips_original_text_and_taipei_parser_basis(
    tmp_path: Path,
) -> None:
    raw_bytes = b"<html>roc clock body</html>"
    record = DailySourceSnapshotRecord(
        stock_code="2330",
        market="twse",
        period="2026-04",
        source_version=(
            "mops-static-snapshot.v2:twse:2026-04:body_completed_at:"
            "2026-10-02T10:20:00+08:00:sha256:"
            f"{hashlib.sha256(raw_bytes).hexdigest()}"
        ),
        raw_source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        unit="TWD",
        official_timestamp=datetime(2026, 5, 14, 14, 45, tzinfo=TAIPEI),
        official_timestamp_original_text="115/05/14 14:45:00",
        official_timestamp_original_timezone="Asia/Taipei",
    )

    _write(tmp_path, raw_bytes=raw_bytes, record=record)
    snapshot = read_daily_source_snapshot(
        tmp_path,
        "2026-10-02-twse-001",
        expected_scope=_scope(),
    )

    assert snapshot.records[0].official_timestamp_original_text == "115/05/14 14:45:00"
    assert snapshot.records[0].official_timestamp == datetime(
        2026, 5, 14, 14, 45, tzinfo=TAIPEI
    )
    assert snapshot.records[0].official_timestamp_original_timezone == "Asia/Taipei"


def test_availability_uses_ceiling_of_both_clocks_and_exact_cutoff(
    tmp_path: Path,
) -> None:
    _write(tmp_path)
    snapshot = read_daily_source_snapshot(
        tmp_path,
        "2026-10-02-twse-001",
        expected_scope=_scope(),
    )
    record = snapshot.records[0]
    available_at, basis = snapshot.availability_for(record)

    assert available_at == datetime(2026, 10, 2, 11, 0, tzinfo=available_at.tzinfo)
    assert basis == "official_timestamp_and_successful_batch_completion"
    assert not snapshot.is_available_by(
        record,
        datetime(2026, 10, 2, 10, 59, 59, tzinfo=available_at.tzinfo),
    )
    assert snapshot.is_available_by(record, available_at)


def test_receipt_persists_derived_available_hour_and_exact_hour_publish_guard(
    tmp_path: Path,
) -> None:
    raw_bytes = b"<html>exact completion hour</html>"
    record = _record(raw_bytes, official_timestamp=None, official_original="")
    exact = datetime(2026, 10, 2, 10, 0, tzinfo=TAIPEI)
    _write(
        tmp_path,
        raw_bytes=raw_bytes,
        record=record,
        times=(
            exact,
            exact,
            datetime(2026, 10, 2, 10, 10, tzinfo=TAIPEI),
            datetime(2026, 10, 2, 10, 20, tzinfo=TAIPEI),
        ),
    )
    receipt = json.loads(
        (tmp_path / "2026-10-02-twse-001" / "receipt.json").read_text(
            encoding="utf-8"
        )
    )

    assert receipt["successful_batch_completed_at"] == exact.isoformat(
        timespec="microseconds"
    )
    assert receipt["successful_batch_completion_basis"] == "durable_temporary_receipt_closed"
    assert receipt["record_availability"][0]["available_hour"] == datetime(
        2026, 10, 2, 11, 0, tzinfo=TAIPEI
    ).isoformat(timespec="microseconds")
    assert (
        receipt["record_availability"][0]["basis"]
        == "successful_batch_completion_exact_hour_publication_guard"
    )

    snapshot = read_daily_source_snapshot(
        tmp_path,
        "2026-10-02-twse-001",
        expected_scope=_scope(),
    )
    assert snapshot.availability_for(snapshot.records[0]) == (
        datetime(2026, 10, 2, 11, 0, tzinfo=TAIPEI),
        "successful_batch_completion_exact_hour_publication_guard",
    )


def test_writer_quarantines_a_batch_whose_persistence_crosses_an_hour(
    tmp_path: Path,
) -> None:
    raw_bytes = b"<html>persistence crossed hour</html>"
    boundary_times = (
        datetime(2026, 10, 2, 10, 59, 59, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 11, 0, 1, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 11, 0, 2, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 11, 0, 3, tzinfo=TAIPEI),
    )

    with pytest.raises(DailySourceSnapshotError, match="跨越整點"):
        _write(tmp_path, raw_bytes=raw_bytes, times=boundary_times)

    quarantine = json.loads(
        (tmp_path / "quarantine" / "2026-10-02-twse-001.json").read_text(
            encoding="utf-8"
        )
    )
    assert quarantine["failure_reason_code"] == "batch_persistence_crossed_hour_boundary"
    assert quarantine["raw_source_bytes_base64"] == base64.b64encode(raw_bytes).decode(
        "ascii"
    )
    assert not (tmp_path / "2026-10-02-twse-001" / "manifest.json").exists()
    with pytest.raises(DailySourceSnapshotError, match="不存在"):
        read_daily_source_snapshot(
            tmp_path,
            "2026-10-02-twse-001",
            expected_scope=_scope(),
        )


def test_writer_quarantines_when_success_receipt_write_finishes_after_guard_hour(
    tmp_path: Path,
) -> None:
    raw_bytes = b"<html>receipt persisted too late</html>"
    times = (
        datetime(2026, 10, 2, 10, 10, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 10, 20, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 11, 0, 1, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 11, 0, 2, tzinfo=TAIPEI),
    )

    with pytest.raises(DailySourceSnapshotError, match="成功收據晚於可用小時"):
        _write(tmp_path, raw_bytes=raw_bytes, times=times)

    quarantine = json.loads(
        (tmp_path / "quarantine" / "2026-10-02-twse-001.json").read_text(
            encoding="utf-8"
        )
    )
    assert quarantine["failure_reason_code"] == "successful_receipt_persisted_after_available_hour"
    assert not (tmp_path / "2026-10-02-twse-001" / "manifest.json").exists()


def test_writer_isolates_when_final_publish_finishes_after_guard_hour(
    tmp_path: Path,
) -> None:
    raw_bytes = b"<html>final publication too late</html>"
    times = (
        datetime(2026, 10, 2, 10, 10, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 10, 20, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 10, 55, tzinfo=TAIPEI),
        datetime(2026, 10, 2, 11, 0, 1, tzinfo=TAIPEI),
    )

    with pytest.raises(DailySourceSnapshotError, match="快照發布跨越可用小時"):
        _write(tmp_path, raw_bytes=raw_bytes, times=times)

    quarantine = json.loads(
        (tmp_path / "quarantine" / "2026-10-02-twse-001.json").read_text(
            encoding="utf-8"
        )
    )
    assert quarantine["failure_reason_code"] == "snapshot_published_after_available_hour"
    assert not (tmp_path / "2026-10-02-twse-001" / "manifest.json").exists()
    assert (
        tmp_path
        / ".daily_source_snapshot_isolated"
        / "2026-10-02-twse-001"
        / "manifest.json"
    ).exists()


def test_missing_official_clock_uses_successful_batch_completion_with_named_basis(
    tmp_path: Path,
) -> None:
    raw_bytes = b"<html>batch-clock fallback</html>"
    no_clock_record = _record(raw_bytes, official_timestamp=None, official_original="")
    _write(tmp_path, raw_bytes=raw_bytes, record=no_clock_record)
    snapshot = read_daily_source_snapshot(
        tmp_path,
        "2026-10-02-twse-001",
        expected_scope=_scope(),
    )

    available_at, basis = snapshot.availability_for(snapshot.records[0])
    assert available_at.hour == 11
    assert basis == "successful_batch_completion_fallback"


def test_later_official_clock_is_retained_and_cutoff_blocks_until_its_hour(
    tmp_path: Path,
) -> None:
    raw_bytes = b"<html>official clock after batch completion</html>"
    later_record = _record(
        raw_bytes,
        official_timestamp=datetime(2026, 10, 2, 3, 20, tzinfo=UTC),
        official_original="2026-10-02T03:20:00+00:00",
    )
    _write(tmp_path, raw_bytes=raw_bytes, record=later_record)
    snapshot = read_daily_source_snapshot(
        tmp_path,
        "2026-10-02-twse-001",
        expected_scope=_scope(),
    )
    record = snapshot.records[0]
    available_at, _ = snapshot.availability_for(record)

    assert available_at.hour == 12
    assert not snapshot.is_available_by(
        record,
        datetime(2026, 10, 2, 11, 59, 59, tzinfo=available_at.tzinfo),
    )
    assert snapshot.is_available_by(record, available_at)


def test_naive_timestamps_are_rejected_and_all_aware_zones_normalize_to_taipei(
    tmp_path: Path,
) -> None:
    raw_bytes = b"<html>naive must fail</html>"
    with pytest.raises(DailySourceSnapshotError, match="aware datetime"):
        write_daily_source_snapshot(
            tmp_path,
            batch_id="naive-batch",
            scope=_scope(),
            use_acceptance=_acceptance(),
            source_batch_started_at=datetime(2026, 10, 2, 9, 55),
            raw_source_bytes=raw_bytes,
            records=(_record(raw_bytes),),
            validation=_validation(),
            clock=lambda: datetime(2026, 10, 2, 10, 10, tzinfo=UTC),
        )

    _write(tmp_path)
    snapshot = read_daily_source_snapshot(
        tmp_path,
        "2026-10-02-twse-001",
        expected_scope=_scope(),
    )
    assert snapshot.first_persisted_at.tzinfo == TAIPEI


@pytest.mark.parametrize(
    "check_id",
    (
        "source_status",
        "raw_source_hash",
        "schema",
        "unit",
        "finite_values",
        "missing_values",
    ),
)
def test_named_daily_quality_failure_is_rejected_before_any_manifest_is_written(
    tmp_path: Path,
    check_id: str,
) -> None:
    failed = _validation(status_overrides={check_id: ("fail", f"{check_id}_mismatch")})

    with pytest.raises(DailySourceSnapshotError, match="品質驗證未通過"):
        _write(tmp_path, validation=failed, quarantine_root=tmp_path)

    assert not (tmp_path / "2026-10-02-twse-001" / "manifest.json").exists()
    quarantine = json.loads(
        (tmp_path / "quarantine" / "2026-10-02-twse-001.json").read_text(
            encoding="utf-8"
        )
    )
    expected_raw = b"<html>immutable MOPS response</html>"
    assert quarantine["failure_reason_code"].startswith("snapshot_validation_rejected:")
    assert quarantine["raw_source_bytes_base64"] == base64.b64encode(expected_raw).decode(
        "ascii"
    )
    assert quarantine["raw_source_sha256"] == hashlib.sha256(expected_raw).hexdigest()
    assert quarantine["validation"][f"{check_id}_check"]["status"] == "fail"


def test_quarantine_candidate_records_failed_partitions_without_success_receipt(
    tmp_path: Path,
) -> None:
    raw_bytes = b"<html>failed partition body</html>"
    candidate = write_daily_source_quarantine_candidate(
        tmp_path,
        batch_id="failed-partition-batch",
        raw_source_bytes=raw_bytes,
        failure_reason_code="partition_fetch_failed:tpex_monthly_revenue",
        scope=_scope(),
        source_batch_started_at=datetime(2026, 10, 2, 9, 55, tzinfo=TAIPEI),
        failed_partition_ids=("tpex-monthly-revenue",),
    )
    payload = json.loads(candidate.read_text(encoding="utf-8"))

    assert payload["failed_partition_ids"] == ["tpex-monthly-revenue"]
    assert payload["raw_source_bytes_base64"] == base64.b64encode(raw_bytes).decode("ascii")
    assert "available_hour" not in payload
    assert not (tmp_path / "failed-partition-batch" / "receipt.json").exists()
    assert "transport_capture" not in payload


def test_quarantine_preserves_big5_http_original_and_payload_mismatch(
    tmp_path: Path,
) -> None:
    canonical_bytes, _, capture = _big5_transport_fixture()
    mismatched_payload = canonical_bytes + b"<!-- unexpected parser payload -->"
    candidate = write_daily_source_quarantine_candidate(
        tmp_path,
        batch_id="transport-mismatch-candidate",
        raw_source_bytes=mismatched_payload,
        failure_reason_code="canonical_payload_transport_mismatch",
        scope=_scope(),
        transport_capture=capture,
    )
    saved_bytes = candidate.read_bytes()
    payload = json.loads(saved_bytes)
    assert payload["schema_version"] == "daily-source-quarantine.v2"
    content_hash = payload.pop("quarantine_sha256")
    assert content_hash == hashlib.sha256(_fixture_json_bytes(payload)).hexdigest()
    stored = payload["transport_capture"]
    assert base64.b64decode(stored["raw_response_bytes_base64"]) == capture.raw_response_bytes
    assert stored["transport_sha256"] == hashlib.sha256(capture.raw_response_bytes).hexdigest()
    assert payload["raw_source_sha256"] == hashlib.sha256(mismatched_payload).hexdigest()
    assert payload["canonical_payload_matches_transport"] is False
    assert stored["official_source_url"] == capture.official_source_url
    assert stored["body_completion_evidence_ref"] == capture.body_completion_evidence_ref
    assert "available_hour" not in payload
    with pytest.raises(DailySourceSnapshotError):
        DailySourceSnapshotFileReader(tmp_path, trusted_acceptance=_acceptance()).read_snapshot(
            "transport-mismatch-candidate", expected_scope=_scope()
        )
    with pytest.raises(DailySourceSnapshotError, match="已存在"):
        write_daily_source_quarantine_candidate(
            tmp_path,
            batch_id="transport-mismatch-candidate",
            raw_source_bytes=canonical_bytes,
            failure_reason_code="attempted_overwrite",
            transport_capture=capture,
        )
    assert candidate.read_bytes() == saved_bytes


def test_cross_hour_writer_quarantine_keeps_http_transport_evidence(tmp_path: Path) -> None:
    canonical_bytes, record, capture = _big5_transport_fixture()
    with pytest.raises(DailySourceSnapshotError, match="跨越整點"):
        _write(
            tmp_path,
            raw_bytes=canonical_bytes,
            record=record,
            transport_capture=capture,
            times=(
                datetime(2026, 10, 2, 10, 59, tzinfo=TAIPEI),
                datetime(2026, 10, 2, 11, 0, tzinfo=TAIPEI),
                datetime(2026, 10, 2, 11, 1, tzinfo=TAIPEI),
                datetime(2026, 10, 2, 11, 2, tzinfo=TAIPEI),
            ),
        )
    payload = json.loads((tmp_path / "quarantine" / "2026-10-02-twse-001.json").read_bytes())
    assert payload["failure_reason_code"] == "batch_persistence_crossed_hour_boundary"
    assert payload["canonical_payload_matches_transport"] is True
    assert payload["transport_capture"] == capture.to_dict()
    assert not (tmp_path / "2026-10-02-twse-001" / "receipt.json").exists()


def test_quarantine_rejects_invalid_transport_without_creating_candidate(tmp_path: Path) -> None:
    _, _, capture = _big5_transport_fixture()
    object.__setattr__(capture, "raw_response_bytes", b"changed HTTP original")
    with pytest.raises(DailySourceSnapshotError, match="body 長度不符"):
        write_daily_source_quarantine_candidate(
            tmp_path,
            batch_id="invalid-transport-candidate",
            raw_source_bytes=b"canonical source",
            failure_reason_code="invalid_transport",
            transport_capture=capture,
        )
    assert not (tmp_path / "quarantine" / "invalid-transport-candidate.json").exists()


@pytest.mark.parametrize("cancel_at", [1, 2])
def test_writer_cooperative_cancel_before_persistence_or_publish_has_no_public_snapshot(
    tmp_path: Path, cancel_at: int,
) -> None:
    calls = 0

    def check_cancel() -> None:
        nonlocal calls
        calls += 1
        if calls == cancel_at:
            raise RuntimeError("cooperative_cancelled")

    with pytest.raises(RuntimeError, match="cooperative_cancelled"):
        _write(tmp_path, check_cancel=check_cancel)
    assert calls == cancel_at
    assert not (tmp_path / "2026-10-02-twse-001").exists()
    with pytest.raises(DailySourceSnapshotError):
        DailySourceSnapshotFileReader(tmp_path, trusted_acceptance=_acceptance()).read_snapshot(
            "2026-10-02-twse-001", expected_scope=_scope()
        )
    if cancel_at == 2:
        assert (tmp_path / ".daily_source_snapshot_staging" / "2026-10-02-twse-001" / "receipt.json").exists()


def test_quarantine_collision_does_not_hide_primary_validation_error(tmp_path: Path) -> None:
    quarantine = tmp_path / "quarantine" / "2026-10-02-twse-001.json"
    quarantine.parent.mkdir()
    original = b"existing failure evidence"
    quarantine.write_bytes(original)
    with pytest.raises(DailySourceSnapshotError, match="單位") as failure:
        _write(tmp_path, record=_record(b"<html>immutable MOPS response</html>", unit="USD"), quarantine_root=tmp_path)
    assert any("quarantine_preservation_failed:" in note for note in failure.value.__notes__)
    assert quarantine.read_bytes() == original
    assert not (tmp_path / "2026-10-02-twse-001").exists()


def test_post_publish_quarantine_collision_still_isolates_late_snapshot(tmp_path: Path) -> None:
    quarantine = tmp_path / "quarantine" / "2026-10-02-twse-001.json"
    quarantine.parent.mkdir()
    original = b"existing failure evidence"
    quarantine.write_bytes(original)
    with pytest.raises(DailySourceSnapshotError, match="發布跨越可用小時") as failure:
        _write(tmp_path, times=(
            datetime(2026, 10, 2, 10, 10, tzinfo=TAIPEI),
            datetime(2026, 10, 2, 10, 20, tzinfo=TAIPEI),
            datetime(2026, 10, 2, 10, 30, tzinfo=TAIPEI),
            datetime(2026, 10, 2, 11, 0, 0, 1, tzinfo=TAIPEI),
        ))
    assert any("quarantine_preservation_failed:" in note for note in failure.value.__notes__)
    assert quarantine.read_bytes() == original
    assert not (tmp_path / "2026-10-02-twse-001").exists()
    assert (tmp_path / ".daily_source_snapshot_isolated" / "2026-10-02-twse-001").is_dir()


@pytest.mark.parametrize("failure_mode", ["clock_exception", "invalid_clock", "isolation_collision", "isolation_move", "isolation_symlink", "pending_unlink"])
def test_post_publish_failure_leaves_reader_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_mode: str,
) -> None:
    calls = 0
    real_rename = os.rename
    real_is_symlink = Path.is_symlink
    real_unlink = Path.unlink

    def clock() -> datetime:
        nonlocal calls
        calls += 1
        if calls == 4:
            if failure_mode == "clock_exception":
                raise RuntimeError("post_publish_clock_unavailable")
            if failure_mode == "invalid_clock":
                return datetime(2026, 10, 2, 10, 30)
            if failure_mode == "pending_unlink":
                return datetime(2026, 10, 2, 10, 30, tzinfo=TAIPEI)
            return datetime(2026, 10, 2, 11, 0, 0, 1, tzinfo=TAIPEI)
        return datetime(2026, 10, 2, 10, calls * 5, tzinfo=TAIPEI)

    def rename(source: Path, destination: Path) -> None:
        if failure_mode == "isolation_move" and destination.parent.name == ".daily_source_snapshot_isolated":
            raise PermissionError("owned_isolation_move_denied")
        real_rename(source, destination)

    def is_symlink(path: Path) -> bool:
        return (failure_mode == "isolation_symlink" and path.name == ".daily_source_snapshot_isolated") or real_is_symlink(path)

    def unlink(path: Path, missing_ok: bool = False) -> None:
        if failure_mode == "pending_unlink" and path.name == ".receipt.pending.json":
            raise PermissionError("owned_pending_barrier_unlink_denied")
        real_unlink(path, missing_ok=missing_ok)

    if failure_mode == "isolation_collision":
        (tmp_path / ".daily_source_snapshot_isolated" / "2026-10-02-twse-001").mkdir(parents=True)
    monkeypatch.setattr(os, "rename", rename)
    monkeypatch.setattr(Path, "is_symlink", is_symlink)
    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises((RuntimeError, DailySourceSnapshotError, OSError)):
        write_daily_source_snapshot(
            tmp_path, batch_id="2026-10-02-twse-001", scope=_scope(),
            use_acceptance=_acceptance(),
            source_batch_started_at=datetime(2026, 10, 2, 9, 55, tzinfo=TAIPEI),
            raw_source_bytes=b"<html>immutable MOPS response</html>",
            records=(_record(b"<html>immutable MOPS response</html>"),),
            validation=_validation(), clock=clock,
        )
    with pytest.raises(DailySourceSnapshotError, match="publication 尚未完成或已拒絕"):
        DailySourceSnapshotFileReader(tmp_path, trusted_acceptance=_acceptance()).read_snapshot(
            "2026-10-02-twse-001", expected_scope=_scope()
        )
    assert (tmp_path / "2026-10-02-twse-001" / ".receipt.pending.json").is_file()


def test_writer_tampered_transport_preserves_canonical_only_failure(tmp_path: Path) -> None:
    canonical_bytes, record, capture = _big5_transport_fixture()
    object.__setattr__(capture, "raw_response_bytes", b"changed HTTP original")
    with pytest.raises(DailySourceSnapshotError):
        _write(tmp_path, raw_bytes=canonical_bytes, record=record, transport_capture=capture, quarantine_root=tmp_path)
    payload = json.loads((tmp_path / "quarantine" / "2026-10-02-twse-001.json").read_bytes())
    assert payload["schema_version"] == "daily-source-quarantine.v1"
    assert "transport_capture" not in payload
    assert base64.b64decode(payload["raw_source_bytes_base64"]) == canonical_bytes
    assert payload["raw_source_sha256"] == hashlib.sha256(canonical_bytes).hexdigest()
    assert payload["failure_reason_code"].endswith("transport_capture_not_archived")
    assert not (tmp_path / "2026-10-02-twse-001").exists()


def test_partial_batch_bad_unit_and_wrong_use_scope_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(DailySourceSnapshotError, match="分區未完整成功"):
        DailySourceBatchValidation(
            validation_id="partial",
            expected_partition_ids=("a", "b"),
            successful_partition_ids=("a",),
            failed_partition_ids=("b",),
            expected_record_count=1,
            actual_record_count=1,
            source_status_check=DailySourceValidationCheck("source_status", "pass", "ok"),
            raw_source_hash_check=DailySourceValidationCheck("raw_source_hash", "pass", "ok"),
            schema_check=DailySourceValidationCheck("schema", "pass", "ok"),
            unit_check=DailySourceValidationCheck("unit", "pass", "ok"),
            finite_values_check=DailySourceValidationCheck("finite_values", "pass", "ok"),
            missing_values_check=DailySourceValidationCheck("missing_values", "pass", "ok"),
            prior_period_required_check=DailySourceValidationCheck(
                "prior_period_required", "not_required", "prior_period_not_required"
            ),
            official_timestamp_parse_check=DailySourceValidationCheck(
                "official_timestamp_parse",
                "pass",
                "official_timestamp_parsed_by:mops-current-revenue-normalizer.v2",
            ),
        )

    raw_bytes = b"<html>wrong unit</html>"
    with pytest.raises(DailySourceSnapshotError, match="單位"):
        _write(tmp_path, raw_bytes=raw_bytes, record=_record(raw_bytes, unit="USD"))

    _write(tmp_path)
    with pytest.raises(DailySourceSnapshotError, match="範圍與呼叫端預期不符"):
        _read_daily_source_snapshot(
            tmp_path,
            "2026-10-02-twse-001",
            expected_scope=replace(_scope(), intended_use="forward_research"),
            trusted_acceptance=_acceptance(),
        )


def test_create_only_batch_ids_preserve_corrections_as_distinct_snapshots(
    tmp_path: Path,
) -> None:
    initial_bytes = b"<html>original body</html>"
    initial_record = _record(initial_bytes)
    _write(
        tmp_path,
        batch_id="initial-batch",
        raw_bytes=initial_bytes,
        record=initial_record,
    )
    with pytest.raises(DailySourceSnapshotError, match="已存在"):
        _write(
            tmp_path,
            batch_id="initial-batch",
            raw_bytes=initial_bytes,
            record=initial_record,
        )

    corrected_bytes = b"<html>corrected official response</html>"
    with pytest.raises(DailySourceSnapshotError, match="source_version SHA 與原始 bytes 不符"):
        conflicting_record = _record(
            corrected_bytes,
            source_version=initial_record.source_version,
        )
        _write(
            tmp_path,
            batch_id="conflicting-version",
            raw_bytes=corrected_bytes,
            record=conflicting_record,
        )

    corrected_record = _record(
        corrected_bytes,
        source_version=(
            "mops-static-snapshot.v2:twse:2026-04:body_completed_at:"
            "2026-10-02T10:05:00+08:00:sha256:"
            f"{hashlib.sha256(corrected_bytes).hexdigest()}"
        ),
    )
    _write(
        tmp_path,
        batch_id="corrected-batch",
        raw_bytes=corrected_bytes,
        record=corrected_record,
    )

    original = read_daily_source_snapshot(
        tmp_path,
        "initial-batch",
        expected_scope=_scope(),
    )
    corrected = read_daily_source_snapshot(
        tmp_path,
        "corrected-batch",
        expected_scope=_scope(),
    )
    assert original.raw_source_bytes != corrected.raw_source_bytes
    assert original.records[0].source_version != corrected.records[0].source_version


def test_reader_rejects_missing_receipt_and_manifest_tampering(tmp_path: Path) -> None:
    _write(tmp_path)
    batch_root = tmp_path / "2026-10-02-twse-001"
    manifest = batch_root / "manifest.json"
    original_manifest = manifest.read_bytes()
    manifest.write_bytes(
        original_manifest.replace(b"mops-static-snapshot", b"mops-static-revision")
    )
    with pytest.raises(DailySourceSnapshotError, match="未綁定目前 manifest"):
        read_daily_source_snapshot(
            tmp_path,
            "2026-10-02-twse-001",
            expected_scope=_scope(),
        )

    manifest.write_bytes(original_manifest)
    (batch_root / "receipt.json").unlink()
    with pytest.raises(DailySourceSnapshotError, match="不存在"):
        read_daily_source_snapshot(
            tmp_path,
            "2026-10-02-twse-001",
            expected_scope=_scope(),
        )


def test_reader_rejects_receipt_hash_and_validation_evidence_tampering(
    tmp_path: Path,
) -> None:
    _write(tmp_path)
    batch_root = tmp_path / "2026-10-02-twse-001"
    receipt = batch_root / "receipt.json"
    original_receipt = receipt.read_bytes()

    altered_hash = original_receipt.replace(
        b'"receipt_sha256":"', b'"receipt_sha256":"0', 1
    )
    receipt.write_bytes(altered_hash)
    with pytest.raises(DailySourceSnapshotError, match="receipt SHA-256 不符"):
        read_daily_source_snapshot(
            tmp_path,
            "2026-10-02-twse-001",
            expected_scope=_scope(),
        )

    tampered_availability = json.loads(original_receipt.decode("utf-8"))
    tampered_availability["record_availability"][0]["available_hour"] = datetime(
        2026, 10, 2, 12, 0, tzinfo=TAIPEI
    ).isoformat(timespec="microseconds")
    unsigned_receipt = dict(tampered_availability)
    unsigned_receipt.pop("receipt_sha256")
    tampered_availability["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned_receipt,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    receipt.write_text(
        json.dumps(
            tampered_availability,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(DailySourceSnapshotError, match="固定政策重算不符"):
        read_daily_source_snapshot(
            tmp_path,
            "2026-10-02-twse-001",
            expected_scope=_scope(),
        )

    altered_validation = original_receipt.replace(
        b'"reason_code":"source_status_pass"',
        b'"reason_code":"source_status_tampered"',
        1,
    )
    assert altered_validation != original_receipt
    receipt.write_bytes(altered_validation)
    with pytest.raises(DailySourceSnapshotError, match="receipt SHA-256 不符"):
        read_daily_source_snapshot(
            tmp_path,
            "2026-10-02-twse-001",
            expected_scope=_scope(),
        )
