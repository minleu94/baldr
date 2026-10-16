"""舊格式推薦只讀清單到個股追蹤的原路徑回歸。"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from app_module.research_session import ResearchStockContextDTO
from tests.test_c1_legacy_query_readiness import _install_legacy_row, _stack
from tests.test_ui_qt_personal_recommendation_choice import (
    _IsolatedRecommendationConfig,
    _make_view,
    _wait_for_saved_result_load,
    qt_app,
)


def test_legacy_saved_source_opens_read_only_stock_journey_and_returns(
    qt_app: QApplication,
) -> None:
    with TemporaryDirectory(prefix=".tmp_ui_legacy_journey_", dir=Path.cwd()) as root:
        isolated_root = Path(root).resolve()
        store, _, queries = _stack(isolated_root)
        raw_path, raw_before = _install_legacy_row(store.database_path.parent)
        database_before = hashlib.sha256(store.database_path.read_bytes()).hexdigest()
        source_models = queries.list()
        assert len(source_models) == 1
        view = _make_view()
        view.config = _IsolatedRecommendationConfig(isolated_root / "output")
        view.recommendation_composition = SimpleNamespace(queries=queries)
        contexts: list[ResearchStockContextDTO] = []
        view.stockResearchRequested.connect(contexts.append)
        try:
            view._refresh_saved_sources()
            worker = view._saved_source_list_worker
            assert worker is not None and worker.wait(10_000)
            qt_app.processEvents()
            qt_app.processEvents()
            assert view.saved_source_combo.count() == 2, view.result_status_label.text()
            assert "舊格式推薦／唯讀" in view.saved_source_combo.itemText(1)
            assert "僅當次原件雜湊" in view.saved_source_combo.itemText(1)

            view.saved_source_combo.setCurrentIndex(1)
            view._load_saved_recommendation_result()
            _wait_for_saved_result_load(view, qt_app)
            assert view.current_execution is None
            assert view.current_read_model is not None
            assert view.current_read_model.legacy_result is not None
            assert view._verified_saved_result_id() == ""
            assert view._verified_legacy_result_id() == "c1-r016-legacy"
            assert view.recommendations_model.getDataFrame().iloc[0]["證券代號"] == "2330"
            assert "沒有獨立可信值" in view.result_status_label.text()
            assert not view.save_result_btn.isVisible()
            assert not view.add_to_watchlist_btn.isVisible()
            assert not view.select_stock("2330", result_id="another-result")
            assert view.select_stock("2330", result_id="c1-r016-legacy")
            view._open_selected_stock_research()
            assert len(contexts) == 1
            context = contexts[0]
            assert context.stock_code == "2330"
            assert context.result_id == "c1-r016-legacy"
            assert context.source_workspace == "recommendation"
            assert context.source_kind == "recommendation"
            assert context.data_date == ""
            assert "歷史可得性未獨立驗證" in context.source_label
            assert view.select_stock(context.stock_code, result_id=context.result_id)
            original_read_model = view.current_read_model
            view._on_saved_result_load_finished(
                replace(original_read_model, raw_artifact_sha256="sha256:" + "0" * 64),
                "c1-r016-legacy",
                view._saved_result_load_generation,
                view._loaded_saved_result_identity,
            )
            assert view.current_read_model is original_read_model
            assert "原畫面保留" in view.result_status_label.text()
            assert raw_path.read_bytes() == raw_before
            assert hashlib.sha256(store.database_path.read_bytes()).hexdigest() == database_before
            assert not store.artifact_root.exists()
        finally:
            view.close()
            qt_app.processEvents()
