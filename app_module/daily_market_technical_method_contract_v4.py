"""P02 首批技術條件的固定 v4 方法契約。"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from collections.abc import Mapping
from typing import Any, NoReturn

from app_module.daily_market_technical_source import (
    DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
    DAILY_MARKET_TECHNICAL_SOURCE_SCHEMA,
)
from decision_module.factors.selection_technical_rules import (
    CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
    CAUSAL_INDICATOR_LINEAGE_VERSION,
    KD_CROSS_METHOD_ID,
    MACD_CROSS_METHOD_ID,
    MA5_20_CROSS_METHOD_ID,
    PRICE_UNIT,
    RAW_VOLUME_LINEAGE_METHOD_ID,
    RAW_VOLUME_LINEAGE_VERSION,
    SELECTION_TECHNICAL_RULE_VERSION,
    STOCH_UNIT,
    TECHNICAL_SOURCE_ID,
    VOLUME_RATIO_20_METHOD_ID,
    VOLUME_RATIO_5_METHOD_ID,
    VOLUME_SOURCE_ID,
    VOLUME_UNIT,
)


DAILY_MARKET_TECHNICAL_METHOD_CONTRACT_SCHEMA_V4 = (
    "daily-market-technical-method-contract.v4"
)
DAILY_MARKET_TECHNICAL_METHOD_CONTRACT_VERSION_V4 = "1.0.0"
DAILY_MARKET_TECHNICAL_RULE_KEYS_V4 = (
    "ma5_20_golden_cross",
    "kd_golden_cross",
    "macd_golden_cross",
    "volume_ratio_20_including_current",
    "volume_ratio_5_including_current",
)
DAILY_MARKET_TECHNICAL_FEATURE_KEYS_V4 = (
    "MA5",
    "MA20",
    "slowk",
    "slowd",
    "MACD",
    "MACD_signal",
    "volume_shares",
)

_FEATURES: tuple[dict[str, Any], ...] = (
    {
        "key": "MA5",
        "source_id": TECHNICAL_SOURCE_ID,
        "method_id": CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
        "method_version": CAUSAL_INDICATOR_LINEAGE_VERSION,
        "unit": PRICE_UNIT,
        "parameters": {"input": "Close", "method": "SMA", "timeperiod": 5},
        "warmup_required_sessions": 5,
    },
    {
        "key": "MA20",
        "source_id": TECHNICAL_SOURCE_ID,
        "method_id": CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
        "method_version": CAUSAL_INDICATOR_LINEAGE_VERSION,
        "unit": PRICE_UNIT,
        "parameters": {"input": "Close", "method": "SMA", "timeperiod": 20},
        "warmup_required_sessions": 20,
    },
    {
        "key": "slowk",
        "source_id": TECHNICAL_SOURCE_ID,
        "method_id": CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
        "method_version": CAUSAL_INDICATOR_LINEAGE_VERSION,
        "unit": STOCH_UNIT,
        "parameters": {
            "fastk_period": 5,
            "slowd_matype": "SMA",
            "slowd_period": 3,
            "slowk_matype": "SMA",
            "slowk_period": 3,
        },
        "warmup_required_sessions": 9,
    },
    {
        "key": "slowd",
        "source_id": TECHNICAL_SOURCE_ID,
        "method_id": CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
        "method_version": CAUSAL_INDICATOR_LINEAGE_VERSION,
        "unit": STOCH_UNIT,
        "parameters": {
            "fastk_period": 5,
            "slowd_matype": "SMA",
            "slowd_period": 3,
            "slowk_matype": "SMA",
            "slowk_period": 3,
        },
        "warmup_required_sessions": 9,
    },
    {
        "key": "MACD",
        "source_id": TECHNICAL_SOURCE_ID,
        "method_id": CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
        "method_version": CAUSAL_INDICATOR_LINEAGE_VERSION,
        "unit": PRICE_UNIT,
        "parameters": {
            "fastperiod": 12,
            "input": "Close",
            "signalperiod": 9,
            "slowperiod": 26,
        },
        "warmup_required_sessions": 34,
    },
    {
        "key": "MACD_signal",
        "source_id": TECHNICAL_SOURCE_ID,
        "method_id": CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
        "method_version": CAUSAL_INDICATOR_LINEAGE_VERSION,
        "unit": PRICE_UNIT,
        "parameters": {
            "fastperiod": 12,
            "input": "Close",
            "signalperiod": 9,
            "slowperiod": 26,
        },
        "warmup_required_sessions": 34,
    },
    {
        "key": "volume_shares",
        "source_id": VOLUME_SOURCE_ID,
        "method_id": RAW_VOLUME_LINEAGE_METHOD_ID,
        "method_version": RAW_VOLUME_LINEAGE_VERSION,
        "unit": VOLUME_UNIT,
        "parameters": {"field": "成交股數", "unit": VOLUME_UNIT},
        "warmup_required_sessions": None,
    },
)

_RULES: tuple[dict[str, Any], ...] = (
    {
        "key": "ma5_20_golden_cross",
        "method_id": MA5_20_CROSS_METHOD_ID,
        "version": SELECTION_TECHNICAL_RULE_VERSION,
        "parameters": {
            "current": "MA5>MA20",
            "previous": "MA5<=MA20",
            "short_window": 5,
            "long_window": 20,
        },
        "required_feature_keys": ["MA5", "MA20"],
    },
    {
        "key": "kd_golden_cross",
        "method_id": KD_CROSS_METHOD_ID,
        "version": SELECTION_TECHNICAL_RULE_VERSION,
        "parameters": {
            "current": "K>D",
            "formula": "STOCH",
            "fastk_period": 5,
            "previous": "K<=D",
            "slowk_matype": "SMA",
            "slowk_period": 3,
            "slowd_matype": "SMA",
            "slowd_period": 3,
        },
        "required_feature_keys": ["slowk", "slowd"],
    },
    {
        "key": "macd_golden_cross",
        "method_id": MACD_CROSS_METHOD_ID,
        "version": SELECTION_TECHNICAL_RULE_VERSION,
        "parameters": {
            "current": "MACD>signal",
            "fastperiod": 12,
            "previous": "MACD<=signal",
            "signalperiod": 9,
            "slowperiod": 26,
        },
        "required_feature_keys": ["MACD", "MACD_signal"],
    },
    {
        "key": "volume_ratio_20_including_current",
        "method_id": VOLUME_RATIO_20_METHOD_ID,
        "version": SELECTION_TECHNICAL_RULE_VERSION,
        "parameters": {
            "includes_current_session": "true",
            "threshold_ratio": "1.5",
            "window_sessions": 20,
        },
        "required_feature_keys": ["volume_shares"],
    },
    {
        "key": "volume_ratio_5_including_current",
        "method_id": VOLUME_RATIO_5_METHOD_ID,
        "version": SELECTION_TECHNICAL_RULE_VERSION,
        "parameters": {
            "includes_current_session": "true",
            "threshold_ratio": "2",
            "window_sessions": 5,
        },
        "required_feature_keys": ["volume_shares"],
    },
)


def daily_market_technical_method_contract_v4_payload() -> dict[str, Any]:
    """回傳五條已實作規則及輸入 feature 的 detached 保存契約。"""

    return {
        "schema_version": DAILY_MARKET_TECHNICAL_METHOD_CONTRACT_SCHEMA_V4,
        "contract_version": DAILY_MARKET_TECHNICAL_METHOD_CONTRACT_VERSION_V4,
        "source": {
            "schema_version": DAILY_MARKET_TECHNICAL_SOURCE_SCHEMA,
            "source_id": "sqlite.daily_prices",
            "technical_source_id": TECHNICAL_SOURCE_ID,
            "volume_source_id": VOLUME_SOURCE_ID,
            "cutoff_guard_version": DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        },
        "features": deepcopy(_FEATURES),
        "rules": deepcopy(_RULES),
    }


def canonical_daily_market_technical_method_contract_v4_json(
    payload: Mapping[str, Any] | None = None,
) -> str:
    """以唯一 JSON 編碼序列化 v4 方法契約。"""

    value = daily_market_technical_method_contract_v4_payload() if payload is None else payload
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def daily_market_technical_method_contract_v4_sha256(
    payload: Mapping[str, Any] | None = None,
) -> str:
    raw = canonical_daily_market_technical_method_contract_v4_json(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_daily_market_technical_method_contract_v4(
    payload: Mapping[str, Any],
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """只接受目前固定契約的精確欄位和值，不作寬鬆升級。"""

    if not isinstance(payload, Mapping):
        raise ValueError("technical_method_contract_v4_invalid")
    try:
        actual_json = canonical_daily_market_technical_method_contract_v4_json(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("technical_method_contract_v4_invalid") from exc
    expected = daily_market_technical_method_contract_v4_payload()
    expected_json = canonical_daily_market_technical_method_contract_v4_json(expected)
    if actual_json != expected_json:
        raise ValueError("technical_method_contract_v4_mismatch")
    digest = hashlib.sha256(actual_json.encode("utf-8")).hexdigest()
    if expected_sha256 is not None and expected_sha256 != digest:
        raise ValueError("technical_method_contract_v4_hash_mismatch")
    return expected


def parse_daily_market_technical_method_contract_v4(raw: bytes | str) -> dict[str, Any]:
    """嚴格解析契約 JSON，拒絕重複鍵、常數與非 UTF-8 bytes。"""

    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("technical_method_contract_v4_invalid_json") from exc
    elif isinstance(raw, str):
        text = raw
    else:
        raise TypeError("raw 必須是 bytes 或 str")
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("technical_method_contract_v4_invalid_json") from exc
    validated = validate_daily_market_technical_method_contract_v4(payload)
    if canonical_daily_market_technical_method_contract_v4_json(validated) != text:
        raise ValueError("technical_method_contract_v4_noncanonical")
    return validated


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"unsupported_json_constant:{value}")
