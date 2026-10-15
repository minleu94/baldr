"""Exercise explicit Registry registration and exact reopen in the scenario panel."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.portfolio_research_registry import (
    PortfolioScenarioRegistryService,
    ScenarioRegistryEntry,
)
from app_module.research_run_repository import ResearchRunRepository
from app_module.portfolio_research_scenario_workspace import PortfolioResearchScenarioWorkspace
from test_portfolio_research_scenario_widget import (
    _app,
    _open_exact,
    _seed_workspace,
    _wait_until,
)
from ui_qt.widgets.portfolio_research_scenario_widget import PortfolioResearchScenarioWidget


def _registry_workspace(tmp_path: Path):
    paths, scenario_repository, workspace, saved = _seed_workspace(tmp_path)
    registry_repository = ResearchRunRepository(
        SimpleNamespace(research_run_db_file=tmp_path / "registry.sqlite")
    )
    workspace.registry = PortfolioScenarioRegistryService(
        registry_repository,
        scenario_repository,
    )
    return paths, scenario_repository, workspace, saved


def test_explicit_registry_register_and_open_reuses_exact_saved_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app()
    _, scenario_repository, workspace, saved = _registry_workspace(tmp_path)
    assert saved is not None
    assert isinstance(workspace, PortfolioResearchScenarioWorkspace)
    widget = PortfolioResearchScenarioWidget(workspace)
    assert not widget.register_button.isEnabled()

    _open_exact(app, widget, saved.artifact_id)
    assert widget.register_button.isEnabled()

    widget.target_spinboxes["2330"].setValue(1600)
    widget.cash_weight_spin.setValue(8400)
    widget.compare_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker()
        and widget.current_comparison is not None
        and widget.current_comparison.request.explicit_weights is not None
        and widget.current_comparison.request.explicit_weights.weight_for("2330") == 1600,
    )
    assert not widget.register_button.isEnabled()

    preview = widget.current_comparison
    assert preview is not None
    widget.save_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker()
        and widget.current_artifact_id != saved.artifact_id
        and widget.current_comparison == preview,
    )
    registered_artifact_id = widget.current_artifact_id
    # Saving a new scenario artifact does not implicitly write a Registry record.
    assert workspace.list_registered(account_kind="paper", portfolio_id="account-a") == ()
    assert widget.register_button.isEnabled()

    opened: list[object] = []
    open_registered = workspace.open_registered

    def track_open(selection, *, cancel_callback=None):
        opened.append(selection)
        return open_registered(selection, cancel_callback=cancel_callback)

    monkeypatch.setattr(workspace, "open_registered", track_open)
    widget.register_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker()
        and "已登錄 Registry 研究紀錄" in widget.status_label.text(),
    )

    entries = workspace.list_registered(account_kind="paper", portfolio_id="account-a")
    assert len(entries) == 1
    entry = entries[0]
    assert type(entry) is ScenarioRegistryEntry
    assert entry.artifact_id == registered_artifact_id
    assert entry.account_kind == "paper"
    assert entry.portfolio_id == "account-a"
    assert entry.snapshot_id == preview.account.snapshot_id
    assert entry.decision_at == preview.decision_at
    assert entry.input_hash == preview.input_hash
    with pytest.raises(ValueError):
        wrong_selection = replace(entry.selection(), portfolio_id="other-account")
        workspace.open_registered(wrong_selection)
    assert opened == [wrong_selection]
    opened.clear()
    assert registered_artifact_id in widget.status_label.text()
    assert widget.current_artifact_id == registered_artifact_id
    assert scenario_repository.get_exact(
        registered_artifact_id,
        account_kind="paper",
        portfolio_id="account-a",
    ) is not None

    # Registry open sets the selection's identity without using the currently selected account.
    widget.account_kind_combo.setCurrentIndex(widget.account_kind_combo.findData("manual"))
    widget.portfolio_id_edit.setText("other-account")
    widget.open_registered(entry.selection())
    assert widget.account_kind_combo.currentData() == "paper"
    assert widget.portfolio_id_edit.text() == "account-a"
    _wait_until(
        app,
        lambda: not widget.has_running_worker()
        and widget.current_artifact_id == registered_artifact_id
        and "已由 Registry exact 重開原研究紀錄" in widget.status_label.text(),
    )
    assert opened == [entry.selection()]
    assert widget.current_comparison == preview
    assert scenario_repository.get_exact(
        registered_artifact_id,
        account_kind="paper",
        portfolio_id="account-a",
    ) is not None
    widget.close()


def test_registry_write_rejects_wrong_account_and_cannot_be_cancelled(
    tmp_path: Path,
) -> None:
    app = _app()
    _, _, workspace, saved = _registry_workspace(tmp_path)
    assert saved is not None

    with pytest.raises(ValueError):
        workspace.register_saved(
            saved.artifact_id,
            account_kind="paper",
            portfolio_id="other-account",
        )
    assert workspace.list_registered(account_kind="paper", portfolio_id="account-a") == ()

    class DelayedRegistryWorkspace(PortfolioResearchScenarioWorkspace):
        def __init__(self, base: PortfolioResearchScenarioWorkspace) -> None:
            super().__init__(base.repository, registry=base.registry)
            self.started = threading.Event()
            self.release = threading.Event()
            self.received_cancel_callback = object()

        def register_saved(
            self,
            artifact_id: str,
            *,
            account_kind: str,
            portfolio_id: str,
            cancel_callback=None,
        ) -> ScenarioRegistryEntry:
            self.received_cancel_callback = cancel_callback
            self.started.set()
            if not self.release.wait(2.0):
                raise TimeoutError("test registration gate was not released")
            return super().register_saved(
                artifact_id,
                account_kind=account_kind,
                portfolio_id=portfolio_id,
            )

    delayed = DelayedRegistryWorkspace(workspace)
    widget = PortfolioResearchScenarioWidget(delayed)
    _open_exact(app, widget, saved.artifact_id)
    widget.register_button.click()
    assert delayed.started.wait(2.0)
    assert not widget.cancel_button.isEnabled()
    assert not widget.account_kind_combo.isEnabled()
    assert not widget.portfolio_id_edit.isEnabled()

    widget.cancel_current_operation()
    assert widget.has_running_worker()
    delayed.release.set()
    _wait_until(
        app,
        lambda: not widget.has_running_worker()
        and "已登錄 Registry 研究紀錄" in widget.status_label.text(),
    )
    assert delayed.received_cancel_callback is None
    assert len(delayed.list_registered(account_kind="paper", portfolio_id="account-a")) == 1
    widget.close()
