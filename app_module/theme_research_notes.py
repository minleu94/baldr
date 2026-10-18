"""沿既有Journal追加綁定精確題材版本的使用者研究筆記。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
import re
from typing import Any, Mapping, Sequence

from app_module.dtos.decision_continuity_dtos import (
    ACTION_NOTE,
    DECISION_CONTINUITY_RECORD_TYPE,
    IDENTITY_STATUS_UNKNOWN,
    DecisionContinuityRevision,
    DecisionIdentity,
)
from app_module.journal_service import JournalService
from app_module.theme_daily_service import ThemeDailyReport
from app_module.theme_research_snapshot import ThemeResearchSnapshot


THEME_RESEARCH_NOTE_SOURCE_TYPE = "theme_research_note.v1"
_MAX_NOTE_LENGTH = 8000
_DATA_DATE_TAG = "theme_research_data_date:"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ThemeResearchNote:
    revision_id: str
    snapshot_identity_sha256: str
    text: str
    data_date: str
    revision_of: str | None = None
    recorded_at: str = field(default="", compare=False)


class ThemeResearchNoteError(ValueError):
    """研究筆記內容或保存身份不一致。"""


class ThemeResearchNoteNotFound(ThemeResearchNoteError):
    """Journal沒有明選的筆記修訂。"""


class ThemeResearchNoteConflict(ThemeResearchNoteError):
    """修訂身份或原保存來源衝突。"""


class ThemeResearchNoteService:
    """在既有Journal修訂流保存使用者文字，不重讀或重建來源快照。

    傳入的ThemeResearchSnapshot須為呼叫者明選並讀回的版本；此層保存
    它的身份與資料日，不補造個股、推薦或策略資格。
    """

    def __init__(self, journal_service: JournalService):
        if not isinstance(journal_service, JournalService):
            raise TypeError("journal_service must be JournalService")
        self._journal_service = journal_service

    def save(
        self,
        snapshot: ThemeResearchSnapshot,
        text: str,
        *,
        revision_id: str,
        revision_of: str | None = None,
    ) -> ThemeResearchNote:
        snapshot_identity, data_date = _snapshot_identity(snapshot)
        note_text = _validated_note_text(text)
        resolved_revision_id = _required_revision_id(revision_id, "revision_id")
        resolved_revision_of = (
            _required_revision_id(revision_of, "revision_of")
            if revision_of is not None
            else None
        )
        if resolved_revision_id == resolved_revision_of:
            raise ThemeResearchNoteConflict("revision_of must differ from revision_id")

        history, history_token = self._journal_service.store.load_journal_snapshot()
        revisions = _decode_history(history)
        existing = [item for item in revisions if item.revision_id == resolved_revision_id]
        if existing:
            if len(existing) != 1:
                raise ThemeResearchNoteConflict("revision_id is ambiguous in journal history")
            saved = _decode_note_revision(existing[0])
            requested = ThemeResearchNote(
                revision_id=resolved_revision_id,
                snapshot_identity_sha256=snapshot_identity,
                text=note_text,
                data_date=data_date,
                revision_of=resolved_revision_of,
            )
            if saved != requested:
                raise ThemeResearchNoteConflict("revision_id already names different saved content")
            return saved

        # 每篇新筆記有自己的修訂根；同快照可保存多篇獨立觀察。
        note_root = sha256(
            f"{snapshot_identity}\0{resolved_revision_id}".encode("utf-8")
        ).hexdigest()
        entity_id = f"theme-research-note:{note_root}"
        if resolved_revision_of is not None:
            prior = [item for item in revisions if item.revision_id == resolved_revision_of]
            if len(prior) != 1:
                raise ThemeResearchNoteConflict("revision_of must identify one saved theme note")
            prior_note = _decode_note_revision(prior[0])
            if prior_note.snapshot_identity_sha256 != snapshot_identity:
                raise ThemeResearchNoteConflict("revision_of belongs to another theme snapshot")
            # 沿原根追加，也相容先前以快照身份作根的已保存筆記。
            entity_id = prior[0].entity_id

        identity = DecisionIdentity(
            source_snapshot_id=snapshot_identity,
            source_snapshot_hash=snapshot_identity,
        )
        try:
            revision = self._journal_service.record_research_action(
                ACTION_NOTE,
                identity,
                body=note_text,
                note=note_text,
                title="題材研究筆記",
                journal_id=entity_id,
                entity_id=entity_id,
                linked_type="theme_research_snapshot",
                linked_id=snapshot_identity,
                source_type=THEME_RESEARCH_NOTE_SOURCE_TYPE,
                source_id=snapshot_identity,
                tags=[_DATA_DATE_TAG + data_date],
                source_snapshot_id=snapshot_identity,
                source_snapshot_hash=snapshot_identity,
                revision_id=resolved_revision_id,
                continuity_event_id=resolved_revision_id,
                revision_of=resolved_revision_of or "",
                expected_history_token=history_token,
            )
        except RuntimeError as exc:
            if "journal_revision_event_conflict" in str(exc):
                raise ThemeResearchNoteConflict("journal revision identity conflicts with saved content") from exc
            raise

        saved = _decode_note_revision(revision)
        requested = ThemeResearchNote(
            revision_id=resolved_revision_id,
            snapshot_identity_sha256=snapshot_identity,
            text=note_text,
            data_date=data_date,
            revision_of=resolved_revision_of,
        )
        if saved != requested:
            raise ThemeResearchNoteConflict("journal returned a different saved theme note")
        return saved

    def get_note(self, revision_id: str) -> ThemeResearchNote:
        resolved_revision_id = _required_revision_id(revision_id, "revision_id")
        matches = [
            item for item in self._journal_service.list_decision_revisions()
            if item.revision_id == resolved_revision_id
        ]
        if not matches:
            raise ThemeResearchNoteNotFound("theme research note revision not found")
        if len(matches) != 1:
            raise ThemeResearchNoteConflict("revision_id is ambiguous in journal history")
        return _decode_note_revision(matches[0])

    def list_notes(self) -> tuple[ThemeResearchNote, ...]:
        revisions = self._journal_service.list_decision_revisions()
        revision_counts: dict[str, int] = {}
        for revision in revisions:
            revision_counts[revision.revision_id] = revision_counts.get(revision.revision_id, 0) + 1
        matching = [
            item for item in revisions
            if isinstance(item.payload, Mapping)
            and item.payload.get("source_type") == THEME_RESEARCH_NOTE_SOURCE_TYPE
        ]
        seen: set[str] = set()
        notes: list[ThemeResearchNote] = []
        for revision in matching:
            if revision.revision_id in seen or revision_counts[revision.revision_id] != 1:
                raise ThemeResearchNoteConflict("revision_id is ambiguous in journal history")
            seen.add(revision.revision_id)
            notes.append(_decode_note_revision(revision))
        return tuple(notes)


def _snapshot_identity(snapshot: ThemeResearchSnapshot) -> tuple[str, str]:
    if not isinstance(snapshot, ThemeResearchSnapshot):
        raise TypeError("snapshot must be a saved ThemeResearchSnapshot")
    identity = snapshot.identity_sha256
    if not isinstance(identity, str) or not _SHA256_RE.fullmatch(identity):
        raise ThemeResearchNoteError("theme snapshot identity must be a lowercase SHA-256")
    report = snapshot.report
    if not isinstance(report, ThemeDailyReport):
        raise ThemeResearchNoteError("theme snapshot report is missing or invalid")
    if not snapshot.mapping:
        raise ThemeResearchNoteError("theme snapshot source mapping is missing")
    if report.historical_pit_eligible is not False:
        raise ThemeResearchNoteError("theme research notes require historical_pit_eligible=False")
    if report.status != "current_research":
        raise ThemeResearchNoteError("theme snapshot report is not a loaded research report")
    if type(report.data_date) is not date:
        raise ThemeResearchNoteError("theme report data_date is missing or invalid")
    return identity, report.data_date.isoformat()


def _required_revision_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ThemeResearchNoteError(f"{field_name} must be a non-empty exact string")
    if len(value) > 256:
        raise ThemeResearchNoteError(f"{field_name} is too long")
    return value


def _validated_note_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ThemeResearchNoteError("theme research note text is required")
    if len(value) > _MAX_NOTE_LENGTH:
        raise ThemeResearchNoteError(f"theme research note exceeds {_MAX_NOTE_LENGTH} characters")
    return value


def _decode_history(history: Sequence[Mapping[str, Any]]) -> tuple[DecisionContinuityRevision, ...]:
    try:
        return tuple(
            DecisionContinuityRevision.from_mapping(item)
            for item in history
            if isinstance(item, Mapping)
            and item.get("record_type") == DECISION_CONTINUITY_RECORD_TYPE
        )
    except (TypeError, ValueError) as exc:
        raise ThemeResearchNoteConflict("journal history contains an invalid continuity revision") from exc


def _decode_note_revision(revision: DecisionContinuityRevision) -> ThemeResearchNote:
    payload = revision.payload
    if (
        revision.action != ACTION_NOTE
        or revision.entity_type != "journal"
        or not isinstance(payload, Mapping)
        or payload.get("source_type") != THEME_RESEARCH_NOTE_SOURCE_TYPE
    ):
        raise ThemeResearchNoteConflict("revision is not a theme research note")

    identity = revision.decision_identity
    source_identity = payload.get("source_id")
    source_snapshot_id = payload.get("source_snapshot_id")
    source_snapshot_hash = payload.get("source_snapshot_hash")
    if (
        not isinstance(source_identity, str)
        or not _SHA256_RE.fullmatch(source_identity)
        or source_snapshot_id != source_identity
        or source_snapshot_hash != source_identity
        or identity.source_snapshot_id != source_identity
        or identity.source_snapshot_hash != source_identity
    ):
        raise ThemeResearchNoteConflict("saved theme note source identity is inconsistent")
    if (
        identity.result_id
        or identity.stock_code
        or identity.decision_date
        or identity.identity_status != IDENTITY_STATUS_UNKNOWN
        or payload.get("stock_code", "") != ""
    ):
        raise ThemeResearchNoteConflict("theme note must not carry a stock or recommendation identity")

    # 來源資料日與實際保存時鐘分開；研究筆記不是該歷史日的交易決策。
    tags = payload.get("tags")
    if not isinstance(tags, (list, tuple)):
        raise ThemeResearchNoteConflict("saved theme note data-date tag is missing")
    data_tags = [tag[len(_DATA_DATE_TAG):] for tag in tags
                 if isinstance(tag, str) and tag.startswith(_DATA_DATE_TAG)]
    if len(data_tags) != 1:
        raise ThemeResearchNoteConflict("saved theme note data-date tag is ambiguous")
    data_date = _canonical_date(data_tags[0])
    try:
        recorded = datetime.fromisoformat(revision.created_at)
        if recorded.tzinfo is None or recorded.utcoffset() is None:
            raise ValueError("missing timezone")
    except ValueError as exc:
        raise ThemeResearchNoteConflict("saved theme note recorded clock is invalid") from exc
    text = payload.get("body")
    if not isinstance(text, str) or not text.strip() or len(text) > _MAX_NOTE_LENGTH:
        raise ThemeResearchNoteConflict("saved theme note text is missing or invalid")
    if revision.note != text:
        raise ThemeResearchNoteConflict("saved theme note body differs from its revision note")
    if payload.get("journal_id") != revision.entity_id:
        raise ThemeResearchNoteConflict("saved theme note journal identity is inconsistent")
    if (
        payload.get("linked_type") != "theme_research_snapshot"
        or payload.get("linked_id") != source_identity
    ):
        raise ThemeResearchNoteConflict("saved theme note link identity is inconsistent")

    return ThemeResearchNote(
        revision_id=revision.revision_id,
        snapshot_identity_sha256=source_identity,
        text=text,
        data_date=data_date,
        revision_of=revision.revision_of or None,
        recorded_at=revision.created_at,
    )


def _canonical_date(value: Any) -> str:
    if not isinstance(value, str):
        raise ThemeResearchNoteConflict("saved theme note data date is missing")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ThemeResearchNoteConflict("saved theme note data date is invalid") from exc
    if parsed.isoformat() != value:
        raise ThemeResearchNoteConflict("saved theme note data date is not canonical")
    return value
