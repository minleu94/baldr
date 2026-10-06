from types import SimpleNamespace

import pytest

from app_module.personal_store_routes import PersonalStoreDomain, PersonalStoreMode, PersonalStoreRouteError, StoreIdentity
from app_module.personal_store_selection import resolve_personal_store_selection
from data_module.config import TWStockConfig


def test_config_cli_selects_private_stores_without_watchlist_activation(tmp_path, monkeypatch):
    for name in ("PERSONAL_STORE_ROOT", "PERSONAL_STORE_MODE", "PERSONAL_DATA_ROOT", "PERSONAL_WATCHLIST_SOURCE"):
        monkeypatch.delenv(name, raising=False)
    market = tmp_path / "market"
    output = tmp_path / "output"
    root = market / "personal"
    config, _ = TWStockConfig.from_args([
        "--data-root", str(market), "--output-root", str(output),
        "--personal-store-root", str(root), "--personal-store-mode", "personal",
    ])
    selected = resolve_personal_store_selection(config)
    assert selected.mode is PersonalStoreMode.PERSONAL
    assert selected.route(PersonalStoreDomain.TRADES, StoreIdentity("account-1")).read_source == root / "portfolio/trades.jsonl"
    assert config.db_file == market / "sqlite/twstock.db"
    assert config.output_root == output
    assert config.personal_data_root is None
    assert config.personal_watchlist_source is None
    assert not root.exists()


def test_legacy_readonly_selection_never_has_writer(tmp_path):
    config = SimpleNamespace(data_root=tmp_path / "market", output_root=tmp_path / "output",
                             personal_store_root=tmp_path / "market/personal", personal_store_mode="legacy_read_only")
    route = resolve_personal_store_selection(config).route(PersonalStoreDomain.TRADES, StoreIdentity("account-1"))
    assert route.read_source == config.output_root / "portfolio/trades.jsonl"
    assert route.write_target is None
    assert not config.data_root.exists()


@pytest.mark.parametrize("root,mode", [(None,"personal"),("selected",None),("selected","invented")])
def test_partial_selection_fails_before_config_creates_directories(tmp_path, root, mode):
    with pytest.raises(PersonalStoreRouteError):
        TWStockConfig(data_root=tmp_path / "market", output_root=tmp_path / "output",
                      personal_store_root=tmp_path / root if root else None, personal_store_mode=mode)
    assert not (tmp_path / "market").exists()
    assert not (tmp_path / "output").exists()
