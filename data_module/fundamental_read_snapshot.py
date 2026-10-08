"""隔離基本面 SQLite 來源後，才在研究副本上建立唯讀 cohort。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import struct
import sys
from threading import Event, Lock
from typing import Callable, Literal, Sequence
from uuid import uuid4

from data_module.config import TWStockConfig

from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)
from data_module.fundamental_read_copy_contract import (
    FundamentalReadCopyBinding,
    FundamentalReadCopyBindingCancelled,
    FundamentalReadCopyBindingError,
    FundamentalReadCopyFileReference,
)
from data_module.selection_fact_readers import (
    FundamentalFilePin,
    FundamentalReadBatchCandidate,
    FundamentalReadSessionCancelled,
    FundamentalReadSessionError,
    FundamentalSourceClock,
    SelectionFundamentalReadSession,
)


FUNDAMENTAL_READ_SNAPSHOT_SCHEMA: Literal["selection-fundamental-read-snapshot.v1"] = (
    "selection-fundamental-read-snapshot.v1"
)
FUNDAMENTAL_SNAPSHOT_SOURCE_CLOCK_SCHEMA: Literal[
    "selection-fundamental-source-clock.snapshot.v1"
] = "selection-fundamental-source-clock.snapshot.v1"
MAX_SNAPSHOT_SOURCE_FILE_BYTES = 16 * 1024 * 1024 * 1024
SNAPSHOT_COPY_CHUNK_BYTES = 1024 * 1024
MAX_SNAPSHOT_CAPTURE_MANIFEST_BYTES = 256 * 1024
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
    ) -> None:
        self._provider = provider
        self._attempt = attempt
        self._read_session = read_session
        self._cancel_callback = cancel_callback
        self._cancel_event = cancel_event
        self._publication_gate = Lock()
        self._state: Literal["open", "finished", "cancelled", "failed"] = "open"
        self._finished: FinishedFundamentalSnapshotReadCohort | None = None

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
        try:
            reader_provider = _clone_provider_for_reader(
                provider,
                reader_database_path=attempt.reader_database_path,
            )
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
            copy_binding = _make_copy_binding(
                attempt,
                cancel_callback=session_cancelled,
            )
            read_session = SelectionFundamentalReadSession.open(
                reader_provider,
                database_path=attempt.reader_database_path,
                copy_binding=copy_binding,
                stock_codes=stock_codes,
                cutoff_at=cutoff_at,
                cancel_callback=session_cancelled,
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

    def load_batch(self, stock_codes: Sequence[str]) -> FundamentalReadBatchCandidate:
        self._require_open()
        return self._read_session.load_batch(stock_codes)

    def finish(self) -> FinishedFundamentalSnapshotReadCohort:
        if self._finished is not None:
            return self._finished
        self._require_open()
        try:
            _poll_cancel(self._effective_cancel_callback)
            reader_finished = self._read_session.finish()
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
            source_pins_finish = _pin_source_file_set(
                self._attempt.source_database_path,
                cancel_callback=self._effective_cancel_callback,
            )
            if source_pins_finish != self._attempt.source_file_pins_start:
                raise FundamentalReadSnapshotError(
                    "fundamental_snapshot_original_source_changed_before_finish"
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
            source_clock = FundamentalSnapshotSourceClock(
                database_path=str(self._attempt.source_database_path),
                decision_cutoff=reader_clock.decision_cutoff,
                declared_stock_codes=reader_clock.declared_stock_codes,
                schema_identity_sha256=reader_clock.schema_identity_sha256,
                schema_descriptor=reader_clock.schema_descriptor,
                database_file_pins_start=self._attempt.source_file_pins_start,
                database_file_pins_finish=source_pins_finish,
                capture_file_pins_start=reader_clock.capture_file_pins_start,
                capture_file_pins_finish=reader_clock.capture_file_pins_finish,
                snapshot_binding=binding,
            )
            session_id = _canonical_sha256(
                {
                    "schema_version": "selection-fundamental-snapshot-session.v1",
                    "reader_session_id": reader_finished.session_id,
                    "source_clock_sha256": source_clock.identity_sha256,
                }
            )
            finished = FinishedFundamentalSnapshotReadCohort(
                session_id=session_id,
                source_clock=source_clock,
                processed_stock_codes=reader_finished.processed_stock_codes,
                result_identity_by_stock=reader_finished.result_identity_by_stock,
                result_status_counts=reader_finished.result_status_counts,
            )
            _poll_cancel(self._effective_cancel_callback)
            finished_manifest: dict[str, object] = {
                "schema_version": FUNDAMENTAL_READ_SNAPSHOT_SCHEMA,
                "manifest_state": "candidate_pending_publication",
                "snapshot_binding": binding.to_dict(),
                "source_clock": source_clock.to_dict(),
                "cohort_identity_sha256": finished.identity_sha256,
            }
            finished_manifest["manifest_sha256"] = _canonical_sha256(finished_manifest)
            _write_atomic_json(
                self._attempt.snapshot_root / "finished_source_clock.json",
                finished_manifest,
            )
            with self._publication_gate:
                if self._state != "open":
                    raise FundamentalReadSnapshotCancelled(
                        "fundamental_snapshot_cancelled_before_publication"
                    )
                _poll_cancel(self._effective_cancel_callback)
                finished_manifest["manifest_state"] = "complete"
                finished_manifest.pop("manifest_sha256", None)
                finished_manifest["manifest_sha256"] = _canonical_sha256(
                    finished_manifest
                )
                _write_atomic_json(
                    self._attempt.snapshot_root / "finished_source_clock.json",
                    finished_manifest,
                )
                self._state = "finished"
                self._finished = finished
            _write_attempt_status(
                self._attempt.snapshot_root,
                status="complete",
                reason=None,
                source_clock_sha256=source_clock.identity_sha256,
                cohort_sha256=finished.identity_sha256,
            )
            return finished
        except BaseException as exc:
            self._state = "cancelled" if isinstance(
                exc, (FundamentalReadSessionCancelled, FundamentalReadSnapshotCancelled)
            ) else "failed"
            try:
                self._read_session.cancel()
            except BaseException:
                pass
            _write_attempt_status(
                self._attempt.snapshot_root,
                status="cancelled" if self._state == "cancelled" else "failed",
                reason=f"finish_failed:{type(exc).__name__}",
            )
            raise

    def cancel(self) -> bool:
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
) -> RecommendationCurrentFundamentalProvider:
    """沿公開 constructor 建立 copy-bound provider，不改原 instance。"""

    return RecommendationCurrentFundamentalProvider(
        db_file=reader_database_path,
        output_root=provider.output_root,
        monthly_source_root=provider.monthly_source_root,
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
    with temporary.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


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
