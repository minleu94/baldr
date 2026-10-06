"""既有 close／均線研究觀察的固定方法契約。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any


_METHOD_CONTRACTS: dict[str, dict[str, Any]] = {
    "close_above_ma20": {
        "method_id": "daily_market.close_above_ma20",
        "family": "close_vs_moving_average",
        "version": "1.0.0",
        "parameters": {"window": 20, "direction": "above"},
        "required_fields": ["close", "MA20"],
    },
    "close_above_ma60": {
        "method_id": "daily_market.close_above_ma60",
        "family": "close_vs_moving_average",
        "version": "1.0.0",
        "parameters": {"window": 60, "direction": "above"},
        "required_fields": ["close", "MA60"],
    },
}

_BBANDS30_UPPER_METHOD_CONTRACT: dict[str, Any] = {
    "method_id": "daily_market.close_above_bbands30_upper",
    "family": "close_vs_bollinger_upper",
    "version": "1.0.0",
    "parameters": {
        "timeperiod": 30,
        "nbdevup": "2.0",
        "nbdevdn": "2.0",
        "matype": "SMA",
        "direction": "above",
    },
    "required_fields": ["close", "BB_Upper"],
}


def method_contracts_payload(
    *, include_bbands30_upper: bool = False
) -> dict[str, dict[str, Any]]:
    """回傳所選研究版本的 detached canonical payload。"""

    if not isinstance(include_bbands30_upper, bool):
        raise TypeError("include_bbands30_upper 必須是 bool")
    payload = deepcopy(_METHOD_CONTRACTS)
    if include_bbands30_upper:
        payload["close_above_bbands30_upper"] = deepcopy(
            _BBANDS30_UPPER_METHOD_CONTRACT
        )
    return payload


def method_contracts_canonical_json(
    payload: Mapping[str, Any] | None = None,
) -> str:
    """以固定 JSON 規則序列化方法契約，供 hash 與 snapshot capture 共用。"""

    contracts = method_contracts_payload() if payload is None else payload
    return json.dumps(
        contracts,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def method_contracts_sha256(
    payload: Mapping[str, Any] | None = None,
) -> str:
    """回傳 canonical 方法契約 payload 的 SHA256。"""

    encoded = method_contracts_canonical_json(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
