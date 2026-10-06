"""無來源個股研究可恢復，且切股／日期錯誤不能套錯 Advice。"""
from datetime import date
import time,json
from PySide6.QtWidgets import QApplication, QTableView
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from app_module.stock_research_report_service import StockResearchReportReadService
from app_module.research_session import ResearchStockContextDTO
from ui_qt.views.stock_research_report_view import (
    StockResearchReportView,
    _read_report_with_context_cutoff,
)
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


def test_future_market_data_date_source_is_not_offered_or_composed(tmp_path):
    config = _config(tmp_path)
    _seed_normal(config)
    artifact = config.output_root / "recommendation" / "runs" / "run-1.json"
    payload = json.loads(artifact.read_text(encoding="utf8"))
    payload["run_context"]["data_date"] = "2026-09-09"
    artifact.write_text(json.dumps(payload), encoding="utf8")

    report = StockResearchReportReadService(config).read_report(
        "2330",
        as_of_date="2026-09-08",
        context=ResearchStockContextDTO(stock_code="2330", result_id="run-1"),
    )

    assert report.saved_source_options == ()
    assert report.advice.recommendation is None
    assert report.advice.status == "unavailable"
    assert report.advice.saved_analysis is not None
    assert report.advice.saved_analysis.data_date == "2026-09-09"
    assert any(
        "2026-09-09" in item and "2026-09-08" in item
        for item in report.advice.limitations
    )


def test_unlinked_portfolio_quote_date_is_shown_without_last_trade_substitution(tmp_path):
    config = _config(tmp_path)
    view = StockResearchReportView(StockResearchReportReadService(config))
    context = ResearchStockContextDTO(
        stock_code="2382",
        data_date="2026-10-02",
        identity_status="unlinked",
        source_workspace="portfolio",
    )

    view.set_context(context)

    assert "2026-10-02" in view.context_path_label.text()
    assert "2026-07-31" not in view.context_path_label.text()
    assert view.context is context
    view.close()


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
                "unknown", "0", "0", "",
        )))
        conn.execute(f"INSERT INTO fundamental_current_observations ({','.join(COLUMNS)}) VALUES ({','.join('?' for _ in COLUMNS)})", tuple(row[k] for k in COLUMNS))
    service = StockResearchReportReadService(config, clock=lambda: datetime(2026,9,8,tzinfo=timezone.utc))
    rows, _, _ = service._read_fundamentals("2330", date(2026,9,8), include_current=True)
    found = next(row for row in rows if row.label == "舊 API 金額")
    assert found.value is None and found.unit == ""
    assert "單位契約尚未驗證" in found.value_text
    with sqlite3.connect(config.db_file) as conn:
        assert conn.execute("SELECT value,unit FROM fundamental_current_observations WHERE item_code='old-api-item'").fetchone() == ("123000", "TWD")


def test_manual_ui_route_reads_current_fundamentals_but_date_bound_route_keeps_pit(tmp_path):
    import sqlite3
    from datetime import datetime, timezone
    from decimal import Decimal

    from data_module.current_fundamental_snapshots import COLUMNS, SCHEMA

    config = _config(tmp_path)
    _seed_normal(config)
    with sqlite3.connect(config.db_file) as conn:
        conn.executescript(SCHEMA)
        row = dict(
            zip(
                COLUMNS,
                (
                    "2330",
                    "statement_item",
                    "2026-Q2",
                    "2026-06-30",
                    "current-revenue",
                    "本期營收觀測",
                    "987654",
                    "TWD",
                    "2026-09-08T08:00:00+00:00",
                    "https://official.example/current-statement",
                    "current-snapshot-test.v1",
                    "twse",
                    "unknown",
                    "0",
                    "0",
                    "",
                ),
            )
        )
        conn.execute(
            f"INSERT INTO fundamental_current_observations ({','.join(COLUMNS)}) "
            f"VALUES ({','.join('?' for _ in COLUMNS)})",
            tuple(row[key] for key in COLUMNS),
        )

    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 9, 8, 9, tzinfo=timezone.utc),
    )
    manual_context = ResearchStockContextDTO(
        stock_code="2330",
        source_workspace="watchlist",
    )
    manual_report = _read_report_with_context_cutoff(
        service,
        "2330",
        context=manual_context,
    )
    current_observation = next(
        row for row in manual_report.fundamentals if row.label == "本期營收觀測"
    )
    assert current_observation.value == Decimal("987654")
    assert current_observation.unit == "TWD"
    assert current_observation.source_id == "sqlite.fundamental_current_observations"

    app = QApplication.instance() or QApplication([])
    view = StockResearchReportView(service)
    view.set_context(manual_context)
    wait_idle(app, view)
    view.tabs.setCurrentIndex(2)
    app.processEvents()
    fundamentals_tables = view.tabs.widget(2).findChildren(QTableView)
    rendered_cells = [
        fundamentals_tables[0].model().index(row, column).data()
        for row in range(fundamentals_tables[0].model().rowCount())
        for column in range(fundamentals_tables[0].model().columnCount())
    ]
    assert any("本期營收觀測" in str(cell) for cell in rendered_cells)
    assert any("987,654" in str(cell) for cell in rendered_cells)
    view.close()
    app.processEvents()

    date_bound_report = _read_report_with_context_cutoff(
        service,
        "2330",
        context=ResearchStockContextDTO(
            stock_code="2330",
            decision_date="2026-09-08",
            source_workspace="watchlist",
        ),
    )
    assert all(
        row.label != "本期營收觀測" for row in date_bound_report.fundamentals
    )


def test_formal_execution_market_date_provenance_roundtrips_without_data_snapshot_ref(
    tmp_path,
):
    from app_module.recommendation.codec import decode_execution, encode_execution
    from app_module.recommendation.contracts import ExecutionStatus
    from app_module.recommendation.execute import execute_recommendation
    from tests.test_recommendation_execution_use_case import (
        _config as execution_config,
        _service as execution_service,
    )

    from decimal import Decimal

    service = execution_service(tmp_path, ("AAA",), {"AAA": Decimal("88.5")})
    capture = {}
    execution = execute_recommendation(
        service,
        execution_config("2026-05-21"),
        top_n=1,
        result_id="source-recovery-formal-market-date",
        capture_sink=capture,
    )

    assert execution.status is ExecutionStatus.COMPLETED
    assert execution.context.as_of_date == date(2026, 5, 21)
    assert execution.context.data_snapshot_refs == ()
    legacy_context = capture["compatibility_snapshot"].materialize()[
        "last_run_context"
    ]
    event = next(
        item for item in execution.events if item.event_type == "legacy_invocation_context"
    )
    provenance = event.details["market_data_provenance"]
    captured_data_date = legacy_context["data_date"]
    if isinstance(captured_data_date, date):
        captured_data_date = captured_data_date.isoformat()
    assert captured_data_date == "2026-05-20"
    expected_decision_at = (
        execution.context.decision_at.isoformat()
        if execution.context.decision_at is not None
        else None
    )
    assert dict(provenance) == {
        "schema_version": "recommendation-market-data-provenance.v1",
        "result_id": execution.result_id,
        "invocation_id": event.details["invocation_id"],
        "scope": "formal_pit",
        "as_of_date": execution.context.as_of_date.isoformat(),
        "data_date": captured_data_date,
        "decision_at": expected_decision_at,
        "source_id": legacy_context["source_id"],
        "market_data_fingerprint": legacy_context["market_data_fingerprint"],
    }
    assert event.details["result_id"] == provenance["result_id"]
    assert event.details["source_id"] == provenance["source_id"]
    assert event.details["market_data_fingerprint"] == provenance[
        "market_data_fingerprint"
    ]
    assert event.details["current_market_status_preflight_diagnostics"] == ()
    assert not {
        "available_at",
        "pit_eligible",
        "formal_pit_eligible",
    }.intersection(provenance)

    reopened = decode_execution(encode_execution(execution))
    reopened_event = next(
        item
        for item in reopened.events
        if item.event_type == "legacy_invocation_context"
    )
    assert reopened_event.details["market_data_provenance"] == provenance
    assert reopened_event.details["current_market_status_preflight_diagnostics"] == ()
