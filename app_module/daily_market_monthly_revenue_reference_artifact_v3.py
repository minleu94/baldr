"""保存及精確重讀 reader-issued 月營收來源參照的隔離 artifact。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from dataclasses import dataclass
from typing import Callable, Sequence, cast

from app_module.daily_market_monthly_revenue_yoy_index_v2 import (
    DailyMarketMonthlyRevenueYoyIndexSessionV2,
)
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    DAILY_MARKET_MONTHLY_REVENUE_SOURCE_REFERENCE_V3_SCHEMA,
    DailyMarketMonthlyRevenueCohortV2Error,
    DailyMarketMonthlyRevenueSourceReferenceV3,
    UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3,
    decode_daily_market_monthly_revenue_source_reference_v3,
)


DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_DESCRIPTOR_V3_SCHEMA = (
    "daily-market-monthly-revenue-reference-artifact-descriptor.v3"
)
DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_V3_SCHEMA = (
    "daily-market-monthly-revenue-reference-artifact.v3"
)
_MAX_REFERENCE_BYTES = 32 * 1024 * 1024
_MAX_DESCRIPTOR_BYTES = 4 * 1024 * 1024
_MAX_DESCRIPTOR_DEPTH = 24
_MAX_CODES = 100_000
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_ARTIFACT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
_DESCRIPTOR_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_schema_version",
        "artifact_id",
        "reference_relative_path",
        "descriptor_relative_path",
        "reference_size_bytes",
        "reference_sha256",
        "source_reference_identity_sha256",
        "index_identity_sha256",
        "read_session_identity_sha256",
        "source_clock_identity_sha256",
        "source_content_identity_sha256",
        "finished_cohort_identity_sha256",
        "cohort_sha256",
        "decision_cutoff",
        "declared_stock_codes",
        "declared_stock_codes_sha256",
        "result_ledger_sha256",
        "fact_ledger_sha256",
        "reader_result_status_counts",
        "fact_state_counts",
        "projected_state_counts",
        "source_scope",
        "availability_status",
        "complete",
        "historical_pit_eligible",
        "formal_pit_eligible",
    }
)


class DailyMarketMonthlyRevenueReferenceArtifactV3Error(ValueError):
    """參照 artifact 的來源、路徑、內容或外部錨點無效。"""


def _fail(reason: str) -> DailyMarketMonthlyRevenueReferenceArtifactV3Error:
    return DailyMarketMonthlyRevenueReferenceArtifactV3Error(reason)


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise _fail("reference_artifact_json_not_canonicalizable") from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _fail(f"{label}_sha256_invalid")
    return cast(str, value)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _fail("reference_artifact_duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise _fail(f"reference_artifact_nonfinite_json_number:{value}")


def _reject_float(value: str) -> object:
    raise _fail("reference_artifact_float_not_allowed")


def _validate_json_depth(raw: bytes) -> None:
    depth = 0
    in_string = False
    escaped = False
    for byte in raw:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x7B, 0x5B):
            depth += 1
            if depth > _MAX_DESCRIPTOR_DEPTH:
                raise _fail("reference_artifact_json_depth_exceeded")
        elif byte in (0x7D, 0x5D):
            depth -= 1
            if depth < 0:
                raise _fail("reference_artifact_json_depth_invalid")
    if in_string or depth != 0:
        raise _fail("reference_artifact_json_structure_invalid")


def _decode_json_object(raw: bytes, *, label: str, maximum: int) -> dict[str, object]:
    if type(raw) is not bytes or len(raw) > maximum:
        raise _fail(f"{label}_size_invalid")
    if not raw:
        raise _fail(f"{label}_empty")
    _validate_json_depth(raw)
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except DailyMarketMonthlyRevenueReferenceArtifactV3Error:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise _fail(f"{label}_json_invalid") from exc
    if type(value) is not dict:
        raise _fail(f"{label}_object_required")
    return cast(dict[str, object], value)


def _stat_signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_size),
        int(getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000))),
        int(getattr(info, "st_ctime_ns", int(info.st_ctime * 1_000_000_000))),
        int(getattr(info, "st_nlink", 1)),
        int(getattr(info, "st_file_attributes", 0)),
    )


def _is_reparse_or_link(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


def _check_path_components(path: Path, *, require_directory: bool) -> os.stat_result:
    if not path.is_absolute() or ".." in path.parts or "\x00" in str(path):
        raise _fail("artifact_root_must_be_absolute_normal_path")
    current = Path(path.anchor)
    parts = path.parts[1:]
    final_info: os.stat_result | None = None
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except OSError as exc:
            raise _fail("artifact_root_component_unavailable") from exc
        if _is_reparse_or_link(info):
            raise _fail("artifact_root_component_reparse_refused")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise _fail("artifact_root_ancestor_not_directory")
        final_info = info
    if final_info is None:
        final_info = path.lstat()
    if require_directory and not stat.S_ISDIR(final_info.st_mode):
        raise _fail("artifact_root_not_directory")
    return final_info


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path))).rstrip("\\/").casefold()


def _overlaps(left: Path, right: Path) -> bool:
    left_key = _path_key(left)
    right_key = _path_key(right)
    separator = os.sep.casefold()
    return (
        left_key == right_key
        or left_key.startswith(right_key + separator)
        or right_key.startswith(left_key + separator)
    )


def _protected_roots(caller_roots: Sequence[Path]) -> tuple[Path, ...]:
    if type(caller_roots) not in (tuple, list) or not caller_roots:
        raise _fail("artifact_protected_roots_required")
    roots: list[Path] = []
    for caller_root in caller_roots:
        if not isinstance(caller_root, Path) or not caller_root.is_absolute() or ".." in caller_root.parts:
            raise _fail("artifact_protected_root_invalid")
        roots.append(caller_root)
    project_root = Path(__file__).resolve().parents[1]
    roots.append(project_root / "output")
    data_root_value = os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data")
    output_root_value = os.environ.get(
        "OUTPUT_ROOT", str(Path(data_root_value) / "output")
    )
    for configured_root_raw in (data_root_value, output_root_value):
        configured_root_path = Path(configured_root_raw)
        if not configured_root_path.is_absolute() or ".." in configured_root_path.parts:
            raise _fail("artifact_configured_protected_root_invalid")
        roots.append(configured_root_path)
    for key in ("PERSONAL_DATA_ROOT", "PERSONAL_STORE_ROOT"):
        personal_root_raw = os.environ.get(key)
        if personal_root_raw:
            personal_root_path = Path(personal_root_raw)
            if not personal_root_path.is_absolute() or ".." in personal_root_path.parts:
                raise _fail("artifact_configured_personal_root_invalid")
            roots.append(personal_root_path)
    return tuple(roots)


def _validate_artifact_root(
    value: Path,
    *,
    protected_roots: Sequence[Path],
) -> Path:
    if not isinstance(value, Path):
        raise _fail("artifact_root_path_required")
    _check_path_components(value, require_directory=True)
    for forbidden in _protected_roots(protected_roots):
        if _overlaps(value, forbidden):
            raise _fail("artifact_root_overlaps_project_output_or_formal_data")
    return value


def _artifact_id(value: object) -> str:
    if type(value) is not str or _ARTIFACT_ID_RE.fullmatch(value) is None:
        raise _fail("artifact_id_invalid")
    return cast(str, value)


def _check_file(path: Path, label: str) -> tuple[int, ...]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise _fail(f"{label}_unavailable") from exc
    if _is_reparse_or_link(info):
        raise _fail(f"{label}_reparse_refused")
    if not stat.S_ISREG(info.st_mode):
        raise _fail(f"{label}_not_regular")
    if int(getattr(info, "st_nlink", 1)) != 1:
        raise _fail(f"{label}_hardlink_refused")
    return _stat_signature(info)


def _read_verified_file(path: Path, *, label: str, maximum: int) -> tuple[bytes, tuple[int, ...]]:
    before = _check_file(path, label)
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise _fail(f"{label}_open_failed") from exc
    try:
        opened = os.fstat(descriptor)
        if _is_reparse_or_link(opened) or not stat.S_ISREG(opened.st_mode):
            raise _fail(f"{label}_opened_file_invalid")
        if int(getattr(opened, "st_nlink", 1)) != 1 or _stat_signature(opened) != before:
            raise _fail(f"{label}_changed_before_read")
        chunks: list[bytes] = []
        total = 0
        after_handle: os.stat_result | None = None
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise _fail(f"{label}_size_exceeded")
        after_handle = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after_path = _check_file(path, label)
    if (
        after_handle is None
        or _stat_signature(after_handle) != before
        or after_path != before
        or total != before[3]
    ):
        raise _fail(f"{label}_changed_during_read")
    return b"".join(chunks), before


def _create_only_write(
    path: Path,
    raw: bytes,
    *,
    label: str,
    cancel_callback: Callable[[], bool] | None,
) -> tuple[int, ...]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise _fail(f"{label}_create_only_collision") from exc
    except OSError as exc:
        raise _fail(f"{label}_create_failed") from exc
    created_identity: tuple[int, int] | None = None
    after_handle: os.stat_result | None = None
    try:
        opened = os.fstat(descriptor)
        created_identity = (int(opened.st_dev), int(opened.st_ino))
        if _is_reparse_or_link(opened) or not stat.S_ISREG(opened.st_mode):
            raise _fail(f"{label}_created_file_invalid")
        if int(getattr(opened, "st_nlink", 1)) != 1:
            raise _fail(f"{label}_created_file_hardlinked")
        offset = 0
        while offset < len(raw):
            _check_cancel(cancel_callback)
            count = os.write(descriptor, raw[offset : offset + 1024 * 1024])
            if count <= 0:
                raise _fail(f"{label}_short_write")
            offset += count
        os.fsync(descriptor)
        after_handle = os.fstat(descriptor)
    except BaseException:
        os.close(descriptor)
        _cleanup_created_identity(path, created_identity)
        raise
    else:
        os.close(descriptor)
    try:
        after_path = _check_file(path, label)
        if (
            after_handle is None
            or after_path != _stat_signature(after_handle)
            or after_path[3] != len(raw)
        ):
            raise _fail(f"{label}_changed_after_write")
        return after_path
    except BaseException:
        _cleanup_created_identity(path, created_identity)
        raise


def _check_cancel(callback: Callable[[], bool] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        raise _fail("cancel_callback_invalid")
    try:
        result = callback()
    except Exception as exc:
        raise _fail("artifact_cancel_callback_failed") from exc
    if type(result) is not bool:
        raise _fail("artifact_cancel_callback_not_boolean")
    if result:
        raise _fail("artifact_publication_cancelled")


def _cleanup_owned(path: Path, signature: tuple[int, ...] | None) -> None:
    if signature is None:
        return
    try:
        current = _check_file(path, "artifact_cleanup_target")
        if current == signature:
            path.unlink()
    except OSError:
        return
    except DailyMarketMonthlyRevenueReferenceArtifactV3Error:
        return


def _cleanup_created_identity(path: Path, identity: tuple[int, int] | None) -> None:
    """寫入失敗時，只移除本次 exclusive-create 出現的同一檔案物件。"""

    if identity is None:
        return
    try:
        current = _check_file(path, "artifact_partial_cleanup_target")
        if current[:2] == identity:
            path.unlink()
    except OSError:
        return
    except DailyMarketMonthlyRevenueReferenceArtifactV3Error:
        return


def _status_counts(value: object, *, label: str) -> tuple[tuple[str, int], ...]:
    if type(value) is not tuple:
        raise _fail(f"{label}_invalid")
    items = cast(tuple[object, ...], value)
    if len(items) > 8:
        raise _fail(f"{label}_invalid")
    result: list[tuple[str, int]] = []
    for item in items:
        if (
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
            or item[1] < 0
        ):
            raise _fail(f"{label}_entry_invalid")
        pair = cast(tuple[object, ...], item)
        result.append((cast(str, pair[0]), cast(int, pair[1])))
    return tuple(result)


@dataclass(frozen=True, slots=True, init=False)
class DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3:
    """不可變 artifact descriptor；跨程序信任仍須 caller 提供外部 SHA。"""

    schema_version: str
    artifact_schema_version: str
    artifact_id: str
    reference_relative_path: str
    descriptor_relative_path: str
    reference_size_bytes: int
    reference_sha256: str
    source_reference_identity_sha256: str
    index_identity_sha256: str
    read_session_identity_sha256: str
    source_clock_identity_sha256: str
    source_content_identity_sha256: str
    finished_cohort_identity_sha256: str
    cohort_sha256: str
    decision_cutoff: str
    declared_stock_codes: tuple[str, ...]
    declared_stock_codes_sha256: str
    result_ledger_sha256: str
    fact_ledger_sha256: str
    reader_result_status_counts: tuple[tuple[str, int], ...]
    fact_state_counts: tuple[tuple[str, int], ...]
    projected_state_counts: tuple[tuple[str, int], ...]
    source_scope: str
    availability_status: str
    complete: bool
    historical_pit_eligible: bool
    formal_pit_eligible: bool
    _writer_issued: bool

    def __init__(self) -> None:
        raise TypeError("descriptor 只能由 publisher 或 artifact reader 建立")

    @classmethod
    def _from_values(
        cls,
        values: dict[str, object],
        *,
        writer_issued: bool,
    ) -> DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3:
        result = object.__new__(cls)
        for name in (
            "schema_version",
            "artifact_schema_version",
            "artifact_id",
            "reference_relative_path",
            "descriptor_relative_path",
            "reference_size_bytes",
            "reference_sha256",
            "source_reference_identity_sha256",
            "index_identity_sha256",
            "read_session_identity_sha256",
            "source_clock_identity_sha256",
            "source_content_identity_sha256",
            "finished_cohort_identity_sha256",
            "cohort_sha256",
            "decision_cutoff",
            "declared_stock_codes",
            "declared_stock_codes_sha256",
            "result_ledger_sha256",
            "fact_ledger_sha256",
            "reader_result_status_counts",
            "fact_state_counts",
            "projected_state_counts",
            "source_scope",
            "availability_status",
            "complete",
            "historical_pit_eligible",
            "formal_pit_eligible",
        ):
            object.__setattr__(result, name, values[name])
        object.__setattr__(result, "_writer_issued", writer_issued)
        return cast(DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3, result)

    @property
    def is_writer_issued(self) -> bool:
        return self._writer_issued is True

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_schema_version": self.artifact_schema_version,
            "artifact_id": self.artifact_id,
            "reference_relative_path": self.reference_relative_path,
            "descriptor_relative_path": self.descriptor_relative_path,
            "reference_size_bytes": self.reference_size_bytes,
            "reference_sha256": self.reference_sha256,
            "source_reference_identity_sha256": self.source_reference_identity_sha256,
            "index_identity_sha256": self.index_identity_sha256,
            "read_session_identity_sha256": self.read_session_identity_sha256,
            "source_clock_identity_sha256": self.source_clock_identity_sha256,
            "source_content_identity_sha256": self.source_content_identity_sha256,
            "finished_cohort_identity_sha256": self.finished_cohort_identity_sha256,
            "cohort_sha256": self.cohort_sha256,
            "decision_cutoff": self.decision_cutoff,
            "declared_stock_codes": list(self.declared_stock_codes),
            "declared_stock_codes_sha256": self.declared_stock_codes_sha256,
            "result_ledger_sha256": self.result_ledger_sha256,
            "fact_ledger_sha256": self.fact_ledger_sha256,
            "reader_result_status_counts": [list(item) for item in self.reader_result_status_counts],
            "fact_state_counts": [list(item) for item in self.fact_state_counts],
            "projected_state_counts": [list(item) for item in self.projected_state_counts],
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "complete": self.complete,
            "historical_pit_eligible": self.historical_pit_eligible,
            "formal_pit_eligible": self.formal_pit_eligible,
        }

    def to_bytes(self) -> bytes:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > _MAX_DESCRIPTOR_BYTES:
            raise _fail("descriptor_size_exceeded")
        return raw

    def to_json(self) -> str:
        return self.to_bytes().decode("utf-8")

    @property
    def external_descriptor_sha256(self) -> str:
        return _sha256(self.to_bytes())


@dataclass(frozen=True, slots=True)
class UnverifiedDailyMarketMonthlyRevenueReferenceArtifactV3:
    """已由外部 descriptor SHA 綁定的解析結果；不代表 source acceptance。"""

    source_reference: UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3
    descriptor: DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3
    external_descriptor_sha256: str

    def __post_init__(self) -> None:
        if type(self.source_reference) is not UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3:
            raise _fail("artifact_unverified_source_reference_type_invalid")
        if type(self.descriptor) is not DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3:
            raise _fail("artifact_descriptor_type_invalid")
        _require_sha256(self.external_descriptor_sha256, "external_descriptor")


def _ledger_hash(ledger: tuple[tuple[str, str], ...]) -> str:
    return _sha256(_canonical_json_bytes([list(item) for item in ledger]))


def _build_descriptor_values(
    *,
    artifact_id: str,
    reference_raw: bytes,
    source_reference: DailyMarketMonthlyRevenueSourceReferenceV3,
    index: object,
) -> dict[str, object]:
    index_identity = getattr(index, "index_identity_sha256", None)
    clock = getattr(index, "source_clock", None)
    read_session_identity = getattr(index, "read_session_identity_sha256", None)
    if type(index_identity) is not str or clock is None or type(read_session_identity) is not str:
        raise _fail("reader_issued_index_metadata_missing")
    if type(clock.identity_sha256) is not str:
        raise _fail("reader_issued_source_clock_identity_missing")
    codes = source_reference.declared_stock_codes
    if type(codes) is not tuple or not codes or len(codes) > _MAX_CODES:
        raise _fail("source_reference_declared_codes_invalid")
    return {
        "schema_version": DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_DESCRIPTOR_V3_SCHEMA,
        "artifact_schema_version": DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_V3_SCHEMA,
        "artifact_id": artifact_id,
        "reference_relative_path": f"{artifact_id}.source-reference.v3.json",
        "descriptor_relative_path": f"{artifact_id}.descriptor.v3.json",
        "reference_size_bytes": len(reference_raw),
        "reference_sha256": _sha256(reference_raw),
        "source_reference_identity_sha256": source_reference.identity_sha256,
        "index_identity_sha256": index_identity,
        "read_session_identity_sha256": read_session_identity,
        "source_clock_identity_sha256": clock.identity_sha256,
        "source_content_identity_sha256": source_reference.source_content_identity_sha256,
        "finished_cohort_identity_sha256": source_reference.finished_cohort_identity_sha256,
        "cohort_sha256": source_reference.cohort_pin.cohort_sha256,
        "decision_cutoff": source_reference.decision_cutoff,
        "declared_stock_codes": codes,
        "declared_stock_codes_sha256": source_reference.declared_stock_codes_sha256,
        "result_ledger_sha256": _ledger_hash(source_reference.result_identity_by_stock),
        "fact_ledger_sha256": _ledger_hash(source_reference.fact_identity_by_stock),
        "reader_result_status_counts": _status_counts(
            source_reference.reader_result_status_counts,
            label="reader_result_status_counts",
        ),
        "fact_state_counts": _status_counts(
            source_reference.fact_state_counts,
            label="fact_state_counts",
        ),
        "projected_state_counts": _status_counts(
            getattr(index, "projected_state_counts", None),
            label="projected_state_counts",
        ),
        "source_scope": source_reference.source_scope,
        "availability_status": source_reference.availability_status,
        "complete": getattr(index, "complete", None),
        "historical_pit_eligible": source_reference.historical_pit_eligible,
        "formal_pit_eligible": source_reference.formal_pit_eligible,
    }


def _descriptor_from_values(
    values: dict[str, object],
    *,
    writer_issued: bool,
) -> DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3:
    codes = values.get("declared_stock_codes")
    if type(codes) not in (tuple, list):
        raise _fail("descriptor_declared_codes_invalid")
    code_items = cast(tuple[object, ...] | list[object], codes)
    if not code_items or len(code_items) > _MAX_CODES:
        raise _fail("descriptor_declared_codes_invalid")
    if any(
        type(code) is not str or not re.fullmatch(r"[A-Za-z0-9]{1,6}", code)
        for code in code_items
    ):
        raise _fail("descriptor_declared_codes_invalid")
    code_strings = tuple(cast(str, code) for code in code_items)
    if code_strings != tuple(sorted(set(code_strings))):
        raise _fail("descriptor_declared_codes_invalid")
    if values.get("schema_version") != DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_DESCRIPTOR_V3_SCHEMA:
        raise _fail("descriptor_schema_unsupported")
    if values.get("artifact_schema_version") != DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_V3_SCHEMA:
        raise _fail("descriptor_artifact_schema_unsupported")
    artifact_id = _artifact_id(values.get("artifact_id"))
    if values.get("reference_relative_path") != f"{artifact_id}.source-reference.v3.json":
        raise _fail("descriptor_reference_path_invalid")
    if values.get("descriptor_relative_path") != f"{artifact_id}.descriptor.v3.json":
        raise _fail("descriptor_path_invalid")
    size = values.get("reference_size_bytes")
    if type(size) is not int or size <= 0 or size > _MAX_REFERENCE_BYTES:
        raise _fail("descriptor_reference_size_invalid")
    for key in (
        "reference_sha256",
        "source_reference_identity_sha256",
        "index_identity_sha256",
        "read_session_identity_sha256",
        "source_clock_identity_sha256",
        "source_content_identity_sha256",
        "finished_cohort_identity_sha256",
        "cohort_sha256",
        "declared_stock_codes_sha256",
        "result_ledger_sha256",
        "fact_ledger_sha256",
    ):
        _require_sha256(values.get(key), f"descriptor_{key}")
    cutoff = values.get("decision_cutoff")
    if type(cutoff) is not str or not cutoff or len(cutoff) > 64:
        raise _fail("descriptor_decision_cutoff_invalid")
    if values.get("source_scope") != "current_observed_only":
        raise _fail("descriptor_source_scope_invalid")
    if values.get("availability_status") != "cohort_hour_bound":
        raise _fail("descriptor_availability_status_invalid")
    if values.get("complete") is not True:
        raise _fail("descriptor_incomplete")
    if values.get("historical_pit_eligible") is not False:
        raise _fail("descriptor_historical_pit_must_remain_false")
    if values.get("formal_pit_eligible") is not False:
        raise _fail("descriptor_formal_pit_must_remain_false")
    counts_fields: dict[str, tuple[tuple[str, int], ...]] = {}
    for key in (
        "reader_result_status_counts",
        "fact_state_counts",
        "projected_state_counts",
    ):
        raw = values.get(key)
        if type(raw) not in (list, tuple):
            raise _fail(f"descriptor_{key}_invalid")
        raw_items = cast(list[object] | tuple[object, ...], raw)
        if len(raw_items) > 8:
            raise _fail(f"descriptor_{key}_invalid")
        counts: list[tuple[str, int]] = []
        for raw_item in raw_items:
            if type(raw_item) not in (list, tuple):
                raise _fail(f"descriptor_{key}_entry_invalid")
            item = cast(list[object] | tuple[object, ...], raw_item)
            if (
                len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) is not int
                or item[1] < 0
            ):
                raise _fail(f"descriptor_{key}_entry_invalid")
            counts.append((cast(str, item[0]), cast(int, item[1])))
        counts_fields[key] = tuple(counts)
    for key in (
        "reader_result_status_counts",
        "fact_state_counts",
        "projected_state_counts",
    ):
        if sum(count for _, count in counts_fields[key]) != len(code_strings):
            raise _fail(f"descriptor_{key}_denominator_mismatch")
    result = dict(values)
    result["artifact_id"] = artifact_id
    result["declared_stock_codes"] = code_strings
    result.update(counts_fields)
    return DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3._from_values(
        result,
        writer_issued=writer_issued,
    )


def _descriptor_from_bytes(raw: bytes) -> DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3:
    payload = _decode_json_object(raw, label="descriptor", maximum=_MAX_DESCRIPTOR_BYTES)
    if set(payload) != _DESCRIPTOR_FIELDS:
        raise _fail("descriptor_fields_invalid")
    descriptor = _descriptor_from_values(payload, writer_issued=False)
    if descriptor.to_bytes() != raw:
        raise _fail("descriptor_not_canonical")
    return descriptor


def _verify_writer_inputs(
    index_session: DailyMarketMonthlyRevenueYoyIndexSessionV2,
) -> tuple[object, DailyMarketMonthlyRevenueSourceReferenceV3, bytes]:
    if type(index_session) is not DailyMarketMonthlyRevenueYoyIndexSessionV2:
        raise _fail("reader_issued_index_session_required")
    if index_session.finished is not True:
        raise _fail("index_session_not_finished")
    index = index_session.index
    index.require_reader_issued(index_session)
    reference = index_session.source_reference
    if type(reference) is not DailyMarketMonthlyRevenueSourceReferenceV3:
        raise _fail("source_reference_v3_required")
    if (
        index.complete is not True
        or index.source_scope != "current_observed_only"
        or index.availability_status != "cohort_hour_bound"
        or index.historical_pit_eligible is not False
        or index.formal_pit_eligible is not False
        or index._source_reference != reference
        or index.declared_stock_codes != reference.declared_stock_codes
        or index.cohort_pin != reference.cohort_pin
        or index.decision_cutoff.isoformat() != reference.decision_cutoff
        or index.source_content_identity_sha256 != reference.source_content_identity_sha256
        or index.finished_cohort_identity_sha256 != reference.finished_cohort_identity_sha256
        or index.result_identity_by_stock != reference.result_identity_by_stock
        or index.fact_identity_by_stock != reference.fact_identity_by_stock
        or index.reader_result_status_counts != reference.reader_result_status_counts
        or index.fact_state_counts != reference.fact_state_counts
        or tuple(entry.stock_code for entry in index.entries) != reference.declared_stock_codes
        or tuple((entry.stock_code, entry.result_identity_sha256) for entry in index.entries)
        != index.result_identity_by_stock
        or tuple((entry.stock_code, entry.source_fact.identity_sha256) for entry in index.entries)
        != index.fact_identity_by_stock
        or tuple((entry.stock_code, entry.projected_fact.identity_sha256) for entry in index.entries)
        != index.projected_fact_identity_by_stock
    ):
        raise _fail("index_and_source_reference_binding_mismatch")
    total = len(index.declared_stock_codes)
    if any(
        sum(count for _, count in counts) != total
        for counts in (
            index.reader_result_status_counts,
            index.fact_state_counts,
            index.projected_state_counts,
        )
    ):
        raise _fail("index_ledger_denominator_mismatch")
    raw = reference.to_json().encode("utf-8", errors="strict")
    if len(raw) > _MAX_REFERENCE_BYTES or _sha256(raw) != reference.external_reference_sha256:
        raise _fail("source_reference_canonical_bytes_invalid")
    if _sha256(raw) != index.source_reference_external_sha256:
        raise _fail("index_source_reference_sha_mismatch")
    return index, reference, raw


def publish_daily_market_monthly_revenue_reference_artifact_v3(
    root: Path,
    *,
    artifact_id: str,
    index_session: DailyMarketMonthlyRevenueYoyIndexSessionV2,
    protected_roots: Sequence[Path],
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3:
    """以兩個 create-only 檔保存完整 V3 source reference 與提交 descriptor。"""

    selected_root = _validate_artifact_root(root, protected_roots=protected_roots)
    selected_id = _artifact_id(artifact_id)
    index, reference, reference_raw = _verify_writer_inputs(index_session)
    _check_cancel(cancel_callback)
    values = _build_descriptor_values(
        artifact_id=selected_id,
        reference_raw=reference_raw,
        source_reference=reference,
        index=index,
    )
    descriptor = _descriptor_from_values(values, writer_issued=True)
    descriptor_raw = descriptor.to_bytes()
    reference_path = selected_root / descriptor.reference_relative_path
    descriptor_path = selected_root / descriptor.descriptor_relative_path
    if reference_path.exists() or descriptor_path.exists():
        raise _fail("artifact_create_only_collision")
    reference_signature: tuple[int, ...] | None = None
    descriptor_signature: tuple[int, ...] | None = None
    try:
        _check_cancel(cancel_callback)
        _check_path_components(selected_root, require_directory=True)
        reference_signature = _create_only_write(
            reference_path,
            reference_raw,
            label="source_reference",
            cancel_callback=cancel_callback,
        )
        _check_cancel(cancel_callback)
        _check_path_components(selected_root, require_directory=True)
        descriptor_signature = _create_only_write(
            descriptor_path,
            descriptor_raw,
            label="descriptor",
            cancel_callback=cancel_callback,
        )
        _check_cancel(cancel_callback)
        _check_path_components(selected_root, require_directory=True)
        readback_reference, checked_reference_signature = _read_verified_file(
            reference_path,
            label="published_source_reference",
            maximum=_MAX_REFERENCE_BYTES,
        )
        readback_descriptor, checked_descriptor_signature = _read_verified_file(
            descriptor_path,
            label="published_descriptor",
            maximum=_MAX_DESCRIPTOR_BYTES,
        )
        if (
            readback_reference != reference_raw
            or readback_descriptor != descriptor_raw
            or checked_reference_signature != reference_signature
            or checked_descriptor_signature != descriptor_signature
        ):
            raise _fail("artifact_publish_readback_mismatch")
        rechecked_index, rechecked_reference, rechecked_raw = _verify_writer_inputs(index_session)
        if (
            rechecked_index is not index
            or rechecked_reference != reference
            or rechecked_raw != reference_raw
        ):
            raise _fail("reader_issued_index_changed_during_publication")
        _check_cancel(cancel_callback)
        _check_path_components(selected_root, require_directory=True)
        return descriptor
    except BaseException:
        _cleanup_owned(descriptor_path, descriptor_signature)
        _cleanup_owned(reference_path, reference_signature)
        raise


def read_daily_market_monthly_revenue_reference_artifact_v3(
    root: Path,
    *,
    descriptor: DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3 | bytes,
    expected_descriptor_sha256: str,
    protected_roots: Sequence[Path],
) -> UnverifiedDailyMarketMonthlyRevenueReferenceArtifactV3:
    """依 caller 外部固定的 descriptor SHA 重讀，不由檔案自行授權。"""

    selected_root = _validate_artifact_root(root, protected_roots=protected_roots)
    expected_sha = _require_sha256(expected_descriptor_sha256, "external_descriptor")
    if type(descriptor) is DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3:
        if descriptor.is_writer_issued is not True:
            raise _fail("descriptor_typed_input_not_writer_issued")
        descriptor_raw = descriptor.to_bytes()
    elif type(descriptor) is bytes:
        descriptor_raw = descriptor
    else:
        raise _fail("descriptor_input_type_invalid")
    if len(descriptor_raw) > _MAX_DESCRIPTOR_BYTES or _sha256(descriptor_raw) != expected_sha:
        raise _fail("external_descriptor_sha_mismatch")
    parsed_descriptor = _descriptor_from_bytes(descriptor_raw)
    descriptor_path = selected_root / parsed_descriptor.descriptor_relative_path
    reference_path = selected_root / parsed_descriptor.reference_relative_path
    _check_path_components(selected_root, require_directory=True)
    disk_descriptor, disk_descriptor_signature = _read_verified_file(
        descriptor_path,
        label="descriptor",
        maximum=_MAX_DESCRIPTOR_BYTES,
    )
    if disk_descriptor != descriptor_raw or _sha256(disk_descriptor) != expected_sha:
        raise _fail("persisted_descriptor_does_not_match_external_anchor")
    _check_path_components(selected_root, require_directory=True)
    reference_raw, reference_signature = _read_verified_file(
        reference_path,
        label="source_reference",
        maximum=_MAX_REFERENCE_BYTES,
    )
    if (
        len(reference_raw) != parsed_descriptor.reference_size_bytes
        or _sha256(reference_raw) != parsed_descriptor.reference_sha256
    ):
        raise _fail("persisted_source_reference_size_or_sha_mismatch")
    try:
        unverified_reference = decode_daily_market_monthly_revenue_source_reference_v3(
            reference_raw,
            expected_reference_sha256=parsed_descriptor.reference_sha256,
        )
    except DailyMarketMonthlyRevenueCohortV2Error as exc:
        raise _fail("persisted_source_reference_v3_decode_failed") from exc
    reference = unverified_reference.reference
    if (
        reference.schema_version != DAILY_MARKET_MONTHLY_REVENUE_SOURCE_REFERENCE_V3_SCHEMA
        or reference.identity_sha256 != parsed_descriptor.source_reference_identity_sha256
        or unverified_reference.external_reference_sha256 != parsed_descriptor.reference_sha256
        or reference.declared_stock_codes != parsed_descriptor.declared_stock_codes
        or reference.declared_stock_codes_sha256 != parsed_descriptor.declared_stock_codes_sha256
        or reference.decision_cutoff != parsed_descriptor.decision_cutoff
        or reference.cohort_pin.cohort_sha256 != parsed_descriptor.cohort_sha256
        or reference.source_content_identity_sha256 != parsed_descriptor.source_content_identity_sha256
        or reference.finished_cohort_identity_sha256
        != parsed_descriptor.finished_cohort_identity_sha256
        or _ledger_hash(reference.result_identity_by_stock)
        != parsed_descriptor.result_ledger_sha256
        or _ledger_hash(reference.fact_identity_by_stock) != parsed_descriptor.fact_ledger_sha256
        or reference.reader_result_status_counts != parsed_descriptor.reader_result_status_counts
        or reference.fact_state_counts != parsed_descriptor.fact_state_counts
        or reference.source_scope != parsed_descriptor.source_scope
        or reference.availability_status != parsed_descriptor.availability_status
        or reference.historical_pit_eligible is not parsed_descriptor.historical_pit_eligible
        or reference.formal_pit_eligible is not parsed_descriptor.formal_pit_eligible
    ):
        raise _fail("descriptor_and_source_reference_binding_mismatch")
    if _check_file(descriptor_path, "descriptor") != disk_descriptor_signature:
        raise _fail("descriptor_changed_after_read")
    if _check_file(reference_path, "source_reference") != reference_signature:
        raise _fail("source_reference_changed_after_read")
    _check_path_components(selected_root, require_directory=True)
    return UnverifiedDailyMarketMonthlyRevenueReferenceArtifactV3(
        source_reference=unverified_reference,
        descriptor=parsed_descriptor,
        external_descriptor_sha256=expected_sha,
    )


__all__ = [
    "DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_DESCRIPTOR_V3_SCHEMA",
    "DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_V3_SCHEMA",
    "DailyMarketMonthlyRevenueReferenceArtifactV3Error",
    "DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3",
    "UnverifiedDailyMarketMonthlyRevenueReferenceArtifactV3",
    "publish_daily_market_monthly_revenue_reference_artifact_v3",
    "read_daily_market_monthly_revenue_reference_artifact_v3",
]
