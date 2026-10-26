from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor, QFont

from app_module.workbench_dtos import (
    WorkbenchActionItem,
    WorkbenchChecklistItem,
    WorkbenchEvidenceFeedItem,
    WorkbenchEvidenceSummary,
    WorkbenchOperatingLoopStep,
    WorkbenchReviewItem,
    WorkbenchStatusItem,
)
from app_module.advice_dtos import PortfolioAdviceDTO, RecommendationAdviceDTO
from app_module.decision_presentation import (
    PositionHealthPresentationDTO,
    position_health_action_label,
    position_health_reason_text,
    position_health_review_label,
    position_health_source_status_label,
)
from ui_qt.theme.tokens import MIDNIGHT_ANALYST


ColumnSpec = tuple[tuple[str, str], ...]


class _WorkbenchTableModel(QAbstractTableModel):
    COLUMNS: ColumnSpec = ()

    def __init__(self, rows: Sequence[Any] = (), parent=None) -> None:
        super().__init__(parent)
        self._rows = tuple(rows)

    def set_rows(self, rows: Sequence[Any]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        field_name = self.COLUMNS[index.column()][0]
        row = self._rows[index.row()]
        if role == Qt.DisplayRole:
            return _display_value(getattr(row, field_name, None))
        status = _row_status(row)
        tone = _status_tone(status)
        if role == Qt.ForegroundRole and field_name in {"status", "severity"}:
            return QBrush(QColor(tone["fg"]))
        if role == Qt.BackgroundRole and _is_attention_status(status):
            return QBrush(QColor(tone["bg"]))
        if role == Qt.FontRole and field_name in {"status", "severity", "title", "label"}:
            font = QFont()
            font.setBold(True)
            return font
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self.COLUMNS):
            return self.COLUMNS[section][1]
        return section + 1

    def column_index(self, field_name: str) -> int:
        for index, (column_field, _) in enumerate(self.COLUMNS):
            if column_field == field_name:
                return index
        raise KeyError(field_name)

    def raw_value(self, row: int, field_name: str):
        return getattr(self._rows[row], field_name)

    def row_at(self, row: int):
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None


@dataclass(frozen=True)
class GuidedWorkbenchRow:
    """首頁摘要專用的 UI read model；不承載策略或來源計算。"""

    key: str
    title: str
    status: str
    conclusion: str
    reasons: str
    action_label: str
    target: str


class WorkbenchGuidedSummaryTableModel(_WorkbenchTableModel):
    """將首頁四個重點保留成可測試的輕量投影，完整欄位仍留在進階模型。"""

    COLUMNS = (
        ("title", "重點"),
        ("status", "狀態"),
        ("conclusion", "結論"),
        ("reasons", "主要理由"),
        ("action_label", "下一步"),
    )

    def __init__(self, rows: Sequence[GuidedWorkbenchRow] = (), parent=None) -> None:
        super().__init__(rows, parent)


class WorkbenchStatusStripTableModel(_WorkbenchTableModel):
    COLUMNS = (
        ("label", "項目"),
        ("value", "值"),
        ("status", "狀態"),
        ("summary", "摘要"),
    )

    def __init__(self, rows: Sequence[WorkbenchStatusItem] = (), parent=None) -> None:
        super().__init__(rows, parent)


class WorkbenchReviewQueueTableModel(_WorkbenchTableModel):
    COLUMNS = (
        ("severity", "嚴重度"),
        ("title", "標題"),
        ("source", "來源"),
        ("code", "代碼"),
        ("summary", "摘要"),
        ("drilldown_target", "下鑽"),
    )

    def __init__(self, rows: Sequence[WorkbenchReviewItem] = (), parent=None) -> None:
        super().__init__(rows, parent)


class WorkbenchEvidenceFeedTableModel(_WorkbenchTableModel):
    COLUMNS = (
        ("label", "證據來源"),
        ("status", "狀態"),
        ("summary", "摘要"),
    )

    def __init__(self, rows: Sequence[WorkbenchEvidenceFeedItem] = (), parent=None) -> None:
        super().__init__(rows, parent)


class WorkbenchActionItemTableModel(_WorkbenchTableModel):
    COLUMNS = (
        ("queue_group", "佇列"),
        ("severity", "嚴重度"),
        ("source_label", "來源"),
        ("title", "待處理事項"),
        ("summary", "摘要"),
    )

    def __init__(self, rows: Sequence[WorkbenchActionItem] = (), parent=None) -> None:
        super().__init__(rows, parent)


class WorkbenchOperatingLoopTableModel(_WorkbenchTableModel):
    COLUMNS = (
        ("label", "步驟"),
        ("cadence", "節奏"),
        ("status", "狀態"),
        ("summary", "摘要"),
        ("source_trace", "Source trace"),
        ("linked_item_ids", "連結項目"),
        ("drilldown_target", "下鑽"),
        ("guidance", "人工提示"),
        ("write_intent", "寫入意圖"),
    )

    def __init__(self, rows: Sequence[WorkbenchOperatingLoopStep] = (), parent=None) -> None:
        super().__init__(rows, parent)


class WorkbenchEvidenceTableModel(_WorkbenchTableModel):
    COLUMNS = (
        ("label", "證據"),
        ("status", "狀態"),
        ("summary", "摘要"),
    )

    def __init__(self, rows: Sequence[WorkbenchEvidenceSummary] = (), parent=None) -> None:
        super().__init__(rows, parent)


class WorkbenchChecklistTableModel(_WorkbenchTableModel):
    COLUMNS = (
        ("label", "檢查項目"),
        ("status", "狀態"),
        ("summary", "摘要"),
    )

    def __init__(self, rows: Sequence[WorkbenchChecklistItem] = (), parent=None) -> None:
        super().__init__(rows, parent)


class AdviceRecommendationTableModel(_WorkbenchTableModel):
    COLUMNS = (
        ("stock_code", "標的"),
        ("advice_action", "動作"),
        ("quick_reasons", "支持／反證"),
        ("primary_risk", "主要風險"),
        ("evidence_status", "資料與執行狀態"),
        # 保留具名唯讀欄位，供既有 model consumer 與輔助讀取使用；View 會收合。
        ("data_quality", "資料品質（明細）"),
        ("execution_feasibility", "可成交性（明細）"),
    )

    def __init__(self, rows: Sequence[RecommendationAdviceDTO] = (), parent=None) -> None:
        super().__init__(rows, parent)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        field_name = self.COLUMNS[index.column()][0]
        row = self._rows[index.row()]
        if field_name == "stock_code":
            stock_code = str(row.stock_code or "").strip()
            stock_name = str(row.stock_name or "").strip()
            exact_source = bool(row.source_result_id)
            display = f"{stock_code} {stock_name}" if exact_source and stock_name else stock_code
            detail = (
                f"股票代碼：{stock_code}；股票名稱：{stock_name}；"
                f"保存結果已對齊：{row.source_result_id}"
                if exact_source and stock_name
                else f"股票代碼：{stock_code}；股票名稱：未與目前保存結果核對"
            )
            if role == Qt.DisplayRole:
                return display
            if role in {Qt.ToolTipRole, Qt.AccessibleTextRole}:
                return detail
            return None
        if field_name in {"quick_reasons", "primary_risk", "evidence_status"}:
            display, detail = _advice_quick_read(row, field_name)
            if role == Qt.DisplayRole:
                return display
            if role == Qt.ToolTipRole:
                return detail
            if role == Qt.AccessibleTextRole:
                return detail
            return None
        if field_name not in {"advice_action", "data_quality", "execution_feasibility"}:
            return super().data(index, role)
        raw = getattr(row, field_name, None)
        raw_text = raw.value if isinstance(raw, Enum) else str(raw or "").strip()
        label = _advice_display_label(field_name, raw_text)
        if role == Qt.DisplayRole:
            return label
        if role == Qt.ToolTipRole:
            return f"原始值：{raw_text or '未知'}"
        if role == Qt.AccessibleTextRole:
            return f"{label}；原始值：{raw_text or '未知'}"
        return super().data(index, role)


class AdviceCandidateTableModel(AdviceRecommendationTableModel):
    """Professional research candidates only; never used for formal Advice rows."""


def _advice_display_label(field_name: str, raw_value: str) -> str:
    if not raw_value:
        return "未知"
    maps = {
        "advice_action": {
            "RESEARCH": "研究",
            "ADD_CANDIDATE": "新增候選",
            "HOLD": "持有",
            "REDUCE_CANDIDATE": "減碼候選",
            "EXIT_CANDIDATE": "退出候選",
            "AVOID": "避開",
            "NO_NEW_POSITION": "暫不新增部位",
        },
        "data_quality": {
            "VERIFIED": "已驗證",
            "OBSERVED": "已觀測",
            "PARTIAL": "部分資料",
            "DEGRADED": "降級",
            "MISSING": "缺漏",
            "UNAVAILABLE": "不可用",
        },
        "execution_feasibility": {
            "FEASIBLE": "原狀態：可成交",
            "NOT_FEASIBLE": "原狀態：不可成交",
            "PARTIAL": "原狀態：部分可成交",
            "UNKNOWN": "未知",
            "UNAVAILABLE": "不可用",
        },
    }
    return maps[field_name].get(raw_value.upper(), raw_value)


def _advice_quick_read(row: RecommendationAdviceDTO, field_name: str) -> tuple[str, str]:
    """在建議列展示短摘要，完整欄位仍可由提示與選列詳情核對。"""

    if field_name == "quick_reasons":
        support = tuple(_public_advice_reason(item) for item in row.why_reasons if str(item).strip())
        counter = tuple(
            _public_advice_reason(item)
            for item in row.why_not_reasons
            if str(item).strip()
        )
        support_text = _first_reason(support)
        counter_text = _first_reason(counter)
        display = (
            f"支持：{_compact_advice_text(support_text)}｜"
            f"反證：{_compact_advice_text(counter_text)}"
        )
        detail = (
            f"支持理由：{'；'.join(support) if support else '未提供'}\n"
            f"反證／不支持理由：{'；'.join(counter) if counter else '未提供'}"
        )
        return display, detail

    if field_name == "primary_risk":
        risks = tuple(_public_advice_reason(item) for item in row.risk_reasons if str(item).strip())
        display = _compact_advice_text(risks[0]) if risks else "未提供風險判讀"
        detail = "風險判讀：" + ("；".join(risks) if risks else "未提供；不能據此推定沒有風險")
        if len(risks) > 1:
            display += f"（另 {len(risks) - 1} 項）"
        return display, detail

    quality = _advice_display_label("data_quality", str(row.data_quality or "").strip())
    feasibility = _advice_display_label(
        "execution_feasibility", str(row.execution_feasibility or "").strip()
    )
    if feasibility.startswith("原狀態："):
        feasibility = feasibility.removeprefix("原狀態：")
    data_date = str(row.data_as_of_date or "").strip() or "未知"
    display = f"{quality}｜成交：{feasibility}｜資料日：{data_date}"
    detail = (
        f"資料品質：{quality}\n可成交性：{feasibility}\n"
        f"決策日：{str(row.decision_date or '').strip() or '未知'}\n"
        f"資料日：{data_date}"
    )
    return display, detail


def _first_reason(values: tuple[str, ...]) -> str:
    if not values:
        return "未提供"
    suffix = f"（另 {len(values) - 1} 項）" if len(values) > 1 else ""
    return values[0] + suffix


def _compact_advice_text(value: str, *, limit: int = 34) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _public_advice_reason(value: object) -> str:
    """將常見 Advice 診斷碼改成使用者語句；保留未知文字但隱去底線格式。"""

    raw = " ".join(str(value or "").split())
    known = {
        "evidence_quality_missing": "缺少合格證據",
        "research_gate_passed": "符合研究條件",
        "position_limit_review": "持倉限制待覆核",
        "data_quality_missing": "資料品質缺漏",
        "data_quality_degraded": "資料品質降級",
        "data_quality_not_observed": "資料尚未驗證",
        "guided_mode_strategy_not_promoted": "策略尚未正式採用",
        "guided_mode_strategy_parameters_not_locked": "策略參數尚未鎖定",
        "guided_mode_strategy_disclosure_incomplete": "策略揭露尚未完整",
        "professional_candidate_research_only": "僅供研究，不屬正式建議",
        "strategy_status_not_promoted": "策略尚未正式採用",
        "execution_not_feasible": "目前不可成交",
        "price_current_session_missing": "缺少當日價格",
        "source_not_fresh": "來源資料非最新",
        "low_liquidity_review": "需覆核流動性",
        "source_missing": "來源缺漏",
        "execution_feasibility_not_confirmed": "可成交性尚未核實",
    }
    return known.get(raw, raw.replace("_", " "))


class AdvicePortfolioTableModel(_WorkbenchTableModel):
    COLUMNS = (
        ("stock_code", "標的"),
        ("advice_action", "動作"),
        ("target_weight_bp", "目標配置（bp）"),
        ("current_weight_bp", "目前配置（bp）"),
        ("weight_gap_bp", "配置差距（bp）"),
        ("data_quality", "資料品質"),
        ("execution_feasibility", "可成交性"),
    )

    def __init__(self, rows: Sequence[PortfolioAdviceDTO] = (), parent=None) -> None:
        super().__init__(rows, parent)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        field_name = self.COLUMNS[index.column()][0]
        row = self._rows[index.row()]
        if field_name in {"advice_action", "data_quality", "execution_feasibility"}:
            raw = getattr(row, field_name, None)
            raw_text = raw.value if isinstance(raw, Enum) else str(raw or "").strip()
            label = _advice_display_label(field_name, raw_text)
            if role == Qt.DisplayRole:
                return label
            if role == Qt.ToolTipRole:
                return f"原始值：{raw_text or '未知'}"
            if role == Qt.AccessibleTextRole:
                return f"{label}；原始值：{raw_text or '未知'}"
            return super().data(index, role)
        if field_name in {"target_weight_bp", "current_weight_bp", "weight_gap_bp"}:
            raw = getattr(row, field_name, None)
            raw_text = str(raw) if raw is not None else "未知"
            if role == Qt.DisplayRole:
                return raw_text
            if role == Qt.ToolTipRole:
                return f"原始值：{raw_text}{' bp' if raw is not None else ''}"
            if role == Qt.AccessibleTextRole:
                return (
                    f"{raw_text} bp；原始整數基點值：{raw_text}"
                    if raw is not None
                    else "未知；原始整數基點值：未知"
                )
        return super().data(index, role)


class PositionHealthTableModel(_WorkbenchTableModel):
    """以共用 typed projection 呈現 Paper health，不讀取原始 dictionary。"""

    COLUMNS = (
        ("stock_code", "標的"),
        ("review_required", "需要確認"),
        ("decision_date", "決策日"),
        ("source_status", "來源狀態"),
        ("action_suitability", "研究建議"),
        ("why", "評估原因"),
    )

    def __init__(
        self,
        rows: Sequence[PositionHealthPresentationDTO] = (),
        parent=None,
    ) -> None:
        super().__init__(rows, parent)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if index.isValid() and 0 <= index.row() < len(self._rows):
            row = self._rows[index.row()]
            field_name = self.COLUMNS[index.column()][0]
            if role == Qt.ToolTipRole and field_name == "stock_code":
                position_id = str(row.position_id or "").strip() or "未提供"
                snapshot_id = str(row.source_snapshot_id or "").strip() or "未提供"
                cohort_key = str(row.cohort_key or "").strip() or "未提供"
                return (
                    f"Paper 部位識別（精確 position_id）：{position_id}\n"
                    f"來源 snapshot ID：{snapshot_id}\n"
                    f"cohort key：{cohort_key}\n"
                    "研究資料身分不以股票代號代替。"
                )
        if role == Qt.DisplayRole and index.isValid() and 0 <= index.row() < len(self._rows):
            field_name = self.COLUMNS[index.column()][0]
            row = self._rows[index.row()]
            if field_name == "source_status":
                return position_health_source_status_label(row.source_status)
            if field_name == "action_suitability":
                return position_health_action_label(row.action_suitability)
            if field_name == "why":
                return position_health_reason_text(row.why)
            if field_name == "review_required":
                return position_health_review_label(row.review_required)
        return super().data(index, role)


def _display_value(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, tuple):
        return "；".join(_display_token(str(item)) for item in value) or "無"
    if isinstance(value, list):
        return "；".join(_display_token(str(item)) for item in value) or "無"
    if value is None:
        return ""
    return _display_token(str(value))


def display_workbench_value(value: str) -> str:
    return _display_token(value)


def _display_token(value: str) -> str:
    text = value.strip()
    if not text:
        return ""

    token_map = {
        "Daily Decision snapshot": "每日決策快照",
        "Data quality": "資料品質",
        "Evidence gate": "證據門檻",
        "Production Scheduler": "正式排程器",
        "Watchlist trigger review": "觀察清單觸發覆盤",
        "Portfolio alert review": "持倉警示覆盤",
        "Historical replay simulated evidence": "歷史 replay 模擬證據",
        "Weekly evidence operations history": "每週 evidence operations 歷史",
        "Multi-day dry-run": "多日 dry-run",
        "Source gaps 收斂狀態": "來源缺口收斂狀態",
        "Read-only Agent report sample": "唯讀 Agent 報告樣本",
        "Decision snapshot freshness": "決策快照新鮮度",
        "Evidence gate status": "證據門檻狀態",
        "Manual review note": "人工覆盤註記",
        "Scheduler write-mode": "排程器寫入模式",
        "Weekly review history": "每週覆盤歷史",
        "Scheduler gate": "排程 Gate",
        "daily": "每日",
        "weekly_until_3": "每週直到 3 筆",
        "daily_until_3": "每日直到 3 筆",
        "after_manual_review": "人工覆盤後",
        "phase_gate": "Phase gate",
        "read_only_sources": "唯讀來源",
        "read_only_sources_plus_historical_replay": "唯讀來源 + 歷史 replay summary",
        "missing": "缺漏",
        "source_missing": "來源缺件",
        "read_failure": "來源讀取失敗",
        "invalid_evidence": "證據無效",
        "machine_candidate": "機器候選",
        "machine_verified": "機器已驗證",
        "machine_degraded": "機器觀測降級",
        "candidate": "研究候選",
        "candidate_degraded": "研究候選（資料降級）",
        "challenger_candidate": "challenger 研究候選",
        "active_model": "active model",
        "future_blocked": "未來日期已阻擋",
        "stale": "資料過期（stale）",
        "unknown": "未知",
        "verified": "已驗證",
        "unverified": "未驗證",
        "HOLD": "持有",
        "WATCH": "觀察／未知",
        "REDUCE_CANDIDATE": "減碼候選",
        "EXIT_CANDIDATE": "退出候選",
        "warning": "警告",
        "info": "資訊",
        "observed": "已觀測",
        "ready": "已就緒",
        "degraded": "降級",
        "blocked": "封鎖",
        "done": "完成",
        "off": "關閉",
        "action_required": "需要處理",
        "waiting_for_time": "等待真實時間累積",
        "manual_required": "需要人工覆盤",
        "pre_v2_readiness": "Pre-V2 準備度",
        "watchlist_trigger": "觀察清單觸發",
        "portfolio_alert": "持倉警示",
        "risk_prompt": "風險提示",
        "continuity_review": "連續研究檢討",
        "decision_continuity_review": "連續研究檢討",
        "portfolio_review": "持倉覆盤",
        "daily_review": "每日判讀",
        "evidence_gate": "證據門檻",
        "replay_diagnostics": "Replay 診斷",
        "manual_review": "人工覆盤",
        "linked": "已精確連結",
        "unlinked": "未連結",
        "conflict": "身份衝突",
        "accepted": "已納入研究",
        "skipped": "已略過",
        "unrecorded": "尚未記錄",
        "scheduled": "已排程",
        "due": "今日到期",
        "overdue": "已逾期",
        "invalid": "無效",
        "evidence_mode": "證據模式",
        "daily_decision": "每日決策",
        "evidence_review": "證據覆盤",
        "daily_decision_snapshot": "Daily Decision snapshot",
        "evidence_review_readiness": "Evidence Review readiness",
        "portfolio_alerts": "Portfolio alerts",
        "replay_summary_diagnostics": "Replay summary diagnostics",
        "DecisionDeskSnapshot": "DecisionDeskSnapshot",
        "DecisionDeskSnapshot.portfolio_alerts": "DecisionDeskSnapshot.portfolio_alerts",
        "PreV2ReadinessReport": "PreV2ReadinessReport",
        "HistoricalReplaySummary": "HistoricalReplaySummary",
        "portfolio_alert_requires_manual_review": "portfolio_alert_requires_manual_review",
        "watchlist_trigger_requires_manual_review": "watchlist_trigger_requires_manual_review",
        "replay_summary_not_supplied": "未提供 replay summary",
        "decision_desk_snapshot_missing": "缺 Daily Decision snapshot",
        "why_not_payload_missing": "缺 Why Not payload",
        "liquidity_gate_payload_missing": "缺 liquidity gate payload",
        "screening_matrix_missing": "缺 screening matrix",
        "strategy_lifecycle_evidence_table_missing": "缺 strategy lifecycle evidence table",
        "insufficient_weekly_history_records": "每週歷史筆數不足",
        "insufficient_dry_run_days": "多日 dry-run 天數不足",
        "simulated_scheduler": "模擬 scheduler（simulated_scheduler）",
        "not_production_readiness": "非 production readiness 證據",
        "missing_industry_benchmark": "缺產業基準",
        "pending_insufficient_future_data": "等待未來資料不足",
    }
    if text in token_map:
        return token_map[text]

    if text.startswith("source_gap_coverage:"):
        payload = text.split(":", 1)[1]
        source, _, ratio = payload.partition("=")
        return f"來源缺口覆蓋：{_display_token(source)} {ratio}"
    if text.startswith("source_gap:"):
        return f"來源缺口：{_display_token(text.split(':', 1)[1])}"
    if text.startswith("payload_gap:"):
        return f"payload 缺口：{_display_token(text.split(':', 1)[1])}"
    if text.startswith("outcome_maturity:"):
        values = _key_values(text.split(":", 1)[1])
        return (
            f"結果成熟度：已成熟 {_fmt_int(values.get('ready'))}；"
            f"等待未來資料 {_fmt_int(values.get('pending_future_data'))}"
        )
    if text.startswith("benchmark_coverage:"):
        return _coverage_text("市場基準覆蓋", text)
    if text.startswith("industry_benchmark_coverage:"):
        return _coverage_text("產業基準覆蓋", text)
    if text.startswith("missing_benchmark:"):
        return f"缺市場基準：{_fmt_int(text.split(':', 1)[1])}"
    if text.startswith("missing_industry_benchmark:"):
        return f"缺產業基準：{_fmt_int(text.split(':', 1)[1])}"
    if text.startswith("pending_future_data:"):
        return f"等待未來資料限制：{_fmt_int(text.split(':', 1)[1])}"
    if text.startswith("phase0_gate_not_satisfied:"):
        return "Phase 0 限制：weekly history 與 multi-day dry-run 必須靠真實時間累積"
    if text.startswith("replay_direction_assessment:"):
        return "方向判讀：市場基準已可用，但產業基準、來源缺口或未成熟 outcome 仍阻擋 production readiness"

    return text


def _row_status(row: object) -> str:
    return str(
        getattr(
            row,
            "status",
            getattr(row, "source_status", getattr(row, "severity", "")),
        )
        or ""
    )


def _is_attention_status(status: str) -> bool:
    return status in {
        "critical",
        "warning",
        "degraded",
        "missing",
        "blocked",
        "action_required",
        "waiting_for_time",
        "manual_required",
        "source_missing",
        "invalid_evidence",
        "machine_candidate",
        "machine_degraded",
        "stale",
    }


def _status_tone(status: str) -> dict[str, str]:
    token = str(status)
    if token in {"critical", "blocked", "missing", "source_missing", "invalid_evidence", "future_blocked"}:
        return {"fg": MIDNIGHT_ANALYST.status_error, "bg": "#27162d"}
    if token in {
        "warning",
        "degraded",
        "action_required",
        "manual_required",
        "waiting_for_time",
        "machine_degraded",
        "stale",
    }:
        return {"fg": MIDNIGHT_ANALYST.status_warning, "bg": "#221a10"}
    if token in {"ready", "done", "passed"}:
        return {"fg": MIDNIGHT_ANALYST.status_success, "bg": "#0b2624"}
    if token in {"observed", "manual_observed", "info", "machine_candidate", "candidate", "challenger_candidate", "active_model"}:
        return {"fg": MIDNIGHT_ANALYST.status_info, "bg": "#0b1c27"}
    if token == "candidate_degraded":
        return {"fg": MIDNIGHT_ANALYST.status_warning, "bg": "#221a10"}
    return {"fg": "#94a3b8", "bg": "#111827"}


def _coverage_text(label: str, text: str) -> str:
    values = _key_values(text.split(":", 1)[1])
    return (
        f"{label}：{_fmt_int(values.get('covered'))}/{_fmt_int(values.get('total'))}，"
        f"缺 {_fmt_int(values.get('missing'))}"
    )


def _key_values(payload: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in payload.split(","):
        key, separator, value = part.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def _fmt_int(value: str | None) -> str:
    try:
        return f"{int(value or 0):,}"
    except ValueError:
        return str(value or 0)
