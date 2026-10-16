"""沿真Registry與版本服務讀回；不升級資格、不碰正式資料。"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import json

import pytest

from app_module.research_history_lookup import ResearchHistoryLookup, ResearchHistoryReadBudget
from app_module.saved_strategy_version_reader import SavedStrategyVersionReader
from app_module.saved_strategy_rule_card import metadata_sha256
from app_module.strategy_version_service import StrategyVersionService
from app_module.research_run_service import ResearchRunReadCancelledError
from decision_module.strategies.registry import StrategyRegistry
from tests.test_saved_strategy_rule_card import inventory, saved_case
from tests.test_single_backtest_rule_execution_v2 import executed_v2_case


def saved_version_case(tmp_path, *, registry=None, metadata=None, config=None):
    if registry is None:
        registry, metadata = saved_case(tmp_path)
        config = registry.config
    versions = StrategyVersionService(config)
    version_id = versions.create_version(
        version_id="version_saved_01", strategy_id=metadata.strategy_id,
        strategy_version="1.9.3", source_run_id=metadata.run_id,
        params=deepcopy(metadata.normalized_params),
        config={"source": "research_run_registry", "run_type": metadata.run_type,
                "parameter_contract_version": metadata.parameter_contract_version,
                "data_fingerprint": metadata.data_fingerprint,
                "execution_price": metadata.execution_price, "sizing_mode": metadata.sizing_mode},
        validation_status="pending", notes="隔離研究fixture，未執行promotion",
    )
    lookup = ResearchHistoryLookup(registry=registry,
        read_budget=ResearchHistoryReadBudget(64 * 1024 * 1024, 256 * 1024 * 1024))
    return SavedStrategyVersionReader(versions, lookup), versions, registry, metadata, version_id


@pytest.mark.parametrize("strategy_id", ("stable_conservative_v1", "momentum_aggressive_v1"))
def test_saved_lifecycle_version_and_original_executor_version_remain_distinct(tmp_path, monkeypatch, strategy_id):
    config, registry, metadata, _, _, _ = executed_v2_case(tmp_path, monkeypatch, strategy_id)
    reader, _, _, _, _ = saved_version_case(tmp_path, registry=registry, metadata=metadata, config=config)
    before = inventory(tmp_path)
    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", lambda *_: pytest.fail("不能用current registry替歷史"))
    monkeypatch.setattr(StrategyRegistry, "get_executor", lambda *_: pytest.fail("不能重算"))
    page = reader.list_versions()
    assert len(page.entries) == page.total_catalog_count == 1 and not page.diagnostics
    selected = page.entries[0]
    assert selected.strategy_version == "1.9.3"
    assert json.loads(selected.source_entry.metadata_json)["strategy_version"] == "1.0.0"
    assert selected.validation_status == "pending"
    result = reader.read_source(selected)
    assert result.rule_card.rule_card.rule_status == "execution_contract_bound"
    assert result.rule_card.source_status == "source_ref_only"
    assert result.rule_card.performance_status == "not_evaluable"
    assert metadata_sha256(result.history_result.result.metadata) == metadata_sha256(metadata)
    assert inventory(tmp_path) == before


def test_version_mutation_between_select_and_read_refused(tmp_path):
    reader, versions, _, _, version_id = saved_version_case(tmp_path)
    selected = reader.list_versions().entries[0]
    versions.update_version(version_id, notes="選取後改版")
    with pytest.raises(ValueError, match="saved_strategy_version_changed"):
        reader.read_source(selected)


def test_source_metadata_change_after_select_refused_without_latest_fallback(tmp_path):
    reader, _, registry, metadata, _ = saved_version_case(tmp_path)
    selected = reader.list_versions().entries[0]
    registry.repository.archive_run(metadata.run_id)
    with pytest.raises(ValueError, match="selected_source_changed"):
        reader.read_source(selected)


def test_version_mutation_during_source_read_refused(tmp_path, monkeypatch):
    reader, versions, _, _, version_id = saved_version_case(tmp_path)
    selected = reader.list_versions().entries[0]
    original = reader.lookup.resolve
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        versions.update_version(version_id, notes="讀回中改版")
        return result
    monkeypatch.setattr(reader.lookup, "resolve", changed)
    with pytest.raises(ValueError, match="saved_strategy_version_changed"):
        reader.read_source(selected)


@pytest.mark.parametrize("mutation,reason", (
    ({"strategy_id": "other"}, "source_mismatch"),
    ({"params": {"buy_score": 66}}, "source_mismatch"),
    ({"config": {"source": "legacy_backtest"}}, "source_kind_unsupported"),
    ({"validation_metrics": {"data_fingerprint": "sha256:" + "e" * 64}}, "validation_source_mismatch"),
))
def test_conflicting_saved_declaration_listed_but_not_opened(tmp_path, mutation, reason):
    reader, versions, _, _, version_id = saved_version_case(tmp_path)
    versions.update_version(version_id, **mutation)
    before = inventory(tmp_path)
    entry = reader.list_versions().entries[0]
    assert entry.source_entry is None and reason in entry.diagnostics[0]
    with pytest.raises(ValueError, match="source_unavailable"):
        reader.read_source(entry)
    assert inventory(tmp_path) == before


def test_conflicting_registry_backlink_not_treated_as_selected_promotion(tmp_path):
    reader, _, registry, metadata, _ = saved_version_case(tmp_path)
    registry.repository.mark_promoted(metadata.run_id, "another_version")
    entry = reader.list_versions().entries[0]
    assert entry.source_entry is None and "source_backlink_mismatch" in entry.diagnostics[0]


def test_selection_fields_cannot_override_snapshot_identity(tmp_path):
    reader, _, _, _, _ = saved_version_case(tmp_path)
    entry = reader.list_versions().entries[0]
    with pytest.raises(ValueError, match="selection_mismatch"):
        reader.read_source(replace(entry, strategy_version="forged"))


def test_absent_service_cancellation_and_limits_do_not_create_storage(tmp_path):
    lookup = ResearchHistoryLookup()
    reader = SavedStrategyVersionReader(None, lookup)
    before = inventory(tmp_path)
    assert reader.list_versions().diagnostics == ("saved_strategy_version_service_unavailable",)
    with pytest.raises(ValueError, match="cancelled"):
        reader.list_versions(check_cancel=lambda: True)
    with pytest.raises(ValueError, match="limit_invalid"):
        reader.list_versions(limit=True)
    assert inventory(tmp_path) == before


def test_exact_registry_selection_is_not_limited_to_recent_catalog(tmp_path, monkeypatch):
    reader, _, _, metadata, _ = saved_version_case(tmp_path)
    monkeypatch.setattr(reader.lookup, "list_entries", lambda **_: pytest.fail("不能掃近期清單代替exact來源"))
    selected = reader.list_versions().entries[0]
    assert selected.source_entry.run_id == metadata.run_id
    assert reader.read_source(selected).history_result.entry == selected.source_entry


def test_metadata_only_source_is_listed_without_openable_history(tmp_path):
    registry, metadata = saved_case(tmp_path, kind="research_forward")
    reader, _, _, _, _ = saved_version_case(tmp_path, registry=registry, metadata=metadata, config=registry.config)
    entry = reader.list_versions().entries[0]
    assert entry.source_entry is None and entry.diagnostics == ("research_forward_metadata_only",)
    with pytest.raises(ValueError, match="source_unavailable"):
        reader.read_source(entry)


def test_catalog_pages_reach_older_saved_version_without_scanning_recent_runs(tmp_path, monkeypatch):
    reader, versions, _, metadata, first_id = saved_version_case(tmp_path)
    original = versions.get_version(first_id)
    class LaterClock:
        @staticmethod
        def now():
            return datetime.fromisoformat(original.promoted_at) + timedelta(seconds=1)
    monkeypatch.setattr("app_module.strategy_version_service.datetime", LaterClock)
    versions.create_version(version_id="version_saved_02", strategy_id=metadata.strategy_id,
        strategy_version="1.9.4", source_run_id=metadata.run_id,
        params=deepcopy(original.params), config=deepcopy(original.config), validation_status="pending")
    first = reader.list_versions(limit=1)
    second = reader.list_versions(limit=1, offset=1)
    assert first.total_catalog_count == second.total_catalog_count == 2
    assert first.offset == 0 and first.entries[0].version_id == "version_saved_02"
    assert second.offset == 1 and second.entries[0].version_id == first_id
    assert reader.read_source(second.entries[0]).history_result.entry.run_id == metadata.run_id
    with pytest.raises(ValueError, match="offset_invalid"):
        reader.list_versions(offset=True)


def test_cancellation_after_history_load_reaches_original_rule_reader(tmp_path, monkeypatch):
    reader, _, _, _, _ = saved_version_case(tmp_path)
    selected = reader.list_versions().entries[0]
    cancelled = False
    original = reader.lookup.resolve
    def cancel_after_load(*args, **kwargs):
        nonlocal cancelled
        result = original(*args, **kwargs)
        cancelled = True
        return result
    monkeypatch.setattr(reader.lookup, "resolve", cancel_after_load)
    before = inventory(tmp_path)
    with pytest.raises(ResearchRunReadCancelledError):
        reader.read_source(selected, check_cancel=lambda: cancelled)
    assert inventory(tmp_path) == before
