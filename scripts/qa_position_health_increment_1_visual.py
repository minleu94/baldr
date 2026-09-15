"""Render isolated Position Health Qt panels for Increment 1 visual QA.

The runner intentionally uses the same evaluator/read-service fixture as the
contract tests, while keeping all generated receipts and screenshots outside
the repository's production data root.  It is a bounded, read-only consumer
exercise: no evaluator receipt is written by the UI views themselves.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication, QGroupBox

from app_module.dtos.portfolio_dtos import PortfolioDTO, PositionDTO
from app_module.position_health_transition_read_service import (
    PositionHealthTransitionReadService,
)
from tests.test_position_health_transition_read_service import (
    DECISION_DATE,
    _reader,
    _write_source_fixture,
)
from tests.test_ui_qt_workbench_view import _dashboard_with_replay
from ui_qt.main import apply_app_theme
from ui_qt.views.portfolio_view import PortfolioView
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView


class _RecordingHealthReader:
    def __init__(self, model) -> None:
        self.model = model

    def read_latest(self, **_kwargs):
        return self.model


class _Config:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root
        self.data_dir = output_root
        self.broker_branch_registry_file = output_root / "missing.csv"

    def resolve_output_path(self, relative_path: str) -> Path:
        return self.output_root / relative_path


class _PortfolioService:
    def __init__(self, output_root: Path) -> None:
        self.config = _Config(output_root)

    def get_portfolio(self) -> PortfolioDTO:
        return PortfolioDTO(
            portfolio_id="default",
            portfolio_name="Default",
            total_positions=1,
            active_positions=1,
            positions=(
                PositionDTO(
                    position_id="default:2330",
                    portfolio_id="default",
                    stock_code="2330",
                    stock_name="台積電",
                    quantity=1000,
                    average_cost=100,
                    invested_amount=100000,
                    current_price=101,
                    source_summary={"current_price_date": "2026-09-14"},
                ),
            ),
            total_invested_amount=100000,
            total_realized_pnl=0,
        )

    def list_trades(self):
        return []

    def get_current_price(self, _stock_code: str):
        return 101


class _JournalService:
    def list_journal_entries(self, stock_code: str = ""):
        return []


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/qa/position_health_increment_1_visual"),
        help="Directory for isolated PNG evidence.",
    )
    return parser.parse_args()


def _paper_group(view: PortfolioView) -> QGroupBox:
    groups = [
        group
        for group in view.findChildren(QGroupBox)
        if "Paper 持倉健康" in group.title()
    ]
    if len(groups) != 1:
        raise AssertionError(f"expected one Paper health group, found {len(groups)}")
    return groups[0]


def _save_panel(widget, path: Path) -> None:
    if not widget.grab().save(str(path)):
        raise AssertionError(f"failed to save Qt evidence: {path}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="position-health-visual-") as temp_dir:
        temp = Path(temp_dir)
        source_output = _write_source_fixture(
            temp / "health", action="exit", metric_value="0"
        )
        verified = _reader(source_output).read_latest(
            expected_decision_date=DECISION_DATE
        )
        missing = PositionHealthTransitionReadService(temp / "missing").read_latest()
        if verified.status != "passed" or verified.position_ids != (
            "paper:2330:entry-20260901",
        ):
            raise AssertionError(
                "positive fixture did not produce the expected verified Paper row"
            )

        app = QApplication.instance() or QApplication([])
        apply_app_theme(app)
        portfolio_service = _PortfolioService(temp / "portfolio")
        journal_service = _JournalService()

        portfolio_verified = PortfolioView(
            portfolio_service=portfolio_service,
            journal_service=journal_service,
            position_health_read_service=_RecordingHealthReader(verified),
        )
        portfolio_verified.resize(1600, 1100)
        portfolio_verified.show()
        app.processEvents()
        if portfolio_verified.position_health_model.rowCount() <= 0:
            raise AssertionError("Portfolio positive health row was not rendered")
        if portfolio_verified.position_health_table.model() is not portfolio_verified.position_health_model:
            raise AssertionError("Portfolio health table is not bound to its typed model")
        _save_panel(
            _paper_group(portfolio_verified),
            args.output_dir / "portfolio_verified.png",
        )

        portfolio_degraded = PortfolioView(
            portfolio_service=portfolio_service,
            journal_service=journal_service,
            position_health_read_service=_RecordingHealthReader(missing),
        )
        portfolio_degraded.resize(1600, 1100)
        portfolio_degraded.show()
        app.processEvents()
        if portfolio_degraded.position_health_model.rowCount() != 0:
            raise AssertionError("Portfolio missing receipt rendered an unsafe row")
        if "尚無持倉健康評估資料" not in portfolio_degraded.position_health_summary_label.text():
            raise AssertionError("Portfolio missing receipt summary is not user-readable")
        if "[Errno" in portfolio_degraded.position_health_summary_label.text():
            raise AssertionError("Portfolio summary leaked a Python exception")
        _save_panel(
            _paper_group(portfolio_degraded),
            args.output_dir / "portfolio_degraded.png",
        )

        base_dashboard = _dashboard_with_replay()
        workbench_verified = UnifiedDecisionWorkbenchView(
            dashboard=replace(base_dashboard, position_health=verified),
            auto_refresh=False,
        )
        workbench_verified.resize(1600, 1100)
        workbench_verified.show()
        app.processEvents()
        if workbench_verified.position_health_model.rowCount() <= 0:
            raise AssertionError("Workbench positive health row was not rendered")
        _save_panel(
            workbench_verified.position_health_section_title.parentWidget(),
            args.output_dir / "workbench_verified.png",
        )

        workbench_degraded = UnifiedDecisionWorkbenchView(
            dashboard=replace(base_dashboard, position_health=missing),
            auto_refresh=False,
        )
        workbench_degraded.resize(1600, 1100)
        workbench_degraded.show()
        app.processEvents()
        if workbench_degraded.position_health_model.rowCount() != 0:
            raise AssertionError("Workbench missing receipt rendered an unsafe row")
        if "尚無持倉健康評估資料" not in workbench_degraded.position_health_summary_label.text():
            raise AssertionError("Workbench missing receipt summary is not user-readable")
        if "[Errno" in workbench_degraded.position_health_summary_label.text():
            raise AssertionError("Workbench summary leaked a Python exception")
        _save_panel(
            workbench_degraded.position_health_section_title.parentWidget(),
            args.output_dir / "workbench_degraded.png",
        )

        print("visual_qa_status=passed")
        print(f"verified_status={verified.status}")
        print(f"verified_position_ids={verified.position_ids}")
        print(f"portfolio_verified_row_count={portfolio_verified.position_health_model.rowCount()}")
        print(f"workbench_verified_row_count={workbench_verified.position_health_model.rowCount()}")
        print(f"portfolio_degraded_summary={portfolio_degraded.position_health_summary_label.text()}")
        print(f"workbench_degraded_summary={workbench_degraded.position_health_summary_label.text()}")
        for path in sorted(args.output_dir.glob("*.png")):
            print(f"screenshot={path.resolve()}")

        for widget in (
            workbench_degraded,
            workbench_verified,
            portfolio_degraded,
            portfolio_verified,
        ):
            widget.close()
            widget.deleteLater()
        app.processEvents()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
