"""規則卡的唯讀／缺件／版本／模式契約，不使用正式資料。"""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app_module.daily_market_feature_snapshot import DailyMarketFeatureSnapshotService
from app_module.stock_research_report_dtos import (
    StockMetricDTO, StockPricePointDTO, StockTechnicalSnapshotDTO,
)
from app_module.strategy_rule_card_readmodel import (
    RuleCardResultReference, bind_result_reference, read_daily_method_rule_card,
    read_profile_rule_card, read_strategy_rule_card,
)
from app_module.strategy_version_service import StrategyVersion
from app_module.recommendation_profile_service import RecommendationProfile
from decision_module.strategies.contracts import StrategySpec


def snapshot(*, ma=Decimal("99"), count=60):
    points = tuple(StockPricePointDTO(
        data_date=(date(2026, 1, 1) + timedelta(days=i)).isoformat(),
        open_price=Decimal("100"), high_price=Decimal("101"),
        low_price=Decimal("99"), close_price=Decimal("100"),
        volume=1000, turnover=Decimal("100000"), change=Decimal("0"),
        available_at="2026-10-05T16:00:00+08:00", source_id="synthetic.price",
        source_snapshot_hash=f"fixture-{i}", quality="observed",
    ) for i in range(count))
    day = points[-1].data_date
    technical = StockTechnicalSnapshotDTO(
        data_date=day,
        indicators=tuple(StockMetricDTO(key=key, label=key, value=ma,
                                        unit="TWD/share", data_as_of=day,
                                        source_id="synthetic.technical", quality="observed")
                         for key in ("MA20", "MA60")),
        source_id="synthetic.technical", quality="observed",
    )
    return DailyMarketFeatureSnapshotService().project(
        "2382", date.fromisoformat(day), "synthetic.cohort", points, technical)


def test_existing_method_projects_actual_service_result_without_trading_credit():
    original = snapshot()
    before = original.to_dict()
    card = read_daily_method_rule_card("close_above_ma20", snapshot=original)
    assert card.identity.rule_id == "daily_market.close_above_ma20"
    assert card.identity.rule_version == "1.0.0"
    assert card.field("parameters").value == {"window": 20, "direction": "above"}
    assert card.field("required_features").value == ["close", "MA20"]
    assert card.observation_qualification == "eligible_observation_only"
    assert card.to_dict()["observation"]["state"] == "match"
    assert card.field("qualification").value["historical_pit_eligible"] is False
    assert card.rule_status == card.performance_status == "not_evaluable"
    assert {"exit", "cost", "benchmark", "earliest_execution"} <= set(card.missing)
    assert original.to_dict() == before


@pytest.mark.parametrize("ma,relation,state", [
    (Decimal("100"), "equal", "no_match"),
    (Decimal("101"), "below", "no_match"),
])
def test_tie_and_nonmatch_are_eligible_observations(ma, relation, state):
    card = read_daily_method_rule_card("close_above_ma20", snapshot=snapshot(ma=ma))
    assert card.observation_qualification == "eligible_observation_only"
    assert card.to_dict()["observation"]["relation"] == relation
    assert card.to_dict()["observation"]["state"] == state


@pytest.mark.parametrize("count", [1, 19])
def test_warmup_missing_is_not_negative_result(count):
    card = read_daily_method_rule_card("close_above_ma20", snapshot=snapshot(count=count))
    assert card.observation_qualification == "not_evaluable"
    assert "condition_unknown" in card.reasons
    assert card.field("data_insufficiency").value == "insufficient_valid_ohlc_streak"
    assert card.to_dict()["observation"] is None


def test_unknown_method_and_no_snapshot_have_precise_missing():
    card = read_daily_method_rule_card("invented_sell_strategy")
    assert "method_contract_missing" in card.reasons
    assert card.observation_qualification == "not_evaluable"
    known = read_daily_method_rule_card("close_above_ma60")
    assert known.field("parameters").value["window"] == 60
    assert {"universe", "period", "cost", "exit", "qualification"} <= set(known.missing)


@pytest.mark.parametrize("patch,reason", [
    ({"market_date": "2026-12-01"}, "future_data_date"),
    ({"market_date": "2026-02-30"}, "data_date_invalid"),
    ({"market_date": "20260105"}, "condition_contract_mismatch"),
    ({"method_contracts_sha256": "a" * 64}, "snapshot_method_hash_mismatch"),
    ({"snapshot_identity_sha256": ""}, "snapshot_source_identity_missing"),
    ({"scope_identity": ""}, "snapshot_scope_missing"),
])
def test_snapshot_corruption_fails_closed(patch, reason):
    card = read_daily_method_rule_card("close_above_ma20", snapshot=replace(snapshot(), **patch))
    assert reason in card.reasons
    assert card.observation_qualification == "not_evaluable"


@pytest.mark.parametrize("patch", [
    {"version": "2.0"}, {"decision_date": "2025-01-01"},
    {"parameters": (("window", 60), ("direction", "above"))},
    {"method_id": "daily_market.close_above_ma60"},
    {"family": "invented"},
])
def test_mixed_condition_identity_is_rejected(patch):
    s = snapshot()
    condition = replace(s.conditions[0], **patch)
    card = read_daily_method_rule_card("close_above_ma20",
                                      snapshot=replace(s, conditions=(condition, s.conditions[1])))
    assert "condition_contract_mismatch" in card.reasons
    assert card.observation_qualification == "not_evaluable"


def test_missing_duplicate_and_contradictory_conditions_are_rejected():
    s = snapshot(ma=Decimal("100"))
    for conditions, reason in [
        ((), "condition_missing_or_duplicate"),
        ((s.conditions[0], s.conditions[0]), "condition_missing_or_duplicate"),
        ((replace(s.conditions[0], state="match"),), "condition_state_invalid"),
        ((replace(s.conditions[0], close_value=Decimal("123")),), "condition_feature_mismatch"),
    ]:
        card = read_daily_method_rule_card("close_above_ma20", snapshot=replace(s, conditions=conditions))
        assert reason in card.reasons
        assert card.observation_qualification == "not_evaluable"


def test_required_features_cannot_disappear_under_eligible_flag():
    s = snapshot()
    card = read_daily_method_rule_card("close_above_ma20", snapshot=replace(s, features=()))
    assert "required_feature_missing_or_duplicate:close" in card.reasons
    assert card.observation_qualification == "not_evaluable"


@pytest.mark.parametrize("kind", ["historical_backtest", "research_forward", "paper", "unknown"])
def test_current_snapshot_never_becomes_historical_or_forward(kind):
    card = read_daily_method_rule_card("close_above_ma20", snapshot=snapshot(), result_kind=kind)
    assert "snapshot_result_kind_mismatch" in card.reasons
    assert card.observation_qualification == "not_evaluable"


@pytest.mark.parametrize("change", [
    {"rule_version": "2.0"}, {"source_sha256": "f" * 64},
    {"rule_sha256": "f" * 64}, {"context_sha256": "f" * 64},
    {"result_kind": "research_forward"}, {"result_kind": "historical_backtest"},
])
def test_old_card_cannot_bind_new_version_hash_or_mode(change):
    card = read_daily_method_rule_card("close_above_ma20", snapshot=snapshot())
    result = RuleCardResultReference(replace(card.identity, **change), "saved/result", "e" * 64)
    bound = bind_result_reference(card, result)
    assert bound["status"] == "not_evaluable"
    assert bound["result_ref"] is None
    assert "result_identity_mismatch" in bound["reasons"]


def test_matching_reference_is_not_verified_performance_or_fabricated_cost():
    card = read_daily_method_rule_card("close_above_ma20", snapshot=snapshot())
    bound = bind_result_reference(card, RuleCardResultReference(card.identity, "saved/result", "e" * 64))
    assert bound["status"] == "source_ref_only"
    assert bound["performance_status"] == "not_evaluable"
    assert "metrics" not in bound
    assert card.field("cost").value is None
    assert card.field("benchmark").value is None


@pytest.mark.parametrize("ref,hash_value", [("", "e" * 64), ("saved/result", "invalid")])
def test_result_source_missing_is_not_evaluable(ref, hash_value):
    card = read_daily_method_rule_card("close_above_ma20")
    bound = bind_result_reference(card, RuleCardResultReference(card.identity, ref, hash_value))
    assert bound["status"] == "not_evaluable"
    assert "result_source_missing" in bound["reasons"]


def test_registry_metadata_projection_never_guesses_from_strategy_name(monkeypatch):
    spec = StrategySpec("baseline_score_threshold", "1.0", config={"params": {"buy_score": 65}})
    monkeypatch.setattr("decision_module.strategies.registry.StrategyRegistry.get_executor",
                        lambda *_: pytest.fail("不可建立執行器"))
    card = read_strategy_rule_card(spec)
    assert card.field("name").value == "基準分數門檻策略"
    assert card.field("parameters").value == {"buy_score": 65}
    assert card.field("parameter_schema").value["sell_score"]["default"] == 40
    assert card.field("exit").value is None
    assert card.field("entry").value is None
    assert card.performance_status == "not_evaluable"
    spec.config["params"]["buy_score"] = 99
    assert card.field("parameters").value["buy_score"] == 65


def test_strategy_version_mismatch_and_declared_validation_are_separate():
    spec = StrategySpec("baseline_score_threshold", "1.0", config={"params": {"buy_score": 65}})
    version = StrategyVersion("v1", spec.strategy_id, "1.0", "run1", "2026-01-01",
                              {"buy_score": 65}, spec.config, {"win_rate": "0.99"}, [],
                              validation_status="validated")
    card = read_strategy_rule_card(spec, version=version)
    assert card.field("qualification").value["validation_status"] == "validated"
    assert "win_rate" not in str(card.to_dict())
    assert card.performance_status == "not_evaluable"
    bad = read_strategy_rule_card(spec, version=replace(version, strategy_version="2.0"))
    assert "strategy_version_spec_mismatch" in bad.reasons
    unknown = read_strategy_rule_card(StrategySpec("unknown", "1"))
    assert "registry_metadata_missing" in unknown.reasons


def test_parameter_revision_changes_source_pin_and_inconsistent_version_is_rejected():
    spec = StrategySpec("baseline_score_threshold", "1.0", config={"params": {"buy_score": 65}})
    old = read_strategy_rule_card(spec)
    spec.config["params"]["buy_score"] = 66
    new = read_strategy_rule_card(spec)
    assert old.identity.source_sha256 != new.identity.source_sha256
    assert old.identity.rule_sha256 != new.identity.rule_sha256
    bound = bind_result_reference(old, RuleCardResultReference(new.identity, "run/new", "a" * 64))
    assert bound["status"] == "not_evaluable"
    version = StrategyVersion("v1", spec.strategy_id, "1.0", "run1", "2026-01-01",
                              {"buy_score": 65}, spec.config, {}, [])
    assert "strategy_version_params_mismatch" in read_strategy_rule_card(spec, version=version).reasons


def test_registry_version_mismatch_cannot_borrow_current_defaults():
    card = read_strategy_rule_card(StrategySpec("baseline_score_threshold", "2.0"))
    assert "registry_version_mismatch" in card.reasons
    result = RuleCardResultReference(card.identity, "run/fake", "a" * 64)
    assert bind_result_reference(card, result)["result_ref"] is None


def test_source_payload_is_bound_and_old_snapshot_uses_captured_contract(monkeypatch):
    s = snapshot()
    before = read_daily_method_rule_card("close_above_ma20", snapshot=s)
    monkeypatch.setattr("app_module.strategy_rule_card_readmodel.method_contracts_payload",
                        lambda: {"close_above_ma20": {"method_id": "new", "version": "2"}})
    pinned = read_daily_method_rule_card("close_above_ma20", snapshot=s)
    assert pinned.identity == before.identity
    latest = read_daily_method_rule_card("close_above_ma20")
    assert latest.identity != before.identity


def test_context_payload_stock_and_scope_cannot_reuse_result_pin():
    s = snapshot()
    old = read_daily_method_rule_card("close_above_ma20", snapshot=s)
    changed = read_daily_method_rule_card("close_above_ma20", snapshot=replace(s, stock_code="2330"))
    assert changed.identity.context_sha256 != old.identity.context_sha256
    assert bind_result_reference(old, RuleCardResultReference(changed.identity, "saved/new", "b" * 64))["status"] == "not_evaluable"
    assert old.field("source_trace").value["snapshot_identity_sha256"] == s.snapshot_identity_sha256


def test_fabricated_relation_and_unknown_features_never_gain_eligibility():
    s = snapshot()
    forged = replace(s.conditions[0], relation="equal", state="no_match")
    card = read_daily_method_rule_card("close_above_ma20", snapshot=replace(s, conditions=(forged,)))
    assert "condition_relation_mismatch" in card.reasons
    unknown = replace(s.features[0], state="unknown")
    card = read_daily_method_rule_card("close_above_ma20", snapshot=replace(s, features=(unknown, *s.features[1:])))
    assert "required_feature_unknown:close" in card.reasons
    assert card.observation_qualification == "not_evaluable"


def test_card_export_and_profile_config_are_detached():
    profile = RecommendationProfile("p", "builtin", "勝率百分百", "1", "風格", {"filters": {}})
    card = read_profile_rule_card(profile)
    assert "profile_execution_contract_unbound" in card.reasons
    assert {"entry", "exit", "cost", "benchmark"} <= set(card.missing)
    exported = card.to_dict()
    exported["fields"]["parameters"]["value"]["filters"]["new"] = True
    assert card.field("parameters").value == {"filters": {}}
    profile.config["filters"]["new"] = True
    assert card.field("parameters").value == {"filters": {}}


def test_invalid_source_payload_fails_closed_instead_of_hashing_a_placeholder():
    spec = StrategySpec("baseline_score_threshold", "1.0", config={"params": {"invalid": object()}})
    card = read_strategy_rule_card(spec)
    assert card.field("parameters").missing_reason == "source_contract_value_invalid"
    assert card.identity.source_sha256 == ""
    assert "source_hash_missing_or_invalid" in card.reasons
    assert card.performance_status == "not_evaluable"
