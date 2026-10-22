"""以有界不可變產物記錄 Forward 計算實際讀取的資料列。"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable, Mapping, Sequence


SCHEMA_VERSION = "forward-source-observations.v1"
CHUNK_SCHEMA_VERSION = "forward-source-observation-chunk.v1"
MAX_CHUNK_BYTES = 512 * 1024
MAX_MANIFEST_BYTES = 512 * 1024
MAX_RUN_BYTES = 64 * 1024 * 1024
MAX_RETAINED_BYTES = 12 * 1024 * 1024 * 1024
MAX_RETAINED_RUNS = 4096
MAX_QUERIES = 4096
MAX_ROWS = 500_000
MAX_CHUNKS = 128
MAX_OUTCOMES = 10_000
_RUN_ID = re.compile(r"\d{8}T\d{12}Z\Z")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class ForwardSourceObservationError(ValueError):
    """無法安全擷取或持久化 Forward 讀取證據。"""


ArtifactWriter = Callable[[Path, str], None]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _json_value(value: Any) -> Any:
    if value is None or type(value) in {str, int, bool}:
        return value
    if type(value) is float:
        if value != value or value in {float("inf"), float("-inf")}:
            raise ForwardSourceObservationError("source_observation_non_finite_value")
        return {"type": "sqlite_float", "value": repr(value)}
    if isinstance(value, bytes):
        return {
            "type": "sqlite_blob_base64",
            "value": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ForwardSourceObservationError("source_observation_mapping_key_invalid")
        return {key: _json_value(item) for key, item in value.items()}
    raise ForwardSourceObservationError("source_observation_value_type_unsupported")


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _validate_directory(path: Path) -> None:
    info = _lstat(path)
    if info is None or not stat.S_ISDIR(info.st_mode) or _is_reparse(info):
        raise ForwardSourceObservationError("source_observation_directory_invalid")


def _ensure_child_directory(root: Path, relative: Path) -> Path:
    current = root
    for part in relative.parts:
        if part in {"", ".", ".."}:
            raise ForwardSourceObservationError("source_observation_path_invalid")
        current = current / part
        info = _lstat(current)
        if info is None:
            try:
                current.mkdir()
            except FileExistsError:
                pass
            except OSError as exc:
                raise ForwardSourceObservationError(
                    "source_observation_directory_create_failed"
                ) from exc
        _validate_directory(current)
    return current


class ForwardSourceObservationRecorder:
    """在 reader fetch 邊界收集原始資料列並發布 run manifest。

    產物只記錄觀察時間，不宣稱來源可用時間、PIT 資格或不同讀取間的一致性。
    writer 由排程 app service 注入，避免本模組另行實作檔案發布機制。
    """

    def __init__(
        self,
        *,
        run_id: str,
        output_root: str | Path,
        db_path: str | Path,
        writer: ArtifactWriter,
    ) -> None:
        if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
            raise ForwardSourceObservationError("source_observation_run_id_invalid")
        self.run_id = run_id
        self.output_root = Path(output_root).expanduser().resolve(strict=False)
        if self.output_root != Path(output_root).expanduser():
            # 呼叫端須先解析核准的輸出根目錄（包含已設定的 junction），再建立 recorder。
            raise ForwardSourceObservationError("source_observation_output_root_not_canonical")
        self.db_path = str(Path(db_path).expanduser().resolve(strict=False))
        self._writer = writer
        self._queries: list[dict[str, Any]] = []
        self._query_by_id: dict[str, dict[str, Any]] = {}
        self._outcomes: list[dict[str, Any]] = []
        self._active: dict[str, Any] | None = None
        self._row_count = 0
        self._row_bytes = 0
        self._calculation_started = False
        self._persist_attempted = False
        self.reference: dict[str, Any] | None = None

    def begin_calculation(self) -> None:
        """將 recorder 綁定至單次 calculate 呼叫。"""
        if (
            self._calculation_started
            or self._persist_attempted
            or self.reference is not None
        ):
            raise ForwardSourceObservationError("source_observation_recorder_already_used")
        self._calculation_started = True

    def begin_outcome(self, *, event_id: str, window_days: int) -> None:
        if self._active is not None:
            raise ForwardSourceObservationError("source_observation_context_nested")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ForwardSourceObservationError("source_observation_event_id_invalid")
        if type(window_days) is not int or window_days <= 0:
            raise ForwardSourceObservationError("source_observation_window_invalid")
        self._active = {
            "event_id": event_id,
            "window_days": window_days,
            "query_ids": set(),
        }

    def end_outcome(self) -> tuple[str, ...]:
        if self._active is None:
            raise ForwardSourceObservationError("source_observation_context_missing")
        query_ids = tuple(sorted(self._active["query_ids"]))
        self._active = None
        return query_ids

    def observe_query(
        self,
        *,
        table: str,
        query: str,
        parameters: Sequence[Any],
        rows: Sequence[Sequence[Any]],
        symbol: str | None,
        purpose: str,
        observed_at: datetime | None = None,
    ) -> str:
        if self._active is None:
            raise ForwardSourceObservationError("source_observation_query_outside_outcome")
        if len(self._queries) >= MAX_QUERIES:
            raise ForwardSourceObservationError("source_observation_query_limit")
        captured_at = observed_at or datetime.now(timezone.utc)
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ForwardSourceObservationError("source_observation_clock_naive")
        observed_text = captured_at.astimezone(timezone.utc).isoformat()
        normalized_rows = [_json_value(tuple(row)) for row in rows]
        row_bytes = _canonical_bytes(normalized_rows)
        self._row_count += len(normalized_rows)
        self._row_bytes += len(row_bytes)
        if self._row_count > MAX_ROWS or self._row_bytes > MAX_RUN_BYTES:
            raise ForwardSourceObservationError("source_observation_row_budget_exceeded")
        query_id = f"q{len(self._queries) + 1:06d}"
        query_record: dict[str, Any] = {
            "query_id": query_id,
            "table": table,
            "query": query,
            "parameters": _json_value(tuple(parameters)),
            "symbol": symbol,
            "purpose": purpose,
            "observed_at": observed_text,
            "row_count": len(normalized_rows),
            "rows_sha256": _sha256(row_bytes),
            "rows": normalized_rows,
            "uses": [],
        }
        self._queries.append(query_record)
        self._query_by_id[query_id] = query_record
        self.record_use(query_id, purpose=purpose)
        return query_id

    def record_use(self, query_id: str, *, purpose: str) -> None:
        if self._active is None:
            raise ForwardSourceObservationError("source_observation_use_outside_outcome")
        record = self._query_by_id.get(query_id)
        if record is None:
            raise ForwardSourceObservationError("source_observation_query_reference_invalid")
        use = {
            "event_id": self._active["event_id"],
            "window_days": self._active["window_days"],
            "purpose": purpose,
        }
        if use not in record["uses"]:
            record["uses"].append(use)
        self._active["query_ids"].add(query_id)

    def record_outcome(
        self,
        *,
        event_id: str,
        window_days: int,
        return_basis: str,
        outcome_status: str,
        outcome_payload: Mapping[str, Any],
        query_ids: Sequence[str],
    ) -> None:
        if len(self._outcomes) >= MAX_OUTCOMES:
            raise ForwardSourceObservationError("source_observation_outcome_limit")
        if any(query_id not in self._query_by_id for query_id in query_ids):
            raise ForwardSourceObservationError("source_observation_outcome_query_invalid")
        outcome_sha256 = _sha256(_canonical_bytes(_json_value(outcome_payload)))
        self._outcomes.append(
            {
                "event_id": event_id,
                "window_days": window_days,
                "return_basis": return_basis,
                "outcome_status": outcome_status,
                "outcome_sha256": outcome_sha256,
                "query_ids": list(query_ids),
            }
        )

    def persist(self) -> dict[str, Any]:
        if self.reference is not None:
            return dict(self.reference)
        if self._persist_attempted:
            raise ForwardSourceObservationError("source_observation_recorder_already_used")
        self._persist_attempted = True
        if self._active is not None:
            raise ForwardSourceObservationError("source_observation_context_unclosed")
        chunk_payloads: list[tuple[str, bytes, int]] = []
        manifest_queries: list[dict[str, Any]] = []
        for query in self._queries:
            rows = query["rows"]
            chunks: list[dict[str, Any]] = []
            row_batches = self._chunk_rows(query["query_id"], rows)
            for index, (chunk_value, row_count) in enumerate(row_batches):
                raw = _canonical_bytes(chunk_value)
                if len(raw) > MAX_CHUNK_BYTES:
                    raise ForwardSourceObservationError("source_observation_chunk_too_large")
                relative = (
                    f"scheduled/forward_outcomes/source_observations/runs/"
                    f"{self.run_id}/chunk-{len(chunk_payloads) + 1:04d}.json"
                )
                digest = _sha256(raw)
                chunk_payloads.append((relative, raw, row_count))
                chunks.append(
                    {"path": relative, "sha256": digest, "row_count": row_count}
                )
            query_copy = {key: value for key, value in query.items() if key != "rows"}
            query_copy["chunks"] = chunks
            manifest_queries.append(query_copy)

        if len(chunk_payloads) > MAX_CHUNKS:
            raise ForwardSourceObservationError("source_observation_chunk_count_limit")
        total_bytes = sum(len(raw) for _, raw, _ in chunk_payloads)
        if total_bytes > MAX_RUN_BYTES:
            raise ForwardSourceObservationError("source_observation_run_byte_limit")
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "db_path": self.db_path,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "semantics": {
                "source_availability": "unknown",
                "pit_qualified": False,
                "training_eligible": False,
                "cross_read_snapshot_consistency": "not_guaranteed",
                "rows_are_actual_fetch_results": True,
            },
            "query_count": len(manifest_queries),
            "row_count": self._row_count,
            "chunk_count": len(chunk_payloads),
            "outcomes": self._outcomes,
            "queries": manifest_queries,
        }
        manifest_raw = _canonical_bytes(manifest)
        if len(manifest_raw) > MAX_MANIFEST_BYTES:
            raise ForwardSourceObservationError("source_observation_manifest_too_large")
        if total_bytes + len(manifest_raw) > MAX_RUN_BYTES:
            raise ForwardSourceObservationError("source_observation_run_byte_limit")

        runs_root = self._prepare_store()
        self._check_retention(runs_root, total_bytes + len(manifest_raw))
        _ensure_child_directory(runs_root, Path(self.run_id))
        # 最後寫入 manifest，作為這批 chunks 的提交標記；不完整的 create-only chunks
        # 不得視為完整 run。
        for relative, raw, _ in chunk_payloads:
            path = self.output_root / Path(relative)
            self._write_and_verify(path, raw)
        manifest_relative = (
            f"scheduled/forward_outcomes/source_observations/runs/"
            f"{self.run_id}/manifest.json"
        )
        manifest_path = self.output_root / Path(manifest_relative)
        self._write_and_verify(manifest_path, manifest_raw)
        self.reference = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "manifest_path": manifest_relative,
            "manifest_sha256": _sha256(manifest_raw),
            "query_count": len(manifest_queries),
            "row_count": self._row_count,
            "chunk_count": len(chunk_payloads),
            "source_availability": "unknown",
            "pit_qualified": False,
            "training_eligible": False,
            "cross_read_snapshot_consistency": "not_guaranteed",
        }
        return dict(self.reference)

    def _chunk_rows(
        self, query_id: str, rows: Sequence[Any]
    ) -> list[tuple[dict[str, Any], int]]:
        batches: list[tuple[dict[str, Any], int]] = []
        current: list[Any] = []
        for row in rows:
            candidate = [*current, row]
            value = {
                "schema_version": CHUNK_SCHEMA_VERSION,
                "run_id": self.run_id,
                "query_id": query_id,
                "rows": candidate,
            }
            if current and len(_canonical_bytes(value)) > MAX_CHUNK_BYTES:
                batches.append(
                    (
                        {
                            "schema_version": CHUNK_SCHEMA_VERSION,
                            "run_id": self.run_id,
                            "query_id": query_id,
                            "rows": current,
                        },
                        len(current),
                    )
                )
                current = [row]
                single = {
                    "schema_version": CHUNK_SCHEMA_VERSION,
                    "run_id": self.run_id,
                    "query_id": query_id,
                    "rows": current,
                }
                if len(_canonical_bytes(single)) > MAX_CHUNK_BYTES:
                    raise ForwardSourceObservationError("source_observation_row_too_large")
            else:
                current = candidate
        if current or not rows:
            batches.append(
                (
                    {
                        "schema_version": CHUNK_SCHEMA_VERSION,
                        "run_id": self.run_id,
                        "query_id": query_id,
                        "rows": current,
                    },
                    len(current),
                )
            )
        return batches

    def _prepare_store(self) -> Path:
        root = self.output_root
        if root.resolve(strict=False) != root:
            raise ForwardSourceObservationError("source_observation_output_root_not_canonical")
        root_info = _lstat(root)
        if root_info is None:
            root.parent.mkdir(parents=True, exist_ok=True)
            root.mkdir()
            root_info = _lstat(root)
        if root_info is None or not stat.S_ISDIR(root_info.st_mode):
            raise ForwardSourceObservationError("source_observation_output_root_invalid")
        if _is_reparse(root_info):
            raise ForwardSourceObservationError("source_observation_output_root_reparse")
        return _ensure_child_directory(
            root, Path("scheduled") / "forward_outcomes" / "source_observations" / "runs"
        )

    def _check_retention(self, runs_root: Path, new_bytes: int) -> None:
        count = 0
        retained_bytes = 0
        try:
            with os.scandir(runs_root) as iterator:
                entries = list(iterator)
        except OSError as exc:
            raise ForwardSourceObservationError("source_observation_retention_unreadable") from exc
        if len(entries) > MAX_RETAINED_RUNS:
            raise ForwardSourceObservationError("source_observation_retained_run_limit")
        for entry in entries:
            info = entry.stat(follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or _is_reparse(info):
                raise ForwardSourceObservationError("source_observation_retained_entry_invalid")
            count += 1
            try:
                with os.scandir(entry.path) as files:
                    file_entries = list(files)
            except OSError as exc:
                raise ForwardSourceObservationError("source_observation_retention_unreadable") from exc
            if len(file_entries) > MAX_CHUNKS + 1:
                raise ForwardSourceObservationError("source_observation_retained_file_limit")
            for file_entry in file_entries:
                file_info = file_entry.stat(follow_symlinks=False)
                if (
                    not stat.S_ISREG(file_info.st_mode)
                    or _is_reparse(file_info)
                    or file_entry.is_symlink()
                ):
                    raise ForwardSourceObservationError("source_observation_retained_file_invalid")
                retained_bytes += int(file_info.st_size)
                if retained_bytes > MAX_RETAINED_BYTES:
                    raise ForwardSourceObservationError("source_observation_retained_byte_limit")
        if count >= MAX_RETAINED_RUNS:
            raise ForwardSourceObservationError("source_observation_retained_run_limit")
        if retained_bytes + new_bytes > MAX_RETAINED_BYTES:
            raise ForwardSourceObservationError("source_observation_retained_byte_limit")

    def _write_and_verify(self, path: Path, raw: bytes) -> None:
        _validate_directory(path.parent)
        try:
            self._writer(path, raw.decode("utf-8"))
            info = path.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or _is_reparse(info)
                or info.st_nlink != 1
            ):
                raise ForwardSourceObservationError("source_observation_file_invalid")
            persisted = path.read_bytes()
        except ForwardSourceObservationError:
            raise
        except (OSError, UnicodeError) as exc:
            raise ForwardSourceObservationError("source_observation_write_failed") from exc
        if persisted != raw or _sha256(persisted) != _sha256(raw):
            raise ForwardSourceObservationError("source_observation_readback_mismatch")


__all__ = [
    "CHUNK_SCHEMA_VERSION",
    "ForwardSourceObservationError",
    "ForwardSourceObservationRecorder",
    "MAX_CHUNK_BYTES",
    "MAX_CHUNKS",
    "MAX_MANIFEST_BYTES",
    "MAX_QUERIES",
    "MAX_RETAINED_BYTES",
    "MAX_RETAINED_RUNS",
    "MAX_ROWS",
    "MAX_RUN_BYTES",
    "SCHEMA_VERSION",
]
