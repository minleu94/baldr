"""V2 snapshot 與原始月營收來源的純資料 archive 契約。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Literal, overload

from data_module.fundamental_read_snapshot import (
    FundamentalFilePin,
    MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES,
    MAX_RAW_ARCHIVE_FILE_BYTES,
    MAX_RAW_ARCHIVE_FILES,
    MAX_RAW_ARCHIVE_MANIFEST_BYTES,
    MAX_RAW_ARCHIVE_REFERENCE_JSON_BYTES,
    MAX_RAW_ARCHIVE_TOTAL_BYTES,
    MAX_SNAPSHOT_CAPTURE_MANIFEST_BYTES,
    MAX_SNAPSHOT_SOURCE_FILE_BYTES,
    _canonical_json_bytes,
    _canonical_sha256,
    _parse_snapshot_pin,
    _paths_overlap,
    _reject_json_constant,
    _unique_json_object,
    _validate_json_depth,
)
from data_module.fundamental_read_snapshot_cohort_v2 import (
    FundamentalReadSnapshotReferenceV2,
    FundamentalSnapshotSourceClockV2,
)


FUNDAMENTAL_READ_SNAPSHOT_RAW_ARCHIVE_V2_SCHEMA: Literal[
    "fundamental-monthly-raw-source-archive.v2"
] = "fundamental-monthly-raw-source-archive.v2"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ARCHIVE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_MAX_ARCHIVE_JSON_DEPTH = 24


def _reject_json_float(value: str) -> None:
    raise ValueError(f"raw archive JSON 不接受浮點數：{value[:32]}")


def _reject_float_tree(value: object) -> None:
    if type(value) is float:
        raise ValueError("raw archive JSON 不接受浮點數")
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("raw archive JSON object key 必須是字串")
            _reject_float_tree(item)
    elif type(value) is list:
        for item in value:
            _reject_float_tree(item)


def _bounded_object_json_bytes(value: object, *, limit: int, label: str) -> bytes:
    """對已解析 object 先限制 canonical 大小與深度，再驗型別。"""

    try:
        raw = _canonical_json_bytes(value)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError(f"{label} 無法 canonical 序列化") from exc
    if len(raw) > limit:
        raise ValueError(f"{label} 超過大小上限")
    _validate_json_depth(raw, max_depth=_MAX_ARCHIVE_JSON_DEPTH)
    _reject_float_tree(value)
    return raw


def _require_digest(value: object, name: str) -> str:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} 必須是小寫 SHA-256")
    return value


def _canonical_absolute_path(value: object, name: str) -> str:
    if type(value) is not str or not value or len(value) > 32_768 or "\x00" in value:
        raise ValueError(f"{name} 路徑無效")
    path = Path(value)
    if not path.is_absolute() or os.path.normpath(value) != value:
        raise ValueError(f"{name} 必須是詞法 canonical 絕對路徑")
    return value


def _relative_archive_path(value: object, name: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 4096
        or "\\" in value
        or ":" in value
    ):
        raise ValueError(f"{name} 必須是 POSIX 相對路徑")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{name} 不可離開 archive 根目錄")
    return value


@dataclass(frozen=True, slots=True)
class FundamentalReadSnapshotRawArchiveFileV2:
    """將一份原始月營收 capture pin 映射到 archive 根目錄。"""

    historical_pin: FundamentalFilePin
    relative_path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if type(self.historical_pin) is not FundamentalFilePin:
            raise TypeError("raw archive V2 historical_pin 型別錯誤")
        if (
            not self.historical_pin.present
            or self.historical_pin.role not in {"monthly_html", "monthly_csv"}
        ):
            raise ValueError("raw archive V2 僅接受存在的月營收 HTML/CSV pin")
        _relative_archive_path(self.relative_path, "raw archive V2 relative_path")
        if (
            type(self.size_bytes) is not int
            or not 0 <= self.size_bytes <= MAX_RAW_ARCHIVE_FILE_BYTES
        ):
            raise ValueError("raw archive V2 單份原始檔超過大小上限")
        digest = _require_digest(self.sha256, "raw archive V2 file sha256")
        if (
            self.historical_pin.size_bytes != self.size_bytes
            or self.historical_pin.sha256 != digest
        ):
            raise ValueError("raw archive V2 原始 bytes 必須等於歷史 pin")

    def to_dict(self) -> dict[str, object]:
        return {
            "historical_pin": self.historical_pin.to_dict(),
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class FundamentalReadSnapshotArchiveStoredFileV2:
    """將原 snapshot 樹中的一份檔案映射到自包含 archive。"""

    historical_pin: FundamentalFilePin
    relative_path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if type(self.historical_pin) is not FundamentalFilePin:
            raise TypeError("archive stored V2 historical_pin 型別錯誤")
        if not self.historical_pin.present:
            raise ValueError("archive stored V2 必須保留存在的原 snapshot pin")
        _relative_archive_path(self.relative_path, "archive stored V2 relative_path")
        if (
            type(self.size_bytes) is not int
            or not 0 <= self.size_bytes <= MAX_SNAPSHOT_SOURCE_FILE_BYTES
        ):
            raise ValueError("archive stored V2 單份 snapshot 檔超過大小上限")
        digest = _require_digest(self.sha256, "archive stored V2 file sha256")
        if (
            self.historical_pin.size_bytes != self.size_bytes
            or self.historical_pin.sha256 != digest
        ):
            raise ValueError("archive stored V2 bytes 必須等於歷史 pin")

    def to_dict(self) -> dict[str, object]:
        return {
            "historical_pin": self.historical_pin.to_dict(),
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


def _expected_snapshot_files(
    snapshot_reference: FundamentalReadSnapshotReferenceV2,
    source_clock: FundamentalSnapshotSourceClockV2,
) -> dict[str, tuple[FundamentalFilePin | None, int | None, str | None, str]]:
    """由原始 binding 推導 archive 必須保存的完整 snapshot 檔案清冊。"""

    binding = source_clock.snapshot_binding
    root = Path(snapshot_reference.snapshot_root)
    if binding.snapshot_root != str(root) or binding.snapshot_id != snapshot_reference.snapshot_id:
        raise ValueError("archive stored V2 snapshot binding root/id 不符")
    if binding.capture_manifest_pin_start != binding.capture_manifest_pin_finish:
        raise ValueError("archive stored V2 capture manifest 起訖 pin 不同")
    expected: dict[str, tuple[FundamentalFilePin | None, int | None, str | None, str]] = {}

    def add(
        relative_path: str,
        pin: FundamentalFilePin | None,
        size: int | None,
        digest: str | None,
        role: str,
    ) -> None:
        _relative_archive_path(relative_path, "snapshot logical relative_path")
        if relative_path in expected:
            prior_pin, prior_size, prior_digest, prior_role = expected[relative_path]
            if (
                prior_role != role
                or (prior_pin is not None and pin is not None and prior_pin != pin)
                or (prior_size is not None and size is not None and prior_size != size)
                or (prior_digest is not None and digest is not None and prior_digest != digest)
            ):
                raise ValueError("archive stored V2 snapshot pin 重複且內容不一致")
            merged_pin = pin if pin is not None else prior_pin
            if merged_pin is not None and merged_pin.role != role:
                raise ValueError("archive stored V2 snapshot pin role 不符")
            expected[relative_path] = (
                merged_pin,
                size if size is not None else prior_size,
                digest if digest is not None else prior_digest,
                role,
            )
            return
        if pin is not None:
            if (
                not pin.present
                or pin.path != str(root / Path(*PurePosixPath(relative_path).parts))
                or pin.role != role
            ):
                raise ValueError("archive stored V2 snapshot pin path/role 不符")
            if size is not None and pin.size_bytes != size:
                raise ValueError("archive stored V2 snapshot pin size 不符")
            if digest is not None and pin.sha256 != digest:
                raise ValueError("archive stored V2 snapshot pin sha 不符")
        expected[relative_path] = (pin, size, digest, role)

    capture_manifest_pin = binding.capture_manifest_pin_finish
    if (
        capture_manifest_pin.size_bytes is None
        or capture_manifest_pin.size_bytes > MAX_SNAPSHOT_CAPTURE_MANIFEST_BYTES
    ):
        raise ValueError("archive stored V2 snapshot capture manifest 超過大小上限")
    add(
        "snapshot_capture.json",
        capture_manifest_pin,
        capture_manifest_pin.size_bytes,
        capture_manifest_pin.sha256,
        "snapshot_capture_manifest",
    )
    add(
        "finished_source_clock.json",
        None,
        None,
        snapshot_reference.finished_manifest_sha256,
        "finished_source_clock_manifest",
    )
    add("attempt_status.json", None, None, None, "attempt_status")

    if len(binding.captured_files) != len(binding.captured_file_pins_start):
        raise ValueError("archive stored V2 captured file refs/pins 數量不符")
    if (
        len({item.relative_path for item in binding.captured_files})
        != len(binding.captured_files)
        or len({item.role for item in binding.captured_files})
        != len(binding.captured_files)
    ):
        raise ValueError("archive stored V2 captured file refs 重複")
    if binding.captured_file_pins_start != binding.captured_file_pins_finish:
        raise ValueError("archive stored V2 captured file 起訖 pin 不同")
    for reference, pin in zip(
        binding.captured_files,
        binding.captured_file_pins_start,
        strict=True,
    ):
        if (
            pin.role != reference.role
            or pin.size_bytes != reference.size_bytes
            or pin.sha256 != reference.sha256
        ):
            raise ValueError("archive stored V2 captured file pin/ref 不符")
        add(reference.relative_path, pin, reference.size_bytes, reference.sha256, reference.role)

    if (
        len({item.relative_path for item in binding.reader_files}) != len(binding.reader_files)
        or len({item.role for item in binding.reader_files}) != len(binding.reader_files)
    ):
        raise ValueError("archive stored V2 reader file refs 重複")
    reader_refs: dict[str, tuple[str, int, str]] = {}
    for reference in binding.reader_files:
        row = (reference.role, reference.size_bytes, reference.sha256)
        reader_refs[reference.relative_path] = row
        add(reference.relative_path, None, reference.size_bytes, reference.sha256, reference.role)
    for pin in binding.reader_file_pins_finish:
        if not pin.present:
            continue
        try:
            relative = Path(pin.path).relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError("archive stored V2 reader pin 離開 logical snapshot root") from exc
        expected_ref = reader_refs.get(relative)
        if expected_ref is None or expected_ref != (pin.role, pin.size_bytes, pin.sha256):
            raise ValueError("archive stored V2 reader pin/ref 不符")
        add(relative, pin, pin.size_bytes, pin.sha256, pin.role)
    return expected


@dataclass(frozen=True, slots=True)
class FundamentalReadSnapshotRawArchiveReferenceV2:
    """V2 archive 的傳輸資料；本物件不宣告檔案已讀回或來源已授權。"""

    snapshot_reference: FundamentalReadSnapshotReferenceV2
    snapshot_reference_sha256: str
    source_clock: FundamentalSnapshotSourceClockV2
    archive_root: str
    archive_id: str
    archived_snapshot_root: str
    archived_monthly_source_root: str
    original_monthly_source_root: str
    files: tuple[FundamentalReadSnapshotRawArchiveFileV2, ...]
    snapshot_files: tuple[FundamentalReadSnapshotArchiveStoredFileV2, ...]
    archive_manifest_sha256: str
    archive_identity_sha256: str
    schema_version: Literal["fundamental-monthly-raw-source-archive.v2"] = (
        FUNDAMENTAL_READ_SNAPSHOT_RAW_ARCHIVE_V2_SCHEMA
    )
    source_scope: Literal["current_observed_only"] = "current_observed_only"
    availability_status: Literal["cohort_hour_bound"] = "cohort_hour_bound"
    historical_pit_eligible: Literal[False] = False
    formal_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not str
            or self.schema_version != FUNDAMENTAL_READ_SNAPSHOT_RAW_ARCHIVE_V2_SCHEMA
        ):
            raise ValueError("raw archive V2 schema 不支援")
        if type(self.snapshot_reference) is not FundamentalReadSnapshotReferenceV2:
            raise TypeError("raw archive V2 必須綁 exact snapshot reference V2")
        if type(self.source_clock) is not FundamentalSnapshotSourceClockV2:
            raise TypeError("raw archive V2 必須綁 exact source clock V2")
        _require_digest(self.snapshot_reference_sha256, "snapshot_reference_sha256")
        if self.snapshot_reference_sha256 != sha256(
            self.snapshot_reference.to_json().encode("utf-8")
        ).hexdigest():
            raise ValueError("raw archive V2 nested snapshot reference sha 不符")

        snapshot_root = Path(
            _canonical_absolute_path(
                self.snapshot_reference.snapshot_root,
                "snapshot_reference.snapshot_root",
            )
        )
        archive_root = Path(_canonical_absolute_path(self.archive_root, "archive_root"))
        original_root = Path(
            _canonical_absolute_path(
                self.original_monthly_source_root,
                "original_monthly_source_root",
            )
        )
        if type(self.archive_id) is not str or not _ARCHIVE_ID_RE.fullmatch(self.archive_id):
            raise ValueError("raw archive V2 archive_id 格式錯誤")
        if archive_root.name != self.archive_id:
            raise ValueError("raw archive V2 archive_root/id 不符")
        expected_archived_snapshot = (
            archive_root / "saved_snapshot" / self.snapshot_reference.snapshot_id
        )
        expected_archived_monthly = archive_root / "monthly_source"
        if (
            _canonical_absolute_path(self.archived_snapshot_root, "archived_snapshot_root")
            != str(expected_archived_snapshot)
            or _canonical_absolute_path(
                self.archived_monthly_source_root,
                "archived_monthly_source_root",
            )
            != str(expected_archived_monthly)
        ):
            raise ValueError("raw archive V2 archived roots 不符固定 layout")
        if (
            _paths_overlap(archive_root, snapshot_root)
            or _paths_overlap(archive_root, original_root)
            or _paths_overlap(snapshot_root, original_root)
            or _paths_overlap(archive_root, Path(self.source_clock.database_path).parent)
        ):
            raise ValueError("raw archive V2 archive/source roots 重疊")

        clock = self.source_clock
        binding = clock.snapshot_binding
        reference = self.snapshot_reference
        if (
            binding.snapshot_root != reference.snapshot_root
            or binding.snapshot_id != reference.snapshot_id
            or reference.source_clock_identity_sha256 != clock.identity_sha256
            or reference.source_content_identity_sha256 != clock.source_content_identity_sha256
            or reference.daily_cohort_sha256 != clock.cohort_sha256
            or reference.decision_cutoff != clock.decision_cutoff.isoformat()
            or reference.declared_stock_codes != clock.declared_stock_codes
            or reference.declared_stock_codes_sha256 != clock.declared_stock_codes_sha256
            or clock.verified_markets != clock.cohort_pin.required_markets
            or clock.cohort_pin.available_hour > clock.decision_cutoff
        ):
            raise ValueError("raw archive V2 snapshot/clock/full daily pin 不一致")

        if (
            type(self.files) is not tuple
            or not self.files
            or len(self.files) > MAX_RAW_ARCHIVE_FILES
            or any(type(item) is not FundamentalReadSnapshotRawArchiveFileV2 for item in self.files)
            or len({item.relative_path for item in self.files}) != len(self.files)
            or len({item.historical_pin.path for item in self.files}) != len(self.files)
            or sum(item.size_bytes for item in self.files) > MAX_RAW_ARCHIVE_TOTAL_BYTES
        ):
            raise ValueError("raw archive V2 原始 capture inventory 無效或超過上限")
        if clock.capture_file_pins_start != clock.capture_file_pins_finish:
            raise ValueError("raw archive V2 historical capture 起訖 pin 不同")
        historical_capture_pins = clock.capture_file_pins_start
        if (
            tuple(item.historical_pin for item in self.files) != historical_capture_pins
            or len(historical_capture_pins) != len(self.files)
            or any(
                pin.role not in {"monthly_html", "monthly_csv"} or not pin.present
                for pin in historical_capture_pins
            )
        ):
            raise ValueError("raw archive V2 原件 inventory 未完整對應 source clock")
        for item in self.files:
            pin_path = Path(item.historical_pin.path)
            try:
                original_relative = pin_path.relative_to(original_root).as_posix()
            except ValueError as exc:
                raise ValueError("raw archive V2 historical capture 離開原始月營收根") from exc
            expected_relative = (
                PurePosixPath("monthly_source") / PurePosixPath(original_relative)
            ).as_posix()
            if item.relative_path != expected_relative:
                raise ValueError("raw archive V2 raw file relative path 不符 historical pin")

        expected_snapshot_files = _expected_snapshot_files(reference, clock)
        if (
            type(self.snapshot_files) is not tuple
            or len(self.snapshot_files) != len(expected_snapshot_files)
            or len(self.snapshot_files) > MAX_RAW_ARCHIVE_FILES
            or any(
                type(item) is not FundamentalReadSnapshotArchiveStoredFileV2
                for item in self.snapshot_files
            )
            or len({item.relative_path for item in self.snapshot_files}) != len(self.snapshot_files)
        ):
            raise ValueError("raw archive V2 saved snapshot inventory 不完整或超過上限")
        archived_prefix = PurePosixPath("saved_snapshot") / reference.snapshot_id
        for stored_item in self.snapshot_files:
            archived_prefix_text = f"{archived_prefix.as_posix()}/"
            expected = expected_snapshot_files.get(
                stored_item.relative_path.removeprefix(archived_prefix_text)
            )
            if expected is None or not stored_item.relative_path.startswith(archived_prefix_text):
                raise ValueError("raw archive V2 stored file 不在完整 saved snapshot 清冊中")
            expected_pin, expected_size, expected_sha, expected_role = expected
            relative_inside_snapshot = stored_item.relative_path.removeprefix(archived_prefix_text)
            historical_path = str(
                snapshot_root / Path(*PurePosixPath(relative_inside_snapshot).parts)
            )
            if (
                stored_item.historical_pin.path != historical_path
                or stored_item.historical_pin.role != expected_role
            ):
                raise ValueError("raw archive V2 stored historical path 與原 snapshot root 不符")
            if (
                expected_pin is not None and stored_item.historical_pin != expected_pin
            ) or (
                expected_size is not None and stored_item.size_bytes != expected_size
            ) or (
                expected_sha is not None and stored_item.sha256 != expected_sha
            ):
                raise ValueError("raw archive V2 stored file 與原 snapshot binding 不符")
            if (
                expected_role == "finished_source_clock_manifest"
                and stored_item.size_bytes > MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES
            ):
                raise ValueError("raw archive V2 finished manifest 超過大小上限")
            if (
                expected_role == "attempt_status"
                and stored_item.size_bytes > MAX_SNAPSHOT_CAPTURE_MANIFEST_BYTES
            ):
                raise ValueError("raw archive V2 attempt status 超過大小上限")
        if sum(item.size_bytes for item in self.snapshot_files) + sum(
            item.size_bytes for item in self.files
        ) > MAX_RAW_ARCHIVE_TOTAL_BYTES:
            raise ValueError("raw archive V2 合計 bytes 超過上限")
        if len(self.snapshot_files) + len(self.files) > MAX_RAW_ARCHIVE_FILES:
            raise ValueError("raw archive V2 合計檔案數超過上限")

        if (
            type(self.source_scope) is not str
            or self.source_scope != "current_observed_only"
            or type(self.availability_status) is not str
            or self.availability_status != "cohort_hour_bound"
        ):
            raise ValueError("raw archive V2 scope/availability 固定值不符")
        if self.historical_pit_eligible is not False or self.formal_pit_eligible is not False:
            raise ValueError("raw archive V2 不可授予 PIT 資格")

        manifest_digest = _require_digest(self.archive_manifest_sha256, "archive_manifest_sha256")
        identity_digest = _require_digest(self.archive_identity_sha256, "archive_identity_sha256")
        manifest_raw = _canonical_json_bytes(self.to_manifest_dict())
        if len(manifest_raw) > MAX_RAW_ARCHIVE_MANIFEST_BYTES:
            raise ValueError("raw archive V2 manifest 超過大小上限")
        if manifest_digest != sha256(manifest_raw).hexdigest():
            raise ValueError("raw archive V2 manifest body sha 不符")
        if identity_digest != _canonical_sha256(self._archive_identity_payload()):
            raise ValueError("raw archive V2 archive identity 不符")

    def to_manifest_dict(self) -> dict[str, object]:
        """回傳 raw_archive.json 的 canonical body，不含自我摘要欄位。"""

        return {
            "schema_version": self.schema_version,
            "snapshot_reference": self.snapshot_reference.to_dict(),
            "snapshot_reference_sha256": self.snapshot_reference_sha256,
            "source_clock": self.source_clock.to_dict(),
            "archive_root": self.archive_root,
            "archive_id": self.archive_id,
            "archived_snapshot_root": self.archived_snapshot_root,
            "archived_monthly_source_root": self.archived_monthly_source_root,
            "original_monthly_source_root": self.original_monthly_source_root,
            "files": [item.to_dict() for item in self.files],
            "snapshot_files": [item.to_dict() for item in self.snapshot_files],
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
        }

    def _archive_identity_payload(self) -> dict[str, object]:
        return {
            **self.to_manifest_dict(),
            "archive_manifest_sha256": self.archive_manifest_sha256,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._archive_identity_payload(),
            "archive_identity_sha256": self.archive_identity_sha256,
        }

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > MAX_RAW_ARCHIVE_REFERENCE_JSON_BYTES:
            raise ValueError("raw archive V2 reference 超過傳輸上限")
        return raw.decode("utf-8")

    @classmethod
    def from_dict(
        cls,
        value: object,
        *,
        expected_reference_sha256: str,
    ) -> FundamentalReadSnapshotRawArchiveReferenceV2:
        _require_digest(expected_reference_sha256, "expected_reference_sha256")
        if type(value) is not dict:
            raise ValueError("raw archive V2 reference 必須是 object")
        raw_bytes = _bounded_object_json_bytes(
            value,
            limit=MAX_RAW_ARCHIVE_REFERENCE_JSON_BYTES,
            label="raw archive V2 reference",
        )
        expected_keys = {
            "schema_version", "snapshot_reference", "snapshot_reference_sha256", "source_clock",
            "archive_root", "archive_id", "archived_snapshot_root", "archived_monthly_source_root",
            "original_monthly_source_root", "files", "snapshot_files", "archive_manifest_sha256",
            "archive_identity_sha256", "source_scope", "availability_status",
            "historical_pit_eligible", "formal_pit_eligible",
        }
        if set(value) != expected_keys:
            raise ValueError("raw archive V2 reference 欄位不符")
        if sha256(raw_bytes).hexdigest() != expected_reference_sha256:
            raise ValueError("raw archive V2 external reference sha 不符")
        snapshot_raw = value["snapshot_reference"]
        clock_raw = value["source_clock"]
        raw_files = value["files"]
        raw_snapshot_files = value["snapshot_files"]
        if (
            type(snapshot_raw) is not dict
            or type(clock_raw) is not dict
            or type(raw_files) is not list
            or type(raw_snapshot_files) is not list
        ):
            raise ValueError("raw archive V2 nested 欄位型別錯誤")
        if (
            len(raw_files) > MAX_RAW_ARCHIVE_FILES
            or len(raw_snapshot_files) > MAX_RAW_ARCHIVE_FILES
        ):
            raise ValueError("raw archive V2 nested file 數超過上限")
        snapshot_reference_sha = _require_digest(
            value["snapshot_reference_sha256"], "snapshot_reference_sha256"
        )
        snapshot_reference = FundamentalReadSnapshotReferenceV2.from_dict(
            snapshot_raw,
            expected_reference_sha256=snapshot_reference_sha,
        )
        source_clock_raw = _canonical_json_bytes(clock_raw)
        if len(source_clock_raw) > MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES:
            raise ValueError("raw archive V2 source clock 超過上限")
        source_clock = FundamentalSnapshotSourceClockV2.from_json(source_clock_raw)
        files = tuple(_parse_file_v2(item, stored=False) for item in raw_files)
        snapshot_files = tuple(_parse_file_v2(item, stored=True) for item in raw_snapshot_files)
        string_keys = {
            "schema_version", "snapshot_reference_sha256", "archive_root", "archive_id",
            "archived_snapshot_root", "archived_monthly_source_root",
            "original_monthly_source_root", "archive_manifest_sha256",
            "archive_identity_sha256", "source_scope", "availability_status",
        }
        if any(type(value[key]) is not str for key in string_keys):
            raise ValueError("raw archive V2 string field 型別錯誤")
        if (
            type(value["historical_pit_eligible"]) is not bool
            or type(value["formal_pit_eligible"]) is not bool
        ):
            raise ValueError("raw archive V2 PIT field 型別錯誤")
        if value["historical_pit_eligible"] is not False or value["formal_pit_eligible"] is not False:
            raise ValueError("raw archive V2 不可授予 PIT 資格")
        reference = cls(
            snapshot_reference=snapshot_reference,
            snapshot_reference_sha256=snapshot_reference_sha,
            source_clock=source_clock,
            archive_root=value["archive_root"],
            archive_id=value["archive_id"],
            archived_snapshot_root=value["archived_snapshot_root"],
            archived_monthly_source_root=value["archived_monthly_source_root"],
            original_monthly_source_root=value["original_monthly_source_root"],
            files=files,
            snapshot_files=snapshot_files,
            archive_manifest_sha256=value["archive_manifest_sha256"],
            archive_identity_sha256=value["archive_identity_sha256"],
            schema_version=value["schema_version"],
            source_scope=value["source_scope"],
            availability_status=value["availability_status"],
            historical_pit_eligible=False,
            formal_pit_eligible=False,
        )
        if raw_bytes != reference.to_json().encode("utf-8"):
            raise ValueError("raw archive V2 reference 必須是 canonical JSON")
        return reference

    @classmethod
    def from_manifest_dict(
        cls,
        value: object,
    ) -> FundamentalReadSnapshotRawArchiveReferenceV2:
        """解讀 archive manifest body；自洽不代表檔案已讀回或來源已受信任。"""

        if type(value) is not dict:
            raise ValueError("raw archive V2 manifest 必須是 object")
        _bounded_object_json_bytes(
            value,
            limit=MAX_RAW_ARCHIVE_MANIFEST_BYTES,
            label="raw archive V2 manifest",
        )
        expected_keys = {
            "schema_version", "snapshot_reference", "snapshot_reference_sha256", "source_clock",
            "archive_root", "archive_id", "archived_snapshot_root", "archived_monthly_source_root",
            "original_monthly_source_root", "files", "snapshot_files", "source_scope",
            "availability_status", "historical_pit_eligible", "formal_pit_eligible",
        }
        if set(value) != expected_keys:
            raise ValueError("raw archive V2 manifest 欄位不符")
        snapshot_raw = value["snapshot_reference"]
        clock_raw = value["source_clock"]
        raw_files = value["files"]
        raw_snapshot_files = value["snapshot_files"]
        if (
            type(snapshot_raw) is not dict
            or type(clock_raw) is not dict
            or type(raw_files) is not list
            or type(raw_snapshot_files) is not list
        ):
            raise ValueError("raw archive V2 manifest nested 欄位型別錯誤")
        if (
            len(raw_files) > MAX_RAW_ARCHIVE_FILES
            or len(raw_snapshot_files) > MAX_RAW_ARCHIVE_FILES
        ):
            raise ValueError("raw archive V2 manifest file 數超過上限")
        if type(value["snapshot_reference_sha256"]) is not str:
            raise ValueError("raw archive V2 snapshot reference digest 型別錯誤")
        snapshot_reference = FundamentalReadSnapshotReferenceV2.from_dict(
            snapshot_raw,
            expected_reference_sha256=value["snapshot_reference_sha256"],
        )
        clock_bytes = _canonical_json_bytes(clock_raw)
        if len(clock_bytes) > MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES:
            raise ValueError("raw archive V2 source clock 超過大小上限")
        source_clock = FundamentalSnapshotSourceClockV2.from_json(clock_bytes)
        files = tuple(_parse_file_v2(item, stored=False) for item in raw_files)
        snapshot_files = tuple(_parse_file_v2(item, stored=True) for item in raw_snapshot_files)
        string_keys = {
            "schema_version", "snapshot_reference_sha256", "archive_root", "archive_id",
            "archived_snapshot_root", "archived_monthly_source_root",
            "original_monthly_source_root",
            "source_scope", "availability_status",
        }
        if any(type(value[key]) is not str for key in string_keys):
            raise ValueError("raw archive V2 manifest string field 型別錯誤")
        if (
            type(value["historical_pit_eligible"]) is not bool
            or type(value["formal_pit_eligible"]) is not bool
        ):
            raise ValueError("raw archive V2 manifest PIT field 型別錯誤")
        if value["historical_pit_eligible"] is not False or value["formal_pit_eligible"] is not False:
            raise ValueError("raw archive V2 不可授予 PIT 資格")
        reference = make_raw_archive_reference_v2(
            snapshot_reference=snapshot_reference,
            snapshot_reference_sha256=value["snapshot_reference_sha256"],
            source_clock=source_clock,
            archive_root=value["archive_root"],
            archive_id=value["archive_id"],
            archived_snapshot_root=value["archived_snapshot_root"],
            archived_monthly_source_root=value["archived_monthly_source_root"],
            original_monthly_source_root=value["original_monthly_source_root"],
            files=files,
            snapshot_files=snapshot_files,
        )
        if reference.to_manifest_dict() != value:
            raise ValueError("raw archive V2 manifest body 非 canonical 或固定欄位不符")
        return reference

    @classmethod
    def from_json(
        cls,
        raw: str | bytes,
        *,
        expected_reference_sha256: str,
    ) -> FundamentalReadSnapshotRawArchiveReferenceV2:
        if type(raw) is bytes:
            encoded = raw
        elif type(raw) is str:
            try:
                encoded = raw.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise ValueError("raw archive V2 reference 非 UTF-8") from exc
        else:
            raise TypeError("raw archive V2 reference 必須是 str 或 bytes")
        if len(encoded) > MAX_RAW_ARCHIVE_REFERENCE_JSON_BYTES:
            raise ValueError("raw archive V2 reference 超過傳輸上限")
        _require_digest(expected_reference_sha256, "expected_reference_sha256")
        if sha256(encoded).hexdigest() != expected_reference_sha256:
            raise ValueError("raw archive V2 external reference sha 不符")
        _validate_json_depth(encoded, max_depth=_MAX_ARCHIVE_JSON_DEPTH)
        try:
            payload = json.loads(
                encoded.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
                parse_float=_reject_json_float,
            )
        except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise ValueError("raw archive V2 reference JSON 無效") from exc
        if type(payload) is not dict:
            raise ValueError("raw archive V2 reference 必須是 object")
        reference = cls.from_dict(
            payload,
            expected_reference_sha256=expected_reference_sha256,
        )
        if encoded != reference.to_json().encode("utf-8"):
            raise ValueError("raw archive V2 reference 必須是 canonical bytes")
        return reference


@overload
def _parse_file_v2(
    value: object,
    *,
    stored: Literal[False],
) -> FundamentalReadSnapshotRawArchiveFileV2: ...


@overload
def _parse_file_v2(
    value: object,
    *,
    stored: Literal[True],
) -> FundamentalReadSnapshotArchiveStoredFileV2: ...


def _parse_file_v2(
    value: object,
    *,
    stored: bool,
) -> FundamentalReadSnapshotRawArchiveFileV2 | FundamentalReadSnapshotArchiveStoredFileV2:
    expected = {"historical_pin", "relative_path", "size_bytes", "sha256"}
    if type(value) is not dict or set(value) != expected:
        raise ValueError("raw archive V2 file 欄位不符")
    if (
        type(value["relative_path"]) is not str
        or type(value["size_bytes"]) is not int
        or type(value["sha256"]) is not str
    ):
        raise ValueError("raw archive V2 file 欄位型別錯誤")
    historical_pin = _parse_snapshot_pin(value["historical_pin"])
    relative_path = value["relative_path"]
    size_bytes = value["size_bytes"]
    digest = value["sha256"]
    if stored:
        return FundamentalReadSnapshotArchiveStoredFileV2(
            historical_pin=historical_pin,
            relative_path=relative_path,
            size_bytes=size_bytes,
            sha256=digest,
        )
    return FundamentalReadSnapshotRawArchiveFileV2(
        historical_pin=historical_pin,
        relative_path=relative_path,
        size_bytes=size_bytes,
        sha256=digest,
    )


def make_raw_archive_reference_v2(
    *,
    snapshot_reference: FundamentalReadSnapshotReferenceV2,
    snapshot_reference_sha256: str,
    source_clock: FundamentalSnapshotSourceClockV2,
    archive_root: str,
    archive_id: str,
    archived_snapshot_root: str,
    archived_monthly_source_root: str,
    original_monthly_source_root: str,
    files: tuple[FundamentalReadSnapshotRawArchiveFileV2, ...],
    snapshot_files: tuple[FundamentalReadSnapshotArchiveStoredFileV2, ...],
) -> FundamentalReadSnapshotRawArchiveReferenceV2:
    """依 manifest body 與 archive identity 的固定順序建立 typed V2 參照。"""

    if type(snapshot_reference) is not FundamentalReadSnapshotReferenceV2:
        raise TypeError("raw archive V2 factory 必須使用 snapshot reference V2")
    if type(source_clock) is not FundamentalSnapshotSourceClockV2:
        raise TypeError("raw archive V2 factory 必須使用 source clock V2")
    if type(files) is not tuple or type(snapshot_files) is not tuple:
        raise TypeError("raw archive V2 factory file inventories 必須是 tuple")
    if any(type(item) is not FundamentalReadSnapshotRawArchiveFileV2 for item in files):
        raise TypeError("raw archive V2 factory raw file 型別錯誤")
    if any(type(item) is not FundamentalReadSnapshotArchiveStoredFileV2 for item in snapshot_files):
        raise TypeError("raw archive V2 factory stored file 型別錯誤")
    payload = {
        "schema_version": FUNDAMENTAL_READ_SNAPSHOT_RAW_ARCHIVE_V2_SCHEMA,
        "snapshot_reference": snapshot_reference.to_dict(),
        "snapshot_reference_sha256": snapshot_reference_sha256,
        "source_clock": source_clock.to_dict(),
        "archive_root": archive_root,
        "archive_id": archive_id,
        "archived_snapshot_root": archived_snapshot_root,
        "archived_monthly_source_root": archived_monthly_source_root,
        "original_monthly_source_root": original_monthly_source_root,
        "files": [item.to_dict() for item in files],
        "snapshot_files": [item.to_dict() for item in snapshot_files],
        "source_scope": "current_observed_only",
        "availability_status": "cohort_hour_bound",
        "historical_pit_eligible": False,
        "formal_pit_eligible": False,
    }
    manifest_raw = _canonical_json_bytes(payload)
    if len(manifest_raw) > MAX_RAW_ARCHIVE_MANIFEST_BYTES:
        raise ValueError("raw archive V2 manifest 超過大小上限")
    manifest_sha = sha256(manifest_raw).hexdigest()
    archive_identity = _canonical_sha256({**payload, "archive_manifest_sha256": manifest_sha})
    return FundamentalReadSnapshotRawArchiveReferenceV2(
        snapshot_reference=snapshot_reference,
        snapshot_reference_sha256=snapshot_reference_sha256,
        source_clock=source_clock,
        archive_root=archive_root,
        archive_id=archive_id,
        archived_snapshot_root=archived_snapshot_root,
        archived_monthly_source_root=archived_monthly_source_root,
        original_monthly_source_root=original_monthly_source_root,
        files=files,
        snapshot_files=snapshot_files,
        archive_manifest_sha256=manifest_sha,
        archive_identity_sha256=archive_identity,
    )


@dataclass(frozen=True, slots=True)
class UnverifiedFundamentalReadSnapshotRawArchiveReferenceV2:
    """外部 digest 已比對的傳輸參照，尚未驗證 archive 檔案或發行資格。"""

    reference: FundamentalReadSnapshotRawArchiveReferenceV2
    external_reference_sha256: str

    def __post_init__(self) -> None:
        if type(self.reference) is not FundamentalReadSnapshotRawArchiveReferenceV2:
            raise TypeError("unverified raw archive V2 reference 型別錯誤")
        _require_digest(self.external_reference_sha256, "external_reference_sha256")
        actual = sha256(self.reference.to_json().encode("utf-8")).hexdigest()
        if actual != self.external_reference_sha256:
            raise ValueError("unverified raw archive V2 external sha 與內容不符")


def decode_raw_archive_reference_v2(
    raw: str | bytes,
    *,
    expected_reference_sha256: str,
) -> UnverifiedFundamentalReadSnapshotRawArchiveReferenceV2:
    """解碼需 caller digest 錨定的 V2 reference；不授予 reader 資格。"""

    reference = FundamentalReadSnapshotRawArchiveReferenceV2.from_json(
        raw,
        expected_reference_sha256=expected_reference_sha256,
    )
    return UnverifiedFundamentalReadSnapshotRawArchiveReferenceV2(
        reference=reference,
        external_reference_sha256=expected_reference_sha256,
    )


__all__ = [
    "FUNDAMENTAL_READ_SNAPSHOT_RAW_ARCHIVE_V2_SCHEMA",
    "FundamentalReadSnapshotArchiveStoredFileV2",
    "FundamentalReadSnapshotRawArchiveFileV2",
    "FundamentalReadSnapshotRawArchiveReferenceV2",
    "UnverifiedFundamentalReadSnapshotRawArchiveReferenceV2",
    "decode_raw_archive_reference_v2",
    "make_raw_archive_reference_v2",
]
