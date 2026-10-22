"""月營收原始批次的唯讀版本封存與觀測時間選擇。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from data_module.opendata_monthly_revenue import (
    OPENAPI_MONTHLY_REVENUE_PARSER_VERSION,
    OpenApiMonthlyRevenueBatch,
    OpenApiMonthlyRevenueCapture,
    OpenApiMonthlyRevenueError,
    prepare_openapi_monthly_revenue_batch,
)
from data_module.daily_source_snapshot import _transport_capture_from_dict
from data_module.mops_monthly_revenue_history import (
    MOPS_MONTHLY_REVENUE_HISTORY_PARSER_VERSION,
    MopsHistoryMarket,
    MopsMonthlyRevenueHistoricalCapture,
    MopsMonthlyRevenueHistoryError,
    parse_mops_monthly_revenue_history_capture,
    rebuild_mops_monthly_revenue_history_capture_from_transport_chain,
)


MONTHLY_REVENUE_REVISION_ARCHIVE_SCHEMA_V1 = "monthly-revenue-revision-archive.v1"
MONTHLY_REVENUE_RAW_BATCH_SCHEMA_V1 = "monthly-revenue-raw-batch.v1"
MONTHLY_REVENUE_OBSERVATION_AS_OF_SCHEMA_V1 = "monthly-revenue-observation-as-of.v1"
MONTHLY_REVENUE_ARCHIVE_MAX_BATCHES = 4096
MONTHLY_REVENUE_ARCHIVE_MAX_ROWS = 100_000
MONTHLY_REVENUE_ARCHIVE_MAX_RAW_BYTES = 64 * 1024 * 1024
MONTHLY_REVENUE_ARCHIVE_MAX_INDEX_BYTES = 16 * 1024 * 1024
MONTHLY_REVENUE_ARCHIVE_MAX_HISTORY_BATCHES = MONTHLY_REVENUE_ARCHIVE_MAX_BATCHES
_MARKETS = ("twse", "tpex")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_TAIPEI = ZoneInfo("Asia/Taipei")


class MonthlyRevenueRevisionArchiveError(ValueError):
    """月營收版本封存或觀測時間選擇未通過契約。"""


@dataclass(frozen=True, slots=True)
class MonthlyRevenueRawRowV1:
    """保留原始欄位文字、單位狀態及穩定逐列摘要。"""

    stock_code: str
    period: str
    source_values: tuple[tuple[str, str], ...]
    source_unit_text: str | None
    unit_status: str
    unit_proof_sha256: str | None
    row_sha256: str

    def __post_init__(self) -> None:
        _validate_stock_code(self.stock_code)
        _validate_period(self.period)
        if type(self.source_values) is not tuple or not self.source_values:
            raise MonthlyRevenueRevisionArchiveError("raw_row_source_values_invalid")
        if any(
            type(pair) is not tuple
            or len(pair) != 2
            or type(pair[0]) is not str
            or not pair[0]
            or type(pair[1]) is not str
            for pair in self.source_values
        ):
            raise MonthlyRevenueRevisionArchiveError("raw_row_source_values_invalid")
        names = tuple(pair[0] for pair in self.source_values)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise MonthlyRevenueRevisionArchiveError("raw_row_source_values_not_canonical")
        if self.source_unit_text is not None and type(self.source_unit_text) is not str:
            raise MonthlyRevenueRevisionArchiveError("raw_row_source_unit_invalid")
        if self.unit_status not in {"unknown", "verified"}:
            raise MonthlyRevenueRevisionArchiveError("raw_row_unit_status_invalid")
        if self.unit_status == "unknown" and self.unit_proof_sha256 is not None:
            raise MonthlyRevenueRevisionArchiveError("unknown_unit_cannot_claim_proof")
        if self.unit_proof_sha256 is not None:
            _require_sha256(self.unit_proof_sha256, "unit_proof_sha256")
        _require_sha256(self.row_sha256, "row_sha256")
        if self.row_sha256 != _row_sha256(
            stock_code=self.stock_code,
            period=self.period,
            source_values=self.source_values,
            source_unit_text=self.source_unit_text,
            unit_status=self.unit_status,
            unit_proof_sha256=self.unit_proof_sha256,
        ):
            raise MonthlyRevenueRevisionArchiveError("raw_row_hash_mismatch")

    @classmethod
    def build(
        cls,
        *,
        stock_code: str,
        period: str,
        source_values: Mapping[str, str],
        source_unit_text: str | None,
        unit_status: str,
        unit_proof_sha256: str | None,
    ) -> "MonthlyRevenueRawRowV1":
        pairs = tuple(sorted((str(key), str(value)) for key, value in source_values.items()))
        return cls(
            stock_code=stock_code,
            period=period,
            source_values=pairs,
            source_unit_text=source_unit_text,
            unit_status=unit_status,
            unit_proof_sha256=unit_proof_sha256,
            row_sha256=_row_sha256(
                stock_code=stock_code,
                period=period,
                source_values=pairs,
                source_unit_text=source_unit_text,
                unit_status=unit_status,
                unit_proof_sha256=unit_proof_sha256,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "stock_code": self.stock_code,
            "period": self.period,
            "source_values": {key: value for key, value in self.source_values},
            "source_unit_text": self.source_unit_text,
            "unit_status": self.unit_status,
            "unit_proof_sha256": self.unit_proof_sha256,
            "row_sha256": self.row_sha256,
        }


@dataclass(frozen=True, slots=True)
class MonthlyRevenueRawBatchEvidenceV1:
    """可封存的不可變原始批次；時間只表示捕獲後可觀測。"""

    market: str
    source_id: str
    source_version: str
    period: str
    parser_version: str
    raw_source_bytes: bytes
    raw_source_sha256: str
    captured_at: datetime
    available_at: datetime
    availability_basis: str
    rows: tuple[MonthlyRevenueRawRowV1, ...]
    parent_revision_ids: tuple[tuple[str, str, str, str], ...] = ()
    transport_provenance: tuple[
        tuple[str, str | int | bool | None], ...
    ] = ()
    official_announcement_at: datetime | None = None
    official_revision_id: str | None = None

    def __post_init__(self) -> None:
        if self.market not in _MARKETS:
            raise MonthlyRevenueRevisionArchiveError("batch_market_invalid")
        _require_nonempty(self.source_id, "source_id")
        _require_nonempty(self.source_version, "source_version")
        _validate_period(self.period)
        _require_nonempty(self.parser_version, "parser_version")
        if not isinstance(self.raw_source_bytes, bytes) or not self.raw_source_bytes:
            raise MonthlyRevenueRevisionArchiveError("batch_raw_bytes_invalid")
        if len(self.raw_source_bytes) > MONTHLY_REVENUE_ARCHIVE_MAX_RAW_BYTES:
            raise MonthlyRevenueRevisionArchiveError("batch_raw_bytes_exceeds_limit")
        _require_sha256(self.raw_source_sha256, "raw_source_sha256")
        if hashlib.sha256(self.raw_source_bytes).hexdigest() != self.raw_source_sha256:
            raise MonthlyRevenueRevisionArchiveError("batch_raw_hash_mismatch")
        captured = _aware_taipei(self.captured_at, "captured_at")
        available = _aware_taipei(self.available_at, "available_at")
        if available < captured:
            raise MonthlyRevenueRevisionArchiveError("available_before_capture")
        if not self.availability_basis:
            raise MonthlyRevenueRevisionArchiveError("availability_basis_missing")
        if not isinstance(self.rows, tuple) or not self.rows:
            raise MonthlyRevenueRevisionArchiveError("batch_rows_invalid")
        if len(self.rows) > MONTHLY_REVENUE_ARCHIVE_MAX_ROWS:
            raise MonthlyRevenueRevisionArchiveError("batch_rows_exceed_limit")
        if any(type(row) is not MonthlyRevenueRawRowV1 for row in self.rows):
            raise MonthlyRevenueRevisionArchiveError("batch_row_type_invalid")
        if any(row.period != self.period for row in self.rows):
            raise MonthlyRevenueRevisionArchiveError("batch_row_period_mismatch")
        identities = tuple(row.stock_code for row in self.rows)
        if identities != tuple(sorted(identities)) or len(identities) != len(set(identities)):
            raise MonthlyRevenueRevisionArchiveError("batch_row_order_or_identity_invalid")
        if len(self.parent_revision_ids) > len(self.rows):
            raise MonthlyRevenueRevisionArchiveError("parent_revision_count_invalid")
        parent_keys: set[tuple[str, str, str]] = set()
        for item in self.parent_revision_ids:
            if type(item) is not tuple or len(item) != 4:
                raise MonthlyRevenueRevisionArchiveError("parent_revision_reference_invalid")
            stock_code, period, row_hash, revision_id = item
            _validate_stock_code(stock_code)
            _validate_period(period)
            _require_sha256(row_hash, "parent_row_sha256")
            _require_sha256(revision_id, "parent_revision_id")
            key = (stock_code, period, revision_id)
            if key in parent_keys:
                raise MonthlyRevenueRevisionArchiveError("parent_revision_reference_duplicate")
            parent_keys.add(key)
        if tuple(sorted(self.parent_revision_ids)) != self.parent_revision_ids:
            raise MonthlyRevenueRevisionArchiveError("parent_revision_references_not_canonical")
        if tuple(sorted(self.transport_provenance)) != self.transport_provenance:
            raise MonthlyRevenueRevisionArchiveError("transport_provenance_not_canonical")
        for provenance_key, value in self.transport_provenance:
            if type(provenance_key) is not str or not provenance_key or (
                value is not None and type(value) not in (str, int, bool)
            ):
                raise MonthlyRevenueRevisionArchiveError("transport_provenance_invalid")
        if self.official_announcement_at is not None:
            object.__setattr__(
                self,
                "official_announcement_at",
                _aware_taipei(self.official_announcement_at, "official_announcement_at"),
            )
        if self.official_revision_id is not None:
            _require_nonempty(self.official_revision_id, "official_revision_id")
        object.__setattr__(self, "captured_at", captured)
        object.__setattr__(self, "available_at", available)


@dataclass(frozen=True, slots=True)
class MonthlyRevenueArchiveAppendResult:
    archive_sha256: str
    archive_path: Path
    raw_blob_sha256: str
    batch_revision_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MonthlyRevenueArchivedObservationV1:
    market: str
    stock_code: str
    period: str
    source_id: str
    source_version: str
    revision_id: str
    parent_revision_id: str | None
    row_sha256: str
    raw_source_sha256: str
    captured_at: datetime
    captured_batch_available_at: datetime
    archive_persisted_at: datetime
    available_at: datetime
    availability_basis: str
    source_values: tuple[tuple[str, str], ...]
    source_unit_text: str | None
    unit_status: str
    unit_proof_sha256: str | None
    official_announcement_at: datetime | None
    official_revision_id: str | None
    archive_sha256: str

    def __post_init__(self) -> None:
        captured = _aware_taipei(self.captured_at, "captured_at")
        batch_available = _aware_taipei(
            self.captured_batch_available_at, "captured_batch_available_at"
        )
        persisted = _aware_taipei(self.archive_persisted_at, "archive_persisted_at")
        effective = _aware_taipei(self.available_at, "available_at")
        if batch_available < captured:
            raise MonthlyRevenueRevisionArchiveError(
                "archive_observation_source_available_before_capture"
            )
        if effective != max(batch_available, _ceil_hour(persisted)):
            raise MonthlyRevenueRevisionArchiveError(
                "archive_observation_effective_availability_mismatch"
            )


@dataclass(frozen=True, slots=True)
class MonthlyRevenueAsOfResult:
    observation: MonthlyRevenueArchivedObservationV1 | None
    observation_as_of_verified: bool
    formal_pit_eligible: bool
    status: str
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MonthlyRevenueRevisionArchiveV1:
    root: Path
    archive_sha256: str
    parent_archive_sha256: str | None
    batches: tuple[Mapping[str, object], ...]


def raw_batch_from_openapi(batch: OpenApiMonthlyRevenueBatch) -> MonthlyRevenueRawBatchEvidenceV1:
    """從 OpenData 候選建立原單位觀測 DTO，不授予用途或正式 PIT 資格。"""

    if type(batch) is not OpenApiMonthlyRevenueBatch:
        raise MonthlyRevenueRevisionArchiveError("openapi_batch_type_invalid")
    capture = batch.capture
    if capture.body_completed_at is None:
        raise MonthlyRevenueRevisionArchiveError("openapi_capture_completion_missing")
    rows = tuple(
        MonthlyRevenueRawRowV1.build(
            stock_code=row.stock_code,
            period=row.period,
            source_values={
                **dict(row.source_values),
                **{key: str(value) for key, value in row.amount_values_source_unit},
                **{
                    key: (str(value) if value is not None else "")
                    for key, value in row.percentage_values
                },
            },
            source_unit_text=None,
            unit_status="unknown",
            unit_proof_sha256=None,
        )
        for row in batch.rows
    )
    return MonthlyRevenueRawBatchEvidenceV1(
        market=capture.market,
        source_id=capture.source_id,
        source_version=batch.rows[0].source_version,
        period=batch.period,
        parser_version=OPENAPI_MONTHLY_REVENUE_PARSER_VERSION,
        raw_source_bytes=capture.raw_response_bytes,
        raw_source_sha256=capture.raw_response_sha256,
        captured_at=batch.successful_batch_completed_at,
        available_at=batch.available_hour,
        availability_basis="captured_complete_batch_available_hour",
        rows=rows,
        transport_provenance=tuple(
            sorted(
                (key, _transport_provenance_value(value))
                for key, value in capture.provenance_dict().items()
            )
        ),
    )


def append_monthly_revenue_batch(
    root: Path | str,
    batch: MonthlyRevenueRawBatchEvidenceV1,
    *,
    archive_sha256: str | None,
    expected_archive_sha256: str | None,
) -> MonthlyRevenueArchiveAppendResult:
    """以 create-only blob 與外部 SHA 綁定的索引封存一個批次。

    完整索引包含所有批次與逐列 revision chain；parent hash 僅記錄呼叫端明選
    的不可變前版，不宣稱有共享 head 或跨程序 CAS。不同呼叫可由同一 parent
    建立不同的不可變分支，之後讀取完整索引不依賴前版索引檔仍存在。
    """

    if type(batch) is not MonthlyRevenueRawBatchEvidenceV1:
        raise MonthlyRevenueRevisionArchiveError("batch_evidence_type_invalid")
    base = _checked_root(root, create=True)
    if (archive_sha256 is None) != (expected_archive_sha256 is None):
        raise MonthlyRevenueRevisionArchiveError("archive_expected_hash_pair_incomplete")
    old_batches: tuple[dict[str, object], ...]
    if archive_sha256 is not None:
        _require_sha256(archive_sha256, "archive_sha256")
        _require_sha256(expected_archive_sha256, "expected_archive_sha256")
        if archive_sha256 != expected_archive_sha256:
            raise MonthlyRevenueRevisionArchiveError("archive_external_hash_mismatch")
        previous = read_monthly_revenue_revision_archive(
            base,
            archive_sha256,
            expected_archive_sha256=expected_archive_sha256,
        )
        old_batches = tuple(
            _copy_validated_archive_batch(item) for item in previous.batches
        )
        parent_hash: str | None = previous.archive_sha256
    else:
        old_batches = ()
        parent_hash = None
    if len(old_batches) >= MONTHLY_REVENUE_ARCHIVE_MAX_HISTORY_BATCHES:
        raise MonthlyRevenueRevisionArchiveError(
            "archive_history_limit_reached_start_a_new_explicit_archive_shard"
        )

    blob_hash = batch.raw_source_sha256
    blob_dir = base / "raw" / "sha256"
    _ensure_directory(base, blob_dir)
    blob_path = blob_dir / f"{blob_hash}.bin"
    _write_content_addressed(blob_path, batch.raw_source_bytes, blob_hash)
    row_entries = tuple(
        _row_entry(batch, row) for row in batch.rows
    )
    persisted_at = _aware_utc(_utc_now(), "archive_persisted_at")
    source_available_at = batch.available_at
    effective_available_at = max(source_available_at, _ceil_hour(persisted_at))
    batch_entry: dict[str, object] = {
        "schema_version": MONTHLY_REVENUE_RAW_BATCH_SCHEMA_V1,
        "market": batch.market,
        "source_id": batch.source_id,
        "source_version": batch.source_version,
        "period": batch.period,
        "parser_version": batch.parser_version,
        "raw_source_sha256": blob_hash,
        "captured_at": _datetime_text(batch.captured_at),
        "captured_batch_available_at": _datetime_text(source_available_at),
        "archive_persisted_at": _utc_datetime_text(persisted_at),
        "available_at": _datetime_text(effective_available_at),
        "availability_basis": batch.availability_basis,
        "transport_provenance": {key: value for key, value in batch.transport_provenance},
        "official_announcement_at": (
            _datetime_text(batch.official_announcement_at)
            if batch.official_announcement_at is not None
            else None
        ),
        "official_revision_id": batch.official_revision_id,
        "parent_revision_ids": [list(item) for item in batch.parent_revision_ids],
        "rows": list(row_entries),
    }
    if any(
        item.get("market") == batch.market
        and item.get("source_id") == batch.source_id
        and item.get("source_version") == batch.source_version
        for item in old_batches
    ):
        raise MonthlyRevenueRevisionArchiveError("archive_batch_identity_duplicate")
    batches: tuple[Mapping[str, object], ...] = (*old_batches, batch_entry)
    total_rows = sum(len(_batch_rows(item)) for item in batches)
    total_bytes = sum(_archive_batch_raw_byte_count(item) for item in old_batches)
    batch_entry["raw_byte_count"] = len(batch.raw_source_bytes)
    total_bytes += len(batch.raw_source_bytes)
    if total_rows > MONTHLY_REVENUE_ARCHIVE_MAX_ROWS:
        raise MonthlyRevenueRevisionArchiveError("archive_row_count_exceeds_limit")
    if total_bytes > MONTHLY_REVENUE_ARCHIVE_MAX_RAW_BYTES:
        raise MonthlyRevenueRevisionArchiveError("archive_raw_bytes_exceed_limit")
    _validate_parent_references(batches)
    payload = _canonical_json_bytes(
        {
            "schema_version": MONTHLY_REVENUE_REVISION_ARCHIVE_SCHEMA_V1,
            "parent_archive_sha256": parent_hash,
            "batches": list(batches),
        }
    )
    if len(payload) > MONTHLY_REVENUE_ARCHIVE_MAX_INDEX_BYTES:
        raise MonthlyRevenueRevisionArchiveError("archive_index_exceeds_limit")
    digest = hashlib.sha256(payload).hexdigest()
    index_dir = base / "indexes"
    _ensure_directory(base, index_dir)
    index_path = index_dir / f"{digest}.json"
    _write_create_only(index_path, payload)
    return MonthlyRevenueArchiveAppendResult(
        archive_sha256=digest,
        archive_path=index_path,
        raw_blob_sha256=blob_hash,
        batch_revision_ids=tuple(str(item["revision_id"]) for item in row_entries),
    )


def read_monthly_revenue_revision_archive(
    root: Path | str,
    archive_sha256: str,
    *,
    expected_archive_sha256: str,
) -> MonthlyRevenueRevisionArchiveV1:
    """只讀呼叫端明選且以外部 SHA 錨定的 archive index。"""

    selected = _require_sha256(archive_sha256, "archive_sha256")
    expected = _require_sha256(expected_archive_sha256, "expected_archive_sha256")
    if selected != expected:
        raise MonthlyRevenueRevisionArchiveError("archive_external_hash_mismatch")
    base = _checked_root(root, create=False)
    index_path = base / "indexes" / f"{selected}.json"
    payload = _read_regular_file(index_path, MONTHLY_REVENUE_ARCHIVE_MAX_INDEX_BYTES)
    if hashlib.sha256(payload).hexdigest() != selected:
        raise MonthlyRevenueRevisionArchiveError("archive_index_hash_mismatch")
    decoded = _decode_canonical_json(payload)
    if type(decoded) is not dict or set(decoded) != {
        "schema_version",
        "parent_archive_sha256",
        "batches",
    }:
        raise MonthlyRevenueRevisionArchiveError("archive_index_schema_invalid")
    if decoded["schema_version"] != MONTHLY_REVENUE_REVISION_ARCHIVE_SCHEMA_V1:
        raise MonthlyRevenueRevisionArchiveError("archive_index_schema_unsupported")
    batches_raw = decoded["batches"]
    if type(batches_raw) is not list or not 1 <= len(batches_raw) <= MONTHLY_REVENUE_ARCHIVE_MAX_BATCHES:
        raise MonthlyRevenueRevisionArchiveError("archive_batch_count_invalid")
    batches: list[Mapping[str, object]] = []
    total_rows = 0
    total_bytes = 0
    for entry in batches_raw:
        _validate_batch_entry(entry)
        raw_hash = str(entry["raw_source_sha256"])
        blob = _read_regular_file(
            base / "raw" / "sha256" / f"{raw_hash}.bin",
            MONTHLY_REVENUE_ARCHIVE_MAX_RAW_BYTES,
        )
        if hashlib.sha256(blob).hexdigest() != raw_hash:
            raise MonthlyRevenueRevisionArchiveError("archive_raw_hash_mismatch")
        if len(blob) != entry["raw_byte_count"]:
            raise MonthlyRevenueRevisionArchiveError("archive_raw_byte_count_mismatch")
        _reparse_and_verify(entry, blob)
        total_rows += len(entry["rows"])
        total_bytes += len(blob)
        batches.append(entry)
    if total_rows > MONTHLY_REVENUE_ARCHIVE_MAX_ROWS:
        raise MonthlyRevenueRevisionArchiveError("archive_row_count_exceeds_limit")
    if total_bytes > MONTHLY_REVENUE_ARCHIVE_MAX_RAW_BYTES:
        raise MonthlyRevenueRevisionArchiveError("archive_raw_bytes_exceed_limit")
    _validate_parent_references(batches)
    parent_hash = decoded["parent_archive_sha256"]
    if parent_hash is not None:
        _require_sha256(parent_hash, "parent_archive_sha256")
    return MonthlyRevenueRevisionArchiveV1(
        root=base,
        archive_sha256=selected,
        parent_archive_sha256=parent_hash,
        batches=tuple(batches),
    )


def select_monthly_revenue_observation_as_of(
    archive: MonthlyRevenueRevisionArchiveV1,
    *,
    market: str,
    stock_code: str,
    period: str,
    cutoff_at: datetime,
) -> MonthlyRevenueAsOfResult:
    """選 cutoff 前實際保存批次中唯一最新的列；不同內容同時鐘時拒絕。"""

    if type(archive) is not MonthlyRevenueRevisionArchiveV1:
        raise MonthlyRevenueRevisionArchiveError("archive_type_invalid")
    verified_archive = read_monthly_revenue_revision_archive(
        archive.root,
        archive.archive_sha256,
        expected_archive_sha256=archive.archive_sha256,
    )
    if (
        archive.parent_archive_sha256 != verified_archive.parent_archive_sha256
        or archive.batches != verified_archive.batches
    ):
        raise MonthlyRevenueRevisionArchiveError("archive_object_identity_mismatch")
    archive = verified_archive
    if market not in _MARKETS:
        raise MonthlyRevenueRevisionArchiveError("selection_market_invalid")
    _validate_stock_code(stock_code)
    _validate_period(period)
    cutoff = _aware_taipei(cutoff_at, "cutoff_at")
    candidates: list[MonthlyRevenueArchivedObservationV1] = []
    for batch in archive.batches:
        if (
            batch["market"] != market
            or batch["period"] != period
            or not _to_datetime(str(batch["available_at"])) <= cutoff
        ):
            continue
        parent_by_stock = {item[0]: item[3] for item in _batch_parent_refs(batch)}
        for row in _batch_rows(batch):
            if row["stock_code"] != stock_code:
                continue
            source_values = _row_source_values(row)
            source_unit_text = row["source_unit_text"]
            unit_proof_sha256 = row["unit_proof_sha256"]
            official_announcement_at = batch["official_announcement_at"]
            if source_unit_text is not None and type(source_unit_text) is not str:
                raise MonthlyRevenueRevisionArchiveError("archive_row_source_unit_invalid")
            if unit_proof_sha256 is not None and type(unit_proof_sha256) is not str:
                raise MonthlyRevenueRevisionArchiveError("archive_row_unit_proof_invalid")
            if official_announcement_at is not None and type(official_announcement_at) is not str:
                raise MonthlyRevenueRevisionArchiveError("archive_official_clock_invalid")
            candidates.append(
                MonthlyRevenueArchivedObservationV1(
                    market=market,
                    stock_code=stock_code,
                    period=period,
                    source_id=str(batch["source_id"]),
                    source_version=str(batch["source_version"]),
                    revision_id=str(row["revision_id"]),
                    parent_revision_id=parent_by_stock.get(stock_code),
                    row_sha256=str(row["row_sha256"]),
                    raw_source_sha256=str(batch["raw_source_sha256"]),
                    captured_at=_to_datetime(str(batch["captured_at"])),
                    captured_batch_available_at=_to_datetime(
                        str(batch["captured_batch_available_at"])
                    ),
                    archive_persisted_at=_to_datetime(
                        str(batch["archive_persisted_at"])
                    ),
                    available_at=_to_datetime(str(batch["available_at"])),
                    availability_basis=str(batch["availability_basis"]),
                    source_values=tuple(sorted(source_values.items())),
                    source_unit_text=source_unit_text,
                    unit_status=str(row["unit_status"]),
                    unit_proof_sha256=unit_proof_sha256,
                    official_announcement_at=(
                        _to_datetime(official_announcement_at)
                        if official_announcement_at is not None
                        else None
                    ),
                    official_revision_id=(
                        batch["official_revision_id"]
                        if type(batch["official_revision_id"]) is str
                        else None
                    ),
                    archive_sha256=archive.archive_sha256,
                )
            )
    if not candidates:
        return MonthlyRevenueAsOfResult(None, False, False, "not_visible_by_cutoff")
    latest_at = max(item.available_at for item in candidates)
    latest = tuple(item for item in candidates if item.available_at == latest_at)
    content_hashes = {item.row_sha256 for item in latest}
    if len(content_hashes) > 1:
        return MonthlyRevenueAsOfResult(
            None,
            False,
            False,
            "ambiguous_same_time_content",
            ("same_market_period_code_and_available_at_have_different_row_hashes",),
        )
    unique_by_source = {item.revision_id: item for item in latest}
    if len(unique_by_source) > 1:
        return MonthlyRevenueAsOfResult(
            None,
            False,
            False,
            "ambiguous_same_time_revisions",
            ("distinct_revision_id_same_available_at",),
        )
    selected = next(iter(unique_by_source.values()))
    return MonthlyRevenueAsOfResult(
        selected,
        True,
        False,
        "observed_as_of",
        ("official_pit_provenance_not_established",),
    )


def _row_entry(
    batch: MonthlyRevenueRawBatchEvidenceV1,
    row: MonthlyRevenueRawRowV1,
) -> dict[str, object]:
    revision_id = hashlib.sha256(
        _canonical_json_bytes(
            {
                "market": batch.market,
                "stock_code": row.stock_code,
                "period": row.period,
                "source_id": batch.source_id,
                "source_version": batch.source_version,
                "row_sha256": row.row_sha256,
                "raw_source_sha256": batch.raw_source_sha256,
            }
        )
    ).hexdigest()
    parents = tuple(
        item for item in batch.parent_revision_ids if item[0] == row.stock_code
    )
    if len(parents) > 1:
        raise MonthlyRevenueRevisionArchiveError("row_parent_revision_ambiguous")
    return {
        **row.to_dict(),
        "revision_id": revision_id,
        "parent_revision_id": parents[0][3] if parents else None,
    }


def _transport_provenance_value(value: object) -> str | int | bool | None:
    if value is None:
        return value
    if type(value) is str:
        return value
    if type(value) is int:
        return value
    if type(value) is bool:
        return value
    return None


def _copy_validated_archive_batch(
    value: Mapping[str, object],
) -> dict[str, object]:
    entry = dict(value)
    _ = _batch_rows(entry)
    _ = _archive_batch_raw_byte_count(entry)
    return entry


def _archive_batch_raw_byte_count(batch: Mapping[str, object]) -> int:
    value = batch.get("raw_byte_count")
    if type(value) is not int or value <= 0:
        raise MonthlyRevenueRevisionArchiveError(
            "archive_raw_byte_count_invalid"
        )
    return value


def _validate_batch_entry(value: object) -> None:
    fields = {
        "schema_version", "market", "source_id", "source_version", "period",
        "parser_version", "raw_source_sha256", "captured_at", "captured_batch_available_at",
        "archive_persisted_at", "available_at",
        "availability_basis", "transport_provenance", "official_announcement_at",
        "official_revision_id", "parent_revision_ids", "rows", "raw_byte_count",
    }
    if type(value) is not dict or set(value) != fields:
        raise MonthlyRevenueRevisionArchiveError("archive_batch_entry_schema_invalid")
    if value["schema_version"] != MONTHLY_REVENUE_RAW_BATCH_SCHEMA_V1:
        raise MonthlyRevenueRevisionArchiveError("archive_batch_entry_schema_unsupported")
    if value["market"] not in _MARKETS:
        raise MonthlyRevenueRevisionArchiveError("archive_batch_market_invalid")
    for key in ("source_id", "source_version", "parser_version", "availability_basis"):
        _require_nonempty(value[key], key)
    _validate_period(value["period"])
    raw_hash = _require_sha256(value["raw_source_sha256"], "raw_source_sha256")
    captured = _to_datetime(value["captured_at"])
    source_available = _to_datetime(value["captured_batch_available_at"])
    persisted = _to_datetime(value["archive_persisted_at"])
    available = _to_datetime(value["available_at"])
    if source_available < captured:
        raise MonthlyRevenueRevisionArchiveError("archive_source_available_before_capture")
    if available != max(source_available, _ceil_hour(persisted)):
        raise MonthlyRevenueRevisionArchiveError("archive_effective_availability_mismatch")
    if type(value["raw_byte_count"]) is not int or value["raw_byte_count"] <= 0:
        raise MonthlyRevenueRevisionArchiveError("archive_raw_byte_count_invalid")
    if type(value["rows"]) is not list or not value["rows"]:
        raise MonthlyRevenueRevisionArchiveError("archive_batch_rows_invalid")
    if type(value["parent_revision_ids"]) is not list:
        raise MonthlyRevenueRevisionArchiveError("archive_parent_revisions_invalid")
    parent_stocks: set[str] = set()
    for reference in _batch_parent_refs(value):
        if type(reference) is not tuple or len(reference) != 4:
            raise MonthlyRevenueRevisionArchiveError("archive_parent_revision_reference_invalid")
        parent_stock, parent_period, parent_row_hash, parent_revision_id = reference
        _validate_stock_code(parent_stock)
        _validate_period(parent_period)
        if parent_period != value["period"] or parent_stock in parent_stocks:
            raise MonthlyRevenueRevisionArchiveError("archive_parent_revision_scope_invalid")
        _require_sha256(parent_row_hash, "archive_parent_row_sha256")
        _require_sha256(parent_revision_id, "archive_parent_revision_id")
        parent_stocks.add(parent_stock)
    if type(value["transport_provenance"]) is not dict:
        raise MonthlyRevenueRevisionArchiveError("archive_transport_provenance_invalid")
    _ = raw_hash
    for row in _batch_rows(value):
        _validate_row_entry(row, value)


def _validate_row_entry(row: object, batch: Mapping[str, object]) -> None:
    fields = {
        "stock_code", "period", "source_values", "source_unit_text", "unit_status",
        "unit_proof_sha256", "row_sha256", "revision_id", "parent_revision_id",
    }
    if type(row) is not dict or set(row) != fields:
        raise MonthlyRevenueRevisionArchiveError("archive_row_schema_invalid")
    _validate_stock_code(row["stock_code"])
    _validate_period(row["period"])
    if row["period"] != batch["period"]:
        raise MonthlyRevenueRevisionArchiveError("archive_row_period_mismatch")
    values = _row_source_values(row)
    row_dto = MonthlyRevenueRawRowV1.build(
        stock_code=row["stock_code"],
        period=row["period"],
        source_values=values,
        source_unit_text=row["source_unit_text"],
        unit_status=row["unit_status"],
        unit_proof_sha256=row["unit_proof_sha256"],
    )
    if row["row_sha256"] != row_dto.row_sha256:
        raise MonthlyRevenueRevisionArchiveError("archive_row_hash_mismatch")
    _require_sha256(row["revision_id"], "revision_id")
    if row["parent_revision_id"] is not None:
        _require_sha256(row["parent_revision_id"], "parent_revision_id")


def _validate_parent_references(batches: Sequence[Mapping[str, object]]) -> None:
    revisions: dict[str, tuple[str, str, str, str, str, datetime]] = {}
    parent_by_revision: dict[str, str] = {}
    for batch in batches:
        market = str(batch["market"])
        source_id = str(batch["source_id"])
        available = _to_datetime(str(batch["available_at"]))
        for row in _batch_rows(batch):
            revision_id = str(row["revision_id"])
            identity = (
                market,
                str(row["stock_code"]),
                str(row["period"]),
                source_id,
                str(row["row_sha256"]),
                available,
            )
            if revision_id in revisions:
                raise MonthlyRevenueRevisionArchiveError("archive_revision_id_duplicate")
            revisions[revision_id] = identity
            parent_id = row["parent_revision_id"]
            if parent_id is not None:
                parent_by_revision[revision_id] = str(parent_id)
    for batch in batches:
        market = str(batch["market"])
        source_id = str(batch["source_id"])
        available = _to_datetime(str(batch["available_at"]))
        for row in _batch_rows(batch):
            parent_id = row["parent_revision_id"]
            if parent_id is None:
                continue
            parent = revisions.get(str(parent_id))
            if parent is None:
                raise MonthlyRevenueRevisionArchiveError("archive_parent_revision_missing")
            expected = (market, str(row["stock_code"]), str(row["period"]), source_id)
            if parent[:4] != expected:
                raise MonthlyRevenueRevisionArchiveError("archive_parent_natural_key_mismatch")
            parent_refs = tuple(
                reference
                for reference in _batch_parent_refs(batch)
                if reference[0] == row["stock_code"]
                and reference[1] == row["period"]
                and reference[3] == parent_id
            )
            if len(parent_refs) != 1 or parent_refs[0][2] != parent[4]:
                raise MonthlyRevenueRevisionArchiveError("archive_parent_row_hash_mismatch")
            if parent[5] > available:
                raise MonthlyRevenueRevisionArchiveError("archive_parent_after_child")
    for revision_id in parent_by_revision:
        seen: set[str] = set()
        current = revision_id
        while current in parent_by_revision:
            if current in seen:
                raise MonthlyRevenueRevisionArchiveError("archive_parent_revision_cycle")
            seen.add(current)
            current = parent_by_revision[current]


def _batch_rows(batch: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    raw_rows = batch.get("rows")
    if type(raw_rows) is not list:
        raise MonthlyRevenueRevisionArchiveError("archive_batch_rows_invalid")
    rows: list[dict[str, object]] = []
    for raw_row in raw_rows:
        if type(raw_row) is not dict or any(type(key) is not str for key in raw_row):
            raise MonthlyRevenueRevisionArchiveError("archive_row_schema_invalid")
        rows.append(raw_row)
    return tuple(rows)


def _batch_parent_refs(
    batch: Mapping[str, object],
) -> tuple[tuple[str, str, str, str], ...]:
    raw_refs = batch.get("parent_revision_ids")
    if type(raw_refs) is not list:
        raise MonthlyRevenueRevisionArchiveError("archive_parent_revisions_invalid")
    references: list[tuple[str, str, str, str]] = []
    for raw in raw_refs:
        if (
            type(raw) is not list
            or len(raw) != 4
            or any(type(item) is not str for item in raw)
        ):
            raise MonthlyRevenueRevisionArchiveError("archive_parent_revision_reference_invalid")
        references.append((raw[0], raw[1], raw[2], raw[3]))
    return tuple(references)


def _row_source_values(row: Mapping[str, object]) -> dict[str, str]:
    values = row.get("source_values")
    if (
        type(values) is not dict
        or not values
        or any(
            type(key) is not str or not key or type(value) is not str
            for key, value in values.items()
        )
    ):
        raise MonthlyRevenueRevisionArchiveError("archive_row_source_values_invalid")
    result: dict[str, str] = {}
    for key, value in values.items():
        if type(key) is not str or not key or type(value) is not str:
            raise MonthlyRevenueRevisionArchiveError("archive_row_source_values_invalid")
        result[key] = value
    return result


def _reparse_and_verify(entry: Mapping[str, object], raw_bytes: bytes) -> None:
    provenance = entry["transport_provenance"]
    if type(provenance) is not dict:
        raise MonthlyRevenueRevisionArchiveError("archive_transport_provenance_invalid")
    if entry["parser_version"] == MOPS_MONTHLY_REVENUE_HISTORY_PARSER_VERSION:
        _reparse_mops_and_verify(entry, provenance, raw_bytes)
        return
    if entry["parser_version"] != OPENAPI_MONTHLY_REVENUE_PARSER_VERSION:
        raise MonthlyRevenueRevisionArchiveError(
            f"archive_parser_not_supported:{entry['parser_version']}"
        )
    required = {
        "market", "requested_url", "response_url", "response_status",
        "content_type_original_text", "content_encoding_original_text",
        "content_length_original_text", "response_body_complete", "eof_observed",
        "received_body_bytes", "raw_response_sha256", "body_observation_ended_at",
        "body_completed_at",
    }
    if not required.issubset(provenance):
        raise MonthlyRevenueRevisionArchiveError("archive_openapi_transport_fields_missing")
    capture = OpenApiMonthlyRevenueCapture(
        market=provenance["market"],
        requested_url=provenance["requested_url"],
        response_url=provenance["response_url"],
        response_status=int(provenance["response_status"]),
        content_type_original_text=provenance["content_type_original_text"],
        content_encoding_original_text=provenance["content_encoding_original_text"],
        content_length_original_text=provenance["content_length_original_text"],
        response_body_complete=provenance["response_body_complete"],
        eof_observed=provenance["eof_observed"],
        received_body_bytes=int(provenance["received_body_bytes"]),
        body_observation_ended_at=_to_datetime(provenance["body_observation_ended_at"]),
        body_completed_at=_to_datetime(provenance["body_completed_at"]),
        raw_response_bytes=raw_bytes,
    )
    if capture.raw_response_sha256 != entry["raw_source_sha256"]:
        raise MonthlyRevenueRevisionArchiveError("archive_openapi_capture_hash_mismatch")
    try:
        batch = prepare_openapi_monthly_revenue_batch(
            capture=capture,
            successful_batch_completed_at=_to_datetime(entry["captured_at"]),
        )
    except (OpenApiMonthlyRevenueError, TypeError, ValueError) as exc:
        raise MonthlyRevenueRevisionArchiveError("archive_openapi_reparse_failed") from exc
    if batch.period != entry["period"] or batch.rows[0].source_version != entry["source_version"]:
        raise MonthlyRevenueRevisionArchiveError("archive_openapi_batch_identity_mismatch")
    if (
        _datetime_text(batch.successful_batch_completed_at) != entry["captured_at"]
        or _datetime_text(batch.available_hour) != entry["captured_batch_available_at"]
        or entry["availability_basis"] != "captured_complete_batch_available_hour"
        or entry["official_announcement_at"] is not None
        or entry["official_revision_id"] is not None
    ):
        raise MonthlyRevenueRevisionArchiveError("archive_openapi_clock_or_provenance_mismatch")
    reparsed = raw_batch_from_openapi(batch)
    archived_rows = _batch_rows(entry)
    archived_rows_by_stock = {row["stock_code"]: row for row in archived_rows}
    if len(archived_rows_by_stock) != len(archived_rows):
        raise MonthlyRevenueRevisionArchiveError("archive_openapi_row_identity_ambiguous")
    archived_rows = _batch_rows(entry)
    expected_rows = [
        {
            **row.to_dict(),
            "revision_id": _revision_id(
                market=batch.capture.market,
                stock_code=row.stock_code,
                period=row.period,
                source_id=batch.capture.source_id,
                source_version=batch.rows[0].source_version,
                row_sha256=row.row_sha256,
                raw_source_sha256=batch.capture.raw_response_sha256,
            ),
            "parent_revision_id": archived_rows_by_stock[row.stock_code][
                "parent_revision_id"
            ],
        }
        for row in reparsed.rows
    ]
    if expected_rows != entry["rows"]:
        raise MonthlyRevenueRevisionArchiveError("archive_openapi_rows_mismatch")


def _reparse_mops_and_verify(
    entry: Mapping[str, object],
    provenance: Mapping[str, object],
    raw_bytes: bytes,
) -> None:
    market = _mops_market_from_archive_value(entry.get("market"))
    period = entry.get("period")
    if type(period) is not str:
        raise MonthlyRevenueRevisionArchiveError("archive_mops_period_invalid")
    request_started_at = provenance.get("request_started_at")
    requested_url = provenance.get("requested_url")
    response_url = provenance.get("response_url")
    transport_json = provenance.get("transport_capture_json")
    if (
        type(request_started_at) is not str
        or type(requested_url) is not str
        or type(response_url) is not str
        or type(transport_json) is not str
    ):
        raise MonthlyRevenueRevisionArchiveError("archive_mops_transport_fields_missing")
    try:
        transport_value = json.loads(transport_json, object_pairs_hook=_reject_duplicate_pairs)
    except (json.JSONDecodeError, MonthlyRevenueRevisionArchiveError) as exc:
        raise MonthlyRevenueRevisionArchiveError("archive_mops_transport_json_invalid") from exc
    if type(transport_value) is not dict:
        raise MonthlyRevenueRevisionArchiveError("archive_mops_transport_json_invalid")
    if _canonical_json_bytes(transport_value).decode("utf-8") != transport_json:
        raise MonthlyRevenueRevisionArchiveError("archive_mops_transport_json_not_canonical")
    transport_data = dict(transport_value)
    if "raw_response_bytes_base64" in transport_data:
        raise MonthlyRevenueRevisionArchiveError("archive_mops_raw_bytes_must_be_external_blob")
    import base64

    transport_data["raw_response_bytes_base64"] = base64.b64encode(raw_bytes).decode("ascii")
    transport_mode = provenance.get("transport_mode", "direct_static_v1")
    if type(transport_mode) is not str:
        raise MonthlyRevenueRevisionArchiveError("archive_mops_transport_mode_invalid")
    raw_chain_json = provenance.get("transport_chain_json")
    transport_hop_values: tuple[object, ...] = ()
    if transport_mode == "redirect_chain_v1":
        if type(raw_chain_json) is not str:
            raise MonthlyRevenueRevisionArchiveError("archive_mops_transport_chain_missing")
        try:
            chain_value = json.loads(
                raw_chain_json,
                object_pairs_hook=_reject_duplicate_pairs,
            )
        except (json.JSONDecodeError, MonthlyRevenueRevisionArchiveError) as exc:
            raise MonthlyRevenueRevisionArchiveError(
                "archive_mops_transport_chain_invalid"
            ) from exc
        if (
            type(chain_value) is not list
            or _canonical_json_bytes(chain_value).decode("utf-8") != raw_chain_json
        ):
            raise MonthlyRevenueRevisionArchiveError(
                "archive_mops_transport_chain_not_canonical"
            )
        transport_hop_values = tuple(chain_value)
        if len(transport_hop_values) != 3:
            raise MonthlyRevenueRevisionArchiveError(
                "archive_mops_transport_chain_hop_count_invalid"
            )
    elif transport_mode != "direct_static_v1" or raw_chain_json is not None:
        raise MonthlyRevenueRevisionArchiveError("archive_mops_transport_mode_invalid")
    try:
        transport = _transport_capture_from_dict(transport_data)
        if transport_mode == "redirect_chain_v1":
            capture = rebuild_mops_monthly_revenue_history_capture_from_transport_chain(
                market=market,
                period=period,
                transport_mode=transport_mode,
                transport_hops=transport_hop_values,
                final_transport_capture=transport,
            )
            if (
                capture.requested_url != requested_url
                or capture.response_url != response_url
                or _datetime_text(capture.request_started_at)
                != _datetime_text(_to_datetime(request_started_at))
            ):
                raise MopsMonthlyRevenueHistoryError(
                    "redirect_chain_top_level_fields_mismatch"
                )
        else:
            capture = MopsMonthlyRevenueHistoricalCapture(
                market=market,
                period=period,
                requested_url=requested_url,
                response_url=response_url,
                request_started_at=_to_datetime(request_started_at),
                transport_capture=transport,
                transport_mode=transport_mode,
                transport_hops=(),
            )
        rows = parse_mops_monthly_revenue_history_capture(capture)
        rebuilt = capture.to_monthly_revenue_raw_batch_evidence()
    except (MopsMonthlyRevenueHistoryError, TypeError, ValueError) as exc:
        raise MonthlyRevenueRevisionArchiveError("archive_mops_reparse_failed") from exc
    if (
        capture.source_id != entry["source_id"]
        or capture.source_version != entry["source_version"]
        or capture.period != entry["period"]
        or capture.raw_response_sha256 != entry["raw_source_sha256"]
        or _datetime_text(capture.transport_capture.body_completed_at)
        != entry["captured_at"]
        or entry["captured_batch_available_at"] != entry["captured_at"]
        or entry["availability_basis"] != "retrospective_capture_observation"
        or entry["official_announcement_at"] is not None
        or entry["official_revision_id"] is not None
    ):
        raise MonthlyRevenueRevisionArchiveError("archive_mops_batch_identity_mismatch")
    if tuple(sorted(rebuilt.transport_provenance)) != tuple(
        sorted((key, value) for key, value in provenance.items())
    ):
        raise MonthlyRevenueRevisionArchiveError("archive_mops_transport_provenance_mismatch")
    archived_rows = _batch_rows(entry)
    expected_rows = tuple(
        {
            **row.to_dict(),
            "revision_id": _revision_id(
                market=rebuilt.market,
                stock_code=row.stock_code,
                period=row.period,
                source_id=rebuilt.source_id,
                source_version=rebuilt.source_version,
                row_sha256=row.row_sha256,
                raw_source_sha256=rebuilt.raw_source_sha256,
            ),
            "parent_revision_id": row_entry["parent_revision_id"],
        }
        for row, row_entry in zip(rebuilt.rows, archived_rows, strict=True)
    )
    if expected_rows != archived_rows or len(rows) != len(rebuilt.rows):
        raise MonthlyRevenueRevisionArchiveError("archive_mops_rows_mismatch")


def _mops_market_from_archive_value(value: object) -> MopsHistoryMarket:
    if type(value) is str and value == "twse":
        return "twse"
    if type(value) is str and value == "tpex":
        return "tpex"
    raise MonthlyRevenueRevisionArchiveError("archive_mops_market_invalid")


def _revision_id(
    *, market: str, stock_code: str, period: str, source_id: str,
    source_version: str, row_sha256: str, raw_source_sha256: str,
) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "market": market,
                "stock_code": stock_code,
                "period": period,
                "source_id": source_id,
                "source_version": source_version,
                "row_sha256": row_sha256,
                "raw_source_sha256": raw_source_sha256,
            }
        )
    ).hexdigest()


def _write_content_addressed(path: Path, payload: bytes, digest: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = _read_regular_file(path, MONTHLY_REVENUE_ARCHIVE_MAX_RAW_BYTES)
        if existing != payload or hashlib.sha256(existing).hexdigest() != digest:
            raise MonthlyRevenueRevisionArchiveError("archive_blob_create_only_conflict")
        return
    _write_create_only(path, payload)


def _write_create_only(path: Path, payload: bytes) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        existing = _read_regular_file(path, MONTHLY_REVENUE_ARCHIVE_MAX_INDEX_BYTES)
        if existing != payload:
            raise MonthlyRevenueRevisionArchiveError("archive_create_only_conflict")
        return
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            if handle.write(payload) != len(payload):
                raise MonthlyRevenueRevisionArchiveError("archive_short_write")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_regular_file(path: Path, max_bytes: int) -> bytes:
    try:
        if path.is_symlink():
            raise MonthlyRevenueRevisionArchiveError("archive_path_is_symlink")
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise MonthlyRevenueRevisionArchiveError("archive_file_type_or_size_invalid")
        payload = path.read_bytes()
    except MonthlyRevenueRevisionArchiveError:
        raise
    except OSError as exc:
        raise MonthlyRevenueRevisionArchiveError("archive_file_unreadable") from exc
    if len(payload) > max_bytes:
        raise MonthlyRevenueRevisionArchiveError("archive_file_exceeds_limit")
    return payload


def _ensure_directory(root: Path, directory: Path) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        resolved = directory.resolve(strict=True)
        if directory.is_symlink() or not resolved.is_relative_to(root):
            raise MonthlyRevenueRevisionArchiveError("archive_directory_escape")
    except MonthlyRevenueRevisionArchiveError:
        raise
    except OSError as exc:
        raise MonthlyRevenueRevisionArchiveError("archive_directory_unavailable") from exc


def _checked_root(root: Path | str, *, create: bool) -> Path:
    path = Path(root)
    if not path.is_absolute() or path.is_symlink():
        raise MonthlyRevenueRevisionArchiveError("archive_root_must_be_absolute_nonsymlink")
    try:
        if create:
            path.mkdir(parents=True, exist_ok=True)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise MonthlyRevenueRevisionArchiveError("archive_root_unavailable") from exc
    if path.is_symlink() or not resolved.is_dir():
        raise MonthlyRevenueRevisionArchiveError("archive_root_invalid")
    return resolved


def _row_sha256(
    *, stock_code: str, period: str, source_values: Sequence[tuple[str, str]],
    source_unit_text: str | None, unit_status: str, unit_proof_sha256: str | None,
) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "stock_code": stock_code,
                "period": period,
                "source_values": {key: value for key, value in source_values},
                "source_unit_text": source_unit_text,
                "unit_status": unit_status,
                "unit_proof_sha256": unit_proof_sha256,
            }
        )
    ).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MonthlyRevenueRevisionArchiveError("archive_value_not_canonical_json") from exc


def _decode_canonical_json(payload: bytes) -> object:
    try:
        text = payload.decode("utf-8", errors="strict")
        decoded = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MonthlyRevenueRevisionArchiveError("archive_json_invalid") from exc
    if _canonical_json_bytes(decoded) != payload:
        raise MonthlyRevenueRevisionArchiveError("archive_json_not_canonical")
    return decoded


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MonthlyRevenueRevisionArchiveError("archive_json_duplicate_key")
        result[key] = value
    return result


def _aware_taipei(value: datetime, field: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise MonthlyRevenueRevisionArchiveError(f"{field}_must_be_aware")
    return value.astimezone(_TAIPEI)


def _utc_now() -> datetime:
    """回傳真實 UTC 持久化時鐘；測試只可替換此私有時鐘。"""

    return datetime.now(timezone.utc)


def _aware_utc(value: datetime, field: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise MonthlyRevenueRevisionArchiveError(f"{field}_must_be_aware")
    return value.astimezone(timezone.utc)


def _utc_datetime_text(value: datetime) -> str:
    return _aware_utc(value, "archive_persisted_at").isoformat(timespec="microseconds")


def _ceil_hour(value: datetime) -> datetime:
    local = _aware_taipei(value, "hour_clock")
    current_hour = local.replace(minute=0, second=0, microsecond=0)
    if current_hour == local:
        return current_hour
    from datetime import timedelta

    return current_hour + timedelta(hours=1)


def _datetime_text(value: datetime) -> str:
    return _aware_taipei(value, "datetime").isoformat(timespec="microseconds")


def _to_datetime(value: object) -> datetime:
    if type(value) is not str:
        raise MonthlyRevenueRevisionArchiveError("archive_datetime_invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MonthlyRevenueRevisionArchiveError("archive_datetime_invalid") from exc
    return _aware_taipei(parsed, "archive_datetime")


def _require_sha256(value: object, field: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise MonthlyRevenueRevisionArchiveError(f"{field}_invalid")
    return value


def _require_nonempty(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise MonthlyRevenueRevisionArchiveError(f"{field}_missing")
    return value


def _validate_stock_code(value: object) -> str:
    if type(value) is not str or not re.fullmatch(r"[0-9]{4,6}", value):
        raise MonthlyRevenueRevisionArchiveError("stock_code_invalid")
    return value


def _validate_period(value: object) -> str:
    if type(value) is not str or _PERIOD_RE.fullmatch(value) is None:
        raise MonthlyRevenueRevisionArchiveError("period_invalid")
    return value


__all__ = [
    "MONTHLY_REVENUE_ARCHIVE_MAX_BATCHES",
    "MONTHLY_REVENUE_ARCHIVE_MAX_RAW_BYTES",
    "MONTHLY_REVENUE_REVISION_ARCHIVE_SCHEMA_V1",
    "MonthlyRevenueArchiveAppendResult",
    "MonthlyRevenueArchivedObservationV1",
    "MonthlyRevenueAsOfResult",
    "MonthlyRevenueRawBatchEvidenceV1",
    "MonthlyRevenueRawRowV1",
    "MonthlyRevenueRevisionArchiveError",
    "MonthlyRevenueRevisionArchiveV1",
    "append_monthly_revenue_batch",
    "read_monthly_revenue_revision_archive",
    "raw_batch_from_openapi",
    "select_monthly_revenue_observation_as_of",
]
