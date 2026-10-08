"""固定 full-N 技術來源與 current-only 市場／處置觀察的有界 sidecar。"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import threading
from typing import Any, Literal, NoReturn, cast
from uuid import uuid4

from app_module.daily_market_technical_method_contract_v4 import (
    daily_market_technical_method_contract_v4_sha256,
)
from app_module.daily_market_technical_read_session import (
    DailyMarketTechnicalSourceClockV4,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
    DailyMarketTechnicalUniverseV4Counts,
    DailyMarketTechnicalUniverseV4ParentReceiptReference,
    DailyMarketTechnicalUniverseV4StoreError,
    DailyMarketTechnicalUniverseV4StoreReader,
    DailyMarketTechnicalUniverseV4VerifiedState,
    daily_market_technical_source_clock_v4_from_dict,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import (
    ResearchCaptureWriteScope,
    RuleSampleCaptureError,
)
from data_module.selection_market_assignments import (
    CurrentMarketAssignmentError,
    CurrentMarketAssignmentReader,
    CurrentMarketAssignmentSourcePinV1,
    MarketAssignmentObservationV1,
)
from data_module.selection_official_events import (
    CurrentOfficialDisposalReader,
    CurrentOfficialDisposalSourcePinV1,
    CurrentOfficialDisposalObservationV1,
    SelectionOfficialEventError,
)


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_SCHEMA_V1 = (
    "daily-market-technical-official-disposition-fact-bundle.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_DIRECTORY_V1 = (
    "daily_market_technical_official_disposition_v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES = 4 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROW_BYTES = 16 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROWS_PER_SHARD = 256
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_PATH_CHARS = 4096
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARDS = 391
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SELECTED_CODES = 256
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_SELECTED_ROWS_SCHEMA_V1 = (
    "daily-market-technical-official-disposition-selected-rows.v1"
)

_BUNDLE_ROOT_CHILDREN = frozenset({".attempts", "manifests", "objects"})
_MANIFEST_KEYS = frozenset({
    "schema_version",
    "scope",
    "historical_pit_eligible",
    "official_available_at",
    "projection_status",
    "source_coverage_status",
    "technical_store",
    "source_pins",
    "source_inventory",
    "cohort_summary",
    "source_coverage",
    "row_count",
    "row_shards",
    "bundle_identity_sha256",
})
_TECHNICAL_STORE_KEYS = frozenset({
    "output_root",
    "generation_identity_sha256",
    "plan_identity_sha256",
    "plan_sha256",
    "receipt_identity_sha256",
    "receipt_sha256",
    "receipt_status",
    "cohort_identity_sha256",
    "decision_date",
    "declared_count",
    "included_count",
    "excluded_count",
    "source_clock_identity_sha256",
    "source_clock",
    "method_contracts_sha256",
    "counts",
    "parent_references",
})
_SOURCE_PINS_KEYS = frozenset({"market_assignment", "official_disposal"})
_SOURCE_INVENTORY_KEYS = frozenset({
    "technical_database",
    "technical_store_root",
    "technical_parent_roots",
    "market_assignment_root",
    "official_disposal_root",
})
_COHORT_SUMMARY_KEYS = frozenset({
    "identity_sha256",
    "decision_date",
    "declared_count",
    "included_count",
    "excluded_count",
    "declared_stock_codes_sha256",
    "exclusion_reasons_sha256",
})
_SOURCE_COVERAGE_KEYS = frozenset({
    "market_assignment_counts",
    "official_disposal_counts",
    "market_capture_statuses",
    "official_capture_statuses",
    "market_snapshot_partial_failure",
    "official_snapshot_partial_failure",
    "market_partial_observation_count",
    "official_partial_observation_count",
    "incomplete_reasons",
})
_ROW_KEYS = frozenset({
    "schema_version",
    "stock_code",
    "cohort_role",
    "exclusion_reason",
    "technical_status",
    "technical_missing_data",
    "market_assignment",
    "official_disposal",
})
_ROW_SCHEMA = "daily-market-technical-official-disposition-fact-row.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_OFFICIAL_SYMBOL_RE = re.compile(r"^[0-9]{4,6}$")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_VERIFIED_STATE_SEAL = object()
_VERIFIED_STORAGE_SEAL = object()
_SELECTED_ROWS_SEAL_ISSUER = object()


class DailyMarketTechnicalOfficialDispositionBundleError(ValueError):
    """F17 sidecar 的穩定拒絕碼。"""

    def __init__(self, code: str, *, cause_code: str | None = None) -> None:
        self.code = code
        self.cause_code = cause_code
        super().__init__(code)


class DailyMarketTechnicalOfficialDispositionBundleCancelled(
    DailyMarketTechnicalOfficialDispositionBundleError
):
    """發布前取消；不代表已有 complete bundle。"""


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionBundleReferenceV1:
    output_root: str
    bundle_identity_sha256: str
    manifest_relative_path: str
    manifest_sha256: str
    row_count: int
    projection_status: Literal["complete"]
    technical_receipt_status: str
    source_coverage_status: Literal["complete", "partial"]


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionFactRowV1:
    """以 canonical JSON 保存的單列 immutable projection。"""

    body_json: str
    stock_code: str
    cohort_role: Literal["included", "excluded"]

    def to_dict(self) -> dict[str, object]:
        payload = _strict_json_object(self.body_json.encode("utf-8"), "row_json_invalid")
        return payload


@dataclass(frozen=True, slots=True)
class _BundleRowLocatorV1:
    stock_code: str
    shard_index: int
    byte_offset: int
    line_length: int
    line_sha256: str


class _VerifiedBundleStorageV1:
    """由 exact reader 發行的不可變分片與列位置索引。"""

    output_root: Path
    bundle_identity_sha256: str
    manifest_relative_path: str
    manifest_sha256: str
    shard_payloads: tuple[bytes, ...]
    row_locators: tuple[_BundleRowLocatorV1, ...]
    index_identity_sha256: str
    _seal: object
    _locked: bool

    __slots__ = (
        "output_root",
        "bundle_identity_sha256",
        "manifest_relative_path",
        "manifest_sha256",
        "shard_payloads",
        "row_locators",
        "index_identity_sha256",
        "_seal",
        "_locked",
    )

    def __init__(
        self,
        *,
        output_root: Path,
        bundle_identity_sha256: str,
        manifest_relative_path: str,
        manifest_sha256: str,
        shard_payloads: tuple[bytes, ...],
        row_locators: tuple[_BundleRowLocatorV1, ...],
        cancel_callback: Callable[[], bool] | None,
        _issuer: object,
    ) -> None:
        if _issuer is not _VERIFIED_STORAGE_SEAL:
            _fail("verified_storage_not_reader_issued")
        _check_read_cancel(cancel_callback)
        index_digest = sha256()
        index_digest.update(_canonical_json({
            "schema_version": "daily-market-technical-official-disposition-row-index.v1",
            "output_root": str(output_root),
            "bundle_identity_sha256": bundle_identity_sha256,
            "manifest_relative_path": manifest_relative_path,
            "manifest_sha256": manifest_sha256,
            "shard_count": len(shard_payloads),
            "row_count": len(row_locators),
        }).encode("utf-8"))
        for index, payload in enumerate(shard_payloads):
            _check_read_cancel(cancel_callback)
            index_digest.update(b"\n")
            index_digest.update(_canonical_json({
                "shard_index": index,
                "size_bytes": len(payload),
                "sha256": _sha256_bytes(payload),
            }).encode("utf-8"))
            _check_read_cancel(cancel_callback)
        for index, item in enumerate(row_locators):
            if index % 256 == 0:
                _check_read_cancel(cancel_callback)
            index_digest.update(_canonical_json({
                "stock_code": item.stock_code,
                "shard_index": item.shard_index,
                "byte_offset": item.byte_offset,
                "line_length": item.line_length,
                "line_sha256": item.line_sha256,
            }).encode("utf-8"))
        _check_read_cancel(cancel_callback)
        object.__setattr__(self, "output_root", output_root)
        object.__setattr__(self, "bundle_identity_sha256", bundle_identity_sha256)
        object.__setattr__(self, "manifest_relative_path", manifest_relative_path)
        object.__setattr__(self, "manifest_sha256", manifest_sha256)
        object.__setattr__(self, "shard_payloads", shard_payloads)
        object.__setattr__(self, "row_locators", row_locators)
        object.__setattr__(self, "index_identity_sha256", index_digest.hexdigest())
        object.__setattr__(self, "_seal", _VERIFIED_STORAGE_SEAL)
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_locked", False):
            raise AttributeError("verified bundle storage is immutable")
        object.__setattr__(self, name, value)

    def validate_reference(
        self,
        reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
    ) -> None:
        if (
            self._seal is not _VERIFIED_STORAGE_SEAL
            or str(self.output_root) != reference.output_root
            or self.bundle_identity_sha256 != reference.bundle_identity_sha256
            or self.manifest_relative_path != reference.manifest_relative_path
            or self.manifest_sha256 != reference.manifest_sha256
            or len(self.row_locators) != reference.row_count
            or len(self.shard_payloads) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARDS
        ):
            _fail("verified_storage_reference_mismatch")


class _SelectedRowsSealV1:
    __slots__ = ("identity_sha256", "_locked")

    identity_sha256: str
    _locked: bool

    def __init__(self, identity_sha256: str, *, _issuer: object) -> None:
        if _issuer is not _SELECTED_ROWS_SEAL_ISSUER:
            _fail("selected_rows_not_reader_issued")
        object.__setattr__(self, "identity_sha256", identity_sha256)
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_locked", False):
            raise AttributeError("selected rows seal is immutable")
        object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1:
    """依 exact bundle pin 讀回的有界列；不包含完整母體 facts。"""

    output_root: str
    bundle_identity_sha256: str
    manifest_relative_path: str
    manifest_sha256: str
    requested_stock_codes: tuple[str, ...]
    ordered_stock_codes_sha256: str
    rows: tuple[DailyMarketTechnicalOfficialDispositionFactRowV1, ...]
    rows_identity_sha256: str
    materialization_identity_sha256: str
    _seal: _SelectedRowsSealV1

    def __post_init__(self) -> None:
        if type(self._seal) is not _SelectedRowsSealV1:
            _fail("selected_rows_not_reader_issued")
        if (
            not 0 <= len(self.requested_stock_codes)
            <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SELECTED_CODES
            or len(self.rows) != len(self.requested_stock_codes)
            or tuple(row.stock_code for row in self.rows) != self.requested_stock_codes
        ):
            _fail("selected_rows_shape_invalid")
        for value in (
            self.bundle_identity_sha256,
            self.manifest_sha256,
            self.ordered_stock_codes_sha256,
            self.rows_identity_sha256,
            self.materialization_identity_sha256,
        ):
            _require_sha256(value, "selected_rows_identity_invalid")
        if self.ordered_stock_codes_sha256 != _sha256_json(list(self.requested_stock_codes)):
            _fail("selected_rows_ordered_codes_digest_mismatch")
        row_payloads = [row.to_dict() for row in self.rows]
        if self.rows_identity_sha256 != _sha256_json(row_payloads):
            _fail("selected_rows_digest_mismatch")
        expected_identity = _sha256_json({
            "schema_version": "daily-market-technical-official-disposition-selected-rows.identity.v1",
            "output_root": self.output_root,
            "bundle_identity_sha256": self.bundle_identity_sha256,
            "manifest_relative_path": self.manifest_relative_path,
            "manifest_sha256": self.manifest_sha256,
            "ordered_stock_codes_sha256": self.ordered_stock_codes_sha256,
            "requested_count": len(self.requested_stock_codes),
            "rows_identity_sha256": self.rows_identity_sha256,
            "row_count": len(self.rows),
        })
        if (
            self.materialization_identity_sha256 != expected_identity
            or self._seal.identity_sha256 != expected_identity
        ):
            _fail("selected_rows_materialization_identity_mismatch")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_SELECTED_ROWS_SCHEMA_V1,
            "output_root": self.output_root,
            "bundle_identity_sha256": self.bundle_identity_sha256,
            "manifest_relative_path": self.manifest_relative_path,
            "manifest_sha256": self.manifest_sha256,
            "requested_stock_codes": list(self.requested_stock_codes),
            "ordered_stock_codes_sha256": self.ordered_stock_codes_sha256,
            "rows": [row.to_dict() for row in self.rows],
            "rows_identity_sha256": self.rows_identity_sha256,
            "materialization_identity_sha256": self.materialization_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1:
    reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1
    manifest_json: str
    _storage: _VerifiedBundleStorageV1
    _seal: object

    def __post_init__(self) -> None:
        if self._seal is not _VERIFIED_STATE_SEAL or type(self._storage) is not _VerifiedBundleStorageV1:
            _fail("verified_state_not_reader_issued")
        self._storage.validate_reference(self.reference)
        raw_manifest = self.manifest_json.encode("utf-8")
        if _sha256_bytes(raw_manifest) != self.reference.manifest_sha256:
            _fail("verified_state_manifest_digest_mismatch")
        manifest = _strict_json_object(raw_manifest, "manifest_json_invalid")
        _validate_manifest_header(manifest, expected_identity=self.reference.bundle_identity_sha256)
        if (
            manifest.get("row_count") != self.reference.row_count
            or self.reference.manifest_relative_path
            != f"manifests/{self.reference.bundle_identity_sha256}.json"
        ):
            _fail("verified_state_manifest_reference_mismatch")

    @property
    def _shard_payloads(self) -> tuple[bytes, ...]:
        """保留舊讀取端的唯讀分片存取形狀。"""
        return self._storage.shard_payloads

    @property
    def manifest(self) -> dict[str, object]:
        return _strict_json_object(self.manifest_json.encode("utf-8"), "manifest_json_invalid")

    def iter_verified_rows(
        self,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> Iterator[DailyMarketTechnicalOfficialDispositionFactRowV1]:
        """只從 read_exact 已完整核驗並固定在記憶體的分片逐列讀回。"""

        _validate_cancel_callback(cancel_callback)
        for shard in self._shard_payloads:
            stream = BytesIO(shard)
            while True:
                _check_read_cancel(cancel_callback)
                line = stream.readline(DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROW_BYTES + 2)
                if not line:
                    break
                if not line.endswith(b"\n") or len(line) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROW_BYTES + 1:
                    _fail("row_line_bound_or_terminator_invalid")
                payload = _strict_json_object(line[:-1], "row_json_invalid")
                row = _row_from_payload(payload)
                yield row

    def read_selected_rows(
        self,
        explicit_stock_codes: Sequence[str],
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1:
        """以有界二分索引讀指定列；沒有全檔掃描 fallback。"""

        _validate_cancel_callback(cancel_callback)
        if self._seal is not _VERIFIED_STATE_SEAL:
            _fail("verified_state_not_reader_issued")
        self._storage.validate_reference(self.reference)
        codes = _validate_selected_stock_codes(explicit_stock_codes, cancel_callback)
        _check_read_cancel(cancel_callback)
        manifest = self._read_pinned_manifest(cancel_callback)
        if not codes:
            selected = _selected_rows_result(self.reference, (), ())
            _check_read_cancel(cancel_callback)
            return selected

        locators: list[_BundleRowLocatorV1] = []
        for code in codes:
            _check_read_cancel(cancel_callback)
            locator = _find_row_locator(self._storage.row_locators, code)
            if locator is None:
                _fail("selected_stock_code_not_in_bundle")
            locators.append(locator)

        refs = manifest.get("row_shards")
        if not isinstance(refs, list) or len(refs) != len(self._storage.shard_payloads):
            _fail("selected_manifest_shard_list_invalid")
        hit_payloads: dict[int, bytes] = {}
        for locator in locators:
            _check_read_cancel(cancel_callback)
            if locator.shard_index not in hit_payloads:
                reference = refs[locator.shard_index]
                hit_payloads[locator.shard_index] = self._read_selected_shard(
                    locator.shard_index,
                    reference,
                    cancel_callback,
                )

        rows: list[DailyMarketTechnicalOfficialDispositionFactRowV1] = []
        for code, locator in zip(codes, locators, strict=True):
            _check_read_cancel(cancel_callback)
            raw = hit_payloads.get(locator.shard_index)
            if raw is None:
                _fail("selected_shard_not_loaded")
            start = locator.byte_offset
            end = start + locator.line_length
            line = raw[start:end]
            if (
                len(line) != locator.line_length
                or not line.endswith(b"\n")
                or len(line) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROW_BYTES + 1
                or _sha256_bytes(line) != locator.line_sha256
            ):
                _fail("selected_row_bytes_sha_mismatch")
            payload = _strict_json_object(line[:-1], "row_json_invalid")
            row = _row_from_payload(payload)
            if row.stock_code != code or row.stock_code != locator.stock_code:
                _fail("selected_row_code_mismatch")
            rows.append(row)
            _check_read_cancel(cancel_callback)
        _check_read_cancel(cancel_callback)
        selected = _selected_rows_result(self.reference, codes, tuple(rows))
        _check_read_cancel(cancel_callback)
        return selected

    def _read_pinned_manifest(
        self,
        cancel_callback: Callable[[], bool] | None,
    ) -> dict[str, object]:
        _check_read_cancel(cancel_callback)
        root = self._storage.output_root
        relative = self._storage.manifest_relative_path
        if (
            str(root) != self.reference.output_root
            or relative != self.reference.manifest_relative_path
        ):
            _fail("selected_manifest_root_binding_mismatch")
        path = _resolve_bundle_relative(root, relative, "selected_manifest_path_invalid")
        raw = _read_bounded_regular_file(
            path,
            DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES,
            "selected_manifest_missing_or_invalid",
        )
        _check_read_cancel(cancel_callback)
        if _sha256_bytes(raw) != self.reference.manifest_sha256:
            _fail("selected_manifest_bytes_sha_mismatch")
        if raw != self.manifest_json.encode("utf-8"):
            _fail("selected_manifest_bytes_changed")
        manifest = _strict_json_object(raw, "manifest_json_invalid")
        _validate_manifest_header(manifest, expected_identity=self.reference.bundle_identity_sha256)
        if manifest.get("row_count") != self.reference.row_count:
            _fail("selected_manifest_row_count_mismatch")
        return manifest

    def _read_selected_shard(
        self,
        shard_index: int,
        reference: object,
        cancel_callback: Callable[[], bool] | None,
    ) -> bytes:
        _check_read_cancel(cancel_callback)
        if not isinstance(reference, Mapping) or set(reference) != {
            "shard_index", "relative_path", "sha256", "size_bytes",
            "first_stock_code", "last_stock_code", "row_count",
        }:
            _fail("selected_shard_reference_invalid")
        if type(reference.get("shard_index")) is not int or reference.get("shard_index") != shard_index:
            _fail("selected_shard_order_invalid")
        digest = _require_sha256(reference.get("sha256"), "selected_shard_hash_invalid")
        relative = reference.get("relative_path")
        if relative != f"objects/{digest}.jsonl":
            _fail("selected_shard_content_address_invalid")
        size = reference.get("size_bytes")
        if (
            type(size) is not int
            or not 0 < size <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES
        ):
            _fail("selected_shard_size_invalid")
        path = _resolve_bundle_relative(
            self._storage.output_root,
            cast(str, relative),
            "selected_shard_path_invalid",
        )
        raw = _read_bounded_regular_file(
            path,
            DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES,
            "selected_shard_missing_or_invalid",
        )
        _check_read_cancel(cancel_callback)
        if len(raw) != size or _sha256_bytes(raw) != digest:
            _fail("selected_shard_bytes_sha_mismatch")
        return raw


class DailyMarketTechnicalOfficialDispositionBundleWriterV1:
    """以明示 ResearchCaptureWriteScope 保存 exact full-N F17 facts。"""

    def __init__(
        self,
        output_root: str | Path,
        *,
        research_scope: ResearchCaptureWriteScope,
    ) -> None:
        if not isinstance(research_scope, ResearchCaptureWriteScope):
            _fail("research_scope_required")
        try:
            research_scope.validate()
            canonical, _ = _canonical_path(output_root, must_exist=False, expect_directory=True)
            scope_root, _ = _canonical_path(research_scope.root, must_exist=False, expect_directory=True)
        except (OSError, RuleSampleCaptureError, ValueError) as error:
            raise _wrapped_error("writer_root_invalid", error) from error
        if canonical == scope_root or not _is_child(canonical, scope_root):
            _fail("writer_root_outside_research_scope")
        self.output_root = canonical
        self.research_scope = research_scope
        self._cancel_event = threading.Event()
        self._publication_gate = threading.Lock()
        self._published = False
        self._busy = False
        self._busy_gate = threading.Lock()

    def cancel(self) -> Literal["cancel_requested", "already_published"]:
        """取消會與最終 manifest create-only 發布使用同一 gate。"""

        with self._publication_gate:
            if self._published:
                return "already_published"
            self._cancel_event.set()
            return "cancel_requested"

    def create_from_pins(
        self,
        *,
        store_output_root: str | Path,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        expected_plan_sha256: str,
        receipt_identity_sha256: str,
        expected_receipt_sha256: str,
        market_assignment_source_pin: CurrentMarketAssignmentSourcePinV1,
        official_disposal_source_pin: CurrentOfficialDisposalSourcePinV1,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionBundleReferenceV1:
        """由指定的三組 exact pins 產生 sidecar；絕不讀 latest pointer。"""

        _validate_cancel_callback(cancel_callback)
        with self._busy_gate:
            if self._busy:
                _fail("writer_already_running")
            self._busy = True
        attempt_root: Path | None = None
        try:
            self._check_cancelled(cancel_callback)
            if not isinstance(market_assignment_source_pin, CurrentMarketAssignmentSourcePinV1):
                _fail("market_assignment_typed_pin_required")
            if not isinstance(official_disposal_source_pin, CurrentOfficialDisposalSourcePinV1):
                _fail("official_disposal_typed_pin_required")
            _assert_output_disjoint(
                self.output_root,
                {
                    "technical_database": str(self.research_scope.source_database),
                    "technical_store_root": str(store_output_root),
                    "technical_parent_roots": [],
                    "market_assignment_root": market_assignment_source_pin.output_root,
                    "official_disposal_root": official_disposal_source_pin.output_root,
                },
            )
            store_state, store_reader, clock, market_reader, disposal_reader = self._open_pinned_sources(
                store_output_root=store_output_root,
                generation_identity_sha256=generation_identity_sha256,
                plan_identity_sha256=plan_identity_sha256,
                expected_plan_sha256=expected_plan_sha256,
                receipt_identity_sha256=receipt_identity_sha256,
                expected_receipt_sha256=expected_receipt_sha256,
                market_assignment_source_pin=market_assignment_source_pin,
                official_disposal_source_pin=official_disposal_source_pin,
                cancel_callback=cancel_callback,
            )
            store_descriptor = _store_descriptor(
                store_state,
                store_reader.output_root,
                expected_plan_sha256=expected_plan_sha256,
                expected_receipt_sha256=expected_receipt_sha256,
            )
            source_inventory = _source_inventory(
                store_state,
                store_reader.output_root,
                market_assignment_source_pin,
                official_disposal_source_pin,
                clock,
            )
            _assert_output_disjoint(self.output_root, source_inventory)
            self._preflight_output_root()
            self._check_cancelled(cancel_callback)

            attempt_root = self._create_attempt_root()
            shard_refs, row_count, coverage = self._write_row_shards(
                attempt_root,
                store_state,
                market_reader,
                disposal_reader,
                market_assignment_source_pin,
                official_disposal_source_pin,
                cancel_callback,
            )
            cohort = store_state.plan.cohort
            if row_count != len(cohort.declared_stock_codes):
                _fail("projection_declared_row_count_mismatch")
            if row_count > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS:
                _fail("projection_declared_limit")

            source_coverage_status = cast(
                Literal["complete", "partial"],
                "complete" if not coverage["incomplete_reasons"] else "partial",
            )
            manifest_body: dict[str, object] = {
                "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_SCHEMA_V1,
                "scope": "current_only",
                "historical_pit_eligible": False,
                "official_available_at": None,
                "projection_status": "complete",
                "source_coverage_status": source_coverage_status,
                "technical_store": store_descriptor,
                "source_pins": {
                    "market_assignment": market_assignment_source_pin.to_dict(),
                    "official_disposal": official_disposal_source_pin.to_dict(),
                },
                "source_inventory": source_inventory,
                "cohort_summary": _cohort_summary(store_state),
                "source_coverage": coverage,
                "row_count": row_count,
                "row_shards": shard_refs,
            }
            identity = _sha256_json(manifest_body)
            manifest = {**manifest_body, "bundle_identity_sha256": identity}
            manifest_raw = _canonical_json(manifest).encode("utf-8")
            if len(manifest_raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES:
                _fail("manifest_byte_limit")
            manifest_candidate = attempt_root / "manifest.json.tmp"
            self._check_cancelled(cancel_callback)
            self._publish_objects(attempt_root, shard_refs, cancel_callback)
            self._repin_before_publish(
                store_output_root=store_reader.output_root,
                generation_identity_sha256=generation_identity_sha256,
                plan_identity_sha256=plan_identity_sha256,
                expected_plan_sha256=expected_plan_sha256,
                receipt_identity_sha256=receipt_identity_sha256,
                expected_receipt_sha256=expected_receipt_sha256,
                market_assignment_source_pin=market_assignment_source_pin,
                official_disposal_source_pin=official_disposal_source_pin,
                cutoff=clock.decision_cutoff,
                cancel_callback=cancel_callback,
            )
            _write_new_file(manifest_candidate, manifest_raw, "manifest_candidate_write_failed")
            self._check_cancelled(cancel_callback)
            manifest_relative_path = f"manifests/{identity}.json"
            manifest_path = self.output_root / PurePosixPath(manifest_relative_path)
            _ensure_directory(self.output_root / "manifests")
            _check_output_path(manifest_path, may_not_exist=True)
            with self._publication_gate:
                if self._cancel_event.is_set():
                    _fail_cancelled()
                try:
                    os.link(
                        to_internal_io_path(manifest_candidate),
                        to_internal_io_path(manifest_path),
                    )
                except FileExistsError:
                    existing = _read_bounded_regular_file(
                        manifest_path,
                        DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES,
                        "existing_manifest_invalid",
                    )
                    if existing != manifest_raw:
                        _fail("identity_collision_or_existing_manifest_conflict")
                    self._published = True
                else:
                    self._published = True
                    _fsync_directory(manifest_path.parent)
                    if manifest_candidate.parent != attempt_root:
                        _fail("manifest_candidate_scope_invalid")
                    _unlink_own_candidate(
                        manifest_candidate,
                        published_path=manifest_path,
                        expected_link_count=2,
                    )
                final_raw = _read_bounded_regular_file(
                    manifest_path,
                    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES,
                    "published_manifest_readback_failed",
                )
                if final_raw != manifest_raw:
                    _fail("published_manifest_readback_mismatch")

            manifest_sha = _sha256_bytes(manifest_raw)
            reference = DailyMarketTechnicalOfficialDispositionBundleReferenceV1(
                output_root=str(self.output_root),
                bundle_identity_sha256=identity,
                manifest_relative_path=manifest_relative_path,
                manifest_sha256=manifest_sha,
                row_count=row_count,
                projection_status="complete",
                technical_receipt_status=store_state.receipt.status,
                source_coverage_status=source_coverage_status,
            )
            self._remove_successful_attempt(attempt_root)
            attempt_root = None
            return reference
        except DailyMarketTechnicalOfficialDispositionBundleError:
            raise
        except (
            DailyMarketTechnicalUniverseV4StoreError,
            CurrentMarketAssignmentError,
            SelectionOfficialEventError,
            RuleSampleCaptureError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            raise _wrapped_error("bundle_create_failed", error) from error
        finally:
            with self._busy_gate:
                self._busy = False

    def _open_pinned_sources(
        self,
        *,
        store_output_root: str | Path,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        expected_plan_sha256: str,
        receipt_identity_sha256: str,
        expected_receipt_sha256: str,
        market_assignment_source_pin: CurrentMarketAssignmentSourcePinV1,
        official_disposal_source_pin: CurrentOfficialDisposalSourcePinV1,
        cancel_callback: Callable[[], bool] | None,
    ) -> tuple[
        DailyMarketTechnicalUniverseV4VerifiedState,
        DailyMarketTechnicalUniverseV4StoreReader,
        DailyMarketTechnicalSourceClockV4,
        CurrentMarketAssignmentReader,
        CurrentOfficialDisposalReader,
    ]:
        if not isinstance(market_assignment_source_pin, CurrentMarketAssignmentSourcePinV1):
            _fail("market_assignment_typed_pin_required")
        if not isinstance(official_disposal_source_pin, CurrentOfficialDisposalSourcePinV1):
            _fail("official_disposal_typed_pin_required")
        self.research_scope.validate()
        _check_output_path(self.output_root, may_not_exist=True)
        try:
            store_reader = DailyMarketTechnicalUniverseV4StoreReader(store_output_root)
            store_state = store_reader.read_exact_with_verified_parent_callback(
                generation_identity_sha256,
                plan_identity_sha256,
                receipt_identity_sha256,
                expected_receipt_sha256=expected_receipt_sha256,
                expected_plan_sha256=expected_plan_sha256,
                cancel_callback=lambda: self._cancelled(cancel_callback),
            )
        except DailyMarketTechnicalUniverseV4StoreError as error:
            if error.code == "technical_universe_v4_read_cancelled":
                _fail_cancelled()
            raise _wrapped_error("technical_store_exact_read_failed", error) from error
        self._check_cancelled(cancel_callback)
        try:
            clock = store_state.plan.source_clock
        except (AttributeError, TypeError, ValueError) as error:
            raise _wrapped_error("technical_source_clock_invalid", error) from error
        if clock.decision_date != store_state.plan.cohort.decision_date:
            _fail("technical_decision_date_mismatch")
        expected_database = Path(str(clock.database_path)).resolve(strict=True)
        scope_database = Path(str(self.research_scope.source_database)).resolve(strict=True)
        if expected_database != scope_database:
            _fail("research_scope_database_mismatch")
        cutoff = clock.decision_cutoff.astimezone(timezone.utc)
        market_cutoff = _parse_aware_datetime(
            market_assignment_source_pin.cutoff_at,
            "market_assignment_cutoff_invalid",
        ).astimezone(timezone.utc)
        if market_cutoff != cutoff:
            _fail("market_assignment_cutoff_mismatch")
        try:
            market_reader = CurrentMarketAssignmentReader.from_exact(
                market_assignment_source_pin,
                cutoff_at=clock.decision_cutoff,
            )
            disposal_reader = CurrentOfficialDisposalReader.from_exact(
                official_disposal_source_pin,
                cutoff_at=clock.decision_cutoff,
            )
        except CurrentMarketAssignmentError as error:
            raise _wrapped_error("market_assignment_exact_read_failed", error) from error
        except SelectionOfficialEventError as error:
            raise _wrapped_error("official_disposal_exact_read_failed", error) from error
        self.research_scope.validate()
        self._check_cancelled(cancel_callback)
        return store_state, store_reader, clock, market_reader, disposal_reader

    def _write_row_shards(
        self,
        attempt_root: Path,
        state: DailyMarketTechnicalUniverseV4VerifiedState,
        market_reader: CurrentMarketAssignmentReader,
        disposal_reader: CurrentOfficialDisposalReader,
        market_pin: CurrentMarketAssignmentSourcePinV1,
        disposal_pin: CurrentOfficialDisposalSourcePinV1,
        cancel_callback: Callable[[], bool] | None,
    ) -> tuple[list[dict[str, object]], int, dict[str, object]]:
        _ensure_directory(self.output_root / "objects")
        cohort = state.plan.cohort
        status_by_code, missing_by_code = _technical_code_status(state)
        shard_refs: list[dict[str, object]] = []
        coverage = _new_coverage(market_pin, disposal_pin)
        buffer = bytearray()
        buffer_count = 0
        first_code: str | None = None
        last_code: str | None = None
        total_bytes = 0
        row_count = 0
        shard_index = 0

        def flush_shard() -> None:
            nonlocal buffer, buffer_count, first_code, last_code, total_bytes, shard_index
            if not buffer_count:
                return
            if shard_index >= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARDS:
                _fail("shard_count_limit")
            raw = bytes(buffer)
            if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES:
                _fail("shard_byte_limit")
            digest = _sha256_bytes(raw)
            name = f"shard-{shard_index + 1:06d}.jsonl"
            candidate = attempt_root / name
            _write_new_file(candidate, raw, "row_shard_write_failed")
            shard_refs.append({
                "shard_index": shard_index,
                "relative_path": f"objects/{digest}.jsonl",
                "sha256": digest,
                "size_bytes": len(raw),
                "first_stock_code": first_code,
                "last_stock_code": last_code,
                "row_count": buffer_count,
            })
            total_bytes += len(raw)
            if total_bytes > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_BYTES:
                _fail("bundle_byte_limit")
            shard_index += 1
            buffer = bytearray()
            buffer_count = 0
            first_code = None
            last_code = None

        included_set = set(cohort.included_stock_codes)
        exclusion_reasons = dict(cohort.exclusion_reasons)
        for stock_code in cohort.declared_stock_codes:
            self._check_cancelled(cancel_callback)
            role: Literal["included", "excluded"] = (
                "included" if stock_code in included_set else "excluded"
            )
            technical_status = "excluded" if role == "excluded" else status_by_code[stock_code]
            technical_missing_data: bool | None = (
                None if role == "excluded" or technical_status == "pending"
                else stock_code in missing_by_code
            )
            market_payload = _market_observation_payload(
                stock_code,
                market_reader,
                market_pin,
            )
            market_state = str(market_payload["state"])
            if market_state not in {"assigned_twse", "assigned_tpex", "unknown"}:
                _fail("market_assignment_state_invalid")
            disposal_payload = _disposal_observation_payload(
                stock_code,
                market_payload,
                disposal_reader,
                disposal_pin,
            )
            _record_coverage(coverage, market_payload, disposal_payload)
            row_payload: dict[str, object] = {
                "schema_version": _ROW_SCHEMA,
                "stock_code": stock_code,
                "cohort_role": role,
                "exclusion_reason": exclusion_reasons.get(stock_code),
                "technical_status": technical_status,
                "technical_missing_data": technical_missing_data,
                "market_assignment": market_payload,
                "official_disposal": disposal_payload,
            }
            row_raw = _canonical_json(row_payload).encode("utf-8")
            if len(row_raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROW_BYTES:
                _fail("row_byte_limit")
            line = row_raw + b"\n"
            if buffer_count and (
                buffer_count >= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROWS_PER_SHARD
                or len(buffer) + len(line) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES
            ):
                flush_shard()
            if not buffer_count:
                first_code = stock_code
            buffer.extend(line)
            buffer_count += 1
            last_code = stock_code
            row_count += 1
            self._check_cancelled(cancel_callback)
        flush_shard()
        coverage = _finish_coverage(coverage)
        return shard_refs, row_count, coverage

    def _repin_before_publish(
        self,
        *,
        store_output_root: str | Path,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        expected_plan_sha256: str,
        receipt_identity_sha256: str,
        expected_receipt_sha256: str,
        market_assignment_source_pin: CurrentMarketAssignmentSourcePinV1,
        official_disposal_source_pin: CurrentOfficialDisposalSourcePinV1,
        cutoff: datetime,
        cancel_callback: Callable[[], bool] | None,
    ) -> None:
        self._check_cancelled(cancel_callback)
        try:
            reader = DailyMarketTechnicalUniverseV4StoreReader(store_output_root)
            reader.read_exact_with_verified_parent_callback(
                generation_identity_sha256,
                plan_identity_sha256,
                receipt_identity_sha256,
                expected_receipt_sha256=expected_receipt_sha256,
                expected_plan_sha256=expected_plan_sha256,
                cancel_callback=lambda: self._cancelled(cancel_callback),
            )
            self._check_cancelled(cancel_callback)
            CurrentMarketAssignmentReader.from_exact(
                market_assignment_source_pin,
                cutoff_at=cutoff,
            )
            self._check_cancelled(cancel_callback)
            CurrentOfficialDisposalReader.from_exact(
                official_disposal_source_pin,
                cutoff_at=cutoff,
            )
        except DailyMarketTechnicalUniverseV4StoreError as error:
            if error.code == "technical_universe_v4_read_cancelled":
                _fail_cancelled()
            raise _wrapped_error("technical_store_changed_before_publish", error) from error
        except CurrentMarketAssignmentError as error:
            raise _wrapped_error("market_assignment_changed_before_publish", error) from error
        except SelectionOfficialEventError as error:
            raise _wrapped_error("official_disposal_changed_before_publish", error) from error
        self._check_cancelled(cancel_callback)
        self.research_scope.validate()

    def _publish_objects(
        self,
        attempt_root: Path,
        shard_refs: list[dict[str, object]],
        cancel_callback: Callable[[], bool] | None,
    ) -> None:
        objects_root = self.output_root / "objects"
        _ensure_directory(objects_root)
        for item in shard_refs:
            self._check_cancelled(cancel_callback)
            relative = cast(str, item["relative_path"])
            target = _resolve_bundle_relative(self.output_root, relative, "object_path_invalid")
            shard_index = item["shard_index"]
            if type(shard_index) is not int or shard_index < 0:
                _fail("staged_shard_index_invalid")
            source = attempt_root / f"shard-{shard_index + 1:06d}.jsonl"
            candidate_raw = _read_bounded_regular_file(
                source,
                DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES,
                "staged_object_invalid",
            )
            if _sha256_bytes(candidate_raw) != item["sha256"]:
                _fail("staged_object_hash_mismatch")
            _check_output_path(target, may_not_exist=True)
            try:
                os.link(to_internal_io_path(source), to_internal_io_path(target))
            except FileExistsError:
                raw = _read_bounded_regular_file(
                    target,
                    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES,
                    "existing_object_invalid",
                )
                if _sha256_bytes(raw) != item["sha256"]:
                    _fail("existing_object_hash_mismatch")
                if raw != candidate_raw:
                    _fail("existing_object_content_mismatch")
            else:
                raw = _read_bounded_regular_file(
                    target,
                    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES,
                    "published_object_readback_failed",
                    expected_link_count=2,
                )
                if raw != candidate_raw or _sha256_bytes(raw) != item["sha256"]:
                    _fail("published_object_hash_mismatch")
                if source.parent != attempt_root:
                    _fail("object_candidate_scope_invalid")
                _unlink_own_candidate(
                    source,
                    published_path=target,
                    expected_link_count=2,
                )
                raw = _read_bounded_regular_file(
                    target,
                    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES,
                    "published_object_single_link_readback_failed",
                )
                if raw != candidate_raw or _sha256_bytes(raw) != item["sha256"]:
                    _fail("published_object_single_link_hash_mismatch")
            _check_output_path(target, may_not_exist=False)
            _fsync_directory(objects_root)

    def _preflight_output_root(self) -> None:
        _check_output_path(self.output_root, may_not_exist=True)
        if not self.output_root.exists():
            return
        info = _lstat(self.output_root)
        if not stat.S_ISDIR(info.st_mode) or _is_link_or_reparse(info):
            _fail("bundle_root_not_regular_directory")
        with os.scandir(to_internal_io_path(self.output_root)) as entries:
            names = {entry.name for entry in entries}
        if not names.issubset(_BUNDLE_ROOT_CHILDREN):
            _fail("bundle_root_contains_unknown_entries")
        for name in names:
            child = self.output_root / name
            info = _lstat(child)
            if not stat.S_ISDIR(info.st_mode) or _is_link_or_reparse(info):
                _fail("bundle_root_child_invalid")

    def _create_attempt_root(self) -> Path:
        _ensure_directory(self.output_root)
        attempts_root = self.output_root / ".attempts"
        _ensure_directory(attempts_root)
        candidate = attempts_root / f"attempt-{uuid4().hex}"
        try:
            os.mkdir(to_internal_io_path(candidate))
        except FileExistsError as error:
            raise DailyMarketTechnicalOfficialDispositionBundleError("attempt_identity_collision") from error
        _check_output_path(candidate, may_not_exist=False)
        return candidate

    def _remove_successful_attempt(self, attempt_root: Path) -> None:
        _check_output_path(attempt_root, may_not_exist=False)
        if attempt_root.parent != self.output_root / ".attempts":
            _fail("attempt_cleanup_path_invalid")
        shutil.rmtree(to_internal_io_path(attempt_root))

    def _cancelled(self, callback: Callable[[], bool] | None) -> bool:
        if self._cancel_event.is_set():
            return True
        if callback is None:
            return False
        value = callback()
        if type(value) is not bool:
            raise DailyMarketTechnicalOfficialDispositionBundleError("cancel_callback_invalid")
        if value:
            self._cancel_event.set()
            return True
        return False

    def _check_cancelled(self, callback: Callable[[], bool] | None) -> None:
        try:
            if self._cancelled(callback):
                _fail_cancelled()
        except DailyMarketTechnicalOfficialDispositionBundleError:
            raise
        except BaseException as error:
            raise DailyMarketTechnicalOfficialDispositionBundleError(
                "cancel_callback_failed",
                cause_code=type(error).__name__,
            ) from error


class DailyMarketTechnicalOfficialDispositionBundleReaderV1:
    """指定 bundle identity 的唯讀 exact reader；不追 pointer 或開來源 DB。"""

    def __init__(self, output_root: str | Path) -> None:
        try:
            canonical, _ = _canonical_path(output_root, must_exist=True, expect_directory=True)
        except (OSError, ValueError) as error:
            raise _wrapped_error("reader_root_invalid", error) from error
        self.output_root = canonical

    def read_exact(
        self,
        bundle_identity_sha256: str,
        *,
        expected_manifest_sha256: str,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1:
        _validate_cancel_callback(cancel_callback)
        identity = _require_sha256(bundle_identity_sha256, "bundle_identity_invalid")
        expected_manifest = _require_sha256(expected_manifest_sha256, "expected_manifest_sha_invalid")
        manifest_path = self.output_root / "manifests" / f"{identity}.json"
        try:
            _check_read_cancel(cancel_callback)
            raw = _read_bounded_regular_file(
                manifest_path,
                DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES,
                "manifest_missing_or_invalid",
            )
            if _sha256_bytes(raw) != expected_manifest:
                _fail("manifest_bytes_sha_mismatch")
            manifest = _strict_json_object(raw, "manifest_json_invalid")
            _validate_manifest_header(manifest, expected_identity=identity)
            shard_payloads, row_locators = self._read_all_shards(manifest, cancel_callback)
            verified = self._verify_exact_sources_and_rows(manifest, shard_payloads, cancel_callback)
            if verified.row_count != manifest["row_count"]:
                _fail("verified_row_count_mismatch")
            reference = DailyMarketTechnicalOfficialDispositionBundleReferenceV1(
                output_root=str(self.output_root),
                bundle_identity_sha256=identity,
                manifest_relative_path=f"manifests/{identity}.json",
                manifest_sha256=expected_manifest,
                row_count=verified.row_count,
                projection_status="complete",
                technical_receipt_status=verified.technical_receipt_status,
                source_coverage_status=cast(
                    Literal["complete", "partial"], manifest["source_coverage_status"]
                ),
            )
            storage = _VerifiedBundleStorageV1(
                output_root=self.output_root,
                bundle_identity_sha256=identity,
                manifest_relative_path=reference.manifest_relative_path,
                manifest_sha256=expected_manifest,
                shard_payloads=shard_payloads,
                row_locators=row_locators,
                cancel_callback=cancel_callback,
                _issuer=_VERIFIED_STORAGE_SEAL,
            )
            state = DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1(
                reference=reference,
                manifest_json=_canonical_json(manifest),
                _storage=storage,
                _seal=_VERIFIED_STATE_SEAL,
            )
            _check_read_cancel(cancel_callback)
            return state
        except DailyMarketTechnicalOfficialDispositionBundleError:
            raise
        except (
            DailyMarketTechnicalUniverseV4StoreError,
            CurrentMarketAssignmentError,
            SelectionOfficialEventError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            raise _wrapped_error("bundle_exact_read_failed", error) from error

    def _read_all_shards(
        self,
        manifest: Mapping[str, object],
        cancel_callback: Callable[[], bool] | None,
    ) -> tuple[tuple[bytes, ...], tuple[_BundleRowLocatorV1, ...]]:
        refs = manifest.get("row_shards")
        if not isinstance(refs, list) or len(refs) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARDS:
            _fail("shard_reference_list_invalid")
        total = 0
        result: list[bytes] = []
        row_locators: list[_BundleRowLocatorV1] = []
        seen_codes: set[str] = set()
        previous_code: str | None = None
        total_rows = 0
        for index, value in enumerate(cast(list[object], refs)):
            _check_read_cancel(cancel_callback)
            if not isinstance(value, Mapping) or set(value) != {
                "shard_index", "relative_path", "sha256", "size_bytes",
                "first_stock_code", "last_stock_code", "row_count",
            }:
                _fail("shard_reference_invalid")
            if type(value["shard_index"]) is not int or value["shard_index"] != index:
                _fail("shard_order_invalid")
            size = value["size_bytes"]
            count = value["row_count"]
            if type(size) is not int or not 0 < size <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES:
                _fail("shard_size_invalid")
            if type(count) is not int or not 0 < count <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROWS_PER_SHARD:
                _fail("shard_row_count_invalid")
            digest = _require_sha256(value["sha256"], "shard_hash_invalid")
            relative = value["relative_path"]
            if relative != f"objects/{digest}.jsonl":
                _fail("shard_content_address_invalid")
            path = _resolve_bundle_relative(self.output_root, cast(str, relative), "shard_path_invalid")
            raw = _read_bounded_regular_file(
                path,
                DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES,
                "shard_missing_or_invalid",
            )
            if len(raw) != size or _sha256_bytes(raw) != digest:
                _fail("shard_bytes_sha_mismatch")
            shard_first: str | None = None
            shard_last: str | None = None
            line_count = 0
            stream = BytesIO(raw)
            while True:
                _check_read_cancel(cancel_callback)
                line = stream.readline(DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROW_BYTES + 2)
                if not line:
                    break
                if not line.endswith(b"\n") or len(line) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROW_BYTES + 1:
                    _fail("row_line_bound_or_terminator_invalid")
                payload = _strict_json_object(line[:-1], "row_json_invalid")
                row = _row_from_payload(payload)
                code = row.stock_code
                if previous_code is not None and code <= previous_code:
                    _fail("stock_code_global_order_or_duplicate")
                if code in seen_codes:
                    _fail("stock_code_duplicate")
                seen_codes.add(code)
                previous_code = code
                shard_first = code if shard_first is None else shard_first
                shard_last = code
                line_count += 1
                total_rows += 1
                row_locators.append(_BundleRowLocatorV1(
                    stock_code=code,
                    shard_index=index,
                    byte_offset=stream.tell() - len(line),
                    line_length=len(line),
                    line_sha256=_sha256_bytes(line),
                ))
            if line_count != count or shard_first != value["first_stock_code"] or shard_last != value["last_stock_code"]:
                _fail("shard_row_identity_mismatch")
            total += len(raw)
            if total > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_BYTES:
                _fail("bundle_byte_limit")
            result.append(raw)
        if total_rows != manifest.get("row_count"):
            _fail("manifest_row_count_mismatch")
        return tuple(result), tuple(row_locators)

    def _verify_exact_sources_and_rows(
        self,
        manifest: Mapping[str, object],
        shard_payloads: tuple[bytes, ...],
        cancel_callback: Callable[[], bool] | None,
    ) -> "_ExactBundleVerification":
        store_descriptor_value = manifest["technical_store"]
        pins_value = manifest["source_pins"]
        inventory_value = manifest["source_inventory"]
        if not isinstance(store_descriptor_value, Mapping) or set(store_descriptor_value) != _TECHNICAL_STORE_KEYS:
            _fail("technical_store_descriptor_invalid")
        if not isinstance(pins_value, Mapping) or set(pins_value) != _SOURCE_PINS_KEYS:
            _fail("source_pin_mapping_invalid")
        if not isinstance(inventory_value, Mapping) or set(inventory_value) != _SOURCE_INVENTORY_KEYS:
            _fail("source_inventory_invalid")
        store_descriptor = cast(Mapping[str, object], store_descriptor_value)
        pins = cast(Mapping[str, object], pins_value)
        inventory = cast(Mapping[str, object], inventory_value)

        market_pin = CurrentMarketAssignmentSourcePinV1.from_dict(pins["market_assignment"])
        disposal_pin = CurrentOfficialDisposalSourcePinV1.from_dict(pins["official_disposal"])
        store_root = cast(str, store_descriptor["output_root"])
        generation_id = cast(str, store_descriptor["generation_identity_sha256"])
        plan_id = cast(str, store_descriptor["plan_identity_sha256"])
        receipt_id = cast(str, store_descriptor["receipt_identity_sha256"])
        plan_sha = cast(str, store_descriptor["plan_sha256"])
        receipt_sha = cast(str, store_descriptor["receipt_sha256"])
        _require_sha256(plan_sha, "plan_sha_invalid")
        _require_sha256(receipt_sha, "receipt_sha_invalid")
        try:
            store_reader = DailyMarketTechnicalUniverseV4StoreReader(store_root)
            store_state = store_reader.read_exact_with_verified_parent_callback(
                generation_id,
                plan_id,
                receipt_id,
                expected_receipt_sha256=receipt_sha,
                expected_plan_sha256=plan_sha,
                cancel_callback=lambda: _callback_true(cancel_callback),
            )
            clock = store_state.plan.source_clock
            market_reader = CurrentMarketAssignmentReader.from_exact(
                market_pin,
                cutoff_at=clock.decision_cutoff,
            )
            disposal_reader = CurrentOfficialDisposalReader.from_exact(
                disposal_pin,
                cutoff_at=clock.decision_cutoff,
            )
        except DailyMarketTechnicalUniverseV4StoreError as error:
            if error.code == "technical_universe_v4_read_cancelled":
                _fail_cancelled()
            raise _wrapped_error("technical_store_exact_read_failed", error) from error
        except CurrentMarketAssignmentError as error:
            raise _wrapped_error("market_assignment_exact_read_failed", error) from error
        except SelectionOfficialEventError as error:
            raise _wrapped_error("official_disposal_exact_read_failed", error) from error

        expected_store_descriptor = _store_descriptor(
            store_state,
            store_reader.output_root,
            expected_plan_sha256=plan_sha,
            expected_receipt_sha256=receipt_sha,
        )
        if expected_store_descriptor != store_descriptor:
            _fail("technical_store_descriptor_mismatch")
        expected_inventory = _source_inventory(
            store_state,
            store_reader.output_root,
            market_pin,
            disposal_pin,
            clock,
        )
        if expected_inventory != inventory:
            _fail("source_inventory_mismatch")
        _assert_output_disjoint(self.output_root, expected_inventory)
        if market_reader.source_pin.to_dict() != market_pin.to_dict():
            _fail("market_assignment_pin_reverification_mismatch")
        if disposal_reader.source_pin.to_dict() != disposal_pin.to_dict():
            _fail("official_disposal_pin_reverification_mismatch")

        cohort = store_state.plan.cohort
        if manifest["cohort_summary"] != _cohort_summary(store_state):
            _fail("cohort_summary_mismatch")
        if manifest["row_count"] != len(cohort.declared_stock_codes):
            _fail("cohort_declared_row_count_mismatch")
        status_by_code, missing_by_code = _technical_code_status(store_state)
        codes = cohort.declared_stock_codes
        included = set(cohort.included_stock_codes)
        exclusions = dict(cohort.exclusion_reasons)
        coverage = _new_coverage(market_pin, disposal_pin)
        shard_index = 0
        shard_stream: BytesIO | None = None
        current_ref: Mapping[str, object] | None = None
        current_rows = 0
        verified_count = 0
        for stock_code in codes:
            _check_read_cancel(cancel_callback)
            if shard_stream is None or current_ref is None:
                if shard_index >= len(shard_payloads):
                    _fail("shard_missing_rows")
                shard_stream = BytesIO(shard_payloads[shard_index])
                ref_value = cast(list[object], manifest["row_shards"])[shard_index]
                current_ref = cast(Mapping[str, object], ref_value)
                current_rows = 0
            line = shard_stream.readline(DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROW_BYTES + 2)
            if not line:
                _fail("shard_rows_missing")
            actual_payload = _strict_json_object(line[:-1], "row_json_invalid")
            actual_row = _row_from_payload(actual_payload)
            role: Literal["included", "excluded"] = "included" if stock_code in included else "excluded"
            technical_status = "excluded" if role == "excluded" else status_by_code[stock_code]
            missing: bool | None = (
                None if role == "excluded" or technical_status == "pending"
                else stock_code in missing_by_code
            )
            market_payload = _market_observation_payload(stock_code, market_reader, market_pin)
            disposal_payload = _disposal_observation_payload(
                stock_code,
                market_payload,
                disposal_reader,
                disposal_pin,
            )
            _record_coverage(coverage, market_payload, disposal_payload)
            expected_payload: dict[str, object] = {
                "schema_version": _ROW_SCHEMA,
                "stock_code": stock_code,
                "cohort_role": role,
                "exclusion_reason": exclusions.get(stock_code),
                "technical_status": technical_status,
                "technical_missing_data": missing,
                "market_assignment": market_payload,
                "official_disposal": disposal_payload,
            }
            expected_raw = _canonical_json(expected_payload)
            if actual_row.body_json != expected_raw:
                _fail("row_exact_source_projection_mismatch")
            current_rows += 1
            verified_count += 1
            if current_rows == current_ref["row_count"]:
                if shard_stream.read(1):
                    _fail("shard_has_extra_rows")
                current_ref = None
                shard_stream = None
                shard_index += 1
        if shard_index != len(shard_payloads) or current_ref is not None:
            _fail("shard_extra_rows_or_refs")
        computed_coverage = _finish_coverage(coverage)
        if computed_coverage != manifest["source_coverage"]:
            _fail("source_coverage_counts_mismatch")
        expected_status = "complete" if not computed_coverage["incomplete_reasons"] else "partial"
        if manifest["source_coverage_status"] != expected_status:
            _fail("source_coverage_status_mismatch")
        return _ExactBundleVerification(verified_count, store_state.receipt.status)


@dataclass(frozen=True, slots=True)
class _ExactBundleVerification:
    row_count: int
    technical_receipt_status: str


def _store_descriptor(
    state: DailyMarketTechnicalUniverseV4VerifiedState,
    output_root: Path,
    *,
    expected_plan_sha256: str,
    expected_receipt_sha256: str,
) -> dict[str, object]:
    plan = state.plan
    receipt = state.receipt
    plan_payload = plan.to_dict()
    receipt_payload = receipt.to_dict()
    plan_raw = plan.to_json().encode("utf-8")
    receipt_raw = receipt.to_json().encode("utf-8")
    plan_sha = _sha256_bytes(plan_raw)
    receipt_sha = _sha256_bytes(receipt_raw)
    if plan_sha != expected_plan_sha256:
        _fail("technical_plan_bytes_sha_mismatch")
    if receipt_sha != expected_receipt_sha256:
        _fail("technical_receipt_bytes_sha_mismatch")
    if receipt.identity_sha256 != receipt_payload.get("receipt_identity_sha256"):
        _fail("technical_receipt_identity_mismatch")
    cohort = plan.cohort
    counts = state.counts
    if counts.declared_count != len(cohort.declared_stock_codes):
        _fail("technical_declared_count_mismatch")
    if counts.included_count != len(cohort.included_stock_codes):
        _fail("technical_included_count_mismatch")
    if counts.excluded_count != len(cohort.excluded_stock_codes):
        _fail("technical_excluded_count_mismatch")
    source_clock = plan_payload.get("source_clock")
    if not isinstance(source_clock, Mapping):
        _fail("technical_source_clock_invalid")
    parsed_clock = daily_market_technical_source_clock_v4_from_dict(source_clock)
    source_clock_sha = cast(str, plan_payload.get("source_clock_identity_sha256"))
    if parsed_clock.identity_sha256 != source_clock_sha:
        _fail("technical_source_clock_identity_mismatch")
    method_sha = plan_payload.get("method_contracts_sha256")
    if method_sha != daily_market_technical_method_contract_v4_sha256():
        _fail("technical_method_version_unsupported")
    parent_refs: list[dict[str, object]] = []
    for segment_index, reference in state.segment_parent_references:
        if not isinstance(reference, DailyMarketTechnicalUniverseV4ParentReceiptReference):
            _fail("technical_parent_reference_type_invalid")
        parent_refs.append({
            "segment_index": segment_index,
            "reference": reference.to_dict(),
        })
    return {
        "output_root": str(output_root),
        "generation_identity_sha256": plan.generation_identity_sha256,
        "plan_identity_sha256": plan.identity_sha256,
        "plan_sha256": plan_sha,
        "receipt_identity_sha256": receipt.identity_sha256,
        "receipt_sha256": receipt_sha,
        "receipt_status": receipt.status,
        "cohort_identity_sha256": cohort.cohort_identity_sha256,
        "decision_date": cohort.decision_date.isoformat(),
        "declared_count": counts.declared_count,
        "included_count": counts.included_count,
        "excluded_count": counts.excluded_count,
        "source_clock_identity_sha256": source_clock_sha,
        "source_clock": dict(cast(Mapping[str, object], source_clock)),
        "method_contracts_sha256": cast(str, method_sha),
        "counts": counts.to_dict(),
        "parent_references": parent_refs,
    }


def _source_inventory(
    state: DailyMarketTechnicalUniverseV4VerifiedState,
    store_root: Path,
    market_pin: CurrentMarketAssignmentSourcePinV1,
    disposal_pin: CurrentOfficialDisposalSourcePinV1,
    clock: DailyMarketTechnicalSourceClockV4,
) -> dict[str, object]:
    parent_roots = sorted({reference.parent_root for _, reference in state.segment_parent_references})
    return {
        "technical_database": clock.database_path,
        "technical_store_root": str(store_root),
        "technical_parent_roots": parent_roots,
        "market_assignment_root": market_pin.output_root,
        "official_disposal_root": disposal_pin.output_root,
    }


def _assert_output_disjoint(output_root: Path, inventory: Mapping[str, object]) -> None:
    try:
        target, _ = _canonical_path(output_root, must_exist=False, expect_directory=True)
        paths: list[tuple[str, Path]] = []
        for key in ("technical_database", "technical_store_root", "market_assignment_root", "official_disposal_root"):
            value = inventory.get(key)
            if not isinstance(value, str):
                _fail("source_inventory_path_invalid")
            canonical, _ = _canonical_path(
                value,
                must_exist=True,
                expect_directory=key != "technical_database",
            )
            paths.append((key, canonical))
        parents = inventory.get("technical_parent_roots")
        if not isinstance(parents, list):
            _fail("source_inventory_parent_roots_invalid")
        for value in parents:
            if not isinstance(value, str):
                _fail("source_inventory_parent_root_invalid")
            canonical, _ = _canonical_path(value, must_exist=True, expect_directory=True)
            paths.append(("technical_parent_root", canonical))
    except DailyMarketTechnicalOfficialDispositionBundleError:
        raise
    except (OSError, ValueError) as error:
        raise _wrapped_error("source_inventory_path_invalid", error) from error
    for _, source_path in paths:
        if _paths_overlap(target, source_path):
            _fail("bundle_root_overlaps_source")


def _cohort_summary(state: DailyMarketTechnicalUniverseV4VerifiedState) -> dict[str, object]:
    cohort = state.plan.cohort
    code_list = list(cohort.declared_stock_codes)
    reasons = {code: reason for code, reason in cohort.exclusion_reasons}
    return {
        "identity_sha256": cohort.cohort_identity_sha256,
        "decision_date": cohort.decision_date.isoformat(),
        "declared_count": len(cohort.declared_stock_codes),
        "included_count": len(cohort.included_stock_codes),
        "excluded_count": len(cohort.excluded_stock_codes),
        "declared_stock_codes_sha256": _sha256_json(code_list),
        "exclusion_reasons_sha256": _sha256_json(reasons),
    }


def _technical_code_status(
    state: DailyMarketTechnicalUniverseV4VerifiedState,
) -> tuple[dict[str, str], set[str]]:
    cohort = state.plan.cohort
    plan_payload = state.plan.to_dict()
    segments = plan_payload.get("segments")
    if not isinstance(segments, list):
        _fail("technical_segment_list_invalid")
    completed = {index for index, _ in state.segment_parent_references}
    processed_codes: set[str] = set()
    for index in completed:
        if not 0 <= index < len(segments):
            _fail("technical_completed_segment_invalid")
        segment = cast(list[object], segments)[index]
        if not isinstance(segment, Mapping):
            _fail("technical_segment_invalid")
        start = segment.get("included_start")
        stop = segment.get("included_stop")
        if type(start) is not int or type(stop) is not int or not 0 <= start <= stop <= len(cohort.included_stock_codes):
            _fail("technical_segment_range_invalid")
        processed_codes.update(cohort.included_stock_codes[start:stop])
    status = {
        code: "processed" if code in processed_codes else "pending"
        for code in cohort.included_stock_codes
    }
    missing = set(state.missing_data_stock_codes)
    if not missing.issubset(processed_codes):
        _fail("technical_missing_data_not_processed")
    return status, missing


def _market_observation_payload(
    stock_code: str,
    reader: CurrentMarketAssignmentReader,
    pin: CurrentMarketAssignmentSourcePinV1,
) -> dict[str, object]:
    if not _OFFICIAL_SYMBOL_RE.fullmatch(stock_code):
        return {
            "schema_version": "current-market-assignment-observation.v1",
            "symbol": stock_code,
            "state": "unknown",
            "market": None,
            "reason_code": "market_symbol_unsupported_by_reader",
            "roster_source_ids": [],
            "roster_sha256s": [],
            "source_data_dates": [],
            "snapshot_observed_at": pin.snapshot_observed_at,
            "pointer_published_at": pin.pointer_published_at,
            "cutoff_at": pin.cutoff_at,
            "termination_evidence": "not_verified",
            "source_pin_identity_sha256": pin.identity_sha256,
            "scope": "current_only",
            "historical_pit_eligible": False,
            "official_available_at": None,
        }
    try:
        observation = reader.get(stock_code)
    except CurrentMarketAssignmentError as error:
        raise _wrapped_error("market_assignment_projection_failed", error) from error
    if observation.source_pin_identity_sha256 != pin.identity_sha256:
        _fail("market_assignment_projection_pin_mismatch")
    return _market_observation_to_dict(observation)


def _market_observation_to_dict(observation: MarketAssignmentObservationV1) -> dict[str, object]:
    return {
        "schema_version": observation.schema_version,
        "symbol": observation.symbol,
        "state": observation.state,
        "market": observation.market,
        "reason_code": observation.reason_code,
        "roster_source_ids": list(observation.roster_source_ids),
        "roster_sha256s": list(observation.roster_sha256s),
        "source_data_dates": [
            {"source_id": source_id, "dates": list(dates)}
            for source_id, dates in observation.source_data_dates
        ],
        "snapshot_observed_at": observation.snapshot_observed_at,
        "pointer_published_at": observation.pointer_published_at,
        "cutoff_at": observation.cutoff_at,
        "termination_evidence": observation.termination_evidence,
        "source_pin_identity_sha256": observation.source_pin_identity_sha256,
        "scope": observation.scope,
        "historical_pit_eligible": observation.historical_pit_eligible,
        "official_available_at": observation.official_available_at,
    }


def _disposal_observation_payload(
    stock_code: str,
    market_payload: Mapping[str, object],
    reader: CurrentOfficialDisposalReader,
    pin: CurrentOfficialDisposalSourcePinV1,
) -> dict[str, object]:
    market = market_payload.get("market")
    if market not in {"twse", "tpex"}:
        return {
            "symbol": stock_code,
            "market": None,
            "state": "unknown",
            "observed_at": None,
            "observed_date": None,
            "events": [],
            "source_data_dates": [],
            "source_id": None,
            "source_status": "not_queried",
            "source_parse_status": None,
            "source_raw_sha256": None,
            "source_pin_sha256": pin.identity_sha256,
            "reason_code": "market_assignment_unknown",
            "source_warnings": [],
            "partial_failure": pin.snapshot_partial_failure,
            "scope": "current_only",
            "historical_pit_eligible": False,
            "official_available_at": None,
            "source_capture_dates_by_id": _capture_dates_by_source(pin),
        }
    try:
        observation = reader.get(stock_code, market=cast(Literal["twse", "tpex"], market))
    except SelectionOfficialEventError as error:
        raise _wrapped_error("official_disposal_projection_failed", error) from error
    if observation.source_pin_sha256 != pin.identity_sha256:
        _fail("official_disposal_projection_pin_mismatch")
    return _disposal_observation_to_dict(observation)


def _disposal_observation_to_dict(
    observation: CurrentOfficialDisposalObservationV1,
) -> dict[str, object]:
    return {
        "symbol": observation.symbol,
        "market": observation.market,
        "state": observation.state,
        "observed_at": observation.observed_at.isoformat() if observation.observed_at else None,
        "observed_date": observation.observed_date.isoformat() if observation.observed_date else None,
        "events": [event.to_dict() for event in observation.events],
        "source_data_dates": list(observation.source_data_dates),
        "source_id": observation.source_id,
        "source_status": observation.source_status,
        "source_parse_status": observation.source_parse_status,
        "source_raw_sha256": observation.source_raw_sha256,
        "source_pin_sha256": observation.source_pin_sha256,
        "reason_code": observation.reason_code,
        "source_warnings": list(observation.source_warnings),
        "partial_failure": observation.partial_failure,
        "scope": observation.scope,
        "historical_pit_eligible": observation.historical_pit_eligible,
        "official_available_at": None,
        "source_capture_dates_by_id": [],
    }


def _capture_dates_by_source(pin: CurrentOfficialDisposalSourcePinV1) -> list[dict[str, object]]:
    return [
        {
            "source_id": capture.source_id,
            "captured_at": capture.captured_at,
            "source_data_dates": list(capture.source_data_dates),
            "raw_sha256": capture.raw_sha256,
            "status": capture.status,
            "parse_status": capture.parse_status,
        }
        for capture in pin.captures
    ]


def _new_coverage(
    market_pin: CurrentMarketAssignmentSourcePinV1,
    disposal_pin: CurrentOfficialDisposalSourcePinV1,
) -> dict[str, object]:
    return {
        "market_assignment_counts": {"assigned_twse": 0, "assigned_tpex": 0, "unknown": 0},
        "official_disposal_counts": {
            "reported_upcoming": 0,
            "reported_active": 0,
            "reported_elapsed_only": 0,
            "unknown": 0,
        },
        "market_capture_statuses": [
            {
                "source_id": capture.source_id,
                "market": capture.market,
                "status": capture.status,
                "parse_status": capture.parse_status,
                "captured_at": capture.captured_at,
                "source_data_dates": list(capture.source_data_dates),
                "row_count": capture.row_count,
                "row_schema_sha256": capture.row_schema_sha256,
                "raw_sha256": capture.raw_sha256,
                "raw_bytes": capture.raw_bytes,
            }
            for capture in market_pin.captures
        ],
        "official_capture_statuses": [
            {
                "source_id": capture.source_id,
                "status": capture.status,
                "parse_status": capture.parse_status,
                "captured_at": capture.captured_at,
                "source_data_dates": list(capture.source_data_dates),
                "raw_sha256": capture.raw_sha256,
                "raw_bytes": capture.raw_bytes,
            }
            for capture in disposal_pin.captures
        ],
        "market_snapshot_partial_failure": market_pin.snapshot_partial_failure,
        "official_snapshot_partial_failure": disposal_pin.snapshot_partial_failure,
        "market_partial_observation_count": 0,
        "official_partial_observation_count": 0,
        "incomplete_reasons": [],
    }


def _record_coverage(
    coverage: dict[str, object],
    market: Mapping[str, object],
    disposal: Mapping[str, object],
) -> None:
    market_counts = cast(dict[str, int], coverage["market_assignment_counts"])
    market_state = market.get("state")
    if market_state not in market_counts:
        _fail("market_assignment_state_invalid")
    market_counts[cast(str, market_state)] += 1
    disposal_counts = cast(dict[str, int], coverage["official_disposal_counts"])
    disposal_state = disposal.get("state")
    if disposal_state not in disposal_counts:
        _fail("official_disposal_state_invalid")
    disposal_counts[cast(str, disposal_state)] += 1
    if disposal.get("partial_failure") is True:
        coverage["official_partial_observation_count"] = cast(
            int, coverage["official_partial_observation_count"]
        ) + 1


def _finish_coverage(coverage: dict[str, object]) -> dict[str, object]:
    reasons: set[str] = set()
    market_counts = cast(dict[str, int], coverage["market_assignment_counts"])
    disposal_counts = cast(dict[str, int], coverage["official_disposal_counts"])
    if market_counts["unknown"]:
        reasons.add("market_assignment_unknown_rows")
    if disposal_counts["unknown"]:
        reasons.add("official_disposal_unknown_rows")
    market_statuses = cast(list[dict[str, object]], coverage["market_capture_statuses"])
    if any(
        item.get("status") != "captured"
        or item.get("parse_status") != "parsed"
        or type(item.get("row_count")) is not int
        or cast(int, item.get("row_count")) <= 0
        for item in market_statuses
    ):
        reasons.add("market_roster_capture_incomplete")
    official_statuses = cast(list[dict[str, object]], coverage["official_capture_statuses"])
    if any(
        item.get("status") != "captured" or item.get("parse_status") != "parsed"
        for item in official_statuses
    ):
        reasons.add("official_disposal_capture_incomplete")
    if coverage["market_snapshot_partial_failure"] is True:
        reasons.add("market_snapshot_partial_failure")
    if coverage["official_snapshot_partial_failure"] is True:
        reasons.add("official_snapshot_partial_failure")
    if cast(int, coverage["official_partial_observation_count"]):
        reasons.add("official_disposal_partial_observations")
    coverage["incomplete_reasons"] = sorted(reasons)
    return coverage


def _validate_manifest_header(
    manifest: Mapping[str, object],
    *,
    expected_identity: str,
) -> None:
    if set(manifest) != _MANIFEST_KEYS:
        _fail("manifest_keys_invalid")
    if manifest.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_SCHEMA_V1:
        _fail("manifest_schema_unsupported")
    if manifest.get("scope") != "current_only" or manifest.get("historical_pit_eligible") is not False:
        _fail("manifest_scope_invalid")
    if manifest.get("official_available_at") is not None:
        _fail("manifest_available_at_must_be_unknown")
    if manifest.get("projection_status") != "complete":
        _fail("manifest_projection_not_complete")
    if manifest.get("source_coverage_status") not in {"complete", "partial"}:
        _fail("manifest_source_coverage_status_invalid")
    if manifest.get("bundle_identity_sha256") != expected_identity:
        _fail("manifest_identity_mismatch")
    body = {key: value for key, value in manifest.items() if key != "bundle_identity_sha256"}
    if _sha256_json(body) != expected_identity:
        _fail("manifest_identity_digest_mismatch")
    row_count = manifest.get("row_count")
    if type(row_count) is not int or not 0 <= row_count <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS:
        _fail("manifest_row_count_invalid")
    if not isinstance(manifest.get("row_shards"), list):
        _fail("manifest_row_shards_invalid")
    cohort = manifest.get("cohort_summary")
    if not isinstance(cohort, Mapping) or set(cohort) != _COHORT_SUMMARY_KEYS:
        _fail("manifest_cohort_summary_invalid")
    coverage = manifest.get("source_coverage")
    if not isinstance(coverage, Mapping) or set(coverage) != _SOURCE_COVERAGE_KEYS:
        _fail("manifest_source_coverage_invalid")
    inventory = manifest.get("source_inventory")
    if not isinstance(inventory, Mapping) or set(inventory) != _SOURCE_INVENTORY_KEYS:
        _fail("manifest_source_inventory_invalid")


def _row_from_payload(payload: Mapping[str, object]) -> DailyMarketTechnicalOfficialDispositionFactRowV1:
    if set(payload) != _ROW_KEYS or payload.get("schema_version") != _ROW_SCHEMA:
        _fail("row_schema_invalid")
    code = payload.get("stock_code")
    if not isinstance(code, str) or not _STOCK_CODE_RE.fullmatch(code):
        _fail("row_stock_code_invalid")
    role = payload.get("cohort_role")
    if role not in {"included", "excluded"}:
        _fail("row_cohort_role_invalid")
    reason = payload.get("exclusion_reason")
    if role == "included" and reason is not None:
        _fail("included_row_has_exclusion_reason")
    if role == "excluded" and (not isinstance(reason, str) or not reason.strip()):
        _fail("excluded_row_missing_exclusion_reason")
    technical_status = payload.get("technical_status")
    if technical_status not in {"processed", "pending", "excluded"}:
        _fail("row_technical_status_invalid")
    if role == "excluded" and technical_status != "excluded":
        _fail("excluded_row_technical_status_invalid")
    if role == "included" and technical_status == "excluded":
        _fail("included_row_technical_status_invalid")
    missing = payload.get("technical_missing_data")
    if role == "excluded" or technical_status == "pending":
        if missing is not None:
            _fail("row_missing_data_state_invalid")
    elif type(missing) is not bool:
        _fail("row_missing_data_state_invalid")
    market = payload.get("market_assignment")
    disposal = payload.get("official_disposal")
    if not isinstance(market, Mapping) or not isinstance(disposal, Mapping):
        _fail("row_observation_shape_invalid")
    if market.get("symbol") != code or market.get("historical_pit_eligible") is not False or market.get("official_available_at") is not None:
        _fail("row_market_observation_scope_invalid")
    if disposal.get("symbol") != code or disposal.get("historical_pit_eligible") is not False or disposal.get("official_available_at") is not None:
        _fail("row_disposal_observation_scope_invalid")
    if market.get("state") not in {"assigned_twse", "assigned_tpex", "unknown"}:
        _fail("row_market_observation_state_invalid")
    if disposal.get("state") not in {"reported_upcoming", "reported_active", "reported_elapsed_only", "unknown"}:
        _fail("row_disposal_observation_state_invalid")
    body = _canonical_json(dict(payload))
    return DailyMarketTechnicalOfficialDispositionFactRowV1(
        body_json=body,
        stock_code=code,
        cohort_role=cast(Literal["included", "excluded"], role),
    )


def _validate_selected_stock_codes(
    value: Sequence[str],
    cancel_callback: Callable[[], bool] | None,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail("selected_stock_codes_invalid")
    result: list[str] = []
    seen: set[str] = set()
    try:
        iterator = iter(value)
        while True:
            _check_read_cancel(cancel_callback)
            try:
                code = next(iterator)
            except StopIteration:
                break
            if len(result) >= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SELECTED_CODES:
                _fail("selected_stock_codes_limit")
            if not isinstance(code, str) or not _STOCK_CODE_RE.fullmatch(code):
                _fail("selected_stock_code_invalid")
            if code in seen:
                _fail("selected_stock_code_duplicate")
            seen.add(code)
            result.append(code)
    except DailyMarketTechnicalOfficialDispositionBundleError:
        raise
    except BaseException as error:
        raise DailyMarketTechnicalOfficialDispositionBundleError(
            "selected_stock_codes_iteration_failed",
            cause_code=type(error).__name__,
        ) from error
    return tuple(result)


def _find_row_locator(
    locators: tuple[_BundleRowLocatorV1, ...],
    stock_code: str,
) -> _BundleRowLocatorV1 | None:
    low = 0
    high = len(locators)
    while low < high:
        middle = (low + high) // 2
        candidate = locators[middle]
        if candidate.stock_code < stock_code:
            low = middle + 1
        else:
            high = middle
    if low < len(locators) and locators[low].stock_code == stock_code:
        return locators[low]
    return None


def _selected_rows_result(
    reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
    stock_codes: tuple[str, ...],
    rows: tuple[DailyMarketTechnicalOfficialDispositionFactRowV1, ...],
) -> DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1:
    ordered_sha = _sha256_json(list(stock_codes))
    rows_sha = _sha256_json([row.to_dict() for row in rows])
    identity = _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-selected-rows.identity.v1",
        "output_root": reference.output_root,
        "bundle_identity_sha256": reference.bundle_identity_sha256,
        "manifest_relative_path": reference.manifest_relative_path,
        "manifest_sha256": reference.manifest_sha256,
        "ordered_stock_codes_sha256": ordered_sha,
        "requested_count": len(stock_codes),
        "rows_identity_sha256": rows_sha,
        "row_count": len(rows),
    })
    return DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1(
        output_root=reference.output_root,
        bundle_identity_sha256=reference.bundle_identity_sha256,
        manifest_relative_path=reference.manifest_relative_path,
        manifest_sha256=reference.manifest_sha256,
        requested_stock_codes=stock_codes,
        ordered_stock_codes_sha256=ordered_sha,
        rows=rows,
        rows_identity_sha256=rows_sha,
        materialization_identity_sha256=identity,
        _seal=_SelectedRowsSealV1(identity, _issuer=_SELECTED_ROWS_SEAL_ISSUER),
    )


def _strict_json_object(raw: bytes, code: str) -> dict[str, object]:
    if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES:
        _fail(code)
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_unique_object_pairs,
            parse_float=_reject_json_float,
            parse_constant=_reject_json_constant,
        )
    except DailyMarketTechnicalOfficialDispositionBundleError:
        raise
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise DailyMarketTechnicalOfficialDispositionBundleError(code) from error
    if not isinstance(value, dict):
        _fail(code)
    _reject_floats(value)
    if _canonical_json(value).encode("utf-8") != raw:
        _fail("json_not_canonical")
    return cast(dict[str, object], value)


def _unique_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key")
        result[key] = value
    return result


def _reject_json_float(value: str) -> object:
    raise DailyMarketTechnicalOfficialDispositionBundleError("json_float_forbidden")


def _reject_json_constant(value: str) -> object:
    raise DailyMarketTechnicalOfficialDispositionBundleError("json_nonfinite_number_forbidden")


def _reject_floats(value: object) -> None:
    if isinstance(value, float):
        _fail("json_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("json_object_key_invalid")
            _reject_floats(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_floats(item)


def _canonical_json(value: object) -> str:
    _reject_floats(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise DailyMarketTechnicalOfficialDispositionBundleError("json_value_invalid") from error


def _sha256_json(value: object) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _sha256_bytes(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _require_sha256(value: object, code: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail(code)
    return value


def _parse_aware_datetime(value: object, code: str) -> datetime:
    if not isinstance(value, str) or len(value) > 128:
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DailyMarketTechnicalOfficialDispositionBundleError(code) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code)
    return parsed


def _validate_cancel_callback(callback: Callable[[], bool] | None) -> None:
    if callback is not None and not callable(callback):
        _fail("cancel_callback_invalid")


def _callback_true(callback: Callable[[], bool] | None) -> bool:
    if callback is None:
        return False
    result = callback()
    if type(result) is not bool:
        _fail("cancel_callback_invalid")
    return result


def _check_read_cancel(callback: Callable[[], bool] | None) -> None:
    try:
        if _callback_true(callback):
            _fail_cancelled()
    except DailyMarketTechnicalOfficialDispositionBundleError:
        raise
    except BaseException as error:
        raise DailyMarketTechnicalOfficialDispositionBundleError(
            "cancel_callback_failed",
            cause_code=type(error).__name__,
        ) from error


def _fail_cancelled() -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionBundleCancelled("cancelled_before_publish")


def _wrapped_error(code: str, error: BaseException) -> DailyMarketTechnicalOfficialDispositionBundleError:
    cause = getattr(error, "code", None)
    cause_code = cause if isinstance(cause, str) and len(cause) <= 160 else type(error).__name__
    return DailyMarketTechnicalOfficialDispositionBundleError(code, cause_code=cause_code)


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionBundleError(code)


def _canonical_path(
    value: str | Path,
    *,
    must_exist: bool,
    expect_directory: bool,
) -> tuple[Path, os.stat_result | None]:
    path = Path(value).expanduser()
    if not path.is_absolute() or ".." in path.parts or len(str(path)) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_PATH_CHARS:
        _fail("path_not_canonical_absolute")
    _check_no_reparse_components(path, allow_missing=not must_exist)
    try:
        resolved_text = os.path.realpath(to_internal_io_path(path), strict=must_exist)
        if os.name == "nt":
            folded = resolved_text.casefold()
            if folded.startswith("\\\\?\\unc\\"):
                resolved_text = "\\\\" + resolved_text[len("\\\\?\\unc\\"):]
            elif folded.startswith("\\\\?\\"):
                resolved_text = resolved_text[4:]
        canonical = Path(resolved_text)
        try:
            info = os.lstat(to_internal_io_path(canonical))
        except FileNotFoundError:
            info = None
    except OSError as error:
        raise DailyMarketTechnicalOfficialDispositionBundleError("path_resolution_failed") from error
    if str(canonical) != str(path):
        _fail("path_not_canonical_absolute")
    if must_exist and info is None:
        _fail("path_missing")
    if info is not None:
        if _is_link_or_reparse(info):
            _fail("path_link_or_reparse")
        if expect_directory and not stat.S_ISDIR(info.st_mode):
            _fail("path_not_directory")
        if not expect_directory and not stat.S_ISREG(info.st_mode):
            _fail("path_not_regular_file")
    return canonical, info


def _check_no_reparse_components(path: Path, *, allow_missing: bool) -> None:
    current = Path(path.anchor)
    missing = False
    for part in path.parts[1:]:
        current = current / part
        if missing:
            continue
        try:
            info = os.lstat(to_internal_io_path(current))
        except FileNotFoundError:
            if allow_missing:
                missing = True
                continue
            raise DailyMarketTechnicalOfficialDispositionBundleError("path_component_missing")
        except OSError as error:
            raise DailyMarketTechnicalOfficialDispositionBundleError("path_component_unreadable") from error
        if _is_link_or_reparse(info):
            _fail("path_component_link_or_reparse")
        if current != path and not stat.S_ISDIR(info.st_mode):
            _fail("path_component_not_directory")
    if missing and not allow_missing:
        _fail("path_component_missing")


def _is_link_or_reparse(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


def _lstat(path: Path) -> os.stat_result:
    try:
        return os.lstat(to_internal_io_path(path))
    except OSError as error:
        raise DailyMarketTechnicalOfficialDispositionBundleError("path_stat_failed") from error


def _check_output_path(path: Path, *, may_not_exist: bool) -> None:
    if len(str(path)) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_PATH_CHARS:
        _fail("path_length_limit")
    _check_no_reparse_components(path, allow_missing=may_not_exist)
    try:
        info = os.lstat(to_internal_io_path(path))
    except FileNotFoundError:
        if may_not_exist:
            return
        _fail("path_missing")
    except OSError as error:
        raise DailyMarketTechnicalOfficialDispositionBundleError("path_stat_failed") from error
    if _is_link_or_reparse(info):
        _fail("path_link_or_reparse")


def _is_child(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or _is_child(left, right) or _is_child(right, left)


def _resolve_bundle_relative(root: Path, relative: str, code: str) -> Path:
    if not isinstance(relative, str) or not relative or len(relative) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_PATH_CHARS:
        _fail(code)
    if "\\" in relative or ":" in relative or relative.startswith("/"):
        _fail(code)
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        _fail(code)
    target = root.joinpath(*parsed.parts)
    canonical, _ = _canonical_path(target, must_exist=False, expect_directory=False)
    if not _is_child(canonical, root):
        _fail(code)
    return canonical


def _ensure_directory(path: Path) -> None:
    _check_output_path(path, may_not_exist=True)
    try:
        os.mkdir(to_internal_io_path(path))
    except FileExistsError:
        info = _lstat(path)
        if not stat.S_ISDIR(info.st_mode) or _is_link_or_reparse(info):
            _fail("output_directory_invalid")
    except FileNotFoundError as error:
        if path.parent == path:
            raise DailyMarketTechnicalOfficialDispositionBundleError("output_directory_parent_missing") from error
        _ensure_directory(path.parent)
        _ensure_directory(path)
    _check_output_path(path, may_not_exist=False)


def _write_new_file(path: Path, raw: bytes, code: str) -> None:
    _check_output_path(path, may_not_exist=True)
    try:
        with open(to_internal_io_path(path), "xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise DailyMarketTechnicalOfficialDispositionBundleError("output_file_already_exists") from error
    except OSError as error:
        raise DailyMarketTechnicalOfficialDispositionBundleError(code) from error
    _check_output_path(path, may_not_exist=False)
    info = _lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        _fail("output_file_link_or_type_invalid")


def _read_bounded_regular_file(
    path: Path,
    limit: int,
    code: str,
    *,
    expected_link_count: int = 1,
) -> bytes:
    _check_output_path(path, may_not_exist=False)
    before = _lstat(path)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != expected_link_count
        or before.st_size > limit
    ):
        _fail(code)
    try:
        with open(to_internal_io_path(path), "rb") as stream:
            raw = stream.read(limit + 1)
            opened = os.fstat(stream.fileno())
        current = _lstat(path)
    except OSError as error:
        raise DailyMarketTechnicalOfficialDispositionBundleError(code) from error
    pin_before = (before.st_dev, before.st_ino, before.st_nlink, before.st_size, before.st_mtime_ns)
    pin_opened = (opened.st_dev, opened.st_ino, opened.st_nlink, opened.st_size, opened.st_mtime_ns)
    pin_current = (current.st_dev, current.st_ino, current.st_nlink, current.st_size, current.st_mtime_ns)
    if pin_before != pin_opened or pin_opened != pin_current or len(raw) != before.st_size or len(raw) > limit:
        _fail("file_changed_during_read")
    return raw


def _unlink_own_candidate(
    path: Path,
    *,
    published_path: Path,
    expected_link_count: int,
) -> None:
    _check_output_path(path, may_not_exist=False)
    _check_output_path(published_path, may_not_exist=False)
    info = _lstat(path)
    published_info = _lstat(published_path)
    if (
        not stat.S_ISREG(info.st_mode)
        or not stat.S_ISREG(published_info.st_mode)
        or info.st_nlink != expected_link_count
        or published_info.st_nlink != expected_link_count
        or (info.st_dev, info.st_ino) != (published_info.st_dev, published_info.st_ino)
    ):
        _fail("published_candidate_link_state_invalid")
    try:
        os.unlink(to_internal_io_path(path))
    except OSError as error:
        raise DailyMarketTechnicalOfficialDispositionBundleError(
            "published_candidate_cleanup_failed"
        ) from error
    final_info = _lstat(published_path)
    if not stat.S_ISREG(final_info.st_mode) or final_info.st_nlink != 1:
        _fail("published_target_link_state_invalid")


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor: int | None = None
    try:
        descriptor = os.open(to_internal_io_path(path), os.O_RDONLY)
        os.fsync(descriptor)
    except OSError:
        _fail("directory_fsync_failed")
    finally:
        if descriptor is not None:
            os.close(descriptor)
