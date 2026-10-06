"""B07 固定來源與真正 typed execution 的隔離驗證；不讀正式市場／個人資料。"""
from dataclasses import asdict, replace
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest

from app_module.backtest_service import BacktestService
from app_module.backtest_repository import BacktestRunRepository
from app_module.recommendation_portfolio_run_repository import RecommendationPortfolioRunRepository
from app_module.recommendation_portfolio_dtos import RecommendationPortfolioBacktestResultDTO
from app_module.research_history_lookup import ResearchHistoryLookup, ResearchHistoryUnavailable, ResearchHistoryReadBudget
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_service import ResearchRunService, ResearchRunIntegrityError
from app_module.saved_strategy_rule_card import load_saved_strategy_rule_card
from data_module.config import TWStockConfig
from decision_module.strategies.contracts import StrategySpec
from ui_qt.views.backtest.execution_coordinator import BacktestExecutionRequest
from ui_qt.views.backtest.research_run_metadata import execute_single_backtest_with_rule_source, build_single_backtest_metadata


def inventory(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_size, p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def executed_case(tmp_path, monkeypatch):
    """只替換市場 I/O；StrategyRegistry／executor／broker／analyzer／保存都是真正既有實作。"""
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output", profile="test")
    index = pd.bdate_range("2026-01-02", periods=30)
    prices = [100 + i for i in range(30)]
    frame = pd.DataFrame({"Open": prices, "High": [p + 2 for p in prices], "Low": [p - 2 for p in prices],
                          "Close": prices, "Volume": [1000000] * 30}, index=index)
    service = BacktestService(config=None)
    loads = []
    def source(*args):
        loads.append(args)
        return frame.copy(), "2026-01-02", index[-1].strftime("%Y-%m-%d")
    monkeypatch.setattr(service, "_load_stock_data", source)
    spec = StrategySpec("baseline_score_threshold", "1.0", config={"params": {
        "threshold_mode": "fixed", "buy_score": 0, "sell_score": 100,
        "buy_confirm_days": 1, "sell_confirm_days": 1, "cooldown_days": 0}})
    request = BacktestExecutionRequest(stock_code="2330", start_date="2026-01-02",
        end_date=index[-1].strftime("%Y-%m-%d"), strategy_id=spec.strategy_id, strategy_spec=spec,
        strategy_params=dict(spec.config["params"]), capital=1000000, fee_bps=Decimal("14.25"),
        slippage_bps=Decimal("5"), execution_price="next_open", stop_loss_pct=None, take_profit_pct=None,
        stop_loss_atr_mult=None, take_profit_atr_mult=None, sizing_mode="all_in", fixed_amount=None,
        risk_pct=None, max_positions=1, position_sizing="equal_weight", allow_pyramid=False,
        allow_reentry=True, reentry_cooldown_days=0, enable_limit=True, enable_volume=True,
        max_participation=Decimal("0.05"))
    report = execute_single_backtest_with_rule_source(request, service)
    assert len(loads) == 1
    assert not report.details["trade_list"].empty
    assert report.details["data_manifest"]["strategy_spec"]["data_version"].startswith("sha256:")
    assert request.strategy_spec.data_version is None
    metadata = build_single_backtest_metadata(run_id="executed-baseline", run_name="實際 typed 合成執行",
        notes="", params=request.run_params(), details=report.details, report=report, created_at="2026-10-06T10:00:00")
    registry = ResearchRunService(config)
    metadata = registry.save_run(metadata, report.details["equity_curve"], report.details["trade_list"])
    return config, registry, metadata, request, report, service


def test_actual_typed_execution_artifact_newprocess_complete_card(tmp_path, monkeypatch):
    config, registry, metadata, request, report, service = executed_case(tmp_path, monkeypatch)
    before = inventory(tmp_path)
    saved = load_saved_strategy_rule_card(registry, metadata)
    assert saved.source_status == "source_ref_only", saved.reasons
    assert saved.rule_card.rule_status == "execution_contract_bound"
    assert saved.rule_card.missing == ()
    assert saved.rule_card.field("entry").value["threshold"] == 0
    assert saved.rule_card.field("cost").value["sell_tax_bps"] == "30"
    assert saved.rule_card.field("qualification").value["historical_pit_eligible"] is False
    assert saved.performance_status == "not_evaluable"
    # 真正另一個 interpreter；consumer 禁止重新載入行情或取得 executor。
    code = '''import json,sys
from types import SimpleNamespace
from app_module.research_run_service import ResearchRunService
from app_module.saved_strategy_rule_card import load_saved_strategy_rule_card
from decision_module.strategies.registry import StrategyRegistry
def denied(*a,**k): raise AssertionError("reader tried executor/current metadata")
StrategyRegistry.get_executor=denied
StrategyRegistry.get_strategy_meta=denied
config=SimpleNamespace(**json.loads(sys.argv[1]))
service=ResearchRunService(config)
meta=service.repository.get_metadata("executed-baseline")
print(json.dumps(load_saved_strategy_rule_card(service,meta).to_dict(),ensure_ascii=True,sort_keys=True))
'''
    paths = {key: str(getattr(config, key)) for key in ("research_run_db_file", "research_run_parquet_dir", "research_run_staging_dir")}
    child = subprocess.run([sys.executable, "-c", code, json.dumps(paths)], capture_output=True, text=True, check=True)
    assert json.loads(child.stdout) == saved.to_dict()
    assert inventory(tmp_path) == before


def test_original_execution_values_unchanged_and_future_data_refused(tmp_path, monkeypatch):
    _, _, _, request, report, service = executed_case(tmp_path, monkeypatch)
    original = request.execute(service)
    pd.testing.assert_frame_equal(original.details["equity_curve"], report.details["equity_curve"])
    pd.testing.assert_frame_equal(original.details["trade_list"], report.details["trade_list"])
    frame = pd.DataFrame({"Close": [100]}, index=pd.to_datetime(["2027-01-02"]))
    monkeypatch.setattr(service, "_load_stock_data", lambda *_: (frame, "2027-01-02", "2027-01-02"))
    with pytest.raises(ValueError, match="決策期間"):
        execute_single_backtest_with_rule_source(request, service)


def fixed_sources(tmp_path):
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output", profile="test")
    backtest = BacktestRunRepository(config)
    portfolio = RecommendationPortfolioRunRepository(config)
    equity = tmp_path / "legacy.parquet"
    pd.DataFrame({"equity": [1000000]}).to_parquet(equity)
    # 此 metadata fixture 只驗既有 legacy 來源查找，不能替代 typed execution 正向。
    with sqlite3.connect(backtest.db_path) as conn:
        conn.execute("INSERT INTO runs (run_id,run_name,stock_code,strategy_id,start_date,end_date,created_at,equity_curve_path) VALUES (?,?,?,?,?,?,?,?)",
                     ("same-id", "舊單股", "2330", "old", "2026-01-02", "2026-01-05", "2026-10-06", str(equity)))
    dto = RecommendationPortfolioBacktestResultDTO(summary={"total_return": 0}, equity_curve=pd.DataFrame(),
        trades=pd.DataFrame(), snapshots=[], period_holdings=[], stock_contribution=[])
    portfolio.save_run(run_name="舊回放", profile_id="old", start_date="2026-01-02", end_date="2026-01-05",
        initial_capital=1000000, rebalance_frequency="daily", top_n=1, allocation_method="equal_weight",
        holding_days=5, stop_loss_pct=None, take_profit_pct=None, result=dto, run_id="same-id")
    registry = ResearchRunService(config)
    for kind in ("single_backtest", "batch_backtest_stock", "fixed_basket_stock", "recommendation_portfolio", "research_forward", "unexpected"):
        metadata = ResearchRunMetadataDTO(run_id=kind, run_name=kind, run_type=kind, universe=["2330"],
            start_date="2026-01-02", end_date="2026-01-05", created_at="2026-10-06")
        registry.save_run(metadata, pd.DataFrame({"equity": [1]}), pd.DataFrame())
    lookup = ResearchHistoryLookup(registry=registry, legacy_backtest_db=backtest.db_path, legacy_portfolio_db=portfolio.db_path,
        read_budget=ResearchHistoryReadBudget(max_artifact_bytes=1024 * 1024, max_total_bytes=4 * 1024 * 1024))
    return config, lookup, backtest, portfolio, registry


def test_all_fixed_sources_same_readonly_lookup_and_original_results(tmp_path):
    _, lookup, backtest, portfolio, registry = fixed_sources(tmp_path)
    before = inventory(tmp_path)
    page = lookup.list_entries()
    assert page.diagnostics == ()
    assert {e.run_type for e in page.entries} == {"legacy_backtest", "legacy_recommendation_portfolio", "single_backtest",
        "batch_backtest_stock", "fixed_basket_stock", "recommendation_portfolio", "research_forward", "unexpected"}
    assert len(page.entries) == 8
    for entry in page.entries:
        if entry.result_supported:
            loaded = lookup.resolve(entry)
            assert loaded.entry == entry
            if entry.source_kind == "legacy_backtest":
                assert loaded.result["stock_code"] == "2330"
                assert not loaded.result["equity_curve"].empty
            elif entry.source_kind == "legacy_recommendation_portfolio":
                assert type(loaded.result["result_dto"]) is RecommendationPortfolioBacktestResultDTO
        else:
            assert json.loads(entry.metadata_json)["run_id"] == entry.run_id
            with pytest.raises(ResearchHistoryUnavailable, match="metadata_only"):
                lookup.resolve(entry)
    assert inventory(tmp_path) == before
    assert len(registry.list_runs()) == 6  # legacy 查找不 backfill。


@pytest.mark.parametrize("change", [{"source_kind": "unrecognized"}, {"run_type": "research_forward"},
    {"run_id": "no-such-run"}, {"stock_code": "2382"}, {"metadata_sha256": "a" * 64}, {"context_sha256": "b" * 64}])
@pytest.mark.parametrize("kind", ["legacy_backtest", "legacy_recommendation_portfolio", "single_backtest"])
def test_exact_kind_run_hash_stock_context_refused(tmp_path, change, kind):
    _, lookup, *_ = fixed_sources(tmp_path)
    selected = next(e for e in lookup.list_entries().entries if e.run_type == kind)
    before = inventory(tmp_path)
    with pytest.raises(ResearchHistoryUnavailable):
        lookup.resolve(replace(selected, **change))
    assert inventory(tmp_path) == before


def test_missing_sources_no_mkdir_or_empty_database(tmp_path, monkeypatch):
    paths = [tmp_path / "absent" / "backtest.db", tmp_path / "absent" / "portfolio.db"]
    lookup = ResearchHistoryLookup(legacy_backtest_db=paths[0], legacy_portfolio_db=paths[1],
        read_budget=ResearchHistoryReadBudget(max_artifact_bytes=1024, max_total_bytes=4096))
    monkeypatch.setattr(Path, "mkdir", lambda *_a, **_k: pytest.fail("lookup mkdir"))
    before = inventory(tmp_path)
    page = lookup.list_entries()
    assert not page.entries and len(page.diagnostics) == 3
    assert inventory(tmp_path) == before and not paths[0].parent.exists()


def test_legacy_artifact_revision_and_active_sidecar_refused(tmp_path):
    _, lookup, backtest, *_ = fixed_sources(tmp_path)
    selected = next(e for e in lookup.list_entries().entries if e.run_type == "legacy_backtest")
    (tmp_path / "legacy.parquet").write_bytes(b"changed")
    with pytest.raises(ResearchHistoryUnavailable, match="selected_source_changed"):
        lookup.resolve(selected)
    Path(str(backtest.db_path) + "-wal").write_bytes(b"active WAL")
    before = inventory(tmp_path)
    assert any("active_sqlite_sidecar_unsupported" in reason for reason in lookup.list_entries().diagnostics)
    assert inventory(tmp_path) == before


def test_registry_parquet_tamper_not_opened(tmp_path):
    _, lookup, _, _, registry = fixed_sources(tmp_path)
    selected = next(e for e in lookup.list_entries().entries if e.run_type == "single_backtest")
    metadata = registry.repository.get_metadata(selected.run_id)
    Path(metadata.equity_path).write_bytes(b"changed")
    with pytest.raises(ResearchRunIntegrityError):
        lookup.resolve(selected)


def test_lookup_connections_are_immutable_query_only_and_never_use_legacy_constructor(tmp_path, monkeypatch):
    _, lookup, _, _, registry = fixed_sources(tmp_path)
    monkeypatch.setattr(BacktestRunRepository, "__init__", lambda *_: pytest.fail("legacy writer constructor"))
    monkeypatch.setattr(RecommendationPortfolioRunRepository, "__init__", lambda *_: pytest.fail("portfolio writer constructor"))
    monkeypatch.setattr(type(registry.repository), "ensure_schema", lambda *_: pytest.fail("schema writer"))
    original = sqlite3.connect
    uris = []
    def connect(database, **kwargs):
        assert "mode=ro&immutable=1" in database and kwargs.get("uri") is True
        uris.append(database)
        return original(database, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", connect)
    before = inventory(tmp_path)
    page = lookup.list_entries()
    lookup.resolve(next(e for e in page.entries if e.run_type == "single_backtest"))
    assert uris and inventory(tmp_path) == before


def test_registry_active_sidecar_is_visible_and_unchanged(tmp_path):
    _, lookup, _, _, registry = fixed_sources(tmp_path)
    Path(str(registry.repository.db_path) + "-wal").write_bytes(b"not a detached snapshot")
    before = inventory(tmp_path)
    page = lookup.list_entries()
    assert any("active_sqlite_sidecar_unsupported" in reason for reason in page.diagnostics)
    assert {entry.source_kind for entry in page.entries} == {"legacy_backtest", "legacy_recommendation_portfolio"}
    assert inventory(tmp_path) == before


def test_lookup_newprocess_exact_reopen_no_source_write(tmp_path):
    config, lookup, backtest, portfolio, registry = fixed_sources(tmp_path)
    selected = next(entry for entry in lookup.list_entries().entries if entry.run_type == "legacy_backtest")
    before = inventory(tmp_path)
    code = '''import json,sys
from pathlib import Path
from types import SimpleNamespace
from app_module.research_history_lookup import ResearchHistoryLookup,ResearchHistoryEntry,ResearchHistoryReadBudget
from app_module.research_run_service import ResearchRunService
paths=json.loads(sys.argv[1]); expected=ResearchHistoryEntry(**json.loads(sys.argv[2]))
registry=ResearchRunService(SimpleNamespace(**paths["registry"]))
lookup=ResearchHistoryLookup(registry=registry,legacy_backtest_db=Path(paths["backtest"]),legacy_portfolio_db=Path(paths["portfolio"]),read_budget=ResearchHistoryReadBudget(max_artifact_bytes=1024*1024,max_total_bytes=4*1024*1024))
page=lookup.list_entries(); resolved=lookup.resolve(expected)
print(json.dumps({"types":sorted(e.run_type for e in page.entries),"identity":resolved.entry.context_sha256,"stock":resolved.result["stock_code"]}))
'''
    paths = {"registry": {key: str(getattr(config, key)) for key in ("research_run_db_file", "research_run_parquet_dir", "research_run_staging_dir")},
             "backtest": str(backtest.db_path), "portfolio": str(portfolio.db_path)}
    result = subprocess.run([sys.executable, "-c", code, json.dumps(paths), json.dumps(asdict(selected))], capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    assert len(payload["types"]) == 8 and payload["identity"] == selected.context_sha256 and payload["stock"] == "2330"
    assert inventory(tmp_path) == before


def test_single_backtest_existing_ui_save_entry(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from ui_qt.views.backtest_view import BacktestView
    app = QApplication.instance() or QApplication([])
    config, registry, _, request, report, service = executed_case(tmp_path, monkeypatch)
    view = BacktestView(backtest_service=service, config=None)
    view.research_run_service = registry
    view.current_run_params = request.run_params()
    view.current_report = report
    view._single_backtest_result_generation = view._execution_generation
    run_id = view._save_single_backtest_to_research_registry("UI 原保存入口", "")
    metadata = registry.repository.get_metadata(run_id)
    result = load_saved_strategy_rule_card(registry, metadata)
    assert result.rule_card.rule_status == "execution_contract_bound"
    assert result.source_status == "source_ref_only"
    assert result.rule_card.missing == ()
    view.close()
    app.processEvents()


def test_legacy_budget_required_and_stat_overflow_never_opens_artifact(tmp_path, monkeypatch):
    _, lookup, backtest, *_ = fixed_sources(tmp_path)
    selected = next(e for e in lookup.list_entries().entries if e.run_type == "legacy_backtest")
    no_budget = ResearchHistoryLookup(legacy_backtest_db=backtest.db_path)
    assert any("legacy_read_budget_required" in item for item in no_budget.list_entries().diagnostics)
    with pytest.raises(ResearchHistoryUnavailable, match="legacy_read_budget_required"):
        no_budget.resolve(selected)
    artifact = tmp_path / "legacy.parquet"
    budget = ResearchHistoryReadBudget(max_artifact_bytes=artifact.stat().st_size - 1, max_total_bytes=100000)
    before = inventory(tmp_path)
    original_open = Path.open
    def no_artifact_open(path, *args, **kwargs):
        if path == artifact:
            pytest.fail("stat 超限仍開啟 artifact")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", no_artifact_open)
    assert any("artifact_byte_budget_exceeded" in item for item in lookup.list_entries(read_budget=budget).diagnostics)
    with pytest.raises(ResearchHistoryUnavailable, match="artifact_byte_budget_exceeded"):
        lookup.resolve(selected, read_budget=budget)
    monkeypatch.setattr(Path, "open", original_open)
    assert inventory(tmp_path) == before


def test_legacy_one_round_aggregate_budget_covers_both_artifacts(tmp_path):
    _, _, backtest, *_ = fixed_sources(tmp_path)
    equity = tmp_path / "legacy.parquet"
    trades = tmp_path / "trades.parquet"
    trades.write_bytes(equity.read_bytes())
    with sqlite3.connect(backtest.db_path) as connection:
        connection.execute("UPDATE runs SET trade_list_path = ?", (str(trades),))
    size = equity.stat().st_size
    lookup = ResearchHistoryLookup(legacy_backtest_db=backtest.db_path,
        read_budget=ResearchHistoryReadBudget(max_artifact_bytes=size, max_total_bytes=size * 2))
    selected = lookup.list_entries().entries[0]
    budget = ResearchHistoryReadBudget(max_artifact_bytes=size, max_total_bytes=size * 2 - 1)
    before = inventory(tmp_path)
    page = lookup.list_entries(read_budget=budget)
    assert not page.entries and any("aggregate_byte_budget_exceeded" in item for item in page.diagnostics)
    with pytest.raises(ResearchHistoryUnavailable, match="aggregate_byte_budget_exceeded"):
        lookup.resolve(selected, read_budget=budget)
    # 每次呼叫另起一輪，不借用上一輪剩餘容量；兩檔僅各讀一次。
    assert lookup.resolve(selected).entry == selected
    assert inventory(tmp_path) == before


def test_legacy_aggregate_budget_is_shared_across_sources(tmp_path):
    _, lookup, *_ = fixed_sources(tmp_path)
    size = (tmp_path / "legacy.parquet").stat().st_size
    before = inventory(tmp_path)
    page = lookup.list_entries(read_budget=ResearchHistoryReadBudget(max_artifact_bytes=100000, max_total_bytes=size))
    assert {e.source_kind for e in page.entries} == {"legacy_backtest", "registry"}
    assert any("aggregate_byte_budget_exceeded" in item for item in page.diagnostics)
    assert inventory(tmp_path) == before


def test_legacy_read_chunks_are_bounded_and_cancel_is_optional(tmp_path, monkeypatch):
    from app_module.research_history_lookup import _ReadRound
    _, lookup, *_ = fixed_sources(tmp_path)
    path = tmp_path / "legacy.parquet"
    path.write_bytes(b"x" * (_ReadRound.CHUNK_BYTES * 3))
    requested = []
    original_open = Path.open
    class TrackedFile:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.handle.close()
        def fileno(self):
            return self.handle.fileno()
        def read(self, size):
            requested.append(size)
            return self.handle.read(size)
    def tracked_open(source, *args, **kwargs):
        handle = original_open(source, *args, **kwargs)
        return TrackedFile(handle) if source == path else handle
    monkeypatch.setattr(Path, "open", tracked_open)
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        return bool(requested)
    page = lookup.list_entries(check_cancel=cancel)
    assert not page.entries and any("read_cancelled" in item for item in page.diagnostics)
    assert calls and requested == [_ReadRound.CHUNK_BYTES]
    requested.clear()
    selected = next(e for e in lookup.list_entries().entries if e.run_type == "legacy_backtest")
    assert max(requested) <= _ReadRound.CHUNK_BYTES
    requested.clear()
    with pytest.raises(ResearchHistoryUnavailable, match="read_cancelled"):
        lookup.resolve(selected, check_cancel=cancel)
    assert requested == [_ReadRound.CHUNK_BYTES]


def test_legacy_selected_same_raw_bytes_are_pinned_before_decode(tmp_path, monkeypatch):
    _, lookup, *_ = fixed_sources(tmp_path)
    selected = next(e for e in lookup.list_entries().entries if e.run_type == "legacy_backtest")
    path = tmp_path / "legacy.parquet"
    original_raw = path.read_bytes()
    decoded = []
    original_decoder = pd.read_parquet
    def decode(raw, *args, **kwargs):
        assert isinstance(raw, __import__("io").BytesIO)
        decoded.append(raw.getvalue())
        path.write_bytes(b"source changed during decode")
        return original_decoder(raw, *args, **kwargs)
    monkeypatch.setattr(pd, "read_parquet", decode)
    with pytest.raises(ResearchHistoryUnavailable, match="artifact_source_changed"):
        lookup.resolve(selected)
    assert decoded == [original_raw]


def test_legacy_source_swap_after_read_refused_even_same_size_and_mtime(tmp_path, monkeypatch):
    from app_module.research_history_lookup import _ReadRound
    _, lookup, *_ = fixed_sources(tmp_path)
    selected = next(e for e in lookup.list_entries().entries if e.run_type == "legacy_backtest")
    path = tmp_path / "legacy.parquet"
    stamp = path.stat()
    replacement = tmp_path / "replacement.parquet"
    replacement.write_bytes(path.read_bytes())
    os.utime(replacement, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    original_read = _ReadRound.read
    def swapped(self, source, **kwargs):
        result = original_read(self, source, **kwargs)
        if source == path:
            replacement.replace(path)
        return result
    monkeypatch.setattr(_ReadRound, "read", swapped)
    monkeypatch.setattr(pd, "read_parquet", lambda *_: pytest.fail("來源已替換仍 decode"))
    with pytest.raises(ResearchHistoryUnavailable, match="artifact_source_changed"):
        lookup.resolve(selected)


def test_legacy_source_missing_after_read_returns_unavailable(tmp_path, monkeypatch):
    from app_module.research_history_lookup import _ReadRound
    _, lookup, *_ = fixed_sources(tmp_path)
    selected = next(e for e in lookup.list_entries().entries if e.run_type == "legacy_backtest")
    path = tmp_path / "legacy.parquet"
    original_read = _ReadRound.read
    def moved(self, source, **kwargs):
        result = original_read(self, source, **kwargs)
        if source == path:
            path.rename(tmp_path / "preserved-source.parquet")
        return result
    monkeypatch.setattr(_ReadRound, "read", moved)
    with pytest.raises(ResearchHistoryUnavailable, match="artifact_source_unavailable"):
        lookup.resolve(selected)


@pytest.mark.parametrize("artifact,total", [(0, 1), (1, 0), (True, 1), (1, "100")])
def test_legacy_budget_requires_explicit_positive_integer_bytes(artifact, total):
    with pytest.raises(ValueError):
        ResearchHistoryReadBudget(max_artifact_bytes=artifact, max_total_bytes=total)
