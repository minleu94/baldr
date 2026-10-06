"""每日市場研究篩選預設與已發布 cohort 摘要。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from app_module.daily_market_feature_snapshot import DAILY_MARKET_CONDITION_KEYS


_ALL_CONDITIONS: Final[tuple[str, ...]] = tuple(DAILY_MARKET_CONDITION_KEYS)
_MA20_CONDITION: Final[tuple[str, ...]] = ("close_above_ma20",)
_MA60_CONDITION: Final[tuple[str, ...]] = ("close_above_ma60",)
_FILTER_STATES: Final[frozenset[str]] = frozenset(
    {"all", "match", "no_match", "unknown"}
)
_ROW_STATES: Final[frozenset[str]] = frozenset({"match", "no_match", "unknown"})
_STATE_LABELS: Final[dict[str, str]] = {
    "match": "符合",
    "no_match": "不符合",
    "unknown": "未知",
}


@dataclass(frozen=True, slots=True)
class ResearchFilterPreset:
    """呈現既有每日市場條件的篩選預設。"""

    preset_id: str
    label: str
    condition_keys: tuple[str, ...]
    combine_mode: str
    filter_state: str
    description: str


DAILY_MARKET_RESEARCH_PRESETS: Final[tuple[ResearchFilterPreset, ...]] = (
    ResearchFilterPreset(
        preset_id="all_observations",
        label="全部觀察（預設）",
        condition_keys=_ALL_CONDITIONS,
        combine_mode="AND",
        filter_state="all",
        description="保留既有 MA20／MA60 AND 條件，顯示所有已發布觀察列。",
    ),
    ResearchFilterPreset(
        preset_id="any_above",
        label="任一均線之上",
        condition_keys=_ALL_CONDITIONS,
        combine_mode="OR",
        filter_state="match",
        description="顯示收盤價高於 MA20 或 MA60 的已發布列。",
    ),
    ResearchFilterPreset(
        preset_id="ma20_above",
        label="收盤價高於 MA20",
        condition_keys=_MA20_CONDITION,
        combine_mode="AND",
        filter_state="match",
        description="只顯示既有收盤價高於 MA20 條件符合的列。",
    ),
    ResearchFilterPreset(
        preset_id="ma60_above",
        label="收盤價高於 MA60",
        condition_keys=_MA60_CONDITION,
        combine_mode="AND",
        filter_state="match",
        description="只顯示既有收盤價高於 MA60 條件符合的列。",
    ),
    ResearchFilterPreset(
        preset_id="needs_review",
        label="待檢視（未知）",
        condition_keys=_ALL_CONDITIONS,
        combine_mode="AND",
        filter_state="unknown",
        description="顯示兩項既有條件以 AND 組合後為未知的已發布列。",
    ),
)


@dataclass(frozen=True, slots=True)
class ResearchCandidateSummary:
    """以宣告 cohort 為分母的唯讀研究列摘要。"""

    declared_count: int
    published_count: int
    missing_count: int
    match_count: int
    no_match_count: int
    unknown_count: int
    visible_count: int
    excluded_count: int
    missing_stock_codes: tuple[str, ...]
    excluded_reasons: tuple[str, ...]


def get_research_filter_preset(preset_id: str) -> ResearchFilterPreset:
    """依識別碼取得預設；未知識別碼明確失敗。"""

    for preset in DAILY_MARKET_RESEARCH_PRESETS:
        if preset.preset_id == preset_id:
            return preset
    raise ValueError(f"未知的每日市場研究篩選預設：{preset_id!r}")


def match_research_filter_preset(
    condition_keys: Sequence[str], combine_mode: str, filter_state: str
) -> str | None:
    """完全符合預設時回傳識別碼，自訂條件維持原樣並回傳 None。"""

    if isinstance(condition_keys, (str, bytes)) or not isinstance(
        condition_keys, Sequence
    ):
        return None
    keys = tuple(condition_keys)
    for preset in DAILY_MARKET_RESEARCH_PRESETS:
        if (
            keys == preset.condition_keys
            and combine_mode == preset.combine_mode
            and filter_state == preset.filter_state
        ):
            return preset.preset_id
    return None


def summarize_research_candidates(
    snapshot: object, rows: Sequence[object], filter_state: str
) -> ResearchCandidateSummary:
    """彙總已發布研究列；宣告缺件計為未知但不建立可下鑽列。"""

    if filter_state not in _FILTER_STATES:
        raise ValueError(f"未知的每日市場研究篩選狀態：{filter_state!r}")

    manifest = getattr(snapshot, "manifest", None)
    if not isinstance(manifest, Mapping):
        raise ValueError("snapshot 缺少已驗證的 manifest 宣告母體")
    declared_values = manifest.get("declared_stock_codes")
    if (
        isinstance(declared_values, (str, bytes))
        or not isinstance(declared_values, Sequence)
        or not declared_values
        or any(not isinstance(code, str) or not code for code in declared_values)
    ):
        raise ValueError("snapshot 未提供有效的宣告股票母體")
    declared_codes = tuple(declared_values)
    if len(set(declared_codes)) != len(declared_codes):
        raise ValueError("snapshot 宣告股票母體含有重複代碼")

    published_snapshots = getattr(snapshot, "stock_snapshots", None)
    if not isinstance(published_snapshots, Mapping):
        raise ValueError("snapshot 缺少已發布個股資料映射")
    published_codes = set(published_snapshots)
    if any(not isinstance(code, str) or not code for code in published_codes):
        raise ValueError("已發布個股資料含有無效股票代碼")
    declared_set = set(declared_codes)
    outside_codes = published_codes - declared_set
    if outside_codes:
        raise ValueError(
            "已發布個股資料包含未宣告股票：" + ", ".join(sorted(outside_codes))
        )

    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        raise TypeError("rows 必須是每日市場研究列序列")
    row_by_code: dict[str, object] = {}
    for row in rows:
        stock_code = getattr(row, "stock_code", None)
        if not isinstance(stock_code, str) or not stock_code:
            raise ValueError("研究列缺少有效股票代碼")
        if stock_code in row_by_code:
            raise ValueError(f"研究列含有重複股票代碼：{stock_code}")
        if stock_code not in published_codes:
            raise ValueError(f"研究列不屬於已發布 cohort：{stock_code}")
        row_by_code[stock_code] = row
    if set(row_by_code) != published_codes:
        missing_rows = sorted(published_codes - set(row_by_code))
        raise ValueError(
            "研究列必須完整對應已發布個股資料；缺少：" + ", ".join(missing_rows)
        )

    published_state_counts = {state: 0 for state in _ROW_STATES}
    excluded_reasons: list[str] = []
    seen_reasons: set[str] = set()
    for row in rows:
        state = getattr(row, "combined_state", None)
        if state not in _ROW_STATES:
            raise ValueError(
                f"研究列狀態必須是 match/no_match/unknown，收到：{state!r}"
            )
        published_state_counts[state] += 1

    visible_count = (
        len(published_codes)
        if filter_state == "all"
        else published_state_counts[filter_state]
    )
    excluded_count = len(published_codes) - visible_count
    if excluded_count:
        for row in rows:
            row_state = getattr(row, "combined_state")
            if filter_state != "all" and row_state == filter_state:
                continue
            stock_code = getattr(row, "stock_code")
            filter_reason = (
                f"{stock_code}：整體狀態「{_STATE_LABELS[row_state]}」，"
                f"目前只顯示「{_STATE_LABELS[filter_state]}」。"
            )
            _append_reason(filter_reason, excluded_reasons, seen_reasons)
            _append_existing_reasons(row, excluded_reasons, seen_reasons)

    missing_codes = tuple(code for code in declared_codes if code not in published_codes)
    missing_count = len(missing_codes)
    return ResearchCandidateSummary(
        declared_count=len(declared_codes),
        published_count=len(published_codes),
        missing_count=missing_count,
        match_count=published_state_counts["match"],
        no_match_count=published_state_counts["no_match"],
        unknown_count=published_state_counts["unknown"] + missing_count,
        visible_count=visible_count,
        excluded_count=excluded_count,
        missing_stock_codes=missing_codes,
        excluded_reasons=tuple(excluded_reasons),
    )


def _append_existing_reasons(
    row: object, target: list[str], seen: set[str]
) -> None:
    """只彙集 row 已保存的 why_not 或 condition reason 字串。"""

    why_not = getattr(row, "why_not", ())
    if isinstance(why_not, str):
        why_not = (why_not,)
    if isinstance(why_not, Sequence):
        for reason in why_not:
            _append_reason(reason, target, seen)

    conditions = getattr(row, "conditions", ())
    if isinstance(conditions, Sequence) and not isinstance(
        conditions, (str, bytes)
    ):
        for condition in conditions:
            _append_reason(getattr(condition, "unknown_reason", None), target, seen)
            _append_reason(getattr(condition, "reason", None), target, seen)


def _append_reason(value: object, target: list[str], seen: set[str]) -> None:
    if isinstance(value, str) and value.strip() and value not in seen:
        target.append(value)
        seen.add(value)
