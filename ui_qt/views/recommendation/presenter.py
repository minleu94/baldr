"""RecommendationView 的純文字呈現規則。"""

from __future__ import annotations

import html
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Mapping, Optional, Sequence
from typing import Any

from ui_qt.status_vocabulary import status_label


def format_regime_names(regimes: Sequence[Optional[str]]) -> str:
    regime_names = {
        "Trend": "Trend / 趨勢追蹤",
        "Reversion": "Reversion / 均值回歸",
        "Breakout": "Breakout / 突破準備",
    }
    names = [regime_names.get(regime, regime or "未知") for regime in regimes if regime]
    return "、".join(names) if names else "未指定"


def _decimal_value(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def screening_research_summary(row: Mapping[str, Any]) -> str:
    """以已核驗篩選列解釋用途；不補推薦分數或改變策略門檻。"""
    purpose = (
        "這份紀錄用來查看本次策略在哪個條件停止，以及比較不同策略的條件。"
        "個人 H20 的保存預測請在「個人模型選股研究」查看，兩者分開判讀。"
    )
    reason = row.get("原因代碼", "")
    observed = _decimal_value(row.get("觀測值"))
    required = _decimal_value(row.get("要求值"))
    if (isinstance(reason, str) and reason in {
                "liquidity_volume_ratio_below_min",
                "量能未達本次策略的放量門檻（liquidity_volume_ratio_below_min）",
            }
            and row.get("原篩選狀態") == "skipped"
            and observed is not None and required is not None
            and observed < required):
        return (
            "本次未入選：成交量變化未達策略的放量門檻。\n"
            f"相對本次成交量基準，觀測變化為 {observed:.2f}%；"
            f"策略要求至少 {required:.2f}%。負值表示量縮。\n"
            "此條件在策略打分前檢查，本次未產生推薦分數或排名。\n"
            + purpose
            + "\n下一步：核對策略條件與資料日期，再決定是否用另一策略研究。"
        )
    return "本次策略沒有產生入選結果。\n" + purpose


def format_profile_weight(value: Any) -> str:
    if value is None:
        return "N/A"
    numeric = _decimal_value(value)
    if numeric is None:
        return str(value)
    if numeric <= Decimal("1"):
        return f"{numeric * Decimal('100'):.0f}%"
    if numeric <= Decimal("100"):
        return f"{numeric:.0f}"
    return f"{int(numeric)}bp"


def format_profile_filter_value(value: Any) -> str:
    numeric = _decimal_value(value)
    if numeric is None:
        return str(value)
    return f"{numeric.normalize():g}"


def profile_filter_summary(filters: dict[str, Any]) -> str:
    parts: list[str] = []
    if "price_change_min" in filters or "price_change_max" in filters:
        min_value = filters.get("price_change_min", "N/A")
        max_value = filters.get("price_change_max", "N/A")
        parts.append(
            f"漲幅 {format_profile_filter_value(min_value)}% ~ "
            f"{format_profile_filter_value(max_value)}%"
        )
    if "volume_ratio_min" in filters:
        parts.append(
            f"成交量 >= {format_profile_filter_value(filters.get('volume_ratio_min'))} 倍"
        )
    if filters.get("industry"):
        parts.append(f"產業 {filters.get('industry')}")
    return "、".join(parts) if parts else "未指定"


def profile_advanced_summary(config: dict[str, Any]) -> str:
    signals = config.get("signals", {})
    weights = signals.get("weights", {})
    indicators = signals.get("technical_indicators", [])
    patterns = config.get("patterns", {}).get("selected", [])
    weight_text = (
        f"型態 {format_profile_weight(weights.get('pattern'))} / "
        f"技術 {format_profile_weight(weights.get('technical'))} / "
        f"量能 {format_profile_weight(weights.get('volume'))}"
    )
    indicator_text = "、".join(indicators) if indicators else "未指定"
    pattern_preview = "、".join(str(pattern) for pattern in patterns[:5])
    if len(patterns) > 5:
        pattern_preview += f" 等 {len(patterns)} 種"
    elif pattern_preview:
        pattern_preview += f"（共 {len(patterns)} 種）"
    else:
        pattern_preview = "未指定"
    return (
        f"權重 {weight_text}；"
        f"技術分類 {indicator_text}；"
        f"型態 {pattern_preview}；"
        f"主要篩選 {profile_filter_summary(config.get('filters', {}))}"
    )


def format_recommendation_reason(
    reason_text: str,
    *,
    technical_descriptions: dict[str, Any],
    pattern_descriptions: dict[str, Any],
) -> str:
    """格式化推薦理由，使用 Tag/關鍵詞高亮顯示，並加入可反推線索

    Args:
        reason_text: 原始推薦理由文字

    Returns:
        str: 格式化後的推薦理由（使用 HTML 格式以便高亮）
    """
    if not reason_text:
        return "無推薦理由"

    # 從集中資料結構建立關鍵詞映射（技術指標）
    technical_keywords = {}
    for key, desc in technical_descriptions.items():
        # 建立名稱映射
        name_map = {
            'ma': ['移動平均', '均線', 'MA'],
            'adx': ['ADX'],
            'macd': ['MACD'],
            'rsi': ['RSI'],
            'kd': ['KD'],
            'bollinger': ['布林', '布林通道'],
            'atr': ['ATR']
        }
        for name in name_map.get(key, []):
            technical_keywords[name] = {
                'display': f'<b style="color: #2563eb;">{name}</b>',
                'category': desc.get('category', ''),
                'tags': desc.get('tags', [])
            }

    # 從集中資料結構建立關鍵詞映射（圖形模式）
    pattern_keywords = {}
    for key, desc in pattern_descriptions.items():
        # 建立名稱映射
        name_map = {
            'w_bottom': ['W底'],
            'head_shoulder_bottom': ['頭肩底'],
            'double_bottom': ['雙底'],
            'v_reversal': ['V形反轉', 'V形'],
            'rounding_bottom': ['圓底'],
            'flag': ['旗形'],
            'wedge': ['楔形'],
            'rectangle': ['矩形'],
            'triangle': ['三角形'],
            'head_shoulder_top': ['頭肩頂'],
            'double_top': ['雙頂'],
            'rounding_top': ['圓頂']
        }
        for name in name_map.get(key, []):
            category = desc.get('category', '')
            if category == 'Reversal':
                icon = ''
                color = '#16a34a'
            elif category == 'Continuation':
                icon = ''
                color = '#16a34a'
            elif category == 'Consolidation':
                icon = ''
                color = '#7c3aed'
            else:  # Bearish
                icon = ''
                color = '#dc2626'

            pattern_keywords[name] = {
                'display': f'<b style="color: {color};">{name}</b>',
                'category': category,
                'tags': desc.get('tags', [])
            }

    # 替換關鍵詞
    formatted_text = reason_text
    all_keywords = {**technical_keywords, **pattern_keywords}

    # 按長度排序，先替換長關鍵詞
    sorted_keywords = sorted(all_keywords.keys(), key=len, reverse=True)
    for keyword in sorted_keywords:
        if keyword in formatted_text:
            formatted_text = formatted_text.replace(keyword, all_keywords[keyword]['display'])

    # 其他標籤映射
    other_tags = {
        '趨勢': '<b style="color: #2563eb;">趨勢</b>',
        '動能': '<b style="color: #2563eb;">動能</b>',
        '波動': '<b style="color: #2563eb;">波動</b>',
        '反轉': '<b style="color: #16a34a;">反轉</b>',
        '延續': '<b style="color: #16a34a;">延續</b>',
        '盤整': '<b style="color: #16a34a;">盤整</b>',
        '超買': '<span style="color: #dc2626;">超買</span>',
        '超賣': '<span style="color: #16a34a;">超賣</span>',
        '金叉': '<span style="color: #16a34a;">金叉</span>',
        '死叉': '<span style="color: #dc2626;">死叉</span>',
        '多頭': '<span style="color: #16a34a;">多頭</span>',
        '空頭': '<span style="color: #dc2626;">空頭</span>',
        '成交量': '<b style="color: #2563eb;">成交量</b>',
    }

    for keyword, replacement in other_tags.items():
        formatted_text = formatted_text.replace(keyword, replacement)

    # 解析理由文字，提取觸發來源
    # 如果理由文字包含 "、" 分隔符，則按分隔符拆分
    if '、' in formatted_text:
        parts = formatted_text.split('、')
        formatted_parts = []
        triggered_indicators = []
        triggered_patterns = []

        for part in parts:
            part = part.strip()
            if part:
                # 移除 + 或 - 符號
                clean_part = part.replace('+', '').replace('-', '')

                # 檢查是否包含技術指標
                for keyword, info in technical_keywords.items():
                    if keyword in clean_part:
                        if keyword not in triggered_indicators:
                            triggered_indicators.append(keyword)

                # 檢查是否包含圖形模式
                for keyword, info in pattern_keywords.items():
                    if keyword in clean_part:
                        if keyword not in triggered_patterns:
                            triggered_patterns.append(keyword)

                formatted_parts.append(f"• {clean_part}")

        # 組合為 HTML 格式
        html_text = "<div style='line-height: 1.6;'>"
        html_text += "<p style='margin: 5px 0;'><b>表格摘要：</b></p>"

        # 顯示觸發來源（可反推線索）
        if triggered_indicators or triggered_patterns:
            html_text += "<p style='margin: 5px 0; font-size: 0.9em; color: #666;'><b>觸發來源：</b>"
            if triggered_indicators:
                indicators_display = '、'.join([all_keywords[k]['display'] for k in triggered_indicators if k in all_keywords])
                html_text += f"技術指標：{indicators_display}"
            if triggered_patterns:
                if triggered_indicators:
                    html_text += " | "
                patterns_display = '、'.join([all_keywords[k]['display'] for k in triggered_patterns if k in all_keywords])
                html_text += f"圖形訊號：{patterns_display}"
            html_text += "</p>"

        html_text += "<ul style='margin: 5px 0; padding-left: 20px;'>"
        for part in formatted_parts:
            html_text += f"<li style='margin: 3px 0;'>{part}</li>"
        html_text += "</ul>"
        html_text += "</div>"
        return html_text
    else:
        # 單一理由，直接格式化
        html_text = "<div style='line-height: 1.6;'>"
        html_text += f"<p style='margin: 5px 0;'><b>表格摘要：</b>{formatted_text}</p>"
        html_text += "</div>"
        return html_text


def ranking_value_label(kind: str, value: Any) -> str:
    text = str(value or "")
    mappings = {
        "threshold_mode": {"fixed": "固定門檻", "quantile": "百分位排名"},
        "ranking_method": {"nearest_rank": "最近名次法"},
    }
    return mappings.get(kind, {}).get(text, text or "未設定")


def _table_reason_summary(item: Any) -> str:
    """依保存的結構化理由項目產生表格前三項；不猜測文字分隔符。"""
    reason_text = getattr(item, "reason_text", None)
    if not isinstance(reason_text, str):
        reason_text = getattr(item, "recommendation_reasons", "")
    reasons = getattr(item, "reasons", ())
    if type(reasons) not in (tuple, list) or any(
        type(reason) is not str or not reason for reason in reasons
    ):
        reasons = ()
    if not isinstance(reason_text, str):
        reason_text = ""
    if not reason_text:
        return "、".join(reasons[:3])
    if len(reasons) <= 3:
        return reason_text

    # 分隔符也可能出現在 tag 內；逐一核對保存的 tag 才能安全切摘要。
    position = 0
    for index, reason in enumerate(reasons[:3]):
        if not reason_text.startswith(reason, position):
            return reason_text
        position += len(reason)
        if position < len(reason_text) and reason_text[position] in "+-":
            position += 1
        if index < 2:
            if not reason_text.startswith("、", position):
                return reason_text
            position += 1
    # 若舊保存列已只有三項，保留原文，不補造無法回推的理由。
    return reason_text[:position]


def recommendation_item_to_view_row(
    item: Any,
    *,
    ml_status: str,
    ml_projection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """把 sealed RecommendationItem 投影成既有 Qt 表格欄位。

    校準欄只接受已驗證 read model 的逐股 projection；其餘狀態維持未知或不可得。
    """

    percentile_bp = getattr(item, "score_percentile_bp", None)
    universe_date = getattr(item, "eligible_universe_date", None)
    if universe_date is not None:
        universe_date = universe_date.isoformat()
    projection = ml_projection if ml_status == "verified" else None

    def projected_value(*names: str) -> Any:
        if projection is None:
            return None
        for name in names:
            value = projection.get(name)
            if value is not None and value != "":
                return value
        return None

    field_status = {
        "not_requested": "unavailable",
        "unknown": "unknown",
        "unavailable": "unavailable",
        "verified": "verified" if projection is not None else "unavailable",
        "legacy_saved_fields": "verified" if projection is not None else "unavailable",
    }.get(ml_status, "unknown")

    calibrated_probability_status = (
        projected_value("calibrated_probability_status") or field_status
    )
    after_cost_status = (
        projected_value("after_cost_profit_probability_status") or field_status
    )
    calibration_status = (
        projected_value("calibration_status", "status") or field_status
    )
    provenance_status = projected_value("provenance_status") or "unavailable"

    row: dict[str, Any] = {
        "證券代號": item.stock_code,
        "證券名稱": item.stock_name or item.stock_code,
        "收盤價": item.close_price,
        "漲幅%": item.price_change,
        "總分": item.rule_score,
        "指標分": item.indicator_score,
        "圖形分": item.pattern_score,
        "成交量分": item.volume_score,
        "推薦理由": _table_reason_summary(item),
        "產業": item.industry or "",
        "Regime匹配": (
            "是" if item.regime_match is True
            else "否" if item.regime_match is False
            else "未知"
        ),
        "score_percentile_bp": percentile_bp,
        "eligible_universe_size": item.eligible_universe_size,
        "eligible_universe_date": universe_date,
        "ranking_method": item.ranking_method,
        "threshold_mode": item.threshold_mode,
        "ranking_score_bp": projected_value("ranking_score_bp"),
        "calibrated_probability_bp": projected_value("calibrated_probability_bp"),
        "calibrated_probability_status": calibrated_probability_status,
        "校準機率資料狀態": status_label(
            calibrated_probability_status, dimension="data"
        ),
        "after_cost_profit_probability_bp": projected_value(
            "after_cost_profit_probability_bp"
        ),
        "after_cost_profit_probability_status": after_cost_status,
        "成本後機率資料狀態": status_label(
            after_cost_status, dimension="data"
        ),
        "evidence_confidence": projected_value("evidence_confidence") or "",
        "sample_size": projected_value("sample_size"),
        "cost_basis_bp": projected_value("cost_basis_bp"),
        "calibration_model_version": (
            projected_value("calibration_model_version", "model_version", "model_id") or ""
        ),
        "calibration_dataset_version": (
            projected_value("calibration_dataset_version", "dataset_version", "dataset_id") or ""
        ),
        "calibration_horizon": projected_value(
            "calibration_horizon", "horizon_trading_days", "horizon"
        ) or "",
        "calibration_status": calibration_status,
        "校準資格狀態": status_label(
            calibration_status, dimension="qualification"
        ),
        "calibration_source": projected_value("calibration_source", "source") or "",
        "calibration_warnings": list(
            projected_value("calibration_warnings", "warnings") or ()
        ),
        "calibration_source_trace": list(
            projected_value("calibration_source_trace", "source_trace") or ()
        ),
        "calibration_probability_transform_id": (
            projected_value("calibration_probability_transform_id", "probability_transform_id") or ""
        ),
        "calibration_probability_baseline_id": (
            projected_value("calibration_probability_baseline_id", "probability_baseline_id") or ""
        ),
        "calibration_probability_baseline_kind": (
            projected_value("calibration_probability_baseline_kind", "probability_baseline_kind") or ""
        ),
        "calibration_probability_baseline_probability_bp": projected_value(
            "calibration_probability_baseline_probability_bp",
            "probability_baseline_probability_bp",
        ),
        "calibration_raw_probability_bp": projected_value(
            "calibration_raw_probability_bp", "raw_calibrated_probability_bp"
        ),
        "calibration_raw_after_cost_probability_bp": projected_value(
            "calibration_raw_after_cost_probability_bp",
            "raw_after_cost_profit_probability_bp",
        ),
        "calibration_provenance": {
            "training_provenance": dict(projected_value("training_provenance") or {}),
            "inference_provenance": dict(projected_value("inference_provenance") or {}),
            "provenance_compatibility": dict(
                projected_value("provenance_compatibility") or {}
            ),
            "provenance_status": provenance_status,
        },
    }
    if item.threshold_mode == "quantile":
        percentile = (
            Decimal(percentile_bp) / Decimal(100)
            if percentile_bp is not None
            else None
        )
        row.update(
            {
                "百分位": (
                    f"{percentile:.2f}%"
                    if percentile is not None
                    else "N/A"
                ),
                "母體數": (
                    item.eligible_universe_size
                    if item.eligible_universe_size is not None
                    else "N/A"
                ),
                "排名日期": universe_date or "N/A",
                "排名方法": item.ranking_method or "N/A",
                "門檻模式": "百分位",
            }
        )
    elif item.threshold_mode == "fixed":
        row["門檻模式"] = "固定門檻"
    else:
        row["門檻模式"] = "未知"
    return row


def _recommendation_value(
    recommendation: Any,
    execution_field: str,
    legacy_field: str,
    default: Any = None,
) -> Any:
    """同時呈現 sealed item 與歷史 DTO，未知值維持 None。"""

    if hasattr(recommendation, execution_field):
        return getattr(recommendation, execution_field)
    return getattr(recommendation, legacy_field, default)


def _score_text(value: Any) -> str:
    numeric = _decimal_value(value)
    return f"{numeric:.1f}" if numeric is not None else "未知"


def _reason_text_tag_count(reason_text: str, tags: tuple[str, ...]) -> int:
    """回報保存文字能依序核對到幾個原始 tag，不拆解 tag 內分隔符。"""
    position = 0
    matched = 0
    for index, tag in enumerate(tags):
        if not reason_text.startswith(tag, position):
            return matched
        position += len(tag)
        if position < len(reason_text) and reason_text[position] in "+-":
            position += 1
        matched += 1
        if index < len(tags) - 1:
            if not reason_text.startswith("、", position):
                return matched
            position += 1
    return matched


def generate_explain_panel(recommendation: Any) -> str:
    """生成 Explain 面板 v1：推薦分數拆解 + 風險點（Phase 3.3）

    Args:
        recommendation: 推薦股票 DTO

    Returns:
        str: Explain 面板 HTML 內容
    """
    html_text = "<div style='line-height: 1.6;'>"
    html_text += "<p style='margin: 5px 0;'><b>分數拆解：</b></p>"
    html_text += "<table style='width: 100%; border-collapse: collapse; margin: 5px 0;'>"

    # 總分
    total_score = _recommendation_value(recommendation, "rule_score", "total_score")
    indicator_score = recommendation.indicator_score
    pattern_score = recommendation.pattern_score
    volume_score = recommendation.volume_score
    total_number = _decimal_value(total_score)
    score_color = (
        '#16a34a' if total_number is not None and total_number >= 60
        else '#f59e0b' if total_number is not None and total_number >= 50
        else '#dc2626' if total_number is not None
        else '#6b7280'
    )
    html_text += f"""
    <tr style='background-color: #2d2d2d;'>
        <td style='padding: 5px; border: 1px solid #444;'><b>總分</b></td>
        <td style='padding: 5px; border: 1px solid #444; text-align: right;'>
            <span style='color: {score_color}; font-weight: bold; font-size: 1.1em;'>{_score_text(total_score)}</span>
        </td>
    </tr>
    """

    # 各子分數
    # 指標分數
    indicator_number = _decimal_value(indicator_score)
    indicator_color = (
        '#16a34a' if indicator_number is not None and indicator_number >= 60
        else '#f59e0b' if indicator_number is not None and indicator_number >= 50
        else '#dc2626' if indicator_number is not None
        else '#6b7280'
    )
    html_text += f"""
    <tr style='background-color: #1e1e1e;'>
        <td style='padding: 5px; border: 1px solid #444;'>技術指標分數</td>
        <td style='padding: 5px; border: 1px solid #444; text-align: right;'>
            <span style='color: {indicator_color};'>{_score_text(indicator_score)}</span>
        </td>
    </tr>
    """

    # 圖形分數
    pattern_number = _decimal_value(pattern_score)
    pattern_color = (
        '#16a34a' if pattern_number is not None and pattern_number >= 60
        else '#f59e0b' if pattern_number is not None and pattern_number >= 50
        else '#dc2626' if pattern_number is not None
        else '#6b7280'
    )
    html_text += f"""
    <tr style='background-color: #1e1e1e;'>
        <td style='padding: 5px; border: 1px solid #444;'>圖形模式分數</td>
        <td style='padding: 5px; border: 1px solid #444; text-align: right;'>
            <span style='color: {pattern_color};'>{_score_text(pattern_score)}</span>
        </td>
    </tr>
    """

    # 成交量分數
    volume_number = _decimal_value(volume_score)
    volume_color = (
        '#16a34a' if volume_number is not None and volume_number >= 60
        else '#f59e0b' if volume_number is not None and volume_number >= 50
        else '#dc2626' if volume_number is not None
        else '#6b7280'
    )
    html_text += f"""
    <tr style='background-color: #1e1e1e;'>
        <td style='padding: 5px; border: 1px solid #444;'>成交量分數</td>
        <td style='padding: 5px; border: 1px solid #444; text-align: right;'>
            <span style='color: {volume_color};'>{_score_text(volume_score)}</span>
        </td>
    </tr>
    """

    html_text += "</table>"

    # 這裡只呈現當次保存的完整理由，不從目前行情重建理由。
    reason_text = getattr(recommendation, "reason_text", None)
    if isinstance(reason_text, str) and reason_text.strip():
        full_reason_text = html.escape(reason_text)
    else:
        full_reason_text = "未知（保存項目未提供）"
    html_text += (
        "<p style='margin: 10px 0 5px 0;'><b>保存的推薦理由文字（舊紀錄若已截短，無法回推）：</b></p>"
        f"<p style='margin: 5px 0;'>{full_reason_text}</p>"
    )

    saved_reason_tags = getattr(recommendation, "reasons", ())
    if type(saved_reason_tags) not in (tuple, list) or any(
        type(tag) is not str or not tag for tag in saved_reason_tags
    ):
        saved_reason_tags = ()
    else:
        saved_reason_tags = tuple(saved_reason_tags)
    represented_tag_count = (
        _reason_text_tag_count(reason_text, saved_reason_tags)
        if isinstance(reason_text, str)
        else 0
    )
    remaining_saved_tags = saved_reason_tags[represented_tag_count:]
    if remaining_saved_tags:
        html_text += (
            "<p style='margin: 5px 0;'><b>另有保存的理由標籤（未保存貢獻符號）：</b></p>"
            "<ul style='margin: 5px 0; padding-left: 20px;'>"
        )
        for tag in remaining_saved_tags:
            html_text += f"<li>{html.escape(tag)}</li>"
        html_text += "</ul>"

    # 逐因子欄位只接受 sealed item 已提供的事實，不推導缺失貢獻。
    factor_contributions = getattr(recommendation, "factor_contributions", ())
    html_text += (
        "<p style='margin: 10px 0 5px 0;'><b>逐因子貢獻（本次結果提供）：</b></p>"
    )
    if factor_contributions:
        html_text += "<ul style='margin: 5px 0; padding-left: 20px;'>"
        for contribution in factor_contributions:
            factor_id = html.escape(str(getattr(contribution, "factor_id", "未知")))
            value = getattr(contribution, "value", None)
            value_text = "未知" if value is None else html.escape(str(value))
            unit = html.escape(str(getattr(contribution, "unit", "未知")))
            version = html.escape(str(getattr(contribution, "version", "未知")))
            source_refs = getattr(contribution, "source_refs", ())
            source_texts = []
            for source_ref in source_refs:
                source_id = html.escape(str(getattr(source_ref, "source_id", "未知")))
                revision = html.escape(str(getattr(source_ref, "revision", "未知")))
                snapshot_id = getattr(source_ref, "snapshot_id", None)
                source_text = f"{source_id}（版本 {revision}"
                if snapshot_id:
                    source_text += f"；快照 {html.escape(str(snapshot_id))}"
                source_texts.append(source_text + "）")
            sources_label = "、".join(source_texts) or "未提供來源參照"
            html_text += (
                f"<li>{factor_id}：{value_text} {unit}；因子版本 {version}；"
                f"來源：{sources_label}</li>"
            )
        html_text += "</ul>"
    else:
        html_text += "<p style='margin: 5px 0;'>未知（本次結果未提供）</p>"

    html_text += "<p style='margin: 10px 0 5px 0;'><b>排名門檻：</b></p>"
    html_text += "<ul style='margin: 5px 0; padding-left: 20px;'>"
    threshold_mode = getattr(recommendation, "threshold_mode", None)
    ranking_method = getattr(recommendation, "ranking_method", None)
    score_percentile_bp = getattr(recommendation, "score_percentile_bp", None)
    eligible_universe_size = getattr(recommendation, "eligible_universe_size", None)
    rank = getattr(recommendation, "rank", None)
    eligible_universe_date = getattr(recommendation, "eligible_universe_date", None)
    html_text += f"<li>門檻模式：{ranking_value_label('threshold_mode', threshold_mode)}</li>"
    html_text += f"<li>排名：{rank if rank is not None else '未知'}</li>"
    if type(eligible_universe_date) is date:
        eligible_date_text = eligible_universe_date.isoformat()
    else:
        eligible_date_text = "未知"
    html_text += f"<li>合格母體日期：{html.escape(eligible_date_text)}</li>"
    if ranking_method:
        html_text += f"<li>排名方法：{ranking_value_label('ranking_method', ranking_method)}</li>"
    if score_percentile_bp is not None:
        html_text += f"<li>分數百分位：{Decimal(score_percentile_bp) / Decimal(100):.1f}%</li>"
    if eligible_universe_size is not None:
        html_text += f"<li>合格母體數：{eligible_universe_size} 檔</li>"
    html_text += "</ul>"

    # 風險點提示
    html_text += "<p style='margin: 10px 0 5px 0;'><b>風險點：</b></p>"
    html_text += "<ul style='margin: 5px 0; padding-left: 20px;'>"

    risk_points = []

    # 檢查各項分數是否偏低
    if indicator_number is not None and indicator_number < 50:
        risk_points.append(f"技術指標分數偏低（{_score_text(indicator_score)}），可能缺乏技術面支撐")
    if pattern_number is not None and pattern_number < 40:
        risk_points.append(f"圖形模式分數偏低（{_score_text(pattern_score)}），圖形尚未完全形成")
    if volume_number is not None and volume_number < 50:
        risk_points.append(f"成交量分數偏低（{_score_text(volume_score)}），可能缺乏資金關注")

    # 檢查總分
    if total_number is not None and total_number < 50:
        risk_points.append(f"總分偏低（{_score_text(total_score)}），綜合評分不足，建議謹慎")
    elif total_number is not None and total_number < 60:
        risk_points.append(f"總分中等（{_score_text(total_score)}），建議觀察後續表現")

    # 檢查 Regime 匹配
    regime_match = getattr(recommendation, "regime_match", None)
    if regime_match is False:
        risk_points.append("市場狀態不匹配，策略可能不適用當前市場環境")

    # 檢查價格變化
    price_change = _decimal_value(getattr(recommendation, "price_change", None))
    if price_change is not None and price_change < 0:
        risk_points.append(f"價格下跌（{_score_text(price_change)}%），需注意趨勢反轉風險")
    elif price_change is not None and price_change > 10:
        risk_points.append(f"價格漲幅較大（{_score_text(price_change)}%），需注意追高風險")

    if not risk_points:
        complete_positive_evidence = (
            total_number is not None
            and total_number >= 60
            and indicator_number is not None
            and indicator_number >= 60
            and pattern_number is not None
            and pattern_number >= 60
            and volume_number is not None
            and volume_number >= 60
            and regime_match is True
            and price_change is not None
            and price_change <= 10
        )
        known_evidence = any(
            value is not None
            for value in (
                total_number,
                indicator_number,
                pattern_number,
                volume_number,
                regime_match,
                price_change,
            )
        )
        if complete_positive_evidence:
            risk_points.append("已提供分數、Regime 與漲幅未顯示明確風險；仍須依資料日期與其他限制判讀")
        elif known_evidence:
            risk_points.append("目前已提供欄位未辨識額外風險；缺少資料不代表風險較低")
        else:
            risk_points.append("風險評估資料不足，無法判定目前風險")

    for risk in risk_points:
        html_text += f"<li style='margin: 3px 0; color: #e0e0e0;'>{risk}</li>"

    html_text += "</ul>"
    html_text += "</div>"

    return html_text


def generate_why_not(recommendation: Any, config: dict[str, Any]) -> str:
    """生成 Why Not（反向解釋）：為什麼分數不夠高或可能被其他股票超越

    Args:
        recommendation: 推薦股票 DTO
        config: 策略配置

    Returns:
        str: Why Not 說明文字（HTML 格式）
    """
    why_not_items = []

    # 檢查各子分數（相對於理想值）
    # 理想值：各子分數都應該在 60 以上才算優秀
    ideal_score = 60

    indicator_score = _decimal_value(recommendation.indicator_score)
    pattern_score = _decimal_value(recommendation.pattern_score)
    volume_score = _decimal_value(recommendation.volume_score)
    price_change = _decimal_value(getattr(recommendation, "price_change", None))
    total_score = _decimal_value(
        _recommendation_value(recommendation, "rule_score", "total_score")
    )
    ideal_number = Decimal(ideal_score)

    if indicator_score is not None and indicator_score < ideal_number:
        gap = ideal_number - indicator_score
        why_not_items.append({
            'item': '技術指標分數',
            'current': _score_text(indicator_score),
            'ideal': f'{ideal_number:.1f}',
            'gap': f'{gap:.1f}',
            'severity': 'high' if gap > 20 else 'medium' if gap > 10 else 'low',
            'hint': '可考慮等待更多技術指標訊號'
        })

    if pattern_score is not None and pattern_score < ideal_number:
        gap = ideal_number - pattern_score
        why_not_items.append({
            'item': '圖形模式分數',
            'current': _score_text(pattern_score),
            'ideal': f'{ideal_number:.1f}',
            'gap': f'{gap:.1f}',
            'severity': 'high' if gap > 20 else 'medium' if gap > 10 else 'low',
            'hint': '圖形模式尚未完全形成'
        })

    if volume_score is not None and volume_score < ideal_number:
        gap = ideal_number - volume_score
        why_not_items.append({
            'item': '成交量分數',
            'current': _score_text(volume_score),
            'ideal': f'{ideal_number:.1f}',
            'gap': f'{gap:.1f}',
            'severity': 'medium' if gap > 15 else 'low',
            'hint': '成交量可能尚未明顯放大'
        })

    # 檢查篩選條件（如果不符合會被直接過濾）
    filters = config.get('filters', {})
    minimum_change = _decimal_value(filters.get('price_change_min'))
    maximum_change = _decimal_value(filters.get('price_change_max'))
    if price_change is not None and minimum_change is not None and price_change < minimum_change:
        gap = minimum_change - price_change
        why_not_items.append({
            'item': '漲幅篩選',
            'current': f'{_score_text(price_change)}%',
            'required': f'{_score_text(minimum_change)}%',
            'gap': f'{_score_text(gap)}%',
            'severity': 'high',
            'hint': '不符合漲幅篩選條件，可能被過濾'
        })

    if price_change is not None and maximum_change is not None and price_change > maximum_change:
        gap = price_change - maximum_change
        why_not_items.append({
            'item': '漲幅上限',
            'current': f'{_score_text(price_change)}%',
            'required': f'{_score_text(maximum_change)}%',
            'gap': f'{_score_text(gap)}%',
            'severity': 'medium',
            'hint': '漲幅過大，可能不符合策略要求'
        })

    # 檢查 Regime 匹配
    if getattr(recommendation, "regime_match", None) is False:
        why_not_items.append({
            'item': '市場狀態匹配',
            'current': '不匹配',
            'required': '匹配',
            'gap': '需等待市場狀態變化',
            'severity': 'medium',
            'hint': '當前市場狀態與策略不匹配，分數可能被降權'
        })

    # 總分相對排名提示（如果總分較低）
    if total_score is not None and total_score < 50:
        why_not_items.append({
            'item': '總分偏低',
            'current': _score_text(total_score),
            'ideal': '60.0+',
            'gap': _score_text(Decimal(60) - total_score),
            'severity': 'high',
            'hint': '總分較低，可能排名較後'
        })

    # 格式化輸出
    if not why_not_items:
        has_complete_evidence = (
            indicator_score is not None
            and pattern_score is not None
            and volume_score is not None
            and price_change is not None
            and total_score is not None
            and getattr(recommendation, "regime_match", None) is True
            and minimum_change is not None
            and maximum_change is not None
        )
        if has_complete_evidence:
            return "<div style='line-height: 1.6;'><p style='color: #16a34a;'><b>已提供資料未顯示明確排名疑慮；仍須依其他風險限制判讀</b></p></div>"
        return "<div style='line-height: 1.6;'><p style='color: #6b7280;'><b>分數或篩選資料不足，無法判定排名疑慮</b></p></div>"

    html_text = "<div style='line-height: 1.6;'>"
    html_text += "<p style='margin: 5px 0;'><b>可能影響排名的因素：</b></p>"
    html_text += "<ul style='margin: 5px 0; padding-left: 20px;'>"

    for item in why_not_items:
        severity_color = {
            'high': '#dc2626',
            'medium': '#f59e0b',
            'low': '#6b7280'
        }.get(item['severity'], '#6b7280')

        html_text += f"<li style='margin: 5px 0;'>"
        html_text += f"<span style='color: {severity_color}; font-weight: bold;'>{item['item']}</span><br/>"
        html_text += f"&nbsp;&nbsp;目前：{item['current']}"
        if 'ideal' in item:
            html_text += f"，理想：{item['ideal']}"
        elif 'required' in item:
            html_text += f"，需要：{item['required']}"
        html_text += f"，差距：{item['gap']}<br/>"
        if 'hint' in item:
            html_text += f"&nbsp;&nbsp;<span style='color: #6b7280; font-size: 0.9em;'>{item['hint']}</span>"
        html_text += "</li>"

    html_text += "</ul>"
    html_text += "</div>"

    return html_text
