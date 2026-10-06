"""UX08 同次推薦 writer → 新程序保存來源研究圖表整合。"""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import json
import os
import subprocess
import sys
from unittest.mock import Mock

import pytest
from app_module.recommendation.execute import execute_recommendation
from app_module.recommendation.contracts import ExecutionStatus
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.save import RecommendationSaveService
from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_service import StockResearchReportReadService
from app_module.stock_research_chart_payload import project_stock_chart_payload
from data_module.result_artifact_store import ResultArtifactStore
from tests.test_recommendation_execution_use_case import _service, _config, _market_frame, _FrameProvider


def produce(tmp_path):
    frame = _market_frame("2330")
    frame["開盤價"] = Decimal("98.125")
    frame["最高價"] = Decimal("102.125")
    frame["最低價"] = Decimal("97.125")
    frame["收盤價"] = Decimal("100.125")
    frame["成交金額"] = Decimal("100125")
    frame["MA20"] = Decimal("99.123456")
    frame["MA60"] = None
    class CountedProvider(_FrameProvider):
        calls = 0

        def __call__(self):
            self.calls += 1
            return super().__call__()

    provider = CountedProvider(frame)
    service = _service(tmp_path, ("2330",), {"2330": Decimal("90")}, provider=provider, output_root=tmp_path)
    execution = execute_recommendation(service, _config(), top_n=1, result_id="ux08-chart-exact")
    assert execution.status is ExecutionStatus.COMPLETED
    assert provider.calls == 1
    capture = next(e.details for e in execution.events if e.event_type == "recommendation_saved_technical_charts")
    assert capture["chart_count"] == 1, dict(capture)
    runs = tmp_path / "recommendation" / "runs"
    persistence = RecommendationExecutionPersistence(ResultArtifactStore(
        artifact_root=runs / "execution_artifacts", database_path=runs / "recommendation_runs.db"))
    receipt = RecommendationSaveService(persistence).save_execution(execution)
    config = SimpleNamespace(output_root=tmp_path, db_file=tmp_path / "missing.sqlite", use_sqlite=False)
    context = ResearchStockContextDTO(stock_code="2330", result_id=execution.result_id,
        source_id=execution.result_id, decision_date="2026-05-20", data_date="2026-05-20",
        source_kind="recommendation", source_workspace="recommendation", ml_scope_mode="selected_saved_decision")
    return frame, service, execution, receipt, config, context


def reader(config):
    result = StockResearchReportReadService(config, clock=lambda: datetime(2026, 10, 6, tzinfo=timezone.utc))
    result._read_prices = Mock(side_effect=AssertionError("保存圖不可讀現況價格"))
    result._read_technical = Mock(side_effect=AssertionError("保存圖不可读現況MA"))
    result._read_technical_history = Mock(side_effect=AssertionError("保存圖不可讀現況MA歷史"))
    return result


def test_writer_save_reopen_exact_projection_and_new_process(tmp_path):
    frame, service, execution, receipt, config, context = produce(tmp_path)
    frame["收盤價"] = Decimal("999")
    service.last_run_context.clear()
    report = reader(config).read_report("2330", as_of_date="2026-05-20", context=context)
    assert len(report.price_points) == 20
    assert report.price_points[-1].close_price == Decimal("100.125")
    assert report.technical_history[-1].ma20 == Decimal("99.123456")
    assert report.technical_history[-1].ma60 is None
    projection = project_stock_chart_payload(report, expected_source_context={"result_id": execution.result_id})
    assert projection.status == "unknown" and projection.payload is not None, projection
    assert not projection.payload.historical_pit_eligible
    script = """from pathlib import Path
from types import SimpleNamespace
from app_module.stock_research_report_service import StockResearchReportReadService
from app_module.research_session import ResearchStockContextDTO
import sys,json
cfg=SimpleNamespace(output_root=Path(sys.argv[1]),db_file=Path(sys.argv[1])/'missing.sqlite',use_sqlite=False)
c=ResearchStockContextDTO(stock_code='2330',result_id='ux08-chart-exact',source_id='ux08-chart-exact',decision_date='2026-05-20',source_kind='recommendation')
r=StockResearchReportReadService(cfg).read_report('2330',as_of_date='2026-05-20',context=c)
print(json.dumps({'chart':r.saved_technical_chart_json,'close':str(r.price_points[-1].close_price),'ma20':str(r.technical_history[-1].ma20)}))
"""
    output = subprocess.run([sys.executable, "-c", script, str(tmp_path)], check=True, capture_output=True,
                            text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    reopened = json.loads(output.stdout.strip().splitlines()[-1])
    assert reopened["chart"] == report.saved_technical_chart_json
    assert reopened["close"] == "100.125" and reopened["ma20"] == "99.123456"


@pytest.mark.parametrize("changes,day", [({"result_id":"other"},"2026-05-20"),
    ({"source_id":"other"},"2026-05-20"), ({"data_date":"2026-05-19"},"2026-05-20"),
    ({"stock_code":"2317"},"2026-05-20"), ({},"2026-05-21"),
    ({"ml_scope_mode":"current_stock_research", "result_id":"missing"},"2026-05-20")])
def test_source_binding_rejects_without_current_fallback(tmp_path, changes, day):
    *_, config, context = produce(tmp_path)
    report = reader(config).read_report("2330", as_of_date=day, context=replace(context, **changes))
    assert not report.price_points and not report.saved_technical_chart_json
    assert not report.technical_history


def test_missing_ohlc_does_not_fail_recommendation(tmp_path):
    service = _service(tmp_path, ("2330",), {"2330": Decimal("90")}, output_root=tmp_path)
    execution = execute_recommendation(service, _config(), top_n=1, result_id="ux08-missing")
    assert execution.status is ExecutionStatus.COMPLETED
    capture = next(e.details for e in execution.events if e.event_type == "recommendation_saved_technical_charts")
    assert capture["selected_count"] == capture["missing_count"] == 1
    assert capture["chart_count"] == 0


from tests.test_scheduled_recommendation_date_roles import base_execution, execution as scheduled_execution
from app_module.recommendation_saved_chart import build_recommendation_chart_capture
from app_module.recommendation.contracts import ExecutionEvent
from zoneinfo import ZoneInfo


@pytest.mark.parametrize("day,expected", [("2026-10-03", True), ("2026-10-02", False)])
def test_scheduled_decision_day_keeps_original_market_cutoff(tmp_path, base_execution, day, expected):
    value = scheduled_execution(base_execution)
    frame = _market_frame("2330")
    for column in ("開盤價", "最高價", "最低價"):
        frame[column] = Decimal("100")
    frame["MA20"] = Decimal("99.123456")
    codes = tuple(item.stock_code for item in value.items)
    capture = build_recommendation_chart_capture(frame=frame, stock_column="證券代號",
        stock_codes=codes, result_id=value.result_id, source_id="scheduled_fixture",
        market_data_fingerprint="same-frame-version", decision_cutoff=datetime(2026,10,2,23,59,59,999999,tzinfo=ZoneInfo("Asia/Taipei")))
    events = tuple(replace(event, details={**dict(event.details), "source_id":"scheduled_fixture", "market_data_fingerprint":"same-frame-version"})
                   if event.event_type == "legacy_invocation_context" else event for event in value.events)
    value = replace(value, events=events+(ExecutionEvent(event_type="recommendation_saved_technical_charts",
        message="隔離圖表fixture", occurred_at=value.context.decision_at, details=capture),))
    runs = tmp_path / "recommendation" / "runs"
    RecommendationSaveService(RecommendationExecutionPersistence(ResultArtifactStore(
        artifact_root=runs/"execution_artifacts",database_path=runs/"recommendation_runs.db"))).save_execution(value)
    cfg = SimpleNamespace(output_root=tmp_path, db_file=tmp_path/"missing.sqlite", use_sqlite=False)
    context = ResearchStockContextDTO(stock_code="2330",result_id=value.result_id,source_id=value.result_id,
        decision_date="2026-10-03",source_kind="recommendation")
    report = reader(cfg).read_report("2330",as_of_date=day,context=context)
    assert bool(report.saved_technical_chart_json) is expected, report.limitations
    if expected:
        assert json.loads(report.saved_technical_chart_json)["decision_cutoff"].startswith("2026-10-02")
        projected = project_stock_chart_payload(report, expected_source_context={"result_id":value.result_id})
        assert projected.payload is not None, projected
