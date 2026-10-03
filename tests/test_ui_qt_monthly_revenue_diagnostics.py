"""月營收 dry-run 診斷的可見說明回歸。"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox

from ui_qt.views.update_view import UpdateView


class _VisibleState:
    def __init__(self) -> None:
        self.visible: bool | None = None

    def setVisible(self, visible: bool) -> None:
        self.visible = visible


class _UpdateViewHarness:
    _monthly_revenue_diagnostic_display = staticmethod(
        UpdateView._monthly_revenue_diagnostic_display
    )

    def __init__(self) -> None:
        self.progress_bar = _VisibleState()
        self.progress_label = _VisibleState()
        self.logs: list[str] = []
        self.summaries: list[dict[str, Any]] = []
        self.enabled_states: list[bool] = []
        self.cache_invalidations = 0

    def _invalidate_detail_cache(self) -> None:
        self.cache_invalidations += 1

    def _set_monthly_revenue_buttons_enabled(self, enabled: bool) -> None:
        self.enabled_states.append(enabled)

    def _log(self, message: str) -> None:
        self.logs.append(message)

    def _render_manual_update_summary(self, status: str, **kwargs: Any) -> None:
        self.summaries.append({"status": status, **kwargs})


def _capture_dialogs(monkeypatch: Any) -> list[tuple[str, str]]:
    dialogs: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: dialogs.append((title, message)),
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, message: dialogs.append((title, message)),
    )
    return dialogs


def test_mapping_blocker_is_explained_and_a_later_clean_retry_has_no_stale_diagnostic(
    monkeypatch: Any,
) -> None:
    dialogs = _capture_dialogs(monkeypatch)
    view = _UpdateViewHarness()
    blocked_result = {
        "success": False,
        "ready_for_apply": False,
        "raw_row_count": 1855,
        "normalized_record_count": 0,
        "diagnostic_count": 1,
        "message": "MOPS 月營收 dry-run 完成：normalized=0, diagnostics=1",
        "diagnostics": [
            {
                "code": "fundamental_availability.snapshot_mapping_incomplete",
                "message": (
                    "MOPS snapshot rows without a governed availability mapping; "
                    "unmatched_count=1855; sample=1240|2026-08"
                ),
            }
        ],
    }

    UpdateView._on_monthly_revenue_finished(view, blocked_result, apply=False)

    failure_message = view.summaries[-1]["message"]
    assert view.summaries[-1]["status"] == "failed"
    assert dialogs[-1][0] == "月營收處理失敗"
    assert dialogs[-1][1] == failure_message
    assert "fundamental_availability.snapshot_mapping_incomplete" in failure_message
    assert "unmatched_count=1855" in failure_message
    assert "正式治理的可得日 mapping" in failure_message
    assert "不得以抓取日代替可得日" in failure_message
    assert "補齊並核准對應期間" in failure_message
    assert any("snapshot_mapping_incomplete" in line for line in view.logs)
    assert any("unmatched_count=1855" in line for line in view.logs)
    assert view.enabled_states == [True]
    assert view.progress_bar.visible is False
    assert view.progress_label.visible is False

    clean_retry = {
        "success": True,
        "ready_for_apply": True,
        "raw_row_count": 1855,
        "normalized_record_count": 1855,
        "diagnostic_count": 0,
        "message": "MOPS 月營收 dry-run 完成：normalized=1,855, diagnostics=0",
        "diagnostics": [],
    }
    UpdateView._on_monthly_revenue_finished(view, clean_retry, apply=False)

    assert view.summaries[-1]["status"] == "success"
    assert "fundamental_availability.snapshot_mapping_incomplete" not in view.summaries[-1]["message"]
    assert dialogs[-1][0] == "月營收處理完成"
    assert view.cache_invalidations == 2


def test_missing_candidate_snapshot_has_a_clear_fetch_then_dry_run_next_step(
    monkeypatch: Any,
) -> None:
    dialogs = _capture_dialogs(monkeypatch)
    view = _UpdateViewHarness()
    result = {
        "success": False,
        "ready_for_apply": False,
        "raw_row_count": 0,
        "normalized_record_count": 0,
        "diagnostic_count": 1,
        "message": "MOPS 月營收 dry-run 失敗",
        "diagnostics": [
            {
                "code": "monthly_revenue.dry_run_error",
                "message": "指定 snapshot 不存在：candidate.csv",
            }
        ],
    }

    UpdateView._on_monthly_revenue_finished(view, result, apply=False)

    shown = dialogs[-1][1]
    assert "指定的月營收候選快照檔不存在" in shown
    assert "抓取最新候選快照" in shown
    assert "重新執行 dry-run" in shown
    assert "不會替代正式可得日 mapping" in shown
    assert view.summaries[-1]["status"] == "failed"


def test_unknown_diagnostic_stays_failed_and_is_not_interpreted_as_ready(
    monkeypatch: Any,
) -> None:
    dialogs = _capture_dialogs(monkeypatch)
    view = _UpdateViewHarness()
    result = {
        "success": False,
        "ready_for_apply": False,
        "raw_row_count": 3,
        "normalized_record_count": 0,
        "diagnostic_count": 1,
        "message": "dry-run blocked",
        "diagnostics": [
            {"code": "future.diagnostic.v9", "message": "unrecognized source condition"}
        ],
    }

    UpdateView._on_monthly_revenue_finished(view, result, apply=False)

    shown = dialogs[-1][1]
    assert "future.diagnostic.v9" in shown
    assert "unrecognized source condition" in shown
    assert "沒有這個診斷代碼的已知解讀" in shown
    assert "不會推定資料可用" in shown
    assert "不要以此結果執行正式回填" in shown
    assert view.summaries[-1]["status"] == "failed"
