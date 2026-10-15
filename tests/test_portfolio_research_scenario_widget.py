"""以真 repository 檢查人選研究情境面板的 exact 回訪與另存流程。"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_store_routes import PersonalStoreMode
from app_module.portfolio_research_scenario_repository import (
    PortfolioResearchScenarioRepository,
    SavedPortfolioResearchScenario,
)
from app_module.portfolio_research_scenario_workspace import PortfolioResearchScenarioWorkspace
from test_portfolio_research_scenario_repository import _comparison, _route
from ui_qt.widgets.portfolio_research_scenario_widget import PortfolioResearchScenarioWidget


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
        # 釋放 Python GIL，讓真正 TaskWorker 能完成；期限與斷言保持原值。
        time.sleep(0.005)
    app.processEvents()
    assert condition(), "Qt worker operation did not settle before the bounded test deadline"


def _seed_workspace(
    tmp_path: Path,
    mode: PersonalStoreMode = PersonalStoreMode.PERSONAL,
) -> tuple[
    PersonalDataPaths,
    PortfolioResearchScenarioRepository,
    PortfolioResearchScenarioWorkspace,
    SavedPortfolioResearchScenario | None,
]:
    paths = PersonalDataPaths(
        market_root=tmp_path / "market",
        legacy_output_root=tmp_path / "legacy",
        personal_root=tmp_path / "market" / "personal",
    )
    repo = PortfolioResearchScenarioRepository(
        route=_route(paths, mode),
        personal_paths=paths,
    )
    saved = None
    if mode is PersonalStoreMode.PERSONAL:
        saved = repo.append(_comparison(), saved_at=_SAVED_AT)
    return paths, repo, PortfolioResearchScenarioWorkspace(repo), saved


def _open_exact(
    app: QApplication,
    widget: PortfolioResearchScenarioWidget,
    artifact_id: str,
) -> None:
    widget.account_kind_combo.setCurrentIndex(widget.account_kind_combo.findData("paper"))
    widget.portfolio_id_edit.setText("account-a")
    widget.load_saved_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker()
        and widget.saved_artifact_combo.findData(artifact_id) >= 0,
    )
    widget.saved_artifact_combo.setCurrentIndex(widget.saved_artifact_combo.findData(artifact_id))
    widget.open_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker() and widget.current_artifact_id == artifact_id,
    )


def test_exact_saved_artifact_displays_source_and_restores_only_its_stock(tmp_path: Path) -> None:
    app = _app()
    _, repo, workspace, saved = _seed_workspace(tmp_path)
    assert saved is not None
    widget = PortfolioResearchScenarioWidget(workspace)
    _open_exact(app, widget, saved.artifact_id)

    assert widget.current_comparison == saved.comparison
    assert "paper" in widget.account_summary_label.text()
    assert "account-a" in widget.account_summary_label.text()
    assert "snapshot-a" in widget.account_summary_label.text()
    assert "2026-10-08" in widget.account_summary_label.text()
    assert saved.comparison.decision_at.isoformat() in widget.account_summary_label.text()
    assert "精確現金：900000.00" in widget.valuation_summary_label.text()
    assert "原時鐘不變" in widget.scope_notice_label.text()
    assert "精確 NAV：1000000.00" in widget.valuation_summary_label.text()
    assert widget.positions_table.item(0, 0).text() == "2330"
    assert widget.positions_table.item(0, 1).text() == "1000"
    # mark_price 由既有估值契約 canonical 化為 100；UI 應保存原文而非補尾零。
    assert str(saved.comparison.account.valuation.positions[0].mark_price) == "100"
    assert widget.positions_table.item(0, 2).text() == "100"
    assert widget.positions_table.item(0, 3).text() == "100000.00"
    assert "maintain" in widget.scenario_summary_label.text()
    assert widget.restore_artifact(saved.artifact_id, "2330") is True
    assert widget.restore_artifact("sha256:" + "f" * 64, "2330") is False
    assert widget.restore_artifact(saved.artifact_id, "9999") is False

    opened_stocks: list[str] = []
    widget.stockResearchRequested.connect(opened_stocks.append)
    widget.stock_research_button.click()
    assert opened_stocks == ["2330"]
    assert repo.get_exact(
        saved.artifact_id,
        account_kind="paper",
        portfolio_id="account-a",
    ) == saved
    widget.close()


def test_target_preview_and_new_artifact_reopen_preserve_original_evidence(tmp_path: Path) -> None:
    app = _app()
    _, repo, workspace, saved = _seed_workspace(tmp_path)
    assert saved is not None
    original = saved.comparison
    widget = PortfolioResearchScenarioWidget(workspace)
    _open_exact(app, widget, saved.artifact_id)

    assert set(widget.target_spinboxes) == {"2330", "2382"}
    assert widget.target_spinboxes["2330"].value() == 1500
    assert widget.target_spinboxes["2382"].value() == 0
    assert widget.cash_weight_spin.value() == 8500
    widget.target_spinboxes["2330"].setValue(1600)
    widget.cash_weight_spin.setValue(8400)
    assert widget.current_comparison == original
    assert widget.current_artifact_id == saved.artifact_id
    assert not widget.save_button.isEnabled()

    widget.compare_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker()
        and widget.current_comparison is not None
        and widget.current_comparison.request.explicit_weights is not None
        and widget.current_comparison.request.explicit_weights.weight_for("2330") == 1600,
    )
    preview = widget.current_comparison
    assert preview is not None
    assert preview.account == original.account
    assert preview.decision_at == original.decision_at
    assert widget.current_artifact_id == saved.artifact_id
    assert widget.save_button.isEnabled()

    widget.save_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker()
        and widget.current_artifact_id != saved.artifact_id
        and widget.current_comparison == preview,
    )
    new_id = widget.current_artifact_id
    assert new_id.startswith("sha256:")
    assert widget.saved_artifact_combo.currentData() == new_id
    assert new_id in widget.status_label.text()
    assert widget.current_comparison is not None
    assert widget.current_comparison.account.snapshot_id == original.account.snapshot_id
    assert widget.current_comparison.account.as_of_date == original.account.as_of_date
    assert widget.current_comparison.decision_at == original.decision_at
    assert repo.get_exact(
        saved.artifact_id,
        account_kind="paper",
        portfolio_id="account-a",
    ) == saved
    reopened = repo.get_exact(new_id, account_kind="paper", portfolio_id="account-a")
    assert reopened is not None
    assert reopened.comparison == preview

    widget.load_saved_button.click()
    _wait_until(app, lambda: not widget.has_running_worker())
    assert widget.saved_artifact_combo.currentData() == new_id
    widget.open_button.click()
    _wait_until(
        app,
        lambda: not widget.has_running_worker() and widget.current_artifact_id == new_id,
    )
    assert widget.current_comparison == preview
    widget.close()


def test_read_only_route_keeps_save_disabled(tmp_path: Path) -> None:
    _app()
    _, _, workspace, saved = _seed_workspace(tmp_path, PersonalStoreMode.LEGACY_READ_ONLY)
    assert saved is None
    assert workspace.can_save is False
    widget = PortfolioResearchScenarioWidget(workspace)
    assert widget.save_button.isEnabled() is False
    widget.close()


def test_identity_change_cancels_stale_list_result_without_restoring_old_selection(
    tmp_path: Path,
) -> None:
    app = _app()
    _, _, real_workspace, saved = _seed_workspace(tmp_path)
    assert saved is not None

    class DelayedWorkspace(PortfolioResearchScenarioWorkspace):
        def __init__(self, base: PortfolioResearchScenarioWorkspace) -> None:
            super().__init__(base.repository)
            self.started = threading.Event()
            self.release = threading.Event()

        def list_saved(
            self,
            *,
            account_kind: str,
            portfolio_id: str,
            cancel_callback=None,
        ) -> tuple[str, ...]:
            self.started.set()
            while not self.release.wait(0.01):
                if cancel_callback is not None and cancel_callback():
                    raise InterruptedError("cancelled stale list")
            return super().list_saved(
                account_kind=account_kind,
                portfolio_id=portfolio_id,
                cancel_callback=cancel_callback,
            )

    delayed = DelayedWorkspace(real_workspace)
    widget = PortfolioResearchScenarioWidget(delayed)
    widget.account_kind_combo.setCurrentIndex(widget.account_kind_combo.findData("paper"))
    widget.portfolio_id_edit.setText("account-a")
    widget.load_saved_button.click()
    assert delayed.started.wait(2.0)

    widget.portfolio_id_edit.setText("account-b")
    delayed.release.set()
    _wait_until(app, lambda: not widget.has_running_worker())
    assert widget.current_comparison is None
    assert widget.current_artifact_id == ""
    assert widget.saved_artifact_combo.count() == 1
    assert widget.saved_artifact_combo.currentData() is None
    widget.close()
