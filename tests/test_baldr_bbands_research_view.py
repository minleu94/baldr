"""BBUI01 原保存 v2/v3 → 唯讀 view → exact context 的有界驗證。"""
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import os
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION as V2,
    DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER as V3,
)
from app_module.daily_market_research_screener import DailyMarketResearchScreenerService
from app_module.daily_market_snapshot_producer import DailyMarketSnapshotInput, DailyMarketSnapshotProducer
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
from app_module.research_session import ResearchStockContextDTO
from tests.test_baldr_a01_bbands_upper import _band
from tests.test_daily_market_snapshot_producer import _capacity_probe
from tests.test_ux04_05_daily_market_research_view import _wait
from ui_qt.views.daily_market_research_view import DailyMarketResearchView

METHOD = "close_above_bbands30_upper"
COHORT = "synthetic-offline-bbui01"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _saved(tmp_path, version=V3, variant="match"):
    # 只建立合成 DTO 與原保存檔，UI 測試沒有即時 DB 或模型推論。
    points, technical = _band(Decimal("150") if variant != "no_match" else Decimal("170"))
    if variant == "warmup":
        points = points[-29:]
    if variant == "missing":
        technical = replace(technical, indicators=technical.indicators[:-1])
    if variant == "source":
        technical = replace(technical, source_id="", indicators=(
            *technical.indicators[:-1], replace(technical.indicators[-1], source_id="")))
    day = date.fromisoformat(points[-1].data_date)
    cutoff = datetime.combine(day, time(16), tzinfo=ZoneInfo("Asia/Taipei"))
    root = tmp_path / "snapshots"
    source = tmp_path / "synthetic-source.txt"
    source.write_text("immutable synthetic input", encoding="utf-8")
    inputs = DailyMarketSnapshotInput(
        "2382", "synthetic:stock:2382", points, technical,
        {"database": str(source.resolve()), "schema_identity_sha256": "a" * 64,
         "price": f"{source.resolve()}#daily_prices", "technical": f"{source.resolve()}#technical_indicators"},
    )
    result = DailyMarketSnapshotProducer(root, capacity_probe=_capacity_probe(),
        clock=lambda: cutoff + timedelta(hours=1)).produce(
            cohort_id=COHORT, decision_cutoff=cutoff, stock_codes=("2382",),
            source_loader=lambda code, requested: inputs, contract_version=version)
    assert result.status == "published_complete", (result.error_code, result.error_message)
    repository = DailyMarketSnapshotRepository(root)
    snapshot = repository.load_manifest(result.manifest_sha256, cohort_id=COHORT, decision_date=day)
    return snapshot, source


class _SavedService:
    """以原 repository 讀保存 fixture，篩選與 DTO 使用原公開 API。"""
    def __init__(self, snapshot, root):
        self.snapshot_root = Path(root)
        self.repository = DailyMarketSnapshotRepository(self.snapshot_root)
        self.snapshot = snapshot
        self.screener = DailyMarketResearchScreenerService(SimpleNamespace(db_file="unused"), self.snapshot_root)
        self.produced = []
        self.reads = []
        self.failure = False

    def read_snapshot(self, cohort, day, manifest_sha256=None, *, cancel_callback=None):
        if self.failure:
            raise RuntimeError("snapshot_input_hash_mismatch")
        assert not cancel_callback or not cancel_callback()
        self.reads.append((cohort, day, manifest_sha256))
        return self.repository.load_manifest(manifest_sha256 or self.snapshot.manifest_sha256,
            cohort_id=cohort, decision_date=day)

    def read_latest(self, cohort, *, cancel_callback=None):
        return self.read_snapshot(cohort, self.snapshot.decision_date,
            self.snapshot.manifest_sha256, cancel_callback=cancel_callback)

    read_latest_published_snapshot = read_latest

    def filter_rows(self, snapshot, condition_keys, combine_mode):
        return self.screener.filter_rows(snapshot, condition_keys, combine_mode)

    def context_for_stock(self, row, *, stock_name=""):
        return self.screener.context_for_stock(row, stock_name=stock_name)

    def produce_snapshot(self, codes, cutoff, cohort, **options):
        self.produced.append((codes, cutoff, cohort, dict(options)))
        return SimpleNamespace(status="unchanged", manifest_sha256=self.snapshot.manifest_sha256,
            reused_stock_codes=("2382",), recomputed_stock_codes=())


def _view(snapshot, root, *, bb=True, watchlist=None):
    service = _SavedService(snapshot, root)
    view = DailyMarketResearchView(service, watchlist_service=watchlist,
        bookmark_confirmation_callback=lambda bookmark: True)
    view.cohort_id_input.setText(COHORT)
    view.stock_codes_input.setText("2382")
    view.bbands30_upper_checkbox.setChecked(bb)
    if bb:
        view.ma20_checkbox.setChecked(False)
        view.ma60_checkbox.setChecked(False)
    view.on_first_open()
    _wait(view)
    assert view._snapshot is not None, view.status_label.text()
    assert view.results_table.rowCount() == 1
    return view, service


@pytest.mark.parametrize("version", [V2, V3])
def test_saved_versions_keep_identity_and_exact_drilldown_restore(app, tmp_path, version):
    snapshot, source = _saved(tmp_path, version)
    source_before = (source.read_bytes(), source.stat().st_mtime_ns)
    saved_before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (tmp_path / "snapshots").rglob("*.json")}
    view, service = _view(snapshot, tmp_path / "snapshots", bb=version == V3)
    try:
        assert service.produced == []
        assert view._cohort_projection is not None, view.cohort_identity_label.toolTip()
        keys = view._selected_condition_keys()
        assert keys == ((METHOD,) if version == V3 else ("close_above_ma20", "close_above_ma60"))
        expected = service.filter_rows(snapshot, keys, "AND")[0]
        assert view._all_rows[0] == expected
        view.results_table.selectRow(0)
        contexts = []
        view.stockResearchRequested.connect(contexts.append)
        assert view.open_selected_stock()
        context = contexts[0]
        assert isinstance(context, ResearchStockContextDTO)
        assert context == service.context_for_stock(expected)
        assert context.source_snapshot_hash == snapshot.manifest_sha256
        assert context.source_snapshot_id == snapshot.manifest_identity_sha256
        assert context.daily_snapshot_condition_keys == ",".join(keys)
        assert view.restore_research_snapshot_stock(context.stock_code, context.source_snapshot_hash)
        assert not view.restore_research_snapshot_stock(context.stock_code, "f" * 64)
        assert not view.restore_research_snapshot_stock("9999", context.source_snapshot_hash)
        for _ in range(2):
            view.reload_published_snapshot()
            _wait(view)
            assert view._all_rows[0] == expected
            assert view.restore_research_snapshot_stock("2382", context.source_snapshot_hash)
        assert service.produced == []
        assert source_before == (source.read_bytes(), source.stat().st_mtime_ns)
        assert all((p.read_bytes(), p.stat().st_mtime_ns) == pin for p, pin in saved_before.items())
        if version == V3:
            assert "布林" in view.selected_summary_label.text()
            assert "lineage" in view.selected_summary_label.toolTip()
            assert "timeperiod" in view.preset_help_label.toolTip()
        else:
            assert "未保存 BB" in view.results_table.item(0, 11).text()
    finally:
        view.begin_shutdown()
        view.close()
        app.processEvents()


@pytest.mark.parametrize("variant,state,detail", [
    ("match", "match", "符合"), ("no_match", "no_match", "不符合"),
    ("warmup", "unknown", "不足 30 根"), ("missing", "unknown", "缺少保存上軌"),
    ("source", "unknown", "來源身份未知"),
])
def test_v3_saved_three_states_and_lineage_remain_explicit(app, tmp_path, variant, state, detail):
    snapshot, _ = _saved(tmp_path, variant=variant)
    view, _ = _view(snapshot, tmp_path / "snapshots")
    try:
        row = view._all_rows[0]
        assert row.combined_state == state
        assert row.conditions[0].key == METHOD
        assert detail in view.results_table.item(0, 11).text()
        assert "lineage 未核驗（未知）" in view.results_table.item(0, 11).text()
        view.results_table.selectRow(0)
        assert "布林上軌" in view.selected_summary_label.text()
    finally:
        view.begin_shutdown()
        view.close()
        app.processEvents()


def test_v2_bb_selection_does_not_invent_evidence_and_preset_clears_bb(app, tmp_path):
    snapshot, _ = _saved(tmp_path, V2)
    view, service = _view(snapshot, tmp_path / "snapshots")
    try:
        assert view._all_rows[0].combined_state == "unknown"
        assert "未保存 BB" in view.results_table.item(0, 11).text()
        assert view.apply_selected_preset()
        assert not view.bbands30_upper_checkbox.isChecked()
        assert service.produced == []
    finally:
        view.begin_shutdown()
        view.close()
        app.processEvents()


@pytest.mark.parametrize("version", [V2, V3])
def test_explicit_update_opt_in_and_generation_source_close_guards(app, tmp_path, version):
    snapshot, _ = _saved(tmp_path, version)
    view, service = _view(snapshot, tmp_path / "snapshots", bb=version == V3)
    try:
        view.start_snapshot_update()
        _wait(view)
        options = service.produced[-1][3]
        assert options.get("include_bbands30_upper", False) is (version == V3)
        assert ("include_bbands30_upper" in options) is (version == V3)
        generation = view._operation_generation
        view._on_operation_error(generation - 1, "stale error")
        view._on_operation_finished(generation - 1, "reload", snapshot)
        assert view._manifest_sha256 == snapshot.manifest_sha256
        service.failure = True
        view.reload_published_snapshot()
        _wait(view)
        assert view._snapshot is None and view.results_table.rowCount() == 0
        assert "snapshot_input_hash_mismatch" in view.status_label.text()
        view.begin_shutdown()
        view._on_operation_finished(view._operation_generation, "reload", snapshot)
        assert view._snapshot is None
        assert not view.restore_research_snapshot_stock("2382", snapshot.manifest_sha256)
        assert not view.open_selected_stock()
        assert not view.bbands30_upper_checkbox.isEnabled()
    finally:
        view.begin_shutdown()
        view.close()
        app.processEvents()


def test_bookmark_ui_saves_reopens_and_restores_bb_context(app, tmp_path):
    from app_module.watchlist_service import WatchlistService
    from app_module.daily_market_research_bookmark import decode_daily_market_research_bookmark
    snapshot, _ = _saved(tmp_path)
    config = SimpleNamespace(output_root=tmp_path / "personal", resolve_output_path=lambda name: tmp_path / "personal" / name)
    watchlist = WatchlistService(config)
    view, _ = _view(snapshot, tmp_path / "snapshots", watchlist=watchlist)
    try:
        view.results_table.selectRow(0)
        captured = []
        view.bookmarkSaved.connect(captured.append)
        assert view.bookmark_selected_research(), view.status_label.text()
        saved = WatchlistService(config).get_research_bookmark(captured[0].bookmark_id)
        assert saved.to_dict() == captured[0].to_dict()
        assert saved.context.daily_snapshot_condition_keys == METHOD
        assert saved.context.source_snapshot_hash == snapshot.manifest_sha256
        decoded = decode_daily_market_research_bookmark(saved.to_dict())
        assert decoded.context == saved.context
        view.bbands30_upper_checkbox.setChecked(False)
        view.ma20_checkbox.setChecked(True)
        assert view.open_latest_research(decoded.context)
        _wait(view)
        assert view.bbands30_upper_checkbox.isChecked()
        assert view._selected_condition_keys() == (METHOD,)
        assert view.restore_research_snapshot_stock(saved.stock_code, saved.source_snapshot_hash)
        contexts = []
        view.stockResearchRequested.connect(contexts.append)
        assert view.open_selected_stock()
        assert contexts[0].source_snapshot_hash == saved.context.source_snapshot_hash
        assert contexts[0].daily_snapshot_condition_keys == saved.context.daily_snapshot_condition_keys
    finally:
        view.begin_shutdown()
        view.close()
        app.processEvents()
