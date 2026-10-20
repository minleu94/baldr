"""明選離線研究輸出的新副本；原件唯讀，金融原件不重新序列化。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
from types import SimpleNamespace
from typing import Any, Callable

from app_module.recommendation_portfolio_calendar_artifact_v1 import _canonical_path
from app_module.research_history_lookup import ResearchHistoryLookup, ResearchHistoryReadBudget
from app_module.research_run_service import ResearchRunService
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.queries import RecommendationExecutionQueries
from data_module.result_artifact_store import ResultArtifactStore

SCHEMA = "research-output-copy.v1"
# 只重綁既有reader實際使用的SQLite欄位，不對JSON／文字做全域取代。
_STORES: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "registry": ("research_runs", "research_runs.db", "research_runs", ("equity_path", "trades_path")),
    "legacy_backtest": ("backtest/runs", "backtest_runs.db", "runs", ("equity_curve_path", "trade_list_path")),
    "legacy_recommendation_portfolio": ("recommendation_portfolio/runs", "recommendation_portfolio_runs.db", "runs", ("data_path",)),
    "recommendation": ("recommendation/runs", "recommendation_runs.db", "runs", ("data_path",)),
}
_STORE_KEYS = {kind: "result_id" if kind == "recommendation" else "run_id" for kind in _STORES}


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


def _inventory(root: Path, budget: ResearchOutputCopyBudget, check: Callable[[], bool] | None,
               *, store_kinds: tuple[str, ...] | None = None) -> dict[str, tuple[tuple[int, int, int, int], str]]:
    result = {}
    selected = store_kinds if store_kinds is not None else tuple(kind for kind in _STORES if kind != "recommendation")
    stack = [root / _STORES[kind][0] for kind in selected if (root / _STORES[kind][0]).exists()]
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


def _rows(path: Path, table: str, maximum: int, check: Callable[[], bool] | None,
          *, key: str = "run_id", optional_table: bool = False) -> list[dict[str, Any]]:
    # table只能來自本模組常數。
    connection = _connection(path)
    try:
        connection.set_progress_handler(lambda: int(check is not None and check()), 1000)
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1").fetchone():
            raise ResearchOutputCopyError("研究索引含非標準trigger／view，不能安全重綁")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ResearchOutputCopyError("來源SQLite integrity_check失敗")
        if optional_table and not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone():
            return []
        if table == "research_runs":
            extra = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='portfolio_scenario_registry'").fetchone()
            if extra and connection.execute("SELECT 1 FROM portfolio_scenario_registry LIMIT 1").fetchone():
                raise ResearchOutputCopyError("配置情境含外部帳本引用，需另核搬移，不能省略")
        rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY {key} LIMIT ?", (maximum + 1,))]
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


@dataclass(frozen=True)
class _RecommendationIdentity:
    metadata_sha256: str
    context_sha256: str


def _recommendation_entries(root: Path, budget: ResearchOutputCopyBudget,
                            check: Callable[[], bool] | None) -> dict[str, _RecommendationIdentity]:
    """沿正常推薦query核原JSON；先拒絕尚無搬移契約的外部ML收據。"""
    runs = root / "recommendation/runs"
    database = runs / "recommendation_runs.db"
    store = ResultArtifactStore(runs / "execution_artifacts", database)
    persistence = RecommendationExecutionPersistence(store)
    canonical = _rows(database, "result_artifact_index", budget.max_runs, check,
                      key="result_id", optional_table=True)
    for row in canonical:
        _cancel(check)
        _record, envelope = persistence.read_verified_envelope(row["result_id"])
        if envelope.execution.ml_receipt_refs:
            raise ResearchOutputCopyError("推薦含外部ML收據，須另核依賴搬移，不能沿舊根補件")
    query = RecommendationExecutionQueries(persistence)
    views = query.list()
    if len(views) > budget.max_runs:
        raise ResearchOutputCopyError("research_copy_run_budget_exceeded")
    result = {}
    for view in views:
        _cancel(check)
        metadata = {"result_id": view.result_id, "label": view.label, "notes": view.notes,
            "persisted_at": view.persisted_at.isoformat() if view.persisted_at else None,
            "payload_hash": view.payload_hash, "schema_version": view.schema_version,
            "schema_revision": view.schema_revision, "integrity_basis": view.integrity_basis,
            "ml_read_status": view.ml_read_status, "diagnostics": view.diagnostics}
        result[view.result_id] = _RecommendationIdentity(
            sha256(json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            view.raw_artifact_sha256)
    return result


def _emit(path: Path, payload: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def copy_research_output(source_output_root: Path, destination_output_root: Path, *,
                         budget: ResearchOutputCopyBudget,
                         include_recommendations: bool = False,
                         check_cancel: Callable[[], bool] | None = None) -> Path:
    """建立明選保存研究與一般推薦的新副本；不啟用新根或修改原件。"""
    if type(budget) is not ResearchOutputCopyBudget:
        raise ResearchOutputCopyError("請明示具型別的複製預算")
    if type(include_recommendations) is not bool:
        raise ResearchOutputCopyError("一般推薦搬移必須明示布林選項")
    store_kinds = tuple(kind for kind in _STORES if include_recommendations or kind != "recommendation")
    _cancel(check_cancel)
    source = _canonical_path(source_output_root, "research_copy_source", allow_missing=False)
    target = _canonical_path(destination_output_root, "research_copy_target", allow_missing=True)
    if os.path.lexists(target) or source.is_relative_to(target) or target.is_relative_to(source):
        raise ResearchOutputCopyError("目的根須不存在且不得與來源重疊")
    for text in (os.environ.get("DATA_ROOT", "F:/Min/Python/Project/FA_Data"), os.environ.get("OUTPUT_ROOT"),
                 os.environ.get("PERSONAL_DATA_ROOT"), os.environ.get("PERSONAL_STORE_ROOT"), os.environ.get("PERSONAL_JOURNAL_ROOT")):
        if text:
            protected = Path(text).absolute()
            if target.is_relative_to(protected) or protected.is_relative_to(target):
                raise ResearchOutputCopyError("目的根不得包含正式／私人根或位於其下")
    before = _inventory(source, budget, check_cancel, store_kinds=store_kinds)
    stores: dict[str, list[dict[str, Any]]] = {}
    rewrites: dict[str, dict[str, dict[str, str]]] = {}
    source_entries = {}
    lookup = _lookup(source, budget)
    count = 0
    for kind, (directory, filename, table, fields) in _STORES.items():
        if kind not in store_kinds:
            continue
        db_relative = directory + "/" + filename
        if db_relative not in before:
            if any(name.startswith(directory + "/") for name in before):
                raise ResearchOutputCopyError("研究檔案缺所屬索引：" + directory)
            continue
        key = _STORE_KEYS[kind]
        rows = _rows(source / db_relative, table, budget.max_runs - count, check_cancel,
                     key=key, optional_table=(kind == "recommendation"))
        count += len(rows)
        if count > budget.max_runs:
            raise ResearchOutputCopyError("research_copy_run_budget_exceeded")
        stores[kind] = rows
        rewrites[kind] = {}
        for row in rows:
            _cancel(check_cancel)
            run_id = row[key]
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
            if kind != "recommendation":
                source_entries[(kind, run_id)] = _entry(lookup, kind, run_id, check_cancel)
        if kind == "recommendation":
            entries = _recommendation_entries(source, budget, check_cancel)
            count += len(entries) - len(rows)
            if count > budget.max_runs:
                raise ResearchOutputCopyError("research_copy_run_budget_exceeded")
            source_entries.update({(kind, identity): value for identity, value in entries.items()})
    if not stores:
        raise ResearchOutputCopyError("明選根沒有受支援的研究索引")
    if _inventory(source, budget, check_cancel, store_kinds=store_kinds) != before:
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
            key = _STORE_KEYS[kind]
            database = target / directory / filename
            connection = sqlite3.connect(database)
            try:
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("BEGIN IMMEDIATE")
                for row in rows:
                    mapped = rewrites[kind][row[key]]
                    if mapped:
                        columns = ",".join(field + "=?" for field in mapped)
                        connection.execute(f"UPDATE {table} SET {columns} WHERE {key}=?", (*mapped.values(), row[key]))
                connection.commit()
            finally:
                connection.close()
            expected = [dict(row, **rewrites[kind][row[key]]) for row in rows]
            if _rows(database, table, len(expected), check_cancel, key=key,
                     optional_table=(kind == "recommendation")) != expected:
                raise ResearchOutputCopyError("新索引有路徑以外的metadata變更")
        destination_before = _inventory(target, budget, check_cancel, store_kinds=store_kinds)
        if destination_before.keys() != before.keys():
            raise ResearchOutputCopyError("新副本檔案集合不符")
        copied_lookup = _lookup(target, budget)
        copied_recommendations = (_recommendation_entries(target, budget, check_cancel)
                                  if "recommendation" in stores else {})
        identities = []
        for (kind, run_id), original in source_entries.items():
            selected = (copied_recommendations[run_id] if kind == "recommendation"
                        else _entry(copied_lookup, kind, run_id, check_cancel))
            if kind == "recommendation" and selected != original:
                raise ResearchOutputCopyError("新推薦副本的原值／metadata／資格不符")
            identities.append({"kind": kind, "run_id": run_id, "source_metadata_sha256": original.metadata_sha256,
                "source_context_sha256": original.context_sha256, "destination_metadata_sha256": selected.metadata_sha256,
                "destination_context_sha256": selected.context_sha256, "rewritten_fields": rewrites[kind].get(run_id, {})})
        changed_db = {directory + "/" + filename for kind, (directory, filename, _, _) in _STORES.items() if kind in stores}
        for relative, (_, digest) in before.items():
            if relative not in changed_db and _digest(target / relative, check_cancel) != digest:
                raise ResearchOutputCopyError("新副本金融原件SHA不符")
        if _inventory(source, budget, check_cancel, store_kinds=store_kinds) != before:
            raise ResearchOutputCopyError("來源在建立新副本期間已變更")
        if _inventory(target, budget, check_cancel, store_kinds=store_kinds) != destination_before:
            raise ResearchOutputCopyError("新副本在reader驗證期間已變更")
        receipt = target / "RESEARCH_COPY_RECEIPT.json"
        _emit(receipt, {"schema": SCHEMA, "status": "copied_and_public_readers_verified",
            "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_output_root": str(source),
            "selected_store_kinds": list(store_kinds),
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


def restore_research_output(archive_directory: Path, archive_receipt_sha256: str,
                            destination_output_root: Path, *, budget: ResearchOutputCopyBudget,
                            check_cancel: Callable[[], bool] | None = None) -> Path:
    """從明選且完整的copy封存恢復新根；原邏輯位置只作比對，絕不開啟。"""
    if type(budget) is not ResearchOutputCopyBudget:
        raise ResearchOutputCopyError("請明示具型別的恢復預算")
    if type(archive_receipt_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", archive_receipt_sha256):
        raise ResearchOutputCopyError("封存恢復需要外部固定收據SHA")
    _cancel(check_cancel)
    source = _canonical_path(archive_directory, "research_restore_archive", allow_missing=False)
    target = _canonical_path(destination_output_root, "research_restore_target", allow_missing=True)
    if os.path.lexists(target) or source.is_relative_to(target) or target.is_relative_to(source):
        raise ResearchOutputCopyError("恢復目的根須不存在且不得與封存重疊")
    for text in (os.environ.get("DATA_ROOT", "F:/Min/Python/Project/FA_Data"), os.environ.get("OUTPUT_ROOT"),
                 os.environ.get("PERSONAL_DATA_ROOT"), os.environ.get("PERSONAL_STORE_ROOT"), os.environ.get("PERSONAL_JOURNAL_ROOT")):
        if text:
            protected = Path(text).absolute()
            if target.is_relative_to(protected) or protected.is_relative_to(target):
                raise ResearchOutputCopyError("恢復目的根不得包含正式／私人根或位於其下")
    if any(os.path.lexists(source / name) for name in (".research_copy_pending.json", "RESEARCH_COPY_FAILURE.json")):
        raise ResearchOutputCopyError("封存仍pending或有失敗標記")
    receipt_path = _canonical_path(source / "RESEARCH_COPY_RECEIPT.json", "research_restore_receipt", allow_missing=False)
    receipt_stamp = _stamp(receipt_path)
    if receipt_stamp[0] > budget.max_file_bytes:
        raise ResearchOutputCopyError("封存收據超過單檔預算")
    with receipt_path.open("rb") as receipt_stream:
        raw = receipt_stream.read(budget.max_file_bytes + 1)
    if len(raw) != receipt_stamp[0] or sha256(raw).hexdigest() != archive_receipt_sha256 or _stamp(receipt_path) != receipt_stamp:
        raise ResearchOutputCopyError("封存收據SHA不符或讀取中變更")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ResearchOutputCopyError("封存收據JSON鍵重複")
            result[key] = value
        return result
    def invalid_constant(value: str) -> None:
        raise ResearchOutputCopyError("封存收據含非有限JSON常數：" + value)
    proof = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
    if (not isinstance(proof, dict) or proof.get("schema") != SCHEMA
            or proof.get("status") not in {"copied_and_public_readers_verified", "restored_and_public_readers_verified"}
            or proof.get("source_unchanged") is not True or proof.get("financial_artifacts_reencoded") is not False
            or proof.get("configuration_activated") is not False):
        raise ResearchOutputCopyError("封存不是已核且未重編金融原件的copy收據")
    declared = proof.get("selected_store_kinds")
    choices = ([kind for kind in _STORES if kind != "recommendation"], list(_STORES))
    if type(declared) is not list or declared not in choices:
        raise ResearchOutputCopyError("封存store範圍不支援")
    kinds = tuple(declared)
    logical_value = proof.get("destination_output_root")
    if type(logical_value) is not str or not Path(logical_value).is_absolute() or ".." in Path(logical_value).parts:
        raise ResearchOutputCopyError("封存原邏輯根缺失或不明確")
    logical = Path(logical_value)
    manifest = proof.get("destination_files")
    if type(manifest) is not list or len(manifest) >= budget.max_entries:
        raise ResearchOutputCopyError("封存檔案清冊缺失或超限")
    expected_files: dict[str, tuple[int, str]] = {}
    for item in manifest:
        if not isinstance(item, dict):
            raise ResearchOutputCopyError("封存檔案清冊列格式錯誤")
        name, size, digest = item.get("path"), item.get("bytes"), item.get("sha256")
        if (type(name) is not str or not name or "\\" in name or ":" in name or PurePosixPath(name).is_absolute()
                or ".." in PurePosixPath(name).parts or PurePosixPath(name).as_posix() != name or name in expected_files
                or type(size) is not int or size < 0 or type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ResearchOutputCopyError("封存清冊路徑、大小、SHA或唯一性不符")
        expected_files[name] = (size, digest)
    if sum(size for size, _ in expected_files.values()) + len(raw) > budget.max_total_bytes:
        raise ResearchOutputCopyError("封存含收據的總bytes超過預算")
    before = _inventory(source, budget, check_cancel, store_kinds=kinds)
    if {name: (stamp[0], digest) for name, (stamp, digest) in before.items()} != expected_files:
        raise ResearchOutputCopyError("封存完整檔案集合或原件SHA不符")
    stores: dict[str, list[dict[str, Any]]] = {}
    rewrites: dict[str, dict[str, dict[str, str]]] = {}
    expected_ids: set[tuple[str, str]] = set()
    count = 0
    for kind in kinds:
        directory, filename, table, fields = _STORES[kind]
        relative_db = directory + "/" + filename
        if relative_db not in before:
            if any(name.startswith(directory + "/") for name in before):
                raise ResearchOutputCopyError("封存研究缺所屬索引")
            continue
        key = _STORE_KEYS[kind]
        rows = _rows(source / relative_db, table, budget.max_runs - count, check_cancel,
                     key=key, optional_table=kind == "recommendation")
        count += len(rows)
        stores[kind], rewrites[kind] = rows, {}
        for row in rows:
            mapped: dict[str, str] = {}
            identifier = row[key]
            expected_ids.add((kind, identifier))
            for field in fields:
                value = row.get(field)
                if not value:
                    continue
                if type(value) is not str or not Path(value).is_absolute() or ".." in Path(value).parts:
                    raise ResearchOutputCopyError("封存索引路徑不是明確絕對路徑")
                try:
                    relative = Path(value).relative_to(logical).as_posix()
                except ValueError as error:
                    raise ResearchOutputCopyError("封存索引跳出原邏輯根") from error
                if relative not in before or not relative.startswith(directory + "/"):
                    raise ResearchOutputCopyError("封存索引不是同store已核原件")
                mapped[field] = str(target / relative)
            rewrites[kind][identifier] = mapped
        if kind == "recommendation":
            canonical = _rows(source / relative_db, "result_artifact_index", budget.max_runs, check_cancel,
                              key="result_id", optional_table=True)
            expected_ids.update((kind, row["result_id"]) for row in canonical)
    runs = proof.get("runs")
    if type(runs) is not list or len(runs) > budget.max_runs or not stores or count > budget.max_runs:
        raise ResearchOutputCopyError("封存研究清冊缺失或超過run預算")
    for item in runs:
        if (not isinstance(item, dict) or type(item.get("kind")) is not str or item["kind"] not in kinds
                or type(item.get("run_id")) is not str or not item["run_id"]
                or any(type(item.get(field)) is not str or not re.fullmatch(
                       ("sha256:" if item["kind"] == "recommendation" and field == "destination_context_sha256" else "") + r"[0-9a-f]{64}", item[field])
                       for field in ("destination_metadata_sha256", "destination_context_sha256"))):
            raise ResearchOutputCopyError("封存研究身分或固定SHA格式不符")
    declared_ids = [(item["kind"], item["run_id"]) for item in runs]
    if len(declared_ids) != len(runs) or len(set(declared_ids)) != len(runs) or set(declared_ids) != expected_ids:
        raise ResearchOutputCopyError("封存研究身分與索引清冊不符")
    def verify_archive() -> None:
        if (_stamp(receipt_path) != receipt_stamp or _digest(receipt_path, check_cancel) != archive_receipt_sha256
                or _inventory(source, budget, check_cancel, store_kinds=kinds) != before):
            raise ResearchOutputCopyError("封存在恢復過程中變更")
    verify_archive()
    target.mkdir(parents=True, exist_ok=False)
    pending = target / ".research_copy_pending.json"
    _emit(pending, {"schema": SCHEMA, "archive_receipt_sha256": archive_receipt_sha256})
    try:
        for name, (_, digest) in before.items():
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            _canonical_path(destination, "research_restore_target", allow_missing=True)
            if _digest(source / name, check_cancel, destination) != digest:
                raise ResearchOutputCopyError("恢復過程的封存原件SHA變更")
        for kind, rows in stores.items():
            directory, filename, table, _ = _STORES[kind]
            key = _STORE_KEYS[kind]
            database = target / directory / filename
            connection = sqlite3.connect(database)
            try:
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("BEGIN IMMEDIATE")
                for row in rows:
                    _cancel(check_cancel)
                    mapped = rewrites[kind][row[key]]
                    if mapped:
                        columns = ",".join(field + "=?" for field in mapped)
                        connection.execute(f"UPDATE {table} SET {columns} WHERE {key}=?", (*mapped.values(), row[key]))
                connection.commit()
            finally:
                connection.close()
            if _rows(database, table, len(rows), check_cancel, key=key, optional_table=kind == "recommendation") != [
                    dict(row, **rewrites[kind][row[key]]) for row in rows]:
                raise ResearchOutputCopyError("恢復索引有路徑以外的metadata變更")
        after = _inventory(target, budget, check_cancel, store_kinds=kinds)
        changed_db = {directory + "/" + filename for kind, (directory, filename, _, _) in _STORES.items() if kind in stores}
        if after.keys() != before.keys() or any(after[name][1] != digest for name, (_, digest) in before.items() if name not in changed_db):
            raise ResearchOutputCopyError("恢復副本金融原件bytes或集合改變")
        lookup = _lookup(target, budget)
        recommendations = _recommendation_entries(target, budget, check_cancel) if "recommendation" in stores else {}
        identities = []
        for original in runs:
            kind, identifier = original["kind"], original["run_id"]
            current = recommendations[identifier] if kind == "recommendation" else _entry(lookup, kind, identifier, check_cancel)
            if kind == "recommendation" and (current.metadata_sha256 != original["destination_metadata_sha256"]
                                            or current.context_sha256 != original["destination_context_sha256"]):
                raise ResearchOutputCopyError("恢復推薦的原值／metadata／資格不符")
            identities.append({"kind": kind, "run_id": identifier,
                "source_metadata_sha256": original["destination_metadata_sha256"],
                "source_context_sha256": original["destination_context_sha256"],
                "destination_metadata_sha256": current.metadata_sha256, "destination_context_sha256": current.context_sha256,
                "rewritten_fields": rewrites[kind].get(identifier, {})})
        verify_archive()
        if _inventory(target, budget, check_cancel, store_kinds=kinds) != after:
            raise ResearchOutputCopyError("恢復副本在public reader驗證中變更")
        original_receipt = target / "original/RESEARCH_COPY_RECEIPT.json"
        original_receipt.parent.mkdir()
        if _digest(receipt_path, check_cancel, original_receipt) != archive_receipt_sha256:
            raise ResearchOutputCopyError("封存收據在最後核驗時變更")
        receipt = target / "RESEARCH_COPY_RECEIPT.json"
        _emit(receipt, {"schema": SCHEMA, "status": "restored_and_public_readers_verified",
            "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_output_root": str(source),
            "destination_output_root": str(target), "selected_store_kinds": list(kinds), "runs": identities,
            "archive_receipt_sha256": archive_receipt_sha256, "archive_unchanged": True,
            "source_files": manifest, "destination_files": [{"path": name, "bytes": stamp[0], "sha256": digest}
                for name, (stamp, digest) in after.items()], "source_unchanged": True, "financial_artifacts_reencoded": False,
            "configuration_activated": False, "full_environment_portability_accepted": False, "full_gate_accepted": False})
        pending.unlink()
        return receipt
    except Exception as error:
        _emit(target / "RESEARCH_COPY_FAILURE.json", {"schema": SCHEMA, "reason": str(error)[:2048]})
        raise
