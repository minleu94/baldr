"""固定研究來源的唯讀查找；不建庫、不遷移、不授比較或績效資格。"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from copy import copy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Callable, Iterator

import pandas as pd

from app_module.research_run_dtos import canonical_json, normalize_research_run_json_value
from app_module.research_run_service import ResearchRunService, ResearchRunData
from app_module.research_run_repository import ResearchRunRepository, ResearchRunRepositoryError
from app_module.saved_strategy_rule_card import metadata_sha256, result_context_sha256

REGISTRY_BACKTEST_TYPES = frozenset({"single_backtest", "batch_backtest_stock", "fixed_basket_stock"})
REGISTRY_RESULT_TYPES = REGISTRY_BACKTEST_TYPES | {"recommendation_portfolio"}


class ResearchHistoryUnavailable(ValueError):
    """來源缺件、已修訂或種類不支援；不能換成另一份結果。"""


@dataclass(frozen=True)
class ResearchHistoryReadBudget:
    """caller 明示 Registry／legacy 序列化讀取預算；不代表解碼 RAM 上限。"""

    max_artifact_bytes: int
    max_total_bytes: int

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0
               for value in (self.max_artifact_bytes, self.max_total_bytes)):
            raise ValueError("artifact／aggregate byte budget 必須為正整數")


def _source_stamp(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_size, value.st_mtime_ns, value.st_dev, value.st_ino


class _ReadRound:
    """一輪 legacy artifact I/O；每 64 KiB 檢查取消，hash／decode 使用同次 bytes。"""

    CHUNK_BYTES = 64 * 1024

    def __init__(self, budget: ResearchHistoryReadBudget | None,
                 check_cancel: Callable[[], bool] | None):
        self.budget = budget
        self.check_cancel = check_cancel
        self.used_bytes = 0
        self.sources: dict[Path, tuple[int, int, int, int]] = {}

    def cancelled(self) -> None:
        if self.check_cancel is not None and self.check_cancel():
            raise ResearchHistoryUnavailable("read_cancelled")

    def read(self, path: Path, *, keep: bool = False) -> tuple[str, bytes]:
        try:
            return self._read(path, keep=keep)
        except OSError as exc:
            raise ResearchHistoryUnavailable("artifact_source_unavailable:" + str(path)) from exc

    def _read(self, path: Path, *, keep: bool) -> tuple[str, bytes]:
        self.cancelled()
        if self.budget is None:
            raise ResearchHistoryUnavailable("legacy_read_budget_required")
        before = _source_stamp(path.stat())
        if path in self.sources and self.sources[path] != before:
            raise ResearchHistoryUnavailable("artifact_source_changed:" + str(path))
        if before[0] > self.budget.max_artifact_bytes:
            raise ResearchHistoryUnavailable("artifact_byte_budget_exceeded:" + str(path))
        if before[0] > self.budget.max_total_bytes - self.used_bytes:
            raise ResearchHistoryUnavailable("aggregate_byte_budget_exceeded:" + str(path))
        # stat 超限時不 open；已讀／嘗試的 bytes 不因某一列失敗而重置 aggregate。
        self.used_bytes += before[0]
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        count = 0
        with path.open("rb") as handle:
            if _source_stamp(os.fstat(handle.fileno())) != before:
                raise ResearchHistoryUnavailable("artifact_source_changed:" + str(path))
            while True:
                self.cancelled()
                chunk = handle.read(min(self.CHUNK_BYTES, before[0] - count + 1))
                if not chunk:
                    break
                count += len(chunk)
                if count > before[0]:
                    raise ResearchHistoryUnavailable("artifact_source_changed:" + str(path))
                digest.update(chunk)
                if keep:
                    chunks.append(chunk)
            if count != before[0] or _source_stamp(os.fstat(handle.fileno())) != before:
                raise ResearchHistoryUnavailable("artifact_source_changed:" + str(path))
        self.cancelled()
        if _source_stamp(path.stat()) != before:
            raise ResearchHistoryUnavailable("artifact_source_changed:" + str(path))
        self.sources[path] = before
        return digest.hexdigest(), b"".join(chunks)

    def verify_sources(self) -> None:
        self.cancelled()
        for path, before in self.sources.items():
            try:
                after = _source_stamp(path.stat())
            except OSError as exc:
                raise ResearchHistoryUnavailable("artifact_source_unavailable:" + str(path)) from exc
            if after != before:
                raise ResearchHistoryUnavailable("artifact_source_changed:" + str(path))


def _immutable_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise ResearchHistoryUnavailable("source_missing:" + str(path))
    if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ResearchHistoryUnavailable("active_sqlite_sidecar_unsupported:" + str(path))
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


class _HistoryRegistryReadRepository(ResearchRunRepository):
    """沿用原 schema／decoder，查找時不取 lock／建立 WAL sidecar。"""
    history_limit = 200

    def list_metadata(self, *, include_archived: bool = False) -> list[Any]:
        if not self.db_path.is_file():
            raise ResearchHistoryUnavailable("registry:source_missing")
        where = "" if include_archived else " AND is_archived = 0"
        with self._read_connection() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM research_runs WHERE storage_state = 'committed' AND integrity_status = 'valid'"
                + where + " ORDER BY created_at DESC, run_id DESC LIMIT ?", (self.history_limit,)).fetchall()
        return [self._row_to_dto(dict(row)) for row in rows]

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        connection = _immutable_connection(self.db_path)
        try:
            row = connection.execute("SELECT version FROM schema_version WHERE name = ?", (self.SCHEMA_NAME,)).fetchone()
            if row is None or int(row[0]) != self.SCHEMA_VERSION:
                raise ResearchRunRepositoryError("Registry schema version 不相容；唯讀查找不遷移")
            yield connection
        finally:
            connection.close()


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(normalize_research_run_json_value(value)).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResearchHistoryEntry:
    source_kind: str
    run_type: str
    run_id: str
    run_name: str
    stock_code: str
    start_date: str
    end_date: str
    created_at: str
    metadata_sha256: str
    context_sha256: str
    metadata_json: str
    result_supported: bool
    unsupported_reason: str


@dataclass(frozen=True)
class ResearchHistoryResult:
    entry: ResearchHistoryEntry
    result: dict[str, Any] | ResearchRunData


@dataclass(frozen=True)
class ResearchHistoryPage:
    entries: tuple[ResearchHistoryEntry, ...]
    diagnostics: tuple[str, ...]
    per_source_limit: int


class ResearchHistoryLookup:
    """注入既有 Registry reader 與兩個 legacy DB 路徑；建構子沒有 I/O。"""

    def __init__(self, *, registry: ResearchRunService | None = None,
                 legacy_backtest_db: Path | None = None,
                 legacy_portfolio_db: Path | None = None,
                 read_budget: ResearchHistoryReadBudget | None = None):
        self.read_budget = read_budget
        self.registry = copy(registry) if registry is not None else None
        if self.registry is not None:
            self.registry.repository = _HistoryRegistryReadRepository(self.registry.config)
        self.legacy_paths = {"legacy_backtest": legacy_backtest_db,
                             "legacy_recommendation_portfolio": legacy_portfolio_db}

    def _legacy_rows(self, kind: str, *, limit: int = 200,
                     run_id: str | None = None) -> list[dict[str, Any]]:
        path = self.legacy_paths.get(kind)
        if path is None or not Path(path).is_file():
            raise ResearchHistoryUnavailable(f"{kind}:source_missing")
        path = Path(path).resolve()
        # immutable 模式不取 SQLite lock／不建 sidecar；有待合併 journal 時拒絕舊 snapshot。
        if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ResearchHistoryUnavailable(f"{kind}:active_sqlite_sidecar_unsupported")
        connection = _immutable_connection(path)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.row_factory = sqlite3.Row
            if run_id is None:
                rows = connection.execute("SELECT * FROM runs ORDER BY created_at DESC, run_id LIMIT ?", (limit,))
            else:
                rows = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
            result = [dict(row) for row in rows]
        finally:
            connection.close()
        for row in result:
            for key in ("strategy_params", "tags"):
                if isinstance(row.get(key), str) and row[key]:
                    row[key] = json.loads(row[key])
        return result

    def _legacy_entry(self, kind: str, row: dict[str, Any], *,
                      artifacts: dict[str, str | None]) -> ResearchHistoryEntry:
        meta_hash = _hash(row)
        stock = str(row.get("stock_code") or "")
        source_path = self.legacy_paths[kind]
        if source_path is None:
            raise ResearchHistoryUnavailable("source_missing")
        context = {"source_kind": kind, "source_db": str(source_path.resolve()),
                   "run_id": row["run_id"], "stock_code": stock,
                   "metadata_sha256": meta_hash, "artifacts": artifacts}
        return ResearchHistoryEntry(kind, kind, str(row["run_id"]), str(row.get("run_name") or row["run_id"]),
            stock, str(row.get("start_date") or ""), str(row.get("end_date") or ""),
            str(row.get("created_at") or ""), meta_hash, _hash(context), canonical_json(row), True,
            "legacy_rule_contract_unknown_performance_not_evaluable")

    def _registry_entry(self, metadata: Any) -> ResearchHistoryEntry:
        from dataclasses import asdict
        if self.registry is None:
            raise ResearchHistoryUnavailable("registry:source_missing")
        stock = metadata.universe[0] if len(metadata.universe) == 1 else ""
        supported = metadata.run_type in REGISTRY_RESULT_TYPES
        reason = "" if supported else ("research_forward_metadata_only" if metadata.run_type == "research_forward"
                                       else "unknown_run_type_metadata_only")
        snapshot = normalize_research_run_json_value(asdict(metadata))
        return ResearchHistoryEntry("registry", metadata.run_type, metadata.run_id, metadata.run_name, stock,
            metadata.start_date, metadata.end_date, metadata.created_at, metadata_sha256(metadata),
            _hash({"source_kind": "registry", "source_db": str(self.registry.repository.db_path.resolve()),
                   "run_type": metadata.run_type, "run_id": metadata.run_id, "stock_code": stock,
                   "result_context": result_context_sha256(metadata), "metadata_sha256": metadata_sha256(metadata)}),
            canonical_json(snapshot), supported, reason)

    def list_entries(self, *, limit: int = 200,
                     read_budget: ResearchHistoryReadBudget | None = None,
                     check_cancel: Callable[[], bool] | None = None) -> ResearchHistoryPage:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("每個來源的查找上限需為 1–1000")
        entries: list[ResearchHistoryEntry] = []
        diagnostics: list[str] = []
        reading = _ReadRound(read_budget or self.read_budget, check_cancel)
        for kind in self.legacy_paths:
            try:
                reading.cancelled()
                if reading.budget is None:
                    raise ResearchHistoryUnavailable(f"{kind}:legacy_read_budget_required")
                for row in self._legacy_rows(kind, limit=limit):
                    reading.cancelled()
                    try:
                        artifacts = {}
                        for key in ("equity_curve_path", "trade_list_path", "data_path"):
                            if row.get(key):
                                path = Path(row[key])
                                artifacts[key] = reading.read(path)[0] if path.is_file() else None
                        entries.append(self._legacy_entry(kind, row, artifacts=artifacts))
                    except (OSError, ValueError) as exc:
                        diagnostics.append(f"{kind}/{row.get('run_id')}:{exc}")
                        reading.cancelled()
            except (OSError, sqlite3.Error, ValueError) as exc:
                diagnostics.append(str(exc))
        try:
            reading.verify_sources()
        except (OSError, ValueError) as exc:
            # 不保留本輪來源已變動的 legacy pins；Registry metadata 可獨立查找。
            entries.clear()
            diagnostics.append(str(exc))
        if check_cancel is not None and check_cancel():
            return ResearchHistoryPage((), tuple(diagnostics), limit)
        if self.registry is None:
            diagnostics.append("registry:source_missing")
        else:
            try:
                if isinstance(self.registry.repository, _HistoryRegistryReadRepository):
                    self.registry.repository.history_limit = limit
                runs = sorted(self.registry.list_runs(), key=lambda m: (m.created_at, m.run_id), reverse=True)
                entries.extend(self._registry_entry(metadata) for metadata in runs[:limit])
            except (OSError, ValueError, RuntimeError, sqlite3.Error, ResearchRunRepositoryError) as exc:
                diagnostics.append("registry:" + str(exc))
        return ResearchHistoryPage(tuple(sorted(entries, key=lambda e: (e.created_at, e.source_kind, e.run_id), reverse=True)),
                                   tuple(diagnostics), limit)

    def select_registry_run(self, run_id: str, *,
                            check_cancel: Callable[[], bool] | None = None) -> ResearchHistoryEntry:
        """按明示run建立當次唯讀選取；不掃latest、不讀結果或建立來源。"""
        if type(run_id) is not str or not run_id.strip() or run_id != run_id.strip() or len(run_id) > 512:
            raise ResearchHistoryUnavailable("registry:run_id_invalid")
        reading = _ReadRound(self.read_budget, check_cancel)
        reading.cancelled()
        if self.registry is None:
            raise ResearchHistoryUnavailable("registry:source_missing")
        metadata = self.registry.repository.get_metadata(run_id)
        reading.cancelled()
        if metadata is None or metadata.run_id != run_id:
            raise ResearchHistoryUnavailable("registry:run_missing")
        return self._registry_entry(metadata)

    def resolve(self, expected: ResearchHistoryEntry, *,
                read_budget: ResearchHistoryReadBudget | None = None,
                check_cancel: Callable[[], bool] | None = None) -> ResearchHistoryResult:
        """重新核對 exact kind/run/hash/stock/context，回傳原結果，不做比較判定。"""
        reading = _ReadRound(read_budget or self.read_budget, check_cancel)
        reading.cancelled()
        if expected.source_kind == "registry":
            if self.registry is None:
                raise ResearchHistoryUnavailable("registry:source_missing")
            metadata = self.registry.repository.get_metadata(expected.run_id)
            if metadata is None or self._registry_entry(metadata) != expected:
                raise ResearchHistoryUnavailable("selected_source_changed")
            if not expected.result_supported:
                raise ResearchHistoryUnavailable(expected.unsupported_reason)
            if reading.budget is None:
                raise ResearchHistoryUnavailable("registry_read_budget_required")
            loaded = self.registry.load_run_data(
                expected.run_id,
                max_artifact_bytes=reading.budget.max_artifact_bytes,
                max_total_bytes=reading.budget.max_total_bytes,
                check_cancel=check_cancel,
            )
            reading.cancelled()
            if self._registry_entry(loaded.metadata) != expected:
                raise ResearchHistoryUnavailable("selected_source_changed")
            return ResearchHistoryResult(expected, loaded)
        if expected.source_kind not in self.legacy_paths:
            raise ResearchHistoryUnavailable("source_kind_unknown")
        if reading.budget is None:
            raise ResearchHistoryUnavailable("legacy_read_budget_required")
        rows = self._legacy_rows(expected.source_kind, run_id=expected.run_id)
        if len(rows) != 1:
            raise ResearchHistoryUnavailable("selected_source_changed")
        row = rows[0]
        artifacts: dict[str, str | None] = {}
        raw_artifacts: dict[str, bytes] = {}
        for key in ("equity_curve_path", "trade_list_path", "data_path"):
            if row.get(key):
                path = Path(row[key])
                if not path.is_file():
                    raise ResearchHistoryUnavailable("legacy_artifact_missing:" + key)
                artifacts[key], raw_artifacts[key] = reading.read(path, keep=True)
        # 同份待 decode bytes 算 SHA，重建與清單完全相同的 entry/context pin。
        if self._legacy_entry(expected.source_kind, row, artifacts=artifacts) != expected:
            raise ResearchHistoryUnavailable("selected_source_changed")
        reading.verify_sources()
        if expected.source_kind == "legacy_backtest":
            payload = dict(row)
            for key, destination in (("equity_curve_path", "equity_curve"), ("trade_list_path", "trade_list")):
                if row.get(key):
                    path = Path(row[key])
                    if not path.is_file():
                        raise ResearchHistoryUnavailable("legacy_artifact_missing:" + key)
                    raw = raw_artifacts[key]
                    reading.cancelled()
                    payload[destination] = (pd.read_parquet(BytesIO(raw)) if path.suffix == ".parquet"
                        else pd.read_csv(BytesIO(raw), **({"index_col": 0, "parse_dates": True} if destination == "equity_curve" else {})))
        else:
            from app_module.recommendation_portfolio_dtos import RecommendationPortfolioBacktestResultDTO
            path = Path(row.get("data_path") or "")
            if not path.is_file():
                raise ResearchHistoryUnavailable("legacy_artifact_missing:data_path")
            reading.cancelled()
            payload = json.loads(raw_artifacts["data_path"])
            if payload.get("run_id") != expected.run_id:
                raise ResearchHistoryUnavailable("legacy_artifact_run_mismatch")
            payload["result_dto"] = RecommendationPortfolioBacktestResultDTO.from_dict(payload.get("result", {}))
        # decode 後只核對 metadata 與來源 stat，不從路徑第二次讀取不同 bytes。
        rows_after = self._legacy_rows(expected.source_kind, run_id=expected.run_id)
        reading.verify_sources()
        if len(rows_after) != 1 or self._legacy_entry(expected.source_kind, rows_after[0], artifacts=artifacts) != expected:
            raise ResearchHistoryUnavailable("selected_source_changed")
        return ResearchHistoryResult(expected, payload)
