from __future__ import annotations

import os
import threading
from datetime import timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
import pytest

from app_module.portfolio_research_account_reader import StrategyPaperResearchCheckpointSelection
from app_module.portfolio_research_initial_source import (
    InitialPortfolioAccountCatalogue,
    InitialPortfolioAccountIdentity,
    InitialPortfolioResearchCandidate,
    InitialPortfolioResearchCatalogue,
    InitialPortfolioResearchSelection,
)
from app_module.position_health_strategy_archive import StrategyHealthArchiveReference
from app_module.portfolio_research_scenario_repository import (
    PortfolioResearchScenarioRepository,
    SavedPortfolioResearchScenario,
)
from app_module.portfolio_research_scenario_service import PortfolioResearchScenarioComparison
from app_module.portfolio_research_scenario_workspace import PortfolioResearchScenarioWorkspace
from test_portfolio_research_scenario_repository import _comparison
from test_portfolio_research_scenario_widget import _SAVED_AT, _app, _open_exact, _seed_workspace, _wait_until
from ui_qt.widgets.portfolio_research_scenario_widget import PortfolioResearchScenarioWidget


def _initial_selection() -> InitialPortfolioResearchSelection:
    checkpoint = StrategyPaperResearchCheckpointSelection(
        strategy_id="momentum_aggressive_v1",
        strategy_version_id="1.0.0",
        account_namespace="account-a",
        operation_id="operation-a",
        snapshot_id="snapshot-a",
    )
    health = StrategyHealthArchiveReference(
        receipt_id="phsr-v2-" + "a" * 64,
        receipt_sha256="sha256:" + "b" * 64,
    )
    return InitialPortfolioResearchSelection(checkpoint=checkpoint, health_reference=health)


class _InitialWorkspace:
    def __init__(
        self,
        base: PortfolioResearchScenarioWorkspace,
        selection: InitialPortfolioResearchSelection,
        *,
        delay_catalogue: bool = False,
        delay_compare: bool = False,
        delay_save: bool = False,
    ) -> None:
        self.base = base
        self.repository: PortfolioResearchScenarioRepository = base.repository
        self.selection = selection
        self.catalogue = InitialPortfolioResearchCatalogue(
            (InitialPortfolioResearchCandidate(selection=selection, label="策略與 Health 同來源候選"),),
            truncated=False,
        )
        self.started = threading.Event()
        self.release = threading.Event()
        self.delay_catalogue = delay_catalogue
        self.delay_compare = delay_compare
        self.delay_save = delay_save
        self.compare_started = threading.Event()
        self.compare_release = threading.Event()
        self.save_started = threading.Event()
        self.save_release = threading.Event()
        self.list_calls: list[tuple[str, str, str]] = []
        self.account_list_calls = 0
        self.compare_calls: list[tuple[InitialPortfolioResearchSelection, tuple[str, ...], object]] = []

    @property
    def can_create_initial(self) -> bool:
        return True

    @property
    def can_save(self) -> bool:
        return self.base.can_save

    def __getattr__(self, name: str):
        return getattr(self.base, name)

    def list_initial_accounts(self, *, cancel_callback=None) -> InitialPortfolioAccountCatalogue:
        self.account_list_calls += 1
        if cancel_callback is not None and cancel_callback():
            raise InterruptedError("策略帳清單已取消")
        return InitialPortfolioAccountCatalogue((
            InitialPortfolioAccountIdentity("other", "1.0.0", "account-b"),
            InitialPortfolioAccountIdentity(
                self.selection.checkpoint.strategy_id,
                self.selection.checkpoint.strategy_version_id,
                self.selection.checkpoint.account_namespace,
            ),
        ), truncated=False, unavailable_count=1)

    def list_initial_sources(
        self,
        *,
        strategy_id: str,
        strategy_version_id: str,
        account_namespace: str,
        cancel_callback=None,
    ) -> InitialPortfolioResearchCatalogue:
        self.list_calls.append((strategy_id, strategy_version_id, account_namespace))
        if self.delay_catalogue:
            self.started.set()
            while not self.release.wait(0.01):
                if cancel_callback is not None and cancel_callback():
                    raise InterruptedError("初次來源清單已取消")
        if cancel_callback is not None and cancel_callback():
            raise InterruptedError("初次來源清單已取消")
        return self.catalogue

    def compare_initial(
        self,
        selection: InitialPortfolioResearchSelection,
        *,
        candidate_symbols: tuple[str, ...],
        explicit_weights=None,
        cancel_callback=None,
    ) -> PortfolioResearchScenarioComparison:
        self.compare_calls.append((selection, candidate_symbols, explicit_weights))
        if selection != self.selection or explicit_weights is not None:
            raise ValueError("初次比較輸入身分不符")
        if self.delay_compare:
            self.compare_started.set()
            while not self.compare_release.wait(0.01):
                if cancel_callback is not None and cancel_callback():
                    raise InterruptedError("初次比較已取消")
        if cancel_callback is not None and cancel_callback():
            raise InterruptedError("初次比較已取消")
        return _comparison(
            kind="paper",
            account_id=selection.checkpoint.account_namespace,
            explicit=False,
        )

    def save_initial(
        self,
        selection: InitialPortfolioResearchSelection,
        comparison: PortfolioResearchScenarioComparison,
    ) -> SavedPortfolioResearchScenario:
        if selection != self.selection:
            raise ValueError("初次保存來源身分不符")
        if self.delay_save:
            self.save_started.set()
            if not self.save_release.wait(5.0):
                raise TimeoutError("初次保存測試閘未釋放")
        return self.repository.append(comparison, saved_at=_SAVED_AT + timedelta(minutes=1))


def _fill_initial_controls(
    app: QApplication,
    widget: PortfolioResearchScenarioWidget,
    selection: InitialPortfolioResearchSelection,
) -> None:
    checkpoint = selection.checkpoint
    widget.initial_strategy_id_edit.setText(checkpoint.strategy_id)
    widget.initial_strategy_version_edit.setText(checkpoint.strategy_version_id)
    widget.initial_namespace_edit.setText(checkpoint.account_namespace)
    widget.load_initial_sources_button.click()
    _wait_until(app, lambda: not widget.has_running_worker() and widget.initial_source_combo.count() == 2)
    widget.initial_source_combo.setCurrentIndex(1)
    widget.initial_candidate_symbols_edit.setText("2382,2330")


def test_initial_account_discovery_requires_selection_then_fills_exact_identity(tmp_path) -> None:
    app = _app()
    _, _, base, _saved = _seed_workspace(tmp_path)
    selection = _initial_selection()
    workspace = _InitialWorkspace(base, selection)
    widget = PortfolioResearchScenarioWidget(workspace)

    widget.load_initial_accounts_button.click()
    _wait_until(app, lambda: not widget.has_running_worker() and widget.initial_account_combo.count() == 3)
    assert workspace.account_list_calls == 1
    assert widget.initial_account_combo.currentData() is None
    assert widget.initial_strategy_id_edit.text() == ""
    assert widget.load_initial_sources_button.isEnabled() is False
    assert "1 筆帳戶未通過" in widget.initial_sources_status_label.text()

    widget.initial_account_combo.setCurrentIndex(2)
    assert widget._selected_initial_identity() == (
        selection.checkpoint.strategy_id,
        selection.checkpoint.strategy_version_id,
        selection.checkpoint.account_namespace,
    )
    assert widget.load_initial_sources_button.isEnabled()
    widget.load_initial_sources_button.click()
    _wait_until(app, lambda: not widget.has_running_worker() and widget.initial_source_combo.count() == 2)
    assert workspace.list_calls == [widget._selected_initial_identity()]
    widget.initial_strategy_version_edit.setText("2.0.0")
    assert widget.initial_account_combo.currentData() is None
    assert widget.initial_source_combo.count() == 1
    assert widget.initial_compare_button.isEnabled() is False
    widget.close()


def test_initial_compare_save_returns_to_exact_saved_target_and_stock_flow(tmp_path) -> None:
    app = _app()
    _, repository, base, old_saved = _seed_workspace(tmp_path)
    assert old_saved is not None
    selection = _initial_selection()
    workspace = _InitialWorkspace(base, selection)
    widget = PortfolioResearchScenarioWidget(workspace)
    widget.account_kind_combo.setCurrentIndex(widget.account_kind_combo.findData("paper"))
    widget.portfolio_id_edit.setText("account-a")
    _open_exact(app, widget, old_saved.artifact_id)

    opened_stocks: list[str] = []
    widget.stockResearchRequested.connect(opened_stocks.append)
    _fill_initial_controls(app, widget, selection)
    assert workspace.list_calls == [("momentum_aggressive_v1", "1.0.0", "account-a")]
    assert widget.initial_compare_button.isEnabled()
    widget.initial_compare_button.click()
    _wait_until(app, lambda: not widget.has_running_worker() and widget.current_comparison is not None)

    initial_preview = widget.current_comparison
    assert initial_preview is not None
    assert widget.current_artifact_id == ""
    assert workspace.compare_calls == [(selection, ("2382", "2330"), None)]
    assert widget.restore_artifact(old_saved.artifact_id, "2330") is False
    widget.scenario_table.selectRow(0)
    assert widget.stock_research_button.isEnabled() is False
    widget.stock_research_button.click()
    assert opened_stocks == []

    assert widget.initial_save_button.isEnabled()
    widget.initial_save_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker()
        and bool(widget.current_artifact_id)
        and widget.current_comparison == initial_preview,
    )
    initial_artifact_id = widget.current_artifact_id
    assert initial_artifact_id.startswith("sha256:")
    assert widget.saved_artifact_combo.currentData() == initial_artifact_id
    assert repository.get_exact(
        old_saved.artifact_id, account_kind="paper", portfolio_id="account-a"
    ) == old_saved
    assert widget.current_comparison is not None
    assert widget.current_comparison.request.explicit_weights is None

    assert widget.restore_artifact(initial_artifact_id, "2330") is True
    widget.stock_research_button.click()
    assert opened_stocks == ["2330"]
    assert set(widget.target_spinboxes) == {"2330", "2382"}
    widget.target_spinboxes["2330"].setValue(1500)
    widget.cash_weight_spin.setValue(8500)
    assert widget.compare_button.isEnabled()
    widget.compare_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker()
        and widget.current_comparison is not None
        and widget.current_comparison.request.explicit_weights is not None
        and widget.current_comparison.request.explicit_weights.weight_for("2330") == 1500,
    )
    target_preview = widget.current_comparison
    assert target_preview is not None
    widget.save_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker()
        and widget.current_artifact_id != initial_artifact_id
        and widget.current_comparison == target_preview,
    )
    target_artifact_id = widget.current_artifact_id
    assert repository.get_exact(
        initial_artifact_id, account_kind="paper", portfolio_id="account-a"
    ) is not None

    widget.load_saved_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker()
        and widget.saved_artifact_combo.findData(target_artifact_id) >= 0,
    )
    widget.saved_artifact_combo.setCurrentIndex(widget.saved_artifact_combo.findData(target_artifact_id))
    widget.open_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker() and widget.current_artifact_id == target_artifact_id,
    )
    assert widget.current_comparison == target_preview
    widget.close()


@pytest.mark.parametrize("change", ["identity", "source", "candidate"])
def test_initial_identity_source_or_candidate_change_clears_preview_and_disables_save(
    tmp_path, change: str
) -> None:
    app = _app()
    _, _, base, _saved = _seed_workspace(tmp_path)
    selection = _initial_selection()
    widget = PortfolioResearchScenarioWidget(_InitialWorkspace(base, selection))
    _fill_initial_controls(app, widget, selection)
    widget.initial_compare_button.click()
    _wait_until(app, lambda: not widget.has_running_worker() and widget.current_comparison is not None)
    assert widget.initial_save_button.isEnabled()

    if change == "identity":
        widget.initial_strategy_version_edit.setText("1.0.1")
    elif change == "source":
        widget.initial_source_combo.setCurrentIndex(0)
    else:
        widget.initial_candidate_symbols_edit.setText("2330")
    assert widget.current_comparison is None
    assert widget.current_artifact_id == ""
    assert widget.initial_save_button.isEnabled() is False
    assert widget.scenario_table.rowCount() == 0
    widget.close()


def test_late_initial_catalogue_is_not_applied_after_identity_changes(tmp_path) -> None:
    app = _app()
    _, _, base, _saved = _seed_workspace(tmp_path)
    selection = _initial_selection()
    workspace = _InitialWorkspace(base, selection, delay_catalogue=True)
    widget = PortfolioResearchScenarioWidget(workspace)
    checkpoint = selection.checkpoint
    widget.initial_strategy_id_edit.setText(checkpoint.strategy_id)
    widget.initial_strategy_version_edit.setText(checkpoint.strategy_version_id)
    widget.initial_namespace_edit.setText(checkpoint.account_namespace)
    widget.load_initial_sources_button.click()
    assert workspace.started.wait(2.0)

    widget.initial_strategy_version_edit.setText("1.0.1")
    workspace.release.set()
    _wait_until(app, lambda: not widget.has_running_worker())
    assert widget.initial_source_combo.count() == 1
    assert widget.initial_source_combo.currentData() is None
    assert widget.current_comparison is None
    assert widget.current_artifact_id == ""
    widget.close()


def test_initial_compare_late_result_is_dropped_after_candidate_change(tmp_path) -> None:
    app = _app()
    _, repository, base, saved = _seed_workspace(tmp_path)
    assert saved is not None
    selection = _initial_selection()
    workspace = _InitialWorkspace(base, selection, delay_compare=True)
    widget = PortfolioResearchScenarioWidget(workspace)
    before_ids = repository.list_artifact_ids(account_kind="paper", portfolio_id="account-a")
    _fill_initial_controls(app, widget, selection)

    widget.initial_compare_button.click()
    assert workspace.compare_started.wait(2.0)
    widget.initial_candidate_symbols_edit.setText("2330")
    workspace.compare_release.set()
    _wait_until(app, lambda: not widget.has_running_worker())
    assert widget.current_comparison is None
    assert widget.current_artifact_id == ""
    assert widget.initial_save_button.isEnabled() is False
    assert widget.scenario_table.rowCount() == 0
    assert repository.list_artifact_ids(account_kind="paper", portfolio_id="account-a") == before_ids
    widget.close()


def test_initial_save_is_not_cancellable_and_locks_source_identity(tmp_path) -> None:
    app = _app()
    _, _, base, _saved = _seed_workspace(tmp_path)
    selection = _initial_selection()
    workspace = _InitialWorkspace(base, selection, delay_save=True)
    widget = PortfolioResearchScenarioWidget(workspace)
    _fill_initial_controls(app, widget, selection)
    widget.initial_compare_button.click()
    _wait_until(app, lambda: not widget.has_running_worker() and widget.current_comparison is not None)

    widget.initial_save_button.click()
    assert workspace.save_started.wait(2.0)
    assert widget.cancel_button.isEnabled() is False
    assert widget.initial_strategy_id_edit.isEnabled() is False
    assert widget.initial_strategy_version_edit.isEnabled() is False
    assert widget.initial_namespace_edit.isEnabled() is False
    assert widget.initial_source_combo.isEnabled() is False
    assert widget.initial_candidate_symbols_edit.isEnabled() is False
    widget.cancel_current_operation()
    assert widget.has_running_worker() is True
    assert widget.current_artifact_id == ""

    workspace.save_release.set()
    _wait_until(app, lambda: not widget.has_running_worker() and bool(widget.current_artifact_id))
    assert widget.account_kind_combo.currentData() == "paper"
    assert widget.portfolio_id_edit.text() == selection.checkpoint.account_namespace
    assert widget.current_artifact_id.startswith("sha256:")
    widget.close()
