"""搬移只改新索引；舊根不可用後仍沿原reader重開，金融原件不重算。"""
from dataclasses import asdict, replace
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pandas as pd
import pytest

from app_module.backtest_repository import BacktestRunRepository
from app_module.recommendation_portfolio_run_repository import RecommendationPortfolioRunRepository
from app_module.research_history_lookup import ResearchHistoryUnavailable
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_service import ResearchRunService
from app_module import research_output_copy as copy

BUDGET = copy.ResearchOutputCopyBudget(8 * 1024**2, 32 * 1024**2, 100, 10)


class Config:
    def __init__(self, root):
        self.output_root = root
        self.research_run_db_file = root / "research_runs/research_runs.db"
        self.research_run_parquet_dir = root / "research_runs/parquet"
        self.research_run_staging_dir = root / "research_runs/staging"

    def resolve_output_path(self, relative):
        path = self.output_root / relative
        path.mkdir(parents=True, exist_ok=True)
        return path


def inventory(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "original"
    config = Config(root)
    equity = pd.DataFrame({"日期": ["2026-01-02"], "portfolio_value": [Decimal("1000000.123456789123456789")]})
    trades = pd.DataFrame({"stock_code": ["2330"], "quantity": [2**60 + 7], "price": [Decimal("123.123456789")]})
    service = ResearchRunService(config)
    service.save_run(ResearchRunMetadataDTO(run_id="exact", run_name="原研究", run_type="single_backtest",
        payload_hash="sha256:" + "a" * 64, metrics={"exact": "0.123456789123456789"},
        data_manifest={"original_source": "not_rewritten"}), equity, trades)
    legacy = BacktestRunRepository(config)
    equity_path = legacy.runs_dir / "old_equity_curve.parquet"
    trades_path = legacy.runs_dir / "old_trades.parquet"
    equity.to_parquet(equity_path)
    trades.to_parquet(trades_path)
    with sqlite3.connect(legacy.db_path) as db:
        db.execute("INSERT INTO runs(run_id,run_name,stock_code,created_at,equity_curve_path,trade_list_path) VALUES(?,?,?,?,?,?)",
                   ("old", "原單股", "2330", "2026-01-03", str(equity_path), str(trades_path)))
    portfolio = RecommendationPortfolioRunRepository(config)
    data_path = portfolio.runs_dir / "basket.json"
    data_path.write_text(json.dumps({"run_id": "basket", "result": {"summary": {"total_trades": 0},
        "equity_curve": [{"date": "2026-01-02", "equity": 1000000}], "trades": [],
        "snapshots": [], "period_holdings": [], "stock_contribution": []}}))
    with sqlite3.connect(portfolio.db_path) as db:
        db.execute("INSERT INTO runs(run_id,run_name,created_at,data_path) VALUES(?,?,?,?)",
                   ("basket", "原組合", "2026-01-03", str(data_path)))
    return root


def test_all_three_stores_reopen_without_original_and_without_reencoding(source, tmp_path, monkeypatch):
    before = inventory(source)
    original_lookup = copy._lookup(source, BUDGET)
    original_entry = original_lookup.select_registry_run("exact")
    original = original_lookup.resolve(original_entry).result
    monkeypatch.setattr(pd.DataFrame, "to_parquet", lambda *a, **k: pytest.fail("搬移不可重新序列化金融原件"))
    monkeypatch.setattr(ResearchRunService, "save_run", lambda *a, **k: pytest.fail("不可重建原研究"))
    destination = tmp_path / "new"
    receipt = copy.copy_research_output(source, destination, budget=BUDGET)
    proof = json.loads(receipt.read_bytes())
    assert proof["status"] == "copied_and_public_readers_verified" and len(proof["runs"]) == 3
    assert inventory(source) == before and not (destination / ".research_copy_pending.json").exists()
    for item in proof["source_files"]:
        if not item["path"].endswith(".db"):
            assert sha256((destination / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    # 測試自有暫存根明確位於tmp_path，原根移開後禁止舊路徑fallback。
    assert source.resolve().is_relative_to(tmp_path.resolve())
    source.rename(tmp_path / "source_not_available")
    lookup = copy._lookup(destination, BUDGET)
    saved = lookup.resolve(lookup.select_registry_run("exact")).result
    expected = asdict(original.metadata)
    expected.update(equity_path=saved.metadata.equity_path, trades_path=saved.metadata.trades_path)
    assert asdict(saved.metadata) == expected
    assert saved.equity.equals(original.equity) and saved.trades.equals(original.trades)
    assert saved.equity.iloc[0]["portfolio_value"] == Decimal("1000000.123456789123456789")
    assert saved.trades.iloc[0]["quantity"] == 2**60 + 7
    with pytest.raises((ValueError, ResearchHistoryUnavailable)):
        lookup.resolve(original_entry)
    for kind, run_id in (("legacy_backtest", "old"), ("legacy_recommendation_portfolio", "basket")):
        selected = lookup.select_legacy_run(kind, run_id)
        assert lookup.resolve(selected).entry == selected
    assert not proof["financial_artifacts_reencoded"] and not proof["configuration_activated"]


@pytest.mark.parametrize("kind", ["journal", "staging", "outside_path", "trigger", "scenario", "broken_artifact"])
def test_invalid_source_refused_before_destination_creation(source, tmp_path, monkeypatch, kind):
    if kind == "journal":
        (source / "research_runs/research_runs.db-wal").write_bytes(b"active")
    elif kind == "staging":
        path = source / "research_runs/staging/not_complete.tmp"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"pending")
    elif kind == "outside_path":
        outside = tmp_path / "outside.parquet"
        original = source / "backtest/runs/old_equity_curve.parquet"
        outside.write_bytes(original.read_bytes())
        with sqlite3.connect(source / "backtest/runs/backtest_runs.db") as db:
            db.execute("UPDATE runs SET equity_curve_path=?", (str(outside),))
    elif kind in {"trigger", "scenario"}:
        with sqlite3.connect(source / "research_runs/research_runs.db") as db:
            if kind == "trigger":
                db.execute("CREATE TRIGGER altered AFTER UPDATE ON research_runs BEGIN UPDATE research_runs SET run_name='bad'; END")
            else:
                db.execute("CREATE TABLE portfolio_scenario_registry(payload_json BLOB)")
                db.execute("INSERT INTO portfolio_scenario_registry VALUES('{}')")
    else:
        (source / "backtest/runs/old_equity_curve.parquet").write_bytes(b"not parquet")
    before = inventory(source)
    if kind == "outside_path":
        original_open = Path.open
        def reject_external_read(path, *args, **kwargs):
            if path == outside:
                pytest.fail("來源邊界檢查前不可先讀外部原件")
            return original_open(path, *args, **kwargs)
        monkeypatch.setattr(Path, "open", reject_external_read)
    target = tmp_path / "new"
    with pytest.raises(ValueError):
        copy.copy_research_output(source, target, budget=BUDGET)
    assert not target.exists() and inventory(source) == before


@pytest.mark.parametrize("field,value", [("max_file_bytes", 1), ("max_total_bytes", 1), ("max_entries", 1), ("max_runs", 1)])
def test_explicit_budgets_do_not_truncate_source(source, tmp_path, field, value):
    target = tmp_path / "new"
    with pytest.raises(copy.ResearchOutputCopyError, match="budget"):
        copy.copy_research_output(source, target, budget=replace(BUDGET, **{field: value}))
    assert not target.exists()


def test_destination_cannot_overlap_overwrite_or_enter_protected_root(source, tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        copy.copy_research_output(source, source / "child", budget=BUDGET)
    with pytest.raises(ValueError):
        copy.copy_research_output(source, source, budget=BUDGET)
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "formal"))
    with pytest.raises(ValueError, match="正式"):
        copy.copy_research_output(source, tmp_path / "formal/new", budget=BUDGET)
    assert not (tmp_path / "formal").exists()


def test_cancelled_copy_keeps_failure_and_original(source, tmp_path, monkeypatch):
    before = inventory(source)
    target = tmp_path / "new"
    original_digest = copy._digest
    def fail_during_copy(path, check, destination=None):
        if destination is not None:
            raise copy.ResearchOutputCopyError("research_copy_cancelled")
        return original_digest(path, check, destination)
    monkeypatch.setattr(copy, "_digest", fail_during_copy)
    with pytest.raises(copy.ResearchOutputCopyError, match="cancelled"):
        copy.copy_research_output(source, target, budget=BUDGET)
    assert (target / ".research_copy_pending.json").exists() and (target / "RESEARCH_COPY_FAILURE.json").exists()
    assert not (target / "RESEARCH_COPY_RECEIPT.json").exists() and inventory(source) == before


def test_exact_legacy_selection_uses_same_identity_as_list_and_obeys_cancel(source):
    lookup = copy._lookup(source, BUDGET)
    selected = lookup.select_legacy_run("legacy_backtest", "old")
    assert selected in lookup.list_entries().entries
    with pytest.raises(ValueError, match="cancelled"):
        lookup.select_legacy_run("legacy_backtest", "old", check_cancel=lambda: True)
    with pytest.raises(ValueError):
        lookup.select_legacy_run("not_a_source", "old")


def test_source_revision_during_copy_never_gets_success_receipt(source, tmp_path, monkeypatch):
    target = tmp_path / "new"
    original_digest = copy._digest
    revised = False
    def change_after_copy(path, check, destination=None):
        nonlocal revised
        digest = original_digest(path, check, destination)
        if destination is not None and not revised:
            revised = True
            artifact = source / "research_runs/parquet"
            selected = next(artifact.glob("*equity.parquet"))
            selected.write_bytes(selected.read_bytes() + b"external_revision")
        return digest
    monkeypatch.setattr(copy, "_digest", change_after_copy)
    with pytest.raises(ValueError, match="SHA|變更"):
        copy.copy_research_output(source, target, budget=BUDGET)
    assert not (target / "RESEARCH_COPY_RECEIPT.json").exists()


def test_destination_revision_after_public_read_is_not_accepted(source, tmp_path, monkeypatch):
    target = tmp_path / "new"
    before = inventory(source)
    original_entry = copy._entry
    def change_after_read(lookup, kind, run_id, check):
        selected = original_entry(lookup, kind, run_id, check)
        database = lookup.registry.repository.db_path
        if kind == "registry" and database.is_relative_to(target):
            with sqlite3.connect(database) as db:
                db.execute("UPDATE research_runs SET run_name='external revision'")
        return selected
    monkeypatch.setattr(copy, "_entry", change_after_read)
    with pytest.raises(copy.ResearchOutputCopyError, match="副本.*變更"):
        copy.copy_research_output(source, target, budget=BUDGET)
    assert not (target / "RESEARCH_COPY_RECEIPT.json").exists() and inventory(source) == before


def test_cli_creates_new_copy_and_fresh_process_can_read_it(source, tmp_path):
    destination = tmp_path / "cli-new"
    completed = subprocess.run([sys.executable, "-X", "utf8", "-B", "scripts/copy_research_output.py",
        "--source-output-root", str(source), "--destination-output-root", str(destination)],
        capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert json.loads((destination / "RESEARCH_COPY_RECEIPT.json").read_bytes())["source_unchanged"]
