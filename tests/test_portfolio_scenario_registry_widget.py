"""以真 scenario／registry repository 檢查明示清單、選取與取消生命週期。"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_store_routes import PersonalStoreMode
from app_module.portfolio_research_registry import (
    PortfolioScenarioRegistryService,
    ScenarioRegistryEntry,
    ScenarioRegistrySelection,
)
from app_module.portfolio_research_scenario_repository import (
    PortfolioResearchScenarioRepository,
    SavedPortfolioResearchScenario,
)
from app_module.portfolio_research_scenario_workspace import PortfolioResearchScenarioWorkspace
from app_module.research_run_repository import ResearchRunRepository
from test_portfolio_research_scenario_repository import _comparison, _route
from ui_qt.widgets.portfolio_scenario_registry_widget import PortfolioScenarioRegistryWidget


_SAVED_AT = datetime(2026, 10, 9, 2, tzinfo=timezone.utc)


def _app() -> QApplication:
    instance = QApplication.instance()
    return instance if instance is not None else QApplication([])


def _wait_until(
    app: QApplication,
    condition: Callable[[], bool],
    timeout_seconds: float = 8.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.005)
    app.processEvents()
    assert condition(), "Qt worker operation did not settle before the bounded test deadline"


def _seed_workspace(
    tmp_path: Path,
) -> tuple[
    PortfolioResearchScenarioRepository,
    PortfolioResearchScenarioWorkspace,
    SavedPortfolioResearchScenario,
    ScenarioRegistryEntry,
]:
    paths = PersonalDataPaths(
        market_root=tmp_path / "market",
        legacy_output_root=tmp_path / "legacy",
        personal_root=tmp_path / "market" / "personal",
    )
    scenario_repository = PortfolioResearchScenarioRepository(
        route=_route(paths, PersonalStoreMode.PERSONAL),
        personal_paths=paths,
    )
    saved = scenario_repository.append(_comparison(), saved_at=_SAVED_AT)
    registry_repository = ResearchRunRepository(
        SimpleNamespace(research_run_db_file=tmp_path / "registry.sqlite")
    )
    registry = PortfolioScenarioRegistryService(registry_repository, scenario_repository)
    workspace = PortfolioResearchScenarioWorkspace(scenario_repository, registry=registry)
    registered = workspace.register_saved(
        saved.artifact_id,
        account_kind="paper",
        portfolio_id="account-a",
    )
    return scenario_repository, workspace, saved, registered


def _start_list(
    app: QApplication,
    widget: PortfolioScenarioRegistryWidget,
    portfolio_id: str = "account-a",
) -> None:
    widget.account_kind_combo.setCurrentIndex(widget.account_kind_combo.findData("paper"))
    widget.portfolio_id_edit.setText(portfolio_id)
    widget.load_button.click()
    _wait_until(app, lambda: not widget.has_running_worker())


def test_registered_entries_load_in_worker_and_open_emits_exact_selection(tmp_path: Path) -> None:
    app = _app()
    _, workspace, saved, registered = _seed_workspace(tmp_path)
    widget = PortfolioScenarioRegistryWidget(workspace)
    opened: list[object] = []
    widget.openRequested.connect(opened.append)

    assert widget.has_running_worker() is False
    assert widget.entry_combo.count() == 1
    assert widget.entry_combo.currentData() is None
    assert opened == []

    _start_list(app, widget)

    assert widget.entry_combo.count() == 2
    assert isinstance(widget.entry_combo.itemData(1), ScenarioRegistryEntry)
    assert widget.entry_combo.itemData(1) == registered
    assert widget.entry_combo.currentData() is None
    assert not widget.open_button.isEnabled()

    widget.entry_combo.setCurrentIndex(1)
    assert widget.open_button.isEnabled()
    assert opened == []
    widget.open_button.click()

    selection = opened[0]
    assert isinstance(selection, ScenarioRegistrySelection)
    assert opened == [registered.selection()]
    assert workspace.open_registered(selection) == saved
    widget.close()


def test_account_change_cancels_and_discards_late_registry_list(tmp_path: Path) -> None:
    app = _app()
    _, base_workspace, _saved, _registered = _seed_workspace(tmp_path)

    class DelayedWorkspace(PortfolioResearchScenarioWorkspace):
        def __init__(self, base: PortfolioResearchScenarioWorkspace) -> None:
            super().__init__(base.repository, registry=base.registry)
            self.started = threading.Event()
            self.release = threading.Event()

        def list_registered(
            self,
            *,
            account_kind: str,
            portfolio_id: str,
            cancel_callback=None,
        ) -> tuple[ScenarioRegistryEntry, ...]:
            self.started.set()
            while not self.release.wait(0.01):
                if cancel_callback is not None and cancel_callback():
                    raise InterruptedError("cancelled stale registry list")
            return super().list_registered(
                account_kind=account_kind,
                portfolio_id=portfolio_id,
                cancel_callback=cancel_callback,
            )

    delayed = DelayedWorkspace(base_workspace)
    widget = PortfolioScenarioRegistryWidget(delayed)
    widget.account_kind_combo.setCurrentIndex(widget.account_kind_combo.findData("paper"))
    widget.portfolio_id_edit.setText("account-a")
    widget.load_button.click()
    assert delayed.started.wait(2.0)

    widget.portfolio_id_edit.setText("account-b")
    assert widget.entry_combo.count() == 1
    delayed.release.set()
    _wait_until(app, lambda: not widget.has_running_worker())

    assert widget._loaded_identity is None
    assert widget.entry_combo.count() == 1
    assert widget.entry_combo.currentData() is None
    assert not widget.open_button.isEnabled()
    widget.close()


def test_registry_read_error_is_bounded_and_not_applied(tmp_path: Path) -> None:
    app = _app()
    _, base_workspace, _saved, _registered = _seed_workspace(tmp_path)

    class BrokenWorkspace(PortfolioResearchScenarioWorkspace):
        def __init__(self, base: PortfolioResearchScenarioWorkspace) -> None:
            super().__init__(base.repository, registry=base.registry)

        def list_registered(
            self,
            *,
            account_kind: str,
            portfolio_id: str,
            cancel_callback=None,
        ) -> tuple[ScenarioRegistryEntry, ...]:
            raise ValueError("E" * 1200)

    widget = PortfolioScenarioRegistryWidget(BrokenWorkspace(base_workspace))
    _start_list(app, widget)

    assert widget.entry_combo.count() == 1
    assert "載入失敗，未套用登錄清單。" in widget.status_label.text()
    detail = widget.status_label.text().split("原因：", 1)[1]
    assert len(detail) == 500
    assert widget._loaded_identity is None
    widget.close()


def test_shutdown_cooperatively_cancels_worker_and_ignores_late_result(tmp_path: Path) -> None:
    app = _app()
    _, base_workspace, _saved, _registered = _seed_workspace(tmp_path)

    class DelayedWorkspace(PortfolioResearchScenarioWorkspace):
        def __init__(self, base: PortfolioResearchScenarioWorkspace) -> None:
            super().__init__(base.repository, registry=base.registry)
            self.started = threading.Event()
            self.release = threading.Event()

        def list_registered(
            self,
            *,
            account_kind: str,
            portfolio_id: str,
            cancel_callback=None,
        ) -> tuple[ScenarioRegistryEntry, ...]:
            self.started.set()
            while not self.release.wait(0.01):
                if cancel_callback is not None and cancel_callback():
                    raise InterruptedError("cancelled on shutdown")
            return super().list_registered(
                account_kind=account_kind,
                portfolio_id=portfolio_id,
                cancel_callback=cancel_callback,
            )

    delayed = DelayedWorkspace(base_workspace)
    widget = PortfolioScenarioRegistryWidget(delayed)
    widget.account_kind_combo.setCurrentIndex(widget.account_kind_combo.findData("paper"))
    widget.portfolio_id_edit.setText("account-a")
    widget.load_button.click()
    assert delayed.started.wait(2.0)

    widget.begin_shutdown()
    assert widget.has_running_worker()
    delayed.release.set()
    _wait_until(app, lambda: not widget.has_running_worker())

    assert widget.entry_combo.count() == 1
    assert widget.entry_combo.currentData() is None
    assert widget._loaded_identity is None
    widget.close()
