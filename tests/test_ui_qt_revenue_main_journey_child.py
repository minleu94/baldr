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
    expected_request_identity = os.environ["F12_EXPECTED_REQUEST_IDENTITY"]
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
        from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
            DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1,
        )
        from app_module.daily_market_technical_official_disposition_query_v1 import (
            DailyMarketTechnicalOfficialDispositionQueryV1,
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
    saved_recipe = bookmark.saved_recipe
    selected_page_request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.from_json(
        bookmark.selected_page_request_json
    )
    assert selected_page_request.to_json() == bookmark.selected_page_request_json
    assert selected_page_request.request_identity_sha256 == expected_request_identity
    assert selected_page_request.query.query_identity_sha256 == bookmark.selected_query_identity_sha256
    assert selected_page_request.page_index == saved_recipe.page_index
    assert selected_page_request.page_size == saved_recipe.page_size
    selected_query = selected_page_request.query
    saved_f17_query = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(
        saved_recipe.f17_query_json
    )
    assert saved_f17_query.to_json() == saved_recipe.f17_query_json
    assert selected_query.ma_query.f17_query.to_json() == saved_f17_query.to_json()
    assert selected_query.ma_query.ma_states == saved_recipe.ma_states
    assert selected_query.minimum_yoy_percent == saved_recipe.minimum_yoy_percent
    assert selected_query.condition_combine_mode == saved_recipe.condition_combine_mode
    assert selected_query.unknown_policy == saved_recipe.unknown_policy
    assert tuple(item.to_dict() for item in selected_query.sort_clauses) == tuple(
        item.to_dict() for item in saved_recipe.sort_clauses
    )
    assert saved_f17_query.bundle_identity_sha256 == expected_bundle_identity
    assert saved_recipe.monthly_source_reference_json == expected_monthly_reference.read_text(
        encoding="utf-8"
    )
    assert saved_recipe.declared_stock_count == expected_count

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
    reopened_recipe = revenue_view.current_recipe
    reopened_query = revenue_view.current_query
    reopened_page = revenue_view.current_page
    reopened_request = revenue_view._page_request
    assert reopened_recipe is not None
    assert reopened_query is not None
    assert reopened_page is not None
    assert type(reopened_request) is DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1
    reopened_f17_query = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(
        reopened_recipe.f17_query_json
    )
    assert reopened_f17_query.bundle_identity_sha256 == expected_bundle_identity
    assert reopened_f17_query.to_json() == saved_recipe.f17_query_json
    assert reopened_f17_query.to_json() == reopened_query.ma_query.f17_query.to_json()
    assert reopened_page.query.to_json() == reopened_query.to_json()
    assert reopened_request.query.to_json() == reopened_query.to_json()
    assert reopened_request.to_json() == DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.from_json(
        reopened_request.to_json()
    ).to_json()
    assert reopened_recipe.to_json() == saved_recipe.to_json()
    assert reopened_query.query_identity_sha256 != bookmark.selected_query_identity_sha256
    assert reopened_request.request_identity_sha256 != selected_page_request.request_identity_sha256
    assert reopened_page.query.query_identity_sha256 == reopened_query.query_identity_sha256
    assert reopened_request.query.query_identity_sha256 == reopened_query.query_identity_sha256
    assert reopened_page.request_identity_sha256 == reopened_request.request_identity_sha256
    assert reopened_page.page_index == reopened_request.page_index == saved_recipe.page_index
    assert reopened_page.page_size == reopened_request.page_size == saved_recipe.page_size
    assert reopened_request.page_index == selected_page_request.page_index
    assert reopened_request.page_size == selected_page_request.page_size
    assert reopened_query.ma_query.f17_query.to_json() == saved_recipe.f17_query_json
    assert reopened_query.ma_query.ma_states == saved_recipe.ma_states
    assert reopened_query.minimum_yoy_percent == saved_recipe.minimum_yoy_percent
    assert reopened_query.condition_combine_mode == saved_recipe.condition_combine_mode
    assert reopened_query.unknown_policy == saved_recipe.unknown_policy
    assert tuple(item.to_dict() for item in reopened_query.sort_clauses) == tuple(
        item.to_dict() for item in saved_recipe.sort_clauses
    )
    assert reopened_query.monthly_yoy_cutoff == saved_recipe.monthly_cutoff_utc
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
        "selected_query_identity": bookmark.selected_query_identity_sha256,
        "selected_request_identity": selected_page_request.request_identity_sha256,
        "selected_request_query_identity": selected_page_request.query.query_identity_sha256,
        "selected_page_request_json_sha256": hashlib.sha256(
            bookmark.selected_page_request_json.encode("utf-8")
        ).hexdigest(),
        "selected_recipe_identity": saved_recipe.recipe_identity_sha256,
        "saved_recipe_json_sha256": hashlib.sha256(
            bookmark.saved_recipe_json.encode("utf-8")
        ).hexdigest(),
        "saved_f17_query_identity": saved_f17_query.query_identity_sha256,
        "saved_f17_query_json_sha256": hashlib.sha256(
            saved_recipe.f17_query_json.encode("utf-8")
        ).hexdigest(),
        "selected_page_index": selected_page_request.page_index,
        "selected_page_size": selected_page_request.page_size,
        "reopened_query_identity": reopened_query.query_identity_sha256,
        "reopened_page_query_identity": reopened_page.query.query_identity_sha256,
        "reopened_request_identity": reopened_request.request_identity_sha256,
        "reopened_request_query_identity": reopened_request.query.query_identity_sha256,
        "reopened_page_request_identity": reopened_page.request_identity_sha256,
        "reopened_page_index": reopened_page.page_index,
        "reopened_page_size": reopened_page.page_size,
        "reopened_request_page_index": reopened_request.page_index,
        "reopened_request_page_size": reopened_request.page_size,
        "reopened_recipe_identity": reopened_recipe.recipe_identity_sha256,
        "reopened_recipe_json_sha256": hashlib.sha256(
            reopened_recipe.to_json().encode("utf-8")
        ).hexdigest(),
        "reopened_f17_query_identity": reopened_f17_query.query_identity_sha256,
        "reopened_f17_query_json_sha256": hashlib.sha256(
            reopened_f17_query.to_json().encode("utf-8")
        ).hexdigest(),
        "reopened_query_ma_states": (
            None if reopened_query.ma_query.ma_states is None
            else list(reopened_query.ma_query.ma_states)
        ),
        "reopened_query_minimum_yoy_percent": reopened_query.to_dict()["minimum_yoy_percent"],
        "reopened_query_condition_combine_mode": reopened_query.condition_combine_mode,
        "reopened_query_unknown_policy": reopened_query.unknown_policy,
        "reopened_query_sort_clauses": [
            item.to_dict() for item in reopened_query.sort_clauses
        ],
        "reopened_monthly_cutoff_utc": reopened_query.monthly_yoy_cutoff,
        "reopened_monthly_method_id": reopened_query.monthly_yoy_method_id,
        "reopened_monthly_method_version": reopened_query.monthly_yoy_method_version,
        "reopened_page_request_json_sha256": hashlib.sha256(
            reopened_request.to_json().encode("utf-8")
        ).hexdigest(),
        "bundle_identity": reopened_f17_query.bundle_identity_sha256,
        "monthly_reference_identity": reopened_recipe.monthly_source_reference_identity_sha256,
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
