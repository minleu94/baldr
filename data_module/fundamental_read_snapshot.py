"""隔離基本面 SQLite 來源後，才在研究副本上建立唯讀 cohort。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import struct
import sys
from threading import Event, Lock, get_ident
from typing import TYPE_CHECKING, Callable, Literal, Sequence, cast
from uuid import uuid4

from data_module.config import TWStockConfig
from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortReader
from app_module.personal_data_paths import to_internal_io_path

from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)
from data_module.fundamental_read_copy_contract import (
    FundamentalReadArchivedCopyBinding,
    FundamentalReadArchivedFilePinPair,
    FundamentalReadCopyBinding,
    FundamentalReadCopyBindingCancelled,
    FundamentalReadCopyBindingError,
    FundamentalReadCopyFilePin,
    FundamentalReadCopyFileReference,
    _ARCHIVED_BINDING_ISSUER,
    _issue_archived_copy_binding,
)
from data_module.selection_fact_readers import (
    FinishedFundamentalReadCohort,
    FinishedFundamentalReadCohortV2,
    FundamentalFilePin,
    FundamentalReadBatchCandidate,
    FundamentalReadSessionCancelled,
    FundamentalReadSessionError,
    FundamentalSourceClock,
    SelectionFundamentalReadSession,
)

if TYPE_CHECKING:
    from data_module.fundamental_read_snapshot_cohort_v2 import (
        FinishedFundamentalSnapshotReadCohortV2, FundamentalSnapshotSourceClockV2,
    )
    from data_module.fundamental_read_snapshot_daily_v2 import _VerifiedSnapshotReferenceV2
    from data_module.fundamental_read_snapshot_raw_archive_io_v2 import _VerifiedArchivedSnapshotReferenceV2
    from data_module.fundamental_read_archived_copy_contract_v2 import FundamentalReadArchivedCopyBindingV2


FUNDAMENTAL_READ_SNAPSHOT_SCHEMA: Literal["selection-fundamental-read-snapshot.v1"] = (
    "selection-fundamental-read-snapshot.v1"
)
FUNDAMENTAL_SNAPSHOT_SOURCE_CLOCK_SCHEMA: Literal[
    "selection-fundamental-source-clock.snapshot.v1"
] = "selection-fundamental-source-clock.snapshot.v1"
MAX_SNAPSHOT_SOURCE_FILE_BYTES = 16 * 1024 * 1024 * 1024
SNAPSHOT_COPY_CHUNK_BYTES = 1024 * 1024
MAX_SNAPSHOT_CAPTURE_MANIFEST_BYTES = 256 * 1024
MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES = 32 * 1024 * 1024
MAX_SNAPSHOT_REFERENCE_JSON_BYTES = 8 * 1024 * 1024
MAX_RAW_ARCHIVE_REFERENCE_JSON_BYTES = 64 * 1024 * 1024
MAX_RAW_ARCHIVE_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_RAW_ARCHIVE_TOTAL_BYTES = 64 * 1024 * 1024 * 1024
MAX_RAW_ARCHIVE_FILES = 100_000
MAX_RAW_ARCHIVE_FILE_BYTES = 32 * 1024 * 1024
_SQLITE_HEADER = b"SQLite format 3\x00"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SQLITE_WAL_MAGIC = {0x377F0682, 0x377F0683}
_SQLITE_WAL_VERSION = 3_007_000
_WINDOWS_REPARSE_POINT = 0x400


class FundamentalReadSnapshotError(FundamentalReadSessionError):
    """來源無法安全複製或在隔離 SQLite 副本上驗證。"""


class FundamentalReadSnapshotCancelled(FundamentalReadSessionCancelled):
    """在 snapshot copy 或來源起訖比對前取消。"""


FundamentalReadSnapshotFileReference = FundamentalReadCopyFileReference


@dataclass(frozen=True, slots=True)
class FundamentalReadSnapshotBinding:
    """完成來源 session 後保存原始來源與隔離 reader 副本的關係。"""

    snapshot_id: str
    snapshot_root: str
    source_database_path: str
    reader_database_path: str
    source_file_pins_start: tuple[FundamentalFilePin, ...]
    source_file_pins_after_copy: tuple[FundamentalFilePin, ...]
    source_file_pins_finish: tuple[FundamentalFilePin, ...]
    captured_files: tuple[FundamentalReadSnapshotFileReference, ...]
    captured_file_pins_start: tuple[FundamentalFilePin, ...]
    captured_file_pins_finish: tuple[FundamentalFilePin, ...]
    capture_manifest_pin_start: FundamentalFilePin
    capture_manifest_pin_finish: FundamentalFilePin
    reader_files: tuple[FundamentalReadSnapshotFileReference, ...]
    reader_file_pins_finish: tuple[FundamentalFilePin, ...]
    sqlite_journal_mode: Literal["rollback", "wal"]
    wal_sidecar_state: Literal["complete", "absent", "not_applicable"]
    source_snapshot_sha256: str
    source_copy_bytes: int
    reader_only_sidecar_bytes: int
    duplicated_disk_bytes: int
    schema_version: Literal["selection-fundamental-read-snapshot.v1"] = (
        FUNDAMENTAL_READ_SNAPSHOT_SCHEMA
    )

    def __post_init__(self) -> None:
        if not re.fullmatch(r"^[0-9a-f]{32}$", self.snapshot_id):
            raise ValueError("snapshot_id 格式錯誤")
        for name in ("snapshot_root", "source_database_path", "reader_database_path"):
            value = getattr(self, name)
            if type(value) is not str or not Path(value).is_absolute():
                raise ValueError(f"{name} 必須是絕對路徑")
        if self.schema_version != FUNDAMENTAL_READ_SNAPSHOT_SCHEMA:
            raise ValueError("snapshot schema version 不支援")
        if self.source_file_pins_start != self.source_file_pins_after_copy:
            raise ValueError("snapshot copy 前後來源檔 pins 不一致")
        if self.source_file_pins_start != self.source_file_pins_finish:
            raise ValueError("source session 起訖來源檔 pins 不一致")
        if not self.source_file_pins_start:
            raise ValueError("snapshot 必須保留來源檔 pins")
        if not self.captured_files or not self.reader_files or not self.reader_file_pins_finish:
            raise ValueError("snapshot 必須同時保留 captured 與 reader copy refs")
        if self.captured_file_pins_start != self.captured_file_pins_finish:
            raise ValueError("captured file 起訖 pins 不一致")
        if len(self.captured_file_pins_start) != len(self.captured_files):
            raise ValueError("captured file refs 與 stat pins 數量不一致")
        if self.capture_manifest_pin_start != self.capture_manifest_pin_finish:
            raise ValueError("capture manifest 起訖 pins 不一致")
        if any(type(item) is not FundamentalReadSnapshotFileReference for item in (
            *self.captured_files,
            *self.reader_files,
        )):
            raise TypeError("snapshot refs 型別錯誤")
        if not _SHA256_RE.fullmatch(self.source_snapshot_sha256):
            raise ValueError("source_snapshot_sha256 格式錯誤")
        if type(self.source_copy_bytes) is not int or self.source_copy_bytes < 0:
            raise ValueError("source_copy_bytes 必須是非負整數")
        if type(self.duplicated_disk_bytes) is not int or self.duplicated_disk_bytes < 0:
            raise ValueError("duplicated_disk_bytes 必須是非負整數")
        if type(self.reader_only_sidecar_bytes) is not int or self.reader_only_sidecar_bytes < 0:
            raise ValueError("reader_only_sidecar_bytes 必須是非負整數")
        if self.duplicated_disk_bytes != (
            self.source_copy_bytes * 2 + self.reader_only_sidecar_bytes
        ):
            raise ValueError("duplicated_disk_bytes 未反映 captured/reader/SQLite sidecars")
        if self.sqlite_journal_mode == "wal":
            if self.wal_sidecar_state not in {"complete", "absent"}:
                raise ValueError("WAL snapshot sidecar 狀態錯誤")
        elif self.wal_sidecar_state != "not_applicable":
            raise ValueError("rollback snapshot 不可宣告 WAL sidecar 狀態")

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "snapshot_root": self.snapshot_root,
            "source_database_path": self.source_database_path,
            "reader_database_path": self.reader_database_path,
            "source_file_pins_start": [pin.to_dict() for pin in self.source_file_pins_start],
            "source_file_pins_after_copy": [
                pin.to_dict() for pin in self.source_file_pins_after_copy
            ],
            "source_file_pins_finish": [
                pin.to_dict() for pin in self.source_file_pins_finish
            ],
            "captured_files": [item.to_dict() for item in self.captured_files],
            "captured_file_pins_start": [
                pin.to_dict() for pin in self.captured_file_pins_start
            ],
            "captured_file_pins_finish": [
                pin.to_dict() for pin in self.captured_file_pins_finish
            ],
            "capture_manifest_pin_start": self.capture_manifest_pin_start.to_dict(),
            "capture_manifest_pin_finish": self.capture_manifest_pin_finish.to_dict(),
            "reader_files": [item.to_dict() for item in self.reader_files],
            "reader_file_pins_finish": [
                pin.to_dict() for pin in self.reader_file_pins_finish
            ],
            "sqlite_journal_mode": self.sqlite_journal_mode,
            "wal_sidecar_state": self.wal_sidecar_state,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "source_copy_bytes": self.source_copy_bytes,
            "reader_only_sidecar_bytes": self.reader_only_sidecar_bytes,
            "duplicated_disk_bytes": self.duplicated_disk_bytes,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._identity_payload()
        payload["identity_sha256"] = self.identity_sha256
        return payload


@dataclass(frozen=True, slots=True)
class FundamentalSnapshotSourceClock:
    """原始來源 clock，另外綁定實際開啟的隔離副本。"""

    database_path: str
    decision_cutoff: datetime
    declared_stock_codes: tuple[str, ...]
    schema_identity_sha256: str
    schema_descriptor: tuple[tuple[int, str, str, int, str | None, int], ...]
    database_file_pins_start: tuple[FundamentalFilePin, ...]
    database_file_pins_finish: tuple[FundamentalFilePin, ...]
    capture_file_pins_start: tuple[FundamentalFilePin, ...]
    capture_file_pins_finish: tuple[FundamentalFilePin, ...]
    snapshot_binding: FundamentalReadSnapshotBinding
    schema_version: Literal["selection-fundamental-source-clock.snapshot.v1"] = (
        FUNDAMENTAL_SNAPSHOT_SOURCE_CLOCK_SCHEMA
    )
    source_id: Literal["sqlite.fundamental_current_observations"] = (
        "sqlite.fundamental_current_observations"
    )
    source_scope: Literal["current_observed_only"] = "current_observed_only"
    availability_status: Literal["unknown"] = "unknown"
    historical_pit_eligible: Literal[False] = False
    formal_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if type(self.database_path) is not str or not Path(self.database_path).is_absolute():
            raise ValueError("database_path 必須是原始來源 canonical 絕對路徑")
        if self.snapshot_binding.source_database_path != self.database_path:
            raise ValueError("snapshot binding 必須指向原始 database_path")
        if self.snapshot_binding.source_file_pins_start != self.database_file_pins_start:
            raise ValueError("snapshot binding 起始 pins 與 source clock 不符")
        if self.snapshot_binding.source_file_pins_finish != self.database_file_pins_finish:
            raise ValueError("snapshot binding 完成 pins 與 source clock 不符")
        if self.database_file_pins_start != self.database_file_pins_finish:
            raise ValueError("DB/WAL/SHM 起訖 pins 不一致")
        if self.capture_file_pins_start != self.capture_file_pins_finish:
            raise ValueError("capture 起訖 pins 不一致")
        if self.source_scope != "current_observed_only" or self.availability_status != "unknown":
            raise ValueError("fundamental snapshot 必須保持 current-only/unknown")
        if self.historical_pit_eligible is not False or self.formal_pit_eligible is not False:
            raise ValueError("current-only session 不可標記為 PIT eligible")

    @property
    def declared_stock_codes_sha256(self) -> str:
        return _canonical_sha256(list(self.declared_stock_codes))

    @property
    def source_pin_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    @property
    def identity_sha256(self) -> str:
        return self.source_pin_sha256

    @property
    def source_content_identity_sha256(self) -> str:
        """不含本次 reader 路徑／session 的固定來源內容身分。"""

        payload = self._identity_payload()
        payload.pop("snapshot_binding")
        return _canonical_sha256(payload)

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "database_path": self.database_path,
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "declared_stock_codes": list(self.declared_stock_codes),
            "declared_stock_codes_sha256": self.declared_stock_codes_sha256,
            "schema_identity_sha256": self.schema_identity_sha256,
            "schema_descriptor": [list(item) for item in self.schema_descriptor],
            "database_file_pins_start": [
                pin.to_dict() for pin in self.database_file_pins_start
            ],
            "database_file_pins_finish": [
                pin.to_dict() for pin in self.database_file_pins_finish
            ],
            "capture_file_pins_start": [
                pin.to_dict() for pin in self.capture_file_pins_start
            ],
            "capture_file_pins_finish": [
                pin.to_dict() for pin in self.capture_file_pins_finish
            ],
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "snapshot_binding": self.snapshot_binding.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._identity_payload()
        payload["source_pin_sha256"] = self.source_pin_sha256
        payload["identity_sha256"] = self.identity_sha256
        return payload


@dataclass(frozen=True, slots=True)
class FinishedFundamentalSnapshotReadCohort:
    """完成隔離 copy 與原來源起訖驗證的 cohort finish token。"""

    session_id: str
    source_clock: FundamentalSnapshotSourceClock
    processed_stock_codes: tuple[str, ...]
    result_identity_by_stock: tuple[tuple[str, str], ...]
    result_status_counts: tuple[tuple[str, int], ...]
    complete: Literal[True] = True

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.session_id):
            raise ValueError("snapshot session_id 格式錯誤")
        if self.processed_stock_codes != self.source_clock.declared_stock_codes:
            raise ValueError("finished snapshot cohort 未完整涵蓋 declared 清冊")
        if tuple(code for code, _ in self.result_identity_by_stock) != self.processed_stock_codes:
            raise ValueError("snapshot result identities 未按 declared 清冊排序")
        if any(not _SHA256_RE.fullmatch(value) for _, value in self.result_identity_by_stock):
            raise ValueError("snapshot result identity SHA-256 格式錯誤")
        if self.complete is not True:
            raise ValueError("FinishedFundamentalSnapshotReadCohort 必須是完整結果")

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(
            {
                "schema_version": "selection-fundamental-snapshot-finished-cohort.v1",
                "session_id": self.session_id,
                "source_clock_sha256": self.source_clock.identity_sha256,
                "processed_stock_codes": list(self.processed_stock_codes),
                "result_identity_by_stock": [list(item) for item in self.result_identity_by_stock],
                "result_status_counts": [list(item) for item in self.result_status_counts],
                "complete": True,
            }
        )


@dataclass(frozen=True, slots=True)
class FundamentalReadSnapshotReferenceV1:
    """指向已完成來源 snapshot 的傳輸參照；自我雜湊本身不授予讀取資格。"""

    snapshot_root: str
    snapshot_id: str
    finished_manifest_sha256: str
    source_clock_identity_sha256: str
    source_content_identity_sha256: str
    cohort_identity_sha256: str
    decision_cutoff: str
    declared_stock_codes: tuple[str, ...]
    declared_stock_codes_sha256: str
    schema_version: Literal["fundamental-read-snapshot-reference.v1"] = (
        "fundamental-read-snapshot-reference.v1"
    )

    def __post_init__(self) -> None:
        if self.schema_version != "fundamental-read-snapshot-reference.v1":
            raise ValueError("snapshot reference schema 不支援")
        if type(self.snapshot_root) is not str or not Path(self.snapshot_root).is_absolute():
            raise ValueError("snapshot_root 必須是絕對路徑")
        if type(self.snapshot_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", self.snapshot_id):
            raise ValueError("snapshot_id 格式錯誤")
        for value in (
            self.finished_manifest_sha256,
            self.source_clock_identity_sha256,
            self.source_content_identity_sha256,
            self.cohort_identity_sha256,
            self.declared_stock_codes_sha256,
        ):
            if type(value) is not str or not _SHA256_RE.fullmatch(value):
                raise ValueError("snapshot reference SHA-256 格式錯誤")
        parsed_cutoff = _parse_reference_cutoff(self.decision_cutoff)
        if parsed_cutoff.isoformat() != self.decision_cutoff:
            raise ValueError("snapshot reference cutoff 必須使用 aware canonical ISO 格式")
        if (
            type(self.declared_stock_codes) is not tuple
            or not self.declared_stock_codes
            or self.declared_stock_codes != tuple(sorted(set(self.declared_stock_codes)))
            or any(not re.fullmatch(r"[0-9]{4,6}", code) for code in self.declared_stock_codes)
            or self.declared_stock_codes_sha256 != _canonical_sha256(list(self.declared_stock_codes))
        ):
            raise ValueError("snapshot reference declared codes 格式或摘要錯誤")

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "snapshot_root": self.snapshot_root,
            "snapshot_id": self.snapshot_id,
            "finished_manifest_sha256": self.finished_manifest_sha256,
            "source_clock_identity_sha256": self.source_clock_identity_sha256,
            "source_content_identity_sha256": self.source_content_identity_sha256,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "decision_cutoff": self.decision_cutoff,
            "declared_stock_codes": list(self.declared_stock_codes),
            "declared_stock_codes_sha256": self.declared_stock_codes_sha256,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._identity_payload()
        payload["identity_sha256"] = self.identity_sha256
        return payload

    def to_json(self) -> str:
        encoded = _canonical_json_bytes(self.to_dict())
        if len(encoded) > MAX_SNAPSHOT_REFERENCE_JSON_BYTES:
            raise ValueError("snapshot reference 超過傳輸上限")
        return encoded.decode("utf-8")

    @classmethod
    def from_json(cls, raw: str | bytes) -> FundamentalReadSnapshotReferenceV1:
        if type(raw) is bytes:
            encoded = raw
        elif type(raw) is str:
            encoded = raw.encode("utf-8")
        else:
            raise TypeError("snapshot reference JSON 必須是 str 或 bytes")
        if len(encoded) > MAX_SNAPSHOT_REFERENCE_JSON_BYTES:
            raise ValueError("snapshot reference 超過傳輸上限")
        _validate_json_depth(encoded, max_depth=16)
        try:
            payload = json.loads(
                encoded.decode("utf-8"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("snapshot reference JSON 無效") from exc
        if type(payload) is not dict:
            raise ValueError("snapshot reference JSON 必須是 object")
        expected_keys = {
            "schema_version", "snapshot_root", "snapshot_id", "finished_manifest_sha256",
            "source_clock_identity_sha256", "source_content_identity_sha256",
            "cohort_identity_sha256", "decision_cutoff", "declared_stock_codes",
            "declared_stock_codes_sha256", "identity_sha256",
        }
        if set(payload) != expected_keys:
            raise ValueError("snapshot reference JSON 欄位不符")
        codes_raw = payload["declared_stock_codes"]
        if type(codes_raw) is not list or any(type(code) is not str for code in codes_raw):
            raise ValueError("snapshot reference code 清冊格式錯誤")
        reference = cls(
            snapshot_root=_require_json_string(payload, "snapshot_root"),
            snapshot_id=_require_json_string(payload, "snapshot_id"),
            finished_manifest_sha256=_require_json_string(payload, "finished_manifest_sha256"),
            source_clock_identity_sha256=_require_json_string(payload, "source_clock_identity_sha256"),
            source_content_identity_sha256=_require_json_string(payload, "source_content_identity_sha256"),
            cohort_identity_sha256=_require_json_string(payload, "cohort_identity_sha256"),
            decision_cutoff=_require_json_string(payload, "decision_cutoff"),
            declared_stock_codes=tuple(codes_raw),
            declared_stock_codes_sha256=_require_json_string(payload, "declared_stock_codes_sha256"),
        )
        if payload["identity_sha256"] != reference.identity_sha256:
            raise ValueError("snapshot reference identity 摘要不符")
        if encoded != reference.to_json().encode("utf-8"):
            raise ValueError("snapshot reference JSON 必須是 canonical bytes")
        return reference


@dataclass(frozen=True, slots=True)
class FundamentalReadSnapshotRawArchiveFileV1:
    """把歷史原始 capture pin 對應到 durable archive 的相對檔案。"""

    historical_pin: FundamentalFilePin
    relative_path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if type(self.historical_pin) is not FundamentalFilePin:
            raise TypeError("raw archive 歷史 pin 型別錯誤")
        if not self.historical_pin.present or self.historical_pin.role not in {
            "monthly_html", "monthly_csv"
        }:
            raise ValueError("raw archive 只接受已存在的月營收 HTML/CSV capture")
        if type(self.relative_path) is not str or not self.relative_path or "\\" in self.relative_path:
            raise ValueError("raw archive 路徑必須是非空 POSIX 相對路徑")
        relative = PurePosixPath(self.relative_path)
        if (
            relative.is_absolute()
            or str(relative) != self.relative_path
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ValueError("raw archive 路徑不可離開封存根目錄")
        if type(self.size_bytes) is not int or not 0 <= self.size_bytes <= MAX_RAW_ARCHIVE_FILE_BYTES:
            raise ValueError("raw archive 單檔大小超過上限")
        if self.size_bytes != self.historical_pin.size_bytes or self.sha256 != self.historical_pin.sha256:
            raise ValueError("raw archive bytes 必須等於歷史原始 capture")
        if type(self.sha256) is not str or not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("raw archive SHA-256 格式錯誤")

    def to_dict(self) -> dict[str, object]:
        return {
            "historical_pin": self.historical_pin.to_dict(),
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class FundamentalReadSnapshotRawArchiveReferenceV1:
    """durable raw archive 的傳輸參照；JSON 自洽不等於來源已核驗。"""

    snapshot_reference: FundamentalReadSnapshotReferenceV1
    raw_archive_root: str
    archived_monthly_source_root: str
    original_monthly_source_root: str
    archive_id: str
    source_clock_identity_sha256: str
    source_content_identity_sha256: str
    cohort_identity_sha256: str
    decision_cutoff: str
    declared_stock_codes: tuple[str, ...]
    declared_stock_codes_sha256: str
    files: tuple[FundamentalReadSnapshotRawArchiveFileV1, ...]
    manifest_sha256: str
    archive_identity_sha256: str
    schema_version: Literal["fundamental-monthly-raw-source-archive.v1"] = (
        "fundamental-monthly-raw-source-archive.v1"
    )
    source_scope: Literal["current_observed_only"] = "current_observed_only"
    availability_status: Literal["unknown"] = "unknown"
    historical_pit_eligible: Literal[False] = False
    formal_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if type(self.snapshot_reference) is not FundamentalReadSnapshotReferenceV1:
            raise TypeError("raw archive 必須綁 typed snapshot reference")
        if self.schema_version != "fundamental-monthly-raw-source-archive.v1":
            raise ValueError("raw archive schema 不支援")
        for name in (
            "raw_archive_root", "archived_monthly_source_root", "original_monthly_source_root"
        ):
            value = getattr(self, name)
            if type(value) is not str or not Path(value).is_absolute():
                raise ValueError(f"{name} 必須是絕對路徑")
        if type(self.archive_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", self.archive_id):
            raise ValueError("raw archive id 格式錯誤")
        for name in (
            "source_clock_identity_sha256", "source_content_identity_sha256",
            "cohort_identity_sha256", "declared_stock_codes_sha256",
            "manifest_sha256", "archive_identity_sha256",
        ):
            value = getattr(self, name)
            if type(value) is not str or not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} SHA-256 格式錯誤")
        root = Path(self.raw_archive_root)
        if root.name != self.archive_id or Path(self.archived_monthly_source_root) != root / "monthly_source":
            raise ValueError("raw archive root 與 monthly source root 不符")
        cutoff = _parse_reference_cutoff(self.decision_cutoff)
        if cutoff.isoformat() != self.decision_cutoff:
            raise ValueError("raw archive cutoff 必須是 canonical aware ISO")
        if (
            type(self.declared_stock_codes) is not tuple
            or self.declared_stock_codes != self.snapshot_reference.declared_stock_codes
            or self.declared_stock_codes_sha256 != _canonical_sha256(list(self.declared_stock_codes))
            or self.source_clock_identity_sha256 != self.snapshot_reference.source_clock_identity_sha256
            or self.source_content_identity_sha256 != self.snapshot_reference.source_content_identity_sha256
            or self.cohort_identity_sha256 != self.snapshot_reference.cohort_identity_sha256
            or self.decision_cutoff != self.snapshot_reference.decision_cutoff
        ):
            raise ValueError("raw archive 與 snapshot source identity 不一致")
        if (
            type(self.files) is not tuple
            or not self.files
            or len(self.files) > MAX_RAW_ARCHIVE_FILES
            or any(type(item) is not FundamentalReadSnapshotRawArchiveFileV1 for item in self.files)
            or len({item.historical_pin.role for item in self.files}) != len(self.files)
            or sum(item.size_bytes for item in self.files) > MAX_RAW_ARCHIVE_TOTAL_BYTES
        ):
            raise ValueError("raw archive capture inventory 無效或超過上限")
        if self.source_scope != "current_observed_only" or self.availability_status != "unknown":
            raise ValueError("raw archive 必須保持 current-only/availability unknown")
        if self.historical_pit_eligible is not False or self.formal_pit_eligible is not False:
            raise ValueError("raw archive 不可授予 PIT 資格")
        if self.archive_identity_sha256 != _canonical_sha256(self._archive_identity_payload()):
            raise ValueError("raw archive identity 摘要不符")

    def _archive_identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "snapshot_reference": self.snapshot_reference.to_dict(),
            "raw_archive_root": self.raw_archive_root,
            "archived_monthly_source_root": self.archived_monthly_source_root,
            "original_monthly_source_root": self.original_monthly_source_root,
            "archive_id": self.archive_id,
            "source_clock_identity_sha256": self.source_clock_identity_sha256,
            "source_content_identity_sha256": self.source_content_identity_sha256,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "decision_cutoff": self.decision_cutoff,
            "declared_stock_codes": list(self.declared_stock_codes),
            "declared_stock_codes_sha256": self.declared_stock_codes_sha256,
            "files": [item.to_dict() for item in self.files],
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
        }

    def _identity_payload(self) -> dict[str, object]:
        payload = self._archive_identity_payload()
        payload["manifest_sha256"] = self.manifest_sha256
        payload["archive_identity_sha256"] = self.archive_identity_sha256
        return payload

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    def to_dict(self) -> dict[str, object]:
        payload = self._identity_payload()
        payload["archive_identity_sha256"] = self.archive_identity_sha256
        payload["identity_sha256"] = self.identity_sha256
        return payload

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > MAX_RAW_ARCHIVE_REFERENCE_JSON_BYTES:
            raise ValueError("raw archive reference 超過傳輸上限")
        return raw.decode("utf-8")

    @classmethod
    def from_json(cls, raw: str | bytes) -> FundamentalReadSnapshotRawArchiveReferenceV1:
        if type(raw) is bytes:
            encoded = raw
        elif type(raw) is str:
            encoded = raw.encode("utf-8")
        else:
            raise TypeError("raw archive reference 必須是 str 或 bytes")
        if len(encoded) > MAX_RAW_ARCHIVE_REFERENCE_JSON_BYTES:
            raise ValueError("raw archive reference 超過傳輸上限")
        _validate_json_depth(encoded, max_depth=20)
        try:
            payload = json.loads(
                encoded.decode("utf-8"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("raw archive reference JSON 無效") from exc
        if type(payload) is not dict:
            raise ValueError("raw archive reference 必須是 object")
        expected = {
            "schema_version", "snapshot_reference", "raw_archive_root",
            "archived_monthly_source_root", "original_monthly_source_root", "archive_id",
            "source_clock_identity_sha256", "source_content_identity_sha256",
            "cohort_identity_sha256", "decision_cutoff", "declared_stock_codes",
            "declared_stock_codes_sha256", "files", "manifest_sha256",
            "source_scope", "availability_status", "historical_pit_eligible",
            "formal_pit_eligible", "archive_identity_sha256", "identity_sha256",
        }
        if set(payload) != expected:
            raise ValueError("raw archive reference 欄位不符")
        nested = payload["snapshot_reference"]
        raw_codes = payload["declared_stock_codes"]
        raw_files = payload["files"]
        if type(nested) is not dict or type(raw_codes) is not list or type(raw_files) is not list:
            raise ValueError("raw archive nested fields 格式錯誤")
        if any(type(code) is not str for code in raw_codes):
            raise ValueError("raw archive codes 型別錯誤")
        reference = cls(
            snapshot_reference=FundamentalReadSnapshotReferenceV1.from_json(
                _canonical_json_bytes(nested)
            ),
            raw_archive_root=_require_json_string(payload, "raw_archive_root"),
            archived_monthly_source_root=_require_json_string(payload, "archived_monthly_source_root"),
            original_monthly_source_root=_require_json_string(payload, "original_monthly_source_root"),
            archive_id=_require_json_string(payload, "archive_id"),
            source_clock_identity_sha256=_require_json_string(payload, "source_clock_identity_sha256"),
            source_content_identity_sha256=_require_json_string(payload, "source_content_identity_sha256"),
            cohort_identity_sha256=_require_json_string(payload, "cohort_identity_sha256"),
            decision_cutoff=_require_json_string(payload, "decision_cutoff"),
            declared_stock_codes=tuple(raw_codes),
            declared_stock_codes_sha256=_require_json_string(payload, "declared_stock_codes_sha256"),
            files=tuple(_parse_raw_archive_file(item) for item in raw_files),
            manifest_sha256=_require_json_string(payload, "manifest_sha256"),
            archive_identity_sha256=_require_json_string(payload, "archive_identity_sha256"),
            schema_version=payload["schema_version"],
            source_scope=payload["source_scope"],
            availability_status=payload["availability_status"],
            historical_pit_eligible=payload["historical_pit_eligible"],
            formal_pit_eligible=payload["formal_pit_eligible"],
        )
        if payload["identity_sha256"] != reference.identity_sha256:
            raise ValueError("raw archive reference identity mismatch")
        if encoded != reference.to_json().encode("utf-8"):
            raise ValueError("raw archive reference JSON 必須 canonical bytes")
        return reference


@dataclass(frozen=True, slots=True)
class _VerifiedArchivedSnapshotReference:
    """snapshot、raw archive 與其檔案 bytes 都已在本次入口實際核驗。"""

    snapshot: _VerifiedSnapshotReference
    archive_reference: FundamentalReadSnapshotRawArchiveReferenceV1
    snapshot_manifest_pin: FundamentalFilePin
    archive_manifest_pin: FundamentalFilePin
    archive_file_pins: tuple[FundamentalFilePin, ...]


@dataclass(frozen=True, slots=True)
class _RawArchiveVerificationRoots:
    """只提供 raw archive 核驗所需的詞法保護根，不建立 provider。"""

    output_root: Path
    monthly_source_root: Path


@dataclass(frozen=True, slots=True)
class _VerifiedSnapshotReference:
    reference: FundamentalReadSnapshotReferenceV1
    binding: FundamentalReadSnapshotBinding
    source_clock: FundamentalSnapshotSourceClock
    reader_session_id: str
    finished_session_id: str
    processed_stock_codes: tuple[str, ...]
    result_identity_by_stock: tuple[tuple[str, str], ...]
    result_status_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class _SnapshotAttempt:
    snapshot_id: str
    snapshot_root: Path
    source_database_path: Path
    reader_database_path: Path
    source_file_pins_start: tuple[FundamentalFilePin, ...]
    source_file_pins_after_copy: tuple[FundamentalFilePin, ...]
    captured_files: tuple[FundamentalReadSnapshotFileReference, ...]
    captured_file_pins_start: tuple[FundamentalFilePin, ...]
    capture_manifest_pin_start: FundamentalFilePin
    reader_files: tuple[FundamentalReadSnapshotFileReference, ...]
    sqlite_journal_mode: Literal["rollback", "wal"]
    wal_sidecar_state: Literal["complete", "absent", "not_applicable"]
    source_snapshot_sha256: str
    source_copy_bytes: int


class FundamentalReadSnapshotSession:
    """以副本 provider 跑共用 reader，finish 才發布原始來源 clock。"""

    def __init__(
        self,
        *,
        provider: RecommendationCurrentFundamentalProvider,
        attempt: _SnapshotAttempt,
        read_session: SelectionFundamentalReadSession,
        cancel_callback: Callable[[], bool] | None,
        cancel_event: Event,
        expected_reference: _VerifiedSnapshotReference | _VerifiedSnapshotReferenceV2 | None = None,
        expected_archived_reference: _VerifiedArchivedSnapshotReference | _VerifiedArchivedSnapshotReferenceV2 | None = None,
        daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader | None = None,
    ) -> None:
        self._provider = provider
        self._attempt = attempt
        self._read_session = read_session
        self._cancel_callback = cancel_callback
        self._cancel_event = cancel_event
        self._publication_gate = Lock()
        self._state: Literal["open", "finished", "cancelled", "failed"] = "open"
        self._finished: FinishedFundamentalSnapshotReadCohort | FinishedFundamentalSnapshotReadCohortV2 | None = None
        self._owner_thread_id = get_ident()
        self._expected_reference = expected_reference
        self._expected_archived_reference = expected_archived_reference
        self._daily_monthly_cohort_reader = daily_monthly_cohort_reader

    @classmethod
    def open_from_config(
        cls,
        config: TWStockConfig,
        *,
        stock_codes: Sequence[str],
        cutoff_at: datetime,
        provider: RecommendationCurrentFundamentalProvider | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> FundamentalReadSnapshotSession:
        """正式配置的副本入口；不連線原庫、不使用隱含QA或正式輸出根。"""
        if not isinstance(config, TWStockConfig):
            raise TypeError("config 必須是 TWStockConfig")
        root = config.fundamental_read_snapshot_root
        if root is None:
            raise FundamentalReadSnapshotError("fundamental_snapshot_root_not_configured")
        _reject_reparse_components(root, allow_missing=True)
        normalized = Path(os.path.abspath(root.expanduser()))
        if any(_paths_overlap(normalized, Path(value).expanduser().resolve(strict=False))
               for value in (config.data_root, config.output_root)):
            raise FundamentalReadSnapshotError("fundamental_snapshot_root_overlaps_configured_data_or_output")
        selected_provider = provider if provider is not None else RecommendationCurrentFundamentalProvider(
            db_file=config.db_file, output_root=config.output_root,
            calendar_cache_path=config.official_calendar_cache_path,
        )
        if not isinstance(selected_provider, RecommendationCurrentFundamentalProvider):
            raise TypeError("provider 必須是 RecommendationCurrentFundamentalProvider")
        if (selected_provider.db_file != config.db_file.expanduser().resolve(strict=False)
                or selected_provider.output_root != config.output_root.expanduser().resolve(strict=False)):
            raise FundamentalReadSnapshotError("fundamental_snapshot_provider_config_identity_mismatch")
        return cls.open(selected_provider, snapshot_root=root, stock_codes=stock_codes,
                        cutoff_at=cutoff_at, cancel_callback=cancel_callback)

    @classmethod
    def open(
        cls,
        provider: RecommendationCurrentFundamentalProvider,
        *,
        snapshot_root: Path | str,
        stock_codes: Sequence[str],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> FundamentalReadSnapshotSession:
        """先隔離來源 bytes，再只對 reader copy 建立 SQLite read session。"""

        if not isinstance(provider, RecommendationCurrentFundamentalProvider):
            raise TypeError("provider 必須是 RecommendationCurrentFundamentalProvider")
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        cancel_event = Event()

        def session_cancelled() -> bool:
            if cancel_event.is_set():
                return True
            if cancel_callback is None:
                return False
            value = cancel_callback()
            if type(value) is not bool:
                raise FundamentalReadSnapshotCancelled(
                    "fundamental_snapshot_cancel_callback_must_return_bool"
                )
            return value

        _poll_cancel(session_cancelled)
        attempt = _capture_snapshot(
            provider,
            snapshot_root=snapshot_root,
            cancel_callback=session_cancelled,
        )
        return cls._open_reader_attempt(
            provider,
            attempt,
            stock_codes=stock_codes,
            cutoff_at=cutoff_at,
            cancel_callback=cancel_callback,
            cancel_event=cancel_event,
            expected_reference=None,
        )

    @classmethod
    def open_exact(
        cls,
        provider: RecommendationCurrentFundamentalProvider,
        *,
        snapshot_root: Path | str,
        source_reference: FundamentalReadSnapshotReferenceV1 | str | bytes,
        stock_codes: Sequence[str],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> FundamentalReadSnapshotSession:
        """由已封存來源重新建立新 reader operation，絕不連線原 DB 或 saved reader copy。"""

        if type(provider) is not RecommendationCurrentFundamentalProvider:
            raise TypeError("provider 必須是 RecommendationCurrentFundamentalProvider")
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        if type(source_reference) is FundamentalReadSnapshotReferenceV1:
            reference = cast(FundamentalReadSnapshotReferenceV1, source_reference)
        elif type(source_reference) in {str, bytes}:
            reference = FundamentalReadSnapshotReferenceV1.from_json(
                cast(str | bytes, source_reference)
            )
        else:
            raise TypeError("source_reference 必須是 typed reference、str 或 bytes")
        codes = _normalize_snapshot_codes(stock_codes)
        if type(cutoff_at) is not datetime or cutoff_at.tzinfo is None:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_cutoff_must_be_aware")
        cutoff = cutoff_at.astimezone(timezone.utc)
        reference_cutoff = _parse_reference_cutoff(reference.decision_cutoff)
        if cutoff != reference_cutoff.astimezone(timezone.utc):
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_cutoff_mismatch")
        if codes != reference.declared_stock_codes:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_declared_codes_mismatch")
        verified = _verify_finished_snapshot_reference(
            reference,
            provider=provider,
            cancel_callback=cancel_callback,
        )
        origin_database_path = Path(verified.source_clock.database_path)
        if provider.db_file != origin_database_path:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_provider_database_mismatch")
        cancel_event = Event()

        def session_cancelled() -> bool:
            if cancel_event.is_set():
                return True
            if cancel_callback is None:
                return False
            value = cancel_callback()
            if type(value) is not bool:
                raise FundamentalReadSnapshotCancelled(
                    "fundamental_snapshot_cancel_callback_must_return_bool"
                )
            return value

        _poll_cancel(session_cancelled)
        attempt = _capture_snapshot_from_reference(
            provider,
            source_reference=verified,
            snapshot_root=snapshot_root,
            cancel_callback=session_cancelled,
        )
        return cls._open_reader_attempt(
            provider,
            attempt,
            stock_codes=codes,
            cutoff_at=cutoff,
            cancel_callback=cancel_callback,
            cancel_event=cancel_event,
            expected_reference=verified,
        )

    @classmethod
    def open_exact_archived(
        cls,
        provider: RecommendationCurrentFundamentalProvider,
        *,
        snapshot_root: Path | str,
        source_reference: FundamentalReadSnapshotReferenceV1 | str | bytes,
        raw_archive_reference: FundamentalReadSnapshotRawArchiveReferenceV1 | str | bytes,
        stock_codes: Sequence[str],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> FundamentalReadSnapshotSession:
        """只由 saved snapshot 與 raw archive 建新的 operation；不讀 live source。"""

        if type(provider) is not RecommendationCurrentFundamentalProvider:
            raise TypeError("provider 必須是 RecommendationCurrentFundamentalProvider")
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        if type(source_reference) is FundamentalReadSnapshotReferenceV1:
            snapshot_ref = cast(FundamentalReadSnapshotReferenceV1, source_reference)
        elif type(source_reference) in {str, bytes}:
            snapshot_ref = FundamentalReadSnapshotReferenceV1.from_json(
                cast(str | bytes, source_reference)
            )
        else:
            raise TypeError("source_reference 必須是 typed snapshot reference 或 canonical JSON")
        if type(raw_archive_reference) is FundamentalReadSnapshotRawArchiveReferenceV1:
            archive_ref = cast(FundamentalReadSnapshotRawArchiveReferenceV1, raw_archive_reference)
        elif type(raw_archive_reference) in {str, bytes}:
            archive_ref = FundamentalReadSnapshotRawArchiveReferenceV1.from_json(
                cast(str | bytes, raw_archive_reference)
            )
        else:
            raise TypeError("raw_archive_reference 必須是 typed archive reference 或 canonical JSON")
        if archive_ref.snapshot_reference.identity_sha256 != snapshot_ref.identity_sha256:
            raise FundamentalReadSnapshotError("fundamental_snapshot_archived_reference_mismatch")
        codes = _normalize_snapshot_codes(stock_codes)
        if type(cutoff_at) is not datetime or cutoff_at.tzinfo is None:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_cutoff_must_be_aware")
        cutoff = cutoff_at.astimezone(timezone.utc)
        if cutoff != _parse_reference_cutoff(snapshot_ref.decision_cutoff).astimezone(timezone.utc):
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_cutoff_mismatch")
        if codes != snapshot_ref.declared_stock_codes:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_declared_codes_mismatch")
        cancel_event = Event()

        def session_cancelled() -> bool:
            if cancel_event.is_set():
                return True
            if cancel_callback is None:
                return False
            value = cancel_callback()
            if type(value) is not bool:
                raise FundamentalReadSnapshotCancelled(
                    "fundamental_snapshot_cancel_callback_must_return_bool"
                )
            return value

        _poll_cancel(session_cancelled)
        verified = _verify_raw_archive_reference(
            archive_ref,
            provider=provider,
            cancel_callback=session_cancelled,
        )
        if verified.snapshot.reference.identity_sha256 != snapshot_ref.identity_sha256:
            raise FundamentalReadSnapshotError("fundamental_snapshot_archived_snapshot_identity_mismatch")
        attempt = _capture_snapshot_from_archived_reference(
            provider,
            verified_reference=verified,
            snapshot_root=snapshot_root,
            cancel_callback=session_cancelled,
        )
        return cls._open_reader_attempt(
            provider,
            attempt,
            stock_codes=codes,
            cutoff_at=cutoff,
            cancel_callback=cancel_callback,
            cancel_event=cancel_event,
            expected_reference=None,
            expected_archived_reference=verified,
        )

    @classmethod
    def _open_reader_attempt(
        cls,
        provider: RecommendationCurrentFundamentalProvider,
        attempt: _SnapshotAttempt,
        *,
        stock_codes: Sequence[str],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None,
        cancel_event: Event,
        expected_reference: _VerifiedSnapshotReference | _VerifiedSnapshotReferenceV2 | None,
        expected_archived_reference: _VerifiedArchivedSnapshotReference | _VerifiedArchivedSnapshotReferenceV2 | None = None,
        daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader | None = None,
    ) -> FundamentalReadSnapshotSession:
        def session_cancelled() -> bool:
            if cancel_event.is_set():
                return True
            if cancel_callback is None:
                return False
            value = cancel_callback()
            if type(value) is not bool:
                raise FundamentalReadSnapshotCancelled(
                    "fundamental_snapshot_cancel_callback_must_return_bool"
                )
            return value

        try:
            reader_provider = _clone_provider_for_reader(
                provider,
                reader_database_path=attempt.reader_database_path,
                monthly_source_root=(
                    Path(expected_archived_reference.archive_reference.archived_monthly_source_root)
                    if expected_archived_reference is not None
                    else None
                ),
            )
            if daily_monthly_cohort_reader is not None:
                if (type(daily_monthly_cohort_reader) is not DailyMonthlyRevenueCohortReader
                        or provider.daily_source_snapshot_reader is not daily_monthly_cohort_reader):
                    raise FundamentalReadSnapshotError("fundamental_snapshot_v2_reader_identity_mismatch")
                reader_provider.daily_source_snapshot_reader = daily_monthly_cohort_reader
            if attempt.sqlite_journal_mode == "wal" and attempt.wal_sidecar_state == "absent":
                primer_binding = _make_copy_binding(
                    attempt,
                    cancel_callback=session_cancelled,
                )
                _verify_copy_binding_for_provider(
                    primer_binding,
                    provider=reader_provider,
                    cancel_callback=session_cancelled,
                )
                _prime_reader_copy(
                    attempt.reader_database_path,
                    cancel_callback=session_cancelled,
                )
            copy_binding: FundamentalReadCopyBinding | FundamentalReadArchivedCopyBinding | FundamentalReadArchivedCopyBindingV2
            if expected_archived_reference is None:
                copy_binding = _make_copy_binding(
                    attempt,
                    cancel_callback=session_cancelled,
                )
            else:
                from data_module.fundamental_read_snapshot_raw_archive_io_v2 import (
                    _VerifiedArchivedSnapshotReferenceV2, make_archived_copy_binding_v2,
                )
                if type(expected_archived_reference) is _VerifiedArchivedSnapshotReferenceV2:
                    if daily_monthly_cohort_reader is None:
                        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_missing_daily_reader")
                    copy_binding = make_archived_copy_binding_v2(attempt,
                        verified=expected_archived_reference, cancel_callback=session_cancelled)
                elif type(expected_archived_reference) is _VerifiedArchivedSnapshotReference:
                    copy_binding = _make_archived_copy_binding(attempt,
                        verified_reference=expected_archived_reference, cancel_callback=session_cancelled)
                else:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_archived_reference_kind_mismatch")
            if daily_monthly_cohort_reader is None:
                read_session = SelectionFundamentalReadSession.open(
                    reader_provider, database_path=attempt.reader_database_path,
                    copy_binding=copy_binding, stock_codes=stock_codes,
                    cutoff_at=cutoff_at, cancel_callback=session_cancelled,
                )
            else:
                read_session = SelectionFundamentalReadSession.open(
                    reader_provider, database_path=attempt.reader_database_path,
                    copy_binding=copy_binding, stock_codes=stock_codes,
                    cutoff_at=cutoff_at, cancel_callback=session_cancelled,
                    daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                )
        except FundamentalReadSessionCancelled as exc:
            _write_attempt_status(
                attempt.snapshot_root,
                status="cancelled",
                reason=f"reader_copy_open_cancelled:{type(exc).__name__}",
            )
            raise FundamentalReadSnapshotCancelled(str(exc)) from exc
        except BaseException as exc:
            _write_attempt_status(
                attempt.snapshot_root,
                status="failed",
                reason=f"reader_copy_open_failed:{type(exc).__name__}",
            )
            raise FundamentalReadSnapshotError(
                f"fundamental_snapshot_reader_copy_invalid:{type(exc).__name__}"
            ) from exc
        return cls(
            provider=reader_provider,
            attempt=attempt,
            read_session=read_session,
            cancel_callback=cancel_callback,
            cancel_event=cancel_event,
            expected_reference=expected_reference,
            expected_archived_reference=expected_archived_reference,
            daily_monthly_cohort_reader=daily_monthly_cohort_reader,
        )

    @property
    def snapshot_id(self) -> str:
        return self._attempt.snapshot_id

    @property
    def snapshot_root(self) -> Path:
        return self._attempt.snapshot_root

    @property
    def reader_database_path(self) -> Path:
        return self._attempt.reader_database_path

    @property
    def closed(self) -> bool:
        return self._read_session.closed

    @property
    def declared_stock_codes(self) -> tuple[str, ...]:
        return self._read_session.declared_stock_codes

    @property
    def source_reference(self) -> FundamentalReadSnapshotReferenceV1:
        """回傳已完成 attempt 的 exact 來源參照；未完成時不發行。"""

        self._require_owner_thread()
        if self._finished is None or self._state != "finished":
            raise FundamentalReadSnapshotError("fundamental_snapshot_reference_requires_finished_session")
        if type(self._finished) is not FinishedFundamentalSnapshotReadCohort:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v1_refuses_v2_reference")
        return _reference_from_finished_snapshot(self._attempt.snapshot_root)

    @property
    def archived_raw_source_reference(self) -> FundamentalReadSnapshotRawArchiveReferenceV1 | None:
        """回傳本次 exact archive reopen 使用的已核驗 raw archive 參照。"""

        self._require_owner_thread()
        if self._expected_archived_reference is None:
            return None
        if type(self._expected_archived_reference) is not _VerifiedArchivedSnapshotReference:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v1_refuses_v2_raw_archive")
        return self._expected_archived_reference.archive_reference

    def resolve_archived_capture_pin(
        self,
        historical_pin: FundamentalFilePin,
    ) -> FundamentalFilePin:
        """將 source clock 的歷史 capture pin 映射到本次已核驗 archive 檔案。"""

        self._require_owner_thread()
        verified = self._expected_archived_reference
        if verified is None or type(historical_pin) is not FundamentalFilePin:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_archived_capture_resolution_unavailable"
            )
        from data_module.fundamental_read_snapshot_raw_archive_io_v2 import _VerifiedArchivedSnapshotReferenceV2
        if type(verified) is _VerifiedArchivedSnapshotReferenceV2:
            historical_pins = tuple(item.historical_pin for item in verified.archive_reference.files)
        elif type(verified) is _VerifiedArchivedSnapshotReference:
            historical_pins = tuple(item.historical_pin for item in verified.archive_reference.files)
        else:
            raise FundamentalReadSnapshotError("fundamental_snapshot_archived_reference_kind_mismatch")
        for archived_pin, archive_pin in zip(
            historical_pins,
            verified.archive_file_pins,
            strict=True,
        ):
            _poll_cancel(self._effective_cancel_callback)
            if archived_pin == historical_pin:
                if (
                    archive_pin.role != historical_pin.role
                    or archive_pin.size_bytes != historical_pin.size_bytes
                    or archive_pin.sha256 != historical_pin.sha256
                ):
                    raise FundamentalReadSnapshotError(
                        "fundamental_snapshot_archived_capture_pin_mismatch"
                    )
                return archive_pin
        raise FundamentalReadSnapshotError(
            "fundamental_snapshot_archived_capture_pin_not_found"
        )

    def archive_monthly_raw_sources(
        self,
        archive_parent: Path | str,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> FundamentalReadSnapshotRawArchiveReferenceV1:
        """將已完成來源的 HTML/CSV 原件複製到唯一、不可覆寫的 sibling archive。"""

        self._require_owner_thread()
        if self._state != "finished" or self._finished is None:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_raw_archive_requires_finished_session"
            )
        if type(self._finished) is not FinishedFundamentalSnapshotReadCohort:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v1_refuses_v2_raw_archive")
        callback = self._effective_cancel_callback if cancel_callback is None else cancel_callback
        if not callable(callback):
            raise TypeError("cancel_callback 必須可呼叫")
        archive_provider = _clone_provider_for_reader(
            self._provider,
            reader_database_path=Path(self._finished.source_clock.database_path),
            monthly_source_root=self._provider.monthly_source_root,
        )
        return _create_raw_source_archive(
            provider=archive_provider,
            source_clock=self._finished.source_clock,
            snapshot_reference=self.source_reference,
            archive_parent=archive_parent,
            cancel_callback=callback,
        )

    def load_batch(self, stock_codes: Sequence[str]) -> FundamentalReadBatchCandidate:
        self._require_owner_thread()
        self._require_open()
        batch = self._read_session.load_batch(stock_codes)
        if type(batch) is not FundamentalReadBatchCandidate:
            self.close()
            raise FundamentalReadSnapshotError("fundamental_snapshot_v1_refuses_v2_batch")
        return batch

    def finish(self) -> FinishedFundamentalSnapshotReadCohort:
        finished = self._finish_core(daily_v2=False)
        if type(finished) is not FinishedFundamentalSnapshotReadCohort:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v1_refuses_v2_finished")
        return finished

    def _finish_core(
        self, *, daily_v2: bool,
    ) -> FinishedFundamentalSnapshotReadCohort | FinishedFundamentalSnapshotReadCohortV2:
        self._require_owner_thread()
        if type(daily_v2) is not bool:
            raise TypeError("snapshot version mode 必須是 exact bool")
        if self._finished is not None:
            return self._finished
        self._require_open()
        published = False
        try:
            _poll_cancel(self._effective_cancel_callback)
            reader_finished = self._read_session.finish()
            if daily_v2:
                if (type(reader_finished) is not FinishedFundamentalReadCohortV2
                        or self._daily_monthly_cohort_reader is None):
                    raise FundamentalReadSnapshotError("fundamental_snapshot_v2_requires_v2_finished")
            elif type(reader_finished) is not FinishedFundamentalReadCohort:
                raise FundamentalReadSnapshotError("fundamental_snapshot_v1_refuses_v2_finished")
            if not self._read_session.closed:
                raise FundamentalReadSnapshotError(
                    "fundamental_snapshot_reader_connection_not_closed_after_finish"
                )
            reader_file_pins_finish = _pin_reader_file_set(
                self._attempt.reader_database_path,
                cancel_callback=self._effective_cancel_callback,
            )
            captured_file_pins_finish, capture_manifest_pin_finish = (
                _verify_captured_evidence(
                    self._attempt,
                    cancel_callback=self._effective_cancel_callback,
                )
            )
            if self._expected_archived_reference is not None:
                source_pins_finish = (
                    self._expected_archived_reference.snapshot.source_clock.database_file_pins_finish
                )
                final_archive = _reverify_archived_subject(self._expected_archived_reference,
                    provider=self._provider, cancel_callback=self._effective_cancel_callback)
                reader_capture_pins = reader_finished.source_clock.capture_file_pins_start
                if reader_capture_pins != reader_finished.source_clock.capture_file_pins_finish:
                    raise FundamentalReadSnapshotError(
                        "fundamental_snapshot_archived_reader_capture_pins_changed"
                    )
                if tuple(
                    (pin.role, pin.size_bytes, pin.sha256) for pin in reader_capture_pins
                ) != tuple(
                    (pin.role, pin.size_bytes, pin.sha256)
                    for pin in final_archive.archive_file_pins
                ):
                    raise FundamentalReadSnapshotError(
                        "fundamental_snapshot_archived_reader_capture_content_mismatch"
                    )
            else:
                source_pins_finish = _pin_source_file_set(
                    self._attempt.source_database_path,
                    cancel_callback=self._effective_cancel_callback,
                )
                if source_pins_finish != self._attempt.source_file_pins_start:
                    raise FundamentalReadSnapshotError(
                        "fundamental_snapshot_original_source_changed_before_finish"
                    )
            if self._expected_reference is not None:
                origin_provider = _clone_provider_for_reader(
                    self._provider,
                    reader_database_path=Path(
                        self._expected_reference.source_clock.database_path
                    ),
                )
                if daily_v2:
                    from data_module.fundamental_read_snapshot_daily_v2 import (
                        _VerifiedSnapshotReferenceV2, _verify_finished_snapshot_reference_v2,
                    )
                    if type(self._expected_reference) is not _VerifiedSnapshotReferenceV2:
                        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_expected_reference_kind_mismatch")
                    if self._daily_monthly_cohort_reader is None:
                        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_missing_reader")
                    origin_provider.daily_source_snapshot_reader = self._daily_monthly_cohort_reader
                    _verify_finished_snapshot_reference_v2(
                        self._expected_reference.reference, provider=origin_provider,
                        daily_monthly_cohort_reader=self._daily_monthly_cohort_reader,
                        cancel_callback=self._effective_cancel_callback,
                    )
                else:
                    if type(self._expected_reference) is not _VerifiedSnapshotReference:
                        raise FundamentalReadSnapshotError("fundamental_snapshot_v1_expected_reference_kind_mismatch")
                    _verify_finished_snapshot_reference(
                        self._expected_reference.reference, provider=origin_provider,
                        cancel_callback=self._effective_cancel_callback,
                    )
            _poll_cancel(self._effective_cancel_callback)
            binding = FundamentalReadSnapshotBinding(
                snapshot_id=self._attempt.snapshot_id,
                snapshot_root=str(self._attempt.snapshot_root),
                source_database_path=str(self._attempt.source_database_path),
                reader_database_path=str(self._attempt.reader_database_path),
                source_file_pins_start=self._attempt.source_file_pins_start,
                source_file_pins_after_copy=self._attempt.source_file_pins_after_copy,
                source_file_pins_finish=source_pins_finish,
                captured_files=self._attempt.captured_files,
                captured_file_pins_start=self._attempt.captured_file_pins_start,
                captured_file_pins_finish=captured_file_pins_finish,
                capture_manifest_pin_start=self._attempt.capture_manifest_pin_start,
                capture_manifest_pin_finish=capture_manifest_pin_finish,
                reader_files=self._attempt.reader_files,
                reader_file_pins_finish=reader_file_pins_finish,
                sqlite_journal_mode=self._attempt.sqlite_journal_mode,
                wal_sidecar_state=self._attempt.wal_sidecar_state,
                source_snapshot_sha256=self._attempt.source_snapshot_sha256,
                source_copy_bytes=self._attempt.source_copy_bytes,
                reader_only_sidecar_bytes=_reader_only_sidecar_bytes(
                    self._attempt.reader_files,
                    reader_file_pins_finish,
                ),
                duplicated_disk_bytes=(
                    self._attempt.source_copy_bytes * 2
                    + _reader_only_sidecar_bytes(
                        self._attempt.reader_files,
                        reader_file_pins_finish,
                    )
                ),
            )
            reader_clock = reader_finished.source_clock
            base_source_clock = FundamentalSnapshotSourceClock(
                database_path=str(self._attempt.source_database_path),
                decision_cutoff=reader_clock.decision_cutoff,
                declared_stock_codes=reader_clock.declared_stock_codes,
                schema_identity_sha256=reader_clock.schema_identity_sha256,
                schema_descriptor=reader_clock.schema_descriptor,
                database_file_pins_start=self._attempt.source_file_pins_start,
                database_file_pins_finish=source_pins_finish,
                capture_file_pins_start=(
                    self._expected_archived_reference.snapshot.source_clock.capture_file_pins_start
                    if self._expected_archived_reference is not None
                    else reader_clock.capture_file_pins_start
                ),
                capture_file_pins_finish=(
                    self._expected_archived_reference.snapshot.source_clock.capture_file_pins_finish
                    if self._expected_archived_reference is not None
                    else reader_clock.capture_file_pins_finish
                ),
                snapshot_binding=binding,
            )
            source_clock: FundamentalSnapshotSourceClock | FundamentalSnapshotSourceClockV2 = base_source_clock
            if daily_v2:
                from data_module.fundamental_read_snapshot_cohort_v2 import FundamentalSnapshotSourceClockV2
                if type(reader_finished) is not FinishedFundamentalReadCohortV2:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_v2_lost_finished_reader")
                source_clock = FundamentalSnapshotSourceClockV2.from_base_clock(
                    base_source_clock, cohort_pin=reader_finished.source_clock.cohort_pin,
                    verified_markets=reader_finished.source_clock.verified_markets,
                )
            session_id = _canonical_sha256(
                {
                    "schema_version": ("selection-fundamental-snapshot-session.v2" if daily_v2
                                       else "selection-fundamental-snapshot-session.v1"),
                    "reader_session_id": reader_finished.session_id,
                    "source_clock_sha256": source_clock.identity_sha256,
                }
            )
            finished: FinishedFundamentalSnapshotReadCohort | FinishedFundamentalSnapshotReadCohortV2 | None = None
            if not daily_v2:
                if type(source_clock) is not FundamentalSnapshotSourceClock:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_v1_clock_kind_mismatch")
                finished = FinishedFundamentalSnapshotReadCohort(
                    session_id=session_id, source_clock=source_clock,
                    processed_stock_codes=reader_finished.processed_stock_codes,
                    result_identity_by_stock=reader_finished.result_identity_by_stock,
                    result_status_counts=reader_finished.result_status_counts,
                )
            expected_ledger = (
                self._expected_archived_reference.snapshot
                if self._expected_archived_reference is not None
                else self._expected_reference
            )
            if expected_ledger is not None:
                expected = expected_ledger
                if (
                    reader_finished.processed_stock_codes != expected.processed_stock_codes
                    or reader_finished.result_identity_by_stock != expected.result_identity_by_stock
                    or reader_finished.result_status_counts != expected.result_status_counts
                    or source_clock.source_content_identity_sha256
                    != expected.source_clock.source_content_identity_sha256
                ):
                    raise FundamentalReadSnapshotError(
                        "fundamental_snapshot_exact_reopen_result_ledger_mismatch"
                    )
            _poll_cancel(self._effective_cancel_callback)
            if daily_v2:
                from data_module.fundamental_read_snapshot_cohort_v2 import (
                    make_finished_snapshot_manifest_v2, parse_finished_snapshot_cohort_v2,
                )
                if type(source_clock) is not FundamentalSnapshotSourceClockV2:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_v2_clock_kind_mismatch")
                finished_manifest = make_finished_snapshot_manifest_v2(
                    session_id=session_id, reader_session_id=reader_finished.session_id,
                    source_clock=source_clock,
                    processed_stock_codes=reader_finished.processed_stock_codes,
                    result_identity_by_stock=reader_finished.result_identity_by_stock,
                    result_status_counts=reader_finished.result_status_counts,
                    manifest_state="candidate_pending_publication",
                )
            else:
                if finished is None:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_v1_missing_finished")
                finished_manifest = {
                "schema_version": FUNDAMENTAL_READ_SNAPSHOT_SCHEMA,
                "manifest_state": "candidate_pending_publication",
                "snapshot_binding": binding.to_dict(),
                "source_clock": source_clock.to_dict(),
                "cohort_identity_sha256": finished.identity_sha256,
                "finished_cohort": {
                    "session_id": finished.session_id,
                    "reader_session_id": reader_finished.session_id,
                    "processed_stock_codes": list(finished.processed_stock_codes),
                    "result_identity_by_stock": [
                        [code, identity]
                        for code, identity in finished.result_identity_by_stock
                    ],
                    "result_status_counts": [list(item) for item in finished.result_status_counts],
                    "complete": True,
                    "identity_sha256": finished.identity_sha256,
                },
                }
            finished_manifest.pop("manifest_sha256", None)
            finished_manifest["manifest_sha256"] = _canonical_sha256(finished_manifest)
            _write_atomic_json(
                self._attempt.snapshot_root / "finished_source_clock.json",
                finished_manifest,
            )
            _poll_cancel(self._effective_cancel_callback)
            if daily_v2:
                reader = self._daily_monthly_cohort_reader
                if reader is None or self._provider.daily_source_snapshot_reader is not reader:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_v2_reader_changed_before_publication")
                reader.verify_cohort()
                if (type(source_clock) is not FundamentalSnapshotSourceClockV2
                        or reader.pin != source_clock.cohort_pin):
                    raise FundamentalReadSnapshotError("fundamental_snapshot_v2_pin_changed_before_publication")
                _poll_cancel(self._effective_cancel_callback)
            with self._publication_gate:
                if self._state != "open":
                    raise FundamentalReadSnapshotCancelled(
                        "fundamental_snapshot_cancelled_before_publication"
                    )
                finished_manifest["manifest_state"] = "complete"
                finished_manifest.pop("manifest_sha256", None)
                finished_manifest["manifest_sha256"] = _canonical_sha256(
                    finished_manifest
                )
                _write_atomic_json(
                    self._attempt.snapshot_root / "finished_source_clock.json",
                    finished_manifest,
                )
                if daily_v2:
                    if type(source_clock) is not FundamentalSnapshotSourceClockV2:
                        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_clock_kind_mismatch")
                    actual_manifest, actual_raw = _read_canonical_json_file(
                        self._attempt.snapshot_root / "finished_source_clock.json",
                        max_bytes=MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES,
                    )
                    if actual_manifest != finished_manifest or actual_raw != _canonical_json_bytes(finished_manifest):
                        raise FundamentalReadSnapshotError("fundamental_snapshot_v2_publication_bytes_mismatch")
                    finished = parse_finished_snapshot_cohort_v2(actual_manifest, source_clock)
                if finished is None:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_missing_finished")
                self._state = "finished"
                self._finished = finished
                published = True
            _write_attempt_status(
                self._attempt.snapshot_root,
                status="complete",
                reason=None,
                source_clock_sha256=source_clock.identity_sha256,
                cohort_sha256=finished.identity_sha256,
            )
            return finished
        except BaseException as exc:
            if published:
                raise FundamentalReadSnapshotError(
                    "fundamental_snapshot_finished_but_status_write_failed"
                ) from exc
            with self._publication_gate:
                self._state = "cancelled" if isinstance(
                    exc, (FundamentalReadSessionCancelled, FundamentalReadSnapshotCancelled)
                ) else "failed"
            reader_cleanup_error: BaseException | None = None
            try:
                self._read_session.close()
            except BaseException as close_exc:
                reader_cleanup_error = close_exc
            if not self._read_session.closed and reader_cleanup_error is None:
                reader_cleanup_error = FundamentalReadSnapshotError(
                    "fundamental_snapshot_reader_connection_remains_open_after_finish_failure"
                )
            if reader_cleanup_error is not None:
                raise FundamentalReadSnapshotError(
                    "fundamental_snapshot_finish_failed_and_reader_cleanup_failed"
                ) from BaseExceptionGroup(
                    "primary snapshot finish failure and reader cleanup failure",
                    [exc, reader_cleanup_error],
                )
            try:
                _write_attempt_status(
                    self._attempt.snapshot_root,
                    status="cancelled" if self._state == "cancelled" else "failed",
                    reason=f"finish_failed:{type(exc).__name__}",
                )
            except BaseException as status_exc:
                raise FundamentalReadSnapshotError(
                    "fundamental_snapshot_finish_failed_and_status_write_failed"
                ) from BaseExceptionGroup(
                    "primary snapshot finish failure and attempt-status failure",
                    [exc, status_exc],
                )
            raise

    def cancel(self) -> bool:
        """可跨執行緒要求取消；connection 必須由 owner thread close。"""

        with self._publication_gate:
            if self._state == "finished":
                return False
            if self._state in {"cancelled", "failed"}:
                return True
            self._state = "cancelled"
            self._cancel_event.set()
        self._read_session.cancel()
        _write_attempt_status(
            self._attempt.snapshot_root,
            status="cancelled",
            reason="cancel_requested",
        )
        return True

    def close(self) -> None:
        """由建立 session 的 thread 關閉唯讀副本；不會產生 finished token。"""

        self._require_owner_thread()
        cancel_error: BaseException | None = None
        if self._state == "open":
            try:
                self.cancel()
            except BaseException as exc:
                cancel_error = exc
        close_error: BaseException | None = None
        try:
            self._read_session.close()
        except BaseException as exc:
            close_error = exc
        if not self._read_session.closed:
            close_error = close_error or FundamentalReadSnapshotError(
                "fundamental_snapshot_reader_connection_not_closed"
            )
        errors = [error for error in (cancel_error, close_error) if error is not None]
        if len(errors) == 1:
            raise errors[0]
        if len(errors) == 2:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_cancel_and_reader_cleanup_failed"
            ) from BaseExceptionGroup("snapshot cancel and cleanup failures", errors)

    def __enter__(self) -> FundamentalReadSnapshotSession:
        self._require_owner_thread()
        self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> Literal[False]:
        try:
            self.close()
        except BaseException as cleanup_exc:
            if exc is not None:
                raise FundamentalReadSnapshotError(
                    "fundamental_snapshot_context_exit_cleanup_failed"
                ) from BaseExceptionGroup(
                    "primary context exception and snapshot cleanup exception",
                    [exc, cleanup_exc],
                )
            raise
        return False

    def _effective_cancel_callback(self) -> bool:
        if self._cancel_event.is_set():
            return True
        if self._cancel_callback is None:
            return False
        return self._cancel_callback()

    def _require_open(self) -> None:
        if self._state != "open":
            raise FundamentalReadSnapshotError(
                f"fundamental_snapshot_session_{self._state}"
            )

    def _require_owner_thread(self) -> None:
        if get_ident() != self._owner_thread_id:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_session_thread_affinity_violation"
            )


def _capture_snapshot_from_reference(
    provider: RecommendationCurrentFundamentalProvider,
    *,
    source_reference: _VerifiedSnapshotReference | _VerifiedSnapshotReferenceV2,
    snapshot_root: Path | str,
    cancel_callback: Callable[[], bool] | None,
) -> _SnapshotAttempt:
    """只從已核驗 snapshot 的 captured bytes 建立新 attempt，不開原件 SQLite。"""

    source_database_path = _safe_source_database_path(
        source_reference.source_clock.database_path
    )
    if provider.db_file != source_database_path:
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_provider_database_mismatch")
    root = _validate_snapshot_root(
        snapshot_root,
        source_database_path=source_database_path,
        provider=provider,
    )
    snapshot_id = uuid4().hex
    attempt_root = root / snapshot_id
    try:
        root.mkdir(parents=True, exist_ok=True)
        _reject_reparse_components(root)
        attempt_root.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise FundamentalReadSnapshotError("fundamental_snapshot_id_collision") from exc
    _write_attempt_status(attempt_root, status="capturing", reason=None)
    captured_dir = attempt_root / "captured"
    reader_dir = attempt_root / "reader"
    captured_dir.mkdir()
    reader_dir.mkdir()
    try:
        _poll_cancel(cancel_callback)
        source_pins_start = _pin_source_file_set(
            source_database_path,
            cancel_callback=cancel_callback,
        )
        binding = source_reference.binding
        if (
            source_pins_start != binding.source_file_pins_start
            or source_pins_start != binding.source_file_pins_finish
        ):
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_source_database_changed")
        header = _read_sqlite_header(source_database_path)
        journal_mode, wal_sidecar_state = _qualify_sqlite_sidecars(
            source_database_path,
            source_pins_start,
            header,
            cancel_callback=cancel_callback,
        )
        if (
            journal_mode != binding.sqlite_journal_mode
            or wal_sidecar_state != binding.wal_sidecar_state
        ):
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_sqlite_sidecar_state_changed")
        _verify_reference_capture_pins(
            source_reference.source_clock,
            monthly_source_root=provider.monthly_source_root,
            cancel_callback=cancel_callback,
        )
        source_copy_bytes = sum(
            pin.size_bytes or 0 for pin in source_pins_start if pin.present
        )
        if source_copy_bytes != binding.source_copy_bytes:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_source_copy_size_mismatch")
        source_snapshot_sha256 = _canonical_sha256(
            {
                "schema_version": FUNDAMENTAL_READ_SNAPSHOT_SCHEMA,
                "source_database_path": str(source_database_path),
                "source_file_pins": [pin.to_dict() for pin in source_pins_start],
                "captured_files": [item.to_dict() for item in binding.captured_files],
            }
        )
        if source_snapshot_sha256 != binding.source_snapshot_sha256:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_source_snapshot_changed")

        captured_refs: list[FundamentalReadSnapshotFileReference] = []
        captured_pins: list[FundamentalFilePin] = []
        original_root = Path(source_reference.reference.snapshot_root)
        source_pins_by_role = {pin.role: pin for pin in binding.source_file_pins_start}
        for source_ref in binding.captured_files:
            _poll_cancel(cancel_callback)
            source_pin = source_pins_by_role.get(source_ref.role)
            if source_pin is None or not source_pin.present:
                raise FundamentalReadSnapshotError("fundamental_snapshot_exact_copy_role_mismatch")
            if source_ref.role != source_pin.role:
                raise FundamentalReadSnapshotError("fundamental_snapshot_exact_copy_role_mismatch")
            source_path = _attempt_reference_path(original_root, source_ref.relative_path)
            destination = captured_dir / source_path.name
            copied_size, copied_sha = _copy_file_bounded(
                source_path,
                destination,
                max_bytes=MAX_SNAPSHOT_SOURCE_FILE_BYTES,
                cancel_callback=cancel_callback,
            )
            if copied_size != source_ref.size_bytes or copied_sha != source_ref.sha256:
                raise FundamentalReadSnapshotError("fundamental_snapshot_exact_saved_capture_copy_mismatch")
            _make_read_only(destination)
            destination_ref = FundamentalReadSnapshotFileReference(
                role=source_ref.role,
                relative_path=destination.relative_to(attempt_root).as_posix(),
                size_bytes=copied_size,
                sha256=copied_sha,
            )
            destination_pin = _pin_file(
                source_ref.role,
                destination,
                required=True,
                cancel_callback=cancel_callback,
            )
            _require_single_link(destination, "captured")
            if destination_pin.size_bytes != copied_size or destination_pin.sha256 != copied_sha:
                raise FundamentalReadSnapshotError("fundamental_snapshot_exact_new_capture_pin_mismatch")
            captured_refs.append(destination_ref)
            captured_pins.append(destination_pin)

        source_pins_after_copy = _pin_source_file_set(
            source_database_path,
            cancel_callback=cancel_callback,
        )
        if source_pins_after_copy != source_pins_start:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_source_changed_during_copy")
        _verify_reference_capture_pins(
            source_reference.source_clock,
            monthly_source_root=provider.monthly_source_root,
            cancel_callback=cancel_callback,
        )
        reader_refs: list[FundamentalReadSnapshotFileReference] = []
        for capture_ref in captured_refs:
            _poll_cancel(cancel_callback)
            captured_path = attempt_root / Path(capture_ref.relative_path)
            reader_path = reader_dir / captured_path.name
            copied_size, copied_sha = _copy_file_bounded(
                captured_path,
                reader_path,
                max_bytes=MAX_SNAPSHOT_SOURCE_FILE_BYTES,
                cancel_callback=cancel_callback,
            )
            if copied_size != capture_ref.size_bytes or copied_sha != capture_ref.sha256:
                raise FundamentalReadSnapshotError("fundamental_snapshot_exact_new_reader_copy_mismatch")
            _require_single_link(reader_path, "reader")
            reader_refs.append(
                FundamentalReadSnapshotFileReference(
                    role=capture_ref.role,
                    relative_path=reader_path.relative_to(attempt_root).as_posix(),
                    size_bytes=copied_size,
                    sha256=copied_sha,
                )
            )
        reader_database_path = reader_dir / source_database_path.name
        if not (captured_dir / source_database_path.name).is_file() or not reader_database_path.is_file():
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_main_copy_missing")
        captured_manifest_files = tuple(captured_refs)
        reader_manifest_files = tuple(reader_refs)
        _write_snapshot_capture_manifest(
            attempt_root,
            snapshot_id=snapshot_id,
            source_database_path=source_database_path,
            source_pins=source_pins_start,
            captured_files=captured_manifest_files,
            reader_files=reader_manifest_files,
            journal_mode=journal_mode,
            wal_sidecar_state=wal_sidecar_state,
            source_snapshot_sha256=source_snapshot_sha256,
            source_copy_bytes=source_copy_bytes,
        )
        capture_manifest_pin_start = _pin_file(
            "snapshot_capture_manifest",
            attempt_root / "snapshot_capture.json",
            required=True,
            cancel_callback=cancel_callback,
        )
        _poll_cancel(cancel_callback)
        return _SnapshotAttempt(
            snapshot_id=snapshot_id,
            snapshot_root=attempt_root,
            source_database_path=source_database_path,
            reader_database_path=reader_database_path,
            source_file_pins_start=source_pins_start,
            source_file_pins_after_copy=source_pins_after_copy,
            captured_files=captured_manifest_files,
            captured_file_pins_start=tuple(captured_pins),
            capture_manifest_pin_start=capture_manifest_pin_start,
            reader_files=reader_manifest_files,
            sqlite_journal_mode=journal_mode,
            wal_sidecar_state=wal_sidecar_state,
            source_snapshot_sha256=source_snapshot_sha256,
            source_copy_bytes=source_copy_bytes,
        )
    except BaseException as exc:
        _write_attempt_status(
            attempt_root,
            status="cancelled" if isinstance(exc, FundamentalReadSnapshotCancelled) else "failed",
            reason=f"exact_snapshot_copy_failed:{type(exc).__name__}",
        )
        raise


def _reverify_archived_subject(
    verified: _VerifiedArchivedSnapshotReference | _VerifiedArchivedSnapshotReferenceV2,
    *, provider: RecommendationCurrentFundamentalProvider,
    cancel_callback: Callable[[], bool] | None,
) -> _VerifiedArchivedSnapshotReference | _VerifiedArchivedSnapshotReferenceV2:
    from data_module.fundamental_read_snapshot_raw_archive_io_v2 import (
        _VerifiedArchivedSnapshotReferenceV2, reverify_raw_archive_reference_v2,
    )
    if type(verified) is _VerifiedArchivedSnapshotReferenceV2:
        original = _clone_provider_for_reader(provider,
            reader_database_path=Path(verified.snapshot.source_clock.database_path),
            monthly_source_root=Path(verified.archive_reference.original_monthly_source_root))
        reader = provider.daily_source_snapshot_reader
        if type(reader) is not DailyMonthlyRevenueCohortReader:
            raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archive_missing_daily_reader")
        original.daily_source_snapshot_reader = reader
        return reverify_raw_archive_reference_v2(verified, provider=original,
            daily_monthly_cohort_reader=reader, cancel_callback=cancel_callback)
    if type(verified) is not _VerifiedArchivedSnapshotReference:
        raise FundamentalReadSnapshotError("fundamental_snapshot_archived_reference_kind_mismatch")
    roots = _RawArchiveVerificationRoots(output_root=provider.output_root,
        monthly_source_root=Path(verified.archive_reference.original_monthly_source_root))
    return _verify_raw_archive_reference(verified.archive_reference, provider=roots,
                                       cancel_callback=cancel_callback)


def _capture_snapshot_from_archived_reference(
    provider: RecommendationCurrentFundamentalProvider,
    *,
    verified_reference: _VerifiedArchivedSnapshotReference | _VerifiedArchivedSnapshotReferenceV2,
    snapshot_root: Path | str,
    cancel_callback: Callable[[], bool] | None,
) -> _SnapshotAttempt:
    """由 saved captured DB/WAL/SHM bytes 建新 operation，不讀任何 live source。"""

    _poll_cancel(cancel_callback)
    from data_module.fundamental_read_snapshot_raw_archive_io_v2 import _VerifiedArchivedSnapshotReferenceV2
    verified = _reverify_archived_subject(verified_reference, provider=provider,
                                        cancel_callback=cancel_callback)
    source_database_path = Path(verified.snapshot.source_clock.database_path)
    original_binding = verified.snapshot.binding
    root = _validate_snapshot_root(
        snapshot_root,
        source_database_path=source_database_path,
        provider=provider,
    )
    if type(verified) is _VerifiedArchivedSnapshotReferenceV2:
        archive_root = Path(verified.archive_reference.archive_root)
    elif type(verified) is _VerifiedArchivedSnapshotReference:
        archive_root = Path(verified.archive_reference.raw_archive_root)
    else:
        raise FundamentalReadSnapshotError("fundamental_snapshot_archived_reference_kind_mismatch")
    if _paths_overlap(root, archive_root) or _paths_overlap(
        root, Path(verified.archive_reference.snapshot_reference.snapshot_root)
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_archived_operation_root_overlap")
    snapshot_id = uuid4().hex
    attempt_root = root / snapshot_id
    try:
        root.mkdir(parents=True, exist_ok=True)
        _reject_reparse_components(root)
        attempt_root.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise FundamentalReadSnapshotError("fundamental_snapshot_id_collision") from exc
    _write_attempt_status(attempt_root, status="capturing", reason=None)
    captured_dir = attempt_root / "captured"
    reader_dir = attempt_root / "reader"
    captured_dir.mkdir()
    reader_dir.mkdir()
    try:
        source_pins = original_binding.source_file_pins_start
        source_copy_bytes = original_binding.source_copy_bytes
        if (
            source_pins != original_binding.source_file_pins_after_copy
            or source_pins != original_binding.source_file_pins_finish
            or source_copy_bytes != sum(pin.size_bytes or 0 for pin in source_pins if pin.present)
        ):
            raise FundamentalReadSnapshotError("fundamental_snapshot_archived_database_pins_inconsistent")
        source_captured_root = Path(verified.archive_reference.archived_snapshot_root
            if type(verified) is _VerifiedArchivedSnapshotReferenceV2
            else verified.archive_reference.snapshot_reference.snapshot_root)
        captured_refs: list[FundamentalReadSnapshotFileReference] = []
        captured_pins: list[FundamentalFilePin] = []
        for source_ref, expected_pin in zip(
            original_binding.captured_files,
            original_binding.captured_file_pins_start,
            strict=True,
        ):
            _poll_cancel(cancel_callback)
            source_path = _attempt_reference_path(source_captured_root, source_ref.relative_path)
            source_pin = _pin_file(
                source_ref.role, source_path, required=True, cancel_callback=cancel_callback
            )
            expected_physical = expected_pin
            if type(verified) is _VerifiedArchivedSnapshotReferenceV2:
                matching = tuple((entry, pin) for entry, pin in zip(
                    verified.archive_reference.snapshot_files,
                    verified.archive_all_file_pins[:len(verified.archive_reference.snapshot_files)], strict=True)
                    if entry.historical_pin == expected_pin)
                if len(matching) != 1:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_v2_archived_saved_pin_missing")
                expected_physical = matching[0][1]
            if (
                source_pin != expected_physical
                or source_pin.sha256 != source_ref.sha256
                or source_pin.size_bytes != source_ref.size_bytes
            ):
                raise FundamentalReadSnapshotError("fundamental_snapshot_archived_saved_db_copy_changed")
            destination = captured_dir / Path(source_ref.relative_path).name
            copied_size, copied_sha = _copy_file_bounded(
                source_path,
                destination,
                max_bytes=MAX_SNAPSHOT_SOURCE_FILE_BYTES,
                cancel_callback=cancel_callback,
            )
            _make_read_only(destination)
            destination_pin = _pin_file(
                source_ref.role, destination, required=True, cancel_callback=cancel_callback
            )
            _require_single_link(destination, "captured")
            if (
                copied_size != source_ref.size_bytes
                or copied_sha != source_ref.sha256
                or destination_pin.size_bytes != copied_size
                or destination_pin.sha256 != copied_sha
            ):
                raise FundamentalReadSnapshotError("fundamental_snapshot_archived_operation_capture_copy_mismatch")
            captured_refs.append(
                FundamentalReadSnapshotFileReference(
                    role=source_ref.role,
                    relative_path=destination.relative_to(attempt_root).as_posix(),
                    size_bytes=copied_size,
                    sha256=copied_sha,
                )
            )
            captured_pins.append(destination_pin)

        reader_refs: list[FundamentalReadSnapshotFileReference] = []
        for capture_ref in captured_refs:
            _poll_cancel(cancel_callback)
            captured_path = attempt_root / Path(capture_ref.relative_path)
            reader_path = reader_dir / captured_path.name
            copied_size, copied_sha = _copy_file_bounded(
                captured_path,
                reader_path,
                max_bytes=MAX_SNAPSHOT_SOURCE_FILE_BYTES,
                cancel_callback=cancel_callback,
            )
            _require_single_link(reader_path, "reader")
            if copied_size != capture_ref.size_bytes or copied_sha != capture_ref.sha256:
                raise FundamentalReadSnapshotError("fundamental_snapshot_archived_operation_reader_copy_mismatch")
            reader_refs.append(
                FundamentalReadSnapshotFileReference(
                    role=capture_ref.role,
                    relative_path=reader_path.relative_to(attempt_root).as_posix(),
                    size_bytes=copied_size,
                    sha256=copied_sha,
                )
            )
        reader_database_path = reader_dir / source_database_path.name
        if not (captured_dir / source_database_path.name).is_file() or not reader_database_path.is_file():
            raise FundamentalReadSnapshotError("fundamental_snapshot_archived_main_copy_missing")
        captured_tuple = tuple(captured_refs)
        reader_tuple = tuple(reader_refs)
        _write_snapshot_capture_manifest(
            attempt_root,
            snapshot_id=snapshot_id,
            source_database_path=source_database_path,
            source_pins=source_pins,
            captured_files=captured_tuple,
            reader_files=reader_tuple,
            journal_mode=original_binding.sqlite_journal_mode,
            wal_sidecar_state=original_binding.wal_sidecar_state,
            source_snapshot_sha256=original_binding.source_snapshot_sha256,
            source_copy_bytes=source_copy_bytes,
        )
        capture_manifest_pin = _pin_file(
            "snapshot_capture_manifest",
            attempt_root / "snapshot_capture.json",
            required=True,
            cancel_callback=cancel_callback,
        )
        final_verified = _reverify_archived_subject(verified, provider=provider,
                                                  cancel_callback=cancel_callback)
        if (
            final_verified.snapshot_manifest_pin != verified.snapshot_manifest_pin
            or final_verified.archive_manifest_pin != verified.archive_manifest_pin
            or final_verified.archive_file_pins != verified.archive_file_pins
            or final_verified != verified
        ):
            raise FundamentalReadSnapshotError("fundamental_snapshot_archived_source_changed_during_copy")
        _poll_cancel(cancel_callback)
        return _SnapshotAttempt(
            snapshot_id=snapshot_id,
            snapshot_root=attempt_root,
            source_database_path=source_database_path,
            reader_database_path=reader_database_path,
            source_file_pins_start=source_pins,
            source_file_pins_after_copy=source_pins,
            captured_files=captured_tuple,
            captured_file_pins_start=tuple(captured_pins),
            capture_manifest_pin_start=capture_manifest_pin,
            reader_files=reader_tuple,
            sqlite_journal_mode=original_binding.sqlite_journal_mode,
            wal_sidecar_state=original_binding.wal_sidecar_state,
            source_snapshot_sha256=original_binding.source_snapshot_sha256,
            source_copy_bytes=source_copy_bytes,
        )
    except BaseException as exc:
        _write_attempt_status(
            attempt_root,
            status="cancelled" if isinstance(exc, FundamentalReadSnapshotCancelled) else "failed",
            reason=f"archived_snapshot_copy_failed:{type(exc).__name__}",
        )
        raise


def _capture_snapshot(
    provider: RecommendationCurrentFundamentalProvider,
    *,
    snapshot_root: Path | str,
    cancel_callback: Callable[[], bool] | None,
) -> _SnapshotAttempt:
    source_database_path = _safe_source_database_path(provider.db_file)
    root = _validate_snapshot_root(
        snapshot_root,
        source_database_path=source_database_path,
        provider=provider,
    )
    snapshot_id = uuid4().hex
    attempt_root = root / snapshot_id
    try:
        root.mkdir(parents=True, exist_ok=True)
        _reject_reparse_components(root)
        attempt_root.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise FundamentalReadSnapshotError("fundamental_snapshot_id_collision") from exc
    _write_attempt_status(attempt_root, status="capturing", reason=None)
    captured_dir = attempt_root / "captured"
    reader_dir = attempt_root / "reader"
    captured_dir.mkdir()
    reader_dir.mkdir()

    try:
        _poll_cancel(cancel_callback)
        source_pins_start = _pin_source_file_set(
            source_database_path,
            cancel_callback=cancel_callback,
        )
        header = _read_sqlite_header(source_database_path)
        try:
            journal_mode, wal_sidecar_state = _qualify_sqlite_sidecars(
                source_database_path,
                source_pins_start,
                header,
            cancel_callback=cancel_callback,
            )
        except FundamentalReadSnapshotError as qualification_error:
            if any(
                pin.role == "sqlite_rollback_journal" and pin.present
                for pin in source_pins_start
            ):
                source_pins_finish = _pin_source_file_set(
                    source_database_path,
                    cancel_callback=cancel_callback,
                )
                if source_pins_finish != source_pins_start:
                    raise FundamentalReadSnapshotError(
                        "fundamental_snapshot_source_changed_with_rollback_journal"
                    ) from qualification_error
            raise
        source_copy_bytes = sum(
            pin.size_bytes or 0 for pin in source_pins_start if pin.present
        )

        captured_files: list[FundamentalReadSnapshotFileReference] = []
        captured_file_pins_start: list[FundamentalFilePin] = []
        for pin in source_pins_start:
            _poll_cancel(cancel_callback)
            if not pin.present:
                continue
            source_path = Path(pin.path)
            captured_path = captured_dir / source_path.name
            size, digest = _copy_file_bounded(
                source_path,
                captured_path,
                max_bytes=MAX_SNAPSHOT_SOURCE_FILE_BYTES,
                cancel_callback=cancel_callback,
            )
            if size != pin.size_bytes or digest != pin.sha256:
                raise FundamentalReadSnapshotError(
                    f"fundamental_snapshot_source_copy_mismatch:{pin.role}"
                )
            captured_files.append(
                FundamentalReadSnapshotFileReference(
                    role=pin.role,
                    relative_path=captured_path.relative_to(attempt_root).as_posix(),
                    size_bytes=size,
                    sha256=digest,
                )
            )
            _make_read_only(captured_path)
            captured_file_pins_start.append(
                _pin_file(
                    pin.role,
                    captured_path,
                    required=True,
                    cancel_callback=cancel_callback,
                )
            )

        source_pins_after_copy = _pin_source_file_set(
            source_database_path,
            cancel_callback=cancel_callback,
        )
        if source_pins_after_copy != source_pins_start:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_original_source_changed_during_copy"
            )
        _poll_cancel(cancel_callback)

        reader_files: list[FundamentalReadSnapshotFileReference] = []
        for source_ref in captured_files:
            _poll_cancel(cancel_callback)
            captured_path = attempt_root / Path(source_ref.relative_path)
            reader_path = reader_dir / captured_path.name
            size, digest = _copy_file_bounded(
                captured_path,
                reader_path,
                max_bytes=MAX_SNAPSHOT_SOURCE_FILE_BYTES,
                cancel_callback=cancel_callback,
            )
            if size != source_ref.size_bytes or digest != source_ref.sha256:
                raise FundamentalReadSnapshotError(
                    f"fundamental_snapshot_reader_copy_mismatch:{source_ref.role}"
                )
            reader_files.append(
                FundamentalReadSnapshotFileReference(
                    role=source_ref.role,
                    relative_path=reader_path.relative_to(attempt_root).as_posix(),
                    size_bytes=size,
                    sha256=digest,
                )
            )

        captured_main = captured_dir / source_database_path.name
        reader_database_path = reader_dir / source_database_path.name
        if not captured_main.is_file() or not reader_database_path.is_file():
            raise FundamentalReadSnapshotError("fundamental_snapshot_main_copy_missing")
        source_snapshot_sha256 = _canonical_sha256(
            {
                "schema_version": FUNDAMENTAL_READ_SNAPSHOT_SCHEMA,
                "source_database_path": str(source_database_path),
                "source_file_pins": [pin.to_dict() for pin in source_pins_start],
                "captured_files": [item.to_dict() for item in captured_files],
            }
        )
        _write_snapshot_capture_manifest(
            attempt_root,
            snapshot_id=snapshot_id,
            source_database_path=source_database_path,
            source_pins=source_pins_start,
            captured_files=tuple(captured_files),
            reader_files=tuple(reader_files),
            journal_mode=journal_mode,
            wal_sidecar_state=wal_sidecar_state,
            source_snapshot_sha256=source_snapshot_sha256,
            source_copy_bytes=source_copy_bytes,
        )
        capture_manifest_pin_start = _pin_file(
            "snapshot_capture_manifest",
            attempt_root / "snapshot_capture.json",
            required=True,
            cancel_callback=cancel_callback,
        )
        return _SnapshotAttempt(
            snapshot_id=snapshot_id,
            snapshot_root=attempt_root,
            source_database_path=source_database_path,
            reader_database_path=reader_database_path,
            source_file_pins_start=source_pins_start,
            source_file_pins_after_copy=source_pins_after_copy,
            captured_files=tuple(captured_files),
            captured_file_pins_start=tuple(captured_file_pins_start),
            capture_manifest_pin_start=capture_manifest_pin_start,
            reader_files=tuple(reader_files),
            sqlite_journal_mode=journal_mode,
            wal_sidecar_state=wal_sidecar_state,
            source_snapshot_sha256=source_snapshot_sha256,
            source_copy_bytes=source_copy_bytes,
        )
    except BaseException as exc:
        _write_attempt_status(
            attempt_root,
            status="cancelled" if isinstance(exc, FundamentalReadSnapshotCancelled) else "failed",
            reason=f"snapshot_capture_failed:{type(exc).__name__}",
        )
        raise


def _clone_provider_for_reader(
    provider: RecommendationCurrentFundamentalProvider,
    *,
    reader_database_path: Path,
    monthly_source_root: Path | None = None,
) -> RecommendationCurrentFundamentalProvider:
    """沿公開 constructor 建立 copy-bound provider，不改原 instance。"""

    return RecommendationCurrentFundamentalProvider(
        db_file=reader_database_path,
        output_root=provider.output_root,
        monthly_source_root=(
            provider.monthly_source_root
            if monthly_source_root is None
            else monthly_source_root
        ),
        valuation_provider_factory=provider._valuation_provider_factory,
        calendar_cache_path=provider.calendar_cache_path,
        temporary_closure_path=provider.temporary_closure_path,
    )


def _make_copy_binding(
    attempt: _SnapshotAttempt,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> FundamentalReadCopyBinding:
    """由已寫好的 attempt 產生 typed binding，讀取器仍會自行重驗。"""

    manifest_pin = _pin_file(
        "snapshot_capture_manifest",
        attempt.snapshot_root / "snapshot_capture.json",
        required=True,
        cancel_callback=cancel_callback,
    )
    if manifest_pin != attempt.capture_manifest_pin_start:
        raise FundamentalReadSnapshotError("fundamental_snapshot_capture_manifest_changed_before_open")
    reader_pins = _pin_reader_file_set(
        attempt.reader_database_path,
        cancel_callback=cancel_callback,
    )
    return FundamentalReadCopyBinding(
        snapshot_id=attempt.snapshot_id,
        snapshot_root=str(attempt.snapshot_root),
        source_database_path=str(attempt.source_database_path),
        reader_database_path=str(attempt.reader_database_path),
        source_file_pins=attempt.source_file_pins_start,
        captured_files=attempt.captured_files,
        reader_files=attempt.reader_files,
        capture_manifest_pin=manifest_pin,
        reader_file_pins_before_open=reader_pins,
        sqlite_journal_mode=attempt.sqlite_journal_mode,
        wal_sidecar_state=attempt.wal_sidecar_state,
        source_snapshot_sha256=attempt.source_snapshot_sha256,
        source_copy_bytes=attempt.source_copy_bytes,
    )


def _make_archived_copy_binding(
    attempt: _SnapshotAttempt,
    *,
    verified_reference: _VerifiedArchivedSnapshotReference,
    cancel_callback: Callable[[], bool] | None,
) -> FundamentalReadArchivedCopyBinding:
    operation_binding = _make_copy_binding(attempt, cancel_callback=cancel_callback)
    archive_reference = verified_reference.archive_reference
    capture_pairs: list[FundamentalReadArchivedFilePinPair] = []
    for file_reference, archive_pin in zip(
        archive_reference.files,
        verified_reference.archive_file_pins,
        strict=True,
    ):
        _poll_cancel(cancel_callback)
        capture_pairs.append(
            FundamentalReadArchivedFilePinPair(
                historical_pin=file_reference.historical_pin,
                archive_pin=archive_pin,
            )
        )
    return _issue_archived_copy_binding(
        issuer_anchor=_ARCHIVED_BINDING_ISSUER,
        operation_copy_binding=operation_binding,
        historical_snapshot_root=archive_reference.snapshot_reference.snapshot_root,
        archive_root=archive_reference.raw_archive_root,
        archived_monthly_source_root=archive_reference.archived_monthly_source_root,
        snapshot_reference_identity_sha256=archive_reference.snapshot_reference.identity_sha256,
        source_clock_identity_sha256=archive_reference.source_clock_identity_sha256,
        source_content_identity_sha256=archive_reference.source_content_identity_sha256,
        cohort_identity_sha256=archive_reference.cohort_identity_sha256,
        raw_archive_identity_sha256=archive_reference.archive_identity_sha256,
        snapshot_manifest_pin=verified_reference.snapshot_manifest_pin,
        archive_manifest_pin=verified_reference.archive_manifest_pin,
        historical_source_pins=tuple(
            FundamentalReadCopyFilePin(
                role=pin.role,
                path=pin.path,
                present=pin.present,
                device=pin.device,
                inode=pin.inode,
                size_bytes=pin.size_bytes,
                mtime_ns=pin.mtime_ns,
                mode=pin.mode,
                sha256=pin.sha256,
            )
            for pin in verified_reference.snapshot.binding.source_file_pins_start
        ),
        capture_file_pairs=tuple(capture_pairs),
        archive_file_pins=tuple(pair.archive_pin for pair in capture_pairs),
    )


def _verify_copy_binding_for_provider(
    binding: FundamentalReadCopyBinding,
    *,
    provider: RecommendationCurrentFundamentalProvider,
    cancel_callback: Callable[[], bool] | None,
) -> None:
    try:
        binding.verify_before_open(
            database_path=binding.reader_database_path,
            provider_database_path=provider.db_file,
            protected_roots=(
                provider.output_root,
                provider.monthly_source_root,
                Path(os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data")),
            ),
            cancel_callback=cancel_callback,
        )
    except FundamentalReadCopyBindingCancelled as exc:
        raise FundamentalReadSnapshotCancelled(str(exc)) from exc
    except FundamentalReadCopyBindingError as exc:
        raise FundamentalReadSnapshotError(f"fundamental_snapshot_copy_binding_invalid:{exc}") from exc


def _safe_source_database_path(database_path: Path | str) -> Path:
    raw = Path(database_path).expanduser()
    if not raw.is_absolute():
        raise FundamentalReadSnapshotError("fundamental_snapshot_source_path_not_absolute")
    _reject_reparse_components(raw)
    canonical = Path(os.path.abspath(raw))
    current = canonical.lstat()
    _require_regular_non_reparse(canonical, current, "sqlite_main")
    return canonical


def _validate_snapshot_root(
    snapshot_root: Path | str,
    *,
    source_database_path: Path,
    provider: RecommendationCurrentFundamentalProvider,
) -> Path:
    raw = Path(snapshot_root).expanduser()
    if not raw.is_absolute():
        raise FundamentalReadSnapshotError("fundamental_snapshot_root_not_absolute")
    _reject_reparse_components(raw, allow_missing=True)
    root = Path(os.path.abspath(raw))
    protected: list[Path] = [
        source_database_path.parent,
        provider.output_root,
        provider.monthly_source_root,
        Path(os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data")),
    ]
    if bool(getattr(sys, "frozen", False)):
        protected.append(Path(sys.executable).parent)
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root is not None:
            protected.append(Path(bundle_root))
    for protected_root in protected:
        normalized = Path(os.path.abspath(protected_root.expanduser()))
        if _paths_overlap(root, normalized):
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_root_overlaps_source_or_formal_data_root"
            )
    return root


def _paths_overlap(left: Path, right: Path) -> bool:
    try:
        left.relative_to(right)
        return True
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return True
    except ValueError:
        return False


def _pin_source_file_set(
    database_path: Path,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> tuple[FundamentalFilePin, ...]:
    pins: list[FundamentalFilePin] = []
    for role, path, required in (
        ("sqlite_main", database_path, True),
        ("sqlite_wal", Path(f"{database_path}-wal"), False),
        ("sqlite_shm", Path(f"{database_path}-shm"), False),
        ("sqlite_rollback_journal", Path(f"{database_path}-journal"), False),
    ):
        _poll_cancel(cancel_callback)
        pins.append(
            _pin_file(
                role,
                path,
                required=required,
                cancel_callback=cancel_callback,
            )
        )
    return tuple(pins)


def _pin_reader_file_set(
    database_path: Path,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> tuple[FundamentalFilePin, ...]:
    return _pin_source_file_set(database_path, cancel_callback=cancel_callback)


def _reader_only_sidecar_bytes(
    reader_files: tuple[FundamentalReadSnapshotFileReference, ...],
    reader_pins_finish: tuple[FundamentalFilePin, ...],
) -> int:
    copied_roles = {item.role for item in reader_files}
    return sum(
        pin.size_bytes or 0
        for pin in reader_pins_finish
        if pin.present and pin.role in {"sqlite_wal", "sqlite_shm", "sqlite_rollback_journal"}
        and pin.role not in copied_roles
    )


def _make_read_only(path: Path) -> None:
    try:
        current_mode = stat.S_IMODE(path.stat().st_mode)
        path.chmod(current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
    except OSError as exc:
        raise FundamentalReadSnapshotError(
            f"fundamental_snapshot_captured_file_readonly_failed:{type(exc).__name__}"
        ) from exc


def _pin_file(
    role: str,
    path: Path,
    *,
    required: bool,
    cancel_callback: Callable[[], bool] | None,
) -> FundamentalFilePin:
    _reject_reparse_components(path, allow_missing=True)
    canonical_path = Path(os.path.abspath(path))
    try:
        first = path.lstat()
    except FileNotFoundError:
        if required:
            raise FundamentalReadSnapshotError(f"fundamental_snapshot_source_missing:{role}")
        return FundamentalFilePin(
            role=role,
            path=str(canonical_path),
            present=False,
            device=None,
            inode=None,
            size_bytes=None,
            mtime_ns=None,
            mode=None,
            sha256=None,
        )
    _require_regular_non_reparse(path, first, role)
    if first.st_size < 0 or first.st_size > MAX_SNAPSHOT_SOURCE_FILE_BYTES:
        raise FundamentalReadSnapshotError(
            f"fundamental_snapshot_source_file_over_16gib:{role}"
        )
    digest, byte_count = _hash_file(path, cancel_callback=cancel_callback)
    if byte_count != first.st_size:
        raise FundamentalReadSnapshotError(f"fundamental_snapshot_source_size_changed:{role}")
    second = path.lstat()
    _require_regular_non_reparse(path, second, role)
    if _stat_identity(first) != _stat_identity(second):
        raise FundamentalReadSnapshotError(f"fundamental_snapshot_source_changed_while_hashing:{role}")
    return FundamentalFilePin(
        role=role,
        path=str(canonical_path),
        present=True,
        device=int(second.st_dev),
        inode=int(second.st_ino),
        size_bytes=int(second.st_size),
        mtime_ns=int(second.st_mtime_ns),
        mode=int(stat.S_IMODE(second.st_mode)),
        sha256=digest,
    )


def _hash_file(
    path: Path,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> tuple[str, int]:
    digest = sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            while True:
                _poll_cancel(cancel_callback)
                block = stream.read(SNAPSHOT_COPY_CHUNK_BYTES)
                if not block:
                    break
                digest.update(block)
                total += len(block)
                if total > MAX_SNAPSHOT_SOURCE_FILE_BYTES:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_source_over_16gib")
                _poll_cancel(cancel_callback)
    except FundamentalReadSnapshotCancelled:
        raise
    except OSError as exc:
        raise FundamentalReadSnapshotError(
            f"fundamental_snapshot_source_hash_failed:{type(exc).__name__}"
        ) from exc
    return digest.hexdigest(), total


def _copy_file_bounded(
    source: Path,
    destination: Path,
    *,
    max_bytes: int,
    cancel_callback: Callable[[], bool] | None,
) -> tuple[int, str]:
    _poll_cancel(cancel_callback)
    source_stat = source.lstat()
    _require_regular_non_reparse(source, source_stat, "snapshot_copy_source")
    if source_stat.st_size > max_bytes:
        raise FundamentalReadSnapshotError("fundamental_snapshot_copy_exceeds_16gib")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FundamentalReadSnapshotError("fundamental_snapshot_destination_already_exists")
    digest = sha256()
    total = 0
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(destination, flags, 0o600)
    try:
        with source.open("rb") as input_stream, os.fdopen(fd, "wb", closefd=False) as output_stream:
            while True:
                _poll_cancel(cancel_callback)
                block = input_stream.read(SNAPSHOT_COPY_CHUNK_BYTES)
                if not block:
                    break
                output_stream.write(block)
                digest.update(block)
                total += len(block)
                if total > max_bytes:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_copy_exceeds_16gib")
                _poll_cancel(cancel_callback)
            output_stream.flush()
            os.fsync(output_stream.fileno())
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    else:
        os.close(fd)
    source_after = source.lstat()
    _require_regular_non_reparse(source, source_after, "snapshot_copy_source")
    if _stat_identity(source_stat) != _stat_identity(source_after):
        raise FundamentalReadSnapshotError("fundamental_snapshot_copy_source_changed")
    destination_stat = destination.lstat()
    _require_regular_non_reparse(destination, destination_stat, "snapshot_copy_destination")
    if destination_stat.st_size != total:
        raise FundamentalReadSnapshotError("fundamental_snapshot_copy_destination_size_mismatch")
    persisted_digest, persisted_size = _hash_file(
        destination,
        cancel_callback=cancel_callback,
    )
    if persisted_size != total or persisted_digest != digest.hexdigest():
        raise FundamentalReadSnapshotError("fundamental_snapshot_copy_persisted_bytes_mismatch")
    return total, digest.hexdigest()


@dataclass(frozen=True, slots=True)
class _SQLiteHeader:
    page_size: int
    read_version: int
    write_version: int


def _read_sqlite_header(database_path: Path) -> _SQLiteHeader:
    try:
        with database_path.open("rb") as stream:
            raw = stream.read(100)
    except OSError as exc:
        raise FundamentalReadSnapshotError(
            f"fundamental_snapshot_sqlite_header_read_failed:{type(exc).__name__}"
        ) from exc
    if len(raw) < 100 or raw[:16] != _SQLITE_HEADER:
        raise FundamentalReadSnapshotError("fundamental_snapshot_invalid_sqlite_header")
    page_size = int.from_bytes(raw[16:18], "big")
    if page_size == 1:
        page_size = 65_536
    if page_size < 512 or page_size > 65_536 or page_size & (page_size - 1):
        raise FundamentalReadSnapshotError("fundamental_snapshot_invalid_sqlite_page_size")
    read_version = raw[18]
    write_version = raw[19]
    if (read_version, write_version) not in {(1, 1), (2, 2)}:
        raise FundamentalReadSnapshotError("fundamental_snapshot_invalid_sqlite_journal_header")
    return _SQLiteHeader(page_size, read_version, write_version)


def _qualify_sqlite_sidecars(
    database_path: Path,
    source_pins: tuple[FundamentalFilePin, ...],
    header: _SQLiteHeader,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> tuple[Literal["rollback", "wal"], Literal["complete", "absent", "not_applicable"]]:
    pins = {pin.role: pin for pin in source_pins}
    journal = pins["sqlite_rollback_journal"]
    if journal.present:
        raise FundamentalReadSnapshotError(
            "fundamental_snapshot_rollback_journal_present_refused_without_replay"
        )
    wal = pins["sqlite_wal"]
    shm = pins["sqlite_shm"]
    if header.read_version == 1:
        if wal.present or shm.present:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_rollback_header_has_wal_sidecars"
            )
        return "rollback", "not_applicable"
    if not wal.present and not shm.present:
        return "wal", "absent"
    if wal.present and not shm.present:
        raise FundamentalReadSnapshotError("fundamental_snapshot_wal_sidecar_shm_missing")
    if shm.present and not wal.present:
        raise FundamentalReadSnapshotError("fundamental_snapshot_wal_sidecar_wal_missing")
    _validate_wal_header(
        Path(wal.path),
        header.page_size,
        cancel_callback=cancel_callback,
    )
    return "wal", "complete"


def _validate_wal_header(
    wal_path: Path,
    database_page_size: int,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> None:
    try:
        metadata = wal_path.lstat()
        _require_regular_non_reparse(wal_path, metadata, "sqlite_wal")
        size = metadata.st_size
        with wal_path.open("rb") as stream:
            raw = stream.read(32)
            _poll_cancel(cancel_callback)
            if len(raw) != 32:
                raise FundamentalReadSnapshotError("fundamental_snapshot_wal_header_truncated")
            magic = int.from_bytes(raw[:4], "big")
            version = int.from_bytes(raw[4:8], "big")
            wal_page_size = int.from_bytes(raw[8:12], "big")
            if magic not in _SQLITE_WAL_MAGIC or version != _SQLITE_WAL_VERSION:
                raise FundamentalReadSnapshotError("fundamental_snapshot_wal_header_invalid")
            if wal_page_size != database_page_size:
                raise FundamentalReadSnapshotError("fundamental_snapshot_wal_page_size_mismatch")
            frame_size = 24 + database_page_size
            if size < 32 or (size - 32) % frame_size != 0:
                raise FundamentalReadSnapshotError("fundamental_snapshot_wal_frame_truncated")

            byte_order: Literal["<", ">"] = "<" if magic == 0x377F0682 else ">"
            checksum_1, checksum_2 = _wal_checksum(raw[:24], byte_order, (0, 0))
            stored_header_checksum = struct.unpack(">II", raw[24:32])
            if (checksum_1, checksum_2) != stored_header_checksum:
                raise FundamentalReadSnapshotError("fundamental_snapshot_wal_header_checksum_mismatch")
            salts = raw[16:24]
            frame_count = (size - 32) // frame_size
            for _ in range(frame_count):
                _poll_cancel(cancel_callback)
                frame_header = stream.read(24)
                page_data = stream.read(database_page_size)
                if len(frame_header) != 24 or len(page_data) != database_page_size:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_wal_frame_truncated")
                if frame_header[8:16] != salts:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_wal_frame_salt_mismatch")
                checksum_1, checksum_2 = _wal_checksum(
                    frame_header[:8] + page_data,
                    byte_order,
                    (checksum_1, checksum_2),
                )
                stored_frame_checksum = struct.unpack(">II", frame_header[16:24])
                if (checksum_1, checksum_2) != stored_frame_checksum:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_wal_checksum_mismatch")
                _poll_cancel(cancel_callback)
    except OSError as exc:
        raise FundamentalReadSnapshotError(
            f"fundamental_snapshot_wal_header_read_failed:{type(exc).__name__}"
        ) from exc


def _wal_checksum(
    raw: bytes,
    byte_order: Literal["<", ">"],
    initial: tuple[int, int],
) -> tuple[int, int]:
    if len(raw) % 8 != 0:
        raise FundamentalReadSnapshotError("fundamental_snapshot_wal_checksum_alignment_error")
    checksum_1, checksum_2 = initial
    for offset in range(0, len(raw), 8):
        word_1, word_2 = struct.unpack(f"{byte_order}II", raw[offset : offset + 8])
        checksum_1 = (checksum_1 + word_1 + checksum_2) & 0xFFFFFFFF
        checksum_2 = (checksum_2 + word_2 + checksum_1) & 0xFFFFFFFF
    return checksum_1, checksum_2


def _prime_reader_copy(
    database_path: Path,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> None:
    """只允許 SQLite 在隔離 reader 目錄建立 main-only WAL sidecars。"""

    connection: sqlite3.Connection | None = None
    try:
        _poll_cancel(cancel_callback)
        uri = f"{database_path.as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        connection.execute("PRAGMA schema_version").fetchone()
        database_rows = connection.execute("PRAGMA database_list").fetchall()
        main_path = next(
            (
                Path(os.path.abspath(str(row[2])))
                for row in database_rows
                if row[1] == "main"
            ),
            None,
        )
        if main_path != Path(os.path.abspath(database_path)):
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_reader_prime_opened_wrong_database"
            )
        if int(connection.execute("PRAGMA query_only").fetchone()[0]) != 1:
            raise FundamentalReadSnapshotError("fundamental_snapshot_reader_prime_not_query_only")
        _poll_cancel(cancel_callback)
    except sqlite3.Error as exc:
        raise FundamentalReadSnapshotError(
            f"fundamental_snapshot_reader_prime_sqlite_error:{type(exc).__name__}"
        ) from exc
    finally:
        if connection is not None:
            connection.close()


def _write_snapshot_capture_manifest(
    attempt_root: Path,
    *,
    snapshot_id: str,
    source_database_path: Path,
    source_pins: tuple[FundamentalFilePin, ...],
    captured_files: tuple[FundamentalReadSnapshotFileReference, ...],
    reader_files: tuple[FundamentalReadSnapshotFileReference, ...],
    journal_mode: Literal["rollback", "wal"],
    wal_sidecar_state: Literal["complete", "absent", "not_applicable"],
    source_snapshot_sha256: str,
    source_copy_bytes: int,
) -> None:
    payload = _snapshot_capture_manifest_payload(
        snapshot_id=snapshot_id,
        source_database_path=source_database_path,
        source_pins=source_pins,
        captured_files=captured_files,
        reader_files=reader_files,
        journal_mode=journal_mode,
        wal_sidecar_state=wal_sidecar_state,
        source_snapshot_sha256=source_snapshot_sha256,
        source_copy_bytes=source_copy_bytes,
    )
    path = attempt_root / "snapshot_capture.json"
    _write_atomic_json(path, payload)
    _make_read_only(path)


def _snapshot_capture_manifest_payload(
    *,
    snapshot_id: str,
    source_database_path: Path,
    source_pins: tuple[FundamentalFilePin, ...],
    captured_files: tuple[FundamentalReadSnapshotFileReference, ...],
    reader_files: tuple[FundamentalReadSnapshotFileReference, ...],
    journal_mode: Literal["rollback", "wal"],
    wal_sidecar_state: Literal["complete", "absent", "not_applicable"],
    source_snapshot_sha256: str,
    source_copy_bytes: int,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": FUNDAMENTAL_READ_SNAPSHOT_SCHEMA,
        "snapshot_id": snapshot_id,
        "source_database_path": str(source_database_path),
        "source_file_pins_start": [pin.to_dict() for pin in source_pins],
        "captured_files": [item.to_dict() for item in captured_files],
        "reader_files_before_sqlite_open": [item.to_dict() for item in reader_files],
        "sqlite_journal_mode": journal_mode,
        "wal_sidecar_state": wal_sidecar_state,
        "source_snapshot_sha256": source_snapshot_sha256,
        "source_copy_bytes": source_copy_bytes,
        "duplicated_disk_bytes": source_copy_bytes * 2,
        "manifest_state": "captured_source_copy",
    }
    payload["manifest_sha256"] = _canonical_sha256(payload)
    return payload


def _verify_captured_evidence(
    attempt: _SnapshotAttempt,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> tuple[tuple[FundamentalFilePin, ...], FundamentalFilePin]:
    if len(attempt.captured_files) != len(attempt.captured_file_pins_start):
        raise FundamentalReadSnapshotError("fundamental_snapshot_captured_file_pin_count_mismatch")

    finish_pins: list[FundamentalFilePin] = []
    for reference, expected_pin in zip(
        attempt.captured_files,
        attempt.captured_file_pins_start,
        strict=True,
    ):
        _poll_cancel(cancel_callback)
        path = _attempt_reference_path(attempt.snapshot_root, reference.relative_path)
        current_pin = _pin_file(
            reference.role,
            path,
            required=True,
            cancel_callback=cancel_callback,
        )
        if (
            current_pin != expected_pin
            or current_pin.size_bytes != reference.size_bytes
            or current_pin.sha256 != reference.sha256
        ):
            raise FundamentalReadSnapshotError(
                f"fundamental_snapshot_captured_file_changed_before_finish:{reference.role}"
            )
        finish_pins.append(current_pin)

    manifest_path = attempt.snapshot_root / "snapshot_capture.json"
    manifest_bytes = _read_bounded_regular_file(
        manifest_path,
        max_bytes=MAX_SNAPSHOT_CAPTURE_MANIFEST_BYTES,
        cancel_callback=cancel_callback,
    )
    manifest_payload = _snapshot_capture_manifest_payload(
        snapshot_id=attempt.snapshot_id,
        source_database_path=attempt.source_database_path,
        source_pins=attempt.source_file_pins_start,
        captured_files=attempt.captured_files,
        reader_files=attempt.reader_files,
        journal_mode=attempt.sqlite_journal_mode,
        wal_sidecar_state=attempt.wal_sidecar_state,
        source_snapshot_sha256=attempt.source_snapshot_sha256,
        source_copy_bytes=attempt.source_copy_bytes,
    )
    if manifest_bytes != _canonical_json_bytes(manifest_payload):
        raise FundamentalReadSnapshotError(
            "fundamental_snapshot_capture_manifest_bytes_mismatch"
        )
    manifest_pin_finish = _pin_file(
        "snapshot_capture_manifest",
        manifest_path,
        required=True,
        cancel_callback=cancel_callback,
    )
    if manifest_pin_finish != attempt.capture_manifest_pin_start:
        raise FundamentalReadSnapshotError(
            "fundamental_snapshot_capture_manifest_pin_changed_before_finish"
        )
    return tuple(finish_pins), manifest_pin_finish


def _attempt_reference_path(snapshot_root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if (
        not relative_path
        or relative.is_absolute()
        or "\\" in relative_path
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_unsafe_attempt_reference")
    root = Path(os.path.abspath(snapshot_root))
    path = Path(os.path.abspath(root / relative))
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise FundamentalReadSnapshotError(
            "fundamental_snapshot_attempt_reference_escaped_root"
        ) from exc
    return path


def _read_bounded_regular_file(
    path: Path,
    *,
    max_bytes: int,
    cancel_callback: Callable[[], bool] | None,
) -> bytes:
    _reject_reparse_components(path)
    try:
        first = path.lstat()
    except OSError as exc:
        raise FundamentalReadSnapshotError(
            f"fundamental_snapshot_bounded_read_stat_failed:{type(exc).__name__}"
        ) from exc
    _require_regular_non_reparse(path, first, "capture_manifest")
    if first.st_size < 0 or first.st_size > max_bytes:
        raise FundamentalReadSnapshotError("fundamental_snapshot_capture_manifest_over_limit")
    chunks: list[bytes] = []
    total = 0
    try:
        with path.open("rb") as stream:
            while True:
                _poll_cancel(cancel_callback)
                block = stream.read(min(SNAPSHOT_COPY_CHUNK_BYTES, max_bytes + 1 - total))
                if not block:
                    break
                chunks.append(block)
                total += len(block)
                if total > max_bytes:
                    raise FundamentalReadSnapshotError(
                        "fundamental_snapshot_capture_manifest_over_limit"
                    )
        second = path.lstat()
    except FundamentalReadSnapshotCancelled:
        raise
    except OSError as exc:
        raise FundamentalReadSnapshotError(
            f"fundamental_snapshot_bounded_read_failed:{type(exc).__name__}"
        ) from exc
    _require_regular_non_reparse(path, second, "capture_manifest")
    if total != first.st_size or _stat_identity(first) != _stat_identity(second):
        raise FundamentalReadSnapshotError(
            "fundamental_snapshot_capture_manifest_changed_while_reading"
        )
    _poll_cancel(cancel_callback)
    return b"".join(chunks)


def _write_attempt_status(
    attempt_root: Path,
    *,
    status: Literal["capturing", "failed", "cancelled", "complete"],
    reason: str | None,
    source_clock_sha256: str | None = None,
    cohort_sha256: str | None = None,
    strict: bool = False,
) -> None:
    payload: dict[str, object] = {
        "schema_version": FUNDAMENTAL_READ_SNAPSHOT_SCHEMA,
        "status": status,
        "reason": reason,
        "source_clock_sha256": source_clock_sha256,
        "cohort_sha256": cohort_sha256,
    }
    payload["status_sha256"] = _canonical_sha256(payload)
    try:
        _write_atomic_json(attempt_root / "attempt_status.json", payload)
    except OSError:
        if strict:
            raise
        # 保留原始錯誤為主要原因；未完成目錄留作診斷。
        pass


def _write_atomic_json(path: Path, payload: dict[str, object]) -> None:
    raw = _canonical_json_bytes(payload)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    with open(to_internal_io_path(temporary), "xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(to_internal_io_path(temporary), to_internal_io_path(path))


def _write_create_only_bytes(path: Path, raw: bytes) -> None:
    """以排他建立寫出 manifest；已存在的 archive 絕不覆寫。"""

    if type(raw) is not bytes:
        raise TypeError("create-only manifest 必須是 bytes")
    _reject_reparse_components(path.parent)
    if path.exists() or path.is_symlink():
        raise FundamentalReadSnapshotError("fundamental_snapshot_create_only_target_exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise FundamentalReadSnapshotError("fundamental_snapshot_create_only_target_exists") from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    else:
        os.close(descriptor)
    metadata = path.lstat()
    _require_regular_non_reparse(path, metadata, "raw_archive_manifest")
    if metadata.st_nlink != 1 or metadata.st_size != len(raw):
        raise FundamentalReadSnapshotError("fundamental_snapshot_create_only_manifest_pin_invalid")


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _reject_reparse_components(path: Path, *, allow_missing: bool = False) -> None:
    absolute = path.absolute()
    drive = Path(absolute.anchor)
    current = drive
    for part in absolute.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if allow_missing:
                continue
            raise FundamentalReadSnapshotError("fundamental_snapshot_path_component_missing")
        _reject_reparse(current, metadata)


def _reject_reparse(path: Path, metadata: os.stat_result) -> None:
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    if stat.S_ISLNK(metadata.st_mode) or attributes & _WINDOWS_REPARSE_POINT:
        raise FundamentalReadSnapshotError(
            f"fundamental_snapshot_reparse_path_refused:{path.name}"
        )


def _require_regular_non_reparse(
    path: Path,
    metadata: os.stat_result,
    role: str,
) -> None:
    _reject_reparse(path, metadata)
    if not stat.S_ISREG(metadata.st_mode):
        raise FundamentalReadSnapshotError(
            f"fundamental_snapshot_non_regular_file:{role}"
        )


def _stat_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_size),
        int(metadata.st_mtime_ns),
        int(stat.S_IMODE(metadata.st_mode)),
    )


def _poll_cancel(callback: Callable[[], bool] | None) -> None:
    if callback is None:
        return
    try:
        value = callback()
    except BaseException as exc:
        raise FundamentalReadSnapshotCancelled(
            f"fundamental_snapshot_cancel_callback_failed:{type(exc).__name__}"
        ) from exc
    if type(value) is not bool:
        raise FundamentalReadSnapshotCancelled(
            "fundamental_snapshot_cancel_callback_must_return_bool"
        )
    if value:
        raise FundamentalReadSnapshotCancelled("fundamental_snapshot_cancelled")


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(raw).hexdigest()


def _normalize_snapshot_codes(stock_codes: Sequence[str]) -> tuple[str, ...]:
    if isinstance(stock_codes, (str, bytes)):
        raise FundamentalReadSnapshotError("fundamental_snapshot_stock_codes_invalid")
    try:
        codes = tuple(stock_codes)
    except TypeError as exc:
        raise FundamentalReadSnapshotError("fundamental_snapshot_stock_codes_invalid") from exc
    if (
        not codes
        or len(codes) > 100_000
        or any(type(code) is not str or not re.fullmatch(r"[0-9]{4,6}", code) for code in codes)
        or codes != tuple(sorted(set(codes)))
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_stock_codes_invalid")
    return codes


def _parse_reference_cutoff(value: str) -> datetime:
    if type(value) is not str or len(value) > 64:
        raise ValueError("snapshot reference cutoff 格式錯誤")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("snapshot reference cutoff 格式錯誤") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("snapshot reference cutoff 必須帶時區")
    return parsed


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON duplicate key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"JSON constant is not allowed: {value}")


def _validate_json_depth(raw: bytes, *, max_depth: int) -> None:
    depth = 0
    inside_string = False
    escaped = False
    for byte in raw:
        if inside_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                inside_string = False
            continue
        if byte == 0x22:
            inside_string = True
        elif byte in {0x5B, 0x7B}:
            depth += 1
            if depth > max_depth:
                raise ValueError("JSON nesting depth exceeds limit")
        elif byte in {0x5D, 0x7D}:
            depth -= 1
            if depth < 0:
                raise ValueError("JSON delimiters are unbalanced")
    if inside_string or depth != 0:
        raise ValueError("JSON delimiters are unbalanced")


def _require_json_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise ValueError(f"snapshot reference {key} 必須是字串")
    return value


def _parse_snapshot_pin(value: object) -> FundamentalFilePin:
    if type(value) is not dict:
        raise ValueError("snapshot file pin 必須是 object")
    expected = {
        "role", "path", "present", "device", "inode", "size_bytes", "mtime_ns", "mode", "sha256"
    }
    if set(value) != expected:
        raise ValueError("snapshot file pin 欄位不符")
    role = value["role"]
    path = value["path"]
    present = value["present"]
    if type(role) is not str or type(path) is not str or type(present) is not bool:
        raise ValueError("snapshot file pin 欄位型別錯誤")
    numeric: dict[str, int | None] = {}
    for key in ("device", "inode", "size_bytes", "mtime_ns", "mode"):
        item = value[key]
        if item is not None and type(item) is not int:
            raise ValueError("snapshot file pin stat 型別錯誤")
        numeric[key] = item
    digest = value["sha256"]
    if digest is not None and type(digest) is not str:
        raise ValueError("snapshot file pin digest 型別錯誤")
    pin = FundamentalFilePin(
        role=role,
        path=path,
        present=present,
        device=numeric["device"],
        inode=numeric["inode"],
        size_bytes=numeric["size_bytes"],
        mtime_ns=numeric["mtime_ns"],
        mode=numeric["mode"],
        sha256=digest,
    )
    if pin.to_dict() != value:
        raise ValueError("snapshot file pin 非 canonical")
    return pin


def _parse_raw_archive_file(value: object) -> FundamentalReadSnapshotRawArchiveFileV1:
    expected = {"historical_pin", "relative_path", "size_bytes", "sha256"}
    if type(value) is not dict or set(value) != expected:
        raise ValueError("raw archive file 欄位不符")
    relative_path = value["relative_path"]
    size_bytes = value["size_bytes"]
    digest = value["sha256"]
    if type(relative_path) is not str or type(size_bytes) is not int or type(digest) is not str:
        raise ValueError("raw archive file 欄位型別錯誤")
    return FundamentalReadSnapshotRawArchiveFileV1(
        historical_pin=_parse_snapshot_pin(value["historical_pin"]),
        relative_path=relative_path,
        size_bytes=size_bytes,
        sha256=digest,
    )


def _parse_snapshot_file_reference(value: object) -> FundamentalReadSnapshotFileReference:
    if type(value) is not dict or set(value) != {
        "role", "relative_path", "size_bytes", "sha256"
    }:
        raise ValueError("snapshot file reference 欄位不符")
    role = value["role"]
    relative_path = value["relative_path"]
    size_bytes = value["size_bytes"]
    digest = value["sha256"]
    if (
        type(role) is not str
        or type(relative_path) is not str
        or type(size_bytes) is not int
        or type(digest) is not str
    ):
        raise ValueError("snapshot file reference 型別錯誤")
    result = FundamentalReadSnapshotFileReference(
        role=role,
        relative_path=relative_path,
        size_bytes=size_bytes,
        sha256=digest,
    )
    if result.to_dict() != value:
        raise ValueError("snapshot file reference 非 canonical")
    return result


def _parse_snapshot_pin_tuple(value: object) -> tuple[FundamentalFilePin, ...]:
    if type(value) is not list:
        raise ValueError("snapshot pins 必須是 array")
    return tuple(_parse_snapshot_pin(item) for item in value)


def _parse_snapshot_reference_tuple(
    value: object,
) -> tuple[FundamentalReadSnapshotFileReference, ...]:
    if type(value) is not list:
        raise ValueError("snapshot file references 必須是 array")
    return tuple(_parse_snapshot_file_reference(item) for item in value)


def _parse_snapshot_binding(value: object) -> FundamentalReadSnapshotBinding:
    expected = {
        "schema_version", "snapshot_id", "snapshot_root", "source_database_path",
        "reader_database_path", "source_file_pins_start", "source_file_pins_after_copy",
        "source_file_pins_finish", "captured_files", "captured_file_pins_start",
        "captured_file_pins_finish", "capture_manifest_pin_start", "capture_manifest_pin_finish",
        "reader_files", "reader_file_pins_finish", "sqlite_journal_mode", "wal_sidecar_state",
        "source_snapshot_sha256", "source_copy_bytes", "reader_only_sidecar_bytes",
        "duplicated_disk_bytes", "identity_sha256",
    }
    if type(value) is not dict or set(value) != expected:
        raise ValueError("snapshot binding 欄位不符")
    string_keys = (
        "schema_version", "snapshot_id", "snapshot_root", "source_database_path",
        "reader_database_path", "sqlite_journal_mode", "wal_sidecar_state",
        "source_snapshot_sha256",
    )
    if any(type(value[key]) is not str for key in string_keys):
        raise ValueError("snapshot binding 字串欄位型別錯誤")
    integer_keys = ("source_copy_bytes", "reader_only_sidecar_bytes", "duplicated_disk_bytes")
    if any(type(value[key]) is not int for key in integer_keys):
        raise ValueError("snapshot binding 整數欄位型別錯誤")
    capture_manifest_start = _parse_snapshot_pin(value["capture_manifest_pin_start"])
    capture_manifest_finish = _parse_snapshot_pin(value["capture_manifest_pin_finish"])
    binding = FundamentalReadSnapshotBinding(
        snapshot_id=value["snapshot_id"],
        snapshot_root=value["snapshot_root"],
        source_database_path=value["source_database_path"],
        reader_database_path=value["reader_database_path"],
        source_file_pins_start=_parse_snapshot_pin_tuple(value["source_file_pins_start"]),
        source_file_pins_after_copy=_parse_snapshot_pin_tuple(value["source_file_pins_after_copy"]),
        source_file_pins_finish=_parse_snapshot_pin_tuple(value["source_file_pins_finish"]),
        captured_files=_parse_snapshot_reference_tuple(value["captured_files"]),
        captured_file_pins_start=_parse_snapshot_pin_tuple(value["captured_file_pins_start"]),
        captured_file_pins_finish=_parse_snapshot_pin_tuple(value["captured_file_pins_finish"]),
        capture_manifest_pin_start=capture_manifest_start,
        capture_manifest_pin_finish=capture_manifest_finish,
        reader_files=_parse_snapshot_reference_tuple(value["reader_files"]),
        reader_file_pins_finish=_parse_snapshot_pin_tuple(value["reader_file_pins_finish"]),
        sqlite_journal_mode=value["sqlite_journal_mode"],
        wal_sidecar_state=value["wal_sidecar_state"],
        source_snapshot_sha256=value["source_snapshot_sha256"],
        source_copy_bytes=value["source_copy_bytes"],
        reader_only_sidecar_bytes=value["reader_only_sidecar_bytes"],
        duplicated_disk_bytes=value["duplicated_disk_bytes"],
    )
    if binding.to_dict() != value:
        raise ValueError("snapshot binding identity/noncanonical bytes mismatch")
    return binding


def _parse_snapshot_source_clock(value: object) -> FundamentalSnapshotSourceClock:
    expected = {
        "schema_version", "source_id", "database_path", "decision_cutoff",
        "declared_stock_codes", "declared_stock_codes_sha256", "schema_identity_sha256",
        "schema_descriptor", "database_file_pins_start", "database_file_pins_finish",
        "capture_file_pins_start", "capture_file_pins_finish", "source_scope",
        "availability_status", "historical_pit_eligible", "formal_pit_eligible",
        "snapshot_binding", "source_pin_sha256", "identity_sha256",
    }
    if type(value) is not dict or set(value) != expected:
        raise ValueError("snapshot source clock 欄位不符")
    string_keys = (
        "schema_version", "source_id", "database_path", "decision_cutoff",
        "declared_stock_codes_sha256", "schema_identity_sha256", "source_scope",
        "availability_status", "source_pin_sha256", "identity_sha256",
    )
    if any(type(value[key]) is not str for key in string_keys):
        raise ValueError("snapshot source clock 字串欄位型別錯誤")
    raw_codes = value["declared_stock_codes"]
    raw_descriptor = value["schema_descriptor"]
    if type(raw_codes) is not list or any(type(code) is not str for code in raw_codes):
        raise ValueError("snapshot source clock 清冊型別錯誤")
    if type(raw_descriptor) is not list:
        raise ValueError("snapshot source clock schema descriptor 型別錯誤")
    descriptor: list[tuple[int, str, str, int, str | None, int]] = []
    for row in raw_descriptor:
        if (
            type(row) is not list or len(row) != 6
            or type(row[0]) is not int or type(row[1]) is not str
            or type(row[2]) is not str or type(row[3]) is not int
            or (row[4] is not None and type(row[4]) is not str)
            or type(row[5]) is not int
        ):
            raise ValueError("snapshot source clock schema descriptor 列型別錯誤")
        descriptor.append((row[0], row[1], row[2], row[3], row[4], row[5]))
    if (
        value["historical_pit_eligible"] is not False
        or value["formal_pit_eligible"] is not False
    ):
        raise ValueError("snapshot source clock PIT flags 型別錯誤")
    source_clock = FundamentalSnapshotSourceClock(
        database_path=value["database_path"],
        decision_cutoff=_parse_reference_cutoff(value["decision_cutoff"]),
        declared_stock_codes=tuple(raw_codes),
        schema_identity_sha256=value["schema_identity_sha256"],
        schema_descriptor=tuple(descriptor),
        database_file_pins_start=_parse_snapshot_pin_tuple(value["database_file_pins_start"]),
        database_file_pins_finish=_parse_snapshot_pin_tuple(value["database_file_pins_finish"]),
        capture_file_pins_start=_parse_snapshot_pin_tuple(value["capture_file_pins_start"]),
        capture_file_pins_finish=_parse_snapshot_pin_tuple(value["capture_file_pins_finish"]),
        snapshot_binding=_parse_snapshot_binding(value["snapshot_binding"]),
        schema_version=value["schema_version"],
        source_id=value["source_id"],
        source_scope=value["source_scope"],
        availability_status=value["availability_status"],
        historical_pit_eligible=False,
        formal_pit_eligible=False,
    )
    if (
        source_clock.to_dict() != value
        or value["source_pin_sha256"] != source_clock.source_pin_sha256
        or value["identity_sha256"] != source_clock.identity_sha256
    ):
        raise ValueError("snapshot source clock hash/noncanonical bytes mismatch")
    return source_clock


def _parse_finished_cohort_ledger(
    value: object,
    *,
    source_clock: FundamentalSnapshotSourceClock,
    expected_identity: object,
) -> tuple[str, str, tuple[str, ...], tuple[tuple[str, str], ...], tuple[tuple[str, int], ...]]:
    expected_keys = {
        "session_id", "reader_session_id", "processed_stock_codes",
        "result_identity_by_stock", "result_status_counts", "complete", "identity_sha256",
    }
    if type(value) is not dict or set(value) != expected_keys:
        raise ValueError("finished snapshot cohort ledger 欄位不符")
    if any(type(value[key]) is not str for key in ("session_id", "reader_session_id", "identity_sha256")):
        raise ValueError("finished snapshot cohort identity 型別錯誤")
    if value["complete"] is not True:
        raise ValueError("finished snapshot cohort 必須 complete")
    codes_raw = value["processed_stock_codes"]
    identities_raw = value["result_identity_by_stock"]
    counts_raw = value["result_status_counts"]
    if type(codes_raw) is not list or any(type(code) is not str for code in codes_raw):
        raise ValueError("finished snapshot cohort codes 型別錯誤")
    if type(identities_raw) is not list or any(
        type(item) is not list or len(item) != 2 or any(type(part) is not str for part in item)
        for item in identities_raw
    ):
        raise ValueError("finished snapshot result ledger 型別錯誤")
    if type(counts_raw) is not list or any(
        type(item) is not list or len(item) != 2 or type(item[0]) is not str or type(item[1]) is not int
        for item in counts_raw
    ):
        raise ValueError("finished snapshot status counts 型別錯誤")
    processed = tuple(codes_raw)
    result_identities = tuple((item[0], item[1]) for item in identities_raw)
    status_counts = tuple((item[0], item[1]) for item in counts_raw)
    finished = FinishedFundamentalSnapshotReadCohort(
        session_id=value["session_id"],
        source_clock=source_clock,
        processed_stock_codes=processed,
        result_identity_by_stock=result_identities,
        result_status_counts=status_counts,
    )
    if finished.identity_sha256 != expected_identity or value["identity_sha256"] != finished.identity_sha256:
        raise ValueError("finished snapshot cohort identity mismatch")
    return (
        value["reader_session_id"],
        finished.session_id,
        finished.processed_stock_codes,
        finished.result_identity_by_stock,
        finished.result_status_counts,
    )


def _read_canonical_json_file(path: Path, *, max_bytes: int) -> tuple[dict[str, object], bytes]:
    raw = _read_bounded_regular_file(path, max_bytes=max_bytes, cancel_callback=None)
    _validate_json_depth(raw, max_depth=48)
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise FundamentalReadSnapshotError("fundamental_snapshot_manifest_json_invalid") from exc
    if type(payload) is not dict or raw != _canonical_json_bytes(payload):
        raise FundamentalReadSnapshotError("fundamental_snapshot_manifest_not_canonical")
    return payload, raw


def _load_finished_snapshot_manifest(
    snapshot_root: Path,
) -> tuple[dict[str, object], FundamentalReadSnapshotBinding, FundamentalSnapshotSourceClock,
           tuple[str, str, tuple[str, ...], tuple[tuple[str, str], ...], tuple[tuple[str, int], ...]],
           bytes]:
    manifest_path = snapshot_root / "finished_source_clock.json"
    manifest, raw = _read_canonical_json_file(
        manifest_path,
        max_bytes=MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES,
    )
    expected_keys = {
        "schema_version", "manifest_state", "snapshot_binding", "source_clock",
        "cohort_identity_sha256", "finished_cohort", "manifest_sha256",
    }
    if set(manifest) != expected_keys:
        raise FundamentalReadSnapshotError("fundamental_snapshot_finished_manifest_fields_mismatch")
    digest = manifest.get("manifest_sha256")
    body = {key: item for key, item in manifest.items() if key != "manifest_sha256"}
    if (
        manifest.get("schema_version") != FUNDAMENTAL_READ_SNAPSHOT_SCHEMA
        or manifest.get("manifest_state") != "complete"
        or type(digest) is not str
        or digest != _canonical_sha256(body)
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_finished_manifest_invalid")
    try:
        binding = _parse_snapshot_binding(manifest["snapshot_binding"])
        source_clock = _parse_snapshot_source_clock(manifest["source_clock"])
        ledger = _parse_finished_cohort_ledger(
            manifest["finished_cohort"],
            source_clock=source_clock,
            expected_identity=manifest["cohort_identity_sha256"],
        )
    except (TypeError, ValueError) as exc:
        raise FundamentalReadSnapshotError("fundamental_snapshot_finished_manifest_contract_invalid") from exc
    if (
        binding != source_clock.snapshot_binding
        or binding.snapshot_root != str(snapshot_root)
        or binding.snapshot_id != snapshot_root.name
        or source_clock.database_path != binding.source_database_path
        or ledger[2] != source_clock.declared_stock_codes
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_finished_manifest_source_mismatch")
    return manifest, binding, source_clock, ledger, raw


def _reference_from_finished_snapshot(snapshot_root: Path) -> FundamentalReadSnapshotReferenceV1:
    manifest, _binding, source_clock, _ledger, manifest_raw = _load_finished_snapshot_manifest(snapshot_root)
    digest = sha256(manifest_raw).hexdigest()
    cohort_identity = manifest.get("cohort_identity_sha256")
    if type(digest) is not str or type(cohort_identity) is not str:
        raise FundamentalReadSnapshotError("fundamental_snapshot_reference_manifest_identity_missing")
    return FundamentalReadSnapshotReferenceV1(
        snapshot_root=str(snapshot_root),
        snapshot_id=snapshot_root.name,
        finished_manifest_sha256=digest,
        source_clock_identity_sha256=source_clock.identity_sha256,
        source_content_identity_sha256=source_clock.source_content_identity_sha256,
        cohort_identity_sha256=cohort_identity,
        decision_cutoff=source_clock.decision_cutoff.isoformat(),
        declared_stock_codes=source_clock.declared_stock_codes,
        declared_stock_codes_sha256=source_clock.declared_stock_codes_sha256,
    )


def _verify_finished_snapshot_reference(
    reference: FundamentalReadSnapshotReferenceV1,
    *,
    provider: RecommendationCurrentFundamentalProvider,
    cancel_callback: Callable[[], bool] | None,
) -> _VerifiedSnapshotReference:
    _poll_cancel(cancel_callback)
    snapshot_root = Path(reference.snapshot_root)
    if (
        not snapshot_root.is_absolute()
        or Path(os.path.abspath(snapshot_root)) != snapshot_root
        or snapshot_root.name != reference.snapshot_id
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_reference_path_invalid")
    _reject_reparse_components(snapshot_root)
    manifest, binding, source_clock, ledger, manifest_raw = _load_finished_snapshot_manifest(snapshot_root)
    manifest_path = snapshot_root / "finished_source_clock.json"
    manifest_pin = _pin_file(
        "finished_source_clock_manifest",
        manifest_path,
        required=True,
        cancel_callback=cancel_callback,
    )
    if (
        manifest_pin.size_bytes is None
        or manifest_pin.size_bytes > MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES
        or manifest_pin.sha256 != reference.finished_manifest_sha256
        or sha256(manifest_raw).hexdigest() != reference.finished_manifest_sha256
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_finished_manifest_pin_mismatch")
    if (
        reference.source_clock_identity_sha256 != source_clock.identity_sha256
        or reference.source_content_identity_sha256 != source_clock.source_content_identity_sha256
        or reference.cohort_identity_sha256 != manifest.get("cohort_identity_sha256")
        or reference.decision_cutoff != source_clock.decision_cutoff.isoformat()
        or reference.declared_stock_codes != source_clock.declared_stock_codes
        or reference.declared_stock_codes_sha256 != source_clock.declared_stock_codes_sha256
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_reference_manifest_mismatch")
    source_database_path = _safe_source_database_path(source_clock.database_path)
    if provider.db_file != source_database_path:
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_provider_database_mismatch")
    if any(
        _paths_overlap(snapshot_root, Path(os.path.abspath(path)))
        for path in (provider.output_root, provider.monthly_source_root)
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_root_overlaps_provider_root")
    if _paths_overlap(snapshot_root, Path(os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data"))):
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_root_overlaps_formal_data_root")
    source_pins = _pin_source_file_set(source_database_path, cancel_callback=cancel_callback)
    if (
        source_pins != binding.source_file_pins_start
        or source_pins != binding.source_file_pins_after_copy
        or source_pins != binding.source_file_pins_finish
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_original_database_pin_changed")
    _verify_reference_capture_pins(
        source_clock,
        monthly_source_root=provider.monthly_source_root,
        cancel_callback=cancel_callback,
    )
    _verify_snapshot_binding_files(
        snapshot_root,
        binding,
        cancel_callback=cancel_callback,
    )
    _verify_snapshot_capture_manifest(snapshot_root, binding, cancel_callback=cancel_callback)
    _verify_finished_snapshot_status(snapshot_root, source_clock, manifest, cancel_callback)
    _verify_snapshot_file_inventory(
        snapshot_root,
        binding,
        cancel_callback=cancel_callback,
    )
    _poll_cancel(cancel_callback)
    return _VerifiedSnapshotReference(
        reference=reference,
        binding=binding,
        source_clock=source_clock,
        reader_session_id=ledger[0],
        finished_session_id=ledger[1],
        processed_stock_codes=ledger[2],
        result_identity_by_stock=ledger[3],
        result_status_counts=ledger[4],
    )


def _create_raw_source_archive(
    *,
    provider: RecommendationCurrentFundamentalProvider,
    source_clock: FundamentalSnapshotSourceClock,
    snapshot_reference: FundamentalReadSnapshotReferenceV1,
    archive_parent: Path | str,
    cancel_callback: Callable[[], bool] | None,
) -> FundamentalReadSnapshotRawArchiveReferenceV1:
    """建立 raw archive；live DB 與原 capture 必須在整個複製期間保持相同。"""

    _poll_cancel(cancel_callback)
    if snapshot_reference.source_clock_identity_sha256 != source_clock.identity_sha256:
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_clock_mismatch")
    original_monthly_root = Path(os.path.abspath(provider.monthly_source_root))
    source_database_path = Path(source_clock.database_path)
    raw_parent = Path(archive_parent).expanduser()
    if not raw_parent.is_absolute():
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_parent_not_absolute")
    _reject_reparse_components(raw_parent, allow_missing=True)
    archive_parent_abs = Path(os.path.abspath(raw_parent))
    protected = (
        source_database_path.parent,
        Path(snapshot_reference.snapshot_root),
        provider.output_root,
        provider.monthly_source_root,
        Path(os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data")),
    )
    for protected_root in protected:
        candidate = Path(os.path.abspath(protected_root.expanduser()))
        if _paths_overlap(archive_parent_abs, candidate):
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_raw_archive_root_overlaps_protected_root"
            )

    source_pins_start = _pin_source_file_set(
        source_database_path, cancel_callback=cancel_callback
    )
    if source_pins_start != source_clock.database_file_pins_start:
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_live_database_changed")
    capture_pins_start = _pin_raw_capture_set(
        source_clock, original_monthly_root, cancel_callback=cancel_callback
    )

    archive_id = uuid4().hex
    archive_root = archive_parent_abs / archive_id
    if archive_root.exists() or archive_root.is_symlink():
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_id_collision")
    try:
        archive_parent_abs.mkdir(parents=True, exist_ok=True)
        _reject_reparse_components(archive_parent_abs)
        archive_root.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_id_collision") from exc
    monthly_root = archive_root / "monthly_source"
    monthly_root.mkdir()

    archived_files: list[FundamentalReadSnapshotRawArchiveFileV1] = []
    archive_file_pins: list[FundamentalFilePin] = []
    try:
        if len(capture_pins_start) > MAX_RAW_ARCHIVE_FILES:
            raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_file_count_over_limit")
        total_bytes = 0
        for historic_pin in capture_pins_start:
            _poll_cancel(cancel_callback)
            original = Path(historic_pin.path)
            try:
                relative = original.relative_to(original_monthly_root).as_posix()
            except ValueError as exc:
                raise FundamentalReadSnapshotError(
                    "fundamental_snapshot_raw_archive_capture_outside_source_root"
                ) from exc
            if historic_pin.size_bytes is None or historic_pin.size_bytes > MAX_RAW_ARCHIVE_FILE_BYTES:
                raise FundamentalReadSnapshotError(
                    "fundamental_snapshot_raw_archive_file_over_limit"
                )
            total_bytes += historic_pin.size_bytes
            if total_bytes > MAX_RAW_ARCHIVE_TOTAL_BYTES:
                raise FundamentalReadSnapshotError(
                    "fundamental_snapshot_raw_archive_total_bytes_over_limit"
                )
            destination = monthly_root / Path(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _reject_reparse_components(destination.parent)
            current_pin = _pin_file(
                historic_pin.role, original, required=True, cancel_callback=cancel_callback
            )
            if current_pin != historic_pin:
                raise FundamentalReadSnapshotError(
                    "fundamental_snapshot_raw_archive_capture_changed_before_copy"
                )
            copied_size, copied_sha = _copy_file_bounded(
                original,
                destination,
                max_bytes=MAX_RAW_ARCHIVE_FILE_BYTES,
                cancel_callback=cancel_callback,
            )
            _make_read_only(destination)
            _require_single_link(destination, "raw_archive")
            archive_pin = _pin_file(
                historic_pin.role,
                destination,
                required=True,
                cancel_callback=cancel_callback,
            )
            after_original_pin = _pin_file(
                historic_pin.role, original, required=True, cancel_callback=cancel_callback
            )
            if (
                copied_size != historic_pin.size_bytes
                or copied_sha != historic_pin.sha256
                or archive_pin.size_bytes != copied_size
                or archive_pin.sha256 != copied_sha
                or after_original_pin != historic_pin
            ):
                raise FundamentalReadSnapshotError(
                    "fundamental_snapshot_raw_archive_copy_bytes_or_source_pin_mismatch"
                )
            archived_files.append(
                FundamentalReadSnapshotRawArchiveFileV1(
                    historical_pin=historic_pin,
                    relative_path=relative,
                    size_bytes=copied_size,
                    sha256=copied_sha,
                )
            )
            archive_file_pins.append(archive_pin)

        source_pins_finish = _pin_source_file_set(
            source_database_path, cancel_callback=cancel_callback
        )
        capture_pins_finish = _pin_raw_capture_set(
            source_clock, original_monthly_root, cancel_callback=cancel_callback
        )
        if source_pins_finish != source_pins_start:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_raw_archive_live_database_changed_during_copy"
            )
        if capture_pins_finish != capture_pins_start:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_raw_archive_live_capture_changed_during_copy"
            )

        base = _raw_archive_payload(
            snapshot_reference=snapshot_reference,
            archive_root=archive_root,
            archived_monthly_source_root=monthly_root,
            original_monthly_source_root=original_monthly_root,
            archive_id=archive_id,
            source_clock=source_clock,
            files=tuple(archived_files),
        )
        archive_identity = _canonical_sha256(base)
        manifest = dict(base)
        manifest["archive_identity_sha256"] = archive_identity
        raw_manifest = _canonical_json_bytes(manifest)
        if len(raw_manifest) > MAX_RAW_ARCHIVE_MANIFEST_BYTES:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_raw_archive_manifest_over_limit"
            )
        manifest_path = archive_root / "raw_source_archive.json"
        _write_create_only_bytes(manifest_path, raw_manifest)
        _make_read_only(manifest_path)
        manifest_pin = _pin_file(
            "monthly_raw_archive_manifest",
            manifest_path,
            required=True,
            cancel_callback=cancel_callback,
        )
        reference = FundamentalReadSnapshotRawArchiveReferenceV1(
            snapshot_reference=snapshot_reference,
            raw_archive_root=str(archive_root),
            archived_monthly_source_root=str(monthly_root),
            original_monthly_source_root=str(original_monthly_root),
            archive_id=archive_id,
            source_clock_identity_sha256=source_clock.identity_sha256,
            source_content_identity_sha256=source_clock.source_content_identity_sha256,
            cohort_identity_sha256=snapshot_reference.cohort_identity_sha256,
            decision_cutoff=source_clock.decision_cutoff.isoformat(),
            declared_stock_codes=source_clock.declared_stock_codes,
            declared_stock_codes_sha256=source_clock.declared_stock_codes_sha256,
            files=tuple(archived_files),
            manifest_sha256=manifest_pin.sha256 or "",
            archive_identity_sha256=archive_identity,
        )
        _verify_raw_archive_reference(
            reference,
            provider=provider,
            cancel_callback=cancel_callback,
        )
        source_pins_final = _pin_source_file_set(
            source_database_path, cancel_callback=cancel_callback
        )
        capture_pins_final = _pin_raw_capture_set(
            source_clock, original_monthly_root, cancel_callback=cancel_callback
        )
        if source_pins_final != source_pins_start or capture_pins_final != capture_pins_start:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_raw_archive_source_changed_before_issue"
            )
        _poll_cancel(cancel_callback)
        return reference
    except BaseException:
        # 未完成 archive 留作失敗證據，不刪除或覆寫。
        raise


def _pin_raw_capture_set(
    source_clock: FundamentalSnapshotSourceClock,
    monthly_source_root: Path,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> tuple[FundamentalFilePin, ...]:
    if source_clock.capture_file_pins_start != source_clock.capture_file_pins_finish:
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_capture_ledger_changed")
    pins: list[FundamentalFilePin] = []
    for expected in source_clock.capture_file_pins_start:
        _poll_cancel(cancel_callback)
        if not expected.present or expected.role not in {"monthly_html", "monthly_csv"}:
            raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_capture_unsupported")
        path = Path(expected.path)
        try:
            path.relative_to(monthly_source_root)
        except ValueError as exc:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_raw_archive_capture_outside_source_root"
            ) from exc
        actual = _pin_file(
            expected.role, path, required=True, cancel_callback=cancel_callback
        )
        if actual != expected:
            raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_capture_pin_changed")
        pins.append(actual)
    return tuple(pins)


def _raw_archive_payload(
    *,
    snapshot_reference: FundamentalReadSnapshotReferenceV1,
    archive_root: Path,
    archived_monthly_source_root: Path,
    original_monthly_source_root: Path,
    archive_id: str,
    source_clock: FundamentalSnapshotSourceClock,
    files: tuple[FundamentalReadSnapshotRawArchiveFileV1, ...],
) -> dict[str, object]:
    return {
        "schema_version": "fundamental-monthly-raw-source-archive.v1",
        "snapshot_reference": snapshot_reference.to_dict(),
        "raw_archive_root": str(archive_root),
        "archived_monthly_source_root": str(archived_monthly_source_root),
        "original_monthly_source_root": str(original_monthly_source_root),
        "archive_id": archive_id,
        "source_clock_identity_sha256": source_clock.identity_sha256,
        "source_content_identity_sha256": source_clock.source_content_identity_sha256,
        "cohort_identity_sha256": snapshot_reference.cohort_identity_sha256,
        "decision_cutoff": source_clock.decision_cutoff.isoformat(),
        "declared_stock_codes": list(source_clock.declared_stock_codes),
        "declared_stock_codes_sha256": source_clock.declared_stock_codes_sha256,
        "files": [item.to_dict() for item in files],
        "source_scope": "current_observed_only",
        "availability_status": "unknown",
        "historical_pit_eligible": False,
        "formal_pit_eligible": False,
    }


def _verify_raw_archive_reference(
    reference: FundamentalReadSnapshotRawArchiveReferenceV1,
    *,
    provider: RecommendationCurrentFundamentalProvider | _RawArchiveVerificationRoots,
    cancel_callback: Callable[[], bool] | None,
) -> _VerifiedArchivedSnapshotReference:
    _poll_cancel(cancel_callback)
    snapshot_reference = reference.snapshot_reference
    snapshot_root = Path(snapshot_reference.snapshot_root)
    archive_root = Path(reference.raw_archive_root)
    monthly_root = Path(reference.archived_monthly_source_root)
    original_monthly_root = Path(reference.original_monthly_source_root)
    if (
        not snapshot_root.is_absolute()
        or Path(os.path.abspath(snapshot_root)) != snapshot_root
        or snapshot_root.name != snapshot_reference.snapshot_id
        or not archive_root.is_absolute()
        or Path(os.path.abspath(archive_root)) != archive_root
        or archive_root.name != reference.archive_id
        or monthly_root != archive_root / "monthly_source"
        or not original_monthly_root.is_absolute()
        or Path(os.path.abspath(original_monthly_root)) != original_monthly_root
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_reference_path_invalid")
    _reject_reparse_components(snapshot_root)
    _reject_reparse_components(archive_root)
    _reject_reparse_components(monthly_root)

    manifest, binding, source_clock, ledger, snapshot_raw = _load_finished_snapshot_manifest(
        snapshot_root
    )
    source_database_path = Path(source_clock.database_path)
    if (
        reference.source_clock_identity_sha256 != source_clock.identity_sha256
        or reference.source_content_identity_sha256 != source_clock.source_content_identity_sha256
        or reference.cohort_identity_sha256 != snapshot_reference.cohort_identity_sha256
        or reference.decision_cutoff != source_clock.decision_cutoff.isoformat()
        or reference.declared_stock_codes != source_clock.declared_stock_codes
        or reference.declared_stock_codes_sha256 != source_clock.declared_stock_codes_sha256
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_source_identity_mismatch")
    if (
        source_clock.capture_file_pins_start != source_clock.capture_file_pins_finish
        or binding.source_file_pins_start != binding.source_file_pins_after_copy
        or binding.source_file_pins_start != binding.source_file_pins_finish
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_historical_pins_inconsistent")

    protected_roots = (
        source_database_path.parent,
        provider.output_root,
        provider.monthly_source_root,
        Path(os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data")),
    )
    for protected_root in protected_roots:
        protected = Path(os.path.abspath(protected_root.expanduser()))
        if _paths_overlap(snapshot_root, protected) or _paths_overlap(archive_root, protected):
            raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_root_overlaps_protected_root")
    if _paths_overlap(snapshot_root, archive_root) or _paths_overlap(archive_root, original_monthly_root):
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_roots_overlap")

    snapshot_manifest_path = snapshot_root / "finished_source_clock.json"
    snapshot_manifest_pin = _pin_file(
        "finished_source_clock_manifest",
        snapshot_manifest_path,
        required=True,
        cancel_callback=cancel_callback,
    )
    if (
        snapshot_manifest_pin.sha256 != snapshot_reference.finished_manifest_sha256
        or sha256(snapshot_raw).hexdigest() != snapshot_reference.finished_manifest_sha256
        or snapshot_reference.source_clock_identity_sha256 != source_clock.identity_sha256
        or snapshot_reference.source_content_identity_sha256 != source_clock.source_content_identity_sha256
        or snapshot_reference.cohort_identity_sha256 != manifest.get("cohort_identity_sha256")
        or snapshot_reference.decision_cutoff != source_clock.decision_cutoff.isoformat()
        or snapshot_reference.declared_stock_codes != source_clock.declared_stock_codes
        or snapshot_reference.declared_stock_codes_sha256 != source_clock.declared_stock_codes_sha256
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_snapshot_reference_mismatch")
    _verify_snapshot_binding_files(snapshot_root, binding, cancel_callback=cancel_callback)
    _verify_snapshot_capture_manifest(snapshot_root, binding, cancel_callback=cancel_callback)
    _verify_finished_snapshot_status(snapshot_root, source_clock, manifest, cancel_callback)
    _verify_snapshot_file_inventory(
        snapshot_root,
        binding,
        cancel_callback=cancel_callback,
    )

    expected_files = _pin_raw_capture_set_from_clock(source_clock, original_monthly_root)
    if tuple(item.historical_pin for item in reference.files) != expected_files:
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_capture_manifest_mismatch")
    if tuple(item.historical_pin.role for item in reference.files) != tuple(
        pin.role for pin in source_clock.capture_file_pins_start
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_capture_roles_mismatch")

    manifest_path = archive_root / "raw_source_archive.json"
    raw_manifest = _read_bounded_regular_file(
        manifest_path, max_bytes=MAX_RAW_ARCHIVE_MANIFEST_BYTES, cancel_callback=cancel_callback
    )
    _validate_json_depth(raw_manifest, max_depth=20)
    try:
        payload = json.loads(
            raw_manifest.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_manifest_invalid") from exc
    expected_payload = _raw_archive_payload(
        snapshot_reference=snapshot_reference,
        archive_root=archive_root,
        archived_monthly_source_root=monthly_root,
        original_monthly_source_root=original_monthly_root,
        archive_id=reference.archive_id,
        source_clock=source_clock,
        files=reference.files,
    )
    expected_payload["archive_identity_sha256"] = _canonical_sha256(expected_payload)
    if (
        type(payload) is not dict
        or raw_manifest != _canonical_json_bytes(payload)
        or payload != expected_payload
        or reference.archive_identity_sha256 != expected_payload["archive_identity_sha256"]
        or reference.manifest_sha256 != sha256(raw_manifest).hexdigest()
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_manifest_mismatch")
    archive_manifest_pin = _pin_file(
        "monthly_raw_archive_manifest", manifest_path, required=True, cancel_callback=cancel_callback
    )
    if archive_manifest_pin.sha256 != reference.manifest_sha256:
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_manifest_pin_mismatch")

    expected_fileset = {"raw_source_archive.json"}
    expected_dirs: set[str] = set()
    archive_file_pins: list[FundamentalFilePin] = []
    for item in reference.files:
        _poll_cancel(cancel_callback)
        relative = PurePosixPath(item.relative_path)
        archive_relative = PurePosixPath("monthly_source") / relative
        expected_fileset.add(archive_relative.as_posix())
        for index in range(1, len(archive_relative.parts)):
            expected_dirs.add(PurePosixPath(*archive_relative.parts[:index]).as_posix())
        candidate = monthly_root.joinpath(*relative.parts)
        _reject_reparse_components(candidate)
        actual = _pin_file(
            item.historical_pin.role,
            candidate,
            required=True,
            cancel_callback=cancel_callback,
        )
        _require_single_link(candidate, "raw_archive")
        if actual.size_bytes != item.size_bytes or actual.sha256 != item.sha256:
            raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_capture_bytes_changed")
        archive_file_pins.append(actual)
    _verify_raw_archive_inventory(
        archive_root,
        expected_files=expected_fileset,
        expected_dirs=expected_dirs,
        cancel_callback=cancel_callback,
    )
    _poll_cancel(cancel_callback)
    _ = ledger
    return _VerifiedArchivedSnapshotReference(
        snapshot=_VerifiedSnapshotReference(
            reference=snapshot_reference,
            binding=binding,
            source_clock=source_clock,
            reader_session_id=ledger[0],
            finished_session_id=ledger[1],
            processed_stock_codes=ledger[2],
            result_identity_by_stock=ledger[3],
            result_status_counts=ledger[4],
        ),
        archive_reference=reference,
        snapshot_manifest_pin=snapshot_manifest_pin,
        archive_manifest_pin=archive_manifest_pin,
        archive_file_pins=tuple(archive_file_pins),
    )


def _pin_raw_capture_set_from_clock(
    source_clock: FundamentalSnapshotSourceClock,
    original_monthly_source_root: Path,
) -> tuple[FundamentalFilePin, ...]:
    pins: list[FundamentalFilePin] = []
    for pin in source_clock.capture_file_pins_start:
        if not pin.present or pin.role not in {"monthly_html", "monthly_csv"}:
            raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_capture_pin_invalid")
        try:
            path = Path(pin.path)
            relative = path.relative_to(original_monthly_source_root)
        except ValueError as exc:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_raw_archive_capture_path_invalid"
            ) from exc
        if not relative.parts or any(part in {".", ".."} for part in relative.parts):
            raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_capture_path_invalid")
        pins.append(pin)
    return tuple(pins)


def _verify_raw_archive_inventory(
    archive_root: Path,
    *,
    expected_files: set[str],
    expected_dirs: set[str],
    cancel_callback: Callable[[], bool] | None,
) -> None:
    found_files: set[str] = set()
    found_dirs: set[str] = set()
    total_bytes = 0
    pending = [archive_root]
    while pending:
        _poll_cancel(cancel_callback)
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = list(iterator)
        except OSError as exc:
            raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_inventory_failed") from exc
        if len(entries) > 10_000 or len(found_files) + len(found_dirs) + len(entries) > MAX_RAW_ARCHIVE_FILES + 10_000:
            raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_inventory_over_limit")
        for entry in entries:
            _poll_cancel(cancel_callback)
            path = Path(entry.path)
            _reject_reparse_components(path)
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_inventory_drift") from exc
            _reject_reparse(path, metadata)
            relative = path.relative_to(archive_root).as_posix()
            if stat.S_ISDIR(metadata.st_mode):
                found_dirs.add(relative)
                pending.append(path)
            elif stat.S_ISREG(metadata.st_mode):
                found_files.add(relative)
                total_bytes += int(metadata.st_size)
                if int(metadata.st_nlink) != 1:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_hardlink_refused")
                if total_bytes > MAX_RAW_ARCHIVE_TOTAL_BYTES:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_total_bytes_over_limit")
            else:
                raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_non_regular_entry")
    if found_files != expected_files or found_dirs != expected_dirs:
        raise FundamentalReadSnapshotError("fundamental_snapshot_raw_archive_inventory_mismatch")


def _verify_reference_capture_pins(
    source_clock: FundamentalSnapshotSourceClock | FundamentalSnapshotSourceClockV2,
    *,
    monthly_source_root: Path,
    cancel_callback: Callable[[], bool] | None,
) -> None:
    if source_clock.capture_file_pins_start != source_clock.capture_file_pins_finish:
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_capture_ledger_changed")
    root = Path(os.path.abspath(monthly_source_root))
    for expected in source_clock.capture_file_pins_start:
        _poll_cancel(cancel_callback)
        if not expected.present or expected.role not in {"monthly_html", "monthly_csv"}:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_capture_reference_unsupported")
        path = Path(expected.path)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise FundamentalReadSnapshotError(
                "fundamental_snapshot_exact_capture_outside_monthly_source_root"
            ) from exc
        actual = _pin_file(
            expected.role,
            path,
            required=True,
            cancel_callback=cancel_callback,
        )
        if actual != expected:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_capture_pin_changed")
    _poll_cancel(cancel_callback)


def _verify_snapshot_binding_files(
    snapshot_root: Path,
    binding: FundamentalReadSnapshotBinding,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> None:
    if binding.snapshot_root != str(snapshot_root) or binding.snapshot_id != snapshot_root.name:
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_binding_root_mismatch")
    source = Path(binding.source_database_path)
    reader = Path(binding.reader_database_path)
    if (
        _paths_overlap(snapshot_root, source.parent)
        or reader != snapshot_root / "reader" / source.name
        or binding.source_database_path != str(source)
        or binding.reader_database_path != str(reader)
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_binding_path_mismatch")
    if tuple(pin.role for pin in binding.source_file_pins_start) != (
        "sqlite_main", "sqlite_wal", "sqlite_shm", "sqlite_rollback_journal"
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_source_pin_roles_invalid")
    if tuple(pin.role for pin in binding.reader_file_pins_finish) != (
        "sqlite_main", "sqlite_wal", "sqlite_shm", "sqlite_rollback_journal"
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_reader_pin_roles_invalid")
    expected_source_snapshot_sha = _canonical_sha256(
        {
            "schema_version": FUNDAMENTAL_READ_SNAPSHOT_SCHEMA,
            "source_database_path": binding.source_database_path,
            "source_file_pins": [pin.to_dict() for pin in binding.source_file_pins_start],
            "captured_files": [item.to_dict() for item in binding.captured_files],
        }
    )
    if expected_source_snapshot_sha != binding.source_snapshot_sha256:
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_source_snapshot_sha_mismatch")
    present_source_roles = tuple(pin.role for pin in binding.source_file_pins_start if pin.present)
    if tuple(item.role for item in binding.captured_files) != present_source_roles:
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_captured_roles_mismatch")
    captured_by_role = {item.role: item for item in binding.captured_files}
    if tuple(item.role for item in binding.reader_files) != present_source_roles:
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_reader_roles_mismatch")
    for reference, expected_pin in zip(
        binding.captured_files,
        binding.captured_file_pins_start,
        strict=True,
    ):
        _poll_cancel(cancel_callback)
        path = _attempt_reference_path(snapshot_root, reference.relative_path)
        actual = _pin_file(reference.role, path, required=True, cancel_callback=cancel_callback)
        _require_single_link(path, "captured")
        if actual != expected_pin or actual.sha256 != reference.sha256 or actual.size_bytes != reference.size_bytes:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_captured_copy_changed")
    for reader_reference in binding.reader_files:
        source_reference = captured_by_role.get(reader_reference.role)
        if source_reference is None or (
            reader_reference.sha256 != source_reference.sha256
            or reader_reference.size_bytes != source_reference.size_bytes
        ):
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_reader_copy_source_mismatch")
        path = _attempt_reference_path(snapshot_root, reader_reference.relative_path)
        _require_single_link(path, "reader")
        if path != Path(binding.reader_database_path).with_name(Path(binding.reader_database_path).name + _role_suffix(reader_reference.role)):
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_reader_reference_path_mismatch")
    reader_pins = _pin_reader_file_set(reader, cancel_callback=cancel_callback)
    if reader_pins != binding.reader_file_pins_finish:
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_reader_finish_pins_changed")
    for pin in reader_pins:
        if pin.present:
            _require_single_link(Path(pin.path), "reader")
    capture_manifest_path = snapshot_root / "snapshot_capture.json"
    capture_manifest_pin = _pin_file(
        "snapshot_capture_manifest",
        capture_manifest_path,
        required=True,
        cancel_callback=cancel_callback,
    )
    if (
        capture_manifest_pin != binding.capture_manifest_pin_start
        or binding.capture_manifest_pin_start != binding.capture_manifest_pin_finish
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_capture_manifest_pin_changed")


def _role_suffix(role: str) -> str:
    return {
        "sqlite_main": "",
        "sqlite_wal": "-wal",
        "sqlite_shm": "-shm",
        "sqlite_rollback_journal": "-journal",
    }[role]


def _require_single_link(path: Path, role: str) -> None:
    _reject_reparse_components(path)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise FundamentalReadSnapshotError(
            f"fundamental_snapshot_exact_{role}_stat_failed:{type(exc).__name__}"
        ) from exc
    _require_regular_non_reparse(path, metadata, role)
    if int(metadata.st_nlink) != 1:
        raise FundamentalReadSnapshotError(f"fundamental_snapshot_exact_{role}_hardlink_refused")


def _verify_snapshot_capture_manifest(
    snapshot_root: Path,
    binding: FundamentalReadSnapshotBinding,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> None:
    path = snapshot_root / "snapshot_capture.json"
    payload, raw = _read_canonical_json_file(path, max_bytes=MAX_SNAPSHOT_CAPTURE_MANIFEST_BYTES)
    expected = _snapshot_capture_manifest_payload(
        snapshot_id=binding.snapshot_id,
        source_database_path=Path(binding.source_database_path),
        source_pins=binding.source_file_pins_start,
        captured_files=binding.captured_files,
        reader_files=binding.reader_files,
        journal_mode=binding.sqlite_journal_mode,
        wal_sidecar_state=binding.wal_sidecar_state,
        source_snapshot_sha256=binding.source_snapshot_sha256,
        source_copy_bytes=binding.source_copy_bytes,
    )
    _poll_cancel(cancel_callback)
    if payload != expected or raw != _canonical_json_bytes(expected):
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_capture_manifest_bytes_mismatch")


def _verify_finished_snapshot_status(
    snapshot_root: Path,
    source_clock: FundamentalSnapshotSourceClock | FundamentalSnapshotSourceClockV2,
    manifest: dict[str, object],
    cancel_callback: Callable[[], bool] | None,
) -> None:
    payload, _raw = _read_canonical_json_file(
        snapshot_root / "attempt_status.json",
        max_bytes=MAX_SNAPSHOT_CAPTURE_MANIFEST_BYTES,
    )
    status_sha = payload.get("status_sha256")
    body = {key: value for key, value in payload.items() if key != "status_sha256"}
    if (
        payload.get("status") != "complete"
        or payload.get("source_clock_sha256") != source_clock.identity_sha256
        or payload.get("cohort_sha256") != manifest.get("cohort_identity_sha256")
        or status_sha != _canonical_sha256(body)
    ):
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_attempt_status_not_complete")
    _poll_cancel(cancel_callback)


def _verify_snapshot_file_inventory(
    snapshot_root: Path,
    binding: FundamentalReadSnapshotBinding,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> None:
    expected_files = {
        "snapshot_capture.json",
        "finished_source_clock.json",
        "attempt_status.json",
        *(item.relative_path for item in binding.captured_files),
        *(item.relative_path for item in binding.reader_files),
    }
    expected_files.update(
        Path(pin.path).relative_to(snapshot_root).as_posix()
        for pin in binding.reader_file_pins_finish
        if pin.present
    )
    expected_dirs = {"captured", "reader"}
    found_files: set[str] = set()
    found_dirs: set[str] = set()
    pending = [snapshot_root]
    total_bytes = 0
    while pending:
        _poll_cancel(cancel_callback)
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_inventory_failed") from exc
        if len(entries) > 10_000 or len(found_files) + len(found_dirs) + len(entries) > 10_000:
            raise FundamentalReadSnapshotError("fundamental_snapshot_exact_inventory_over_limit")
        for entry in entries:
            _poll_cancel(cancel_callback)
            path = Path(entry.path)
            _reject_reparse_components(path)
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise FundamentalReadSnapshotError(
                    "fundamental_snapshot_exact_inventory_entry_changed"
                ) from exc
            _reject_reparse(path, metadata)
            relative = path.relative_to(snapshot_root).as_posix()
            if stat.S_ISDIR(metadata.st_mode):
                found_dirs.add(relative)
                pending.append(path)
            elif stat.S_ISREG(metadata.st_mode):
                found_files.add(relative)
                total_bytes += int(metadata.st_size)
                if total_bytes > 64 * 1024 * 1024 * 1024:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_exact_inventory_bytes_over_limit")
                if int(metadata.st_nlink) != 1:
                    raise FundamentalReadSnapshotError("fundamental_snapshot_exact_inventory_hardlink_refused")
            else:
                raise FundamentalReadSnapshotError("fundamental_snapshot_exact_inventory_non_regular_entry")
    if found_files != expected_files or found_dirs != expected_dirs:
        raise FundamentalReadSnapshotError("fundamental_snapshot_exact_inventory_mismatch")
