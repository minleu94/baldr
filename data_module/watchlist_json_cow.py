"""將單一 legacy watchlist JSON 唯讀轉成獨立 SQLite v3 COW 副本。"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import errno
import hashlib
import importlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, BinaryIO, Callable, Iterator, Mapping
import uuid

from app_module.personal_data_paths import WatchlistCowControlPaths
from data_module import watchlist_item_storage as item_storage
from data_module.watchlist_item_storage import WatchlistWriteCapacityRequest
from data_module.watchlist_sqlite_cow import (
    _Blocked,
    _io_path,
    _canonical_path,
    _Current,
    _Snapshot,
    _base_result,
    _build_database,
    _create_stage,
    _decode_source_payload,
    _publish_noreplace,
    _validate_stage,
    _write_receipt_stage,
)


_RECEIPT_SCHEMA = "watchlist-cow-conversion.v1"
_SOURCE_FORMAT = "legacy_json_v1"
_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = item_storage.MAX_ROWS * 32
_MANAGEMENT_SUFFIXES = (
    ".cow-active.json",
    ".cow-conversion.v1.json",
    ".cow-backup.v1.json",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@contextmanager
def held_json_source(source: Path | str) -> Iterator[BinaryIO]:
    """在轉換或啟用期間獨占持有 JSON 唯讀 handle，阻擋其他程序開啟寫入或刪除。"""
    source_input = Path(source).expanduser().absolute()
    if _io_path(source_input).is_symlink():
        raise _Blocked("source_not_regular_file")
    path = _canonical_path(source_input, strict=True)
    if not _io_path(path).is_file():
        raise _Blocked("source_not_regular_file")
    if os.name == "nt":
        import msvcrt
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        # 允許其他唯讀 handle 共存，仍拒絕任何寫入或刪除/rename handle。
        handle = create_file(str(_io_path(path)), 0x80000000, 1, None, 3, 0x80, None)
        invalid_handle = ctypes.c_void_p(-1).value
        handle_value = handle if isinstance(handle, int) else getattr(handle, "value", None)
        if handle_value is None or handle_value == invalid_handle:
            error = ctypes.get_last_error()
            if error in {32, 33}:
                raise _Blocked("source_writer_busy")
            raise OSError(error, ctypes.FormatError(error), str(path))
        try:
            descriptor = msvcrt.open_osfhandle(
                int(handle_value), os.O_RDONLY | getattr(os, "O_BINARY", 0),
            )
        except Exception:
            kernel32.CloseHandle(wintypes.HANDLE(handle_value))
            raise
        stream = os.fdopen(descriptor, "rb", closefd=True)
        try:
            yield stream
        finally:
            stream.close()
        return

    stream = _io_path(path).open("rb")
    try:
        try:
            fcntl = importlib.import_module("fcntl")
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, OSError) as exc:
            if isinstance(exc, OSError) and exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise _Blocked("source_writer_busy") from exc
            raise OSError(errno.EBUSY, "來源 JSON 唯讀鎖無法取得", str(path)) from exc
        yield stream
    finally:
        stream.close()


def _receipt_path(target: Path) -> Path:
    return target.with_name(target.name + ".cow-conversion.v1.json")


def _other_json_sources(source: Path, target: Path, receipt: Path) -> bool:
    """只檢查名稱；單檔轉換不得略過同資料夾的其他 JSON 清單。"""
    for count, entry in enumerate(_io_path(source.parent).iterdir(), 1):
        entry = source.parent / entry.name
        if count > item_storage.MAX_ROWS + 2:
            raise _Blocked("source_directory_scan_limit_exceeded")
        if entry in {source, target, receipt} or entry.suffix.casefold() != ".json":
            continue
        name = entry.name.casefold()
        if name.endswith(_MANAGEMENT_SUFFIXES) or (
            ".cow-rollback." in name and name.endswith(".json")
        ):
            continue
        # 目錄中的任何其他 JSON 都可能是另一張合法清單；不讀取或猜測它的內容。
        return True
    return False


def _normalize_paths(
    source: Path | str, destination: Path | str, *,
    control_paths: WatchlistCowControlPaths | None = None,
) -> tuple[Path, Path, Path]:
    source_input = Path(source).expanduser().absolute()
    target_input = Path(destination).expanduser().absolute()
    try:
        if _io_path(source_input).is_symlink() or not _io_path(source_input).is_file():
            raise _Blocked("source_not_regular_file")
        if source_input.suffix.casefold() != ".json":
            raise _Blocked("source_not_json")
        if control_paths is None:
            source_path = _canonical_path(source_input, strict=True)
            target_parent_input = target_input.parent
            if _io_path(target_parent_input).is_symlink():
                raise _Blocked("target_parent_symlink_unsupported")
            target_parent = _canonical_path(target_parent_input, strict=True)
            target_path = target_parent / target_input.name
            receipt = _receipt_path(target_path)
        else:
            control_paths.validate(
                source_input, target_input, _receipt_path(target_input),
            )
            source_path = _canonical_path(source_input, strict=True)
            target_path = control_paths.assert_personal(
                control_paths.personal_paths.watchlist_db,
            )
            receipt = control_paths.assert_personal(control_paths.receipt_path)
        if not target_path.name or _io_path(target_path).exists() or _io_path(target_path).is_symlink():
            raise _Blocked("target_already_exists")
        if _io_path(receipt).exists() or _io_path(receipt).is_symlink():
            raise _Blocked("receipt_already_exists")
        if os.path.normcase(str(source_path)) == os.path.normcase(str(target_path)):
            raise _Blocked("source_target_same_path")
        if target_path.name.casefold() == "watchlists.db":
            raise _Blocked("target_is_canonical_path")
        canonical_database = source_path.parent / "watchlists.db"
        if _io_path(canonical_database).exists() or _io_path(canonical_database).is_symlink():
            raise _Blocked("canonical_database_present")
        if _io_path(source_path).stat(follow_symlinks=False).st_nlink != 1:
            raise _Blocked("source_hardlink_unsupported")
        if control_paths is not None:
            control_paths.assert_personal(target_path)
            control_paths.assert_personal(receipt)
        if _other_json_sources(source_path, target_path, receipt):
            raise _Blocked("other_json_sources_present")
        for path, code in ((source_path, "source_sidecar_present"),
                           (target_path, "target_sidecar_present"),
                           (receipt, "receipt_sidecar_present")):
            if any(_io_path(Path(f"{path}{suffix}")).exists() for suffix in ("-journal", "-wal", "-shm")):
                raise _Blocked(code)
    except _Blocked:
        raise
    except OSError as exc:
        raise _Blocked("path_preflight_failed") from exc
    return source_path, target_path, receipt


def _history_field_paths(value: Any) -> list[str]:
    """回報名字像歷史資料的欄位路徑，但不把它們解讀成 revision ledger。"""
    found: list[str] = []
    pending: list[tuple[Any, str]] = [(value, "$")]
    while pending:
        current, location = pending.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                child_path = f"{location}.{key}"
                lowered = str(key).casefold()
                if "history" in lowered or "revision" in lowered or lowered == "events":
                    found.append(child_path)
                pending.append((child, child_path))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                pending.append((child, f"{location}[{index}]"))
    return sorted(found)


def _validate_payload_complexity(value: Any) -> None:
    pending: list[tuple[Any, int]] = [(value, 0)]
    node_count = 0
    while pending:
        current, depth = pending.pop()
        node_count += 1
        if node_count > _MAX_JSON_NODES:
            raise _Blocked("payload_node_limit_exceeded")
        if depth > _MAX_JSON_DEPTH:
            raise _Blocked("payload_depth_limit_exceeded")
        if isinstance(current, dict):
            pending.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            pending.extend((child, depth + 1) for child in current)


def _validate_legacy_v1_payload(payload: Mapping[str, Any]) -> None:
    if type(payload.get("version")) is not int or payload.get("version") != 1:
        raise _Blocked("unsupported_legacy_json_version")
    for field_name in ("name", "description", "created_at", "updated_at"):
        if field_name in payload and not isinstance(payload[field_name], str):
            raise _Blocked(f"invalid_legacy_envelope_{field_name}")
    for field_name in ("name", "created_at", "updated_at"):
        if not isinstance(payload.get(field_name), str) or not payload[field_name]:
            raise _Blocked(f"invalid_legacy_envelope_{field_name}")
    items = payload.get("items")
    if not isinstance(items, list):
        raise _Blocked("invalid_payload_shape")
    string_fields = (
        "stock_code", "證券代號", "stock_name", "證券名稱", "added_at",
        "source", "notes", "source_id",
    )
    identity_string_fields = (
        "result_id", "stock_code", "證券代號", "source_snapshot_id",
        "source_snapshot_hash", "decision_date", "identity_status",
    )
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise _Blocked("invalid_item_object")
        for field_name in string_fields:
            if field_name in item and not isinstance(item[field_name], str):
                raise _Blocked(f"invalid_legacy_item_{field_name}")
        code_value = item.get("stock_code", item.get("證券代號"))
        name_value = item.get("stock_name", item.get("證券名稱"))
        if not isinstance(code_value, str) or not code_value or code_value != code_value.strip():
            raise _Blocked("invalid_legacy_item_stock_code")
        if not isinstance(name_value, str) or not name_value:
            raise _Blocked("invalid_legacy_item_stock_name")
        for field_name in ("added_at", "source"):
            if not isinstance(item.get(field_name), str) or not item[field_name]:
                raise _Blocked(f"invalid_legacy_item_{field_name}")
        # typed reader 會重新判讀 manual 收藏來源；拒絕此歧義，避免後續保存改來源。
        if "research_bookmark" in item and item.get("source") == "manual":
            raise _Blocked("ambiguous_legacy_manual_bookmark_source")
        if "tags" in item and (
            not isinstance(item["tags"], list)
            or any(not isinstance(tag, str) for tag in item["tags"])
        ):
            raise _Blocked("invalid_legacy_item_tags")
        if ("stock_code" in item and "證券代號" in item
                and item["stock_code"] != item["證券代號"]):
            raise _Blocked(f"conflicting_legacy_item_stock_code_{index}")
        if ("stock_name" in item and "證券名稱" in item
                and item["stock_name"] != item["證券名稱"]):
            raise _Blocked(f"conflicting_legacy_item_stock_name_{index}")
        if "decision_identity" in item:
            identity = item["decision_identity"]
            if not isinstance(identity, dict):
                raise _Blocked("invalid_legacy_item_decision_identity")
        else:
            identity = {}
        for source in (item, identity):
            for field_name in identity_string_fields:
                if field_name not in source:
                    continue
                value = source[field_name]
                if not isinstance(value, str) or value != value.strip():
                    raise _Blocked(f"invalid_legacy_decision_identity_{field_name}")
                if field_name == "identity_status" and not value:
                    raise _Blocked("invalid_legacy_decision_identity_identity_status")
                if field_name in {"stock_code", "證券代號"} and not value:
                    raise _Blocked("invalid_legacy_decision_identity_stock_code")
                if field_name == "identity_status" and value not in {
                    "linked", "unknown", "conflict", "unlinked",
                }:
                    raise _Blocked("invalid_legacy_decision_identity_identity_status")
        nested_code = identity.get("stock_code", identity.get("證券代號", ""))
        if nested_code and nested_code != code_value:
            raise _Blocked("conflicting_legacy_decision_identity_stock_code")


def _file_stat_record(stream: BinaryIO) -> dict[str, int]:
    value = os.fstat(stream.fileno())
    return {
        "size": int(value.st_size), "mtime_ns": int(value.st_mtime_ns),
        "inode": int(value.st_ino), "device": int(value.st_dev),
    }


def _stream_sha256(stream: BinaryIO) -> str:
    previous = stream.tell()
    digest = hashlib.sha256()
    total = 0
    try:
        stream.seek(0)
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > item_storage.MAX_PAYLOAD_BYTES:
                raise _Blocked("payload_limit_exceeded")
            digest.update(block)
        return digest.hexdigest()
    finally:
        stream.seek(previous)


def _snapshot_from_json(
    source: Path, stream: BinaryIO,
) -> tuple[_Snapshot, dict[str, Any], list[str]]:
    before_stat = _file_stat_record(stream)
    if before_stat["size"] > item_storage.MAX_PAYLOAD_BYTES:
        raise _Blocked("payload_limit_exceeded")
    try:
        stream.seek(0)
        source_bytes = stream.read(item_storage.MAX_PAYLOAD_BYTES + 1)
    except OSError as exc:
        raise _Blocked("source_read_failed") from exc
    if len(source_bytes) > item_storage.MAX_PAYLOAD_BYTES:
        raise _Blocked("payload_limit_exceeded")
    if source_bytes.startswith(b"\xef\xbb\xbf"):
        raise _Blocked("unsupported_utf8_bom")
    try:
        raw = source_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _Blocked("invalid_source_encoding") from exc
    source_hash = _sha256_bytes(source_bytes)
    if _file_stat_record(stream) != before_stat:
        raise _Blocked("source_changed_during_read")
    try:
        source_raw, payload, _, item_json = _decode_source_payload(raw)
    except _Blocked:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        raise _Blocked("invalid_json_payload") from exc
    if source_raw != raw or not isinstance(payload, dict):
        raise _Blocked("invalid_payload_shape")
    _validate_payload_complexity(payload)
    _validate_legacy_v1_payload(payload)
    if len(payload["items"]) + 2 > item_storage.MAX_ROWS:
        # 物件、baseline revision、current row 與新增 item events 都受下方
        # save_v3 的完整 row count 檢查；此項先擋明顯超界輸入，避免大額配置。
        raise _Blocked("row_limit_exceeded")
    source_size = len(source_bytes)
    current = _Current(
        source.stem, source_raw, payload, 1, "", False, "",
    )
    snapshot = _Snapshot(
        source_path=source,
        source_schema_version=1,
        source_sha256=source_hash,
        source_size_bytes=source_size,
        source_stat=before_stat,
        currents=(current,),
        revisions=(),
        source_row_count=1,
        source_payload_bytes=source_size,
        source_scan_bytes=source_size,
        source_database_bytes=0,
    )
    return snapshot, payload, item_json


def _preservation_comparison(
    comparison: Mapping[str, Any], source_raw: str, payload: Mapping[str, Any],
    item_json: list[str],
) -> dict[str, Any]:
    result = dict(comparison)
    paths = _history_field_paths(payload)
    result.update({
        "source_format": _SOURCE_FORMAT,
        "source_payload_sha256": _sha256_bytes(source_raw.encode("utf-8")),
        "source_payload_bytes": len(source_raw.encode("utf-8")),
        "raw_payload_bytes_preserved": True,
        "ordered_raw_item_count": len(item_json),
        "ordered_raw_item_sha256": [_sha256_bytes(item.encode("utf-8")) for item in item_json],
        "ordered_raw_items_preserved": True,
        "payload_envelope_fields_preserved": sorted(str(key) for key in payload if key != "items"),
        "item_fields_preserved": sorted({str(key) for item in payload["items"] for key in item}),
        "uninterpreted_json_extensions_preserved": True,
        "history_like_field_paths_preserved_as_opaque_payload": paths,
        "history_like_field_count": len(paths),
        "source_revision_ledger": "not_provided_by_legacy_json_v1",
        "history_interpreted_as_revision_events": False,
        "target_synthetic_baseline_count": 1,
        "target_revision_number": 1,
    })
    # SQLite v1 會標示來源 revision history 缺口；JSON 可能含 opaque history 值，故不沿用該描述。
    result.pop("source_history_gaps_preserved", None)
    return result


def _result(
    snapshot: _Snapshot, target: Path, receipt: Path, status: str,
    details: Mapping[str, Any], source_raw: str, payload: Mapping[str, Any], item_json: list[str],
    *, target_hash: str | None, target_size: int | None,
    source_backup_path: str | None = None,
    source_backup_sha256: str | None = None,
) -> dict[str, Any]:
    result = _base_result(
        snapshot, target, receipt, status, details,
        target_hash=target_hash, target_size=target_size,
    )
    result["source_format"] = _SOURCE_FORMAT
    result["canonical_path"] = str(snapshot.source_path)
    result["comparison"] = _preservation_comparison(
        result["comparison"], source_raw, payload, item_json,
    )
    if source_backup_path is not None and source_backup_sha256 is not None:
        result["source_backup_path"] = source_backup_path
        result["source_backup_sha256"] = source_backup_sha256
    result["migration_notes"] = [
        "legacy_json_v1 只按單檔 current payload 匯入；revision 1 明確標記為 synthetic baseline。",
        "未知欄位與 history-like 值保留為 opaque JSON payload，不推定或生成歷史 revision。",
        "其他同目錄 JSON 清單會拒絕轉換，需逐檔處理以免遺漏 watchlist。",
        "只支援無 BOM 的 UTF-8 JSON；不接受其他編碼或未知 version。",
    ]
    return result


def _capacity_preflight(
    target: Path, snapshot: _Snapshot, details: Mapping[str, Any], receipt_template: Mapping[str, Any],
    callback: Callable[[WatchlistWriteCapacityRequest], bool | None] | None,
    *, source_backup_bytes: int = 0,
) -> None:
    database_bytes = int(details["database_bytes"])
    receipt_bytes = len(json.dumps(
        receipt_template, ensure_ascii=False, sort_keys=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8"))
    if database_bytes > item_storage.MAX_DATABASE_BYTES:
        raise _Blocked("database_limit_exceeded")
    if receipt_bytes > 1024 * 1024:
        raise _Blocked("receipt_limit_exceeded")
    # stage 與 final 使用同一個 hard link；容量預估取較保守的雙份上限。
    required_peak_bytes = database_bytes * 2 + receipt_bytes * 2 + source_backup_bytes
    request = WatchlistWriteCapacityRequest(
        db_path=target,
        operation="watchlist-json-cow-convert",
        payload_bytes_after=int(details["payload_bytes"]),
        rows_after=int(details["row_count"]),
        database_bytes_before=0,
        sidecar_bytes_before=0,
        estimated_database_growth_bytes=database_bytes + receipt_bytes + source_backup_bytes,
        required_peak_bytes=required_peak_bytes,
    )
    if callback is not None:
        try:
            approved = callback(request)
        except Exception as exc:
            raise _Blocked("capacity_unknown") from exc
        if approved is not True:
            raise _Blocked("capacity_unknown" if approved is None else "capacity_insufficient")
    try:
        from data_module.ml_storage_capacity import (
            evaluate_capacity, filesystem_usage, heavy_chain_capacity_budget,
        )
        decision = evaluate_capacity(
            budget=heavy_chain_capacity_budget(),
            usage=filesystem_usage(target),
            stage="watchlist-cow-conversion",
            persistent_existing_bytes=snapshot.source_size_bytes,
            persistent_new_bytes_estimate=database_bytes + receipt_bytes + source_backup_bytes,
            temporary_peak_bytes_observed=required_peak_bytes,
        )
    except Exception as exc:
        raise _Blocked("capacity_unknown") from exc
    if getattr(decision, "within_budget", None) is not True:
        raise _Blocked("capacity_insufficient")


def _write_source_backup(
    control_paths: WatchlistCowControlPaths, stream: BinaryIO, expected_sha256: str,
) -> tuple[Path, str]:
    backup = control_paths.assert_personal(control_paths.source_backup_path)
    try:
        stream.seek(0)
        source_bytes = stream.read(item_storage.MAX_PAYLOAD_BYTES + 1)
    except OSError as exc:
        raise _Blocked("source_backup_read_failed") from exc
    if len(source_bytes) > item_storage.MAX_PAYLOAD_BYTES:
        raise _Blocked("payload_limit_exceeded")
    backup_sha256 = _sha256_bytes(source_bytes)
    if backup_sha256 != expected_sha256:
        raise _Blocked("source_changed_before_backup")

    if _io_path(backup).exists() or _io_path(backup).is_symlink():
        control_paths.assert_personal(backup)
        try:
            if _io_path(backup).read_bytes() != source_bytes:
                raise _Blocked("source_backup_conflict")
        except _Blocked:
            raise
        except OSError as exc:
            raise _Blocked("source_backup_unavailable") from exc
        return backup, backup_sha256

    control_paths.assert_personal(backup)
    try:
        descriptor = os.open(_io_path(backup), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(source_bytes)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError:
        control_paths.assert_personal(backup)
        try:
            if _io_path(backup).read_bytes() != source_bytes:
                raise _Blocked("source_backup_conflict")
        except _Blocked:
            raise
        except OSError as exc:
            raise _Blocked("source_backup_unavailable") from exc
    except OSError as exc:
        raise _Blocked("source_backup_write_failed") from exc
    control_paths.assert_personal(backup)
    try:
        if _io_path(backup).read_bytes() != source_bytes:
            raise _Blocked("source_backup_verify_failed")
    except _Blocked:
        raise
    except OSError as exc:
        raise _Blocked("source_backup_verify_failed") from exc
    return backup, backup_sha256


def _verify_source_still_held(snapshot: _Snapshot, stream: BinaryIO) -> None:
    try:
        handle_stat = _file_stat_record(stream)
        current_hash = _stream_sha256(stream)
        if os.name == "nt":
            path_record = handle_stat
        else:
            path_stat = _io_path(snapshot.source_path).stat(follow_symlinks=False)
            path_record = {
                "size": int(path_stat.st_size), "mtime_ns": int(path_stat.st_mtime_ns),
                "inode": int(path_stat.st_ino), "device": int(path_stat.st_dev),
            }
    except OSError as exc:
        raise _Blocked("source_unavailable_before_publish") from exc
    if (path_record != snapshot.source_stat or handle_stat != snapshot.source_stat
            or current_hash != snapshot.source_sha256):
        raise _Blocked("source_changed_before_publish")


def _convert(
    source: Path | str, destination: Path | str, *, dry_run: bool,
    capacity_preflight: Callable[[WatchlistWriteCapacityRequest], bool | None] | None,
    cancel_check: Callable[[], bool] | None,
    control_paths: WatchlistCowControlPaths | None = None,
) -> dict[str, Any]:
    try:
        if control_paths is not None:
            target_input = Path(destination).expanduser().absolute()
            expected_receipt = _receipt_path(target_input)
            control_paths.validate(source, target_input, expected_receipt)
            source_input = Path(source).expanduser().absolute()
            if any(
                _io_path(Path(f"{source_input}{suffix}")).exists()
                or _io_path(Path(f"{source_input}{suffix}")).is_symlink()
                for suffix in (".cow-active.json", ".cow-conversion.v1.json",
                               ".cow-backup.v1.json")
            ):
                raise _Blocked("legacy_control_marker_requires_review")
            if not dry_run:
                control_paths.prepare_directories()
        source_path, target, receipt = _normalize_paths(
            source, destination, control_paths=control_paths,
        )
        with held_json_source(source_path) as source_stream:
            return _convert_held(
                source_path, target, receipt, source_stream, dry_run=dry_run,
                capacity_preflight=capacity_preflight, cancel_check=cancel_check,
                control_paths=control_paths,
            )
    except _Blocked as exc:
        return {
            "schema_version": _RECEIPT_SCHEMA,
            "source_format": _SOURCE_FORMAT,
            "status": "blocked",
            "error_code": exc.code,
        }
    except (OSError, ValueError, TypeError) as exc:
        error_code = (
            str(getattr(exc, "code", type(exc).__name__))
            if control_paths is not None else "source_read_lock_unavailable"
        )
        return {
            "schema_version": _RECEIPT_SCHEMA,
            "source_format": _SOURCE_FORMAT,
            "status": "blocked",
            "error_code": error_code,
        }


def _convert_held(
    source_path: Path, target: Path, receipt: Path, source_stream: BinaryIO, *,
    dry_run: bool,
    capacity_preflight: Callable[[WatchlistWriteCapacityRequest], bool | None] | None,
    cancel_check: Callable[[], bool] | None,
    control_paths: WatchlistCowControlPaths | None = None,
) -> dict[str, Any]:
    stage: Path | None = None
    receipt_stage: Path | None = None
    try:
        snapshot, payload, item_json = _snapshot_from_json(source_path, source_stream)
        source_raw = snapshot.currents[0].payload_raw
        if cancel_check is not None and cancel_check():
            raise _Blocked("cancelled")
        memory_conn, details = _build_database(snapshot)
        try:
            backup_path = (
                control_paths.assert_personal(control_paths.source_backup_path)
                if control_paths is not None else None
            )
            receipt_result = _result(
                snapshot, target, receipt, "ready", details, source_raw, payload, item_json,
                target_hash="0" * 64, target_size=int(details["database_bytes"]),
                source_backup_path=str(backup_path) if backup_path is not None else None,
                source_backup_sha256=snapshot.source_sha256 if backup_path is not None else None,
            )
            _capacity_preflight(
                target, snapshot, details, receipt_result, capacity_preflight,
                source_backup_bytes=(snapshot.source_size_bytes if backup_path is not None else 0),
            )
            if cancel_check is not None and cancel_check():
                raise _Blocked("cancelled")
            if dry_run:
                _verify_source_still_held(snapshot, source_stream)
                return _result(
                    snapshot, target, receipt, "dry_run", details, source_raw, payload, item_json,
                    target_hash=None, target_size=int(details["database_bytes"]),
                )
            backup_sha256: str | None = None
            if control_paths is not None:
                _verify_source_still_held(snapshot, source_stream)
                backup_path, backup_sha256 = _write_source_backup(
                    control_paths, source_stream, snapshot.source_sha256,
                )
                _verify_source_still_held(snapshot, source_stream)
            stage = _create_stage(
                target, memory_conn, control_paths=control_paths,
            )
            target_hash, target_size = _validate_stage(
                stage, details, control_paths=control_paths,
            )
            if target_size > item_storage.MAX_DATABASE_BYTES:
                raise _Blocked("database_limit_exceeded")
            _verify_source_still_held(snapshot, source_stream)
            ready_receipt = _result(
                snapshot, target, receipt, "ready", details, source_raw, payload, item_json,
                target_hash=target_hash, target_size=target_size,
                source_backup_path=str(backup_path) if control_paths is not None else None,
                source_backup_sha256=backup_sha256,
            )
            receipt_stage = _write_receipt_stage(
                receipt, ready_receipt, control_paths=control_paths,
            )
            _verify_source_still_held(snapshot, source_stream)
            _publish_noreplace(stage, target, control_paths=control_paths)
            if control_paths is not None:
                stage = None
            # 收據發布前再核對來源；沒有匹配收據時 activation 不會信任 target。
            _verify_source_still_held(snapshot, source_stream)
            try:
                if control_paths is not None:
                    control_paths.assert_personal(receipt_stage)
                    control_paths.assert_personal(receipt)
                os.link(_io_path(receipt_stage), _io_path(receipt))
                os.unlink(_io_path(receipt_stage))
                receipt_stage = None
                if stage is not None:
                    os.unlink(_io_path(stage))
                    stage = None
            except Exception as exc:
                raise _Blocked("receipt_publish_failed") from exc
            return ready_receipt
        finally:
            memory_conn.close()
    except _Blocked as exc:
        result: dict[str, Any] = {
            "schema_version": _RECEIPT_SCHEMA,
            "source_format": _SOURCE_FORMAT,
            "status": "blocked",
            "error_code": exc.code,
        }
        if stage is not None and _io_path(stage).exists():
            result["failed_stage_path"] = str(stage)
        if receipt_stage is not None and _io_path(receipt_stage).exists():
            result["failed_receipt_stage_path"] = str(receipt_stage)
        return result
    except (sqlite3.Error, OSError, ValueError, TypeError, RecursionError) as exc:
        result = {
            "schema_version": _RECEIPT_SCHEMA,
            "source_format": _SOURCE_FORMAT,
            "status": "blocked",
            "error_code": str(getattr(exc, "code", type(exc).__name__)),
        }
        if stage is not None and _io_path(stage).exists():
            result["failed_stage_path"] = str(stage)
        if receipt_stage is not None and _io_path(receipt_stage).exists():
            result["failed_receipt_stage_path"] = str(receipt_stage)
        return result


def dry_run_watchlist_json(
    source: Path | str,
    destination: Path | str,
    *,
    capacity_preflight: Callable[[WatchlistWriteCapacityRequest], bool | None] | None = None,
    control_paths: WatchlistCowControlPaths | None = None,
) -> dict[str, Any]:
    """唯讀驗證單一 legacy JSON，於記憶體建構副本，不建立目標或收據。"""
    return _convert(
        source, destination, dry_run=True,
        capacity_preflight=capacity_preflight, cancel_check=None,
        control_paths=control_paths,
    )


def convert_watchlist_json(
    source: Path | str,
    destination: Path | str,
    *,
    capacity_preflight: Callable[[WatchlistWriteCapacityRequest], bool | None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    control_paths: WatchlistCowControlPaths | None = None,
) -> dict[str, Any]:
    """建立獨立 SQLite v3 副本；原始 JSON 唯讀，驗證成功後才發布 target/receipt。"""
    return _convert(
        source, destination, dry_run=False,
        capacity_preflight=capacity_preflight, cancel_check=cancel_check,
        control_paths=control_paths,
    )
