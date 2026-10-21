"""以既有 Journal 與 typed note readers 建立唯讀研究時間軸索引。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Callable

from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.journal_service import JournalService
from app_module.pinned_stock_research_notes import (
    PINNED_STOCK_RESEARCH_NOTE_SOURCE_TYPE,
    PinnedStockResearchNote,
    PinnedStockResearchNoteService,
)
from app_module.research_timeline_dtos import (
    ResearchTimelineEntry,
    ResearchTimelineReadResult,
    TimelineReference,
)
from app_module.stock_research_report_notes import (
    STOCK_RESEARCH_REPORT_NOTE_SOURCE_TYPE,
    StockResearchReportNote,
    StockResearchReportNoteService,
)
from app_module.theme_research_notes import (
    THEME_RESEARCH_NOTE_SOURCE_TYPE,
    ThemeResearchNote,
    ThemeResearchNoteService,
)


_SPECIAL_SOURCE_TYPES = frozenset(
    {
        PINNED_STOCK_RESEARCH_NOTE_SOURCE_TYPE,
        STOCK_RESEARCH_REPORT_NOTE_SOURCE_TYPE,
        THEME_RESEARCH_NOTE_SOURCE_TYPE,
    }
)
_MAX_ENTRIES = 500


class ResearchTimelineService:
    """只索引原始紀錄，不重建來源、Journal 或任何研究結果。"""

    def __init__(
        self,
        journal_service: JournalService,
        *,
        price_note_service: PinnedStockResearchNoteService | None = None,
        report_note_service: StockResearchReportNoteService | None = None,
        theme_note_service: ThemeResearchNoteService | None = None,
    ) -> None:
        self._journal = journal_service
        self._price_notes = price_note_service or PinnedStockResearchNoteService(journal_service)
        self._report_notes = report_note_service or StockResearchReportNoteService(journal_service)
        self._theme_notes = theme_note_service or ThemeResearchNoteService(journal_service)

    def read(
        self,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> ResearchTimelineReadResult:
        """讀取各個已驗證 lane；單一 reader 失敗時保留其餘紀錄。"""

        entries: list[ResearchTimelineEntry] = []
        warnings: list[str] = []
        cancelled = False

        def is_cancelled() -> bool:
            nonlocal cancelled
            if cancel_callback is None:
                return False
            try:
                cancelled = bool(cancel_callback())
            except Exception:
                cancelled = True
                warnings.append("取消狀態讀取失敗；已安全停止後續時間軸讀取。")
            return cancelled

        lanes = (
            ("manual", self._read_manual),
            ("price", self._read_price),
            ("report", self._read_reports),
            ("theme", self._read_themes),
        )
        for lane_name, reader in lanes:
            if is_cancelled():
                warnings.append("時間軸讀取已取消；已完成的 lane 仍可查看。")
                break
            try:
                lane_entries = reader()
                for item in lane_entries:
                    if is_cancelled():
                        warnings.append("時間軸讀取已取消；已完成的 lane 仍可查看。")
                        break
                    entries.append(item)
                if cancelled:
                    break
            except Exception as exc:
                warnings.append(f"{lane_name} lane 讀取失敗（{type(exc).__name__}）；其他 lane 已保留。")

        ordered = _sort_by_recorded_at(entries)
        limited = len(ordered) > _MAX_ENTRIES
        return ResearchTimelineReadResult(
            entries=tuple(ordered[:_MAX_ENTRIES]),
            warnings=tuple(dict.fromkeys(warnings)),
            limited=limited,
        )

    def read_original(
        self,
        entry: ResearchTimelineEntry,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[TimelineReference, object | None]:
        """重新讀取明選 entry 的原件，逐欄核對後才回傳可回訪來源。"""

        _raise_if_cancelled(cancel_callback)
        if type(entry) is not ResearchTimelineEntry:
            raise ValueError("研究時間軸項目型別無效")

        expected_types = {
            "price": PinnedStockResearchNote,
            "report": StockResearchReportNote,
            "theme": ThemeResearchNote,
        }
        expected_type = expected_types.get(entry.kind)
        if expected_type is None:
            raise ValueError("只有價格、報告或題材筆記可回訪原版本")
        if type(entry.reference) is not expected_type or not entry.record_id:
            raise ValueError("所選項目的原件型別或修訂識別無效")

        _raise_if_cancelled(cancel_callback)
        note: TimelineReference
        if entry.kind == "price":
            note = self._price_notes.get_note(entry.record_id)
        elif entry.kind == "report":
            note = self._report_notes.get_note(entry.record_id)
        else:
            note = self._theme_notes.get_note(entry.record_id)
        _raise_if_cancelled(cancel_callback)
        if type(note) is not expected_type:
            raise ValueError("原件 reader 回傳了不同型別")
        if not _exact_value_equal(entry.reference, note):
            raise ValueError("原件欄位已變更；未回訪")

        projected = _project_note(entry.kind, note)
        if not _exact_value_equal(entry, projected):
            raise ValueError("時間軸項目與重新讀取的原件投影不一致；未回訪")

        if entry.kind != "price":
            return note, None
        if not isinstance(note, PinnedStockResearchNote):
            raise ValueError("價格筆記原件型別不符")

        _raise_if_cancelled(cancel_callback)
        state = self._price_notes.verify_source(note, cancel_callback=cancel_callback)
        _raise_if_cancelled(cancel_callback)
        _verify_price_state(note, state)
        return note, state

    def _read_manual(self) -> tuple[ResearchTimelineEntry, ...]:
        result: list[ResearchTimelineEntry] = []
        for record in self._journal.list_journal_entries():
            if type(record) is not JournalEntryDTO or record.source_type in _SPECIAL_SOURCE_TYPES:
                continue
            identity = record.decision_identity
            result_id = identity.result_id if identity is not None else ""
            source_identity = ""
            if identity is not None:
                source_identity = identity.source_snapshot_id or identity.source_snapshot_hash
            record_id = record.revision_id or record.journal_id
            result.append(
                ResearchTimelineEntry(
                    kind="manual",
                    record_id=record_id,
                    recorded_at=record.created_at,
                    text=record.body,
                    reference=record,
                    stock_code=record.stock_code,
                    data_date="",
                    source_identity=source_identity,
                    result_id=result_id,
                    revision_of=record.revision_of or "",
                )
            )
        return tuple(result)

    def _read_price(self) -> tuple[ResearchTimelineEntry, ...]:
        result: list[ResearchTimelineEntry] = []
        for note in self._price_notes.list_notes():
            if type(note) is not PinnedStockResearchNote:
                continue
            result.append(_project_note("price", note))
        return tuple(result)

    def _read_reports(self) -> tuple[ResearchTimelineEntry, ...]:
        result: list[ResearchTimelineEntry] = []
        for note in self._report_notes.list_notes():
            if type(note) is not StockResearchReportNote:
                continue
            result.append(_project_note("report", note))
        return tuple(result)

    def _read_themes(self) -> tuple[ResearchTimelineEntry, ...]:
        result: list[ResearchTimelineEntry] = []
        for note in self._theme_notes.list_notes():
            if type(note) is not ThemeResearchNote:
                continue
            result.append(_project_note("theme", note))
        return tuple(result)


def _project_note(kind: str, note: object) -> ResearchTimelineEntry:
    if kind == "price" and type(note) is PinnedStockResearchNote:
        return ResearchTimelineEntry(
            kind="price",
            record_id=note.revision_id,
            recorded_at=note.recorded_at,
            text=note.text,
            reference=note,
            stock_code=note.source.stock_code,
            data_date=note.source.data_date,
            source_identity=note.source.identity_sha256,
            result_id="",
            revision_of=note.revision_of or "",
        )
    if kind == "report" and type(note) is StockResearchReportNote:
        snapshot = note.snapshot
        context = snapshot.context
        return ResearchTimelineEntry(
            kind="report",
            record_id=note.revision_id,
            recorded_at=note.recorded_at,
            text=note.text,
            reference=note,
            stock_code=snapshot.stock_code,
            data_date=context.data_date if context is not None else "",
            source_identity=snapshot.identity_sha256,
            result_id=context.result_id if context is not None else "",
            revision_of=note.revision_of or "",
        )
    if kind == "theme" and type(note) is ThemeResearchNote:
        return ResearchTimelineEntry(
            kind="theme",
            record_id=note.revision_id,
            recorded_at=note.recorded_at,
            text=note.text,
            reference=note,
            data_date=note.data_date,
            source_identity=note.snapshot_identity_sha256,
            result_id="",
            revision_of=note.revision_of or "",
        )
    raise ValueError("研究筆記型別與 lane 不一致")


def _exact_value_equal(left: object, right: object) -> bool:
    """遞迴比較 dataclass 全欄位，包含 compare=False 的原保存時間。"""

    if is_dataclass(left) or is_dataclass(right):
        if type(left) is not type(right) or not is_dataclass(left) or not is_dataclass(right):
            return False
        return all(
            _exact_value_equal(getattr(left, field.name), getattr(right, field.name))
            for field in fields(left)
        )
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        if not isinstance(left, Mapping) or not isinstance(right, Mapping):
            return False
        return left.keys() == right.keys() and all(
            _exact_value_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, (tuple, list)) or isinstance(right, (tuple, list)):
        if (type(left) is not type(right) or not isinstance(left, (tuple, list))
                or not isinstance(right, (tuple, list))):
            return False
        return len(left) == len(right) and all(
            _exact_value_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    if isinstance(left, (set, frozenset)) or isinstance(right, (set, frozenset)):
        return type(left) is type(right) and left == right
    return type(left) is type(right) and left == right


def _raise_if_cancelled(cancel_callback: Callable[[], bool] | None) -> None:
    if cancel_callback is not None and cancel_callback():
        raise InterruptedError("研究時間軸原件核對已取消")


def _verify_price_state(note: PinnedStockResearchNote, state: object) -> None:
    bookmark = getattr(state, "bookmark", None)
    to_json = getattr(bookmark, "to_json", None)
    canonical = to_json() if callable(to_json) else None
    if (
        canonical != note.source.bookmark_json
        or getattr(bookmark, "bookmark_identity_sha256", None)
        != note.source.identity_sha256
        or getattr(bookmark, "stock_code", None) != note.source.stock_code
    ):
        raise ValueError("重新核對的價格 bookmark 與原保存筆記不一致")


def _sort_by_recorded_at(
    entries: list[ResearchTimelineEntry],
) -> list[ResearchTimelineEntry]:
    known: list[tuple[datetime, int, ResearchTimelineEntry]] = []
    unknown: list[ResearchTimelineEntry] = []
    for index, entry in enumerate(entries):
        parsed = _parse_aware_datetime(entry.recorded_at)
        if parsed is None:
            unknown.append(entry)
        else:
            known.append((parsed, index, entry))
    known.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in known] + unknown


def _parse_aware_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


__all__ = ["ResearchTimelineService"]
