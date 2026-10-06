"""明示管理 watchlist SQLite COW 副本的 activation 指向與回復。

personal 模式明示傳入 WatchlistCowControlPaths：來源僅唯讀，marker、lock、
receipt、JSON bytes 備份與rollback audit均在個人root；不搬舊marker。
PersonalWatchlistCowService 是未接全域config/UI的backend consumer，僅active
狀態可load/save。rollback保存target新增revision，原來源仍唯讀、personal writer
停用；None保留舊API。personal marker新schema只由明示control reader接受。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from uuid import uuid4

from data_module.watchlist_repository import WatchlistRepository
from app_module.personal_data_paths import PersonalDataPathError, WatchlistCowControlPaths


ACTIVATION_SCHEMA = "watchlist-cow-activation.v1"
PERSONAL_ACTIVATION_SCHEMA = "watchlist-cow-activation.personal.v1"
BACKUP_SCHEMA = "watchlist-cow-rollback.v1"
RECEIPT_SCHEMA = "watchlist-cow-conversion.v1"
JSON_SOURCE_FORMAT = "legacy_json_v1"
_CancelCheck = Callable[[], bool | None]


class WatchlistCowActivationError(RuntimeError):
    """COW activation fail-closed 錯誤；CLI 可用 code 映射退出結果。"""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _verify_personal_receipt(receipt: Mapping[str, Any], control_paths: WatchlistCowControlPaths | None) -> None:
    if control_paths is None or receipt.get("source_format") != JSON_SOURCE_FORMAT:
        return
    backup = _control_output(str(receipt.get("source_backup_path", "")), control_paths)
    if backup != control_paths.source_backup_path:
        raise WatchlistCowActivationError("control_source_backup_mismatch")
    if _sha256(backup) != receipt.get("source_sha256") or receipt.get("source_backup_sha256") != receipt.get("source_sha256"):
        raise WatchlistCowActivationError("source_backup_changed")


def _control_kwargs(control_paths: WatchlistCowControlPaths | None) -> dict[str, Any]:
    return {"control_paths": control_paths} if control_paths is not None else {}


def _activation_schema(control_paths: WatchlistCowControlPaths | None) -> str:
    return PERSONAL_ACTIVATION_SCHEMA if control_paths is not None else ACTIVATION_SCHEMA


def _control_output(path: str | Path, control_paths: WatchlistCowControlPaths | None) -> Path:
    if control_paths is None:
        return Path(path)
    try:
        return control_paths.assert_personal(path)
    except PersonalDataPathError as exc:
        raise WatchlistCowActivationError(exc.code, str(exc)) from exc


def _check_controls(source: str | Path, target: str | Path, receipt: str | Path | None,
                    control_paths: WatchlistCowControlPaths | None) -> None:
    if control_paths is None:
        return
    try:
        control_paths.validate(source, target, receipt)
        # 舊指向不自動搬移；明示新控制平面時避免兩套writer身分。
        if Path(source).suffix.lower() != ".json" and _legacy_json_sources(Path(source)):
            raise WatchlistCowActivationError("legacy_json_scope_requires_review")
        if Path(source).with_name(Path(source).name + ".cow-active.json").exists():
            raise WatchlistCowActivationError("legacy_control_marker_requires_review")
    except WatchlistCowActivationError:
        raise
    except PersonalDataPathError as exc:
        raise WatchlistCowActivationError(exc.code, str(exc)) from exc


    except (OSError, RuntimeError) as exc:
        raise WatchlistCowActivationError("control_path_unavailable", str(exc)) from exc

def cow_activation_marker_path(canonical_repository_path: str | Path, *, control_paths: WatchlistCowControlPaths | None = None) -> Path:
    """回傳與舊 `.active` 分離的 explicit COW 指向檔。"""

    if control_paths is not None:
        _check_controls(canonical_repository_path, control_paths.personal_paths.watchlist_db, None, control_paths)
        return _control_output(control_paths.marker_path, control_paths)
    path = Path(canonical_repository_path)
    return path.with_name(f"{path.name}.cow-active.json")


def watchlist_cow_activation_source_candidates(
    canonical_repository_path: str | Path,
    *, control_paths: WatchlistCowControlPaths | None = None,
) -> tuple[tuple[Path, Path], ...]:
    """列出 canonical SQLite 與目錄內 JSON COW marker 的來源候選。"""

    if control_paths is not None:
        _check_controls(control_paths.source_path, canonical_repository_path, None, control_paths)
        return ((control_paths.source_path, _control_output(control_paths.marker_path, control_paths)),)
    canonical = Path(canonical_repository_path).expanduser().resolve(strict=False)
    candidates: dict[Path, Path] = {canonical: cow_activation_marker_path(canonical, **_control_kwargs(control_paths))}
    suffix = ".cow-active.json"
    try:
        markers = canonical.parent.glob(f"*{suffix}")
        for marker in markers:
            if marker == candidates[canonical]:
                continue
            if not marker.name.endswith(suffix):
                continue
            source = marker.with_name(marker.name[: -len(suffix)])
            if source.suffix.lower() == ".json":
                resolved_source = source.resolve(strict=False)
                candidates[resolved_source] = marker
    except OSError:
        pass
    return tuple(sorted(candidates.items(), key=lambda item: str(item[0]).casefold()))


def cow_conversion_receipt_path(target_path: str | Path, *, control_paths: WatchlistCowControlPaths | None = None) -> Path:
    """回傳 converter 的 sibling receipt 預設路徑。"""

    if control_paths is not None:
        _check_controls(control_paths.source_path, target_path, None, control_paths)
        return _control_output(control_paths.receipt_path, control_paths)
    path = Path(target_path)
    return path.with_name(f"{path.name}.cow-conversion.v1.json")


def _resolved(path: str | Path, *, must_exist: bool = True) -> Path:
    value = Path(path).expanduser()
    try:
        return value.resolve(strict=must_exist)
    except (OSError, RuntimeError) as exc:
        raise WatchlistCowActivationError("path_unavailable", str(value)) from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise WatchlistCowActivationError("path_unreadable", str(path)) from exc
    return digest.hexdigest()


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _loads_strict_json(raw: bytes) -> Any:
    if len(raw) > 1024 * 1024:
        raise ValueError("JSON metadata exceeds 1 MiB")
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )


def _read_json(path: Path, code: str) -> tuple[dict[str, Any], bytes]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(1024 * 1024 + 1)
        payload = _loads_strict_json(raw)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise WatchlistCowActivationError(code, str(path)) from exc
    if not isinstance(payload, dict):
        raise WatchlistCowActivationError(code, "JSON root 必須是 object")
    return payload, raw


def _required_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise WatchlistCowActivationError("invalid_receipt", f"receipt {key} 必須是整數")
    return value


def _cancel_if_requested(cancel_check: _CancelCheck | None) -> None:
    if cancel_check is None:
        return
    try:
        cancelled = cancel_check()
    except Exception as exc:
        raise WatchlistCowActivationError("cancelled", "取消檢查失敗") from exc
    if cancelled:
        raise WatchlistCowActivationError("cancelled", "操作已取消")


def _sidecars(path: Path) -> tuple[Path, ...]:
    return tuple(path.with_name(path.name + suffix) for suffix in ("-wal", "-shm", "-journal"))


def _assert_no_sidecars(path: Path) -> None:
    present = [str(sidecar) for sidecar in _sidecars(path) if sidecar.exists()]
    if present:
        raise WatchlistCowActivationError("sqlite_sidecar_present", ", ".join(present))


def _assert_writable_directory(path: Path) -> None:
    parent = path.parent
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        raise WatchlistCowActivationError("readonly_config", str(parent))


def _assert_metadata_capacity(source: Path, target: Path, *payloads: bytes, control_paths: WatchlistCowControlPaths | None = None) -> None:
    """Recheck the current central reserve before publishing activation audit bytes."""
    try:
        from data_module.ml_storage_capacity import (
            evaluate_capacity, filesystem_usage, heavy_chain_capacity_budget,
        )
        persistent = source.stat().st_size + target.stat().st_size
        added = sum(len(raw) for raw in payloads)
        decision = evaluate_capacity(
            budget=heavy_chain_capacity_budget(), usage=filesystem_usage(target.parent if control_paths is not None else source.parent),
            stage="watchlist-cow-activation-metadata", persistent_existing_bytes=persistent,
            persistent_new_bytes_estimate=added, temporary_peak_bytes_observed=added + 8192,
        )
    except Exception as exc:
        raise WatchlistCowActivationError("capacity_unknown") from exc
    if getattr(decision, "within_budget", None) is not True:
        raise WatchlistCowActivationError("capacity_insufficient")


@contextmanager
def _sqlite_writer_locks(*paths: Path, control_paths: WatchlistCowControlPaths | None = None) -> Iterator[None]:
    """Keep reserved SQLite locks until the explicit marker is published."""

    unique = sorted({path.resolve() for path in paths}, key=lambda path: str(path).casefold())
    connections: list[sqlite3.Connection] = []
    try:
        for path in unique:
            _assert_no_sidecars(path)
            readonly_source = control_paths is not None and path == control_paths.source_path
            if control_paths is not None and not readonly_source:
                _control_output(path, control_paths)
            uri = f"{path.as_uri()}?mode={'ro' if readonly_source else 'rw'}"
            connection = sqlite3.connect(uri, uri=True, timeout=0, isolation_level=None)
            connections.append(connection)
            connection.execute("BEGIN" if readonly_source else "BEGIN IMMEDIATE")
            if readonly_source:
                connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
        for path in unique:
            _assert_no_sidecars(path)
        yield
    except WatchlistCowActivationError:
        raise
    except sqlite3.OperationalError as exc:
        message = str(exc).lower()
        if "locked" in message or "busy" in message:
            raise WatchlistCowActivationError("active_writer", str(paths[0])) from exc
        if "readonly" in message or "read-only" in message:
            raise WatchlistCowActivationError("readonly_config", str(paths[0])) from exc
        raise WatchlistCowActivationError("sqlite_unavailable", str(paths[0])) from exc
    except sqlite3.Error as exc:
        raise WatchlistCowActivationError("sqlite_unavailable", str(paths[0])) from exc
    finally:
        for connection in reversed(connections):
            try:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            connection.close()


def _assert_no_writer(path: Path, *, control_paths: WatchlistCowControlPaths | None = None) -> None:
    with _sqlite_writer_locks(path, **_control_kwargs(control_paths)):
        return


def _detect(path: Path, *, expected: set[int] | None = None) -> dict[str, Any]:
    detected = WatchlistRepository(path).detect_storage_format()
    schema = detected.get("schema_version")
    if detected.get("ready") is not True or not isinstance(schema, int):
        raise WatchlistCowActivationError("unknown_schema", str(path))
    if expected is not None and schema not in expected:
        raise WatchlistCowActivationError("unknown_schema", f"{path}: schema={schema}")
    return detected


def _source_stat_matches(receipt: Mapping[str, Any], source: Path) -> bool:
    expected = receipt.get("source_stat")
    if not isinstance(expected, Mapping):
        return False
    try:
        actual_stat = source.stat()
    except OSError:
        return False
    aliases: dict[str, int] = {
        "size": int(actual_stat.st_size),
        "size_bytes": int(actual_stat.st_size),
        "st_size": int(actual_stat.st_size),
        "mtime_ns": int(actual_stat.st_mtime_ns),
        "st_mtime_ns": int(actual_stat.st_mtime_ns),
        "inode": int(getattr(actual_stat, "st_ino", 0)),
        "st_ino": int(getattr(actual_stat, "st_ino", 0)),
        "device": int(getattr(actual_stat, "st_dev", 0)),
        "st_dev": int(getattr(actual_stat, "st_dev", 0)),
    }
    required = {"size", "mtime_ns", "inode", "device"}
    if not required.issubset(expected):
        return False
    return all(
        isinstance(expected[key], int)
        and not isinstance(expected[key], bool)
        and aliases[key] == expected[key]
        for key in required
    )


def _validate_receipt(
    source_path: Path,
    target_path: Path,
    receipt_path: Path | None,
    *,
    check_writers: bool = True,
    control_paths: WatchlistCowControlPaths | None = None,
) -> tuple[dict[str, Any], Path, str]:
    _check_controls(source_path, target_path, receipt_path, control_paths)
    source_input = Path(source_path).expanduser()
    target_input = Path(target_path).expanduser()
    if not source_input.exists():
        raise WatchlistCowActivationError("source_missing", str(source_input))
    if not target_input.exists():
        raise WatchlistCowActivationError("missing_target", str(target_input))
    if source_input.is_symlink() or target_input.is_symlink():
        raise WatchlistCowActivationError("path_alias", "source/target 不可為 symbolic link")
    source = _resolved(source_path)
    target = _resolved(target_path)
    receipt_input = Path(receipt_path).expanduser() if receipt_path is not None else cow_conversion_receipt_path(target, **_control_kwargs(control_paths))
    if not receipt_input.is_file():
        raise WatchlistCowActivationError("missing_receipt", str(receipt_input))
    receipt = _resolved(receipt_input, must_exist=True)
    if source == target:
        raise WatchlistCowActivationError("target_not_independent", str(target))
    if not source.is_file():
        raise WatchlistCowActivationError("source_unavailable", str(source))
    if not target.is_file():
        raise WatchlistCowActivationError("missing_target", str(target))
    for path in (source, target):
        try:
            file_stat = path.stat()
        except OSError as exc:
            raise WatchlistCowActivationError("path_unavailable", str(path)) from exc
        if getattr(file_stat, "st_nlink", 1) > 1:
            raise WatchlistCowActivationError("path_alias", str(path))
    payload, raw = _read_json(receipt, "invalid_receipt")
    _verify_personal_receipt(payload, control_paths)
    if payload.get("schema_version") != RECEIPT_SCHEMA or payload.get("status") != "ready":
        raise WatchlistCowActivationError("receipt_not_ready", str(receipt))
    if payload.get("source_path") != str(source) or payload.get("target_path") != str(target):
        raise WatchlistCowActivationError("receipt_path_mismatch", str(receipt))
    if payload.get("receipt_path") != str(receipt):
        raise WatchlistCowActivationError("receipt_path_mismatch", str(receipt))
    source_schema = _required_int(payload, "source_schema_version")
    target_schema = _required_int(payload, "target_schema_version")
    source_size = _required_int(payload, "source_size_bytes")
    target_size = _required_int(payload, "target_size_bytes")
    source_format = payload.get("source_format")
    if source_format not in (None, JSON_SOURCE_FORMAT):
        raise WatchlistCowActivationError("unknown_source_format", str(source_format))
    if target_schema != 3 or (source_format is None and source_schema not in {1, 2}) or (
        source_format == JSON_SOURCE_FORMAT and source_schema != 1
    ):
        raise WatchlistCowActivationError("unknown_schema", "receipt schema 不受支援")
    if source_format == JSON_SOURCE_FORMAT:
        if payload.get("canonical_path") != str(source):
            raise WatchlistCowActivationError("receipt_path_mismatch", "JSON canonical_path mismatch")
        _assert_json_source_scope(source, target)
        _assert_no_sidecars(target)
    else:
        _assert_no_sidecars(source)
        _assert_no_sidecars(target)
    _assert_writable_directory(target if control_paths is not None else source)
    if check_writers:
        if source_format is None:
            _assert_no_writer(source, **_control_kwargs(control_paths))
        _assert_no_writer(target, **_control_kwargs(control_paths))
    if source_format == JSON_SOURCE_FORMAT and source.stat().st_size != source_size:
        raise WatchlistCowActivationError("source_changed", str(source))
    if source.stat().st_size != source_size or target.stat().st_size != target_size:
        raise WatchlistCowActivationError("stale_hash", "source／target size 與 receipt 不同")
    source_hash = _sha256(source)
    target_hash = _sha256(target)
    if source_hash != payload.get("source_sha256"):
        raise WatchlistCowActivationError("source_changed", str(source))
    if target_hash != payload.get("target_sha256"):
        raise WatchlistCowActivationError("stale_hash", str(target))
    if not _source_stat_matches(payload, source):
        raise WatchlistCowActivationError("source_changed", "source stat identity 與 receipt 不同")
    if source_format is None and _detect(source, expected={1, 2}).get("schema_version") != source_schema:
        raise WatchlistCowActivationError("unknown_schema", "source schema 與 receipt 不同")
    _detect(target, expected={3})
    return payload, receipt, hashlib.sha256(raw).hexdigest()


def watchlist_cow_lineage_from_inventory(
    inventory: Mapping[str, Any],
    expected: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """由已取得的 bounded inventory 驗證 append-only base lineage。

    `lineage_sha256` 使用 inventory 已驗證的 revision chain_hash；不重建歷史
    payload，也不額外讀資料庫，讓既有 scanner 可以共用同一份演算法。
    """

    if (
        inventory.get("complete") is not True
        or inventory.get("schema_version") != 3
        or inventory.get("revision_chain_valid") is not True
        or inventory.get("delta_refs_valid") is not True
        or inventory.get("current_projection_valid") is not True
    ):
        raise WatchlistCowActivationError("target_history_invalid", "v3 bounded inventory 未完整通過")
    rows = inventory.get("watchlists")
    revisions = inventory.get("revisions")
    if not isinstance(rows, list) or not isinstance(revisions, list):
        raise WatchlistCowActivationError("target_history_invalid", "inventory 格式錯誤")
    known_ids = {
        str(row.get("watchlist_id", ""))
        for row in rows
        if isinstance(row, Mapping) and str(row.get("watchlist_id", ""))
    }
    chains: dict[str, list[Mapping[str, Any]]] = {watchlist_id: [] for watchlist_id in known_ids}
    for revision in revisions:
        if not isinstance(revision, Mapping):
            raise WatchlistCowActivationError("target_history_invalid", "revision row 格式錯誤")
        watchlist_id = str(revision.get("watchlist_id", ""))
        if watchlist_id not in chains:
            raise WatchlistCowActivationError("target_history_invalid", "revision 指向未知 watchlist")
        chains[watchlist_id].append(revision)

    result: dict[str, dict[str, Any]] = {}
    for watchlist_id, history in chains.items():
        history.sort(key=lambda row: int(row.get("revision", 0)))
        count = len(history)
        final_chain = str(history[-1].get("chain_hash", "")) if history else ""
        result[watchlist_id] = {"revision_count": count, "lineage_sha256": final_chain}
        if expected is None or watchlist_id not in expected:
            continue
        wanted = expected[watchlist_id]
        wanted_count = int(wanted.get("revision_count", -1))
        if wanted_count < 0 or count < wanted_count:
            raise WatchlistCowActivationError("target_lineage_mismatch", watchlist_id)
        base_chain = str(history[wanted_count - 1].get("chain_hash", "")) if wanted_count else ""
        if base_chain != wanted.get("lineage_sha256"):
            raise WatchlistCowActivationError("target_lineage_mismatch", watchlist_id)
    if expected is not None:
        missing = set(expected) - set(result)
        if missing:
            raise WatchlistCowActivationError("target_lineage_mismatch", ",".join(sorted(missing)))
    return result


def _history_prefixes(
    repository_path: Path,
    expected: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """以一次有界 v3 inventory 驗 schema、hash、refs、chain 與 current projection。"""

    repository = WatchlistRepository(repository_path)
    _detect(repository_path, expected={3})
    try:
        inventory = repository.get_item_storage_inventory()
    except Exception as exc:
        raise WatchlistCowActivationError("target_history_invalid", str(exc)) from exc
    return watchlist_cow_lineage_from_inventory(inventory, expected)


def _base_lineage_snapshot(target: Path) -> dict[str, dict[str, Any]]:
    current = _history_prefixes(target)
    return {
        watchlist_id: {
            "revision_count": int(row["revision_count"]),
            "lineage_sha256": str(row["lineage_sha256"]),
        }
        for watchlist_id, row in current.items()
    }


def _legacy_marker_path(source: Path) -> Path:
    return source.with_name(f"{source.name}.active")


def _legacy_json_sources(source: Path) -> tuple[Path, ...]:
    excluded = (".cow-conversion.v1.json", ".cow-active.json")
    return tuple(sorted(
        path.resolve()
        for path in source.parent.glob("*.json")
        if not path.name.endswith(excluded) and ".cow-rollback." not in path.name
    ))


def _assert_json_source_scope(source: Path, target: Path) -> None:
    """Refuse one-file COW when service discovery would omit JSON siblings."""

    canonical = source.parent / "watchlists.db"
    if canonical.exists():
        raise WatchlistCowActivationError("canonical_repository_exists", str(canonical))
    if target.resolve(strict=False) == canonical.resolve(strict=False):
        raise WatchlistCowActivationError("canonical_target_refused", str(target))
    if _legacy_json_sources(source) != (source.resolve(strict=True),):
        raise WatchlistCowActivationError(
            "source_scope_ambiguous",
            "JSON COW 僅支援目錄內唯一的 watchlist JSON；目前來源範圍不完整",
        )


def _legacy_marker_is_valid(raw: bytes | None) -> bool:
    if raw is None:
        return False
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") == "watchlist-activation.v1"
        and payload.get("status") == "complete"
        and isinstance(payload.get("source_hashes"), dict)
        and all(isinstance(key, str) and isinstance(value, str)
                for key, value in payload["source_hashes"].items())
    )


def _original_state(
    source: Path,
    source_schema: int,
    source_format: str | None = None,
    *, control_paths: WatchlistCowControlPaths | None = None,
) -> dict[str, Any]:
    marker_path = _legacy_marker_path(source)
    marker_raw = marker_path.read_bytes() if marker_path.is_file() else None
    json_sources = _legacy_json_sources(source)
    json_hashes = {str(path): _sha256(path) for path in json_sources}
    if source_format == JSON_SOURCE_FORMAT:
        mode = "legacy_json_v1"
    elif source_schema == 1:
        mode = "sqlite_v1_readonly"
    elif _legacy_marker_is_valid(marker_raw) or (marker_raw is None and not json_sources):
        mode = "sqlite_v2"
    else:
        mode = "legacy_json"
    return {
        "mode": mode,
        "repository_path": str(source) if mode.startswith("sqlite_") else None,
        "legacy_marker_path": str(marker_path),
        "legacy_marker_raw_b64": base64.b64encode(marker_raw).decode("ascii") if marker_raw is not None else None,
        "legacy_marker_sha256": hashlib.sha256(marker_raw).hexdigest() if marker_raw is not None else None,
        "legacy_json_sha256": json_hashes,
    }


def _backup_path(canonical: Path, activation_id: str, *, control_paths: WatchlistCowControlPaths | None = None) -> Path:
    if control_paths is not None:
        return _control_output(control_paths.backup_marker_path(activation_id), control_paths)
    return canonical.with_name(f"{canonical.name}.cow-rollback.{activation_id}.json")


def _lock_path(canonical: Path, *, control_paths: WatchlistCowControlPaths | None = None) -> Path:
    if control_paths is not None:
        return _control_output(control_paths.lock_path, control_paths)
    return canonical.with_name(f"{canonical.name}.cow-lock")


@contextmanager
def _marker_lock(canonical: Path, *, control_paths: WatchlistCowControlPaths | None = None) -> Iterator[None]:
    if control_paths is not None:
        _check_controls(canonical, control_paths.personal_paths.watchlist_db, None, control_paths)
    lock = _lock_path(canonical, **_control_kwargs(control_paths))
    token = uuid4().hex.encode("ascii")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise WatchlistCowActivationError("active_writer", "activation marker lock 已存在") from exc
    except OSError as exc:
        raise WatchlistCowActivationError("readonly_config", str(lock)) from exc
    try:
        os.write(descriptor, token)
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            if lock.read_bytes() == token:
                lock.unlink()
        except OSError:
            pass


@contextmanager
def watchlist_service_writer_guard(
    canonical_repository_path: str | Path,
    *,
    expected_marker_sha256: str | None,
    activation_source_path: str | Path | None = None,
    expected_target_path: str | Path | None = None,
    control_paths: WatchlistCowControlPaths | None = None,
) -> Iterator[None]:
    """Serialize service writes with COW pointers and pin active JSON sources."""

    if control_paths is not None:
        _check_controls(control_paths.source_path, canonical_repository_path, None, control_paths)
        if activation_source_path is not None and Path(activation_source_path) != control_paths.source_path:
            raise WatchlistCowActivationError("control_source_mismatch")
        activation_source_path = control_paths.source_path
        active = resolve_watchlist_sqlite_activation(control_paths.source_path, control_paths=control_paths)
        if active.get("status") != "active":
            raise WatchlistCowActivationError("personal_writer_disabled", str(active.get("code", active.get("status"))))
    canonical = _resolved(canonical_repository_path, must_exist=False)
    owner = _resolved(
        activation_source_path if activation_source_path is not None else canonical,
        must_exist=False,
    )
    marker_path = cow_activation_marker_path(owner, **_control_kwargs(control_paths))
    with _marker_lock(owner, **_control_kwargs(control_paths)):
        present_markers = [
            marker for _, marker in watchlist_cow_activation_source_candidates(canonical, **_control_kwargs(control_paths))
            if marker.exists()
        ]
        if len(present_markers) > 1:
            raise WatchlistCowActivationError("invalid_explicit_marker", "multiple COW markers found")
        if present_markers and present_markers[0] != marker_path:
            raise WatchlistCowActivationError("stale_service_pointer", str(present_markers[0]))
        if marker_path.exists():
            current, raw = _marker_payload(marker_path)
            source_format = current.get("source_format")
            if source_format not in (None, JSON_SOURCE_FORMAT):
                raise WatchlistCowActivationError("invalid_explicit_marker", "unknown source format")
            if (
                current.get("schema_version") != _activation_schema(control_paths)
                or current.get("canonical_path") != str(owner)
                or current.get("source_path") != str(owner)
                or current.get("status") not in {"active", "rolled_back"}
            ):
                raise WatchlistCowActivationError("invalid_explicit_marker", str(marker_path))
            if expected_marker_sha256 is None or hashlib.sha256(raw).hexdigest() != expected_marker_sha256:
                raise WatchlistCowActivationError("stale_service_pointer", str(marker_path))
            if expected_target_path is not None and current.get("status") == "active":
                if _resolved(str(current.get("target_path", ""))) != _resolved(expected_target_path):
                    raise WatchlistCowActivationError("stale_service_pointer", str(marker_path))
            if source_format == JSON_SOURCE_FORMAT and current.get("status") == "active":
                with _held_json_source(owner) as source_handle:
                    _verify_held_json_source(
                        source_handle,
                        source_path=owner,
                        expected_sha256=str(current.get("source_sha256", "")),
                        expected_size=_required_int(current, "source_size_bytes"),
                        expected_stat=current.get("source_stat"),
                    )
                    yield
                return
        elif expected_marker_sha256 is not None:
            raise WatchlistCowActivationError("stale_service_pointer", str(marker_path))
        yield


@contextmanager
def _held_json_source(path: Path) -> Iterator[Any]:
    """Hold the converter's cross-process read lock, excluding writes and renames."""

    try:
        from data_module.watchlist_json_cow import held_json_source
    except ImportError as exc:
        raise WatchlistCowActivationError("source_read_lock_unavailable", str(path)) from exc
    try:
        with held_json_source(path) as source_handle:
            yield source_handle
    except OSError as exc:
        raise WatchlistCowActivationError("source_read_lock_unavailable", str(path)) from exc


def _verify_held_json_source(
    source_handle: Any,
    *,
    source_path: Path,
    expected_sha256: str,
    expected_size: int,
    expected_stat: Any,
) -> None:
    try:
        source_handle.seek(0)
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = source_handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
        source_handle.seek(0)
        actual_stat = os.fstat(source_handle.fileno())
    except (OSError, AttributeError, ValueError) as exc:
        raise WatchlistCowActivationError("source_read_lock_unavailable", str(source_path)) from exc
    if size != expected_size or digest.hexdigest() != expected_sha256:
        raise WatchlistCowActivationError("source_changed", str(source_path))
    if not isinstance(expected_stat, Mapping):
        raise WatchlistCowActivationError("source_changed", "source stat pin missing")
    actual = {
        "size": int(actual_stat.st_size),
        "mtime_ns": int(actual_stat.st_mtime_ns),
        "inode": int(getattr(actual_stat, "st_ino", 0)),
        "device": int(getattr(actual_stat, "st_dev", 0)),
    }
    try:
        path_stat = source_path.stat()
    except OSError as exc:
        raise WatchlistCowActivationError("source_changed", str(source_path)) from exc
    path_identity = {
        "size": int(path_stat.st_size),
        "mtime_ns": int(path_stat.st_mtime_ns),
        "inode": int(getattr(path_stat, "st_ino", 0)),
        "device": int(getattr(path_stat, "st_dev", 0)),
    }
    if any(
        isinstance(expected_stat.get(key), bool)
        or not isinstance(expected_stat.get(key), int)
        or expected_stat[key] != actual[key]
        or actual[key] != path_identity[key]
        for key in actual
    ):
        raise WatchlistCowActivationError("source_changed", str(source_path))


def _atomic_create(path: Path, raw: bytes, *, control_paths: WatchlistCowControlPaths | None = None) -> None:
    _control_output(path, control_paths)
    if len(raw) > 1024 * 1024:
        raise WatchlistCowActivationError("marker_too_large", str(path))
    temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    _control_output(temporary, control_paths)
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise WatchlistCowActivationError("marker_changed", str(path)) from exc
    except OSError as exc:
        raise WatchlistCowActivationError("marker_publish_failed", str(path)) from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _atomic_replace(path: Path, raw: bytes, *, control_paths: WatchlistCowControlPaths | None = None) -> None:
    _control_output(path, control_paths)
    if len(raw) > 1024 * 1024:
        raise WatchlistCowActivationError("marker_too_large", str(path))
    temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    _control_output(temporary, control_paths)
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise WatchlistCowActivationError("marker_publish_failed", str(path)) from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _marker_payload(path: Path) -> tuple[dict[str, Any], bytes]:
    return _read_json(path, "invalid_explicit_marker")


def _validate_active_marker(canonical: Path, marker: Mapping[str, Any], *, control_paths: WatchlistCowControlPaths | None = None) -> dict[str, Any]:
    if marker.get("schema_version") != _activation_schema(control_paths):
        raise WatchlistCowActivationError("invalid_explicit_marker", "schema_version 不支援")
    if marker.get("canonical_path") != str(canonical):
        raise WatchlistCowActivationError("invalid_explicit_marker", "canonical path 不符")
    status = marker.get("status")
    if status not in {"active", "rolled_back"}:
        raise WatchlistCowActivationError("invalid_explicit_marker", "status 不支援")
    if control_paths is not None:
        _check_controls(str(marker.get("source_path", "")), str(marker.get("target_path", "")),
                        str(marker.get("receipt_path", "")), control_paths)
        expected_backup = control_paths.backup_marker_path(str(marker.get("activation_id", "")))
        if _control_output(str(marker.get("backup_marker_path", "")), control_paths) != expected_backup:
            raise WatchlistCowActivationError("control_backup_mismatch")
    source = _resolved(str(marker.get("source_path", "")))
    target = _resolved(str(marker.get("target_path", "")))
    source_format = marker.get("source_format")
    if source_format not in (None, JSON_SOURCE_FORMAT):
        raise WatchlistCowActivationError("invalid_explicit_marker", "unknown source format")
    if source != canonical:
        raise WatchlistCowActivationError("invalid_explicit_marker", "source 必須是 canonical repository path")
    backup_path = _resolved(str(marker.get("backup_marker_path", "")))
    backup, _ = _read_json(backup_path, "rollback_marker_invalid")
    backup_raw = backup_path.read_bytes()
    if hashlib.sha256(backup_raw).hexdigest() != marker.get("backup_marker_sha256"):
        raise WatchlistCowActivationError("rollback_marker_invalid", "rollback marker hash 不符")
    if backup.get("schema_version") != BACKUP_SCHEMA or backup.get("activation_id") != marker.get("activation_id"):
        raise WatchlistCowActivationError("rollback_marker_invalid", "rollback marker identity 不符")
    if backup.get("source_path") != str(source) or backup.get("target_path") != str(target):
        raise WatchlistCowActivationError("rollback_marker_invalid", "rollback marker paths 不符")
    if source_format == JSON_SOURCE_FORMAT and (
        backup.get("source_format") != JSON_SOURCE_FORMAT
        or backup.get("canonical_path") != str(source)
    ):
        raise WatchlistCowActivationError("rollback_marker_invalid", "JSON rollback source identity mismatch")
    original_state = backup.get("original_state")
    if not isinstance(original_state, Mapping):
        raise WatchlistCowActivationError("rollback_marker_invalid", "缺 original state")
    original_mode = _verify_original_state(
        source, original_state, verify_json=(status == "active" or original_state.get("mode") == "sqlite_v1_readonly"),
    **_control_kwargs(control_paths))
    receipt_path = _resolved(str(marker.get("receipt_path", "")))
    receipt, receipt_raw = _read_json(receipt_path, "invalid_receipt")
    _verify_personal_receipt(receipt, control_paths)
    if hashlib.sha256(receipt_raw).hexdigest() != marker.get("receipt_sha256"):
        raise WatchlistCowActivationError("invalid_receipt", "activation 後 receipt 改變")
    if (
        receipt.get("schema_version") != RECEIPT_SCHEMA
        or receipt.get("status") != "ready"
        or receipt.get("source_path") != str(source)
        or receipt.get("target_path") != str(target)
        or receipt.get("source_sha256") != marker.get("source_sha256")
        or receipt.get("target_sha256") != marker.get("prepared_target_sha256")
    ):
        raise WatchlistCowActivationError("invalid_receipt", "receipt pins 與 activation 不符")
    if receipt.get("source_format") != source_format:
        raise WatchlistCowActivationError("invalid_receipt", "receipt source format mismatch")
    if source_format == JSON_SOURCE_FORMAT and receipt.get("canonical_path") != str(source):
        raise WatchlistCowActivationError("invalid_receipt", "JSON receipt canonical path mismatch")
    if source_format == JSON_SOURCE_FORMAT and (
        marker.get("source_size_bytes") != receipt.get("source_size_bytes")
        or marker.get("source_stat") != receipt.get("source_stat")
        or backup.get("source_size_bytes") != receipt.get("source_size_bytes")
        or backup.get("source_stat") != receipt.get("source_stat")
    ):
        raise WatchlistCowActivationError("invalid_explicit_marker", "JSON source stat pins mismatch")
    if int(marker.get("source_schema_version", 0)) != int(receipt.get("source_schema_version", -1)):
        raise WatchlistCowActivationError("invalid_explicit_marker", "source schema pin 不一致")
    # active期間 source 必須逐 byte 不變；rollback 後 v2 已重新成為
    # 正常 writer，之後的合法 append 不會令 COW pointer 失效。
    if source_format == JSON_SOURCE_FORMAT:
        if (source.parent / "watchlists.db").exists():
            raise WatchlistCowActivationError(
                "canonical_repository_exists", str(source.parent / "watchlists.db")
            )
        if status == "active" or control_paths is not None:
            _assert_json_source_scope(source, target)
            if (
                _sha256(source) != marker.get("source_sha256")
                or not _source_stat_matches(receipt, source)
            ):
                raise WatchlistCowActivationError("source_changed", str(source))
    elif status == "active" or control_paths is not None or original_mode not in {"sqlite_v2", "legacy_json"}:
        if _sha256(source) != marker.get("source_sha256"):
            raise WatchlistCowActivationError("source_changed", str(source))
    if control_paths is not None and not _source_stat_matches(receipt, source):
        raise WatchlistCowActivationError("source_changed", "個人模式來源stat身分已變動")
    if source_format is None:
        _assert_no_sidecars(source)
    _assert_no_sidecars(target)
    if source_format is None:
        _assert_no_writer(source, **_control_kwargs(control_paths))
    _assert_no_writer(target, **_control_kwargs(control_paths))
    if source_format is None:
        _detect(source, expected={int(receipt.get("source_schema_version", 0))})
    _detect(target, expected={3})
    base = marker.get("target_base_lineage")
    if not isinstance(base, Mapping):
        raise WatchlistCowActivationError("invalid_explicit_marker", "缺 target base lineage")
    current_history = _history_prefixes(target, base)
    return {
        "status": status,
        "canonical_path": str(canonical),
        "source_format": source_format,
        "source_path": str(source),
        "target_path": str(target),
        "source_schema_version": int(receipt.get("source_schema_version", 0)),
        "receipt_path": str(receipt_path),
        "backup_marker_path": str(backup_path),
        "original_state": backup.get("original_state"),
        "schema_version": 3 if status == "active" else int(receipt.get("source_schema_version", 0)),
        "repository_path": str(target) if status == "active" else None,
        "mode": "sqlite_v3" if status == "active" else str((backup.get("original_state") or {}).get("mode", "blocked")),
        "activation_id": marker.get("activation_id"),
        "prepared_target_sha256": marker.get("prepared_target_sha256"),
        "target_revision_counts": {
            watchlist_id: int(row.get("revision_count", 0))
            for watchlist_id, row in current_history.items()
        },
    }


def resolve_watchlist_sqlite_activation(canonical_repository_path: str | Path, *, control_paths: WatchlistCowControlPaths | None = None) -> dict[str, Any]:
    """只讀解析 activation；明確 marker 損毀時回傳 blocked，絕不 fallback。"""

    try:
        if control_paths is not None:
            _check_controls(canonical_repository_path, control_paths.personal_paths.watchlist_db, None, control_paths)
        canonical = _resolved(canonical_repository_path, must_exist=False)
        marker_path = cow_activation_marker_path(canonical, **_control_kwargs(control_paths))
        if not marker_path.exists():
            return {"status": "inactive", "canonical_path": str(canonical), "marker_path": str(marker_path)}
        marker, raw = _marker_payload(marker_path)
        resolved = _validate_active_marker(canonical, marker, **_control_kwargs(control_paths))
        resolved["marker_path"] = str(marker_path)
        resolved["marker_sha256"] = hashlib.sha256(raw).hexdigest()
        return resolved
    except WatchlistCowActivationError as exc:
        return {
            "status": "blocked",
            "code": exc.code,
            "message": exc.detail or str(exc),
            "canonical_path": str(Path(canonical_repository_path).expanduser()),
            "marker_path": str(control_paths.marker_path if control_paths is not None else Path(canonical_repository_path).with_name(Path(canonical_repository_path).name + ".cow-active.json")),
        }
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "status": "blocked",
            "code": "invalid_explicit_marker",
            "message": str(exc),
            "canonical_path": str(Path(canonical_repository_path).expanduser()),
        }


def _preview(
    source: str | Path,
    target: str | Path,
    receipt_path: str | Path | None,
    *,
    check_writers: bool = True,
    control_paths: WatchlistCowControlPaths | None = None,
) -> dict[str, Any]:
    _check_controls(source, target, receipt_path, control_paths)
    source_resolved = _resolved(source)
    target_resolved = _resolved(target)
    receipt_resolved = _resolved(receipt_path) if receipt_path is not None else cow_conversion_receipt_path(target_resolved, **_control_kwargs(control_paths))
    current = resolve_watchlist_sqlite_activation(source_resolved, **_control_kwargs(control_paths))
    if current.get("status") == "blocked":
        raise WatchlistCowActivationError(str(current.get("code", "invalid_explicit_marker")), str(current.get("message", "")))
    if current.get("status") == "active":
        same = (
            current.get("source_path") == str(source_resolved)
            and current.get("target_path") == str(target_resolved)
            and current.get("receipt_path") == str(receipt_resolved)
        )
        if same:
            return {
                "status": "already_active",
                "source_path": str(source_resolved),
                "target_path": str(target_resolved),
                "receipt_path": str(receipt_resolved),
                "activation_id": current.get("activation_id"),
            }
        raise WatchlistCowActivationError("another_activation_active", str(current.get("target_path", "")))
    receipt, receipt_path_resolved, receipt_hash = _validate_receipt(
        source_resolved,
        target_resolved,
        receipt_resolved,
        check_writers=check_writers,
     **_control_kwargs(control_paths))
    lineage = _base_lineage_snapshot(target_resolved)
    source_schema = int(receipt["source_schema_version"])
    source_format = receipt.get("source_format")
    original = _original_state(source_resolved, source_schema, source_format, **_control_kwargs(control_paths))
    return {
        "status": "ready",
        "source_path": str(source_resolved),
        "target_path": str(target_resolved),
        "receipt_path": str(receipt_path_resolved),
        "receipt_sha256": receipt_hash,
        "source_sha256": str(receipt["source_sha256"]),
        "source_size_bytes": int(receipt["source_size_bytes"]),
        "source_stat": receipt.get("source_stat"),
        "source_format": source_format,
        "canonical_path": str(source_resolved),
        "target_size_bytes": int(receipt["target_size_bytes"]),
        "prepared_target_sha256": str(receipt["target_sha256"]),
        "source_schema_version": source_schema,
        "target_schema_version": 3,
        "target_base_lineage": lineage,
        "original_state": original,
        "revision_count": int(receipt.get("revision_count", 0)),
        "item_count": int(receipt.get("item_count", 0)),
        "comparison": receipt.get("comparison"),
    }


def _revalidate_json_activation_under_lock(
    source: Path, target: Path, receipt_path: Path, preview: Mapping[str, Any], source_handle: Any
,
    *, control_paths: WatchlistCowControlPaths | None = None,
) -> None:
    _verify_held_json_source(source_handle, source_path=source,
                            expected_sha256=str(preview["source_sha256"]),
                            expected_size=_required_int(preview, "source_size_bytes"),
                            expected_stat=preview.get("source_stat"))
    receipt, raw = _read_json(receipt_path, "invalid_receipt")
    if hashlib.sha256(raw).hexdigest() != preview.get("receipt_sha256"):
        raise WatchlistCowActivationError("receipt_changed", str(receipt_path))
    if receipt.get("source_format") != JSON_SOURCE_FORMAT or receipt.get("canonical_path") != str(source):
        raise WatchlistCowActivationError("invalid_receipt", "JSON source identity mismatch")
    if receipt.get("source_sha256") != preview.get("source_sha256") or receipt.get("target_sha256") != preview.get("prepared_target_sha256"):
        raise WatchlistCowActivationError("invalid_receipt", "source/target hash pin changed")
    if target.stat().st_size != _required_int(preview, "target_size_bytes") or _sha256(target) != preview.get("prepared_target_sha256"):
        raise WatchlistCowActivationError("stale_hash", str(target))
    _assert_json_source_scope(source, target)
    _detect(target, expected={3})
    if _base_lineage_snapshot(target) != preview.get("target_base_lineage"):
        raise WatchlistCowActivationError("target_lineage_mismatch", str(target))
    _verify_original_state(source, preview["original_state"], verify_json=False, **_control_kwargs(control_paths))


def preview_watchlist_sqlite_activation(
    source: str | Path,
    target: str | Path,
    *,
    receipt_path: str | Path | None = None,
    control_paths: WatchlistCowControlPaths | None = None,
) -> dict[str, Any]:
    """唯讀檢查 converter receipt、資料庫 pin、sidecar 與目前指向。"""

    try:
        return _preview(source, target, receipt_path, **_control_kwargs(control_paths))
    except WatchlistCowActivationError as exc:
        return {
            "status": "blocked",
            "code": exc.code,
            "message": exc.detail or str(exc),
            "source_path": str(Path(source).expanduser().resolve()),
            "target_path": str(Path(target).expanduser().resolve()),
        }


def _publish_activation_markers(
    source: Path,
    target: Path,
    preview: Mapping[str, Any],
    marker_path: Path,
    cancel_check: _CancelCheck | None,
    *, control_paths: WatchlistCowControlPaths | None = None,
) -> None:
    activation_id = uuid4().hex
    backup_path = _backup_path(source, activation_id, **_control_kwargs(control_paths))
    backup: dict[str, Any] = {
        "schema_version": BACKUP_SCHEMA,
        "activation_id": activation_id,
        "canonical_path": str(source),
        "source_path": str(source),
        "target_path": str(target),
        "original_state": preview["original_state"],
    }
    marker: dict[str, Any] = {
        "schema_version": _activation_schema(control_paths),
        "status": "active",
        "activation_id": activation_id,
        "canonical_path": str(source),
        "source_path": str(source),
        "target_path": str(target),
        "receipt_path": str(preview["receipt_path"]),
        "receipt_sha256": str(preview["receipt_sha256"]),
        "source_schema_version": int(preview["source_schema_version"]),
        "source_sha256": str(preview["source_sha256"]),
        "prepared_target_sha256": str(preview["prepared_target_sha256"]),
        "target_base_lineage": preview["target_base_lineage"],
        "backup_marker_path": str(backup_path),
    }
    if preview.get("source_format") is not None:
        source_format = str(preview["source_format"])
        backup["source_format"] = source_format
        backup["source_size_bytes"] = int(preview["source_size_bytes"])
        backup["source_stat"] = preview["source_stat"]
        marker["source_format"] = source_format
        marker["source_size_bytes"] = int(preview["source_size_bytes"])
        marker["source_stat"] = preview["source_stat"]
    backup_raw = json.dumps(backup, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    marker["backup_marker_sha256"] = hashlib.sha256(backup_raw).hexdigest()
    marker_raw = json.dumps(marker, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    _cancel_if_requested(cancel_check)
    _assert_metadata_capacity(source, target, backup_raw, marker_raw, **_control_kwargs(control_paths))
    _atomic_create(backup_path, backup_raw, **_control_kwargs(control_paths))
    _atomic_create(marker_path, marker_raw, **_control_kwargs(control_paths))


def activate_watchlist_sqlite(
    source: str | Path,
    target: str | Path,
    *,
    receipt_path: str | Path | None = None,
    cancel_check: _CancelCheck | None = None,
    control_paths: WatchlistCowControlPaths | None = None,
) -> dict[str, Any]:
    """Explicitly publish a COW marker after validating and pinning both databases."""

    _cancel_if_requested(cancel_check)
    if control_paths is not None:
        _check_controls(source, target, receipt_path, control_paths)
        control_paths.prepare_directories()
    initial = _preview(source, target, receipt_path, **_control_kwargs(control_paths))
    if initial.get("status") == "already_active":
        return initial
    canonical = Path(str(initial["source_path"]))
    target_path_resolved = Path(str(initial["target_path"]))
    marker_path = cow_activation_marker_path(canonical, **_control_kwargs(control_paths))
    _cancel_if_requested(cancel_check)
    with _marker_lock(canonical, **_control_kwargs(control_paths)):
        _cancel_if_requested(cancel_check)
        if marker_path.exists():
            current = resolve_watchlist_sqlite_activation(canonical, **_control_kwargs(control_paths))
            if current.get("status") == "active" and current.get("target_path") == str(target_path_resolved):
                return {**current, "status": "already_active"}
            if current.get("status") == "blocked":
                raise WatchlistCowActivationError(
                    str(current.get("code", "invalid_explicit_marker")),
                    str(current.get("message", "")),
                )
            raise WatchlistCowActivationError("another_activation_active", str(marker_path))
        if initial.get("source_format") == JSON_SOURCE_FORMAT:
            with _sqlite_writer_locks(target_path_resolved, **_control_kwargs(control_paths)):
                with _held_json_source(canonical) as source_handle:
                    _revalidate_json_activation_under_lock(
                        canonical,
                        target_path_resolved,
                        Path(str(initial["receipt_path"])),
                        initial,
                        source_handle,
                     **_control_kwargs(control_paths))
                    _cancel_if_requested(cancel_check)
                    _publish_activation_markers(
                        canonical, target_path_resolved, initial, marker_path, cancel_check,
                    **_control_kwargs(control_paths))
            resolved = resolve_watchlist_sqlite_activation(canonical, **_control_kwargs(control_paths))
            if resolved.get("status") != "active":
                raise WatchlistCowActivationError(
                    str(resolved.get("code", "marker_publish_failed")),
                    str(resolved.get("message", "")),
                )
            return {**resolved, "status": "activated"}

        with _sqlite_writer_locks(canonical, target_path_resolved, **_control_kwargs(control_paths)):
            # Recheck receipt and history only after both writers are excluded.
            preview = _preview(
                canonical,
                target_path_resolved,
                receipt_path,
                check_writers=False,
             **_control_kwargs(control_paths))
            if preview.get("status") != "ready":
                raise WatchlistCowActivationError("marker_changed", str(marker_path))
            _cancel_if_requested(cancel_check)
            _verify_original_state(canonical, preview["original_state"], verify_json=True, **_control_kwargs(control_paths))
            activation_id = uuid4().hex
            backup_path = _backup_path(canonical, activation_id, **_control_kwargs(control_paths))
            backup = {
                "schema_version": BACKUP_SCHEMA,
                "activation_id": activation_id,
                "source_path": str(canonical),
                "target_path": str(target_path_resolved),
                "original_state": preview["original_state"],
            }
            backup_raw = json.dumps(
                backup, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            marker = {
                "schema_version": _activation_schema(control_paths),
                "status": "active",
                "activation_id": activation_id,
                "canonical_path": str(canonical),
                "source_path": str(canonical),
                "target_path": str(target_path_resolved),
                "receipt_path": str(preview["receipt_path"]),
                "receipt_sha256": str(preview["receipt_sha256"]),
                "source_schema_version": int(preview["source_schema_version"]),
                "source_sha256": str(preview["source_sha256"]),
                "prepared_target_sha256": str(preview["prepared_target_sha256"]),
                "target_base_lineage": preview["target_base_lineage"],
                "backup_marker_path": str(backup_path),
                "backup_marker_sha256": hashlib.sha256(backup_raw).hexdigest(),
            }
            marker_raw = json.dumps(
                marker, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            _cancel_if_requested(cancel_check)
            _assert_metadata_capacity(canonical, target_path_resolved, backup_raw, marker_raw, **_control_kwargs(control_paths))
            _atomic_create(backup_path, backup_raw, **_control_kwargs(control_paths))
            _atomic_create(marker_path, marker_raw, **_control_kwargs(control_paths))
    resolved = resolve_watchlist_sqlite_activation(canonical, **_control_kwargs(control_paths))
    if resolved.get("status") != "active":
        raise WatchlistCowActivationError(
            str(resolved.get("code", "marker_publish_failed")),
            str(resolved.get("message", "")),
        )
    return {**resolved, "status": "activated"}


def _verify_original_state(
    source: Path, state: Mapping[str, Any], *, verify_json: bool = True
,
    control_paths: WatchlistCowControlPaths | None = None,
) -> str:
    if control_paths is not None:
        if state.get("legacy_marker_path") != str(_legacy_marker_path(source)):
            raise WatchlistCowActivationError("original_marker_path_mismatch")
        for value in state.get("legacy_json_sha256", {}):
            candidate = Path(str(value))
            if candidate.parent != source.parent:
                raise WatchlistCowActivationError("original_json_path_mismatch")
    mode = str(state.get("mode", ""))
    marker_path = _resolved(str(state.get("legacy_marker_path", source.with_name(source.name + ".active"))), must_exist=False)
    expected_marker = state.get("legacy_marker_raw_b64")
    current_marker = marker_path.read_bytes() if marker_path.is_file() else None
    if expected_marker is None:
        if current_marker is not None:
            raise WatchlistCowActivationError("original_marker_changed", str(marker_path))
    else:
        try:
            original_raw = base64.b64decode(str(expected_marker), validate=True)
        except (ValueError, TypeError) as exc:
            raise WatchlistCowActivationError("rollback_marker_invalid", "legacy marker bytes invalid") from exc
        if current_marker != original_raw:
            raise WatchlistCowActivationError("original_marker_changed", str(marker_path))
    expected_json = state.get("legacy_json_sha256", {})
    if not isinstance(expected_json, Mapping):
        raise WatchlistCowActivationError("rollback_marker_invalid", "legacy JSON pins invalid")
    if verify_json:
        for path_text, expected_hash in expected_json.items():
            path = _resolved(str(path_text))
            if _sha256(path) != expected_hash:
                raise WatchlistCowActivationError("original_source_changed", str(path))
    return mode


def _rollback_json_under_lock(
    canonical: Path,
    target: Path,
    marker_path: Path,
    marker_hash: str,
    activation_id: str,
    cancel_check: _CancelCheck | None,
    *, control_paths: WatchlistCowControlPaths | None = None,
) -> str:
    with _sqlite_writer_locks(target, **_control_kwargs(control_paths)):
        with _held_json_source(canonical) as source_handle:
            current, current_raw = _marker_payload(marker_path)
            if hashlib.sha256(current_raw).hexdigest() != marker_hash:
                raise WatchlistCowActivationError("marker_changed", str(marker_path))
            if current.get("status") != "active" or current.get("activation_id") != activation_id:
                raise WatchlistCowActivationError("marker_changed", str(marker_path))
            _verify_held_json_source(
                source_handle,
                source_path=canonical,
                expected_sha256=str(current.get("source_sha256", "")),
                expected_size=_required_int(current, "source_size_bytes"),
                expected_stat=current.get("source_stat"),
            )
            _assert_json_source_scope(canonical, target)
            backup_path = _resolved(str(current.get("backup_marker_path", "")))
            backup, backup_raw = _read_json(backup_path, "rollback_marker_invalid")
            if hashlib.sha256(backup_raw).hexdigest() != current.get("backup_marker_sha256"):
                raise WatchlistCowActivationError("rollback_marker_invalid", "rollback marker hash mismatch")
            state = backup.get("original_state")
            if not isinstance(state, Mapping):
                raise WatchlistCowActivationError("rollback_marker_invalid", "original state missing")
            mode = _verify_original_state(canonical, state, verify_json=False, **_control_kwargs(control_paths))
            if mode != "legacy_json_v1":
                raise WatchlistCowActivationError("rollback_mode_unknown", mode)
            receipt_path = _resolved(str(current.get("receipt_path", "")))
            receipt, receipt_raw = _read_json(receipt_path, "invalid_receipt")
            if (
                hashlib.sha256(receipt_raw).hexdigest() != current.get("receipt_sha256")
                or receipt.get("schema_version") != RECEIPT_SCHEMA
                or receipt.get("status") != "ready"
                or receipt.get("source_format") != JSON_SOURCE_FORMAT
                or receipt.get("canonical_path") != str(canonical)
                or receipt.get("source_sha256") != current.get("source_sha256")
                or receipt.get("target_sha256") != current.get("prepared_target_sha256")
                or receipt.get("source_schema_version") != 1
                or receipt.get("target_schema_version") != 3
            ):
                raise WatchlistCowActivationError("invalid_receipt", "JSON receipt pins changed")
            _detect(target, expected={3})
            base = current.get("target_base_lineage")
            if not isinstance(base, Mapping):
                raise WatchlistCowActivationError("invalid_explicit_marker", "target base lineage missing")
            _history_prefixes(target, base)
            _cancel_if_requested(cancel_check)
            current["status"] = "rolled_back"
            current["rollback_source_schema_version"] = 1
            current["rollback_source_format"] = JSON_SOURCE_FORMAT
            current["rollback_original_mode"] = mode
            current["rollback_marker_sha256"] = hashlib.sha256(backup_raw).hexdigest()
            replacement = json.dumps(current, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            _assert_metadata_capacity(canonical, target, replacement, **_control_kwargs(control_paths))
            _atomic_replace(marker_path, replacement, **_control_kwargs(control_paths))
            return mode


def rollback_watchlist_sqlite(
    source: str | Path,
    *,
    cancel_check: _CancelCheck | None = None,
    control_paths: WatchlistCowControlPaths | None = None,
) -> dict[str, Any]:
    """Atomically return to the pinned source mode without changing either database."""

    _cancel_if_requested(cancel_check)
    if control_paths is not None:
        _check_controls(source, control_paths.personal_paths.watchlist_db, None, control_paths)
    canonical = _resolved(source)
    marker_path = cow_activation_marker_path(canonical, **_control_kwargs(control_paths))
    if not marker_path.is_file():
        return {"status": "already_rolled_back", "canonical_path": str(canonical)}
    resolved = resolve_watchlist_sqlite_activation(canonical, **_control_kwargs(control_paths))
    if resolved.get("status") == "blocked":
        raise WatchlistCowActivationError(
            str(resolved.get("code", "invalid_explicit_marker")),
            str(resolved.get("message", "")),
        )
    if resolved.get("source_path") != str(canonical):
        raise WatchlistCowActivationError("source_mismatch", str(canonical))
    if resolved.get("status") == "rolled_back":
        return {**resolved, "status": "already_rolled_back"}

    target = _resolved(str(resolved["target_path"]))
    _cancel_if_requested(cancel_check)
    if resolved.get("source_format") == JSON_SOURCE_FORMAT:
        with _marker_lock(canonical, **_control_kwargs(control_paths)):
            current, current_raw = _marker_payload(marker_path)
            if hashlib.sha256(current_raw).hexdigest() != resolved.get("marker_sha256"):
                raise WatchlistCowActivationError("marker_changed", str(marker_path))
            if current.get("status") != "active" or current.get("activation_id") != resolved.get("activation_id"):
                raise WatchlistCowActivationError("marker_changed", str(marker_path))
            mode = _rollback_json_under_lock(
                canonical,
                target,
                marker_path,
                str(resolved.get("marker_sha256", "")),
                str(resolved.get("activation_id", "")),
                cancel_check,
             **_control_kwargs(control_paths))
        after = resolve_watchlist_sqlite_activation(canonical, **_control_kwargs(control_paths))
        if after.get("status") != "rolled_back":
            raise WatchlistCowActivationError(
                str(after.get("code", "rollback_failed")),
                str(after.get("message", "")),
            )
        return {**after, "status": "rolled_back", "original_mode": mode}

    with _marker_lock(canonical, **_control_kwargs(control_paths)):
        current, current_raw = _marker_payload(marker_path)
        if hashlib.sha256(current_raw).hexdigest() != resolved.get("marker_sha256"):
            raise WatchlistCowActivationError("marker_changed", str(marker_path))
        if current.get("status") != "active" or current.get("activation_id") != resolved.get("activation_id"):
            raise WatchlistCowActivationError("marker_changed", str(marker_path))
        with _sqlite_writer_locks(canonical, target, **_control_kwargs(control_paths)):
            # Repeat all mutable checks while both databases are write-locked.
            current, current_raw = _marker_payload(marker_path)
            if hashlib.sha256(current_raw).hexdigest() != resolved.get("marker_sha256"):
                raise WatchlistCowActivationError("marker_changed", str(marker_path))
            if current.get("status") != "active" or current.get("activation_id") != resolved.get("activation_id"):
                raise WatchlistCowActivationError("marker_changed", str(marker_path))
            source_sha = str(current.get("source_sha256", ""))
            if _sha256(canonical) != source_sha:
                raise WatchlistCowActivationError("source_changed", str(canonical))
            backup_path = _resolved(str(current.get("backup_marker_path", "")))
            backup, backup_raw = _read_json(backup_path, "rollback_marker_invalid")
            if hashlib.sha256(backup_raw).hexdigest() != current.get("backup_marker_sha256"):
                raise WatchlistCowActivationError("rollback_marker_invalid", "rollback marker hash mismatch")
            state = backup.get("original_state")
            if not isinstance(state, Mapping):
                raise WatchlistCowActivationError("rollback_marker_invalid", "original state missing")
            mode = _verify_original_state(canonical, state, verify_json=True, **_control_kwargs(control_paths))
            source_schema = int(current.get("source_schema_version", 0))
            if mode == "sqlite_v1_readonly":
                _detect(canonical, expected={1})
            elif mode == "sqlite_v2":
                _detect(canonical, expected={2})
            elif mode != "legacy_json":
                raise WatchlistCowActivationError("rollback_mode_unknown", mode)
            receipt_path = _resolved(str(current.get("receipt_path", "")))
            receipt, receipt_raw = _read_json(receipt_path, "invalid_receipt")
            if (
                hashlib.sha256(receipt_raw).hexdigest() != current.get("receipt_sha256")
                or receipt.get("schema_version") != RECEIPT_SCHEMA
                or receipt.get("status") != "ready"
                or receipt.get("source_sha256") != source_sha
                or receipt.get("target_sha256") != current.get("prepared_target_sha256")
                or receipt.get("source_schema_version") != source_schema
                or receipt.get("target_schema_version") != 3
            ):
                raise WatchlistCowActivationError("invalid_receipt", "receipt pins changed")
            _detect(target, expected={3})
            base = current.get("target_base_lineage")
            if not isinstance(base, Mapping):
                raise WatchlistCowActivationError("invalid_explicit_marker", "target base lineage missing")
            _history_prefixes(target, base)
            _cancel_if_requested(cancel_check)
            current["status"] = "rolled_back"
            current["rollback_source_schema_version"] = source_schema
            current["rollback_original_mode"] = mode
            current["rollback_marker_sha256"] = hashlib.sha256(backup_raw).hexdigest()
            replacement = json.dumps(
                current, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            _assert_metadata_capacity(canonical, target, replacement, **_control_kwargs(control_paths))
            _atomic_replace(marker_path, replacement, **_control_kwargs(control_paths))
    after = resolve_watchlist_sqlite_activation(canonical, **_control_kwargs(control_paths))
    if after.get("status") != "rolled_back":
        raise WatchlistCowActivationError(
            str(after.get("code", "rollback_failed")),
            str(after.get("message", "")),
        )
    return {**after, "status": "rolled_back", "original_mode": mode}


class PersonalWatchlistCowService:
    """供明示個人模式 caller 重開與保存；未接全域配置或 UI。"""

    def __init__(self, control_paths: WatchlistCowControlPaths) -> None:
        self.control_paths = control_paths
        self.status = resolve_watchlist_sqlite_activation(
            control_paths.source_path, control_paths=control_paths,
        )
        if self.status.get("status") != "active":
            raise WatchlistCowActivationError(
                "personal_writer_disabled", str(self.status.get("code", self.status.get("status"))),
            )
        self.repository = WatchlistRepository(control_paths.personal_paths.watchlist_db)

    def load(self, watchlist_id: str) -> tuple[dict[str, Any], int] | None:
        with watchlist_service_writer_guard(
            self.control_paths.personal_paths.watchlist_db,
            expected_marker_sha256=str(self.status["marker_sha256"]),
            expected_target_path=self.control_paths.personal_paths.watchlist_db,
            control_paths=self.control_paths,
        ):
            return self.repository.load(watchlist_id)

    def save(self, watchlist_id: str, payload: dict[str, Any], *, expected_revision: int) -> int:
        with watchlist_service_writer_guard(
            self.control_paths.personal_paths.watchlist_db,
            expected_marker_sha256=str(self.status["marker_sha256"]),
            expected_target_path=self.control_paths.personal_paths.watchlist_db,
            control_paths=self.control_paths,
        ):
            return self.repository.save(watchlist_id, payload, expected_revision=expected_revision)