"""可重建的研究名單歷史 manifest 索引與有界唯讀分頁。"""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid
from typing import Any, Literal

from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_LEGACY_MANIFEST_SCHEMA,
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
    DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES,
    DailyMarketSnapshotRepository,
    DailyMarketSnapshotVerificationError,
    canonical_snapshot_json_bytes,
    snapshot_manifest_relpath,
)


INDEX_SCHEMA_VERSION = "research-membership-history-index.v1"
POINTER_SCHEMA_VERSION = "research-membership-history-index-pointer.v1"
GENERATION_SCHEMA_VERSION = "research-membership-history-generation.v1"
CURSOR_SCHEMA_VERSION = "research-membership-history-cursor.v1"
MAX_MEMBERSHIP_HISTORY_PAGE_SIZE = 32
MAX_MEMBERSHIP_HISTORY_PAGE_JSON_BYTES = 32 * 1024 * 1024
MAX_MEMBERSHIP_HISTORY_PAGE_MANIFEST_BYTES = 32 * 1024 * 1024
MAX_MEMBERSHIP_HISTORY_CURSOR_BYTES = 16 * 1024
MAX_MEMBERSHIP_HISTORY_GENERATION_BYTES = 64 * 1024 * 1024
_SQLITE_PAGE_BYTES = 4096
_MAX_GENERATION_PAGES = MAX_MEMBERSHIP_HISTORY_GENERATION_BYTES // _SQLITE_PAGE_BYTES

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GENERATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_MANIFEST_FILE_RE = re.compile(r"^(?P<sha256>[0-9a-f]{64})\.json$")
_POINTER_FIELDS = {
    "schema_version",
    "generation_id",
    "generation_sha256",
    "source_fingerprint",
}
_GENERATION_FIELDS = {
    "schema_version",
    "generation_id",
    "generation_sha256",
    "generation_size_bytes",
    "generation_mtime_ns",
    "source_fingerprint",
    "source_path",
    "source_directory_stat",
    "manifest_count",
}
_CURSOR_FIELDS = {
    "schema_version",
    "generation_id",
    "generation_sha256",
    "source_fingerprint",
    "query_fingerprint",
    "current_pin",
    "anchor_decision_date",
    "anchor_published_at",
    "anchor_manifest_sha256",
    "cursor_sha256",
}


class MembershipHistoryIndexError(RuntimeError):
    """以穩定 reason 回報索引、來源或 cursor 無法安全使用。"""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class MembershipHistoryManifestRef:
    """索引與頁內 manifest 核驗後的不可變快照參照。"""

    manifest_sha256: str
    cohort_id: str
    decision_date: date
    manifest_identity_sha256: str
    published_at: datetime
    schema_version: str
    completeness: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_sha256": self.manifest_sha256,
            "cohort_id": self.cohort_id,
            "decision_date": self.decision_date.isoformat(),
            "manifest_identity_sha256": self.manifest_identity_sha256,
            "published_at": self.published_at.astimezone(timezone.utc).isoformat(),
            "schema_version": self.schema_version,
            "completeness": self.completeness,
        }


@dataclass(frozen=True, slots=True)
class MembershipHistoryIndexBuildResult:
    """已驗證並原子啟用的衍生索引 generation。"""

    generation_id: str
    source_fingerprint: str
    manifest_count: int
    activated: bool
    index_path: Path
    index_size_bytes: int
    retained_generation_count: int
    retained_generation_bytes: int


@dataclass(frozen=True, slots=True)
class MembershipHistoryPage:
    """固定 generation、current pin 與 query 的 manifest ref 分頁。"""

    generation_id: str
    source_fingerprint: str
    query_fingerprint: str
    current_pin: MembershipHistoryManifestRef
    refs: tuple[MembershipHistoryManifestRef, ...]
    has_more: bool
    next_cursor: str | None

    @property
    def history_coverage(self) -> Literal["complete", "truncated"]:
        """有下一頁代表實際截斷；資料量本身不代表歷史缺口。"""

        return "truncated" if self.has_more else "complete"

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation_id": self.generation_id,
            "source_fingerprint": self.source_fingerprint,
            "query_fingerprint": self.query_fingerprint,
            "current_pin": self.current_pin.to_dict(),
            "refs": [item.to_dict() for item in self.refs],
            "has_more": self.has_more,
            "next_cursor": self.next_cursor,
            "history_coverage": self.history_coverage,
        }


@dataclass(frozen=True, slots=True)
class _Generation:
    generation_id: str
    generation_sha256: str
    source_fingerprint: str
    source_path: str
    source_directory_stat: Mapping[str, int]
    manifest_count: int
    index_size_bytes: int
    index_path: Path


def default_membership_history_cache_root(source_dir: str | Path) -> Path:
    """回傳與 immutable snapshot root 並列的 local derivative cache 路徑。"""

    source = Path(source_dir).expanduser()
    if not source.name:
        raise ValueError("source_dir 必須有明確目錄名稱")
    return source.parent / f"{source.name}_membership_history_index"


def rebuild_membership_history_index(
    source_dir: str | Path,
    cache_dir: str | Path,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> MembershipHistoryIndexBuildResult:
    """逐一核驗 manifests，建立新 SQLite generation 並原子啟用。"""

    source_path, manifest_directory, initial_directory_stat = _source_paths(source_dir)
    cache_root = _prepare_cache_root(cache_dir, source_path, create=True)
    try:
        generations_dir = cache_root / "generations"
        if _is_redirect_path(generations_dir):
            raise MembershipHistoryIndexError("unsafe_cache_path", "generations 不可為 symlink/junction。")
        generations_dir.mkdir(exist_ok=True)
    except OSError as exc:
        raise MembershipHistoryIndexError("corrupt", "無法建立索引 cache 目錄") from exc

    with _writer_lock(cache_root):
        _check_cancel(cancel_check)
        generation_id = uuid.uuid4().hex
        generation_path = generations_dir / f"{generation_id}.sqlite"
        staging_path = generations_dir / f".building-{generation_id}.sqlite"
        connection: sqlite3.Connection | None = None
        manifest_count = 0
        try:
            connection = sqlite3.connect(staging_path)
            connection.execute(f"PRAGMA page_size={_SQLITE_PAGE_BYTES}")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(f"PRAGMA max_page_count={_MAX_GENERATION_PAGES}")
            connection.execute("PRAGMA user_version=1")
            _create_index_schema(connection)
            with connection:
                for manifest_path, manifest_sha256, _manifest_stat in _iter_manifest_paths(
                    manifest_directory
                ):
                    _check_cancel(cancel_check)
                    manifest_ref = _read_manifest_metadata(
                        source_path,
                        manifest_path,
                        manifest_sha256,
                    )
                    connection.execute(
                        """INSERT INTO manifests (
                               manifest_sha256, cohort_id, decision_date,
                               published_at, manifest_identity_sha256,
                               schema_version, completeness
                           ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            manifest_ref.manifest_sha256,
                            manifest_ref.cohort_id,
                            manifest_ref.decision_date.isoformat(),
                            _datetime_key(manifest_ref.published_at),
                            manifest_ref.manifest_identity_sha256,
                            manifest_ref.schema_version,
                            manifest_ref.completeness,
                        ),
                    )
                    manifest_count += 1
            if manifest_count == 0:
                raise MembershipHistoryIndexError(
                    "empty", "manifest 歷史目錄沒有可建立索引的快照。"
                )
            _check_cancel(cancel_check)
            final_directory_stat = _directory_stat(manifest_directory)
            if final_directory_stat != initial_directory_stat:
                raise MembershipHistoryIndexError(
                    "source_changed", "重建期間 manifests 目錄已變更。"
                )
            source_key = _source_key(source_path)
            source_fingerprint = _source_fingerprint(
                source_key,
                initial_directory_stat,
                manifest_count,
            )
            _write_metadata(
                connection,
                {
                    "schema_version": INDEX_SCHEMA_VERSION,
                    "generation_id": generation_id,
                    "state": "complete",
                    "source_fingerprint": source_fingerprint,
                    "source_path": source_key,
                    "source_directory_stat": _canonical_json(initial_directory_stat),
                    "manifest_count": str(manifest_count),
                },
            )
            check_rows = connection.execute("PRAGMA quick_check(1)").fetchall()
            if check_rows != [("ok",)]:
                raise MembershipHistoryIndexError("corrupt", "SQLite generation 完整性檢查失敗。")
            connection.commit()
            connection.close()
            connection = None
            _fsync_file(staging_path)
            os.replace(staging_path, generation_path)
            _fsync_directory(generations_dir)
            generation_stat = generation_path.stat()
            if generation_stat.st_size > MAX_MEMBERSHIP_HISTORY_GENERATION_BYTES:
                raise MembershipHistoryIndexError(
                    "index_budget_exceeded", "SQLite generation 超過 64 MiB 上限。"
                )
            generation_sha256 = _sha256_file(generation_path, cancel_check=cancel_check)
            generation_record = {
                "schema_version": GENERATION_SCHEMA_VERSION,
                "generation_id": generation_id,
                "generation_sha256": generation_sha256,
                "generation_size_bytes": generation_stat.st_size,
                "generation_mtime_ns": generation_stat.st_mtime_ns,
                "source_fingerprint": source_fingerprint,
                "source_path": source_key,
                "source_directory_stat": initial_directory_stat,
                "manifest_count": manifest_count,
            }
            _write_atomic_json(
                generations_dir / f"{generation_id}.json",
                generation_record,
            )
            retained_count, retained_bytes = _retained_generation_totals(generations_dir)
            latest_source_path, latest_manifest_directory, latest_directory_stat = _source_paths(
                source_dir
            )
            _require_source_unchanged(
                latest_source_path,
                latest_manifest_directory,
                latest_directory_stat,
                _open_generation(cache_root, generation_record),
            )
            _check_cancel(cancel_check)
            _write_active_pointer(cache_root, generation_record)
            return MembershipHistoryIndexBuildResult(
                generation_id=generation_id,
                source_fingerprint=source_fingerprint,
                manifest_count=manifest_count,
                activated=True,
                index_path=generation_path,
                index_size_bytes=generation_stat.st_size,
                retained_generation_count=retained_count,
                retained_generation_bytes=retained_bytes,
            )
        except MembershipHistoryIndexError:
            raise
        except (OSError, sqlite3.Error, TypeError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, sqlite3.Error) and getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL:
                raise MembershipHistoryIndexError(
                    "index_budget_exceeded", "SQLite generation 達到 64 MiB 上限；舊 active generation 保留。"
                ) from exc
            raise MembershipHistoryIndexError(
                "partial_update", "索引 generation 未完整建立或啟用；舊 active generation 保留。"
            ) from exc
        finally:
            if connection is not None:
                connection.close()


def read_membership_history_page(
    source_dir: str | Path,
    cache_dir: str | Path,
    *,
    cohort: str,
    as_of: datetime,
    current_pin: str,
    date_from: date | None = None,
    date_to: date | None = None,
    page_size: int = MAX_MEMBERSHIP_HISTORY_PAGE_SIZE,
    cursor: str | None = None,
    direction: Literal["older"] = "older",
    cancel_check: Callable[[], bool] | None = None,
) -> MembershipHistoryPage:
    """讀取固定 generation 中最近一頁，並嚴格重核頁內 manifest refs。"""

    normalized_cohort = _validate_cohort(cohort)
    normalized_as_of = _normalize_as_of(as_of)
    normalized_pin = _validate_sha256(current_pin, "current_pin")
    if isinstance(page_size, bool) or not isinstance(page_size, int):
        raise ValueError("page_size 必須是 1 至 32 的整數")
    if page_size < 1 or page_size > MAX_MEMBERSHIP_HISTORY_PAGE_SIZE:
        raise ValueError("page_size 必須是 1 至 32 的整數")
    if direction != "older":
        raise ValueError("direction 目前只支援 older")
    normalized_from = _validate_optional_date(date_from, "date_from")
    normalized_to = _validate_optional_date(date_to, "date_to")
    if normalized_from is not None and normalized_to is not None and normalized_from > normalized_to:
        raise ValueError("date_from 不可晚於 date_to")

    _check_cancel(cancel_check)
    source_path, manifest_directory, current_directory_stat = _source_paths(source_dir)
    cache_root = _prepare_cache_root(cache_dir, source_path, create=False)
    cursor_value = _decode_cursor(cursor) if cursor is not None else None
    if cursor_value is None:
        generation_record = _read_active_generation(cache_root, cancel_check=cancel_check)
    else:
        generation_record = _read_generation_record(
            cache_root,
            str(cursor_value["generation_id"]),
            cancel_check=cancel_check,
        )
        if (
            generation_record["generation_sha256"]
            != cursor_value["generation_sha256"]
        ):
            raise MembershipHistoryIndexError("invalid_cursor", "cursor 的 generation hash 不符。")

    generation = _open_generation(cache_root, generation_record)
    _require_source_unchanged(
        source_path,
        manifest_directory,
        current_directory_stat,
        generation,
    )
    connection = _connect_readonly(generation.index_path)
    try:
        _validate_database(connection, generation)
        pin_row = _fetch_manifest_row(connection, normalized_pin)
        if pin_row is None:
            raise MembershipHistoryIndexError(
                "invalid_current_pin", "current_pin 不存在於固定 generation。"
            )
        pin_ref = _row_to_ref(pin_row)
        if pin_ref.cohort_id != normalized_cohort:
            raise MembershipHistoryIndexError(
                "invalid_current_pin", "current_pin cohort 與查詢不同。"
            )
        if pin_ref.published_at > normalized_as_of:
            raise MembershipHistoryIndexError(
                "invalid_current_pin", "current_pin 在指定 as_of 之後才發布。"
            )
        effective_to = normalized_to or pin_ref.decision_date
        if effective_to > pin_ref.decision_date:
            raise ValueError("date_to 不可晚於 current_pin.decision_date")
        if normalized_from is not None and normalized_from > pin_ref.decision_date:
            raise ValueError("date_from 不可晚於 current_pin.decision_date")

        query_fingerprint = _query_fingerprint(
            cohort=normalized_cohort,
            as_of=normalized_as_of,
            current_pin=normalized_pin,
            date_from=normalized_from,
            date_to=effective_to,
            page_size=page_size,
            direction=direction,
        )
        if cursor_value is not None:
            _validate_cursor_binding(
                cursor_value,
                generation=generation,
                query_fingerprint=query_fingerprint,
                current_pin=normalized_pin,
            )
        raw_rows = _select_page_rows(
            connection,
            cohort=normalized_cohort,
            as_of=normalized_as_of,
            date_from=normalized_from,
            date_to=effective_to,
            page_size=page_size,
            anchor=cursor_value,
        )
        _check_cancel(cancel_check)
        if cursor_value is not None and not raw_rows:
            raise MembershipHistoryIndexError(
                "invalid_cursor", "cursor 沒有對應的較舊頁面。"
            )
        has_more = len(raw_rows) > page_size
        selected_rows = raw_rows[:page_size]
        refs = tuple(_row_to_ref(row) for row in reversed(selected_rows))
        total_manifest_bytes = 0
        verified_by_hash: dict[str, MembershipHistoryManifestRef] = {}
        for ref in (pin_ref, *refs):
            _check_cancel(cancel_check)
            if ref.manifest_sha256 in verified_by_hash:
                continue
            verified_ref, manifest_bytes = _verify_manifest_ref(
                source_path,
                ref,
            )
            total_manifest_bytes += manifest_bytes
            if total_manifest_bytes > MAX_MEMBERSHIP_HISTORY_PAGE_MANIFEST_BYTES:
                raise MembershipHistoryIndexError(
                    "page_budget_exceeded", "頁內 manifest 驗證超過 32 MiB 上限。"
                )
            if verified_ref != ref:
                raise MembershipHistoryIndexError(
                    "source_changed", "頁內 manifest metadata 與索引 generation 不符。"
                )
            verified_by_hash[ref.manifest_sha256] = verified_ref
            _check_cancel(cancel_check)
        _require_source_unchanged(
            source_path,
            manifest_directory,
            _directory_stat(manifest_directory),
            generation,
        )
        next_cursor = None
        if has_more and selected_rows:
            oldest_row = selected_rows[-1]
            next_cursor = _encode_cursor(
                generation=generation,
                query_fingerprint=query_fingerprint,
                current_pin=normalized_pin,
                anchor_decision_date=str(oldest_row["decision_date"]),
                anchor_published_at=str(oldest_row["published_at"]),
                anchor_manifest_sha256=str(oldest_row["manifest_sha256"]),
            )
        page = MembershipHistoryPage(
            generation_id=generation.generation_id,
            source_fingerprint=generation.source_fingerprint,
            query_fingerprint=query_fingerprint,
            current_pin=verified_by_hash[normalized_pin],
            refs=tuple(verified_by_hash[item.manifest_sha256] for item in refs),
            has_more=has_more,
            next_cursor=next_cursor,
        )
        if len(_canonical_json(page.to_dict()).encode("utf-8")) > MAX_MEMBERSHIP_HISTORY_PAGE_JSON_BYTES:
            raise MembershipHistoryIndexError(
                "page_budget_exceeded", "頁面 JSON 超過 32 MiB 上限。"
            )
        return page
    except MembershipHistoryIndexError:
        raise
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MembershipHistoryIndexError("corrupt", "索引資料或頁內來源無法核驗。") from exc
    finally:
        connection.close()


def rollback_membership_history_index(
    source_dir: str | Path,
    cache_dir: str | Path,
    *,
    generation_id: str,
) -> MembershipHistoryIndexBuildResult:
    """明確將 active pointer 回復至 cache 內已完成且來源仍匹配的 generation。"""

    _validate_generation_id(generation_id)
    source_path, manifest_directory, current_directory_stat = _source_paths(source_dir)
    cache_root = _prepare_cache_root(cache_dir, source_path, create=False)
    generations_dir = cache_root / "generations"
    generation_record = _read_generation_record(cache_root, generation_id)
    generation = _open_generation(cache_root, generation_record)
    _require_source_unchanged(
        source_path,
        manifest_directory,
        current_directory_stat,
        generation,
    )
    actual_hash = _sha256_file(generation.index_path)
    if actual_hash != generation.generation_sha256:
        raise MembershipHistoryIndexError("corrupt", "rollback generation hash 不符。")
    connection = _connect_readonly(generation.index_path)
    try:
        _validate_database(connection, generation)
        integrity = [tuple(row) for row in connection.execute("PRAGMA quick_check(1)").fetchall()]
        if integrity != [("ok",)]:
            raise MembershipHistoryIndexError("corrupt", "rollback generation 完整性檢查失敗。")
    finally:
        connection.close()
    with _writer_lock(cache_root):
        latest_source_path, latest_manifest_directory, latest_directory_stat = _source_paths(source_dir)
        _require_source_unchanged(
            latest_source_path,
            latest_manifest_directory,
            latest_directory_stat,
            generation,
        )
        retained_count, retained_bytes = _retained_generation_totals(generations_dir)
        _write_active_pointer(cache_root, generation_record)
    return MembershipHistoryIndexBuildResult(
        generation_id=generation.generation_id,
        source_fingerprint=generation.source_fingerprint,
        manifest_count=generation.manifest_count,
        activated=True,
        index_path=generation.index_path,
        index_size_bytes=generation.index_size_bytes,
        retained_generation_count=retained_count,
        retained_generation_bytes=retained_bytes,
    )


def _create_index_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE metadata (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)"
    )
    connection.execute(
        """CREATE TABLE manifests (
               manifest_sha256 TEXT PRIMARY KEY NOT NULL,
               cohort_id TEXT NOT NULL,
               decision_date TEXT NOT NULL,
               published_at TEXT NOT NULL,
               manifest_identity_sha256 TEXT NOT NULL,
               schema_version TEXT NOT NULL,
               completeness TEXT NOT NULL
           )"""
    )
    connection.execute(
        "CREATE INDEX manifests_query_order ON manifests "
        "(cohort_id, decision_date, published_at, manifest_sha256)"
    )


def _write_metadata(connection: sqlite3.Connection, values: Mapping[str, str]) -> None:
    connection.executemany(
        "INSERT INTO metadata (key, value) VALUES (?, ?)",
        tuple(values.items()),
    )


def _iter_manifest_paths(
    manifest_directory: Path,
) -> Iterator[tuple[Path, str, os.stat_result]]:
    try:
        with os.scandir(manifest_directory) as entries:
            for entry in entries:
                match = _MANIFEST_FILE_RE.fullmatch(entry.name)
                try:
                    entry_stat = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise MembershipHistoryIndexError(
                        "partial_update", "manifest 目錄在掃描期間發生變更。"
                    ) from exc
                if (
                    match is None
                    or stat.S_ISLNK(entry_stat.st_mode)
                    or not stat.S_ISREG(entry_stat.st_mode)
                ):
                    raise MembershipHistoryIndexError(
                        "unsupported_manifest_schema",
                        "manifest 目錄含有不符合 immutable hash 檔名契約的項目。",
                    )
                yield Path(entry.path), match.group("sha256"), entry_stat
    except MembershipHistoryIndexError:
        raise
    except OSError as exc:
        raise MembershipHistoryIndexError("partial_update", "無法完整列舉 manifests 目錄。") from exc


def _read_manifest_metadata(
    source_path: Path,
    manifest_path: Path,
    manifest_sha256: str,
) -> MembershipHistoryManifestRef:
    raw, manifest = _read_manifest_json(source_path, manifest_path)
    if hashlib.sha256(raw).hexdigest() != manifest_sha256:
        raise MembershipHistoryIndexError("source_changed", "manifest 內容 hash 與 immutable 檔名不符。")
    try:
        if canonical_snapshot_json_bytes(manifest) != raw:
            raise MembershipHistoryIndexError("corrupt", "manifest JSON 不是 canonical bytes。")
    except (TypeError, ValueError) as exc:
        raise MembershipHistoryIndexError("corrupt", "manifest JSON 無法 canonicalize。") from exc
    return _validate_manifest_metadata(source_path, manifest_path, manifest_sha256, manifest)


def _validate_manifest_metadata(
    source_path: Path,
    manifest_path: Path,
    manifest_sha256: str,
    manifest: Mapping[str, Any],
) -> MembershipHistoryManifestRef:
    schema_version = manifest.get("schema_version")
    if schema_version == DAILY_MARKET_SNAPSHOT_LEGACY_MANIFEST_SCHEMA:
        raise MembershipHistoryIndexError(
            "unsupported_manifest_schema",
            "manifest v1 缺少目前 reader 要求的方法契約；不做隱性遷移。",
        )
    if schema_version != DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA:
        raise MembershipHistoryIndexError(
            "unsupported_manifest_schema", "manifest schema 不受目前 snapshot reader 支援。"
        )
    cohort_id = manifest.get("cohort_id")
    raw_date = manifest.get("decision_date")
    if not isinstance(cohort_id, str) or not cohort_id.strip() or not isinstance(raw_date, str):
        raise MembershipHistoryIndexError("corrupt", "manifest 缺少 cohort/date metadata。")
    try:
        decision_date = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise MembershipHistoryIndexError("corrupt", "manifest decision_date 格式錯誤。") from exc
    repository = DailyMarketSnapshotRepository(source_path)
    try:
        repository._validate_manifest(
            dict(manifest),
            cohort_id=cohort_id,
            decision_date=decision_date,
            expected_codes=None,
        )
    except (DailyMarketSnapshotVerificationError, OSError, TypeError, ValueError) as exc:
        raise MembershipHistoryIndexError(
            "corrupt", "manifest metadata 未通過 snapshot reader 驗證。"
        ) from exc
    identity_sha256 = manifest.get("manifest_identity_sha256")
    if not isinstance(identity_sha256, str) or _SHA256_RE.fullmatch(identity_sha256) is None:
        raise MembershipHistoryIndexError("corrupt", "manifest identity hash 格式錯誤。")
    published_at = _parse_aware_datetime(manifest.get("published_at"))
    return MembershipHistoryManifestRef(
        manifest_sha256=manifest_sha256,
        cohort_id=cohort_id,
        decision_date=decision_date,
        manifest_identity_sha256=identity_sha256,
        published_at=published_at,
        schema_version=str(schema_version),
        completeness=str(manifest.get("completeness")),
    )


def _read_manifest_json(source_path: Path, manifest_path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        if _is_redirect_path(manifest_path):
            raise MembershipHistoryIndexError("corrupt", "manifest 不可為 symlink。")
        resolved = manifest_path.resolve(strict=True)
        manifests_root = (source_path / "manifests").resolve(strict=True)
        resolved.relative_to(manifests_root)
        file_stat = resolved.stat()
        if not stat.S_ISREG(file_stat.st_mode):
            raise MembershipHistoryIndexError("corrupt", "manifest 必須是一般檔案。")
        with resolved.open("rb") as stream:
            raw = stream.read(DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES + 1)
    except MembershipHistoryIndexError:
        raise
    except (OSError, ValueError) as exc:
        raise MembershipHistoryIndexError("source_changed", "manifest 在核驗期間消失或超出來源目錄。") from exc
    if len(raw) > DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES:
        raise MembershipHistoryIndexError("corrupt", "manifest 超過既有 reader byte 上限。")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MembershipHistoryIndexError("corrupt", "manifest JSON 無效。") from exc
    if not isinstance(value, dict):
        raise MembershipHistoryIndexError("corrupt", "manifest JSON root 必須是 object。")
    return raw, value


def _verify_manifest_ref(
    source_path: Path,
    expected: MembershipHistoryManifestRef,
) -> tuple[MembershipHistoryManifestRef, int]:
    try:
        relpath = Path(snapshot_manifest_relpath(expected.manifest_sha256))
    except ValueError as exc:
        raise MembershipHistoryIndexError("corrupt", "索引 manifest hash 格式無效。") from exc
    raw, manifest = _read_manifest_json(source_path, source_path / relpath)
    if hashlib.sha256(raw).hexdigest() != expected.manifest_sha256:
        raise MembershipHistoryIndexError("source_changed", "頁內 manifest hash 已改變。")
    if canonical_snapshot_json_bytes(manifest) != raw:
        raise MembershipHistoryIndexError("corrupt", "頁內 manifest 不是 canonical JSON。")
    verified = _validate_manifest_metadata(
        source_path,
        source_path / relpath,
        expected.manifest_sha256,
        manifest,
    )
    return verified, len(raw)


def _read_active_generation(
    cache_root: Path,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if not cache_root.exists():
        raise MembershipHistoryIndexError("missing", "尚未建立研究名單歷史索引。")
    pointer_path = cache_root / "active.json"
    if _is_redirect_path(pointer_path):
        raise MembershipHistoryIndexError("unsafe_cache_path", "active pointer cannot be a symlink or junction")
    if not pointer_path.exists():
        raise MembershipHistoryIndexError("missing", "尚未啟用研究名單歷史索引。")
    pointer = _read_json_object(pointer_path, max_bytes=16 * 1024)
    if pointer.get("schema_version") != POINTER_SCHEMA_VERSION:
        raise MembershipHistoryIndexError("unsupported_index_schema", "active pointer schema 不受支援。")
    if set(pointer) != _POINTER_FIELDS:
        raise MembershipHistoryIndexError("corrupt", "active pointer 欄位不符合索引 v1 契約。")
    generation_id = _validate_generation_id(pointer.get("generation_id"))
    generation_record = _read_generation_record(
        cache_root,
        generation_id,
        cancel_check=cancel_check,
    )
    for key in ("generation_sha256", "source_fingerprint"):
        if pointer.get(key) != generation_record.get(key):
            raise MembershipHistoryIndexError("corrupt", "active pointer 與 generation metadata 不一致。")
    return generation_record


def _read_generation_record(
    cache_root: Path,
    generation_id: str,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    _validate_generation_id(generation_id)
    generations_dir = cache_root / "generations"
    if _is_redirect_path(generations_dir):
        raise MembershipHistoryIndexError("unsafe_cache_path", "generations 不可為 symlink/junction。")
    record_path = generations_dir / f"{generation_id}.json"
    index_path = generations_dir / f"{generation_id}.sqlite"
    if _is_redirect_path(record_path) or _is_redirect_path(index_path):
        raise MembershipHistoryIndexError("unsafe_cache_path", "generation files 不可為 symlink/junction。")
    if not record_path.is_file() or not index_path.is_file():
        raise MembershipHistoryIndexError("corrupt", "active generation 缺少完成檔或 SQLite 索引。")
    record = _read_json_object(record_path, max_bytes=16 * 1024)
    if record.get("schema_version") != GENERATION_SCHEMA_VERSION:
        raise MembershipHistoryIndexError("unsupported_index_schema", "generation schema 不受支援。")
    if set(record) != _GENERATION_FIELDS:
        raise MembershipHistoryIndexError("corrupt", "generation metadata 欄位不符合 v1 契約。")
    if record.get("generation_id") != generation_id:
        raise MembershipHistoryIndexError("corrupt", "generation metadata id 不符。")
    for key in ("generation_sha256", "source_fingerprint"):
        _validate_sha256(record.get(key), key)
    for key in ("generation_size_bytes", "generation_mtime_ns", "manifest_count"):
        if type(record.get(key)) is not int or record[key] < 0:
            raise MembershipHistoryIndexError("corrupt", f"generation metadata {key} 無效。")
    if record["manifest_count"] < 1:
        raise MembershipHistoryIndexError("empty", "generation 沒有 manifest refs。")
    if record["generation_size_bytes"] > MAX_MEMBERSHIP_HISTORY_GENERATION_BYTES:
        raise MembershipHistoryIndexError("index_budget_exceeded", "generation 超過 64 MiB 上限。")
    source_path = record.get("source_path")
    directory_stat = record.get("source_directory_stat")
    if not isinstance(source_path, str) or not source_path or not _valid_directory_stat(directory_stat):
        raise MembershipHistoryIndexError("corrupt", "generation source metadata 無效。")
    file_stat = index_path.stat()
    if (
        file_stat.st_size != record["generation_size_bytes"]
        or file_stat.st_mtime_ns != record["generation_mtime_ns"]
    ):
        raise MembershipHistoryIndexError("corrupt", "generation SQLite file stat 與 seal 不符。")
    actual_hash = _sha256_file(index_path, cancel_check=cancel_check)
    if actual_hash != record["generation_sha256"]:
        raise MembershipHistoryIndexError("corrupt", "generation SQLite hash 與 seal 不符。")
    return record


def _open_generation(cache_root: Path, record: Mapping[str, Any]) -> _Generation:
    generation_id = str(record["generation_id"])
    _validate_generation_id(generation_id)
    index_path = cache_root / "generations" / f"{generation_id}.sqlite"
    source_stat = record["source_directory_stat"]
    assert isinstance(source_stat, Mapping)
    return _Generation(
        generation_id=generation_id,
        generation_sha256=str(record["generation_sha256"]),
        source_fingerprint=str(record["source_fingerprint"]),
        source_path=str(record["source_path"]),
        source_directory_stat={key: int(value) for key, value in source_stat.items()},
        manifest_count=int(record["manifest_count"]),
        index_size_bytes=int(record["generation_size_bytes"]),
        index_path=index_path,
    )


def _connect_readonly(path: Path) -> sqlite3.Connection:
    try:
        uri = path.resolve(strict=True).as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise MembershipHistoryIndexError("corrupt", "無法唯讀開啟索引 generation。") from exc


def _validate_database(connection: sqlite3.Connection, generation: _Generation) -> None:
    try:
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    except sqlite3.Error as exc:
        raise MembershipHistoryIndexError("corrupt", "索引 SQLite schema 無效。") from exc
    if user_version != 1 or metadata.get("schema_version") != INDEX_SCHEMA_VERSION:
        raise MembershipHistoryIndexError("unsupported_index_schema", "索引 SQLite schema 不受支援。")
    if (
        metadata.get("generation_id") != generation.generation_id
        or metadata.get("state") != "complete"
        or metadata.get("source_fingerprint") != generation.source_fingerprint
        or metadata.get("source_path") != generation.source_path
        or metadata.get("manifest_count") != str(generation.manifest_count)
    ):
        raise MembershipHistoryIndexError("corrupt", "索引 SQLite metadata 與 seal 不一致。")
    try:
        stat_payload = json.loads(metadata["source_directory_stat"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise MembershipHistoryIndexError("corrupt", "索引 source stat metadata 無效。") from exc
    if stat_payload != dict(generation.source_directory_stat):
        raise MembershipHistoryIndexError("corrupt", "索引 source stat metadata 與 seal 不一致。")


def _fetch_manifest_row(
    connection: sqlite3.Connection,
    manifest_sha256: str,
) -> sqlite3.Row | None:
    try:
        return connection.execute(
            "SELECT manifest_sha256, cohort_id, decision_date, published_at, "
            "manifest_identity_sha256, schema_version, completeness "
            "FROM manifests WHERE manifest_sha256 = ?",
            (manifest_sha256,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise MembershipHistoryIndexError("corrupt", "無法讀取 current pin metadata。") from exc


def _row_to_ref(row: sqlite3.Row) -> MembershipHistoryManifestRef:
    try:
        return MembershipHistoryManifestRef(
            manifest_sha256=str(row["manifest_sha256"]),
            cohort_id=str(row["cohort_id"]),
            decision_date=date.fromisoformat(str(row["decision_date"])),
            manifest_identity_sha256=str(row["manifest_identity_sha256"]),
            published_at=_parse_aware_datetime(row["published_at"]),
            schema_version=str(row["schema_version"]),
            completeness=str(row["completeness"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MembershipHistoryIndexError("corrupt", "索引 manifest metadata row 無效。") from exc


def _select_page_rows(
    connection: sqlite3.Connection,
    *,
    cohort: str,
    as_of: datetime,
    date_from: date | None,
    date_to: date,
    page_size: int,
    anchor: Mapping[str, Any] | None,
) -> list[sqlite3.Row]:
    conditions = [
        "cohort_id = ?",
        "published_at <= ?",
        "decision_date <= ?",
    ]
    parameters: list[Any] = [cohort, _datetime_key(as_of), date_to.isoformat()]
    if date_from is not None:
        conditions.append("decision_date >= ?")
        parameters.append(date_from.isoformat())
    if anchor is not None:
        conditions.append(
            "(decision_date < ? OR (decision_date = ? AND published_at < ?) "
            "OR (decision_date = ? AND published_at = ? AND manifest_sha256 < ?))"
        )
        anchor_date = str(anchor["anchor_decision_date"])
        anchor_published = str(anchor["anchor_published_at"])
        anchor_sha = str(anchor["anchor_manifest_sha256"])
        parameters.extend(
            [anchor_date, anchor_date, anchor_published, anchor_date, anchor_published, anchor_sha]
        )
    query = (
        "SELECT manifest_sha256, cohort_id, decision_date, published_at, "
        "manifest_identity_sha256, schema_version, completeness FROM manifests WHERE "
        + " AND ".join(conditions)
        + " ORDER BY decision_date DESC, published_at DESC, manifest_sha256 DESC LIMIT ?"
    )
    parameters.append(page_size + 1)
    try:
        return connection.execute(query, tuple(parameters)).fetchall()
    except sqlite3.Error as exc:
        raise MembershipHistoryIndexError("corrupt", "歷史分頁 SQL 查詢失敗。") from exc


def _require_source_unchanged(
    source_path: Path,
    manifest_directory: Path,
    current_directory_stat: Mapping[str, int],
    generation: _Generation,
) -> None:
    if _source_key(source_path) != generation.source_path:
        raise MembershipHistoryIndexError("source_changed", "查詢使用的 source_dir 與索引不同。")
    if dict(current_directory_stat) != dict(generation.source_directory_stat):
        raise MembershipHistoryIndexError("source_changed", "manifests 目錄 stat 與索引 generation 不同。")
    expected_fingerprint = _source_fingerprint(
        generation.source_path,
        current_directory_stat,
        generation.manifest_count,
    )
    if expected_fingerprint != generation.source_fingerprint:
        raise MembershipHistoryIndexError("source_changed", "來源指紋與索引 generation 不同。")


def _is_redirect_path(path: Path) -> bool:
    """Reject symlinks, Windows junctions, and other reparse points."""

    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        path_stat = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(path_stat, "st_file_attributes", 0) & reparse_flag)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath((os.path.normcase(str(path)), os.path.normcase(str(parent)))) == os.path.normcase(str(parent))
    except (OSError, ValueError):
        return False


def _prepare_cache_root(cache_dir: str | Path, source_path: Path, *, create: bool) -> Path:
    raw_root = Path(cache_dir).expanduser()
    if _is_redirect_path(raw_root):
        raise MembershipHistoryIndexError("unsafe_cache_path", "cache root cannot be a symlink or junction")
    try:
        cache_root = raw_root.resolve(strict=False)
        resolved_source = source_path.resolve(strict=True)
    except OSError as exc:
        raise MembershipHistoryIndexError("unsafe_cache_path", "cannot resolve cache/source path") from exc
    if cache_root == resolved_source or _is_within(cache_root, resolved_source):
        raise MembershipHistoryIndexError("unsafe_cache_path", "cache root cannot equal or be inside snapshot source")

    if create:
        try:
            cache_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise MembershipHistoryIndexError("partial_update", "cannot create derived cache root") from exc
    if _is_redirect_path(cache_root):
        raise MembershipHistoryIndexError("unsafe_cache_path", "cache root cannot be a symlink or junction")
    if not cache_root.is_dir():
        raise MembershipHistoryIndexError("missing", "membership history cache root does not exist")

    generations_dir = cache_root / "generations"
    if _is_redirect_path(generations_dir):
        raise MembershipHistoryIndexError("unsafe_cache_path", "generations cannot be a symlink or junction")
    if create:
        try:
            generations_dir.mkdir(exist_ok=True)
        except OSError as exc:
            raise MembershipHistoryIndexError("partial_update", "cannot create generations directory") from exc
    elif not generations_dir.is_dir():
        raise MembershipHistoryIndexError("missing", "membership history generations are missing")
    if _is_redirect_path(generations_dir):
        raise MembershipHistoryIndexError("unsafe_cache_path", "generations cannot be a symlink or junction")
    return cache_root


def _retained_generation_totals(generations_dir: Path) -> tuple[int, int]:
    count = 0
    total_bytes = 0
    try:
        for path in generations_dir.iterdir():
            if _GENERATION_ID_RE.fullmatch(path.stem) is None or path.suffix != ".sqlite":
                continue
            if _is_redirect_path(path):
                raise MembershipHistoryIndexError("unsafe_cache_path", "generation file cannot be a symlink or junction")
            item_stat = path.stat()
            if not stat.S_ISREG(item_stat.st_mode):
                raise MembershipHistoryIndexError("corrupt", "generation path is not a regular file")
            count += 1
            total_bytes += item_stat.st_size
    except MembershipHistoryIndexError:
        raise
    except OSError as exc:
        raise MembershipHistoryIndexError("corrupt", "cannot measure retained generations") from exc
    return count, total_bytes


def _source_paths(source_dir: str | Path) -> tuple[Path, Path, dict[str, int]]:
    source = Path(source_dir).expanduser()
    if _is_redirect_path(source):
        raise MembershipHistoryIndexError("source_changed", "source_dir 不可為 symlink。")
    try:
        source_path = source.resolve(strict=True)
        source_stat = source_path.stat()
        manifest_directory = source_path / "manifests"
        if not stat.S_ISDIR(source_stat.st_mode) or _is_redirect_path(manifest_directory):
            raise MembershipHistoryIndexError("source_changed", "snapshot root/manifests 不是一般目錄。")
        manifest_directory = manifest_directory.resolve(strict=True)
        manifest_stat = manifest_directory.stat()
        if not stat.S_ISDIR(manifest_stat.st_mode):
            raise MembershipHistoryIndexError("source_changed", "manifests 不是一般目錄。")
    except MembershipHistoryIndexError:
        raise
    except OSError as exc:
        raise MembershipHistoryIndexError("source_changed", "無法定位 snapshot manifests 目錄。") from exc
    return source_path, manifest_directory, _stat_payload(manifest_stat)


def _directory_stat(manifest_directory: Path) -> dict[str, int]:
    try:
        if _is_redirect_path(manifest_directory):
            raise MembershipHistoryIndexError("source_changed", "manifests 目錄不可為 symlink。")
        return _stat_payload(manifest_directory.stat())
    except MembershipHistoryIndexError:
        raise
    except OSError as exc:
        raise MembershipHistoryIndexError("source_changed", "無法讀取 manifests 目錄 stat。") from exc


def _stat_payload(value: os.stat_result) -> dict[str, int]:
    return {
        "device": int(value.st_dev),
        "inode": int(value.st_ino),
        "mode": int(stat.S_IFMT(value.st_mode)),
        "size": int(value.st_size),
        "modified_ns": int(value.st_mtime_ns),
        "changed_ns": int(value.st_ctime_ns),
        "links": int(value.st_nlink),
    }


def _valid_directory_stat(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value)
        == {"device", "inode", "mode", "size", "modified_ns", "changed_ns", "links"}
        and all(type(item) is int and item >= 0 for item in value.values())
    )


def _source_key(source_path: Path) -> str:
    return os.path.normcase(str(source_path.resolve(strict=True)))


def _source_fingerprint(
    source_path: str,
    source_stat: Mapping[str, int],
    manifest_count: int,
) -> str:
    return _sha256_bytes(
        _canonical_json(
            {
                "source_path": source_path,
                "source_directory_stat": dict(source_stat),
                "manifest_count": manifest_count,
            }
        ).encode("utf-8")
    )


def _query_fingerprint(
    *,
    cohort: str,
    as_of: datetime,
    current_pin: str,
    date_from: date | None,
    date_to: date,
    page_size: int,
    direction: str,
) -> str:
    payload = {
        "cohort": cohort,
        "as_of": _datetime_key(as_of),
        "current_pin": current_pin,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat(),
        "page_size": page_size,
        "direction": direction,
    }
    return _sha256_bytes(_canonical_json(payload).encode("utf-8"))


def _encode_cursor(
    *,
    generation: _Generation,
    query_fingerprint: str,
    current_pin: str,
    anchor_decision_date: str,
    anchor_published_at: str,
    anchor_manifest_sha256: str,
) -> str:
    payload: dict[str, Any] = {
        "schema_version": CURSOR_SCHEMA_VERSION,
        "generation_id": generation.generation_id,
        "generation_sha256": generation.generation_sha256,
        "source_fingerprint": generation.source_fingerprint,
        "query_fingerprint": query_fingerprint,
        "current_pin": current_pin,
        "anchor_decision_date": anchor_decision_date,
        "anchor_published_at": anchor_published_at,
        "anchor_manifest_sha256": anchor_manifest_sha256,
    }
    payload["cursor_sha256"] = _sha256_bytes(_canonical_json(payload).encode("utf-8"))
    encoded = base64.urlsafe_b64encode(_canonical_json(payload).encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _decode_cursor(cursor: str) -> dict[str, Any]:
    if not isinstance(cursor, str) or not cursor or len(cursor) > MAX_MEMBERSHIP_HISTORY_CURSOR_BYTES:
        raise MembershipHistoryIndexError("invalid_cursor", "cursor 格式或長度無效。")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise MembershipHistoryIndexError("invalid_cursor", "cursor 編碼或 JSON 無效。") from exc
    if not isinstance(decoded, dict) or set(decoded) != _CURSOR_FIELDS:
        raise MembershipHistoryIndexError("invalid_cursor", "cursor 欄位不符合 v1 契約。")
    if decoded.get("schema_version") != CURSOR_SCHEMA_VERSION:
        raise MembershipHistoryIndexError("invalid_cursor", "cursor schema 不受支援。")
    claimed_hash = decoded.get("cursor_sha256")
    payload = {key: value for key, value in decoded.items() if key != "cursor_sha256"}
    if not isinstance(claimed_hash, str) or _sha256_bytes(_canonical_json(payload).encode("utf-8")) != claimed_hash:
        raise MembershipHistoryIndexError("invalid_cursor", "cursor checksum 不符。")
    try:
        _validate_generation_id(decoded.get("generation_id"))
        for field in (
            "generation_sha256",
            "source_fingerprint",
            "query_fingerprint",
            "current_pin",
            "anchor_manifest_sha256",
        ):
            _validate_sha256(decoded.get(field), field)
    except MembershipHistoryIndexError as exc:
        raise MembershipHistoryIndexError(
            "invalid_cursor", "cursor contains invalid identity/hash fields"
        ) from exc
    try:
        date.fromisoformat(decoded["anchor_decision_date"])
        _parse_aware_datetime(decoded["anchor_published_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MembershipHistoryIndexError("invalid_cursor", "cursor anchor 無效。") from exc
    return decoded


def _validate_cursor_binding(
    cursor: Mapping[str, Any],
    *,
    generation: _Generation,
    query_fingerprint: str,
    current_pin: str,
) -> None:
    if (
        cursor.get("generation_id") != generation.generation_id
        or cursor.get("generation_sha256") != generation.generation_sha256
        or cursor.get("source_fingerprint") != generation.source_fingerprint
    ):
        raise MembershipHistoryIndexError("invalid_cursor", "cursor 不屬於目前 source/generation。")
    if cursor.get("query_fingerprint") != query_fingerprint or cursor.get("current_pin") != current_pin:
        raise MembershipHistoryIndexError("invalid_cursor", "cursor 不屬於目前 cohort/as_of/date/query。")


def _write_active_pointer(cache_root: Path, generation_record: Mapping[str, Any]) -> None:
    pointer = {
        "schema_version": POINTER_SCHEMA_VERSION,
        "generation_id": generation_record["generation_id"],
        "generation_sha256": generation_record["generation_sha256"],
        "source_fingerprint": generation_record["source_fingerprint"],
    }
    _write_atomic_json(cache_root / "active.json", pointer)


def _write_atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    if _is_redirect_path(path):
        raise MembershipHistoryIndexError("unsafe_cache_path", "index metadata cannot be a symlink or junction")
    raw = _canonical_json(value).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise MembershipHistoryIndexError("partial_update", "active pointer 未能原子發布。") from exc


@contextmanager
def _writer_lock(cache_root: Path) -> Iterator[None]:
    lock_path = cache_root / "writer.lock"
    if _is_redirect_path(lock_path):
        raise MembershipHistoryIndexError("unsafe_cache_path", "writer lock cannot be a symlink or junction")
    try:
        handle = lock_path.open("a+b")
    except OSError as exc:
        raise MembershipHistoryIndexError("partial_update", "cannot open writer lock") from exc
    locked = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl = __import__("fcntl")

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except (ImportError, OSError) as exc:
            raise MembershipHistoryIndexError("index_busy", "另一個索引 writer 正在執行。") from exc
        yield
    finally:
        if locked:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl = __import__("fcntl")

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass
        handle.close()


def _read_json_object(path: Path, *, max_bytes: int) -> dict[str, Any]:
    try:
        if _is_redirect_path(path) or not path.is_file():
            raise MembershipHistoryIndexError("corrupt", "索引 pointer/metadata 不是一般檔案。")
        with path.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
    except MembershipHistoryIndexError:
        raise
    except OSError as exc:
        raise MembershipHistoryIndexError("corrupt", "無法讀取索引 pointer/metadata。") from exc
    if len(raw) > max_bytes:
        raise MembershipHistoryIndexError("corrupt", "索引 pointer/metadata 超過 byte 上限。")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MembershipHistoryIndexError("corrupt", "索引 pointer/metadata JSON 無效。") from exc
    if not isinstance(value, dict):
        raise MembershipHistoryIndexError("corrupt", "索引 pointer/metadata root 必須是 object。")
    return value


def _validate_generation_id(value: Any) -> str:
    if not isinstance(value, str) or _GENERATION_ID_RE.fullmatch(value) is None:
        raise MembershipHistoryIndexError("corrupt", "generation id 格式無效。")
    return value


def _validate_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise MembershipHistoryIndexError("corrupt", f"{field} 格式不是 SHA256。")
    return value


def _validate_cohort(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("cohort 必須是非空字串")
    return value.strip()


def _validate_optional_date(value: date | None, field: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValueError(f"{field} 必須是 date")
    return value


def _normalize_as_of(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of 必須是 timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _parse_aware_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise MembershipHistoryIndexError("corrupt", "manifest published_at 缺少 aware timestamp。")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MembershipHistoryIndexError("corrupt", "manifest timestamp 格式錯誤。") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MembershipHistoryIndexError("corrupt", "manifest timestamp 必須是 timezone-aware。")
    return parsed.astimezone(timezone.utc)


def _datetime_key(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(
    path: Path,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while True:
                _check_cancel(cancel_check)
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise MembershipHistoryIndexError("corrupt", "無法計算 generation SQLite hash。") from exc
    return digest.hexdigest()


def _check_cancel(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check is None:
        return
    try:
        cancelled = cancel_check()
    except Exception as exc:
        raise MembershipHistoryIndexError("cancelled", "取消狀態不明，停止索引重建。") from exc
    if cancelled:
        raise MembershipHistoryIndexError("cancelled", "索引重建已取消，舊 active generation 保留。")


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDWR)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
