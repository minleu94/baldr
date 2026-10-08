"""列出 F17 保存 bundle 的 manifest-only 候選，不授予來源資格。"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Literal, NoReturn, cast

from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_DIRECTORY_V1,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_PATH_CHARS,
    DailyMarketTechnicalOfficialDispositionBundleCancelled,
    DailyMarketTechnicalOfficialDispositionBundleError,
    DailyMarketTechnicalOfficialDispositionBundleManifestMetadataV1,
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
)
from app_module.personal_data_paths import to_internal_io_path


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_SCHEMA_V1 = (
    "daily-market-technical-official-disposition-bundle-catalog.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_CURSOR_SCHEMA_V1 = (
    "daily-market-technical-official-disposition-bundle-catalog-cursor.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT = 20
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_LIMIT = 100
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_ENTRIES = 100_000
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_INVENTORY_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_CURSOR_CHARS = 8192
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_SCAN_NOTICE = (
    "每頁會重新盤點 manifests/ 中最多 100,000 個直接項目及最多 64 MiB manifest bytes；"
    "每份 manifest 最多 8 MiB。候選依 manifest 檔名順序列出，並非最新資料選取。"
    "清單只檢查 manifest，選取後仍須以原 exact reader 核驗 sources 與 row shards。"
)

_IDENTITY_RE = re.compile(r"^[0-9a-f]{64}\.json$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CURSOR_KEYS = frozenset({
    "schema_version",
    "output_root_sha256",
    "inventory_sha256",
    "last_relative_path",
    "cursor_sha256",
})
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_StatSignature = tuple[int, int, int, int, int, int, int]


class DailyMarketTechnicalOfficialDispositionBundleCatalogError(ValueError):
    """F17 manifest catalog 的穩定拒絕碼。"""

    def __init__(self, code: str, *, cause_code: str | None = None) -> None:
        self.code = code
        self.cause_code = cause_code
        super().__init__(code)


class DailyMarketTechnicalOfficialDispositionBundleCatalogCancelled(
    DailyMarketTechnicalOfficialDispositionBundleCatalogError
):
    """本次 metadata inventory 在回傳前被取消。"""


def _fail(code: str, *, cause_code: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionBundleCatalogError(
        code,
        cause_code=cause_code,
    )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1:
    """一筆 manifest-only 顯示資料；diagnostic 列不含可選來源身份。"""

    relative_path: str
    metadata_state: Literal["metadata_unverified", "diagnostic"]
    metadata: DailyMarketTechnicalOfficialDispositionBundleManifestMetadataV1 | None
    diagnostic_code: str | None

    @property
    def bundle_identity_sha256(self) -> str | None:
        return self.metadata.bundle_identity_sha256 if self.metadata is not None else None

    @property
    def manifest_sha256(self) -> str | None:
        return self.metadata.manifest_sha256 if self.metadata is not None else None

    @property
    def can_attempt_exact_read(self) -> bool:
        """只表示可以嘗試精確讀回，不代表已核來源或有資格參與研究。"""

        return self.metadata_state == "metadata_unverified" and self.metadata is not None


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1:
    """有界 manifest inventory 的一頁結果。"""

    entries: tuple[DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1, ...]
    next_cursor: str | None
    has_more: bool | None
    scan_complete: bool
    continuation_required: bool
    scanned_entry_count: int
    manifest_bytes_scanned: int
    inventory_sha256: str | None
    source_inventory_state: Literal[
        "no_saved_manifests",
        "saved_manifests_present",
        "inventory_incomplete",
    ]
    diagnostic_code: str | None
    scan_cost_notice: str = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_SCAN_NOTICE


@dataclass(frozen=True, slots=True)
class _Cursor:
    inventory_sha256: str
    last_relative_path: str


@dataclass(frozen=True, slots=True)
class _ScanResult:
    entries: tuple[DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1, ...]
    inventory_sha256: str | None
    scan_complete: bool
    scanned_entry_count: int
    manifest_bytes_scanned: int
    has_more_after_cursor: bool
    cursor_position_seen: bool
    has_saved_manifests: bool
    diagnostic_code: str | None


class DailyMarketTechnicalOfficialDispositionBundleCatalogV1:
    """重掃明示 bundle root 下的 manifests/，不開 source、objects 或 rows。"""

    def __init__(self, output_root: str | Path) -> None:
        try:
            self._reader = DailyMarketTechnicalOfficialDispositionBundleReaderV1(output_root)
        except (DailyMarketTechnicalOfficialDispositionBundleError, OSError, ValueError) as error:
            cause_code = getattr(error, "code", type(error).__name__)
            raise DailyMarketTechnicalOfficialDispositionBundleCatalogError(
                "catalog_root_invalid",
                cause_code=cause_code if isinstance(cause_code, str) else type(error).__name__,
            ) from error
        self.output_root = self._reader.output_root
        self.manifests_root = (
            self.output_root / "manifests"
        )

    def list_page(
        self,
        *,
        limit: int = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT,
        cursor: str | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1:
        """重掃 manifest inventory，僅在完整且未漂移時提供 continuation cursor。"""

        if type(limit) is not int or not 1 <= limit <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_LIMIT:
            _fail("catalog_limit_invalid")
        _validate_cancel_callback(cancel_callback)
        decoded = self._decode_cursor(cursor) if cursor is not None else None
        _check_cancel(cancel_callback)
        scan = self._scan_inventory(
            page_limit=limit + 1,
            after_relative_path=decoded.last_relative_path if decoded is not None else None,
            cancel_callback=cancel_callback,
        )
        _check_cancel(cancel_callback)

        if decoded is not None:
            if not scan.scan_complete:
                _fail("catalog_cursor_inventory_incomplete")
            if scan.inventory_sha256 != decoded.inventory_sha256:
                _fail("catalog_cursor_stale")
            if not scan.cursor_position_seen:
                _fail("catalog_cursor_position_missing")

        if not scan.scan_complete:
            visible = scan.entries[:limit]
            if not any(entry.metadata_state == "diagnostic" for entry in visible):
                visible = (*visible[: max(0, limit - 1)], self._diagnostic_entry(
                    "@catalog/inventory",
                    scan.diagnostic_code or "catalog_inventory_incomplete",
                ))
            _check_cancel(cancel_callback)
            return DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1(
                entries=tuple(visible),
                next_cursor=None,
                has_more=None,
                scan_complete=False,
                continuation_required=True,
                scanned_entry_count=scan.scanned_entry_count,
                manifest_bytes_scanned=scan.manifest_bytes_scanned,
                inventory_sha256=None,
                source_inventory_state="inventory_incomplete",
                diagnostic_code=scan.diagnostic_code or "catalog_inventory_incomplete",
            )

        if decoded is not None and not scan.cursor_position_seen:
            _fail("catalog_cursor_position_missing")
        visible = scan.entries[:limit]
        has_more = scan.has_more_after_cursor
        next_cursor = None
        if has_more and visible:
            next_cursor = self._encode_cursor(
                cast(str, scan.inventory_sha256),
                visible[-1].relative_path,
            )
        _check_cancel(cancel_callback)
        return DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1(
            entries=tuple(visible),
            next_cursor=next_cursor,
            has_more=has_more,
            scan_complete=True,
            continuation_required=False,
            scanned_entry_count=scan.scanned_entry_count,
            manifest_bytes_scanned=scan.manifest_bytes_scanned,
            inventory_sha256=scan.inventory_sha256,
            source_inventory_state=(
                "saved_manifests_present" if scan.has_saved_manifests else "no_saved_manifests"
            ),
            diagnostic_code=None,
        )

    def _scan_inventory(
        self,
        *,
        page_limit: int,
        after_relative_path: str | None,
        cancel_callback: Callable[[], bool] | None,
    ) -> _ScanResult:
        root_signature = _stat_signature(_lstat(self.output_root, "catalog_root_stat_failed"))
        inventory_sha: str | None = None
        try:
            directory_before = _lstat_optional(self.manifests_root)
        except OSError:
            return _incomplete_scan(
                "catalog_manifest_directory_stat_failed",
                0,
                0,
            )
        if directory_before is None:
            try:
                directory_after = _lstat_optional(self.manifests_root)
                root_after = _lstat(self.output_root, "catalog_root_stat_failed")
            except OSError:
                directory_after = None
                root_after = None
            if directory_after is not None or root_after is None or _stat_signature(root_after) != root_signature:
                return _incomplete_scan(
                    "catalog_manifest_inventory_changed",
                    0,
                    0,
                )
            inventory_sha = _hash_inventory(
                self.output_root,
                directory_signature=None,
                records=(),
                directory_state="missing",
            )
            return _ScanResult((), inventory_sha, True, 0, 0, False, after_relative_path is None, False, None)
        if not stat.S_ISDIR(directory_before.st_mode) or _is_link_or_reparse(directory_before):
            return _incomplete_scan(
                "catalog_manifest_directory_unsafe",
                0,
                0,
            )

        names: list[str] = []
        diagnostic_code: str | None = None
        overflow = False
        try:
            with os.scandir(to_internal_io_path(self.manifests_root)) as iterator:
                for item in iterator:
                    _check_cancel(cancel_callback)
                    if len(names) >= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_ENTRIES:
                        overflow = True
                        diagnostic_code = "catalog_entry_budget_exceeded"
                        break
                    names.append(item.name)
        except OSError:
            diagnostic_code = "catalog_manifest_directory_scan_failed"
        names.sort()

        records: list[dict[str, object]] = []
        selected: list[DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1] = []
        bytes_scanned = 0
        scanned = 0
        cursor_seen = after_relative_path is None
        rows_after_cursor = 0
        has_saved_manifests = bool(names)
        incomplete = diagnostic_code is not None

        for name in names:
            _check_cancel(cancel_callback)
            scanned += 1
            relative = f"manifests/{name}"
            if relative == after_relative_path:
                cursor_seen = True
            path = self.manifests_root / name
            record: dict[str, object] = {
                "relative_path": relative,
                "signature": None,
                "kind": "invalid",
                "manifest_sha256": None,
                "diagnostic_code": None,
            }
            item_metadata: DailyMarketTechnicalOfficialDispositionBundleManifestMetadataV1 | None = None
            item_diagnostic: str | None = None
            before: os.stat_result | None = None
            try:
                before = _lstat_optional(path)
                if before is None:
                    item_diagnostic = "catalog_manifest_entry_missing"
                else:
                    signature_before = _stat_signature(before)
                    record["signature"] = list(signature_before)
                if before is None:
                    pass
                elif _is_link_or_reparse(before):
                    item_diagnostic = "catalog_manifest_reparse_rejected"
                elif not stat.S_ISREG(before.st_mode):
                    item_diagnostic = "catalog_manifest_entry_not_regular"
                elif before.st_nlink != 1:
                    item_diagnostic = "catalog_manifest_hardlink_rejected"
                else:
                    record["kind"] = "regular"
                    if type(before.st_size) is not int or before.st_size < 0:
                        item_diagnostic = "catalog_manifest_size_invalid"
                    else:
                        if before.st_size > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES:
                            item_diagnostic = "catalog_manifest_byte_limit"
                        elif not _IDENTITY_RE.fullmatch(name):
                            item_diagnostic = "catalog_manifest_name_invalid"
                        elif (
                            bytes_scanned + before.st_size
                            > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_INVENTORY_BYTES
                        ):
                            item_diagnostic = "catalog_inventory_byte_budget_exceeded"
                            diagnostic_code = item_diagnostic
                            incomplete = True
                        else:
                            bytes_scanned += before.st_size
                            identity = name[:-5]
                            try:
                                item_metadata = self._reader.read_manifest_metadata(
                                    identity,
                                    cancel_callback=cancel_callback,
                                )
                            except DailyMarketTechnicalOfficialDispositionBundleCancelled as error:
                                raise DailyMarketTechnicalOfficialDispositionBundleCatalogCancelled(
                                    "catalog_cancelled",
                                    cause_code=error.code,
                                ) from error
                            except DailyMarketTechnicalOfficialDispositionBundleError as error:
                                if error.code in {"cancel_callback_invalid", "cancel_callback_failed"}:
                                    _fail(error.code, cause_code=error.cause_code)
                                item_diagnostic = f"manifest_{error.code}"
                if before is not None:
                    after = _lstat_optional(path)
                    if (
                        after is None
                        or _stat_signature(after) != _stat_signature(before)
                        or _is_link_or_reparse(after)
                    ):
                        item_diagnostic = "catalog_manifest_changed_during_inventory"
                        item_metadata = None
                    elif item_metadata is not None:
                        record["manifest_sha256"] = item_metadata.manifest_sha256
                if item_diagnostic is not None:
                    record["diagnostic_code"] = item_diagnostic
                    incomplete = True
                    diagnostic_code = diagnostic_code or item_diagnostic
            except DailyMarketTechnicalOfficialDispositionBundleCatalogCancelled:
                raise
            except DailyMarketTechnicalOfficialDispositionBundleCatalogError:
                raise
            except OSError:
                item_diagnostic = "catalog_manifest_entry_unavailable"
                record["diagnostic_code"] = item_diagnostic
                incomplete = True
                diagnostic_code = diagnostic_code or item_diagnostic

            records.append(record)
            if after_relative_path is not None and relative == after_relative_path:
                cursor_seen = True
            if after_relative_path is not None and relative <= after_relative_path:
                continue
            if item_metadata is None:
                entry = self._diagnostic_entry(relative, item_diagnostic or "catalog_manifest_metadata_invalid")
            else:
                entry = DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1(
                    relative_path=relative,
                    metadata_state="metadata_unverified",
                    metadata=item_metadata,
                    diagnostic_code=None,
                )
            rows_after_cursor += 1
            if len(selected) < page_limit:
                selected.append(entry)
            if item_diagnostic == "catalog_inventory_byte_budget_exceeded":
                break

        try:
            directory_after = _lstat_optional(self.manifests_root)
            root_after = _lstat(self.output_root, "catalog_root_stat_failed")
        except OSError:
            directory_after = None
            root_after = None
        if (
            directory_after is None
            or root_after is None
            or _stat_signature(directory_after) != _stat_signature(directory_before)
            or _stat_signature(root_after) != root_signature
        ):
            incomplete = True
            diagnostic_code = diagnostic_code or "catalog_manifest_inventory_changed"

        if overflow:
            incomplete = True
        if not cursor_seen:
            # 只有完整 inventory 才會向 caller 回報此旗標為 false。
            incomplete = True
            diagnostic_code = diagnostic_code or "catalog_cursor_position_missing"

        if incomplete:
            inventory_sha = None
        else:
            inventory_sha = _hash_inventory(
                self.output_root,
                directory_signature=_stat_signature(directory_before),
                records=records,
                directory_state="present",
            )
        return _ScanResult(
            entries=tuple(selected),
            inventory_sha256=inventory_sha,
            scan_complete=not incomplete,
            scanned_entry_count=scanned,
            manifest_bytes_scanned=bytes_scanned,
            has_more_after_cursor=rows_after_cursor > page_limit - 1,
            cursor_position_seen=cursor_seen,
            has_saved_manifests=has_saved_manifests,
            diagnostic_code=diagnostic_code,
        )

    def _encode_cursor(self, inventory_sha256: str, last_relative_path: str) -> str:
        body: dict[str, object] = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_CURSOR_SCHEMA_V1,
            "output_root_sha256": _sha256_text(str(self.output_root)),
            "inventory_sha256": inventory_sha256,
            "last_relative_path": last_relative_path,
        }
        payload = {**body, "cursor_sha256": _sha256_json(body)}
        raw = _canonical_json(payload).encode("utf-8")
        cursor = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        if len(cursor) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_CURSOR_CHARS:
            _fail("catalog_cursor_size_limit")
        return cursor

    def _decode_cursor(self, cursor: str) -> _Cursor:
        if (
            not isinstance(cursor, str)
            or not cursor
            or len(cursor) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_MAX_CURSOR_CHARS
            or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor)
        ):
            _fail("catalog_cursor_invalid")
        try:
            encoded = cursor.encode("ascii")
            raw = base64.b64decode(
                encoded + b"=" * (-len(encoded) % 4),
                altchars=b"-_",
                validate=True,
            )
            payload = _strict_json_object(raw)
        except (UnicodeError, ValueError, json.JSONDecodeError) as error:
            raise DailyMarketTechnicalOfficialDispositionBundleCatalogError(
                "catalog_cursor_invalid"
            ) from error
        if _canonical_json(payload).encode("utf-8") != raw or set(payload) != _CURSOR_KEYS:
            _fail("catalog_cursor_invalid")
        body = {key: value for key, value in payload.items() if key != "cursor_sha256"}
        if (
            payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_CURSOR_SCHEMA_V1
            or payload.get("output_root_sha256") != _sha256_text(str(self.output_root))
            or not _is_sha256(payload.get("inventory_sha256"))
            or payload.get("cursor_sha256") != _sha256_json(body)
        ):
            _fail("catalog_cursor_invalid")
        last_path = payload.get("last_relative_path")
        if not isinstance(last_path, str) or not re.fullmatch(r"manifests/[0-9a-f]{64}\.json", last_path):
            _fail("catalog_cursor_invalid")
        return _Cursor(
            inventory_sha256=cast(str, payload["inventory_sha256"]),
            last_relative_path=last_path,
        )

    @staticmethod
    def _diagnostic_entry(
        relative_path: str,
        code: str,
    ) -> DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1:
        return DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1(
            relative_path=relative_path,
            metadata_state="diagnostic",
            metadata=None,
            diagnostic_code=code,
        )


def _incomplete_scan(
    diagnostic_code: str,
    scanned_entry_count: int,
    bytes_scanned: int,
) -> _ScanResult:
    return _ScanResult(
        entries=(DailyMarketTechnicalOfficialDispositionBundleCatalogV1._diagnostic_entry(
            "@catalog/manifests",
            diagnostic_code,
        ),),
        inventory_sha256=None,
        scan_complete=False,
        scanned_entry_count=scanned_entry_count,
        manifest_bytes_scanned=bytes_scanned,
        has_more_after_cursor=False,
        cursor_position_seen=False,
        has_saved_manifests=False,
        diagnostic_code=diagnostic_code,
    )


def _validate_cancel_callback(callback: Callable[[], bool] | None) -> None:
    if callback is not None and not callable(callback):
        _fail("cancel_callback_invalid")


def _check_cancel(callback: Callable[[], bool] | None) -> None:
    if callback is None:
        return
    try:
        result = callback()
    except BaseException as error:
        _fail("cancel_callback_failed", cause_code=type(error).__name__)
    if type(result) is not bool:
        _fail("cancel_callback_invalid")
    if result:
        raise DailyMarketTechnicalOfficialDispositionBundleCatalogCancelled("catalog_cancelled")


def _lstat(path: Path, code: str) -> os.stat_result:
    try:
        return os.lstat(to_internal_io_path(path))
    except OSError as error:
        raise DailyMarketTechnicalOfficialDispositionBundleCatalogError(
            code,
            cause_code=type(error).__name__,
        ) from error


def _lstat_optional(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(to_internal_io_path(path))
    except FileNotFoundError:
        return None


def _stat_signature(info: os.stat_result) -> _StatSignature:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_nlink),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
    )


def _is_link_or_reparse(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


def _strict_json_object(raw: bytes) -> dict[str, object]:
    if not raw or len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES:
        _fail("catalog_cursor_bytes_invalid")
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object_pairs,
            parse_float=_reject_json_float,
            parse_constant=_reject_json_constant,
        )
    except DailyMarketTechnicalOfficialDispositionBundleCatalogError:
        raise
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise DailyMarketTechnicalOfficialDispositionBundleCatalogError(
            "catalog_cursor_json_invalid"
        ) from error
    if not isinstance(payload, dict):
        _fail("catalog_cursor_json_invalid")
    return cast(dict[str, object], payload)


def _unique_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("catalog_cursor_duplicate_json_key")
        result[key] = value
    return result


def _reject_json_float(value: str) -> object:
    del value
    _fail("catalog_cursor_float_forbidden")


def _reject_json_constant(value: str) -> object:
    del value
    _fail("catalog_cursor_constant_forbidden")


def _canonical_json(payload: object) -> str:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise DailyMarketTechnicalOfficialDispositionBundleCatalogError(
            "catalog_json_value_invalid"
        ) from error


def _sha256_json(payload: object) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _hash_inventory(
    output_root: Path,
    *,
    directory_signature: _StatSignature | None,
    records: tuple[dict[str, object], ...] | list[dict[str, object]],
    directory_state: Literal["present", "missing"],
) -> str:
    hasher = sha256()
    header = {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_SCHEMA_V1,
        "output_root_sha256": _sha256_text(str(output_root)),
        "directory_state": directory_state,
        "directory_signature": list(directory_signature) if directory_signature is not None else None,
    }
    hasher.update(_canonical_json(header).encode("utf-8") + b"\n")
    for record in records:
        hasher.update(_canonical_json(record).encode("utf-8") + b"\n")
    return hasher.hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None
