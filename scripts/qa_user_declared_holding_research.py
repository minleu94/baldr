"""隔離驗收 user_declared holding research 的 UI、跨程序 readback 與關閉生命週期。

預設模式是 bounded writer／reader subprocess runner：writer 以實際 Portfolio UI
保存新增與 revision（含 notes／研究假設），reader 只讀同一路徑重開驗證 exact
identity／history，不建立 fixture。writer 另以慢來源讓主視窗在 worker 尚未完成時
只收到一次使用者 close；沿用 MainWindow 的合作式取消與 last-window 自然退出。
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow

from app_module.dtos.portfolio_dtos import PortfolioDTO, PositionDTO
from app_module.portfolio_condition_monitor import PortfolioConditionMonitor
from app_module.user_declared_holding_research import (
    ConditionObservation,
    ConditionRuleContext,
    MarketObservation,
    PortfolioConditionResearchProvider,
    RESEARCH_ACTION_REDUCE,
    UserDeclaredHoldingResearchService,
)
from ui_qt.main import MainWindow, apply_app_theme
from ui_qt.views.portfolio_view import PortfolioView


EVALUATION_DATE = date(2026, 9, 15)
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


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
            portfolio_name="QA Default",
            total_positions=1,
            active_positions=1,
            positions=(
                PositionDTO(
                    position_id="default:2330",
                    portfolio_id="default",
                    stock_code="2330",
                    stock_name="台積電",
                    quantity=100,
                    average_cost=Decimal("100.00"),
                    invested_amount=Decimal("10000.00"),
                    current_price=Decimal("123.45"),
                    unrealized_pnl=Decimal("2345.00"),
                    unrealized_pnl_pct=Decimal("23.45"),
                    source_type="",
                    source_id="",
                    source_summary={},
                ),
            ),
            total_invested_amount=Decimal("10000.00"),
            total_realized_pnl=Decimal("0"),
        )

    def list_trades(self):
        return []

    def get_current_price(self, _stock_code: str):
        return Decimal("123.45")


class _JournalService:
    def list_journal_entries(self, stock_code: str = ""):
        return []


class _MarketSource:
    def __call__(self, stock_code: str, evaluation_date: date) -> MarketObservation:
        return MarketObservation(
            stock_code=stock_code,
            price=Decimal("123.45"),
            as_of_date=evaluation_date,
            source_id="qa-market-snapshot",
            source_snapshot_hash="sha256:" + "c" * 64,
            available_at=NOW - timedelta(hours=1),
            quality="verified",
        )


class _ConditionContextSource:
    def __call__(self, record, evaluation_date: date) -> ConditionRuleContext:
        return ConditionRuleContext(
            source_id="qa-advice-score-snapshot",
            source_snapshot_hash="sha256:" + "d" * 64,
            as_of_date=evaluation_date,
            available_at=NOW - timedelta(hours=1),
            source_summary={
                "entry_regime": "Trend",
                "entry_total_score": "80",
                "profile_id": "qa-profile",
                "profile_version": "1.0.0",
                "strategy_config_id": "qa-score-v1",
            },
            current_regime="Trend",
            current_total_score=Decimal("80"),
            reasons=("qa_producer_rule_snapshot",),
            quality="verified",
        )


def _condition(record, evaluation_date: date) -> ConditionObservation:
    return ConditionObservation(
        stock_code=record.stock_code,
        suggested_action=RESEARCH_ACTION_REDUCE,
        as_of_date=evaluation_date,
        source_id="qa-condition-snapshot",
        source_snapshot_hash="sha256:" + "e" * 64,
        reasons=("QA 條件需人工複核",),
        summary="研究條件需人工複核",
        available_at=NOW - timedelta(hours=1),
        quality="verified",
    )


class _SlowMarketSource:
    """可觀察取消的慢市場來源，專供忙碌 close QA。"""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.cancelled = threading.Event()
        self.delay_seconds = 0.35

    def __call__(self, stock_code: str, evaluation_date: date, *, cancel_callback=None):
        self.started.set()
        deadline = time.monotonic() + self.delay_seconds
        while time.monotonic() < deadline:
            if callable(cancel_callback) and cancel_callback():
                self.cancelled.set()
                raise RuntimeError("QA slow market source cancelled cooperatively")
            time.sleep(0.005)
        return _MarketSource()(stock_code, evaluation_date)


class _ShutdownHarness(QMainWindow):
    """以既有 MainWindow shutdown methods 驗證 Portfolio 子頁生命週期。"""

    _request_shutdown_dependencies = MainWindow._request_shutdown_dependencies
    _record_shutdown_message = MainWindow._record_shutdown_message
    _freeze_child_refresh_sources = MainWindow._freeze_child_refresh_sources
    _set_shutdown_ui = MainWindow._set_shutdown_ui
    _poll_shutdown_close = MainWindow._poll_shutdown_close
    closeEvent = MainWindow.closeEvent

    def __init__(self, portfolio_view: PortfolioView) -> None:
        super().__init__()
        self.setWindowTitle("user_declared QA Portfolio")
        self._shutdown_close_requested = False
        self._shutdown_close_finalizing = False
        self._shutdown_close_started_monotonic: float | None = None
        self._shutdown_close_last_blockers: tuple[str, ...] = ()
        self._shutdown_close_last_diagnostic_monotonic: float | None = None
        self._shutdown_close_timer = QTimer(self)
        self._shutdown_close_timer.setInterval(25)
        self._shutdown_close_timer.timeout.connect(self._poll_shutdown_close)
        self.portfolio_view = portfolio_view
        self.update_view = None
        self.setCentralWidget(portfolio_view)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("all", "writer", "reader"),
        default="all",
        help="all 會以獨立 writer／reader subprocess 驗收；其餘供 bounded runner 呼叫。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/qa/user_declared_holding_research_increment_2"),
        help="隔離 QA evidence 輸出目錄。",
    )
    parser.add_argument("--runtime-root", type=Path, default=None)
    parser.add_argument("--evidence-dir", type=Path, default=None)
    return parser.parse_args(argv)


def _save(widget, path: Path) -> None:
    pixmap = widget.grab()
    if pixmap.isNull() or not pixmap.save(str(path)):
        raise AssertionError(f"Qt screenshot 保存失敗：{path}")


def _child_json(stdout: str) -> dict[str, object]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise AssertionError(f"subprocess 未輸出 JSON evidence：{stdout[-1000:]}")


def _run_child(
    mode: str,
    *,
    output_dir: Path,
    runtime_root: Path,
    evidence_dir: Path,
) -> dict[str, object]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--mode",
        mode,
        "--output-dir",
        str(output_dir),
        "--runtime-root",
        str(runtime_root),
        "--evidence-dir",
        str(evidence_dir),
    ]
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"{mode} subprocess exit={completed.returncode}\n"
            f"stdout={completed.stdout[-4000:]}\n"
            f"stderr={completed.stderr[-4000:]}"
        )
    result = _child_json(completed.stdout)
    result["subprocess_returncode"] = completed.returncode
    return result


def _run_writer(output_dir: Path, runtime_root: Path, evidence_dir: Path) -> dict[str, object]:
    runtime_root.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    apply_app_theme(app)
    service = UserDeclaredHoldingResearchService.under_output_root(
        runtime_root,
        now_provider=lambda: NOW,
    )
    fast_market = _MarketSource()
    fast_condition = PortfolioConditionResearchProvider(
        fast_market,
        condition_monitor=PortfolioConditionMonitor(),
        condition_context_source=_ConditionContextSource(),
    )
    view = PortfolioView(
        portfolio_service=_PortfolioService(runtime_root),
        journal_service=_JournalService(),
        condition_monitor=PortfolioConditionMonitor(),
        user_declared_research_service=service,
        user_declared_market_source=fast_market,
        user_declared_condition_source=fast_condition,
        parent=None,
    )
    harness = _ShutdownHarness(view)
    harness.resize(1366, 768)
    harness.show()
    app.setQuitOnLastWindowClosed(True)
    child = view.user_declared_research_widget
    tab_index = view.portfolio_detail_tabs.indexOf(
        view.user_declared_research_scroll_area.parentWidget()
    )
    if tab_index < 0:
        raise AssertionError("Portfolio 未找到聲明持倉研究 tab")
    view.portfolio_detail_tabs.setCurrentIndex(tab_index)
    state: dict[str, object] = {"close_requests_from_user": 0}
    deadline = time.monotonic() + 18.0
    slow_market = _SlowMarketSource()

    def close_from_user_once() -> None:
        if state.get("close_requests_from_user"):
            return
        state["close_requests_from_user"] = 1
        # 只有這一個 user-level close request；MainWindow 之後的 final close
        # 是其既有 shutdown coordinator 自動完成，不是第二次人工操作。
        harness.close()

    def fail_and_close(message: str) -> None:
        state["error"] = message
        close_from_user_once()

    def poll_initial() -> None:
        if child._refresh_worker is None:
            if child.form_group.isHidden() is False:
                child.form_toggle.click()
            child.form_toggle.click()
            child.stock_code_input.setText("2330")
            child.quantity_input.setValue(100)
            child.declared_cost_input.setText("100.00")
            child.declared_date_input.setDate(QDate(2026, 9, 15))
            child.notes_input.setPlainText("writer 新增 note")
            child.thesis_input.setPlainText("writer 初始研究假設")
            child.save_button.click()
            QTimer.singleShot(10, poll_after_create)
            return
        if time.monotonic() >= deadline:
            fail_and_close("initial user_declared refresh 未完成")
            return
        QTimer.singleShot(10, poll_initial)

    def poll_after_create() -> None:
        if child._refresh_worker is None:
            row = child.table_model.row_at(0)
            if row is None or row.record.revision_number != 1:
                fail_and_close("UI 新增後未讀回 revision 1")
                return
            child.quantity_input.setValue(120)
            child.notes_input.setPlainText("writer revision note")
            child.thesis_input.setPlainText("writer revision 研究假設")
            child.revise_button.click()
            QTimer.singleShot(10, poll_after_revision)
            return
        if time.monotonic() >= deadline:
            fail_and_close("UI 新增後 refresh 未完成")
            return
        QTimer.singleShot(10, poll_after_create)

    def prepare_visual_evidence() -> None:
        row = child.table_model.row_at(0)
        if row is None or row.record.revision_number != 2 or row.research_status != "ready":
            fail_and_close("UI revision 2 未產生 ready research row")
            return
        # 主畫面收合 editor／技術詳情，確保 1366×768 先看見完整結果列；
        # 技術資料另存一張圖，仍可由同一列展開核對。
        if child.form_toggle.isChecked():
            child.form_toggle.click()
        if child.technical_toggle.isChecked():
            child.technical_toggle.click()
        app.processEvents()
        _save(harness, evidence_dir / "portfolio_user_declared_research_1366.png")
        harness.resize(1700, 1100)
        app.processEvents()
        _save(harness, evidence_dir / "portfolio_user_declared_research_1700.png")
        child.technical_toggle.click()
        app.processEvents()
        _save(child, evidence_dir / "user_declared_research_technical.png")

        # 替換為可觀察慢來源；下一輪尚未完成時由使用者只按一次主視窗 close。
        child.market_source = slow_market
        child.condition_source = _condition
        child.refresh_research()
        QTimer.singleShot(10, poll_busy_close)

    def poll_after_revision() -> None:
        if child._refresh_worker is None:
            prepare_visual_evidence()
            return
        if time.monotonic() >= deadline:
            fail_and_close("UI revision 後 refresh 未完成")
            return
        QTimer.singleShot(10, poll_after_revision)

    def poll_busy_close() -> None:
        if slow_market.started.is_set():
            state["busy_close_started"] = True
            close_from_user_once()
            return
        if time.monotonic() >= deadline:
            fail_and_close("慢來源未進入 busy worker 狀態")
            return
        QTimer.singleShot(10, poll_busy_close)

    QTimer.singleShot(0, poll_initial)
    app_exec_exit_code = app.exec()
    state["app_exec_exit_code"] = app_exec_exit_code
    state["cancel_observed"] = slow_market.cancelled.is_set()
    state["forced_termination"] = False
    state["ui_saved_revision"] = 2
    state["screenshots"] = [
        str((evidence_dir / "portfolio_user_declared_research_1366.png").resolve()),
        str((evidence_dir / "portfolio_user_declared_research_1700.png").resolve()),
        str((evidence_dir / "user_declared_research_technical.png").resolve()),
    ]
    harness.deleteLater()
    app.processEvents()
    if app_exec_exit_code != 0:
        raise AssertionError(f"writer QApplication.exec exit={app_exec_exit_code}")
    if state.get("error"):
        raise AssertionError(str(state["error"]))
    if state.get("close_requests_from_user") != 1:
        raise AssertionError("busy close 未符合單次 user-level close contract")
    if not state.get("busy_close_started") or not state.get("cancel_observed"):
        raise AssertionError("busy close 未觀察到慢來源 started／cooperative cancellation")
    result = {"mode": "writer", "status": "passed", **state}
    print(json.dumps(result, ensure_ascii=False))
    return result


def _run_reader(runtime_root: Path) -> dict[str, object]:
    """獨立 reader：不 create fixture、不 append，只讀 writer 同一路徑。"""

    service = UserDeclaredHoldingResearchService.under_output_root(
        runtime_root,
        now_provider=lambda: NOW,
    )
    holdings = service.list_holdings(include_archived=True)
    if len(holdings) != 1:
        raise AssertionError(f"reader 預期一筆 writer holding，實際 {len(holdings)}")
    record = holdings[0]
    history = service.history(record.holding_id)
    expected_history_actions = ("created", "revised")
    if (
        record.revision_number != 2
        or record.quantity != 120
        or record.notes != "writer revision note"
        or record.thesis != "writer revision 研究假設"
        or tuple(item.action for item in history) != expected_history_actions
    ):
        raise AssertionError("reader 未讀回 writer UI 保存的 exact revision／notes／研究假設")
    result = {
        "mode": "reader",
        "status": "passed",
        "fixture_created_by_reader": False,
        "holding_id": record.holding_id,
        "revision_number": record.revision_number,
        "quantity": record.quantity,
        "notes": record.notes,
        "thesis": record.thesis,
        "history_actions": list(expected_history_actions),
        "history_count": len(history),
    }
    print(json.dumps(result, ensure_ascii=False))
    return result


def _run_all(args: argparse.Namespace) -> dict[str, object]:
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / f"run_{uuid4().hex[:12]}"
    runtime_root = run_dir / "runtime"
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    writer = _run_child(
        "writer",
        output_dir=output_dir,
        runtime_root=runtime_root,
        evidence_dir=evidence_dir,
    )
    reader = _run_child(
        "reader",
        output_dir=output_dir,
        runtime_root=runtime_root,
        evidence_dir=evidence_dir,
    )
    if writer.get("app_exec_exit_code") != 0 or not writer.get("cancel_observed"):
        raise AssertionError("writer busy close／自然 app.exec evidence 不完整")
    if reader.get("fixture_created_by_reader") is not False:
        raise AssertionError("reader 不得建立 fixture")
    summary = {
        "status": "passed",
        "evidence_kind": "independent_writer_reader_qt_portfolio_user_declared",
        "writer": writer,
        "reader": reader,
        "same_runtime_root": str(runtime_root.resolve()),
        "separate_processes": True,
        "writer_ui_saved_revision": 2,
        "reader_created_fixture": False,
        "busy_close_user_requests": writer.get("close_requests_from_user"),
        "busy_close_cancellation_observed": writer.get("cancel_observed"),
        "app_exec_exit_code": writer.get("app_exec_exit_code"),
        "forced_termination": writer.get("forced_termination"),
        "screenshots": writer.get("screenshots"),
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = _parse_args(argv)
    if args.mode == "all":
        _run_all(args)
        return 0
    output_dir = args.output_dir.expanduser().resolve()
    runtime_root = (args.runtime_root or (output_dir / "isolated_runtime")).expanduser().resolve()
    evidence_dir = (args.evidence_dir or output_dir).expanduser().resolve()
    if args.mode == "writer":
        _run_writer(output_dir, runtime_root, evidence_dir)
    else:
        _run_reader(runtime_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
