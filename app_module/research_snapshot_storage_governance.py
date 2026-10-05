"""研究快照長期儲存的唯讀盤點與保留候選清單。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Mapping, Sequence

from app_module.daily_market_research_bookmark import (
    DailyMarketResearchBookmark,
    OriginalStockRankingBookmark,
    decode_daily_market_research_bookmark,
)
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
    DAILY_MARKET_SNAPSHOT_MAX_ARTIFACT_BYTES,
    DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES,
    DAILY_MARKET_SNAPSHOT_MAX_POINTER_BYTES,
    DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA,
    snapshot_manifest_identity_sha256,
    _validate_method_contract_binding,
)
from app_module.daily_market_feature_snapshot import DAILY_MARKET_FEATURE_CONTRACT_VERSION
from app_module.original_stock_ranking import (
    ORIGINAL_RANKING_ARTIFACT_SCHEMA,
    ORIGINAL_RANKING_MANIFEST_SCHEMA,
    ORIGINAL_RANKING_POINTER_SCHEMA,
)
from data_module.ml_storage_capacity import (
    BYTES_PER_GIB,
    evaluate_capacity,
    filesystem_usage,
    heavy_chain_capacity_budget,
)
from data_module.watchlist_repository import WatchlistRepository
from data_module.watchlist_item_storage import WatchlistStorageCapacityError


SCHEMA_VERSION = "research-snapshot-storage-governance.v1"
MAX_RETAINED_BYTES = 64 * 1024 * 1024
MAX_RETAINED_ENTRIES = 4096
MAX_BATCH_NEW_BYTES = 8 * 1024 * 1024
MAX_TEMPORARY_PEAK_BYTES = 8 * 1024 * 1024
MAX_SCAN_HASH_BYTES = 64 * 1024 * 1024
MAX_WATCHLIST_DB_BYTES = 32 * 1024 * 1024
MAX_WATCHLIST_JSON_BYTES = 1024 * 1024
MAX_WATCHLIST_PAYLOAD_BYTES = 4 * 1024 * 1024
MAX_WATCHLIST_ROWS = 4096
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TEMP_NAMES = {".staging", ".tmp", "staging", "tmp"}
_WATCHLIST_COLUMNS = {
    "watchlists": {"watchlist_id", "payload_json", "revision", "source_hash", "is_deleted", "last_revision_id"},
    "watchlist_revisions": {
        "revision_id", "watchlist_id", "revision", "operation", "payload_json", "payload_hash",
        "source_hash", "identity_status", "continuity_event_id", "revision_of", "created_at",
    },
}
_FEATURE_OBJECT_KEYS = {
    "contract_version", "snapshot_identity_sha256", "input_fingerprint_sha256", "stock_code",
    "decision_date", "scope_identity", "market_date", "features", "conditions",
    "method_contracts", "method_contracts_sha256", "policy",
}


class StorageGovernanceError(ValueError):
    """儲存盤點遇到未知或超出界線的資料。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class StorageGrowthSample:
    """帶時區的歷史留存量樣本；bytes 使用整數。"""

    observed_at_utc: datetime
    retained_bytes: int


@dataclass(frozen=True, slots=True)
class _Entry:
    path: Path
    relative: str
    size_bytes: int
    modified_ns: int
    is_directory: bool


class _Budget:
    def __init__(self) -> None:
        self.entries = 0
        self.bytes_read = 0

    def add_entry(self) -> None:
        self.entries += 1
        if self.entries > MAX_RETAINED_ENTRIES:
            raise StorageGovernanceError("scan_entry_budget_exceeded", "掃描超過 entries 上限")

    def add_read(self, size: int) -> None:
        if self.bytes_read + size > MAX_SCAN_HASH_BYTES:
            raise StorageGovernanceError("scan_byte_budget_exceeded", "掃描超過讀取/hash bytes 上限")
        self.bytes_read += size


def preflight_research_snapshot_publication(
    *,
    output_root: Path,
    persistent_existing_bytes: int,
    persistent_new_bytes: int,
    temporary_peak_bytes: int,
    temporary_root: Path | None = None,
    stage: str = "before_immutable_writes",
) -> dict[str, Any]:
    """提供 producer 可選用的有界容量預檢，不掃描 manifest/hash/reference inventory。"""
    for name, value in (
        ("persistent_existing_bytes", persistent_existing_bytes),
        ("persistent_new_bytes", persistent_new_bytes),
        ("temporary_peak_bytes", temporary_peak_bytes),
    ):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} 必須為非負整數 bytes")
    if persistent_new_bytes > MAX_BATCH_NEW_BYTES:
        raise StorageGovernanceError("batch_growth_budget_exceeded", "單批新增超過 8 MiB 上限")
    if temporary_peak_bytes > MAX_TEMPORARY_PEAK_BYTES:
        raise StorageGovernanceError("temporary_budget_exceeded", "暫存峰值超過 8 MiB 上限")
    root = Path(output_root)
    temporary = Path(temporary_root) if temporary_root is not None else root
    budget = heavy_chain_capacity_budget(
        persistent_new_bytes_budget=MAX_BATCH_NEW_BYTES,
        temporary_peak_bytes_budget=MAX_TEMPORARY_PEAK_BYTES,
    )
    paths = [root] if _same_filesystem_probe(root, temporary) else [root, temporary]
    checks = [
        evaluate_capacity(
            budget=budget,
            usage=filesystem_usage(path),
            stage=stage,
            persistent_existing_bytes=persistent_existing_bytes,
            persistent_new_bytes_estimate=persistent_new_bytes,
            temporary_peak_bytes_observed=temporary_peak_bytes,
        ).as_dict()
        for path in paths
    ]
    preflight = dict(checks[0])
    preflight["filesystem_checks"] = checks
    preflight["within_budget"] = all(bool(check.get("within_budget")) for check in checks)
    preflight.update(
        {
            "persistent_existing_bytes_observed": persistent_existing_bytes,
            "central_reserve_source": "data_module.ml_storage_capacity.heavy_chain_capacity_budget",
            "central_reserve_bytes": budget.safety_reserve_bytes,
            "central_reserve_gib": budget.safety_reserve_bytes // BYTES_PER_GIB,
        }
    )
    return preflight


def diagnose_research_snapshot_storage(
    snapshot_root: Path,
    *,
    rank_root: Path | None = None,
    watchlist_dir: Path | None = None,
    watchlist_inventory_complete: bool = False,
    previous_samples: Sequence[StorageGrowthSample] = (),
    observed_batch_growth_bytes: int | None = None,
    observed_at_utc: datetime | None = None,
) -> dict[str, Any]:
    """唯讀盤點 feature/rank 快照、Watchlist pin、容量及 dry-run 候選。"""
    root = Path(snapshot_root).expanduser()
    effective_rank_root = Path(rank_root).expanduser() if rank_root is not None else root / "original_rankings"
    now = _aware_utc(observed_at_utc or datetime.now(timezone.utc))
    issues: list[dict[str, str]] = []
    budget = _Budget()
    entries: list[_Entry] = []
    storage_complete = True
    busy = False
    try:
        if _path_key(effective_rank_root) == _path_key(root / "original_rankings"):
            entries = _scan_tree(root, budget)
        else:
            entries = _scan_tree(root, budget, ignore_top_level={"original_rankings"})
            entries.extend(
                _Entry(item.path, f"original_rankings/{item.relative}", item.size_bytes, item.modified_ns, item.is_directory)
                for item in _scan_tree(effective_rank_root, budget)
            )
    except (OSError, StorageGovernanceError) as exc:
        storage_complete = False
        issues.append(_issue(exc))

    features: set[str] = set()
    ranks: set[str] = set()
    feature_objects: set[str] = set()
    rank_objects: set[str] = set()
    feature_object_refs: set[str] = set()
    rank_object_refs: set[str] = set()
    feature_pins: set[str] = set()
    rank_pins: dict[str, str] = {}
    rank_parent: dict[str, str] = {}
    feature_identity: dict[str, str] = {}
    rank_identity: dict[str, str] = {}
    temp_entries: list[_Entry] = []
    counts = {"feature_manifests": 0, "rank_manifests": 0, "feature_objects": 0,
              "rank_objects": 0, "feature_pointers": 0, "rank_pointers": 0, "unknown_entries": 0}

    if storage_complete:
        for entry in entries:
            if entry.is_directory:
                continue
            parts = Path(entry.relative).parts
            if any(part.lower() in _TEMP_NAMES for part in parts) or entry.path.name.lower().endswith(".tmp"):
                temp_entries.append(entry)
                continue
            if entry.path.name.lower().endswith(".lock"):
                busy = True
                issues.append({"code": "writer_lock_present", "message": "發現 writer lock；候選清單停用"})
                continue
            kind, digest = _classify(entry.relative)
            if kind == "unknown":
                counts["unknown_entries"] += 1
                storage_complete = False
                issues.append({"code": "unknown_storage_entry", "message": entry.relative})
                continue
            try:
                if kind == "feature_pointer":
                    counts["feature_pointers"] += 1
                    payload, _ = _read_json(entry.path, DAILY_MARKET_SNAPSHOT_MAX_POINTER_BYTES, budget)
                    if set(payload) != {"schema_version", "manifest_sha256"} or payload.get("schema_version") != DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA:
                        raise StorageGovernanceError("feature_pointer_schema_unknown", "feature pointer schema 未知")
                    feature_pins.add(_sha(payload.get("manifest_sha256")))
                elif kind == "rank_pointer":
                    counts["rank_pointers"] += 1
                    payload, _ = _read_json(entry.path, 16 * 1024, budget)
                    keys = {"schema_version", "period", "direction", "manifest_sha256", "parent_manifest_sha256"}
                    if set(payload) != keys or payload.get("schema_version") != ORIGINAL_RANKING_POINTER_SCHEMA:
                        raise StorageGovernanceError("rank_pointer_schema_unknown", "rank pointer schema 未知")
                    if payload.get("period") not in {"day", "week"} or payload.get("direction") not in {"strong", "weak"}:
                        raise StorageGovernanceError("rank_pointer_scope_invalid", "rank pointer scope 無效")
                    rank_pins[_sha(payload["manifest_sha256"])] = _sha(payload["parent_manifest_sha256"])
                else:
                    limit = _file_limit(kind)
                    payload, raw = _read_json(entry.path, limit, budget)
                    if hashlib.sha256(raw).hexdigest() != digest:
                        raise StorageGovernanceError("artifact_hash_mismatch", "內容 hash 與檔名不符")
                    if kind == "feature_manifest":
                        if payload.get("schema_version") != DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA:
                            raise StorageGovernanceError("feature_manifest_schema_unknown", "v1/未知 feature schema 全部保留")
                        if snapshot_manifest_identity_sha256(payload) != payload.get("manifest_identity_sha256"):
                            raise StorageGovernanceError("feature_manifest_identity_mismatch", "feature manifest identity 不符")
                        records = payload.get("stocks")
                        if not isinstance(records, list) or not records:
                            raise StorageGovernanceError("feature_manifest_references_incomplete", "feature stocks 不完整")
                        feature_object_refs.update(_sha(row.get("artifact_sha256")) for row in records if isinstance(row, Mapping))
                        if any(not isinstance(row, Mapping) for row in records):
                            raise StorageGovernanceError("feature_manifest_references_incomplete", "feature stock row 無效")
                        features.add(digest)
                        feature_identity[digest] = str(payload["manifest_identity_sha256"])
                        counts["feature_manifests"] += 1
                    elif kind == "rank_manifest":
                        if payload.get("schema_version") != ORIGINAL_RANKING_MANIFEST_SCHEMA:
                            raise StorageGovernanceError("rank_manifest_schema_unknown", "未知 rank schema 全部保留")
                        identity_body = {key: value for key, value in payload.items() if key != "manifest_identity_sha256"}
                        if hashlib.sha256(_canonical(identity_body)).hexdigest() != payload.get("manifest_identity_sha256"):
                            raise StorageGovernanceError("rank_manifest_identity_mismatch", "rank manifest identity 不符")
                        rank_object_refs.add(_sha(payload.get("artifact_sha256")))
                        ranks.add(digest)
                        rank_parent[digest] = _sha(payload.get("parent_manifest_sha256"))
                        rank_identity[digest] = str(payload["manifest_identity_sha256"])
                        counts["rank_manifests"] += 1
                    elif kind == "feature_object":
                        if set(payload) != _FEATURE_OBJECT_KEYS or payload.get("contract_version") != DAILY_MARKET_FEATURE_CONTRACT_VERSION:
                            raise StorageGovernanceError("feature_object_schema_unknown", "feature object contract/version 未知")
                        for key in ("features", "conditions", "method_contracts", "policy"):
                            if not isinstance(payload.get(key), Mapping):
                                raise StorageGovernanceError("feature_object_schema_unknown", f"feature object 欄位無效：{key}")
                        _sha(payload.get("snapshot_identity_sha256"))
                        _sha(payload.get("input_fingerprint_sha256"))
                        _sha(payload.get("method_contracts_sha256"))
                        _validate_method_contract_binding(payload.get("method_contracts"), payload.get("method_contracts_sha256"))
                        feature_objects.add(digest)
                        counts["feature_objects"] += 1
                    elif kind == "rank_object":
                        if payload.get("schema_version") != ORIGINAL_RANKING_ARTIFACT_SCHEMA:
                            raise StorageGovernanceError("rank_artifact_schema_unknown", "rank artifact schema 未知")
                        rank_objects.add(digest)
                        counts["rank_objects"] += 1
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                storage_complete = False
                issues.append(_issue(exc, entry.relative))

    for digest in feature_pins - features:
        storage_complete = False
        issues.append({"code": "latest_feature_manifest_missing", "message": digest})
    for digest, parent in rank_pins.items():
        if digest not in ranks:
            storage_complete = False
            issues.append({"code": "latest_rank_manifest_missing", "message": digest})
        if parent not in features:
            storage_complete = False
            issues.append({"code": "rank_parent_manifest_missing", "message": parent})
        elif digest in rank_parent and rank_parent[digest] != parent:
            storage_complete = False
            issues.append({"code": "rank_pointer_parent_mismatch", "message": digest})
    for digest in ranks:
        if rank_parent[digest] not in features:
            storage_complete = False
            issues.append({"code": "rank_parent_manifest_missing", "message": rank_parent[digest]})
    if feature_object_refs - feature_objects:
        storage_complete = False
        issues.append({"code": "feature_object_missing", "message": "published feature manifest 指向缺少 object"})
    if rank_object_refs - rank_objects:
        storage_complete = False
        issues.append({"code": "rank_object_missing", "message": "published rank manifest 指向缺少 object"})

    watchlists = _scan_watchlists(
        watchlist_dir, root, effective_rank_root, budget,
        inventory_complete=watchlist_inventory_complete,
    )
    issues.extend(watchlists["issues"])
    references_complete = bool(storage_complete and watchlists["complete"])
    for reference in watchlists["references"]:
        if reference["kind"] == "feature" and reference["manifest_sha256"] not in features:
            references_complete = False
            issues.append({"code": "bookmark_feature_reference_missing", "message": reference["manifest_sha256"]})
        elif reference["kind"] == "feature" and reference.get("identity_sha256") != feature_identity.get(reference["manifest_sha256"]):
            references_complete = False
            issues.append({"code": "bookmark_feature_identity_mismatch", "message": reference["manifest_sha256"]})
        elif reference["kind"] == "rank":
            if reference["manifest_sha256"] not in ranks:
                references_complete = False
                issues.append({"code": "bookmark_rank_reference_missing", "message": reference["manifest_sha256"]})
            elif rank_parent.get(reference["manifest_sha256"]) != reference["parent_manifest_sha256"]:
                references_complete = False
                issues.append({"code": "bookmark_rank_parent_mismatch", "message": reference["manifest_sha256"]})
            elif rank_identity.get(reference["manifest_sha256"]) != reference["identity_sha256"]:
                references_complete = False
                issues.append({"code": "bookmark_rank_identity_mismatch", "message": reference["manifest_sha256"]})

    files = [entry for entry in entries if not entry.is_directory]
    retained_bytes = sum(entry.size_bytes for entry in files)
    temporary_bytes = sum(entry.size_bytes for entry in temp_entries)
    candidates: list[dict[str, Any]] = []
    if storage_complete and references_complete and not busy:
        for entry in files:
            kind, digest = _classify(entry.relative)
            if kind == "feature_object" and digest not in feature_object_refs:
                candidates.append(_candidate(entry, "unreferenced_feature_object", references_complete))
            elif kind == "rank_object" and digest not in rank_object_refs:
                candidates.append(_candidate(entry, "unreferenced_rank_object", references_complete))
        candidates.extend(_candidate(entry, "temporary_or_staging_file", references_complete) for entry in temp_entries)

    alerts: list[str] = []
    if retained_bytes > MAX_RETAINED_BYTES:
        alerts.append("retention_bytes_limit_exceeded")
    if len(entries) > MAX_RETAINED_ENTRIES:
        alerts.append("retention_entry_limit_exceeded")
    if temporary_bytes > MAX_TEMPORARY_PEAK_BYTES:
        alerts.append("temporary_bytes_limit_exceeded")
    capacity: dict[str, Any] | None = None
    if storage_complete:
        try:
            capacity = preflight_research_snapshot_publication(
                output_root=root,
                persistent_existing_bytes=retained_bytes,
                persistent_new_bytes=0,
                temporary_peak_bytes=temporary_bytes,
            )
            if not capacity.get("within_budget", False):
                alerts.append("central_capacity_reserve_unavailable")
        except Exception as exc:
            alerts.append("central_capacity_preflight_unavailable")
            issues.append({"code": "central_capacity_preflight_unavailable", "message": type(exc).__name__})

    growth = _growth(retained_bytes, previous_samples, observed_batch_growth_bytes, now)
    if not storage_complete:
        growth["forecast_status"] = "incomplete_inventory"
        growth["forecast_bytes"] = None
        growth["growth_rate_bytes_per_day"] = None
    if growth["batch_growth_status"] == "exceeded":
        alerts.append("batch_growth_limit_exceeded")
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at_utc": now.isoformat().replace("+00:00", "Z"),
        "roots": {
            "snapshot_root": str(root.resolve(strict=False)),
            "rank_root": str(effective_rank_root.resolve(strict=False)),
            "watchlist_dir": str(Path(watchlist_dir).resolve(strict=False)) if watchlist_dir else None,
        },
        "policy": {
            "retention_bytes_limit": MAX_RETAINED_BYTES,
            "retention_entries_limit": MAX_RETAINED_ENTRIES,
            "batch_new_bytes_limit": MAX_BATCH_NEW_BYTES,
            "temporary_peak_bytes_limit": MAX_TEMPORARY_PEAK_BYTES,
            "scan_hash_bytes_limit": MAX_SCAN_HASH_BYTES,
            "automatic_delete_enabled": False,
            "permanent_delete_enabled": False,
            "cleanup_authorized": False,
        },
        "storage": {
            "scan_complete": storage_complete,
            "references_complete": references_complete,
            "entries": len(entries),
            "files": len(files),
            "retained_bytes": retained_bytes,
            "retained_bytes_complete": storage_complete,
            "temporary_entries": len(temp_entries),
            "temporary_bytes": temporary_bytes,
            "published_feature_manifests": counts["feature_manifests"],
            "published_rank_manifests": counts["rank_manifests"],
            "feature_objects": counts["feature_objects"],
            "rank_objects": counts["rank_objects"],
            "latest_feature_pins": len(feature_pins),
            "latest_rank_pins": len(rank_pins),
            "watchlist_sources_scanned": watchlists["source_count"],
            "watchlist_bookmarks_v1": watchlists["v1_count"],
            "watchlist_bookmarks_v2": watchlists["v2_count"],
            "reference_count": len(watchlists["references"]),
            "unknown_entries": counts["unknown_entries"],
            "bytes_read_for_validation": budget.bytes_read,
        },
        "growth": growth,
        "capacity": capacity,
        "alerts": sorted(set(alerts)),
        "dry_run_candidates": candidates,
        "issues": issues,
        "automatic_action": "none",
    }


def _scan_tree(root: Path, budget: _Budget, *, ignore_top_level: set[str] | None = None) -> list[_Entry]:
    if root.is_symlink() or _is_reparse(root):
        raise StorageGovernanceError("storage_root_symlink", "snapshot root 不接受 symbolic link")
    if not root.exists():
        raise StorageGovernanceError("storage_root_missing", "snapshot root 不存在")
    if not root.is_dir():
        raise StorageGovernanceError("storage_root_invalid", "snapshot root 不是目錄")
    result: list[_Entry] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        children: list[os.DirEntry[str]] = []
        with os.scandir(directory) as iterator:
            for child in iterator:
                budget.add_entry()
                children.append(child)
        for child in sorted(children, key=lambda item: item.name):
            if directory == root and child.name in (ignore_top_level or set()):
                continue
            if child.is_symlink():
                raise StorageGovernanceError("storage_symlink_found", "snapshot tree 含 symbolic link")
            stat = child.stat(follow_symlinks=False)
            if _is_reparse_stat(stat):
                raise StorageGovernanceError("storage_reparse_point_found", "snapshot tree 含 Windows junction/reparse point")
            path = Path(child.path)
            relative = path.relative_to(root).as_posix()
            is_directory = child.is_dir(follow_symlinks=False)
            result.append(_Entry(path, relative, 0 if is_directory else stat.st_size, stat.st_mtime_ns, is_directory))
            if is_directory:
                pending.append(path)
    return result


def _classify(relative: str) -> tuple[str, str]:
    parts = Path(relative).parts
    is_rank = len(parts) > 1 and parts[0] == "original_rankings"
    sub = parts[1:] if is_rank else parts
    if not is_rank and sub == ("latest.json",):
        return "feature_pointer", ""
    if is_rank and len(sub) == 1 and re.fullmatch(r"latest-(day|week)-(strong|weak)\.json", sub[0]):
        return "rank_pointer", ""
    if len(sub) in {2, 3} and sub[0] in {"manifests", "objects"}:
        name = Path(sub[-1])
        if name.suffix != ".json" or not _SHA256_RE.fullmatch(name.stem):
            return "unknown", ""
        digest = name.stem
        if len(sub) == 3 and (not is_rank or sub[1] != digest[:2]):
            return "unknown", ""
        if is_rank and len(sub) != 3:
            return "unknown", ""
        if not is_rank and len(sub) != 2:
            return "unknown", ""
        suffix = "manifest" if sub[0] == "manifests" else "object"
        return f"{'rank' if is_rank else 'feature'}_{suffix}", digest
    return "unknown", ""


def _file_limit(kind: str) -> int:
    if kind == "feature_manifest":
        return DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES
    if kind == "feature_object":
        return DAILY_MARKET_SNAPSHOT_MAX_ARTIFACT_BYTES
    if kind == "rank_manifest":
        return 8 * 1024 * 1024
    if kind == "rank_object":
        return 8 * 1024 * 1024
    raise StorageGovernanceError("storage_file_kind_unknown", "未知 immutable 檔案型別")


def _read_json(
    path: Path, maximum: int, budget: _Budget, *, require_canonical: bool = True
) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink():
        raise StorageGovernanceError("storage_symlink_found", "不讀取 symbolic link")
    size = path.stat(follow_symlinks=False).st_size
    if size > maximum:
        raise StorageGovernanceError("storage_file_size_limit", "JSON 超過單檔 bytes 上限")
    budget.add_read(size)
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) != size or len(raw) > maximum:
        raise StorageGovernanceError("storage_file_changed_during_read", "檔案讀取期間大小改變")
    payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(payload, dict) or (require_canonical and _canonical(payload) != raw):
        raise StorageGovernanceError("storage_json_noncanonical", "JSON 必須為 canonical object")
    return payload, raw


def _scan_cow_watchlist_metadata(
    children: Sequence[os.DirEntry[str]], budget: _Budget,
) -> tuple[set[Path], set[Path], dict[Path, Mapping[str, Any]]]:
    """只辨識精確COW審計格式；不把metadata誤作使用者清單。"""
    managed: set[Path] = set()
    databases: set[Path] = set()
    lineages: dict[Path, Mapping[str, Any]] = {}
    records: dict[Path, tuple[dict[str, Any], bytes]] = {}
    for child in children:
        if child.name.endswith(".cow-lock"):
            raise StorageGovernanceError("watchlist_source_busy", "COW鎖尚未釋放")
        if not (child.name.endswith((".cow-active.json", ".cow-conversion.v1.json"))
                or ".cow-rollback." in child.name and child.name.endswith(".json")):
            continue
        path = Path(child.path).resolve()
        if child.is_symlink() or _is_reparse_stat(child.stat(follow_symlinks=False)):
            raise StorageGovernanceError("watchlist_cow_metadata_linked", "COW metadata不接受link")
        records[path] = _read_json(path, MAX_WATCHLIST_JSON_BYTES, budget, require_canonical=False)

    def bound_path(value: Any) -> Path:
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise StorageGovernanceError("watchlist_cow_path_invalid", "COW必須使用明示absolute path")
        path = Path(value)
        if path.is_symlink() or _is_reparse(path) or not path.is_file():
            raise StorageGovernanceError("watchlist_cow_path_invalid", "COW來源不完整或含link")
        return path.resolve()

    # Explicit targets may be in another directory; read only audit files named by
    # the canonical pointer, under the same entry/byte budgets.
    for record, _ in tuple(records.values()):
        if record.get("schema_version") != "watchlist-cow-activation.v1":
            continue
        for key in ("receipt_path", "backup_marker_path"):
            path = bound_path(record.get(key))
            if path not in records:
                budget.add_entry()
                records[path] = _read_json(path, MAX_WATCHLIST_JSON_BYTES, budget, require_canonical=False)

    for path, (record, raw) in records.items():
        schema = record.get("schema_version")
        if schema == "watchlist-cow-conversion.v1":
            source, target = bound_path(record.get("source_path")), bound_path(record.get("target_path"))
            if (record.get("status") != "ready" or type(record.get("source_schema_version")) is not int
                    or record.get("source_schema_version") not in (1, 2)
                    or record.get("target_schema_version") != 3 or source == target
                    or str(path) != record.get("receipt_path")
                    or path != target.with_name(target.name + ".cow-conversion.v1.json")
                    or not isinstance(record.get("comparison"), dict)):
                raise StorageGovernanceError("watchlist_cow_receipt_invalid", "COW收據schema/path/comparison未知")
            for key in ("source_sha256", "target_sha256"):
                if not isinstance(record.get(key), str) or not _SHA256_RE.fullmatch(record[key]):
                    raise StorageGovernanceError("watchlist_cow_receipt_invalid", "COW收據hash未知")
            databases.update((source, target)); managed.add(path)
        elif schema == "watchlist-cow-rollback.v1":
            source, target = bound_path(record.get("source_path")), bound_path(record.get("target_path"))
            activation_id = record.get("activation_id")
            if (not isinstance(activation_id, str) or not re.fullmatch(r"[0-9a-f]{32}", activation_id)
                    or path != source.with_name(source.name + ".cow-rollback." + activation_id + ".json")
                    or not isinstance(record.get("original_state"), dict)):
                raise StorageGovernanceError("watchlist_cow_backup_invalid", "COW回滾審計schema/path未知")
            databases.update((source, target)); managed.add(path)
        elif schema != "watchlist-cow-activation.v1":
            raise StorageGovernanceError("watchlist_cow_metadata_schema_unknown", "COW metadata schema未知")
    for path, (record, raw) in records.items():
        if record.get("schema_version") != "watchlist-cow-activation.v1":
            continue
        source, target = bound_path(record.get("source_path")), bound_path(record.get("target_path"))
        receipt = bound_path(record.get("receipt_path"))
        backup = bound_path(record.get("backup_marker_path"))
        if (record.get("status") not in ("active", "rolled_back")
                or str(source) != record.get("canonical_path")
                or path != source.with_name(source.name + ".cow-active.json")
                or receipt not in records or backup not in records):
            raise StorageGovernanceError("watchlist_cow_marker_invalid", "COW pointer/path/審計檔不完整")
        receipt_record, receipt_raw = records[receipt]
        backup_record, backup_raw = records[backup]
        if (receipt_record.get("schema_version") != "watchlist-cow-conversion.v1"
                or backup_record.get("schema_version") != "watchlist-cow-rollback.v1"
                or record.get("receipt_sha256") != hashlib.sha256(receipt_raw).hexdigest()
                or record.get("backup_marker_sha256") != hashlib.sha256(backup_raw).hexdigest()
                or record.get("activation_id") != backup_record.get("activation_id")
                or record.get("source_sha256") != receipt_record.get("source_sha256")
                or record.get("prepared_target_sha256") != receipt_record.get("target_sha256")
                or any(bound_path(item.get(key)) != expected for item in (receipt_record, backup_record)
                       for key, expected in (("source_path", source), ("target_path", target)))):
            raise StorageGovernanceError("watchlist_cow_marker_invalid", "COW pointer審計hash/path不一致")
        lineage = record.get("target_base_lineage")
        if not isinstance(lineage, dict):
            raise StorageGovernanceError("watchlist_cow_lineage_unknown", "COW基準歷史未知")
        for watchlist_id, entry in lineage.items():
            if (not isinstance(watchlist_id, str) or not watchlist_id or not isinstance(entry, dict)
                    or type(entry.get("revision_count")) is not int or entry["revision_count"] < 0
                    or not isinstance(entry.get("lineage_sha256"), str)
                    or (entry["revision_count"] > 0 and not _SHA256_RE.fullmatch(entry["lineage_sha256"]))
                    or (entry["revision_count"] == 0 and entry["lineage_sha256"] != "")):
                raise StorageGovernanceError("watchlist_cow_lineage_unknown", "COW基準歷史欄位未知")
        lineages[target] = lineage
        databases.update((source, target)); managed.add(path)
    return managed, databases, lineages


def _verify_cow_lineage(inventory: Mapping[str, Any] | None, expected: Mapping[str, Any]) -> None:
    """沿activation同一chain codec驗已有inventory，不再讀DB。"""
    from app_module.watchlist_cow_activation import (
        WatchlistCowActivationError, watchlist_cow_lineage_from_inventory,
    )
    if inventory is None:
        raise StorageGovernanceError("watchlist_cow_lineage_invalid", "COW target必須是v3")
    try:
        watchlist_cow_lineage_from_inventory(inventory, expected)
    except WatchlistCowActivationError as exc:
        raise StorageGovernanceError("watchlist_cow_lineage_invalid", str(exc)) from exc


def _scan_watchlists(
    directory: Path | None,
    root: Path,
    rank_root: Path,
    budget: _Budget,
    *,
    inventory_complete: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {"complete": False, "issues": [], "references": [], "source_count": 0, "v1_count": 0, "v2_count": 0}
    if directory is None:
        result["issues"].append({"code": "watchlist_sources_not_explicit", "message": "未提供完整 Watchlist 來源目錄"})
        return result
    directory = Path(directory).expanduser()
    if directory.is_symlink() or _is_reparse(directory) or not directory.is_dir():
        result["issues"].append({"code": "watchlist_source_root_unavailable", "message": "Watchlist 來源目錄不存在或不可讀"})
        return result
    try:
        children: list[os.DirEntry[str]] = []
        with os.scandir(directory) as iterator:
            for child in iterator:
                budget.add_entry()
                children.append(child)
        json_paths: list[Path] = []
        child_pins = {
            Path(child.path).resolve(): (stat.st_size, stat.st_mtime_ns, stat.st_ino, stat.st_dev)
            for child in children for stat in (Path(child.path).stat(follow_symlinks=False),)
        }
        cow_metadata, cow_databases, cow_lineages = _scan_cow_watchlist_metadata(children, budget)
        cow_pins = {}
        for path in cow_metadata | cow_databases:
            stat = path.stat(follow_symlinks=False)
            cow_pins[path] = child_pins.get(path, (stat.st_size, stat.st_mtime_ns, stat.st_ino, stat.st_dev))
        db_paths: set[Path] = set(cow_databases)
        for child in children:
            if child.is_symlink():
                raise StorageGovernanceError("watchlist_symlink_found", "Watchlist 來源含 symbolic link")
            child_stat = child.stat(follow_symlinks=False)
            if _is_reparse_stat(child_stat):
                raise StorageGovernanceError("watchlist_reparse_point_found", "Watchlist 來源含 junction/reparse point")
            if child.name.lower().endswith(("-wal", "-shm", ".json.tmp")):
                raise StorageGovernanceError("watchlist_source_busy", "Watchlist 有 WAL/SHM/staging sidecar")
            if Path(child.path).resolve() in cow_metadata or Path(child.path).resolve() in cow_databases:
                continue
            if child.name == "watchlists.db":
                db_paths.add(Path(child.path).resolve())
            elif child.name == "watchlists.db.active":
                # marker 可能由舊版以不同空白格式寫入，只做有界 JSON/schema 驗證。
                payload = _read_json(Path(child.path), 64 * 1024, budget, require_canonical=False)[0]
                if payload.get("schema_version") != "watchlist-activation.v1" or payload.get("status") != "complete":
                    raise StorageGovernanceError("watchlist_marker_schema_unknown", "Watchlist marker schema 未知")
            elif child.name.endswith(".json"):
                json_paths.append(Path(child.path))
            else:
                raise StorageGovernanceError("watchlist_source_schema_unknown", "Watchlist 目錄含未知檔案")
        for path in sorted(json_paths):
            payload, _ = _read_json(path, MAX_WATCHLIST_JSON_BYTES, budget, require_canonical=False)
            _scan_watchlist_payload(payload, path, root, rank_root, result)
            result["source_count"] += 1
        for db_path in sorted(db_paths):
            if db_path.stat().st_size > MAX_WATCHLIST_DB_BYTES:
                raise StorageGovernanceError("watchlist_db_size_limit", "Watchlist SQLite 超過 32 MiB")
            inventory = _scan_watchlist_db(db_path, root, rank_root, budget, result)
            if db_path in cow_lineages:
                _verify_cow_lineage(inventory, cow_lineages[db_path])
            result["source_count"] += 1
        if cow_metadata:
            for path, expected in cow_pins.items():
                stat = path.stat(follow_symlinks=False)
                if (stat.st_size, stat.st_mtime_ns, stat.st_ino, stat.st_dev) != expected:
                    raise StorageGovernanceError("watchlist_cow_changed_during_scan", "COW來源或審計檔掃描期間變動")
            with os.scandir(directory) as iterator:
                names = set()
                for child in iterator:
                    budget.add_entry()
                    names.add(child.name)
            if names != {child.name for child in children}:
                raise StorageGovernanceError("watchlist_cow_changed_during_scan", "COW來源目錄掃描期間變動")
        result["complete"] = bool(inventory_complete)
        if not inventory_complete:
            result["issues"].append({
                "code": "watchlist_inventory_completeness_unasserted",
                "message": "已掃描提供來源，但未確認已列出全部 Watchlist 來源",
            })
    except (OSError, sqlite3.Error, UnicodeError, json.JSONDecodeError, ValueError, WatchlistStorageCapacityError) as exc:
        result["issues"].append(_issue(exc))
    return result


def _scan_watchlist_db(db_path: Path, root: Path, rank_root: Path, budget: _Budget, result: dict[str, Any]) -> dict[str, Any] | None:
    if db_path.is_symlink():
        raise StorageGovernanceError("watchlist_db_symlink", "不讀取 Watchlist SQLite symbolic link")
    before = db_path.stat(follow_symlinks=False)
    if before.st_size > MAX_WATCHLIST_DB_BYTES:
        raise StorageGovernanceError("watchlist_db_size_limit", "Watchlist SQLite 超過 32 MiB")
    uri = f"{db_path.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    inventory: dict[str, Any] | None = None
    try:
        connection.execute("PRAGMA query_only=ON")
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "watchlist_storage_meta" in tables:
            inventory = _scan_item_watchlist_db(connection, db_path, root, rank_root, budget, result)
        else:
            _scan_legacy_watchlist_db(connection, tables, db_path, root, rank_root, budget, result)
    finally:
        connection.close()
    after = db_path.stat(follow_symlinks=False)
    sidecars = (Path(f"{db_path}-wal"), Path(f"{db_path}-shm"), Path(f"{db_path}-journal"))
    if any(path.exists() for path in sidecars):
        raise StorageGovernanceError("watchlist_db_sidecar_changed", "SQLite 讀取前後出現 WAL/SHM/journal sidecar")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise StorageGovernanceError("watchlist_db_changed_during_read", "SQLite 讀取前後 stat 不一致")
    return inventory


def _scan_legacy_watchlist_db(
    connection: sqlite3.Connection, tables: set[str], db_path: Path,
    root: Path, rank_root: Path, budget: _Budget, result: dict[str, Any],
) -> None:
    """沿用舊 v1/v2 全份 payload reader，不在診斷時升版。"""
    if tables == {"watchlists"}:
        actual = {str(row[1]) for row in connection.execute("PRAGMA table_info(watchlists)")}
        required = {"watchlist_id", "payload_json", "revision"}
        if actual not in (required, required | {"source_hash"}):
            raise StorageGovernanceError("watchlist_db_schema_unknown", "Watchlist SQLite v1 欄位 schema 未知")
    elif tables == set(_WATCHLIST_COLUMNS):
        for table, expected in _WATCHLIST_COLUMNS.items():
            actual = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
            if actual != expected:
                raise StorageGovernanceError("watchlist_db_schema_unknown", "Watchlist SQLite 欄位 schema 未知")
    else:
        raise StorageGovernanceError("watchlist_db_schema_unknown", "Watchlist SQLite 缺少已知 tables")
    rows_seen = 0
    payload_bytes = 0
    for table in sorted(tables):
        cursor = connection.execute(f"SELECT payload_json FROM {table}")
        while rows := cursor.fetchmany(64):
            for (raw_value,) in rows:
                raw = str(raw_value).encode("utf-8")
                rows_seen += 1
                payload_bytes += len(raw)
                if rows_seen > MAX_WATCHLIST_ROWS or payload_bytes > MAX_WATCHLIST_PAYLOAD_BYTES:
                    raise StorageGovernanceError("watchlist_scan_budget_exceeded", "Watchlist rows/payload 超過預算")
                budget.add_read(len(raw))
                payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
                _scan_watchlist_payload(payload, db_path, root, rank_root, result)


def _scan_item_watchlist_db(
    connection: sqlite3.Connection, db_path: Path, root: Path, rank_root: Path,
    budget: _Budget, result: dict[str, Any],
) -> dict[str, Any]:
    """驗 unique objects 與 sparse journal；完整歷史 hash 由增量 replay API 另驗。"""
    remaining = MAX_SCAN_HASH_BYTES - budget.bytes_read
    if remaining <= 0:
        raise StorageGovernanceError("scan_byte_budget_exceeded", "Watchlist 沒有剩餘讀取預算")
    inventory = WatchlistRepository(db_path).get_item_storage_inventory(connection=connection, max_scan_bytes=remaining)
    valid_keys = ("complete", "schema_valid", "object_hashes_valid", "delta_refs_valid", "revision_chain_valid", "current_projection_valid")
    if inventory.get("schema_version") != 3 or inventory.get("storage_format") != "watchlist-item-events.v1" or any(inventory.get(key) is not True for key in valid_keys):
        raise StorageGovernanceError("watchlist_item_storage_invalid", "Watchlist 項目 schema/hash/refs/chain/projection 核驗失敗")
    payload_bytes = inventory.get("payload_bytes")
    scanned_bytes = inventory.get("scanned_bytes")
    counts = inventory.get("row_counts")
    if type(payload_bytes) is not int or type(scanned_bytes) is not int or not isinstance(counts, Mapping) or any(type(value) is not int or value < 0 for value in counts.values()):
        raise StorageGovernanceError("watchlist_item_inventory_unknown", "Watchlist 項目盤點計量未知")
    if payload_bytes < 0 or scanned_bytes < payload_bytes or payload_bytes > MAX_WATCHLIST_PAYLOAD_BYTES or sum(counts.values()) > MAX_WATCHLIST_ROWS:
        raise StorageGovernanceError("watchlist_scan_budget_exceeded", "Watchlist 項目 rows/payload 超過預算")
    budget.add_read(scanned_bytes)
    for obj in inventory["objects"]:
        _scan_watchlist_payload({"items": [obj["item"]]}, db_path, root, rank_root, result)
    return inventory


def _scan_watchlist_payload(payload: Any, source: Path, root: Path, rank_root: Path, result: dict[str, Any]) -> None:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("items"), list):
        raise StorageGovernanceError("watchlist_payload_schema_unknown", "Watchlist payload 缺少 items")
    for item in payload["items"]:
        if not isinstance(item, Mapping):
            raise StorageGovernanceError("watchlist_item_invalid", "Watchlist item 型別無效")
        raw = item.get("research_bookmark")
        if raw is None:
            continue
        if not isinstance(raw, Mapping):
            raise StorageGovernanceError("bookmark_schema_unknown", "bookmark 不是 object")
        bookmark = decode_daily_market_research_bookmark(raw)
        if (
            str(item.get("source_id") or "") != bookmark.bookmark_id
            or str(item.get("stock_code") or "") != bookmark.stock_code
            or str(item.get("stock_name") or "") != bookmark.stock_name
        ):
            raise StorageGovernanceError("bookmark_item_identity_mismatch", "bookmark 與 Watchlist item 不一致")
        if isinstance(bookmark, DailyMarketResearchBookmark):
            if _path_key(bookmark.snapshot_root) != _path_key(root):
                raise StorageGovernanceError("bookmark_external_root", "feature bookmark 指向其他 snapshot root")
            result["references"].append({
                "kind": "feature", "manifest_sha256": bookmark.source_snapshot_hash,
                "identity_sha256": bookmark.snapshot_identity_sha256,
            })
            result["v1_count"] += 1
        elif isinstance(bookmark, OriginalStockRankingBookmark):
            rank = bookmark.rank_context
            if rank is None or _path_key(rank.snapshot_root) != _path_key(root) or _path_key(rank.ranking_root) != _path_key(rank_root):
                raise StorageGovernanceError("bookmark_external_root", "rank bookmark 指向其他 root")
            result["references"].append({
                "kind": "feature", "manifest_sha256": rank.parent_snapshot_hash,
                "identity_sha256": bookmark.context.source_snapshot_id,
            })
            result["references"].append({
                "kind": "rank", "manifest_sha256": rank.source_hash,
                "parent_manifest_sha256": rank.parent_snapshot_hash,
                "identity_sha256": rank.rank_snapshot_id,
            })
            result["v2_count"] += 1
        else:
            raise StorageGovernanceError("bookmark_schema_unknown", "bookmark 版本不支援")


def _candidate(entry: _Entry, reason: str, references_complete: bool) -> dict[str, Any]:
    return {
        "path": entry.relative,
        "bytes": entry.size_bytes,
        "reason": reason,
        "dry_run_only": True,
        "requires_user_approval_each_time": True,
        "reference_inventory_complete": references_complete,
        "automatic_action": "none",
    }


def _growth(retained: int, samples: Sequence[StorageGrowthSample], batch: int | None, now: datetime) -> dict[str, Any]:
    if batch is not None and (type(batch) is not int or batch < 0):
        raise ValueError("observed_batch_growth_bytes 必須為非負整數")
    if len(samples) > 90:
        raise ValueError("previous_samples 最多 90 筆")
    points = [_aware_utc(sample.observed_at_utc) for sample in samples if isinstance(sample, StorageGrowthSample)]
    if len(points) != len(samples) or any(type(sample.retained_bytes) is not int or sample.retained_bytes < 0 for sample in samples):
        raise ValueError("previous_samples 格式無效")
    forecast: dict[str, int] | None = None
    rate: int | None = None
    status = "insufficient_history"
    ordered = sorted([*zip(points, [sample.retained_bytes for sample in samples]), (now, retained)], key=lambda pair: pair[0])
    if len(ordered) >= 2:
        first_time, first_size = ordered[0]
        last_time, last_size = ordered[-1]
        seconds = int((last_time - first_time).total_seconds())
        delta = last_size - first_size
        if seconds > 0 and delta >= 0:
            rate = delta * 86400 // seconds
            forecast = {str(days): retained + rate * days for days in (7, 30, 90)}
            status = "available"
        else:
            status = "invalid_or_decreasing_history"
    return {
        "observed_batch_growth_bytes": batch,
        "batch_growth_limit_bytes": MAX_BATCH_NEW_BYTES,
        "batch_growth_status": "unknown" if batch is None else ("exceeded" if batch > MAX_BATCH_NEW_BYTES else "within_budget"),
        "growth_rate_bytes_per_day": rate,
        "forecast_status": status,
        "forecast_bytes": forecast,
    }


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("時間必須為具時區 datetime")
    return value.astimezone(timezone.utc)


def _path_key(value: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(Path(value).expanduser().resolve(strict=False))))


def _same_filesystem_probe(first: Path, second: Path) -> bool:
    """相同路徑只做一次；其他情況雙 probe，避免依賴無界目錄大小掃描。"""
    return _path_key(first) == _path_key(second)


def _is_reparse(path: Path) -> bool:
    return _is_reparse_stat(path.lstat())


def _is_reparse_stat(value: os.stat_result) -> bool:
    flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(int(getattr(value, "st_file_attributes", 0)) & flag)


def _sha(value: Any) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise StorageGovernanceError("storage_reference_hash_invalid", "reference 不是 lowercase SHA-256")
    return value


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object 有重複 key")
        result[key] = value
    return result


def _issue(exc: Exception, prefix: str = "") -> dict[str, str]:
    code = exc.code if isinstance(exc, StorageGovernanceError) else "storage_file_invalid"
    message = f"{prefix}: {type(exc).__name__}" if prefix else type(exc).__name__
    return {"code": code, "message": message}


__all__ = [
    "MAX_BATCH_NEW_BYTES", "MAX_RETAINED_BYTES", "MAX_RETAINED_ENTRIES", "MAX_TEMPORARY_PEAK_BYTES",
    "SCHEMA_VERSION", "StorageGovernanceError", "StorageGrowthSample",
    "diagnose_research_snapshot_storage", "preflight_research_snapshot_publication",
]
