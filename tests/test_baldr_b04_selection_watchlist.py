"""B04 保存來源、局部篩選與視窗查看狀態的限定驗證。"""
from dataclasses import replace
import hashlib
import os
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from tests.test_personal_recommendation_choice import _canonical_rule_only_query_fixture
from tests.test_ui_qt_personal_recommendation_choice import _make_view, _wait_for_saved_result_load
from tests.test_ui_qt_recommendation_execution import _execution
from tests.test_ux04_05_daily_market_research_view import _FakeScreener, _wait, _MANIFEST_SHA
from ui_qt.views.daily_market_research_view import DailyMarketResearchView
from ui_qt.views.watchlist_view import WatchlistView
from app_module.recommendation.composition import build_recommendation_composition


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def _saved_model(result_id="b04-synthetic-result"):
    queries, _ = _canonical_rule_only_query_fixture(result_id)
    return queries.get(result_id)


def _source_view(tmp_path, model):
    view = _make_view(personal_policy_path=tmp_path / "absent-policy.json")
    view.config = SimpleNamespace(output_root=tmp_path)
    calls = []

    def get(result_id):
        calls.append(result_id)
        return model

    view.recommendation_composition = SimpleNamespace(
        queries=SimpleNamespace(list=lambda: (model,), get=get)
    )
    return view, calls


def _read_options(view, app):
    view._refresh_saved_sources()
    worker = view._saved_source_list_worker
    assert worker is not None
    assert worker.wait(10_000)
    app.processEvents()
    app.processEvents()


def test_saved_source_selection_loads_exact_identity_without_typing(app, tmp_path):
    model = _saved_model()
    view, calls = _source_view(tmp_path, model)
    try:
        assert view.personal_capture_widget.isHidden()
        assert view.personal_assessment_group.isHidden()
        view.personal_research_toggle.setChecked(True)
        assert not view.personal_assessment_group.isHidden()
        _read_options(view, app)
        assert view.saved_source_combo.count() == 2
        assert view.saved_result_id_input.text() == ""
        view.saved_source_combo.setCurrentIndex(1)
        view._load_saved_recommendation_result()
        _wait_for_saved_result_load(view, app)
        assert calls == [model.result_id]
        assert view.current_read_model is model
        assert view._loaded_saved_result_identity == tuple(view.saved_source_combo.currentData())
        assert view.current_save_receipt is None
        assert view.personal_research_toggle.isChecked()
    finally:
        view.close()
        app.processEvents()


def test_real_synthetic_store_chooser_read_and_stock_context_preserve_saved_bytes(app, tmp_path):
    class Config:
        output_root = tmp_path / "output"

        def resolve_output_path(self, name):
            path = self.output_root / name
            path.mkdir(parents=True, exist_ok=True)
            return path

    config = Config()
    composition = build_recommendation_composition(config)
    execution = _execution("b04-real-synthetic")
    composition.save_service.save_execution(execution, label="合成保存推薦")
    composition.save_service.save_execution(_execution("b04-empty-synthetic", empty=True), label="合成空結果")

    def pins():
        return {str(path.relative_to(composition.runs_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in composition.runs_dir.rglob("*") if path.is_file()}

    before = pins()
    view = _make_view(personal_policy_path=tmp_path / "absent-policy.json")
    view.config = config
    view.recommendation_composition = composition
    contexts = []
    view.stockResearchRequested.connect(contexts.append)
    try:
        _read_options(view, app)
        assert view.saved_source_combo.count() == 3
        index = next(i for i in range(1, 3) if view.saved_source_combo.itemData(i)[3] == execution.result_id)
        empty_index = next(i for i in range(1, 3) if i != index)
        assert "非推薦" in view.saved_source_combo.itemText(empty_index)
        view.saved_source_combo.setCurrentIndex(index)
        view._load_saved_recommendation_result()
        _wait_for_saved_result_load(view, app)
        assert view.current_execution == execution
        view.results_table.selectRow(0)
        view._open_selected_stock_research()
        assert len(contexts) == 1
        assert contexts[0].result_id == execution.result_id
        assert contexts[0].stock_code == "2330"
        assert contexts[0].decision_date == execution.context.as_of_date.isoformat()
        assert pins() == before
    finally:
        view.close()
        app.processEvents()


def test_selected_source_revision_changed_keeps_last_good_result(app, tmp_path):
    model = _saved_model()
    view, _ = _source_view(tmp_path, model)
    try:
        _read_options(view, app)
        view.saved_source_combo.setCurrentIndex(1)
        prior = object()
        view.current_execution = prior
        view.recommendation_composition.queries.get = lambda _id: replace(model, raw_artifact_sha256="d" * 64)
        view._load_saved_recommendation_result()
        _wait_for_saved_result_load(view, app)
        assert view.current_execution is prior
        assert view.current_read_model is None
        assert "來源已變動" in view.result_status_label.text()
    finally:
        view.close()
        app.processEvents()


def test_unreadable_unknown_source_is_not_selectable(app, tmp_path):
    model = _saved_model()
    view, calls = _source_view(tmp_path, model)
    try:
        view.recommendation_composition.queries.list = lambda: (
            replace(model, integrity_basis="legacy_read_time_hash_only"), None,
        )
        _read_options(view, app)
        assert view.saved_source_combo.count() == 1
        assert view.saved_source_combo.currentData() is None
        assert "缺件 2" in view.result_status_label.text()
        view._load_saved_recommendation_result()
        assert calls == []
    finally:
        view.close()
        app.processEvents()


@pytest.mark.parametrize("operation", ["options", "one_result"])
def test_source_cancel_rejects_late_callback_and_keeps_last_good(app, tmp_path, operation):
    model = _saved_model()
    view, _ = _source_view(tmp_path, model)
    entered, release = threading.Event(), threading.Event()

    def delayed(*_args):
        entered.set()
        assert release.wait(5)
        return (model,) if operation == "options" else model

    prior = object()
    view.current_execution = prior
    try:
        if operation == "options":
            view.recommendation_composition.queries.list = delayed
            view._refresh_saved_sources()
            worker = view._saved_source_list_worker
        else:
            _read_options(view, app)
            view.saved_source_combo.setCurrentIndex(1)
            view.recommendation_composition.queries.get = delayed
            view._load_saved_recommendation_result()
            worker = view._saved_result_load_worker
        assert entered.wait(2)
        view._cancel_saved_source_read()
        release.set()
        assert worker.wait(10_000)
        app.processEvents()
        app.processEvents()
        assert view.current_execution is prior
        assert view.current_read_model is None
        assert "已取消" in view.result_status_label.text()
        if operation == "options":
            assert view.saved_source_combo.count() == 1
    finally:
        release.set()
        view.close()
        app.processEvents()


def test_source_error_and_stale_options_keep_previous_selection(app, tmp_path):
    model = _saved_model()
    view, _ = _source_view(tmp_path, model)
    try:
        _read_options(view, app)
        view.saved_source_combo.setCurrentIndex(1)
        identity = view.saved_source_combo.currentData()
        generation = view._saved_source_list_generation
        view._on_saved_sources_finished((), generation - 1)
        view._on_saved_sources_error("broken index", generation)
        assert view.saved_source_combo.currentData() == identity
        assert "保留原選項" in view.result_status_label.text()
    finally:
        view.close()
        app.processEvents()


def test_local_stock_filter_preserves_full_denominator_unknown_and_exact_return(app):
    service = _FakeScreener()
    view = DailyMarketResearchView(service)
    try:
        view.on_first_open()
        _wait(view)
        full_rows = view._all_rows
        calls = list(service.calls)
        summary = view.summary_label.text()
        view.local_stock_filter.setText("1477")
        assert view.results_table.rowCount() == 1
        assert "資料不足" in view.results_table.item(0, 4).text() or "未知" in view.results_table.item(0, 4).text()
        assert view._all_rows == full_rows
        assert view.summary_label.text() == summary
        assert service.calls == calls
        assert service.produce_calls == []
        assert not view.restore_research_snapshot_stock("2382", _MANIFEST_SHA)
        view.local_stock_filter.clear()
        assert view.restore_research_snapshot_stock("2382", _MANIFEST_SHA)
        assert not view.restore_research_snapshot_stock("2382", "f" * 64)
    finally:
        view.close()
        app.processEvents()


def test_unconfigured_observation_state_refuses_writer_and_does_not_write_evidence(app):
    service = MagicMock()
    rows = [
        {"stock_code": "2330", "stock_name": "合成", "source": "manual", "source_id": source,
         "added_at": "2026-10-05 10:00:00", "notes": "觀察原因"}
        for source in ("first-version", "second-version")
    ]
    service.get_stocks.return_value = rows
    view = WatchlistView(service)
    view._request_stock_summary = lambda *_args: None
    try:
        before = view.stocks_model.getDataFrame().copy(deep=True)
        view.stocks_table.selectRow(0)
        view.confirm_observation_button.click()
        assert not view.confirm_observation_button.isEnabled()
        assert "目前不可保存" in view.observation_state_label.text()
        assert "觀察原因" in view.observation_reason_label.text()
        assert "未知" in view.observation_change_label.text()
        view.stocks_table.clearSelection()
        view.stocks_table.selectRow(1)
        assert "目前不可保存" in view.observation_state_label.text()
        view.later_observation_button.click()
        assert not view.later_observation_button.isEnabled()
        view.stocks_table.clearSelection()
        view.stocks_table.selectRow(0)
        assert "目前不可保存" in view.observation_state_label.text()
        assert view.stocks_model.getDataFrame().equals(before)
        service.add_stocks.assert_not_called()
        service.bind_stock_decision_identity.assert_not_called()
        service.save_review_state.assert_not_called()
        view.stocks_table.clearSelection()
        assert not view.confirm_observation_button.isEnabled()
    finally:
        view.close()
        app.processEvents()
