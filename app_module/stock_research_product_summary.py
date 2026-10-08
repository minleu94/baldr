"""將既有個股報告與 H20 讀回整理成唯讀產品摘要。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app_module.recommendation.personal_h20_product_evidence import (
    PersonalH20ProductEvidence,
)
from app_module.recommendation.personal_h20_price_chart import (
    PersonalH20PriceChartProjectionV1,
    assert_personal_h20_price_chart_projection_binding,
)
from app_module.research_result_presentation import (
    research_limitation_text,
    research_risk_text,
)
from app_module.stock_research_report_dtos import (
    StockResearchReportDTO,
)


_AVAILABLE_H20_STATUS = "available"
_SAVED_H20_COHORT_SOURCE = "personal_h20_saved_cohort"
_CURRENT_H20_SOURCE_KINDS = frozenset({"explicit_latest_stock_research"})
_AFTER_COST_TARGETS = frozenset(
    {
        "cost-adjusted benchmark excess bp",
        "cost_adjusted_benchmark_excess_bp",
        "benchmark_excess_after_cost_bp",
        "cost_adjusted_benchmark_excess_return_bp",
        "benchmark_excess_after_standard_80bp_cost",
        "成本後基準超額報酬",
    }
)


@dataclass(frozen=True, slots=True)
class ProductResearchSummary:
    """提供首屏文字及可展開來源資訊，不承擔評分或決策。"""

    conclusion: str
    reasons: tuple[str, ...]
    risks: str
    holding_relation: str
    next_step: str
    status_lines: tuple[str, ...]
    advanced_notes: tuple[str, ...]


def build_stock_research_product_summary(
    report: StockResearchReportDTO,
    h20: PersonalH20ProductEvidence | None = None,
    *,
    h20_price_chart: PersonalH20PriceChartProjectionV1 | None = None,
) -> ProductResearchSummary:
    """只投影報告與原 H20 讀回欄位，不重算或補造研究結果。"""

    if not isinstance(report, StockResearchReportDTO):
        raise TypeError("report 必須是 StockResearchReportDTO")
    if h20 is not None and not isinstance(h20, PersonalH20ProductEvidence):
        raise TypeError("h20 必須是 PersonalH20ProductEvidence 或 None")
    if h20 is not None and h20.stock_code != report.stock_code:
        raise ValueError("H20 股票代碼與個股報告不一致")
    context = report.research_context
    source_kind = _context_value(context, "source_kind")
    if h20_price_chart is not None:
        if type(h20_price_chart) is not PersonalH20PriceChartProjectionV1:
            raise TypeError("h20_price_chart 必須是核驗過的個人 H20 價格圖投影")
        if h20 is None or h20.status != _AVAILABLE_H20_STATUS:
            raise ValueError("H20 價格圖須有同列可用的 H20 保存估計")
        _validate_h20_price_chart_binding(
            report,
            h20,
            h20_price_chart,
            source_kind=source_kind,
        )

    source_relation = _h20_source_relation(report, h20, source_kind)
    if h20 is not None and h20.status == _AVAILABLE_H20_STATUS:
        _validate_saved_h20_cohort_identity(report, h20, source_kind)

    return ProductResearchSummary(
        conclusion=_conclusion(report, h20),
        reasons=_reasons(report, h20),
        risks=_risks(report, h20),
        holding_relation=_holding_relation(report),
        next_step=_next_step(report, h20, source_relation),
        status_lines=_status_lines(report, h20, source_relation, h20_price_chart),
        advanced_notes=_advanced_notes(report, h20),
    )


def _validate_h20_price_chart_binding(
    report: StockResearchReportDTO,
    h20: PersonalH20ProductEvidence,
    chart: PersonalH20PriceChartProjectionV1,
    *,
    source_kind: str,
) -> None:
    """只讓同一已保存 H20 列與來源脈絡使用程序內簽發的圖表。"""

    context = report.research_context
    if (
        h20.stock_code != report.stock_code
        or not h20.candidate_id
        or not h20.sample_id
        or not h20.prediction_id
        or not h20.decision_date
        or not h20.source_date
        or not h20.feature_date
    ):
        raise ValueError("H20 價格圖的保存列身分不足")
    if source_kind == "personal_h20_saved_cohort":
        expected_source_id = h20.prediction_id
        expected_origin_id = None
    elif source_kind == "personal_h20_research_bookmark":
        expected_source_id = _context_value(context, "source_id")
        expected_origin_id = expected_source_id
        if not expected_source_id:
            raise ValueError("H20 收藏價格圖缺少原 bookmark 身分")
    else:
        raise ValueError("H20 價格圖不可用於一般或目前行情報告")

    expected_context = {
        "stock_code": h20.stock_code,
        "profile_id": h20.candidate_id,
        "source_version": _context_value(context, "source_version"),
        "source_snapshot_id": chart.cycle_id,
        "decision_date": h20.decision_date,
        "data_date": h20.source_date,
        "source_id": expected_source_id,
    }
    for key, expected in expected_context.items():
        actual = _context_value(context, key)
        if not actual or actual != expected:
            raise ValueError(f"H20 價格圖的 {key} 與目前保存來源不一致")
    assert_personal_h20_price_chart_projection_binding(
        chart,
        stock_code=report.stock_code,
        source_kind=source_kind,
        manifest_sha256=_context_value(context, "source_snapshot_hash"),
        decision_date=h20.decision_date,
        candidate_id=h20.candidate_id,
        contract_hash=_context_value(context, "source_version"),
        cycle_id=_context_value(context, "source_snapshot_id"),
        sample_id=h20.sample_id,
        prediction_id=h20.prediction_id,
        source_date=h20.source_date,
        feature_as_of_date=h20.feature_date,
        # capture SHA 由不可序列化 issuer 投影從同列 reader 終態固定；H20 DTO
        # 不複製 capture pin，Main 的 setter 另以原 selection/bookmark row 重核。
        capture_sha256=chart.capture_sha256,
        origin_identity_sha256=expected_origin_id,
    )


def _conclusion(
    report: StockResearchReportDTO,
    h20: PersonalH20ProductEvidence | None,
) -> str:
    if h20 is not None and h20.status == _AVAILABLE_H20_STATUS:
        return (
            "個人 H20 研究估計：20 個交易日未扣成本毛報酬 "
            f"{_percent_from_bp(h20.gross_return_bp)}。這是保存的預測值，"
            "不代表實際結果。"
        )
    if report.attention_reasons:
        return "個股報告有待核對事項：" + _present_limitation(report.attention_reasons[0])
    if report.rule_reasons:
        return "個股報告已有研究條件：" + _present_reason(report.rule_reasons[0])
    return "目前沒有可核讀的個人 H20 估計；報告其他資料依各自日期判讀。"


def _reasons(
    report: StockResearchReportDTO,
    h20: PersonalH20ProductEvidence | None,
) -> tuple[str, ...]:
    if report.rule_reasons:
        return tuple(
            "個股報告既有研究條件（非 H20 模型歸因）：" + _present_reason(reason)
            for reason in report.rule_reasons[:3]
        )
    if report.attention_reasons:
        return tuple(
            "個股報告待核對事項：" + _present_limitation(reason)
            for reason in report.attention_reasons[:3]
        )
    if h20 is not None and h20.status == _AVAILABLE_H20_STATUS:
        return (
            "H20 讀回沒有逐項模型歸因；摘要不把其他報告內容說成預測原因。",
        )
    return ("目前沒有可核對的支持理由。",)


def _risks(
    report: StockResearchReportDTO,
    h20: PersonalH20ProductEvidence | None,
) -> str:
    risks = [research_risk_text(reason) for reason in report.key_risks if reason.strip()][:3]
    if h20 is not None and h20.status == _AVAILABLE_H20_STATUS:
        risks.append("此估計未扣成本；本讀回沒有證明 H20 的實際或成本後效果。")
    if not risks:
        return "目前沒有可核對的風險依據；不代表沒有風險。"
    return "；".join(dict.fromkeys(risks[:4]))


def _holding_relation(report: StockResearchReportDTO) -> str:
    position = report.position
    if position is None:
        return "持倉資料尚未載入；未知不等於沒有持倉。"
    if not position.is_holding:
        return "此份報告未標記為持倉。"

    status = (position.health_label or "").strip()
    if not status:
        status = _health_status_label(position.health_status)
    if status == "未知":
        return "此份報告標記為持倉；健康狀態未知。"
    return f"此份報告標記為持倉；既有健康狀態為「{status}」，不代表交易指令。"


def _status_lines(
    report: StockResearchReportDTO,
    h20: PersonalH20ProductEvidence | None,
    source_relation: str,
    h20_price_chart: PersonalH20PriceChartProjectionV1 | None,
) -> tuple[str, ...]:
    source_kind = _context_value(report.research_context, "source_kind")
    saved_h20 = source_kind in {_SAVED_H20_COHORT_SOURCE, "personal_h20_research_bookmark"}
    report_scope_label = "一般個股報告" if saved_h20 else ""
    lines = (
        report_scope_label + _data_completeness_line(report),
        report_scope_label + _freshness_line(report),
        _h20_availability_line(h20),
        _h20_dates_line(h20),
        _natural_result_line(h20),
        _usage_line(h20, source_relation),
    )
    if saved_h20:
        return (*lines, _h20_price_chart_line(h20_price_chart))
    return lines


def _h20_price_chart_line(
    chart: PersonalH20PriceChartProjectionV1 | None,
) -> str:
    if chart is None:
        return (
            "H20 價格來源：尚無同次終態核驗的 OHLCV 圖表；保留缺件，"
            "不以其他報告或目前行情補入。"
        )
    if chart.status == "available":
        first = chart.points[0].trading_date if chart.points else "未知"
        last = chart.points[-1].trading_date if chart.points else "未知"
        return (
            f"H20 價格來源：同次原快照 OHLCV 已核驗，涵蓋 {first} 至 {last}；"
            "資料可得時間未知，只供保存來源重述，不授歷史 PIT 或可交易資格。"
        )
    reason = {
        "daily_prices_empty": "原快照沒有符合範圍的價格列",
        "daily_prices_date_out_of_range": "原快照日期超出保存視窗",
        "daily_prices_hash_mismatch": "原快照價格列與 capture 的邏輯 hash 不一致",
        "daily_prices_invalid": "原快照價格資料不完整或格式不符",
        "daily_prices_ohlc_missing": "原快照 OHLC 缺欄",
        "daily_prices_ohlc_inconsistent": "原快照 OHLC 範圍不一致",
        "chart_capacity_exceeded": "原快照價格圖超出 bounded 投影容量",
        "source_initial_terminal_changed": "來源初讀與終態重讀不一致",
        "capture_binding_mismatch": "capture 與 H20 保存來源無法對應",
        "capture_observer_missing": "同次來源價格讀取未完整記錄",
        "h20_row_unknown": "此 H20 列本身仍未知",
    }.get(chart.reason_code, "原保存來源未能核驗價格圖")
    return f"H20 價格來源：{reason}；保留缺件，不以其他行情補入。"


def _data_completeness_line(report: StockResearchReportDTO) -> str:
    if not report.sections:
        return "資料完整度：報告沒有提供各區資料狀態。"

    missing = tuple(
        section.label
        for section in report.sections
        if _token(section.status) in {"missing", "error"}
    )
    partial = tuple(
        section.label
        for section in report.sections
        if _token(section.status) in {"partial", "stale"}
    )
    unknown = tuple(
        section.label
        for section in report.sections
        if _token(section.status) not in {"available", "partial", "stale", "missing", "error"}
    )
    if missing:
        return f"資料完整度：{_join_labels(missing)}缺少或讀取失敗；缺件保持未知。"
    if partial:
        return f"資料完整度：{_join_labels(partial)}部分可用或已標記過期。"
    if unknown:
        return f"資料完整度：{_join_labels(unknown)}狀態未核。"
    return "資料完整度：報告列出的主要區塊都有可讀狀態；實際涵蓋仍依各區資料日。"


def _freshness_line(report: StockResearchReportDTO) -> str:
    if not report.sections:
        return "資料時效：沒有分區時效狀態；不由查詢日期推定新鮮度。"

    fresh = tuple(
        section.label
        for section in report.sections
        if _token(section.freshness) == "fresh"
    )
    stale = tuple(
        section.label
        for section in report.sections
        if _token(section.freshness) == "stale" or _token(section.status) == "stale"
    )
    unknown = tuple(
        section.label
        for section in report.sections
        if _token(section.freshness) not in {"fresh", "stale"}
    )
    parts: list[str] = []
    if fresh:
        parts.append(f"{_join_labels(fresh)}原來源標記新鮮")
    if stale:
        parts.append(f"{_join_labels(stale)}原來源標記過期")
    if unknown:
        parts.append(f"{_join_labels(unknown)}時效未核")
    if not parts:
        return "資料時效：各區沒有可辨識的時效標記。"
    return "資料時效：" + "；".join(parts) + "。"


def _h20_availability_line(h20: PersonalH20ProductEvidence | None) -> str:
    if h20 is None:
        return "模型可用性：沒有提供個人 H20 個股讀回；不把缺件補成零。"
    if h20.status == "available":
        return (
            "模型可用性：個人 H20 原保存估計已讀回；20 個交易日、未扣成本，"
            f"{_percent_from_bp(h20.gross_return_bp)}（{h20.gross_return_bp} bp）。"
        )
    labels = {
        "pending": "等待可核的個人 H20 預測",
        "disabled": "個人 H20 已停用",
        "unavailable": "個人 H20 預測目前無法核驗",
    }
    return f"模型可用性：{labels.get(h20.status, '個人 H20 狀態未核')}；不沿用其他日期的估計。"


def _h20_dates_line(h20: PersonalH20ProductEvidence | None) -> str:
    if h20 is None or h20.status != "available":
        return "估計日期：沒有可核讀的 H20 預測日期。"
    return (
        f"估計日期：適用／決策日 {h20.decision_date}；來源日 {h20.source_date}；"
        f"特徵截至 {h20.feature_date}。"
    )


def _natural_result_line(h20: PersonalH20ProductEvidence | None) -> str:
    if h20 is None:
        return "自然結果：未提供 H20 預測讀回，成熟狀態未知。"
    if h20.status == "available":
        reason = _present_limitation(h20.reason)
        detail = f"原讀回說明：{reason}。" if reason else "原讀回沒有提供成熟結果狀態。"
        return "自然結果：預測可讀不代表結果已成熟；這份輸入沒有成熟 outcome 欄位。" + detail
    return "自然結果：目前沒有可核讀的預測結果，成熟狀態未知；不可補成零。"


def _usage_line(
    h20: PersonalH20ProductEvidence | None,
    source_relation: str,
) -> str:
    if h20 is None or h20.status != "available":
        return "用途：可讀資料供研究檢視；不產生 Advice、權重、勝率或買賣指令。"
    if source_relation == "same_saved_cohort":
        use = "可比較同份 H20 候選及檢視已載入持倉情境"
    elif source_relation == "current_stock":
        use = "可作個股研究比較；同份候選順位需回原 H20 名單核對"
    else:
        use = "這是獨立 H20 估計；先回原模型名單核對候選來源再比較"
    return f"用途：{use}；不產生 Advice、權重、勝率或買賣指令。"


def _next_step(
    report: StockResearchReportDTO,
    h20: PersonalH20ProductEvidence | None,
    source_relation: str,
) -> str:
    if h20 is not None and h20.status == "available":
        if source_relation == "same_saved_cohort":
            return "先比較同份 H20 候選；有持倉時再檢視本報告所載情境。無需先保存 Advice。"
        if source_relation == "current_stock":
            if report.position is not None and report.position.is_holding:
                return "先檢視本報告所載持倉情境，再比較其他研究來源。無需先保存 Advice。"
            return "先比較此股其他研究來源；候選名次回原 H20 名單核對。無需先保存 Advice。"
        return "先回原 H20 名單核對候選來源與名次，再比較同份候選或檢視持倉情境。無需先保存 Advice。"
    if h20 is not None and h20.status == "unavailable":
        return "先依進階資料中的來源診斷重新核對原 H20 讀回；不借用舊估計。"
    return "先核對報告各區的資料完整度與時效，再按需要檢視研究條件或持倉情境。"


def _advanced_notes(
    report: StockResearchReportDTO,
    h20: PersonalH20ProductEvidence | None,
) -> tuple[str, ...]:
    notes: list[str] = []
    context = report.research_context
    source_kind = _context_value(context, "source_kind")
    if h20 is not None:
        notes.append(
            "H20 原始身分："
            f"狀態={h20.status}；candidate_id={h20.candidate_id or '未提供'}；"
            f"sample_id={h20.sample_id or '未提供'}；prediction_id={h20.prediction_id or '未提供'}。"
        )
        if h20.observed_at:
            notes.append(f"H20 原觀測時間：{h20.observed_at}。")
        if h20.reason:
            notes.append(f"H20 原讀回說明：{h20.reason}")
    notes.append(
        "H20 同份候選名次與母體分母不在個股 H20 DTO 內；不可用其他原始排名代替。"
    )
    if context:
        fields = (
            ("source_kind", "來源型態"),
            ("source_id", "來源 ID"),
            ("source_version", "來源版本"),
            ("decision_date", "報告決策日"),
            ("data_date", "報告資料日"),
            ("profile_id", "候選版本 ID"),
            ("source_snapshot_id", "來源快照 ID"),
            ("source_snapshot_hash", "來源快照 SHA"),
            ("daily_snapshot_cohort_id", "研究母體 ID"),
        )
        values = [
            f"{label}：{_context_value(context, key)}"
            for key, label in fields
            if _context_value(context, key)
        ]
        if values:
            notes.append("報告來源：" + "；".join(values) + "。")
    if report.as_of:
        notes.append(f"報告查詢日：{report.as_of}。")
    for section in report.sections:
        if section.data_as_of or section.available_at:
            notes.append(
                f"資料區「{section.label}」：資料日 {section.data_as_of or '未提供'}；"
                f"可得時間 {section.available_at or '未提供'}；來源時效 {section.freshness}。"
            )
    for limitation in report.limitations:
        if limitation.strip():
            notes.append("報告原始限制：" + limitation.strip())
    notes.extend(_h5_notes(report))
    return tuple(dict.fromkeys(note for note in notes if note.strip()))


def _h5_notes(report: StockResearchReportDTO) -> tuple[str, ...]:
    mapped_h5 = report.ml.predicted_benchmark_excess_return_bp.get("H5")
    explicit_h5 = report.ml.h5_benchmark_excess_after_standard_80bp_cost
    if type(mapped_h5) is int and type(explicit_h5) is int and mapped_h5 != explicit_h5:
        return ("H5 原值欄位不一致；暫不呈現 H5 數值，也不延伸套用至 H20。",)
    h5 = mapped_h5 if type(mapped_h5) is int else explicit_h5
    if type(h5) is not int:
        return ()

    target = _token(report.ml.target_metric).casefold()
    explicit_after_cost = type(report.ml.h5_benchmark_excess_after_standard_80bp_cost) is int
    after_cost = explicit_after_cost or target in _AFTER_COST_TARGETS
    if after_cost:
        semantic = "成本後基準超額估計"
        relation = _percentage_point_relation(h5)
    else:
        semantic = "H5 基準超額原值；目標／成本語意未核"
        relation = "未換算成百分點"

    notes = [
        f"另一份 H5 研究：{semantic} {h5} bp（{relation}）；此值不換算為 H20 毛報酬。"
    ]
    total = report.ml.target_round_trip_cost_bp
    buy = report.ml.target_buy_side_cost_bp
    sell = report.ml.target_sell_side_cost_bp
    if type(total) is int and type(buy) is int and type(sell) is int:
        if total >= 0 and buy >= 0 and sell >= 0 and total == buy + sell:
            notes.append(
                f"H5 成本情境原值：總計 {total} bp（買進 {buy} bp、賣出 {sell} bp）；"
                "只屬 H5 模型假設，不是實際帳戶成本，也不套用於 H20。"
            )
        else:
            notes.append("H5 成本欄位未能相互核對；不延伸套用至 H20。")
    return tuple(notes)


def _h20_source_relation(
    report: StockResearchReportDTO,
    h20: PersonalH20ProductEvidence | None,
    source_kind: str,
) -> str:
    if h20 is None or h20.status != _AVAILABLE_H20_STATUS:
        return "unavailable"
    if source_kind == _SAVED_H20_COHORT_SOURCE:
        return "same_saved_cohort"
    scope_mode = _context_value(report.research_context, "ml_scope_mode")
    if source_kind in _CURRENT_H20_SOURCE_KINDS or (
        scope_mode == "current_stock_research"
        and source_kind != "daily_market_research_snapshot"
    ):
        return "current_stock"
    return "independent_record"


def _validate_saved_h20_cohort_identity(
    report: StockResearchReportDTO,
    h20: PersonalH20ProductEvidence,
    source_kind: str,
) -> None:
    if source_kind != _SAVED_H20_COHORT_SOURCE:
        return
    expected = {
        "stock_code": h20.stock_code,
        "profile_id": h20.candidate_id,
        "source_id": h20.prediction_id,
        "decision_date": h20.decision_date,
        "data_date": h20.source_date,
    }
    for key, actual in expected.items():
        declared = _context_value(report.research_context, key)
        if not declared or declared != actual:
            raise ValueError(f"H20 已保存候選來源的 {key} 身分不一致或缺少")


def _present_reason(reason: str) -> str:
    return research_risk_text(reason.strip()) if reason.strip() else "未提供"


def _present_limitation(reason: str) -> str:
    return research_limitation_text(reason.strip()) if reason.strip() else "未提供"


def _health_status_label(value: str) -> str:
    labels = {
        "HEALTHY": "健康",
        "WATCH": "待檢視",
        "REDUCE_CANDIDATE": "減碼候選（研究狀態）",
        "EXIT_CANDIDATE": "退出候選（研究狀態）",
        "CLOSED": "已結束",
    }
    return labels.get(_token(value).upper(), "未知")


def _percent_from_bp(value: int | None) -> str:
    if type(value) is not int:
        return "未提供"
    sign = "+" if value >= 0 else "-"
    magnitude = abs(value)
    return f"{sign}{magnitude // 100}.{magnitude % 100:02d}%"


def _percentage_point_relation(value: int) -> str:
    if value > 0:
        return f"高於基準 {value // 100}.{value % 100:02d} 個百分點"
    if value < 0:
        magnitude = abs(value)
        return f"落後基準 {magnitude // 100}.{magnitude % 100:02d} 個百分點"
    return "與基準相同"


def _join_labels(labels: tuple[str, ...]) -> str:
    return "、".join(label.strip() for label in labels if label.strip())


def _context_value(context: Mapping[str, str], key: str) -> str:
    value = context.get(key, "") if isinstance(context, Mapping) else ""
    return str(value or "").strip()


def _token(value: object) -> str:
    return str(getattr(value, "value", value) or "").strip()
