"""以既有 Journal 記錄固定價格研究收藏上的使用者筆記。"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
import re
from typing import Any, Callable, Mapping, Sequence

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkV1,
    DailyMarketTechnicalUniversePriceBookmarkV1Error,
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
    read_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.dtos.decision_continuity_dtos import (
    ACTION_NOTE,
    ACTION_REMOVED,
    DECISION_CONTINUITY_RECORD_TYPE,
    IDENTITY_STATUS_UNKNOWN,
    DecisionContinuityRevision,
    DecisionIdentity,
)
from app_module.journal_service import JournalService
from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.portfolio_store import project_journal_records
from app_module.daily_market_technical_snapshot_v4_repository import (
    DailyMarketTechnicalSnapshotProofScope,
)


PINNED_STOCK_RESEARCH_NOTE_SOURCE_TYPE = "technical_price_research_note.v1"
_LINKED_TYPE = "technical_price_research_bookmark"
_MAX_NOTE_LENGTH = 8000
_BOOKMARK_TAG = "technical_price_research_bookmark:"
_DATA_DATE_TAG = "technical_price_research_data_date:"
_RESEARCH_DATE_TAG = "technical_price_research_date:"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class PinnedStockResearchSource:
    """一份 F07 價格研究收藏的 canonical bytes；建立時不讀來源。"""

    bookmark_json: str

    def __post_init__(self) -> None:
        if not isinstance(self.bookmark_json, str):
            raise PinnedStockResearchNoteError("bookmark_json must be a canonical string")
        try:
            bookmark = DailyMarketTechnicalUniversePriceBookmarkV1.from_json(
                self.bookmark_json
            )
        except DailyMarketTechnicalUniversePriceBookmarkV1Error as exc:
            raise _reader_error(exc) from exc
        if bookmark.to_json() != self.bookmark_json:
            raise PinnedStockResearchNoteError("bookmark_json is not canonical")

    @property
    def stock_code(self) -> str:
        return self._bookmark().selected.stock_code

    @property
    def identity_sha256(self) -> str:
        return self._bookmark().bookmark_identity_sha256

    @property
    def data_date(self) -> str:
        return self._bookmark().selected.observation_date or ""

    @property
    def research_date(self) -> str:
        return self._bookmark().selected.query.source.decision_date.isoformat()

    @property
    def snapshot_identity_sha256(self) -> str:
        return self._bookmark().selected.snapshot_identity_sha256

    def _bookmark(self) -> DailyMarketTechnicalUniversePriceBookmarkV1:
        try:
            return DailyMarketTechnicalUniversePriceBookmarkV1.from_json(
                self.bookmark_json
            )
        except DailyMarketTechnicalUniversePriceBookmarkV1Error as exc:
            raise _reader_error(exc) from exc


@dataclass(frozen=True, slots=True)
class PinnedStockResearchNote:
    revision_id: str
    source: PinnedStockResearchSource
    text: str
    revision_of: str | None = None
    recorded_at: str = field(default="", compare=False)


@dataclass(frozen=True, slots=True)
class PinnedStockResearchNoteSaveReadback:
    """同次保存的來源核對與 Journal 原文回讀；不供下一次動作免驗。"""

    note: PinnedStockResearchNote
    source_state: DailyMarketTechnicalUniversePriceBookmarkStateV1
    notes: tuple[PinnedStockResearchNote, ...]


class PinnedStockResearchNoteError(ValueError):
    """價格研究收藏筆記或其固定來源無法驗證。"""

    def __init__(self, message: str, *, code: str = "") -> None:
        self.code = code
        super().__init__(message)


class PinnedStockResearchNoteNotFound(PinnedStockResearchNoteError):
    """Journal 中沒有指定的筆記修訂。"""


class PinnedStockResearchNoteConflict(PinnedStockResearchNoteError):
    """筆記修訂或 Journal 歷史身份互相衝突。"""


class PinnedStockResearchNoteService:
    """以 Journal append-only 修訂流記錄 F07 固定收藏上的使用者文字。"""

    def __init__(self, journal_service: JournalService) -> None:
        if not isinstance(journal_service, JournalService):
            raise TypeError("journal_service must be JournalService")
        self._journal_service = journal_service
        self._source_proof_scope = DailyMarketTechnicalSnapshotProofScope()

    def source_read_scope(self) -> AbstractContextManager[None]:
        """在執行來源工作的背景 context 啟用同服務證明，不保留舊 DTO。"""

        return self._source_proof_scope.activate()

    def save(
        self,
        source: PinnedStockResearchSource,
        text: str,
        *,
        revision_id: str,
        revision_of: str | None = None,
    ) -> PinnedStockResearchNote:
        saved, _state = self._save_exact(
            source, text, revision_id=revision_id, revision_of=revision_of
        )
        return saved

    def save_with_readback(
        self,
        source: PinnedStockResearchSource,
        text: str,
        *,
        revision_id: str,
        revision_of: str | None = None,
    ) -> PinnedStockResearchNoteSaveReadback:
        """保存前 fresh exact 不變；以本次核對結果及新讀 Journal 刷新畫面。"""

        saved, state = self._save_exact(
            source,
            text,
            revision_id=revision_id,
            revision_of=revision_of,
            require_typed_state=True,
        )
        notes = self.list_notes(stock_code=source.stock_code)
        matching = tuple(note for note in notes if note.revision_id == saved.revision_id)
        if (
            len(matching) != 1
            or matching[0] != saved
            or matching[0].recorded_at != saved.recorded_at
        ):
            raise PinnedStockResearchNoteConflict(
                "journal readback differs from the saved price research note"
            )
        return PinnedStockResearchNoteSaveReadback(
            note=matching[0], source_state=state, notes=notes
        )

    def _save_exact(
        self,
        source: PinnedStockResearchSource,
        text: str,
        *,
        revision_id: str,
        revision_of: str | None = None,
        require_typed_state: bool = False,
    ) -> tuple[PinnedStockResearchNote, DailyMarketTechnicalUniversePriceBookmarkStateV1]:
        if type(source) is not PinnedStockResearchSource:
            raise PinnedStockResearchNoteError(
                "source must be a verified pinned stock research source"
            )
        note_text = _validated_note_text(text)
        resolved_revision_id = _required_revision_id(revision_id, "revision_id")
        resolved_revision_of = (
            _required_revision_id(revision_of, "revision_of")
            if revision_of is not None
            else None
        )
        if resolved_revision_id == resolved_revision_of:
            raise PinnedStockResearchNoteConflict(
                "revision_of must differ from revision_id"
            )

        with self.source_read_scope():
            state = _read_exact_source(source)
        if require_typed_state and (
            type(state) is not DailyMarketTechnicalUniversePriceBookmarkStateV1
            or state.bookmark.to_json() != source.bookmark_json
        ):
            raise PinnedStockResearchNoteConflict(
                "saved note source readback differs from the exact submitted bookmark"
            )

        history, history_token = self._journal_service.store.load_journal_snapshot()
        revisions = _decode_history(history)
        note_history = _decode_note_history(revisions)
        existing = [item for item in revisions if item.revision_id == resolved_revision_id]
        if existing:
            if len(existing) != 1:
                raise PinnedStockResearchNoteConflict(
                    "revision_id is ambiguous in journal history"
                )
            if not any(item.revision_id == resolved_revision_id for item in note_history):
                raise PinnedStockResearchNoteNotFound("此篇筆記已刪除，不能重用原修訂ID保存。")
            saved = _decode_note_revision(existing[0])
            requested = PinnedStockResearchNote(
                revision_id=resolved_revision_id,
                source=source,
                text=note_text,
                revision_of=resolved_revision_of,
            )
            if saved != requested:
                raise PinnedStockResearchNoteConflict(
                    "revision_id already names different saved content"
                )
            return saved, state

        entity_id = _root_entity_id(source, resolved_revision_id)
        if resolved_revision_of is not None:
            prior = [
                item for item in revisions
                if item.revision_id == resolved_revision_of
            ]
            if len(prior) != 1:
                raise PinnedStockResearchNoteConflict(
                    "revision_of must identify one saved price research note"
                )
            prior_notes = [
                note for note in note_history
                if note.revision_id == resolved_revision_of
            ]
            if len(prior_notes) != 1:
                raise PinnedStockResearchNoteConflict(
                    "revision_of must identify one saved price research note"
                )
            prior_note = prior_notes[0]
            if prior_note.source.bookmark_json != source.bookmark_json:
                raise PinnedStockResearchNoteConflict(
                    "revision_of belongs to another exact price bookmark"
                )
            entity_id = prior[0].entity_id

        identity_sha256 = source.identity_sha256
        bookmark_sha256 = _bookmark_bytes_sha256(source.bookmark_json)
        identity = DecisionIdentity(
            stock_code=source.stock_code,
            source_snapshot_id=identity_sha256,
            source_snapshot_hash=bookmark_sha256,
            identity_status=IDENTITY_STATUS_UNKNOWN,
        )
        tags = [
            _BOOKMARK_TAG + source.bookmark_json,
            _DATA_DATE_TAG + source.data_date,
            _RESEARCH_DATE_TAG + source.research_date,
        ]
        try:
            revision = self._journal_service.record_research_action(
                ACTION_NOTE,
                identity,
                body=note_text,
                note=note_text,
                title="價格研究筆記",
                journal_id=entity_id,
                entity_id=entity_id,
                linked_type=_LINKED_TYPE,
                linked_id=identity_sha256,
                source_type=PINNED_STOCK_RESEARCH_NOTE_SOURCE_TYPE,
                source_id=identity_sha256,
                tags=tags,
                source_snapshot_id=identity_sha256,
                source_snapshot_hash=bookmark_sha256,
                revision_id=resolved_revision_id,
                continuity_event_id=resolved_revision_id,
                revision_of=resolved_revision_of or "",
                expected_history_token=history_token,
            )
        except (RuntimeError, ValueError) as exc:
            if _is_journal_conflict(exc):
                raise PinnedStockResearchNoteConflict(
                    f"journal append conflict: {exc}"
                ) from exc
            raise

        saved = _decode_note_revision(revision)
        requested = PinnedStockResearchNote(
            revision_id=resolved_revision_id,
            source=source,
            text=note_text,
            revision_of=resolved_revision_of,
        )
        if saved != requested:
            raise PinnedStockResearchNoteConflict(
                "journal returned a different saved price research note"
            )
        return saved, state

    def get_note(self, revision_id: str) -> PinnedStockResearchNote:
        resolved_revision_id = _required_revision_id(revision_id, "revision_id")
        revisions = self._journal_service.list_decision_revisions()
        matches = [
            item for item in revisions
            if item.revision_id == resolved_revision_id
        ]
        if not matches:
            raise PinnedStockResearchNoteNotFound(
                "pinned stock research note revision not found"
            )
        if len(matches) != 1:
            raise PinnedStockResearchNoteConflict(
                "revision_id is ambiguous in journal history"
            )
        note_history = _decode_note_history(revisions)
        note_matches = [
            note for note in note_history
            if note.revision_id == resolved_revision_id
        ]
        if len(note_matches) != 1:
            raise PinnedStockResearchNoteNotFound(
                "pinned stock research note revision not found"
            )
        return note_matches[0]

    def list_notes(
        self,
        *,
        stock_code: str = "",
    ) -> tuple[PinnedStockResearchNote, ...]:
        if not isinstance(stock_code, str) or stock_code.strip() != stock_code:
            raise PinnedStockResearchNoteError("stock_code must be an exact string")
        revisions = self._journal_service.list_decision_revisions()
        notes = _decode_note_history(revisions)
        matching: list[PinnedStockResearchNote] = []
        for note in notes:
            if not stock_code or note.source.stock_code == stock_code:
                matching.append(note)
        return tuple(matching)

    def delete_note_family(
        self, note: PinnedStockResearchNote, *, removal_revision_id: str,
    ) -> tuple[str, ...]:
        """追加一筆刪除事件隱藏整篇修訂鏈；不刪原文字或價格來源。"""
        if type(note) is not PinnedStockResearchNote:
            raise PinnedStockResearchNoteError("note must be a pinned stock research note")
        removal_id = _required_revision_id(removal_revision_id, "removal_revision_id")
        revisions = self._journal_service.list_decision_revisions()
        active_notes = _decode_note_history(revisions)
        originals = [item for item in revisions if item.revision_id == note.revision_id]
        if len(originals) != 1 or _decode_note_revision(originals[0]) != note:
            raise PinnedStockResearchNoteConflict("所選筆記身份或原文已改變；未刪除。")
        entity_id = originals[0].entity_id
        family = tuple(item.revision_id for item in revisions if item.entity_id == entity_id
                       and item.action == ACTION_NOTE)
        prior_removal = [item for item in revisions if item.revision_id == removal_id]
        if prior_removal:
            if (any(item.revision_id in family for item in active_notes)
                or len(prior_removal) != 1 or prior_removal[0].action != ACTION_REMOVED
                or prior_removal[0].entity_id != entity_id or prior_removal[0].entity_type != "journal"):
                raise PinnedStockResearchNoteConflict("刪除事件ID已用於其他內容。")
            return family
        if not any(item.revision_id == note.revision_id for item in active_notes):
            raise PinnedStockResearchNoteNotFound("此篇筆記已刪除。")
        head = next(item for item in reversed(revisions) if item.entity_id == entity_id)
        try:
            removed = self._journal_service.delete_journal_entry(
                entity_id, revision_id=removal_id, continuity_event_id=removal_id,
                actor="user", reason="使用者刪除價格研究筆記及其修訂",
                expected_current_revision_id=head.revision_id,
            )
        except (RuntimeError, ValueError) as exc:
            raise PinnedStockResearchNoteConflict(f"刪除時Journal已改變：{exc}") from exc
        if not removed:
            raise PinnedStockResearchNoteNotFound("此篇筆記已刪除。")
        remaining = _decode_note_history(self._journal_service.list_decision_revisions())
        if any(item.revision_id in family for item in remaining):
            raise PinnedStockResearchNoteConflict("Journal刪除回讀仍含原筆記；未確認完成。")
        return family

    def verify_source(
        self,
        note: PinnedStockResearchNote,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
        if type(note) is not PinnedStockResearchNote:
            raise PinnedStockResearchNoteError("note must be a pinned stock research note")
        _required_revision_id(note.revision_id, "revision_id")
        _validated_note_text(note.text)
        with self.source_read_scope():
            return _read_exact_source(note.source, cancel_callback=cancel_callback)


def verify_pinned_stock_research_source(
    bookmark: DailyMarketTechnicalUniversePriceBookmarkV1 | str,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> PinnedStockResearchSource:
    """Fresh exact-open one明示 F07 收藏並回傳其 canonical 原文。"""

    if isinstance(bookmark, DailyMarketTechnicalUniversePriceBookmarkV1):
        raw = bookmark.to_json()
    elif isinstance(bookmark, str):
        raw = bookmark
    else:
        raise PinnedStockResearchNoteError(
            "bookmark must be a versioned F07 bookmark or canonical JSON"
        )
    try:
        parsed = DailyMarketTechnicalUniversePriceBookmarkV1.from_json(raw)
    except DailyMarketTechnicalUniversePriceBookmarkV1Error as exc:
        raise _reader_error(exc) from exc
    state = _read_exact_bookmark(parsed, cancel_callback=cancel_callback)
    return PinnedStockResearchSource(bookmark_json=state.bookmark.to_json())


def _read_exact_source(
    source: PinnedStockResearchSource,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
    if type(source) is not PinnedStockResearchSource:
        raise PinnedStockResearchNoteError("source must be a pinned stock research source")
    return _read_exact_bookmark(source._bookmark(), cancel_callback=cancel_callback)


def _read_exact_bookmark(
    bookmark: DailyMarketTechnicalUniversePriceBookmarkV1,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
    if cancel_callback is not None and cancel_callback():
        raise InterruptedError("原價格版本核對已取消")
    try:
        if cancel_callback is None:
            state = read_daily_market_technical_universe_price_bookmark_v1(bookmark)
        else:
            state = read_daily_market_technical_universe_price_bookmark_v1(
                bookmark, cancel_callback=cancel_callback
            )
    except InterruptedError:
        # 取消是唯讀工作的終態，不可改寫成來源缺件或回傳部分結果。
        raise
    except DailyMarketTechnicalUniversePriceBookmarkV1Error as exc:
        # 舊 parent reader 用 typed error 回報取消；只轉接明確碼與實際取消。
        if (
            exc.code in {
                "technical_parent_v4_read_cancelled",
                "technical_universe_v4_technical_parent_v4_read_cancelled",
                "technical_universe_v4_read_cancelled",
            }
            and cancel_callback is not None
            and cancel_callback()
        ):
            raise InterruptedError("原價格版本核對已取消") from exc
        raise _reader_error(exc) from exc
    except (OSError, ValueError, RuntimeError) as exc:
        raise PinnedStockResearchNoteError(
            f"price bookmark exact reader failed: {exc}"
        ) from exc
    if cancel_callback is not None and cancel_callback():
        raise InterruptedError("原價格版本核對已取消")
    if state.bookmark.to_json() != bookmark.to_json():
        raise PinnedStockResearchNoteConflict(
            "price bookmark exact reader returned a different bookmark"
        )
    return state


def _reader_error(exc: DailyMarketTechnicalUniversePriceBookmarkV1Error) -> PinnedStockResearchNoteError:
    code = str(getattr(exc, "code", "") or "")
    message = f"price bookmark exact reader failed: {exc}"
    return PinnedStockResearchNoteError(message, code=code)


def _required_revision_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise PinnedStockResearchNoteError(
            f"{field_name} must be a non-empty exact string"
        )
    if len(value) > 256:
        raise PinnedStockResearchNoteError(f"{field_name} is too long")
    return value


def _validated_note_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PinnedStockResearchNoteError("price research note text is required")
    if len(value) > _MAX_NOTE_LENGTH:
        raise PinnedStockResearchNoteError(
            f"price research note exceeds {_MAX_NOTE_LENGTH} characters"
        )
    return value


def _bookmark_bytes_sha256(bookmark_json: str) -> str:
    return sha256(bookmark_json.encode("utf-8")).hexdigest()


def _root_entity_id(source: PinnedStockResearchSource, revision_id: str) -> str:
    root_hash = sha256(
        f"{source.identity_sha256}\0{revision_id}".encode("utf-8")
    ).hexdigest()
    return f"technical-price-research-note:{root_hash}"


def _decode_history(
    history: Sequence[Mapping[str, Any]],
) -> tuple[DecisionContinuityRevision, ...]:
    try:
        return tuple(
            DecisionContinuityRevision.from_mapping(item)
            for item in history
            if isinstance(item, Mapping)
            and item.get("record_type") == DECISION_CONTINUITY_RECORD_TYPE
        )
    except (TypeError, ValueError) as exc:
        raise PinnedStockResearchNoteConflict(
            "journal history contains an invalid continuity revision"
        ) from exc


def _decode_note_history(
    revisions: Sequence[DecisionContinuityRevision],
) -> tuple[PinnedStockResearchNote, ...]:
    """驗證本服務筆記在 Journal 中的唯一 ID、根與直接父子關係。"""

    revision_counts: dict[str, int] = {}
    for revision in revisions:
        revision_counts[revision.revision_id] = (
            revision_counts.get(revision.revision_id, 0) + 1
        )
    note_entities = {
        revision.entity_id for revision in revisions
        if isinstance(revision.payload, Mapping)
        and revision.payload.get("source_type") == PINNED_STOCK_RESEARCH_NOTE_SOURCE_TYPE
        and revision.action == ACTION_NOTE
    }
    matching = [
        revision for revision in revisions
        if (isinstance(revision.payload, Mapping)
        and revision.payload.get("source_type")
        == PINNED_STOCK_RESEARCH_NOTE_SOURCE_TYPE)
        or (revision.entity_id in note_entities and revision.action in {ACTION_NOTE, ACTION_REMOVED})
    ]
    by_id: dict[str, tuple[DecisionContinuityRevision, PinnedStockResearchNote]] = {}
    for revision in matching:
        if revision_counts.get(revision.revision_id, 0) != 1:
            raise PinnedStockResearchNoteConflict(
                "revision_id is ambiguous in journal history"
            )
        if revision.action == ACTION_REMOVED:
            continue
        note = _decode_note_revision(revision)
        if revision.revision_id in by_id:
            raise PinnedStockResearchNoteConflict(
                "revision_id is ambiguous in journal history"
            )
        by_id[revision.revision_id] = (revision, note)

    children: dict[str, int] = {}
    for revision, note in by_id.values():
        if note.revision_of is None:
            expected_root = _root_entity_id(note.source, note.revision_id)
            if revision.entity_id != expected_root:
                raise PinnedStockResearchNoteConflict(
                    "saved price research note root identity is inconsistent"
                )
            continue
        parent = by_id.get(note.revision_of)
        if parent is None:
            raise PinnedStockResearchNoteConflict(
                "saved price research note parent is missing or belongs to another source"
            )
        parent_revision, parent_note = parent
        if (
            parent_note.source.bookmark_json != note.source.bookmark_json
            or parent_revision.entity_id != revision.entity_id
        ):
            raise PinnedStockResearchNoteConflict(
                "saved price research note parent identity is inconsistent"
            )
        children[note.revision_of] = children.get(note.revision_of, 0) + 1
        if children[note.revision_of] > 1:
            raise PinnedStockResearchNoteConflict(
                "saved price research note revision chain branches"
            )

    for note in (value[1] for value in by_id.values()):
        visited: set[str] = set()
        current_id = note.revision_id
        while current_id:
            if current_id in visited:
                raise PinnedStockResearchNoteConflict(
                    "saved price research note revision chain contains a cycle"
                )
            visited.add(current_id)
            current = by_id.get(current_id)
            if current is None:
                raise PinnedStockResearchNoteConflict(
                    "saved price research note parent is missing"
                )
            parent_id = current[1].revision_of
            if parent_id is None:
                break
            current_id = parent_id

    removed_entities: set[str] = set()
    heads: dict[str, DecisionContinuityRevision] = {}
    family_records: dict[str, list[dict[str, Any]]] = {}
    for revision in matching:
        if revision.action == ACTION_NOTE:
            if revision.entity_id in removed_entities:
                raise PinnedStockResearchNoteConflict("已刪除的筆記鏈不可追加修訂。")
            heads[revision.entity_id] = revision
            raw = revision.to_dict()
            # DTO envelope版本與Journal欄位版本不同；原writer明確採payload的Journal schema。
            raw["schema_version"] = revision.payload.get("schema_version", "4.1")
            family_records.setdefault(revision.entity_id, []).append(raw)
            continue
        current_head = heads.get(revision.entity_id)
        if (
            current_head is None or revision.entity_id in removed_entities
            or revision.entity_type != "journal" or revision.revision_of != current_head.revision_id
            or revision.continuity_event_id != revision.revision_id
            or revision.decision_identity != current_head.decision_identity
        ):
            raise PinnedStockResearchNoteConflict("價格筆記刪除事件與原修訂不一致。")
        # 使用與原Journal writer相同的公開投影，保留完整身份、原文與原版本欄位。
        projected = project_journal_records(family_records[revision.entity_id])
        if len(projected) != 1 or revision.to_dict()["payload"] != JournalEntryDTO.from_dict(projected[0]).to_dict():
            raise PinnedStockResearchNoteConflict("價格筆記刪除內容與原修訂不一致。")
        removed_entities.add(revision.entity_id)
    return tuple(note for revision, note in by_id.values() if revision.entity_id not in removed_entities)


def _decode_note_revision(
    revision: DecisionContinuityRevision,
) -> PinnedStockResearchNote:
    payload = revision.payload
    if (
        revision.action != ACTION_NOTE
        or revision.entity_type != "journal"
        or not isinstance(payload, Mapping)
        or payload.get("source_type") != PINNED_STOCK_RESEARCH_NOTE_SOURCE_TYPE
    ):
        raise PinnedStockResearchNoteConflict(
            "revision is not a pinned stock research note"
        )

    tags = payload.get("tags")
    if not isinstance(tags, (list, tuple)) or any(
        not isinstance(tag, str) for tag in tags
    ):
        raise PinnedStockResearchNoteConflict(
            "saved price research note tags are invalid"
        )
    if len(tags) != 3:
        raise PinnedStockResearchNoteConflict(
            "saved price research note tags are missing or unexpected"
        )
    bookmark_json = _one_tag_value(tags, _BOOKMARK_TAG)
    data_date = _one_tag_value(tags, _DATA_DATE_TAG)
    research_date = _one_tag_value(tags, _RESEARCH_DATE_TAG)
    try:
        source = PinnedStockResearchSource(bookmark_json)
    except PinnedStockResearchNoteError as exc:
        raise PinnedStockResearchNoteConflict(
            "saved price research bookmark tag is invalid"
        ) from exc
    if data_date != source.data_date or research_date != source.research_date:
        raise PinnedStockResearchNoteConflict(
            "saved price research note dates conflict with its bookmark"
        )

    identity_sha256 = source.identity_sha256
    bookmark_sha256 = _bookmark_bytes_sha256(source.bookmark_json)
    identity = revision.decision_identity
    if (
        identity.stock_code != source.stock_code
        or identity.result_id
        or identity.decision_date
        or identity.identity_status != IDENTITY_STATUS_UNKNOWN
        or identity.source_snapshot_id != identity_sha256
        or identity.source_snapshot_hash != bookmark_sha256
        or payload.get("stock_code") != source.stock_code
        or payload.get("source_id") != identity_sha256
        or payload.get("source_snapshot_id") != identity_sha256
        or payload.get("source_snapshot_hash") != bookmark_sha256
        or payload.get("journal_id") != revision.entity_id
        or payload.get("linked_type") != _LINKED_TYPE
        or payload.get("linked_id") != identity_sha256
        or "personalization_action" in payload
        or "personal_recommendation_choice" in payload
    ):
        raise PinnedStockResearchNoteConflict(
            "saved price research note identity is inconsistent"
        )

    try:
        recorded = datetime.fromisoformat(revision.created_at)
        if recorded.tzinfo is None or recorded.utcoffset() is None:
            raise ValueError("missing timezone")
    except (TypeError, ValueError) as exc:
        raise PinnedStockResearchNoteConflict(
            "saved price research note recorded clock is invalid"
        ) from exc
    if (
        payload.get("created_at") != revision.created_at
        or payload.get("updated_at") != revision.created_at
    ):
        raise PinnedStockResearchNoteConflict(
            "saved price research note recorded clock is inconsistent"
        )
    text = payload.get("body")
    if (
        not isinstance(text, str)
        or not text.strip()
        or len(text) > _MAX_NOTE_LENGTH
        or revision.note != text.strip()
    ):
        raise PinnedStockResearchNoteConflict(
            "saved price research note text is missing or inconsistent"
        )
    if (
        not revision.revision_id
        or revision.revision_of == revision.revision_id
        or revision.continuity_event_id != revision.revision_id
    ):
        raise PinnedStockResearchNoteConflict(
            "saved price research note revision chain is invalid"
        )
    return PinnedStockResearchNote(
        revision_id=revision.revision_id,
        source=source,
        text=text,
        revision_of=revision.revision_of or None,
        recorded_at=revision.created_at,
    )


def _one_tag_value(tags: Sequence[str], prefix: str) -> str:
    values = [tag[len(prefix):] for tag in tags if tag.startswith(prefix)]
    if len(values) != 1:
        raise PinnedStockResearchNoteConflict(
            "saved price research note tag is missing or duplicated"
        )
    return values[0]


def _is_journal_conflict(exc: BaseException) -> bool:
    return any(
        marker in str(exc)
        for marker in (
            "journal_revision_event_conflict",
            "journal_revision_chain_conflict",
            "journal_revision_stream_conflict",
        )
    )
