"""真 MainWindow 與新 PID 的 F07 完整母體價格研究收藏旅程。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest_plugins = ("tests.test_daily_market_technical_universe_price_query_v1",)

from tests import test_ui_qt_technical_official_main_new_process as _process_support

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkV1,
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
)
from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceComparisonV1,
    DailyMarketTechnicalUniversePriceSelectionV1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePriceStockV1,
)
if TYPE_CHECKING:
    from ui_qt.views.daily_market_technical_price_comparison_v1_view import (
        DailyMarketTechnicalPriceComparisonV1View,
    )
    from ui_qt.views.daily_market_technical_price_stock_v1_view import (
        DailyMarketTechnicalPriceStockV1View,
    )
    from ui_qt.views.daily_market_technical_universe_price_view_v1 import (
        DailyMarketTechnicalUniversePriceV1View,
    )


_TOTAL_DEADLINE_SECONDS = _process_support._TOTAL_DEADLINE_SECONDS
_CHILD_DEADLINE_SECONDS = _process_support._CHILD_DEADLINE_SECONDS
_QA_ROOT = Path("output/qa/f07_fulln_price_main_new_process_20261008_a")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def _append_phase(path: Path, started: float, name: str, **details: object) -> None:
    record = {
        "phase": name,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        **details,
    }
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()


def _phase_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_digest(source_root: Path) -> str:
    inventory = _process_support._tree_inventory(source_root)
    return hashlib.sha256(
        json.dumps(inventory, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _path_key(path: str | Path) -> str:
    """以不觸碰檔案系統的正規字串比較長路徑設定。"""
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _payload_int(value: object, *, field_name: str) -> int:
    if type(value) is not int:
        raise AssertionError(f"child payload {field_name} 必須是整數")
    return cast(int, value)


def _wait_for(
    app: Any,
    predicate: Any,
    *,
    deadline: float,
    stage: str,
    cancel_marker: Path | None = None,
) -> None:
    while not predicate():
        app.processEvents()
        if cancel_marker is not None and cancel_marker.exists():
            raise AssertionError(f"父程序要求 child 合作取消：{stage}")
        if time.monotonic() >= deadline:
            raise AssertionError(f"F07 新程序旅程超過既有 deadline：{stage}")
        time.sleep(0.005)
    app.processEvents()
    if cancel_marker is not None and cancel_marker.exists():
        raise AssertionError(f"父程序要求 child 合作取消：{stage}")
    if time.monotonic() > deadline:
        raise AssertionError(f"F07 新程序旅程在 deadline 後完成：{stage}")


def _view_idle(view: DailyMarketTechnicalUniversePriceV1View) -> bool:
    return not view.busy and view.workers_remaining == 0


def _complete_source_index(view: DailyMarketTechnicalUniversePriceV1View) -> int:
    for index in range(view.sources.count()):
        entry = view.sources.itemData(index)
        if getattr(entry, "source_status", None) == "complete":
            return index
    return -1


def _selected_code(view: DailyMarketTechnicalUniversePriceV1View) -> str | None:
    index = view.table.currentIndex()
    if not index.isValid():
        return None
    row = view.results_model.row_at(index.row())
    code = getattr(getattr(row, "technical_row", None), "stock_code", None)
    return code if isinstance(code, str) else None


def _scroll_geometry(view: DailyMarketTechnicalUniversePriceV1View) -> dict[str, object]:
    scrollbar = view.table.verticalScrollBar()
    viewport = view.table.viewport()
    page = view.current_page
    model = view.table.model()
    return {
        "scroll_value": int(scrollbar.value()),
        "scroll_minimum": int(scrollbar.minimum()),
        "scroll_maximum": int(scrollbar.maximum()),
        "viewport_width": int(viewport.width()),
        "viewport_height": int(viewport.height()),
        "table_width": int(view.table.width()),
        "table_height": int(view.table.height()),
        "table_visible": bool(view.table.isVisible()),
        "view_visible": bool(view.isVisible()),
        "model_row_count": int(model.rowCount()) if model is not None else 0,
        "page_row_count": len(page.rows) if page is not None else 0,
        "page_index": page.request.page_index if page is not None else None,
    }


def _click_price_row(
    app: Any,
    view: DailyMarketTechnicalUniversePriceV1View,
    stock_code: str,
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    assert view.select_stock_code(stock_code)
    index = view.results_model.index_for_stock(stock_code)
    assert index.isValid()
    view.table.scrollTo(index)
    app.processEvents()
    rect = view.table.visualRect(index)
    assert rect.isValid() and view.table.viewport().rect().intersects(rect)
    QTest.mouseClick(view.table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    app.processEvents()


def _double_click_price_row(
    app: Any,
    view: DailyMarketTechnicalUniversePriceV1View,
    stock_code: str,
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    _click_price_row(app, view, stock_code)
    index = view.results_model.index_for_stock(stock_code)
    rect = view.table.visualRect(index)
    assert rect.isValid() and view.table.viewport().rect().intersects(rect)
    QTest.mouseDClick(view.table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    app.processEvents()


def _watchlist_bookmark_row(
    watchlist: Any, bookmark_id: str, *, price_bookmark_source: str
) -> int:
    model = watchlist.stocks_table.model()
    assert model is not None
    frame = watchlist.stocks_model.getDataFrame()
    matches: list[int] = []
    for index, row in frame.iterrows():
        source = str(row.get("source", "") or "").strip()
        source_id = str(row.get("source_id", "") or "").strip()
        if source == price_bookmark_source and source_id == bookmark_id:
            matches.append(int(index))
    assert len(matches) == 1, "Watchlist 必須只有一筆目標價格研究收藏列"
    return matches[0]


def _click_watchlist_row(app: Any, watchlist: Any, row_number: int) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    model = watchlist.stocks_table.model()
    assert model is not None and 0 <= row_number < model.rowCount()
    watchlist.page_scroll.ensureWidgetVisible(watchlist.stocks_table)
    index = model.index(row_number, 0)
    watchlist.stocks_table.scrollTo(index)
    app.processEvents()
    rect = watchlist.stocks_table.visualRect(index)
    assert rect.isValid() and watchlist.stocks_table.viewport().rect().intersects(rect)
    QTest.mouseClick(
        watchlist.stocks_table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center()
    )
    QTest.mouseDClick(
        watchlist.stocks_table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center()
    )
    app.processEvents()


def _helper_source() -> str:
    return "\n".join(
        (
            "from __future__ import annotations",
            "import sys",
            "from pathlib import Path",
            "repo_root = Path(sys.argv[1]).resolve()",
            "payload_path = Path(sys.argv[2]).resolve()",
            "sys.path.insert(0, str(repo_root))",
            "sys.path.insert(0, str(repo_root / 'tests'))",
            "from test_ui_qt_daily_market_technical_universe_price_main_new_process import _child_main",
            "raise SystemExit(_child_main(payload_path))",
            "",
        )
    )


def _child_main(payload_path: Path) -> int:
    payload_value = json.loads(payload_path.read_text(encoding="utf-8"))
    if not isinstance(payload_value, dict):
        raise AssertionError("child payload 必須是 JSON object")
    payload = cast(dict[str, object], payload_value)
    expected_env = _process_support._validate_child_environment(
        os.environ,
        expected_environment=payload.get("expected_environment"),
        unset_environment_keys=payload.get("unset_environment_keys"),
    )
    source_root = Path(str(payload["source_root"])).resolve(strict=True)
    source_before = _process_support._tree_inventory(source_root)
    source_before_sha = hashlib.sha256(
        json.dumps(source_before, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if source_before_sha != payload.get("source_inventory_sha256"):
        raise AssertionError("child 啟動前 F07 synthetic source inventory 已改變")
    attempt_root = Path(str(payload["attempt_root"])).resolve(strict=True)
    receipt_path = attempt_root / "child_receipt.json"
    trace_path = attempt_root / "child_trace.jsonl"
    cancel_marker = Path(str(payload["cancel_marker_path"]))
    _process_support._check_cancel_marker(cancel_marker)
    started = time.monotonic()
    remaining_total = payload.get("remaining_total_seconds")
    if type(remaining_total) not in {int, float}:
        raise AssertionError("child payload remaining_total_seconds 無效")
    remaining_total_seconds = cast(float, remaining_total)
    if remaining_total_seconds <= 0:
        raise AssertionError("child payload remaining_total_seconds 無效")
    deadline = started + min(
        _CHILD_DEADLINE_SECONDS,
        float(remaining_total_seconds),
    )
    receipt: dict[str, object] = {
        "status": "in_progress",
        "pid": os.getpid(),
        "parent_pid": os.getppid(),
        "executable": _process_support._normalize_executable_path(
            sys.executable, label="child sys.executable"
        ),
        "source_inventory_before_sha256": source_before_sha,
        "phases": [],
    }
    phases: list[dict[str, object]] = []

    def mark(name: str, **details: object) -> None:
        item = {
            "phase": name,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            **details,
        }
        phases.append(item)
        receipt["phases"] = phases
        _write_json(receipt_path, receipt)
        _append_phase(trace_path, started, name, **details)

    network_attempts: list[str] = []

    def deny_network(*args: object, **kwargs: object) -> int:
        target = str(args[1]) if len(args) > 1 else "unknown"
        network_attempts.append(target)
        raise AssertionError(f"F07 synthetic MainWindow 禁止網路連線：{target}")

    setattr(socket.socket, "connect", deny_network)
    setattr(socket.socket, "connect_ex", deny_network)
    setattr(socket, "create_connection", deny_network)

    app: Any | None = None
    window: Any | None = None
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication

        from app_module.daily_market_technical_universe_price_bookmark_v1 import (
            DailyMarketTechnicalUniversePriceBookmarkV1,
            DailyMarketTechnicalUniversePriceBookmarkStateV1,
        )
        from app_module.daily_market_technical_universe_price_comparison_v1 import (
            DailyMarketTechnicalUniversePriceSelectionV1,
        )
        from app_module.daily_market_technical_universe_price_query_v1 import (
            DailyMarketTechnicalUniversePriceStockV1,
        )
        from app_module.watchlist_service import TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE
        from ui_qt.views.daily_market_technical_price_comparison_v1_view import (
            DailyMarketTechnicalPriceComparisonV1View,
        )
        from ui_qt.views.daily_market_technical_price_stock_v1_view import (
            DailyMarketTechnicalPriceStockV1View,
        )
        from ui_qt.main import MainWindow

        app = cast(QApplication, QApplication.instance() or QApplication([]))
        window = MainWindow()
        output_root = Path(expected_env["OUTPUT_ROOT"]).resolve(strict=False)
        watchlist_root = output_root / "watchlist"
        watchlist_before = _process_support._watchlist_inventory(watchlist_root)
        expected_primary = tuple(
            tuple(cast(tuple[str, int, str], item))
            for item in cast(list[object], payload["watchlist_primary_bytes"])
        )
        if _process_support._primary_watchlist_bytes(watchlist_before) != expected_primary:
            raise AssertionError("child Main 啟動前 Watchlist 收藏 bytes 不符")
        assert Path(window.config.output_root).resolve() == output_root
        assert Path(window.config.data_root).resolve() == Path(
            expected_env["DATA_ROOT"]
        ).resolve()
        configured_store = getattr(window.config, "technical_universe_read_root", None)
        assert configured_store is not None
        assert Path(configured_store).resolve() == Path(
            str(payload["store_root"])
        ).resolve()
        service = window.watchlist_service
        assert service is not None
        assert Path(service.watchlist_dir).resolve() == watchlist_root.resolve()
        main_price_view = window.recommendation_view.daily_market_research_view.technical_price_view
        assert main_price_view is not None

        def trace_scroll_restore(stage: str) -> None:
            mark(f"bookmark_scroll_{stage}", **_scroll_geometry(main_price_view))

        original_restore = main_price_view.restore_bookmark_state

        def traced_restore_bookmark_state(
            value: DailyMarketTechnicalUniversePriceBookmarkStateV1,
        ) -> bool:
            trace_scroll_restore("callback_before_apply")
            result = original_restore(value)
            trace_scroll_restore("callback_returned_before_main_navigation")
            return result

        setattr(main_price_view, "restore_bookmark_state", traced_restore_bookmark_state)
        window.resize(1440, 980)
        window.show()
        app.processEvents()
        mark("new_main_constructed", main_type=type(window).__name__)

        watchlist = window.watchlist_view
        state_events: list[object] = []
        watchlist.technicalPriceBookmarkStateReady.connect(state_events.append)
        nav = window.left_navigation.button_for_key("watchlist")
        assert nav is not None and nav.isVisible()
        QTest.mouseClick(nav, Qt.MouseButton.LeftButton)
        assert window.left_navigation.current_key() == "watchlist"
        expected_bookmark_id = str(payload["bookmark_id"])
        persisted = service.get_research_bookmark(expected_bookmark_id)
        if type(persisted) is not DailyMarketTechnicalUniversePriceBookmarkV1:
            raise AssertionError("child Watchlist 未讀回精確價格收藏 DTO")
        expected_bookmark_json = str(payload["bookmark_json"])
        if persisted.to_json() != expected_bookmark_json:
            raise AssertionError("child Watchlist 收藏 JSON 與 parent 原件不同")

        controls = watchlist.price_bookmark_controls
        _wait_for(
            app,
            lambda: (
                not controls.busy
                and watchlist.stocks_model is not None
            and _watchlist_bookmark_row(
                watchlist,
                expected_bookmark_id,
                price_bookmark_source=TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE,
            ) >= 0
            ),
            deadline=deadline,
            stage="child Watchlist 清單與價格收藏盤點",
            cancel_marker=cancel_marker,
        )
        row_index = _watchlist_bookmark_row(
            watchlist,
            expected_bookmark_id,
            price_bookmark_source=TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE,
        )
        mark("watchlist_exact_bookmark_listed", row_index=row_index)
        _click_watchlist_row(app, watchlist, row_index)

        _wait_for(
            app,
            lambda: bool(state_events)
            and not controls.busy
            and window.recommendation_view.daily_market_research_view.technical_price_view.current_page
            is not None,
            deadline=deadline,
            stage="Watchlist 雙擊後 F07 fresh exact reopen",
            cancel_marker=cancel_marker,
        )
        if len(state_events) != 1:
            raise AssertionError("Watchlist 雙擊必須只發出一次 fresh 價格收藏狀態")
        state = state_events[0]
        if type(state) is not DailyMarketTechnicalUniversePriceBookmarkStateV1:
            raise AssertionError("Watchlist 未交付 typed fresh 價格收藏狀態")
        state = cast(DailyMarketTechnicalUniversePriceBookmarkStateV1, state)
        if state.bookmark.to_json() != expected_bookmark_json:
            raise AssertionError("新程序 fresh reader 重開的收藏與原保存內容不同")
        if state.selected.selection.to_dict() != state.bookmark.selected.to_dict():
            raise AssertionError("fresh selected anchors 與原收藏不同")
        expected_query_json = str(payload["query_json"])
        expected_page_identity = str(payload["page_identity_sha256"])
        expected_query_identity = str(payload["query_identity_sha256"])
        expected_stock_code = str(payload["selected_stock_code"])
        expected_page_index = _payload_int(
            payload.get("selected_page_index"), field_name="selected_page_index"
        )
        expected_basket_codes = tuple(
            str(value) for value in cast(list[object], payload["comparison_stock_codes"])
        )
        expected_basket_pages = tuple(
            _payload_int(value, field_name="comparison_page_indices[]")
            for value in cast(list[object], payload["comparison_page_indices"])
        )
        if state.selected.selection.query_json != expected_query_json:
            raise AssertionError("fresh reader 沒有保留完整原價格查詢")
        if state.selected.selection.stock_code != expected_stock_code:
            raise AssertionError("fresh reader 選取股票與原收藏不同")
        if tuple(
            item.stock_code for item in state.bookmark.comparison_selections
        ) != expected_basket_codes:
            raise AssertionError("fresh reader 比較籃股票與原收藏不同")
        if tuple(
            item.page_request.page_index
            for item in state.bookmark.comparison_selections
        ) != expected_basket_pages:
            raise AssertionError("fresh reader 比較籃頁碼與原收藏不同")
        mark(
            "watchlist_fresh_state_verified",
            bookmark_identity_sha256=state.bookmark.bookmark_identity_sha256,
            query_identity_sha256=state.selected.selection.query.query_identity_sha256,
            selected_stock_code=state.selected.selection.stock_code,
        )

        daily = window.recommendation_view.daily_market_research_view
        price_view = daily.technical_price_view
        assert price_view is not None

        def restored_exactly() -> bool:
            query = price_view.current_query
            page = price_view.current_page
            return bool(
                query is not None
                and page is not None
                and not price_view.busy
                and query.query_identity_sha256 == expected_query_identity
                and query.to_json() == expected_query_json
                and page.page_identity_sha256 == expected_page_identity
                and page.request.page_index == expected_page_index
                and _selected_code(price_view) == expected_stock_code
                and tuple(item.stock_code for item in price_view._basket) == expected_basket_codes
                and tuple(item.page_request.page_index for item in price_view._basket)
                == expected_basket_pages
            )

        _wait_for(
            app,
            restored_exactly,
            deadline=deadline,
            stage="Main 套用同次 fresh 收藏狀態",
            cancel_marker=cancel_marker,
        )
        trace_scroll_restore("after_navigation_and_layout")
        if window.left_navigation.current_key() != "recommendation":
            raise AssertionError("重開價格收藏後 Main 未返回研究工作區")
        if window.recommendation_view.result_source_tabs.currentWidget() is not daily:
            raise AssertionError("重開價格收藏後 Main 未顯示每日研究分頁")
        if price_view.current_page is None or price_view.current_query is None:
            raise AssertionError("Main 收藏還原後缺少原查詢頁")
        if price_view.current_page.source_counts.declared_count != 258:
            raise AssertionError("Main 還原的 full-N 母體宣告數不符")
        if price_view.current_page.source_counts.included_count != 257:
            raise AssertionError("Main 還原的 full-N 納入數不符")
        if price_view.current_page.source_counts.excluded_count != 1:
            raise AssertionError("Main 還原的 full-N 排除數不符")
        if price_view.current_page.source_counts.processed_count != 257:
            raise AssertionError("Main 還原的 full-N 已處理數不符")
        if price_view.current_page.source_counts.pending_count != 0:
            raise AssertionError("完整價格收藏重開不應新增 pending 股票")
        if price_view.current_page.price_counts.unknown_count != 1:
            raise AssertionError("完整母體中缺價股票必須保持 unknown")
        if price_view.current_query.source.historical_pit_eligible is not False:
            raise AssertionError("來源不可得時間未知，不得授予歷史 PIT")
        if price_view.current_query.source.availability_status != "unknown":
            raise AssertionError("新程序需明示保存來源的 availability unknown")

        actual_selected = cast(str, _selected_code(price_view))
        if actual_selected != expected_stock_code:
            raise AssertionError("Main 還原後目前列股票不符")
        restored_page = price_view.current_page
        assert restored_page is not None
        if restored_page.page_identity_sha256 != expected_page_identity:
            raise AssertionError("Main 還原後頁面 identity 不符")
        if tuple(item.stock_code for item in price_view._basket) != expected_basket_codes:
            raise AssertionError("Main 還原後比較籃股票不符")
        if tuple(item.page_request.page_index for item in price_view._basket) != expected_basket_pages:
            raise AssertionError("Main 還原後比較籃原頁碼不符")
        expected_scroll = _payload_int(
            payload.get("scroll_position"), field_name="scroll_position"
        )
        scroll_geometry = _scroll_geometry(price_view)
        actual_scroll = cast(int, scroll_geometry["scroll_value"])
        if actual_scroll != expected_scroll:
            raise AssertionError(
                "Main 還原後收藏捲動位置不符："
                f"expected={expected_scroll}; actual={actual_scroll}; "
                f"geometry={scroll_geometry}; restore_trace={phases}"
            )
        _double_click_price_row(app, price_view, expected_stock_code)
        _wait_for(
            app,
            lambda: window.stock_research_workspace.price_research_view is not None
            and window.stock_research_workspace.price_research_view.isVisible()
            and _view_idle(price_view),
            deadline=deadline, stage="fresh Main 原收藏進同源個股研究", cancel_marker=cancel_marker,
        )
        fresh_detail = window.stock_research_workspace.price_research_view
        assert fresh_detail is not None
        assert fresh_detail._origin_selection.to_dict() == state.selected.selection.to_dict()
        assert fresh_detail.price_table.rowCount() == len(fresh_detail._stock.snapshot.rows)
        fresh_detail.return_button.click()
        _wait_for(
            app, restored_exactly, deadline=deadline,
            stage="fresh Main 同源個股返回原收藏頁", cancel_marker=cancel_marker,
        )
        assert window.workspace_stack.currentWidget() is window.recommendation_view
        mark("fresh_embedded_price_stock_and_exact_return", stock_code=expected_stock_code)
        if price_view.current_query.to_json() != expected_query_json:
            raise AssertionError("Main 還原後 query canonical JSON 不符")
        mark(
            "main_restored_query_page_code_basket",
            query_identity_sha256=price_view.current_query.query_identity_sha256,
            page_index=price_view.current_page.request.page_index,
            page_identity_sha256=price_view.current_page.page_identity_sha256,
            selected_stock_code=actual_selected,
            comparison_stock_codes=list(expected_basket_codes),
            comparison_page_indices=list(expected_basket_pages),
            scroll_position=actual_scroll,
            scroll_geometry=scroll_geometry,
            declared_count=price_view.current_page.source_counts.declared_count,
            included_count=price_view.current_page.source_counts.included_count,
            excluded_count=price_view.current_page.source_counts.excluded_count,
            unknown_price_count=price_view.current_page.price_counts.unknown_count,
        )

        reopened = service.get_research_bookmark(expected_bookmark_id)
        if type(reopened) is not DailyMarketTechnicalUniversePriceBookmarkV1:
            raise AssertionError("child Watchlist 保存後原件類型改變")
        if reopened.to_json() != expected_bookmark_json:
            raise AssertionError("child Main fresh reopen 不得改寫 Watchlist 收藏")
        window.close()
        _wait_for(
            app,
            lambda: not window.isVisible()
            and bool(getattr(window, "_shutdown_close_finalizing", False)),
            deadline=deadline,
            stage="child Main 所有原生工作結束後關閉",
            cancel_marker=cancel_marker,
        )
        mark("child_main_shutdown_complete", workers_remaining=0)
        watchlist_after = _process_support._watchlist_inventory(watchlist_root)
        after_primary = _process_support._primary_watchlist_bytes(watchlist_after)
        if after_primary != expected_primary:
            raise AssertionError("child Watchlist 僅讀重開不應改寫收藏 primary bytes")
        source_after = _process_support._tree_inventory(source_root)
        source_after_sha = hashlib.sha256(
            json.dumps(source_after, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if source_after != source_before:
            raise AssertionError("新 PID Main 讀取期間改動了 full-N synthetic source")
        receipt.update(
            {
                "status": "passed",
                "source_inventory_after_sha256": source_after_sha,
                "watchlist_primary_before": [list(item) for item in expected_primary],
                "watchlist_primary_after": [list(item) for item in after_primary],
                "watchlist_bookmark_json_sha256": hashlib.sha256(
                    reopened.to_json().encode("utf-8")
                ).hexdigest(),
                "network_attempts": network_attempts,
            }
        )
        _write_json(receipt_path, receipt)
        return 0
    except BaseException as exc:
        receipt["status"] = "failed"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        receipt["network_attempts"] = network_attempts
        _write_json(receipt_path, receipt)
        raise
    finally:
        if window is not None and window.isVisible():
            window.close()
            if app is not None:
                cleanup_deadline = min(deadline, time.monotonic() + 20.0)
                while window.isVisible() and time.monotonic() < cleanup_deadline:
                    app.processEvents()
                    time.sleep(0.005)


def test_real_main_full257_price_query_bookmark_and_fresh_pid_restore(
    exact_257_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真 MainWindow 走 full-N 價格查詢，並在新 PID exact 重開原收藏。"""

    pytest.importorskip("PySide6")

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from ui_qt.views.daily_market_technical_price_comparison_v1_view import (
        DailyMarketTechnicalPriceComparisonV1View,
    )
    from ui_qt.views.daily_market_technical_price_stock_v1_view import (
        DailyMarketTechnicalPriceStockV1View,
    )
    from ui_qt.views.daily_market_technical_universe_price_view_v1 import (
        DailyMarketTechnicalUniversePriceV1View,
    )

    from app_module.watchlist_service import TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE
    from ui_qt.main import MainWindow

    started = time.monotonic()
    deadline = started + _TOTAL_DEADLINE_SECONDS
    fixture = exact_257_price_store
    source_root = Path(fixture["root"]).resolve(strict=True)
    # 來源 store 故意位於超過 Windows MAX_PATH 的合成根下；只在這裡
    # 比較其 canonical 字面設定，實際存在性與內容由 strict repository reader 驗證。
    store_root = Path(fixture["store_root"])
    assert not Path(fixture["database"]).exists()
    source_before = _process_support._tree_inventory(source_root)
    source_before_sha = _source_digest(source_root)
    assert source_before

    repo_root = Path(__file__).resolve().parents[1]
    qa_root = repo_root / _QA_ROOT
    qa_root.mkdir(parents=True, exist_ok=True)
    attempt_root = qa_root / f"attempt_{uuid4().hex}"
    attempt_root.mkdir(parents=False, exist_ok=False)
    helper_path = attempt_root / "child_main_runner.py"
    input_path = attempt_root / "child_input.json"
    child_receipt_path = attempt_root / "child_receipt.json"
    child_trace_path = attempt_root / "child_trace.jsonl"
    child_stdout_path = attempt_root / "child_stdout.log"
    child_stderr_path = attempt_root / "child_stderr.log"
    cancel_marker_path = attempt_root / "child_cancel.requested"
    parent_trace_path = attempt_root / "parent_trace.jsonl"
    parent_receipt_path = attempt_root / "parent_receipt.json"

    runtime_root = attempt_root / "parent-runtime"
    env, unset_env_keys = _process_support._isolated_environment(
        root=runtime_root,
        bundle_root=store_root,
    )
    env["TECHNICAL_UNIVERSE_READ_ROOT"] = str(store_root)
    env["TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT"] = str(store_root)
    expected_env = dict(env)
    child_env = _process_support._minimal_child_environment(expected_env=env)
    unset_child_keys = sorted(
        (set(_process_support._ISOLATED_ENVIRONMENT_KEYS) | set(unset_env_keys))
        - set(expected_env)
    )

    for name in _process_support._ISOLATED_ENVIRONMENT_KEYS:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    for name in unset_env_keys:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    temp_root = Path(env["TEMP"])
    temp_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("tempfile.tempdir", str(temp_root))
    network_attempts = _process_support._install_network_deny(monkeypatch)

    app = cast(QApplication, QApplication.instance() or QApplication([]))
    window: Any | None = None
    process: subprocess.Popen[str] | None = None
    job_handle: int | None = None
    child_output_collected = False
    child_stdout = ""
    child_stderr = ""
    child_return_code: int | None = None
    bookmark: DailyMarketTechnicalUniversePriceBookmarkV1 | None = None
    phases: list[dict[str, object]] = []
    catalog_release = threading.Event()

    def mark(name: str, **details: object) -> None:
        entry = {
            "phase": name,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            **details,
        }
        phases.append(entry)
        _append_phase(parent_trace_path, started, name, **details)
        _write_json(
            parent_receipt_path,
            {
                "status": "in_progress",
                "attempt": attempt_root.name,
                "parent_pid": os.getpid(),
                "source_inventory_sha256": source_before_sha,
                "phases": phases,
                "network_attempts": network_attempts,
            },
        )

    mark("source_fixture_pinned", source_inventory_sha256=source_before_sha)
    try:
        window = MainWindow()
        output_root = Path(env["OUTPUT_ROOT"]).resolve()
        assert Path(window.config.output_root).resolve() == output_root
        configured_store = getattr(window.config, "technical_universe_read_root", None)
        assert configured_store is not None
        assert _path_key(configured_store) == _path_key(store_root)
        service = window.watchlist_service
        assert service is not None
        assert Path(service.watchlist_dir).resolve() == (output_root / "watchlist").resolve()
        window.resize(1440, 980)
        window.show()
        app.processEvents()
        mark("parent_main_constructed", main_type=type(window).__name__)

        recommendation_nav = window.left_navigation.button_for_key("recommendation")
        assert recommendation_nav is not None and recommendation_nav.isVisible()
        QTest.mouseClick(recommendation_nav, Qt.MouseButton.LeftButton)
        recommendation = window.recommendation_view
        daily = recommendation.daily_market_research_view
        tabs = recommendation.result_source_tabs
        daily_index = tabs.indexOf(daily)
        assert daily_index >= 0
        QTest.mouseClick(
            tabs.tabBar(),
            Qt.MouseButton.LeftButton,
            pos=tabs.tabBar().tabRect(daily_index).center(),
        )
        assert tabs.currentWidget() is daily
        view = daily.technical_price_view
        assert isinstance(view, DailyMarketTechnicalUniversePriceV1View)
        assert Path(view.store_output_root).resolve() == store_root
        mark("main_price_research_opened", source_root_sha256=source_before_sha)

        prepared_events: list[object] = []
        bookmark_saved_events: list[object] = []
        detail_events: list[tuple[object, object]] = []
        comparison_events: list[object] = []
        view.bookmarkPrepared.connect(prepared_events.append)
        view.stockSelected.connect(lambda stock, selection: detail_events.append((stock, selection)))
        view.comparisonReady.connect(comparison_events.append)
        daily.bookmarkSaved.connect(bookmark_saved_events.append)
        daily.bookmark_confirmation_callback = lambda _value: True

        view.refresh_sources()
        _wait_for(
            app,
            lambda: _view_idle(view) and view.sources.count() > 0,
            deadline=deadline,
            stage="Main F07 保存版本盤點",
        )
        source_index = _complete_source_index(view)
        assert source_index >= 0, view.status.text()
        view.sources.setCurrentIndex(source_index)
        entry = view.selected_source
        assert entry is not None and entry.is_selectable
        mark(
            "complete_source_selected",
            generation_identity_sha256=entry.generation_identity_sha256,
            plan_identity_sha256=entry.plan_identity_sha256,
            receipt_identity_sha256=entry.receipt_identity_sha256,
        )

        page_size_index = view.page_size.findData(50)
        assert page_size_index >= 0
        view.page_size.setCurrentIndex(page_size_index)
        view.descending.setChecked(False)
        view.unknown_policy.setCurrentIndex(view.unknown_policy.findData("include"))
        view.load_selected_source()
        _wait_for(
            app,
            lambda: _view_idle(view) and view.current_result is not None and view.current_page is not None,
            deadline=deadline,
            stage="Main full-N 價格查詢完成",
        )
        _wait_for(
            app,
            lambda: (
                not view.controls_group.isVisible()
                and view.result_guidance.isVisible()
                and recommendation.result_scroll.viewport().rect().contains(
                    view.result_guidance.mapTo(
                        recommendation.result_scroll.viewport(),
                        view.result_guidance.rect().topLeft(),
                    )
                )
            ),
            deadline=deadline,
            stage="Main 載入後結果入口進入可視範圍",
        )
        assert not view.summary.isVisible()
        result = view.current_result
        page = view.current_page
        query = view.current_query
        assert result is not None and page is not None and query is not None
        assert page.full_population_complete is True
        assert page.source_counts.declared_count == 258
        assert page.source_counts.included_count == 257
        assert page.source_counts.excluded_count == 1
        assert page.source_counts.processed_count == 257
        assert page.source_counts.pending_count == 0
        assert page.source_counts.missing_data_count == 1
        assert page.price_counts.base_matching_count == 257
        assert page.price_counts.pass_count == 256
        assert page.price_counts.unknown_count == 1
        assert page.page_count == 6
        assert page.request.page_size == 50
        assert page.rows[0].technical_row.stock_code == "S0256"
        assert page.rows[0].price_fact.close_price is not None
        assert page.rows[0].price_fact.close_price.as_tuple().exponent == 0
        assert page.rows[0].price_fact.close_price == 2
        assert page.rows[-1].price_state == "pass"
        assert query.source.availability_status == "unknown"
        assert query.source.historical_pit_eligible is False
        assert query.source.full_market_claim is False
        original_query_json = query.to_json()
        first_page_identity = page.page_identity_sha256
        first_code = page.rows[0].technical_row.stock_code
        _click_price_row(app, view, first_code)
        QTest.mouseClick(view.add_comparison_button, Qt.MouseButton.LeftButton)
        assert tuple(item.stock_code for item in view._basket) == (first_code,)
        assert view._basket[0].page_request.page_index == 0
        mark(
            "global_price_sort_page_0",
            query_identity_sha256=query.query_identity_sha256,
            page_identity_sha256=first_page_identity,
            first_stock_code=first_code,
            first_close_price=str(page.rows[0].price_fact.close_price),
            pass_count=page.price_counts.pass_count,
            unknown_count=page.price_counts.unknown_count,
        )

        for target_page in range(1, 6):
            assert view.next_page_button.isEnabled()
            QTest.mouseClick(view.next_page_button, Qt.MouseButton.LeftButton)
            _wait_for(
                app,
                lambda expected=target_page: (
                    _view_idle(view)
                    and view.current_page is not None
                    and view.current_page.request.page_index == expected
                ),
                deadline=deadline,
                stage=f"Main 全域價格排序第 {target_page + 1} 頁",
            )
        last_page = view.current_page
        assert last_page is not None and last_page.request.page_index == 5
        second_code = last_page.rows[0].technical_row.stock_code
        assert second_code == "S0250"
        _click_price_row(app, view, second_code)
        QTest.mouseClick(view.add_comparison_button, Qt.MouseButton.LeftButton)
        assert tuple(item.stock_code for item in view._basket) == (first_code, second_code)
        basket_pages = tuple(item.page_request.page_index for item in view._basket)
        assert basket_pages == (0, 5)
        mark(
            "global_price_sort_page_5_and_comparison_basket",
            second_page_identity_sha256=last_page.page_identity_sha256,
            second_stock_code=second_code,
            basket_pages=list(basket_pages),
        )

        _double_click_price_row(app, view, second_code)
        _wait_for(
            app,
            lambda: window.stock_research_workspace.price_research_view is not None
            and window.stock_research_workspace.price_research_view.isVisible()
            and _view_idle(view),
            deadline=deadline,
            stage="Main 真正雙擊 F07 股票並開啟原股詳情",
        )
        assert len(detail_events) == 1
        detail_stock, detail_origin = detail_events[0]
        assert isinstance(detail_stock, DailyMarketTechnicalUniversePriceStockV1)
        assert isinstance(detail_origin, DailyMarketTechnicalUniversePriceSelectionV1)
        assert detail_stock.stock_code == detail_origin.stock_code == second_code
        assert detail_origin.query.to_json() == original_query_json
        assert detail_origin.page_identity_sha256 == last_page.page_identity_sha256
        details = window.stock_research_workspace.price_research_view
        assert details is not None and details.isVisible()
        assert isinstance(details, DailyMarketTechnicalPriceStockV1View)
        assert window.workspace_stack.currentWidget() is window.stock_research_workspace
        assert not details.isWindow() and details.window() is window
        assert daily._price_stock_dialog is None
        assert details.price_table.rowCount() == len(detail_stock.snapshot.rows)
        assert tuple(point.close_price for point in details.price_chart._points) == tuple(
            row.close_price if row.ohlc_valid else None
            for row in detail_stock.snapshot.rows if row.feature_date is not None
        )
        assert second_code in details.summary.text()
        assert details.return_button.isEnabled()
        QTest.mouseClick(details.return_button, Qt.MouseButton.LeftButton)
        _wait_for(
            app,
            lambda: _view_idle(view)
            and window.workspace_stack.currentWidget() is window.recommendation_view
            and view.current_page is not None
            and view.current_page.page_identity_sha256 == last_page.page_identity_sha256,
            deadline=deadline,
            stage="F07 個股詳情返回原 query/page",
        )
        assert view.current_query is not None and view.current_query.to_json() == original_query_json
        assert _selected_code(view) == second_code
        assert tuple(item.stock_code for item in view._basket) == (first_code, second_code)
        returned_page = view.current_page
        assert returned_page is not None
        mark(
            "stock_detail_returned_to_exact_origin",
            stock_code=second_code,
            query_identity_sha256=view.current_query.query_identity_sha256,
            page_identity_sha256=returned_page.page_identity_sha256,
            basket_stock_codes=[first_code, second_code],
        )

        QTest.mouseClick(view.run_comparison_button, Qt.MouseButton.LeftButton)
        _wait_for(
            app,
            lambda: daily._price_comparison_dialog is not None
            and daily._price_comparison_dialog.isVisible()
            and _view_idle(view),
            deadline=deadline,
            stage="Main 重驗並比較兩筆不同頁選取",
        )
        assert len(comparison_events) == 1
        assert daily._price_comparison_dialog.findChild(
            DailyMarketTechnicalPriceComparisonV1View
        ) is not None
        comparison_value = comparison_events[0]
        assert isinstance(comparison_value, DailyMarketTechnicalUniversePriceComparisonV1)
        comparison_codes = tuple(
            column.selection.stock_code for column in comparison_value.columns
        )
        assert comparison_codes == (first_code, second_code)
        daily._price_comparison_dialog.close()
        _wait_for(
            app,
            lambda: daily._price_comparison_dialog is None,
            deadline=deadline,
            stage="Main 關閉比較並保留原頁",
        )
        assert view.current_page is not None
        assert view.current_page.page_identity_sha256 == last_page.page_identity_sha256
        mark(
            "two_stock_comparison_verified",
            stock_codes=list(comparison_codes),
            page_indices=list(basket_pages),
        )

        assert _selected_code(view) == second_code
        scroll_value = min(3, view.table.verticalScrollBar().maximum())
        view.table.verticalScrollBar().setValue(scroll_value)
        daily_service = getattr(daily, "watchlist_service", None)
        add_bookmark = getattr(service, "add_research_bookmark", None)
        if daily_service is not service or not callable(add_bookmark):
            raise AssertionError(
                "Main 收藏服務接線不符："
                f"same_instance={daily_service is service}; "
                f"main_service={type(service).__name__}; "
                f"daily_service={type(daily_service).__name__}; "
                f"add_callable={callable(add_bookmark)}"
            )
        mark(
            "real_watchlist_service_bound_before_bookmark",
            same_instance=True,
            service_type=type(service).__name__,
            add_callable=True,
            confirmation_callback_callable=callable(
                daily.bookmark_confirmation_callback
            ),
        )
        mark(
            "price_bookmark_preparation_started",
            selected_stock_code=_selected_code(view),
            prepared_signal_count=len(prepared_events),
            saved_signal_count=len(bookmark_saved_events),
            workers_remaining=view.workers_remaining,
        )
        view.prepare_bookmark()
        _wait_for(
            app,
            lambda: _view_idle(view),
            deadline=deadline,
            stage="Main 價格收藏準備 worker 原生終態",
        )
        if len(prepared_events) != 1 or len(bookmark_saved_events) != 1:
            raise AssertionError(
                "Main 價格收藏未完成同步保存："
                f"prepared={len(prepared_events)} saved={len(bookmark_saved_events)}; "
                f"view_status={view.status.text()!r}; "
                f"worker_kind={view._worker_kind!r}; busy={view.busy}; "
                f"workers_remaining={view.workers_remaining}; "
                f"selected={_selected_code(view)!r}; "
                f"query={view.current_query.query_identity_sha256 if view.current_query else None!r}; "
                f"page={view.current_page.page_identity_sha256 if view.current_page else None!r}; "
                f"bookmark_enabled={view.bookmark_button.isEnabled()}; "
                f"same_daily_service={daily_service is service}; "
                f"add_callable={callable(add_bookmark)}"
            )
        raw_bookmark = prepared_events[0]
        if type(raw_bookmark) is not DailyMarketTechnicalUniversePriceBookmarkV1:
            raise AssertionError("Main 價格收藏不是 typed v1 bookmark")
        bookmark = cast(DailyMarketTechnicalUniversePriceBookmarkV1, raw_bookmark)
        assert bookmark.bookmark_id
        assert bookmark.selected.stock_code == second_code
        assert bookmark.selected.query_json == original_query_json
        assert bookmark.selected.page_request.page_index == 5
        assert tuple(item.stock_code for item in bookmark.comparison_selections) == (
            first_code,
            second_code,
        )
        assert tuple(
            item.page_request.page_index for item in bookmark.comparison_selections
        ) == (0, 5)
        assert bookmark.scroll_position == scroll_value
        stored = service.get_research_bookmark(bookmark.bookmark_id)
        assert type(stored) is DailyMarketTechnicalUniversePriceBookmarkV1
        assert stored.to_json() == bookmark.to_json()
        assert getattr(bookmark_saved_events[0], "status", None) in {
            "added",
            "already_present",
        }
        mark(
            "price_bookmark_persisted",
            bookmark_id=bookmark.bookmark_id,
            bookmark_identity_sha256=bookmark.bookmark_identity_sha256,
            query_identity_sha256=bookmark.selected.query.query_identity_sha256,
            page_identity_sha256=bookmark.selected.page_identity_sha256,
            selected_stock_code=bookmark.stock_code,
            comparison_stock_codes=[first_code, second_code],
            comparison_page_indices=[0, 5],
            scroll_position=scroll_value,
        )

        source_after_parent = _process_support._tree_inventory(source_root)
        assert source_after_parent == source_before
        watchlist_inventory = _process_support._watchlist_inventory(
            Path(service.watchlist_dir)
        )
        primary_before_child = _process_support._primary_watchlist_bytes(watchlist_inventory)
        assert primary_before_child
        watchlist_records = service.get_stocks()
        assert len(watchlist_records) == 1
        assert watchlist_records[0]["source"] == TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE
        assert watchlist_records[0]["source_id"] == bookmark.bookmark_id

        # 確認 busy 重入只保留一個原生 worker；取消清除排隊工作，關閉等待 native 終態。
        import ui_qt.views.daily_market_technical_universe_price_view_v1 as price_view_module

        catalog_entered = threading.Event()
        catalog_release = threading.Event()
        original_catalog_reader = price_view_module._read_catalog_page

        def gated_catalog_reader(
            root: Path,
            cursor: str | None,
            cancel_callback: Any = None,
        ) -> object:
            catalog_entered.set()
            while not catalog_release.wait(0.01):
                price_view_module._check_cancel(cancel_callback)
            price_view_module._check_cancel(cancel_callback)
            return original_catalog_reader(root, cursor, cancel_callback)

        monkeypatch.setattr(price_view_module, "_read_catalog_page", gated_catalog_reader)
        view.refresh_sources()
        _wait_for(
            app,
            lambda: catalog_entered.is_set() and view._worker is not None,
            deadline=deadline,
            stage="啟動可合作取消的 busy 操作",
        )
        active_worker = view._worker
        assert active_worker is not None
        view.refresh_sources()
        assert view._worker is active_worker
        assert view._pending is not None
        view.cancel()
        assert view._pending is None
        assert view._worker is active_worker
        shutdown_while_active = view.begin_shutdown()
        assert shutdown_while_active is False
        catalog_release.set()
        _wait_for(
            app,
            lambda: view._worker is None and view.workers_remaining == 0,
            deadline=deadline,
            stage="取消工作原生 thread 終態",
        )
        assert view.begin_shutdown() is True
        assert view.current_query is not None
        assert view.current_query.to_json() == original_query_json
        assert view.current_page is not None
        assert view.current_page.page_identity_sha256 == last_page.page_identity_sha256
        mark(
            "busy_cancel_and_shutdown_gate_verified",
            queued_work_cleared=True,
            shutdown_initially_blocked=True,
            shutdown_native_terminal=True,
        )

        window.close()
        _wait_for(
            app,
            lambda: not window.isVisible()
            and bool(getattr(window, "_shutdown_close_finalizing", False)),
            deadline=deadline,
            stage="parent MainWindow 關閉與 worker 終態",
        )
        mark("parent_main_shutdown_complete", workers_remaining=0)

        bookmark_json = bookmark.to_json()
        source_sha_after_parent = _source_digest(source_root)
        assert source_sha_after_parent == source_before_sha
        helper_path.write_text(_helper_source(), encoding="utf-8")
        payload: dict[str, object] = {
            "repo_root": str(repo_root),
            "attempt_root": str(attempt_root),
            "source_root": str(source_root),
            "source_inventory_sha256": source_before_sha,
            "store_root": str(store_root),
            "receipt_path": str(child_receipt_path),
            "trace_path": str(child_trace_path),
            "cancel_marker_path": str(cancel_marker_path),
            "bookmark_id": bookmark.bookmark_id,
            "bookmark_identity_sha256": bookmark.bookmark_identity_sha256,
            "bookmark_json": bookmark_json,
            "query_json": bookmark.selected.query_json,
            "query_identity_sha256": bookmark.selected.query.query_identity_sha256,
            "page_identity_sha256": bookmark.selected.page_identity_sha256,
            "selected_stock_code": bookmark.stock_code,
            "selected_page_index": bookmark.selected.page_request.page_index,
            "comparison_stock_codes": [first_code, second_code],
            "comparison_page_indices": [0, 5],
            "scroll_position": bookmark.scroll_position,
            "watchlist_primary_bytes": [list(item) for item in primary_before_child],
            "expected_environment": expected_env,
            "unset_environment_keys": unset_child_keys,
            "remaining_total_seconds": _process_support._remaining_seconds(deadline),
        }
        _write_json(input_path, payload)
        mark("parent_closed_child_starting", source_inventory_sha256=source_sha_after_parent)

        command = [sys.executable, str(helper_path), str(repo_root), str(input_path)]
        child_deadline = min(time.monotonic() + _CHILD_DEADLINE_SECONDS, deadline)
        process, job_handle = _process_support._spawn_child_process(
            command,
            cwd=str(repo_root),
            env=child_env,
        )
        assert process.pid != os.getpid()
        try:
            timeout = child_deadline - time.monotonic()
            if timeout <= 0:
                raise subprocess.TimeoutExpired(command, timeout=0)
            child_stdout, child_stderr = process.communicate(timeout=timeout)
            child_output_collected = True
        except subprocess.TimeoutExpired as timeout_error:
            child_stdout, child_stderr = _process_support._stop_child_bounded(
                process,
                job_handle=job_handle,
                cancel_marker=cancel_marker_path,
                stdout_path=child_stdout_path,
                stderr_path=child_stderr_path,
            )
            child_output_collected = True
            child_return_code = process.returncode
            raise AssertionError(
                "F07 child MainWindow 超過既有 240 秒／共同 300 秒期限；已合作取消並有限收束"
            ) from timeout_error
        child_return_code = process.returncode
        child_stdout_path.write_text(child_stdout or "", encoding="utf-8")
        child_stderr_path.write_text(child_stderr or "", encoding="utf-8")
        assert child_return_code == 0, (
            f"F07 新 PID MainWindow journey 失敗，exit={child_return_code}; "
            f"stdout={child_stdout_path}; stderr={child_stderr_path}; receipt={child_receipt_path}"
        )
        assert child_receipt_path.is_file()
        child_receipt = json.loads(child_receipt_path.read_text(encoding="utf-8"))
        assert child_receipt["status"] == "passed"
        pid_relation = _process_support._validate_child_pid_chain(
            reporter_pid=child_receipt.get("pid"),
            reporter_parent_pid=child_receipt.get("parent_pid"),
            reporter_executable=child_receipt.get("executable"),
            launcher_pid=process.pid,
            parent_pid=os.getpid(),
            expected_executables=[
                sys.executable,
                getattr(sys, "_base_executable", sys.executable),
            ],
        )
        assert child_receipt["source_inventory_before_sha256"] == source_before_sha
        assert child_receipt["source_inventory_after_sha256"] == source_before_sha
        assert child_receipt["watchlist_bookmark_json_sha256"] == hashlib.sha256(
            bookmark_json.encode("utf-8")
        ).hexdigest()
        assert not network_attempts
        assert child_receipt["network_attempts"] == []
        source_after = _process_support._tree_inventory(source_root)
        assert source_after == source_before
        watchlist_after = _process_support._watchlist_inventory(Path(service.watchlist_dir))
        assert _process_support._primary_watchlist_bytes(watchlist_after) == primary_before_child
        if time.monotonic() > deadline:
            raise AssertionError("F07 full Main／新 PID 旅程超過既有 300 秒 deadline")
        mark(
            "fresh_pid_watchlist_main_restore_passed",
            child_pid=child_receipt["pid"],
            process_relation=pid_relation,
            source_inventory_sha256=source_before_sha,
            child_bookmark_identity_sha256=bookmark.bookmark_identity_sha256,
        )
        _write_json(
            parent_receipt_path,
            {
                "status": "passed",
                "attempt": attempt_root.name,
                "parent_pid": os.getpid(),
                "child_pid": child_receipt["pid"],
                "pid_relation": pid_relation,
                "source_inventory_sha256": source_before_sha,
                "bookmark_identity_sha256": bookmark.bookmark_identity_sha256,
                "query_identity_sha256": bookmark.selected.query.query_identity_sha256,
                "selected_stock_code": bookmark.stock_code,
                "selected_page_index": bookmark.selected.page_request.page_index,
                "comparison_stock_codes": [first_code, second_code],
                "comparison_page_indices": [0, 5],
                "phases": phases,
                "child_receipt_sha256": _phase_digest(child_receipt_path),
                "child_trace_sha256": _phase_digest(child_trace_path),
                "source_unchanged": True,
                "network_attempts": network_attempts,
            },
        )
    except BaseException as exc:
        _write_json(
            parent_receipt_path,
            {
                "status": "failed",
                "attempt": attempt_root.name,
                "parent_pid": os.getpid(),
                "error": f"{type(exc).__name__}: {exc}",
                "child_return_code": child_return_code,
                "phases": phases,
                "source_inventory_before_sha256": source_before_sha,
                "source_inventory_after_sha256": _source_digest(source_root),
                "child_stdout_path": str(child_stdout_path) if child_stdout_path.exists() else None,
                "child_stderr_path": str(child_stderr_path) if child_stderr_path.exists() else None,
                "child_receipt_path": str(child_receipt_path) if child_receipt_path.exists() else None,
                "network_attempts": network_attempts,
            },
        )
        raise
    finally:
        catalog_release.set()
        try:
            if process is not None and (process.poll() is None or not child_output_collected):
                _process_support._stop_child_bounded(
                    process,
                    job_handle=job_handle,
                    cancel_marker=cancel_marker_path,
                    stdout_path=child_stdout_path,
                    stderr_path=child_stderr_path,
                )
                child_output_collected = True
                child_return_code = process.returncode
        finally:
            _process_support._close_process_job(job_handle)
            job_handle = None
        if window is not None and window.isVisible():
            window.close()
            cleanup_deadline = min(deadline, time.monotonic() + 20.0)
            while window.isVisible() and time.monotonic() < cleanup_deadline:
                app.processEvents()
                time.sleep(0.005)
        if window is not None and window.isVisible():
            raise AssertionError("parent MainWindow 關閉未完成；保留來源與 QA 證據")
