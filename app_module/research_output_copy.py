"""明選離線研究輸出的新副本；原件唯讀，金融原件不重新序列化。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import stat
from types import SimpleNamespace
from typing import Any, Callable

from app_module.recommendation_portfolio_calendar_artifact_v1 import _canonical_path
from app_module.research_history_lookup import ResearchHistoryLookup, ResearchHistoryReadBudget
from app_module.research_run_service import ResearchRunService

SCHEMA = "research-output-copy.v1"
# 只重綁既有reader實際使用的SQLite欄位，不對JSON／文字做全域取代。
_STORES: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "registry": ("research_runs", "research_runs.db", "research_runs", ("equity_path", "trades_path")),
    "legacy_backtest": ("backtest/runs", "backtest_runs.db", "runs", ("equity_curve_path", "trade_list_path")),
    "legacy_recommendation_portfolio": ("recommendation_portfolio/runs", "recommendation_portfolio_runs.db", "runs", ("data_path",)),
}


class ResearchOutputCopyError(ValueError):
    """不完整來源、越界或新副本未通過；原件保持。"""


@dataclass(frozen=True, slots=True)
class ResearchOutputCopyBudget:
    max_file_bytes: int
    max_total_bytes: int
    max_entries: int
    max_runs: int

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in (
            self.max_file_bytes, self.max_total_bytes, self.max_entries, self.max_runs,
        )):
            raise ResearchOutputCopyError("複製預算必須是正整數")


def _cancel(check: Callable[[], bool] | None) -> None:
    if check is not None and check():
        raise ResearchOutputCopyError("research_copy_cancelled")


def _stamp(path: Path) -> tuple[int, int, int, int]:
    value = path.lstat()
    if (not stat.S_ISREG(value.st_mode)
            or getattr(value, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
        raise ResearchOutputCopyError("來源不是一般檔案：" + str(path))
    return value.st_size, value.st_mtime_ns, value.st_dev, value.st_ino


def _digest(path: Path, check: Callable[[], bool] | None, destination: Path | None = None) -> str:
    before = _stamp(path)
    digest = sha256()
    copied = 0
    writer = destination.open("xb") if destination is not None else None
    try:
        with path.open("rb") as reader:
            opened = os.fstat(reader.fileno())
            if (opened.st_size, opened.st_mtime_ns, opened.st_dev, opened.st_ino) != before:
                raise ResearchOutputCopyError("來源讀取前已變更")
            while True:
                _cancel(check)
                block = reader.read(64 * 1024)
                if not block:
                    break
                copied += len(block)
                if copied > before[0]:
                    raise ResearchOutputCopyError("來源讀取中增長")
                digest.update(block)
                if writer is not None:
                    writer.write(block)
        if copied != before[0] or _stamp(path) != before:
            raise ResearchOutputCopyError("來源讀取中已變更")
        if writer is not None:
            writer.flush()
            os.fsync(writer.fileno())
    finally:
        if writer is not None:
            writer.close()
    return digest.hexdigest()


def _inventory(root: Path, budget: ResearchOutputCopyBudget, check: Callable[[], bool] | None) -> dict[str, tuple[tuple[int, int, int, int], str]]:
    result = {}
    stack = [root / item[0] for item in _STORES.values() if (root / item[0]).exists()]
    entries = 0
    total = 0
    while stack:
        directory = stack.pop()
        _canonical_path(directory, "research_copy_source", allow_missing=False)
        for child in sorted(directory.iterdir()):
            _cancel(check)
            entries += 1
            if entries > budget.max_entries:
                raise ResearchOutputCopyError("research_copy_entry_budget_exceeded")
            _canonical_path(child, "research_copy_source", allow_missing=False)
            if child.is_dir():
                stack.append(child)
                continue
            stamp = _stamp(child)
            total += stamp[0]
            if stamp[0] > budget.max_file_bytes or total > budget.max_total_bytes:
                raise ResearchOutputCopyError("research_copy_byte_budget_exceeded")
            relative = child.relative_to(root).as_posix()
            if relative.startswith("research_runs/staging/") or child.name.endswith(("-wal", "-shm", "-journal")):
                raise ResearchOutputCopyError("來源仍有staging或SQLite journal，請先關閉保存程序")
            result[relative] = (stamp, _digest(child, check))
    return result


def _connection(path: Path) -> sqlite3.Connection:
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(str(path) + suffix).exists():
            raise ResearchOutputCopyError("來源SQLite尚有journal")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _rows(path: Path, table: str, maximum: int, check: Callable[[], bool] | None) -> list[dict[str, Any]]:
    # table只能來自本模組常數。
    connection = _connection(path)
    try:
        connection.set_progress_handler(lambda: int(check is not None and check()), 1000)
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1").fetchone():
            raise ResearchOutputCopyError("研究索引含非標準trigger／view，不能安全重綁")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ResearchOutputCopyError("來源SQLite integrity_check失敗")
        if table == "research_runs":
            extra = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='portfolio_scenario_registry'").fetchone()
            if extra and connection.execute("SELECT 1 FROM portfolio_scenario_registry LIMIT 1").fetchone():
                raise ResearchOutputCopyError("配置情境含外部帳本引用，需另核搬移，不能省略")
        rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY run_id LIMIT ?", (maximum + 1,))]
        if len(rows) > maximum:
            raise ResearchOutputCopyError("research_copy_run_budget_exceeded")
        return rows
    finally:
        connection.close()


def _lookup(root: Path, budget: ResearchOutputCopyBudget) -> ResearchHistoryLookup:
    config = SimpleNamespace(research_run_db_file=root / "research_runs/research_runs.db",
        research_run_parquet_dir=root / "research_runs/parquet", research_run_staging_dir=root / "research_runs/staging")
    return ResearchHistoryLookup(registry=ResearchRunService(config),
        legacy_backtest_db=root / "backtest/runs/backtest_runs.db",
        legacy_portfolio_db=root / "recommendation_portfolio/runs/recommendation_portfolio_runs.db",
        read_budget=ResearchHistoryReadBudget(budget.max_file_bytes, budget.max_total_bytes))


def _entry(lookup: ResearchHistoryLookup, kind: str, run_id: str, check: Callable[[], bool] | None):
    selected = (lookup.select_registry_run(run_id, check_cancel=check) if kind == "registry"
                else lookup.select_legacy_run(kind, run_id, check_cancel=check))
    lookup.resolve(selected, check_cancel=check)
    return selected


def _emit(path: Path, payload: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def copy_research_output(source_output_root: Path, destination_output_root: Path, *,
                         budget: ResearchOutputCopyBudget,
                         check_cancel: Callable[[], bool] | None = None) -> Path:
    """只建立明選三個研究store的新副本；不啟用新根、不改原件或正式設定。"""
    if type(budget) is not ResearchOutputCopyBudget:
        raise ResearchOutputCopyError("請明示具型別的複製預算")
    _cancel(check_cancel)
    source = _canonical_path(source_output_root, "research_copy_source", allow_missing=False)
    target = _canonical_path(destination_output_root, "research_copy_target", allow_missing=True)
    if os.path.lexists(target) or source.is_relative_to(target) or target.is_relative_to(source):
        raise ResearchOutputCopyError("目的根須不存在且不得與來源重疊")
    for text in (os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data"), os.environ.get("OUTPUT_ROOT"),
                 os.environ.get("PERSONAL_DATA_ROOT"), os.environ.get("PERSONAL_STORE_ROOT"), os.environ.get("PERSONAL_JOURNAL_ROOT")):
        if text:
            protected = Path(text).absolute()
            if target.is_relative_to(protected) or protected.is_relative_to(target):
                raise ResearchOutputCopyError("目的根不得包含正式／私人根或位於其下")
    before = _inventory(source, budget, check_cancel)
    stores: dict[str, list[dict[str, Any]]] = {}
    rewrites: dict[str, dict[str, dict[str, str]]] = {}
    source_entries = {}
    lookup = _lookup(source, budget)
    count = 0
    for kind, (directory, filename, table, fields) in _STORES.items():
        db_relative = directory + "/" + filename
        if db_relative not in before:
            if any(name.startswith(directory + "/") for name in before):
                raise ResearchOutputCopyError("研究檔案缺所屬索引：" + directory)
            continue
        rows = _rows(source / db_relative, table, budget.max_runs - count, check_cancel)
        count += len(rows)
        if count > budget.max_runs:
            raise ResearchOutputCopyError("research_copy_run_budget_exceeded")
        stores[kind] = rows
        rewrites[kind] = {}
        for row in rows:
            _cancel(check_cancel)
            run_id = row["run_id"]
            mapped = {}
            for field in fields:
                value = row.get(field)
                if not value:
                    continue
                if type(value) is not str or not Path(value).is_absolute() or ".." in Path(value).parts:
                    raise ResearchOutputCopyError("索引原路徑不是明確絕對路徑")
                try:
                    relative = Path(value).relative_to(source).as_posix()
                except ValueError as error:
                    raise ResearchOutputCopyError("索引指向明選來源根之外") from error
                if relative not in before or not relative.startswith(directory + "/"):
                    raise ResearchOutputCopyError("索引不是同store已核原件")
                mapped[field] = str(target / relative)
            rewrites[kind][run_id] = mapped
            # 先核明選來源邊界，不能讓舊reader先讀到索引指向的外部檔案。
            source_entries[(kind, run_id)] = _entry(lookup, kind, run_id, check_cancel)
    if not stores:
        raise ResearchOutputCopyError("明選根沒有受支援的研究索引")
    if _inventory(source, budget, check_cancel) != before:
        raise ResearchOutputCopyError("來源在驗證期間已變更")
    target.mkdir(parents=True, exist_ok=False)
    pending = target / ".research_copy_pending.json"
    _emit(pending, {"schema": SCHEMA, "source": str(source)})
    try:
        for relative, (_, digest) in before.items():
            copied = target / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            _canonical_path(copied, "research_copy_target", allow_missing=True)
            if _digest(source / relative, check_cancel, copied) != digest:
                raise ResearchOutputCopyError("複製時來源SHA變更")
        for kind, rows in stores.items():
            directory, filename, table, _ = _STORES[kind]
            database = target / directory / filename
            connection = sqlite3.connect(database)
            try:
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("BEGIN IMMEDIATE")
                for row in rows:
                    mapped = rewrites[kind][row["run_id"]]
                    if mapped:
                        columns = ",".join(field + "=?" for field in mapped)
                        connection.execute(f"UPDATE {table} SET {columns} WHERE run_id=?", (*mapped.values(), row["run_id"]))
                connection.commit()
            finally:
                connection.close()
            expected = [dict(row, **rewrites[kind][row["run_id"]]) for row in rows]
            if _rows(database, table, len(expected), check_cancel) != expected:
                raise ResearchOutputCopyError("新索引有路徑以外的metadata變更")
        destination_before = _inventory(target, budget, check_cancel)
        if destination_before.keys() != before.keys():
            raise ResearchOutputCopyError("新副本檔案集合不符")
        copied_lookup = _lookup(target, budget)
        identities = []
        for (kind, run_id), original in source_entries.items():
            selected = _entry(copied_lookup, kind, run_id, check_cancel)
            identities.append({"kind": kind, "run_id": run_id, "source_metadata_sha256": original.metadata_sha256,
                "source_context_sha256": original.context_sha256, "destination_metadata_sha256": selected.metadata_sha256,
                "destination_context_sha256": selected.context_sha256, "rewritten_fields": rewrites[kind][run_id]})
        changed_db = {directory + "/" + filename for kind, (directory, filename, _, _) in _STORES.items() if kind in stores}
        for relative, (_, digest) in before.items():
            if relative not in changed_db and _digest(target / relative, check_cancel) != digest:
                raise ResearchOutputCopyError("新副本金融原件SHA不符")
        if _inventory(source, budget, check_cancel) != before:
            raise ResearchOutputCopyError("來源在建立新副本期間已變更")
        if _inventory(target, budget, check_cancel) != destination_before:
            raise ResearchOutputCopyError("新副本在reader驗證期間已變更")
        receipt = target / "RESEARCH_COPY_RECEIPT.json"
        _emit(receipt, {"schema": SCHEMA, "status": "copied_and_public_readers_verified",
            "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_output_root": str(source),
            "destination_output_root": str(target), "runs": identities,
            "source_files": [{"path": name, "bytes": stamp[0], "sha256": digest} for name, (stamp, digest) in before.items()],
            "destination_files": [{"path": name, "bytes": stamp[0], "sha256": digest} for name, (stamp, digest) in destination_before.items()],
            "source_unchanged": True, "financial_artifacts_reencoded": False, "configuration_activated": False,
            "full_environment_portability_accepted": False, "full_gate_accepted": False})
        pending.unlink()
        return receipt
    except Exception as error:
        _emit(target / "RESEARCH_COPY_FAILURE.json", {"schema": SCHEMA, "reason": str(error)[:2048]})
        raise
