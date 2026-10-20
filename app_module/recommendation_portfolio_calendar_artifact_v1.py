"""以單一不可覆寫檔案保存期間行事曆候選證據。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Sequence, cast

from app_module.recommendation_portfolio_calendar_evidence_v1 import (
    PortfolioPeriodCalendarEvidenceV1,
)


RECOMMENDATION_PORTFOLIO_CALENDAR_ARTIFACT_V1_SCHEMA = (
    "recommendation-portfolio-period-calendar-artifact.v1"
)
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
_ARTIFACT_FIELDS = frozenset({"schema_version", "evidence"})


class RecommendationPortfolioCalendarArtifactV1Error(ValueError):
    """候選行事曆 artifact 的路徑、內容或外部錨點無效。"""


def _fail(reason: str) -> RecommendationPortfolioCalendarArtifactV1Error:
    return RecommendationPortfolioCalendarArtifactV1Error(
        f"portfolio_calendar_artifact_v1_{reason}"
    )


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
        raise _fail("json_not_canonicalizable") from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _fail("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise _fail(f"nonfinite_json_number:{value}")


def _reject_float(value: str) -> object:
    raise _fail("json_float_not_allowed")


def _decode_object(raw: bytes, *, label: str, maximum: int) -> dict[str, object]:
    if type(raw) is not bytes or not raw or len(raw) > maximum:
        raise _fail(f"{label}_size_invalid")
    _validate_json_depth(raw)
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except RecommendationPortfolioCalendarArtifactV1Error:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise _fail(f"{label}_json_invalid") from exc
    if type(value) is not dict:
        raise _fail(f"{label}_object_required")
    return cast(dict[str, object], value)


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
            if depth > _MAX_JSON_DEPTH:
                raise _fail("json_depth_exceeded")
        elif byte in (0x7D, 0x5D):
            depth -= 1
            if depth < 0:
                raise _fail("json_structure_invalid")
    if in_string or depth != 0:
        raise _fail("json_structure_invalid")


def _is_reparse_or_link(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


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


def _canonical_path(value: object, label: str, *, allow_missing: bool) -> Path:
    if not isinstance(value, Path):
        raise _fail(f"{label}_path_required")
    path = cast(Path, value)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or "\x00" in str(path)
        or str(path).startswith(("\\\\?\\", "\\\\.\\", "//?/", "//./"))
        or path != Path(os.path.abspath(str(path)))
    ):
        raise _fail(f"{label}_must_be_canonical_absolute_path")

    current = Path(path.anchor)
    components = path.parts[1:]
    if not components:
        try:
            info = path.lstat()
        except OSError as exc:
            if allow_missing and isinstance(exc, FileNotFoundError):
                return path
            raise _fail(f"{label}_component_unavailable") from exc
        if _is_reparse_or_link(info):
            raise _fail(f"{label}_reparse_component_refused")
        return path
    missing_seen = False
    for index, component in enumerate(components):
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            if not allow_missing:
                raise _fail(f"{label}_component_missing")
            missing_seen = True
            continue
        except OSError as exc:
            raise _fail(f"{label}_component_unavailable") from exc
        if missing_seen:
            raise _fail(f"{label}_component_after_missing_exists")
        if _is_reparse_or_link(info):
            raise _fail(f"{label}_reparse_component_refused")
        if index < len(components) - 1 and not stat.S_ISDIR(info.st_mode):
            raise _fail(f"{label}_ancestor_not_directory")
    if not allow_missing and missing_seen:
        raise _fail(f"{label}_missing")
    return path


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


def _protected_roots(values: Sequence[Path]) -> tuple[Path, ...]:
    if type(values) not in (tuple, list) or not values or len(values) > 32:
        raise _fail("protected_roots_required_or_unbounded")
    roots: list[Path] = []
    for index, value in enumerate(values):
        root = _canonical_path(value, f"protected_root_{index}", allow_missing=True)
        roots.append(root)

    project_root = Path(__file__).resolve().parents[1]
    roots.append(_canonical_path(project_root / "output", "project_output_root", allow_missing=True))
    data_root_text = os.environ.get("DATA_ROOT", "F:/Min/Python/Project/FA_Data")
    try:
        data_root_path = Path(data_root_text)
        output_root_text = os.environ.get("OUTPUT_ROOT", str(data_root_path / "output"))
        output_root_path = Path(output_root_text)
    except (TypeError, ValueError) as exc:
        raise _fail("configured_data_or_output_root_invalid") from exc
    roots.append(_canonical_path(data_root_path, "configured_data_root", allow_missing=True))
    roots.append(_canonical_path(output_root_path, "configured_output_root", allow_missing=True))
    for key in ("PERSONAL_DATA_ROOT", "PERSONAL_STORE_ROOT"):
        configured_text = os.environ.get(key)
        if configured_text:
            try:
                configured = Path(configured_text)
            except (TypeError, ValueError) as exc:
                raise _fail(f"configured_{key.lower()}_invalid") from exc
            roots.append(_canonical_path(configured, f"configured_{key.lower()}", allow_missing=True))
    return tuple(roots)


def _validate_target(path: Path, protected_roots: Sequence[Path], *, reading: bool) -> Path:
    if not isinstance(path, Path):
        raise _fail("artifact_path_required")
    name = path.name
    device_name = name.split(".", 1)[0].upper()
    if (
        not name
        or name in {".", ".."}
        or any(ord(char) < 32 for char in name)
        or any(char in name for char in ("/", "\\", ":"))
        or name.endswith((".", " "))
        or device_name in {"CON", "PRN", "AUX", "NUL"}
        or re.fullmatch(r"(?:COM|LPT)[1-9]", device_name) is not None
    ):
        raise _fail("artifact_basename_invalid")
    target = _canonical_path(path, "artifact", allow_missing=not reading)
    parent = _canonical_path(target.parent, "artifact_parent", allow_missing=False)
    try:
        parent_info = parent.lstat()
    except OSError as exc:
        raise _fail("artifact_parent_unavailable") from exc
    if not stat.S_ISDIR(parent_info.st_mode):
        raise _fail("artifact_parent_not_directory")

    for root in _protected_roots(protected_roots):
        if _overlaps(target, root):
            raise _fail("artifact_overlaps_protected_or_formal_root")
    return target


def _file_signature(path: Path) -> tuple[int, ...]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise _fail("artifact_unavailable") from exc
    if _is_reparse_or_link(info):
        raise _fail("artifact_reparse_refused")
    if not stat.S_ISREG(info.st_mode):
        raise _fail("artifact_not_regular_file")
    if int(getattr(info, "st_nlink", 1)) != 1:
        raise _fail("artifact_hardlink_refused")
    return _stat_signature(info)


def _read_exact_file(
    path: Path, *, maximum: int = _MAX_ARTIFACT_BYTES,
) -> tuple[bytes, tuple[int, ...]]:
    if type(maximum) is not int or not 1 <= maximum <= _MAX_ARTIFACT_BYTES:
        raise _fail("artifact_read_limit_invalid")
    before = _file_signature(path)
    if before[3] > maximum:
        raise _fail("artifact_size_exceeded")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise _fail("artifact_open_failed") from exc
    total = 0
    chunks: list[bytes] = []
    after_handle: os.stat_result | None = None
    try:
        opened = os.fstat(descriptor)
        if _is_reparse_or_link(opened) or not stat.S_ISREG(opened.st_mode):
            raise _fail("artifact_opened_file_invalid")
        if int(getattr(opened, "st_nlink", 1)) != 1 or _stat_signature(opened) != before:
            raise _fail("artifact_changed_before_read")
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise _fail("artifact_size_exceeded")
        after_handle = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after_path = _file_signature(path)
    if (
        after_handle is None
        or _stat_signature(after_handle) != before
        or after_path != before
        or total != before[3]
    ):
        raise _fail("artifact_changed_during_read")
    return b"".join(chunks), before


def _evidence_json_object(evidence: PortfolioPeriodCalendarEvidenceV1) -> dict[str, object]:
    if type(evidence) is not PortfolioPeriodCalendarEvidenceV1:
        raise _fail("typed_evidence_required")
    try:
        raw = evidence.to_json().encode("utf-8", errors="strict")
    except (AttributeError, UnicodeError, ValueError) as exc:
        raise _fail("evidence_serialization_failed") from exc
    payload = _decode_object(raw, label="evidence", maximum=_MAX_ARTIFACT_BYTES)
    if _canonical_json_bytes(payload) != raw:
        raise _fail("evidence_json_not_canonical")
    try:
        restored = PortfolioPeriodCalendarEvidenceV1.from_json(raw.decode("utf-8", errors="strict"))
        restored_raw = restored.to_json().encode("utf-8", errors="strict")
    except (AttributeError, UnicodeError, ValueError, TypeError) as exc:
        raise _fail("evidence_codec_rejected") from exc
    if type(restored) is not PortfolioPeriodCalendarEvidenceV1 or restored_raw != raw:
        raise _fail("evidence_codec_roundtrip_mismatch")
    return payload


def write_portfolio_period_calendar_evidence_create_only_v1(
    path: Path,
    evidence: PortfolioPeriodCalendarEvidenceV1,
    *,
    protected_roots: Sequence[Path],
) -> str:
    """將一份完整行事曆 evidence 以單檔 create-only JSON 寫入既有隔離資料夾。"""

    target = _validate_target(path, protected_roots, reading=False)
    evidence_payload = _evidence_json_object(evidence)
    raw = _canonical_json_bytes(
        {"schema_version": RECOMMENDATION_PORTFOLIO_CALENDAR_ARTIFACT_V1_SCHEMA, "evidence": evidence_payload}
    )
    return write_calendar_version_bytes_create_only_v1(
        target, raw, protected_roots=protected_roots,
    )


def write_calendar_version_bytes_create_only_v1(
    path: Path, raw: bytes, *, protected_roots: Sequence[Path],
) -> str:
    """共用既有日曆版本檔案守衛；bytes 本身不構成日曆或用途資格。"""
    target = _validate_target(path, protected_roots, reading=False)
    if type(raw) is not bytes or not raw or len(raw) > _MAX_ARTIFACT_BYTES:
        raise _fail("artifact_size_exceeded")
    if target.exists():
        raise _fail("artifact_create_only_collision")
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as exc:
        raise _fail("artifact_create_only_collision") from exc
    except OSError as exc:
        raise _fail("artifact_create_failed") from exc

    after_handle: os.stat_result | None = None
    try:
        opened = os.fstat(descriptor)
        if _is_reparse_or_link(opened) or not stat.S_ISREG(opened.st_mode):
            raise _fail("artifact_created_file_invalid")
        if int(getattr(opened, "st_nlink", 1)) != 1:
            raise _fail("artifact_created_file_hardlinked")
        offset = 0
        while offset < len(raw):
            count = os.write(descriptor, raw[offset : offset + 1024 * 1024])
            if count <= 0:
                raise _fail("artifact_short_write")
            offset += count
        os.fsync(descriptor)
        after_handle = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    after_path = _file_signature(target)
    if (
        after_handle is None
        or _stat_signature(after_handle) != after_path
        or after_path[3] != len(raw)
    ):
        raise _fail("artifact_changed_after_write")
    readback, readback_signature = _read_exact_file(target)
    if readback != raw or _sha256(readback) != _sha256(raw):
        raise _fail("artifact_write_readback_mismatch")
    _validate_target(target, protected_roots, reading=True)
    if _file_signature(target) != readback_signature:
        raise _fail("artifact_changed_after_write_readback")
    return _sha256(readback)


def read_calendar_version_bytes_exact_v1(
    path: Path, *, expected_sha256: str, protected_roots: Sequence[Path],
    max_bytes: int = _MAX_ARTIFACT_BYTES,
) -> bytes:
    """共用有界、單link、無reparse及外部SHA核對，不解讀或升格版本內容。"""
    if type(expected_sha256) is not str or _SHA256_RE.fullmatch(expected_sha256) is None:
        raise _fail("expected_sha256_invalid")
    target = _validate_target(path, protected_roots, reading=True)
    raw, signature = (
        _read_exact_file(target) if max_bytes == _MAX_ARTIFACT_BYTES and type(max_bytes) is int
        else _read_exact_file(target, maximum=max_bytes)
    )
    if _sha256(raw) != expected_sha256:
        raise _fail("external_sha256_mismatch")
    _validate_target(target, protected_roots, reading=True)
    if _file_signature(target) != signature:
        raise _fail("artifact_changed_after_read")
    return raw


def read_portfolio_period_calendar_evidence_v1(
    path: Path,
    *,
    expected_sha256: str,
    protected_roots: Sequence[Path],
) -> PortfolioPeriodCalendarEvidenceV1:
    """以呼叫端外部 SHA 錨點讀回並重建候選行事曆 evidence。"""

    if type(expected_sha256) is not str or _SHA256_RE.fullmatch(expected_sha256) is None:
        raise _fail("expected_sha256_invalid")
    target = _validate_target(path, protected_roots, reading=True)
    raw, signature = _read_exact_file(target)
    if _sha256(raw) != expected_sha256:
        raise _fail("external_sha256_mismatch")
    payload = _decode_object(raw, label="artifact", maximum=_MAX_ARTIFACT_BYTES)
    if set(payload) != _ARTIFACT_FIELDS:
        raise _fail("artifact_fields_invalid")
    if payload.get("schema_version") != RECOMMENDATION_PORTFOLIO_CALENDAR_ARTIFACT_V1_SCHEMA:
        raise _fail("artifact_schema_invalid")
    if _canonical_json_bytes(payload) != raw:
        raise _fail("artifact_json_not_canonical")
    evidence_value = payload.get("evidence")
    if type(evidence_value) is not dict:
        raise _fail("artifact_evidence_object_required")
    evidence_payload = cast(dict[str, object], evidence_value)
    evidence_raw = _canonical_json_bytes(evidence_payload)
    try:
        evidence = PortfolioPeriodCalendarEvidenceV1.from_json(
            evidence_raw.decode("utf-8", errors="strict")
        )
        roundtrip = evidence.to_json().encode("utf-8", errors="strict")
    except (AttributeError, UnicodeError, ValueError, TypeError) as exc:
        raise _fail("evidence_codec_rejected") from exc
    if type(evidence) is not PortfolioPeriodCalendarEvidenceV1 or roundtrip != evidence_raw:
        raise _fail("evidence_codec_roundtrip_mismatch")
    _validate_target(target, protected_roots, reading=True)
    if _file_signature(target) != signature:
        raise _fail("artifact_changed_after_decode")
    return evidence


__all__ = [
    "write_calendar_version_bytes_create_only_v1",
    "read_calendar_version_bytes_exact_v1",
    "RECOMMENDATION_PORTFOLIO_CALENDAR_ARTIFACT_V1_SCHEMA",
    "RecommendationPortfolioCalendarArtifactV1Error",
    "read_portfolio_period_calendar_evidence_v1",
    "write_portfolio_period_calendar_evidence_create_only_v1",
]
