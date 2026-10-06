"""中央 caller 的同帳路由與缺件邊界，全部合成隔離資料。"""
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import pytest

from app_module.personal_store_routes import PersonalStoreMode, PersonalStoreRouteError
from ui_qt.main import MainWindow


@pytest.mark.parametrize("mode", ["personal", "legacy_read_only"])
def test_central_routes_and_paths_injected_without_reader_io(tmp_path, monkeypatch, mode):
    market, legacy, private = (tmp_path / part for part in ("market", "legacy", "private"))
    legacy.mkdir()
    marker = legacy / "source-sentinel"
    marker.write_bytes(b"legacy-source")
    config = SimpleNamespace(data_root=market, output_root=legacy, db_file=market / "market.sqlite",
                             personal_store_root=private, personal_store_mode=mode)
    owner = SimpleNamespace(config=config)
    monkeypatch.setenv("PAPER_TRADE_LEDGER_PATH", str(legacy / "wrong.sqlite"))
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("composition must not connect"))
    MainWindow._configure_personal_portfolio_services(owner)
    selection = owner.personal_store_selection
    expected = private if mode == "personal" else legacy
    assert selection.mode is PersonalStoreMode(mode)
    assert owner.portfolio_service.store.trades_file == expected / "portfolio" / "trades.jsonl"
    assert owner.portfolio_service.store.route.identity.key == "default"
    assert owner.portfolio_service.store._io_custody.paths is selection.paths
    assert owner.portfolio_service.ledger_repository is None
    kwargs = owner._personal_portfolio_view_kwargs
    assert kwargs["user_declared_portfolio_id"] == "default"
    declared = kwargs["user_declared_store"]
    assert declared.path == expected / "portfolio" / "user_declared_holdings.jsonl"
    readiness, weekly = kwargs["paper_readiness_service"], kwargs["paper_weekly_evidence_service"]
    assert readiness.portfolio_id == weekly.portfolio_id == "paper-main"
    assert readiness.benchmark_id == weekly.benchmark_id == "paper-main-equal"
    assert readiness.custody.paths is weekly.custody.paths is selection.paths
    for field in ("state_db_path", "benchmark_db_path", "cost_ledger_db_path"):
        assert getattr(readiness, field) == getattr(weekly, field)
        assert getattr(readiness, field).is_relative_to(expected)
    assert not private.exists()
    assert sorted(p.relative_to(legacy).as_posix() for p in legacy.rglob("*")) == ["source-sentinel"]
    assert marker.read_bytes() == b"legacy-source"


@pytest.mark.parametrize("fields", [{"personal_store_root": ""}, {"personal_store_mode": ""}])
def test_central_incomplete_selection_fails_before_legacy_constructor(tmp_path, fields):
    config = SimpleNamespace(data_root=tmp_path / "market", output_root=tmp_path / "legacy",
                             db_file=tmp_path / "market.sqlite", **fields)
    with pytest.raises(PersonalStoreRouteError):
        MainWindow._configure_personal_portfolio_services(SimpleNamespace(config=config))
    assert not config.output_root.exists()


@pytest.mark.parametrize("aware", [True, False])
def test_new_manual_trade_observation_clock_is_aware_before_append(tmp_path, monkeypatch, aware):
    from datetime import datetime, timezone
    from app_module.portfolio_service import PortfolioService
    from portfolio_module import PortfolioValidationError
    clock = datetime(2026, 10, 6, 10, tzinfo=timezone.utc if aware else None)
    service = PortfolioService(SimpleNamespace(output_root=tmp_path), market_session_cadence=object(),
                               now_provider=lambda: clock)
    if not aware:
        monkeypatch.setattr(service.store, "append_trade", lambda _: pytest.fail("naive clock must not append"))
        with pytest.raises(PortfolioValidationError, match="timezone"):
            service.record_trade("2330", "synthetic", "buy", 1, 100, "2026-10-06")
        assert not service.store.trades_file.exists()
    else:
        trade = service.record_trade("2330", "synthetic", "buy", 1, 100, "2026-10-06")
        assert datetime.fromisoformat(trade.created_at).utcoffset() is not None
        rows = service.store.load_trades()
        assert rows[0]["created_at"] == clock.isoformat()
        assert rows[0]["source_id"] == ""
        assert rows[0]["source_summary"] == {}
