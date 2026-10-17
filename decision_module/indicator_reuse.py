"""技術指標預存欄位的參數契約重用判定。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pandas as pd

from analysis_module.technical_analysis.indicator_parameter_registry import IndicatorParameterRegistry


@dataclass(frozen=True)
class IndicatorReusePlan:
    frame: pd.DataFrame
    technical_config: dict[str, Any]
    reused_indicators: frozenset[str]


_INDICATOR_SECTIONS = {
    "rsi": "momentum",
    "macd": "momentum",
    "kd": "momentum",
    "bollinger": "volatility",
    "sar": "volatility",
    "tsf": "trend",
    "ma": "trend",
}

_INDICATOR_COLUMNS: dict[
    str,
    tuple[tuple[str, ...], dict[str, str]],
] = {
    "rsi": (("RSI",), {}),
    # 重用與重新計算必須提供同一計分器別名，原缺值與既有別名優先序不變。
    "macd": (("MACD", "MACD_signal", "MACD_hist"), {"MACD_Signal": "MACD_signal"}),
    "kd": (("slowk", "slowd"), {"SlowK": "slowk", "SlowD": "slowd"}),
    "bollinger": (
        ("upperband", "middleband", "lowerband"),
        {
            "BB_Upper": "upperband",
            "BB_Middle": "middleband",
            "BB_Lower": "lowerband",
        },
    ),
    "sar": (("SAR",), {}),
    "tsf": (("TSF",), {}),
    "ma": (("MA5", "MA10", "MA20", "MA60"), {}),
}


def _is_enabled(
    section_config: dict[str, Any],
    indicator_name: str,
    *,
    legacy_defaults_enabled: bool,
) -> bool:
    raw = section_config.get(indicator_name)
    if raw is None:
        return legacy_defaults_enabled
    if isinstance(raw, dict):
        return bool(raw.get("enabled", True))
    return raw is True


def _indicator_params(section_config: dict[str, Any], indicator_name: str) -> dict[str, Any]:
    raw = section_config.get(indicator_name)
    if isinstance(raw, dict):
        return {key: value for key, value in raw.items() if key != "enabled"}
    return {}


def _columns_are_reusable(frame: pd.DataFrame, required_columns: tuple[str, ...], *, preserve_unknown: bool = False) -> bool:
    for column in required_columns:
        if column not in frame.columns:
            return False
        numeric = pd.to_numeric(frame[column], errors="coerce")
        if not preserve_unknown and not bool(numeric.notna().any()):
            return False
    return True


def _disable_indicator(config: dict[str, Any], section_name: str, indicator_name: str) -> None:
    section = config.setdefault(section_name, {})
    raw = section.get(indicator_name)
    indicator = dict(raw) if isinstance(raw, dict) else {}
    indicator["enabled"] = False
    section[indicator_name] = indicator


def prepare_indicator_reuse(
    frame: pd.DataFrame,
    technical_config: dict[str, Any] | None,
    full_config: dict[str, Any] | None,
) -> IndicatorReusePlan:
    """驗證參數並關閉可由既存預設欄位安全供應的個別指標計算。"""

    config: dict[str, Any] = deepcopy(technical_config or {})
    result_frame = frame.copy()
    schema_version = IndicatorParameterRegistry.get_config_schema_version(full_config)
    defaults = IndicatorParameterRegistry.get_default_config()
    reused: set[str] = set()

    for indicator_name, section_name in _INDICATOR_SECTIONS.items():
        raw_section = config.get(section_name, {})
        if not isinstance(raw_section, dict) or not raw_section.get("enabled", False):
            continue
        if not _is_enabled(
            raw_section,
            indicator_name,
            legacy_defaults_enabled=schema_version < 1,
        ):
            continue

        params = _indicator_params(raw_section, indicator_name)
        sanitized = IndicatorParameterRegistry.validate_and_sanitize(
            indicator_name,
            params,
            full_config,
        )
        required_columns, aliases = _INDICATOR_COLUMNS[indicator_name]
        if sanitized != defaults[indicator_name]:
            continue
        # 因果缺值版不能因「後日才出現首個值」而改變整段的重算／重用選擇。
        preserve_unknown = isinstance(full_config, dict) and full_config.get("input_preparation_policy") == "causal-score-input.v1"
        if not _columns_are_reusable(result_frame, required_columns, preserve_unknown=preserve_unknown):
            continue

        for alias, source in aliases.items():
            if alias not in result_frame.columns:
                result_frame[alias] = result_frame[source]
        _disable_indicator(config, section_name, indicator_name)
        reused.add(indicator_name)

    return IndicatorReusePlan(
        frame=result_frame,
        technical_config=config,
        reused_indicators=frozenset(reused),
    )
