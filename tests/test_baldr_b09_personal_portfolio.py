"""B09 隔離 fixtures：不讀正式資料、不遷移、不授予成交或 PIT 資格。"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_store_routes import (
    PersonalStoreDomain as Domain, PersonalStoreMode as Mode, StoreIdentity,
    PersonalStoreRouteError, select_personal_store_route,
)
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.portfolio_service import PortfolioService
from app_module.portfolio_store import PortfolioJsonlStore
from app_module.user_declared_holding_research import (
    UserDeclaredHoldingDraft, UserDeclaredHoldingResearchStore, UserDeclaredHoldingResearchService,
)
from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioSnapshot, PaperPortfolioSnapshotRepository,
)
from app_module.paper_portfolio_readiness_service import PaperPortfolioReadinessService
from app_module.paper_portfolio_weekly_evidence_service import PaperPortfolioWeeklyEvidenceService
from data_module.portfolio_ledger_repository import PortfolioLedgerRepository, PortfolioLedgerEvent


def _route(root: Path, domain: Domain, mode: Mode = Mode.PERSONAL, account: str = "account-A"):
    paths = PersonalDataPaths(root / "market", root / "legacy", root / "personal")
    return select_personal_store_route(
        domain=domain, mode=mode, identity=StoreIdentity(account), personal_paths=paths,
        portfolio_ledger_path=(paths.personal_root if mode is Mode.PERSONAL else paths.legacy_output_root)
        / "ledgers" / "account-A.sqlite",
    )


def _trade(account="account-A"):
    return {"portfolio_id": account, "stock_code": "2330", "source_type": "manual",
            "price": Decimal("123.45678901234567890"), "quantity": 100,
            "source_snapshot_hash": "sha256:" + "a" * 64}


def _snapshot(account="account-A"):
    return PaperPortfolioSnapshot("synthetic-snapshot", account, "2026-09-15", "synthetic-source",
                                  Decimal("100.0000"), Decimal("100.0000"), ())


def _event(account="account-A", namespace="synthetic"):
    return PortfolioLedgerEvent(event_id="synthetic-event", portfolio_id=account,
                                source_namespace=namespace, occurred_at="2026-09-15",
                                stock_code="2330", side="buy", quantity=1, price=Decimal("1.23"),
                                created_at="2026-09-15T12:00:00")


def _hashes(root: Path):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("configured", [{"personal_store_root": "selected"},
                                        {"personal_store_mode": "personal"},
                                        {"personal_store_root": "selected", "personal_store_mode": "personal"}])
def test_explicit_config_without_route_rejects_before_legacy_side_effects(tmp_path, configured, monkeypatch):
    config = SimpleNamespace(output_root=tmp_path / "legacy", **configured)
    monkeypatch.setenv("PAPER_TRADE_LEDGER_PATH", str(tmp_path / "legacy" / "cost.sqlite"))
    with pytest.raises(PersonalStoreRouteError, match="personal_store_selector_required"):
        PortfolioService(config, market_session_cadence=object())
    with pytest.raises(PersonalStoreRouteError, match="personal_store_selector_required"):
        UserDeclaredHoldingResearchService(UserDeclaredHoldingResearchStore.under_output_root(config.output_root), config=config)
    for consumer in (PaperPortfolioReadinessService, PaperPortfolioWeeklyEvidenceService):
        with pytest.raises(PersonalStoreRouteError, match="personal_store_selector_required"):
            consumer(output_root=config.output_root, config=config)
    assert not (tmp_path / "legacy").exists()


def test_empty_personal_never_falls_back_to_legacy_or_environment(tmp_path, monkeypatch):
    legacy = PortfolioJsonlStore(tmp_path / "legacy")
    legacy.append_trade(_trade())
    source_hashes = _hashes(tmp_path / "legacy")
    trade_route = _route(tmp_path, Domain.TRADES)
    service = PortfolioService(SimpleNamespace(output_root=tmp_path / "legacy"), route=trade_route,
                               market_session_cadence=object())
    assert service.list_trades("account-A") == []
    assert not trade_route.read_source.parent.exists()
    assert UserDeclaredHoldingResearchStore.from_route(_route(tmp_path, Domain.DECLARED_HOLDINGS)).read_history() == ()
    paper = _route(tmp_path, Domain.PAPER)
    monkeypatch.setenv("PAPER_TRADE_LEDGER_PATH", str(tmp_path / "legacy" / "cost.sqlite"))
    monkeypatch.setenv("PAPER_EQUAL_WEIGHT_BENCHMARK_PATH", str(tmp_path / "legacy" / "benchmark.sqlite"))
    paths = PersonalPaperStorePaths.from_route(paper, portfolio_id="account-A")
    ready = PaperPortfolioReadinessService(output_root=tmp_path / "legacy", route=paper, portfolio_id="account-A")
    weekly = PaperPortfolioWeeklyEvidenceService(output_root=tmp_path / "legacy", route=paper, portfolio_id="account-A")
    assert ready.state_db_path == weekly.state_db_path == paths.state_db
    assert ready.cost_ledger_db_path == weekly.cost_ledger_db_path == paths.cost_ledger_db
    assert ready.benchmark_db_path == weekly.benchmark_db_path == paths.benchmark_db
    assert ready.status_path == paths.status
    assert ready.inspect().status == "not_configured"
    assert weekly.build(period_start="2026-09-14", period_end="2026-09-15", expected_trading_days=2).status != "ready"
    assert not (tmp_path / "personal").exists()
    assert source_hashes == _hashes(tmp_path / "legacy")


def test_trade_identity_and_domain_reject_before_write(tmp_path):
    route = _route(tmp_path, Domain.TRADES)
    store = PortfolioJsonlStore(tmp_path / "legacy", route=route)
    with pytest.raises(PersonalStoreRouteError, match="identity_mismatch"):
        store.append_trade(_trade("other-account"))
    with pytest.raises(PersonalStoreRouteError, match="domain_required"):
        PortfolioJsonlStore(tmp_path / "legacy", route=_route(tmp_path, Domain.PAPER))
    with pytest.raises(PersonalStoreRouteError, match="journal_forbidden"):
        store.append_journal_entry({"body": "不可由交易 route 寫 notes"})
    assert not (tmp_path / "personal").exists()
    route.read_source.parent.mkdir(parents=True)
    route.read_source.write_text(json.dumps(_trade("other-account"), default=str), encoding="utf-8")
    with pytest.raises(PersonalStoreRouteError, match="identity_mismatch"):
        store.load_trades()


def test_legacy_readonly_jsonl_does_not_create_lock_or_allow_any_writer(tmp_path):
    route = _route(tmp_path, Domain.TRADES, Mode.LEGACY_READ_ONLY)
    route.read_source.parent.mkdir(parents=True)
    route.read_source.write_text(json.dumps(_trade(), default=str) + "\n", encoding="utf-8")
    pins = _hashes(tmp_path)
    store = PortfolioJsonlStore(tmp_path / "unused", route=route)
    assert store.load_trades()[0]["portfolio_id"] == "account-A"
    for write in (lambda: store.append_trade(_trade()), lambda: store.overwrite_trades([])):
        with pytest.raises(PermissionError):
            write()
    assert _hashes(tmp_path) == pins


def test_declared_identity_readonly_and_no_cross_account(tmp_path):
    route = _route(tmp_path, Domain.DECLARED_HOLDINGS)
    service = UserDeclaredHoldingResearchService(
        UserDeclaredHoldingResearchStore.from_route(route),
        now_provider=lambda: datetime(2026, 9, 15, 12, tzinfo=timezone.utc), id_provider=lambda: "fixture-id",
    )
    with pytest.raises(PersonalStoreRouteError, match="identity_mismatch"):
        service.create_holding(UserDeclaredHoldingDraft("2330", 100, Decimal("12.30"), "2026-09-15"))
    record = service.create_holding(UserDeclaredHoldingDraft("2330", 100, Decimal("12.30"), "2026-09-15", portfolio_id="account-A"))
    assert record.research_only and record.source_status == "user_declared"
    # 以 legacy 模式讀取同一隔離 fixture，不轉換 identity。
    from dataclasses import replace
    readonly = replace(route, mode=Mode.LEGACY_READ_ONLY, write_target=None)
    store = UserDeclaredHoldingResearchStore.from_route(readonly)
    pins = _hashes(tmp_path)
    assert store.read_head(record.holding_id)["portfolio_id"] == "account-A"
    with pytest.raises(PermissionError):
        store.append_revision(service.store.read_history()[0])
    readonly_service = UserDeclaredHoldingResearchService(store)
    with pytest.raises(PermissionError):
        readonly_service.create_holding(UserDeclaredHoldingDraft("2330", 100, Decimal("12.30"), "2026-09-15", portfolio_id="account-A"))
    with pytest.raises(PersonalStoreRouteError, match="identity_mismatch"):
        store.read_heads(portfolio_id="other-account")
    assert _hashes(tmp_path) == pins


def test_paper_exact_paths_identity_and_readonly_snapshot(tmp_path):
    route = _route(tmp_path, Domain.PAPER)
    paths = PersonalPaperStorePaths.from_route(route, portfolio_id="account-A")
    with pytest.raises(PersonalStoreRouteError, match="override_mismatch"):
        PaperPortfolioReadinessService(output_root=tmp_path, route=route, portfolio_id="account-A", status_path=tmp_path / "legacy.json")
    with pytest.raises(PersonalStoreRouteError, match="identity_mismatch"):
        PersonalPaperStorePaths.from_route(route, portfolio_id="paper-main")
    repo = PaperPortfolioSnapshotRepository(paths.state_db, route=route, portfolio_id="account-A")
    with pytest.raises(ValueError, match="identity mismatch"):
        repo.append(_snapshot("different-account"))
    repo.append(_snapshot())
    from dataclasses import replace
    readonly = replace(route, mode=Mode.LEGACY_READ_ONLY, write_target=None)
    reader = PaperPortfolioSnapshotRepository(paths.state_db, route=readonly, portfolio_id="account-A")
    pins = _hashes(tmp_path)
    assert reader.get("synthetic-snapshot") == _snapshot()
    with pytest.raises(PermissionError):
        reader.append(_snapshot())
    assert _hashes(tmp_path) == pins


def test_ledger_exact_account_namespace_and_readonly(tmp_path):
    route = _route(tmp_path, Domain.PORTFOLIO_LEDGER)
    repository = PortfolioLedgerRepository(route.read_source, portfolio_id="account-A", source_namespace="synthetic")
    for event in (_event("other"), _event(namespace="paper")):
        with pytest.raises(ValueError, match="mismatch"):
            repository.append(event)
    repository.append(_event())
    reader = PortfolioLedgerRepository(route.read_source, read_only=True, portfolio_id="account-A", source_namespace="synthetic")
    pins = _hashes(tmp_path)
    assert reader.list_events() == (_event(),)
    with pytest.raises(ValueError, match="mismatch"):
        reader.list_events(portfolio_id="other")
    with pytest.raises(PermissionError):
        reader.append(_event())
    assert _hashes(tmp_path) == pins


def test_service_requires_explicit_ledger_route_and_matching_identity(tmp_path):
    trades = _route(tmp_path, Domain.TRADES)
    ledger = _route(tmp_path, Domain.PORTFOLIO_LEDGER)
    config = SimpleNamespace(output_root=tmp_path / "legacy")
    with pytest.raises(PersonalStoreRouteError, match="explicit_trades_route_required"):
        PortfolioService(config, ledger_route=ledger, ledger_source_namespace="synthetic", market_session_cadence=object())
    assert not (tmp_path / "legacy").exists()
    service = PortfolioService(config, route=trades, ledger_route=ledger,
                               ledger_source_namespace="synthetic", market_session_cadence=object())
    service.ledger_repository.append(_event())
    assert service.list_ledger_events(portfolio_id="account-A", source_namespace="synthetic")[0].event_id == "synthetic-event"
    with pytest.raises(ValueError, match="mismatch"):
        service.list_ledger_events(portfolio_id="account-A", source_namespace="paper")
    with pytest.raises(PersonalStoreRouteError, match="identity_mismatch"):
        PortfolioService(config, route=trades, ledger_route=_route(tmp_path, Domain.PORTFOLIO_LEDGER, account="other"),
                         ledger_source_namespace="synthetic", market_session_cadence=object())


def test_fresh_process_exact_readback_and_create_only_fixture_restore(tmp_path):
    trade_route = _route(tmp_path, Domain.TRADES)
    PortfolioJsonlStore(tmp_path / "legacy", route=trade_route).append_trade(_trade())
    declared = UserDeclaredHoldingResearchService(
        UserDeclaredHoldingResearchStore.from_route(_route(tmp_path, Domain.DECLARED_HOLDINGS)),
        now_provider=lambda: datetime(2026, 9, 15, 12, tzinfo=timezone.utc), id_provider=lambda: "fixture-id")
    record = declared.create_holding(UserDeclaredHoldingDraft("2330", 100, Decimal("12.3000"), "2026-09-15", portfolio_id="account-A"))
    paper = _route(tmp_path, Domain.PAPER)
    paths = PersonalPaperStorePaths.from_route(paper, portfolio_id="account-A")
    PaperPortfolioSnapshotRepository(paths.state_db, route=paper, portfolio_id="account-A").append(_snapshot())
    ledger = _route(tmp_path, Domain.PORTFOLIO_LEDGER)
    PortfolioLedgerRepository(ledger.read_source, portfolio_id="account-A", source_namespace="synthetic").append(_event())
    pins = _hashes(tmp_path / "personal")
    child = '''
import json, sys
from pathlib import Path
from app_module.portfolio_store import PortfolioJsonlStore
from app_module.user_declared_holding_research import UserDeclaredHoldingResearchStore
from app_module.paper_portfolio_snapshot_repository import PaperPortfolioSnapshotRepository
from data_module.portfolio_ledger_repository import PortfolioLedgerRepository
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_store_routes import PersonalStoreDomain as D, PersonalStoreMode as M, StoreIdentity, select_personal_store_route
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
root=Path(sys.argv[1]); account="account-A"
def route(domain):
    return select_personal_store_route(domain=domain,mode=M.PERSONAL,identity=StoreIdentity(account),
        personal_paths=PersonalDataPaths(root.parent/"market",root.parent/"legacy",root),
        portfolio_ledger_path=root/"ledgers"/"account-A.sqlite")
trade=PortfolioJsonlStore(root.parent/"legacy",route=route(D.TRADES)).load_trades()[0]
declared=UserDeclaredHoldingResearchStore.from_route(route(D.DECLARED_HOLDINGS)).read_head(sys.argv[2])
paper_route=route(D.PAPER); paths=PersonalPaperStorePaths.from_route(paper_route,portfolio_id=account)
paper=PaperPortfolioSnapshotRepository(paths.state_db,route=paper_route,portfolio_id=account).get("synthetic-snapshot")
ledger=PortfolioLedgerRepository(root/"ledgers"/"account-A.sqlite",read_only=True,portfolio_id=account,source_namespace="synthetic").get("synthetic-event")
print(json.dumps([trade["price"],declared["portfolio_id"],str(paper.cash),ledger.to_dict()],sort_keys=True))
'''
    def reopen(root):
        run = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", child, str(root), record.holding_id],
                             text=True, capture_output=True, check=True)
        result = json.loads(run.stdout)
        assert result[:3] == ["123.45678901234567890", "account-A", "100.0000"]
        assert result[3]["portfolio_id"] == "account-A" and result[3]["source_namespace"] == "synthetic"
        return result
    original = reopen(tmp_path / "personal")
    assert _hashes(tmp_path / "personal") == pins

    restore = tmp_path / "restored-fixture"
    for relative in pins:
        target = restore / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write((tmp_path / "personal" / relative).read_bytes())
    assert _hashes(restore) == pins
    assert reopen(restore) == original
    assert _hashes(tmp_path / "personal") == pins


def test_personal_paper_state_benchmark_cost_exact_readback_in_new_process(tmp_path):
    from dataclasses import replace
    from app_module.paper_equal_weight_benchmark_ledger import EqualWeightBenchmarkLedger, EqualWeightBenchmarkService
    from app_module.paper_portfolio_daily_runner import PaperPriceObservation
    from app_module.paper_trade_ledger import PaperTradeFill, PaperTradeLedgerRepository
    route = _route(tmp_path, Domain.PAPER)
    paths = PersonalPaperStorePaths.from_route(route, portfolio_id="account-A")
    snapshots = PaperPortfolioSnapshotRepository(paths.state_db, route=route, portfolio_id="account-A")
    snapshots.append(replace(_snapshot(), decision_date="2026-09-14", snapshot_id="first"))
    snapshots.append(_snapshot())
    service = EqualWeightBenchmarkService()
    baseline = service.create_baseline(benchmark_id="synthetic-equal", decision_date="2026-09-14",
                                       capital=Decimal("100.00"), prices={"2330": Decimal("10.00")})
    benchmark = EqualWeightBenchmarkLedger(paths.benchmark_db)
    benchmark.append(baseline)
    benchmark.append(service.mark(prior=baseline, decision_date="2026-09-15",
                                 prices=(PaperPriceObservation("2330", "2026-09-15", "2026-09-15", Decimal("10.00")),)))
    PaperTradeLedgerRepository(paths.cost_ledger_db).append(PaperTradeFill(
        fill_id="synthetic-fill", order_id="synthetic-order", portfolio_id="account-A",
        event_date="2026-09-14", stock_code="2330", side="buy", requested_quantity=1,
        filled_quantity=1, reference_price=Decimal("10.00"), fill_price=Decimal("10.00"),
        commission=Decimal("0.00"), tax=Decimal("0.00"), slippage_cost=Decimal("0.00"),
        turnover_bp=100, execution_gap_bp=0, status="filled", source_event_id="synthetic-source"))
    pins = _hashes(tmp_path)
    child = '''
import json, sys
from pathlib import Path
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_store_routes import PersonalStoreDomain as D, PersonalStoreMode as M, StoreIdentity, select_personal_store_route
from app_module.paper_portfolio_weekly_evidence_service import PaperPortfolioWeeklyEvidenceService
root=Path(sys.argv[1])
route=select_personal_store_route(domain=D.PAPER,mode=M.PERSONAL,identity=StoreIdentity("account-A"),
    personal_paths=PersonalDataPaths(root/"market",root/"legacy",root/"personal"))
report=PaperPortfolioWeeklyEvidenceService(output_root=root/"legacy",route=route,
    portfolio_id="account-A",benchmark_id="synthetic-equal").build(
    period_start="2026-09-14",period_end="2026-09-15",expected_trading_days=2)
print(json.dumps(report.to_dict()))
'''
    result = subprocess.run([sys.executable, "-B", "-c", child, str(tmp_path)],
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["snapshot_count"] == report["benchmark_observation_count"] == 2
    assert report["cost_record_count"] == 1 and report["portfolio_id"] == "account-A"
    assert Path(report["state_db_path"]) == paths.state_db
    assert Path(report["benchmark_db_path"]) == paths.benchmark_db
    assert Path(report["cost_ledger_db_path"]) == paths.cost_ledger_db
    assert report["research_only"] and not report["writes_allowed"]
    assert _hashes(tmp_path) == pins
