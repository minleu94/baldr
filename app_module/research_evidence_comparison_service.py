"""研究時間軸原件與獨立現況的有界唯讀對照。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Callable, Literal

from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
)
from app_module.pinned_stock_research_notes import PinnedStockResearchNote
from app_module.research_evidence_comparison_dtos import (
    EvidenceComparisonColumn,
    ResearchEvidenceComparison,
)
from app_module.research_session.session_dtos import ResearchStockContextDTO
from app_module.research_timeline_dtos import ResearchTimelineEntry
from app_module.stock_research_report_dtos import StockResearchReportDTO
from app_module.stock_research_report_notes import StockResearchReportNote
from app_module.stock_research_report_service import (
    StockResearchReportCancelled,
    StockResearchReportReadService,
)
from app_module.theme_research_notes import ThemeResearchNote
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from app_module.theme_snapshot_catalog import (
    ThemeSnapshotCatalogResult,
    resolve_latest_theme_research_snapshot,
)
from app_module.research_timeline_service import ResearchTimelineService


_MAX_FIELDS = 48
_MAX_FIELD_TEXT = 240
_MAX_LIMITATIONS = 16
_MAX_LIMITATION_TEXT = 240
_MAX_SOURCES = 8
_MAX_SECTIONS = 12
_ComparisonStatus = Literal["available", "unavailable", "limited"]


class ResearchEvidenceComparisonService:
    """重核明選原件後，另讀一次當下研究；不計算金融差值或授予資格。"""

    def __init__(
        self,
        timeline_service: ResearchTimelineService,
        stock_report_service: StockResearchReportReadService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._timeline = timeline_service
        self._stock_reports = stock_report_service
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def read(
        self,
        entry: ResearchTimelineEntry,
        *,
        theme_catalog_root: Path | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> ResearchEvidenceComparison:
        """先精確重核原件；失敗或取消時不開始現況讀取。"""

        _check_cancel(cancel_callback)
        if type(entry) is not ResearchTimelineEntry:
            raise ValueError("研究時間軸項目型別無效")
        baseline, verified_state = self._timeline.read_evidence_baseline(
            entry, cancel_callback=cancel_callback,
        )
        _check_cancel(cancel_callback)
        original = self._original_column(entry, baseline, verified_state)
        compared_at = self._clock()
        if not isinstance(compared_at, datetime) or compared_at.tzinfo is None or compared_at.utcoffset() is None:
            raise ValueError("對照時鐘必須包含時區")

        if entry.kind == "theme":
            current = self._current_theme(theme_catalog_root, compared_at, cancel_callback)
        elif entry.stock_code:
            current = self._current_stock(entry.stock_code, cancel_callback)
        else:
            current = _column(
                "當下個股研究", "unavailable", (),
                ("原紀錄沒有股票代碼；未代為推定標的。",),
            )
        _check_cancel(cancel_callback)
        return ResearchEvidenceComparison(
            original=original,
            current=current,
            compared_at=compared_at.isoformat(),
        )

    def _original_column(
        self,
        entry: ResearchTimelineEntry,
        baseline: object,
        verified_state: object | None,
    ) -> EvidenceComparisonColumn:
        fields: tuple[tuple[str, str], ...]
        if entry.kind == "manual":
            if type(baseline) is not JournalEntryDTO:
                raise ValueError("手動原件型別不符；未建立對照")
            identity = baseline.decision_identity
            fields = (
                ("保存時間", baseline.created_at),
                ("紀錄識別", baseline.revision_id or baseline.journal_id),
                ("原文", baseline.body),
                ("原股票", baseline.stock_code or "未記錄"),
                ("原來源身份", _identity_from_manual(identity)),
                ("行情資料", "原紀錄未封存行情；無法比較"),
            )
            return _column("原手動紀錄", "available", fields, ())

        if entry.kind == "price":
            if type(baseline) is not PinnedStockResearchNote:
                raise ValueError("價格收藏原件型別不符；未建立對照")
            state = verified_state
            if type(state) is not DailyMarketTechnicalUniversePriceBookmarkStateV1:
                raise ValueError("價格收藏未取得本次已核來源狀態；未建立對照")
            selection = state.selected.selection
            verified_row = state.selected.row
            source = baseline.source
            if (selection.stock_code != source.stock_code
                    or state.bookmark.bookmark_identity_sha256 != source.identity_sha256):
                raise ValueError("已核價格來源與原收藏身份不一致；未建立對照")
            fields = (
                ("原股票", source.stock_code),
                ("原研究日", source.research_date),
                ("資料日", _optional(verified_row.price_fact.observation_date)),
                ("收盤價", _optional(verified_row.price_fact.close_price)),
                ("來源身份", verified_row.price_fact.source_identity),
                ("保存版本身份", source.identity_sha256),
                ("原選列身份", selection.row_identity_sha256),
                ("保存時間", baseline.recorded_at),
                ("研究判斷", baseline.text),
                ("原價格狀態", verified_row.price_state),
                ("原來源可用性", "unknown；依原收藏核驗狀態"),
                ("歷史 PIT", "false；收藏不授予歷史資格"),
            )
            price_status: _ComparisonStatus = (
                "limited" if verified_row.price_state == "unknown" else "available"
            )
            price_limitations = (
                ("原收藏同次核驗的價格狀態為 unknown；未提供收盤價。",)
                if verified_row.price_state == "unknown" else ()
            )
            return _column("原價格研究收藏", price_status, fields, price_limitations)

        if entry.kind == "report":
            if type(baseline) is not StockResearchReportNote:
                raise ValueError("報告原件型別不符；未建立對照")
            snapshot = baseline.snapshot
            report = snapshot.report
            if type(report) is not StockResearchReportDTO or report.stock_code != snapshot.stock_code:
                raise ValueError("保存報告原件身份不符；未建立對照")
            fields = _report_fields(
                report,
                snapshot_identity=snapshot.identity_sha256,
                recorded_at=baseline.recorded_at,
                note_text=baseline.text,
            )
            return _column("保存版本", _report_status(report), fields, _report_limitations(report))

        if entry.kind == "theme":
            if type(baseline) is not ThemeResearchNote:
                raise ValueError("題材原件型別不符；未建立對照")
            fields = (
                ("版本身份", baseline.snapshot_identity_sha256),
                ("資料日", baseline.data_date),
                ("保存時間", baseline.recorded_at),
                ("原題材筆記", baseline.text),
                ("封存行情／成分值", "原筆記未封存；不以現況回填保存版本"),
            )
            return _column("原題材紀錄", "available", fields, ())
        raise ValueError("不支援的研究紀錄類型")

    def _current_stock(
        self,
        stock_code: str,
        cancel_callback: Callable[[], bool] | None,
    ) -> EvidenceComparisonColumn:
        _check_cancel(cancel_callback)
        context = ResearchStockContextDTO(
            stock_code=stock_code,
            source_kind="explicit_latest_stock_research",
            source_workspace="research_timeline",
        )
        try:
            report = self._stock_reports.read_report(
                stock_code, context=context, cancel_callback=cancel_callback,
            )
        except (InterruptedError, StockResearchReportCancelled):
            raise
        except Exception as exc:  # noqa: BLE001 - 現況讀取失敗以明示缺件呈現
            _check_cancel(cancel_callback)
            return _column(
                "當下個股研究", "unavailable", (),
                (f"現況讀取失敗（{type(exc).__name__}）；原保存版本仍保留。",),
            )
        _check_cancel(cancel_callback)
        if type(report) is not StockResearchReportDTO or report.stock_code != stock_code or not report.read_only:
            raise ValueError("當下個股 reader 回傳型別、股票或唯讀身份不符")
        fields = _report_fields(report)
        return _column("當下個股研究", _report_status(report), fields, _report_limitations(report))

    def _current_theme(
        self,
        root: Path | None,
        known_at: datetime,
        cancel_callback: Callable[[], bool] | None,
    ) -> EvidenceComparisonColumn:
        if root is None:
            return _column("當下題材研究", "unavailable", (), ("未設定題材來源目錄。",))
        _check_cancel(cancel_callback)
        try:
            catalog = resolve_latest_theme_research_snapshot(
                root,
                known_at=known_at,
                schema="price-v1",
                cancel_callback=cancel_callback,
            )
        except InterruptedError:
            raise
        except Exception as exc:  # noqa: BLE001 - 不將局部失敗偽裝成最新版本
            _check_cancel(cancel_callback)
            return _column(
                "當下題材研究", "unavailable", (),
                (f"題材來源無法核驗（{type(exc).__name__}）。",),
            )
        _check_cancel(cancel_callback)
        if type(catalog) is not ThemeSnapshotCatalogResult:
            raise ValueError("題材目錄 reader 回傳型別無效")
        if catalog.limited:
            return _column(
                "當下題材研究", "limited", (),
                _bounded_texts((catalog.limit_reason or "目錄搜尋受限；不能確認最新版本。",)),
            )
        selected = catalog.selected
        if selected is None:
            reasons = tuple(item.reason for item in catalog.rejections[:_MAX_LIMITATIONS])
            return _column(
                "當下題材研究", "unavailable", (),
                reasons or ("沒有已核驗的 price-v1 題材來源。",),
            )
        if (type(selected.snapshot) is not ThemeResearchSnapshot
                or selected.snapshot.identity_sha256 != selected.identity_sha256):
            raise ValueError("題材目錄的已核驗快照身份不符")
        report = selected.snapshot.report
        rows = tuple(report.rows)
        fields = (
            ("來源格式", selected.schema),
            ("版本身份", selected.identity_sha256),
            ("題材資料日", selected.data_date.isoformat()),
            ("保存完成時間", selected.saved_completed_at.isoformat()),
            ("題材報告狀態", report.status),
            ("映射快照日", report.mapping_snapshot_date),
            ("映射可得日", report.mapping_available_date),
            ("題材數", str(len(rows))),
            ("歷史 PIT", str(report.historical_pit_eligible).lower()),
        )
        warnings = tuple(report.warnings) + (
            "當下僅讀 price-v1 目錄版本；未比較原題材成分或法人值。",
        )
        status: _ComparisonStatus = (
            "limited" if report.status != "current_research" or warnings or not rows else "available"
        )
        return _column("當下已核驗題材快照", status, fields, warnings)


def _report_fields(
    report: StockResearchReportDTO,
    *,
    snapshot_identity: str = "",
    recorded_at: str = "",
    note_text: str = "",
) -> tuple[tuple[str, str], ...]:
    fields: list[tuple[str, str]] = [
        ("股票", f"{report.stock_code} {report.stock_name}".strip()),
        ("報告資料截至", report.as_of or "原件未提供"),
        ("報告產生時間", report.generated_at or "原件未提供"),
    ]
    if report.price_points:
        point = report.price_points[-1]
        fields.extend((
            ("資料日", point.data_date or "原件未提供"),
            ("收盤價", _optional(point.close_price)),
            ("來源身份", point.source_snapshot_hash or point.source_id or "原件未提供"),
        ))
    else:
        fields.extend((("資料日", "原件未提供"), ("收盤價", "原件未提供"), ("來源身份", "原件未提供")))
    if snapshot_identity:
        fields.append(("保存版本身份", snapshot_identity))
    if recorded_at:
        fields.append(("保存時間", recorded_at))
    if note_text:
        fields.append(("保存判斷", note_text))
    for source in report.sources[:_MAX_SOURCES]:
        fields.append((
            f"來源 {source.source_label} ({source.source_id or '未提供識別'})",
            _join((source.source_id, source.version, source.status, source.quality,
                   source.data_as_of, source.available_at,
                   _optional(source.historical_pit_eligible))),
        ))
    for section in report.sections[:_MAX_SECTIONS]:
        fields.append((
            f"區塊 {section.label}",
            _join((section.status, section.summary, section.data_as_of, section.available_at)),
        ))
    return tuple(fields[:_MAX_FIELDS])


def _report_status(report: StockResearchReportDTO) -> _ComparisonStatus:
    section_statuses = {section.status for section in report.sections}
    source_statuses = {source.status for source in report.sources}
    if not report.price_points and not report.sources and not report.sections:
        return "unavailable"
    if report.limitations or section_statuses - {"available"} or source_statuses - {"available"}:
        return "limited"
    return "available"


def _report_limitations(report: StockResearchReportDTO) -> tuple[str, ...]:
    values: list[str] = list(report.limitations)
    for section in report.sections:
        if section.status != "available":
            values.append(f"{section.label}：{section.status}")
        values.extend(section.limitations)
    for source in report.sources:
        values.extend(source.limitations)
        if source.freshness_reason:
            values.append(f"{source.source_label}：{source.freshness_reason}")
    return _bounded_texts(values)


def _identity_from_manual(identity: object | None) -> str:
    if identity is None:
        return "未記錄"
    source_id = getattr(identity, "source_snapshot_id", "")
    source_hash = getattr(identity, "source_snapshot_hash", "")
    result_id = getattr(identity, "result_id", "")
    return _join((source_id, source_hash, result_id)) or "未記錄"


def _column(
    title: str,
    status: _ComparisonStatus,
    fields: tuple[tuple[str, str], ...],
    limitations: tuple[str, ...],
) -> EvidenceComparisonColumn:
    if status not in {"available", "unavailable", "limited"}:
        raise ValueError("對照狀態無效")
    bounded_fields = tuple(
        (_bounded_text(key, 80), _bounded_text(value, _MAX_FIELD_TEXT))
        for key, value in fields[:_MAX_FIELDS]
    )
    clipped = (
        len(fields) > _MAX_FIELDS
        or any(len(key) > 80 or len(value) > _MAX_FIELD_TEXT for key, value in fields[:_MAX_FIELDS])
        or len(limitations) > _MAX_LIMITATIONS
        or any(len(value) > _MAX_LIMITATION_TEXT for value in limitations[:_MAX_LIMITATIONS])
    )
    final_limitations = _bounded_texts(limitations)
    if clipped:
        marker = "顯示內容為有界摘要；欄位或文字有截斷。"
        final_limitations = _bounded_texts((*final_limitations[:_MAX_LIMITATIONS - 1], marker))
    return EvidenceComparisonColumn(
        title=_bounded_text(title, 80),
        status=status, fields=bounded_fields,
        limitations=final_limitations,
    )


def _bounded_texts(values: object) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        return ()
    result: list[str] = []
    for value in values[:_MAX_LIMITATIONS]:
        rendered = _value(value)
        if rendered:
            result.append(_bounded_text(rendered, _MAX_LIMITATION_TEXT))
    return tuple(result)


def _value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, Decimal, date, datetime, Enum)):
        if isinstance(value, Enum):
            return _value(value.value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return str(value)
    return ""


def _optional(value: object) -> str:
    return _value(value) or "原件未提供"


def _join(values: tuple[object, ...]) -> str:
    return "｜".join(text for value in values if (text := _value(value)))


def _bounded_text(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    return clean if len(clean) <= limit else clean[:limit - 1] + "…"


def _check_cancel(callback: Callable[[], bool] | None) -> None:
    if callback is None:
        return
    try:
        cancelled = bool(callback())
    except Exception as exc:  # noqa: BLE001 - 取消狀態不明時停止後續讀取
        raise InterruptedError("研究證據對照取消狀態無法確認；已停止") from exc
    if cancelled:
        raise InterruptedError("研究證據對照已取消")
