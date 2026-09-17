"""Append-only JSONL storage for the Phase 4.1 Portfolio MVP."""

from contextlib import contextmanager
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
import time
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Sequence

from app_module.dtos.decision_continuity_dtos import (
    ACTION_ADDED,
    ACTION_NOTE,
    ACTION_REMOVED,
    ACTION_UPDATED,
    DECISION_CONTINUITY_RECORD_TYPE,
    DECISION_CONTINUITY_TOMBSTONE_ACTIONS,
    DecisionContinuityRevision,
)


if os.name == "nt":
    import msvcrt
    _fcntl: Any = None
else:  # pragma: no cover - exercised on POSIX CI only
    import fcntl
    _fcntl = fcntl


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


@contextmanager
def _interprocess_lock(path: Path, *, timeout_seconds: float = 10.0) -> Iterator[None]:
    """Lock a sibling file using OS file locking, without PID guesses."""

    lock_path = path.with_name(f".{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:  # pragma: no cover - exercised on POSIX CI only
                    _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"JSONL lock timeout: {path}")
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover - exercised on POSIX CI only
                    _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)
            finally:
                handle.close()
    except Exception:
        handle.close()
        raise


def _canonical_record(record: Mapping[str, Any]) -> str:
    return json.dumps(_json_safe(dict(record)), ensure_ascii=False, sort_keys=True, allow_nan=False)


def _journal_history_token(records: Sequence[Mapping[str, Any]]) -> str:
    raw = "\n".join(_canonical_record(record) for record in records)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_revision_record(record: Mapping[str, Any]) -> bool:
    return str(record.get("record_type", "")) == DECISION_CONTINUITY_RECORD_TYPE


def _materialize_journal_revision(
    raw: Mapping[str, Any], revision: DecisionContinuityRevision
) -> dict[str, Any]:
    payload = dict(revision.payload)
    # JournalService writes both payload and top-level fields. Keeping this
    # allow-list makes a partial/corrupt record unable to inject projection keys.
    journal_fields = (
        "journal_id",
        "portfolio_id",
        "body",
        "title",
        "stock_code",
        "linked_type",
        "linked_id",
        "tags",
        "source_type",
        "source_id",
        "source_snapshot_id",
        "source_snapshot_hash",
        "created_at",
        "updated_at",
        "schema_version",
    )
    for key in journal_fields:
        if key in raw:
            payload[key] = raw[key]
    payload["journal_id"] = revision.entity_id
    payload["record_type"] = "journal_entry"
    payload["revision_id"] = revision.revision_id
    payload["continuity_event_id"] = revision.continuity_event_id
    payload["revision_of"] = revision.revision_of
    payload["action"] = revision.action
    payload["next_review_at"] = revision.next_review_at
    payload["actor"] = revision.actor
    identity = revision.decision_identity.to_dict()
    payload["decision_identity"] = identity
    payload["result_id"] = identity["result_id"]
    payload["stock_code"] = identity["stock_code"] or payload.get("stock_code", "")
    payload["source_snapshot_id"] = identity["source_snapshot_id"] or payload.get(
        "source_snapshot_id", ""
    )
    payload["source_snapshot_hash"] = identity["source_snapshot_hash"] or payload.get(
        "source_snapshot_hash", ""
    )
    payload["decision_date"] = identity["decision_date"]
    payload["identity_status"] = identity["identity_status"]
    return _json_safe(payload)


def project_journal_records(
    records: Sequence[Mapping[str, Any]], *, include_history: bool = False
) -> list[dict[str, Any]]:
    """Build active journal projection while retaining history elsewhere.

    Legacy rows remain valid active entries. Continuity revisions with decision
    entity types are history-only research actions; only journal notes and
    journal tombstones affect the active note projection.
    """

    if include_history:
        return [dict(record) for record in records]

    active: dict[tuple[str, str], dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    heads: dict[tuple[str, str], str] = {}
    seen_revision_ids: dict[str, str] = {}

    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            raise ValueError(f"journal record {index} must be an object")
        if not _is_revision_record(raw):
            journal_id = str(raw.get("journal_id", "") or "")
            if journal_id:
                active[("journal", journal_id)] = dict(raw)
            else:
                anonymous.append(dict(raw))
            continue

        try:
            revision = DecisionContinuityRevision.from_mapping(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid journal continuity revision at {index}") from exc
        revision_id = revision.revision_id
        canonical = _canonical_record(raw)
        previous = seen_revision_ids.get(revision_id)
        if previous is not None:
            if previous != canonical:
                raise RuntimeError("journal_revision_event_conflict")
            continue
        seen_revision_ids[revision_id] = canonical
        key = (revision.entity_type, revision.entity_id)
        current_head = heads.get(key, "")
        if current_head:
            if revision.revision_of != current_head:
                raise ValueError("journal_revision_chain_conflict")
        elif revision.revision_of:
            raise ValueError("journal_revision_chain_conflict")
        heads[key] = revision_id

        if revision.entity_type != "journal":
            continue
        if revision.action in DECISION_CONTINUITY_TOMBSTONE_ACTIONS:
            active.pop(key, None)
        elif revision.action in {ACTION_NOTE, ACTION_ADDED, ACTION_UPDATED}:
            active[key] = _materialize_journal_revision(raw, revision)

    return anonymous + list(active.values())


class PortfolioJsonlStore:
    """Small storage adapter kept behind app_module services."""

    def __init__(self, output_root: Path, *, journal_file: Path | None = None):
        self.portfolio_dir = Path(output_root) / "portfolio"
        if journal_file is None:
            self.portfolio_dir.mkdir(parents=True, exist_ok=True)
        self.trades_file = self.portfolio_dir / "trades.jsonl"
        self.journal_file = (
            Path(journal_file).expanduser().resolve()
            if journal_file is not None
            else self.portfolio_dir / "journal_entries.jsonl"
        )
        if journal_file is not None:
            self.journal_file.parent.mkdir(parents=True, exist_ok=True)

    def append_trade(self, trade: Dict[str, Any]) -> None:
        self._append_jsonl(self.trades_file, trade)

    def load_trades(self) -> List[Dict[str, Any]]:
        with _interprocess_lock(self.trades_file):
            return list(self._read_jsonl_unlocked(self.trades_file))

    def append_journal_entry(self, entry: Dict[str, Any]) -> None:
        self._append_jsonl(self.journal_file, entry)

    def append_journal_revision(
        self,
        revision: Mapping[str, Any],
        *,
        expected_history_token: str | None = None,
    ) -> None:
        self.append_journal_revisions(
            [revision], expected_history_token=expected_history_token
        )

    def append_journal_revisions(
        self,
        revisions: Iterable[Mapping[str, Any]],
        *,
        expected_history_token: str | None = None,
    ) -> None:
        items = [dict(item) for item in revisions]
        if not items:
            return
        for item in items:
            if not _is_revision_record(item):
                raise ValueError("journal revision record_type is required")
            DecisionContinuityRevision.from_mapping(item)
            _canonical_record(item)

        with _interprocess_lock(self.journal_file):
            existing = self._read_jsonl_unlocked(self.journal_file)
            if (
                expected_history_token is not None
                and _journal_history_token(existing) != expected_history_token
            ):
                raise RuntimeError("journal_revision_stream_conflict")
            # Validate the complete current stream before deciding whether any
            # new bytes may be appended.
            project_journal_records(existing)
            by_id = {
                str(item.get("revision_id")): _canonical_record(item)
                for item in existing
                if _is_revision_record(item) and item.get("revision_id")
            }
            lines: list[str] = []
            pending: dict[str, str] = {}
            for item in items:
                revision_id = str(item.get("revision_id", ""))
                canonical = _canonical_record(item)
                prior = by_id.get(revision_id) or pending.get(revision_id)
                if prior is not None:
                    if prior != canonical:
                        raise RuntimeError("journal_revision_event_conflict")
                    continue
                pending[revision_id] = canonical
                lines.append(canonical)
            if not lines:
                return
            # Validate the resulting chain before writing any bytes. This keeps
            # a stale revision or malformed batch from partially advancing the
            # append-only stream.
            project_journal_records(existing + [dict(item) for item in items])
            self.journal_file.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_line_separator_unlocked(self.journal_file)
            with open(self.journal_file, "a", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
                handle.write("\n")

    def load_journal_entries(self) -> List[Dict[str, Any]]:
        with _interprocess_lock(self.journal_file):
            records = self._read_jsonl_unlocked(self.journal_file)
        return project_journal_records(records)

    def load_journal_history(self) -> List[Dict[str, Any]]:
        """Return raw parsed records, including legacy rows and tombstones."""

        with _interprocess_lock(self.journal_file):
            return list(self._read_jsonl_unlocked(self.journal_file))

    def load_journal_snapshot(self) -> tuple[List[Dict[str, Any]], str]:
        """Read history and a compare-and-append token under one lock."""

        with _interprocess_lock(self.journal_file):
            records = list(self._read_jsonl_unlocked(self.journal_file))
            return records, _journal_history_token(records)

    def load_decision_revisions(self) -> List[DecisionContinuityRevision]:
        records = self.load_journal_history()
        result: list[DecisionContinuityRevision] = []
        for index, record in enumerate(records):
            if not _is_revision_record(record):
                continue
            try:
                result.append(DecisionContinuityRevision.from_mapping(record))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid journal continuity revision at {index}") from exc
        return result

    def overwrite_trades(self, trades: List[Dict[str, Any]]) -> None:
        """重寫所有交易紀錄（legacy API；continuity writer 不使用）。"""

        self._overwrite_jsonl(self.trades_file, trades)

    def overwrite_journal_entries(self, entries: List[Dict[str, Any]]) -> None:
        """重寫所有日記紀錄（legacy API；JournalService 不使用）。"""

        self._overwrite_jsonl(self.journal_file, entries)

    def _overwrite_jsonl(self, path: Path, entries: Iterable[Mapping[str, Any]]) -> None:
        lines = [_canonical_record(item) for item in entries]
        path.parent.mkdir(parents=True, exist_ok=True)
        with _interprocess_lock(path):
            with open(path, "w", encoding="utf-8") as handle:
                if lines:
                    handle.write("\n".join(lines))
                    handle.write("\n")

    def _append_jsonl(self, path: Path, item: Dict[str, Any]) -> None:
        line = _canonical_record(item)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _interprocess_lock(path):
            # Never append behind a partial/corrupt stream; importantly, this
            # read does not rewrite any pre-existing bytes.
            self._read_jsonl_unlocked(path)
            self._ensure_line_separator_unlocked(path)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")

    @staticmethod
    def _ensure_line_separator_unlocked(path: Path) -> None:
        """Separate a valid final line that lacks its trailing newline."""

        if not path.exists() or path.stat().st_size == 0:
            return
        with open(path, "rb") as handle:
            handle.seek(-1, os.SEEK_END)
            last = handle.read(1)
        if last != b"\n":
            with open(path, "ab") as handle:
                handle.write(b"\n")

    def _read_jsonl(self, path: Path) -> Iterable[Dict[str, Any]]:
        with _interprocess_lock(path):
            return self._read_jsonl_unlocked(path)

    @staticmethod
    def _read_jsonl_unlocked(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []

        records: list[dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    item = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
                if not isinstance(item, dict):
                    raise ValueError(f"Invalid JSONL object at {path}:{line_number}")
                records.append(item)
        return records
