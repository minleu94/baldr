"""UX23 明示 registry 的唯讀 metadata；不載入模型或授予任何資格。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Mapping, NoReturn

# 僅使用無 I/O 的 immutable DTO 與轉移表；不使用同模組 registry／初始化器。
from ml_module.model_lifecycle_registry import ModelLifecycleEvent, _ALLOWED_TRANSITIONS
from ml_module.model_prediction_registries import MLModelRecord


MAX_DATABASE_BYTES = 32 * 1024 * 1024
MAX_PAYLOAD_BYTES = 256 * 1024
MAX_EVENTS = 256
MAX_EXPORT_BYTES = 64 * 1024
_EXPORT_SCHEMA = "rule-research-shadow-lifecycle-export.v1"
_MODEL_FIELDS = frozenset(field.name for field in fields(MLModelRecord))
_EVENT_FIELDS = frozenset(field.name for field in fields(ModelLifecycleEvent))
_SCHEMA = {
    "ml_models": (("model_id", "TEXT", 0, 1), ("payload_json", "TEXT", 1, 0)),
    "ml_model_lifecycle_events": (
        ("event_id", "TEXT", 0, 1), ("model_id", "TEXT", 1, 0),
        ("event_type", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
        ("payload_json", "TEXT", 1, 0),
    ),
}


class ModelRegistryReadError(ValueError):
    """穩定缺件代碼；不回傳 SQLite 私有內容或部分 DTO。"""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class ModelRegistryReadonlyResult:
    model: MLModelRecord
    events: tuple[ModelLifecycleEvent, ...]
    lifecycle_export: dict[str, Any]
    source_sha256: str
    unverified_metadata_fields: tuple[str, ...]

    @property
    def current_status(self) -> str | None:
        return self.events[-1].event_type if self.events else None

    @property
    def safety_flags(self) -> dict[str, object]:
        return {
            "research_only": True, "shadow_enabled": False,
            "training_eligible": False, "historical_pit_eligible": False,
            "formal_eligible": False, "natural_authority": False,
            "execution_eligible": False, "production_eligible": False,
            "production_action_allowed": False, "production_blend_alpha_bp": 0,
            "qualified_count": 0, "selection_status": "unknown",
        }


def _fail(code: str) -> NoReturn:
    raise ModelRegistryReadError(code)


def _clock(value: object) -> datetime:
    if not isinstance(value, str):
        _fail("registry_time_invalid")
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        raise ModelRegistryReadError("registry_time_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("registry_time_invalid")
    return parsed.astimezone(timezone.utc)


def _object(raw: object, names: frozenset[str]) -> dict[str, Any]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        _fail("registry_payload_bound")
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                _fail("registry_payload_duplicate_key")
            result[key] = value
        return result
    try:
        value = json.loads(str(raw), object_pairs_hook=pairs)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, ModelRegistryReadError):
            raise
        raise ModelRegistryReadError("registry_payload_invalid") from None
    if not isinstance(value, dict) or set(value) != names:
        _fail("registry_payload_schema_mismatch")
    return dict(value)


def _source(path: Path) -> tuple[str, int, int, int]:
    # WAL 開啟即可能建立 shm；在 SQLite connect 前拒絕。
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & 0x400):
            _fail("registry_link_rejected")
    if not path.is_file():
        _fail("registry_missing")
    if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        _fail("registry_sidecar_requires_snapshot")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DATABASE_BYTES:
        _fail("registry_database_bound")
    with path.open("rb") as handle:
        raw = handle.read(MAX_DATABASE_BYTES + 1)
    if len(raw) > MAX_DATABASE_BYTES:
        _fail("registry_database_bound")
    if raw[:16] != b"SQLite format 3\x00":
        _fail("registry_corrupt")
    if raw[18:20] != b"\x01\x01":
        _fail("registry_sidecar_requires_snapshot")
    return hashlib.sha256(raw).hexdigest(), info.st_size, info.st_mtime_ns, info.st_ino


class ModelRegistryReadonly:
    """只接受明示絕對 DB 路徑；沒有預設資料根、寫入或控制方法。"""

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        if not path.is_absolute():
            _fail("registry_explicit_absolute_path_required")
        self._path = path

    def read(
        self, model_id: str, *, expected_metadata: Mapping[str, Any], observed_at: str,
    ) -> ModelRegistryReadonlyResult:
        """pin 比對只證明已存 metadata；audit／target 聲明保持未驗證。"""
        if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 256:
            _fail("registry_model_id_invalid")
        observed = _clock(observed_at)
        try:
            # JSON 深複製 caller pin，避免共享可變物件；不反序列化模型。
            pin = json.loads(json.dumps(dict(expected_metadata), allow_nan=False))
            if not _MODEL_FIELDS <= pin.keys() or set(pin) - _MODEL_FIELDS - {"training_audit", "target_contract"}:
                _fail("registry_expected_metadata_invalid")
            before = _source(self._path)
            connection = sqlite3.connect(
                self._path.as_uri() + "?mode=ro", uri=True, timeout=0,
                isolation_level=None,
            )
            try:
                connection.execute("PRAGMA query_only=ON")
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.set_authorizer(_authorize)
                connection.execute("BEGIN")
                model, events = self._read(connection, model_id, observed)
            finally:
                connection.close()
            if _source(self._path) != before:
                _fail("registry_source_changed")
            metadata = asdict(model)
            metadata["feature_names"] = list(model.feature_names)
            if any(pin[key] != metadata[key] or type(pin[key]) is not type(metadata[key])
                   for key in _MODEL_FIELDS):
                _fail("registry_version_mismatch")
            export = {
                "schema_version": _EXPORT_SCHEMA, "model_id": model.model_id,
                "dataset_id": model.dataset_id, "artifact_hash": model.artifact_hash,
                "metadata": pin, "events": [event.to_dict() for event in events],
            }
            if len(json.dumps(export, ensure_ascii=False).encode("utf-8")) > MAX_EXPORT_BYTES:
                _fail("registry_export_bound")
            return ModelRegistryReadonlyResult(
                model, events, export, before[0], tuple(sorted(set(pin) - _MODEL_FIELDS)),
            )
        except ModelRegistryReadError:
            raise
        except sqlite3.Error as exc:
            code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
            reason = "registry_locked" if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED} else "registry_unreadable"
            raise ModelRegistryReadError(reason) from None
        except OSError:
            raise ModelRegistryReadError("registry_unreadable") from None
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ModelRegistryReadError("registry_metadata_invalid") from None

    @staticmethod
    def _read(
        connection: sqlite3.Connection, model_id: str, observed: datetime,
    ) -> tuple[MLModelRecord, tuple[ModelLifecycleEvent, ...]]:
        for table, expected in _SCHEMA.items():
            kind = connection.execute(
                "SELECT type FROM sqlite_master WHERE name=?", (table,),
            ).fetchone()
            columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
            if kind != ("table",) or tuple((row[1], row[2], row[3], row[5]) for row in columns) != expected:
                _fail("registry_schema_mismatch")
        rows = connection.execute(
            "SELECT model_id, payload_json FROM ml_models WHERE model_id=? LIMIT 2", (model_id,),
        ).fetchall()
        if not rows:
            _fail("registry_model_missing")
        if len(rows) != 1:
            _fail("registry_model_identity_invalid")
        payload = _object(rows[0][1], _MODEL_FIELDS)
        for name in _MODEL_FIELDS - {"feature_names", "calibration_id", "shadow_only", "production_eligible"}:
            if not isinstance(payload[name], str) or not payload[name].strip():
                _fail("registry_metadata_invalid")
        if payload["model_id"] != model_id:
            _fail("registry_model_identity_invalid")
        if payload["lifecycle_status"] != "shadow_candidate":
            _fail("registry_unknown_model_status")
        if payload["shadow_only"] is not True or payload["production_eligible"] is not False:
            _fail("registry_qualification_rejected")
        if not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", payload["artifact_hash"]):
            _fail("registry_metadata_invalid")
        names = payload["feature_names"]
        if not isinstance(names, list) or not names or any(not isinstance(name, str) or not name.strip() for name in names):
            _fail("registry_metadata_invalid")
        if payload["calibration_id"] is not None and (not isinstance(payload["calibration_id"], str) or not payload["calibration_id"].strip()):
            _fail("registry_metadata_invalid")
        if _clock(payload["created_at"]) > observed:
            _fail("registry_future_metadata")
        model = MLModelRecord(**{**payload, "feature_names": tuple(names)})
        event_rows = connection.execute(
            "SELECT event_id, model_id, event_type, created_at, payload_json "
            "FROM ml_model_lifecycle_events WHERE model_id=? ORDER BY rowid LIMIT ?",
            (model_id, MAX_EVENTS + 1),
        ).fetchall()
        if len(event_rows) > MAX_EVENTS:
            _fail("registry_event_bound")
        events: list[ModelLifecycleEvent] = []
        current: str | None = None
        previous = _clock(model.created_at)
        identities: set[str] = set()
        for row in event_rows:
            raw = _object(row[4], _EVENT_FIELDS)
            if any(not isinstance(value, str) or not value.strip() for value in raw.values()):
                _fail("registry_event_invalid")
            if tuple(raw[key] for key in ("event_id", "model_id", "event_type", "created_at")) != tuple(row[:4]):
                _fail("registry_event_identity_mismatch")
            if raw["event_type"] not in _ALLOWED_TRANSITIONS:
                _fail("registry_unknown_event_status")
            event_time = _clock(raw["created_at"])
            if event_time < previous or event_time > observed:
                _fail("registry_event_time_invalid")
            if raw["event_id"] in identities or raw["event_type"] not in _ALLOWED_TRANSITIONS[current]:
                _fail("registry_transition_invalid")
            event = ModelLifecycleEvent(**raw)
            events.append(event)
            identities.add(event.event_id)
            current, previous = event.event_type, event_time
        return model, tuple(events)


def _authorize(action: int, first: str | None, second: str | None,
               database: str | None, trigger: str | None) -> int:
    """只允許固定 SELECT、schema inspection 與 deferred read transaction。"""
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ and first in {*_SCHEMA, "sqlite_master"}:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and first == "table_info" and second in _SCHEMA:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and first == "query_only" and second is None:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_TRANSACTION and first == "BEGIN":
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY
