"""無來源個股研究可恢復，且切股／日期錯誤不能套錯 Advice。"""
from datetime import date
import time,json
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from app_module.stock_research_report_service import StockResearchReportReadService
from app_module.research_session import ResearchStockContextDTO
from ui_qt.views.stock_research_report_view import StockResearchReportView
from tests.test_stock_research_report_service import _config,_seed_normal


def wait_idle(app, view):
    deadline=time.monotonic()+10
    while view.is_busy() and time.monotonic()<deadline:
        app.processEvents();time.sleep(0.01)
    app.processEvents();assert not view.is_busy()


def test_no_source_keeps_independent_rules_and_explicit_valid_choices(tmp_path):
    config=_config(tmp_path);_seed_normal(config)
    report=StockResearchReportReadService(config).read_report('2330',as_of_date=date(2026,9,8))
    assert report.advice.recommendation is None
    assert any('技術觀察' in reason for reason in report.rule_reasons)
    assert [option.result_id for option in report.saved_source_options]==['run-1']
    assert all('勝率' not in reason or '不是推薦或勝率' in reason for reason in report.rule_reasons)


def test_source_picker_loads_exact_run_then_switching_stock_rejects_wrong_advice(tmp_path):
    config=_config(tmp_path);_seed_normal(config)
    app=QApplication.instance() or QApplication([])
    view=StockResearchReportView(StockResearchReportReadService(config))
    view.show();view.set_context(ResearchStockContextDTO(stock_code='2330',decision_date='2026-09-08',source_workspace='watchlist'))
    wait_idle(app,view)
    for index in range(view.tabs.count()):
        if 'Rule' in view.tabs.tabText(index):view.tabs.setCurrentIndex(index);break
    app.processEvents()
    assert view.saved_source_combo.currentData() is None
    view.saved_source_combo.setCurrentIndex(1)
    QTest.mouseClick(view.use_saved_source_button,Qt.LeftButton);wait_idle(app,view)
    assert view.context.result_id=='run-1'
    assert view._loaded_report.advice.recommendation is not None
    view.stock_search.setText('1101');QTest.mouseClick(view.load_button,Qt.LeftButton);wait_idle(app,view)
    assert view._loaded_report.stock_code=='1101'
    assert view._loaded_report.advice.recommendation is None
    assert not view._loaded_report.saved_source_options
    view.close();app.processEvents()


def test_future_source_is_not_offered(tmp_path):
    config=_config(tmp_path);_seed_normal(config)
    artifact=config.output_root/'recommendation/runs/run-1.json'
    payload=json.loads(artifact.read_text(encoding='utf8'))
    payload['run_context']['as_of_date']='2026-09-09'
    artifact.write_text(json.dumps(payload),encoding='utf8')
    report=StockResearchReportReadService(config).read_report('2330',as_of_date='2026-09-08')
    assert not report.saved_source_options
    assert report.advice.recommendation is None


def test_unverified_old_openapi_units_are_not_numeric_research(tmp_path):
    import sqlite3
    from datetime import datetime, timezone
    from data_module.current_fundamental_snapshots import SCHEMA, COLUMNS
    config = _config(tmp_path); _seed_normal(config)
    with sqlite3.connect(config.db_file) as conn:
        conn.executescript(SCHEMA)
        row = dict(zip(COLUMNS, (
            "2330", "statement_item", "2026-Q2", "2026-06-30", "old-api-item",
            "舊 API 金額", "123000", "TWD", "2026-09-07T00:00:00+00:00",
            "https://www.tpex.org.tw/openapi/v1/test",
            "official-openapi-statement-endpoints.v1:sha256:test", "tpex",
        )))
        conn.execute(f"INSERT INTO fundamental_current_observations ({','.join(COLUMNS)}) VALUES ({','.join('?' for _ in COLUMNS)})", tuple(row[k] for k in COLUMNS))
    service = StockResearchReportReadService(config, clock=lambda: datetime(2026,9,8,tzinfo=timezone.utc))
    rows, _, _ = service._read_fundamentals("2330", date(2026,9,8), include_current=True)
    found = next(row for row in rows if row.label == "舊 API 金額")
    assert found.value is None and found.unit == ""
    assert "單位契約尚未驗證" in found.value_text
    with sqlite3.connect(config.db_file) as conn:
        assert conn.execute("SELECT value,unit FROM fundamental_current_observations WHERE item_code='old-api-item'").fetchone() == ("123000", "TWD")
