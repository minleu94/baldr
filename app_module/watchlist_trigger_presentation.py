"""將既有候選池觸發快照轉成判讀說明，不重新評分或推測缺失資料。"""

from app_module.decision_desk_dtos import WatchlistTriggerSummary


def format_watchlist_trigger_review(
    summary: WatchlistTriggerSummary,
    *,
    codes: tuple[str, ...] | None = None,
    count: int | None = None,
) -> str:
    """共用於首頁與每日決策；局部覆蓋時只解釋尚未列出的股票。"""
    selected_codes = tuple(dict.fromkeys(summary.triggered_codes if codes is None else codes))
    reported_count = summary.trigger_count if count is None else count
    total = max(reported_count or 0, len(selected_codes))
    source_date = getattr(summary, "as_of_date", None)
    date_text = source_date.isoformat() if source_date else "未知"
    quality_text = {
        "observed": "已觀測",
        "estimated": "含估計或缺件",
        "degraded": "資料降級",
        "missing": "資料缺失",
    }.get(summary.quality.value, "未知")
    warnings = set(summary.warnings)
    empty_source_pool = total == 0 and "watchlist_trigger_empty_pool" in warnings
    context = (
        f"候選池檢查日：{date_text}；候選池來源：可讀但為空"
        if empty_source_pool
        else f"資料日：{date_text}；資料品質：{quality_text}"
    )
    if not total:
        if empty_source_pool:
            return f"候選池來源為空（{context}）；目前沒有可評估的股票，不代表沒有風險。"
        if reported_count is None:
            return f"候選池觸發數未知（{context}）；請先確認資料是否齊全。"
        return f"候選池目前沒有指標變化觸發（{context}）；不代表沒有風險。"

    # 只翻譯 producer 已輸出的分類；不把陌生訊號或其他股票補進觸發清單。
    signals: dict[str, set[str]] = {}
    for group in (summary.top_signal or "").split(";"):
        kind, separator, raw_codes = group.strip().partition("=")
        if separator and kind in {"new", "up", "down"}:
            for code in raw_codes.split(","):
                signals.setdefault(code.strip(), set()).add(kind)

    lines = [f"候選池有 {total} 筆指標變化待查看（{context}）。"]
    for code in selected_codes:
        kinds = signals.get(code, set())
        if len(kinds) != 1:
            reason = "觸發原因未提供或不一致，暫時無法判定變化方向；先確認來源資料。"
        elif "new" in kinds:
            if f"watchlist_trigger_previous_unknown:{code}" in warnings:
                reason = "目前分數達觀察門檻，但缺前次分數；不能確認是新轉強，請先補查前次資料。"
            else:
                reason = "分數新達觀察門檻；請查看量價與原推薦理由是否支持持續觀察。"
        elif "up" in kinds:
            reason = "分數較前次上升，且仍達觀察門檻；請查看量價是否支持這次轉強。"
        else:
            reason = "分數較前次下降，但仍達觀察門檻；請查看原推薦理由是否轉弱、是否繼續觀察。"
        if f"watchlist_trigger_risk_alert:{code}" in warnings:
            reason += "另有技術風險提示，請一併查看風險說明。"
        lines.append(f"{code}：{reason}")
    if total > len(selected_codes):
        lines.append(f"另有 {total - len(selected_codes)} 筆未提供股票代號與原因，請先確認來源明細。")
    lines.append(
        "下一步：到「候選池」選取上述股票 →「查看選中個股研究報告」，"
        "核對資料日期、價格／技術與原推薦理由，再決定繼續觀察或記錄疑慮。"
        "這是觀察提醒，不是買賣指令；分數變化不等於股價漲跌或獲利機率。"
    )
    return "\n".join(lines)
