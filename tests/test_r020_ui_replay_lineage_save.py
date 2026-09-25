"""R020 BacktestView 至 Research Run Registry 的合成 lineage 保存驗證。"""

from __future__ import annotations

import hashlib
import sys
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation_dataframe_provider import RecommendationDataFrameProvider
from app_module.recommendation.contracts import (
    Context,
    DecisionBatch,
    ExecutionStatus,
    QualityReport,
    RecommendationExecution,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation.persistence import ExecutionArtifactIntegrityError
from app_module.recommendation.replay_lineage_service import (
    verify_replay_lineage_children,
)
from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
    RecommendationSnapshotDTO,
)
from app_module.recommendation_portfolio_backtest_service import (
    RecommendationPortfolioBacktestService,
)
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_service import ResearchRunService
from backtest_module.broker_simulator import LEGACY_CLOSE_CONTRACT
from data_module.config import TWStockConfig
from decision_module.recommendation.contracts import RecommendationItem
from ui_qt.views.backtest_view import BacktestView


@pytest.fixture
def qt_app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _execution(
    parent_result_id: str,
    *,
    snapshot_date: date = date(2026, 9, 23),
    result_id: str = "replay-child-ui-20260923",
) -> RecommendationExecution:
    return RecommendationExecution(
        result_id=result_id,
        request=Request(as_of_date=snapshot_date),
        context=Context(as_of_date=snapshot_date),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(
            items=(
                RecommendationItem(
                    stock_code="2330",
                    stock_name="台積電",
                    rule_score=Decimal("84.25"),
                ),
            )
        ),
        quality=QualityReport(),
        related_references=(
            VersionReference(
                kind=ReferenceKind.REPLAY_PARENT,
                reference_id=parent_result_id,
            ),
        ),
    )


def _result(
    parent_result_id: str,
    *,
    include_child: bool,
    as_of_dates: tuple[date, ...] = (date(2026, 9, 23),),
) -> RecommendationPortfolioBacktestResultDTO:
    snapshots: list[RecommendationSnapshotDTO] = []
    for snapshot_date in as_of_dates:
        snapshot = RecommendationSnapshotDTO(
            as_of_date=snapshot_date.isoformat(),
            profile_id="synthetic-r020-ui",
            strategy_config={"strategy_id": "recommendation_replay"},
            regime="Trend",
            recommendations=[
                {
                    "stock_code": "2330",
                    "stock_name": "台積電",
                    "total_score": 84.25,
                    "selection_reason": "合成測試",
                }
            ],
        )
        snapshot.attach_replay_parent_id(parent_result_id)
        if include_child:
            child_id = f"replay-child-ui-{snapshot_date:%Y%m%d}"
            snapshot.attach_canonical_execution(
                _execution(
                    parent_result_id,
                    snapshot_date=snapshot_date,
                    result_id=child_id,
                )
            )
        snapshots.append(snapshot)
    result = RecommendationPortfolioBacktestResultDTO(
        summary={"status": "completed", "total_return": "0.01"},
        equity_curve=pd.DataFrame(
            [{"日期": "2026-09-23", "portfolio_value": 1_010_000}]
        ),
        trades=pd.DataFrame(
            [{"日期": "2026-09-23", "stock_code": "2330", "side": "buy"}]
        ),
        snapshots=snapshots,
        period_holdings=[],
        stock_contribution=[],
        details={"data_manifest": {"source": "synthetic-r020-test"}},
    )
    result.attach_replay_parent_id(parent_result_id)
    return result


def _view(config: TWStockConfig, service: object) -> BacktestView:
    view = BacktestView(backtest_service=MagicMock(), config=config)
    view.research_run_service = service
    view.run_repository = MagicMock()
    view.portfolio_run_repository = MagicMock()
    view.current_recommendation_portfolio_config = {
        "profile_id": "synthetic-r020-ui",
        "strategy_config": {"strategy_id": "recommendation_replay"},
    }
    view.current_recommendation_portfolio_run_params = {
        "start_date": "2026-09-23",
        "end_date": "2026-09-23",
        "initial_capital": 1_000_000,
        "top_n": 5,
        "allocation_method": "equal_weight",
    }
    view._execution_generation = 1
    view._recommendation_portfolio_result_generation = 1
    view._recommendation_portfolio_result_source = "execution"
    return view


def _config(tmp_path) -> TWStockConfig:
    return TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="test",
    )


def test_ui_save_persists_child_and_registry_manifest_with_verified_hashes(
    qt_app: QApplication,
    tmp_path,
) -> None:
    config = _config(tmp_path)
    registry = ResearchRunService(config)
    composition = build_recommendation_composition(config)
    view = _view(config, registry)
    parent_result_id = "portfolio-parent-ui-r020-success"
    result = _result(parent_result_id, include_child=True)
    view.current_recommendation_portfolio_result = result

    run_id = view._save_recommendation_portfolio_to_research_registry(
        "合成 lineage 回測", "只在 TEMP 測試"
    )
    assert view.current_portfolio_run_id is None
    assert view.current_recommendation_registry_run_id == run_id

    loaded = registry.load_run_data(run_id)
    assert loaded.replay_lineage is not None
    envelope = loaded.replay_lineage
    assert envelope.sidecar.parent_result_id == parent_result_id
    assert len(envelope.sidecar.children) == 1
    child_ref = envelope.sidecar.children[0]
    assert child_ref.result_id == "replay-child-ui-20260923"
    assert child_ref.snapshot_date == date(2026, 9, 23)
    assert (
        "sha256:" + hashlib.sha256(envelope.raw_payload).hexdigest()
        == envelope.raw_payload_sha256
    )

    descriptor = loaded.metadata.data_manifest[
        registry.REPLAY_LINEAGE_MANIFEST_KEY
    ]
    assert descriptor["parent_result_id"] == parent_result_id
    assert descriptor["child_count"] == 1
    assert descriptor["raw_payload_sha256"] == envelope.raw_payload_sha256
    assert "replay_lineage_status" not in loaded.metadata.data_manifest
    child_record, child_envelope = composition.persistence.read_verified_envelope(
        child_ref.result_id
    )
    verified_child = child_ref.verify_execution_artifact(
        child_envelope.raw_payload
    )
    assert verified_child == _execution(parent_result_id)
    assert child_record.metadata.payload_hash == child_ref.canonical_payload_sha256
    assert loaded.equity.equals(result.equity_curve)
    assert loaded.trades.equals(result.trades)
    assert loaded.metadata.run_id == run_id


def test_ui_multi_date_save_reads_back_and_verifies_all_actual_child_bytes(
    qt_app: QApplication,
    tmp_path,
) -> None:
    config = _config(tmp_path)
    registry = ResearchRunService(config)
    view = _view(config, registry)
    parent_result_id = "portfolio-parent-ui-r020-multi-date"
    snapshot_dates = (date(2026, 9, 22), date(2026, 9, 23))
    result = _result(
        parent_result_id,
        include_child=True,
        as_of_dates=snapshot_dates,
    )
    view.current_recommendation_portfolio_result = result

    run_id = view._save_recommendation_portfolio_to_research_registry(
        "合成多日期 lineage 回測", "只在 TEMP 測試"
    )

    reloaded_registry = ResearchRunService(config)
    loaded = reloaded_registry.load_run_data(run_id)
    assert loaded.replay_lineage is not None
    assert loaded.replay_lineage.sidecar.parent_result_id == parent_result_id
    children = loaded.replay_lineage.sidecar.children
    assert [child.snapshot_date for child in children] == list(snapshot_dates)
    assert [child.result_id for child in children] == [
        "replay-child-ui-20260922",
        "replay-child-ui-20260923",
    ]

    fresh_composition = build_recommendation_composition(config)
    verified = verify_replay_lineage_children(
        loaded.replay_lineage,
        fresh_composition.persistence,
    )
    assert [execution.result_id for execution in verified] == [
        child.result_id for child in children
    ]
    assert [execution.context.as_of_date for execution in verified] == list(
        snapshot_dates
    )

    damaged_child_id = children[1].result_id
    artifact_path = (
        fresh_composition.store.artifact_root
        / fresh_composition.store.artifact_name_for(damaged_child_id)
    )
    artifact_path.write_bytes(artifact_path.read_bytes() + b" ")
    partial_result = None
    with pytest.raises(ExecutionArtifactIntegrityError):
        partial_result = verify_replay_lineage_children(
            loaded.replay_lineage,
            fresh_composition.persistence,
        )
    assert partial_result is None


def test_custom_legacy_provider_portfolio_saves_registry_without_fake_child(
    qt_app: QApplication,
    tmp_path,
) -> None:
    config = _config(tmp_path)
    registry = ResearchRunService(config)
    legacy_row = {
        "stock_code": "2330",
        "stock_name": "合成 legacy 標的",
        "total_score": 88.0,
        "factor_scores": {"technical": 80.0},
        "selection_reason": "custom provider v1 row",
    }

    def custom_provider(*_args: object) -> list[dict[str, object]]:
        return [dict(legacy_row)]

    history = pd.DataFrame([
        {"日期": "2026-09-22", "證券代號": "2330", "證券名稱": "合成 legacy 標的", "收盤價": 100},
        {"日期": "2026-09-23", "證券代號": "2330", "證券名稱": "合成 legacy 標的", "收盤價": 101},
    ])
    with pytest.warns(UserWarning):
        result = RecommendationPortfolioBacktestService(custom_provider).run_portfolio_backtest(
            start_date="2026-09-22",
            end_date="2026-09-23",
            profile_id="synthetic-r020-custom-provider",
            recommendation_config={"strategy_id": "synthetic-legacy"},
            history=history,
            initial_capital=1_000_000.0,
            rebalance_frequency="once",
            top_n=1,
            allocation_method="equal_weight",
            holding_days=1,
            execution_contract=LEGACY_CLOSE_CONTRACT,
        )

    assert result.replay_parent_id and result.snapshots
    snapshot = result.snapshots[0]
    assert snapshot.replay_parent_id == result.replay_parent_id and snapshot.canonical_execution is None
    assert snapshot.recommendations == [legacy_row]
    v1_result = result.to_dict()
    assert (
        v1_result["snapshots"][0]["recommendations"] == [legacy_row]
        and "replay_parent_id" not in v1_result
    )

    view = _view(config, registry)
    view.current_recommendation_portfolio_result = result
    view.current_recommendation_portfolio_config.update(
        profile_id="synthetic-r020-custom-provider",
        strategy_config={"strategy_id": "synthetic-legacy"},
    )
    view.current_recommendation_portfolio_run_params.update(
        start_date="2026-09-22", end_date="2026-09-23", top_n=1
    )
    run_id = view._save_recommendation_portfolio_to_research_registry(
        "custom legacy synthetic run", "TEMP integration"
    )

    loaded = ResearchRunService(config).load_run_data(run_id)
    assert loaded.metadata.run_type == "recommendation_portfolio"
    assert loaded.metadata.data_manifest["replay_lineage_status"] == {
        "schema_version": 1,
        "status": "unavailable",
        "parent_result_id": result.replay_parent_id,
        "reason": "canonical_child_unavailable",
    }
    assert (
        "replay_lineage_sidecar" not in loaded.metadata.data_manifest
        and loaded.replay_lineage is None
    )
    assert loaded.equity.equals(result.equity_curve)
    assert loaded.trades.equals(result.trades)

    composition = build_recommendation_composition(config)
    assert tuple(composition.store.iter_artifacts()) == ()
    assert not registry._paths_for(run_id)["replay_lineage_final"].exists()


def test_ui_save_keeps_v1_registry_run_when_child_is_unavailable(
    qt_app: QApplication,
    tmp_path,
) -> None:
    config = _config(tmp_path)
    registry = ResearchRunService(config)
    view = _view(config, registry)
    parent_result_id = "portfolio-parent-ui-r020-no-child"
    result = _result(parent_result_id, include_child=False)
    view.current_recommendation_portfolio_result = result

    run_id = view._save_recommendation_portfolio_to_research_registry(
        "無 child 的舊結果", "保留 v1 run"
    )
    assert view.current_portfolio_run_id is None
    assert view.current_recommendation_registry_run_id == run_id

    loaded = registry.load_run_data(run_id)
    assert loaded.replay_lineage is None
    assert "replay_lineage_sidecar" not in loaded.metadata.data_manifest
    assert loaded.metadata.data_manifest["replay_lineage_status"] == {
        "schema_version": 1,
        "status": "unavailable",
        "parent_result_id": parent_result_id,
        "reason": "canonical_child_unavailable",
    }
    assert loaded.equity.equals(result.equity_curve)
    assert loaded.trades.equals(result.trades)

    reopened = _view(config, ResearchRunService(config))
    reopened.current_recommendation_portfolio_result = None
    reopened.chart_data_service = MagicMock()
    widget = reopened.result_panel.add_registry_compare_tab()
    widget.refresh_runs()
    run_index = next(
        index
        for index in range(widget.run_list.count())
        if widget.run_list.item(index).data(Qt.ItemDataRole.UserRole) == run_id
    )
    widget.run_list.item(run_index).setSelected(True)
    widget.open_selected_recommendation_run()

    assert type(reopened.current_recommendation_portfolio_result) is RecommendationPortfolioBacktestResultDTO
    assert reopened.current_recommendation_portfolio_result.to_dict() == result.to_dict()
    summary = reopened.portfolio_summary_text.toPlainText()
    assert "推薦列仍保留，但 canonical child 不可用" in summary
    assert "沒有完整推薦回放 DTO" not in summary
    reopened.chart_data_service.get_benchmark_series.assert_not_called()


def test_empty_snapshot_registry_save_marks_lineage_unavailable_and_restarts_empty_dto(
    qt_app: QApplication,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    registry = ResearchRunService(config)
    view = _view(config, registry)
    parent_result_id = "portfolio-parent-ui-r020-empty-snapshots"
    result = _result(
        parent_result_id,
        include_child=False,
        as_of_dates=(),
    )
    assert result.snapshots == []
    view.current_recommendation_portfolio_result = result

    def fail_if_called(*_args, **_kwargs):
        pytest.fail("empty-snapshot Registry save/open must not recompute replay")

    monkeypatch.setattr(RecommendationDataFrameProvider, "__call__", fail_if_called)
    monkeypatch.setattr(
        RecommendationPortfolioBacktestService,
        "run_portfolio_backtest",
        fail_if_called,
    )
    from app_module.recommendation import replay_lineage_service

    monkeypatch.setattr(
        replay_lineage_service,
        "persist_replay_lineage_children",
        fail_if_called,
    )

    run_id = view._save_recommendation_portfolio_to_research_registry(
        "空 snapshots 合成回放", "只在 TEMP 測試"
    )
    first_read = registry.load_run_data(run_id)
    assert first_read.metadata.data_manifest["replay_lineage_status"] == {
        "schema_version": 1,
        "status": "unavailable",
        "parent_result_id": parent_result_id,
        "reason": "canonical_child_unavailable",
    }
    assert "replay_lineage_sidecar" not in first_read.metadata.data_manifest
    assert first_read.replay_lineage is None
    assert first_read.portfolio_result_artifact is not None
    assert first_read.portfolio_result_artifact.portfolio_parent_id == parent_result_id
    assert first_read.portfolio_result_artifact.raw_payload
    assert not registry._paths_for(run_id)["replay_lineage_final"].exists()

    reopened_registry = ResearchRunService(config)
    reopened = _view(config, reopened_registry)
    reopened.current_recommendation_portfolio_result = None
    reopened.chart_data_service = MagicMock()
    widget = reopened.result_panel.add_registry_compare_tab()
    widget.refresh_runs()
    run_index = next(
        index
        for index in range(widget.run_list.count())
        if widget.run_list.item(index).data(Qt.ItemDataRole.UserRole) == run_id
    )
    widget.run_list.item(run_index).setSelected(True)
    widget.open_selected_recommendation_run()
    qt_app.processEvents()

    restored = reopened.current_recommendation_portfolio_result
    assert type(restored) is RecommendationPortfolioBacktestResultDTO
    assert restored.snapshots == []
    assert restored.replay_parent_id == parent_result_id
    summary = reopened.portfolio_summary_text.toPlainText()
    assert "本次沒有 recommendation snapshots；canonical child 不可用" in summary
    assert "推薦列仍保留" not in summary
    reopened.chart_data_service.get_benchmark_series.assert_not_called()


def test_legacy_history_readback_cannot_be_saved_as_a_new_registry_run(
    qt_app: QApplication,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    registry = ResearchRunService(config)
    view = _view(config, registry)
    legacy_result = _result(
        "portfolio-parent-ui-r020-legacy-history",
        include_child=False,
    )
    view.portfolio_run_repository.load_run.return_value = {
        "result_dto": legacy_result,
        "notes": "TEMP legacy fixture",
    }
    view._plot_recommendation_portfolio_charts = lambda *_args, **_kwargs: None
    view.portfolio_history_combo.clear()
    view.portfolio_history_combo.addItem(
        "legacy portfolio fixture",
        "legacy-portfolio-run-ui-r020",
    )
    registry.save_run = MagicMock()

    view._on_portfolio_history_changed(0)

    assert view._recommendation_portfolio_result_source == "legacy_history"
    assert view._recommendation_portfolio_result_generation is None
    assert view.current_portfolio_run_id == "legacy-portfolio-run-ui-r020"
    with pytest.raises(ValueError, match="歷史讀回結果不可重新保存"):
        view._save_recommendation_portfolio_to_research_registry(
            "不可重存的舊結果",
            "必須執行新回放",
        )
    registry.save_run.assert_not_called()
    composition = build_recommendation_composition(config)
    assert tuple(composition.store.iter_artifacts()) == ()


def test_registry_open_restarts_full_portfolio_dto_without_current_benchmark(
    qt_app: QApplication,
    tmp_path,
) -> None:
    config = _config(tmp_path)
    registry = ResearchRunService(config)
    saver = _view(config, registry)
    result = _result(
        "portfolio-parent-ui-r020-restart",
        include_child=True,
        as_of_dates=(date(2026, 9, 22), date(2026, 9, 23)),
    )
    saver.current_recommendation_portfolio_result = result
    run_id = saver._save_recommendation_portfolio_to_research_registry(
        "重啟讀回合成結果", "只使用 TEMP"
    )

    reopened = _view(config, ResearchRunService(config))
    reopened.current_recommendation_portfolio_result = None
    reopened.current_recommendation_registry_run_id = None
    reopened.chart_data_service = MagicMock()
    widget = reopened.result_panel.add_registry_compare_tab()
    widget.refresh_runs()
    run_index = next(
        index
        for index in range(widget.run_list.count())
        if widget.run_list.item(index).data(Qt.ItemDataRole.UserRole) == run_id
    )
    widget.run_list.item(run_index).setSelected(True)

    assert widget.open_recommendation_button.isEnabled() is True
    widget.open_selected_recommendation_run()
    qt_app.processEvents()

    loaded = reopened.current_recommendation_portfolio_result
    assert type(loaded) is RecommendationPortfolioBacktestResultDTO
    assert loaded.to_dict() == result.to_dict()
    assert [snapshot.canonical_execution.result_id for snapshot in loaded.snapshots] == [
        "replay-child-ui-20260922",
        "replay-child-ui-20260923",
    ]
    assert reopened.current_recommendation_registry_run_id == run_id
    assert reopened.current_portfolio_run_id is None
    assert reopened._recommendation_portfolio_result_source == "registry"
    assert reopened.portfolio_history_combo.findData(run_id) == -1
    assert reopened.save_portfolio_result_btn.isEnabled() is False
    assert reopened.delete_portfolio_result_btn.isEnabled() is False
    assert reopened.promote_portfolio_result_btn.isEnabled() is False
    reopened.chart_data_service.get_benchmark_series.assert_not_called()
    assert "Registry run ID" in reopened.portfolio_summary_text.toPlainText()
    assert "已讀回並驗證所有 canonical child" in reopened.portfolio_summary_text.toPlainText()
    assert "Benchmark 圖層不可用" in reopened.portfolio_summary_text.toPlainText()


def test_registry_open_reports_markerless_old_run_as_typed_unavailable(
    qt_app: QApplication,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    registry = ResearchRunService(config)
    metadata = ResearchRunMetadataDTO(
        run_id="r020-ui-markerless-old",
        run_name="舊推薦回放",
        run_type="recommendation_portfolio",
        strategy_id="synthetic-legacy",
        original_input={"profile_id": "TEMP"},
        normalized_params={"top_n": 1},
        metrics={"total_return": 0.01},
        data_manifest={"legacy_fixture": True},
        payload_hash="sha256:caller-placeholder",
        created_at="2026-09-24T10:00:00-07:00",
    )
    equity = pd.DataFrame([{"日期": "2026-09-23", "portfolio_value": 100}])
    trades = pd.DataFrame(columns=["日期", "stock_code", "side"])
    saved = registry.save_run(metadata, equity, trades)
    view = _view(config, ResearchRunService(config))
    view.current_recommendation_portfolio_result = None
    messages: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: messages.append(args),
    )
    widget = view.result_panel.add_registry_compare_tab()
    widget.refresh_runs()
    item = next(
        widget.run_list.item(index)
        for index in range(widget.run_list.count())
        if widget.run_list.item(index).data(Qt.ItemDataRole.UserRole) == saved.run_id
    )
    item.setSelected(True)

    widget.open_selected_recommendation_run()

    assert view.current_recommendation_portfolio_result is None
    assert view.current_recommendation_registry_run_id is None
    assert len(messages) == 1
    assert "沒有完整推薦回放 DTO" in str(messages[0][2])
    assert "不會從摘要重建推薦列" in str(messages[0][2])


def test_registry_open_corruption_does_not_apply_partial_dto(
    qt_app: QApplication,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    registry = ResearchRunService(config)
    saver = _view(config, registry)
    result = _result("portfolio-parent-ui-r020-damaged", include_child=False)
    saver.current_recommendation_portfolio_result = result
    run_id = saver._save_recommendation_portfolio_to_research_registry(
        "損毀測試", "只使用 TEMP"
    )
    paths = registry._paths_for(run_id)
    paths["portfolio_result_final"].write_bytes(
        paths["portfolio_result_final"].read_bytes() + b" "
    )

    reopened = _view(config, ResearchRunService(config))
    reopened.current_recommendation_portfolio_result = None
    errors: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args: errors.append(args),
    )
    widget = reopened.result_panel.add_registry_compare_tab()
    widget.refresh_runs()
    item = next(
        widget.run_list.item(index)
        for index in range(widget.run_list.count())
        if widget.run_list.item(index).data(Qt.ItemDataRole.UserRole) == run_id
    )
    item.setSelected(True)

    widget.open_selected_recommendation_run()

    assert reopened.current_recommendation_portfolio_result is None
    assert reopened.current_recommendation_registry_run_id is None
    assert len(errors) == 1
    assert "Research Run 已保存資料未通過完整性讀取" in str(errors[0][2])


def test_registry_open_result_is_discarded_after_new_execution_starts(
    qt_app: QApplication,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.recommendation.portfolio_result_reader import (
        RecommendationPortfolioResultReader,
    )

    config = _config(tmp_path)
    registry = ResearchRunService(config)
    saver = _view(config, registry)
    result = _result("portfolio-parent-ui-r020-stale", include_child=False)
    saver.current_recommendation_portfolio_result = result
    run_id = saver._save_recommendation_portfolio_to_research_registry(
        "stale readback", "只使用 TEMP"
    )

    reopened = _view(config, ResearchRunService(config))
    reopened.current_recommendation_portfolio_result = None
    monkeypatch.setattr(
        RecommendationPortfolioResultReader,
        "read",
        lambda _reader, _run_id: (
            reopened._mark_research_execution_started() or result
        ),
    )
    widget = reopened.result_panel.add_registry_compare_tab()
    widget.refresh_runs()
    item = next(
        widget.run_list.item(index)
        for index in range(widget.run_list.count())
        if widget.run_list.item(index).data(Qt.ItemDataRole.UserRole) == run_id
    )
    item.setSelected(True)

    widget.open_selected_recommendation_run()

    assert reopened._execution_generation == 2
    assert reopened.current_recommendation_portfolio_result is None
    assert reopened.current_recommendation_registry_run_id is None


def test_registry_portfolio_save_rejects_non_dto_before_side_effects(
    qt_app: QApplication,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    registry = MagicMock()
    view = _view(config, registry)
    result = SimpleNamespace(
        summary={"status": "completed"},
        equity_curve=pd.DataFrame([{"value": 1}]),
        trades=pd.DataFrame([{"stock_code": "2330"}]),
        details={},
    )
    view.current_recommendation_portfolio_result = result

    def unexpected_composition(*_args: object, **_kwargs: object) -> None:
        pytest.fail("legacy fake result 不得建立 R012 lineage composition")

    monkeypatch.setattr(
        "app_module.recommendation.composition.build_recommendation_composition",
        unexpected_composition,
    )

    with pytest.raises(TypeError, match="RecommendationPortfolioBacktestResultDTO"):
        view._save_recommendation_portfolio_to_research_registry(
            "舊相容結果", "不含完整 DTO"
        )

    registry.save_run.assert_not_called()


def test_interactive_registry_save_keeps_legacy_history_controls_separate(
    qt_app: QApplication,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    registry = ResearchRunService(config)
    view = _view(config, registry)
    parent_result_id = "portfolio-parent-ui-r020-interactive"
    result = _result(parent_result_id, include_child=True)
    view.current_recommendation_portfolio_result = result
    view.portfolio_run_repository.list_runs.return_value = [
        {
            "run_id": "legacy-portfolio-run",
            "run_name": "舊格式回測",
            "total_return": 0.01,
            "created_at": "2026-09-24T10:00:00-07:00",
        }
    ]
    view.delete_portfolio_result_btn.setEnabled(True)
    view.promote_portfolio_result_btn.setEnabled(True)
    messages: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        QDialog,
        "exec",
        lambda _dialog: QDialog.DialogCode.Accepted,
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: messages.append(args),
    )

    view._save_recommendation_portfolio_result()
    qt_app.processEvents()

    run_id = view.current_recommendation_registry_run_id
    assert run_id is not None
    assert view.current_portfolio_run_id is None
    assert view.delete_portfolio_result_btn.isEnabled() is False
    assert view.promote_portfolio_result_btn.isEnabled() is False
    assert view.portfolio_history_combo.findData("legacy-portfolio-run") >= 0
    assert view.portfolio_history_combo.findData(run_id) == -1
    assert len(messages) == 1
    success_text = str(messages[0][2])
    assert "已保存到 Research Run Registry" in success_text
    assert "歷史推薦回測」下拉選單目前僅顯示舊格式紀錄" in success_text
