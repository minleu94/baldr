"""中央 B05 原保存 source custody 與非同步接線。"""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import MethodType, SimpleNamespace
import json
import subprocess
import sys
import time
import pytest
from PySide6.QtCore import QCoreApplication

from app_module.stock_research_chart_marker_composition import ChartMarkerSource, compose_saved_chart_markers
from app_module.stock_research_chart_marker_reader import StockChartMarkerRecordSource
from app_module.research_session import ResearchStockContextDTO
from tests.test_baldr_b05_chart_marker_reader import saved_fixture, file_witness, POINTS, CONTEXT
from tests.test_stock_research_chart_payload import _report
from tests.test_ui_qt_saved_stock_chart import app


@pytest.mark.parametrize("kind", ["trade", "confirmation"])
def test_original_writer_to_guarded_custody_and_fresh_process(tmp_path, kind):
    _, request, path, _ = saved_fixture(tmp_path, kind)
    report = _report(*POINTS, context=CONTEXT)
    before = file_witness(tmp_path)
    guards = []
    source = ChartMarkerSource(path, request.record_source, lambda p: (guards.append(p), p)[1])
    result = compose_saved_chart_markers(report, cutoff_date=request.cutoff_date, account_id=request.account_id,
                                        expected_source_id=request.source_id, sources=(source,))
    assert len(result.candidates) == 1 and not result.diagnostics
    assert result.identities[0].source_row_hash == request.expected_record_hashes[0][1]
    assert len(guards) >= 4
    assert file_witness(tmp_path) == before
    code = """
import sys
from pathlib import Path
from tests.test_baldr_central_chart_composition import *
source=ChartMarkerSource(Path(sys.argv[1]), StockChartMarkerRecordSource(sys.argv[2]))
r=compose_saved_chart_markers(_report(*POINTS,context=CONTEXT),cutoff_date="2026-10-08",
 account_id="account-a",expected_source_id="source-a",sources=(source,))
assert len(r.candidates)==1
print(r.candidates[0].content_sha256)
"""
    # _report is private and star imports deliberately omit it.
    code = code.replace("source=ChartMarkerSource", "from tests.test_stock_research_chart_payload import _report\nsource=ChartMarkerSource")
    child = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", code, str(path), request.record_source.value],
                           check=True, capture_output=True, text=True, timeout=30)
    assert child.stdout.strip() == result.candidates[0].content_sha256
    assert file_witness(tmp_path) == before


@pytest.mark.parametrize("change", ["account", "source", "context", "cancel", "guard"])
def test_unknown_or_wrong_central_caller_never_borrows_saved_identity(tmp_path, change):
    _, request, path, _ = saved_fixture(tmp_path, "trade")
    report = _report(*POINTS, context=CONTEXT if change != "context" else {})
    guard = (lambda p: (_ for _ in ()).throw(ValueError("guard_refused"))) if change == "guard" else None
    result = compose_saved_chart_markers(report, cutoff_date=request.cutoff_date,
        account_id="other" if change == "account" else request.account_id,
        expected_source_id="other" if change == "source" else request.source_id,
        sources=(ChartMarkerSource(path, request.record_source, guard),),
        cancel_callback=lambda: change == "cancel")
    assert not result.candidates and result.diagnostics


def test_source_byte_bound_is_checked_before_open(tmp_path, monkeypatch):
    _, request, path, _ = saved_fixture(tmp_path, "trade")
    with path.open("wb") as handle:
        handle.truncate(16 * 1024 * 1024 + 1)
    def forbidden(*args, **kwargs):
        pytest.fail("over-budget source must not open")
    import builtins
    monkeypatch.setattr(builtins, "open", forbidden)
    result = compose_saved_chart_markers(_report(*POINTS, context=CONTEXT), cutoff_date=request.cutoff_date,
        account_id=request.account_id, expected_source_id=request.source_id,
        sources=(ChartMarkerSource(path, request.record_source),))
    assert not result.candidates and "source_byte_budget_exceeded" in result.diagnostics[0]


@pytest.mark.parametrize("stale", [False, True])
def test_main_background_completion_rechecks_active_scope(app, tmp_path, stale):
    from app_module.portfolio_store import PortfolioJsonlStore
    from ui_qt.main import MainWindow
    from ui_qt.views.stock_research_report_view import StockResearchReportView
    _, request, path, _ = saved_fixture(tmp_path, "trade")
    store = PortfolioJsonlStore(tmp_path)
    # Explicit selected account is supplied by the central route, not by the row.
    store.route = SimpleNamespace(identity=SimpleNamespace(key=request.account_id))
    view = StockResearchReportView(SimpleNamespace())
    context = ResearchStockContextDTO(stock_code="2330", result_id=CONTEXT["result_id"],
        decision_date=CONTEXT["decision_date"], source_snapshot_id=CONTEXT["source_snapshot_id"],
        source_snapshot_hash=CONTEXT["source_snapshot_hash"], source_id=request.source_id)
    report = _report(*POINTS, context={**CONTEXT, "source_id": request.source_id})
    view._active_code = "2330"
    view._loaded_request_context = context
    view._loaded_report = report
    owner = SimpleNamespace(stock_research_workspace=SimpleNamespace(report_view=view),
        portfolio_service=SimpleNamespace(store=store),
        journal_service=SimpleNamespace(store=SimpleNamespace(journal_file=path)),
        journal_storage_selection=SimpleNamespace(paths=None, legacy_read_only=False))
    owner._clear_stock_chart_markers = MethodType(MainWindow._clear_stock_chart_markers, owner)
    try:
        MainWindow._load_stock_chart_markers(owner, report)
        worker = owner._chart_marker_worker
        if stale:
            owner._chart_marker_generation += 1
        deadline = time.monotonic() + 10
        while worker.isRunning() and time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.001)
        QCoreApplication.processEvents()
        assert not worker.isRunning()
        assert bool(view._chart_marker_candidates) is (not stale)
        if not stale:
            assert len(view._chart_widget._markers) == 1
    finally:
        view.close()


def test_selected_journey_trade_reader_rechecks_post_constructor_hardlink(tmp_path):
    import os
    from app_module.stock_research_chart_marker_composition import SelectedPortfolioTradeReadAdapter
    _, request, path, _ = saved_fixture(tmp_path, "trade")
    reader = SelectedPortfolioTradeReadAdapter(ChartMarkerSource(path, request.record_source),
                                              account_id=request.account_id)
    rows = reader.list_trades()
    assert rows[0]["trade_id"] == "trade-a"
    before = path.read_bytes()
    backup = path.with_name("original-trades")
    path.rename(backup)
    os.link(backup, path)
    with pytest.raises(ValueError, match="source_alias_or_type"):
        reader.list_trades()
    assert backup.read_bytes() == before


def test_selected_journey_journal_preserves_original_as_of_projection(tmp_path):
    from app_module.stock_research_chart_marker_composition import SelectedJournalReadAdapter
    from app_module.personal_journal_paths import PersonalJournalPaths
    from app_module.personal_data_paths import PersonalDataPaths
    _, request, path, _ = saved_fixture(tmp_path / "legacy", "confirmation")
    paths = PersonalJournalPaths(PersonalDataPaths(tmp_path / "market", tmp_path / "legacy", tmp_path / "private"))
    reader = SelectedJournalReadAdapter(ChartMarkerSource(path, request.record_source),
                                        journal_paths=paths, legacy_read_only=True)
    assert reader._records()[0]["revision_id"] == "revision-a"
    assert reader.list_entries_as_of("2026-10-07T15:00:00+08:00") == []
    assert path.exists()


def test_too_many_selected_original_pins_has_explicit_budget_diagnostic(tmp_path):
    _, request, path, rows = saved_fixture(tmp_path, "trade")
    raw = [dict(rows[0], trade_id="trade-" + str(n)) for n in range(129)]
    path.write_text("\n".join(json.dumps(row) for row in raw), encoding="utf-8")
    result = compose_saved_chart_markers(_report(*POINTS, context=CONTEXT), cutoff_date=request.cutoff_date,
        account_id=request.account_id, expected_source_id=request.source_id,
        sources=(ChartMarkerSource(path, request.record_source),))
    assert not result.candidates and "selected_record_pin_budget_exceeded" in result.diagnostics[0]
