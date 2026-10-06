from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_snapshot_producer import DailyMarketSnapshotProducer
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource
from app_module.saved_stock_technical_chart import SavedTechnicalChartError, read_saved_technical_chart, build_saved_technical_chart
from app_module.stock_research_chart_payload import project_stock_chart_payload
from app_module.stock_research_report_service import StockResearchReportReadService, StockResearchReportCancelled
from tests.test_stock_research_technical_history import _service_database
from tests.test_daily_market_snapshot_producer import _capacity_probe

DAY = date(2026, 10, 4)
CUTOFF = datetime(2026, 10, 4, 12, tzinfo=ZoneInfo("Asia/Taipei"))


def _produce(tmp_path: Path):
    database = tmp_path / "market.sqlite"
    _service_database(database)
    producer = DailyMarketSnapshotProducer(tmp_path / "snapshots", capacity_probe=_capacity_probe(), clock=lambda: CUTOFF)
    with SQLiteDailyMarketSnapshotSource(database, DAY) as source:
        result = producer.produce(cohort_id="saved-chart", decision_cutoff=CUTOFF, stock_codes=("2330",),
                                  source_loader=lambda code, _day: source.load_input(code), before_publish=source.validate_source_stable)
    assert result.published, result.to_dict()
    snapshot = DailyMarketSnapshotRepository(tmp_path / "snapshots").load_manifest(result.manifest_sha256, "saved-chart", DAY)
    context = {"stock_code": "2330", "decision_date": DAY.isoformat(), "data_date": DAY.isoformat(),
               "source_kind": "daily_market_research_snapshot", "source_snapshot_hash": snapshot.manifest_sha256,
               "source_snapshot_id": snapshot.manifest_identity_sha256, "daily_snapshot_root": str(tmp_path / "snapshots"),
               "daily_snapshot_cohort_id": "saved-chart", "daily_snapshot_condition_keys": "close_above_ma20", "daily_snapshot_combine_mode": "AND"}
    return database, snapshot, context


def _reader(tmp_path: Path, database: Path):
    return StockResearchReportReadService(SimpleNamespace(db_file=database, output_root=None, data_root=tmp_path), clock=lambda: CUTOFF)


def test_saved_chart_producer_reader_reopens_without_live_database_and_preserves_gaps(tmp_path: Path) -> None:
    database, snapshot, context = _produce(tmp_path)
    pins = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (tmp_path / "snapshots").rglob("*") if path.is_file()}
    # 原決策價格與均線刻意改變，讀回必須仍使用已封存資料。
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE daily_prices SET Close='999'")
        connection.execute("UPDATE technical_indicators SET MA20='999'")
    reader = _reader(tmp_path, tmp_path / "missing.sqlite")
    def reject_live(*_args, **_kwargs):
        raise AssertionError("保存圖不得讀live價格或均線")
    reader._read_prices = reject_live
    reader._read_technical = reject_live
    reader._read_technical_history = reject_live
    report = reader.read_report("2330", as_of_date=DAY, context=context)
    assert report.saved_technical_chart_json
    assert report.price_points[-1].close_price == Decimal("100.125")
    result = project_stock_chart_payload(report, expected_source_context=context)
    assert result.payload is not None, result
    assert tuple(point.value for point in result.payload.technical_lines[0].points) == (None, Decimal("22"), None, Decimal("24"))
    assert result.payload.table_rows == report.price_points
    assert result.payload.historical_pit_eligible is False
    assert pins == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (tmp_path / "snapshots").rglob("*") if path.is_file()}


@pytest.mark.parametrize("field,value", [("stock_code", "2317"), ("scope_identity", "other"), ("decision_cutoff", "2026-10-05T12:00:00+08:00"), ("content_sha256", "0" * 64), ("schema_version", "future.v9"), ("uncompressed_bytes", 999999)])
def test_saved_chart_refuses_identity_hash_version_and_byte_mismatch(tmp_path: Path, field: str, value: object) -> None:
    _database, snapshot, _context = _produce(tmp_path)
    stock = snapshot.stock_snapshots["2330"]
    envelope = {**stock["saved_technical_chart"], field: value}
    with pytest.raises(SavedTechnicalChartError):
        read_saved_technical_chart(envelope, stock_code="2330", decision_date=DAY,
                                   scope_identity=stock["scope_identity"], input_fingerprint_sha256=stock["input_fingerprint_sha256"])


def test_chart_history_revision_changes_artifact_even_when_feature_input_is_same(tmp_path: Path) -> None:
    database, first, _context = _produce(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE technical_indicators SET MA20='20.123456789012345678901' WHERE Date='2026-10-02'")
    with SQLiteDailyMarketSnapshotSource(database, DAY) as source:
        result = DailyMarketSnapshotProducer(tmp_path / "snapshots", capacity_probe=_capacity_probe(), clock=lambda: CUTOFF).produce(
            cohort_id="saved-chart", decision_cutoff=CUTOFF, stock_codes=("2330",), source_loader=lambda code, _day: source.load_input(code))
    assert result.published
    assert result.manifest_sha256 != first.manifest_sha256
    second = DailyMarketSnapshotRepository(tmp_path / "snapshots").load_manifest(result.manifest_sha256, "saved-chart", DAY)
    assert second.stock_snapshots["2330"]["input_fingerprint_sha256"] == first.stock_snapshots["2330"]["input_fingerprint_sha256"]
    assert first.stock_snapshots["2330"]["saved_technical_chart"] != second.stock_snapshots["2330"]["saved_technical_chart"]


def test_saved_chart_report_cannot_substitute_live_rows_and_cancel_retry_is_read_only(tmp_path: Path) -> None:
    database, _snapshot, context = _produce(tmp_path)
    reader = _reader(tmp_path, database)
    with pytest.raises(StockResearchReportCancelled):
        reader.read_report("2330", as_of_date=DAY, context=context, cancel_callback=lambda: True)
    report = reader.read_report("2330", as_of_date=DAY, context=context)
    bad = replace(report, technical_history=())
    assert project_stock_chart_payload(bad).reason == "saved_chart_report_rows_mismatch"
    assert project_stock_chart_payload(report).payload is not None


def test_saved_chart_new_process_reads_exact_manifest_without_database(tmp_path: Path) -> None:
    _database, snapshot, context = _produce(tmp_path)
    request = tmp_path / "reopen.json"
    request.write_text(json.dumps(context), encoding="utf-8")
    script = """
import json, sys
from pathlib import Path
from tests.test_saved_stock_technical_chart import _reader, DAY
from app_module.stock_research_chart_payload import project_stock_chart_payload
p = Path(sys.argv[1])
r = _reader(p.parent, p.parent / 'absent.sqlite').read_report('2330', as_of_date=DAY, context=json.loads(p.read_text()))
chart = project_stock_chart_payload(r)
assert chart.payload is not None
print(json.dumps({'close': str(r.price_points[-1].close_price), 'rows': len(r.price_points), 'pit': chart.payload.historical_pit_eligible, 'source': r.research_context['source_snapshot_hash']}))
"""
    result = subprocess.run([sys.executable, "-c", script, str(request)], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == {"close": "100.125", "rows": 4, "pit": False, "source": snapshot.manifest_sha256}


def test_saved_chart_known_late_price_and_compression_tail_are_rejected(tmp_path: Path) -> None:
    _database, snapshot, _context = _produce(tmp_path)
    stock = snapshot.stock_snapshots["2330"]
    envelope = stock["saved_technical_chart"]
    chart = read_saved_technical_chart(envelope, stock_code="2330", decision_date=DAY,
                                      scope_identity=stock["scope_identity"], input_fingerprint_sha256=stock["input_fingerprint_sha256"])
    with pytest.raises(SavedTechnicalChartError, match="chart_future_availability"):
        build_saved_technical_chart(stock_code="2330", decision_cutoff=CUTOFF,
                                    scope_identity=chart.scope_identity, input_fingerprint_sha256=chart.input_fingerprint_sha256,
                                    price_points=(replace(chart.price_points[0], available_at="2026-10-05T10:00:00+08:00"),), technical_history=())
    import base64
    tailed = {**envelope, "payload_zlib_base64": base64.b64encode(base64.b64decode(envelope["payload_zlib_base64"]) + b"extra").decode("ascii")}
    with pytest.raises(SavedTechnicalChartError, match="chart_compression_invalid"):
        read_saved_technical_chart(tailed, stock_code="2330", decision_date=DAY,
                                  scope_identity=chart.scope_identity, input_fingerprint_sha256=chart.input_fingerprint_sha256)


def test_rank_drilldown_uses_exact_parent_chart_without_granting_missing_rank_child(tmp_path: Path) -> None:
    from tests.test_rank_research_bookmark import _rank_bookmark
    _database, snapshot, _mapping = _produce(tmp_path)
    old = _rank_bookmark().context
    rank = replace(old.rank_context, snapshot_root=str(tmp_path / "snapshots"), ranking_root=str(tmp_path / "missing_rank"),
                   decision_date=DAY.isoformat(), parent_snapshot_id=snapshot.manifest_identity_sha256,
                   parent_snapshot_hash=snapshot.manifest_sha256, parent_cohort_id="saved-chart",
                   latest_date=DAY.isoformat(), comparison_date="2026-10-02",
                   comparison_window_dates=("2026-10-02", "2026-10-03", "2026-10-04"),
                   selected_input_fingerprint_sha256=snapshot.stock_snapshots["2330"]["input_fingerprint_sha256"])
    context = replace(old, decision_date=DAY.isoformat(), data_date=DAY.isoformat(), rank_context=rank)
    report = _reader(tmp_path, tmp_path / "missing.sqlite").read_report("2330", as_of_date=DAY, context=context)
    assert report.price_points[-1].close_price == Decimal("100.125")
    assert report.saved_technical_chart_json
    assert report.original_ranking.status != "available"
    assert project_stock_chart_payload(report).payload is not None
