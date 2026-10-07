from __future__ import annotations

import json

import pytest

from app_module.daily_market_technical_method_contract_v4 import (
    DAILY_MARKET_TECHNICAL_FEATURE_KEYS_V4,
    DAILY_MARKET_TECHNICAL_RULE_KEYS_V4,
    canonical_daily_market_technical_method_contract_v4_json,
    daily_market_technical_method_contract_v4_payload,
    daily_market_technical_method_contract_v4_sha256,
    parse_daily_market_technical_method_contract_v4,
    validate_daily_market_technical_method_contract_v4,
)


def test_v4_method_contract_fixes_feature_rules_parameters_and_units() -> None:
    payload = daily_market_technical_method_contract_v4_payload()

    assert tuple(item["key"] for item in payload["features"]) == DAILY_MARKET_TECHNICAL_FEATURE_KEYS_V4
    assert tuple(item["key"] for item in payload["rules"]) == DAILY_MARKET_TECHNICAL_RULE_KEYS_V4
    assert payload["source"]["availability_status"] == "unknown"
    assert payload["source"]["historical_pit_eligible"] is False
    assert next(item for item in payload["features"] if item["key"] == "MACD")["unit"] == "TWD/share"
    assert next(item for item in payload["rules"] if item["key"] == "volume_ratio_20_including_current")["parameters"] == {
        "includes_current_session": "true",
        "threshold_ratio": "1.5",
        "window_sessions": 20,
    }
    assert next(item for item in payload["rules"] if item["key"] == "volume_ratio_5_including_current")["parameters"]["threshold_ratio"] == "2"


def test_v4_contract_payload_is_detached_and_tampering_is_rejected() -> None:
    payload = daily_market_technical_method_contract_v4_payload()
    payload["features"][0]["parameters"]["timeperiod"] = 99

    fresh = daily_market_technical_method_contract_v4_payload()
    assert fresh["features"][0]["parameters"]["timeperiod"] == 5
    with pytest.raises(ValueError, match="technical_method_contract_v4_mismatch"):
        validate_daily_market_technical_method_contract_v4(payload)


def test_v4_contract_roundtrips_only_canonical_json_and_expected_hash() -> None:
    payload = daily_market_technical_method_contract_v4_payload()
    encoded = canonical_daily_market_technical_method_contract_v4_json(payload)

    parsed = parse_daily_market_technical_method_contract_v4(encoded)

    assert parsed == daily_market_technical_method_contract_v4_payload()
    assert daily_market_technical_method_contract_v4_sha256(parsed) == daily_market_technical_method_contract_v4_sha256()
    with pytest.raises(ValueError, match="technical_method_contract_v4_noncanonical"):
        parse_daily_market_technical_method_contract_v4(json.dumps(payload, ensure_ascii=False))
    with pytest.raises(ValueError, match="technical_method_contract_v4_hash_mismatch"):
        validate_daily_market_technical_method_contract_v4(
            parsed,
            expected_sha256="0" * 64,
        )


def test_v4_contract_parser_rejects_duplicate_json_keys() -> None:
    with pytest.raises(ValueError, match="technical_method_contract_v4_invalid_json"):
        parse_daily_market_technical_method_contract_v4('{"a":1,"a":1}')
