"""P2 真實 synthetic writer／selected routing；不使用正式資料或排程。"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import app_module.paper_equal_weight_benchmark_builder as producer
from app_module.paper_equal_weight_benchmark_builder import PaperEqualWeightBenchmarkBuilder
from app_module.paper_equal_weight_benchmark_ledger import EqualWeightBenchmarkLedger
from app_module.paper_trade_ledger import PaperTradeLedgerRepository, PaperTradeFill
from app_module.personal_data_paths import PersonalDataPaths, to_internal_io_path
from app_module.personal_paper_store_paths import PersonalPaperStorePaths, PersonalStoreCustody
from app_module.personal_store_routes import PersonalStoreDomain, PersonalStoreMode, StoreIdentity, select_personal_store_route
import scripts.run_paper_portfolio_daily as daily
import scripts.build_paper_equal_weight_benchmark as cli

ACCOUNT = "synthetic-account"
BENCHMARK = "separate-equal"
AT = datetime.fromisoformat("2026-08-21T08:30:00+08:00")
NOW = datetime.fromisoformat("2026-08-22T08:30:00+08:00")


class Calendar:
    def is_official_trading_day(self, day):
        return True, "synthetic_official_open"


def io(path):
    return Path(to_internal_io_path(path))


def pin(path):
    p = io(path)
    return hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns


def setup(tmp_path, *, deep=False):
    if deep:
        tmp_path = tmp_path.joinpath(*(["中文😀" + "深" * 30] * 5))
    paths = PersonalDataPaths(tmp_path / "market", tmp_path / "legacy", tmp_path / "private")
    route = select_personal_store_route(domain=PersonalStoreDomain.PAPER,
                                      mode=PersonalStoreMode.PERSONAL,
                                      identity=StoreIdentity(ACCOUNT), personal_paths=paths)
    pp = PersonalPaperStorePaths.from_route(route, portfolio_id=ACCOUNT)
    io(pp.baseline).parent.mkdir(parents=True)
    io(paths.market_root / "sqlite").mkdir(parents=True)
    io(paths.legacy_output_root).mkdir(parents=True)
    sentinel = paths.legacy_output_root / "sentinel.json"
    io(sentinel).write_text("原始 legacy", encoding="utf-8")
    baseline = dict(decision_date="2026-08-20", portfolio_id=ACCOUNT, source_result_id="frozen-source",
                    residual_cash="900", research_only=True, writes_positions_db=False,
                    broker_order_allowed=False, auto_rebalance_allowed=False,
                    allocations=[dict(stock_code="2330", executable_shares=1,
                                      reference_price="100", executable_amount="100")])
    io(pp.baseline).write_text(json.dumps(baseline), encoding="utf-8")
    market = paths.market_root / "sqlite" / "twstock.db"
    with sqlite3.connect(to_internal_io_path(market)) as conn:
        conn.execute('CREATE TABLE daily_prices ("證券代號" TEXT, "日期" TEXT, "收盤價" TEXT)')
        conn.execute('INSERT INTO daily_prices VALUES ("2330", "20260820", "105")')
        conn.execute('INSERT INTO daily_prices VALUES ("2330", "20260821", "99999")')
    conn.close()
    return paths, route, pp, market, sentinel


def build(paths, route):
    return PaperEqualWeightBenchmarkBuilder(portfolio_id=ACCOUNT, benchmark_id=BENCHMARK,
                                           route=route, personal_paths=paths,
                                           today_provider=lambda: date(2026, 8, 22))


def preview(builder, pp, market):
    return builder.preview(baseline_path=pp.baseline, state_db_path=pp.state_db,
                           market_db_path=market, output_ledger_path=pp.benchmark_db)


def run(paths, route, pp, market, **kwargs):
    options = dict(baseline_path=pp.baseline, state_db=pp.state_db, market_db=market,
                   output_root=pp.status.parents[2], route=route, personal_paths=paths,
                   ledger_db=pp.cost_ledger_db, decision_at=AT, now=NOW, calendar=Calendar())
    options.update(kwargs)
    return daily.run(**options)


def write_fill(paths, route, pp):
    repo = PaperTradeLedgerRepository(pp.cost_ledger_db, route=route, personal_paths=paths, portfolio_id=ACCOUNT)
    repo.append(PaperTradeFill(fill_id="fill-1", order_id="order-1", portfolio_id=ACCOUNT,
                              event_date="2026-08-20", stock_code="2330", side="buy",
                              requested_quantity=1, filled_quantity=1, reference_price=Decimal("100"),
                              fill_price=Decimal("100"), commission=Decimal("1"), tax=Decimal("0"),
                              slippage_cost=Decimal("0"), turnover_bp=100, execution_gap_bp=0,
                              status="filled", source_event_id="pinned-event",
                              source_type="paper_daily_execution_v1"))


@pytest.mark.parametrize("deep", [False, True])
def test_real_chain_new_process_b09_same_account_and_source_pins(tmp_path, deep):
    paths, route, pp, market, sentinel = setup(tmp_path, deep=deep)
    pins = pin(market), pin(sentinel), pin(pp.baseline)
    write_fill(paths, route, pp)
    payload = run(paths, route, pp, market)
    assert payload["cash"] == "799.00"
    assert payload["portfolio_id"] == ACCOUNT
    assert payload["paper_ledger_transitions_applied"] == 1
    b = build(paths, route)
    before = pin(pp.state_db), pin(pp.cost_ledger_db)
    p = preview(b, pp, market)
    assert not io(pp.benchmark_db).exists()
    with pytest.raises(ValueError, match="confirm"):
        b.commit(p)
    assert not io(pp.benchmark_db).exists()
    b.commit(p, confirm=True)
    entries = EqualWeightBenchmarkLedger(pp.benchmark_db, route=route, personal_paths=paths,
                    portfolio_id=ACCOUNT, benchmark_id=BENCHMARK, read_only=True).list(BENCHMARK)
    assert entries[-1].total_value == Decimal("1050.00")
    code = """
import json,sys
from pathlib import Path
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_store_routes import *
from app_module.paper_portfolio_readiness_service import PaperPortfolioReadinessService
from app_module.paper_portfolio_weekly_evidence_service import PaperPortfolioWeeklyEvidenceService
root=Path(sys.argv[1])
paths=PersonalDataPaths(root/'market',root/'legacy',root/'private')
route=select_personal_store_route(domain=PersonalStoreDomain.PAPER,mode=PersonalStoreMode.PERSONAL,
 identity=StoreIdentity('synthetic-account'),personal_paths=paths)
kw=dict(output_root=paths.legacy_output_root,route=route,personal_paths=paths,
 portfolio_id='synthetic-account',benchmark_id='separate-equal')
r=PaperPortfolioReadinessService(**kw).inspect().to_dict()
w=PaperPortfolioWeeklyEvidenceService(**kw).build(period_start='2026-08-20',period_end='2026-08-21',
 expected_trading_days=2).to_dict()
print(json.dumps(dict(readiness=r,weekly=w)))
"""
    allpins = [pin(x) for x in (pp.state_db, pp.cost_ledger_db, pp.benchmark_db, pp.status)]
    result = subprocess.run([sys.executable, "-c", code, str(paths.market_root.parent)],
                            capture_output=True, text=True, encoding="utf-8", check=True)
    readback = json.loads(result.stdout)
    assert readback["readiness"]["snapshot_count"] == 2
    assert readback["readiness"]["cost_record_count"] == 1
    assert readback["weekly"]["portfolio_id"] == ACCOUNT
    assert readback["weekly"]["benchmark_id"] == BENCHMARK
    assert readback["weekly"]["benchmark_observation_count"] == 2
    assert readback["weekly"]["investment_effectiveness_claim"] is False
    assert allpins == [pin(x) for x in (pp.state_db, pp.cost_ledger_db, pp.benchmark_db, pp.status)]
    assert before == (pin(pp.state_db), pin(pp.cost_ledger_db))
    assert pins == (pin(market), pin(sentinel), pin(pp.baseline))


@pytest.mark.parametrize("field", ["baseline_path", "state_db", "ledger_db", "output_root", "market_db"])
def test_daily_overrides_reject_before_creation(tmp_path, field):
    paths, route, pp, market, sentinel = setup(tmp_path)
    bad = paths.personal_root / "wrong.sqlite"
    if field == "market_db":
        bad = pp.state_db
    with pytest.raises(ValueError):
        run(paths, route, pp, market, **{field: bad})
    assert not io(pp.state_db).exists()
    assert not io(pp.status).exists()
    assert not io(bad).exists()


def test_identity_missing_paths_and_readonly_writer_before_io(tmp_path):
    paths, route, pp, market, sentinel = setup(tmp_path)
    with pytest.raises(ValueError):
        PaperEqualWeightBenchmarkBuilder(route=route, personal_paths=paths, portfolio_id="wrong")
    with pytest.raises(ValueError):
        build(None, route)
    readonly = select_personal_store_route(domain=PersonalStoreDomain.PAPER, mode=PersonalStoreMode.LEGACY_READ_ONLY,
                identity=StoreIdentity(ACCOUNT), personal_paths=paths)
    rpp = PersonalPaperStorePaths.from_route(readonly, portfolio_id=ACCOUNT)
    with pytest.raises(ValueError, match="read_only"):
        run(paths, readonly, rpp, market)
    with pytest.raises(ValueError, match="read_only"):
        PaperEqualWeightBenchmarkBuilder.write_new_ledger(rpp.benchmark_db, (), route=readonly,
                        personal_paths=paths, portfolio_id=ACCOUNT, benchmark_id=BENCHMARK)
    assert not io(rpp.state_db).exists()
    assert not io(rpp.benchmark_db).exists()


@pytest.mark.parametrize("future", [True, False])
def test_future_and_unknown_do_not_write_state_or_raise_credit(tmp_path, future):
    paths, route, pp, market, sentinel = setup(tmp_path)
    class Unknown:
        def is_official_trading_day(self, day):
            return None, "synthetic_unknown"
    payload = run(paths, route, pp, market, now=AT.replace(day=20) if future else NOW, calendar=Unknown())
    assert payload["status"] == ("skipped_future_decision" if future else "degraded_calendar_unknown")
    assert payload["snapshot_appended"] is False
    assert not io(pp.state_db).exists()
    assert io(pp.status).exists()


@pytest.mark.parametrize("swap", ["baseline", "state", "sidecar"])
def test_post_preview_alias_rejected_without_publication(tmp_path, swap):
    paths, route, pp, market, sentinel = setup(tmp_path)
    run(paths, route, pp, market)
    b = build(paths, route)
    p = preview(b, pp, market)
    target = dict(baseline=pp.baseline, state=pp.state_db,
                  sidecar=pp.benchmark_db.with_name(pp.benchmark_db.name + "-wal"))[swap]
    if io(target).exists():
        io(target).unlink()
    os.link(io(sentinel), io(target))
    before = pin(sentinel)
    with pytest.raises(ValueError):
        b.commit(p, confirm=True)
    assert pin(sentinel) == before
    assert not io(pp.benchmark_db).exists()


@pytest.mark.parametrize("failure", ["partial", "temp_alias", "temp_sidecar", "publication_race"])
def test_staging_failures_preserve_target_and_sources(tmp_path, monkeypatch, failure):
    paths, route, pp, market, sentinel = setup(tmp_path)
    run(paths, route, pp, market)
    b = build(paths, route)
    p = preview(b, pp, market)
    pins = pin(market), pin(sentinel), pin(pp.state_db)
    real_append = producer._GeneratedBenchmarkLedger.append
    count = 0
    def append(self, entry):
        nonlocal count
        count += 1
        if failure == "partial" and count == 2:
            raise RuntimeError("synthetic partial failure")
        if failure in {"temp_alias", "temp_sidecar"} and count == 1:
            target = self.staging.path if failure == "temp_alias" else self.staging.path.with_name(self.staging.path.name + "-journal")
            if io(target).exists():
                io(target).unlink()
            os.link(io(sentinel), io(target))
        real_append(self, entry)
        if failure == "publication_race" and count == 2:
            io(pp.benchmark_db).write_bytes(b"racing-target")
    monkeypatch.setattr(producer._GeneratedBenchmarkLedger, "append", append)
    with pytest.raises((ValueError, RuntimeError)):
        b.commit(p, confirm=True)
    if failure == "publication_race":
        assert io(pp.benchmark_db).read_bytes() == b"racing-target"
    else:
        assert not io(pp.benchmark_db).exists()
    assert pins == (pin(market), pin(sentinel), pin(pp.state_db))
    if failure == "partial":
        assert not list(io(pp.benchmark_db.parent).glob("*.tmp.sqlite"))


@pytest.mark.parametrize("values", [
    {"PERSONAL_STORE_ROOT": "root"}, {"PERSONAL_STORE_MODE": "personal"},
    {"PERSONAL_STORE_ROOT": "", "PERSONAL_STORE_MODE": ""},
    {"PERSONAL_STORE_ROOT": "root", "PERSONAL_STORE_MODE": "unknown"},
])
@pytest.mark.parametrize("which", ["daily", "benchmark"])
def test_cli_bad_config_no_legacy_error_status(tmp_path, monkeypatch, capsys, values, which):
    for key in ("PERSONAL_STORE_ROOT", "PERSONAL_STORE_MODE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, str(tmp_path / value) if key.endswith("ROOT") and value else value)
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "market"))
    legacy = tmp_path / "legacy"
    monkeypatch.setenv("OUTPUT_ROOT", str(legacy))
    assert (daily.main([]) if which == "daily" else cli.main([])) == 2
    assert json.loads(capsys.readouterr().out)["status"] in {"failed", "rejected"}
    assert not legacy.exists()


def test_selected_both_cli_ignore_legacy_ledger_env_and_reject_override(tmp_path, monkeypatch, capsys):
    paths, route, pp, market, sentinel = setup(tmp_path)
    monkeypatch.setenv("DATA_ROOT", str(paths.market_root))
    monkeypatch.setenv("OUTPUT_ROOT", str(paths.legacy_output_root))
    monkeypatch.setenv("PERSONAL_STORE_ROOT", str(paths.personal_root))
    monkeypatch.setenv("PERSONAL_STORE_MODE", "personal")
    monkeypatch.setenv("PAPER_EXECUTION_LEDGER_DB", str(sentinel))
    monkeypatch.setattr(daily, "OfficialTradingCalendar", lambda **kw: Calendar())
    write_fill(paths, route, pp)
    assert daily.main(["--portfolio-id", ACCOUNT, "--decision-at", AT.isoformat()]) == 0
    assert json.loads(capsys.readouterr().out)["cash"] == "799.00"
    assert cli.main(["--portfolio-id", ACCOUNT, "--benchmark-id", BENCHMARK]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "preview"
    assert not io(pp.benchmark_db).exists()
    assert cli.main(["--portfolio-id", ACCOUNT, "--benchmark-id", BENCHMARK, "--confirm-build-paper-benchmark"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "built"
    pins = pin(pp.status), pin(sentinel)
    assert daily.main(["--portfolio-id", ACCOUNT, "--ledger-db", str(sentinel)]) == 2
    capsys.readouterr()
    assert pins == (pin(pp.status), pin(sentinel))
    assert cli.main(["--portfolio-id", ACCOUNT]) == 2
    capsys.readouterr()


def test_cancel_preview_does_not_create_ledger(tmp_path):
    from app_module.sqlite_read_only import cooperative_read_cancellation, ReadOperationCancelled
    paths, route, pp, market, sentinel = setup(tmp_path)
    run(paths, route, pp, market)
    before = pin(pp.state_db)
    with pytest.raises(ReadOperationCancelled):
        with cooperative_read_cancellation(lambda: True):
            preview(build(paths, route), pp, market)
    assert pin(pp.state_db) == before
    assert not io(pp.benchmark_db).exists()

@pytest.mark.parametrize("which", ["baseline", "state", "cost", "status"])
def test_post_constructor_swaps_rejected_before_daily_io(tmp_path, which):
    paths, route, pp, market, sentinel = setup(tmp_path)
    b = build(paths, route)
    target = dict(baseline=pp.baseline, state=pp.state_db, cost=pp.cost_ledger_db, status=pp.status)[which]
    io(target).parent.mkdir(parents=True, exist_ok=True)
    if io(target).exists():
        io(target).unlink()
    os.link(io(sentinel), io(target))
    before = pin(sentinel)
    with pytest.raises(ValueError):
        run(paths, route, pp, market)
    if which in {"baseline", "state"}:
        with pytest.raises(ValueError):
            preview(b, pp, market)
    assert pin(sentinel) == before
    assert not io(pp.benchmark_db).exists()


def test_lexical_alias_not_resolved_before_selected_validation(tmp_path):
    paths, route, pp, market, sentinel = setup(tmp_path)
    bad = pp.baseline.parent / "other" / ".." / pp.baseline.name
    with pytest.raises(ValueError):
        run(paths, route, pp, market, baseline_path=bad)
    target = pp.benchmark_db.parent / "other" / ".." / pp.benchmark_db.name
    with pytest.raises(ValueError):
        build(paths, route).write_new_ledger(target, (), route=route, personal_paths=paths,
                                            portfolio_id=ACCOUNT, benchmark_id=BENCHMARK)
    assert not io(pp.state_db).exists()


def test_private_missing_baseline_never_falls_back(tmp_path):
    paths, route, pp, market, sentinel = setup(tmp_path)
    io(pp.baseline).unlink()
    old = paths.legacy_output_root / "paper_portfolio" / pp.baseline.name
    io(old).parent.mkdir(parents=True)
    io(old).write_bytes(b"legacy must not be read")
    before = pin(old)
    with pytest.raises(FileNotFoundError):
        run(paths, route, pp, market)
    assert pin(old) == before
    assert not io(pp.state_db).exists()
    assert not io(pp.status).exists()


def test_post_preview_junction_parent_rejected(tmp_path):
    paths, route, pp, market, sentinel = setup(tmp_path)
    run(paths, route, pp, market)
    b = build(paths, route)
    p = preview(b, pp, market)
    parent = pp.baseline.parent
    moved = parent.with_name("paper_original")
    os.rename(io(parent), io(moved))
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(parent), str(moved)], capture_output=True)
        if result.returncode:
            pytest.skip("host cannot create synthetic junction")
    else:
        parent.symlink_to(moved, target_is_directory=True)
    pins = pin(market), pin(sentinel)
    with pytest.raises(ValueError):
        b.commit(p, confirm=True)
    assert pins == (pin(market), pin(sentinel))
    assert not io(moved / pp.benchmark_db.name).exists()


def test_daily_status_temporary_alias_does_not_replace_target(tmp_path, monkeypatch):
    paths, route, pp, market, sentinel = setup(tmp_path)
    original = producer.GeneratedPaperStaging.guard
    once = False
    def guard(self, path):
        nonlocal once
        # constructor 已取得 identity 後才置換。
        if self.path == path and self.path.suffix == ".tmp" and not once and hasattr(self, "_ready_for_swap"):
            once = True
            os.link(io(path), io(sentinel.parent / "status-temp-hardlink"))
        return original(self, path)
    init = producer.GeneratedPaperStaging.__init__
    def initialize(self, *args, **kw):
        init(self, *args, **kw)
        self._ready_for_swap = True
    monkeypatch.setattr(producer.GeneratedPaperStaging, "__init__", initialize)
    monkeypatch.setattr(producer.GeneratedPaperStaging, "guard", guard)
    before = pin(sentinel)
    with pytest.raises(ValueError):
        run(paths, route, pp, market, now=AT.replace(day=20))
    assert pin(sentinel) == before
    assert not io(pp.status).exists()


def test_readonly_benchmark_preview_is_pure(tmp_path):
    paths, route, pp, market, sentinel = setup(tmp_path)
    run(paths, route, pp, market)
    legacypp = paths.legacy_output_root / "paper_portfolio"
    io(legacypp).mkdir()
    for source in (pp.baseline, pp.state_db):
        io(legacypp / source.name).write_bytes(io(source).read_bytes())
    readonly = select_personal_store_route(domain=PersonalStoreDomain.PAPER, mode=PersonalStoreMode.LEGACY_READ_ONLY,
                identity=StoreIdentity(ACCOUNT), personal_paths=paths)
    rpp = PersonalPaperStorePaths.from_route(readonly, portfolio_id=ACCOUNT)
    b = build(paths, readonly)
    pins = pin(rpp.baseline), pin(rpp.state_db)
    p = preview(b, rpp, market)
    with pytest.raises(ValueError, match="read_only"):
        b.commit(p, confirm=True)
    assert pins == (pin(rpp.baseline), pin(rpp.state_db))
    assert not io(rpp.benchmark_db).exists()

def test_explicit_benchmark_and_baseline_identity_required_before_schema(tmp_path):
    paths, route, pp, market, sentinel = setup(tmp_path)
    with pytest.raises(ValueError, match="benchmark_identity_required"):
        PaperEqualWeightBenchmarkBuilder(portfolio_id=ACCOUNT, route=route, personal_paths=paths)
    raw = json.loads(io(pp.baseline).read_text(encoding="utf-8"))
    raw["portfolio_id"] = "other-account"
    io(pp.baseline).write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="baseline_identity_mismatch"):
        run(paths, route, pp, market)
    with pytest.raises(ValueError, match="baseline_identity_mismatch"):
        preview(build(paths, route), pp, market)
    assert not io(pp.state_db).exists()
    assert not io(pp.status).exists()
    assert not io(pp.benchmark_db).exists()


def test_public_writer_never_treats_arbitrary_path_as_selected_staging(tmp_path):
    paths, route, pp, market, sentinel = setup(tmp_path)
    wrong = pp.benchmark_db.parent / ".paper_equal_weight_benchmark.arbitrary.tmp.sqlite"
    with pytest.raises(ValueError, match="override_mismatch"):
        PaperEqualWeightBenchmarkBuilder.write_new_ledger(wrong, (), route=route, personal_paths=paths,
                                    portfolio_id=ACCOUNT, benchmark_id=BENCHMARK)
    assert not io(wrong).exists()


def test_repreview_changed_prices_rejects_publication(tmp_path):
    paths, route, pp, market, sentinel = setup(tmp_path)
    run(paths, route, pp, market)
    b = build(paths, route)
    p = preview(b, pp, market)
    with sqlite3.connect(to_internal_io_path(market)) as conn:
        conn.execute('UPDATE daily_prices SET "收盤價" = "106" WHERE "日期" = "20260820"')
    with pytest.raises(ValueError, match="inputs changed"):
        b.commit(p, confirm=True)
    assert not io(pp.benchmark_db).exists()


def test_legacy_relative_status_api_remains_compatible(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    daily._atomic_write_json(Path("relative/status.json"), {"status": "synthetic"})
    assert json.loads((tmp_path / "relative/status.json").read_text(encoding="utf-8"))["status"] == "synthetic"


@pytest.mark.parametrize("suffix", ["", "-journal", "-wal", "-shm"])
@pytest.mark.parametrize("consumer", ["daily", "builder"])
def test_market_custody_outside_hardlink_to_private_rejected_before_write(tmp_path, suffix, consumer):
    paths, route, pp, market, sentinel = setup(tmp_path)
    if consumer == "builder":
        run(paths, route, pp, market)
    hidden = paths.personal_root / "hidden-market.sqlite"
    if suffix:
        io(hidden).write_bytes(io(market).read_bytes())
    else:
        os.rename(io(market), io(hidden))
    alias = market.with_name(market.name + suffix)
    os.link(io(hidden), io(alias))
    pins = pin(hidden), pin(sentinel)
    assert io(alias).stat().st_nlink == 2
    with pytest.raises(ValueError, match="paper_market_alias_or_type"):
        if consumer == "daily":
            run(paths, route, pp, market)
        else:
            preview(build(paths, route), pp, market)
    assert pins == (pin(hidden), pin(sentinel))
    assert not io(pp.benchmark_db).exists()
    if consumer == "daily":
        assert not io(pp.state_db).exists()
        assert not io(pp.status).exists()


@pytest.mark.parametrize("consumer", ["daily", "builder"])
def test_market_custody_junction_ancestor_rejected_before_write(tmp_path, consumer):
    paths, route, pp, market, sentinel = setup(tmp_path)
    if consumer == "builder":
        run(paths, route, pp, market)
    original = market.parent
    hidden = paths.personal_root / "hidden-market-tree"
    os.rename(io(original), io(hidden))
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(original), str(hidden)], capture_output=True)
        if result.returncode:
            pytest.skip("host cannot create synthetic junction")
    else:
        original.symlink_to(hidden, target_is_directory=True)
    pins = pin(hidden / market.name), pin(sentinel)
    with pytest.raises(ValueError, match="linked_path"):
        if consumer == "daily":
            run(paths, route, pp, market)
        else:
            preview(build(paths, route), pp, market)
    assert pins == (pin(hidden / market.name), pin(sentinel))
    assert not io(pp.benchmark_db).exists()
    if consumer == "daily":
        assert not io(pp.state_db).exists()
        assert not io(pp.status).exists()


def test_market_custody_calendar_constructor_swap_not_swallowed(tmp_path, monkeypatch):
    paths, route, pp, market, sentinel = setup(tmp_path)
    hidden = paths.personal_root / "hidden-market.sqlite"
    class SwappingCalendar:
        def __init__(self, **kwargs):
            os.rename(io(market), io(hidden))
            os.link(io(hidden), io(market))
        def is_official_trading_day(self, day):
            pytest.fail("custody must reject before calendar read")
    monkeypatch.setattr(daily, "OfficialTradingCalendar", SwappingCalendar)
    source = pin(market)
    with pytest.raises(ValueError, match="paper_market_alias_or_type"):
        run(paths, route, pp, market, calendar=None)
    assert pin(hidden) == source
    assert not io(pp.state_db).exists()
    assert not io(pp.status).exists()


def test_market_custody_calendar_read_swap_rejected_outside_degraded_handler(tmp_path):
    paths, route, pp, market, sentinel = setup(tmp_path)
    class SwappingCalendar:
        def is_official_trading_day(self, day):
            hidden = paths.personal_root / "hidden-market.sqlite"
            os.rename(io(market), io(hidden))
            os.link(io(hidden), io(market))
            raise RuntimeError("synthetic calendar failure")
    with pytest.raises(ValueError, match="paper_market_alias_or_type"):
        run(paths, route, pp, market, calendar=SwappingCalendar())
    assert not io(pp.state_db).exists()
    assert not io(pp.status).exists()


@pytest.mark.parametrize("consumer", ["daily", "builder"])
def test_market_custody_guard_at_each_price_connect_after_swap(tmp_path, consumer):
    paths, route, pp, market, sentinel = setup(tmp_path)
    hidden = paths.personal_root / "hidden-market.sqlite"
    os.rename(io(market), io(hidden))
    os.link(io(hidden), io(market))
    before = pin(hidden)
    with pytest.raises(ValueError, match="paper_market_alias_or_type"):
        if consumer == "daily":
            daily._latest_prices(market, symbols=("2330",), decision_date="2026-08-21", personal_paths=paths)
        else:
            build(paths, route)._latest_price_observations(market, symbols=("2330",), decision_date="2026-08-21")
    assert pin(hidden) == before
    assert not io(pp.state_db).exists()


def test_market_custody_legacy_relative_market_read_compatible(tmp_path, monkeypatch):
    paths, route, pp, market, sentinel = setup(tmp_path)
    monkeypatch.chdir(paths.market_root.parent)
    before = pin(market)
    rows = daily._latest_prices(Path("market/sqlite/twstock.db"), symbols=("2330",), decision_date="2026-08-21")
    assert rows[0].close == Decimal("105")
    assert producer.require_market_separation(Path("market/sqlite/twstock.db"), None) == market
    assert pin(market) == before


def test_market_custody_calendar_guard_error_is_never_degraded(tmp_path):
    from app_module.personal_data_paths import PersonalDataPathError
    paths, route, pp, market, sentinel = setup(tmp_path)
    class RejectedCalendar:
        def is_official_trading_day(self, day):
            raise PersonalDataPathError("paper_market_alias_or_type", market)
    with pytest.raises(ValueError, match="paper_market_alias_or_type"):
        run(paths, route, pp, market, calendar=RejectedCalendar())
    assert not io(pp.state_db).exists()
    assert not io(pp.status).exists()
