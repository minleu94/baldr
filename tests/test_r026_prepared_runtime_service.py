from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from typing import Any, TypedDict

import pandas as pd
import pytest

from app_module.recommendation_service import RecommendationService
from recommendation_test_support import build_recommendation_test_service
from test_recommendation_service_calibration_integration import (
    _core_feature_samples,
    _make_database,
    _verified_candidate,
)
from test_daily_recommendation_learning_loop import _natural_receipt


def test_service_prepared_runtime_default_persists_and_reads_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
    from ml_module.recommendation_calibration_authority import RecommendationCalibrationPromotionAuthority
    import app_module.recommendation_service as service_module
    import app_module.recommendation.prepared_runtime_projector as projector_module
    from ml_module.recommendation_inference_provenance import read_inference_projection_receipt
    from ml_module.recommendation_inference_provenance import (
        RecommendationProvenanceError,
        _hash_payload,
        _source_contract_feature_rows_hash,
        build_inference_projection_receipt,
    )

    class RepositoryConfig(SimpleNamespace):
        def resolve_output_path(self, relative_path: str) -> Path:
            return Path(self.output_root) / relative_path

    registry = CORE_LONG_HISTORY_FEATURE_REGISTRY
    trained, candidate_root, metadata = _verified_candidate(
        tmp_path,
        candidate_day="2026-06-01",
        training_as_of="2026-05-31",
        samples=_core_feature_samples(),
        feature_names=registry.canonical_ids,
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
        dataset_id="dataset-r026-prepared-runtime-e2e",
    )
    evidence = _natural_receipt(
        tmp_path,
        root=candidate_root,
        candidate_day="2026-06-01",
        evaluation_day="2026-07-27",
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
    )
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    decision = authority.evaluate_and_apply(
        decision_date="2026-07-27",
        candidate_id=str(getattr(trained, "candidate_id")),
        candidate_root=candidate_root,
        candidate_metadata=metadata,
        natural_evidence=evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert decision.decision == "adopt"

    database = tmp_path / "source.db"
    _make_database(
        database,
        days=(date(2026, 7, 27) - date(2026, 1, 1)).days + 1,
        start=date(2026, 1, 1),
    )
    market_frame = pd.DataFrame(
        [
            {
                "日期": date(2026, 1, 1) + timedelta(days=offset),
                "證券代號": "AAA",
                "證券名稱": "測試股票",
                "收盤價": 100 + offset,
                "成交股數": 1_000 + offset,
            }
            for offset in range((date(2026, 7, 27) - date(2026, 1, 1)).days + 1)
        ]
    )
    config = RepositoryConfig(
        db_file=database,
        default_start_date="2026-01-01",
        output_root=tmp_path / "output",
        data_root=tmp_path / "formal-data",
        use_sqlite=False,
    )
    consumer = RecommendationCalibrationConsumer(
        pointer_path=tmp_path / "authority" / "recommendation-calibration-active-pointer.json",
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
        data_root=config.data_root,
    )
    service = build_recommendation_test_service(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=lambda: market_frame.copy(),
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
    )
    assert type(service) is RecommendationService
    monkeypatch.setattr(
        service.strategy_configurator,
        "generate_recommendations",
        lambda _stock_df, _config: pd.DataFrame(
            {
                "TotalScore": [80],
                "FinalScore": [80],
                "收盤價": [Decimal("100")],
                "成交股數": [1_000],
            }
        ),
    )

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = datetime(2026, 7, 27, 16, 50, tzinfo=timezone.utc)
            return current.astimezone(tz) if tz is not None else current.replace(tzinfo=None)

    monkeypatch.setattr(service_module, "datetime", FrozenDatetime)
    runtime_inputs: list[Any] = []
    typed_projection_outputs: list[Any] = []
    trap_projector_io = False
    mutate_contract_after_projector: Path | None = None
    project_prepared = projector_module.project_prepared_ml_runtime_input_v1

    def recording_projector(runtime_input):
        nonlocal mutate_contract_after_projector
        runtime_inputs.append(runtime_input)
        if trap_projector_io:
            import builtins
            import http.client
            import sqlite3
            import urllib.request

            import joblib
            from ml_module.model_artifact_loader import SafeShadowModelArtifactLoader

            def reject_io(*_args: Any, **_kwargs: Any) -> Any:
                pytest.fail("typed projector attempted filesystem, DB, loader, or HTTP I/O")

            with monkeypatch.context() as guard:
                guard.setattr(Path, "resolve", reject_io)
                guard.setattr(Path, "stat", reject_io)
                guard.setattr(Path, "lstat", reject_io)
                guard.setattr(Path, "open", reject_io)
                guard.setattr(Path, "read_bytes", reject_io)
                guard.setattr(Path, "read_text", reject_io)
                guard.setattr(builtins, "open", reject_io)
                guard.setattr(sqlite3, "connect", reject_io)
                guard.setattr(joblib, "load", reject_io)
                guard.setattr(SafeShadowModelArtifactLoader, "load", reject_io)
                guard.setattr(urllib.request, "urlopen", reject_io)
                guard.setattr(http.client.HTTPConnection, "connect", reject_io)
                output = project_prepared(runtime_input)
        else:
            output = project_prepared(runtime_input)
        typed_projection_outputs.append(output)
        if mutate_contract_after_projector is not None:
            changed_path = mutate_contract_after_projector
            mutate_contract_after_projector = None
            changed_path.write_bytes(changed_path.read_bytes() + b"\n")
        return output

    monkeypatch.setattr(
        projector_module,
        "project_prepared_ml_runtime_input_v1",
        recording_projector,
    )
    class RecommendationInvocation(TypedDict):
        max_stocks: int
        top_n: int
        as_of_date: str | date | None
        universe: list[str] | None
        historical_research: bool
        select_latest_available_cutoff: bool

    invocation: RecommendationInvocation = {
        "max_stocks": 1,
        "top_n": 1,
        "as_of_date": None,
        "universe": ["AAA"],
        "historical_research": False,
        "select_latest_available_cutoff": True,
    }
    recommendations = service.run_recommendation(
        {"recommendation_ranking": {"threshold_mode": "fixed"}},
        **invocation,
    )

    assert len(runtime_inputs) == 1, (
        f"prepared projector calls={len(runtime_inputs)}, "
        f"service_status={recommendations[0].calibration_status if recommendations else None!r}, "
        f"warnings={service.last_run_context.get('warnings')!r}, "
        f"projection_status={service.last_run_context.get('calibration_projection_status')!r}, "
        f"receipt_status={service.last_run_context.get('calibration_projection_receipt_status')!r}, "
        f"receipt_error={service.last_run_context.get('calibration_projection_receipt_error')!r}, "
        f"receipt_error_detail={service.last_run_context.get('calibration_projection_receipt_error_detail')!r}"
    )
    first_runtime_input = runtime_inputs[0]
    first_provenance = json.loads(
        first_runtime_input.inference_provenance.canonical_json_bytes.decode("utf-8")
    )
    source_contract_path, source_binding = _write_source_contract_for_provenance(
        tmp_path,
        provenance=first_provenance,
    )
    config.recommendation_source_contract_binding = source_binding
    trap_projector_io = True
    recommendations = service.run_recommendation(
        {"recommendation_ranking": {"threshold_mode": "fixed"}},
        **invocation,
    )

    assert len(runtime_inputs) == 2
    runtime_input = runtime_inputs[1]
    assert (
        runtime_input.identity.loaded_model_runtime_class.module,
        runtime_input.identity.loaded_model_runtime_class.qualified_name,
    ) == runtime_input.invocation_capability.loaded_model_runtime_class
    assert recommendations[0].calibration_status == "active_candidate", (
        "prepared runtime changed the active service outcome: "
        f"status={recommendations[0].calibration_status!r}, "
        f"warnings={recommendations[0].calibration_warnings!r}, "
        f"context={service.last_run_context!r}, "
        f"typed_projection={typed_projection_outputs[-1]!r}"
    )
    from app_module.recommendation.ml_preparation_facts import (
        RecommendationMLPreparationFactsV1,
    )
    assert type(runtime_input.preparation_facts) is RecommendationMLPreparationFactsV1
    assert tuple(
        item.symbol for item in runtime_input.preparation_facts.candidates
    ) == ("AAA",)

    assert service.last_run_context["calibration_projection_receipt_status"] == "persisted"
    receipt_metadata = dict(service.last_run_context["calibration_projection_receipt"])
    first_result_id = str(service.last_run_context["result_id"])
    readback = read_inference_projection_receipt(
        receipt_metadata["path"],
        expected_receipt_hash=receipt_metadata["receipt_hash"],
        expected_result_id=first_result_id,
        expected_stock_code="AAA",
    )
    assert readback.receipt_hash == receipt_metadata["receipt_hash"]
    assert runtime_input.inference_provenance is not None
    assert readback.payload["inference_provenance"] == json.loads(
        runtime_input.inference_provenance.canonical_json_bytes.decode("utf-8")
    )

    # 獨立以舊 project_many 輸出和同次封存輸入重建 receipt；不可從已寫入的
    # receipt body 自我複製，並逐 bytes 檢查原有 wire 格式及 hash 欄位。
    from app_module.recommendation.prepared_runtime_projector import (
        prepare_ml_projection_arguments_v1,
    )

    legacy_arguments = prepare_ml_projection_arguments_v1(runtime_input)
    resolved_consumer = runtime_input.invocation_capability._resolved_consumer_for_isolation()
    legacy_projections = resolved_consumer.project_many(
        feature_values_by_symbol=legacy_arguments.feature_values_by_symbol,
        rule_probability_by_symbol=legacy_arguments.rule_probability_by_symbol,
        decision_date=legacy_arguments.decision_date,
        after_cost_rule_probability_by_symbol=(
            legacy_arguments.after_cost_rule_probability_by_symbol
        ),
        after_cost_rule_baseline_id_by_symbol=(
            legacy_arguments.after_cost_rule_baseline_id_by_symbol
        ),
        rule_baseline_id=legacy_arguments.rule_baseline_id,
        ranking_percentile_by_symbol=legacy_arguments.ranking_percentile_by_symbol,
        data_quality=legacy_arguments.data_quality,
        inference_provenance=legacy_arguments.inference_provenance,
        selection_authority=legacy_arguments.selection_authority,
        selection_score_kind=legacy_arguments.selection_score_kind,
        selection_percentile_kind=legacy_arguments.selection_percentile_kind,
        top_n_changed_by_model=legacy_arguments.top_n_changed_by_model,
    )
    typed_projections = typed_projection_outputs[1]
    assert {
        symbol: projection.to_dict() for symbol, projection in typed_projections.items()
    } == {
        symbol: projection.to_dict() for symbol, projection in legacy_projections.items()
    }

    receipt_payload = readback.payload
    expected_identity = json.loads(
        runtime_input.invocation_binding.expected_identity_canonical_json_bytes.decode(
            "utf-8"
        )
    )
    training_provenance = dict(expected_identity["training_provenance"])
    expected_label_fields = {
        "label_registry_hash": str(training_provenance["label_registry_hash"]),
        "label_contract_id": str(training_provenance["label_contract_id"]),
        "return_basis": str(training_provenance["return_basis"]),
    }
    legacy_rows = []
    for _, projection in sorted(legacy_projections.items()):
        row = projection.to_dict()
        row.update(expected_label_fields)
        legacy_rows.append(row)
    legacy_first = next(iter(legacy_projections.values()))
    assert legacy_arguments.inference_provenance is not None
    expected_receipt = build_inference_projection_receipt(
        decision_date=runtime_input.preparation_facts.decision_date.isoformat(),
        result_id=runtime_input.preparation_facts.result_id,
        candidate_identity=expected_identity,
        training_provenance=training_provenance,
        inference_provenance=legacy_arguments.inference_provenance,
        compatibility=legacy_first.provenance_compatibility,
        projections=legacy_rows,
        selection_contract={
            "authority": runtime_input.projection_context.selection_authority,
            "score_kind": runtime_input.projection_context.selection_score_kind,
            "percentile_kind": runtime_input.projection_context.selection_percentile_kind,
            "model_ranking_kind": "model_return_bp",
            "top_n_changed_by_model": (
                runtime_input.projection_context.top_n_changed_by_model
            ),
        },
    )
    expected_receipt_bytes = (
        json.dumps(
            expected_receipt.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    receipt_path = Path(str(readback.receipt_path))
    assert expected_receipt.receipt_hash == readback.receipt_hash
    assert receipt_path.read_bytes() == expected_receipt_bytes

    # Unknown profile 不建立 capability；exact consumer 仍沿用舊 public
    # project_many，其投影與前一個 typed call 完全相同。
    import app_module.recommendation_calibration_consumer as consumer_module

    projector_call_count = len(runtime_inputs)
    with monkeypatch.context() as profile_guard:
        profile_guard.setattr(
            consumer_module,
            "_current_model_graph_runtime_profile",
            lambda: ("unverified-profile",),
        )
        compatibility_recommendations = service.run_recommendation(
            {"recommendation_ranking": {"threshold_mode": "fixed"}},
            **invocation,
        )
    assert len(runtime_inputs) == projector_call_count
    assert compatibility_recommendations[0].calibration_status == "active_candidate"
    assert service.last_run_context["calibration_projection_receipt_status"] == "persisted"
    assert {
        symbol: projection.to_dict()
        for symbol, projection in service.last_calibration_projections.items()
    } == {
        symbol: projection.to_dict()
        for symbol, projection in typed_projection_outputs[1].items()
    }

    # 同一受驗模型另以三種 selected/features 覆蓋做短路 projector parity：
    # dense、混合缺列與全缺列；這些不重跑 service/receipt 保存流程。
    from app_module.dtos import RecommendationDTO
    from app_module.recommendation.prepared_runtime_preparation import (
        build_prepared_runtime_input_v1,
    )
    from app_module.recommendation.prepared_runtime_projector import (
        project_prepared_ml_runtime_input_v1,
        prepare_ml_projection_arguments_v1,
    )
    from app_module.recommendation.prepared_runtime_input import (
        MissingCandidateFeatureV1,
        MissingCandidateProjectionInputV1,
        PreparedMLInvocationBindingV1,
        PreparedMLProjectionContextV1,
        PreparedMLRuntimeInputV1,
        RecommendationMLSparsePreparationFactsV1,
    )
    from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
    from decision_module.recommendation.contracts import RecommendationItem
    from ml_module.historical_feature_builder import HistoricalFeatureBuilder

    sparse_cases = (
        ("dense", ("AAA",), ("AAA",)),
        ("mixed", ("AAA", "BBB"), ("AAA",)),
    )
    expected_identity = json.loads(
        runtime_input.invocation_binding.expected_identity_canonical_json_bytes.decode(
            "utf-8"
        )
    )
    for case_name, selected_symbols, feature_symbols in sparse_cases:
        provider = MLHistoricalSnapshotProvider(database)
        with provider.open_read_lease() as lease:
            snapshot = lease.load(
                decision_date="2026-07-27",
                history_start_date="2026-01-01",
                symbols=tuple(sorted(selected_symbols)),
                industry_index_names=(),
            )
        feature_builder = HistoricalFeatureBuilder(registry)
        available_rows = feature_builder.compute(snapshot, industry_index_name_by_symbol={})
        rows_by_symbol = {row.symbol: row for row in available_rows}
        feature_rows = tuple(rows_by_symbol[symbol] for symbol in feature_symbols)
        selected_items = tuple(
            RecommendationItem(
                stock_code=symbol,
                rule_score=Decimal("80"),
                rank=index + 1,
            )
            for index, symbol in enumerate(selected_symbols)
        )
        selected_dtos = tuple(
            RecommendationDTO(
                stock_code=symbol,
                stock_name=f"測試 {symbol}",
                close_price=Decimal("100"),
                price_change=0.0,
                total_score=80.0,
                indicator_score=0.0,
                pattern_score=0.0,
                volume_score=0.0,
                recommendation_reasons="synthetic parity case",
                industry="",
                regime_match=False,
                score_percentile_bp=7_400 - index * 600,
            )
            for index, symbol in enumerate(selected_symbols)
        )
        scope_id = f"r026-sparse-{case_name}"
        capability = consumer.resolve_invocation_projection_capability(
            invocation_scope_id=scope_id,
            decision_date="2026-07-27",
            expected_identity=expected_identity,
        )
        assert capability is not None
        sparse_input = build_prepared_runtime_input_v1(
            selected_items=selected_items,
            recommendations=selected_dtos,
            feature_rows=feature_rows,
            feature_builder=feature_builder,
            snapshot=snapshot,
            capability=capability,
            active_identity=expected_identity,
            result_id=f"result-r026-{case_name}",
            history_start_date="2026-01-01",
            invocation_scope_id=scope_id,
            decision_clock=datetime(2026, 7, 27, 16, 50, tzinfo=timezone.utc),
            inference_provenance=None,
            source_contract_evidence=None,
            rule_probability_by_symbol={
                symbol: 5_100 + index * 100
                for index, symbol in enumerate(selected_symbols)
            },
            after_cost_rule_probability_by_symbol={},
            after_cost_rule_baseline_id_by_symbol={},
            selection_authority="rule_top_n",
            selection_score_kind="rule_total_score",
            selection_percentile_kind="rule_percentile",
            top_n_changed_by_model=False,
        )
        assert tuple(
            candidate.symbol if hasattr(candidate, "symbol") else candidate.missing_feature.symbol
            for candidate in sparse_input.projection_context.candidates
        ) == selected_symbols
        sparse_facts = sparse_input.preparation_facts
        if selected_symbols == feature_symbols:
            assert type(sparse_facts) is RecommendationMLPreparationFactsV1
        elif feature_rows:
            assert type(sparse_facts) is RecommendationMLSparsePreparationFactsV1
            assert sparse_facts.present_facts is not None
        else:
            assert type(sparse_facts) is RecommendationMLSparsePreparationFactsV1
            assert sparse_facts.present_facts is None
        typed_sparse_output = project_prepared_ml_runtime_input_v1(sparse_input)
        legacy_sparse_args = prepare_ml_projection_arguments_v1(sparse_input)
        resolved_sparse_consumer = capability._resolved_consumer_for_isolation()
        legacy_sparse_output = resolved_sparse_consumer.project_many(
            feature_values_by_symbol=legacy_sparse_args.feature_values_by_symbol,
            rule_probability_by_symbol=legacy_sparse_args.rule_probability_by_symbol,
            decision_date=legacy_sparse_args.decision_date,
            after_cost_rule_probability_by_symbol=(
                legacy_sparse_args.after_cost_rule_probability_by_symbol
            ),
            after_cost_rule_baseline_id_by_symbol=(
                legacy_sparse_args.after_cost_rule_baseline_id_by_symbol
            ),
            rule_baseline_id=legacy_sparse_args.rule_baseline_id,
            ranking_percentile_by_symbol=legacy_sparse_args.ranking_percentile_by_symbol,
            data_quality=legacy_sparse_args.data_quality,
            inference_provenance=legacy_sparse_args.inference_provenance,
            selection_authority=legacy_sparse_args.selection_authority,
            selection_score_kind=legacy_sparse_args.selection_score_kind,
            selection_percentile_kind=legacy_sparse_args.selection_percentile_kind,
            top_n_changed_by_model=legacy_sparse_args.top_n_changed_by_model,
        )
        assert tuple(sorted(typed_sparse_output)) == tuple(sorted(selected_symbols))
        assert legacy_sparse_args.rule_probability_by_symbol == {
            symbol: 5_100 + index * 100
            for index, symbol in enumerate(selected_symbols)
        }
        assert {
            symbol: projection.to_dict()
            for symbol, projection in typed_sparse_output.items()
        } == {
            symbol: projection.to_dict()
            for symbol, projection in legacy_sparse_output.items()
        }
        for index, symbol in enumerate(selected_symbols):
            assert typed_sparse_output[symbol].ranking_percentile_bp == 7_400 - index * 600

    # 全缺列仍需有同次 query 對象：請 provider 讀取 AAA/BBB，DB 只有 AAA；
    # 以同一快照明確封存被選中的 BBB 無 price row，不補 row hash 或向量。
    from dataclasses import replace as dataclass_replace
    from app_module.recommendation.historical_snapshot_custody import (
        HistoricalRawSnapshotQueryScopeV1,
        build_historical_raw_snapshot_custody_facts_v1,
    )
    from app_module.recommendation.ml_preparation_facts import _selected_item_hash

    provider = MLHistoricalSnapshotProvider(database)
    with provider.open_read_lease() as lease:
        all_missing_snapshot = lease.load(
            decision_date="2026-07-27",
            history_start_date="2026-01-01",
            symbols=("AAA", "BBB"),
            industry_index_names=(),
        )
    all_missing_builder = HistoricalFeatureBuilder(registry)
    all_missing_rows = all_missing_builder.compute(
        all_missing_snapshot,
        industry_index_name_by_symbol={},
    )
    assert tuple(row.symbol for row in all_missing_rows) == ("AAA",)
    missing_item = RecommendationItem(
        stock_code="BBB",
        rule_score=Decimal("80"),
        rank=1,
    )
    missing_feature = MissingCandidateFeatureV1(
        symbol="BBB",
        selection_index=0,
        selected_item_sha256=_selected_item_hash(missing_item),
        reason="historical_price_row_missing",
    )
    all_missing_scope_id = "r026-sparse-all-missing"
    all_missing_capability = consumer.resolve_invocation_projection_capability(
        invocation_scope_id=all_missing_scope_id,
        decision_date="2026-07-27",
        expected_identity=expected_identity,
    )
    assert all_missing_capability is not None
    load_contract = all_missing_builder.load_contract
    all_missing_facts = RecommendationMLSparsePreparationFactsV1(
        result_id="result-r026-all-missing",
        decision_date=date(2026, 7, 27),
        feature_cutoff_date=date.fromisoformat(all_missing_snapshot.feature_as_of_date),
        feature_registry_id=load_contract.registry_id,
        feature_registry_hash=load_contract.registry_hash,
        feature_schema=load_contract.canonical_schema,
        feature_ids=load_contract.canonical_ids,
        feature_schema_hash=load_contract.schema_hash,
        feature_load_contract_hash=load_contract.contract_hash,
        present_facts=None,
        missing_candidates=(missing_feature,),
    )
    provider_contract_id = all_missing_snapshot.provider_contract_id
    assert isinstance(provider_contract_id, str)
    query_scope = HistoricalRawSnapshotQueryScopeV1(
        source_id=provider_contract_id,
        decision_date=date(2026, 7, 27),
        history_start_date=date(2026, 1, 1),
        symbols=("AAA", "BBB"),
        industry_index_names=(),
    )
    custody = build_historical_raw_snapshot_custody_facts_v1(
        snapshot=all_missing_snapshot,
        query_scope=query_scope,
    )
    all_missing_identity = dataclass_replace(
        runtime_input.identity,
        ml_snapshot_refs=(custody.to_snapshot_reference(),),
    )
    all_missing_projection = MissingCandidateProjectionInputV1(
        missing_feature=missing_feature,
        rule_probability_bp=5_100,
        after_cost_rule_probability_bp=None,
        after_cost_rule_baseline_id=None,
        ranking_percentile_bp=7_400,
    )
    all_missing_context = PreparedMLProjectionContextV1(
        candidates=(all_missing_projection,),
        rule_baseline_id=runtime_input.projection_context.rule_baseline_id,
        data_quality=runtime_input.projection_context.data_quality,
        selection_authority=runtime_input.projection_context.selection_authority,
        selection_score_kind=runtime_input.projection_context.selection_score_kind,
        selection_percentile_kind=runtime_input.projection_context.selection_percentile_kind,
        top_n_changed_by_model=False,
    )
    all_missing_input = PreparedMLRuntimeInputV1(
        identity=all_missing_identity,
        preparation_facts=all_missing_facts,
        projection_context=all_missing_context,
        invocation_binding=PreparedMLInvocationBindingV1(
            invocation_scope_id=all_missing_scope_id,
            expected_identity_canonical_json_bytes=(
                runtime_input.invocation_binding.expected_identity_canonical_json_bytes
            ),
        ),
        inference_provenance=None,
        decision_clock=runtime_input.decision_clock,
        invocation_capability=all_missing_capability,
        source_contract_evidence=None,
    )
    all_missing_typed_output = project_prepared_ml_runtime_input_v1(all_missing_input)
    all_missing_arguments = prepare_ml_projection_arguments_v1(all_missing_input)
    all_missing_legacy_output = all_missing_capability._resolved_consumer_for_isolation().project_many(
        feature_values_by_symbol=all_missing_arguments.feature_values_by_symbol,
        rule_probability_by_symbol=all_missing_arguments.rule_probability_by_symbol,
        decision_date=all_missing_arguments.decision_date,
        after_cost_rule_probability_by_symbol=(
            all_missing_arguments.after_cost_rule_probability_by_symbol
        ),
        after_cost_rule_baseline_id_by_symbol=(
            all_missing_arguments.after_cost_rule_baseline_id_by_symbol
        ),
        rule_baseline_id=all_missing_arguments.rule_baseline_id,
        ranking_percentile_by_symbol=all_missing_arguments.ranking_percentile_by_symbol,
        data_quality=all_missing_arguments.data_quality,
        inference_provenance=all_missing_arguments.inference_provenance,
        selection_authority=all_missing_arguments.selection_authority,
        selection_score_kind=all_missing_arguments.selection_score_kind,
        selection_percentile_kind=all_missing_arguments.selection_percentile_kind,
        top_n_changed_by_model=all_missing_arguments.top_n_changed_by_model,
    )
    assert tuple(all_missing_typed_output) == ("BBB",)
    assert all_missing_arguments.feature_values_by_symbol == {}
    assert all_missing_arguments.rule_probability_by_symbol == {"BBB": 5_100}
    assert all_missing_typed_output["BBB"].ranking_percentile_bp == 7_400
    assert all_missing_typed_output["BBB"].warnings
    assert {
        symbol: projection.to_dict()
        for symbol, projection in all_missing_typed_output.items()
    } == {
        symbol: projection.to_dict()
        for symbol, projection in all_missing_legacy_output.items()
    }

    # 變更發生在 typed projection 返回後、receipt preparation 開始前；既有
    # app-boundary 檢查必須先拒絕，且不得呼叫 receipt builder 或寫入新 receipt。
    import app_module.recommendation_service as current_service_module

    builder_calls = 0
    original_receipt_builder = current_service_module.build_inference_projection_receipt

    def count_receipt_builder(*args: Any, **kwargs: Any):
        nonlocal builder_calls
        builder_calls += 1
        return original_receipt_builder(*args, **kwargs)

    monkeypatch.setattr(
        current_service_module,
        "build_inference_projection_receipt",
        count_receipt_builder,
    )
    receipt_files_before = tuple(
        sorted((tmp_path / "authority" / "inference_projection").glob("**/*.json"))
    )
    mutate_contract_after_projector = source_contract_path
    service.run_recommendation(
        {"recommendation_ranking": {"threshold_mode": "fixed"}},
        **invocation,
    )
    assert builder_calls == 0
    assert service.last_run_context["calibration_projection_receipt_status"] == "unavailable"
    assert "source contract file hash mismatch" in str(
        service.last_run_context["calibration_projection_receipt_error_detail"]
    )
    assert tuple(
        sorted((tmp_path / "authority" / "inference_projection").glob("**/*.json"))
    ) == receipt_files_before

    # 移除合成 active pointer 後，同一 service opt-in 應封存真實 rule-only
    # reload 結果；不建立 model binding/class，並與舊 no-model project_many 一致。
    config.recommendation_source_contract_binding = None
    consumer.pointer_path.unlink()
    no_model_recommendations = service.run_recommendation(
        {"recommendation_ranking": {"threshold_mode": "fixed"}},
        **invocation,
    )
    no_model_runtime_input = runtime_inputs[-1]
    from app_module.recommendation.prepared_runtime_input import NoModelShadowIdentityV1

    assert type(no_model_runtime_input.identity) is NoModelShadowIdentityV1
    assert no_model_runtime_input.identity.reload_status == "rule_only"
    assert no_model_runtime_input.identity.blocker == "active_pointer_missing"
    assert no_model_runtime_input.identity.pointer_raw_bytes is None
    assert not hasattr(no_model_runtime_input.identity, "model_resolution")
    assert not hasattr(no_model_runtime_input.identity, "loaded_model_runtime_class")
    assert no_model_recommendations[0].calibration_status == "rule_only"

    from app_module.recommendation.prepared_runtime_projector import (
        prepare_ml_projection_arguments_v1,
    )

    no_model_arguments = prepare_ml_projection_arguments_v1(no_model_runtime_input)
    no_model_oracle_consumer = RecommendationCalibrationConsumer(
        pointer_path=consumer.pointer_path,
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
        data_root=config.data_root,
    )
    no_model_oracle_capability = (
        no_model_oracle_consumer.resolve_invocation_no_model_projection_capability_v1(
            invocation_scope_id="r026-no-model-legacy-oracle",
            decision_date="2026-07-27",
            expected_identity={},
        )
    )
    assert no_model_oracle_capability is not None
    no_model_legacy_output = (
        no_model_oracle_capability._resolved_consumer_for_isolation().project_many(
            feature_values_by_symbol=no_model_arguments.feature_values_by_symbol,
            rule_probability_by_symbol=no_model_arguments.rule_probability_by_symbol,
            decision_date=no_model_arguments.decision_date,
            after_cost_rule_probability_by_symbol=(
                no_model_arguments.after_cost_rule_probability_by_symbol
            ),
            after_cost_rule_baseline_id_by_symbol=(
                no_model_arguments.after_cost_rule_baseline_id_by_symbol
            ),
            rule_baseline_id=no_model_arguments.rule_baseline_id,
            ranking_percentile_by_symbol=(
                no_model_arguments.ranking_percentile_by_symbol
            ),
            data_quality=no_model_arguments.data_quality,
            inference_provenance=no_model_arguments.inference_provenance,
            selection_authority=no_model_arguments.selection_authority,
            selection_score_kind=no_model_arguments.selection_score_kind,
            selection_percentile_kind=no_model_arguments.selection_percentile_kind,
            top_n_changed_by_model=no_model_arguments.top_n_changed_by_model,
        )
    )
    assert {
        symbol: projection.to_dict()
        for symbol, projection in typed_projection_outputs[-1].items()
    } == {
        symbol: projection.to_dict()
        for symbol, projection in no_model_legacy_output.items()
    }


def _write_source_contract_for_provenance(
    tmp_path: Path,
    *,
    provenance: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    from ml_module.recommendation_inference_provenance import (
        _hash_payload,
        _source_contract_feature_rows_hash,
    )

    rows = list(provenance["feature_rows"])
    source_database = str(provenance["source_database"])
    decision_date = str(provenance["decision_date"])
    history_start_date = str(provenance["history_start_date"])
    feature_registry_hash = str(provenance["feature_registry_hash"])
    feature_builder_schema_hash = str(provenance["feature_builder_schema_hash"])
    symbols = sorted({str(row["symbol"]) for row in rows})
    rows_hash = _source_contract_feature_rows_hash(
        source_db=str(Path(source_database).expanduser().resolve()),
        decision_date=decision_date,
        history_start_date=history_start_date,
        feature_registry_hash=feature_registry_hash,
        feature_schema_hash=feature_builder_schema_hash,
        symbols=symbols,
        rows=rows,
    )
    snapshot_body = {
        "component": "prospective_recommendation_features",
        "source_db": str(Path(source_database).expanduser().resolve()),
        "decision_date": decision_date,
        "history_start_date": history_start_date,
        "feature_registry_hash": feature_registry_hash,
        "feature_schema_hash": feature_builder_schema_hash,
        "symbols": symbols,
        "rows": rows,
        "rows_sha256": rows_hash,
    }
    feature_snapshot = {
        **snapshot_body,
        "content_sha256": _hash_payload(snapshot_body),
    }
    contract_body = {
        "schema_version": "recommendation-calibration-source-contract.v1",
        "decision_date": decision_date,
        "symbols": symbols,
        "technical": {"prospective_feature_snapshot": feature_snapshot},
    }
    contract_content_sha256 = _hash_payload(contract_body)
    contract_payload = {
        **contract_body,
        "contract_sha256": contract_content_sha256,
    }
    contract_bytes = (
        json.dumps(contract_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    contract_path = tmp_path / "configured-source-contract.json"
    contract_path.write_bytes(contract_bytes)
    binding = {
        "schema_version": "recommendation-calibration-capture-source-binding.v1",
        "contract_path": str(contract_path.resolve()),
        "contract_content_sha256": contract_content_sha256,
        "contract_file_sha256": "sha256:" + hashlib.sha256(contract_bytes).hexdigest(),
        "symbols": symbols,
        "price_up_prospective_status": "ready",
        "price_up_prospective_blockers": [],
        "feature_snapshot_content_sha256": feature_snapshot["content_sha256"],
        "feature_snapshot_rows_sha256": rows_hash,
        "historical_pit_eligible": False,
    }
    return contract_path, binding
