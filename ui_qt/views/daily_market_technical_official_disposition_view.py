"""已保存 F17 母體的唯讀查詢、個股檢視與跨頁比較介面。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any, Literal, cast

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app_module.daily_market_technical_official_disposition_bundle_catalog_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT,
    DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1,
    DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1,
    DailyMarketTechnicalOfficialDispositionBundleCatalogV1,
)
from app_module.daily_market_technical_official_disposition_bookmark_v1 import (
    DailyMarketTechnicalOfficialDispositionBookmarkComparisonV1,
    DailyMarketTechnicalOfficialDispositionBookmarkV1,
    canonical_daily_market_technical_official_disposition_bookmark_json_v1,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_READER_V1_MAX_PAGE_SIZE,
    DailyMarketTechnicalOfficialDispositionPageRequestV1,
    DailyMarketTechnicalOfficialDispositionQueryPageV1,
    DailyMarketTechnicalOfficialDispositionQueryResultRowV1,
    DailyMarketTechnicalOfficialDispositionReadSessionV1,
    DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1,
    open_daily_market_technical_official_disposition_bundle_session_v1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_MAX_BYTES,
    DailyMarketTechnicalOfficialDispositionQueryV1,
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_method_contract_v4 import (
    daily_market_technical_method_contract_v4_payload,
)
from ui_qt.models.saved_research_page_table_model import (
    SavedResearchPageTableModel, SavedResearchTableRow,
)
from ui_qt.workers.task_worker import TaskWorker


_STATE_VALUES = ("match", "no_match", "unknown")
_STATE_LABELS = {"match": "符合", "no_match": "不符合", "unknown": "未知"}
_NO_RULE_STATE_FILTER = "all"
_RULE_STATE_SELECTIONS = (
    ("match",),
    ("no_match",),
    ("unknown",),
    ("match", "no_match"),
    ("match", "unknown"),
    ("no_match", "unknown"),
    ("match", "no_match", "unknown"),
)
_MAX_STOCK_FILTER_INPUT_CHARACTERS = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS * 18 - 2
)
_SCOPE_VALUES = ("included_processed", "included_pending", "excluded")
_SCOPE_LABELS = {
    "included_processed": "納入且已處理",
    "included_pending": "納入但待處理",
    "excluded": "明示排除",
}
_MARKET_STATE_VALUES = ("assigned_twse", "assigned_tpex", "unknown")
_MARKET_STATE_LABELS = {
    "assigned_twse": "上市 TWSE",
    "assigned_tpex": "上櫃 TPEx",
    "unknown": "未知",
}
_DISPOSAL_STATE_VALUES = (
    "reported_upcoming",
    "reported_active",
    "reported_elapsed_only",
    "unknown",
)
_DISPOSAL_STATE_LABELS = {
    "reported_upcoming": "已公告、尚未生效",
    "reported_active": "公告處置中",
    "reported_elapsed_only": "僅有已經過的處置紀錄",
    "unknown": "未知",
}
_RULE_LABELS = {
    "ma5_20_golden_cross": "MA5／MA20 金叉",
    "kd_golden_cross": "K／D 金叉",
    "macd_golden_cross": "MACD 金叉",
    "volume_ratio_20_including_current": "量能比 20（含當日）",
    "volume_ratio_5_including_current": "量能比 5（含當日）",
}
_RULE_PARAMETER_LABELS = {
    "current": "當日條件",
    "previous": "前一觀測日條件",
    "formula": "指標方法",
    "short_window": "短期窗口",
    "long_window": "長期窗口",
    "fastk_period": "Fast K 期數",
    "slowk_matype": "慢速 K 平滑方法",
    "slowk_period": "慢速 K 期數",
    "slowd_matype": "慢速 D 平滑方法",
    "slowd_period": "慢速 D 期數",
    "fastperiod": "MACD 快線期數",
    "slowperiod": "MACD 慢線期數",
    "signalperiod": "訊號線期數",
    "includes_current_session": "包含當日",
    "threshold_ratio": "契約門檻比率",
    "window_sessions": "契約觀察窗口（交易日）",
}
_TECHNICAL_UNKNOWN_REASON_LABELS = {
    "insufficient_observed_sessions_for_cross": "可觀測交易日不足，無法判斷交叉。",
    "feature_missing_or_duplicate": "所需特徵缺少或重複。",
    "feature_not_observed": "所需特徵尚未觀測到。",
    "feature_not_finite": "所需特徵不是有限數值。",
    "feature_lineage_unverified": "所需特徵的來源脈絡未核實。",
    "feature_source_fingerprint_invalid": "所需特徵的來源指紋無效。",
    "feature_source_id_mismatch": "所需特徵來源不符。",
    "feature_method_id_mismatch": "所需特徵計算方法不符。",
    "feature_method_version_mismatch": "所需特徵計算版本不符。",
    "feature_method_parameters_mismatch": "所需特徵計算參數不符。",
    "feature_unit_mismatch": "所需特徵單位不符。",
    "feature_source_identity_mismatch": "所需特徵來源身份不一致。",
    "warmup_requirement_mismatch": "所需暖機期數不符。",
    "warmup_or_continuity_unverified": "指標暖機期或交易日連續性未核實。",
    "negative_volume_value": "成交股數為負值。",
    "volume_value_not_integral_shares": "成交股數不是整數股數。",
    "non_positive_moving_average": "移動平均值不是正數。",
    "stochastic_value_out_of_range": "隨機指標數值超出可核範圍。",
    "incomplete_volume_window": "量能觀察窗口不完整。",
    "volume_value_missing": "成交股數缺值。",
    "volume_average_denominator_zero": "量能平均值分母為零。",
    "observed_prefix_not_contiguous": "來源觀測交易日不連續。",
    "source_window_fingerprint_mismatch": "來源窗口指紋不一致。",
    "source_availability_unavailable": "來源可用狀態標示為不可用。",
    "source_available_after_decision_cutoff": "來源可用時間晚於決策截止時間。",
    "verified_availability_missing_timestamp": "來源標示已核可用，但缺少可用時間。",
}
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_KEEPALIVE_WORKERS: set[TaskWorker] = set()


def _parse_stock_code_filter(
    raw: object,
    *,
    input_was_truncated: bool = False,
) -> tuple[str, ...]:
    if input_was_truncated:
        raise ValueError("technical_official_view_stock_filter_size_limit")
    if not isinstance(raw, str):
        raise ValueError("technical_official_view_stock_code_invalid")
    try:
        if (
            len(raw) > _MAX_STOCK_FILTER_INPUT_CHARACTERS
            or len(raw.encode("utf-8"))
            > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_MAX_BYTES
        ):
            raise ValueError("technical_official_view_stock_filter_size_limit")
    except UnicodeError as exc:
        raise ValueError("technical_official_view_stock_code_invalid") from exc
    if not raw.strip():
        raise ValueError("technical_official_view_stock_code_required")
    comma_groups = re.split(r"[,，]", raw)
    if any(not group.strip() for group in comma_groups):
        raise ValueError("technical_official_view_stock_code_invalid")
    codes = tuple(token for group in comma_groups for token in group.split())
    if len(codes) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS:
        raise ValueError("technical_official_view_stock_code_limit")
    if any(_STOCK_CODE_RE.fullmatch(code) is None for code in codes):
        raise ValueError("technical_official_view_stock_code_invalid")
    if len(set(codes)) != len(codes):
        raise ValueError("technical_official_view_stock_code_duplicate")
    return tuple(sorted(codes))


class _StockCodeFilterLineEdit(QLineEdit):
    """保留過長貼上的跡象，避免 QLineEdit 靜默截斷後套用代碼前綴。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._input_was_truncated = False
        self.textChanged.connect(self._clear_overflow_after_edit)
        self.inputRejected.connect(self._mark_overflow)

    @property
    def input_was_truncated(self) -> bool:
        return self._input_was_truncated

    def setText(self, text: str) -> None:
        super().setText(text)
        self._input_was_truncated = len(text) > self.maxLength()

    def _mark_overflow(self) -> None:
        self._input_was_truncated = True

    def _clear_overflow_after_edit(self, text: str) -> None:
        if len(text) < self.maxLength():
            self._input_was_truncated = False


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionStockSelectionV1:
    """個股訊號帶著原頁請求與已核列身份，供 host 接續導航。"""

    page_request: DailyMarketTechnicalOfficialDispositionPageRequestV1
    stock_code: str
    row_identity_sha256: str
    row: DailyMarketTechnicalOfficialDispositionQueryResultRowV1

    def __post_init__(self) -> None:
        if (
            type(self.page_request) is not DailyMarketTechnicalOfficialDispositionPageRequestV1
            or type(self.row) is not DailyMarketTechnicalOfficialDispositionQueryResultRowV1
            or self.stock_code != self.row.stock_code
            or self.stock_code == ""
            or self.row_identity_sha256 != self.row.row_identity_sha256
        ):
            raise ValueError("technical_official_view_stock_selection_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionComparisonV1:
    """同一 exact operation 下，依各自原頁請求重讀的有界比較結果。"""

    query_identity_sha256: str
    items: tuple[DailyMarketTechnicalOfficialDispositionStockSelectionV1, ...]

    def __post_init__(self) -> None:
        if (
            len(self.query_identity_sha256) != 64
            or not 2 <= len(self.items) <= 5
            or len({item.stock_code for item in self.items}) != len(self.items)
            or any(
                item.page_request.query.query_identity_sha256 != self.query_identity_sha256
                or item.row.technical_row is None
                for item in self.items
            )
        ):
            raise ValueError("technical_official_comparison_invalid")


@dataclass(frozen=True, slots=True)
class _SourceChoice:
    output_root: str
    bundle_identity_sha256: str
    manifest_sha256: str


@dataclass(frozen=True, slots=True)
class _OpenedQuery:
    source: _SourceChoice
    session: DailyMarketTechnicalOfficialDispositionReadSessionV1
    result: DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1
    page_request: DailyMarketTechnicalOfficialDispositionPageRequestV1
    page: DailyMarketTechnicalOfficialDispositionQueryPageV1


@dataclass(frozen=True, slots=True)
class _RestoredBookmark:
    opened: _OpenedQuery
    bookmark: DailyMarketTechnicalOfficialDispositionBookmarkV1
    selected_row: DailyMarketTechnicalOfficialDispositionQueryResultRowV1
    basket: tuple[DailyMarketTechnicalOfficialDispositionStockSelectionV1, ...]


def _rule_keys() -> tuple[str, ...]:
    payload = daily_market_technical_method_contract_v4_payload()
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, (str, bytes)):
        raise ValueError("technical_official_view_method_contract_invalid")
    keys = tuple(
        str(item["key"])
        for item in raw_rules
        if isinstance(item, Mapping) and isinstance(item.get("key"), str)
    )
    if len(keys) != 5 or len(set(keys)) != 5:
        raise ValueError("technical_official_view_method_contract_invalid")
    return keys


def _rule_contracts_by_key() -> dict[str, Mapping[str, object]]:
    payload = daily_market_technical_method_contract_v4_payload()
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, (str, bytes)):
        raise ValueError("technical_official_view_method_contract_invalid")
    rules = {
        cast(str, item["key"]): cast(Mapping[str, object], item)
        for item in raw_rules
        if isinstance(item, Mapping) and isinstance(item.get("key"), str)
    }
    if len(rules) != 5 or tuple(rules) != _rule_keys():
        raise ValueError("technical_official_view_method_contract_invalid")
    return rules


def _format_rule_contract_description(rule: Mapping[str, object]) -> str:
    parameters = rule.get("parameters")
    if not isinstance(parameters, Mapping):
        return "方法契約未提供規則說明。"
    parts: list[str] = []
    for key, value in parameters.items():
        label = _RULE_PARAMETER_LABELS.get(str(key))
        if label is None:
            continue
        if key == "includes_current_session":
            rendered = "是" if value == "true" else "否" if value == "false" else str(value)
        elif key in {"current", "previous"}:
            rendered = str(value)
        elif isinstance(value, (str, int)) and not isinstance(value, bool):
            rendered = str(value)
        else:
            rendered = "未提供"
        parts.append(f"{label}：{rendered}")
    if not parts:
        return "方法契約未提供規則說明。"
    description = "；".join(parts)
    if str(rule.get("key", "")).startswith("volume_ratio_"):
        description += "；比率計算方式未由方法契約提供"
    return description


def _humanize_technical_unknown_reason(reason: str) -> str:
    if reason in _TECHNICAL_UNKNOWN_REASON_LABELS:
        return f"{_TECHNICAL_UNKNOWN_REASON_LABELS[reason]}（保存原因：{reason}）"
    if reason.startswith("incomplete_volume_window:"):
        count = reason.partition(":")[2]
        return f"量能觀察窗口不完整（保存窗口值：{count}；保存原因：{reason}）"
    pieces = reason.split(":", 2)
    if len(pieces) == 3:
        date_text, feature, code = pieces
        description = _TECHNICAL_UNKNOWN_REASON_LABELS.get(code, "特徵資料未通過核驗")
        return f"{date_text} 的 {feature}：{description}（保存原因：{reason}）"
    return f"保存資料中的原因：{reason}"


def _format_saved_date_values(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return "未提供"
    rendered: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            source_id = item.get("source_id")
            dates = item.get("dates")
            if isinstance(dates, Sequence) and not isinstance(dates, (str, bytes)):
                rendered.append(f"{source_id or '來源'}：{'、'.join(str(date) for date in dates) or '未提供'}")
        elif isinstance(item, str):
            rendered.append(item)
    return "；".join(rendered) or "未提供"


def _format_official_event(event: Mapping[str, object], index: int) -> list[str]:
    lines = [f"處置事件 {index}：{event.get('name') or '名稱未提供'}"]
    for key, label in (
        ("announcement_date", "公告日"),
        ("effective_from", "生效日"),
        ("effective_to", "結束日"),
        ("reason", "原因"),
        ("measure", "措施"),
        ("details", "說明"),
    ):
        value = event.get(key)
        if value not in (None, ""):
            lines.append(f"  {label}：{value}")
    dates = event.get("source_data_dates")
    if isinstance(dates, Sequence) and not isinstance(dates, (str, bytes)) and dates:
        lines.append(f"  來源資料日期：{'、'.join(str(item) for item in dates)}")
    return lines


def format_technical_official_research_row_v1(
    row: DailyMarketTechnicalOfficialDispositionQueryResultRowV1,
) -> str:
    """將已核驗的保存列格式化為可讀事實，不計算新指標或推論建議。"""

    if type(row) is not DailyMarketTechnicalOfficialDispositionQueryResultRowV1:
        raise ValueError("technical_official_view_detail_row_invalid")
    fact = row.fact_row.to_dict()
    market_value = fact.get("market_assignment")
    disposal_value = fact.get("official_disposal")
    market = market_value if isinstance(market_value, Mapping) else {}
    disposal = disposal_value if isinstance(disposal_value, Mapping) else {}
    technical = row.technical_row
    scope = _SCOPE_LABELS.get(row.filter_evaluation.row_scope, "未提供")
    status_value = fact.get("technical_status")
    status = {
        "processed": "已處理",
        "pending": "待處理",
        "excluded": "明示排除",
    }.get(str(status_value), "未提供")
    lines = [
        f"股票代碼：{row.stock_code}",
        f"母體列：{scope}",
        f"處理狀態：{status}",
    ]
    exclusion_reason = fact.get("exclusion_reason")
    if isinstance(exclusion_reason, str) and exclusion_reason:
        lines.append(f"排除理由：{exclusion_reason}")
    if technical is None:
        lines.extend((
            "決策日期：此列沒有已處理的技術來源列，日期未隨此列保存。",
            "技術來源交易日：未提供",
        ))
    else:
        lines.extend((
            f"決策日期：{technical.decision_date.isoformat()}",
            f"技術來源最新交易日：{technical.latest_feature_date.isoformat() if technical.latest_feature_date else '未提供'}",
            f"已保存來源列數：{technical.raw_row_count}",
        ))
    lines.append(f"市場名錄資料日期：{_format_saved_date_values(market.get('source_data_dates'))}")
    lines.append(f"處置資料日期：{_format_saved_date_values(disposal.get('source_data_dates'))}")

    market_state = str(market.get("state", "unknown"))
    market_label = _MARKET_STATE_LABELS.get(market_state, "未知")
    market_code = market.get("market")
    market_text = "上市（TWSE）" if market_code == "twse" else "上櫃（TPEx）" if market_code == "tpex" else "未能核定市場"
    lines.extend((
        "",
        f"市場對照：{market_label}；{market_text}",
        f"市場觀察時間：{market.get('snapshot_observed_at') or '未提供'}",
        f"市場來源原因：{market.get('reason_code') or '未提供'}",
        f"處置狀態：{_DISPOSAL_STATE_LABELS.get(str(disposal.get('state')), '未知')}",
        f"處置觀察時間：{disposal.get('observed_at') or '未提供'}",
        f"處置觀察日期：{disposal.get('observed_date') or '未提供'}",
        f"處置來源原因：{disposal.get('reason_code') or '未提供'}",
    ))
    events = disposal.get("events")
    if isinstance(events, Sequence) and not isinstance(events, (str, bytes)) and events:
        for index, event in enumerate(events, start=1):
            if isinstance(event, Mapping):
                lines.extend(_format_official_event(event, index))
    else:
        lines.append("處置事件：未保存符合此股票的事件列。")

    lines.extend(("", "五項已保存技術規則事實："))
    rules_by_key = _rule_contracts_by_key()
    if technical is None:
        lines.append("未產生技術列；五項規則均未評估。")
    else:
        for evidence in technical.rules:
            label = _RULE_LABELS.get(evidence.key, "未提供規則名稱")
            contract = rules_by_key.get(evidence.key)
            description = (
                _format_rule_contract_description(contract)
                if contract is not None
                else "方法契約未提供此規則的定義。"
            )
            lines.append(f"{label}：{_STATE_LABELS.get(evidence.state, '未知')}")
            lines.append(f"  方法契約：{description}")
            lines.append(
                f"  觀察日期：當日 {evidence.feature_date.isoformat() if evidence.feature_date else '未提供'}；"
                f"前一觀測日 {evidence.previous_feature_date.isoformat() if evidence.previous_feature_date else '未提供'}"
            )
            if evidence.numerator is not None:
                lines.append(f"  保存分子：{evidence.numerator}")
            if evidence.denominator is not None:
                lines.append(f"  保存分母：{evidence.denominator}")
            if evidence.ratio is not None:
                lines.append(f"  保存比率：{evidence.ratio}")
            for support in evidence.supports:
                lines.append(f"  支持事實：{support}")
            for counterevidence in evidence.counterevidence:
                lines.append(f"  未符合事實：{counterevidence}")
            if evidence.unknown_reasons:
                lines.extend(
                    f"  未知原因：{_humanize_technical_unknown_reason(reason)}"
                    for reason in evidence.unknown_reasons
                )
    lines.extend((
        "",
        "來源資格：依原保存版本完成核驗；來源不持續監測。",
        "範圍為 current-only；官方 available_at 未知，不具歷史 PIT 資格。",
    ))
    return "\n".join(lines)


def _open_and_execute(
    source: _SourceChoice,
    *,
    conditions: Mapping[str, object],
    page_index: int,
    page_size: int,
    cancel_callback: Callable[[], bool] | None,
) -> _OpenedQuery:
    if cancel_callback is not None and cancel_callback():
        raise ValueError("technical_official_view_cancelled")
    session = open_daily_market_technical_official_disposition_bundle_session_v1(
        bundle_output_root=source.output_root,
        bundle_identity_sha256=source.bundle_identity_sha256,
        expected_manifest_sha256=source.manifest_sha256,
        row_scope_filter=cast(Sequence[Any], conditions["row_scope_filter"]),
        rule_state_filters=cast(Sequence[Any], conditions["rule_state_filters"]),
        combine_mode=cast(Any, conditions["combine_mode"]),
        market_assignment_states=cast(Sequence[str], conditions["market_assignment_states"]),
        official_disposal_states=cast(Sequence[str], conditions["official_disposal_states"]),
        outer_stock_filter_mode=cast(Any, conditions["outer_stock_filter_mode"]),
        outer_stock_codes=cast(Sequence[str], conditions["outer_stock_codes"]),
        sort_clauses=cast(Sequence[DailyMarketTechnicalOfficialDispositionSortClauseV1], conditions["sort_clauses"]),
        cancel_callback=cancel_callback,
    )
    result = session.execute(cancel_callback=cancel_callback)
    request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
        result.query,
        page_index=page_index,
        page_size=page_size,
    )
    page = result.read_page_request(request, cancel_callback=cancel_callback)
    if cancel_callback is not None and cancel_callback():
        raise ValueError("technical_official_view_cancelled")
    return _OpenedQuery(source, session, result, request, page)


def _execute_with_conditions(
    source: _SourceChoice,
    session: DailyMarketTechnicalOfficialDispositionReadSessionV1,
    *,
    conditions: Mapping[str, object],
    page_index: int,
    page_size: int,
    cancel_callback: Callable[[], bool] | None,
) -> _OpenedQuery:
    if (
        session.query.bundle_identity_sha256 != source.bundle_identity_sha256
        or session.query.expected_manifest_sha256 != source.manifest_sha256
        or session.query.bundle_output_root != source.output_root
    ):
        raise ValueError("technical_official_view_source_session_mismatch")
    conditioned = session.with_conditions(
        row_scope_filter=cast(Sequence[Any], conditions["row_scope_filter"]),
        rule_state_filters=cast(Sequence[Any], conditions["rule_state_filters"]),
        combine_mode=cast(Any, conditions["combine_mode"]),
        market_assignment_states=cast(Sequence[str], conditions["market_assignment_states"]),
        official_disposal_states=cast(Sequence[str], conditions["official_disposal_states"]),
        outer_stock_filter_mode=cast(Any, conditions["outer_stock_filter_mode"]),
        outer_stock_codes=cast(Sequence[str], conditions["outer_stock_codes"]),
        sort_clauses=cast(
            Sequence[DailyMarketTechnicalOfficialDispositionSortClauseV1],
            conditions["sort_clauses"],
        ),
        cancel_callback=cancel_callback,
    )
    result = conditioned.execute(cancel_callback=cancel_callback)
    request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
        result.query,
        page_index=page_index,
        page_size=page_size,
    )
    page = result.read_page_request(request, cancel_callback=cancel_callback)
    if cancel_callback is not None and cancel_callback():
        raise ValueError("technical_official_view_cancelled")
    return _OpenedQuery(source, conditioned, result, request, page)


def _conditions_from_query(query: DailyMarketTechnicalOfficialDispositionQueryV1) -> dict[str, object]:
    return {
        "row_scope_filter": query.row_scope_filter,
        "rule_state_filters": query.technical_query.rule_state_filters,
        "combine_mode": query.technical_query.combine_mode,
        "market_assignment_states": query.market_assignment_states,
        "official_disposal_states": query.official_disposal_states,
        "outer_stock_filter_mode": query.outer_stock_filter_mode,
        "outer_stock_codes": query.outer_stock_codes,
        "sort_clauses": query.sort_clauses,
    }


def _find_row(
    page: DailyMarketTechnicalOfficialDispositionQueryPageV1,
    stock_code: str,
    row_identity_sha256: str,
) -> DailyMarketTechnicalOfficialDispositionQueryResultRowV1:
    matches = tuple(
        row for row in page.rows
        if row.stock_code == stock_code and row.row_identity_sha256 == row_identity_sha256
    )
    if len(matches) != 1:
        raise ValueError("technical_official_view_saved_row_missing_or_changed")
    return matches[0]


def _restore_bookmark_exact(
    bookmark: DailyMarketTechnicalOfficialDispositionBookmarkV1,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> _RestoredBookmark:
    origin_request = DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(
        bookmark.origin_page_request_json
    )
    query = origin_request.query
    source = _SourceChoice(
        query.bundle_output_root,
        query.bundle_identity_sha256,
        query.expected_manifest_sha256,
    )
    opened = _open_and_execute(
        source,
        conditions=_conditions_from_query(query),
        page_index=origin_request.page_index,
        page_size=origin_request.page_size,
        cancel_callback=cancel_callback,
    )
    if opened.result.query.query_identity_sha256 != bookmark.query_identity_sha256:
        raise ValueError("technical_official_view_bookmark_query_changed")
    selected_row = _find_row(
        opened.page,
        bookmark.selected_stock_code,
        bookmark.selected_row_identity_sha256,
    )
    pages: dict[str, DailyMarketTechnicalOfficialDispositionQueryPageV1] = {
        origin_request.to_json(): opened.page
    }
    basket: list[DailyMarketTechnicalOfficialDispositionStockSelectionV1] = []
    for saved in bookmark.comparison_items:
        if cancel_callback is not None and cancel_callback():
            raise ValueError("technical_official_view_cancelled")
        request = DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(
            saved.page_request_json
        )
        page = pages.get(saved.page_request_json)
        if page is None:
            page = opened.result.read_page_request(request, cancel_callback=cancel_callback)
            pages[saved.page_request_json] = page
        row = _find_row(page, saved.stock_code, saved.row_identity_sha256)
        basket.append(
            DailyMarketTechnicalOfficialDispositionStockSelectionV1(
                request, row.stock_code, row.row_identity_sha256, row
            )
        )
    return _RestoredBookmark(opened, bookmark, selected_row, tuple(basket))


def _comparison_from_result(
    result: DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1,
    items: Sequence[DailyMarketTechnicalOfficialDispositionStockSelectionV1],
    *,
    cancel_callback: Callable[[], bool] | None,
) -> DailyMarketTechnicalOfficialDispositionComparisonV1:
    if not 2 <= len(items) <= 5:
        raise ValueError("technical_official_view_comparison_requires_two_to_five_stocks")
    verified: list[DailyMarketTechnicalOfficialDispositionStockSelectionV1] = []
    for item in items:
        if cancel_callback is not None and cancel_callback():
            raise ValueError("technical_official_view_cancelled")
        page = result.read_page_request(item.page_request, cancel_callback=cancel_callback)
        row = _find_row(page, item.stock_code, item.row_identity_sha256)
        if row.technical_row is None:
            raise ValueError("technical_official_view_comparison_stock_not_processed")
        verified.append(
            DailyMarketTechnicalOfficialDispositionStockSelectionV1(
                item.page_request, row.stock_code, row.row_identity_sha256, row
            )
        )
    if cancel_callback is not None and cancel_callback():
        raise ValueError("technical_official_view_cancelled")
    return DailyMarketTechnicalOfficialDispositionComparisonV1(
        result.query.query_identity_sha256, tuple(verified)
    )


class DailyMarketTechnicalOfficialDispositionView(QWidget):
    """以 manifest 清單選來源，再以 exact F17 reader 執行完整母體查詢。"""

    stockSelected = Signal(object)
    bookmarkPrepared = Signal(object)
    comparisonReady = Signal(object)
    operationSettled = Signal(str, bool)

    def __init__(self, bundle_output_root: str | Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bundle_output_root = Path(bundle_output_root) if bundle_output_root is not None else None
        self._catalog_page: DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1 | None = None
        self._catalog_cursor: str | None = None
        self._catalog_entries: tuple[DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1, ...] = ()
        self._source: _SourceChoice | None = None
        self._session: DailyMarketTechnicalOfficialDispositionReadSessionV1 | None = None
        self._result: DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1 | None = None
        self._page: DailyMarketTechnicalOfficialDispositionQueryPageV1 | None = None
        self._page_request: DailyMarketTechnicalOfficialDispositionPageRequestV1 | None = None
        self._selected_row: DailyMarketTechnicalOfficialDispositionQueryResultRowV1 | None = None
        self._basket: list[DailyMarketTechnicalOfficialDispositionStockSelectionV1] = []
        self._detail_selection: DailyMarketTechnicalOfficialDispositionStockSelectionV1 | None = None
        self._busy_worker: TaskWorker | None = None
        self._live_workers: set[TaskWorker] = set()
        self._busy_token = 0
        self._revision = 0
        self._closing = False
        self._worker_kind = ""
        self._worker_apply: Callable[[object], None] | None = None
        self._build_ui()
        if self.bundle_output_root is None:
            self._set_status("尚未選擇已保存研究來源資料夾；請先明確選擇。")
        else:
            self._set_status("請更新已保存來源清單；候選資料尚未完整核驗。")

    @property
    def current_page(self) -> DailyMarketTechnicalOfficialDispositionQueryPageV1 | None:
        return self._page

    @property
    def current_result(self) -> DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1 | None:
        return self._result

    @property
    def current_request(self) -> DailyMarketTechnicalOfficialDispositionPageRequestV1 | None:
        return self._page_request

    @property
    def comparison_basket(self) -> tuple[DailyMarketTechnicalOfficialDispositionStockSelectionV1, ...]:
        return tuple(self._basket)

    @property
    def active_worker(self) -> TaskWorker | None:
        return self._busy_worker

    def choose_bundle_output_root(self) -> None:
        if self._closing or self._busy_worker is not None or self._has_running_worker():
            self._set_status("背景工作進行中或畫面正在關閉，暫時不能更換來源資料夾。")
            return
        selected = QFileDialog.getExistingDirectory(
            self,
            "選擇已保存研究來源資料夾",
            str(self.bundle_output_root) if self.bundle_output_root is not None else "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if selected:
            self.set_bundle_output_root(selected)

    def set_bundle_output_root(self, output_root: str | Path) -> bool:
        """設定使用者明示選取的既有資料夾；不建立目錄或自動挑選來源。"""

        if self._closing or self._busy_worker is not None or self._has_running_worker():
            self._set_status("背景工作進行中或畫面正在關閉，暫時不能更換來源資料夾。")
            return False
        candidate = Path(output_root)
        if not candidate.is_absolute() or not candidate.exists() or not candidate.is_dir():
            self._set_status("來源資料夾必須是已存在的絕對路徑。")
            return False
        if self.bundle_output_root == candidate:
            self.refresh_catalog()
            return True

        self._revision += 1
        self.bundle_output_root = candidate
        self._catalog_page = None
        self._catalog_cursor = None
        self._catalog_entries = ()
        self._source = None
        self._session = None
        self._result = None
        self._page = None
        self._page_request = None
        self._selected_row = None
        self._basket.clear()
        self._detail_selection = None
        self.results_stack.setCurrentIndex(0)
        self.detail_text.clear()
        self.audit_json_text.clear()
        self.audit_toggle.setChecked(False)
        self.catalog_list.clear()
        self._render_page()
        self._update_basket_label()
        self.refresh_catalog()
        return True

    def _has_running_worker(self) -> bool:
        for worker in tuple(self._live_workers):
            try:
                if worker.isRunning():
                    return True
            except RuntimeError:
                self._live_workers.discard(worker)
        return False

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        self.page_scroll = QScrollArea()
        self.page_scroll.setObjectName("technicalOfficialDispositionPageScroll")
        self.page_scroll.setWidgetResizable(True)
        content = QWidget()
        content.setMinimumWidth(0)
        content_layout = QVBoxLayout(content)
        self.page_scroll.setWidget(content)
        outer.addWidget(self.page_scroll)
        title = QLabel("官方處置與市場對照研究（已保存資料）")
        title.setObjectName("technicalOfficialDispositionTitle")
        content_layout.addWidget(title)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("technicalOfficialDispositionStatus")
        content_layout.addWidget(self.status_label)

        catalog_box = QGroupBox("已保存的研究來源")
        catalog_layout = QVBoxLayout(catalog_box)
        catalog_controls = QHBoxLayout()
        self.choose_root_button = QPushButton("選擇保存來源資料夾")
        self.refresh_catalog_button = QPushButton("更新來源清單")
        self.next_catalog_button = QPushButton("下一頁來源")
        self.cancel_button = QPushButton("取消背景工作")
        self.choose_root_button.clicked.connect(self.choose_bundle_output_root)
        self.refresh_catalog_button.clicked.connect(self.refresh_catalog)
        self.next_catalog_button.clicked.connect(self.load_next_catalog_page)
        self.cancel_button.clicked.connect(self.cancel_current_operation)
        catalog_controls.addWidget(self.choose_root_button)
        catalog_controls.addWidget(self.refresh_catalog_button)
        catalog_controls.addWidget(self.next_catalog_button)
        catalog_controls.addWidget(self.cancel_button)
        catalog_layout.addLayout(catalog_controls)
        self.catalog_list = QListWidget()
        self.catalog_list.setObjectName("technicalOfficialDispositionCatalog")
        self.catalog_list.currentRowChanged.connect(self._catalog_row_changed)
        catalog_layout.addWidget(self.catalog_list)
        content_layout.addWidget(catalog_box)

        filters_box = QGroupBox("全母體條件（先過濾與全域排序，再分頁）")
        filters_layout = QVBoxLayout(filters_box)
        filters = QGridLayout()
        filters_layout.addLayout(filters)
        self.rule_filter_enabled = QCheckBox("套用技術規則篩選")
        technical_box = QGroupBox("五項已保存技術規則")
        technical_layout = QGridLayout(technical_box)
        technical_layout.addWidget(self.rule_filter_enabled, 0, 0, 1, 2)
        self.rule_state_boxes: dict[str, QComboBox] = {}
        rule_contracts = _rule_contracts_by_key()
        for index, key in enumerate(_rule_keys()):
            label = QLabel(self._rule_label(key))
            label.setWordWrap(True)
            technical_layout.addWidget(label, index + 1, 0)
            box = QComboBox()
            box.setObjectName(f"ruleState_{key}")
            box.addItem("不指定", _NO_RULE_STATE_FILTER)
            for state_selection in _RULE_STATE_SELECTIONS:
                label_text = "、".join(_STATE_LABELS[state] for state in state_selection)
                box.addItem(label_text, state_selection)
            self.rule_state_boxes[key] = box
            technical_layout.addWidget(box, index + 1, 1)
            meaning = QLabel(_format_rule_contract_description(rule_contracts[key]))
            meaning.setWordWrap(True)
            meaning.setObjectName(f"ruleMeaning_{key}")
            technical_layout.addWidget(meaning, index + 1, 2, 1, 2)
        self.combine_box = QComboBox()
        self.combine_box.addItem("所有已選規則（AND）", "AND")
        self.combine_box.addItem("任一已選規則（OR）", "OR")
        technical_layout.addWidget(QLabel("規則合併"), 0, 2)
        technical_layout.addWidget(self.combine_box, 0, 3)
        filters.addWidget(technical_box, 0, 0, 1, 2)

        scope_box = QGroupBox("列範圍")
        scope_layout = QVBoxLayout(scope_box)
        self.scope_checks: dict[str, QCheckBox] = {}
        for scope in _SCOPE_VALUES:
            checkbox = QCheckBox(_SCOPE_LABELS[scope])
            checkbox.setChecked(True)
            self.scope_checks[scope] = checkbox
            scope_layout.addWidget(checkbox)
        filters.addWidget(scope_box, 0, 2)

        official_box = QGroupBox("官方來源狀態（目前來源；不代表 historical PIT）")
        official_layout = QGridLayout(official_box)
        self.market_filter_enabled = QCheckBox("篩選市場")
        official_layout.addWidget(self.market_filter_enabled, 0, 0)
        self.market_checks: dict[str, QCheckBox] = {}
        for index, state in enumerate(_MARKET_STATE_VALUES):
            checkbox = QCheckBox(_MARKET_STATE_LABELS[state])
            self.market_checks[state] = checkbox
            official_layout.addWidget(checkbox, 0, index + 1)
        self.disposal_filter_enabled = QCheckBox("篩選處置狀態")
        official_layout.addWidget(self.disposal_filter_enabled, 1, 0)
        self.disposal_checks: dict[str, QCheckBox] = {}
        for index, state in enumerate(_DISPOSAL_STATE_VALUES):
            checkbox = QCheckBox(_DISPOSAL_STATE_LABELS[state])
            self.disposal_checks[state] = checkbox
            official_layout.addWidget(checkbox, 1, index + 1)
        filters.addWidget(official_box, 1, 0, 1, 3)

        self.stock_filter_enabled = QCheckBox("只查指定股票代碼")
        self.stock_code_input = _StockCodeFilterLineEdit()
        self.stock_code_input.setMaxLength(
            _MAX_STOCK_FILTER_INPUT_CHARACTERS + 1
        )
        self.stock_code_input.setObjectName("technicalOfficialStockCode")
        filters.addWidget(self.stock_filter_enabled, 2, 0)
        filters.addWidget(self.stock_code_input, 2, 1)
        self.page_size_box = QSpinBox()
        self.page_size_box.setRange(1, 256)
        self.page_size_box.setValue(50)
        filters.addWidget(QLabel("每頁列數（上限 256）"), 2, 2)
        filters.addWidget(self.page_size_box, 2, 3)

        self._sort_fields = self._available_sort_fields()
        sort_box = QGroupBox("全域多欄排序（null 無論升冪或降冪都置尾；代碼最後穩定排序）")
        sort_layout = QVBoxLayout(sort_box)
        self.sort_rows_container = QWidget()
        self.sort_rows_layout = QVBoxLayout(self.sort_rows_container)
        self.sort_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.sort_rows: list[tuple[QComboBox, QComboBox, QPushButton, QWidget]] = []
        sort_scroll = QScrollArea()
        sort_scroll.setObjectName("technicalOfficialSortScroll")
        sort_scroll.setWidgetResizable(True)
        sort_scroll.setMaximumHeight(180)
        sort_scroll.setWidget(self.sort_rows_container)
        sort_layout.addWidget(sort_scroll)
        self.add_sort_clause_button = QPushButton("新增排序欄位")
        self.add_sort_clause_button.clicked.connect(self.add_sort_clause)
        sort_layout.addWidget(self.add_sort_clause_button)
        self._add_sort_clause_row("stock_code", "asc")
        filters_layout.addWidget(sort_box)

        action_row = QHBoxLayout()
        self.apply_query_button = QPushButton("套用條件")
        self.clear_filters_button = QPushButton("清除條件")
        self.apply_query_button.clicked.connect(self.apply_filters)
        self.clear_filters_button.clicked.connect(self.clear_filters)
        action_row.addWidget(self.apply_query_button)
        action_row.addWidget(self.clear_filters_button)
        filters_layout.addLayout(action_row)
        content_layout.addWidget(filters_box)

        self.results_stack = QStackedWidget()
        results_panel = QWidget()
        results_layout = QVBoxLayout(results_panel)
        self.counts_label = QLabel("尚未核驗研究來源。")
        self.counts_label.setWordWrap(True)
        results_layout.addWidget(self.counts_label)
        page_controls = QHBoxLayout()
        self.previous_page_button = QPushButton("上一頁")
        self.page_label = QLabel("第 0 / 0 頁")
        self.next_page_button = QPushButton("下一頁")
        self.previous_page_button.clicked.connect(lambda: self.navigate_page(self._page_index() - 1))
        self.next_page_button.clicked.connect(lambda: self.navigate_page(self._page_index() + 1))
        page_controls.addWidget(self.previous_page_button)
        page_controls.addWidget(self.page_label)
        page_controls.addWidget(self.next_page_button)
        results_layout.addLayout(page_controls)
        self.results_table = QTableView()
        self.results_model = SavedResearchPageTableModel[
            DailyMarketTechnicalOfficialDispositionQueryResultRowV1
        ](
            ("代碼", "列範圍", "技術規則", "市場", "處置", "符合條件", "決策日期"),
            maximum_page_size=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_READER_V1_MAX_PAGE_SIZE,
            parent=self.results_table,
        )
        self.results_table.setModel(self.results_model)
        self.results_table.setSortingEnabled(False)
        self.results_table.setObjectName("technicalOfficialDispositionResults")
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.selectionModel().selectionChanged.connect(
            lambda _selected, _deselected: self._table_selection_changed()
        )
        results_layout.addWidget(self.results_table)
        row_actions = QHBoxLayout()
        self.detail_button = QPushButton("查看個股")
        self.add_comparison_button = QPushButton("加入比較")
        self.remove_comparison_button = QPushButton("移除比較")
        self.compare_button = QPushButton("比較已選股票（2–5 檔）")
        self.bookmark_button = QPushButton("準備原研究收藏")
        self.detail_button.clicked.connect(self.show_selected_detail)
        self.add_comparison_button.clicked.connect(self.add_selected_to_comparison)
        self.remove_comparison_button.clicked.connect(self.remove_selected_from_comparison)
        self.compare_button.clicked.connect(self.compare_basket)
        self.bookmark_button.clicked.connect(self.prepare_bookmark)
        for button in (
            self.detail_button, self.add_comparison_button, self.remove_comparison_button,
            self.compare_button, self.bookmark_button,
        ):
            row_actions.addWidget(button)
        results_layout.addLayout(row_actions)
        self.basket_label = QLabel("比較清單：0 檔")
        self.basket_label.setWordWrap(True)
        results_layout.addWidget(self.basket_label)
        self.results_stack.addWidget(results_panel)

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_title = QLabel("個股保存事實（返回原結果頁可回到原選取）")
        detail_layout.addWidget(detail_title)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName("technicalOfficialDispositionDetailScroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setMinimumHeight(150)
        self.detail_scroll.setMaximumHeight(300)
        detail_content = QWidget()
        detail_content.setMinimumWidth(0)
        detail_content_layout = QVBoxLayout(detail_content)
        self.detail_text = QLabel("")
        self.detail_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_text.setWordWrap(True)
        self.detail_text.setMinimumWidth(0)
        detail_content_layout.addWidget(self.detail_text)
        self.audit_toggle = QPushButton("展開完整稽核資料")
        self.audit_toggle.setCheckable(True)
        self.audit_toggle.setChecked(False)
        self.audit_toggle.toggled.connect(self._set_audit_visible)
        detail_content_layout.addWidget(self.audit_toggle)
        self.audit_json_text = QPlainTextEdit()
        self.audit_json_text.setObjectName("technicalOfficialDispositionAuditJson")
        self.audit_json_text.setReadOnly(True)
        self.audit_json_text.setMinimumHeight(180)
        self.audit_json_text.setVisible(False)
        detail_content_layout.addWidget(self.audit_json_text)
        self.detail_scroll.setWidget(detail_content)
        detail_layout.addWidget(self.detail_scroll, 1)
        self.back_button = QPushButton("返回原結果頁")
        self.back_button.clicked.connect(self.return_to_results)
        detail_layout.addWidget(self.back_button)
        self.results_stack.addWidget(detail_panel)
        content_layout.addWidget(self.results_stack, 1)

        self.next_catalog_button.setEnabled(False)
        self.previous_page_button.setEnabled(False)
        self.next_page_button.setEnabled(False)
        self._set_controls_busy(False)

    def _available_sort_fields(self) -> tuple[tuple[str, str], ...]:
        fields: list[tuple[str, str]] = [
            ("stock_code", "股票代碼"),
            ("decision_date", "決策日期"),
            ("latest_feature_date", "最新特徵日期"),
            ("raw_row_count", "來源列數"),
        ]
        for rule in _rule_keys():
            fields.extend(
                (
                    (f"{rule}.ratio", f"{rule} 比率"),
                    (f"{rule}.numerator", f"{rule} 分子"),
                    (f"{rule}.denominator", f"{rule} 分母"),
                )
            )
        fields.extend(
            (
                ("market_assignment.state", "市場狀態"),
                ("market_assignment.snapshot_observed_at", "市場觀察時間"),
                ("official_disposal.state", "處置狀態"),
                ("official_disposal.observed_at", "處置觀察時間"),
                ("official_disposal.observed_date", "處置公告日"),
            )
        )
        return tuple(fields)

    @staticmethod
    def _rule_label(rule_key: str) -> str:
        return _RULE_LABELS.get(rule_key, "未提供規則名稱")

    def _add_sort_clause_row(self, field: str = "", direction: str = "asc") -> None:
        if len(self.sort_rows) >= 32:
            self.add_sort_clause_button.setEnabled(False)
            return
        row_widget = QWidget(self.sort_rows_container)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        field_box = QComboBox(row_widget)
        field_box.setObjectName(f"technicalOfficialSortField_{len(self.sort_rows)}")
        field_box.addItem("選擇排序欄位", "")
        for field_name, label in self._sort_fields:
            field_box.addItem(label, field_name)
        index = field_box.findData(field)
        field_box.setCurrentIndex(index if index >= 0 else 0)
        direction_box = QComboBox(row_widget)
        direction_box.addItem("升冪", "asc")
        direction_box.addItem("降冪", "desc")
        direction_index = direction_box.findData(direction)
        direction_box.setCurrentIndex(direction_index if direction_index >= 0 else 0)
        remove_button = QPushButton("移除此欄位", row_widget)
        row_layout.addWidget(field_box, 1)
        row_layout.addWidget(direction_box)
        row_layout.addWidget(remove_button)
        controls = (field_box, direction_box, remove_button, row_widget)
        self.sort_rows.append(controls)
        remove_button.clicked.connect(lambda _checked=False, item=controls: self._remove_sort_clause_row(item))
        self.sort_rows_layout.addWidget(row_widget)
        self._refresh_sort_editor()

    def _remove_sort_clause_row(
        self,
        controls: tuple[QComboBox, QComboBox, QPushButton, QWidget],
    ) -> None:
        if controls not in self.sort_rows or len(self.sort_rows) <= 1:
            return
        self.sort_rows.remove(controls)
        self.sort_rows_layout.removeWidget(controls[3])
        controls[3].deleteLater()
        self._refresh_sort_editor()

    def _refresh_sort_editor(self) -> None:
        busy = self._busy_worker is not None
        self.add_sort_clause_button.setEnabled(not busy and len(self.sort_rows) < 32)
        for _field, _direction, remove, _widget in self.sort_rows:
            remove.setEnabled(not busy and len(self.sort_rows) > 1)

    def add_sort_clause(self) -> None:
        self._add_sort_clause_row()

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _set_controls_busy(self, busy: bool) -> None:
        for widget in (
            self.choose_root_button,
            self.refresh_catalog_button,
            self.next_catalog_button,
            self.catalog_list,
            self.apply_query_button,
            self.clear_filters_button,
            self.rule_filter_enabled,
            self.combine_box,
            self.stock_filter_enabled,
            self.stock_code_input,
            self.page_size_box,
            self.add_sort_clause_button,
            self.detail_button,
            self.add_comparison_button,
            self.remove_comparison_button,
            self.compare_button,
            self.bookmark_button,
            self.previous_page_button,
            self.next_page_button,
        ):
            widget.setEnabled(not busy)
        for box in self.rule_state_boxes.values():
            box.setEnabled(not busy)
        for box in (*self.scope_checks.values(), *self.market_checks.values(), *self.disposal_checks.values()):
            box.setEnabled(not busy)
        for field_box, direction_box, _remove_button, _row in self.sort_rows:
            field_box.setEnabled(not busy)
            direction_box.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self._refresh_sort_editor()
        if not busy:
            self.next_catalog_button.setEnabled(self._catalog_cursor is not None)
            self.previous_page_button.setEnabled(self._page is not None and self._page.page_index > 0)
            self.next_page_button.setEnabled(
                self._page is not None and self._page.page_index + 1 < self._page.page_count
            )
            self.compare_button.setEnabled(2 <= len(self._basket) <= 5)

    def _start_task(
        self,
        kind: str,
        task: Callable[..., object],
        apply: Callable[[object], None],
    ) -> None:
        if self._closing:
            return
        if self._busy_worker is not None:
            self._set_status("已有背景工作；請等待或取消後再操作。")
            return
        self._revision += 1
        token = self._revision
        worker = TaskWorker(task)
        self._busy_worker = worker
        self._live_workers.add(worker)
        self._busy_token = token
        self._worker_kind = kind
        self._worker_apply = apply
        _KEEPALIVE_WORKERS.add(worker)
        worker.finished.connect(lambda value, current=token: self._task_finished(current, value))
        worker.error.connect(lambda message, current=token: self._task_error(current, message))
        worker.cancelled.connect(lambda current=token: self._task_cancelled(current))
        worker.native_thread_finished.connect(
            lambda target=worker: self._native_worker_finished(target)
        )
        worker.finished.connect(lambda _value, target=worker: _KEEPALIVE_WORKERS.discard(target))
        worker.error.connect(lambda _message, target=worker: _KEEPALIVE_WORKERS.discard(target))
        worker.cancelled.connect(lambda target=worker: _KEEPALIVE_WORKERS.discard(target))
        self._set_controls_busy(True)
        self._set_status(f"背景工作中：{kind}…")
        worker.start()

    def _native_worker_finished(self, worker: TaskWorker) -> None:
        self._live_workers.discard(worker)

    def begin_shutdown(self) -> bool:
        """合作取消本 view 的工作，只有所有 native QThread 停止才回報完成。"""

        if not self._closing:
            self._closing = True
            self._revision += 1
        still_running = False
        for worker in tuple(self._live_workers):
            try:
                worker.cancel(cooperative=True, wait=False)
                if worker.isRunning():
                    still_running = True
                else:
                    self._live_workers.discard(worker)
            except RuntimeError:
                self._live_workers.discard(worker)
        return not still_running

    def _finish_task(self, token: int) -> bool:
        current = token == self._busy_token
        if current:
            self._busy_worker = None
            self._worker_apply = None
            self._set_controls_busy(False)
        return current and token == self._revision and not self._closing

    def _task_finished(self, token: int, value: object) -> None:
        kind = self._worker_kind
        apply = self._worker_apply
        if self._finish_task(token):
            try:
                if apply is not None:
                    apply(value)
                self.operationSettled.emit(kind, True)
            except Exception as exc:
                self._set_status(f"結果未套用：{exc}")
                self.operationSettled.emit(kind, False)
        else:
            self.operationSettled.emit(kind, False)

    def _task_error(self, token: int, message: str) -> None:
        kind = self._worker_kind
        if self._finish_task(token):
            code = message.splitlines()[0] if message else "背景工作失敗"
            self._set_status(f"{kind} 失敗；保留目前已核結果：{code}")
        self.operationSettled.emit(kind, False)

    def _task_cancelled(self, token: int) -> None:
        kind = self._worker_kind
        if self._finish_task(token):
            self._set_status(f"{kind} 已取消；保留目前已核結果。")
        self.operationSettled.emit(kind, False)

    def cancel_current_operation(self) -> None:
        worker = self._busy_worker
        if worker is None:
            return
        self._revision += 1
        worker.cancel()
        self._set_status("已送出合作式取消；目前結果維持不變。")

    def refresh_catalog(self) -> None:
        if self.bundle_output_root is None:
            self.catalog_list.clear()
            self._catalog_entries = ()
            self._catalog_cursor = None
            self._set_status("尚未選擇保存來源資料夾；未掃描磁碟。")
            return
        root = self.bundle_output_root

        def task(cancel_callback: Callable[[], bool] | None = None) -> DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1:
            return DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page(
                limit=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT,
                cancel_callback=cancel_callback,
            )

        self._start_task("更新來源清單", task, self._apply_catalog_page)

    def load_next_catalog_page(self) -> None:
        if self.bundle_output_root is None or self._catalog_cursor is None:
            self._set_status("沒有可續讀的完整來源清單。")
            return
        root = self.bundle_output_root
        cursor = self._catalog_cursor

        def task(cancel_callback: Callable[[], bool] | None = None) -> DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1:
            return DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page(
                limit=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT,
                cursor=cursor,
                cancel_callback=cancel_callback,
            )

        self._start_task("續讀來源清單", task, self._append_catalog_page)

    def _apply_catalog_page(self, value: object) -> None:
        if not isinstance(value, DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1):
            raise ValueError("technical_official_view_catalog_result_invalid")
        self._catalog_page = value
        self._catalog_cursor = value.next_cursor if value.scan_complete else None
        self._catalog_entries = value.entries
        self._render_catalog(value.entries)
        self.next_catalog_button.setEnabled(value.scan_complete and value.next_cursor is not None)
        if value.scan_complete:
            self._set_status(
                f"來源清單已盤點 {value.scanned_entry_count} 項；候選資料尚未完整核驗，請明確選取。"
            )
        else:
            self._set_status(f"來源 inventory 不完整：{value.diagnostic_code or 'unknown'}；不得續頁。")

    def _append_catalog_page(self, value: object) -> None:
        if not isinstance(value, DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1):
            raise ValueError("technical_official_view_catalog_result_invalid")
        if not value.scan_complete:
            self._catalog_cursor = None
            self._set_status(f"來源 inventory 漂移或不完整：{value.diagnostic_code or 'unknown'}。")
            return
        self._catalog_page = value
        self._catalog_cursor = value.next_cursor
        self._catalog_entries = (*self._catalog_entries, *value.entries)
        self._render_catalog(self._catalog_entries)
        self.next_catalog_button.setEnabled(value.next_cursor is not None)
        self._set_status("來源清單已續讀；清單資料仍未完整核驗。")

    def _render_catalog(
        self,
        entries: Sequence[DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1],
    ) -> None:
        self.catalog_list.blockSignals(True)
        self.catalog_list.clear()
        for index, entry in enumerate(entries):
            if entry.metadata is None:
                label = "來源資訊不完整｜只供診斷，不能讀取研究結果"
            else:
                metadata = entry.metadata
                coverage = "完整" if metadata.source_coverage_status_label == "complete" else "部分"
                label = (
                    f"{metadata.decision_date_label.isoformat()}｜宣告 {metadata.declared_count}、"
                    f"納入 {metadata.included_count}、排除 {metadata.excluded_count}｜"
                    f"來源覆蓋 {coverage}｜清單資訊未核驗"
                )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setFlags(
                item.flags()
                | (Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable if entry.can_attempt_exact_read else Qt.ItemFlag.NoItemFlags)
            )
            self.catalog_list.addItem(item)
        self.catalog_list.blockSignals(False)

    def _catalog_row_changed(self, row_index: int) -> None:
        if row_index < 0 or row_index >= len(self._catalog_entries):
            return
        entry = self._catalog_entries[row_index]
        if not entry.can_attempt_exact_read or entry.metadata is None:
            self._set_status("此列只有未核診斷資訊，不能用來讀取研究結果。")
            return
        self.select_catalog_candidate(entry)

    def select_catalog_candidate(self, entry: DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1) -> None:
        if not entry.can_attempt_exact_read or entry.metadata is None or self.bundle_output_root is None:
            self._set_status("來源候選不能選取；目前資訊僅供診斷。")
            return
        self._start_source_query(
            _SourceChoice(
                str(self.bundle_output_root),
                entry.metadata.bundle_identity_sha256,
                entry.metadata.manifest_sha256,
            ),
            page_index=0,
        )

    def _read_conditions(self) -> dict[str, object]:
        scopes = tuple(scope for scope in _SCOPE_VALUES if self.scope_checks[scope].isChecked())
        if not scopes:
            raise ValueError("technical_official_view_row_scope_empty")
        selected_states: list[DailyMarketTechnicalRuleStateFilterV4] = []
        for key, box in self.rule_state_boxes.items():
            value = box.currentData()
            if value != _NO_RULE_STATE_FILTER:
                if not isinstance(value, (tuple, list)):
                    raise ValueError("technical_official_view_rule_state_selection_invalid")
                if not value:
                    raise ValueError("technical_official_view_rule_state_selection_invalid")
                selected_states.append(
                    DailyMarketTechnicalRuleStateFilterV4.create(
                        key, cast(Sequence[Any], value)
                    )
                )
        if self.rule_filter_enabled.isChecked() and not selected_states:
            raise ValueError("technical_official_view_rule_state_required")
        if not self.rule_filter_enabled.isChecked() and selected_states:
            raise ValueError("technical_official_view_rule_filter_not_enabled")
        market_states = tuple(
            state for state in _MARKET_STATE_VALUES if self.market_checks[state].isChecked()
        )
        if self.market_filter_enabled.isChecked() and not market_states:
            raise ValueError("technical_official_view_market_state_required")
        if not self.market_filter_enabled.isChecked() and market_states:
            raise ValueError("technical_official_view_market_filter_not_enabled")
        disposal_states = tuple(
            state for state in _DISPOSAL_STATE_VALUES if self.disposal_checks[state].isChecked()
        )
        if self.disposal_filter_enabled.isChecked() and not disposal_states:
            raise ValueError("technical_official_view_disposal_state_required")
        if not self.disposal_filter_enabled.isChecked() and disposal_states:
            raise ValueError("technical_official_view_disposal_filter_not_enabled")
        if self.stock_filter_enabled.isChecked():
            stock_codes = _parse_stock_code_filter(
                self.stock_code_input.text(),
                input_was_truncated=self.stock_code_input.input_was_truncated,
            )
            stock_mode: Literal["all", "explicit_codes"] = "explicit_codes"
        else:
            if self.stock_code_input.text().strip():
                raise ValueError("technical_official_view_stock_filter_not_enabled")
            stock_mode = "all"
            stock_codes = ()
        clauses: list[DailyMarketTechnicalOfficialDispositionSortClauseV1] = []
        seen_fields: set[str] = set()
        allowed_sort_fields = {field for field, _label in self._sort_fields}
        if not self.sort_rows or len(self.sort_rows) > 32:
            raise ValueError("technical_official_view_sort_clause_count_invalid")
        for field_box, direction_box, _remove_button, _row in self.sort_rows:
            field = cast(str, field_box.currentData())
            direction = cast(str, direction_box.currentData())
            if not field or field not in allowed_sort_fields or direction not in {"asc", "desc"}:
                raise ValueError("technical_official_view_sort_clause_invalid")
            if field in seen_fields:
                raise ValueError("technical_official_view_sort_duplicate")
            seen_fields.add(field)
            clauses.append(
                DailyMarketTechnicalOfficialDispositionSortClauseV1(
                    field, cast(Any, direction)
                )
            )
        if not clauses:
            raise ValueError("technical_official_view_sort_required")
        return {
            "row_scope_filter": scopes,
            "rule_state_filters": tuple(selected_states),
            "combine_mode": cast(Any, self.combine_box.currentData()),
            "market_assignment_states": market_states,
            "official_disposal_states": disposal_states,
            "outer_stock_filter_mode": stock_mode,
            "outer_stock_codes": stock_codes,
            "sort_clauses": tuple(clauses),
        }

    def apply_filters(self) -> None:
        if self._source is None:
            self._set_status("請先從來源清單明確選取一個保存版本。")
            return
        try:
            conditions = self._read_conditions()
        except (TypeError, ValueError) as exc:
            self._set_status(f"條件無效：{exc}")
            return
        self._start_source_query(
            self._source, page_index=0, conditions=conditions, reuse_session=True
        )

    def clear_filters(self) -> None:
        self.rule_filter_enabled.setChecked(False)
        for box in self.rule_state_boxes.values():
            box.setCurrentIndex(0)
        self.combine_box.setCurrentIndex(0)
        for scope in _SCOPE_VALUES:
            self.scope_checks[scope].setChecked(True)
        self.market_filter_enabled.setChecked(False)
        self.disposal_filter_enabled.setChecked(False)
        for box in (*self.market_checks.values(), *self.disposal_checks.values()):
            box.setChecked(False)
        self.stock_filter_enabled.setChecked(False)
        self.stock_code_input.clear()
        for controls in tuple(self.sort_rows[1:]):
            self._remove_sort_clause_row(controls)
        first_field, first_direction, _remove, _widget = self.sort_rows[0]
        first_field.setCurrentIndex(first_field.findData("stock_code"))
        first_direction.setCurrentIndex(first_direction.findData("asc"))
        self._refresh_sort_editor()
        self.apply_filters()

    def _start_source_query(
        self,
        source: _SourceChoice,
        *,
        page_index: int,
        conditions: Mapping[str, object] | None = None,
        reuse_session: bool = False,
    ) -> None:
        try:
            query_conditions = dict(conditions) if conditions is not None else self._read_conditions()
        except (TypeError, ValueError) as exc:
            self._set_status(f"條件無效：{exc}")
            return
        page_size = self.page_size_box.value()
        existing_session = self._session

        def task(cancel_callback: Callable[[], bool] | None = None) -> _OpenedQuery:
            if reuse_session:
                if existing_session is None:
                    raise ValueError("technical_official_view_read_session_missing")
                return _execute_with_conditions(
                    source,
                    existing_session,
                    conditions=query_conditions,
                    page_index=page_index,
                    page_size=page_size,
                    cancel_callback=cancel_callback,
                )
            return _open_and_execute(
                source,
                conditions=query_conditions,
                page_index=page_index,
                page_size=page_size,
                cancel_callback=cancel_callback,
            )

        self._start_task("核驗保存來源並查詢完整母體", task, self._apply_opened_query)

    def _apply_opened_query(self, value: object) -> None:
        if not isinstance(value, _OpenedQuery):
            raise ValueError("technical_official_view_query_result_invalid")
        previous_query = self._result.query.query_identity_sha256 if self._result else None
        previous_source = self._source
        preserve_basket = (
            previous_query == value.result.query.query_identity_sha256
            and previous_source == value.source
        )
        self._source = value.source
        self._session = value.session
        self._result = value.result
        self._page_request = value.page_request
        self._page = value.page
        self._selected_row = None
        self._detail_selection = None
        if not preserve_basket:
            self._basket.clear()
        self.results_stack.setCurrentIndex(0)
        self._render_page()
        self._set_status(
            "已核驗所選保存版本並完成完整母體查詢；後續條件沿用該核驗工作階段，來源不持續監測。"
            "來源覆蓋或資料處理若為 partial，會在計數與標籤中保留。"
        )
        if previous_query is not None and previous_query != value.result.query.query_identity_sha256:
            self._set_status("條件或來源已更新；比較清單已清空，避免混用來源。")

    def navigate_page(self, page_index: int) -> None:
        result = self._result
        page = self._page
        if result is None or page is None:
            self._set_status("尚無已核結果可翻頁。")
            return
        if type(page_index) is not int or not 0 <= page_index < page.page_count:
            self._set_status("頁碼超出目前結果範圍。")
            return
        request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
            result.query,
            page_index=page_index,
            page_size=page.page_size,
        )

        def task(cancel_callback: Callable[[], bool] | None = None) -> tuple[
            DailyMarketTechnicalOfficialDispositionPageRequestV1,
            DailyMarketTechnicalOfficialDispositionQueryPageV1,
        ]:
            return request, result.read_page_request(request, cancel_callback=cancel_callback)

        self._start_task("讀取指定結果頁", task, self._apply_page)

    def _apply_page(self, value: object) -> None:
        if (
            not isinstance(value, tuple)
            or len(value) != 2
            or not isinstance(value[0], DailyMarketTechnicalOfficialDispositionPageRequestV1)
            or not isinstance(value[1], DailyMarketTechnicalOfficialDispositionQueryPageV1)
        ):
            raise ValueError("technical_official_view_page_result_invalid")
        self._page_request, self._page = value
        self._selected_row = None
        self._detail_selection = None
        self.results_stack.setCurrentIndex(0)
        self._render_page()
        self._set_status("已讀取原研究條件的指定頁；來源版本與全域排序順序不變。")

    def _render_page(self) -> None:
        # reset 前清除 current index，跨頁同位置仍以新的公開 DTO 選取。
        self.results_table.clearSelection()
        self.results_table.setCurrentIndex(QModelIndex())
        self._selected_row = None
        page = self._page
        result = self._result
        if page is None or result is None:
            self.results_model.replace_page(())
            self.counts_label.setText("尚未核驗研究來源。")
            self.page_label.setText("第 0 / 0 頁")
            self.previous_page_button.setEnabled(False)
            self.next_page_button.setEnabled(False)
            return
        counts = page.counts
        population = counts.population
        market_truth = counts.truth("market_assignment")
        disposal_truth = counts.truth("official_disposal")
        combined_membership = counts.membership("combined")
        self.counts_label.setText(
            f"宣告 {population.declared_count}（納入 {population.included_count}、排除 {population.excluded_count}）；"
            f"已處理 {population.processed_count}、待處理 {population.pending_count}、"
            f"缺資料 {population.missing_data_count}、待處理缺資料 {population.missing_data_pending_count}；"
            f"技術規則未知 {counts.unknown_rule_stock_count}；市場未知 {market_truth.unknown}、"
            f"處置未知 {disposal_truth.unknown}；本條件符合 {combined_membership.matched}、"
            f"不符合 {combined_membership.unmatched}；來源覆蓋 {page.official_source_coverage_status}、"
            f"技術處理 {page.technical_processing_status}；current_only，官方 available_at 未知，非歷史 PIT。"
        )
        table_rows: list[SavedResearchTableRow[DailyMarketTechnicalOfficialDispositionQueryResultRowV1]] = []
        for row in page.rows:
            fact = row.fact_row.to_dict()
            market = fact.get("market_assignment", {})
            disposal = fact.get("official_disposal", {})
            technical_text = self._technical_state_text(row)
            values = (
                row.stock_code,
                _SCOPE_LABELS.get(row.filter_evaluation.row_scope, row.filter_evaluation.row_scope),
                technical_text,
                _MARKET_STATE_LABELS.get(_mapping_value(market, "state"), _mapping_value(market, "state")),
                _DISPOSAL_STATE_LABELS.get(_mapping_value(disposal, "state"), _mapping_value(disposal, "state")),
                "符合" if row.overall_match else "不符合／未知",
                str(row.technical_row.decision_date)
                if row.technical_row is not None
                else str(result.query.technical_query.decision_date),
            )
            table_rows.append(SavedResearchTableRow(row.stock_code, row, values, values))
        self.results_model.replace_page(tuple(table_rows))
        if page.page_count == 0:
            self.page_label.setText("第 0 / 0 頁（0 筆符合）")
        else:
            self.page_label.setText(f"第 {page.page_index + 1} / {page.page_count} 頁")
        self.previous_page_button.setEnabled(page.page_index > 0)
        self.next_page_button.setEnabled(page.page_index + 1 < page.page_count)
        self._update_basket_label()

    @staticmethod
    def _technical_state_text(
        row: DailyMarketTechnicalOfficialDispositionQueryResultRowV1,
    ) -> str:
        if row.technical_row is None:
            status = row.fact_row.to_dict().get("technical_status")
            return {
                "processed": "已處理；技術列未提供",
                "pending": "待處理",
                "excluded": "明示排除",
            }.get(str(status), "技術狀態未提供")
        payload = row.technical_row.to_dict()
        rules = payload.get("rules")
        if not isinstance(rules, list):
            return "已處理；技術規則未提供"
        return "、".join(
            f"{_RULE_LABELS.get(str(item.get('key')), '未提供規則名稱')}："
            f"{_STATE_LABELS.get(str(item.get('state')), '未知')}"
            for item in rules
            if isinstance(item, Mapping)
        )

    def _table_selection_changed(self) -> None:
        index = self.results_table.currentIndex()
        self._selected_row = (
            self.results_model.row_at(index.row()) if index.isValid() else None
        )

    def select_stock_code(self, stock_code: str) -> bool:
        index = self.results_model.index_for_stock(stock_code)
        if not index.isValid():
            return False
        self.results_table.setCurrentIndex(index)
        self.results_table.selectRow(index.row())
        self._selected_row = self.results_model.row_at(index.row())
        return True

    def _current_selection(self) -> DailyMarketTechnicalOfficialDispositionStockSelectionV1:
        if self._page is None or self._page_request is None or self._selected_row is None:
            raise ValueError("technical_official_view_stock_not_selected")
        return DailyMarketTechnicalOfficialDispositionStockSelectionV1(
            self._page_request,
            self._selected_row.stock_code,
            self._selected_row.row_identity_sha256,
            self._selected_row,
        )

    def show_selected_detail(self) -> None:
        try:
            selection = self._current_selection()
        except ValueError as exc:
            self._set_status(str(exc))
            return
        self._detail_selection = selection
        self.detail_text.setText(format_technical_official_research_row_v1(selection.row))
        self.audit_json_text.setPlainText(
            canonical_daily_market_technical_official_disposition_bookmark_json_v1(
                selection.row.to_dict()
            )
        )
        self.audit_toggle.setChecked(False)
        self.audit_toggle.setText("展開完整稽核資料")
        self.detail_scroll.verticalScrollBar().setValue(0)
        self.results_stack.setCurrentIndex(1)
        self.stockSelected.emit(selection)

    def _set_audit_visible(self, visible: bool) -> None:
        self.audit_json_text.setVisible(visible)
        self.audit_toggle.setText(
            "收合完整稽核資料" if visible else "展開完整稽核資料"
        )

    def return_to_results(self) -> None:
        if self._detail_selection is not None and self._page_request is not None:
            if self._detail_selection.page_request.request_identity_sha256 != self._page_request.request_identity_sha256:
                self._set_status("返回頁面身份已變更；請重新選取股票。")
                self._detail_selection = None
                self.results_stack.setCurrentIndex(0)
                return
        self.results_stack.setCurrentIndex(0)

    def add_selected_to_comparison(self) -> None:
        try:
            selection = self._current_selection()
        except ValueError as exc:
            self._set_status(str(exc))
            return
        if selection.row.technical_row is None:
            self._set_status("待處理或排除列沒有技術事實，不能加入技術比較。")
            return
        if any(item.stock_code == selection.stock_code for item in self._basket):
            self._set_status("此股票已在比較清單。")
            return
        if len(self._basket) >= 5:
            self._set_status("比較清單最多 5 檔。")
            return
        if self._result is None or selection.page_request.query.query_identity_sha256 != self._result.query.query_identity_sha256:
            self._set_status("比較列與目前原研究條件不一致，請清除比較清單後重選。")
            return
        self._basket.append(selection)
        self._update_basket_label()
        self._set_status(f"已加入 {selection.stock_code}；跨頁比較仍固定於同一 query。")

    def remove_selected_from_comparison(self) -> None:
        selected = self._selected_row
        if selected is None:
            self._set_status("請先選取要移除的股票。")
            return
        self._basket = [item for item in self._basket if item.stock_code != selected.stock_code]
        self._update_basket_label()

    def _update_basket_label(self) -> None:
        codes = "、".join(item.stock_code for item in self._basket)
        self.basket_label.setText(f"比較清單：{len(self._basket)} 檔" + (f"（{codes}）" if codes else ""))
        self.compare_button.setEnabled(
            self._busy_worker is None and 2 <= len(self._basket) <= 5
        )

    def compare_basket(self) -> None:
        if self._result is None:
            self._set_status("尚無已核研究條件可比較。")
            return
        if not 2 <= len(self._basket) <= 5:
            self._set_status("比較需要同一來源、同一 query 的 2–5 檔股票；可跨頁選取。")
            return
        result = self._result
        items = tuple(self._basket)

        def task(cancel_callback: Callable[[], bool] | None = None) -> DailyMarketTechnicalOfficialDispositionComparisonV1:
            return _comparison_from_result(result, items, cancel_callback=cancel_callback)

        self._start_task("核對跨頁比較股票", task, self._apply_comparison)

    def _apply_comparison(self, value: object) -> None:
        if not isinstance(value, DailyMarketTechnicalOfficialDispositionComparisonV1):
            raise ValueError("technical_official_view_comparison_result_invalid")
        self._basket = list(value.items)
        self._update_basket_label()
        self.comparisonReady.emit(value)
        self._set_status("比較列已依同一研究條件與各自原結果頁重新核對。")

    def prepare_bookmark(self) -> None:
        if len(self._basket) == 1:
            self._set_status(
                "比較收藏需選 2–5 檔；請再加入一檔，或清空比較籃後收藏目前查詢與選取股票。"
            )
            return
        try:
            selection = self._current_selection()
            bookmark = DailyMarketTechnicalOfficialDispositionBookmarkV1.create(
                origin_page_request=selection.page_request,
                selected_row=selection.row,
                comparison_items=tuple(
                    DailyMarketTechnicalOfficialDispositionBookmarkComparisonV1(
                        item.page_request.to_json(), item.stock_code, item.row_identity_sha256
                    )
                    for item in self._basket
                ),
            )
        except (TypeError, ValueError) as exc:
            self._set_status(f"無法準備收藏：{exc}")
            return
        self.bookmarkPrepared.emit(bookmark)
        self._set_status("已準備原研究收藏；可從收藏清單重開原結果。")

    def restore_bookmark(self, value: DailyMarketTechnicalOfficialDispositionBookmarkV1 | str | bytes) -> None:
        try:
            bookmark = (
                value
                if type(value) is DailyMarketTechnicalOfficialDispositionBookmarkV1
                else DailyMarketTechnicalOfficialDispositionBookmarkV1.from_json(value)
            )
            # 以 canonical round-trip 再核一次 typed DTO，不接受替換欄位的外來 instance。
            bookmark = DailyMarketTechnicalOfficialDispositionBookmarkV1.from_json(bookmark.to_json())
            _validate_ui_query_compatibility(
                DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(
                    bookmark.origin_page_request_json
                ).query
            )
        except (TypeError, ValueError) as exc:
            self._set_status(f"收藏無效：{exc}")
            return

        def task(cancel_callback: Callable[[], bool] | None = None) -> _RestoredBookmark:
            return _restore_bookmark_exact(bookmark, cancel_callback=cancel_callback)

        self._start_task("重開原研究收藏", task, self._apply_restored_bookmark)

    def _apply_restored_bookmark(self, value: object) -> None:
        if not isinstance(value, _RestoredBookmark):
            raise ValueError("technical_official_view_bookmark_result_invalid")
        opened = value.opened
        query = opened.result.query
        # 完整重開與比較重核成功後才一次套用來源、條件、頁面、個股與 basket。
        self._apply_query_controls(query)
        self.page_size_box.setValue(opened.page_request.page_size)
        self._source = opened.source
        self._session = opened.session
        self._result = opened.result
        self._page_request = opened.page_request
        self._page = opened.page
        self._selected_row = value.selected_row
        self._basket = list(value.basket)
        self._detail_selection = None
        self.results_stack.setCurrentIndex(0)
        self._render_page()
        self.select_stock_code(value.selected_row.stock_code)
        self._set_status("已從原保存來源與各自原結果頁重開收藏，所有比較列均已核對。")

    def _apply_query_controls(self, query: DailyMarketTechnicalOfficialDispositionQueryV1) -> None:
        _validate_ui_query_compatibility(query)
        selected = {
            item.rule_key: item.states for item in query.technical_query.rule_state_filters
        }
        self.rule_filter_enabled.setChecked(bool(selected))
        for key, box in self.rule_state_boxes.items():
            box.setCurrentIndex(
                box.findData(selected.get(key, _NO_RULE_STATE_FILTER))
            )
        self.combine_box.setCurrentIndex(self.combine_box.findData(query.technical_query.combine_mode))
        for scope, box in self.scope_checks.items():
            box.setChecked(scope in query.row_scope_filter)
        market = set(query.market_assignment_states)
        self.market_filter_enabled.setChecked(bool(market))
        for state, box in self.market_checks.items():
            box.setChecked(state in market)
        disposal = set(query.official_disposal_states)
        self.disposal_filter_enabled.setChecked(bool(disposal))
        for state, box in self.disposal_checks.items():
            box.setChecked(state in disposal)
        explicit = query.outer_stock_filter_mode == "explicit_codes"
        self.stock_filter_enabled.setChecked(explicit)
        self.stock_code_input.setText(", ".join(query.outer_stock_codes) if explicit else "")
        for controls in tuple(self.sort_rows[1:]):
            self._remove_sort_clause_row(controls)
        for index, clause in enumerate(query.sort_clauses):
            if index == 0:
                field_box, direction_box, _remove, _widget = self.sort_rows[0]
            else:
                self._add_sort_clause_row()
                field_box, direction_box, _remove, _widget = self.sort_rows[index]
            field_box.setCurrentIndex(field_box.findData(clause.field))
            direction_box.setCurrentIndex(direction_box.findData(clause.direction))
        self._refresh_sort_editor()

    def _page_index(self) -> int:
        return self._page.page_index if self._page is not None else 0

    def closeEvent(self, event: Any) -> None:
        if not self.begin_shutdown():
            self._set_status("正在等待背景工作安全停止；目前已核結果仍保留。")
            event.ignore()
            return
        super().closeEvent(event)


def _mapping_value(value: object, key: str) -> str:
    if isinstance(value, Mapping):
        item = value.get(key)
        return item if isinstance(item, str) else "未知"
    return "未知"


def _validate_ui_query_compatibility(query: DailyMarketTechnicalOfficialDispositionQueryV1) -> None:
    if len(query.sort_clauses) > 32:
        raise ValueError("technical_official_view_bookmark_sort_not_representable")
    if query.technical_query.stock_filter:
        raise ValueError(
            "technical_official_view_bookmark_inner_stock_filter_not_representable"
        )
