"""由固定 CMS 名錄原件產生現況市場歸屬註記。

本模組只讀取已保存的 CMS snapshot、manifest 與三份名錄 raw bytes；不呼叫
更新器、不讀取 latest 以外的推測路徑，也不把名錄缺列解讀為終止或安全證書。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import NoReturn
from zoneinfo import ZoneInfo

from data_module.current_market_status_observation import (
    CurrentMarketStatusError,
    decode_official_rows,
    explicit_payload_source_dates,
    explicit_source_dates,
    extract_symbol,
    extract_termination_date,
    parse_source_date,
    parse_official_market_notice,
    sha256_bytes,
    source_dates_for_aliases,
)


CURRENT_MARKET_ASSIGNMENT_PIN_SCHEMA_V1 = "current-market-assignment-source-pin.v1"
CURRENT_MARKET_ASSIGNMENT_CAPTURE_SCHEMA_V1 = "current-market-assignment-capture.v1"
CURRENT_MARKET_ASSIGNMENT_OBSERVATION_SCHEMA_V1 = "current-market-assignment-observation.v1"
CURRENT_MARKET_ASSIGNMENT_PARSER_VERSION = "cms-roster-membership.v1"
CURRENT_MARKET_STATUS_POINTER_SCHEMA_V1 = "current-market-status-pointer.v1"
CURRENT_MARKET_STATUS_MANIFEST_SCHEMA_V1 = "current-market-status-capture-manifest.v1"
CURRENT_MARKET_STATUS_SNAPSHOT_SCHEMA_V1 = "current-market-status-observation.v1"
CURRENT_ONLY_SCOPE = "current_only"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SYMBOL_RE = re.compile(r"^[0-9]{4,6}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CODE_FIELDS = {
    "twse.current_roster": "公司代號",
    "tpex.current_otc_roster": "SecuritiesCompanyCode",
    "tpex.current_emerging_roster": "SecuritiesCompanyCode",
}
_ROSTER_MARKETS = {
    "twse.current_roster": "twse",
    "tpex.current_otc_roster": "tpex",
    "tpex.current_emerging_roster": "emerging",
}
_ROSTER_URLS = {
    "twse.current_roster": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
    "tpex.current_otc_roster": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
    "tpex.current_emerging_roster": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R",
}
_ROSTER_DATE_ALIASES = {
    "twse.current_roster": (),
    "tpex.current_otc_roster": ("Date",),
    "tpex.current_emerging_roster": ("Date",),
}
_MAX_POINTER_BYTES = 64 * 1024
_MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_MAX_ROSTER_RAW_BYTES = 32 * 1024 * 1024
_MAX_OTHER_RAW_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_ROSTER_RAW_BYTES = 96 * 1024 * 1024
_MAX_TOTAL_AUX_RAW_BYTES = 64 * 1024 * 1024
_MAX_CAPTURE_COUNT = 256


class CurrentMarketAssignmentError(ValueError):
    """CMS 市場名錄來源或保存 pin 不符合封閉契約。"""


def _fail(code: str) -> NoReturn:
    raise CurrentMarketAssignmentError(code)


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _identity_sha256(payload: object) -> str:
    return sha256_bytes(_canonical_json(payload).encode("utf-8"))


def _aware_utc(value: object, code: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        _fail(code)
    return value.astimezone(timezone.utc)


def _parse_aware_datetime(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CurrentMarketAssignmentError(code) from error
    return _aware_utc(parsed, code)


def _datetime_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _read_now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _validate_cutoff(cutoff_at: datetime | None) -> datetime:
    """單次取得讀取時鐘，固定本次入口的來源時間上界。"""
    now = _read_now_utc()
    if cutoff_at is None:
        return now
    cutoff = _aware_utc(cutoff_at, "market_assignment_cutoff_must_be_aware")
    if cutoff > now:
        _fail("market_assignment_cutoff_in_future")
    return cutoff


def _is_reparse_point(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _check_no_reparse_path(path: Path) -> None:
    """逐層檢查路徑，先於 resolve，以免解析後遺失連結證據。"""
    if not path.is_absolute():
        _fail("market_assignment_path_must_be_absolute")
    anchor = Path(path.anchor)
    cursor = anchor
    if cursor.exists():
        metadata = cursor.lstat()
        if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
            _fail("market_assignment_path_reparse_forbidden")
    for part in path.parts[1:]:
        cursor = cursor / part
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            # 尚不存在的尾段由呼叫端檢查；已存在的祖先仍須無 reparse。
            continue
        if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
            _fail("market_assignment_path_reparse_forbidden")


def _canonical_existing_directory(path: Path) -> Path:
    _check_no_reparse_path(path)
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as error:
        raise CurrentMarketAssignmentError("market_assignment_directory_missing") from error
    if not stat.S_ISDIR(metadata.st_mode) or _is_reparse_point(metadata):
        _fail("market_assignment_directory_invalid")
    return resolved


def _file_signature(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_size),
        int(getattr(metadata, "st_mtime_ns", int(metadata.st_mtime * 1_000_000_000))),
        int(metadata.st_nlink),
    )


def _read_bounded_file(path: Path, *, max_bytes: int, code: str) -> bytes:
    _check_no_reparse_path(path)
    try:
        before = path.lstat()
    except OSError as error:
        raise CurrentMarketAssignmentError(f"{code}_missing") from error
    if (
        not stat.S_ISREG(before.st_mode)
        or _is_reparse_point(before)
        or before.st_nlink != 1
        or before.st_size < 0
        or before.st_size > max_bytes
    ):
        _fail(f"{code}_file_invalid_or_oversized")
    try:
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or _file_signature(opened) != _file_signature(before)
                or _is_reparse_point(opened)
            ):
                _fail(f"{code}_file_changed_before_read")
            raw = stream.read(max_bytes + 1)
            after_open = os.fstat(stream.fileno())
        after_path = path.lstat()
    except CurrentMarketAssignmentError:
        raise
    except OSError as error:
        raise CurrentMarketAssignmentError(f"{code}_read_failed") from error
    if (
        len(raw) > max_bytes
        or _file_signature(before) != _file_signature(after_open)
        or _file_signature(before) != _file_signature(after_path)
        or not stat.S_ISREG(after_path.st_mode)
        or _is_reparse_point(after_path)
        or after_path.st_nlink != 1
    ):
        _fail(f"{code}_file_changed_during_read")
    return raw


def _validate_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        _fail(code)
    return value


def _validate_relative_path(value: object, code: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or "\\" in value
        or ":" in value
        or "\x00" in value
    ):
        _fail(code)
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail(code)
    if path.as_posix() != value:
        _fail(code)
    return value


def _resolve_relative(root: Path, relpath: str, code: str) -> Path:
    _validate_relative_path(relpath, code)
    target = root.joinpath(*PurePosixPath(relpath).parts)
    _check_no_reparse_path(target)
    try:
        resolved = target.resolve(strict=True)
    except OSError as error:
        raise CurrentMarketAssignmentError(f"{code}_missing") from error
    if not resolved.is_relative_to(root):
        _fail(f"{code}_outside_root")
    return resolved


def _relative_posix(target: Path, root: Path, code: str) -> str:
    _check_no_reparse_path(target)
    if any(part in {".", ".."} for part in target.parts):
        _fail(f"{code}_path_component_invalid")
    lexical_target = target.resolve(strict=False)
    if not lexical_target.is_relative_to(root):
        _fail(f"{code}_outside_root")
    try:
        resolved = target.resolve(strict=True)
    except OSError as error:
        raise CurrentMarketAssignmentError(f"{code}_missing") from error
    if not resolved.is_relative_to(root):
        _fail(f"{code}_outside_root")
    relative = resolved.relative_to(root).as_posix()
    return _validate_relative_path(relative, code)


def _json_object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _decode_json(raw: bytes, code: str) -> object:
    try:
        return json.loads(raw.decode("utf-8-sig", errors="strict"), object_pairs_hook=_json_object_without_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise CurrentMarketAssignmentError(code) from error


def _mapping(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        _fail(code)
    return value


def _string(value: object, code: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        _fail(code)
    return value


def _strict_bool(value: object, code: str) -> bool:
    if not isinstance(value, bool):
        _fail(code)
    return value


def _normalise_symbol(value: object) -> str:
    if not isinstance(value, str):
        _fail("market_assignment_symbol_must_be_text")
    normalized = value.strip()
    if not SYMBOL_RE.fullmatch(normalized):
        _fail("market_assignment_symbol_invalid")
    return normalized


@dataclass(frozen=True)
class MarketRosterCaptureReferenceV1:
    """一份固定 CMS 名錄 capture 的有界來源參照。"""

    source_id: str
    market: str
    status: str
    parse_status: str
    requested_url: str | None
    final_url: str | None
    raw_relative_path: str | None
    raw_sha256: str | None
    raw_bytes: int | None
    captured_at: str | None
    source_data_dates: tuple[str, ...]
    row_count: int | None
    row_schema_sha256: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": CURRENT_MARKET_ASSIGNMENT_CAPTURE_SCHEMA_V1,
            "source_id": self.source_id,
            "market": self.market,
            "status": self.status,
            "parse_status": self.parse_status,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "raw_relative_path": self.raw_relative_path,
            "raw_sha256": self.raw_sha256,
            "raw_bytes": self.raw_bytes,
            "captured_at": self.captured_at,
            "source_data_dates": list(self.source_data_dates),
            "row_count": self.row_count,
            "row_schema_sha256": self.row_schema_sha256,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "MarketRosterCaptureReferenceV1":
        value = _mapping(payload, "market_assignment_capture_invalid")
        expected = {
            "schema_version", "source_id", "market", "status", "parse_status",
            "requested_url", "final_url", "raw_relative_path", "raw_sha256",
            "raw_bytes", "captured_at", "source_data_dates", "row_count",
            "row_schema_sha256",
        }
        if set(value) != expected or value.get("schema_version") != CURRENT_MARKET_ASSIGNMENT_CAPTURE_SCHEMA_V1:
            _fail("market_assignment_capture_schema_invalid")
        source_id = _string(value.get("source_id"), "market_assignment_capture_source_invalid", maximum=128)
        if source_id not in _ROSTER_MARKETS or value.get("market") != _ROSTER_MARKETS[source_id]:
            _fail("market_assignment_capture_source_invalid")
        status = _string(value.get("status"), "market_assignment_capture_status_invalid", maximum=64)
        parse_status = _string(value.get("parse_status"), "market_assignment_capture_parse_status_invalid", maximum=64)
        if status not in {"captured", "http_error", "capture_error", "missing"}:
            _fail("market_assignment_capture_status_invalid")
        if parse_status not in {"parsed", "unrecognized_schema", "not_attempted_http_error", "missing"}:
            _fail("market_assignment_capture_parse_status_invalid")
        requested_url = value.get("requested_url")
        final_url = value.get("final_url")
        for item, code in ((requested_url, "market_assignment_capture_url_invalid"), (final_url, "market_assignment_capture_url_invalid")):
            if item is not None and (not isinstance(item, str) or len(item) > 2048):
                _fail(code)
        raw_path = value.get("raw_relative_path")
        if raw_path is not None:
            raw_path = _validate_relative_path(raw_path, "market_assignment_capture_raw_path_invalid")
        raw_sha = value.get("raw_sha256")
        if raw_sha is not None:
            raw_sha = _validate_sha(raw_sha, "market_assignment_capture_raw_hash_invalid")
        raw_bytes = value.get("raw_bytes")
        if raw_bytes is not None and (isinstance(raw_bytes, bool) or not isinstance(raw_bytes, int) or raw_bytes < 0 or raw_bytes > _MAX_ROSTER_RAW_BYTES):
            _fail("market_assignment_capture_raw_size_invalid")
        captured_at = value.get("captured_at")
        if captured_at is not None:
            captured_at = _datetime_text(_parse_aware_datetime(captured_at, "market_assignment_capture_time_invalid"))
        dates_value = value.get("source_data_dates")
        if not isinstance(dates_value, list) or len(dates_value) > 256:
            _fail("market_assignment_capture_dates_invalid")
        dates: list[str] = []
        for item in dates_value:
            parsed = parse_source_date(item)
            if parsed is None or parsed.isoformat() != item:
                _fail("market_assignment_capture_dates_invalid")
            dates.append(parsed.isoformat())
        if dates != sorted(set(dates)):
            _fail("market_assignment_capture_dates_invalid")
        row_count = value.get("row_count")
        if row_count is not None and (isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 0 or row_count > 1_000_000):
            _fail("market_assignment_capture_row_count_invalid")
        schema_sha = value.get("row_schema_sha256")
        if schema_sha is not None:
            schema_sha = _validate_sha(schema_sha, "market_assignment_capture_schema_hash_invalid")
        if status == "captured" and (raw_path is None or raw_sha is None or raw_bytes is None or captured_at is None):
            _fail("market_assignment_capture_reference_incomplete")
        if parse_status == "parsed" and row_count is None:
            _fail("market_assignment_capture_row_count_missing")
        if parse_status == "parsed" and row_count and schema_sha is None:
            _fail("market_assignment_capture_schema_hash_missing")
        return cls(
            source_id=source_id,
            market=_ROSTER_MARKETS[source_id],
            status=status,
            parse_status=parse_status,
            requested_url=requested_url if isinstance(requested_url, str) else None,
            final_url=final_url if isinstance(final_url, str) else None,
            raw_relative_path=raw_path if isinstance(raw_path, str) else None,
            raw_sha256=raw_sha if isinstance(raw_sha, str) else None,
            raw_bytes=raw_bytes if isinstance(raw_bytes, int) else None,
            captured_at=captured_at if isinstance(captured_at, str) else None,
            source_data_dates=tuple(dates),
            row_count=row_count if isinstance(row_count, int) else None,
            row_schema_sha256=schema_sha if isinstance(schema_sha, str) else None,
        )


@dataclass(frozen=True)
class CurrentMarketAssignmentSourcePinV1:
    """固定單次 CMS snapshot、manifest 及三份名錄原件的 identity。"""

    output_root: str
    run_id: str
    pointer_sha256: str
    pointer_published_at: str
    snapshot_relative_path: str
    snapshot_sha256: str
    snapshot_observed_at: str
    manifest_relative_path: str
    manifest_sha256: str
    snapshot_partial_failure: bool
    cutoff_at: str
    captures: tuple[MarketRosterCaptureReferenceV1, ...]
    identity_sha256: str

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": CURRENT_MARKET_ASSIGNMENT_PIN_SCHEMA_V1,
            "parser_version": CURRENT_MARKET_ASSIGNMENT_PARSER_VERSION,
            "output_root": self.output_root,
            "run_id": self.run_id,
            "pointer_sha256": self.pointer_sha256,
            "pointer_published_at": self.pointer_published_at,
            "snapshot_relative_path": self.snapshot_relative_path,
            "snapshot_sha256": self.snapshot_sha256,
            "snapshot_observed_at": self.snapshot_observed_at,
            "manifest_relative_path": self.manifest_relative_path,
            "manifest_sha256": self.manifest_sha256,
            "snapshot_partial_failure": self.snapshot_partial_failure,
            "cutoff_at": self.cutoff_at,
            "captures": [capture.to_dict() for capture in self.captures],
            "scope": CURRENT_ONLY_SCOPE,
            "historical_pit_eligible": False,
            "official_available_at": None,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._identity_payload(), "identity_sha256": self.identity_sha256}

    @property
    def identity_payload_json(self) -> str:
        return _canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> "CurrentMarketAssignmentSourcePinV1":
        value = _mapping(payload, "market_assignment_pin_invalid")
        expected = {
            "schema_version", "parser_version", "output_root", "run_id",
            "pointer_sha256", "pointer_published_at", "snapshot_relative_path",
            "snapshot_sha256", "snapshot_observed_at", "manifest_relative_path",
            "manifest_sha256", "snapshot_partial_failure", "cutoff_at", "captures",
            "scope", "historical_pit_eligible", "official_available_at", "identity_sha256",
        }
        if set(value) != expected or value.get("schema_version") != CURRENT_MARKET_ASSIGNMENT_PIN_SCHEMA_V1:
            _fail("market_assignment_pin_schema_invalid")
        if value.get("parser_version") != CURRENT_MARKET_ASSIGNMENT_PARSER_VERSION:
            _fail("market_assignment_pin_version_unsupported")
        if value.get("scope") != CURRENT_ONLY_SCOPE or value.get("historical_pit_eligible") is not False or value.get("official_available_at") is not None:
            _fail("market_assignment_pin_scope_invalid")
        output_root = _string(value.get("output_root"), "market_assignment_pin_root_invalid", maximum=4096)
        if not Path(output_root).is_absolute():
            _fail("market_assignment_pin_root_invalid")
        run_id = _string(value.get("run_id"), "market_assignment_pin_run_id_invalid", maximum=128)
        if not RUN_ID_RE.fullmatch(run_id):
            _fail("market_assignment_pin_run_id_invalid")
        pointer_sha = _validate_sha(value.get("pointer_sha256"), "market_assignment_pin_pointer_hash_invalid")
        snapshot_sha = _validate_sha(value.get("snapshot_sha256"), "market_assignment_pin_snapshot_hash_invalid")
        manifest_sha = _validate_sha(value.get("manifest_sha256"), "market_assignment_pin_manifest_hash_invalid")
        pointer_time = _datetime_text(_parse_aware_datetime(value.get("pointer_published_at"), "market_assignment_pin_pointer_time_invalid"))
        snapshot_time = _datetime_text(_parse_aware_datetime(value.get("snapshot_observed_at"), "market_assignment_pin_snapshot_time_invalid"))
        cutoff = _datetime_text(_parse_aware_datetime(value.get("cutoff_at"), "market_assignment_pin_cutoff_invalid"))
        snapshot_path = _validate_relative_path(value.get("snapshot_relative_path"), "market_assignment_pin_snapshot_path_invalid")
        manifest_path = _validate_relative_path(value.get("manifest_relative_path"), "market_assignment_pin_manifest_path_invalid")
        if snapshot_path != f"cms_{run_id}/snapshot.json" or manifest_path != f"cms_{run_id}/manifest.json":
            _fail("market_assignment_pin_run_paths_invalid")
        partial_failure = _strict_bool(value.get("snapshot_partial_failure"), "market_assignment_pin_partial_failure_invalid")
        raw_captures = value.get("captures")
        if not isinstance(raw_captures, list) or len(raw_captures) != len(_ROSTER_MARKETS):
            _fail("market_assignment_pin_captures_invalid")
        captures = tuple(MarketRosterCaptureReferenceV1.from_dict(item) for item in raw_captures)
        if tuple(capture.source_id for capture in captures) != tuple(_ROSTER_MARKETS):
            _fail("market_assignment_pin_capture_order_invalid")
        instance = cls(
            output_root=output_root,
            run_id=run_id,
            pointer_sha256=pointer_sha,
            pointer_published_at=pointer_time,
            snapshot_relative_path=snapshot_path,
            snapshot_sha256=snapshot_sha,
            snapshot_observed_at=snapshot_time,
            manifest_relative_path=manifest_path,
            manifest_sha256=manifest_sha,
            snapshot_partial_failure=partial_failure,
            cutoff_at=cutoff,
            captures=captures,
            identity_sha256=_validate_sha(value.get("identity_sha256"), "market_assignment_pin_identity_invalid"),
        )
        if _identity_sha256(instance._identity_payload()) != instance.identity_sha256:
            _fail("market_assignment_pin_identity_mismatch")
        if _parse_aware_datetime(pointer_time, "market_assignment_pin_pointer_time_invalid") > _parse_aware_datetime(cutoff, "market_assignment_pin_cutoff_invalid"):
            _fail("market_assignment_pin_pointer_after_cutoff")
        if _parse_aware_datetime(snapshot_time, "market_assignment_pin_snapshot_time_invalid") > _parse_aware_datetime(cutoff, "market_assignment_pin_cutoff_invalid"):
            _fail("market_assignment_pin_snapshot_after_cutoff")
        return instance


@dataclass(frozen=True)
class MarketAssignmentObservationV1:
    """單一代碼的現況名錄註記；不表示終止狀態已完整驗證。"""

    schema_version: str
    symbol: str
    state: str
    market: str | None
    reason_code: str
    roster_source_ids: tuple[str, ...]
    roster_sha256s: tuple[str, ...]
    source_data_dates: tuple[tuple[str, tuple[str, ...]], ...]
    snapshot_observed_at: str
    pointer_published_at: str
    cutoff_at: str
    termination_evidence: str
    source_pin_identity_sha256: str
    scope: str = CURRENT_ONLY_SCOPE
    historical_pit_eligible: bool = False
    official_available_at: None = None


class CurrentMarketAssignmentReader:
    """依 exact CMS pointer 或保存 pin 建立只讀市場名錄查詢器。"""

    def __init__(
        self,
        source_pin: CurrentMarketAssignmentSourcePinV1,
        *,
        memberships: Mapping[str, frozenset[str]],
        duplicates: Mapping[str, frozenset[str]],
        ready: bool,
        incomplete_sources: tuple[str, ...],
        empty_sources: tuple[str, ...],
        termination_symbols: frozenset[str],
        future_termination_symbols: frozenset[str],
    ) -> None:
        self.source_pin = source_pin
        self._memberships = dict(memberships)
        self._duplicates = dict(duplicates)
        self._ready = ready
        self._incomplete_sources = incomplete_sources
        self._empty_sources = empty_sources
        self._termination_symbols = termination_symbols
        self._future_termination_symbols = future_termination_symbols

    @classmethod
    def from_pointer(
        cls,
        pointer_path: str | Path,
        *,
        cutoff_at: datetime | None = None,
    ) -> "CurrentMarketAssignmentReader":
        cutoff = _validate_cutoff(cutoff_at)
        path = Path(pointer_path).expanduser()
        if not path.is_absolute() or path.name != "current_market_status_pointer.json":
            _fail("market_assignment_pointer_path_invalid")
        _check_no_reparse_path(path)
        root = _canonical_existing_directory(path.parent)
        pointer_path_resolved = _resolve_relative(root, path.name, "market_assignment_pointer")
        pointer_raw = _read_bounded_file(pointer_path_resolved, max_bytes=_MAX_POINTER_BYTES, code="market_assignment_pointer")
        pointer = _mapping(_decode_json(pointer_raw, "market_assignment_pointer_json_invalid"), "market_assignment_pointer_invalid")
        pointer_fields = {
            "schema_version", "scope", "pit_eligible", "run_id", "published_at",
            "snapshot_path", "snapshot_sha256", "manifest_path", "manifest_sha256",
            "source_count", "successful_source_count", "partial_failure",
        }
        if set(pointer) != pointer_fields or pointer.get("schema_version") != CURRENT_MARKET_STATUS_POINTER_SCHEMA_V1:
            _fail("market_assignment_pointer_schema_invalid")
        if pointer.get("scope") != CURRENT_ONLY_SCOPE or pointer.get("pit_eligible") is not False:
            _fail("market_assignment_pointer_scope_invalid")
        run_id = _string(pointer.get("run_id"), "market_assignment_run_id_invalid", maximum=128)
        if not RUN_ID_RE.fullmatch(run_id):
            _fail("market_assignment_run_id_invalid")
        pointer_time = _datetime_text(_parse_aware_datetime(pointer.get("published_at"), "market_assignment_pointer_time_invalid"))
        if _parse_aware_datetime(pointer_time, "market_assignment_pointer_time_invalid") > cutoff:
            _fail("market_assignment_pointer_after_cutoff")
        snapshot_rel = _validate_relative_path(pointer.get("snapshot_path"), "market_assignment_snapshot_path_invalid")
        manifest_rel = _validate_relative_path(pointer.get("manifest_path"), "market_assignment_manifest_path_invalid")
        if snapshot_rel != f"cms_{run_id}/snapshot.json" or manifest_rel != f"cms_{run_id}/manifest.json":
            _fail("market_assignment_pointer_run_paths_invalid")
        snapshot_sha = _validate_sha(pointer.get("snapshot_sha256"), "market_assignment_snapshot_hash_invalid")
        manifest_sha = _validate_sha(pointer.get("manifest_sha256"), "market_assignment_manifest_hash_invalid")
        source_count_value = pointer.get("source_count")
        if isinstance(source_count_value, bool) or not isinstance(source_count_value, int) or source_count_value < 0:
            _fail("market_assignment_pointer_source_count_invalid")
        successful_source_count_value = pointer.get("successful_source_count")
        if isinstance(successful_source_count_value, bool) or not isinstance(successful_source_count_value, int) or successful_source_count_value < 0:
            _fail("market_assignment_pointer_success_count_invalid")
        if successful_source_count_value > source_count_value:
            _fail("market_assignment_pointer_success_count_invalid")
        partial = _strict_bool(pointer.get("partial_failure"), "market_assignment_pointer_partial_failure_invalid")
        pointer_sha = sha256_bytes(pointer_raw)
        return cls._load_exact_payload(
            output_root=root,
            run_id=run_id,
            pointer_sha256=pointer_sha,
            pointer_published_at=pointer_time,
            snapshot_relative_path=snapshot_rel,
            snapshot_sha256=snapshot_sha,
            manifest_relative_path=manifest_rel,
            manifest_sha256=manifest_sha,
            snapshot_partial_failure=partial,
            cutoff_at=cutoff,
            expected_source_count=source_count_value,
            expected_successful_source_count=successful_source_count_value,
        )

    @classmethod
    def from_exact(
        cls,
        source_pin: CurrentMarketAssignmentSourcePinV1 | Mapping[str, object],
        *,
        cutoff_at: datetime | None = None,
    ) -> "CurrentMarketAssignmentReader":
        pin_payload: object = source_pin.to_dict() if isinstance(source_pin, CurrentMarketAssignmentSourcePinV1) else source_pin
        pin = CurrentMarketAssignmentSourcePinV1.from_dict(pin_payload)
        # 固定 pin 的截止時點屬於來源 identity；重開時不得改寫該時點。
        now = _read_now_utc()
        pinned_cutoff = _parse_aware_datetime(pin.cutoff_at, "market_assignment_pin_cutoff_invalid")
        if pinned_cutoff > now:
            _fail("market_assignment_cutoff_in_future")
        if cutoff_at is not None:
            requested_cutoff = _aware_utc(cutoff_at, "market_assignment_cutoff_must_be_aware")
            if requested_cutoff > now:
                _fail("market_assignment_cutoff_in_future")
            if requested_cutoff != pinned_cutoff:
                _fail("market_assignment_exact_cutoff_mismatch")
        root = _canonical_existing_directory(Path(pin.output_root))
        canonical_root = str(root)
        if canonical_root != pin.output_root:
            _fail("market_assignment_pin_root_not_canonical")
        return cls._load_exact_payload(
            output_root=root,
            run_id=pin.run_id,
            pointer_sha256=pin.pointer_sha256,
            pointer_published_at=pin.pointer_published_at,
            snapshot_relative_path=pin.snapshot_relative_path,
            snapshot_sha256=pin.snapshot_sha256,
            manifest_relative_path=pin.manifest_relative_path,
            manifest_sha256=pin.manifest_sha256,
            snapshot_partial_failure=pin.snapshot_partial_failure,
            cutoff_at=pinned_cutoff,
            expected_pin=pin,
            expected_source_count=None,
            expected_successful_source_count=None,
        )

    @classmethod
    def _load_exact_payload(
        cls,
        *,
        output_root: Path,
        run_id: str,
        pointer_sha256: str,
        pointer_published_at: str,
        snapshot_relative_path: str,
        snapshot_sha256: str,
        manifest_relative_path: str,
        manifest_sha256: str,
        snapshot_partial_failure: bool,
        cutoff_at: datetime,
        expected_pin: CurrentMarketAssignmentSourcePinV1 | None = None,
        expected_source_count: int | None,
        expected_successful_source_count: int | None,
    ) -> "CurrentMarketAssignmentReader":
        snapshot_path = _resolve_relative(output_root, snapshot_relative_path, "market_assignment_snapshot")
        manifest_path = _resolve_relative(output_root, manifest_relative_path, "market_assignment_manifest")
        snapshot_raw = _read_bounded_file(snapshot_path, max_bytes=_MAX_SNAPSHOT_BYTES, code="market_assignment_snapshot")
        manifest_raw = _read_bounded_file(manifest_path, max_bytes=_MAX_MANIFEST_BYTES, code="market_assignment_manifest")
        if sha256_bytes(snapshot_raw) != snapshot_sha256:
            _fail("market_assignment_snapshot_hash_mismatch")
        if sha256_bytes(manifest_raw) != manifest_sha256:
            _fail("market_assignment_manifest_hash_mismatch")
        snapshot = _mapping(_decode_json(snapshot_raw, "market_assignment_snapshot_json_invalid"), "market_assignment_snapshot_invalid")
        manifest = _mapping(_decode_json(manifest_raw, "market_assignment_manifest_json_invalid"), "market_assignment_manifest_invalid")
        if (
            snapshot.get("schema_version") != CURRENT_MARKET_STATUS_SNAPSHOT_SCHEMA_V1
            or snapshot.get("scope") != CURRENT_ONLY_SCOPE
            or snapshot.get("pit_eligible") is not False
            or snapshot.get("run_id") != run_id
        ):
            _fail("market_assignment_snapshot_contract_invalid")
        if (
            manifest.get("schema_version") != CURRENT_MARKET_STATUS_MANIFEST_SCHEMA_V1
            or manifest.get("run_id") != run_id
            or manifest.get("snapshot_sha256") != snapshot_sha256
        ):
            _fail("market_assignment_manifest_contract_invalid")
        manifest_snapshot_path = manifest.get("snapshot_path")
        if not isinstance(manifest_snapshot_path, str) or not Path(manifest_snapshot_path).is_absolute():
            _fail("market_assignment_manifest_snapshot_path_mismatch")
        _check_no_reparse_path(Path(manifest_snapshot_path))
        try:
            resolved_manifest_snapshot = Path(manifest_snapshot_path).resolve(strict=True)
        except OSError as error:
            raise CurrentMarketAssignmentError("market_assignment_manifest_snapshot_path_mismatch") from error
        if resolved_manifest_snapshot != snapshot_path:
            _fail("market_assignment_manifest_snapshot_path_mismatch")
        if type(snapshot.get("partial_failure")) is not bool or snapshot["partial_failure"] != snapshot_partial_failure:
            _fail("market_assignment_partial_failure_mismatch")
        if expected_source_count is not None and snapshot.get("source_count") != expected_source_count:
            _fail("market_assignment_pointer_source_count_mismatch")
        if expected_successful_source_count is not None and snapshot.get("successful_source_count") != expected_successful_source_count:
            _fail("market_assignment_pointer_success_count_mismatch")
        captures_value = snapshot.get("source_captures")
        manifest_sources_value = manifest.get("raw_sources")
        securities_value = snapshot.get("securities")
        if not isinstance(captures_value, list) or len(captures_value) > _MAX_CAPTURE_COUNT:
            _fail("market_assignment_snapshot_captures_invalid")
        snapshot_source_count = snapshot.get("source_count")
        if isinstance(snapshot_source_count, bool) or not isinstance(snapshot_source_count, int) or snapshot_source_count != len(captures_value):
            _fail("market_assignment_snapshot_source_count_mismatch")
        if not isinstance(manifest_sources_value, list) or len(manifest_sources_value) != len(captures_value):
            _fail("market_assignment_manifest_sources_invalid")
        if not isinstance(securities_value, list) or len(securities_value) > 1_000_000:
            _fail("market_assignment_snapshot_securities_invalid")
        capture_by_id: dict[str, Mapping[str, object]] = {}
        for item in captures_value:
            capture = _mapping(item, "market_assignment_snapshot_capture_invalid")
            source_id = _string(capture.get("source_id"), "market_assignment_snapshot_capture_id_invalid", maximum=256)
            if source_id in capture_by_id:
                _fail("market_assignment_duplicate_source_capture")
            capture_by_id[source_id] = capture
        manifest_by_id: dict[str, Mapping[str, object]] = {}
        manifest_projection_keys = ("source_id", "raw_path", "raw_sha256", "captured_at", "status", "parse_status")
        for item in manifest_sources_value:
            manifest_row = _mapping(item, "market_assignment_manifest_source_invalid")
            if set(manifest_row) != set(manifest_projection_keys):
                _fail("market_assignment_manifest_source_schema_invalid")
            source_id = _string(manifest_row.get("source_id"), "market_assignment_manifest_source_id_invalid", maximum=256)
            if source_id in manifest_by_id:
                _fail("market_assignment_duplicate_manifest_source")
            manifest_by_id[source_id] = manifest_row
        if set(capture_by_id) != set(manifest_by_id):
            _fail("market_assignment_capture_manifest_source_set_mismatch")
        for source_id, capture in capture_by_id.items():
            manifest_row = manifest_by_id[source_id]
            projected = {key: capture.get(key) for key in manifest_projection_keys}
            if projected != dict(manifest_row):
                _fail("market_assignment_capture_manifest_projection_mismatch")
        successful_count = sum(
            capture.get("status") == "captured" and capture.get("parse_status") == "parsed"
            for capture in capture_by_id.values()
        )
        snapshot_successful_count = snapshot.get("successful_source_count")
        if isinstance(snapshot_successful_count, bool) or not isinstance(snapshot_successful_count, int) or snapshot_successful_count != successful_count:
            _fail("market_assignment_snapshot_success_count_mismatch")
        observed_at = _datetime_text(_parse_aware_datetime(snapshot.get("observed_at"), "market_assignment_snapshot_time_invalid"))
        cutoff_text = _datetime_text(cutoff_at)
        if _parse_aware_datetime(observed_at, "market_assignment_snapshot_time_invalid") > cutoff_at:
            _fail("market_assignment_snapshot_after_cutoff")
        pointer_time = _datetime_text(_parse_aware_datetime(pointer_published_at, "market_assignment_pointer_time_invalid"))
        if _parse_aware_datetime(pointer_time, "market_assignment_pointer_time_invalid") > cutoff_at:
            _fail("market_assignment_pointer_after_cutoff")
        if _parse_aware_datetime(pointer_time, "market_assignment_pointer_time_invalid") < _parse_aware_datetime(observed_at, "market_assignment_snapshot_time_invalid"):
            _fail("market_assignment_pointer_before_snapshot")
        run_dir = _canonical_existing_directory(output_root / f"cms_{run_id}")
        if not run_dir.is_relative_to(output_root):
            _fail("market_assignment_run_directory_outside_root")
        total_roster_bytes = 0
        roster_references: list[MarketRosterCaptureReferenceV1] = []
        membership_counts: dict[str, Counter[str]] = {source_id: Counter() for source_id in _ROSTER_MARKETS}
        readiness_failures: list[str] = []
        empty_sources: list[str] = []
        for source_id, expected_market in _ROSTER_MARKETS.items():
            roster_capture = capture_by_id.get(source_id)
            if roster_capture is None:
                roster_references.append(_missing_capture(source_id))
                readiness_failures.append(source_id)
                continue
            capture = roster_capture
            if capture.get("market") != expected_market:
                _fail("market_assignment_roster_market_mismatch")
            requested_url = capture.get("requested_url")
            if requested_url != _ROSTER_URLS[source_id]:
                _fail("market_assignment_roster_endpoint_mismatch")
            status = _string(capture.get("status"), "market_assignment_roster_status_invalid", maximum=64)
            parse_status_value = capture.get("parse_status")
            parse_status = parse_status_value if isinstance(parse_status_value, str) and parse_status_value else "missing"
            if status == "captured" and parse_status == "parsed":
                if capture.get("final_url") != _ROSTER_URLS[source_id]:
                    _fail("market_assignment_roster_final_endpoint_mismatch")
            raw_path_value = capture.get("raw_path")
            raw_sha_value = capture.get("raw_sha256")
            raw_size_value = capture.get("raw_bytes")
            raw_relative_path: str | None = None
            raw_sha: str | None = None
            raw_size: int | None = None
            raw: bytes | None = None
            if raw_path_value is not None:
                if not isinstance(raw_path_value, str):
                    _fail("market_assignment_roster_raw_path_invalid")
                raw_path = Path(raw_path_value)
                if not raw_path.is_absolute():
                    _fail("market_assignment_roster_raw_path_invalid")
                raw_relative_path = _relative_posix(raw_path, output_root, "market_assignment_roster_raw_path")
                resolved_raw_path = _resolve_relative(output_root, raw_relative_path, "market_assignment_roster_raw_path")
                raw = _read_bounded_file(resolved_raw_path, max_bytes=_MAX_ROSTER_RAW_BYTES, code="market_assignment_roster_raw")
                total_roster_bytes += len(raw)
                if total_roster_bytes > _MAX_TOTAL_ROSTER_RAW_BYTES:
                    _fail("market_assignment_roster_total_size_exceeded")
                if not isinstance(raw_sha_value, str):
                    _fail("market_assignment_roster_raw_hash_missing")
                raw_sha = _validate_sha(raw_sha_value, "market_assignment_roster_raw_hash_invalid")
                if sha256_bytes(raw) != raw_sha:
                    _fail("market_assignment_roster_raw_hash_mismatch")
                if isinstance(raw_size_value, bool) or not isinstance(raw_size_value, int) or raw_size_value != len(raw):
                    _fail("market_assignment_roster_raw_size_mismatch")
                raw_size = len(raw)
            elif raw_sha_value is not None or raw_size_value is not None:
                _fail("market_assignment_roster_raw_reference_partial")
            captured_at_value = capture.get("captured_at")
            captured_at = None
            if captured_at_value is not None:
                captured_at = _datetime_text(_parse_aware_datetime(captured_at_value, "market_assignment_roster_capture_time_invalid"))
                if _parse_aware_datetime(captured_at, "market_assignment_roster_capture_time_invalid") > cutoff_at:
                    _fail("market_assignment_roster_capture_after_cutoff")
                if _parse_aware_datetime(captured_at, "market_assignment_roster_capture_time_invalid") > _parse_aware_datetime(observed_at, "market_assignment_snapshot_time_invalid"):
                    _fail("market_assignment_roster_capture_after_snapshot")
            if status == "captured" and parse_status == "parsed" and captured_at is None:
                _fail("market_assignment_roster_capture_clock_missing")
            if status == "captured" and raw is None:
                _fail("market_assignment_captured_roster_raw_missing")
            raw_dates_value = capture.get("source_data_dates", [])
            if raw_dates_value is None:
                raw_dates_value = []
            if not isinstance(raw_dates_value, list) or len(raw_dates_value) > 256:
                _fail("market_assignment_roster_source_dates_invalid")
            reported_dates: list[str] = []
            for raw_date in raw_dates_value:
                parsed_date = parse_source_date(raw_date)
                if parsed_date is None or parsed_date.isoformat() != raw_date:
                    _fail("market_assignment_roster_source_dates_invalid")
                if parsed_date > cutoff_at.astimezone(ZoneInfo("Asia/Taipei")).date():
                    _fail("market_assignment_roster_source_date_after_cutoff")
                if captured_at is not None and parsed_date > _parse_aware_datetime(captured_at, "market_assignment_roster_capture_time_invalid").astimezone(ZoneInfo("Asia/Taipei")).date():
                    _fail("market_assignment_roster_source_date_after_capture")
                reported_dates.append(parsed_date.isoformat())
            if reported_dates != sorted(set(reported_dates)):
                _fail("market_assignment_roster_source_dates_invalid")
            row_count_value = capture.get("row_count")
            row_count = None
            if row_count_value is not None:
                if isinstance(row_count_value, bool) or not isinstance(row_count_value, int) or row_count_value < 0 or row_count_value > 1_000_000:
                    _fail("market_assignment_roster_row_count_invalid")
                row_count = row_count_value
            schema_sha: str | None = None
            if status == "captured" and parse_status == "parsed":
                if raw is None or row_count is None:
                    _fail("market_assignment_roster_parsed_reference_incomplete")
                _decode_json(raw, "market_assignment_roster_json_invalid")
                try:
                    rows = decode_official_rows(raw, str(capture.get("content_type") or ""))
                except (CurrentMarketStatusError, UnicodeError, ValueError) as error:
                    raise CurrentMarketAssignmentError("market_assignment_roster_parser_rejected") from error
                if len(rows) != row_count:
                    _fail("market_assignment_roster_row_count_mismatch")
                extracted_dates = sorted(set(
                    explicit_source_dates(rows)
                    + explicit_payload_source_dates(raw)
                    + source_dates_for_aliases(rows, _ROSTER_DATE_ALIASES[source_id])
                ))
                if extracted_dates != reported_dates:
                    _fail("market_assignment_roster_source_date_projection_mismatch")
                schema_keys: tuple[str, ...] | None = None
                for row in rows:
                    keys = tuple(row.keys())
                    if not keys or any(not isinstance(key, str) or not key.strip() for key in keys):
                        _fail("market_assignment_roster_row_schema_invalid")
                    if schema_keys is None:
                        schema_keys = keys
                    elif keys != schema_keys:
                        _fail("market_assignment_roster_heterogeneous_row_schema")
                    required_code_field = _CODE_FIELDS[source_id]
                    if required_code_field not in row:
                        _fail("market_assignment_roster_code_field_missing")
                    raw_symbol = row.get(required_code_field)
                    if not isinstance(raw_symbol, str):
                        _fail("market_assignment_roster_code_value_invalid")
                    normalized_symbol = raw_symbol.strip()
                    if not SYMBOL_RE.fullmatch(normalized_symbol) or extract_symbol(row) != normalized_symbol:
                        _fail("market_assignment_roster_code_value_invalid")
                    membership_counts[source_id][normalized_symbol] += 1
                schema_sha = _identity_sha256({
                    "schema_version": CURRENT_MARKET_ASSIGNMENT_CAPTURE_SCHEMA_V1,
                    "parser_version": CURRENT_MARKET_ASSIGNMENT_PARSER_VERSION,
                    "source_id": source_id,
                    "ordered_row_fields": list(schema_keys or ()),
                    "required_code_field": _CODE_FIELDS[source_id],
                })
                if row_count and capture.get("row_schema_sha256") not in (None, schema_sha):
                    # CMS 原 schema 未保存此 hash；有提供時才嚴格比對。
                    _fail("market_assignment_roster_row_schema_hash_mismatch")
            ready = (
                status == "captured"
                and parse_status == "parsed"
                and captured_at is not None
                and row_count is not None
                and row_count > 0
                and raw is not None
            )
            if status == "captured" and parse_status == "parsed" and row_count == 0:
                empty_sources.append(source_id)
            if not ready:
                readiness_failures.append(source_id)
            final_url_value = capture.get("final_url")
            final_url_reference = final_url_value if isinstance(final_url_value, str) else None
            capture_reference = MarketRosterCaptureReferenceV1(
                source_id=source_id,
                market=expected_market,
                status=status,
                parse_status=parse_status,
                requested_url=requested_url if isinstance(requested_url, str) else None,
                final_url=final_url_reference,
                raw_relative_path=raw_relative_path,
                raw_sha256=raw_sha,
                raw_bytes=raw_size,
                captured_at=captured_at,
                source_data_dates=tuple(reported_dates),
                row_count=row_count,
                row_schema_sha256=schema_sha,
            )
            roster_references.append(capture_reference)
        if len(roster_references) != len(_ROSTER_MARKETS):
            _fail("market_assignment_roster_reference_count_invalid")
        if _parse_aware_datetime(observed_at, "market_assignment_snapshot_time_invalid") > cutoff_at:
            _fail("market_assignment_snapshot_after_cutoff")
        termination_symbols, future_termination_symbols = _verified_termination_symbols(
            output_root=output_root,
            snapshot=snapshot,
            capture_by_id=capture_by_id,
            manifest_by_id=manifest_by_id,
            cutoff_at=cutoff_at,
        )
        pin_without_identity = CurrentMarketAssignmentSourcePinV1(
            output_root=str(output_root),
            run_id=run_id,
            pointer_sha256=pointer_sha256,
            pointer_published_at=pointer_time,
            snapshot_relative_path=snapshot_relative_path,
            snapshot_sha256=snapshot_sha256,
            snapshot_observed_at=observed_at,
            manifest_relative_path=manifest_relative_path,
            manifest_sha256=manifest_sha256,
            snapshot_partial_failure=snapshot_partial_failure,
            cutoff_at=cutoff_text,
            captures=tuple(roster_references),
            identity_sha256="",
        )
        pin = CurrentMarketAssignmentSourcePinV1(
            **{
                **pin_without_identity.__dict__,
                "identity_sha256": _identity_sha256(pin_without_identity._identity_payload()),
            }
        )
        if expected_pin is not None and pin.to_dict() != expected_pin.to_dict():
            _fail("market_assignment_exact_pin_mismatch")
        memberships = {
            source_id: frozenset(counts)
            for source_id, counts in membership_counts.items()
        }
        duplicates = {
            source_id: frozenset(symbol for symbol, count in counts.items() if count > 1)
            for source_id, counts in membership_counts.items()
        }
        return cls(
            pin,
            memberships=memberships,
            duplicates=duplicates,
            ready=not readiness_failures,
            incomplete_sources=tuple(readiness_failures),
            empty_sources=tuple(empty_sources),
            termination_symbols=termination_symbols,
            future_termination_symbols=future_termination_symbols,
        )

    def get(self, symbol: str) -> MarketAssignmentObservationV1:
        normalized = _normalise_symbol(symbol)
        source_ids: tuple[str, ...] = ()
        reason = "no_positive_roster_evidence"
        state = "unknown"
        market: str | None = None
        if not self._ready:
            reason = "required_roster_source_empty" if self._empty_sources else "required_roster_source_incomplete"
            source_ids = self._incomplete_sources
        elif any(normalized in symbols for symbols in self._duplicates.values()):
            reason = "duplicate_membership_within_source"
        elif normalized in self._termination_symbols:
            reason = "explicit_termination_evidence_conflict"
        else:
            twse = normalized in self._memberships["twse.current_roster"]
            tpex = normalized in self._memberships["tpex.current_otc_roster"]
            emerging = normalized in self._memberships["tpex.current_emerging_roster"]
            if emerging:
                reason = "emerging_roster_membership_unsupported"
                source_ids = ("tpex.current_emerging_roster",)
            elif twse and tpex:
                reason = "cross_market_roster_conflict"
                source_ids = ("twse.current_roster", "tpex.current_otc_roster")
            elif twse:
                state, market = "assigned_twse", "twse"
                reason = "unique_positive_current_roster_membership"
                source_ids = ("twse.current_roster",)
            elif tpex:
                state, market = "assigned_tpex", "tpex"
                reason = "unique_positive_current_roster_membership"
                source_ids = ("tpex.current_otc_roster",)
        captures_by_id = {item.source_id: item for item in self.source_pin.captures}
        selected_refs = tuple(captures_by_id[item] for item in source_ids if item in captures_by_id)
        dates = tuple((item.source_id, item.source_data_dates) for item in selected_refs)
        return MarketAssignmentObservationV1(
            schema_version=CURRENT_MARKET_ASSIGNMENT_OBSERVATION_SCHEMA_V1,
            symbol=normalized,
            state=state,
            market=market,
            reason_code=reason,
            roster_source_ids=source_ids,
            roster_sha256s=tuple(item.raw_sha256 for item in selected_refs if item.raw_sha256 is not None),
            source_data_dates=dates,
            snapshot_observed_at=self.source_pin.snapshot_observed_at,
            pointer_published_at=self.source_pin.pointer_published_at,
            cutoff_at=self.source_pin.cutoff_at,
            termination_evidence=(
                "positive_current_conflict"
                if normalized in self._termination_symbols
                else "future_effective_notice"
                if normalized in self._future_termination_symbols
                else "not_verified"
            ),
            source_pin_identity_sha256=self.source_pin.identity_sha256,
        )


def _missing_capture(source_id: str) -> MarketRosterCaptureReferenceV1:
    return MarketRosterCaptureReferenceV1(
        source_id=source_id,
        market=_ROSTER_MARKETS[source_id],
        status="missing",
        parse_status="missing",
        requested_url=None,
        final_url=None,
        raw_relative_path=None,
        raw_sha256=None,
        raw_bytes=None,
        captured_at=None,
        source_data_dates=(),
        row_count=None,
        row_schema_sha256=None,
    )


def _verified_termination_symbols(
    *,
    output_root: Path,
    snapshot: Mapping[str, object],
    capture_by_id: Mapping[str, Mapping[str, object]],
    manifest_by_id: Mapping[str, Mapping[str, object]],
    cutoff_at: datetime,
) -> tuple[frozenset[str], frozenset[str]]:
    securities = snapshot.get("securities")
    if not isinstance(securities, list):
        _fail("market_assignment_snapshot_securities_invalid")
    found: set[str] = set()
    future: set[str] = set()
    verified_source_facts: dict[str, frozenset[tuple[str, date]]] = {}
    total_aux_bytes = 0
    for security_item in securities:
        security = _mapping(security_item, "market_assignment_security_row_invalid")
        symbol_value = security.get("symbol")
        if not isinstance(symbol_value, str) or not SYMBOL_RE.fullmatch(symbol_value):
            continue
        evidence_value = security.get("evidence", [])
        if not isinstance(evidence_value, list) or len(evidence_value) > 256:
            _fail("market_assignment_security_evidence_invalid")
        for evidence_item in evidence_value:
            evidence = _mapping(evidence_item, "market_assignment_evidence_invalid")
            if evidence.get("evidence_type") != "terminated":
                continue
            if evidence.get("symbol") != symbol_value:
                _fail("market_assignment_termination_symbol_mismatch")
            source_id = _string(evidence.get("source_id"), "market_assignment_termination_source_invalid", maximum=256)
            capture = capture_by_id.get(source_id)
            if capture is None or source_id not in manifest_by_id:
                _fail("market_assignment_termination_capture_missing")
            if capture.get("status") != "captured" or capture.get("parse_status") != "parsed":
                _fail("market_assignment_termination_capture_unverified")
            raw_sha = _validate_sha(capture.get("raw_sha256"), "market_assignment_termination_raw_hash_invalid")
            if evidence.get("raw_sha256") != raw_sha:
                _fail("market_assignment_termination_raw_hash_mismatch")
            observed = _parse_aware_datetime(evidence.get("observed_at"), "market_assignment_termination_observation_time_invalid")
            captured_at = _parse_aware_datetime(capture.get("captured_at"), "market_assignment_termination_capture_time_invalid")
            if observed > cutoff_at or captured_at > cutoff_at:
                _fail("market_assignment_termination_evidence_after_cutoff")
            snapshot_observed_at = _parse_aware_datetime(snapshot.get("observed_at"), "market_assignment_snapshot_time_invalid")
            if observed > snapshot_observed_at or captured_at > snapshot_observed_at:
                _fail("market_assignment_termination_evidence_after_snapshot")
            if evidence.get("source_url") != capture.get("final_url"):
                _fail("market_assignment_termination_source_url_mismatch")
            published_value = evidence.get("published_date")
            published_date = parse_source_date(published_value)
            if published_value is not None and published_date is None:
                _fail("market_assignment_termination_publication_date_invalid")
            if published_date is not None and published_date > cutoff_at.astimezone(ZoneInfo("Asia/Taipei")).date():
                _fail("market_assignment_termination_publication_after_cutoff")
            effective = parse_source_date(evidence.get("effective_from"))
            if effective is None:
                _fail("market_assignment_termination_effective_date_invalid")
            if source_id not in verified_source_facts:
                raw_path_value = capture.get("raw_path")
                if not isinstance(raw_path_value, str) or not Path(raw_path_value).is_absolute():
                    _fail("market_assignment_termination_raw_path_invalid")
                raw_rel = _relative_posix(Path(raw_path_value), output_root, "market_assignment_termination_raw_path")
                raw_path = _resolve_relative(output_root, raw_rel, "market_assignment_termination_raw_path")
                raw = _read_bounded_file(raw_path, max_bytes=_MAX_OTHER_RAW_BYTES, code="market_assignment_termination_raw")
                total_aux_bytes += len(raw)
                if total_aux_bytes > _MAX_TOTAL_AUX_RAW_BYTES:
                    _fail("market_assignment_termination_total_size_exceeded")
                if sha256_bytes(raw) != raw_sha:
                    _fail("market_assignment_termination_raw_hash_mismatch")
                manifest_row = manifest_by_id[source_id]
                if manifest_row.get("raw_path") != raw_path_value or manifest_row.get("raw_sha256") != raw_sha:
                    _fail("market_assignment_termination_manifest_ref_mismatch")
                verified_source_facts[source_id] = _parse_termination_source_facts(
                    source_id=source_id,
                    requested_url=str(capture.get("requested_url") or ""),
                    source_url=str(capture.get("final_url") or ""),
                    expected_market=str(capture.get("market") or ""),
                    captured_at=captured_at,
                    raw=raw,
                    content_type=str(capture.get("content_type") or ""),
                )
            if (symbol_value, effective) not in verified_source_facts[source_id]:
                _fail("market_assignment_termination_source_evidence_mismatch")
            if effective <= cutoff_at.astimezone(ZoneInfo("Asia/Taipei")).date():
                found.add(symbol_value)
            else:
                future.add(symbol_value)
    return frozenset(found), frozenset(future)


def _parse_termination_source_facts(
    *,
    source_id: str,
    requested_url: str,
    source_url: str,
    expected_market: str,
    captured_at: datetime,
    raw: bytes,
    content_type: str,
) -> frozenset[tuple[str, date]]:
    """以保存原件重核 CMS 已記錄的正向終止證據。"""
    if source_id in {"twse.terminated_listing", "tpex.terminated_listing"}:
        expected_market = "twse" if source_id.startswith("twse.") else "tpex"
        expected_url = (
            "https://www.twse.com.tw/company/suspendListingCsvAndHtml?lang=en&selectYear=&type=html"
            if expected_market == "twse"
            else "https://www.tpex.org.tw/www/zh-tw/company/deListed"
        )
        if requested_url != expected_url or source_url != expected_url:
            _fail("market_assignment_termination_endpoint_mismatch")
        if expected_market != ("twse" if source_id.startswith("twse.") else "tpex"):
            _fail("market_assignment_termination_market_mismatch")
        try:
            rows = decode_official_rows(raw, content_type)
        except (CurrentMarketStatusError, UnicodeError, ValueError) as error:
            raise CurrentMarketAssignmentError("market_assignment_termination_parser_rejected") from error
        facts = {
            (symbol, effective)
            for row in rows
            if (symbol := extract_symbol(row)) is not None
            and (effective := extract_termination_date(row)) is not None
        }
        return frozenset(facts)
    if re.fullmatch(r"(?:twse|tpex)\.official_notice\.[0-9a-f]{16}", source_id):
        expected_market = source_id.split(".", maxsplit=1)[0]
        if expected_market != ("twse" if source_id.startswith("twse.") else "tpex"):
            _fail("market_assignment_termination_market_mismatch")
        try:
            statements = parse_official_market_notice(
                raw,
                source_url=source_url,
                observed_at=captured_at,
            )
        except CurrentMarketStatusError as error:
            raise CurrentMarketAssignmentError("market_assignment_termination_parser_rejected") from error
        return frozenset(
            (statement.symbol, statement.effective_date)
            for statement in statements
            if statement.statement_type == "listing_termination" and statement.market == expected_market
        )
    _fail("market_assignment_termination_source_unsupported")


__all__ = [
    "CURRENT_MARKET_ASSIGNMENT_OBSERVATION_SCHEMA_V1",
    "CURRENT_MARKET_ASSIGNMENT_PARSER_VERSION",
    "CURRENT_MARKET_ASSIGNMENT_PIN_SCHEMA_V1",
    "CurrentMarketAssignmentError",
    "CurrentMarketAssignmentReader",
    "CurrentMarketAssignmentSourcePinV1",
    "MarketAssignmentObservationV1",
    "MarketRosterCaptureReferenceV1",
]
