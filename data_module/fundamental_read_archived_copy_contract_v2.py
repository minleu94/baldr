"""V2 封存副本連線契約；不授予 V1 或正式/PIT 資格。"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import TYPE_CHECKING, Callable, Literal, Sequence
import weakref

from data_module.fundamental_read_copy_contract import (
    MAX_ARCHIVED_RAW_MANIFEST_BYTES,
    MAX_COPY_FILE_BYTES,
    FundamentalReadCopyBinding,
    FundamentalReadCopyBindingError,
    FundamentalReadCopyFilePin,
    _canonical_absolute,
    _canonical_json_bytes,
    _canonical_sha256,
    _paths_overlap,
    _pin_file,
    _poll_cancel,
    _read_file_bounded,
    _reject_constant,
    _reject_existing_reparse_components,
    _reject_reparse_components,
    _require_distinct_copy_files,
    _unique_object,
)

if TYPE_CHECKING:
    from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortPin
    from data_module.fundamental_read_snapshot_raw_archive_v2 import (
        FundamentalReadSnapshotRawArchiveReferenceV2,
    )


FUNDAMENTAL_READ_ARCHIVED_COPY_BINDING_V2_SCHEMA: Literal[
    "selection-fundamental-read-archived-copy-binding.v2"
] = "selection-fundamental-read-archived-copy-binding.v2"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ARCHIVE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SNAPSHOT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SQLITE_ROLES = (
    "sqlite_main",
    "sqlite_wal",
    "sqlite_shm",
    "sqlite_rollback_journal",
)
_MAX_ARCHIVE_FILE_PIN_COUNT = 100_000
_ARCHIVED_BINDING_ISSUER_V2 = object()
_ISSUED_ARCHIVED_BINDINGS_V2: dict[
    int,
    tuple[weakref.ReferenceType[FundamentalReadArchivedCopyBindingV2], str],
] = {}


class FundamentalReadArchivedCopyBindingV2Error(FundamentalReadCopyBindingError):
    """V2 封存 snapshot、月營收原件或 operation copy 不符合契約。"""


@dataclass(frozen=True, slots=True)
class FilePinPairV2:
    """把歷史 capture pin 精確配到封存檔案 pin。"""

    historical_pin: FundamentalReadCopyFilePin
    archive_pin: FundamentalReadCopyFilePin

    def __post_init__(self) -> None:
        if type(self.historical_pin) is not FundamentalReadCopyFilePin:
            raise TypeError("V2 歷史 capture pin 型別錯誤")
        if type(self.archive_pin) is not FundamentalReadCopyFilePin:
            raise TypeError("V2 archive capture pin 型別錯誤")
        if not self.historical_pin.present or not self.archive_pin.present:
            raise ValueError("V2 capture 配對兩端都必須存在")
        if self.historical_pin.role not in {"monthly_html", "monthly_csv"}:
            raise ValueError("V2 historical capture role 不支援")
        if self.archive_pin.role != self.historical_pin.role:
            raise ValueError("V2 archive capture role 與歷史來源不同")
        if (
            self.archive_pin.size_bytes != self.historical_pin.size_bytes
            or self.archive_pin.sha256 != self.historical_pin.sha256
        ):
            raise ValueError("V2 封存 capture bytes 與歷史來源不同")

    def to_dict(self) -> dict[str, object]:
        return {
            "historical_pin": self.historical_pin.to_dict(),
            "archive_pin": self.archive_pin.to_dict(),
        }


@dataclass(frozen=True, slots=True, weakref_slot=True)
class FundamentalReadArchivedCopyBindingV2:
    """只由 V2 verified archive issuer 發行的 current/hour-bound 封存入口。"""

    operation_copy_binding: FundamentalReadCopyBinding
    historical_snapshot_root: str
    archived_snapshot_root: str
    archive_root: str
    archived_monthly_source_root: str
    snapshot_reference_identity_sha256: str
    source_clock_identity_sha256: str
    source_content_identity_sha256: str
    cohort_identity_sha256: str
    daily_cohort_pin: DailyMonthlyRevenueCohortPin
    daily_cohort_sha256: str
    raw_archive_identity_sha256: str
    raw_archive_reference_sha256: str
    snapshot_manifest_pin: FundamentalReadCopyFilePin
    archive_manifest_pin: FundamentalReadCopyFilePin
    historical_source_pins: tuple[FundamentalReadCopyFilePin, ...]
    capture_file_pairs: tuple[FilePinPairV2, ...]
    archive_file_pins: tuple[FundamentalReadCopyFilePin, ...]
    _issuer_anchor: object = field(repr=False, compare=False)
    schema_version: Literal[
        "selection-fundamental-read-archived-copy-binding.v2"
    ] = FUNDAMENTAL_READ_ARCHIVED_COPY_BINDING_V2_SCHEMA

    def __post_init__(self) -> None:
        from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortPin

        if type(self.operation_copy_binding) is not FundamentalReadCopyBinding:
            raise TypeError("V2 archived binding 必須含 typed operation copy binding")
        if type(self.schema_version) is not str or self.schema_version != FUNDAMENTAL_READ_ARCHIVED_COPY_BINDING_V2_SCHEMA:
            raise ValueError("V2 archived copy binding schema 不支援")
        for name in (
            "historical_snapshot_root",
            "archived_snapshot_root",
            "archive_root",
            "archived_monthly_source_root",
        ):
            value = getattr(self, name)
            if type(value) is not str or not Path(value).is_absolute() or str(Path(os.path.abspath(value))) != value:
                raise ValueError(f"{name} 必須是 canonical 絕對路徑")
        for name in (
            "snapshot_reference_identity_sha256",
            "source_clock_identity_sha256",
            "source_content_identity_sha256",
            "cohort_identity_sha256",
            "daily_cohort_sha256",
            "raw_archive_identity_sha256",
            "raw_archive_reference_sha256",
        ):
            value = getattr(self, name)
            if type(value) is not str or not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} 格式錯誤")
        if type(self.daily_cohort_pin) is not DailyMonthlyRevenueCohortPin:
            raise TypeError("V2 daily cohort pin 型別錯誤")
        if self.daily_cohort_sha256 != self.daily_cohort_pin.cohort_sha256:
            raise ValueError("V2 daily cohort pin SHA 不一致")
        if self._issuer_anchor is not _ARCHIVED_BINDING_ISSUER_V2:
            raise ValueError("V2 archived binding issuer anchor 無效")
        if type(self.snapshot_manifest_pin) is not FundamentalReadCopyFilePin:
            raise TypeError("V2 snapshot manifest pin 型別錯誤")
        if type(self.archive_manifest_pin) is not FundamentalReadCopyFilePin:
            raise TypeError("V2 archive manifest pin 型別錯誤")
        if (
            self.snapshot_manifest_pin.role != "finished_source_clock_manifest"
            or self.archive_manifest_pin.role != "monthly_raw_archive_manifest"
            or not self.snapshot_manifest_pin.present
            or not self.archive_manifest_pin.present
        ):
            raise ValueError("V2 manifest pin role 不符")
        if type(self.historical_source_pins) is not tuple or tuple(
            pin.role for pin in self.historical_source_pins
        ) != _SQLITE_ROLES:
            raise ValueError("V2 historical SQLite pins 必須完整且按 role 排序")
        if any(
            type(pin) is not FundamentalReadCopyFilePin
            for pin in self.historical_source_pins
        ):
            raise TypeError("V2 historical SQLite pin 型別錯誤")
        if self.operation_copy_binding.source_file_pins != self.historical_source_pins:
            raise ValueError("V2 operation source pins 與歷史 DB pins 不一致")
        if self.operation_copy_binding.sqlite_journal_mode == "rollback":
            if self.historical_source_pins[1].present or self.historical_source_pins[2].present:
                raise ValueError("V2 rollback snapshot 不可攜帶 WAL pins")
        if self.historical_source_pins[3].present:
            raise ValueError("V2 archived rollback journal 不可保留")
        if type(self.capture_file_pairs) is not tuple or not self.capture_file_pairs:
            raise ValueError("V2 archive 必須保存完整 capture 配對")
        if any(type(pair) is not FilePinPairV2 for pair in self.capture_file_pairs):
            raise TypeError("V2 capture pair 型別錯誤")
        historical_capture_pins = tuple(pair.historical_pin for pair in self.capture_file_pairs)
        if len({os.path.normcase(pin.path) for pin in historical_capture_pins}) != len(
            historical_capture_pins
        ):
            raise ValueError("V2 historical capture pin 路徑重複")
        archived_capture_pins = tuple(pair.archive_pin for pair in self.capture_file_pairs)
        if type(self.archive_file_pins) is not tuple or not self.archive_file_pins:
            raise ValueError("V2 archived snapshot/raw tree pins 不可為空")
        if len(self.archive_file_pins) > _MAX_ARCHIVE_FILE_PIN_COUNT:
            raise ValueError("V2 archived file pin 數超過 bounded archive 上限")
        if any(type(pin) is not FundamentalReadCopyFilePin or not pin.present for pin in self.archive_file_pins):
            raise TypeError("V2 archive file pins 必須是存在的 typed pins")
        expected_sorted = tuple(sorted(self.archive_file_pins, key=lambda pin: os.path.normcase(pin.path)))
        if self.archive_file_pins != expected_sorted:
            raise ValueError("V2 archive file pins 必須按 canonical path 排序")
        archive_paths = tuple(os.path.normcase(pin.path) for pin in self.archive_file_pins)
        if len(set(archive_paths)) != len(archive_paths):
            raise ValueError("V2 archive file pin path 重複")
        if any(pin not in self.archive_file_pins for pin in archived_capture_pins):
            raise ValueError("V2 capture pairs 不完整包含於 archive pins")
        if self.snapshot_manifest_pin not in self.archive_file_pins:
            raise ValueError("V2 snapshot manifest 未包含於完整 snapshot pins")
        if self.archive_manifest_pin in self.archive_file_pins:
            raise ValueError("V2 raw archive manifest 應獨立於其自身 file inventory")
        self._validate_declared_layout()

    @property
    def source_scope(self) -> Literal["current_observed_only"]:
        return "current_observed_only"

    @property
    def availability_status(self) -> Literal["cohort_hour_bound"]:
        return "cohort_hour_bound"

    @property
    def historical_pit_eligible(self) -> Literal[False]:
        return False

    @property
    def formal_pit_eligible(self) -> Literal[False]:
        return False

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation_copy_binding_identity_sha256": self.operation_copy_binding.identity_sha256,
            "historical_snapshot_root": self.historical_snapshot_root,
            "archived_snapshot_root": self.archived_snapshot_root,
            "archive_root": self.archive_root,
            "archived_monthly_source_root": self.archived_monthly_source_root,
            "snapshot_reference_identity_sha256": self.snapshot_reference_identity_sha256,
            "source_clock_identity_sha256": self.source_clock_identity_sha256,
            "source_content_identity_sha256": self.source_content_identity_sha256,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "daily_cohort_pin": self.daily_cohort_pin.to_dict(),
            "daily_cohort_sha256": self.daily_cohort_sha256,
            "raw_archive_identity_sha256": self.raw_archive_identity_sha256,
            "raw_archive_reference_sha256": self.raw_archive_reference_sha256,
            "snapshot_manifest_pin": self.snapshot_manifest_pin.to_dict(),
            "archive_manifest_pin": self.archive_manifest_pin.to_dict(),
            "historical_source_pins": [pin.to_dict() for pin in self.historical_source_pins],
            "capture_file_pairs": [pair.to_dict() for pair in self.capture_file_pairs],
            "archive_file_pins": [pin.to_dict() for pin in self.archive_file_pins],
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._identity_payload()
        payload["identity_sha256"] = self.identity_sha256
        return payload

    def verify_before_open(
        self,
        *,
        database_path: Path | str,
        provider_database_path: Path | str,
        provider_monthly_source_root: Path | str,
        protected_roots: Sequence[Path | str],
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[FundamentalReadCopyFilePin, ...]:
        """開 SQLite 前重驗 saved archive 與本次 operation copy，不讀 live source。"""

        return self._verify_operation_copy(
            database_path=database_path,
            provider_database_path=provider_database_path,
            provider_monthly_source_root=provider_monthly_source_root,
            protected_roots=protected_roots,
            cancel_callback=cancel_callback,
        )

    def verify_before_finish(
        self,
        *,
        database_path: Path | str,
        provider_database_path: Path | str,
        provider_monthly_source_root: Path | str,
        protected_roots: Sequence[Path | str],
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[FundamentalReadCopyFilePin, ...]:
        """發布 V2 finished token 前再次核全樹與 copy，不依賴 live source。"""

        return self._verify_operation_copy(
            database_path=database_path,
            provider_database_path=provider_database_path,
            provider_monthly_source_root=provider_monthly_source_root,
            protected_roots=protected_roots,
            cancel_callback=cancel_callback,
        )

    def remap_capture_pin(
        self, historical_pin: FundamentalReadCopyFilePin
    ) -> FundamentalReadCopyFilePin:
        """以完整原始 pin 將歷史 capture 路徑映到 archive 路徑。"""

        self._require_issued()
        if type(historical_pin) is not FundamentalReadCopyFilePin:
            raise TypeError("V2 remap capture pin 型別錯誤")
        for pair in self.capture_file_pairs:
            if pair.historical_pin == historical_pin:
                return pair.archive_pin
        raise FundamentalReadArchivedCopyBindingV2Error("v2_capture_historical_pin_unmapped")

    def restore_capture_pin(
        self, archive_pin: FundamentalReadCopyFilePin
    ) -> FundamentalReadCopyFilePin:
        """以完整封存 pin 還原原始 capture pin；不接受同 hash 的其他路徑。"""

        self._require_issued()
        if type(archive_pin) is not FundamentalReadCopyFilePin:
            raise TypeError("V2 restore capture pin 型別錯誤")
        for pair in self.capture_file_pairs:
            if pair.archive_pin == archive_pin:
                return pair.historical_pin
        raise FundamentalReadArchivedCopyBindingV2Error("v2_capture_archive_pin_unmapped")

    def _require_issued(self) -> None:
        if not _is_issued_archived_binding_v2(self):
            raise FundamentalReadArchivedCopyBindingV2Error("v2_archived_binding_not_issued")

    def _validate_declared_layout(self) -> None:
        historical_root = Path(self.historical_snapshot_root)
        archived_root = Path(self.archived_snapshot_root)
        archive_root = Path(self.archive_root)
        monthly_root = Path(self.archived_monthly_source_root)
        if not _ARCHIVE_ID_RE.fullmatch(archive_root.name):
            raise ValueError("V2 archive root basename 必須是 32 位 lowercase archive id")
        if (
            monthly_root != archive_root / "monthly_source"
            or archived_root.parent.name != "saved_snapshot"
            or archived_root.parent.parent != archive_root
            or not _SNAPSHOT_ID_RE.fullmatch(archived_root.name)
            or historical_root.name != archived_root.name
        ):
            raise ValueError("V2 archived roots 不符合固定 archive layout")
        if _paths_overlap(historical_root, archive_root):
            raise ValueError("V2 logical historical snapshot 與 archive root 重疊")
        if _paths_overlap(archived_root, monthly_root):
            raise ValueError("V2 saved snapshot 與 monthly source 子樹重疊")
        expected_archive_manifest = archive_root / "raw_archive.json"
        if self.archive_manifest_pin.path != str(expected_archive_manifest):
            raise ValueError("V2 raw archive manifest path 不符")
        expected_snapshot_manifest = archived_root / "finished_source_clock.json"
        if self.snapshot_manifest_pin.path != str(expected_snapshot_manifest):
            raise ValueError("V2 finished snapshot manifest path 不符")
        for pin in self.archive_file_pins:
            path = Path(pin.path)
            in_snapshot = _is_strict_descendant(archived_root, path)
            in_monthly = _is_strict_descendant(monthly_root, path)
            if not (in_snapshot or in_monthly):
                raise ValueError("V2 archive file pin 位於 snapshot/monthly source 子樹外")
        for pair in self.capture_file_pairs:
            if not _is_strict_descendant(monthly_root, Path(pair.archive_pin.path)):
                raise ValueError("V2 archive capture pin 位於 monthly source 子樹外")

    def _verify_operation_copy(
        self,
        *,
        database_path: Path | str,
        provider_database_path: Path | str,
        provider_monthly_source_root: Path | str,
        protected_roots: Sequence[Path | str],
        cancel_callback: Callable[[], bool] | None,
    ) -> tuple[FundamentalReadCopyFilePin, ...]:
        if not _is_issued_archived_binding_v2(self):
            raise FundamentalReadArchivedCopyBindingV2Error("v2_archived_binding_not_issued")
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        _poll_cancel(cancel_callback)
        historical_root = _canonical_absolute(
            self.historical_snapshot_root, "historical_snapshot_root"
        )
        archived_root = _canonical_absolute(self.archived_snapshot_root, "archived_snapshot_root")
        archive_root = _canonical_absolute(self.archive_root, "archive_root")
        monthly_root = _canonical_absolute(
            self.archived_monthly_source_root, "archived_monthly_source_root"
        )
        requested_monthly_root = _canonical_absolute(
            str(provider_monthly_source_root), "provider_monthly_source_root"
        )
        if requested_monthly_root != monthly_root:
            raise FundamentalReadArchivedCopyBindingV2Error("v2_archived_monthly_root_mismatch")
        if _paths_overlap(historical_root, archive_root):
            raise FundamentalReadArchivedCopyBindingV2Error("v2_historical_archive_roots_overlap")
        if not _is_strict_descendant(archive_root, archived_root) or not _is_strict_descendant(
            archive_root, monthly_root
        ):
            raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_subroot_outside_archive")
        operation = self.operation_copy_binding
        original_db_root = Path(operation.source_database_path).parent
        if _paths_overlap(archive_root, original_db_root) or _paths_overlap(
            archived_root, original_db_root
        ):
            raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_overlaps_historical_database")
        for protected in protected_roots:
            protected_path = Path(os.path.abspath(Path(protected).expanduser()))
            _reject_existing_reparse_components(protected_path)
            if _paths_overlap(archive_root, protected_path):
                raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_overlaps_protected_root")

        _reject_reparse_components(archive_root)
        _reject_reparse_components(archived_root)
        _reject_reparse_components(monthly_root)
        self._verify_full_archived_tree(cancel_callback=cancel_callback)
        self._verify_saved_snapshot_manifest(cancel_callback=cancel_callback)
        self._verify_raw_archive_manifest(cancel_callback=cancel_callback)
        _poll_cancel(cancel_callback)

        expected_historical_pins = (
            *self.historical_source_pins,
            *(pair.historical_pin for pair in self.capture_file_pairs),
        )
        archived_evidence_pins = (
            *self.archive_file_pins,
            self.archive_manifest_pin,
        )
        return operation.verify_archived_operation_copy_before_open(
            database_path=database_path,
            provider_database_path=provider_database_path,
            protected_roots=protected_roots,
            archived_source_pins=expected_historical_pins,
            archive_file_pins=archived_evidence_pins,
            cancel_callback=cancel_callback,
        )

    def _verify_full_archived_tree(
        self, *, cancel_callback: Callable[[], bool] | None
    ) -> None:
        expected = {os.path.normcase(pin.path): pin for pin in self.archive_file_pins}
        manifest_key = os.path.normcase(self.archive_manifest_pin.path)
        if manifest_key in expected:
            raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_manifest_duplicate_pin")
        expected[manifest_key] = self.archive_manifest_pin
        actual: dict[str, FundamentalReadCopyFilePin] = {}
        for pin in self.archive_file_pins:
            _poll_cancel(cancel_callback)
            path = Path(pin.path)
            _reject_reparse_components(path)
            current = _pin_file(
                pin.role,
                path,
                required=True,
                max_bytes=MAX_COPY_FILE_BYTES,
                cancel_callback=cancel_callback,
            )
            if current != pin:
                raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_file_pin_changed")
            actual[os.path.normcase(str(path))] = current
        manifest_path = Path(self.archive_manifest_pin.path)
        _reject_reparse_components(manifest_path)
        actual_manifest = _pin_file(
            self.archive_manifest_pin.role,
            manifest_path,
            required=True,
            max_bytes=MAX_ARCHIVED_RAW_MANIFEST_BYTES,
            cancel_callback=cancel_callback,
        )
        if actual_manifest != self.archive_manifest_pin:
            raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_manifest_pin_changed")
        actual[os.path.normcase(str(manifest_path))] = actual_manifest
        _require_distinct_copy_files(tuple(actual.values()), "v2 archived snapshot/raw tree")
        if set(actual) != set(expected):
            raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_file_pin_inventory_mismatch")

        expected_directories: set[str] = set()
        for pin in expected.values():
            path = Path(pin.path)
            for parent in path.parents:
                if parent == Path(self.archive_root):
                    break
                if _is_strict_descendant(Path(self.archive_root), parent):
                    expected_directories.add(os.path.normcase(str(parent)))
        actual_directories: set[str] = set()
        for base in (Path(self.archive_root),):
            _require_real_directory(base)
            for current_root, directories, files in os.walk(base, topdown=True, followlinks=False):
                _poll_cancel(cancel_callback)
                current_path = Path(current_root)
                for dirname in tuple(directories):
                    directory_path = current_path / dirname
                    _require_real_directory(directory_path)
                    directory_key = os.path.normcase(str(directory_path))
                    if directory_key not in expected_directories:
                        raise FundamentalReadArchivedCopyBindingV2Error(
                            "v2_archive_tree_contains_unpinned_directory"
                        )
                    actual_directories.add(directory_key)
                for filename in files:
                    file_path = current_path / filename
                    _reject_reparse_components(file_path)
                    key = os.path.normcase(str(Path(os.path.abspath(file_path))))
                    if key not in expected:
                        raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_tree_contains_unpinned_file")
                _poll_cancel(cancel_callback)
        if actual_directories != expected_directories:
            raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_tree_directory_inventory_mismatch")
        _poll_cancel(cancel_callback)

    def _verify_saved_snapshot_manifest(
        self, *, cancel_callback: Callable[[], bool] | None
    ) -> None:
        from data_module.fundamental_read_snapshot_cohort_v2 import (
            FundamentalSnapshotSourceClockV2,
            parse_finished_snapshot_cohort_v2,
            parse_snapshot_source_clock_v2,
        )

        raw = _read_file_bounded(
            Path(self.snapshot_manifest_pin.path),
            max_bytes=32 * 1024 * 1024,
            cancel_callback=cancel_callback,
        )
        manifest = _parse_canonical_json_mapping(raw, "v2_snapshot_manifest")
        try:
            source_clock = parse_snapshot_source_clock_v2(manifest.get("source_clock"))
            if type(source_clock) is not FundamentalSnapshotSourceClockV2:
                raise FundamentalReadArchivedCopyBindingV2Error("v2_snapshot_clock_type_invalid")
            finished = parse_finished_snapshot_cohort_v2(manifest, source_clock)
        except FundamentalReadArchivedCopyBindingV2Error:
            raise
        except (ValueError, TypeError, KeyError) as exc:
            raise FundamentalReadArchivedCopyBindingV2Error(
                "v2_snapshot_manifest_semantics_invalid"
            ) from exc
        if (
            sha256(raw).hexdigest() != self.snapshot_manifest_pin.sha256
            or finished.finished_manifest_sha256 != self.snapshot_manifest_pin.sha256
            or finished.identity_sha256 != self.cohort_identity_sha256
            or source_clock.identity_sha256 != self.source_clock_identity_sha256
            or source_clock.source_content_identity_sha256 != self.source_content_identity_sha256
            or source_clock.cohort_pin != self.daily_cohort_pin
            or source_clock.cohort_sha256 != self.daily_cohort_sha256
            or source_clock.source_scope != self.source_scope
            or source_clock.availability_status != self.availability_status
            or source_clock.historical_pit_eligible is not False
            or source_clock.formal_pit_eligible is not False
            or source_clock.database_file_pins_start != self.historical_source_pins
            or source_clock.database_file_pins_finish != self.historical_source_pins
            or source_clock.capture_file_pins_start
            != tuple(pair.historical_pin for pair in self.capture_file_pairs)
            or source_clock.capture_file_pins_finish
            != tuple(pair.historical_pin for pair in self.capture_file_pairs)
        ):
            raise FundamentalReadArchivedCopyBindingV2Error("v2_snapshot_manifest_binding_mismatch")
        if self.daily_cohort_pin.available_hour > source_clock.decision_cutoff:
            raise FundamentalReadArchivedCopyBindingV2Error("v2_cohort_after_decision_cutoff")
        _poll_cancel(cancel_callback)

    def _verify_raw_archive_manifest(
        self, *, cancel_callback: Callable[[], bool] | None
    ) -> None:
        from data_module.fundamental_read_snapshot_raw_archive_v2 import (
            FundamentalReadSnapshotRawArchiveReferenceV2,
        )

        raw = _read_file_bounded(
            Path(self.archive_manifest_pin.path),
            max_bytes=MAX_ARCHIVED_RAW_MANIFEST_BYTES,
            cancel_callback=cancel_callback,
        )
        payload = _parse_canonical_json_mapping(raw, "v2_raw_archive_manifest")
        try:
            reference = FundamentalReadSnapshotRawArchiveReferenceV2.from_manifest_dict(payload)
        except (ValueError, TypeError, KeyError) as exc:
            raise FundamentalReadArchivedCopyBindingV2Error(
                "v2_raw_archive_manifest_semantics_invalid"
            ) from exc
        reference_json = reference.to_json().encode("utf-8")
        expected_file_pins = _reference_file_pin_map(
            reference,
            historical_snapshot_root=self.historical_snapshot_root,
        )
        actual_file_pins = {
            os.path.normcase(pin.path): (pin.role, pin.size_bytes, pin.sha256)
            for pin in self.archive_file_pins
        }
        expected_pairs = _archive_reference_pairs(reference)
        actual_pairs = _binding_capture_pairs(self.capture_file_pairs, self.archive_root)
        if (
            type(reference) is not FundamentalReadSnapshotRawArchiveReferenceV2
            or raw != _canonical_json_bytes(reference.to_manifest_dict())
            or sha256(raw).hexdigest() != self.archive_manifest_pin.sha256
            or sha256(reference_json).hexdigest() != self.raw_archive_reference_sha256
            or reference.archive_identity_sha256 != self.raw_archive_identity_sha256
            or reference.snapshot_reference.identity_sha256
            != self.snapshot_reference_identity_sha256
            or reference.snapshot_reference.snapshot_root != self.historical_snapshot_root
            or reference.snapshot_reference.finished_manifest_sha256
            != self.snapshot_manifest_pin.sha256
            or reference.source_clock.identity_sha256 != self.source_clock_identity_sha256
            or reference.source_clock.source_content_identity_sha256
            != self.source_content_identity_sha256
            or reference.source_clock.cohort_pin != self.daily_cohort_pin
            or reference.source_clock.cohort_sha256 != self.daily_cohort_sha256
            or reference.snapshot_reference.cohort_identity_sha256
            != self.cohort_identity_sha256
            or reference.archive_root != self.archive_root
            or reference.archived_snapshot_root != self.archived_snapshot_root
            or reference.archived_monthly_source_root != self.archived_monthly_source_root
            or expected_file_pins != actual_file_pins
            or expected_pairs != actual_pairs
        ):
            raise FundamentalReadArchivedCopyBindingV2Error("v2_raw_archive_manifest_binding_mismatch")
        _poll_cancel(cancel_callback)


def _issue_archived_copy_binding_v2(
    *,
    issuer_anchor: object,
    operation_copy_binding: FundamentalReadCopyBinding,
    historical_snapshot_root: str,
    archived_snapshot_root: str,
    archive_root: str,
    archived_monthly_source_root: str,
    snapshot_reference_identity_sha256: str,
    source_clock_identity_sha256: str,
    source_content_identity_sha256: str,
    cohort_identity_sha256: str,
    daily_cohort_pin: DailyMonthlyRevenueCohortPin,
    daily_cohort_sha256: str,
    raw_archive_identity_sha256: str,
    raw_archive_reference_sha256: str,
    snapshot_manifest_pin: FundamentalReadCopyFilePin,
    archive_manifest_pin: FundamentalReadCopyFilePin,
    historical_source_pins: tuple[FundamentalReadCopyFilePin, ...],
    capture_file_pairs: tuple[FilePinPairV2, ...],
    archive_file_pins: tuple[FundamentalReadCopyFilePin, ...],
) -> FundamentalReadArchivedCopyBindingV2:
    """只允許完成 V2 archive verification 的 snapshot owner 使用。"""

    if issuer_anchor is not _ARCHIVED_BINDING_ISSUER_V2:
        raise FundamentalReadArchivedCopyBindingV2Error("v2_archived_binding_issuer_rejected")
    binding = FundamentalReadArchivedCopyBindingV2(
        operation_copy_binding=operation_copy_binding,
        historical_snapshot_root=historical_snapshot_root,
        archived_snapshot_root=archived_snapshot_root,
        archive_root=archive_root,
        archived_monthly_source_root=archived_monthly_source_root,
        snapshot_reference_identity_sha256=snapshot_reference_identity_sha256,
        source_clock_identity_sha256=source_clock_identity_sha256,
        source_content_identity_sha256=source_content_identity_sha256,
        cohort_identity_sha256=cohort_identity_sha256,
        daily_cohort_pin=daily_cohort_pin,
        daily_cohort_sha256=daily_cohort_sha256,
        raw_archive_identity_sha256=raw_archive_identity_sha256,
        raw_archive_reference_sha256=raw_archive_reference_sha256,
        snapshot_manifest_pin=snapshot_manifest_pin,
        archive_manifest_pin=archive_manifest_pin,
        historical_source_pins=historical_source_pins,
        capture_file_pairs=capture_file_pairs,
        archive_file_pins=archive_file_pins,
        _issuer_anchor=issuer_anchor,
    )
    identity = binding.identity_sha256
    binding_id = id(binding)
    reference = weakref.ref(binding)

    def remove_reference(
        removed: weakref.ReferenceType[FundamentalReadArchivedCopyBindingV2],
    ) -> None:
        current = _ISSUED_ARCHIVED_BINDINGS_V2.get(binding_id)
        if current is not None and current[0] is removed:
            _ISSUED_ARCHIVED_BINDINGS_V2.pop(binding_id, None)

    _ISSUED_ARCHIVED_BINDINGS_V2[binding_id] = (reference, identity)
    return binding


def _is_issued_archived_binding_v2(
    binding: FundamentalReadArchivedCopyBindingV2,
) -> bool:
    issued = _ISSUED_ARCHIVED_BINDINGS_V2.get(id(binding))
    return issued is not None and issued[0]() is binding and issued[1] == binding.identity_sha256


def _archive_reference_pairs(
    reference: FundamentalReadSnapshotRawArchiveReferenceV2,
) -> tuple[dict[str, object], ...]:
    files = reference.files
    if type(files) is not tuple:
        raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_capture_files_invalid")
    pairs: list[dict[str, object]] = []
    for item in files:
        historical_pin = item.historical_pin
        relative_path = item.relative_path
        size_bytes = item.size_bytes
        digest = item.sha256
        if type(historical_pin) is not FundamentalReadCopyFilePin:
            raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_capture_file_invalid")
        pairs.append(
            {
                "historical_pin": historical_pin.to_dict(),
                "relative_path": relative_path,
                "size_bytes": size_bytes,
                "sha256": digest,
            }
        )
    return tuple(pairs)


def _binding_capture_pairs(
    pairs: tuple[FilePinPairV2, ...], archive_root: str
) -> tuple[dict[str, object], ...]:
    archive = Path(archive_root)
    output: list[dict[str, object]] = []
    for pair in pairs:
        try:
            relative = Path(pair.archive_pin.path).relative_to(archive).as_posix()
        except ValueError as exc:
            raise FundamentalReadArchivedCopyBindingV2Error(
                "v2_archive_capture_outside_archive_root"
            ) from exc
        output.append(
            {
                "historical_pin": pair.historical_pin.to_dict(),
                "relative_path": relative,
                "size_bytes": pair.archive_pin.size_bytes,
                "sha256": pair.archive_pin.sha256,
            }
        )
    return tuple(output)


def _reference_file_pin_map(
    reference: FundamentalReadSnapshotRawArchiveReferenceV2,
    *,
    historical_snapshot_root: str,
) -> dict[str, tuple[str, int, str]]:
    output: dict[str, tuple[str, int, str]] = {}
    archive_root_raw = reference.archive_root
    original_monthly_root_raw = reference.original_monthly_source_root
    files = reference.files
    snapshot_files = reference.snapshot_files
    if type(files) is not tuple or type(snapshot_files) is not tuple:
        raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_manifest_file_lists_invalid")
    archive_root = Path(archive_root_raw)
    original_monthly_root = Path(original_monthly_root_raw)
    historical_snapshot = Path(historical_snapshot_root)
    archived_snapshot_name = Path(reference.archived_snapshot_root).name
    for label, items, prefix in (
        ("raw", files, PurePosixPath("monthly_source")),
        ("snapshot", snapshot_files, PurePosixPath("saved_snapshot")),
    ):
        for item in items:
            historical_pin = item.historical_pin
            relative_path = item.relative_path
            size_bytes = item.size_bytes
            digest = item.sha256
            if type(historical_pin) is not FundamentalReadCopyFilePin:
                raise FundamentalReadArchivedCopyBindingV2Error(
                    f"v2_archive_{label}_file_invalid"
                )
            relative = PurePosixPath(relative_path)
            if (
                relative.is_absolute()
                or str(relative) != relative_path
                or not relative.parts
                or relative.parts[0] != prefix.parts[0]
                or any(part in {"", ".", ".."} for part in relative.parts)
                or size_bytes != historical_pin.size_bytes
                or digest != historical_pin.sha256
                or not historical_pin.present
            ):
                raise FundamentalReadArchivedCopyBindingV2Error(
                    f"v2_archive_{label}_file_binding_invalid"
                )
            if label == "snapshot" and (
                len(relative.parts) < 3 or relative.parts[1] != archived_snapshot_name
            ):
                raise FundamentalReadArchivedCopyBindingV2Error(
                    "v2_archive_snapshot_id_path_mismatch"
                )
            try:
                if label == "raw":
                    if relative.parts[0] != "monthly_source":
                        raise ValueError("raw archive prefix mismatch")
                    historical_relative = Path(historical_pin.path).relative_to(
                        original_monthly_root
                    )
                    archived_relative = PurePosixPath(*relative.parts[1:])
                else:
                    if (
                        len(relative.parts) < 3
                        or relative.parts[0] != "saved_snapshot"
                        or relative.parts[1] != archived_snapshot_name
                    ):
                        raise ValueError("snapshot archive prefix mismatch")
                    historical_relative = Path(historical_pin.path).relative_to(
                        historical_snapshot
                    )
                    archived_relative = PurePosixPath(*relative.parts[2:])
            except ValueError as exc:
                raise FundamentalReadArchivedCopyBindingV2Error(
                    f"v2_archive_{label}_historical_path_mismatch"
                ) from exc
            if (
                not archived_relative.parts
                or PurePosixPath(*historical_relative.parts).as_posix()
                != archived_relative.as_posix()
            ):
                raise FundamentalReadArchivedCopyBindingV2Error(
                    f"v2_archive_{label}_relative_path_mismatch"
                )
            absolute = archive_root.joinpath(*relative.parts)
            key = os.path.normcase(str(absolute))
            if key in output:
                raise FundamentalReadArchivedCopyBindingV2Error(
                    "v2_archive_manifest_duplicate_relative_path"
                )
            output[key] = (historical_pin.role, size_bytes, digest)
    return output


def _parse_canonical_json_mapping(raw: bytes, label: str) -> dict[str, object]:
    try:
        parsed = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise FundamentalReadArchivedCopyBindingV2Error(f"{label}_invalid") from exc
    if type(parsed) is not dict or raw != _canonical_json_bytes(parsed):
        raise FundamentalReadArchivedCopyBindingV2Error(f"{label}_not_canonical_object")
    return parsed


def _is_strict_descendant(root: Path, candidate: Path) -> bool:
    root_normalized = Path(os.path.normcase(os.path.abspath(root)))
    candidate_normalized = Path(os.path.normcase(os.path.abspath(candidate)))
    try:
        relative = candidate_normalized.relative_to(root_normalized)
    except ValueError:
        return False
    return bool(relative.parts) and all(part not in {".", ".."} for part in relative.parts)


def _require_real_directory(path: Path) -> None:
    _reject_reparse_components(path)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_directory_unavailable") from exc
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    if stat.S_ISLNK(metadata.st_mode) or attributes & 0x400 or not stat.S_ISDIR(metadata.st_mode):
        raise FundamentalReadArchivedCopyBindingV2Error("v2_archive_directory_invalid")

