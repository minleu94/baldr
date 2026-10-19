"""沿用既有 Journal 保存完整個股報告上的使用者判斷。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
import re
from typing import Any

from app_module.dtos.decision_continuity_dtos import (
    ACTION_NOTE,
    DECISION_CONTINUITY_RECORD_TYPE,
    IDENTITY_STATUS_UNKNOWN,
    DecisionContinuityRevision,
    DecisionIdentity,
)
from app_module.journal_service import JournalService
from app_module.stock_research_report_snapshot_codec import (
    STOCK_RESEARCH_REPORT_PROJECTION_SNAPSHOT_SCHEMA_V1,
    StockResearchReportProjectionSnapshot,
    read_stock_research_report_projection_snapshot,
)


STOCK_RESEARCH_REPORT_NOTE_SOURCE_TYPE = "stock_research_report_note.v1"
_LINKED_TYPE = "stock_research_report_projection"
_NOTE_TITLE = "個股研究判斷"
_MAX_NOTE_LENGTH = 8000
_MAX_REVISION_ID_LENGTH = 256
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOURNAL_MIRROR_FIELDS = (
    "journal_id",
    "portfolio_id",
    "title",
    "body",
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


@dataclass(frozen=True, slots=True)
class StockResearchReportNote:
    revision_id: str
    snapshot: StockResearchReportProjectionSnapshot
    text: str
    revision_of: str | None = None
    recorded_at: str = field(default="", compare=False)


class StockResearchReportNoteError(ValueError):
    """個股研究判斷或其保存報告無法驗證。"""


class StockResearchReportNoteNotFound(StockResearchReportNoteError):
    """Journal 中沒有指定的報告判斷或報告身份。"""


class StockResearchReportNoteConflict(StockResearchReportNoteError):
    """報告判斷修訂、來源或 Journal 歷史身份互相衝突。"""


@dataclass(frozen=True, slots=True)
class _StoredNote:
    revision: DecisionContinuityRevision
    note: StockResearchReportNote


class StockResearchReportNoteService:
    """以既有 Journal 的 append-only 修訂流保存一般個股報告判斷。"""

    def __init__(self, journal_service: JournalService) -> None:
        if not isinstance(journal_service, JournalService):
            raise TypeError("journal_service must be JournalService")
        self._journal_service = journal_service

    def save(
        self,
        snapshot: StockResearchReportProjectionSnapshot,
        text: str,
        *,
        revision_id: str,
        revision_of: str | None = None,
    ) -> StockResearchReportNote:
        verified_snapshot = _verified_snapshot(snapshot)
        note_text = _validated_note_text(text)
        resolved_revision_id = _required_revision_id(revision_id, "revision_id")
        resolved_revision_of = (
            _required_revision_id(revision_of, "revision_of")
            if revision_of is not None
            else None
        )
        if resolved_revision_id == resolved_revision_of:
            raise StockResearchReportNoteConflict(
                "revision_of must differ from revision_id"
            )

        history, history_token = self._load_history_snapshot()
        stored_notes, revision_id_counts = _decode_note_history(history)
        existing_notes = [
            item.note
            for item in stored_notes
            if item.note.revision_id == resolved_revision_id
        ]
        if len(existing_notes) > 1:
            raise StockResearchReportNoteConflict(
                "revision_id is ambiguous in journal history"
            )
        if existing_notes:
            saved = existing_notes[0]
            requested = StockResearchReportNote(
                revision_id=resolved_revision_id,
                snapshot=verified_snapshot,
                text=note_text,
                revision_of=resolved_revision_of,
            )
            if saved != requested:
                raise StockResearchReportNoteConflict(
                    "revision_id already names different saved content"
                )
            return saved
        if revision_id_counts.get(resolved_revision_id, 0):
            raise StockResearchReportNoteConflict(
                "revision_id is already used by another Journal action"
            )

        entity_id = _root_entity_id(verified_snapshot, resolved_revision_id)
        if resolved_revision_of is not None:
            parents = [
                item
                for item in stored_notes
                if item.note.revision_id == resolved_revision_of
            ]
            if len(parents) != 1:
                raise StockResearchReportNoteConflict(
                    "revision_of must identify one saved report note"
                )
            parent = parents[0]
            if not _same_snapshot(parent.note.snapshot, verified_snapshot):
                raise StockResearchReportNoteConflict(
                    "revision_of belongs to another exact report snapshot"
                )
            if any(
                item.note.revision_of == resolved_revision_of
                for item in stored_notes
            ):
                raise StockResearchReportNoteConflict(
                    "revision_of is not the current report note head"
                )
            entity_id = parent.revision.entity_id

        identity_sha256 = verified_snapshot.identity_sha256
        identity = DecisionIdentity(
            stock_code=verified_snapshot.stock_code,
            source_snapshot_id=identity_sha256,
            source_snapshot_hash=identity_sha256,
            identity_status=IDENTITY_STATUS_UNKNOWN,
        )
        try:
            revision = self._journal_service.record_research_action(
                ACTION_NOTE,
                identity,
                body=note_text,
                note=note_text,
                title=_NOTE_TITLE,
                journal_id=entity_id,
                entity_id=entity_id,
                linked_type=_LINKED_TYPE,
                linked_id=identity_sha256,
                tags=[],
                source_type=STOCK_RESEARCH_REPORT_NOTE_SOURCE_TYPE,
                source_id=identity_sha256,
                source_snapshot_id=identity_sha256,
                source_snapshot_hash=identity_sha256,
                revision_id=resolved_revision_id,
                continuity_event_id=resolved_revision_id,
                revision_of=resolved_revision_of or "",
                stock_research_report_snapshot=verified_snapshot,
                expected_history_token=history_token,
            )
        except (RuntimeError, ValueError) as exc:
            if _is_journal_conflict(exc):
                raise StockResearchReportNoteConflict(
                    f"journal append conflict: {exc}"
                ) from exc
            if "legacy_journal_read_only" in str(exc):
                raise StockResearchReportNoteError(
                    "selected Journal is read-only"
                ) from exc
            raise StockResearchReportNoteError(
                f"journal append failed: {type(exc).__name__}"
            ) from exc

        saved = _decode_note_revision(revision)
        requested = StockResearchReportNote(
            revision_id=resolved_revision_id,
            snapshot=verified_snapshot,
            text=note_text,
            revision_of=resolved_revision_of,
        )
        if (
            saved != requested
            or revision.entity_id != entity_id
            or revision.revision_of != (resolved_revision_of or "")
        ):
            raise StockResearchReportNoteConflict(
                "Journal returned a different saved stock research report note"
            )
        return saved

    def get_note(self, revision_id: str) -> StockResearchReportNote:
        resolved_revision_id = _required_revision_id(revision_id, "revision_id")
        stored_notes, _revision_id_counts = self._load_notes()
        matches = [
            item.note
            for item in stored_notes
            if item.note.revision_id == resolved_revision_id
        ]
        if not matches:
            raise StockResearchReportNoteNotFound(
                "stock research report note revision not found"
            )
        if len(matches) != 1:
            raise StockResearchReportNoteConflict(
                "revision_id is ambiguous in journal history"
            )
        return matches[0]

    def list_notes(
        self,
        *,
        stock_code: str = "",
    ) -> tuple[StockResearchReportNote, ...]:
        if type(stock_code) is not str or stock_code.strip() != stock_code:
            raise StockResearchReportNoteError("stock_code must be an exact string")
        stored_notes, _revision_id_counts = self._load_notes()
        return tuple(
            item.note
            for item in stored_notes
            if not stock_code or item.note.snapshot.stock_code == stock_code
        )

    def read_exact(self, identity_sha256: str) -> StockResearchReportProjectionSnapshot:
        if type(identity_sha256) is not str or _SHA256_RE.fullmatch(identity_sha256) is None:
            raise StockResearchReportNoteError(
                "identity_sha256 must be lowercase SHA-256"
            )
        stored_notes, _revision_id_counts = self._load_notes()
        matches = [
            item.note.snapshot
            for item in stored_notes
            if item.note.snapshot.identity_sha256 == identity_sha256
        ]
        if not matches:
            raise StockResearchReportNoteNotFound(
                "stock research report snapshot not found"
            )
        canonical_json = matches[0].canonical_json
        if any(item.canonical_json != canonical_json for item in matches[1:]):
            raise StockResearchReportNoteConflict(
                "one report identity names different canonical snapshots"
            )
        return _verified_snapshot(matches[0])

    def _load_notes(
        self,
    ) -> tuple[tuple[_StoredNote, ...], dict[str, int]]:
        history, _history_token = self._load_history_snapshot()
        return _decode_note_history(history)

    def _load_history_snapshot(self) -> tuple[list[dict[str, Any]], str]:
        try:
            return self._journal_service.store.load_journal_snapshot()
        except (RuntimeError, ValueError) as exc:
            if _is_journal_conflict(exc):
                raise StockResearchReportNoteConflict(
                    f"journal history conflict: {exc}"
                ) from exc
            raise StockResearchReportNoteError(
                f"journal history read failed: {type(exc).__name__}"
            ) from exc


def _verified_snapshot(
    snapshot: StockResearchReportProjectionSnapshot,
) -> StockResearchReportProjectionSnapshot:
    if type(snapshot) is not StockResearchReportProjectionSnapshot:
        raise StockResearchReportNoteError(
            "snapshot must be a typed stock research report projection"
        )
    try:
        decoded = read_stock_research_report_projection_snapshot(
            snapshot.canonical_json,
            expected_identity_sha256=snapshot.identity_sha256,
        )
    except (TypeError, ValueError) as exc:
        raise StockResearchReportNoteError(
            "stock research report snapshot failed canonical SHA verification"
        ) from exc
    if snapshot.stock_code != decoded.stock_code:
        raise StockResearchReportNoteError(
            "snapshot stock_code differs from its canonical report"
        )
    return decoded


def _required_revision_id(value: Any, field_name: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise StockResearchReportNoteError(
            f"{field_name} must be a non-empty exact string"
        )
    if len(value) > _MAX_REVISION_ID_LENGTH:
        raise StockResearchReportNoteError(f"{field_name} is too long")
    return value


def _validated_note_text(value: Any) -> str:
    if type(value) is not str or not value.strip():
        raise StockResearchReportNoteError("stock research report note text is required")
    if len(value) > _MAX_NOTE_LENGTH:
        raise StockResearchReportNoteError(
            f"stock research report note exceeds {_MAX_NOTE_LENGTH} characters"
        )
    return value


def _same_snapshot(
    left: StockResearchReportProjectionSnapshot,
    right: StockResearchReportProjectionSnapshot,
) -> bool:
    return (
        left.identity_sha256 == right.identity_sha256
        and left.canonical_json == right.canonical_json
    )


def _root_entity_id(
    snapshot: StockResearchReportProjectionSnapshot,
    revision_id: str,
) -> str:
    root_hash = sha256(
        f"{snapshot.identity_sha256}\0{revision_id}".encode("utf-8")
    ).hexdigest()
    return f"stock-research-report-note:{root_hash}"


def _is_report_note_record(record: Mapping[str, Any]) -> bool:
    payload = record.get("payload")
    return (
        record.get("source_type") == STOCK_RESEARCH_REPORT_NOTE_SOURCE_TYPE
        or record.get("linked_type") == _LINKED_TYPE
        or (
            isinstance(payload, Mapping)
            and (
                payload.get("source_type") == STOCK_RESEARCH_REPORT_NOTE_SOURCE_TYPE
                or "stock_research_report_snapshot" in payload
            )
        )
    )


def _decode_note_history(
    history: Sequence[Mapping[str, Any]],
) -> tuple[tuple[_StoredNote, ...], dict[str, int]]:
    """讀取本服務修訂，保留 Journal 內其他 source type 的隔離。"""

    revision_id_counts: dict[str, int] = {}
    raw_notes: list[tuple[Mapping[str, Any], DecisionContinuityRevision]] = []
    for record in history:
        if not isinstance(record, Mapping):
            continue
        record_type = record.get("record_type")
        revision_id = record.get("revision_id")
        if (
            record_type == DECISION_CONTINUITY_RECORD_TYPE
            and type(revision_id) is str
            and revision_id
        ):
            revision_id_counts[revision_id] = revision_id_counts.get(revision_id, 0) + 1

        is_report_note = _is_report_note_record(record)
        if not is_report_note:
            continue
        if record_type != DECISION_CONTINUITY_RECORD_TYPE:
            raise StockResearchReportNoteConflict(
                "report note Journal record has an invalid record_type"
            )
        try:
            revision = DecisionContinuityRevision.from_mapping(record)
        except (TypeError, ValueError) as exc:
            raise StockResearchReportNoteConflict(
                "Journal history contains an invalid report note revision"
            ) from exc
        raw_notes.append((record, revision))

    stored: dict[str, _StoredNote] = {}
    for record, revision in raw_notes:
        if revision_id_counts.get(revision.revision_id, 0) != 1:
            raise StockResearchReportNoteConflict(
                "revision_id is ambiguous in journal history"
            )
        note = _decode_note_revision(revision, raw_record=record)
        if revision.revision_id in stored:
            raise StockResearchReportNoteConflict(
                "revision_id is ambiguous in report note history"
            )
        stored[revision.revision_id] = _StoredNote(revision=revision, note=note)

    children: dict[str, int] = {}
    for item in stored.values():
        note = item.note
        revision = item.revision
        if note.revision_of is None:
            if revision.entity_id != _root_entity_id(note.snapshot, note.revision_id):
                raise StockResearchReportNoteConflict(
                    "saved report note root identity is inconsistent"
                )
            continue
        parent = stored.get(note.revision_of)
        if parent is None:
            raise StockResearchReportNoteConflict(
                "saved report note parent is missing or belongs to another source"
            )
        if (
            not _same_snapshot(parent.note.snapshot, note.snapshot)
            or parent.revision.entity_id != revision.entity_id
        ):
            raise StockResearchReportNoteConflict(
                "saved report note parent identity is inconsistent"
            )
        children[note.revision_of] = children.get(note.revision_of, 0) + 1
        if children[note.revision_of] > 1:
            raise StockResearchReportNoteConflict(
                "saved report note revision chain branches"
            )

    for note in (item.note for item in stored.values()):
        visited: set[str] = set()
        current_id = note.revision_id
        while True:
            if current_id in visited:
                raise StockResearchReportNoteConflict(
                    "saved report note revision chain contains a cycle"
                )
            visited.add(current_id)
            current = stored.get(current_id)
            if current is None:
                raise StockResearchReportNoteConflict(
                    "saved report note parent is missing"
                )
            parent_id = current.note.revision_of
            if parent_id is None:
                break
            current_id = parent_id

    return tuple(stored.values()), revision_id_counts


def _decode_note_revision(
    revision: DecisionContinuityRevision,
    *,
    raw_record: Mapping[str, Any] | None = None,
) -> StockResearchReportNote:
    payload = revision.payload
    if (
        revision.action != ACTION_NOTE
        or revision.entity_type != "journal"
        or not isinstance(payload, Mapping)
        or payload.get("source_type") != STOCK_RESEARCH_REPORT_NOTE_SOURCE_TYPE
    ):
        raise StockResearchReportNoteConflict(
            "revision is not a stock research report note"
        )

    snapshot_payload = payload.get("stock_research_report_snapshot")
    expected_keys = {"schema_version", "identity_sha256", "canonical_json"}
    if (
        not isinstance(snapshot_payload, Mapping)
        or set(snapshot_payload) != expected_keys
        or snapshot_payload.get("schema_version")
        != STOCK_RESEARCH_REPORT_PROJECTION_SNAPSHOT_SCHEMA_V1
        or type(snapshot_payload.get("identity_sha256")) is not str
        or _SHA256_RE.fullmatch(snapshot_payload["identity_sha256"]) is None
        or type(snapshot_payload.get("canonical_json")) is not str
    ):
        raise StockResearchReportNoteConflict(
            "saved stock research report snapshot payload is invalid"
        )
    try:
        snapshot = read_stock_research_report_projection_snapshot(
            snapshot_payload["canonical_json"],
            expected_identity_sha256=snapshot_payload["identity_sha256"],
        )
    except (TypeError, ValueError) as exc:
        raise StockResearchReportNoteConflict(
            "saved stock research report snapshot failed SHA verification"
        ) from exc

    text = payload.get("body")
    if (
        type(text) is not str
        or not text.strip()
        or len(text) > _MAX_NOTE_LENGTH
        or revision.note != text.strip()
    ):
        raise StockResearchReportNoteConflict(
            "saved stock research report note text is missing or inconsistent"
        )
    try:
        _required_revision_id(revision.revision_id, "revision_id")
        if revision.revision_of:
            _required_revision_id(revision.revision_of, "revision_of")
    except StockResearchReportNoteError as exc:
        raise StockResearchReportNoteConflict(
            "saved stock research report note revision id is invalid"
        ) from exc
    if (
        revision.revision_of == revision.revision_id
        or revision.continuity_event_id != revision.revision_id
    ):
        raise StockResearchReportNoteConflict(
            "saved stock research report note revision chain is invalid"
        )
    try:
        recorded = datetime.fromisoformat(revision.created_at)
        if recorded.tzinfo is None or recorded.utcoffset() is None:
            raise ValueError("missing timezone")
    except (TypeError, ValueError) as exc:
        raise StockResearchReportNoteConflict(
            "saved stock research report note recorded clock is invalid"
        ) from exc
    if (
        payload.get("created_at") != revision.created_at
        or payload.get("updated_at") != revision.created_at
    ):
        raise StockResearchReportNoteConflict(
            "saved stock research report note recorded clock is inconsistent"
        )

    identity_sha256 = snapshot.identity_sha256
    identity = revision.decision_identity
    if (
        identity.stock_code != snapshot.stock_code
        or identity.result_id
        or identity.decision_date
        or identity.identity_status != IDENTITY_STATUS_UNKNOWN
        or identity.source_snapshot_id != identity_sha256
        or identity.source_snapshot_hash != identity_sha256
        or payload.get("stock_code") != snapshot.stock_code
        or payload.get("source_id") != identity_sha256
        or payload.get("source_snapshot_id") != identity_sha256
        or payload.get("source_snapshot_hash") != identity_sha256
        or payload.get("journal_id") != revision.entity_id
        or payload.get("linked_type") != _LINKED_TYPE
        or payload.get("linked_id") != identity_sha256
        or payload.get("source_type") != STOCK_RESEARCH_REPORT_NOTE_SOURCE_TYPE
        or payload.get("title") != _NOTE_TITLE
        or payload.get("body") != text
        or "personalization_action" in payload
        or "personal_recommendation_choice" in payload
    ):
        raise StockResearchReportNoteConflict(
            "saved stock research report note identity is inconsistent"
        )
    tags = payload.get("tags")
    if not isinstance(tags, (list, tuple)) or tags:
        raise StockResearchReportNoteConflict(
            "saved stock research report note tags must be empty"
        )

    if raw_record is not None:
        _validate_journal_record_mirrors(
            raw_record,
            revision=revision,
            payload=payload,
            text=text,
            snapshot=snapshot,
        )

    return StockResearchReportNote(
        revision_id=revision.revision_id,
        snapshot=snapshot,
        text=text,
        revision_of=revision.revision_of or None,
        recorded_at=revision.created_at,
    )


def _validate_journal_record_mirrors(
    raw_record: Mapping[str, Any],
    *,
    revision: DecisionContinuityRevision,
    payload: Mapping[str, Any],
    text: str,
    snapshot: StockResearchReportProjectionSnapshot,
) -> None:
    identity = revision.decision_identity
    expected_outer = {
        "record_type": DECISION_CONTINUITY_RECORD_TYPE,
        "revision_id": revision.revision_id,
        "continuity_event_id": revision.continuity_event_id,
        "revision_of": revision.revision_of,
        "action": ACTION_NOTE,
        "entity_type": "journal",
        "entity_id": revision.entity_id,
        "decision_identity": identity.to_dict(),
        "result_id": "",
        "stock_code": snapshot.stock_code,
        "source_snapshot_id": snapshot.identity_sha256,
        "source_snapshot_hash": snapshot.identity_sha256,
        "decision_date": "",
        "identity_status": IDENTITY_STATUS_UNKNOWN,
        "note": text.strip(),
        "created_at": revision.created_at,
    }
    for key, expected in expected_outer.items():
        if raw_record.get(key) != expected:
            raise StockResearchReportNoteConflict(
                f"saved report note Journal {key} is inconsistent"
            )

    serialized_payload = revision.to_dict().get("payload")
    if (
        not isinstance(serialized_payload, Mapping)
        or raw_record.get("payload") != serialized_payload
    ):
        raise StockResearchReportNoteConflict(
            "saved report note Journal payload differs from its typed revision"
        )
    for key in _JOURNAL_MIRROR_FIELDS:
        if raw_record.get(key) != serialized_payload.get(key):
            raise StockResearchReportNoteConflict(
                f"saved report note Journal mirror {key} is inconsistent"
            )


def _is_journal_conflict(exc: BaseException) -> bool:
    message = str(exc)
    return any(
        marker in message
        for marker in (
            "journal_revision_event_conflict",
            "journal_revision_chain_conflict",
            "journal_revision_stream_conflict",
        )
    )
