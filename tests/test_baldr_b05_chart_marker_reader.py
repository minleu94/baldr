"""合成原 store 保存、唯讀 custody、繪圖及跨程序回歸。"""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QTableView

from app_module.decision_outcome_journey import JsonlJournalReadAdapter, JsonlPortfolioTradeReadAdapter
from app_module.dtos.decision_continuity_dtos import DecisionIdentity
from app_module.dtos.portfolio_dtos import TradeDTO
from app_module.journal_service import JournalService
from app_module.portfolio_store import PortfolioJsonlStore
from app_module.stock_research_chart_marker_reader import (
    StockChartMarkerReadRequest, StockChartMarkerRecordSource, StockResearchChartMarkerReader,
    stock_chart_saved_record_sha256,
)
from app_module.stock_research_chart_payload import project_stock_chart_payload
from tests.test_stock_research_chart_payload import _point, _report, _CONTEXT
from tests.test_ui_qt_saved_stock_chart import app
from ui_qt.views.stock_research_report_view import StockResearchReportView

CONTEXT = {**_CONTEXT, "source_snapshot_hash": "c" * 64}
POINTS = (_point("2026-10-08"),)


def saved_fixture(tmp_path, kind):
    store = PortfolioJsonlStore(tmp_path)
    if kind == "trade":
        store.append_trade(TradeDTO("trade-a", "account-a", "2330", "synthetic", "buy", 1, 100,
            "2026-10-08", source_type="recommendation", source_id="source-a",
            source_snapshot_hash=CONTEXT["source_snapshot_hash"], source_summary={**CONTEXT,"account_kind":"actual"},
            created_at="2026-10-08T15:00:00+08:00").to_dict())
        callback = JsonlPortfolioTradeReadAdapter(store.trades_file).list_trades
        source = StockChartMarkerRecordSource.ACTUAL_TRADES
        path = store.trades_file
        key = "trade_id"
    else:
        identity = DecisionIdentity(result_id=CONTEXT["result_id"], stock_code="2330",
            source_snapshot_id=CONTEXT["source_snapshot_id"], source_snapshot_hash=CONTEXT["source_snapshot_hash"],
            decision_date=CONTEXT["decision_date"])
        JournalService(SimpleNamespace(output_root=tmp_path)).accept_decision(identity,
            portfolio_id="account-a", source_id="source-a", revision_id="revision-a",
            recorded_at="2026-10-08T15:00:00+08:00")
        callback = JsonlJournalReadAdapter(store.journal_file)._records
        source = StockChartMarkerRecordSource.RECOMMENDATION_CONFIRMATIONS
        path = store.journal_file
        key = "revision_id"
    # Custody pins originate in original saved rows BEFORE any display candidate exists.
    rows = callback()
    pins = tuple((row[key], stock_chart_saved_record_sha256(row)) for row in rows)
    assert tuple(sha256(line).hexdigest() for line in path.read_bytes().splitlines()) == tuple(value for _,value in pins)
    request = StockChartMarkerReadRequest(source, "2330", "2026-10-08", "account-a", "source-a",
        CONTEXT["result_id"], CONTEXT["decision_date"], CONTEXT["source_snapshot_id"],
        CONTEXT["source_snapshot_hash"], tuple(sorted(CONTEXT.items())), pins)
    reader = StockResearchChartMarkerReader(**{
        "trade_records" if kind == "trade" else "confirmation_records": callback})
    return reader, request, path, rows


def file_witness(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


def assert_visible(reader, request):
    view = StockResearchReportView(SimpleNamespace())
    try:
        view.set_chart_marker_reader(reader, request)
        view._active_code = "2330"
        view._render_price(_report(*POINTS, context=CONTEXT))
        assert len(view._chart_widget._markers) == 1
        assert view.findChild(QTableView, "stockResearchChartMarkerTable").model().rowCount() == 1
        view._chart_widget._select_point(0)
        assert view._chart_widget._markers[0].label in view._chart_widget.toolTip()
        assert not view._chart_widget.grab().isNull()
        assert view._chart_marker_diagnostics == ()
    finally:
        view.close()


@pytest.mark.parametrize("kind", ["trade", "confirmation"])
def test_original_store_reader_visible_and_new_process(app, tmp_path, kind):
    reader, request, path, rows = saved_fixture(tmp_path, kind)
    before = file_witness(tmp_path)
    result = reader.read(request, price_points=POINTS)
    assert len(result.candidates) == 1 and result.diagnostics == ()
    assert result.identities[0].source_row_hash == request.expected_record_hashes[0][1]
    assert result.historical_pit_eligible is False
    payload = project_stock_chart_payload(_report(*POINTS, context=CONTEXT),
        marker_candidates=result.candidates, marker_identities=result.identities).payload
    assert payload.verified_markers == result.candidates
    assert_visible(reader, request)
    assert file_witness(tmp_path) == before
    # Separate process rereads ORIGINAL rows; custody hashes are carried separately.
    script = '''
import sys,json
from pathlib import Path
sys.path.insert(0, str(Path.cwd()/"tests"))
from PySide6.QtWidgets import QApplication
from tests.test_baldr_b05_chart_marker_reader import *
data=json.loads(sys.argv[1])
kind=data.pop("kind");path=data.pop("path")
data["record_source"]=StockChartMarkerRecordSource(data["record_source"])
data["source_context"]=tuple(map(tuple,data["source_context"]))
data["expected_record_hashes"]=tuple(map(tuple,data["expected_record_hashes"]))
callback=JsonlPortfolioTradeReadAdapter(path).list_trades if kind=="trade" else JsonlJournalReadAdapter(path)._records
reader=StockResearchChartMarkerReader(**{"trade_records" if kind=="trade" else "confirmation_records":callback})
request=StockChartMarkerReadRequest(**data)
app=QApplication([])
assert_visible(reader,request)
print(reader.read(request,price_points=POINTS).candidates[0].content_sha256)
'''
    from dataclasses import asdict
    data = {**asdict(request), "kind":kind, "path":str(path)}
    completed = subprocess.run([sys.executable, "-c", script, json.dumps(data)],
        capture_output=True, text=True, timeout=40, check=True)
    assert completed.stdout.strip() == result.candidates[0].content_sha256
    assert file_witness(tmp_path) == before


@pytest.mark.parametrize("kind", ["trade", "confirmation"])
@pytest.mark.parametrize("field,value,diagnostic", [
    ("account_id", "other", "saved_account_mismatch"),
    ("source_id", "other", "saved_source_mismatch"),
    ("expected_record_hashes", (("missing", "a"*64),), "pinned_record_missing"),
])
def test_wrong_request_identity_rejected(tmp_path, kind, field, value, diagnostic):
    reader, request, *_ = saved_fixture(tmp_path, kind)
    result = reader.read(replace(request, **{field:value}), price_points=POINTS)
    assert not result.candidates and diagnostic in result.diagnostics[0]


@pytest.mark.parametrize("clock,diagnostic", [
    ("", "saved_record_clock_unknown"), ("2026-10-08T15:00:00", "saved_record_clock_unknown"),
    ("2026-10-09T15:00:00+08:00", "saved_record_after_cutoff"),
    ("2026-10-07T15:00:00+08:00", "saved_event_clock_conflict"),
])
def test_saved_clock_unknown_late_or_earlier_cannot_be_filled(tmp_path, clock, diagnostic):
    _, request, _, rows = saved_fixture(tmp_path, "trade")
    row = {**rows[0], "created_at":clock}
    request = replace(request, expected_record_hashes=((row["trade_id"], stock_chart_saved_record_sha256(row)),))
    reader = StockResearchChartMarkerReader(trade_records=lambda:(row,))
    result = reader.read(request, price_points=POINTS)
    assert not result.candidates and diagnostic in result.diagnostics[0]


@pytest.mark.parametrize("kind", ["trade", "confirmation"])
def test_original_row_tamper_fails_frozen_custody_pin(tmp_path, kind):
    _, request, _, rows = saved_fixture(tmp_path, kind)
    changed = {**rows[0], "source_id":"tampered"}
    reader = StockResearchChartMarkerReader(**{
        "trade_records" if kind == "trade" else "confirmation_records":lambda:(changed,)})
    result = reader.read(request, price_points=POINTS)
    assert result.candidates == () and "saved_record_hash_mismatch" in result.diagnostics[0]


def test_cancel_missing_pins_duplicate_and_paper(tmp_path):
    reader, request, _, rows = saved_fixture(tmp_path, "trade")
    assert reader.read(request, price_points=POINTS, cancelled=lambda:True).diagnostics == ("cancelled",)
    assert not reader.read(replace(request, expected_record_hashes=()), price_points=POINTS).candidates
    assert StockResearchChartMarkerReader().read(request, price_points=POINTS).diagnostics == ("readonly_source_unconfigured",)
    duplicate = StockResearchChartMarkerReader(trade_records=lambda:(rows[0], rows[0]))
    assert duplicate.read(request, price_points=POINTS).diagnostics == ("record_identity_ambiguous",)
    row = {**rows[0], "source_type":"paper"}
    paper = StockResearchChartMarkerReader(trade_records=lambda:(row,))
    request = replace(request, expected_record_hashes=((row["trade_id"],stock_chart_saved_record_sha256(row)),))
    assert "paper_trade_rejected" in paper.read(request, price_points=POINTS).diagnostics[0]


def test_view_stale_scope_clears_previously_visible_marker(app, tmp_path):
    reader, request, *_ = saved_fixture(tmp_path, "trade")
    view = StockResearchReportView(SimpleNamespace())
    try:
        view.set_chart_marker_reader(reader, request)
        view._active_code = "2330"
        view._render_price(_report(*POINTS, context=CONTEXT))
        assert len(view._chart_widget._markers) == 1
        view._render_price(_report(*POINTS, context={**CONTEXT,"result_id":"stale"}))
        assert not view._chart_widget._markers
        assert view._chart_marker_diagnostics == ("marker_request_scope_stale",)
    finally:
        view.close()


@pytest.mark.parametrize("field,value,diagnostic", [
    ("stock_code", "2317", "saved_stock_mismatch"),
    ("source_snapshot_hash", "d"*64, "saved_source_mismatch"),
    ("source_summary", {"account_kind":"actual"}, "saved_lineage_mismatch"),
    ("source_summary", {**CONTEXT,"account_kind":"paper"}, "paper_or_declared_trade_rejected"),
    ("schema_version", "unknown", "unsupported_actual_trade"),
])
def test_custody_verified_row_still_requires_saved_identity(tmp_path, field, value, diagnostic):
    _, request, _, rows = saved_fixture(tmp_path, "trade")
    row = {**rows[0], field:value}
    request = replace(request, expected_record_hashes=((row["trade_id"],stock_chart_saved_record_sha256(row)),))
    result = StockResearchChartMarkerReader(trade_records=lambda:(row,)).read(request, price_points=POINTS)
    assert not result.candidates and diagnostic in result.diagnostics[0]


@pytest.mark.parametrize("field,value", [
    ("action", "skipped"), ("stock_code", "2317"),
    ("payload", {}), ("decision_identity", {}),
])
def test_non_confirmation_or_inconsistent_envelope_never_drawn(tmp_path, field, value):
    _, request, _, rows = saved_fixture(tmp_path, "confirmation")
    row = {**rows[0], field:value}
    request = replace(request, expected_record_hashes=((row["revision_id"],stock_chart_saved_record_sha256(row)),))
    result = StockResearchChartMarkerReader(confirmation_records=lambda:(row,)).read(request, price_points=POINTS)
    assert not result.candidates and result.diagnostics


def test_reader_errors_bounds_and_cancellation_after_read(tmp_path):
    _, request, _, rows = saved_fixture(tmp_path, "trade")
    def unavailable():
        raise OSError("source unavailable")
    assert StockResearchChartMarkerReader(trade_records=unavailable).read(request,
        price_points=POINTS).diagnostics == ("readonly_source_unavailable",)
    assert StockResearchChartMarkerReader(trade_records=lambda:rows*5001).read(request,
        price_points=POINTS).diagnostics == ("record_source_over_limit",)
    calls = []
    def cancelled():
        calls.append(True)
        return len(calls) > 1
    assert StockResearchChartMarkerReader(trade_records=lambda:rows).read(request,
        price_points=POINTS, cancelled=cancelled).diagnostics == ("cancelled",)


def test_missing_account_kind_rejected_despite_valid_clock_source_and_custody_hash(tmp_path):
    _, request, _, rows = saved_fixture(tmp_path, "trade")
    row = {**rows[0], "source_summary":dict(CONTEXT)}
    request = replace(request, expected_record_hashes=((row["trade_id"],stock_chart_saved_record_sha256(row)),))
    result = StockResearchChartMarkerReader(trade_records=lambda:(row,)).read(request, price_points=POINTS)
    assert result.candidates == () and result.identities == ()
    assert result.diagnostics == ("paper_or_declared_trade_rejected:trade-a",)


def test_original_confirmation_clock_does_not_backdate_to_decision(tmp_path):
    reader, request, path, rows = saved_fixture(tmp_path, "confirmation")
    # A second genuine accepted revision is saved for an earlier research decision.
    earlier = {**CONTEXT,"decision_date":"2026-10-07"}
    identity = DecisionIdentity(result_id=earlier["result_id"],stock_code="2330",
        source_snapshot_id=earlier["source_snapshot_id"],source_snapshot_hash=earlier["source_snapshot_hash"],
        decision_date=earlier["decision_date"])
    JournalService(SimpleNamespace(output_root=tmp_path)).accept_decision(identity,
        portfolio_id="account-a",source_id="source-a",revision_id="revision-b",
        recorded_at="2026-10-08T15:00:00+08:00")
    row = JsonlJournalReadAdapter(path)._records()[1]
    request = replace(request,decision_date="2026-10-07",source_context=tuple(sorted(earlier.items())),
        expected_record_hashes=((row["revision_id"],stock_chart_saved_record_sha256(row)),))
    result = reader.read(request,price_points=POINTS)
    assert result.candidates[0].event_date == "2026-10-08"
    assert result.candidates[0].account_kind == "research"
    assert not result.historical_pit_eligible
