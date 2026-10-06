"""實際隔離Registry保存／readback；不計算回測或讀正式資料。"""
from dataclasses import asdict, replace
from pathlib import Path
import copy
import pandas as pd
import pytest
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_service import ResearchRunService, ResearchRunIntegrityError
from app_module.saved_strategy_rule_card import load_saved_strategy_rule_card, result_context_sha256
from app_module.strategy_rule_card_readmodel import read_strategy_rule_card
from data_module.config import TWStockConfig
from decision_module.strategies.contracts import StrategySpec


def saved_case(tmp_path, *, mutate=None, kind="single_backtest", benchmark=None):
    spec = StrategySpec("baseline_score_threshold", "1.0", data_version="sha256:" + "d" * 64,
                        config={"params": {"buy_score": 65}})
    meta = ResearchRunMetadataDTO(run_id="fixture-run", run_name="synthetic saved result", run_type=kind,
        strategy_id=spec.strategy_id, strategy_version=spec.strategy_version,
        parameter_contract_version="fixture-params.v1", normalized_params={"buy_score": 65},
        original_input={"raw_params": {"fee_bps": "14.25", "slippage_bps": "5"}},
        universe=["2330"], start_date="2026-01-02", end_date="2026-01-05", data_cutoff_date="2026-01-05",
        data_fingerprint=spec.data_version, payload_hash="sha256:" + "b" * 64,
        capital_cents=1000000, fee_bp_x100=1425, slippage_bp_x100=500,
        execution_price="next-session-open.v2", sizing_mode="fixed_amount",
        benchmark_results=benchmark or {},
        data_manifest={"execution_contract": "next-session-open.v2", "strategy_spec": spec.to_dict()})
    card = read_strategy_rule_card(spec, result_kind="research_forward" if kind == "research_forward" else "historical_backtest")
    meta.data_manifest["rule_card_identity"] = asdict(replace(card.identity, context_sha256=result_context_sha256(meta)))
    if mutate:
        meta = mutate(copy.deepcopy(meta))
    service = ResearchRunService(TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output", profile="test"))
    meta = service.save_run(meta, pd.DataFrame({"date": ["2026-01-05"], "value_cents": [1000000]}),
                            pd.DataFrame({"date": [], "quantity": []}))
    return service, meta


def inventory(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


def test_actual_saved_readback_binds_source_without_performance_credit(tmp_path, monkeypatch):
    service, meta = saved_case(tmp_path)
    before = inventory(tmp_path)
    monkeypatch.setattr("decision_module.strategies.registry.StrategyRegistry.get_executor", lambda *_: pytest.fail("executor"))
    result = load_saved_strategy_rule_card(service, meta)
    assert result.source_status == "source_ref_only"
    assert result.result_ref == "research-run:fixture-run"
    assert result.origin["costs"] == {"fee_bp_x100": 1425, "slippage_bp_x100": 500}
    assert result.origin["benchmark"] is None
    assert result.result_kind == "historical_backtest"
    assert result.performance_status == result.rule_card.performance_status == "not_evaluable"
    assert inventory(tmp_path) == before
    detached = result.origin
    detached["universe"].append("9999")
    assert result.origin["universe"] == ["2330"]


@pytest.mark.parametrize("change,reason", [
    ({"strategy_version": "2.0"}, "saved_strategy_identity_mismatch"),
    ({"start_date": "invalid"}, "result_date_invalid"),
    ({"end_date": "2026-01-04"}, "saved_rule_pin_mismatch"),
    ({"start_date": "2026-01-06"}, "result_window_invalid"),
    ({"data_cutoff_date": "2026-01-04"}, "result_window_invalid"),
    ({"data_fingerprint": "sha256:" + "e" * 64}, "spec_data_source_unbound"),
    ({"normalized_params": {"buy_score": 66}}, "saved_strategy_identity_mismatch"),
    ({"fee_bp_x100": 1400}, "cost_value_mismatch"),
    ({"fee_bp_x100": 1425.5}, "cost_type_invalid"),
    ({"universe": ["2382"]}, "saved_rule_pin_mismatch"),
    ({"universe": []}, "result_universe_missing"),
    ({"run_type": "live"}, "result_kind_unbound"),
])
def test_saved_mismatch_refuses_rule_link(tmp_path, change, reason):
    service, meta = saved_case(tmp_path, mutate=lambda m: replace(m, **change))
    result = load_saved_strategy_rule_card(service, meta)
    assert result.source_status == "not_evaluable" and result.result_ref is None
    assert reason in result.reasons
    assert result.performance_status == "not_evaluable"


def test_missing_cost_and_benchmark_stay_unknown_not_defaults(tmp_path):
    service, meta = saved_case(tmp_path, mutate=lambda m: replace(m, original_input={}))
    result = load_saved_strategy_rule_card(service, meta)
    assert result.origin["costs"] is None and result.origin["benchmark"] is None
    assert "cost_source_missing" in result.reasons
    assert result.result_ref is None


def test_legacy_source_never_borrows_current_spec_or_rule_pin(tmp_path):
    service, meta = saved_case(tmp_path, mutate=lambda m: replace(m, strategy_version="unknown", data_manifest={"execution_contract": "next-session-open.v2"}))
    result = load_saved_strategy_rule_card(service, meta)
    assert "saved_strategy_spec_missing" in result.reasons
    assert "saved_rule_pin_missing" in result.reasons
    assert "saved_strategy_version_missing" in result.reasons
    assert result.rule_card.identity.rule_version == "unknown"
    assert result.result_ref is None


def test_selection_source_revision_is_rejected_even_with_original_pin(tmp_path):
    service, meta = saved_case(tmp_path)
    result = load_saved_strategy_rule_card(service, replace(meta, end_date="2026-01-04"))
    assert "selected_source_changed" in result.reasons and result.result_ref is None


def test_forward_kind_remains_research_and_cannot_take_historical_pin(tmp_path):
    service, meta = saved_case(tmp_path, kind="research_forward")
    result = load_saved_strategy_rule_card(service, meta)
    assert result.source_status == "source_ref_only" and result.result_kind == "research_forward"
    wrong = copy.deepcopy(meta)
    wrong.data_manifest["rule_card_identity"]["result_kind"] = "historical_backtest"
    class ChangedReader:
        def load_run_data(self, run_id):
            return replace(service.load_run_data(run_id), metadata=wrong)
    result = load_saved_strategy_rule_card(ChangedReader(), wrong)
    assert "saved_rule_pin_mismatch" in result.reasons and result.result_ref is None


def test_parquet_tamper_rejected_by_existing_verified_reader(tmp_path):
    service, meta = saved_case(tmp_path)
    path = Path(meta.equity_path)
    path.write_bytes(path.read_bytes() + b"fixture tamper")
    with pytest.raises(ResearchRunIntegrityError):
        load_saved_strategy_rule_card(service, meta)
