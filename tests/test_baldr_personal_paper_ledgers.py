"""P1 精確路由 custody；所有寫入只在 pytest synthetic tmp_path。"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app_module.paper_trade_ledger import PaperTradeFill, PaperTradeLedgerRepository, PaperTradeTransition
from app_module.paper_equal_weight_benchmark_ledger import EqualWeightBenchmarkLedger, EqualWeightBenchmarkService
from app_module.personal_data_paths import PersonalDataPaths, to_internal_io_path
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.personal_store_routes import (
    PersonalStoreDomain, PersonalStoreMode, StoreIdentity, select_personal_store_route,
)

ACCOUNT = "synthetic-paper-account"
BENCHMARK = "synthetic-equal-benchmark"


def selection(tmp_path: Path, *, mode: PersonalStoreMode = PersonalStoreMode.PERSONAL):
    paths = PersonalDataPaths(tmp_path / "market", tmp_path / "legacy", tmp_path / "personal")
    route = select_personal_store_route(
        domain=PersonalStoreDomain.PAPER, mode=mode, identity=StoreIdentity(ACCOUNT),
        personal_paths=paths,
    )
    return paths, route, PersonalPaperStorePaths.from_route(route, portfolio_id=ACCOUNT)


def fill(fill_id: str = "fill-1") -> PaperTradeFill:
    return PaperTradeFill(
        fill_id=fill_id, order_id="order-1", portfolio_id=ACCOUNT, event_date="2026-08-27",
        stock_code="2330", side="buy", requested_quantity=1000, filled_quantity=1000,
        reference_price=Decimal("100"), fill_price=Decimal("100.08"),
        commission=Decimal("15"), tax=Decimal("0"), slippage_cost=Decimal("8"),
        turnover_bp=120, execution_gap_bp=8, status="filled", source_event_id="event-" + fill_id,
    )


def transition(fill_id: str = "fill-1", transition_id: str = "transition-1") -> PaperTradeTransition:
    return PaperTradeTransition(
        transition_id=transition_id, batch_id="batch-1", portfolio_id=ACCOUNT,
        event_date="2026-08-27", fill_ids=(fill_id,), pre_cash=Decimal("200000"),
        pre_total_value=Decimal("200000"), post_cash=Decimal("99905"),
        post_total_value=Decimal("199985"), common_nav=Decimal("200000"),
        common_prices={"2330": Decimal("100.08")}, pre_positions={}, post_positions={"2330": 1000},
    )


def entry():
    return EqualWeightBenchmarkService().create_baseline(
        benchmark_id=BENCHMARK, decision_date="2026-08-27", capital=Decimal("200000"),
        prices={"2330": Decimal("100")},
    )


def repository(kind: str, paths, route, pp, **kwargs):
    options = dict(route=route, personal_paths=paths, portfolio_id=ACCOUNT)
    options.update(kwargs)
    if kind == "trade":
        return PaperTradeLedgerRepository(pp.cost_ledger_db, **options)
    return EqualWeightBenchmarkLedger(pp.benchmark_db, benchmark_id=BENCHMARK, **options)


def append(repo, kind: str):
    if kind == "trade":
        repo.append(fill())
    else:
        repo.append(entry())


def read(repo, kind: str):
    return repo.list(portfolio_id=ACCOUNT) if kind == "trade" else repo.list(BENCHMARK)


def snapshot(path: Path):
    return path.read_bytes(), hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


@pytest.mark.parametrize("deep", [False, True])
def test_selected_atomic_save_fresh_process_and_untouched_sentinels(tmp_path: Path, deep: bool):
    if deep:
        tmp_path = tmp_path.joinpath(*(["中文_😀_" + "深" * 28] * 6))
        assert len(str(tmp_path).encode("utf-16-le")) // 2 > 260
    paths, route, pp = selection(tmp_path)
    # sentinel 是 synthetic，不能接觸正式市場／legacy。
    sentinels = (paths.market_root / "market.sqlite", paths.legacy_output_root / "legacy.sqlite")
    for path in sentinels:
        Path(to_internal_io_path(path)).parent.mkdir(parents=True, exist_ok=True)
        Path(to_internal_io_path(path)).write_bytes(b"synthetic sentinel")
    before = tuple(snapshot(Path(to_internal_io_path(path))) for path in sentinels)
    trade = repository("trade", paths, route, pp)
    trade.append_batch((fill(),), transition())
    benchmark = repository("benchmark", paths, route, pp)
    benchmark.append(entry())
    assert trade.list(portfolio_id=ACCOUNT) == (fill(),)
    assert trade.list_transitions(portfolio_id=ACCOUNT) == (transition(),)
    assert trade.schema_readback()["row_counts"] == {"paper_trade_ledger": 1, "paper_trade_transitions": 1}
    assert benchmark.list(BENCHMARK) == (entry(),)
    # 重複 transition 在 INSERT fills 之後失敗；原 transaction 必須全 rollback。
    with pytest.raises(ValueError, match="already exists"):
        trade.append_batch((fill("fill-2"),), transition("fill-2"))
    assert trade.list(portfolio_id=ACCOUNT) == (fill(),)
    assert trade.list_transitions(portfolio_id=ACCOUNT) == (transition(),)
    script = '''
import json, sys
from pathlib import Path
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_store_routes import *
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.paper_trade_ledger import PaperTradeLedgerRepository
from app_module.paper_equal_weight_benchmark_ledger import EqualWeightBenchmarkLedger
root = Path(sys.argv[1])
paths = PersonalDataPaths(root / 'market', root / 'legacy', root / 'personal')
route = select_personal_store_route(domain=PersonalStoreDomain.PAPER, mode=PersonalStoreMode.PERSONAL, identity=StoreIdentity(sys.argv[2]), personal_paths=paths)
pp = PersonalPaperStorePaths.from_route(route, portfolio_id=sys.argv[2])
trade = PaperTradeLedgerRepository(pp.cost_ledger_db, route=route, personal_paths=paths, portfolio_id=sys.argv[2], read_only=True)
bench = EqualWeightBenchmarkLedger(pp.benchmark_db, route=route, personal_paths=paths, portfolio_id=sys.argv[2], benchmark_id=sys.argv[3], read_only=True)
rows = trade.list(portfolio_id=sys.argv[2])
print(json.dumps({'portfolio': rows[0].portfolio_id, 'cost': str(rows[0].total_cost), 'fills': len(rows), 'transitions': len(trade.list_transitions(portfolio_id=sys.argv[2])), 'benchmark': bench.list(sys.argv[3])[0].benchmark_id, 'path': str(trade.db_path)}))
'''
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), ACCOUNT, BENCHMARK],
        capture_output=True, text=True, check=True,
    )
    receipt = json.loads(completed.stdout)
    assert receipt == dict(portfolio=ACCOUNT, cost="23.00", fills=1, transitions=1,
                           benchmark=BENCHMARK, path=str(pp.cost_ledger_db))
    assert tuple(snapshot(Path(to_internal_io_path(path))) for path in sentinels) == before


@pytest.mark.parametrize("kind", ["trade", "benchmark"])
@pytest.mark.parametrize("fault", ["missing_paths", "missing_account", "wrong_account", "wrong_domain", "wrong_db", "other_root", "readonly_writer", "lexical_alias"])
def test_ctor_rejects_before_any_io(tmp_path: Path, monkeypatch, kind: str, fault: str):
    paths, route, pp = selection(tmp_path)
    options = dict(route=route, personal_paths=paths, portfolio_id=ACCOUNT)
    path = pp.cost_ledger_db if kind == "trade" else pp.benchmark_db
    if fault == "missing_paths":
        options["personal_paths"] = None
    elif fault == "missing_account":
        options["portfolio_id"] = None
    elif fault == "wrong_account":
        options["portfolio_id"] = "other"
    elif fault == "wrong_domain":
        options["route"] = replace(route, domain=PersonalStoreDomain.TRADES)
    elif fault == "wrong_db":
        path = tmp_path / "wrong" / path.name
    elif fault == "other_root":
        options["personal_paths"] = replace(paths, personal_root=tmp_path / "other")
    elif fault == "readonly_writer":
        options["route"] = replace(route, mode=PersonalStoreMode.LEGACY_READ_ONLY, write_target=None)
    elif fault == "lexical_alias":
        path = path.parent / ".." / path.parent.name / path.name
    def forbidden(*args, **kwargs):
        pytest.fail("constructor rejection must precede connect/mkdir")
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    with pytest.raises(ValueError):
        if kind == "trade":
            PaperTradeLedgerRepository(path, **options)
        else:
            EqualWeightBenchmarkLedger(path, benchmark_id=BENCHMARK, **options)
    assert not paths.personal_root.exists()


@pytest.mark.parametrize("benchmark_id", [None, "", " "])
def test_benchmark_requires_independent_caller_identity_before_io(tmp_path: Path, benchmark_id):
    paths, route, pp = selection(tmp_path)
    with pytest.raises(ValueError, match="benchmark_identity_required"):
        EqualWeightBenchmarkLedger(pp.benchmark_db, route=route, personal_paths=paths,
                                   portfolio_id=ACCOUNT, benchmark_id=benchmark_id)
    assert not paths.personal_root.exists()


@pytest.mark.parametrize("kind", ["trade", "benchmark"])
def test_every_reader_is_query_only_and_missing_readonly_never_creates(tmp_path: Path, kind: str):
    paths, route, pp = selection(tmp_path)
    reader = repository(kind, paths, route, pp, read_only=True)
    assert not paths.personal_root.exists()
    with pytest.raises(sqlite3.OperationalError):
        read(reader, kind)
    assert not paths.personal_root.exists()
    writer = repository(kind, paths, route, pp)
    append(writer, kind)
    path = pp.cost_ledger_db if kind == "trade" else pp.benchmark_db
    before = snapshot(path)
    legacy_route = replace(route, mode=PersonalStoreMode.LEGACY_READ_ONLY, write_target=None)
    reader = repository(kind, paths, legacy_route, pp, read_only=True)
    assert len(read(reader, kind)) == 1
    with reader._connect(read_only=True) as conn:
        assert conn.execute("PRAGMA query_only").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE forbidden(value TEXT)")
    with pytest.raises(ValueError, match="read_only_writer_forbidden"):
        append(reader, kind)
    if kind == "trade":
        with pytest.raises(ValueError, match="read_only_writer_forbidden"):
            reader._ensure_schema()
        assert reader.schema_readback()["readback_verified"] is True
    assert snapshot(path) == before


def test_exact_operation_identities_keep_db_unchanged(tmp_path: Path):
    paths, route, pp = selection(tmp_path)
    trade = repository("trade", paths, route, pp)
    benchmark = repository("benchmark", paths, route, pp)
    before = snapshot(pp.cost_ledger_db), snapshot(pp.benchmark_db)
    bad_fill = replace(fill(), portfolio_id="other")
    bad_transition = replace(transition(), portfolio_id="other")
    for operation in (
        lambda: trade.append(bad_fill),
        lambda: trade.append_many((fill(), bad_fill)),
        lambda: trade.append_batch((bad_fill,), bad_transition),
        lambda: trade.list(portfolio_id="other"),
        lambda: trade.list_transitions(portfolio_id="other"),
        lambda: trade.list(),
        lambda: benchmark.append(replace(entry(), benchmark_id=ACCOUNT)),
        lambda: benchmark.list(ACCOUNT),
    ):
        with pytest.raises(ValueError, match="identity_mismatch"):
            operation()
    assert (snapshot(pp.cost_ledger_db), snapshot(pp.benchmark_db)) == before


@pytest.mark.parametrize("kind", ["trade", "benchmark"])
@pytest.mark.parametrize("suffix", ["", "-journal", "-wal", "-shm"])
def test_post_constructor_hardlink_main_and_sidecars_refuse_all_connections(tmp_path: Path, monkeypatch, kind: str, suffix: str):
    paths, route, pp = selection(tmp_path)
    repo = repository(kind, paths, route, pp)
    target = pp.cost_ledger_db if kind == "trade" else pp.benchmark_db
    if suffix:
        sentinel = tmp_path / "unrelated.sqlite"
        sentinel.write_bytes(b"unrelated synthetic data")
        os.link(sentinel, target.with_name(target.name + suffix))
    else:
        sentinel = tmp_path / "alias.sqlite"
        os.link(target, sentinel)
    before = snapshot(sentinel)
    def forbidden(*args, **kwargs):
        pytest.fail("custody must reject before sqlite connect")
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    operations = [lambda: append(repo, kind), lambda: read(repo, kind)]
    if kind == "trade":
        operations += [lambda: repo.list_transitions(portfolio_id=ACCOUNT), repo.schema_readback, repo._ensure_schema]
    for operation in operations:
        with pytest.raises(ValueError):
            operation()
    assert snapshot(sentinel) == before


@pytest.mark.parametrize("kind", ["trade", "benchmark"])
def test_post_constructor_junction_parent_refused(tmp_path: Path, monkeypatch, kind: str):
    if os.name != "nt":
        pytest.skip("Windows junction synthetic coverage")
    paths, route, pp = selection(tmp_path)
    repo = repository(kind, paths, route, pp)
    original = pp.cost_ledger_db.parent
    moved = original.with_name("retained-paper")
    original.rename(moved)
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(original), str(moved)], capture_output=True)
    assert result.returncode == 0, result.stderr
    def forbidden(*args, **kwargs):
        pytest.fail("junction must reject before connect")
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    try:
        with pytest.raises(ValueError):
            read(repo, kind)
        with pytest.raises(ValueError):
            append(repo, kind)
    finally:
        # 只解除本 test 建立且已知的 junction；不遞迴移除 retained synthetic 檔案。
        os.rmdir(original)


@pytest.mark.parametrize("kind", ["trade", "benchmark"])
def test_legacy_compat_route_keeps_original_layout_and_account(tmp_path: Path, kind: str):
    paths, route, pp = selection(tmp_path, mode=PersonalStoreMode.LEGACY_COMPAT)
    repo = repository(kind, paths, route, pp)
    append(repo, kind)
    assert len(read(repo, kind)) == 1
    assert not paths.personal_root.exists()


def test_unconfigured_original_positional_api(tmp_path: Path):
    trade = PaperTradeLedgerRepository(tmp_path / "legacy-trade.sqlite")
    trade.append(replace(fill(), portfolio_id="paper-main"))
    assert len(trade.list()) == 1
    benchmark = EqualWeightBenchmarkLedger(tmp_path / "legacy-benchmark.sqlite")
    benchmark.append(entry())
    assert benchmark.list(BENCHMARK) == (entry(),)


@pytest.mark.parametrize("kind", ["trade", "benchmark"])
def test_legacy_selected_readonly_real_route_and_absent_db(tmp_path: Path, kind: str):
    paths, route, pp = selection(tmp_path, mode=PersonalStoreMode.LEGACY_READ_ONLY)
    reader = repository(kind, paths, route, pp, read_only=True)
    with pytest.raises(sqlite3.OperationalError):
        read(reader, kind)
    assert not paths.legacy_output_root.exists()
    assert not paths.personal_root.exists()
    writer_route = replace(route, mode=PersonalStoreMode.LEGACY_COMPAT, write_target=route.read_source)
    writer = repository(kind, paths, writer_route, pp)
    append(writer, kind)
    target = pp.cost_ledger_db if kind == "trade" else pp.benchmark_db
    before = snapshot(target)
    assert len(read(reader, kind)) == 1
    with pytest.raises(ValueError, match="read_only_writer_forbidden"):
        append(reader, kind)
    assert snapshot(target) == before


@pytest.mark.parametrize("kind", ["trade", "benchmark"])
def test_constructor_sidecar_alias_rejected_before_mkdir_or_schema(tmp_path: Path, monkeypatch, kind: str):
    paths, route, pp = selection(tmp_path)
    target = pp.cost_ledger_db if kind == "trade" else pp.benchmark_db
    target.parent.mkdir(parents=True)
    sentinel = tmp_path / "market-sentinel"
    sentinel.write_bytes(b"synthetic sentinel")
    os.link(sentinel, target.with_name(target.name + "-wal"))
    before = snapshot(sentinel)
    def forbidden(*args, **kwargs):
        pytest.fail("sidecar alias must reject before mkdir/connect/schema")
    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    with pytest.raises(ValueError):
        repository(kind, paths, route, pp)
    assert not target.exists()
    assert snapshot(sentinel) == before


@pytest.mark.parametrize("kind", ["trade", "benchmark"])
def test_unconfigured_explicit_readonly_flag_does_not_create(tmp_path: Path, kind: str):
    target = tmp_path / "absent" / "store.sqlite"
    reader = (PaperTradeLedgerRepository(target, read_only=True) if kind == "trade"
              else EqualWeightBenchmarkLedger(target, read_only=True))
    with pytest.raises(sqlite3.OperationalError):
        read(reader, kind)
    assert not target.parent.exists()


def test_public_trade_db_mutation_refuses_before_file_readback(tmp_path: Path, monkeypatch):
    paths, route, pp = selection(tmp_path)
    trade = repository("trade", paths, route, pp)
    repository("benchmark", paths, route, pp)
    trade.db_path = pp.benchmark_db
    def forbidden(*args, **kwargs):
        pytest.fail("exact selected mismatch must reject before stat/connect")
    monkeypatch.setattr(trade._custody, "exists", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    for operation in (trade.schema_readback, lambda: trade.list(portfolio_id=ACCOUNT), lambda: trade.append(fill())):
        with pytest.raises(ValueError, match="override_mismatch"):
            operation()
