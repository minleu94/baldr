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
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from app_module.personal_journal_paths import PersonalJournalPaths, validate_personal_journal_record
import sqlite3
import stat
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
from app_module.recommendation.queries import (
    RecommendationExecutionReadModel,
    _read_regular_file_no_follow,
)
from app_module.recommendation.personal_prediction_capture import (
    PERSONAL_FIXED_NULL_BENCHMARK_KIND,
    PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2,
    PERSONAL_PREDICTION_CAPTURE_SCHEMA_V3,
    read_personal_prediction_capture,
)
from app_module.recommendation.personal_use_policy import (
    PERSONAL_USE_POLICY_SCHEMA_V2,
)
from app_module.saved_recommendation_queries import build_recommendation_execution_queries
from app_module.recommendation.persistence import ExecutionArtifactIntegrityError
from data_module.result_artifact_store import ResultArtifactStore
from ml_module.recommendation_calibration_evidence import (
    verify_natural_maturity_session_proof,
)


PERSONALIZATION_READ_REPORT_SCHEMA_VERSION = "personalization-read-report.v1"
PERSONAL_MODEL_ASSESSMENT_SCHEMA_VERSION = "personal-model-assessment.v1"
_MARKET_TIMEZONE = ZoneInfo("Asia/Taipei")
DEFAULT_MAX_RESULTS = 100
DEFAULT_MAX_CANDIDATES_PER_RESULT = 100
DEFAULT_MAX_EVIDENCE_EVENTS = 500
DEFAULT_MAX_JOURNAL_ROWS = 50_000
DEFAULT_MAX_RECEIPT_FILES = 5_000
_SQLITE_READ_BIND_CHUNK_SIZE = 900
_MAX_PERSONAL_ASSESSMENT_JSON_BYTES = 16 * 1024 * 1024
_MAX_PERSONAL_OUTCOME_ROWS = 500


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


def _assessment_absolute_path(value: object, field_name: str) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError(f"{field_name} 必須是明確絕對路徑")
    path = Path(value).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name} 必須是正規絕對路徑")
    return Path(os.path.abspath(path))


def _assessment_normalized_path(value: object) -> str:
    path = _assessment_absolute_path(value, "source path")
    return os.path.normcase(os.path.normpath(str(path)))


def _assessment_unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object 含重複 key")
        result[key] = value
    return result


def _assessment_reject_json_constant(value: str) -> None:
    raise ValueError(f"JSON 含非法常數 {value}")


def _read_personal_assessment_json(
    path: Path,
    *,
    max_bytes: int,
    label: str,
) -> tuple[dict[str, Any], str]:
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("personal assessment JSON byte cap 必須是正整數")
    try:
        raw = _read_regular_file_no_follow(
            path,
            Path(path.anchor),
            max_bytes=max_bytes,
        )
    except (ExecutionArtifactIntegrityError, OSError, ValueError) as exc:
        raise ValueError(f"{label} 無法安全、有界且穩定讀取") from exc
    if len(raw) > max_bytes:
        raise ValueError(f"{label} 超過讀取大小上限")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_assessment_unique_pairs,
            parse_constant=_assessment_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} 不是有效 strict JSON") from exc
    if type(value) is not dict:
        raise ValueError(f"{label} 根節點必須是 JSON object")
    return value, "sha256:" + hashlib.sha256(raw).hexdigest()


def _stage_c_payload_hash(value: Mapping[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key != "payload_sha256"}
    try:
        encoded = (
            json.dumps(
                body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Stage C payload 不是可正規化 JSON") from exc
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _verify_personal_outcome_hashed_json(
    value: Mapping[str, Any], *, expected_schema: str
) -> str:
    declared = value.get("payload_sha256")
    if (
        value.get("schema_version") != expected_schema
        or type(declared) is not str
        or len(declared) != 71
        or not declared.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in declared[7:])
    ):
        raise ValueError("Stage C payload schema/hash 格式無效")
    actual = _stage_c_payload_hash(value)
    if declared != actual:
        raise ValueError("Stage C payload 自雜湊不符")
    return actual


def _assessment_nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise ValueError(f"{field_name} 必須是非負整數")
    return value


def _verify_personal_outcome_source_prices(
    *,
    source_database_path: object,
    expected_source_stat: Mapping[str, Any],
    start_date: str,
    end_date: str,
    expected_returns_bp: Mapping[str, int],
) -> str:
    """以同一個 user-declared SQLite 來源重驗成熟 close-to-close 標籤。

    查詢只讀兩個明確日期，每個 symbol 最多取三列以偵測重複；若來源沒有
    可搜尋的 symbol/date 索引、來源已變更或任何列不能唯一綁定，就拒絕成熟讀回。
    此檢查是指定來源內的一致性驗證，不表示官方 PIT 或 publication-time 已證實。
    """

    if not isinstance(expected_source_stat, Mapping) or set(expected_source_stat) != {
        "size",
        "mtime_ns",
        "device",
        "inode",
    }:
        raise ValueError("Stage C market source stat 欄位無效")
    expected_stat: dict[str, int] = {}
    for key in ("size", "mtime_ns", "device", "inode"):
        value = expected_source_stat.get(key)
        if isinstance(value, bool) or type(value) is not int or value < 0:
            raise ValueError("Stage C market source stat 值無效")
        expected_stat[key] = value

    source_path = _assessment_absolute_path(source_database_path, "market source DB")
    _assessment_require_plain_file(source_path)
    _assessment_require_no_sqlite_sidecars(source_path)
    if _assessment_source_file_stat(source_path) != expected_stat:
        raise ValueError("Stage C market source changed since its evaluation snapshot")

    start = _iso_date(start_date, "outcome return start date")
    end = _iso_date(end_date, "outcome return end date")
    if end <= start:
        raise ValueError("Stage C market source return window is invalid")
    symbols = tuple(sorted(expected_returns_bp))
    if not symbols or len(symbols) > _MAX_PERSONAL_OUTCOME_ROWS:
        raise ValueError("Stage C market source row count exceeds the readback bound")
    if any(type(symbol) is not str or not symbol or len(symbol) > 32 for symbol in symbols):
        raise ValueError("Stage C market source symbol identity is invalid")
    if any(
        isinstance(value, bool) or type(value) is not int
        for value in expected_returns_bp.values()
    ):
        raise ValueError("Stage C stock return labels must use integer basis points")

    uri = source_path.resolve(strict=True).as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    except (OSError, sqlite3.Error) as exc:
        raise ValueError("Stage C market source cannot be opened read-only") from exc
    observed_rows: dict[tuple[str, str], tuple[str, Decimal]] = {}
    row_fingerprint: list[dict[str, str]] = []
    try:
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA query_only").fetchone() != (1,):
            raise ValueError("Stage C market source query-only mode is unavailable")
        connection.execute("BEGIN")
        data_version_before_row = connection.execute("PRAGMA data_version").fetchone()
        if (
            data_version_before_row is None
            or len(data_version_before_row) != 1
            or isinstance(data_version_before_row[0], bool)
            or type(data_version_before_row[0]) is not int
        ):
            raise ValueError("Stage C market source data version is unavailable")
        table_row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_prices'"
        ).fetchone()
        if table_row is None:
            raise ValueError("Stage C market source daily_prices table is missing")
        columns = {
            str(row[1])
            for row in connection.execute('PRAGMA table_info("daily_prices")')
        }
        if not {"日期", "證券代號", "收盤價"}.issubset(columns):
            raise ValueError("Stage C market source daily_prices schema is incomplete")

        compact_dates = (date.fromisoformat(start).strftime("%Y%m%d"), date.fromisoformat(end).strftime("%Y%m%d"))
        query_plan = connection.execute(
            'EXPLAIN QUERY PLAN SELECT "證券代號", "日期", "收盤價" '
            'FROM daily_prices WHERE "證券代號"=? AND "日期" IN (?, ?) LIMIT 3',
            (symbols[0], *compact_dates),
        ).fetchall()
        if not any("SEARCH" in str(row[3]).upper() for row in query_plan):
            raise ValueError("Stage C market source price lookup is not indexed")

        per_symbol_query = (
            'SELECT substr(CAST("證券代號" AS TEXT), 1, 33), '
            'length(CAST("證券代號" AS TEXT)), '
            'substr(CAST("日期" AS TEXT), 1, 11), length(CAST("日期" AS TEXT)), '
            'CASE WHEN length(CAST("收盤價" AS TEXT)) <= 128 '
            'THEN CAST("收盤價" AS TEXT) ELSE NULL END, '
            'length(CAST("收盤價" AS TEXT)) '
            'FROM daily_prices WHERE "證券代號"=? AND "日期" IN (?, ?) '
            'ORDER BY "日期" LIMIT 3'
        )
        for symbol in symbols:
            rows = connection.execute(
                per_symbol_query,
                (symbol, *compact_dates),
            ).fetchall()
            for row in rows:
                raw_symbol, symbol_length, raw_day, day_length, close_text, close_length = row
                if (
                    type(symbol_length) is not int
                    or symbol_length > 32
                    or type(day_length) is not int
                    or day_length > 10
                    or type(close_length) is not int
                    or not 0 < close_length <= 128
                    or type(raw_symbol) is not str
                    or raw_symbol != symbol
                    or type(raw_day) is not str
                    or type(close_text) is not str
                ):
                    raise ValueError("Stage C market source price row is malformed")
                normalized_day = _iso_date(raw_day, "source price date")
                if normalized_day not in {start, end}:
                    raise ValueError("Stage C market source returned an unexpected price date")
                try:
                    close = Decimal(close_text.replace(",", "").strip())
                except (InvalidOperation, ValueError) as exc:
                    raise ValueError("Stage C market source close price is invalid") from exc
                if not close.is_finite() or close <= 0:
                    raise ValueError("Stage C market source close price is not positive")
                row_key = (symbol, normalized_day)
                if row_key in observed_rows:
                    raise ValueError("Stage C market source price row is duplicated")
                observed_rows[row_key] = (close_text, close)
                row_fingerprint.append(
                    {
                        "stock_code": symbol,
                        "date": normalized_day,
                        "close_text": close_text,
                    }
                )
        expected_keys = {
            (symbol, endpoint)
            for symbol in symbols
            for endpoint in (start, end)
        }
        if set(observed_rows) != expected_keys:
            raise ValueError("Stage C market source price rows are missing or duplicated")
        for symbol in symbols:
            start_close = observed_rows[(symbol, start)][1]
            end_close = observed_rows[(symbol, end)][1]
            actual_return_bp = int(
                (
                    (end_close / start_close - Decimal(1))
                    * Decimal(10_000)
                ).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
            )
            if actual_return_bp != expected_returns_bp[symbol]:
                raise ValueError(
                    "Stage C stock_return_bp differs from exact read-only source prices"
                )
        connection.commit()
        data_version_after_row = connection.execute("PRAGMA data_version").fetchone()
        if data_version_after_row != data_version_before_row:
            raise ValueError("Stage C market source changed during price verification")
    except sqlite3.Error as exc:
        raise ValueError("Stage C market source price verification failed") from exc
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()

    _assessment_require_plain_file(source_path)
    _assessment_require_no_sqlite_sidecars(source_path)
    if _assessment_source_file_stat(source_path) != expected_stat:
        raise ValueError("Stage C market source changed during price verification")
    encoded_rows = json.dumps(
        sorted(row_fingerprint, key=lambda row: (row["stock_code"], row["date"])),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded_rows).hexdigest()


def _assessment_require_plain_file(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise ValueError("Stage C market source path is unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode) or bool(
            getattr(metadata, "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("Stage C market source path contains a link or reparse point")
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Stage C market source path is not a regular file")


def _assessment_require_no_sqlite_sidecars(path: Path) -> None:
    """只接受已 checkpoint 的單檔來源，因 Stage C summary 未 pin WAL bytes。"""

    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        try:
            metadata = sidecar.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ValueError("Stage C market source sidecar 無法核對") from exc
        if stat.S_ISLNK(metadata.st_mode) or bool(
            getattr(metadata, "st_file_attributes", 0) & 0x400
        ) or not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Stage C market source sidecar 不是一般檔案")
        raise ValueError("Stage C market source has unpinned SQLite sidecars")


def _assessment_source_file_stat(path: Path) -> dict[str, int]:
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Stage C market source is not a regular file")
    return {
        "size": int(metadata.st_size),
        "mtime_ns": int(metadata.st_mtime_ns),
        "device": int(metadata.st_dev),
        "inode": int(metadata.st_ino),
    }


def _assessment_brier_bp(probabilities: Sequence[int], labels: Sequence[int]) -> int:
    if not probabilities or len(probabilities) != len(labels):
        raise ValueError("assessment Brier input lengths are invalid")
    if any(
        isinstance(probability, bool)
        or type(probability) is not int
        or not 0 <= probability <= 10_000
        for probability in probabilities
    ):
        raise ValueError("assessment probabilities must be integer basis points")
    if any(isinstance(label, bool) or type(label) is not int or label not in (0, 1) for label in labels):
        raise ValueError("assessment labels must be binary integers")
    return sum(
        (probability - label * 10_000) ** 2
        for probability, label in zip(probabilities, labels)
    ) // (len(labels) * 10_000)


def _assessment_calibration_gap_bp(
    probabilities: Sequence[int], labels: Sequence[int]
) -> int:
    if not probabilities or len(probabilities) != len(labels):
        raise ValueError("assessment calibration input lengths are invalid")
    return abs(
        sum(probabilities) // len(probabilities)
        - sum(labels) * 10_000 // len(labels)
    )


def _assessment_payload_hash(value: Mapping[str, Any]) -> str:
    return canonical_payload_hash(value)


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
        journal_paths: PersonalJournalPaths | None = None,
        legacy_read_only: bool = False,
    ) -> None:
        if isinstance(max_records, bool) or max_records <= 0:
            raise ValueError("max_records must be positive")
        self.journal_paths = journal_paths
        self.legacy_read_only = legacy_read_only
        if journal_paths is not None:
            journal_paths.assert_selected(Path(path), legacy_read_only=legacy_read_only)
        elif legacy_read_only:
            raise ValueError("personal_journal_paths_required")
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

    def _validate_path(self) -> None:
        if self.journal_paths is not None:
            self.journal_paths.assert_selected(self.path, legacy_read_only=self.legacy_read_only)

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

        self._validate_path()
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
        self._validate_path()
        return (self.path,)

    def _load(self) -> tuple[Mapping[str, Any], ...]:
        self._validate_path()
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
                    if self.journal_paths is not None and isinstance(value, Mapping):
                        validate_personal_journal_record(value)
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

        self._validate_path()
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
                    if self.journal_paths is not None and isinstance(value, Mapping):
                        validate_personal_journal_record(value)
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


@dataclass(frozen=True)
class PersonalModelAssessmentV1:
    """同一 saved recommendation/capture 的唯讀個人模型評估投影。

    此 v1 只呈現 Stage C 已封存的單次 capture 狀態與 scope；單筆結果不
    產生繼續使用、停用或替換模型的效果建議，也不觸發任何自動切換。
    """

    result_id: str
    capture_id: str
    assessment_status: str
    evidence_status: str
    recommendation: str
    reason: str
    identity: Mapping[str, Any]
    scope: Mapping[str, Any]
    matured_sample_count: int
    pending_sample_count: int | None
    metrics: Mapping[str, int | None]
    after_cost: Mapping[str, Any]
    missing_evidence: tuple[str, ...]
    next_steps: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()
    read_only: bool = True
    writes_allowed: bool = False
    auto_switch: bool = False
    schema_version: str = PERSONAL_MODEL_ASSESSMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not self.read_only
            or self.writes_allowed
            or self.auto_switch
            or self.recommendation != "insufficient_data"
            or self.assessment_status != "insufficient_data"
        ):
            raise ValueError("personal model assessment v1 must remain advisory/read-only")
        if self.evidence_status not in {"pending", "unknown", "matured"}:
            raise ValueError("unsupported personal model evidence status")
        if (
            isinstance(self.matured_sample_count, bool)
            or not isinstance(self.matured_sample_count, int)
            or self.matured_sample_count < 0
            or (
                self.pending_sample_count is not None
                and (
                    isinstance(self.pending_sample_count, bool)
                    or not isinstance(self.pending_sample_count, int)
                    or self.pending_sample_count < 0
                )
            )
            or (self.evidence_status != "unknown" and self.pending_sample_count is None)
        ):
            raise ValueError("personal model sample counts must be non-negative integers")
        object.__setattr__(self, "identity", dict(self.identity))
        object.__setattr__(self, "scope", dict(self.scope))
        object.__setattr__(self, "metrics", dict(self.metrics))
        object.__setattr__(self, "after_cost", dict(self.after_cost))
        object.__setattr__(self, "missing_evidence", tuple(self.missing_evidence))
        object.__setattr__(self, "next_steps", tuple(self.next_steps))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def to_dict(self) -> dict[str, Any]:
        body = _json_safe(
            {
                "schema_version": self.schema_version,
                "result_id": self.result_id,
                "capture_id": self.capture_id,
                "assessment_status": self.assessment_status,
                "evidence_status": self.evidence_status,
                "recommendation": self.recommendation,
                "reason": self.reason,
                "identity": dict(self.identity),
                "scope": dict(self.scope),
                "matured_sample_count": self.matured_sample_count,
                "pending_sample_count": self.pending_sample_count,
                "metrics": dict(self.metrics),
                "after_cost": dict(self.after_cost),
                "missing_evidence": list(self.missing_evidence),
                "next_steps": list(self.next_steps),
                "diagnostics": list(self.diagnostics),
                "read_only": self.read_only,
                "writes_allowed": self.writes_allowed,
                "auto_switch": self.auto_switch,
            }
        )
        if not isinstance(body, dict):
            raise ValueError("personal model assessment did not serialize to an object")
        body["assessment_sha256"] = _assessment_payload_hash(body)
        return body


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
        journal_paths: PersonalJournalPaths | None = None,
        legacy_journal_read_only: bool = False,
        evidence_db_path: str | Path | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
        max_candidates_per_result: int = DEFAULT_MAX_CANDIDATES_PER_RESULT,
        max_evidence_events: int = DEFAULT_MAX_EVIDENCE_EVENTS,
        max_journal_rows: int = DEFAULT_MAX_JOURNAL_ROWS,
    ) -> "PersonalizationReadService":
        root = Path(output_root).expanduser().resolve()
        if journal_paths is not None and journal_path is not None:
            raise ValueError("personal_journal_selector_conflict")
        if legacy_journal_read_only and journal_paths is None:
            raise ValueError("personal_journal_paths_required")
        resolved_journal = (
            journal_paths.read_path(legacy_read_only=legacy_journal_read_only)
            if journal_paths is not None
            else (Path(journal_path) if journal_path is not None else root / "portfolio" / "journal_entries.jsonl")
        )
        resolved_evidence = (
            Path(evidence_db_path)
            if evidence_db_path is not None
            else root.parent / "sqlite" / "twstock.db"
        )
        runs_dir = root / "recommendation" / "runs"
        return cls(
            ReadOnlyRecommendationSource(root, max_results=max_results),
            ReadOnlyJournalRevisionSource(
                resolved_journal, max_records=max_journal_rows, journal_paths=journal_paths,
                legacy_read_only=legacy_journal_read_only,
            ),
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

    def read_personal_model_assessment(
        self,
        result_id: str,
        capture_path: str | Path,
        personal_capture_root: str | Path,
        daily_summary_path: str | Path,
    ) -> PersonalModelAssessmentV1:
        """讀回同一 canonical result、personal capture 與 Stage C 摘要。

        Stage C 目前沒有 result→summary 索引；呼叫者必須提供明確 summary
        檔案，不會掃描 latest/glob。所有輸入只讀、有限長度，並要求 canonical
        execution、V2 source-time policy、capture 與 summary 的 identity 完全相符。
        """

        resolved_result = _safe_result_id(result_id)
        if not resolved_result:
            raise ValueError("result_id 必須是精確 filename-like identity")
        if self.execution_queries is None:
            raise ValueError("personal model assessment 缺少 canonical execution queries")

        first_read = self.read_canonical_execution_exact(resolved_result)
        if first_read is None or first_read.execution is None:
            raise ValueError("personal model assessment 需要已保存的 canonical execution")

        personal_root = _assessment_absolute_path(
            personal_capture_root, "personal_capture_root"
        )
        capture_file = _assessment_absolute_path(capture_path, "capture_path")
        capture = read_personal_prediction_capture(
            capture_file,
            self.execution_queries,
            personal_root,
            expected_result_id=resolved_result,
        )
        second_read = self.read_canonical_execution_exact(resolved_result)
        if second_read is None or second_read.execution is None:
            raise ValueError("canonical execution 在 assessment 讀取期間消失")
        canonical = capture.get("canonical")
        if (
            not isinstance(canonical, Mapping)
            or canonical.get("payload_hash") != first_read.payload_hash
            or canonical.get("raw_artifact_sha256") != first_read.raw_artifact_sha256
            or first_read.payload_hash != second_read.payload_hash
            or first_read.raw_artifact_sha256 != second_read.raw_artifact_sha256
        ):
            raise ValueError("canonical execution 在 assessment 讀取期間改變")

        policy_event = capture.get("policy_event")
        policy_snapshot = (
            policy_event.get("policy_snapshot")
            if isinstance(policy_event, Mapping)
            else None
        )
        if (
            not isinstance(policy_event, Mapping)
            or policy_event.get("schema_version")
            != "recommendation-personal-use-policy-snapshot.v2"
            or policy_event.get("result_id") != resolved_result
            or policy_event.get("effective_mode") != "personal_calibrated_probability"
            or not isinstance(policy_snapshot, Mapping)
            or policy_snapshot.get("schema_version") != PERSONAL_USE_POLICY_SCHEMA_V2
        ):
            raise ValueError("assessment 僅支援已讀回的個人 V2 模型政策")
        source_trust = policy_snapshot.get("source_time_trust")
        candidate = policy_snapshot.get("candidate")
        if not isinstance(source_trust, Mapping) or not source_trust:
            raise ValueError("個人 V2 policy 缺少 source-time trust")
        if not isinstance(candidate, Mapping) or not candidate:
            raise ValueError("個人 V2 policy 缺少完整 candidate pins")
        if (
            policy_event.get("source_time_basis") != "user_declared_source_time"
            or policy_event.get("research_only") is not True
            or policy_event.get("official_historical_pit_verified") is not False
            or source_trust.get("basis") != "user_declared_source_time"
            or source_trust.get("research_only") is not True
            or source_trust.get("official_historical_pit_verified") is not False
            or source_trust.get("candidate") != dict(candidate)
        ):
            raise ValueError("個人來源信任標記與 candidate pins 不一致")

        baseline = capture.get("probability_baseline_snapshot")
        if (
            not isinstance(baseline, Mapping)
            or baseline.get("schema_version")
            != PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2
            or capture.get("schema_version") != PERSONAL_PREDICTION_CAPTURE_SCHEMA_V3
            or baseline.get("upside_baseline_kind")
            != PERSONAL_FIXED_NULL_BENCHMARK_KIND
            or baseline.get("upside_baseline_id") != "null_benchmark_50pct_v1"
            or baseline.get("upside_probability_bp_by_symbol")
            != {
                str(code): 5_000
                for code in baseline.get("projected_stock_codes", [])
            }
        ):
            raise ValueError("assessment capture 沒有 exact fixed 50% null baseline")
        delivered_rows = capture.get("delivered_rows")
        if not isinstance(delivered_rows, list) or not delivered_rows:
            raise ValueError("assessment capture delivered rows 缺失")
        active_codes = baseline.get("model_active_stock_codes")
        fallback_codes = baseline.get("rule_only_fallback_stock_codes")
        if (
            not isinstance(active_codes, list)
            or not isinstance(fallback_codes, list)
            or not active_codes
            or any(type(code) is not str or not code for code in active_codes)
            or any(type(code) is not str or not code for code in fallback_codes)
            or len(set(active_codes)) != len(active_codes)
            or len(set(fallback_codes)) != len(fallback_codes)
            or not set(active_codes).isdisjoint(fallback_codes)
            or set(active_codes) | set(fallback_codes)
            != {
                str(row.get("stock_code"))
                for row in delivered_rows
                if isinstance(row, Mapping)
            }
            or any(not isinstance(row, Mapping) for row in delivered_rows)
            or len(active_codes) + len(fallback_codes) != len(delivered_rows)
            or baseline.get("delivered_count") != len(delivered_rows)
            or baseline.get("model_active_count") != len(active_codes)
            or baseline.get("fallback_count") != len(fallback_codes)
            or baseline.get("model_coverage_bp")
            != len(active_codes) * 10_000 // len(delivered_rows)
        ):
            raise ValueError("assessment capture active/fallback partition is inconsistent")

        summary_file = _assessment_absolute_path(
            daily_summary_path, "daily_summary_path"
        )
        summary, summary_raw_sha256 = _read_personal_assessment_json(
            summary_file,
            max_bytes=_MAX_PERSONAL_ASSESSMENT_JSON_BYTES,
            label="Stage C daily summary",
        )
        summary_hash = _verify_personal_outcome_hashed_json(
            summary, expected_schema="personal-recommendation-natural-outcome-daily.v1"
        )
        if (
            summary_file.parent.name != "runs"
            or summary_file.parent.parent.name != "personal_natural_outcomes"
            or summary_file.stem != summary_hash.removeprefix("sha256:")
        ):
            raise ValueError("Stage C summary filename does not match its payload hash")
        summary_sources = summary.get("sources")
        if not isinstance(summary_sources, Mapping):
            raise ValueError("Stage C summary source identities are missing")
        expected_canonical_root = (
            self.canonical_runs_dir.parent.parent
            if self.canonical_runs_dir is not None
            else None
        )
        if (
            expected_canonical_root is None
            or _assessment_normalized_path(
                summary_sources.get("canonical_recommendation_output_root")
            )
            != _assessment_normalized_path(expected_canonical_root)
            or _assessment_normalized_path(
                summary_sources.get("personal_capture_root")
            )
            != _assessment_normalized_path(personal_root)
            or _assessment_normalized_path(summary_sources.get("market_source_db"))
            != _assessment_normalized_path(source_trust.get("source_database_path"))
        ):
            raise ValueError("Stage C summary roots differ from canonical/capture source trust")

        captures = summary.get("captures")
        if (
            not isinstance(captures, list)
            or not 1 <= len(captures) <= 500
            or type(summary.get("selected_capture_count")) is not int
            or summary.get("selected_capture_count") != len(captures)
            or summary.get("global_natural_evidence_created") is not False
            or summary.get("promotion_credit_created") is not False
        ):
            raise ValueError("Stage C summary cohort/credit fields are invalid")
        matching_rows = [
            row
            for row in captures
            if isinstance(row, Mapping)
            and row.get("capture_id") == capture.get("capture_id")
            and row.get("result_id") == resolved_result
        ]
        if len(matching_rows) != 1:
            raise ValueError("Stage C summary must contain exactly one matching capture")
        summary_row = matching_rows[0]
        if (
            _assessment_normalized_path(summary_row.get("capture_path"))
            != _assessment_normalized_path(capture_file)
        ):
            raise ValueError("Stage C summary capture path differs from the exact capture")

        decision_at = _text(capture.get("decision_at"))
        decision_date = _text(baseline.get("decision_date"))
        context = first_read.execution.context
        context_date = getattr(context, "as_of_date", None)
        context_date_iso = getattr(context_date, "isoformat", None)
        context_decision_at = getattr(context, "decision_at", None)
        if (
            not callable(context_date_iso)
            or context_date_iso() != decision_date
            or not isinstance(context_decision_at, datetime)
            or parse_aware_datetime(context_decision_at, "canonical decision_at")
            != parse_aware_datetime(decision_at, "capture decision_at")
        ):
            raise ValueError("canonical decision date/clock differs from personal capture")
        receipt_binding = capture.get("receipt_binding")
        if not isinstance(receipt_binding, Mapping):
            raise ValueError("assessment capture receipt binding is missing")
        if (
            policy_event.get("decision_at") != decision_at
            or receipt_binding.get("decision_date") != decision_date
            or receipt_binding.get("candidate_id") != candidate.get("candidate_id")
            or receipt_binding.get("receipt_hash") is None
            or receipt_binding.get("cost_scenario_hash")
            != baseline.get("cost_scenario_hash")
            or receipt_binding.get("projection_rows_sha256")
            != baseline.get("projection_rows_sha256")
        ):
            raise ValueError("assessment capture policy/receipt/baseline identity mismatch")
        evaluation_at = _text(summary.get("evaluation_at"))
        parsed_evaluation_at = parse_aware_datetime(evaluation_at, "Stage C evaluation_at")
        if parsed_evaluation_at < parse_aware_datetime(
            _text(capture.get("capture_written_at")), "capture_written_at"
        ):
            raise ValueError("Stage C evaluation clock precedes the saved capture")

        row_status = summary_row.get("status")
        if row_status not in {"pending", "unknown", "matured"}:
            raise ValueError("Stage C capture status is unsupported")
        matured_count = _assessment_nonnegative_int(
            summary_row.get("matured_sample_count"), "matured_sample_count"
        )
        pending_raw = summary_row.get("pending_sample_count")
        if pending_raw is None and row_status == "unknown":
            pending_count: int | None = None
        else:
            pending_count = _assessment_nonnegative_int(
                pending_raw, "pending_sample_count"
            )
        if row_status == "pending" and (
            matured_count != 0
            or pending_count != len(active_codes)
            or summary_row.get("projection_status") != "pending"
        ):
            raise ValueError("Stage C pending sample count differs from captured active rows")
        reason = _text(summary_row.get("reason")) or "personal_outcome_reason_missing"
        metrics: dict[str, int | None] = {
            "model_brier_bp": None,
            "model_calibration_gap_bp": None,
            "fixed_null_benchmark_brier_bp": None,
            "fixed_null_benchmark_calibration_gap_bp": None,
            "model_minus_fixed_null_brier_bp": None,
            "sample_count": None,
        }
        after_cost: dict[str, Any] = {
            "status": "unavailable",
            "model_brier_bp": None,
            "fixed_null_benchmark_brier_bp": None,
            "sample_count": None,
        }
        verified_market_price_rows_sha256: str | None = None
        missing: list[str] = []
        next_steps: list[str] = []
        diagnostics: list[str] = []
        evidence_status = str(row_status)
        source_before = summary_sources.get("market_source_db_before")
        source_after = summary_sources.get("market_source_db_after")
        trust_file_identity = source_trust.get("file_identity")
        if not isinstance(source_before, Mapping) or not isinstance(source_after, Mapping):
            evidence_status = "unknown"
            reason = "market_source_stat_missing"
            diagnostics.append("stage_c_market_source_stat_missing")
            missing.append(reason)
            next_steps.append("確認 Stage C 行情來源 before/after 身分收據，再以相同 capture 重跑評估。")
        elif dict(source_before) != dict(source_after):
            evidence_status = "unknown"
            reason = "market_source_changed_during_batch"
            diagnostics.append("stage_c_market_source_changed_during_batch")
            missing.append(reason)
            next_steps.append("隔離來源變動的本次評估；確認資料庫穩定後再以真實 evaluation clock 重跑。")
        elif (
            not isinstance(trust_file_identity, Mapping)
            or isinstance(trust_file_identity.get("device"), bool)
            or type(trust_file_identity.get("device")) is not int
            or isinstance(trust_file_identity.get("inode"), bool)
            or type(trust_file_identity.get("inode")) is not int
            or source_before.get("device") != trust_file_identity.get("device")
            or source_before.get("inode") != trust_file_identity.get("inode")
        ):
            evidence_status = "unknown"
            reason = "market_source_file_identity_differs_from_policy"
            diagnostics.append("stage_c_market_source_policy_identity_mismatch")
            missing.append(reason)
            next_steps.append("用目前明示信任的隔離來源重新檢查政策，再重跑個人評估。")

        outcome_ref = summary_row.get("outcome_artifact")
        outcome_payload: Mapping[str, Any] | None = None
        outcome_raw_hash: str | None = None
        if row_status == "matured":
            if evidence_status != "matured":
                raise ValueError("Stage C matured result has an unverified source identity")
            if not isinstance(source_before, Mapping):
                raise ValueError("Stage C matured result has no bound source stat")
            if (
                matured_count != len(active_codes)
                or pending_count != 0
                or not isinstance(outcome_ref, Mapping)
            ):
                raise ValueError("Stage C matured status has inconsistent counts/artifact")
            (
                outcome_payload,
                outcome_raw_hash,
                verified_metrics,
                verified_after_cost,
                verified_market_price_rows_sha256,
            ) = (
                self._read_personal_model_outcome_artifact(
                    outcome_ref,
                    summary_file=summary_file,
                    capture=capture,
                    policy_snapshot=policy_snapshot,
                    baseline=baseline,
                    source_trust=source_trust,
                    evaluation_at=parsed_evaluation_at,
                    expected_source_stat=source_before,
                )
            )
            metrics.update(verified_metrics)
            after_cost.update(verified_after_cost)
            if matured_count != verified_metrics["sample_count"]:
                raise ValueError("Stage C summary matured count differs from verified outcome rows")
        else:
            if outcome_ref is not None or matured_count != 0:
                raise ValueError("Stage C pending/unknown capture unexpectedly has an outcome")
            if row_status == "pending" and (
                pending_count is None or pending_count <= 0
            ):
                raise ValueError("Stage C pending capture has no pending samples")
            if row_status == "pending":
                missing.append(reason)
                next_steps.append(
                    "檢查同一 capture 的官方 20-session、行情來源及成本診斷；證據補齊後以真實 evaluation clock 重跑 Stage C。"
                )
            else:
                missing.append(reason)
                next_steps.append(
                    "先修復或重新驗證 Stage C 的來源／日曆證據，再對同一 canonical capture 重跑；不要回填時鐘或把未知成本當零。"
                )

        delivered_codes = [str(row["stock_code"]) for row in delivered_rows]
        identity = {
            "canonical_payload_hash": first_read.payload_hash,
            "canonical_raw_artifact_sha256": first_read.raw_artifact_sha256,
            "capture_payload_sha256": capture.get("payload_sha256"),
            "policy_sha256": policy_snapshot.get("policy_sha256"),
            "policy_revision": policy_snapshot.get("revision"),
            "policy_version": policy_snapshot.get("policy_version"),
            "candidate_pins": dict(candidate),
            "source_time_trust": dict(source_trust),
            "market_source_file_identity": (
                dict(source_before) if isinstance(source_before, Mapping) else None
            ),
            "verified_market_price_rows_sha256": verified_market_price_rows_sha256,
            "receipt_hash": receipt_binding.get("receipt_hash"),
            "projection_rows_sha256": receipt_binding.get("projection_rows_sha256"),
            "cost_scenario_hash": receipt_binding.get("cost_scenario_hash"),
            "baseline_snapshot_sha256": baseline.get("snapshot_sha256"),
            "capture_id": capture.get("capture_id"),
            "decision_at": decision_at,
            "result_id": resolved_result,
            "daily_summary_payload_sha256": summary_hash,
            "daily_summary_raw_sha256": summary_raw_sha256,
            "evaluation_at": evaluation_at,
            "outcome_payload_sha256": (
                outcome_ref.get("payload_sha256")
                if isinstance(outcome_ref, Mapping)
                else None
            ),
            "outcome_raw_sha256": outcome_raw_hash,
        }
        scope = {
            "decision_date": decision_date,
            "return_basis": "close_to_close_event_date",
            "return_start_date": decision_date,
            "return_end_date": (
                outcome_payload.get("return_semantics", {}).get("end_date")
                if isinstance(outcome_payload, Mapping)
                and isinstance(outcome_payload.get("return_semantics"), Mapping)
                else None
            ),
            "is_execution_pnl": False,
            "horizon_sessions": 20,
            "cost_scenario_hash": receipt_binding.get("cost_scenario_hash"),
            "delivered_stock_codes": delivered_codes,
            "delivered_count": len(delivered_codes),
            "model_active_stock_codes": list(active_codes),
            "model_active_count": len(active_codes),
            "rule_only_fallback_stock_codes": list(fallback_codes),
            "fallback_count": len(fallback_codes),
            "model_coverage_bp": baseline.get("model_coverage_bp"),
            "upside_baseline": {
                "kind": PERSONAL_FIXED_NULL_BENCHMARK_KIND,
                "id": "null_benchmark_50pct_v1",
                "probability_bp": 5_000,
            },
            "population_or_rule_model_baseline": None,
        }
        if not missing and evidence_status == "matured":
            missing.append(
                "多個成熟決策日的同 scope 個人結果與明確 versioned advisory policy 尚未建立"
            )
            next_steps.append(
                "累積更多同候選、同 source lane、同 20-session horizon、同 cost scenario 的成熟 capture，再由明確版本化的 advisory 規則解讀；此單筆結果不產生效果建議。"
            )

        return PersonalModelAssessmentV1(
            result_id=resolved_result,
            capture_id=str(capture["capture_id"]),
            assessment_status="insufficient_data",
            evidence_status=evidence_status,
            recommendation="insufficient_data",
            reason=reason,
            identity=identity,
            scope=scope,
            matured_sample_count=matured_count,
            pending_sample_count=pending_count,
            metrics=metrics,
            after_cost=after_cost,
            missing_evidence=tuple(missing),
            next_steps=tuple(next_steps),
            diagnostics=tuple(diagnostics),
        )

    def _read_personal_model_outcome_artifact(
        self,
        outcome_ref: Mapping[str, Any],
        *,
        summary_file: Path,
        capture: Mapping[str, Any],
        policy_snapshot: Mapping[str, Any],
        baseline: Mapping[str, Any],
        source_trust: Mapping[str, Any],
        evaluation_at: datetime,
        expected_source_stat: Mapping[str, Any],
    ) -> tuple[
        Mapping[str, Any],
        str,
        dict[str, int | None],
        dict[str, Any],
        str,
    ]:
        if set(outcome_ref) != {"path", "payload_sha256"}:
            raise ValueError("Stage C outcome reference fields are invalid")
        outcome_path = _assessment_absolute_path(outcome_ref.get("path"), "outcome path")
        output_root = summary_file.parent.parent
        expected_outcome_dir = output_root / "outcomes"
        if outcome_path.parent != expected_outcome_dir or outcome_path.suffix.lower() != ".json":
            raise ValueError("Stage C outcome path is outside its summary output root")
        outcome, raw_hash = _read_personal_assessment_json(
            outcome_path,
            max_bytes=_MAX_PERSONAL_ASSESSMENT_JSON_BYTES,
            label="Stage C personal outcome",
        )
        outcome_hash = _verify_personal_outcome_hashed_json(
            outcome, expected_schema="personal-recommendation-natural-outcome.v2"
        )
        outcome_projection = outcome.get("projection")
        outcome_evaluation_at = (
            outcome_projection.get("evaluation_at")
            if isinstance(outcome_projection, Mapping)
            else None
        )
        outcome_capture_id = capture.get("capture_id")
        if (
            type(outcome_capture_id) is not str
            or not outcome_capture_id
            or type(outcome_evaluation_at) is not str
            or not outcome_evaluation_at
        ):
            raise ValueError("Stage C outcome capture/evaluation identity is missing")
        outcome_file_identity: dict[str, Any] = {
            "capture_id": outcome_capture_id,
            "evaluation_at": outcome_evaluation_at,
        }
        if capture.get("schema_version") == "recommendation-personal-prediction-capture.v3":
            outcome_file_identity["outcome_schema_version"] = "personal-recommendation-natural-outcome.v2"
        expected_outcome_stem = _stage_c_payload_hash(outcome_file_identity).removeprefix(
            "sha256:"
        )
        if (
            outcome_hash != outcome_ref.get("payload_sha256")
            or outcome_path.stem != expected_outcome_stem
        ):
            raise ValueError("Stage C outcome bytes/hash/path identity mismatch")
        if (
            outcome.get("lane") != "personal_only"
            or outcome.get("global_natural_evidence_created") is not False
            or outcome.get("promotion_credit_created") is not False
        ):
            raise ValueError("Stage C outcome lane/credit flags are invalid")
        binding = outcome.get("capture_binding")
        baseline_snapshot = capture.get("probability_baseline_snapshot")
        receipt_binding = capture.get("receipt_binding")
        if (
            not isinstance(binding, Mapping)
            or not isinstance(baseline_snapshot, Mapping)
            or not isinstance(receipt_binding, Mapping)
        ):
            raise ValueError("Stage C outcome/capture bindings are missing")
        expected_binding = {
            "capture_id": capture.get("capture_id"),
            "result_id": capture.get("result_id"),
            "policy_sha256": policy_snapshot.get("policy_sha256"),
            "candidate_id": policy_snapshot.get("candidate", {}).get("candidate_id")
            if isinstance(policy_snapshot.get("candidate"), Mapping)
            else None,
            "receipt_hash": receipt_binding.get("receipt_hash"),
            "projection_rows_sha256": receipt_binding.get("projection_rows_sha256"),
            "cost_scenario_hash": receipt_binding.get("cost_scenario_hash"),
            "decision_at": capture.get("decision_at"),
            "probability_baseline_snapshot_sha256": baseline_snapshot.get("snapshot_sha256"),
            "decision_date": baseline_snapshot.get("decision_date"),
        }
        if dict(binding) != expected_binding:
            raise ValueError("Stage C outcome capture binding differs from verified capture")
        source = outcome.get("source")
        session_proof = source.get("session_proof") if isinstance(source, Mapping) else None
        if not isinstance(source, Mapping) or not isinstance(session_proof, Mapping):
            raise ValueError("Stage C outcome close-to-close/session scope is invalid")
        return_semantics = outcome.get("return_semantics")
        if (
            not isinstance(return_semantics, Mapping)
            or set(return_semantics)
            != {"basis", "start_date", "end_date", "is_execution_pnl"}
            or return_semantics.get("basis") != "close_to_close_event_date"
            or return_semantics.get("start_date") != baseline_snapshot.get("decision_date")
            or type(return_semantics.get("end_date")) is not str
            or return_semantics.get("is_execution_pnl") is not False
        ):
            raise ValueError("Stage C outcome close-to-close date semantics are invalid")
        if (
            _assessment_normalized_path(source.get("market_source_db"))
            != _assessment_normalized_path(source_trust.get("source_database_path"))
        ):
            raise ValueError("Stage C outcome source DB differs from V2 source trust")
        if (
            session_proof.get("status") != "ready"
            or session_proof.get("horizon_sessions") != 20
            or session_proof.get("capture_date") != baseline_snapshot.get("decision_date")
            or session_proof.get("endpoint_date")
            != outcome.get("return_semantics", {}).get("end_date")
        ):
            raise ValueError("Stage C outcome has incomplete official 20-session proof")
        verified_session_proof = verify_natural_maturity_session_proof(
            session_proof,
            capture_date=str(baseline_snapshot.get("decision_date")),
            label_end_date=str(return_semantics.get("end_date")),
            evaluation_at=evaluation_at,
            expected_db_path=str(source_trust.get("source_database_path", "")),
        )
        if dict(verified_session_proof) != dict(session_proof):
            raise ValueError("Stage C session proof differs from independent verification")

        projection = outcome.get("projection")
        outcomes = projection.get("outcomes") if isinstance(projection, Mapping) else None
        metrics_value = projection.get("metrics") if isinstance(projection, Mapping) else None
        model_scope = outcome.get("model_scope")
        if (
            not isinstance(projection, Mapping)
            or projection.get("status") != "matured"
            or not isinstance(outcomes, list)
            or not outcomes
            or not isinstance(metrics_value, Mapping)
            or not isinstance(model_scope, Mapping)
        ):
            raise ValueError("Stage C matured outcome projection is incomplete")
        active_codes = baseline.get("model_active_stock_codes")
        fallback_codes = baseline.get("rule_only_fallback_stock_codes")
        if (
            not isinstance(active_codes, list)
            or not isinstance(fallback_codes, list)
            or model_scope.get("model_active_stock_codes") != active_codes
            or model_scope.get("rule_only_fallback_stock_codes") != fallback_codes
            or model_scope.get("model_active_count") != len(active_codes)
            or model_scope.get("rule_only_fallback_count") != len(fallback_codes)
            or model_scope.get("delivered_count")
            != baseline.get("delivered_count")
            or model_scope.get("model_coverage_bp")
            != baseline.get("model_coverage_bp")
            or model_scope.get("fallback_rows_have_model_probability") is not False
            or len(outcomes) != len(active_codes)
        ):
            raise ValueError("Stage C outcome active/fallback cohort differs from capture")
        delivered = capture.get("delivered_rows")
        if not isinstance(delivered, list):
            raise ValueError("verified capture delivered rows are missing")
        delivered_by_code = {
            str(row["stock_code"]): row
            for row in delivered
            if isinstance(row, Mapping) and type(row.get("stock_code")) is str
        }
        seen_codes: set[str] = set()
        model_probabilities: list[int] = []
        null_probabilities: list[int] = []
        labels: list[int] = []
        stock_returns_bp: dict[str, int] = {}
        for row in outcomes:
            if not isinstance(row, Mapping):
                raise ValueError("Stage C outcome row is invalid")
            code = row.get("stock_code")
            if type(code) is not str or code in seen_codes or code not in active_codes:
                raise ValueError("Stage C outcome row is duplicate or not model-active")
            seen_codes.add(code)
            delivered_row = delivered_by_code.get(code)
            delivered_projection = (
                delivered_row.get("projection") if isinstance(delivered_row, Mapping) else None
            )
            probability = row.get("calibrated_probability_bp")
            null_probability = row.get("upside_baseline_probability_bp")
            label = row.get("label")
            stock_return_bp = row.get("stock_return_bp")
            if (
                isinstance(probability, bool)
                or type(probability) is not int
                or not 0 <= probability <= 10_000
                or isinstance(null_probability, bool)
                or type(null_probability) is not int
                or null_probability != 5_000
                or isinstance(label, bool)
                or type(label) is not int
                or label not in (0, 1)
                or row.get("label_kind") != "stock_close_return_positive.v1"
                or isinstance(stock_return_bp, bool)
                or type(stock_return_bp) is not int
                or label != int(stock_return_bp > 0)
                or not isinstance(delivered_projection, Mapping)
                or delivered_projection.get("calibrated_probability_bp") != probability
                or row.get("cost_scenario_hash") != receipt_binding.get("cost_scenario_hash")
                or row.get("return_basis") != "close_to_close_event_date"
                or row.get("return_start_date") != baseline.get("decision_date")
                or row.get("return_end_date") != outcome.get("return_semantics", {}).get("end_date")
                or row.get("is_execution_pnl") is not False
            ):
                raise ValueError("Stage C outcome row does not match captured probability/scope")
            model_probabilities.append(probability)
            null_probabilities.append(null_probability)
            labels.append(label)
            stock_returns_bp[code] = stock_return_bp
        if seen_codes != set(active_codes):
            raise ValueError("Stage C outcome rows do not cover the model-active subset")

        verified_price_rows_sha256 = _verify_personal_outcome_source_prices(
            source_database_path=source_trust.get("source_database_path"),
            expected_source_stat=expected_source_stat,
            start_date=str(baseline_snapshot.get("decision_date")),
            end_date=str(return_semantics.get("end_date")),
            expected_returns_bp=stock_returns_bp,
        )

        model_brier = _assessment_brier_bp(model_probabilities, labels)
        null_brier = _assessment_brier_bp(null_probabilities, labels)
        model_gap = _assessment_calibration_gap_bp(model_probabilities, labels)
        null_gap = _assessment_calibration_gap_bp(null_probabilities, labels)
        if (
            metrics_value.get("sample_count") != len(labels)
            or metrics_value.get("brier_bp") != model_brier
            or metrics_value.get("calibration_gap_bp") != model_gap
            or metrics_value.get("fixed_null_benchmark_sample_count") != len(labels)
            or metrics_value.get("fixed_null_benchmark_brier_bp") != null_brier
            or metrics_value.get("fixed_null_benchmark_calibration_gap_bp") != null_gap
        ):
            raise ValueError("Stage C reported metrics differ from verified outcome rows")
        verified_metrics: dict[str, int | None] = {
            "sample_count": len(labels),
            "model_brier_bp": model_brier,
            "model_calibration_gap_bp": model_gap,
            "fixed_null_benchmark_brier_bp": null_brier,
            "fixed_null_benchmark_calibration_gap_bp": null_gap,
            "model_minus_fixed_null_brier_bp": model_brier - null_brier,
        }
        after_metrics = {
            "status": "unassessed",
            "reported_projection_status": str(
                projection.get("after_cost_status") or "unavailable"
            ),
            "model_brier_bp": None,
            "fixed_null_benchmark_brier_bp": None,
            "sample_count": None,
            "reason": "after_cost_metrics_not_recomputed_by_readback",
        }
        return (
            outcome,
            raw_hash,
            verified_metrics,
            after_metrics,
            verified_price_rows_sha256,
        )

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
    "PERSONAL_MODEL_ASSESSMENT_SCHEMA_VERSION",
    "PersonalModelAssessmentV1",
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
