"""以有界不可變產物記錄 Forward 計算實際讀取的資料列。"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Callable, Mapping, Sequence

from data_module.ml_research_output_boundary import (
    _read_bounded_regular_file_no_follow,
    _reject_json_constant,
    _unique_json_object,
)


SCHEMA_VERSION = "forward-source-observations.v1"
CHUNK_SCHEMA_VERSION = "forward-source-observation-chunk.v1"
BOUND_SCHEMA_VERSION = "forward-source-observations.v2"
BOUND_CHUNK_SCHEMA_VERSION = "forward-source-observation-bound-chunk.v2"
MAX_CHUNK_BYTES = 512 * 1024
# Daily processing can emit 2,500 events × 4 windows of outcome metadata, plus
# bounded per-query references. Keep the manifest within the existing 64 MiB
# run budget while allowing that supported batch to be recorded and read back.
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_RUN_BYTES = 64 * 1024 * 1024
MAX_RETAINED_BYTES = 12 * 1024 * 1024 * 1024
MAX_RETAINED_RUNS = 4096
MAX_QUERIES = 4096
MAX_ROWS = 500_000
# 每筆小查詢至少占一個 chunk；提升既有 128 上限以容納多筆小 query。
# 實際產物仍受 MAX_MANIFEST_BYTES、MAX_RUN_BYTES、MAX_ROWS 與單檔上限約束。
MAX_CHUNKS = 4096
MAX_OUTCOMES = 10_000
MAX_READBACK_BYTES = MAX_RUN_BYTES
_RUN_ID = re.compile(r"\d{8}T\d{12}Z\Z")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class ForwardSourceObservationError(ValueError):
    """無法安全擷取或持久化 Forward 讀取證據。"""


ArtifactWriter = Callable[[Path, str], None]
QualificationVerifier = Callable[[Mapping[str, Any]], bool]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _strict_json(raw: bytes) -> object:
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ForwardSourceObservationError("source_observation_json_invalid") from exc


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
        qualification_verifier: QualificationVerifier | None = None,
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
        self._qualification_verifier = qualification_verifier
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
        columns: Sequence[str] | None = None,
        source_bindings: Sequence[Mapping[str, Any]] | None = None,
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
        normalized_bindings = None
        if columns is not None:
            if len(set(columns)) != len(columns) or any(len(row) != len(columns) for row in rows):
                raise ForwardSourceObservationError("source_observation_columns_invalid")
        if source_bindings is not None:
            if columns is None or len(source_bindings) != len(rows):
                raise ForwardSourceObservationError("source_observation_binding_count_invalid")
            normalized_bindings = []
            for binding in source_bindings:
                qualification_claim = (
                    binding.get("status") in {
                        "source_qualified", "source_identity_and_availability_bound"
                    }
                    or binding.get("source_use_accepted") is True
                    or binding.get("pit_eligible") is True
                    or binding.get("training_eligible") is True
                    or binding.get("available_at") is not None
                    or binding.get("source_published_at") is not None
                )
                if qualification_claim:
                    verifier = self._qualification_verifier
                    if not callable(verifier) or not verifier(binding):
                        raise ForwardSourceObservationError(
                            "source_observation_binding_qualification_invalid"
                        )
                if (
                    binding.get("source_use_accepted") is not False
                    or binding.get("pit_eligible") is not False
                    or binding.get("training_eligible") is not False
                    or binding.get("available_at") is not None
                    or binding.get("source_published_at") is not None
                ):
                    if not qualification_claim:
                        raise ForwardSourceObservationError(
                            "source_observation_binding_contract_invalid"
                        )
                normalized_bindings.append(_json_value(binding))
        self._row_count += len(normalized_rows)
        self._row_bytes += len(row_bytes)
        if normalized_bindings is not None:
            self._row_bytes += len(_canonical_bytes(normalized_bindings))
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
        if columns is not None:
            query_record["columns"] = list(columns)
        if normalized_bindings is not None:
            query_record["source_bindings"] = normalized_bindings
            query_record["source_bindings_sha256"] = _sha256(_canonical_bytes(normalized_bindings))
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
            row_batches = self._chunk_rows(query["query_id"], rows, query.get("source_bindings"))
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
            query_copy = {key: value for key, value in query.items() if key not in {"rows", "source_bindings"}}
            query_copy["chunks"] = chunks
            manifest_queries.append(query_copy)

        if len(chunk_payloads) > MAX_CHUNKS:
            raise ForwardSourceObservationError("source_observation_chunk_count_limit")
        total_bytes = sum(len(raw) for _, raw, _ in chunk_payloads)
        if total_bytes > MAX_RUN_BYTES:
            raise ForwardSourceObservationError("source_observation_run_byte_limit")
        manifest_schema = BOUND_SCHEMA_VERSION if any("source_bindings" in query for query in self._queries) else SCHEMA_VERSION
        manifest: dict[str, Any] = {
            "schema_version": manifest_schema,
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
            "schema_version": manifest_schema,
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
        self, query_id: str, rows: Sequence[Any], bindings: Sequence[Any] | None = None,
    ) -> list[tuple[dict[str, Any], int]]:
        batches: list[tuple[dict[str, Any], int]] = []
        current: list[Any] = []
        current_bindings: list[Any] = []

        def body(values: list[Any], references: list[Any]) -> dict[str, Any]:
            value = {
                "schema_version": BOUND_CHUNK_SCHEMA_VERSION if bindings is not None else CHUNK_SCHEMA_VERSION,
                "run_id": self.run_id,
                "query_id": query_id,
                "rows": values,
            }
            if bindings is not None:
                value["source_bindings"] = references
            return value

        base_bytes = len(_canonical_bytes(body([], [])))
        content_bytes = 0
        for index, row in enumerate(rows):
            binding = bindings[index] if bindings is not None else None
            extra = len(_canonical_bytes(row))
            if bindings is not None:
                extra += len(_canonical_bytes(binding))
            comma_bytes = (2 if bindings is not None else 1) if current else 0
            if current and base_bytes + content_bytes + comma_bytes + extra > MAX_CHUNK_BYTES:
                batches.append((body(current, current_bindings), len(current)))
                current, current_bindings, content_bytes = [], [], 0
                comma_bytes = 0
            if base_bytes + content_bytes + comma_bytes + extra > MAX_CHUNK_BYTES:
                raise ForwardSourceObservationError("source_observation_row_too_large")
            current.append(row)
            if bindings is not None:
                current_bindings.append(binding)
            content_bytes += comma_bytes + extra
        if current or not rows:
            batches.append((body(current, current_bindings), len(current)))
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


def verify_forward_source_observation_readback(
    *,
    output_root: str | Path,
    reference: Mapping[str, Any],
    qualification_verifier: QualificationVerifier | None = None,
) -> dict[str, Any]:
    """在有界路徑內嚴格驗證完整 Forward observation 及其資格綁定。"""

    root = Path(output_root).expanduser().resolve(strict=False)
    manifest_rel = reference.get("manifest_path")
    expected_manifest_sha = reference.get("manifest_sha256")
    run_id = reference.get("run_id")
    schema_version = reference.get("schema_version")
    if (
        not isinstance(manifest_rel, str)
        or not isinstance(expected_manifest_sha, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_manifest_sha)
        or not isinstance(run_id, str)
        or _RUN_ID.fullmatch(run_id) is None
        or schema_version not in {SCHEMA_VERSION, BOUND_SCHEMA_VERSION}
        or manifest_rel != (
            f"scheduled/forward_outcomes/source_observations/runs/{run_id}/manifest.json"
        )
    ):
        raise ForwardSourceObservationError("source_observation_reference_invalid")
    expected_reference_fields = {
        "schema_version", "run_id", "manifest_path", "manifest_sha256",
        "query_count", "row_count", "chunk_count", "source_availability",
        "pit_qualified", "training_eligible", "cross_read_snapshot_consistency",
    }
    if set(reference) != expected_reference_fields:
        raise ForwardSourceObservationError("source_observation_reference_schema_invalid")
    if (
        reference.get("source_availability") != "unknown"
        or reference.get("pit_qualified") is not False
        or reference.get("training_eligible") is not False
        or reference.get("cross_read_snapshot_consistency") != "not_guaranteed"
    ):
        raise ForwardSourceObservationError("source_observation_reference_qualification_invalid")

    manifest_raw = _read_observation_file(root, manifest_rel, MAX_MANIFEST_BYTES)
    if _sha256(manifest_raw) != expected_manifest_sha:
        raise ForwardSourceObservationError("source_observation_manifest_sha256_mismatch")
    manifest = _strict_json(manifest_raw)
    manifest_fields = {
        "schema_version", "run_id", "db_path", "recorded_at", "semantics",
        "query_count", "row_count", "chunk_count", "outcomes", "queries",
    }
    if (
        type(manifest) is not dict
        or set(manifest) != manifest_fields
        or manifest.get("schema_version") != schema_version
        or manifest.get("run_id") != run_id
    ):
        raise ForwardSourceObservationError("source_observation_manifest_invalid")
    semantics = manifest.get("semantics")
    if semantics != {
        "source_availability": "unknown",
        "pit_qualified": False,
        "training_eligible": False,
        "cross_read_snapshot_consistency": "not_guaranteed",
        "rows_are_actual_fetch_results": True,
    }:
        raise ForwardSourceObservationError("source_observation_semantics_invalid")
    _require_bounded_int(manifest.get("query_count"), 0, MAX_QUERIES, "query_count")
    _require_bounded_int(manifest.get("row_count"), 0, MAX_ROWS, "row_count")
    _require_bounded_int(manifest.get("chunk_count"), 0, MAX_CHUNKS, "chunk_count")
    for field_name in ("query_count", "row_count", "chunk_count"):
        _require_bounded_int(reference.get(field_name), 0, MAX_ROWS, f"reference_{field_name}")
        if reference.get(field_name) != manifest.get(field_name):
            raise ForwardSourceObservationError("source_observation_reference_count_mismatch")
    if (
        not isinstance(manifest.get("db_path"), str)
        or not manifest["db_path"]
        or not isinstance(manifest.get("recorded_at"), str)
    ):
        raise ForwardSourceObservationError("source_observation_manifest_identity_invalid")
    try:
        recorded_at = datetime.fromisoformat(manifest["recorded_at"])
    except ValueError as exc:
        raise ForwardSourceObservationError("source_observation_recorded_at_invalid") from exc
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise ForwardSourceObservationError("source_observation_recorded_at_invalid")
    queries = manifest.get("queries")
    outcomes = manifest.get("outcomes")
    if (
        not isinstance(queries, list)
        or len(queries) != manifest["query_count"]
        or not isinstance(outcomes, list)
        or len(outcomes) > MAX_OUTCOMES
    ):
        raise ForwardSourceObservationError("source_observation_manifest_counts_invalid")

    verified_queries: list[dict[str, Any]] = []
    seen_query_ids: set[str] = set()
    query_uses: dict[str, list[Mapping[str, Any]]] = {}
    found_bound_query = False
    total_rows = 0
    total_chunks = 0
    total_bytes = len(manifest_raw)
    for query_index, query_meta in enumerate(queries, start=1):
        if not isinstance(query_meta, Mapping):
            raise ForwardSourceObservationError("source_observation_query_meta_invalid")
        base_query_fields = {
            "query_id", "table", "query", "parameters", "symbol", "purpose",
            "observed_at", "row_count", "rows_sha256", "uses", "chunks",
        }
        query_fields = set(query_meta)
        has_bindings = "source_bindings_sha256" in query_fields
        found_bound_query = found_bound_query or has_bindings
        if query_fields not in (
            base_query_fields,
            base_query_fields | {"columns"},
            base_query_fields | {"source_bindings_sha256"},
            base_query_fields | {"columns", "source_bindings_sha256"},
        ):
            raise ForwardSourceObservationError("source_observation_query_schema_invalid")
        query_id = query_meta.get("query_id")
        if (
            not isinstance(query_id, str)
            or not re.fullmatch(r"q\d{6}", query_id)
            or query_id != f"q{query_index:06d}"
            or query_id in seen_query_ids
            or not isinstance(query_meta.get("table"), str)
            or not isinstance(query_meta.get("query"), str)
            or not isinstance(query_meta.get("purpose"), str)
            or not isinstance(query_meta.get("rows_sha256"), str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", query_meta["rows_sha256"])
        ):
            raise ForwardSourceObservationError("source_observation_query_identity_invalid")
        seen_query_ids.add(query_id)
        uses = query_meta.get("uses")
        if not isinstance(uses, list) or not uses:
            raise ForwardSourceObservationError("source_observation_query_uses_invalid")
        for use in uses:
            if not isinstance(use, Mapping) or set(use) != {
                "event_id", "window_days", "purpose"
            }:
                raise ForwardSourceObservationError("source_observation_query_use_invalid")
            if (
                not isinstance(use.get("event_id"), str)
                or type(use.get("window_days")) is not int
                or use["window_days"] <= 0
                or not isinstance(use.get("purpose"), str)
            ):
                raise ForwardSourceObservationError("source_observation_query_use_invalid")
        query_uses[query_id] = uses
        _require_bounded_int(query_meta.get("row_count"), 0, MAX_ROWS, "query_row_count")
        columns = query_meta.get("columns")
        if columns is not None and (
            not isinstance(columns, list)
            or any(not isinstance(column, str) for column in columns)
            or len(columns) != len(set(columns))
        ):
            raise ForwardSourceObservationError("source_observation_columns_invalid")
        query_chunks = query_meta.get("chunks")
        if not isinstance(query_chunks, list) or not query_chunks:
            raise ForwardSourceObservationError("source_observation_query_chunks_invalid")
        reconstructed_rows: list[Any] = []
        reconstructed_bindings: list[Any] = []
        for chunk_meta in query_chunks:
            if not isinstance(chunk_meta, Mapping) or set(chunk_meta) != {
                "path", "sha256", "row_count"
            }:
                raise ForwardSourceObservationError("source_observation_chunk_meta_invalid")
            chunk_rel = chunk_meta.get("path")
            expected_chunk_path = re.compile(
                rf"scheduled/forward_outcomes/source_observations/runs/{re.escape(run_id)}/chunk-\d{{4}}\.json"
            )
            expected_chunk_index = total_chunks + 1
            if (
                not isinstance(chunk_rel, str)
                or expected_chunk_path.fullmatch(chunk_rel) is None
                or chunk_rel.endswith(f"chunk-{expected_chunk_index:04d}.json") is False
            ):
                raise ForwardSourceObservationError("source_observation_chunk_path_invalid")
            chunk_raw = _read_observation_file(root, chunk_rel, MAX_CHUNK_BYTES)
            total_bytes += len(chunk_raw)
            total_chunks += 1
            if total_bytes > MAX_READBACK_BYTES or total_chunks > MAX_CHUNKS:
                raise ForwardSourceObservationError("source_observation_readback_budget_exceeded")
            if _sha256(chunk_raw) != chunk_meta.get("sha256"):
                raise ForwardSourceObservationError("source_observation_chunk_sha256_mismatch")
            chunk_body = _strict_json(chunk_raw)
            expected_chunk_fields = (
                {"schema_version", "run_id", "query_id", "rows", "source_bindings"}
                if has_bindings
                else {"schema_version", "run_id", "query_id", "rows"}
            )
            if (
                type(chunk_body) is not dict
                or set(chunk_body) != expected_chunk_fields
                or chunk_body.get("schema_version") != (
                    BOUND_CHUNK_SCHEMA_VERSION if has_bindings else CHUNK_SCHEMA_VERSION
                )
                or chunk_body.get("run_id") != run_id
                or chunk_body.get("query_id") != query_id
                or not isinstance(chunk_body.get("rows"), list)
            ):
                raise ForwardSourceObservationError("source_observation_chunk_schema_invalid")
            chunk_rows = chunk_body["rows"]
            _require_bounded_int(
                chunk_meta.get("row_count"), 0, MAX_ROWS, "chunk_row_count"
            )
            if len(chunk_rows) != chunk_meta["row_count"]:
                raise ForwardSourceObservationError("source_observation_chunk_row_count_mismatch")
            reconstructed_rows.extend(chunk_rows)
            if has_bindings:
                chunk_bindings = chunk_body.get("source_bindings")
                if not isinstance(chunk_bindings, list) or len(chunk_bindings) != len(chunk_rows):
                    raise ForwardSourceObservationError("source_observation_chunk_binding_count_mismatch")
                for binding in chunk_bindings:
                    if not isinstance(binding, Mapping):
                        raise ForwardSourceObservationError("source_observation_binding_invalid")
                    _verify_observed_binding(
                        binding, qualification_verifier=qualification_verifier
                    )
                reconstructed_bindings.extend(chunk_bindings)
        if len(reconstructed_rows) != query_meta["row_count"]:
            raise ForwardSourceObservationError("source_observation_query_row_count_mismatch")
        if any(
            not isinstance(row, list)
            or (columns is not None and len(row) != len(columns))
            for row in reconstructed_rows
        ):
            raise ForwardSourceObservationError("source_observation_row_shape_invalid")
        total_rows += len(reconstructed_rows)
        if _sha256(_canonical_bytes(reconstructed_rows)) != query_meta.get("rows_sha256"):
            raise ForwardSourceObservationError("source_observation_rows_sha256_mismatch")
        if has_bindings and (
            not isinstance(query_meta.get("source_bindings_sha256"), str)
            or _sha256(_canonical_bytes(reconstructed_bindings))
            != query_meta.get("source_bindings_sha256")
        ):
            raise ForwardSourceObservationError("source_observation_bindings_sha256_mismatch")
        verified_queries.append(
            {
                "query_id": query_id,
                "purpose": query_meta.get("purpose"),
                "row_count": len(reconstructed_rows),
                "rows": reconstructed_rows,
                "source_bindings": reconstructed_bindings if has_bindings else None,
            }
        )
    if total_rows != manifest["row_count"] or total_chunks != manifest["chunk_count"]:
        raise ForwardSourceObservationError("source_observation_manifest_totals_mismatch")
    if (schema_version == BOUND_SCHEMA_VERSION) is not found_bound_query:
        raise ForwardSourceObservationError("source_observation_schema_binding_mismatch")
    for outcome in outcomes:
        if not isinstance(outcome, Mapping) or set(outcome) != {
            "event_id", "window_days", "return_basis", "outcome_status",
            "outcome_sha256", "query_ids",
        }:
            raise ForwardSourceObservationError("source_observation_outcome_invalid")
        if (
            not isinstance(outcome.get("event_id"), str)
            or type(outcome.get("window_days")) is not int
            or outcome["window_days"] <= 0
            or not isinstance(outcome.get("return_basis"), str)
            or not isinstance(outcome.get("outcome_status"), str)
            or not isinstance(outcome.get("outcome_sha256"), str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", outcome["outcome_sha256"])
            or not isinstance(outcome.get("query_ids"), list)
            or any(query_id not in seen_query_ids for query_id in outcome["query_ids"])
            or any(
                not any(
                    use.get("event_id") == outcome.get("event_id")
                    and use.get("window_days") == outcome.get("window_days")
                    for use in query_uses.get(query_id, [])
                )
                for query_id in outcome.get("query_ids", [])
            )
        ):
            raise ForwardSourceObservationError("source_observation_outcome_identity_invalid")
    return {
        "status": "verified",
        "run_id": run_id,
        "manifest_sha256": expected_manifest_sha,
        "query_count": len(verified_queries),
        "queries": verified_queries,
        "outcomes": outcomes,
    }


def _require_bounded_int(value: object, minimum: int, maximum: int, label: str) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ForwardSourceObservationError(f"source_observation_{label}_invalid")


def _read_observation_file(root: Path, relative: str, maximum_bytes: int) -> bytes:
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or ":" in relative
    ):
        raise ForwardSourceObservationError("source_observation_path_invalid")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ForwardSourceObservationError("source_observation_path_invalid")
    root_info = root.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or _is_reparse(root_info):
        raise ForwardSourceObservationError("source_observation_root_invalid")
    candidate = root.joinpath(*pure.parts)
    parent_states: list[tuple[Path, tuple[int, int, int, int]]] = []
    current = root
    for part in pure.parts[:-1]:
        current = current / part
        info = current.lstat()
        if not stat.S_ISDIR(info.st_mode) or _is_reparse(info):
            raise ForwardSourceObservationError("source_observation_parent_invalid")
        parent_states.append(
            (current, (info.st_dev, info.st_ino, info.st_mode, info.st_mtime_ns))
        )
    before = candidate.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or _is_reparse(before)
        or before.st_nlink != 1
        or before.st_size < 0
        or before.st_size > maximum_bytes
    ):
        raise ForwardSourceObservationError("source_observation_file_invalid")
    raw = _read_bounded_regular_file_no_follow(candidate, maximum_bytes=maximum_bytes)
    after = candidate.lstat()
    if (
        len(raw) != before.st_size
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or not stat.S_ISREG(after.st_mode)
        or _is_reparse(after)
    ):
        raise ForwardSourceObservationError("source_observation_file_changed_during_read")
    for parent, identity in parent_states:
        info = parent.lstat()
        if (info.st_dev, info.st_ino, info.st_mode, info.st_mtime_ns) != identity:
            raise ForwardSourceObservationError("source_observation_parent_changed_during_read")
    return raw


def _verify_observed_binding(
    binding: Mapping[str, Any],
    *,
    qualification_verifier: QualificationVerifier | None,
) -> None:
    claim = (
        binding.get("status") in {
            "source_qualified", "source_identity_and_availability_bound"
        }
        or binding.get("source_use_accepted") is True
        or binding.get("pit_eligible") is True
        or binding.get("training_eligible") is True
        or binding.get("available_at") is not None
        or binding.get("source_published_at") is not None
    )
    if claim:
        if not callable(qualification_verifier) or not qualification_verifier(binding):
            raise ForwardSourceObservationError("source_observation_binding_qualification_invalid")
    elif (
        binding.get("source_use_accepted") is not False
        or binding.get("pit_eligible") is not False
        or binding.get("training_eligible") is not False
        or binding.get("available_at") is not None
        or binding.get("source_published_at") is not None
    ):
        raise ForwardSourceObservationError("source_observation_binding_contract_invalid")


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
    "verify_forward_source_observation_readback",
]
