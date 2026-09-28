"""唯讀讀取既有 Recommendation／Journal／Evidence 的 personalization 入口。

這個模組是 V6 first-slice 的 operational read boundary。它刻意不建立
``TWStockConfig``、``RecommendationRepository`` 或 ``JournalService``，因為
那些 writer-oriented constructor 可能 mkdir、建立 DDL 或取得 process lock。
所有來源都由 caller 注入 path，SQLite 只用 ``mode=ro``，缺少的 root 只產生
diagnostic，不會補建資料夾或檔案。

它不會重算 recommendation、補寫 delivery/action/outcome、建立 learner 或
promotion pointer；只把既有 bytes 組成 ``PersonalizationProjectionService``
的 exact read projection，再依固定 contract 組 evaluation rows。沒有明示的
scope、prediction receipt、label availability、label、outcome tier 或 cost
contract 時，row 會被排除並留下可操作診斷。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.personalization_calibration import (
    PersonalizationCalibrationEvaluation,
    PersonalizationCalibrationEvaluator,
    PersonalizationCalibrationFitArtifact,
)
from app_module.personalization_contract import (
    PERSONALIZATION_ACTIONS,
    PERSONALIZATION_ACTION_STATES,
    PERSONALIZATION_DELIVERY_STATUSES,
    PERSONALIZATION_OUTCOME_STATUSES,
    PERSONALIZATION_OUTCOME_TIERS,
    PersonalRecommendationChoice,
    PersonalizationEvaluationRow,
    canonical_payload_hash,
    parse_aware_datetime,
    read_personal_use_policy_snapshot_event,
)
from app_module.dtos.decision_continuity_dtos import (
    DecisionContinuityRevision,
    DecisionIdentity,
    IDENTITY_STATUS_LINKED,
)
from app_module.personalization_projection import (
    PersonalizationProjectionError,
    PersonalizationProjectionResult,
    PersonalizationProjectionService,
)
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.saved_recommendation_queries import build_recommendation_execution_queries
from data_module.result_artifact_store import ResultArtifactStore


PERSONALIZATION_READ_REPORT_SCHEMA_VERSION = "personalization-read-report.v1"
_MARKET_TIMEZONE = ZoneInfo("Asia/Taipei")
DEFAULT_MAX_RESULTS = 100
DEFAULT_MAX_CANDIDATES_PER_RESULT = 100
DEFAULT_MAX_EVIDENCE_EVENTS = 500
DEFAULT_MAX_JOURNAL_ROWS = 50_000
DEFAULT_MAX_RECEIPT_FILES = 5_000
_SQLITE_READ_BIND_CHUNK_SIZE = 900


def _text(value: object) -> str:
    return str(value or "").strip()


def _json_safe(value: Any) -> Any:
    """Convert source DTOs/enums to JSON-shaped values without numeric coercion."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())
    if hasattr(value, "isoformat") and not isinstance(value, (str, bytes)):
        try:
            return value.isoformat()
        except (AttributeError, TypeError, ValueError):
            pass
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def _safe_result_id(value: object) -> str:
    """Accept only one filename-like result identity; never join by path text."""

    text = _text(value)
    if not text or text in {".", ".."}:
        return ""
    if Path(text).name != text or "/" in text or "\\" in text:
        return ""
    return text


def _iso_date(value: object, field_name: str) -> str:
    text = _text(value)[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO date") from exc


def _optional_datetime(value: object, field_name: str) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return parse_aware_datetime(value, field_name)
    except ValueError:
        return None


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _alias_values(row: Mapping[str, Any], aliases: Sequence[str]) -> tuple[str, ...]:
    """Read explicit result aliases from bounded root/identity/payload/metadata."""

    queue: list[Mapping[str, Any]] = [row]
    seen: set[int] = set()
    values: list[str] = []
    while queue:
        current = queue.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        for alias in aliases:
            if current.get(alias) not in (None, ""):
                value = _text(current.get(alias))
                if value:
                    values.append(value)
        for key in (
            "decision_identity",
            "payload",
            "metadata",
            "personalization_action",
            "personalization_envelope",
        ):
            nested = current.get(key)
            if isinstance(nested, Mapping):
                queue.append(nested)
    return tuple(dict.fromkeys(values))


def _explicit_result_values(row: Mapping[str, Any]) -> tuple[str, ...]:
    # ``source_id`` is deliberately absent.  It identifies a provider/source,
    # not the persisted recommendation result.
    return _alias_values(row, ("result_id", "source_result_id"))


def _explicit_stock_values(row: Mapping[str, Any]) -> tuple[str, ...]:
    return _alias_values(row, ("stock_code", "symbol", "證券代號"))


@dataclass(frozen=True)
class PersonalizationSourceFingerprint:
    """A read source's stat and content hash before/after one report."""

    path: str
    exists: bool
    size: int | None
    mtime_ns: int | None
    sha256: str | None
    read_error: str = ""

    @classmethod
    def missing(cls, path: str | Path) -> "PersonalizationSourceFingerprint":
        """Return a stable missing marker without touching the filesystem."""

        resolved = Path(path).expanduser().resolve()
        return cls(
            path=str(resolved),
            exists=False,
            size=None,
            mtime_ns=None,
            sha256=None,
        )

    @classmethod
    def capture(cls, path: str | Path) -> "PersonalizationSourceFingerprint":
        resolved = Path(path).expanduser().resolve()
        try:
            stat = resolved.stat()
        except FileNotFoundError:
            return cls(
                path=str(resolved),
                exists=False,
                size=None,
                mtime_ns=None,
                sha256=None,
            )
        except OSError as exc:
            return cls(
                path=str(resolved),
                exists=False,
                size=None,
                mtime_ns=None,
                sha256=None,
                read_error=f"stat:{type(exc).__name__}",
            )
        digest = hashlib.sha256()
        try:
            with resolved.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
        except OSError as exc:
            return cls(
                path=str(resolved),
                exists=True,
                size=int(stat.st_size),
                mtime_ns=int(stat.st_mtime_ns),
                sha256=None,
                read_error=f"hash:{type(exc).__name__}",
            )
        try:
            final_stat = resolved.stat()
        except FileNotFoundError:
            return cls(
                path=str(resolved),
                exists=False,
                size=None,
                mtime_ns=None,
                sha256=f"sha256:{digest.hexdigest()}",
                read_error="changed_during_hash",
            )
        except OSError as exc:
            return cls(
                path=str(resolved),
                exists=True,
                size=int(stat.st_size),
                mtime_ns=int(stat.st_mtime_ns),
                sha256=f"sha256:{digest.hexdigest()}",
                read_error=f"stat_after:{type(exc).__name__}",
            )
        if (
            int(final_stat.st_size) != int(stat.st_size)
            or int(final_stat.st_mtime_ns) != int(stat.st_mtime_ns)
        ):
            return cls(
                path=str(resolved),
                exists=True,
                size=int(final_stat.st_size),
                mtime_ns=int(final_stat.st_mtime_ns),
                sha256=f"sha256:{digest.hexdigest()}",
                read_error="changed_during_hash",
            )
        return cls(
            path=str(resolved),
            exists=True,
            size=int(stat.st_size),
            mtime_ns=int(stat.st_mtime_ns),
            sha256=f"sha256:{digest.hexdigest()}",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "sha256": self.sha256,
            "read_error": self.read_error,
        }

    def same_bytes_and_mtime(self, other: "PersonalizationSourceFingerprint") -> bool:
        return (
            self.path == other.path
            and self.exists == other.exists
            and self.size == other.size
            and self.mtime_ns == other.mtime_ns
            and self.sha256 == other.sha256
            and not self.read_error
            and not other.read_error
        )


def _sqlite_sidecar_paths(path: str | Path) -> tuple[Path, ...]:
    """Include SQLite WAL/SHM bytes in a read manifest when present or absent."""

    resolved = Path(path).expanduser().resolve()
    return (
        resolved,
        Path(f"{resolved}-wal"),
        Path(f"{resolved}-shm"),
    )


class ReadOnlyRecommendationSource:
    """Read existing recommendation JSON and ``recommendation_runs`` metadata."""

    def __init__(
        self,
        output_root: str | Path,
        *,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> None:
        if isinstance(max_results, bool) or max_results <= 0:
            raise ValueError("max_results must be positive")
        self.output_root = Path(output_root).expanduser().resolve()
        self.runs_dir = self.output_root / "recommendation" / "runs"
        self.db_path = self.runs_dir / "recommendation_runs.db"
        self.max_results = max_results
        self.diagnostics: list[str] = []
        self._metadata_loaded = False
        self._metadata: dict[str, dict[str, Any]] = {}
        self._accessed_paths: set[Path] = set()
        self._metadata_inventory_truncated = False
        self._json_inventory: dict[str, Path] = {}
        self._json_mtimes: dict[str, int] = {}
        self._inventory: dict[str, Any] = {}

    def _add_diagnostic(self, value: str) -> None:
        if value not in self.diagnostics:
            self.diagnostics.append(value)

    def reset(self) -> None:
        """Start a new read operation without reusing stale source caches."""

        self.diagnostics.clear()
        self._metadata_loaded = False
        self._metadata.clear()
        self._accessed_paths.clear()
        self._metadata_inventory_truncated = False
        self._json_inventory.clear()
        self._json_mtimes.clear()
        self._inventory.clear()

    def inventory_paths(self) -> tuple[Path, ...]:
        """List candidate source paths without opening their contents."""

        paths: set[Path] = set(_sqlite_sidecar_paths(self.db_path))
        if not self.runs_dir.is_dir():
            return tuple(sorted(paths, key=str))
        try:
            for path in self.runs_dir.glob("*.json"):
                if not path.is_file():
                    continue
                resolved = path.resolve()
                paths.add(resolved)
                safe_id = _safe_result_id(path.stem)
                if safe_id:
                    self._json_inventory[safe_id] = resolved
                    try:
                        self._json_mtimes[safe_id] = int(resolved.stat().st_mtime_ns)
                    except OSError:
                        self._json_mtimes[safe_id] = 0
        except OSError as exc:
            self._add_diagnostic(
                f"recommendation_json_inventory_failed:{type(exc).__name__}"
            )
        return tuple(sorted(paths, key=str))

    def candidate_paths_for_result_ids(
        self,
        result_ids: Sequence[str],
    ) -> tuple[Path, ...]:
        """Add default JSON paths for explicit ids without reading metadata."""

        paths = set(_sqlite_sidecar_paths(self.db_path))
        for result_id in result_ids:
            safe_id = _safe_result_id(result_id)
            if safe_id:
                paths.add(self._path_for(safe_id))
        return tuple(sorted(paths, key=str))

    @staticmethod
    def _metadata_from_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
        result_id = _safe_result_id(row.get("result_id"))
        if not result_id:
            return None
        config: Any = row.get("config")
        if isinstance(config, str) and config:
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = None
        return {
            "result_id": result_id,
            "result_name": row.get("result_name"),
            "regime": row.get("regime"),
            "stock_count": row.get("stock_count"),
            "config": config,
            "notes": row.get("notes") or "",
            "created_at": row.get("created_at"),
            "data_path": row.get("data_path"),
        }

    def _load_metadata(self) -> None:
        if self._metadata_loaded:
            return
        self._metadata_loaded = True
        if not self.db_path.is_file():
            self._add_diagnostic("recommendation_metadata_database_missing")
            return
        try:
            uri = self.db_path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                connection.execute("PRAGMA query_only = ON")
                connection.row_factory = sqlite3.Row
                table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    ("runs",),
                ).fetchone()
                if table is None:
                    self._add_diagnostic("recommendation_metadata_runs_table_missing")
                    return
                rows = connection.execute(
                    "SELECT result_id, result_name, regime, stock_count, config, "
                    "notes, created_at, data_path FROM runs "
                    "ORDER BY created_at DESC, result_id DESC LIMIT ?",
                    (self.max_results + 1,),
                ).fetchall()
                self._metadata_inventory_truncated = len(rows) > self.max_results
                for row in rows:
                    metadata = self._metadata_from_row(dict(row))
                    if metadata is None:
                        self._add_diagnostic("recommendation_metadata_result_id_invalid")
                        continue
                    result_id = str(metadata["result_id"])
                    if isinstance(row["config"], str) and row["config"]:
                        try:
                            json.loads(row["config"])
                        except json.JSONDecodeError:
                            self._add_diagnostic(
                                f"recommendation_metadata_config_invalid:{result_id}"
                            )
                    self._metadata[result_id] = metadata
        except (OSError, sqlite3.Error) as exc:
            self._add_diagnostic(
                f"recommendation_metadata_read_failed:{type(exc).__name__}"
            )

    def metadata_for(self, result_id: str) -> Mapping[str, Any] | None:
        self._load_metadata()
        safe_id = _safe_result_id(result_id)
        metadata = self._metadata.get(safe_id)
        if metadata is not None or not safe_id or not self.db_path.is_file():
            return metadata
        # The bounded inventory query may omit a requested JSON whose metadata
        # is older than the first page.  Fetch that exact row only; do not turn
        # the bounded inventory into an unbounded DB scan.
        try:
            uri = self.db_path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                connection.execute("PRAGMA query_only = ON")
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    "SELECT result_id, result_name, regime, stock_count, config, "
                    "notes, created_at, data_path FROM runs WHERE result_id = ? LIMIT 1",
                    (safe_id,),
                ).fetchone()
            if row is not None:
                parsed = self._metadata_from_row(dict(row))
                if parsed is not None:
                    self._metadata[safe_id] = parsed
                    return parsed
        except (OSError, sqlite3.Error) as exc:
            self._add_diagnostic(
                f"recommendation_metadata_lookup_failed:{safe_id}:{type(exc).__name__}"
            )
        return None

    def list_result_ids(
        self,
        *,
        report_truncation: bool = True,
    ) -> tuple[str, ...]:
        self._load_metadata()
        if not self._json_inventory:
            self.inventory_paths()
        ids = set(self._metadata) | set(self._json_inventory)

        def sort_key(result_id: str) -> tuple[str, int, str]:
            metadata = self._metadata.get(result_id) or {}
            return (
                _text(metadata.get("created_at")),
                self._json_mtimes.get(result_id, 0),
                result_id,
            )

        normalized = sorted(ids, key=sort_key, reverse=True)
        selected = normalized[: self.max_results]
        excluded = normalized[self.max_results :]
        truncated = bool(excluded) or self._metadata_inventory_truncated
        self._inventory = {
            "available_result_count": len(normalized),
            "selected_result_count": len(selected),
            "excluded_result_count": len(excluded),
            "selected_result_ids": list(selected),
            "excluded_result_ids_sample": list(excluded[:20]),
            "truncated": truncated,
            "limit": self.max_results,
            "selection_order": "created_at_desc_then_file_mtime_desc_then_result_id_desc",
            "inventory_count_is_lower_bound": self._metadata_inventory_truncated,
            "exclusion_reason": (
                "max_results_bound"
                if excluded
                else (
                    "metadata_inventory_page_bound"
                    if self._metadata_inventory_truncated
                    else "none"
                )
            ),
        }
        if truncated and report_truncation:
            self._add_diagnostic(
                "recommendation_result_inventory_truncated:"
                f"limit={self.max_results}:available_at_least={len(normalized)}"
            )
        return tuple(selected)

    def inventory_summary(self) -> Mapping[str, Any]:
        if not self._inventory:
            self.list_result_ids()
        return dict(self._inventory)

    def _path_for(self, result_id: str) -> Path:
        return self.runs_dir / f"{_safe_result_id(result_id)}.json"

    def paths_for_results(self, result_ids: Sequence[str]) -> tuple[Path, ...]:
        self._load_metadata()
        paths: set[Path] = set(_sqlite_sidecar_paths(self.db_path))
        for result_id in result_ids:
            default_path = self._path_for(result_id)
            paths.add(default_path)
            metadata = self.metadata_for(result_id)
            if metadata is not None:
                declared = metadata.get("data_path")
                if declared not in (None, ""):
                    paths.add(Path(str(declared)).expanduser().resolve())
        self._accessed_paths.update(paths)
        return tuple(sorted(paths, key=str))

    def read_result(self, result_id: str) -> Mapping[str, Any] | None:
        safe_id = _safe_result_id(result_id)
        if not safe_id:
            self._add_diagnostic("recommendation_result_id_invalid")
            return None
        metadata = self.metadata_for(safe_id)
        path = self._path_for(safe_id)
        if metadata is None:
            self._add_diagnostic(f"recommendation_metadata_missing:{safe_id}")
        else:
            declared = metadata.get("data_path")
            if declared not in (None, ""):
                declared_path = Path(str(declared)).expanduser().resolve()
                if declared_path.is_file():
                    path = declared_path
                elif path.is_file():
                    self._add_diagnostic(
                        f"recommendation_metadata_data_path_missing:{safe_id}"
                    )
                else:
                    path = declared_path
            else:
                self._add_diagnostic(
                    f"recommendation_metadata_data_path_missing:{safe_id}"
                )
        self._accessed_paths.add(path)
        if not path.is_file():
            self._add_diagnostic(f"recommendation_json_missing:{safe_id}")
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self._add_diagnostic(
                f"recommendation_json_read_failed:{safe_id}:{type(exc).__name__}"
            )
            return None
        if not isinstance(payload, Mapping):
            self._add_diagnostic(f"recommendation_json_not_object:{safe_id}")
            return None
        payload_map = dict(payload)
        if _text(payload_map.get("result_id")) != safe_id:
            self._add_diagnostic(f"recommendation_result_identity_mismatch:{safe_id}")
        recommendations = payload_map.get("recommendations")
        if metadata is not None and isinstance(recommendations, list):
            expected_count = _int_or_none(metadata.get("stock_count"))
            if expected_count is not None and expected_count != len(recommendations):
                self._add_diagnostic(
                    f"recommendation_metadata_stock_count_mismatch:{safe_id}"
                )
        return payload_map


class ReadOnlyJournalRevisionSource:
    """Direct JSONL reader for continuity revisions and technical ACKs."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_records: int = DEFAULT_MAX_JOURNAL_ROWS,
    ) -> None:
        if isinstance(max_records, bool) or max_records <= 0:
            raise ValueError("max_records must be positive")
        self.path = Path(path).expanduser().resolve()
        self.max_records = max_records
        self.diagnostics: list[str] = []
        self._records: tuple[Mapping[str, Any], ...] | None = None
        self._scope_id = ""
        self._exact_cache: dict[
            tuple[str, str, str, str], tuple[Mapping[str, Any], ...]
        ] = {}
        self._incomplete_queries: set[str] = set()
        self._journal_read_issue = False
        self._broad_history_truncated = False

    def _add_diagnostic(self, value: str) -> None:
        if value not in self.diagnostics:
            self.diagnostics.append(value)

    def reset(self) -> None:
        """Start a new read operation without reusing a prior JSONL cache."""

        self.diagnostics.clear()
        self._records = None
        self._scope_id = ""
        self._exact_cache.clear()
        self._incomplete_queries.clear()
        self._journal_read_issue = False
        self._broad_history_truncated = False

    def set_scope(self, scope_id: str | None) -> None:
        """Bind exact action/ACK reads to one caller-owned personalization scope."""

        self._scope_id = _text(scope_id)
        self._exact_cache.clear()

    @property
    def completeness_status(self) -> str:
        """Whether every exact query used in this read stayed within its bound."""

        return (
            "incomplete"
            if self._journal_read_issue or self._incomplete_queries
            else "verified"
        )

    def inventory_summary(self) -> Mapping[str, Any]:
        """Expose bounded-reader state separately from byte consistency."""

        return {
            "path": str(self.path),
            "exists": self.path.is_file(),
            "max_records": self.max_records,
            "query_mode": "exact_identity_and_scope_before_bound",
            "completeness_status": self.completeness_status,
            "incomplete_queries": sorted(self._incomplete_queries),
            "broad_history_truncated": self._broad_history_truncated,
            "read_integrity": "incomplete" if self._journal_read_issue else "verified",
        }

    def paths_for_fingerprint(self) -> tuple[Path, ...]:
        return (self.path,)

    def _load(self) -> tuple[Mapping[str, Any], ...]:
        if self._records is not None:
            return self._records
        if not self.path.is_file():
            self._add_diagnostic("journal_jsonl_missing")
            self._journal_read_issue = True
            self._records = ()
            return self._records
        records: list[Mapping[str, Any]] = []
        valid_count = 0
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        self._journal_read_issue = True
                        self._add_diagnostic(
                            f"journal_jsonl_malformed_line:{line_number}"
                        )
                        continue
                    if isinstance(value, Mapping):
                        valid_count += 1
                        if len(records) < self.max_records:
                            records.append(dict(value))
                        else:
                            self._broad_history_truncated = True
                    else:
                        self._journal_read_issue = True
                        self._add_diagnostic(
                            f"journal_jsonl_non_object_line:{line_number}"
                        )
        except (OSError, UnicodeError) as exc:
            self._journal_read_issue = True
            self._add_diagnostic(f"journal_jsonl_read_failed:{type(exc).__name__}")
        if valid_count > self.max_records:
            self._add_diagnostic("journal_jsonl_read_limit_reached")
        self._records = tuple(records)
        return self._records

    def scan_integrity(self) -> None:
        """Scan the complete JSONL stream for malformed/unknown bytes."""

        self._load()

    def _scan_exact(
        self,
        *,
        query_kind: str,
        result_id: str,
        stock_code: str,
        predicate: Any,
    ) -> tuple[Mapping[str, Any], ...]:
        """Scan once, filter exact identity first, then apply max_records.

        ``max_records`` bounds the matching query, not unrelated journal
        history.  When the matching history itself exceeds the bound, return a
        conflict marker rather than an apparently complete prefix; projection
        callers can then fail closed without treating unknown history as
        ``not_recorded``.
        """

        cache_key = (query_kind, _text(result_id), _text(stock_code), self._scope_id)
        cached = self._exact_cache.get(cache_key)
        if cached is not None:
            return cached
        if not self.path.is_file():
            self._add_diagnostic("journal_jsonl_missing")
            self._journal_read_issue = True
            self._exact_cache[cache_key] = ()
            return ()
        matched: list[Mapping[str, Any]] = []
        total_matches = 0
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        self._journal_read_issue = True
                        self._add_diagnostic(
                            f"journal_jsonl_malformed_line:{line_number}"
                        )
                        continue
                    if not isinstance(value, Mapping):
                        self._journal_read_issue = True
                        self._add_diagnostic(
                            f"journal_jsonl_non_object_line:{line_number}"
                        )
                        continue
                    if not predicate(value):
                        continue
                    total_matches += 1
                    if len(matched) < self.max_records:
                        matched.append(dict(value))
        except (OSError, UnicodeError) as exc:
            self._journal_read_issue = True
            self._add_diagnostic(f"journal_jsonl_read_failed:{type(exc).__name__}")
        if total_matches > self.max_records:
            query_label = f"{query_kind}:{_text(result_id)}:{_text(stock_code)}"
            self._incomplete_queries.add(query_label)
            self._add_diagnostic(
                f"journal_exact_read_limit_reached:{query_label}:max={self.max_records}"
            )
            matched = [
                self._incomplete_marker(
                    query_kind=query_kind,
                    result_id=_text(result_id),
                    stock_code=_text(stock_code),
                )
            ]
        elif self._journal_read_issue and (query_kind == "action" or not matched):
            # A malformed/non-object line or read failure may hide a relevant
            # row even when the parsed prefix contains no match.  Surface a
            # conflict marker so projection cannot downgrade unknown history
            # to an ordinary ``not_recorded`` result.
            query_label = f"{query_kind}:{_text(result_id)}:{_text(stock_code)}"
            self._incomplete_queries.add(query_label)
            self._add_diagnostic(
                f"journal_exact_read_incomplete:{query_label}"
            )
            matched = [
                self._incomplete_marker(
                    query_kind=query_kind,
                    result_id=_text(result_id),
                    stock_code=_text(stock_code),
                )
            ]
        result = tuple(matched)
        self._exact_cache[cache_key] = result
        return result

    def _incomplete_marker(
        self,
        *,
        query_kind: str,
        result_id: str,
        stock_code: str,
    ) -> Mapping[str, Any]:
        if query_kind == "action":
            return {
                "record_type": "decision_continuity_revision",
                "revision_id": f"journal-incomplete:{result_id}:{stock_code}",
                "action": "accepted",
                "action_state": "conflict",
                "result_id": result_id,
                "stock_code": stock_code,
                "personalization_scope_id": self._scope_id,
                "journal_read_status": "incomplete",
            }
        return {
            "record_type": "decision_continuity_revision",
            "revision_id": f"journal-incomplete:{result_id}:{stock_code}",
            "action": "delivery_ack",
            "entity_type": "personalization_delivery",
            "event_kind": "personalization_delivery_ack.v1",
            "result_id": result_id,
            "stock_code": stock_code,
            "personalization_scope_id": self._scope_id,
            "status": "incomplete",
            "journal_read_status": "incomplete",
        }

    def _matches_exact_scope_identity(
        self,
        row: Mapping[str, Any],
        *,
        result_id: str,
        stock_code: str,
    ) -> bool:
        return (
            _text(result_id) in _explicit_result_values(row)
            and _text(stock_code) in _explicit_stock_values(row)
            and (
                not self._scope_id
                or self._scope_id
                in _alias_values(row, ("personalization_scope_id", "scope_id"))
            )
        )

    def list_decision_revisions(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            row
            for row in self._load()
            if _text(row.get("record_type")) == "decision_continuity_revision"
        )

    def list_action_rows(
        self,
        result_id: str,
        stock_code: str,
    ) -> tuple[Mapping[str, Any], ...]:
        allowed = {"accepted", "skipped", "watch", "held", "buy", "sell", "note", "review_scheduled"}
        return self._scan_exact(
            query_kind="action",
            result_id=result_id,
            stock_code=stock_code,
            predicate=lambda row: (
                _text(row.get("record_type")) == "decision_continuity_revision"
                and _text(row.get("action")) in allowed
                and self._matches_exact_scope_identity(
                    row,
                    result_id=result_id,
                    stock_code=stock_code,
                )
            ),
        )

    def list_delivery_ack_rows(
        self,
        result_id: str,
        stock_code: str,
    ) -> tuple[Mapping[str, Any], ...]:
        return self._scan_exact(
            query_kind="delivery_ack",
            result_id=result_id,
            stock_code=stock_code,
            predicate=lambda row: (
                _text(row.get("record_type")) == "decision_continuity_revision"
                and _text(row.get("action")) == "delivery_ack"
                and _text(row.get("entity_type")) == "personalization_delivery"
                and self._matches_exact_scope_identity(
                    row,
                    result_id=result_id,
                    stock_code=stock_code,
                )
            ),
        )


class ReadOnlyEvidenceSource:
    """Read exact candidate EvidenceEvent rows and nested outcomes."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        max_events: int = DEFAULT_MAX_EVIDENCE_EVENTS,
    ) -> None:
        if isinstance(max_events, bool) or max_events <= 0:
            raise ValueError("max_events must be positive")
        self.db_path = Path(db_path).expanduser().resolve()
        self.max_events = max_events
        self.repository = EvidenceEventRepository(object(), db_path=self.db_path)
        self.diagnostics: list[str] = []
        self._scope_id = ""
        self._stock_cache: dict[
            tuple[str, str, str], tuple[Mapping[str, Any], ...]
        ] = {}

    def _add_diagnostic(self, value: str) -> None:
        if value not in self.diagnostics:
            self.diagnostics.append(value)

    def reset(self) -> None:
        """Start a new read operation without reusing a prior evidence cache."""

        self.diagnostics.clear()
        self._stock_cache.clear()

    def set_scope(self, scope_id: str | None) -> None:
        """Bind the next exact event query to one optional personal scope."""

        self._scope_id = _text(scope_id)
        self._stock_cache.clear()

    def paths_for_fingerprint(self) -> tuple[Path, ...]:
        return _sqlite_sidecar_paths(self.db_path)

    def _stock_events(
        self,
        result_id: str,
        stock_code: str,
    ) -> tuple[Mapping[str, Any], ...]:
        cache_key = (self._scope_id, _text(result_id), _text(stock_code))
        if cache_key in self._stock_cache:
            return self._stock_cache[cache_key]
        if not self.db_path.is_file():
            self._add_diagnostic("evidence_database_missing")
            self._stock_cache[cache_key] = ()
            return ()
        try:
            # Keep event and outcome reads in one explicit SQLite read
            # transaction.  Calling the writer repository's two public read
            # methods would use two connections and could combine different
            # WAL snapshots while an outcome producer is committing.
            uri = self.db_path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                connection.execute("PRAGMA query_only = ON")
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN")
                if (
                    connection.execute(
                        "SELECT 1 FROM sqlite_master "
                        "WHERE type='table' AND name=?",
                        ("evidence_events",),
                    ).fetchone()
                    is None
                ):
                    self._add_diagnostic("evidence_events_table_missing")
                    self._stock_cache[cache_key] = ()
                    return ()
                # Filter the exact persisted result identity in SQLite before
                # applying the event bound.  Limiting all rows for a symbol
                # first would let sibling results crowd out the requested
                # result and falsely report an identity miss.
                metadata_json = (
                    "CASE WHEN json_valid(metadata_json) "
                    "THEN metadata_json ELSE '{}' END"
                )
                identity_paths = (
                    "$.result_id",
                    "$.source_result_id",
                    "$.decision_identity.result_id",
                    "$.decision_identity.source_result_id",
                    "$.payload.result_id",
                    "$.payload.source_result_id",
                    "$.metadata.result_id",
                    "$.metadata.source_result_id",
                    "$.personalization_action.result_id",
                    "$.personalization_action.source_result_id",
                )
                identity_where = " OR ".join(
                    f"CAST(json_extract({metadata_json}, '{path}') AS TEXT) = ?"
                    for path in identity_paths
                )
                scope_paths = (
                    "$.personalization_scope_id",
                    "$.scope_id",
                    "$.decision_identity.personalization_scope_id",
                    "$.decision_identity.scope_id",
                    "$.payload.personalization_scope_id",
                    "$.payload.scope_id",
                    "$.metadata.personalization_scope_id",
                    "$.metadata.scope_id",
                    "$.personalization_action.personalization_scope_id",
                    "$.personalization_action.scope_id",
                )
                scope_where = " OR ".join(
                    f"CAST(json_extract({metadata_json}, '{path}') AS TEXT) = ?"
                    for path in scope_paths
                )
                scope_clause = (
                    f" AND ({scope_where})" if self._scope_id else ""
                )
                query_params_list: list[Any] = [
                    stock_code,
                    *([result_id] * len(identity_paths)),
                ]
                if self._scope_id:
                    query_params_list.extend([self._scope_id] * len(scope_paths))
                query_params_list.append(self.max_events + 1)
                query_params = tuple(query_params_list)
                event_rows = connection.execute(
                    "SELECT * FROM evidence_events "
                    "WHERE symbol = ? AND ("
                    f"{identity_where}"
                    f"){scope_clause} "
                    "ORDER BY decision_date ASC, event_id ASC LIMIT ?",
                    query_params,
                ).fetchall()
                if not event_rows and connection.execute(
                    "SELECT 1 FROM evidence_events "
                    "WHERE symbol = ? AND ("
                    f"{identity_where}"
                    ") LIMIT 1",
                    (stock_code, *([result_id] * len(identity_paths))),
                ).fetchone() is not None:
                    self._add_diagnostic(
                        (
                            f"evidence_event_scope_identity_missing:{result_id}:"
                            f"{stock_code}:{self._scope_id}"
                            if self._scope_id
                            else f"evidence_event_exact_identity_missing:{result_id}:{stock_code}"
                        )
                    )
                events = [
                    self.repository._row_to_event(dict(row))
                    for row in event_rows
                ]
                event_maps = [_json_safe(asdict(event)) for event in events]
                event_ids = [
                    _text(event_map.get("event_id"))
                    for event_map in event_maps
                    if _text(event_map.get("event_id"))
                ]
                outcomes: list[Any] = []
                if (
                    connection.execute(
                        "SELECT 1 FROM sqlite_master "
                        "WHERE type='table' AND name=?",
                        ("evidence_outcomes",),
                    ).fetchone()
                    is None
                ):
                    self._add_diagnostic("evidence_outcomes_table_missing")
                else:
                    for start in range(
                        0,
                        len(event_ids),
                        _SQLITE_READ_BIND_CHUNK_SIZE,
                    ):
                        chunk = event_ids[
                            start : start + _SQLITE_READ_BIND_CHUNK_SIZE
                        ]
                        placeholders = ", ".join("?" for _ in chunk)
                        outcomes.extend(
                            self.repository._row_to_outcome(dict(row))
                            for row in connection.execute(
                                "SELECT * FROM evidence_outcomes "
                                f"WHERE event_id IN ({placeholders}) "
                                "ORDER BY event_id ASC, window_days ASC",
                                tuple(chunk),
                            ).fetchall()
                        )

            if len(events) > self.max_events:
                self._add_diagnostic(
                    f"evidence_event_read_limit_reached:{stock_code}"
                )
            events = events[: self.max_events]
            event_maps = event_maps[: self.max_events]
            outcomes_by_event: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
            for outcome in outcomes:
                outcome_map = _json_safe(asdict(outcome))
                outcome_metadata = outcome_map.get("metadata")
                if isinstance(outcome_metadata, Mapping):
                    # EvidenceOutcome's typed fields do not include V6 label
                    # identity/tier extensions.  Promote only explicit
                    # metadata keys into the child object while retaining the
                    # metadata map so parent/child alias verification can see
                    # both copies.  No value is inferred from return.
                    for key in (
                        "result_id",
                        "source_result_id",
                        "stock_code",
                        "symbol",
                        "personalization_scope_id",
                        "scope_id",
                        "prediction_id",
                        "prediction_receipt_hash",
                        "projection_receipt_hash",
                        "horizon_days",
                        "horizon",
                        "window_type",
                        "event_price_date",
                        "outcome_price_date",
                        "cost_scenario_hash",
                        "label_contract_id",
                        "return_basis",
                        "label_available_date",
                        "label_available_at",
                        "data_as_of_date",
                        "label",
                        "outcome_tier",
                        "outcome_recorded_at",
                        "recorded_at",
                        "utility_eligible",
                        "utility_return_bp",
                        "net_return_bp",
                        "cost_scenario_id",
                        "cost_scenario_version",
                        "statistical_id",
                    ):
                        if outcome_map.get(key) in (None, "") and outcome_metadata.get(key) not in (None, ""):
                            outcome_map[key] = outcome_metadata[key]
                outcomes_by_event[_text(outcome_map.get("event_id"))].append(
                    outcome_map
                )
            selected: list[Mapping[str, Any]] = []
            missing_identity = 0
            for event_map in event_maps:
                result_values = _explicit_result_values(event_map)
                if not result_values:
                    missing_identity += 1
                    continue
                # The target result is applied by list_events_for_candidate;
                # keep every explicitly identified event here so a later
                # exact filter can still expose alias conflicts.
                enriched = dict(event_map)
                enriched["outcomes"] = list(
                    outcomes_by_event.get(_text(event_map.get("event_id")), ())
                )
                selected.append(enriched)
            if missing_identity:
                self._add_diagnostic(
                    f"evidence_event_result_identity_missing:{stock_code}:{missing_identity}"
                )
            self._stock_cache[cache_key] = tuple(selected)
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            self._add_diagnostic(f"evidence_read_failed:{type(exc).__name__}")
            self._stock_cache[cache_key] = ()
        return self._stock_cache[cache_key]

    def list_events(
        self,
        result_id: str,
        stock_code: str,
    ) -> tuple[Mapping[str, Any], ...]:
        exact: list[Mapping[str, Any]] = []
        for event in self._stock_events(result_id, stock_code):
            result_values = _explicit_result_values(event)
            stock_values = _explicit_stock_values(event)
            # An event with one matching alias and one contradictory alias is
            # retained for projection's fail-closed alias diagnostic.
            if result_id in result_values and stock_code in stock_values:
                exact.append(event)
        if not exact and self._stock_events(result_id, stock_code):
            self._add_diagnostic(
                f"evidence_event_exact_identity_missing:{result_id}:{stock_code}"
            )
        return tuple(exact)


class ReadOnlyProjectionReceiptSource:
    """Optional standalone receipt lookup; embedded/path receipts remain primary."""

    def __init__(
        self,
        output_root: str | Path,
        *,
        max_files: int = DEFAULT_MAX_RECEIPT_FILES,
    ) -> None:
        if isinstance(max_files, bool) or max_files <= 0:
            raise ValueError("max_files must be positive")
        root = Path(output_root).expanduser().resolve()
        self.paths = (
            root / "recommendation" / "receipts",
            root / "recommendation" / "projection_receipts",
            root / "calibration" / "receipts",
            root / "scheduled" / "receipts",
        )
        self.max_files = max_files
        self.diagnostics: list[str] = []
        self._scanned = False
        self._by_hash: dict[str, Mapping[str, Any]] = {}
        self._files: set[Path] = set()

    def _scan(self) -> None:
        if self._scanned:
            return
        self._scanned = True
        scanned = 0
        for directory in self.paths:
            if not directory.is_dir():
                continue
            try:
                candidates = sorted(
                    directory.rglob("*.json"),
                    key=lambda item: str(item),
                )
                for path in candidates:
                    if not path.is_file():
                        continue
                    if scanned >= self.max_files:
                        self._add_diagnostic("projection_receipt_read_limit_reached")
                        return
                    scanned += 1
                    self._files.add(path.resolve())
                    try:
                        value = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, UnicodeError, json.JSONDecodeError):
                        continue
                    if not isinstance(value, Mapping):
                        continue
                    receipt_hash = _text(value.get("receipt_hash"))
                    if receipt_hash:
                        self._by_hash[receipt_hash] = dict(value)
            except OSError as exc:
                self._add_diagnostic(
                    f"projection_receipt_inventory_failed:{type(exc).__name__}"
                )

    def _add_diagnostic(self, value: str) -> None:
        if value not in self.diagnostics:
            self.diagnostics.append(value)

    def reset(self) -> None:
        """Start a new receipt read without reusing a prior file cache."""

        self.diagnostics.clear()
        self._scanned = False
        self._by_hash.clear()
        self._files.clear()

    def candidate_paths(self) -> tuple[Path, ...]:
        """Inventory receipt paths without opening JSON contents."""

        paths: set[Path] = set()
        for directory in self.paths:
            if not directory.is_dir():
                continue
            try:
                paths.update(
                    path.resolve()
                    for path in directory.rglob("*.json")
                    if path.is_file()
                )
            except OSError as exc:
                self._add_diagnostic(
                    f"projection_receipt_inventory_failed:{type(exc).__name__}"
                )
        return tuple(sorted(paths, key=str))

    def read(self, receipt_hash: str) -> Mapping[str, Any] | None:
        self._scan()
        return self._by_hash.get(_text(receipt_hash))

    def paths_for_fingerprint(self) -> tuple[Path, ...]:
        self._scan()
        return tuple(sorted(self._files | set(self.candidate_paths()), key=str))


@dataclass(frozen=True)
class PersonalizationReadReport:
    """Machine-readable result of one scope/as-of read-only inspection."""

    scope_id: str
    evaluated_as_of: str
    evaluation_cutoff_at: str | None
    source_manifest_hash: str
    source_bytes_unchanged: bool
    source_consistency_status: str
    source_fingerprints: tuple[Mapping[str, Any], ...]
    recommendation_metadata: tuple[Mapping[str, Any], ...]
    projections: tuple[Mapping[str, Any], ...]
    evaluation_rows: tuple[Mapping[str, Any], ...]
    denominators: Mapping[str, int]
    cohort: Mapping[str, Any]
    inventory: Mapping[str, Any]
    candidate_inventory: Mapping[str, Mapping[str, Any]]
    diagnostics: tuple[str, ...]
    source_completeness_status: str = "verified"
    evaluation: PersonalizationCalibrationEvaluation | None = None
    read_only: bool = True
    writes_allowed: bool = False
    formal_order_allowed: bool = False
    auto_action_allowed: bool = False
    schema_version: str = PERSONALIZATION_READ_REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.read_only or self.writes_allowed or self.formal_order_allowed or self.auto_action_allowed:
            raise ValueError("personalization read report must remain read-only")
        if self.source_completeness_status not in {"verified", "incomplete"}:
            raise ValueError("unsupported personalization source completeness status")

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "schema_version": self.schema_version,
                "scope_id": self.scope_id,
                "evaluated_as_of": self.evaluated_as_of,
                "evaluation_cutoff_at": self.evaluation_cutoff_at,
                "source_manifest_hash": self.source_manifest_hash,
                "source_bytes_unchanged": self.source_bytes_unchanged,
                "source_consistency_status": self.source_consistency_status,
                "source_completeness_status": self.source_completeness_status,
                "source_fingerprints": list(self.source_fingerprints),
                "recommendation_metadata": list(self.recommendation_metadata),
                "projections": list(self.projections),
                "evaluation_rows": list(self.evaluation_rows),
                "denominators": dict(self.denominators),
                "cohort": dict(self.cohort),
                "inventory": dict(self.inventory),
                "candidate_inventory": {
                    key: dict(value)
                    for key, value in self.candidate_inventory.items()
                },
                "diagnostics": list(self.diagnostics),
                "evaluation": self.evaluation.to_dict() if self.evaluation else None,
                "read_only": self.read_only,
                "writes_allowed": self.writes_allowed,
                "formal_order_allowed": self.formal_order_allowed,
                "auto_action_allowed": self.auto_action_allowed,
            }
        )


@dataclass(frozen=True)
class PersonalRecommendationChoiceReadEntry:
    """一筆已綁定 canonical execution 的個人選擇與既有結果狀態。"""

    choice: PersonalRecommendationChoice
    revision_id: str
    continuity_event_id: str
    created_at: str
    outcome_link_status: str = "not_requested"
    outcome_status: str = "not_applicable"
    outcomes: tuple[Mapping[str, Any], ...] = ()
    delivery_scope_id: str | None = None
    source_snapshot_identity_available: bool = False
    diagnostics: tuple[str, ...] = ()
    read_only: bool = True
    writes_allowed: bool = False
    formal_order_allowed: bool = False
    auto_action_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.read_only or self.writes_allowed or self.formal_order_allowed or self.auto_action_allowed:
            raise ValueError("personal recommendation choice readback must remain read-only")
        if self.outcome_link_status not in {
            "not_requested",
            "partial_same_decision",
            "unavailable",
            "identity_conflict",
        }:
            raise ValueError("unsupported personal choice outcome link status")
        object.__setattr__(self, "outcomes", tuple(dict(row) for row in self.outcomes))
        object.__setattr__(self, "diagnostics", tuple(str(item) for item in self.diagnostics))

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "choice": self.choice.to_dict(),
                "revision_id": self.revision_id,
                "continuity_event_id": self.continuity_event_id,
                "created_at": self.created_at,
                "outcome_link_status": self.outcome_link_status,
                "outcome_status": self.outcome_status,
                "outcomes": list(self.outcomes),
                "delivery_scope_id": self.delivery_scope_id,
                "source_snapshot_identity_available": self.source_snapshot_identity_available,
                "diagnostics": list(self.diagnostics),
                "read_only": self.read_only,
                "writes_allowed": self.writes_allowed,
                "formal_order_allowed": self.formal_order_allowed,
                "auto_action_allowed": self.auto_action_allowed,
            }
        )


@dataclass(frozen=True)
class PersonalRecommendationChoiceReadReport:
    """同一保存推薦的 append-only 個人選擇讀回。"""

    result_id: str
    stock_code: str
    decision_date: str
    choices: tuple[PersonalRecommendationChoiceReadEntry, ...]
    source_completeness_status: str
    diagnostics: tuple[str, ...] = ()
    read_only: bool = True
    writes_allowed: bool = False
    formal_order_allowed: bool = False
    auto_action_allowed: bool = False
    schema_version: str = "personal-recommendation-choice-readback.v1"

    def __post_init__(self) -> None:
        if not self.read_only or self.writes_allowed or self.formal_order_allowed or self.auto_action_allowed:
            raise ValueError("personal choice report must remain read-only")
        if self.source_completeness_status not in {"verified", "incomplete"}:
            raise ValueError("unsupported personal choice source completeness status")

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "schema_version": self.schema_version,
                "result_id": self.result_id,
                "stock_code": self.stock_code,
                "decision_date": self.decision_date,
                "choices": [entry.to_dict() for entry in self.choices],
                "source_completeness_status": self.source_completeness_status,
                "diagnostics": list(self.diagnostics),
                "read_only": self.read_only,
                "writes_allowed": self.writes_allowed,
                "formal_order_allowed": self.formal_order_allowed,
                "auto_action_allowed": self.auto_action_allowed,
            }
        )


class PersonalizationReadService:
    """Compose existing sources into one bounded scope/as-of read operation."""

    def __init__(
        self,
        recommendation_source: ReadOnlyRecommendationSource,
        journal_source: ReadOnlyJournalRevisionSource,
        evidence_source: ReadOnlyEvidenceSource,
        receipt_source: ReadOnlyProjectionReceiptSource | None = None,
        *,
        execution_queries: Any = None,
        canonical_runs_dir: str | Path | None = None,
        max_candidates_per_result: int = DEFAULT_MAX_CANDIDATES_PER_RESULT,
    ) -> None:
        if isinstance(max_candidates_per_result, bool) or max_candidates_per_result <= 0:
            raise ValueError("max_candidates_per_result must be positive")
        self.recommendation_source = recommendation_source
        self.journal_source = journal_source
        self.evidence_source = evidence_source
        self.receipt_source = receipt_source
        self.execution_queries = execution_queries
        self.canonical_runs_dir = (
            Path(canonical_runs_dir).expanduser().resolve()
            if canonical_runs_dir is not None
            else None
        )
        self.max_candidates_per_result = max_candidates_per_result
        self._pending_diagnostics: list[str] = []
        self._last_projection_objects: dict[
            tuple[str, str], PersonalizationProjectionResult
        ] = {}
        self.projection_service = PersonalizationProjectionService(
            recommendation_reader=self.recommendation_source.read_result,
            projection_receipt_reader=(
                self.receipt_source.read if self.receipt_source is not None else None
            ),
            action_reader=self.journal_source.list_action_rows,
            evidence_reader=self.evidence_source.list_events,
            delivery_reader=self.journal_source.list_delivery_ack_rows,
        )

    @classmethod
    def from_paths(
        cls,
        *,
        output_root: str | Path,
        journal_path: str | Path | None = None,
        evidence_db_path: str | Path | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
        max_candidates_per_result: int = DEFAULT_MAX_CANDIDATES_PER_RESULT,
        max_evidence_events: int = DEFAULT_MAX_EVIDENCE_EVENTS,
        max_journal_rows: int = DEFAULT_MAX_JOURNAL_ROWS,
    ) -> "PersonalizationReadService":
        root = Path(output_root).expanduser().resolve()
        resolved_journal = Path(journal_path) if journal_path is not None else root / "portfolio" / "journal_entries.jsonl"
        resolved_evidence = (
            Path(evidence_db_path)
            if evidence_db_path is not None
            else root.parent / "sqlite" / "twstock.db"
        )
        runs_dir = root / "recommendation" / "runs"
        return cls(
            ReadOnlyRecommendationSource(root, max_results=max_results),
            ReadOnlyJournalRevisionSource(resolved_journal, max_records=max_journal_rows),
            ReadOnlyEvidenceSource(resolved_evidence, max_events=max_evidence_events),
            ReadOnlyProjectionReceiptSource(root),
            execution_queries=build_recommendation_execution_queries(
                SimpleNamespace(output_root=root)
            ),
            canonical_runs_dir=runs_dir,
            max_candidates_per_result=max_candidates_per_result,
        )

    def read_canonical_execution_exact(
        self,
        result_id: str,
    ) -> RecommendationExecutionReadModel | None:
        """Read one canonical execution by its caller-supplied exact identity."""

        resolved = _safe_result_id(result_id)
        if not resolved:
            raise ValueError("result_id must be a filename-like exact id")
        if self.execution_queries is None:
            return None
        read_model = self.execution_queries.get(resolved)
        if read_model is None or read_model.execution is None:
            return None
        if read_model.result_id != resolved:
            raise ValueError("canonical recommendation exact result identity mismatch")
        if read_model.integrity_basis != "canonical_payload_and_index_verified":
            raise ValueError("canonical recommendation exact readback is not verified")
        return read_model

    def read_personal_recommendation_choices(
        self,
        result_id: str,
        stock_code: str,
        *,
        delivery_scope_id: str | None = None,
        evaluated_as_of: str | None = None,
    ) -> PersonalRecommendationChoiceReadReport:
        """精確讀回同一 canonical recommendation identity 的個人選擇。

        outcome 只有在 caller 明示 delivery scope 與 as-of 日期時才查詢；
        個人 policy scope 不會被拿來猜 delivery scope。既有 outcome 最多以
        result/stock/date 標成部分連結，因為目前 outcome projection 沒有完整
        source snapshot identity 時，這個 reader 不會替它補值。
        """

        resolved_result = _safe_result_id(result_id)
        resolved_stock = _text(stock_code)
        if not resolved_result or not resolved_stock:
            raise ValueError("result_id 與 stock_code 必須是精確 identity")
        if (delivery_scope_id is None) != (evaluated_as_of is None):
            raise ValueError("delivery_scope_id 與 evaluated_as_of 必須同時明示")
        resolved_delivery_scope = _text(delivery_scope_id)
        if delivery_scope_id is not None and not resolved_delivery_scope:
            raise ValueError("delivery_scope_id 不可為空")

        read_model = self.read_canonical_execution_exact(resolved_result)
        if read_model is None or read_model.execution is None:
            raise ValueError("個人選擇只支援已驗證的 canonical execution")
        if read_model.integrity_basis != "canonical_payload_and_index_verified":
            raise ValueError("個人選擇來源不是已驗證 canonical payload/index")
        execution = read_model.execution
        matching_items = tuple(
            item
            for item in execution.items
            if _text(getattr(item, "stock_code", "")) == resolved_stock
        )
        if len(matching_items) != 1:
            raise ValueError("所選股票未唯一存在於 canonical recommendation")
        context = execution.context
        as_of_date = getattr(context, "as_of_date", None)
        as_of_date_isoformat = getattr(as_of_date, "isoformat", None)
        if not callable(as_of_date_isoformat):
            raise ValueError("canonical execution 缺少明確 decision date")
        decision_date = as_of_date_isoformat()
        universe = getattr(context, "universe_identity", None)
        snapshot = getattr(universe, "snapshot", None)
        source_snapshot_id = _text(getattr(snapshot, "universe_snapshot_id", ""))
        source_snapshot_hash = _text(getattr(snapshot, "universe_snapshot_hash", ""))
        if not source_snapshot_id or not source_snapshot_hash:
            raise ValueError("canonical execution 缺少 source snapshot identity")
        policy_event = read_personal_use_policy_snapshot_event(
            execution,
            expected_result_id=resolved_result,
        )
        decision_clock = parse_aware_datetime(
            policy_event["decision_at"], "personal policy event decision_at"
        )

        self.journal_source.reset()
        self.journal_source.set_scope(None)
        self.journal_source.scan_integrity()
        raw_rows = self.journal_source.list_action_rows(resolved_result, resolved_stock)
        diagnostics: list[str] = list(self.journal_source.diagnostics)
        if self.journal_source.completeness_status != "verified":
            diagnostics.append("personal_choice_journal_incomplete")
            return PersonalRecommendationChoiceReadReport(
                result_id=resolved_result,
                stock_code=resolved_stock,
                decision_date=decision_date,
                choices=(),
                source_completeness_status="incomplete",
                diagnostics=tuple(dict.fromkeys(diagnostics)),
            )

        entries: list[PersonalRecommendationChoiceReadEntry] = []
        seen_request_ids: set[str] = set()
        expected_policy = policy_event["policy_snapshot"]
        # 與 writer 共用同一 saved receipt／selected-row 驗證；event 的
        # effective_mode 是整次 execution 狀態，choice 的 mode 則是所選股票狀態。
        from app_module.personalization_action_recorder import (
            PersonalizationDecisionRecorder,
            validate_personal_recommendation_choice_binding,
        )

        expected_choice_identity = DecisionIdentity(
            result_id=resolved_result,
            stock_code=resolved_stock,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
            decision_date=decision_date,
            identity_status=IDENTITY_STATUS_LINKED,
        )

        for raw_row in raw_rows:
            payload = raw_row.get("payload")
            if not isinstance(payload, Mapping) or "personal_recommendation_choice" not in payload:
                continue
            try:
                revision = DecisionContinuityRevision.from_mapping(raw_row)
                choice_value = payload.get("personal_recommendation_choice")
                if not isinstance(choice_value, Mapping):
                    raise ValueError("personal choice payload is not an object")
                choice = PersonalRecommendationChoice.from_mapping(choice_value)
                validate_personal_recommendation_choice_binding(
                    raw_row,
                    revision,
                    choice,
                    expected_identity=expected_choice_identity,
                )
                if (
                    choice.result_id != resolved_result
                    or choice.stock_code != resolved_stock
                    or choice.decision_date != decision_date
                    or choice.source_snapshot_id != source_snapshot_id
                    or choice.source_snapshot_hash != source_snapshot_hash
                    or choice.canonical_payload_hash != read_model.payload_hash
                    or choice.raw_artifact_sha256 != read_model.raw_artifact_sha256
                ):
                    raise ValueError("personal choice canonical recommendation identity conflicts")
                if choice.request_id in seen_request_ids:
                    raise ValueError("personal choice request id is duplicated")
                seen_request_ids.add(choice.request_id)
                if _json_safe(choice.policy_snapshot) != _json_safe(expected_policy):
                    raise ValueError("personal choice policy snapshot differs from its saved execution")
                if choice.requested_mode != policy_event["requested_mode"]:
                    raise ValueError("personal choice requested mode differs from its saved execution")
                expected_model_evidence = (
                    PersonalizationDecisionRecorder.validate_selected_stock_model_evidence(
                        read_model=read_model,
                        execution=execution,
                        stock_code=resolved_stock,
                        decision_date=decision_date,
                        policy_snapshot=expected_policy,
                        requested_mode=policy_event["requested_mode"],
                        event_effective_mode=policy_event["effective_mode"],
                    )
                )
                expected_selected_mode = (
                    "personal_calibrated_probability"
                    if expected_model_evidence is not None
                    else "rule_only"
                )
                if choice.effective_mode != expected_selected_mode:
                    raise ValueError("personal choice selected-stock mode differs from its saved projection")
                if choice.model_evidence != expected_model_evidence:
                    raise ValueError("personal choice model evidence differs from its saved receipt row")
                action_clock = parse_aware_datetime(choice.action_at, "personal choice action_at")
                recorded_clock = parse_aware_datetime(
                    choice.recorded_at, "personal choice recorded_at"
                )
                if action_clock < decision_clock or recorded_clock < decision_clock:
                    raise ValueError("personal choice clock precedes canonical decision")
                created_at = revision.created_at
                if parse_aware_datetime(
                    created_at, "personal choice revision created_at"
                ) != recorded_clock:
                    raise ValueError("personal choice Journal clock conflicts with its payload")
            except (TypeError, ValueError, KeyError) as exc:
                diagnostics.append(
                    f"personal_choice_row_invalid:{type(exc).__name__}"
                )
                return PersonalRecommendationChoiceReadReport(
                    result_id=resolved_result,
                    stock_code=resolved_stock,
                    decision_date=decision_date,
                    choices=(),
                    source_completeness_status="incomplete",
                    diagnostics=tuple(dict.fromkeys(diagnostics)),
                )
            entries.append(
                PersonalRecommendationChoiceReadEntry(
                    choice=choice,
                    revision_id=revision.revision_id,
                    continuity_event_id=revision.continuity_event_id,
                    created_at=revision.created_at,
                )
            )

        if delivery_scope_id is not None and evaluated_as_of is not None:
            outcome_report = self.inspect_scope(
                scope_id=resolved_delivery_scope,
                evaluated_as_of=evaluated_as_of,
                result_id=resolved_result,
                stock_code=resolved_stock,
            )
            diagnostics.extend(outcome_report.diagnostics)
            if (
                outcome_report.source_consistency_status != "verified"
                or outcome_report.source_completeness_status != "verified"
            ):
                entries = [
                    PersonalRecommendationChoiceReadEntry(
                        choice=entry.choice,
                        revision_id=entry.revision_id,
                        continuity_event_id=entry.continuity_event_id,
                        created_at=entry.created_at,
                        outcome_link_status="unavailable",
                        delivery_scope_id=resolved_delivery_scope,
                        source_snapshot_identity_available=False,
                        diagnostics=("outcome_source_not_verified",),
                    )
                    for entry in entries
                ]
            else:
                matching_projection_rows = [
                    row
                    for row in outcome_report.projections
                    if _text(row.get("result_id")) == resolved_result
                    and _text(row.get("stock_code")) == resolved_stock
                    and isinstance(row.get("projection"), Mapping)
                    and _text(row["projection"].get("decision_date")) == decision_date
                ]
                if len(matching_projection_rows) != 1:
                    status = "identity_conflict" if matching_projection_rows else "unavailable"
                    entries = [
                        PersonalRecommendationChoiceReadEntry(
                            choice=entry.choice,
                            revision_id=entry.revision_id,
                            continuity_event_id=entry.continuity_event_id,
                            created_at=entry.created_at,
                            outcome_link_status=status,
                            delivery_scope_id=resolved_delivery_scope,
                            source_snapshot_identity_available=False,
                            diagnostics=("outcome_same_decision_projection_missing_or_ambiguous",),
                        )
                        for entry in entries
                    ]
                else:
                    projection = matching_projection_rows[0]["projection"]
                    prediction = projection.get("prediction")
                    prediction = prediction if isinstance(prediction, Mapping) else {}
                    evidence = projection.get("evidence")
                    evidence = evidence if isinstance(evidence, Mapping) else {}
                    entries = [
                        self._choice_entry_with_outcome(
                            entry,
                            projection=projection,
                            prediction=prediction,
                            evidence=evidence,
                            delivery_scope_id=resolved_delivery_scope,
                        )
                        for entry in entries
                    ]

        return PersonalRecommendationChoiceReadReport(
            result_id=resolved_result,
            stock_code=resolved_stock,
            decision_date=decision_date,
            choices=tuple(entries),
            source_completeness_status="verified",
            diagnostics=tuple(dict.fromkeys(diagnostics)),
        )

    @staticmethod
    def _choice_entry_with_outcome(
        entry: PersonalRecommendationChoiceReadEntry,
        *,
        projection: Mapping[str, Any],
        prediction: Mapping[str, Any],
        evidence: Mapping[str, Any],
        delivery_scope_id: str,
    ) -> PersonalRecommendationChoiceReadEntry:
        choice = entry.choice
        if (
            _text(projection.get("result_id")) != choice.result_id
            or _text(projection.get("stock_code")) != choice.stock_code
            or _text(projection.get("decision_date")) != choice.decision_date
        ):
            return PersonalRecommendationChoiceReadEntry(
                choice=choice,
                revision_id=entry.revision_id,
                continuity_event_id=entry.continuity_event_id,
                created_at=entry.created_at,
                outcome_link_status="identity_conflict",
                delivery_scope_id=delivery_scope_id,
                diagnostics=("outcome_identity_conflicts_with_personal_choice",),
            )
        receipt_hash = _text(prediction.get("prediction_receipt_hash"))
        if not receipt_hash:
            receipt_hash = _text(evidence.get("prediction_receipt_hash"))
        if choice.model_evidence is not None and receipt_hash and (
            receipt_hash != choice.model_evidence.receipt_hash
        ):
            return PersonalRecommendationChoiceReadEntry(
                choice=choice,
                revision_id=entry.revision_id,
                continuity_event_id=entry.continuity_event_id,
                created_at=entry.created_at,
                outcome_link_status="identity_conflict",
                delivery_scope_id=delivery_scope_id,
                diagnostics=("outcome_model_receipt_differs_from_saved_choice",),
            )
        outcome_rows = projection.get("outcomes")
        rows = (
            tuple(row for row in outcome_rows if isinstance(row, Mapping))
            if isinstance(outcome_rows, (list, tuple))
            else ()
        )
        return PersonalRecommendationChoiceReadEntry(
            choice=choice,
            revision_id=entry.revision_id,
            continuity_event_id=entry.continuity_event_id,
            created_at=entry.created_at,
            outcome_link_status="partial_same_decision",
            outcome_status=_text(projection.get("outcome_status")) or "not_applicable",
            outcomes=rows,
            delivery_scope_id=delivery_scope_id,
            source_snapshot_identity_available=False,
            diagnostics=(
                "以同一結果、股票與決策日期部分連結；未取得 outcome source snapshot identity。",
            ),
        )

    def inspect_scope(
        self,
        *,
        scope_id: str,
        evaluated_as_of: str,
        evaluation_cutoff_at: str | None = None,
        result_id: str | None = None,
        stock_code: str | None = None,
        fit_artifact: PersonalizationCalibrationFitArtifact | None = None,
    ) -> PersonalizationReadReport:
        resolved_scope = _text(scope_id)
        if not resolved_scope:
            raise ValueError("scope_id is required")
        resolved_as_of = _iso_date(evaluated_as_of, "evaluated_as_of")
        resolved_cutoff = None
        if evaluation_cutoff_at is not None:
            cutoff = _optional_datetime(evaluation_cutoff_at, "evaluation_cutoff_at")
            if cutoff is None:
                raise ValueError("evaluation_cutoff_at must be an aware ISO datetime")
            if cutoff.astimezone(_MARKET_TIMEZONE).date() > date.fromisoformat(resolved_as_of):
                raise ValueError("evaluation_cutoff_at cannot follow evaluated_as_of")
            resolved_cutoff = cutoff.isoformat(timespec="microseconds")
        requested_result = _safe_result_id(result_id) if result_id else ""
        if result_id and not requested_result:
            raise ValueError("result_id must be a filename-like exact id")
        requested_stock = _text(stock_code)

        # Every source cache is scoped to one operation.  In particular, a
        # caller may reuse this service after a producer append; returning a
        # prior in-memory JSONL/evidence/receipt row would otherwise make the
        # before/after manifest describe bytes that were not actually used.
        self.recommendation_source.reset()
        self.journal_source.reset()
        self.journal_source.set_scope(resolved_scope)
        self.evidence_source.reset()
        self.evidence_source.set_scope(resolved_scope)
        if self.receipt_source is not None:
            self.receipt_source.reset()
        self._last_projection_objects.clear()

        diagnostics: list[str] = []
        self._pending_diagnostics.clear()
        # Establish the baseline before opening any source content.  Directory
        # inventories are path-only here; receipt JSON and recommendation
        # metadata are intentionally not read until this baseline exists.
        source_paths = (
            set(
                self.recommendation_source.candidate_paths_for_result_ids(
                    (requested_result,)
                )
            )
            if requested_result
            else set(self.recommendation_source.inventory_paths())
        )
        source_paths.update(self.journal_source.paths_for_fingerprint())
        source_paths.update(self.evidence_source.paths_for_fingerprint())
        if requested_result and self.canonical_runs_dir is not None:
            source_paths.update(self._canonical_paths_for_result(requested_result))
        if self.receipt_source is not None:
            source_paths.update(self.receipt_source.candidate_paths())
        before = self._capture_sources(source_paths)
        # Scan the complete JSONL stream for malformed/non-object lines after
        # the baseline.  This integrity check is separate from the exact
        # action/ACK bound: unrelated history may be physically truncated for
        # the broad inventory while the requested exact query remains complete.
        self.journal_source.scan_integrity()

        if requested_result:
            read_model = self.read_canonical_execution_exact(requested_result)
            if read_model is not None:
                return self._inspect_canonical_execution(
                    read_model=read_model,
                    scope_id=resolved_scope,
                    evaluated_as_of=resolved_as_of,
                    evaluation_cutoff_at=resolved_cutoff,
                    requested_stock=requested_stock,
                    fit_artifact=fit_artifact,
                    source_paths=source_paths,
                    before=before,
                )

        result_ids = list(
            self.recommendation_source.list_result_ids(
                report_truncation=not bool(requested_result)
            )
        )
        inventory = dict(self.recommendation_source.inventory_summary())
        if requested_result:
            result_ids = [requested_result]
            inventory.update(
                {
                    "selection_mode": "explicit_result_id",
                    "selected_result_ids": [requested_result],
                    "selected_result_count": 1,
                    "excluded_result_count": max(
                        0,
                        int(inventory.get("available_result_count", 0)) - 1,
                    ),
                    "truncated": False,
                    "exclusion_reason": "explicit_result_id_filter",
                }
            )
        else:
            inventory["selection_mode"] = "bounded_inventory"
        if not result_ids:
            diagnostics.append("recommendation_result_inventory_empty")

        # Load metadata after the baseline, then fingerprint any declared data
        # path before opening its JSON.  The metadata DB itself remains in the
        # baseline and is checked again after all reads.
        metadata_by_result: dict[str, Mapping[str, Any] | None] = {}
        metadata_rows: list[Mapping[str, Any]] = []
        for current_result_id in result_ids:
            metadata = self.recommendation_source.metadata_for(current_result_id)
            metadata_by_result[current_result_id] = metadata
            if metadata is not None:
                metadata_rows.append(dict(metadata))
        source_paths.update(
            self.recommendation_source.paths_for_results(tuple(result_ids))
        )
        self._capture_new_source_baselines(before, source_paths)

        if not self.evidence_source.db_path.is_file():
            diagnostics.append("evidence_database_missing")
        if not self.journal_source.path.is_file():
            diagnostics.append("journal_jsonl_missing")

        raw_results: dict[str, Mapping[str, Any]] = {}
        candidate_codes: dict[str, tuple[str, ...]] = {}
        candidate_inventory: dict[str, Mapping[str, Any]] = {}
        for current_result_id in result_ids:
            raw = self.recommendation_source.read_result(current_result_id)
            if raw is None:
                diagnostics.append(f"recommendation_result_unavailable:{current_result_id}")
                continue
            raw_results[current_result_id] = raw
            codes, code_diagnostics = self._candidate_stock_codes(raw, current_result_id)
            diagnostics.extend(code_diagnostics)
            bounded_codes, inventory_row = self._bound_candidate_inventory(
                codes,
                result_id=current_result_id,
                requested_stock_code=requested_stock,
            )
            candidate_codes[current_result_id] = bounded_codes
            candidate_inventory[current_result_id] = inventory_row
            if not bounded_codes:
                diagnostics.append(
                    f"recommendation_candidate_scope_empty:{current_result_id}"
                )
        diagnostics.extend(self._pending_diagnostics)

        # A receipt path can be declared inside the already-read result.  It
        # is still baseline-fingerprinted before the projection opens it.
        for raw in raw_results.values():
            source_paths.update(self._declared_receipt_paths(raw))
        self._capture_new_source_baselines(before, source_paths)

        projection_objects: list[tuple[str, str, PersonalizationProjectionResult, Mapping[str, Any] | None]] = []
        projection_rows: list[dict[str, Any]] = []
        for current_result_id in result_ids:
            raw = raw_results.get(current_result_id)
            if raw is None:
                continue
            metadata = metadata_by_result.get(current_result_id)
            for current_stock_code in candidate_codes.get(current_result_id, ()):
                projection = self.projection_service.build_for_candidate(
                    result_id=current_result_id,
                    stock_code=current_stock_code,
                    personalization_scope_id=resolved_scope,
                    evaluated_as_of=resolved_as_of,
                    evaluation_cutoff_at=resolved_cutoff,
                    result=raw,
                )
                projection_objects.append(
                    (current_result_id, current_stock_code, projection, metadata)
                )
                self._last_projection_objects[
                    (current_result_id, current_stock_code)
                ] = projection
                projection_rows.append(
                    {
                        "result_id": current_result_id,
                        "stock_code": current_stock_code,
                        "recommendation_metadata": dict(metadata or {}),
                        "projection": projection.to_dict(),
                        "source_consistency_status": "unverified_until_read_complete",
                    }
                )

        candidate_evaluation_rows: list[PersonalizationEvaluationRow] = []
        excluded_reason_counts: Counter[str] = Counter()
        denominators = self._empty_denominators()
        for result_key, stock_key, projection, _metadata in projection_objects:
            self._count_projection_denominators(denominators, projection)
            if projection.status != "linked_prediction":
                reason = self._projection_exclusion_reason(projection)
                excluded_reason_counts[reason] += 1
                diagnostics.append(f"{reason}:{result_key}:{stock_key}")
                continue
            row, row_reasons = self._evaluation_row_from_projection(
                projection,
                resolved_as_of=resolved_as_of,
                evaluation_cutoff_at=resolved_cutoff,
            )
            if row is None:
                for reason in row_reasons:
                    excluded_reason_counts[reason] += 1
                    diagnostics.append(f"{reason}:{result_key}:{stock_key}")
                continue
            candidate_evaluation_rows.append(row)

        if self.receipt_source is not None:
            # Include files discovered while scanning after the operation's
            # initial path inventory.  _pair_fingerprints treats a new path as
            # missing-before, so a concurrently-created receipt invalidates
            # the read instead of looking identical to its after-state.
            source_paths.update(self.receipt_source.paths_for_fingerprint())
        # Do the same for recommendation JSON inventory.  A newly-written run
        # must not silently appear after the bounded selection while this
        # report is being assembled.
        if requested_result:
            source_paths.update(
                self.recommendation_source.candidate_paths_for_result_ids(
                    (requested_result,)
                )
            )
        else:
            source_paths.update(self.recommendation_source.inventory_paths())
        after = self._capture_sources(source_paths)
        source_fingerprints, source_unchanged = self._pair_fingerprints(before, after)
        if not source_unchanged:
            diagnostics.append("source_bytes_or_mtime_changed_during_read")
        diagnostics.extend(self.recommendation_source.diagnostics)
        diagnostics.extend(self.journal_source.diagnostics)
        diagnostics.extend(self.evidence_source.diagnostics)
        if self.receipt_source is not None:
            diagnostics.extend(self.receipt_source.diagnostics)
        diagnostics = list(dict.fromkeys(diagnostics))

        source_consistency_status = "verified" if source_unchanged else "invalidated"
        source_completeness_status = self.journal_source.completeness_status
        inventory["journal"] = dict(self.journal_source.inventory_summary())
        if source_completeness_status != "verified":
            diagnostics.append("journal_source_completeness_incomplete")
        evaluation_rows: list[PersonalizationEvaluationRow]
        evaluation: PersonalizationCalibrationEvaluation | None = None
        if source_unchanged and source_completeness_status == "verified":
            evaluation_rows = candidate_evaluation_rows
            for row in evaluation_rows:
                denominators["outcome_ready_count"] += 1
            denominators["evaluation_row_count"] = len(evaluation_rows)
            if fit_artifact is None:
                diagnostics.append("fit_artifact_missing:evaluation_not_run")
            else:
                try:
                    evaluation = PersonalizationCalibrationEvaluator().evaluate(
                        fit_artifact,
                        evaluation_rows,
                        evaluated_as_of=resolved_as_of,
                        evaluation_cutoff_at=resolved_cutoff,
                    )
                except Exception as exc:  # noqa: BLE001 - report the read diagnostic
                    diagnostics.append(f"evaluation_failed:{type(exc).__name__}")
        elif not source_unchanged:
            # The bytes behind any projection are no longer provably the bytes
            # that were read.  Do not expose a ready denominator, evaluation
            # row, or evaluator status from that mixed read.
            evaluation_rows = []
            denominators = self._empty_denominators()
            denominators["source_consistency_invalidated_count"] = 1
            diagnostics.append("evaluation_not_run:source_consistency_invalidated")
            for item in projection_rows:
                item["source_consistency_status"] = source_consistency_status
        else:
            # Bytes are stable, but a bounded exact Journal query did not
            # establish the complete action/ACK history.  Keep projection
            # diagnostics visible while withholding evaluation denominators;
            # an unknown suffix must not become a false not_recorded state.
            evaluation_rows = []
            denominators["source_completeness_incomplete_count"] = 1
            if fit_artifact is None:
                diagnostics.append("fit_artifact_missing:evaluation_not_run")
            diagnostics.append("evaluation_not_run:source_completeness_incomplete")

        if source_unchanged:
            for item in projection_rows:
                item["source_consistency_status"] = source_consistency_status
        cohort = self._cohort_summary(
            resolved_scope,
            projection_objects,
            evaluation_rows,
            excluded_reason_counts,
            source_consistency_status=source_consistency_status,
            source_completeness_status=source_completeness_status,
        )
        manifest_payload = [
            {
                "path": item["path"],
                "before": item["before"],
            }
            for item in source_fingerprints
        ]
        source_manifest_hash = canonical_payload_hash(manifest_payload)
        return PersonalizationReadReport(
            scope_id=resolved_scope,
            evaluated_as_of=resolved_as_of,
            evaluation_cutoff_at=resolved_cutoff,
            source_manifest_hash=source_manifest_hash,
            source_bytes_unchanged=source_unchanged,
            source_consistency_status=source_consistency_status,
            source_completeness_status=source_completeness_status,
            source_fingerprints=tuple(source_fingerprints),
            recommendation_metadata=tuple(metadata_rows),
            projections=tuple(projection_rows),
            evaluation_rows=tuple(row.to_dict() for row in evaluation_rows),
            denominators=dict(denominators),
            cohort=cohort,
            inventory=inventory,
            candidate_inventory=candidate_inventory,
            diagnostics=tuple(diagnostics),
            evaluation=evaluation,
        )

    def _canonical_paths_for_result(self, result_id: str) -> set[Path]:
        if self.canonical_runs_dir is None:
            return set()
        artifact_name = ResultArtifactStore.artifact_name_for(result_id)
        return {
            self.canonical_runs_dir / "recommendation_runs.db",
            self.canonical_runs_dir / "execution_artifacts" / artifact_name,
        }

    def _inspect_canonical_execution(
        self,
        *,
        read_model: RecommendationExecutionReadModel,
        scope_id: str,
        evaluated_as_of: str,
        evaluation_cutoff_at: str | None,
        requested_stock: str,
        fit_artifact: PersonalizationCalibrationFitArtifact | None,
        source_paths: set[Path],
        before: dict[str, PersonalizationSourceFingerprint],
    ) -> PersonalizationReadReport:
        execution = read_model.execution
        if execution is None:
            raise ValueError("canonical read path requires a typed execution")
        result_id = read_model.result_id
        inventory: dict[str, Any] = {
            "selection_mode": "explicit_result_id",
            "selected_result_ids": [result_id],
            "selected_result_count": 1,
            "excluded_result_count": 0,
            "truncated": False,
            "exclusion_reason": "explicit_result_id_filter",
            "canonical_execution_exact": True,
        }
        metadata = {
            "result_id": result_id,
            "result_name": read_model.label,
            "notes": read_model.notes,
            "created_at": (
                read_model.persisted_at.isoformat(timespec="microseconds")
                if read_model.persisted_at is not None
                else None
            ),
            "payload_hash": read_model.payload_hash,
            "artifact_location": read_model.artifact_location,
            "integrity_basis": read_model.integrity_basis,
        }
        metadata_rows: tuple[Mapping[str, Any], ...] = (metadata,)
        source_paths.add(self.evidence_source.db_path)
        source_paths.add(self.journal_source.path)
        capture_events = tuple(
            event
            for event in execution.events
            if event.event_type == "personalization_delivery_capture"
        )
        for event in capture_events:
            details = event.details
            raw_captures = details.get("captures") if isinstance(details, Mapping) else None
            if isinstance(raw_captures, (list, tuple)):
                for row in raw_captures:
                    if not isinstance(row, Mapping):
                        continue
                    receipt_path = _text(row.get("projection_receipt_path"))
                    if receipt_path:
                        source_paths.add(Path(receipt_path).expanduser().resolve())
        self._capture_new_source_baselines(before, source_paths)

        if not self.evidence_source.db_path.is_file():
            self._pending_diagnostics.append("evidence_database_missing")
        if not self.journal_source.path.is_file():
            self._pending_diagnostics.append("journal_jsonl_missing")
        codes = tuple(item.stock_code for item in execution.items)
        bounded_codes, candidate_inventory_row = self._bound_candidate_inventory(
            codes,
            result_id=result_id,
            requested_stock_code=requested_stock,
        )
        candidate_inventory: dict[str, Mapping[str, Any]] = {
            result_id: candidate_inventory_row
        }
        diagnostics = list(read_model.diagnostics)
        diagnostics.extend(self._pending_diagnostics)
        if not bounded_codes:
            diagnostics.append(f"recommendation_candidate_scope_empty:{result_id}")

        projection_objects: list[
            tuple[str, str, PersonalizationProjectionResult, Mapping[str, Any] | None]
        ] = []
        projection_rows: list[dict[str, Any]] = []
        for stock_code in bounded_codes:
            projection = self.projection_service.build_for_execution(
                read_model=read_model,
                stock_code=stock_code,
                personalization_scope_id=scope_id,
                evaluated_as_of=evaluated_as_of,
                evaluation_cutoff_at=evaluation_cutoff_at,
            )
            projection_objects.append((result_id, stock_code, projection, metadata))
            self._last_projection_objects[(result_id, stock_code)] = projection
            projection_rows.append(
                {
                    "result_id": result_id,
                    "stock_code": stock_code,
                    "recommendation_metadata": dict(metadata),
                    "projection": projection.to_dict(),
                    "source_consistency_status": "unverified_until_read_complete",
                }
            )

        candidate_evaluation_rows: list[PersonalizationEvaluationRow] = []
        excluded_reason_counts: Counter[str] = Counter()
        denominators = self._empty_denominators()
        for result_key, stock_key, projection, _metadata in projection_objects:
            self._count_projection_denominators(denominators, projection)
            if projection.status != "linked_prediction":
                reason = self._projection_exclusion_reason(projection)
                excluded_reason_counts[reason] += 1
                diagnostics.append(f"{reason}:{result_key}:{stock_key}")
                continue
            row, row_reasons = self._evaluation_row_from_projection(
                projection,
                resolved_as_of=evaluated_as_of,
                evaluation_cutoff_at=evaluation_cutoff_at,
            )
            if row is None:
                for reason in row_reasons:
                    excluded_reason_counts[reason] += 1
                    diagnostics.append(f"{reason}:{result_key}:{stock_key}")
                continue
            candidate_evaluation_rows.append(row)

        if self.receipt_source is not None:
            source_paths.update(self.receipt_source.paths_for_fingerprint())
        after = self._capture_sources(source_paths)
        source_fingerprints, source_unchanged = self._pair_fingerprints(before, after)
        if not source_unchanged:
            diagnostics.append("source_bytes_or_mtime_changed_during_read")
        diagnostics.extend(self.journal_source.diagnostics)
        diagnostics.extend(self.evidence_source.diagnostics)
        if self.receipt_source is not None:
            diagnostics.extend(self.receipt_source.diagnostics)
        diagnostics = list(dict.fromkeys(diagnostics))

        source_consistency_status = "verified" if source_unchanged else "invalidated"
        source_completeness_status = self.journal_source.completeness_status
        inventory["journal"] = dict(self.journal_source.inventory_summary())
        if source_completeness_status != "verified":
            diagnostics.append("journal_source_completeness_incomplete")
        evaluation_rows: list[PersonalizationEvaluationRow]
        evaluation: PersonalizationCalibrationEvaluation | None = None
        if source_unchanged and source_completeness_status == "verified":
            evaluation_rows = candidate_evaluation_rows
            denominators["outcome_ready_count"] += len(evaluation_rows)
            denominators["evaluation_row_count"] = len(evaluation_rows)
            if fit_artifact is None:
                diagnostics.append("fit_artifact_missing:evaluation_not_run")
            else:
                try:
                    evaluation = PersonalizationCalibrationEvaluator().evaluate(
                        fit_artifact,
                        evaluation_rows,
                        evaluated_as_of=evaluated_as_of,
                        evaluation_cutoff_at=evaluation_cutoff_at,
                    )
                except Exception as exc:  # noqa: BLE001 - report the read diagnostic
                    diagnostics.append(f"evaluation_failed:{type(exc).__name__}")
        elif not source_unchanged:
            evaluation_rows = []
            denominators = self._empty_denominators()
            denominators["source_consistency_invalidated_count"] = 1
            diagnostics.append("evaluation_not_run:source_consistency_invalidated")
        else:
            evaluation_rows = []
            denominators["source_completeness_incomplete_count"] = 1
            diagnostics.append("evaluation_not_run:source_completeness_incomplete")
        for item in projection_rows:
            item["source_consistency_status"] = source_consistency_status

        cohort = self._cohort_summary(
            scope_id,
            projection_objects,
            evaluation_rows,
            excluded_reason_counts,
            source_consistency_status=source_consistency_status,
            source_completeness_status=source_completeness_status,
        )
        source_manifest_hash = canonical_payload_hash(
            [{"path": item["path"], "before": item["before"]} for item in source_fingerprints]
        )
        return PersonalizationReadReport(
            scope_id=scope_id,
            evaluated_as_of=evaluated_as_of,
            evaluation_cutoff_at=evaluation_cutoff_at,
            source_manifest_hash=source_manifest_hash,
            source_bytes_unchanged=source_unchanged,
            source_consistency_status=source_consistency_status,
            source_completeness_status=source_completeness_status,
            source_fingerprints=tuple(source_fingerprints),
            recommendation_metadata=metadata_rows,
            projections=tuple(projection_rows),
            evaluation_rows=tuple(row.to_dict() for row in evaluation_rows),
            denominators=dict(denominators),
            cohort=cohort,
            inventory=inventory,
            candidate_inventory=candidate_inventory,
            diagnostics=tuple(dict.fromkeys(diagnostics)),
            evaluation=evaluation,
        )

    def projection_for_last_read(
        self,
        *,
        result_id: str,
        stock_code: str,
    ) -> PersonalizationProjectionResult | None:
        """Return the exact projection object produced by the last read.

        This is a read-boundary handoff for explicitly requested write
        commands.  The caller must still require a verified, unchanged
        ``PersonalizationReadReport`` before handing this object to a writer;
        the method never reads or writes a source by itself.
        """

        return self._last_projection_objects.get(
            (_safe_result_id(result_id), _text(stock_code))
        )

    def _candidate_stock_codes(
        self,
        result: Mapping[str, Any],
        result_id: str,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        raw_rows = result.get("recommendations")
        if not isinstance(raw_rows, list):
            return (), (f"recommendation_candidates_missing:{result_id}",)
        codes: list[str] = []
        diagnostics: list[str] = []
        for index, raw in enumerate(raw_rows):
            if not isinstance(raw, Mapping):
                diagnostics.append(f"recommendation_candidate_invalid:{result_id}:{index}")
                continue
            values = _explicit_stock_values(raw)
            if len(values) > 1:
                diagnostics.append(f"recommendation_candidate_stock_alias_conflict:{result_id}:{index}")
                continue
            if not values:
                diagnostics.append(f"recommendation_candidate_stock_missing:{result_id}:{index}")
                continue
            codes.append(values[0])
        return tuple(dict.fromkeys(codes)), tuple(diagnostics)

    def _bound_candidate_inventory(
        self,
        codes: Sequence[str],
        *,
        result_id: str,
        requested_stock_code: str,
    ) -> tuple[tuple[str, ...], Mapping[str, Any]]:
        """Apply the candidate bound with an explicit, inspectable denominator."""

        unique_codes = tuple(dict.fromkeys(str(code) for code in codes if _text(code)))
        eligible = tuple(
            code
            for code in unique_codes
            if not requested_stock_code or code == requested_stock_code
        )
        selected = eligible[: self.max_candidates_per_result]
        excluded = eligible[self.max_candidates_per_result :]
        truncated = bool(excluded)
        if truncated:
            self._candidate_inventory_diagnostic(
                result_id,
                len(eligible),
            )
        return selected, {
            "result_id": result_id,
            "selection_mode": (
                "explicit_stock_code"
                if requested_stock_code
                else "bounded_source_order"
            ),
            "requested_stock_code": requested_stock_code,
            "available_candidate_count": len(eligible),
            "selected_candidate_count": len(selected),
            "excluded_candidate_count": len(excluded),
            "selected_stock_codes": list(selected),
            "excluded_stock_codes_sample": list(excluded[:20]),
            "truncated": truncated,
            "limit": self.max_candidates_per_result,
            "selection_order": "recommendation_source_order",
            "exclusion_reason": (
                "max_candidates_per_result_bound" if excluded else "none"
            ),
            "filter_excluded_candidate_count": len(unique_codes) - len(eligible),
        }

    def _candidate_inventory_diagnostic(
        self,
        result_id: str,
        available_count: int,
    ) -> None:
        # Keep this diagnostic on the service's next report without adding a
        # second mutable diagnostic channel to the source adapters.
        self._pending_diagnostics.append(
            "recommendation_candidate_inventory_truncated:"
            f"{result_id}:limit={self.max_candidates_per_result}:available={available_count}"
        )

    @staticmethod
    def _declared_receipt_paths(result: Mapping[str, Any]) -> tuple[Path, ...]:
        paths: list[Path] = []
        context = result.get("run_context")
        context_map = context if isinstance(context, Mapping) else {}
        candidates: list[Any] = [
            context_map.get("calibration_projection_receipt_path"),
            context_map.get("calibration_projection_receipt"),
        ]
        captures = context_map.get("personalization_delivery_captures")
        if isinstance(captures, list):
            candidates.extend(captures)
        for candidate in candidates:
            if isinstance(candidate, Mapping):
                candidate = candidate.get("projection_receipt_path") or candidate.get("path")
            text = _text(candidate)
            if text:
                paths.append(Path(text).expanduser().resolve())
        return tuple(paths)

    @staticmethod
    def _capture_sources(paths: set[Path]) -> dict[str, PersonalizationSourceFingerprint]:
        return {
            str(path.expanduser().resolve()): PersonalizationSourceFingerprint.capture(path)
            for path in sorted(paths, key=lambda item: str(item))
        }

    @staticmethod
    def _capture_new_source_baselines(
        before: dict[str, PersonalizationSourceFingerprint],
        paths: set[Path],
    ) -> None:
        """Fingerprint newly discovered paths before their first content read."""

        for path in sorted(paths, key=lambda item: str(item)):
            key = str(path.expanduser().resolve())
            if key not in before:
                before[key] = PersonalizationSourceFingerprint.capture(path)

    @staticmethod
    def _pair_fingerprints(
        before: Mapping[str, PersonalizationSourceFingerprint],
        after: Mapping[str, PersonalizationSourceFingerprint],
    ) -> tuple[list[Mapping[str, Any]], bool]:
        rows: list[Mapping[str, Any]] = []
        unchanged = True
        for path in sorted(set(before) | set(after)):
            # A path discovered only after reading must compare against an
            # explicit missing-before marker.  Capturing it at this point
            # would make a newly-created file compare equal to itself and
            # silently hide a concurrent receipt/data append.
            first = before.get(path) or PersonalizationSourceFingerprint.missing(path)
            second = after.get(path) or PersonalizationSourceFingerprint.missing(path)
            same = first.same_bytes_and_mtime(second)
            unchanged = unchanged and same
            rows.append(
                {
                    "path": path,
                    "before": first.to_dict(),
                    "after": second.to_dict(),
                    "unchanged": same,
                }
            )
        return rows, unchanged

    @staticmethod
    def _empty_denominators() -> dict[str, int]:
        keys = (
            "prediction_available_count",
            "population_only_count",
            "not_delivered_count",
            "prediction_unavailable_count",
            "prediction_duplicate_exact_count",
            "prediction_duplicate_conflict_count",
            "action_recorded_count",
            "action_not_recorded_count",
            "action_conflict_count",
            "action_accepted_count",
            "action_skipped_count",
            "action_watch_count",
            "action_held_count",
            "action_buy_count",
            "action_sell_count",
            "action_review_scheduled_count",
            "outcome_ready_count",
            "outcome_pending_count",
            "outcome_matured_missing_count",
            "outcome_invalid_count",
            "outcome_conflict_count",
            "outcome_duplicate_exact_count",
            "outcome_duplicate_conflict_count",
            "outcome_missing_count",
            "natural_forward_count",
            "paper_research_count",
            "user_declared_context_count",
            "historical_replay_count",
            "synthetic_fixture_count",
            "action_utility_count",
            "evaluation_row_count",
            "source_consistency_invalidated_count",
            "source_completeness_incomplete_count",
        )
        return {key: 0 for key in keys}

    @staticmethod
    def _count_projection_denominators(
        denominators: dict[str, int],
        projection: PersonalizationProjectionResult,
    ) -> None:
        if projection.status == "linked_prediction":
            if projection.delivery_status == "delivered":
                denominators["prediction_available_count"] += 1
            if projection.action_state == "recorded":
                denominators["action_recorded_count"] += 1
            elif projection.action_state == "conflict":
                denominators["action_conflict_count"] += 1
            else:
                denominators["action_not_recorded_count"] += 1
            # ``not_recorded`` is a contract state, not a recorded action.
            # Counting it again here would double-count the action denominator
            # (once by action_state and once by the action label).
            action_key = f"action_{projection.action}_count"
            if projection.action_state == "recorded" and projection.action in PERSONALIZATION_ACTIONS:
                denominators[action_key] = denominators.get(action_key, 0) + 1
            for outcome in projection.outcomes:
                tier = _text(outcome.get("outcome_tier"))
                if tier in PERSONALIZATION_OUTCOME_TIERS:
                    tier_key = f"{tier}_count"
                    denominators[tier_key] = denominators.get(tier_key, 0) + 1
            if PersonalizationReadService._projection_utility_eligible(projection):
                denominators["action_utility_count"] += 1
            if projection.outcome_status == "pending_maturity":
                denominators["outcome_pending_count"] += 1
            elif projection.outcome_status == "matured_missing":
                denominators["outcome_matured_missing_count"] += 1
            elif projection.outcome_status == "invalid":
                denominators["outcome_invalid_count"] += 1
            elif projection.outcome_status == "conflict":
                denominators["outcome_conflict_count"] += 1
            elif projection.outcome_status == "not_applicable":
                denominators["outcome_missing_count"] += 1
            elif projection.outcome_status == "duplicate_exact":
                denominators["outcome_duplicate_exact_count"] += 1
            elif projection.outcome_status == "ready":
                # The row contract is verified separately below; only the
                # fully built EvaluationRow reaches outcome_ready_count.
                pass
        elif projection.status == "population_only":
            denominators["population_only_count"] += 1
        elif projection.status == "not_delivered":
            denominators["not_delivered_count"] += 1
        elif projection.status == "duplicate_exact":
            denominators["prediction_duplicate_exact_count"] += 1
        elif projection.status == "duplicate_conflict":
            denominators["prediction_duplicate_conflict_count"] += 1
        else:
            denominators["prediction_unavailable_count"] += 1

    @staticmethod
    def _projection_exclusion_reason(projection: PersonalizationProjectionResult) -> str:
        if projection.status == "population_only":
            if projection.scope is None:
                return "scope_missing_population_only"
            if any("receipt" in warning for warning in projection.warnings):
                return "projection_receipt_missing_or_invalid"
            if any("delivery" in warning for warning in projection.warnings):
                return "delivery_missing_population_only"
            return "scope_unverified_population_only"
        if projection.status == "not_delivered":
            return "prediction_not_delivered"
        if projection.status == "duplicate_exact":
            return "prediction_duplicate_exact"
        if projection.status == "duplicate_conflict":
            return "prediction_duplicate_conflict"
        return "prediction_unavailable"

    def _evaluation_row_from_projection(
        self,
        projection: PersonalizationProjectionResult,
        *,
        resolved_as_of: str,
        evaluation_cutoff_at: str | None,
    ) -> tuple[PersonalizationEvaluationRow | None, tuple[str, ...]]:
        reasons: list[str] = []
        if projection.late_delivery:
            # Delivery after an explicit human/evaluation anchor is visible
            # in the projection, but cannot receive natural calibration
            # credit in the evaluation denominator.
            reasons.append("late_delivery_no_natural_credit")
        if projection.duplicate_exact_count:
            reasons.append("outcome_duplicate_exact_excluded")
        if projection.duplicate_conflict_count:
            reasons.append("outcome_duplicate_conflict_excluded")
        if projection.outcome_status != "ready":
            reasons.append(f"outcome_{projection.outcome_status}")
        if len(projection.outcomes) != 1:
            reasons.append("outcome_exact_row_missing_or_multiple")
            return None, tuple(dict.fromkeys(reasons))
        outcome = dict(projection.outcomes[0])
        outcome_status = _text(outcome.get("outcome_status"))
        if outcome_status != "ready":
            reasons.append(f"outcome_{outcome_status or 'status_missing'}")
        tier = _text(outcome.get("outcome_tier"))
        if not tier:
            reasons.append("outcome_tier_missing")
        elif tier not in PERSONALIZATION_OUTCOME_TIERS:
            reasons.append("outcome_tier_invalid")
        label_available_date = _text(outcome.get("label_available_date"))
        if not label_available_date:
            reasons.append("label_availability_missing")
        else:
            try:
                label_available_date = _iso_date(
                    label_available_date,
                    "label_available_date",
                )
            except ValueError:
                reasons.append("label_availability_invalid")
        raw_label = outcome.get("label")
        if isinstance(raw_label, bool) or raw_label not in (0, 1):
            reasons.append("label_missing_or_invalid")
            label = None
        else:
            label = int(raw_label)
        outcome_recorded_at = _text(
            outcome.get("outcome_recorded_at")
            or outcome.get("recorded_at")
            or outcome.get("calculated_at")
        )
        if not outcome_recorded_at:
            reasons.append("outcome_recorded_at_missing")
        event_id = _text(outcome.get("event_id"))
        outcome_id = _text(outcome.get("outcome_id"))
        if not event_id and not outcome_id:
            reasons.append("outcome_identity_missing")
        prediction = dict(projection.prediction)
        population_probability = _int_or_none(
            prediction.get("population_probability_bp")
        )
        if prediction.get("population_probability_bp") not in (None, "") and population_probability is None:
            reasons.append("population_probability_invalid")
        if prediction.get("population_probability_bp") in (None, ""):
            reasons.append("population_probability_missing")
        horizon = _int_or_none(prediction.get("horizon_days"))
        if horizon is None or horizon <= 0:
            reasons.append("prediction_horizon_missing_or_invalid")
            horizon = 1
        cost_hash = _text(prediction.get("cost_scenario_hash")) or None
        if cost_hash is None:
            reasons.append("cost_scenario_missing")
        label_contract = _text(prediction.get("label_contract_id"))
        return_basis = _text(prediction.get("return_basis"))
        if not label_contract:
            reasons.append("label_contract_missing")
        if not return_basis:
            reasons.append("return_basis_missing")
        if reasons:
            return None, tuple(dict.fromkeys(reasons))
        scope = projection.scope
        if scope is None:
            return None, ("scope_missing",)
        decision_date = projection.decision_date or _text(prediction.get("decision_date"))
        if not decision_date:
            return None, ("decision_date_missing",)
        window_days = _int_or_none(outcome.get("window_days"))
        if window_days is None:
            window_days = horizon
        try:
            row = PersonalizationEvaluationRow(
                prediction_id=_text(prediction.get("prediction_id")),
                scope_id=scope.scope_id,
                symbol=projection.stock_code,
                decision_date=decision_date,
                label_available_date=label_available_date,
                horizon_days=horizon,
                cost_scenario_hash=cost_hash,
                population_probability_bp=population_probability,
                label=label,
                label_available_at=(
                    _text(outcome.get("label_available_at")) or None
                ),
                outcome_recorded_at=outcome_recorded_at or None,
                outcome_tier=tier,
                action_state=projection.action_state,
                decision_at=scope.decision_at,
                available_at=scope.available_at,
                receipt_created_at=scope.receipt_created_at,
                captured_at=scope.captured_at,
                prediction_decision_at=(
                    projection.prediction_decision_at or scope.decision_at
                ),
                delivery_at=projection.delivery_at,
                human_decision_at=projection.human_decision_at,
                decision_day_block=decision_date,
                row_id=outcome_id or event_id,
                outcome_status="ready",
                delivery_status=projection.delivery_status,
                late_delivery=projection.late_delivery,
                source_result_id=projection.result_id,
                prediction_receipt_hash=_text(
                    prediction.get("projection_receipt_hash")
                ),
                model_id=_text(prediction.get("model_id")),
                dataset_id=_text(prediction.get("dataset_id")),
                dataset_hash=_text(prediction.get("dataset_hash")),
                cost_scenario_id=_text(outcome.get("cost_scenario_id")),
                cost_scenario_version=_text(outcome.get("cost_scenario_version")),
                universe_policy_hash=_text(prediction.get("universe_policy_hash")),
                label_contract_id=label_contract,
                return_basis=return_basis,
                source_id=_text(prediction.get("source_id")),
                prediction_receipt_schema_version=_text(
                    prediction.get("prediction_receipt_schema_version")
                ),
                statistical_id=_text(outcome.get("statistical_id")),
                outcome_id=outcome_id,
                event_id=event_id,
                window_days=window_days,
            )
        except (TypeError, ValueError) as exc:
            return None, (f"evaluation_row_invalid:{type(exc).__name__}",)
        cutoff = _optional_datetime(evaluation_cutoff_at, "evaluation_cutoff_at")
        label_at = _optional_datetime(row.label_available_at, "label_available_at")
        if label_at is None:
            return None, ("label_availability_timestamp_missing_or_invalid",)
        if label_at.astimezone(_MARKET_TIMEZONE).date() > date.fromisoformat(resolved_as_of):
            return None, ("label_pending_as_of",)
        if cutoff is not None and label_at > cutoff:
            return None, ("label_pending_cutoff",)
        return row, ()

    @staticmethod
    def _projection_utility_eligible(
        projection: PersonalizationProjectionResult,
    ) -> bool:
        """Count utility only when action and outcome explicitly support it."""

        if (
            projection.action_state != "recorded"
            or projection.outcome_status != "ready"
            or len(projection.outcomes) != 1
            or projection.late_delivery
        ):
            return False
        outcome = projection.outcomes[0]
        if outcome.get("utility_eligible") is not True:
            return False
        return _int_or_none(
            outcome.get("utility_return_bp")
            if outcome.get("utility_return_bp") not in (None, "")
            else outcome.get("net_return_bp")
        ) is not None

    @staticmethod
    def _cohort_summary(
        scope_id: str,
        projections: Sequence[
            tuple[str, str, PersonalizationProjectionResult, Mapping[str, Any] | None]
        ],
        evaluation_rows: Sequence[PersonalizationEvaluationRow],
        excluded_reason_counts: Counter[str],
        *,
        source_consistency_status: str,
        source_completeness_status: str,
    ) -> Mapping[str, Any]:
        linked = [item for item in projections if item[2].status == "linked_prediction"]
        contracts: dict[str, set[str]] = defaultdict(set)
        for _, _, projection, _ in linked:
            for key in (
                "prediction_id",
                "projection_receipt_hash",
                "horizon_days",
                "cost_scenario_hash",
                "label_contract_id",
                "return_basis",
                "universe_policy_hash",
            ):
                value = projection.prediction.get(key)
                if value not in (None, ""):
                    contracts[key].add(str(value))
        return {
            "scope_id": scope_id,
            "projection_count": len(projections),
            "linked_prediction_count": len(linked),
            "included_evaluation_row_count": len(evaluation_rows),
            "included_prediction_ids": [
                row.prediction_id for row in evaluation_rows
            ],
            "excluded_reason_counts": dict(excluded_reason_counts),
            "source_consistency_status": source_consistency_status,
            "source_completeness_status": source_completeness_status,
            "contract_values": {
                key: sorted(values) for key, values in sorted(contracts.items())
            },
            "cohort_status": (
                "source_changed_during_read"
                if source_consistency_status != "verified"
                else (
                    "source_incomplete"
                    if source_completeness_status != "verified"
                    else ("ready" if evaluation_rows else "pending_or_insufficient")
                )
            ),
        }


__all__ = [
    "DEFAULT_MAX_CANDIDATES_PER_RESULT",
    "DEFAULT_MAX_EVIDENCE_EVENTS",
    "DEFAULT_MAX_JOURNAL_ROWS",
    "DEFAULT_MAX_RESULTS",
    "PersonalizationReadReport",
    "PersonalizationReadService",
    "PersonalRecommendationChoiceReadEntry",
    "PersonalRecommendationChoiceReadReport",
    "PersonalizationSourceFingerprint",
    "ReadOnlyEvidenceSource",
    "ReadOnlyJournalRevisionSource",
    "ReadOnlyProjectionReceiptSource",
    "ReadOnlyRecommendationSource",
]
