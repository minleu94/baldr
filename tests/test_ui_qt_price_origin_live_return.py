"""F07 原價格查詢返回只重讀目前已發行查詢所指的頁面。"""

from __future__ import annotations

import json
from dataclasses import fields
from decimal import Decimal
from pathlib import Path
from threading import Event
import time
from typing import Any, cast

import pytest
from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceSelectionV1,
)
from app_module.personal_data_paths import to_internal_io_path
from tests.test_daily_market_technical_universe_price_query_v1 import (
    _open_session,
    exact_price_store,
)
from ui_qt.views.daily_market_technical_universe_price_view_v1 import (
    DailyMarketTechnicalUniversePriceV1View,
)
import ui_qt.views.daily_market_technical_universe_price_view_v1 as price_view_module


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return cast(QApplication, instance)


def _wait(
    app: QApplication,
    predicate: Any,
    *,
    timeout_seconds: float = 10.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("F07 原查詢返回背景工作逾時")
        time.sleep(0.01)
    app.processEvents()


def _issued_state_and_selection(
    store: dict[str, Any],
    *,
    minimum: Decimal | None = None,
    stock_code: str = "S0001",
) -> tuple[
    price_view_module._PriceViewState,
    DailyMarketTechnicalUniversePriceSelectionV1,
]:
    session = _open_session(store)
    query = session.create_query(
        min_close_price=minimum,
        unknown_price_policy="include",
    )
    result = session.execute(query)
    request = result.create_page_request(0, page_size=4)
    page = result.read_page(request)
    state = price_view_module._PriceViewState(session, query, result, request, page)
    selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(
        query,
        page,
        stock_code,
    )
    return state, selection


def _view_with_state(
    app: QApplication,
    store: dict[str, Any],
    state: price_view_module._PriceViewState,
) -> DailyMarketTechnicalUniversePriceV1View:
    view = DailyMarketTechnicalUniversePriceV1View(store["store_root"])
    view.resize(800, 600)
    view.show()
    app.processEvents()
    assert view._apply_state(state)
    return view


def test_same_query_return_reads_a_new_issued_page_without_full_reopen(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, selection = _issued_state_and_selection(exact_price_store)
    view = _view_with_state(app, exact_price_store, state)
    old_page = view.current_page
    opener_calls: list[object] = []

    def forbidden_full_reopen(*args: object, **kwargs: object) -> object:
        opener_calls.append((args, kwargs))
        raise AssertionError("同查詢返回不可重新走 full opener")

    monkeypatch.setattr(
        price_view_module,
        "open_daily_market_technical_universe_price_session_for_query_v1",
        forbidden_full_reopen,
    )
    try:
        assert view.restore_origin(selection)
        _wait(app, lambda: not view.busy)

        assert opener_calls == []
        assert view._state is not state
        assert view.current_result is state.result
        assert view.current_page is not old_page
        assert view.current_page is not None
        assert old_page is not None
        assert view.current_page.to_dict() == old_page.to_dict()
        assert view.current_page.page_identity_sha256 == selection.page_identity_sha256
        assert view.select_stock_code(selection.stock_code)
        row = view._selected_row()
        assert row is not None
        assert row.technical_row.stock_code == selection.stock_code
    finally:
        assert view.begin_shutdown()
        view.close()


def test_restore_origin_without_live_state_uses_full_restore_route(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, selection = _issued_state_and_selection(exact_price_store)
    view = DailyMarketTechnicalUniversePriceV1View(exact_price_store["store_root"])
    calls: list[DailyMarketTechnicalUniversePriceSelectionV1] = []

    def recorded_full_restore(
        requested: DailyMarketTechnicalUniversePriceSelectionV1,
        _cancel_callback: object = None,
    ) -> price_view_module._PriceViewState:
        calls.append(requested)
        return state

    monkeypatch.setattr(price_view_module, "_restore_selection", recorded_full_restore)
    try:
        assert view.current_page is None
        assert view.restore_origin(selection)
        _wait(app, lambda: not view.busy)
        assert calls == [selection]
        assert view.current_query == state.query
        assert view.current_page is state.page
    finally:
        assert view.begin_shutdown()
        view.close()


def test_restore_origin_for_another_query_uses_full_restore_route(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_state, _loaded_selection = _issued_state_and_selection(exact_price_store)
    other_state, other_selection = _issued_state_and_selection(
        exact_price_store,
        minimum=Decimal("150"),
        stock_code="S0002",
    )
    view = _view_with_state(app, exact_price_store, loaded_state)
    calls: list[DailyMarketTechnicalUniversePriceSelectionV1] = []

    def recorded_full_restore(
        requested: DailyMarketTechnicalUniversePriceSelectionV1,
        _cancel_callback: object = None,
    ) -> price_view_module._PriceViewState:
        calls.append(requested)
        return other_state

    monkeypatch.setattr(price_view_module, "_restore_selection", recorded_full_restore)
    try:
        assert other_selection.query_json != loaded_state.query.to_json()
        assert view.restore_origin(other_selection)
        _wait(app, lambda: not view.busy)
        assert calls == [other_selection]
        assert view.current_query == other_state.query
        assert view.current_page is other_state.page
    finally:
        assert view.begin_shutdown()
        view.close()


def test_restore_origin_rejects_a_mismatched_selection_pin_and_keeps_state(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, selection = _issued_state_and_selection(exact_price_store)
    view = _view_with_state(app, exact_price_store, state)
    original_page = view.current_page
    opener_calls: list[object] = []
    forged = object.__new__(type(selection))
    for field in fields(selection):
        object.__setattr__(forged, field.name, getattr(selection, field.name))
    object.__setattr__(forged, "page_identity_sha256", "0" * 64)

    def forbidden_full_reopen(*args: object, **kwargs: object) -> object:
        opener_calls.append((args, kwargs))
        raise AssertionError("同查詢 selection pin 錯誤不可退回舊頁或 full opener")

    monkeypatch.setattr(
        price_view_module,
        "open_daily_market_technical_universe_price_session_for_query_v1",
        forbidden_full_reopen,
    )
    try:
        assert view.restore_origin(cast(DailyMarketTechnicalUniversePriceSelectionV1, forged))
        _wait(app, lambda: not view.busy)
        assert opener_calls == []
        assert view._state is state
        assert view.current_page is original_page
        assert "technical_universe_price_selection_identity_mismatch" in view.status.text()
    finally:
        assert view.begin_shutdown()
        view.close()


def test_restore_origin_rejects_selected_artifact_byte_tamper_and_keeps_state(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, selection = _issued_state_and_selection(exact_price_store)
    view = _view_with_state(app, exact_price_store, state)
    original_state = view._state
    original_page = view.current_page
    opener_calls: list[object] = []
    p01_session = state.session._p01_session
    selected_candidate = next(
        item for item in p01_session._candidates
        if item.stock_code == selection.stock_code
    )
    reference = p01_session._artifact_references[selected_candidate.artifact_index]
    manifest_path = Path(to_internal_io_path(reference.manifest_path))
    manifest = json.loads(manifest_path.read_bytes())
    artifact = next(
        item for item in manifest["artifact_refs"]
        if item["stock_code"] == selection.stock_code
    )
    artifact_path = Path(
        to_internal_io_path(reference.manifest_path.parent / artifact["relative_path"])
    )
    original_bytes = artifact_path.read_bytes()
    tampered_bytes = original_bytes[:-1] + bytes((original_bytes[-1] ^ 1,))

    def forbidden_full_reopen(*args: object, **kwargs: object) -> object:
        opener_calls.append((args, kwargs))
        raise AssertionError("來源頁核驗錯誤不可退回 full opener")

    monkeypatch.setattr(
        price_view_module,
        "open_daily_market_technical_universe_price_session_for_query_v1",
        forbidden_full_reopen,
    )
    try:
        artifact_path.write_bytes(tampered_bytes)
        assert view.restore_origin(selection)
        _wait(app, lambda: not view.busy)
        assert opener_calls == []
        assert view._state is original_state
        assert view.current_page is original_page
        assert "原已核驗結果保留" in view.status.text()
        assert "artifact_sha_mismatch" in view.status.text()
    finally:
        if view._worker is not None:
            view.cancel()
            _wait(app, lambda: not view.busy)
        artifact_path.write_bytes(original_bytes)
        assert view.begin_shutdown()
        view.close()


def test_restore_origin_cancel_never_applies_the_new_page(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, selection = _issued_state_and_selection(exact_price_store)
    view = _view_with_state(app, exact_price_store, state)
    original_page = view.current_page
    started = Event()
    release = Event()
    result_type = type(state.result)
    original_read_page = result_type.read_page

    def held_page_read(
        result: Any,
        request: Any,
        *,
        cancel_callback: Any = None,
    ) -> Any:
        if result is state.result:
            started.set()
            if not release.wait(5.0):
                raise AssertionError("測試未釋放原查詢頁讀取")
        return original_read_page(
            result,
            request,
            cancel_callback=cancel_callback,
        )

    monkeypatch.setattr(result_type, "read_page", held_page_read)
    try:
        assert view.restore_origin(selection)
        assert started.wait(5.0)
        assert view.busy
        view.cancel()
        release.set()
        _wait(app, lambda: not view.busy)
        assert view._state is state
        assert view.current_page is original_page
        assert view._pending is None
    finally:
        release.set()
        if view._worker is not None:
            view.cancel()
            _wait(app, lambda: not view.busy)
        assert view.begin_shutdown()
        view.close()
