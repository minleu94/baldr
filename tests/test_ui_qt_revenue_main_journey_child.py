"""F12 合成 Main 旅程中新 Python PID 的 exact reopen 半段。"""

from __future__ import annotations

import hashlib
import json
import math
import os
import faulthandler
from pathlib import Path
import sys
import time

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
MAIN_INITIALIZATION_DEADLINE_SECONDS = 540.0
QUERY_PHASE_DEADLINE_SECONDS = 480.0


def _remaining_query_phase_budget_seconds(
    total_deadline_monotonic: float,
    *,
    now_monotonic: float | None = None,
) -> float:
    """讓 480 秒查詢上限服從 fresh child 的 600 秒總期限。"""

    if not math.isfinite(total_deadline_monotonic):
        raise ValueError("fresh child total deadline must be finite")
    now = time.monotonic() if now_monotonic is None else now_monotonic
    remaining = max(0.0, total_deadline_monotonic - now)
    return min(QUERY_PHASE_DEADLINE_SECONDS, remaining)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wait_until(app: object, predicate: object, *, timeout: float, label: str) -> None:
    deadline = time.monotonic() + timeout
    process_events = getattr(app, "processEvents")
    while time.monotonic() < deadline:
        process_events()
        if predicate():  # type: ignore[operator]
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {label}")


def _append_stage(path: Path, stage: str, **details: object) -> None:
    record = {
        "stage": stage,
        "pid": os.getpid(),
        "monotonic_ns": time.monotonic_ns(),
        **details,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def main() -> None:
    from tests.test_ui_qt_revenue_main_journey import (
        FRESH_CHILD_RECEIPT_PREFIX,
        _validate_and_install_startup_write_guard,
    )

    _validate_and_install_startup_write_guard()
    total_timeout_seconds = float(os.environ["F12_CHILD_TOTAL_TIMEOUT_SECONDS"])
    total_deadline_monotonic = float(
        os.environ["F12_CHILD_TOTAL_DEADLINE_MONOTONIC"]
    )
    remaining_total_seconds = total_deadline_monotonic - time.monotonic()
    if (
        not math.isfinite(total_timeout_seconds)
        or total_timeout_seconds != 600.0
        or not math.isfinite(total_deadline_monotonic)
        or remaining_total_seconds <= 0
        or remaining_total_seconds > total_timeout_seconds
    ):
        raise AssertionError("fresh child total-deadline contract is invalid")
    operation_root = Path(os.environ["F12_OPERATION_ROOT"])
    bookmark_id = os.environ["F12_BOOKMARK_ID"]
    expected_stock_code = os.environ["F12_EXPECTED_STOCK_CODE"]
    expected_query_identity = os.environ["F12_EXPECTED_QUERY_IDENTITY"]
    expected_bundle_identity = os.environ["F12_EXPECTED_BUNDLE_IDENTITY"]
    expected_monthly_reference = Path(os.environ["F12_EXPECTED_MONTHLY_REFERENCE"])
    expected_count = int(os.environ["F12_EXPECTED_COUNT"])
    source_path = Path(os.environ["PERSONAL_WATCHLIST_SOURCE"])

    stage_log = Path(os.environ["F12_CHILD_STAGE_LOG"])
    stack_trace = Path(os.environ["F12_CHILD_STACK_TRACE"])
    stack_handle = stack_trace.open("x", encoding="utf-8")
    faulthandler.enable(file=stack_handle, all_threads=True)
    initialization_started = time.monotonic()
    _append_stage(stage_log, "initialization_started")
    faulthandler.dump_traceback_later(
        MAIN_INITIALIZATION_DEADLINE_SECONDS,
        repeat=False,
        file=stack_handle,
    )
    source_sha_before = _sha256_file(source_path)
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication

        from app_module.daily_market_technical_official_disposition_revenue_bookmark_v1 import (
            DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1,
        )
        from app_module.personal_watchlist_service import PersonalWatchlistService
        from ui_qt.main import MainWindow, apply_app_theme

        _append_stage(stage_log, "imports.after")
        _append_stage(stage_log, "QApplication.before")
        app = QApplication.instance() or QApplication(["f12-fresh-main-revenue-reopen"])
        _append_stage(stage_log, "QApplication.after")
        _append_stage(stage_log, "theme.before")
        apply_app_theme(app)
        _append_stage(stage_log, "theme.after")
        _append_stage(stage_log, "MainWindow.before")
        window = MainWindow()
        elapsed = time.monotonic() - initialization_started
        _append_stage(stage_log, "MainWindow.after", elapsed_seconds=elapsed)
        _append_stage(stage_log, "initialization_complete", elapsed_seconds=elapsed)
    except BaseException as exc:
        _append_stage(stage_log, "initialization_failed", error=repr(exc))
        raise
    finally:
        faulthandler.cancel_dump_traceback_later()
        faulthandler.disable()
        stack_handle.flush()
        stack_handle.close()

    assert elapsed <= MAIN_INITIALIZATION_DEADLINE_SECONDS, (
        f"fresh Main initialization took {elapsed:.3f}s; "
        f"deadline={MAIN_INITIALIZATION_DEADLINE_SECONDS:.3f}s"
    )
    window.resize(1420, 1000)
    window.show()
    app.processEvents()

    service = window.watchlist_service
    assert type(service) is PersonalWatchlistService
    storage = service.get_storage_status()
    assert storage.is_repository is True
    target_path = service.canonical_repository_path
    target_sha_before = _sha256_file(target_path)
    bookmark = service.get_research_bookmark(bookmark_id)
    assert type(bookmark) is DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1
    assert bookmark.stock_code == expected_stock_code
    assert bookmark.selected_query_identity_sha256 == expected_query_identity
    assert bookmark.saved_recipe.f17_query.bundle_identity_sha256 == expected_bundle_identity
    assert bookmark.saved_recipe.monthly_source_reference_json == expected_monthly_reference.read_text(
        encoding="utf-8"
    )
    assert bookmark.saved_recipe.declared_stock_count == expected_count

    revenue_view = window.technical_official_revenue_research_view
    assert revenue_view.set_operation_root_parent(operation_root)
    outcomes: list[tuple[str, bool]] = []
    revenue_view.operationSettled.connect(
        lambda kind, success: outcomes.append((str(kind), bool(success)))
    )

    watchlist = window.watchlist_view
    assert watchlist.watchlist_service is service
    frame = watchlist.stocks_model.getDataFrame()
    matches = [
        index
        for index, row in frame.iterrows()
        if str(row.get("證券代號", "")).strip() == expected_stock_code
        and row.get("source") == bookmark.source
        and row.get("source_id") == bookmark.bookmark_id
    ]
    assert len(matches) == 1, frame.to_dict(orient="records")

    window._select_main_workspace("watchlist")
    index = watchlist.stocks_model.index(int(matches[0]), 0)
    watchlist.stocks_table.scrollTo(index)
    app.processEvents()
    rectangle = watchlist.stocks_table.visualRect(index)
    assert rectangle.isValid()
    QTest.mouseClick(
        watchlist.stocks_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rectangle.center(),
    )
    app.processEvents()
    assert len(watchlist.stocks_table.selectionModel().selectedRows()) == 1
    watchlist.stock_analysis_btn.click()
    query_phase_budget = _remaining_query_phase_budget_seconds(
        total_deadline_monotonic
    )
    if query_phase_budget <= 0:
        raise TimeoutError("fresh child total deadline expired before exact query wait")
    _append_stage(
        stage_log,
        "query_wait_started",
        total_deadline_seconds=total_timeout_seconds,
        total_remaining_seconds=total_deadline_monotonic - time.monotonic(),
        query_phase_budget_seconds=query_phase_budget,
        query_phase_budget_ceiling_seconds=QUERY_PHASE_DEADLINE_SECONDS,
    )
    _wait_until(
        app,
        lambda: bool(outcomes),
        timeout=query_phase_budget,
        label="typed Watchlist revenue bookmark exact reopen",
    )
    assert outcomes == [("依收藏固定雙來源重新核驗", True)], revenue_view.status_label.text()
    assert window.recommendation_view.result_source_tabs.currentWidget() is revenue_view
    assert window.workspace_stack.currentWidget() is window.workspace_widgets["recommendation"]
    assert revenue_view.current_result is not None
    assert revenue_view.current_page is not None
    assert revenue_view.current_query is not None
    assert revenue_view.current_recipe is not None
    assert revenue_view.current_page.page_index == bookmark.saved_recipe.page_index
    assert revenue_view.current_recipe.to_json() == bookmark.saved_recipe.to_json()
    assert revenue_view.current_query.query_identity_sha256 == expected_query_identity
    assert revenue_view.current_page.query.query_identity_sha256 == expected_query_identity
    assert revenue_view._page_request.to_json() == bookmark.selected_page_request_json
    assert revenue_view.current_result.counts.declared_count == expected_count
    assert revenue_view.current_result.counts.visible_count == expected_count
    assert revenue_view.current_result.availability_status == "unknown"
    assert revenue_view.current_result.historical_pit_eligible is False
    assert revenue_view._selected_row is not None
    assert revenue_view._selected_row.stock_code == expected_stock_code
    assert _sha256_file(source_path) == source_sha_before
    target_sha_after = _sha256_file(target_path)
    assert target_sha_after == target_sha_before

    receipt = {
        "status": "passed_fresh_main_revenue_reopen",
        "pid": os.getpid(),
        "parent_pid": os.getppid(),
        "bookmark_id": bookmark.bookmark_id,
        "stock_code": bookmark.stock_code,
        "query_identity": revenue_view.current_query.query_identity_sha256,
        "bundle_identity": revenue_view.current_recipe.f17_query.bundle_identity_sha256,
        "monthly_reference_identity": revenue_view.current_recipe.monthly_source_reference_identity_sha256,
        "declared_count": revenue_view.current_result.counts.declared_count,
        "query_phase_budget_seconds": query_phase_budget,
        "query_phase_budget_ceiling_seconds": QUERY_PHASE_DEADLINE_SECONDS,
        "source_sha256": source_sha_before,
        "private_target_sha256_before": target_sha_before,
        "private_target_sha256_after": target_sha_after,
    }
    print(
        FRESH_CHILD_RECEIPT_PREFIX
        + json.dumps(receipt, ensure_ascii=False, sort_keys=True),
        flush=True,
    )

    window.close()
    _wait_until(
        app,
        lambda: not window.isVisible(),
        timeout=120,
        label="fresh Main close after exact readback",
    )


if __name__ == "__main__":
    main()
