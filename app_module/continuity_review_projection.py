"""Read-only projection for the existing decision-continuity Journal stream.

This module deliberately reads the append-only JSONL file directly.  The
Workbench is a query surface, so constructing ``JournalService`` or
``PortfolioJsonlStore`` here would be an unsafe read path: both constructors
can create output directories and the latter owns write-oriented helpers.

The projection does not create a reminder store or an outcome index.  It only
projects the latest valid review schedule for each exact
``(result_id, stock_code)`` candidate and keeps the user's accepted/skipped
intent as a separate field.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app_module.dtos.decision_continuity_dtos import (
    ACTION_ACCEPTED,
    ACTION_CLEARED,
    ACTION_REMOVED,
    ACTION_REVIEW_SCHEDULED,
    ACTION_SKIPPED,
    DECISION_CONTINUITY_RECORD_TYPE,
    DecisionContinuityRevision,
    IDENTITY_STATUS_LINKED,
)
from app_module.portfolio_store import project_journal_records


ASIA_TAIPEI = ZoneInfo("Asia/Taipei")
CONTINUITY_STREAM_READY = "ready"
CONTINUITY_STREAM_MISSING = "missing"
CONTINUITY_STREAM_EMPTY = "empty"
CONTINUITY_STREAM_INVALID = "invalid"

CONTINUITY_DUE_SCHEDULED = "scheduled"
CONTINUITY_DUE = "due"
CONTINUITY_DUE_OVERDUE = "overdue"
CONTINUITY_DUE_INVALID = "invalid"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalize_strings(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(_text(value) for value in values if _text(value))


@dataclass(frozen=True)
class ContinuityReviewItem:
    """One exact candidate's latest persisted review reminder.

    ``decision_status`` is intentionally independent from ``reminder_status``:
    setting a future review must not overwrite an accepted/skipped intent.
    ``recorded_next_review_at`` preserves the value written in Journal while
    ``next_review_at`` is the same instant normalized to Asia/Taipei for UI and
    comparison.
    """

    result_id: str
    stock_code: str
    decision_status: str = "unrecorded"
    reminder_status: str = CONTINUITY_DUE_INVALID
    due_status: str = CONTINUITY_DUE_INVALID
    next_review_at: str = ""
    recorded_next_review_at: str = ""
    revision_id: str = ""
    reminder_revision_id: str = ""
    revision_of: str = ""
    continuity_event_id: str = ""
    source_snapshot_id: str = ""
    source_snapshot_hash: str = ""
    decision_date: str = ""
    source_trace: str = ""
    identity_status: str = IDENTITY_STATUS_LINKED
    note: str = ""
    history_count: int = 0
    diagnostics: tuple[str, ...] = field(default_factory=tuple)
    read_only: bool = True

    def __post_init__(self) -> None:
        result_id = _text(self.result_id)
        stock_code = _text(self.stock_code)
        if not result_id or not stock_code:
            raise ValueError("continuity review item requires result_id and stock_code")
        if _text(self.identity_status) != IDENTITY_STATUS_LINKED:
            raise ValueError("continuity review item requires linked identity")
        object.__setattr__(self, "result_id", result_id)
        object.__setattr__(self, "stock_code", stock_code)
        object.__setattr__(self, "decision_status", _text(self.decision_status) or "unrecorded")
        reminder_status = _text(self.reminder_status) or CONTINUITY_DUE_INVALID
        due_status = _text(self.due_status) or reminder_status
        object.__setattr__(self, "reminder_status", reminder_status)
        object.__setattr__(self, "due_status", due_status)
        for field_name in (
            "next_review_at",
            "recorded_next_review_at",
            "revision_id",
            "reminder_revision_id",
            "revision_of",
            "continuity_event_id",
            "source_snapshot_id",
            "source_snapshot_hash",
            "decision_date",
            "source_trace",
            "identity_status",
            "note",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name)))
        object.__setattr__(self, "history_count", max(0, int(self.history_count)))
        object.__setattr__(self, "diagnostics", _normalize_strings(self.diagnostics))
        object.__setattr__(self, "read_only", True)

    @property
    def candidate_key(self) -> tuple[str, str]:
        return self.result_id, self.stock_code

    @property
    def candidate_key_text(self) -> str:
        return f"{self.result_id}:{self.stock_code}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "stock_code": self.stock_code,
            "candidate_key": self.candidate_key_text,
            "decision_status": self.decision_status,
            "reminder_status": self.reminder_status,
            "due_status": self.due_status,
            "next_review_at": self.next_review_at,
            "recorded_next_review_at": self.recorded_next_review_at,
            "revision_id": self.revision_id,
            "reminder_revision_id": self.reminder_revision_id,
            "revision_of": self.revision_of,
            "continuity_event_id": self.continuity_event_id,
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_hash": self.source_snapshot_hash,
            "decision_date": self.decision_date,
            "source_trace": self.source_trace,
            "identity_status": self.identity_status,
            "note": self.note,
            "history_count": self.history_count,
            "diagnostics": list(self.diagnostics),
            "read_only": self.read_only,
            "writes_allowed": False,
        }


@dataclass(frozen=True)
class ContinuityReviewProjectionResult:
    """Read result plus stream diagnostics; no mutation capability."""

    items: tuple[ContinuityReviewItem, ...] = ()
    diagnostics: tuple[str, ...] = ()
    stream_status: str = CONTINUITY_STREAM_READY
    source_path: str = ""
    read_only: bool = True
    writes_allowed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "diagnostics", _normalize_strings(self.diagnostics))
        object.__setattr__(self, "stream_status", _text(self.stream_status) or CONTINUITY_STREAM_READY)
        object.__setattr__(self, "source_path", _text(self.source_path))
        object.__setattr__(self, "read_only", True)
        object.__setattr__(self, "writes_allowed", False)

    @property
    def due_items(self) -> tuple[ContinuityReviewItem, ...]:
        """Alias used by callers that only need the reminder queue."""

        return self.items

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "diagnostics": list(self.diagnostics),
            "stream_status": self.stream_status,
            "source_path": self.source_path,
            "read_only": self.read_only,
            "writes_allowed": self.writes_allowed,
        }


@dataclass
class _CandidateState:
    result_id: str
    stock_code: str
    provenance: dict[str, str] = field(default_factory=dict)
    revisions: list[DecisionContinuityRevision] = field(default_factory=list)
    latest: DecisionContinuityRevision | None = None
    latest_intent: DecisionContinuityRevision | None = None
    latest_reminder: DecisionContinuityRevision | None = None
    reminder_cleared: bool = False
    conflict_reason: str = ""


class ContinuityReviewProjectionService:
    """Project existing Journal revisions without opening a writer path."""

    def __init__(self, journal_path: str | Path) -> None:
        self.journal_path = Path(journal_path)

    @classmethod
    def from_output_root(cls, output_root: str | Path) -> "ContinuityReviewProjectionService":
        return cls(Path(output_root) / "portfolio" / "journal_entries.jsonl")

    def project(
        self,
        *,
        as_of: datetime | str | None = None,
    ) -> ContinuityReviewProjectionResult:
        source_path = str(self.journal_path)
        as_of_time, as_of_error = _coerce_as_of(as_of)
        if as_of_error:
            return ContinuityReviewProjectionResult(
                diagnostics=(f"continuity_review_as_of_invalid:{as_of_error}",),
                stream_status=CONTINUITY_STREAM_INVALID,
                source_path=source_path,
            )

        if not self.journal_path.is_file():
            return ContinuityReviewProjectionResult(
                diagnostics=("continuity_review_journal_missing",),
                stream_status=CONTINUITY_STREAM_MISSING,
                source_path=source_path,
            )

        records, read_error = self._read_jsonl()
        if read_error:
            return ContinuityReviewProjectionResult(
                diagnostics=(read_error,),
                stream_status=CONTINUITY_STREAM_INVALID,
                source_path=source_path,
            )
        if not records:
            return ContinuityReviewProjectionResult(
                stream_status=CONTINUITY_STREAM_EMPTY,
                source_path=source_path,
            )

        # Validate the complete stream, including non-continuity legacy rows,
        # before projecting any candidate.  A partial queue from a corrupt
        # chain could otherwise look like a trustworthy reminder list.
        try:
            project_journal_records(records)
        except Exception as exc:  # noqa: BLE001 - fail closed at read boundary
            return ContinuityReviewProjectionResult(
                diagnostics=(
                    "continuity_review_stream_invalid:"
                    f"{type(exc).__name__}:{_first_line(exc)}",
                ),
                stream_status=CONTINUITY_STREAM_INVALID,
                source_path=source_path,
            )

        diagnostics: list[str] = []
        candidates: dict[tuple[str, str], _CandidateState] = {}
        seen_revision_ids: set[str] = set()
        for index, raw in enumerate(records):
            if not isinstance(raw, Mapping):
                # project_journal_records already catches this.  Keep this
                # guard local so a future projector change remains safe.
                diagnostics.append(f"continuity_review_record_not_object:{index}")
                continue
            if _text(raw.get("record_type")) != DECISION_CONTINUITY_RECORD_TYPE:
                continue
            try:
                revision = DecisionContinuityRevision.from_mapping(raw)
            except (TypeError, ValueError) as exc:
                # This should have been caught above; do not expose a partial
                # queue if the two readers ever drift.
                return ContinuityReviewProjectionResult(
                    diagnostics=(
                        "continuity_review_revision_invalid:"
                        f"{index}:{_first_line(exc)}",
                    ),
                    stream_status=CONTINUITY_STREAM_INVALID,
                    source_path=source_path,
                )
            if revision.revision_id in seen_revision_ids:
                # The canonical stream projector already verified identical
                # duplicate IDs.  They are one immutable event, not two rows.
                continue
            seen_revision_ids.add(revision.revision_id)

            # The whole stream was validated above, but a historical query
            # must only see revisions that existed at its observation time.
            # Otherwise a later reschedule/clear/intent would rewrite the
            # state of a previous day.  Missing or naive timestamps cannot be
            # safely ordered and are therefore excluded fail-closed.
            created_at, created_at_error = _normalize_created_at(revision.created_at)
            if created_at_error:
                diagnostics.append(
                    f"continuity_review_revision_time_invalid:{revision.revision_id}:"
                    f"{created_at_error}"
                )
                continue
            if created_at > as_of_time:
                diagnostics.append(
                    f"continuity_review_revision_after_as_of:{revision.revision_id}"
                )
                continue

            identity = revision.decision_identity
            if not identity.is_linked:
                diagnostics.append(
                    f"continuity_review_identity_skipped:{revision.revision_id}:"
                    f"{identity.identity_status}"
                )
                continue
            candidate_key = identity.candidate_key
            if candidate_key is None:
                diagnostics.append(f"continuity_review_identity_skipped:{revision.revision_id}:unknown")
                continue
            expected_entity_id = f"decision-candidate:{candidate_key[0]}:{candidate_key[1]}"
            if revision.entity_type == "decision" and revision.entity_id != expected_entity_id:
                diagnostics.append(
                    f"continuity_review_entity_skipped:{revision.revision_id}"
                )
                continue
            if revision.entity_type == "journal":
                # Notes remain in the formal Journey's active journal
                # projection.  They are not reminder state, but their
                # explicit candidate provenance still participates in the
                # same conflict check as DecisionContinuityController.
                linked_id = _text(revision.payload.get("linked_id", ""))
                if linked_id and linked_id not in {expected_entity_id, candidate_key[0]}:
                    continue
            elif revision.entity_type != "decision":
                continue
            state = candidates.setdefault(
                candidate_key,
                _CandidateState(result_id=candidate_key[0], stock_code=candidate_key[1]),
            )
            state.revisions.append(revision)
            self._record_provenance_conflict(state, revision)
            if revision.entity_type != "decision":
                continue
            state.latest = revision
            if revision.action in {ACTION_ACCEPTED, ACTION_SKIPPED}:
                state.latest_intent = revision
            elif revision.action == ACTION_REVIEW_SCHEDULED:
                state.latest_reminder = revision
                state.reminder_cleared = False
            elif revision.action in {ACTION_CLEARED, ACTION_REMOVED}:
                state.latest_reminder = None
                state.reminder_cleared = True

        items: list[ContinuityReviewItem] = []
        for key, state in candidates.items():
            if state.conflict_reason:
                diagnostics.append(
                    f"continuity_review_identity_conflict:{key[0]}:{key[1]}"
                    f":{state.conflict_reason}"
                )
                continue
            reminder = state.latest_reminder
            if reminder is None or state.reminder_cleared:
                continue
            item = self._build_item(
                state,
                reminder,
                as_of=as_of_time,
                source_path=source_path,
            )
            items.append(item)

        items.sort(key=lambda item: (_due_sort_rank(item.due_status), item.result_id, item.stock_code))
        return ContinuityReviewProjectionResult(
            items=tuple(items),
            diagnostics=tuple(diagnostics),
            stream_status=CONTINUITY_STREAM_READY,
            source_path=source_path,
        )

    # A short alias makes the read boundary explicit at call sites.
    read = project

    def _read_jsonl(self) -> tuple[list[dict[str, Any]], str]:
        records: list[dict[str, Any]] = []
        try:
            with self.journal_path.open("r", encoding="utf-8") as handle:
                for index, line in enumerate(handle):
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        value = json.loads(text)
                    except json.JSONDecodeError as exc:
                        return [], f"continuity_review_json_invalid:{index}:{_first_line(exc)}"
                    if not isinstance(value, dict):
                        return [], f"continuity_review_record_not_object:{index}"
                    records.append(value)
        except (OSError, UnicodeError) as exc:
            return [], f"continuity_review_journal_unavailable:{type(exc).__name__}:{_first_line(exc)}"
        return records, ""

    @staticmethod
    def _record_provenance_conflict(
        state: _CandidateState,
        revision: DecisionContinuityRevision,
    ) -> None:
        identity = revision.decision_identity
        for field_name in ("source_snapshot_id", "source_snapshot_hash", "decision_date"):
            actual = _text(getattr(identity, field_name))
            if not actual:
                continue
            previous = state.provenance.get(field_name, "")
            if previous and previous != actual and not state.conflict_reason:
                state.conflict_reason = (
                    f"{field_name}:previous={previous};current={actual}"
                )
            elif not previous:
                state.provenance[field_name] = actual

    @staticmethod
    def _build_item(
        state: _CandidateState,
        reminder: DecisionContinuityRevision,
        *,
        as_of: datetime,
        source_path: str,
    ) -> ContinuityReviewItem:
        recorded_value = reminder.next_review_at
        normalized_value, review_time, review_error = _normalize_review_at(recorded_value)
        if review_error or review_time is None:
            due_status = CONTINUITY_DUE_INVALID
        elif review_time > as_of:
            due_status = CONTINUITY_DUE_SCHEDULED
        elif review_time.date() == as_of.date():
            due_status = CONTINUITY_DUE
        else:
            due_status = CONTINUITY_DUE_OVERDUE

        latest = state.latest or reminder
        intent = state.latest_intent
        source_snapshot_id = state.provenance.get("source_snapshot_id", "")
        source_snapshot_hash = state.provenance.get("source_snapshot_hash", "")
        decision_date = state.provenance.get("decision_date", "")
        item_diagnostics = (review_error,) if review_error else ()
        revision_ids = [reminder.revision_id]
        if latest.revision_id != reminder.revision_id:
            revision_ids.append(latest.revision_id)
        source_trace = f"{Path(source_path).name}:" + ",".join(revision_ids)
        return ContinuityReviewItem(
            result_id=state.result_id,
            stock_code=state.stock_code,
            decision_status=(
                "accepted"
                if intent is not None and intent.action == ACTION_ACCEPTED
                else "skipped"
                if intent is not None and intent.action == ACTION_SKIPPED
                else "unrecorded"
            ),
            reminder_status=due_status,
            due_status=due_status,
            next_review_at=normalized_value,
            recorded_next_review_at=recorded_value,
            revision_id=latest.revision_id,
            reminder_revision_id=reminder.revision_id,
            revision_of=latest.revision_of,
            continuity_event_id=latest.continuity_event_id,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
            decision_date=decision_date,
            source_trace=source_trace,
            identity_status=IDENTITY_STATUS_LINKED,
            note=latest.note,
            history_count=len(state.revisions),
            diagnostics=item_diagnostics,
        )


def _coerce_as_of(value: datetime | str | None) -> tuple[datetime, str]:
    if value is None:
        # Keep sub-second precision so a revision written immediately before
        # a Workbench refresh is not accidentally treated as future state.
        return datetime.now(ASIA_TAIPEI), ""
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip())
    except (TypeError, ValueError) as exc:
        return datetime.now(ASIA_TAIPEI), _first_line(exc)
    if parsed.tzinfo is None:
        return parsed, "as_of_requires_timezone"
    return parsed.astimezone(ASIA_TAIPEI), ""


def _normalize_review_at(value: str) -> tuple[str, datetime | None, str]:
    text = _text(value)
    if not text:
        return "", None, "next_review_at_missing"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        return text, None, f"next_review_at_invalid:{_first_line(exc)}"
    if parsed.tzinfo is None:
        return text, None, "next_review_at_requires_timezone"
    taipei = parsed.astimezone(ASIA_TAIPEI)
    return taipei.isoformat(timespec="seconds"), taipei, ""


def _normalize_created_at(value: str) -> tuple[datetime, str]:
    text = _text(value)
    if not text:
        return datetime.min.replace(tzinfo=ASIA_TAIPEI), "created_at_missing"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        return datetime.min.replace(tzinfo=ASIA_TAIPEI), f"created_at_invalid:{_first_line(exc)}"
    if parsed.tzinfo is None:
        return datetime.min.replace(tzinfo=ASIA_TAIPEI), "created_at_requires_timezone"
    return parsed.astimezone(ASIA_TAIPEI), ""


def _due_sort_rank(status: str) -> int:
    return {
        CONTINUITY_DUE_OVERDUE: 0,
        CONTINUITY_DUE: 1,
        CONTINUITY_DUE_INVALID: 2,
        CONTINUITY_DUE_SCHEDULED: 3,
    }.get(status, 9)


def _first_line(value: BaseException) -> str:
    return str(value).splitlines()[0].strip() or type(value).__name__


# Friendly aliases for callers/tests that describe the object as a due item.
ContinuityDueReviewItem = ContinuityReviewItem
ContinuityReviewProjection = ContinuityReviewProjectionResult


__all__ = [
    "ASIA_TAIPEI",
    "CONTINUITY_DUE",
    "CONTINUITY_DUE_INVALID",
    "CONTINUITY_DUE_OVERDUE",
    "CONTINUITY_DUE_SCHEDULED",
    "CONTINUITY_STREAM_EMPTY",
    "CONTINUITY_STREAM_INVALID",
    "CONTINUITY_STREAM_MISSING",
    "CONTINUITY_STREAM_READY",
    "ContinuityDueReviewItem",
    "ContinuityReviewItem",
    "ContinuityReviewProjection",
    "ContinuityReviewProjectionResult",
    "ContinuityReviewProjectionService",
]
