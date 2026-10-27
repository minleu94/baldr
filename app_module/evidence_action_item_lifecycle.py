"""Gate 2 action-item status history in a separate append-only projection."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator

from app_module.weekly_review_history_source import resolve_weekly_review_working_copy_path


SCHEMA_VERSION = "evidence-action-item-lifecycle.v1"
ALLOWED_STATUSES = frozenset({"open", "reviewed", "dismissed", "follow_up"})
_GENESIS_HASH = "sha256:" + "0" * 64
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class EvidenceActionItemLifecycleError(ValueError):
    """Action-item source or lifecycle projection is not safe to use."""


class EvidenceActionItemLifecycleService:
    """Read action items from an explicit working copy and append review events."""

    def __init__(
        self,
        config: Any,
        *,
        db_path: str | Path,
        projection_path: str | Path,
    ) -> None:
        self.db_path = resolve_weekly_review_working_copy_path(config, db_path)
        self.projection_path = _resolve_projection_path(projection_path, self.db_path, config)
        self._source_identity = _path_identity(self.db_path)

    def list_action_items(self) -> list[dict[str, Any]]:
        """Return current action rows and projected statuses without creating schema."""

        actions = _read_action_items(self.db_path)
        projection = _read_projection(self.projection_path, self._source_identity)
        latest = _latest_events(projection["events"])
        history: dict[str, list[dict[str, Any]]] = {}
        for event in projection["events"]:
            history.setdefault(str(event["action_item_id"]), []).append(dict(event))
        source_action_ids = {action["action_item_id"] for action in actions}
        if set(latest) - source_action_ids:
            raise EvidenceActionItemLifecycleError("source working-copy is missing a previously reviewed action item")
        result = []
        for action in actions:
            event = latest.get(action["action_item_id"])
            action_hash = _hash_json(action)
            if event is not None and event["action_payload_sha256"] != action_hash:
                raise EvidenceActionItemLifecycleError("action source row changed after prior review")
            result.append(
                {
                    **action,
                    "action_payload_sha256": action_hash,
                    "lifecycle_status": event["to_status"] if event else "open",
                    "latest_event": dict(event) if event else None,
                    "lifecycle_history": history.get(action["action_item_id"], []),
                }
            )
        return result

    def record_transition(
        self,
        action_item_id: str,
        *,
        new_status: str,
        actor_name: str,
        actor_role: str,
        note: str,
        recorded_at: str | None = None,
    ) -> dict[str, Any]:
        """Append one hash-chained human event; never modify the SQLite source."""

        action_id = _required_text(action_item_id, "action_item_id")
        status = _required_text(new_status, "new_status").casefold()
        actor = _required_text(actor_name, "actor_name")
        role = _required_text(actor_role, "actor_role")
        event_note = _required_text(note, "note")
        if status not in ALLOWED_STATUSES - {"open"}:
            raise EvidenceActionItemLifecycleError("new_status must be reviewed, dismissed, or follow_up")

        actions = _read_action_items(self.db_path)
        matches = [action for action in actions if action["action_item_id"] == action_id]
        if len(matches) != 1:
            raise EvidenceActionItemLifecycleError("action_item_id must identify exactly one source row")
        action = matches[0]
        action_hash = _hash_json(action)
        timestamp = _validate_timestamp(recorded_at)
        target = self.projection_path

        with _projection_lock(target.with_name(target.name + ".lock")):
            fresh_actions = _read_action_items(self.db_path)
            fresh_matches = [item for item in fresh_actions if item["action_item_id"] == action_id]
            if len(fresh_matches) != 1 or _hash_json(fresh_matches[0]) != action_hash:
                raise EvidenceActionItemLifecycleError("action source row changed during review; reload before saving")
            payload = _read_projection(target, self._source_identity)
            events = payload["events"]
            prior_for_action = [event for event in events if event["action_item_id"] == action_id]
            if prior_for_action:
                if prior_for_action[-1]["action_payload_sha256"] != action_hash:
                    raise EvidenceActionItemLifecycleError("action source row changed after prior review")
                current_status = prior_for_action[-1]["to_status"]
            else:
                current_status = "open"
            if not _transition_allowed(current_status, status):
                raise EvidenceActionItemLifecycleError(
                    f"invalid action-item transition: {current_status} -> {status}"
                )

            previous_hash = events[-1]["event_sha256"] if events else _GENESIS_HASH
            if events:
                previous_timestamp = datetime.fromisoformat(
                    str(events[-1]["recorded_at"]).replace("Z", "+00:00")
                )
                current_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if current_timestamp < previous_timestamp:
                    raise EvidenceActionItemLifecycleError("recorded_at precedes the latest lifecycle event")
            event: dict[str, Any] = {
                "event_id": f"eail_{sha256(os.urandom(32)).hexdigest()[:24]}",
                "recorded_at": timestamp,
                "action_item_id": action_id,
                "review_id": action["review_id"],
                "review_hash": action["review_hash"],
                "period_start": action["period_start"],
                "period_end": action["period_end"],
                "source_database_identity": self._source_identity,
                "action_payload_sha256": action_hash,
                "from_status": current_status,
                "to_status": status,
                "actor_name": actor,
                "actor_role": role,
                "note": event_note,
                "previous_event_sha256": previous_hash,
                "formal_credit_authorized": False,
                "production_scheduler_allowed": False,
            }
            event["event_sha256"] = _hash_json(event)
            next_payload = {
                "schema_version": SCHEMA_VERSION,
                "source_database_identity": self._source_identity,
                "candidate_only": True,
                "formal_credit_authorized": False,
                "production_scheduler_allowed": False,
                "downstream_eligibility": "none",
                "events": [*events, event],
            }
            _atomic_replace_json(target, next_payload)
        return dict(event)


def _read_action_items(path: Path) -> list[dict[str, Any]]:
    """Read a checkpointed working copy; never create schema or accept concurrent writers."""

    sidecar_stamps = _sqlite_sidecar_stamps(path)
    if _has_nonempty_sqlite_sidecar(sidecar_stamps):
        raise EvidenceActionItemLifecycleError("working-copy must be checkpointed before Action Item review")
    source_stamp = _sqlite_file_stamp(path)
    uri = path.as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = 1")
        connection.execute("BEGIN")
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        required = {"decision_quality_action_items", "decision_quality_reviews"}
        if not required.issubset(tables):
            raise EvidenceActionItemLifecycleError("working-copy action-item tables are missing")
        rows = connection.execute(
            """
            SELECT a.action_item_id, a.review_id, r.review_hash,
                   r.review_period_start AS period_start,
                   r.review_period_end AS period_end,
                   a.item_id, a.description, a.status, a.owner,
                   a.metadata_json, a.created_at
            FROM decision_quality_action_items AS a
            JOIN decision_quality_reviews AS r ON r.review_id = a.review_id
            ORDER BY a.created_at ASC, a.action_item_id ASC
            """
        ).fetchall()
        actions = []
        for row in rows:
            action = dict(row)
            if not _SHA256_PATTERN.fullmatch(str(action.get("review_hash") or "")):
                raise EvidenceActionItemLifecycleError("source review hash is invalid")
            try:
                metadata = json.loads(str(action.pop("metadata_json") or "{}"))
            except json.JSONDecodeError as exc:
                raise EvidenceActionItemLifecycleError("action-item metadata is invalid JSON") from exc
            if not isinstance(metadata, dict):
                raise EvidenceActionItemLifecycleError("action-item metadata must be an object")
            action["metadata_json"] = metadata
            if str(action["status"]) != "open":
                raise EvidenceActionItemLifecycleError("source action item is not in its original open state")
            actions.append(action)
        connection.execute("COMMIT")
        sidecar_stamps_after = _sqlite_sidecar_stamps(path)
        if (
            _sqlite_file_stamp(path) != source_stamp
            or sidecar_stamps_after != sidecar_stamps
            or _has_nonempty_sqlite_sidecar(sidecar_stamps_after)
        ):
            raise EvidenceActionItemLifecycleError("working-copy changed while reading Action Items")
        return actions
    except sqlite3.Error as exc:
        raise EvidenceActionItemLifecycleError("unable to read working-copy action items") from exc
    finally:
        if "connection" in locals():
            connection.close()


def _sqlite_file_stamp(path: Path) -> tuple[int, int, int, int, int]:
    stat = path.stat()
    return (
        int(stat.st_dev),
        int(stat.st_ino),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        int(stat.st_ctime_ns),
    )


def _sqlite_sidecar_stamps(path: Path) -> dict[str, tuple[int, int, int, int, int] | None]:
    stamps: dict[str, tuple[int, int, int, int, int] | None] = {}
    for suffix in ("-wal", "-journal"):
        sidecar = Path(str(path) + suffix)
        try:
            stamps[suffix] = _sqlite_file_stamp(sidecar)
        except FileNotFoundError:
            stamps[suffix] = None
    return stamps


def _has_nonempty_sqlite_sidecar(
    stamps: dict[str, tuple[int, int, int, int, int] | None],
) -> bool:
    return any(stamp is not None and stamp[2] > 0 for stamp in stamps.values())


def _resolve_projection_path(path: str | Path, db_path: Path, config: Any) -> Path:
    if not str(path).strip():
        raise EvidenceActionItemLifecycleError("action-item projection path is required")
    raw_target = Path(path).expanduser()
    if raw_target.is_symlink():
        raise EvidenceActionItemLifecycleError("action-item projection cannot be a symbolic link")
    target = raw_target.resolve(strict=False)
    if target == db_path:
        raise EvidenceActionItemLifecycleError("action-item projection must be separate from source DB")
    source_sidecars = {Path(str(db_path) + suffix).resolve(strict=False) for suffix in ("-wal", "-shm", "-journal")}
    if target in source_sidecars:
        raise EvidenceActionItemLifecycleError("action-item projection must not overwrite SQLite sidecars")
    configured_approval = os.environ.get("WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH", "").strip()
    if configured_approval and target == Path(configured_approval).expanduser().resolve(strict=False):
        raise EvidenceActionItemLifecycleError("action-item projection must be separate from Owner approval projection")
    if target.suffix.casefold() != ".json":
        raise EvidenceActionItemLifecycleError("action-item projection file must use the .json extension")
    formal_roots = {
        Path(config.data_root).expanduser().resolve(strict=False),
        Path(os.environ.get("DATA_ROOT", "F:/Min/Python/Project/FA_Data")).expanduser().resolve(strict=False),
        Path("F:/Min/Python/Project/FA_Data").resolve(strict=False),
    }
    if any(target == root or root in target.parents for root in formal_roots):
        raise EvidenceActionItemLifecycleError("action-item projection cannot be stored under a formal data root")
    normalized = target.as_posix().casefold()
    if target.name.casefold() == "twstock.db" or "/fa_data/sqlite/" in normalized or "/data_root/sqlite/" in normalized:
        raise EvidenceActionItemLifecycleError("action-item projection cannot target a formal database")
    if target.exists() and not target.is_file():
        raise EvidenceActionItemLifecycleError("action-item projection target must be a file")
    if not target.parent.is_dir():
        raise EvidenceActionItemLifecycleError("action-item projection parent directory must exist")
    return target


def _read_projection(path: Path, source_identity: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "source_database_identity": source_identity,
            "candidate_only": True,
            "formal_credit_authorized": False,
            "production_scheduler_allowed": False,
            "downstream_eligibility": "none",
            "events": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceActionItemLifecycleError("action-item projection cannot be read") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceActionItemLifecycleError("action-item projection schema is unsupported")
    if payload.get("source_database_identity") != source_identity:
        raise EvidenceActionItemLifecycleError("action-item projection belongs to another working copy")
    if payload.get("candidate_only") is not True or payload.get("downstream_eligibility") != "none":
        raise EvidenceActionItemLifecycleError("action-item projection must remain candidate-only")
    if payload.get("formal_credit_authorized") is not False or payload.get("production_scheduler_allowed") is not False:
        raise EvidenceActionItemLifecycleError("action-item projection safety flags must remain false")
    events = payload.get("events")
    if not isinstance(events, list):
        raise EvidenceActionItemLifecycleError("action-item projection events must be an array")
    _validate_event_chain(events, source_identity)
    return payload


def _validate_event_chain(events: list[Any], source_identity: str) -> None:
    previous_hash = _GENESIS_HASH
    previous_timestamp: datetime | None = None
    latest_status: dict[str, str] = {}
    payload_hashes: dict[str, str] = {}
    seen_ids: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            raise EvidenceActionItemLifecycleError("action-item projection contains an invalid event")
        event_id = str(event.get("event_id") or "")
        action_id = str(event.get("action_item_id") or "")
        if not event_id or event_id in seen_ids or not action_id:
            raise EvidenceActionItemLifecycleError("action-item projection contains duplicate or missing identity")
        seen_ids.add(event_id)
        if event.get("source_database_identity") != source_identity:
            raise EvidenceActionItemLifecycleError("action-item event source identity mismatch")
        if event.get("formal_credit_authorized") is not False or event.get("production_scheduler_allowed") is not False:
            raise EvidenceActionItemLifecycleError("action-item event safety flags must remain false")
        if event.get("previous_event_sha256") != previous_hash:
            raise EvidenceActionItemLifecycleError("action-item event chain is broken")
        saved_hash = event.get("event_sha256")
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        if saved_hash != _hash_json(body):
            raise EvidenceActionItemLifecycleError("action-item event hash is invalid")
        from_status = str(event.get("from_status") or "")
        to_status = str(event.get("to_status") or "")
        current = latest_status.get(action_id, "open")
        if from_status != current or not _transition_allowed(current, to_status):
            raise EvidenceActionItemLifecycleError("action-item event transition history is invalid")
        payload_hash = str(event.get("action_payload_sha256") or "")
        if not _SHA256_PATTERN.fullmatch(payload_hash):
            raise EvidenceActionItemLifecycleError("action-item payload hash is invalid")
        if not _SHA256_PATTERN.fullmatch(str(event.get("review_hash") or "")):
            raise EvidenceActionItemLifecycleError("action-item event review hash is invalid")
        if action_id in payload_hashes and payload_hashes[action_id] != payload_hash:
            raise EvidenceActionItemLifecycleError("action-item source identity changed within history")
        payload_hashes[action_id] = payload_hash
        latest_status[action_id] = to_status
        timestamp_text = _validate_timestamp(str(event.get("recorded_at") or ""))
        timestamp = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
        if previous_timestamp is not None and timestamp < previous_timestamp:
            raise EvidenceActionItemLifecycleError("action-item event timestamps are out of order")
        previous_timestamp = timestamp
        for field in ("review_id", "review_hash", "period_start", "period_end", "actor_name", "actor_role", "note"):
            if not str(event.get(field) or "").strip():
                raise EvidenceActionItemLifecycleError(f"action-item event {field} is required")
        previous_hash = str(saved_hash)


def _latest_events(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for event in events:
        latest[str(event["action_item_id"])] = event
    return latest


def _transition_allowed(current: str, new: str) -> bool:
    if new not in ALLOWED_STATUSES - {"open"}:
        return False
    transitions = {
        "open": {"reviewed", "dismissed", "follow_up"},
        "reviewed": {"follow_up"},
        "dismissed": {"follow_up"},
        "follow_up": {"reviewed", "dismissed"},
    }
    return new in transitions.get(current, set())


def _validate_timestamp(value: str | None) -> str:
    timestamp = value.strip() if value is not None else _utc_now()
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceActionItemLifecycleError("recorded_at must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceActionItemLifecycleError("recorded_at must include a timezone")
    return timestamp


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _required_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise EvidenceActionItemLifecycleError(f"{field} is required")
    return text


def _path_identity(path: Path) -> str:
    normalized = os.path.normcase(str(path.resolve())).casefold()
    return _hash_json({"resolved_source_path": normalized})


def _hash_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def _atomic_replace_json(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        with temp.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def _projection_lock(path: Path) -> Iterator[None]:
    """Cross-process advisory lock shared by all writers for one projection."""

    if path.is_symlink():
        raise EvidenceActionItemLifecycleError("action-item projection lock cannot be a symbolic link")
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if handle.read(1) == b"":
                handle.seek(0)
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl_lock: Any = __import__("fcntl")
            fcntl_lock.flock(handle.fileno(), fcntl_lock.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl_unlock: Any = __import__("fcntl")
                fcntl_unlock.flock(handle.fileno(), fcntl_unlock.LOCK_UN)
        finally:
            handle.close()
