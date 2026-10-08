"""外部保存研究根的真設定與瀏覽接線；不放寬 producer 寫入範圍。"""
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
import json

import pytest
from PySide6.QtWidgets import QApplication

from app_module.application_bootstrap import apply_application_settings, resolve_application_settings
from data_module.config import TWStockConfig
from ui_qt.views.daily_market_research_view import DailyMarketResearchView


@pytest.mark.parametrize("via_json", [False, True])
def test_portable_read_root_reaches_actual_browser_without_creating_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, via_json: bool,
) -> None:
    root = tmp_path / "shared_saved_research"
    values = {"DATA_ROOT": str(tmp_path / "data"), "OUTPUT_ROOT": str(tmp_path / "private_output"),
              "TECHNICAL_UNIVERSE_READ_ROOT": str(root)}
    environment = {"LOCALAPPDATA": str(tmp_path / "local")}
    if via_json:
        portable = tmp_path / "portable.json"
        portable.write_text(json.dumps(values), encoding="utf-8")
        environment["BALDR_CONFIG"] = str(portable)
    else:
        environment.update(values)
    settings = resolve_application_settings(environ=environment, resource_root=tmp_path / "bundle")
    for key, value in settings.environment.items():
        monkeypatch.setenv(key, value)
    config = TWStockConfig()
    app = QApplication.instance() or QApplication([])
    view = DailyMarketResearchView(SimpleNamespace(config=config))
    try:
        browser = view.technical_universe_view
        assert browser is not None
        assert browser.store_output_root == root.resolve()
        assert browser.production_request_factory is None
        assert not browser.produce_button.isEnabled()
        assert not browser.resume_button.isEnabled()
        assert "外部保存來源" in browser.disclaimer.text()
        assert not root.exists()
        assert config.output_root == tmp_path / "private_output"
    finally:
        view.begin_shutdown()
        view.close()
        view.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("value", ["", "  ", "relative/research"])
def test_explicit_invalid_read_root_is_rejected_without_fallback(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError, match="TECHNICAL_UNIVERSE_READ_ROOT"):
        resolve_application_settings(environ={"LOCALAPPDATA": str(tmp_path / "local"),
                                             "TECHNICAL_UNIVERSE_READ_ROOT": value})
    assert not (tmp_path / "local").exists()


def test_frozen_read_root_inside_bundle_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    with pytest.raises(ValueError, match="TECHNICAL_UNIVERSE_READ_ROOT"):
        resolve_application_settings(environ={"LOCALAPPDATA": str(tmp_path / "local"),
            "TECHNICAL_UNIVERSE_READ_ROOT": str(bundle / "research")}, resource_root=bundle, frozen=True)
    assert not bundle.exists()


@pytest.mark.parametrize("frozen", [False, True])
def test_apply_rechecks_read_root_before_creating_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, frozen: bool,
) -> None:
    bundle = tmp_path / "bundle"
    settings = resolve_application_settings(
        environ={"LOCALAPPDATA": str(tmp_path / "local")}, resource_root=bundle,
    )
    environment = dict(settings.environment)
    environment["TECHNICAL_UNIVERSE_READ_ROOT"] = str(bundle / "research") if frozen else "relative/research"
    monkeypatch.setattr("sys.frozen", frozen, raising=False)
    with pytest.raises(ValueError, match="TECHNICAL_UNIVERSE_READ_ROOT"):
        apply_application_settings(replace(settings, environment=environment))
    assert not settings.runtime_state_root.exists()
    assert not bundle.exists()


@pytest.mark.parametrize("explicit_default", [False, True])
def test_default_store_preserves_existing_production_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit_default: bool,
) -> None:
    monkeypatch.delenv("TECHNICAL_UNIVERSE_READ_ROOT", raising=False)
    output = tmp_path / "private_output"
    default_root = output / "research_snapshots" / "technical_universe"
    config = TWStockConfig(data_root=tmp_path / "data", output_root=output,
        technical_universe_read_root=default_root if explicit_default else None)
    app = QApplication.instance() or QApplication([])
    view = DailyMarketResearchView(SimpleNamespace(config=config))
    try:
        browser = view.technical_universe_view
        assert browser is not None
        assert browser.store_output_root == default_root
        assert browser.production_request_factory is not None
        assert browser.produce_button.isEnabled()
        assert not default_root.exists()
    finally:
        view.begin_shutdown()
        view.close()
        view.deleteLater()
        app.processEvents()
