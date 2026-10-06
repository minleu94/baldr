from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
import hashlib
import json

import pytest

from app_module import rule_research_family_catalog as families
from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_CONDITION_KEYS,
    DAILY_MARKET_FEATURE_CONTRACT_VERSION,
    DAILY_MARKET_FEATURE_KEYS,
)
from app_module.daily_market_method_contract import method_contracts_payload, method_contracts_sha256
from app_module.daily_market_research_capabilities import (
    DAILY_MARKET_RESEARCH_FEATURE_CAPABILITIES,
    DAILY_MARKET_RESEARCH_METHOD_CAPABILITIES,
    DailyMarketResearchCapabilityCatalog,
)


def _old_catalog() -> DailyMarketResearchCapabilityCatalog:
    return DailyMarketResearchCapabilityCatalog(
        DAILY_MARKET_RESEARCH_FEATURE_CAPABILITIES,
        DAILY_MARKET_RESEARCH_METHOD_CAPABILITIES,
    )


def _catalog_hash() -> str:
    encoded = json.dumps(
        _old_catalog().to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_frozen_api_and_original_eight_titles():
    assert tuple(field.name for field in fields(families.RuleResearchFamilyCapability)) == (
        "family_id", "title", "status", "versioned_method_refs", "required_fields",
        "warmup", "missing", "availability", "cost", "source_refs", "blockers",
    )
    catalog = families.list_rule_research_families()
    assert isinstance(catalog, tuple)
    assert tuple(item.title for item in catalog) == (
        "原價量排名", "趨勢轉強", "布林壓縮突破", "波動收斂",
        "型態確認", "籌碼轉強", "基本面動能", "產業領先",
    )
    assert len({item.family_id for item in catalog}) == 8
    assert _old_catalog().families == catalog
    for item in catalog:
        assert families.get_rule_research_family(item.family_id) is item
        assert item.blockers
        assert not item.availability["historical_pit_eligible"]
        assert item.cost["measured_runtime_memory_or_bytes"] == "unknown"
        assert item.missing["unknown_is_preserved"]


def test_nested_immutable_and_detached_serialization():
    family = families.get_rule_research_family("bollinger_compression_breakout")
    with pytest.raises(FrozenInstanceError):
        family.status = "partial"  # type: ignore[misc]
    with pytest.raises(TypeError):
        family.warmup["state"] = "ready"  # type: ignore[index]
    with pytest.raises(TypeError):
        family.warmup["parameters"]["timeperiod"] = 20
    payload = family.to_dict()
    payload["warmup"]["parameters"]["timeperiod"] = 20
    payload["blockers"].clear()
    payload["required_fields"].append("fake")
    assert family.to_dict()["warmup"]["parameters"]["timeperiod"] == 30
    assert family.blockers
    assert "fake" not in family.required_fields
    json.dumps(family.to_dict(), allow_nan=False)


def test_constructor_detaches_caller_owned_nested_values():
    original = families.list_rule_research_families()[0]
    warmup = {"nested": {"windows": [20, 60]}}
    custom = replace(original, warmup=warmup)
    warmup["nested"]["windows"].append(99)
    assert custom.to_dict()["warmup"] == {"nested": {"windows": [20, 60]}}


def test_constructor_rejects_non_json_mutable_metadata():
    original = families.list_rule_research_families()[0]
    with pytest.raises(TypeError):
        replace(original, warmup={"windows": {20, 60}})
    with pytest.raises(TypeError):
        replace(original, required_fields=(["close"],))  # type: ignore[arg-type]


@pytest.mark.parametrize("key", ["", "close_vs_moving_average ", "CLOSE_VS_MOVING_AVERAGE", "趨勢轉強", "future_family"])
def test_unknown_exact_lookup_preserves_missing_and_never_supported(key):
    unknown = families.get_rule_research_family(key)
    assert unknown.family_id == key
    assert unknown.status == "unknown"
    assert unknown.versioned_method_refs == ()
    assert unknown.required_fields == ()
    assert unknown.source_refs == ()
    assert unknown.missing["state"] == "unknown"
    assert unknown.missing["fallback"] == "none"
    assert unknown.warmup["window"] is None
    assert unknown.blockers == ("unknown_family_id",)


def test_only_two_existing_versioned_methods_share_one_family():
    contracts = method_contracts_payload()
    family = families.get_rule_research_family("close_vs_moving_average")
    assert family.versioned_method_refs == (
        "daily_market.close_above_ma20@1.0.0", "daily_market.close_above_ma60@1.0.0",
    )
    assert {contract["family"] for contract in contracts.values()} == {family.family_id}
    upper = families.get_rule_research_family("bollinger_compression_breakout")
    assert upper.versioned_method_refs == ("daily_market.close_above_bbands30_upper@1.0.0",)
    assert all(not item.versioned_method_refs for item in families.list_rule_research_families()
               if item.family_id not in (family.family_id, upper.family_id))


def test_bollinger_candidate_is_not_a_saved_or_enabled_compression_method():
    family = families.get_rule_research_family("bollinger_compression_breakout")
    assert family.status == "partial"
    assert family.versioned_method_refs == ("daily_market.close_above_bbands30_upper@1.0.0",)
    assert family.warmup["required_observation_count"] == 30
    assert family.warmup["parameters"] == {"timeperiod": 30, "nbdevup": "2.0", "nbdevdn": "2.0", "matype": "SMA"}
    assert family.warmup["compression_threshold"] is None
    assert family.warmup["compression_window"] is None
    assert {"upperband", "middleband", "lowerband"}.issubset(family.required_fields)
    assert "upperband" not in DAILY_MARKET_FEATURE_KEYS
    assert "未啟用" in "".join(family.blockers)


def test_old_capabilities_and_v2_method_hash_are_unchanged():
    assert DAILY_MARKET_FEATURE_KEYS == ("close", "MA20", "MA60")
    assert DAILY_MARKET_CONDITION_KEYS == ("close_above_ma20", "close_above_ma60")
    assert DAILY_MARKET_FEATURE_CONTRACT_VERSION == "daily-market-feature-snapshot.v2"
    assert method_contracts_sha256() == "029bcb5ada592619d9748d327eef509db0642a1c6904b652b31f186027025dc5"
    assert _catalog_hash() == "eb93750012c5c7de223cc01ece2a017848d88812a751361883d9a66404ef880e"


def test_future_family_append_does_not_mutate_old_contracts_or_capabilities(monkeypatch):
    before = tuple(item.to_dict() for item in families.list_rule_research_families())
    method_hash = method_contracts_sha256()
    catalog_hash = _catalog_hash()
    future = replace(families.get_rule_research_family("future_family"), title="未來家族")
    monkeypatch.setattr(families, "_FAMILIES", families.list_rule_research_families() + (future,))
    assert _old_catalog().families[-1] is future
    assert tuple(item.to_dict() for item in families.list_rule_research_families()[:-1]) == before
    assert method_contracts_sha256() == method_hash
    assert _catalog_hash() == catalog_hash


def test_future_contract_append_does_not_silently_enable_new_method(monkeypatch):
    contracts = method_contracts_payload()
    contracts["future_ma"] = {
        "method_id": "future", "version": "9", "family": "close_vs_moving_average",
    }
    monkeypatch.setattr(families, "method_contracts_payload", lambda: contracts)
    rebuilt = families._build_catalog()
    assert rebuilt[1].versioned_method_refs == families.list_rule_research_families()[1].versioned_method_refs
