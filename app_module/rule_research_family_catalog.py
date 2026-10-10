"""原八族研究方向的唯讀能力字典；登記方向不授予方法或交易資格。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import Any, Literal

from app_module.daily_market_method_contract import method_contracts_payload


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    raise TypeError("家族中繼資料只接受不可變 JSON 基本值；小數參數請使用字串")


def _detach(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _detach(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_detach(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class RuleResearchFamilyCapability:
    """不可變的家族能力；to_dict 每次提供獨立 JSON-ready 副本。"""

    family_id: str
    title: str
    status: Literal["partial", "unavailable", "unknown"]
    versioned_method_refs: tuple[str, ...]
    required_fields: tuple[str, ...]
    warmup: Mapping[str, Any]
    missing: Mapping[str, Any]
    availability: Mapping[str, Any]
    cost: Mapping[str, Any]
    source_refs: tuple[str, ...]
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("versioned_method_refs", "required_fields", "source_refs", "blockers"):
            values = tuple(getattr(self, name))
            if not all(isinstance(value, str) for value in values):
                raise TypeError(f"{name} 必須是字串序列")
            object.__setattr__(self, name, values)
        for name in ("warmup", "missing", "availability", "cost"):
            object.__setattr__(self, name, _freeze(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {field.name: _detach(getattr(self, field.name)) for field in fields(self)}


_AVAILABILITY = {
    "official_availability_state": "unknown",
    "market_calendar_completeness": "unknown",
    "historical_pit_eligible": False,
    "formal_eligible": False,
    "basis": "目錄不讀取來源；資料日期與 availability 必須沿原保存證據核驗",
}
_MISSING = {
    "state": "unknown",
    "unknown_is_preserved": True,
    "fallback": "none",
    "missing_is_negative_sample": False,
}
_COST = {
    "database_or_network_io_during_projection": False,
    "measured_runtime_memory_or_bytes": "unknown",
    "trading_cost": "unknown",
    "known_operation": "讀取固定能力中繼資料，不計算或啟用研究方法",
}


def _capability(
    family_id: str,
    title: str,
    required_fields: tuple[str, ...],
    source_refs: tuple[str, ...],
    blockers: tuple[str, ...],
    *,
    status: Literal["partial", "unavailable", "unknown"] = "unavailable",
    versioned_method_refs: tuple[str, ...] = (),
    warmup: Mapping[str, Any] | None = None,
) -> RuleResearchFamilyCapability:
    return RuleResearchFamilyCapability(
        family_id=family_id,
        title=title,
        status=status,
        versioned_method_refs=versioned_method_refs,
        required_fields=required_fields,
        warmup=warmup if warmup is not None else {"state": "unknown", "window": None},
        missing=_MISSING,
        availability=_AVAILABILITY,
        cost=_COST,
        source_refs=source_refs,
        blockers=blockers,
    )


def _build_catalog() -> tuple[RuleResearchFamilyCapability, ...]:
    contracts = method_contracts_payload()
    ma_refs = tuple(
        f"{contract['method_id']}@{contract['version']}"
        for contract in (contracts["close_above_ma20"], contracts["close_above_ma60"])
    )
    ma_alignment_ref = "sma_close_alignment_5_10_20_60@1"
    volatility_refs = (
        "daily_market.bollinger_bandwidth_sma30_population_2x@bollinger-bandwidth-sma30-population-2x.v1",
        "daily_market.atr14_sma_true_range@atr14-sma-true-range.v1",
    )
    return (
        _capability(
            "original_price_volume_ranking", "原價量排名",
            ("saved_original_ranking", "declared_universe", "period", "threshold"),
            ("app_module/original_stock_ranking.py",),
            ("僅沿原保存排名；無新版評分或版本化每日方法契約", "母體、期間與門檻須沿原來源"),
            status="partial",
            warmup={"state": "inherited", "basis": "原保存本日／本週排名；不重算"},
        ),
        _capability(
            "close_vs_moving_average", "趨勢轉強",
            ("close", "MA5", "MA10", "MA20", "MA60"),
            (
                "app_module/daily_market_method_contract.py",
                "app_module/daily_market_feature_snapshot.py",
                "app_module/daily_market_technical_ma_alignment_evidence_v1.py",
                "app_module/daily_market_technical_universe_ma_alignment_query_v1.py",
            ),
            (
                "close 高於 MA20／MA60 與四均線排列是不同觀察；排列只比較 MA5>MA10>MA20>MA60",
                "四均線排列不提供斜率、交叉觸發、量能條件或完整進出場；其他獨立方法沿各自契約",
                "MA20 上彎與完整進出場策略未定版；本目錄不授予執行資格",
            ),
            status="partial", versioned_method_refs=(*ma_refs, ma_alignment_ref),
            warmup={
                "state": "method_specific_observed_rows",
                "required_observation_counts": {
                    "MA20": 20,
                    "MA60": 60,
                    "sma_close_alignment_5_10_20_60": 60,
                },
                "basis": "各方法依連續有效來源觀測；F02 不代表官方交易日曆完整性",
                "formal_or_calendar_qualification": False,
            },
        ),
        _capability(
            "bollinger_compression_breakout", "布林壓縮突破",
            ("close", "BB_Upper", "upperband", "middleband", "lowerband", "compression_history", "volume", "liquidity"),
            ("analysis_module/technical_analysis/technical_indicators.py:calculate_causal_indicators",
             "app_module/daily_market_feature_snapshot.py"),
            ("v2 保留 close／MA20／MA60；opt-in v3 已保存 BB_Upper 有限上軌比較",
             "U1 壓縮窗口、門檻、量能與流動性條件未決",
             "close 高於 upperband 只可提有限研究比較，不能稱完整壓縮突破",
             "compression 完整窗口與門檻未定、未啟用；有限上軌方法不授正式或參數 lineage 資格"),
            status="partial",
            versioned_method_refs=("daily_market.close_above_bbands30_upper@1.0.0",),
            warmup={"state": "finite_upper_comparison", "required_observation_count": 30,
                    "basis": "既存 BBANDS 30／2.0／2.0／SMA；連續有效 OHLC prefix",
                    "parameters": {"timeperiod": 30, "nbdevup": "2.0", "nbdevdn": "2.0", "matype": "SMA"},
                    "compression_window": None, "compression_threshold": None,
                    "formal_or_calendar_qualification": False},
        ),
        _capability(
            "volatility_contraction", "波動收斂",
            ("ATR", "amplitude", "bandwidth", "volume_history", "close", "high", "low"),
            (
                "analysis_module/technical_analysis/technical_indicators.py:calculate_causal_indicators",
                "app_module/daily_market_technical_volatility_evidence_v1.py",
                "app_module/daily_market_technical_universe_volatility_alignment_query_v1.py",
            ),
            (
                "目前僅有 BB30 bandwidth 與 ATR14-SMA 原料量測；不是已定版的收斂判斷",
                "收斂窗口與門檻未定版；完整 VCP 多段收縮／樞紐／突破尚未辨識驗證",
                "資料可得時間仍 unknown，projection/query 不代表 reader qualification 或策略執行資格",
            ),
            status="partial", versioned_method_refs=volatility_refs,
            warmup={
                "state": "component_measurements_only",
                "required_observation_counts": {
                    "daily_market.bollinger_bandwidth_sma30_population_2x": 30,
                    "daily_market.atr14_sma_true_range": 14,
                },
                "required_raw_row_counts": {
                    "daily_market.bollinger_bandwidth_sma30_population_2x": 30,
                    "daily_market.atr14_sma_true_range": 15,
                },
                "basis": "連續有效 close／OHLC 觀測；ATR14 需前一收盤價形成 14 個 true range",
                "contraction_window": None,
                "contraction_threshold": None,
                "formal_or_calendar_qualification": False,
            },
        ),
        _capability(
            "pattern_confirmation", "型態確認",
            ("pattern", "confirmation_event", "invalidation_event", "signal_date"),
            ("analysis_module/pattern_analysis",),
            ("型態與確認／失效條件未定版；需證明確認事件當時可得",),
        ),
        _capability(
            "institutional_flow_strengthening", "籌碼轉強",
            ("institutional_net_buy", "flow_history", "price", "volume", "available_date"),
            ("data_module",),
            ("5／20 日來源窗口與缺日未核驗；榜外不可補零", "尚未保存／定版家族方法"),
            warmup={"state": "unverified", "candidate_observation_counts": (5, 20), "basis": "原計畫方向，非已啟用參數"},
        ),
        _capability(
            "fundamental_momentum", "基本面動能",
            ("revenue", "earnings", "period_basis", "previous_period", "unit", "available_date"),
            ("data_module/current_fundamental_snapshots.py",),
            ("營收／獲利前期覆蓋、單位、期間及來源可得時鐘需核驗", "現況觀測不提供歷史 PIT 資格"),
        ),
        _capability(
            "industry_leadership", "產業領先",
            ("stock_return", "market_return", "industry_return", "industry_membership", "available_date"),
            ("data_module",),
            ("相對期間、同期母體與產業分類來源未定版", "當前分類不補歷史 effective intervals 或專有族群模型"),
        ),
    )


_FAMILIES = _build_catalog()


def list_rule_research_families() -> tuple[RuleResearchFamilyCapability, ...]:
    """依原八族順序列出固定能力；不包含推測方法。"""
    return _FAMILIES


def get_rule_research_family(family_id: str) -> RuleResearchFamilyCapability:
    """僅接受 exact ID；未知 ID 保留原值及 unknown，不做別名或模糊配對。"""
    for family in _FAMILIES:
        if family.family_id == family_id:
            return family
    return _capability(
        family_id, "未知研究家族", (), (), ("unknown_family_id",), status="unknown",
    )
