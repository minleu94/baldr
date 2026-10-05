"""研究母體共用顯示；僅呈現已核驗的來源，不建立排名。"""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any

ORIGINAL_RANK_UNKNOWN = "原排名未知；尚缺原強弱引擎的不可變結果、期間、完整母體及來源身份。"

def research_universe_text(binding: Mapping[str, Any] | None, *, published_count: int, declared_count: int) -> tuple[str, str]:
    if binding is None:
        text = f"母體設定來源未知；此 cohort 宣告 {declared_count} 檔，已發布 {published_count} 檔。"
        return text, text + "\n原始母體分母未知；不能將畫面列數當成全市場。\n" + ORIGINAL_RANK_UNKNOWN
    included = binding.get("included_stock_codes", ())
    excluded = binding.get("excluded_stock_codes", ())
    population = binding.get("population_count")
    denominator = "未知" if population is None else str(population)
    text = (f"母體 {binding.get('universe_id')}／{binding.get('version')}｜截至 {binding.get('as_of_date')}"
            f"｜納入 {len(included)}／排除 {len(excluded)}｜設定分母 {denominator}"
            f"｜發布涵蓋 {published_count}/{len(included)}")
    reasons = "; ".join(f"{item.get('stock_code')}：{item.get('reason')}" for item in excluded if isinstance(item, Mapping)) or "無"
    detail = (text + f"\n納入：{', '.join(included)}\n設定排除：{reasons}"
              f"\n來源設定：{binding.get('source_ref')}\n來源 SHA256：{binding.get('source_sha256')}"
              "\n設定母體不是資料資格；MA 暖機、缺件與三態仍依同一快照核驗。"
              "\n篩選隱藏不改變納入分母；設定分母不代表全市場。\n" + ORIGINAL_RANK_UNKNOWN)
    return text, detail
