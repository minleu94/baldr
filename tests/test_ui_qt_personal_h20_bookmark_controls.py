"""H20 觀察清單收藏控制項；來源與 COW 均為隔離合成 fixture。"""

from __future__ import annotations

from pathlib import Path
import time
from dataclasses import replace
from types import SimpleNamespace
import threading
from typing import Any, cast

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkRestoreToken
from app_module.recommendation.personal_h20_research_bookmark import (
    PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE,
    PersonalH20ResearchBookmark,
    PersonalH20ResearchBookmarkState,
    create_personal_h20_research_bookmark,
)
from app_module.watchlist_service import WatchlistService
from tests.test_personal_h20_research_bookmark import _fixture
from tests.test_personal_h20_research_cohort import public_reader
from ui_qt.widgets.personal_h20_bookmark_controls import PersonalH20BookmarkControls


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    return instance


def _wait_for(
    app: QApplication,
    predicate: Any,
    *,
    timeout_seconds: float = 30.0,
    message: str = "H20 收藏背景工作逾時",
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            app.processEvents()
            return
        time.sleep(0.005)
    app.processEvents()
    assert predicate(), message


def _make_watchlist(
    tmp_path: Path,
    *,
    include_invalid: bool = True,
    include_same_stock_manual: bool = True,
    include_second_h20: bool = False,
) -> tuple[WatchlistService, dict[str, Any], object | None]:
    source_root = tmp_path / "synthetic-source"
    source_root.mkdir(parents=True)
    fixture = _fixture(source_root)
    output_root = tmp_path / "watchlist-output"
    config = SimpleNamespace(
        output_root=output_root,
        resolve_output_path=lambda relative: output_root / relative,
    )
    service = WatchlistService(config)
    if include_same_stock_manual:
        assert service.add_stocks(
            [{"stock_code": fixture["bookmark"].stock_code, "stock_name": "同股手動列"}],
            source="manual",
        ) == 1
    assert service.add_research_bookmark(fixture["bookmark"]).status == "added"

    second_bookmark = None
    if include_second_h20:
        second_bookmark = create_personal_h20_research_bookmark(
            fixture["reference"],
            fixture["cohort"],
            fixture["selection"],
            sort_descending=True,
            scroll_position=29,
        )
        assert second_bookmark.bookmark_id != fixture["bookmark"].bookmark_id
        assert service.add_research_bookmark(second_bookmark).status == "added"

    if include_invalid:
        assert service.add_stocks(
            [{"stock_code": "7777", "stock_name": "缺 payload 的 H20 列"}],
            source=PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE,
        ) == 1

    if include_invalid:
        # JSON loader 可讀取明確壞列供 UI 顯示；COW migration 本身會拒絕
        # 損毀收藏，故此案例不繞過 migration guard 建立人工 COW 狀態。
        return service, fixture, second_bookmark
    assert service.upgrade_to_repository().is_repository
    repository, storage_status = WatchlistService.discover_repository(config)
    assert repository is not None and storage_status.is_repository
    reopened = WatchlistService(config, repository=repository, storage_status=storage_status)
    return reopened, fixture, second_bookmark


def _entry_for(widget: PersonalH20BookmarkControls, bookmark_id: str) -> int:
    for row in range(widget.bookmarks.count()):
        item = widget.bookmarks.item(row)
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if getattr(entry, "bookmark_id", "") == bookmark_id:
            return row
    raise AssertionError(f"找不到指定 H20 bookmark：{bookmark_id}")


def _current_bookmark_id(widget: PersonalH20BookmarkControls) -> str | None:
    entry = widget._current_entry()
    return entry.bookmark_id if entry is not None else None


def _record_confirmation(
    confirmations: list[tuple[str, str]], code: str, identity: str
) -> bool:
    confirmations.append((code, identity))
    return True


def _widget(
    service: WatchlistService,
    fixture: dict[str, Any],
    *,
    confirm_remove=None,
    bookmark_state_reader=None,
) -> PersonalH20BookmarkControls:
    return PersonalH20BookmarkControls(
        service,
        config_path=fixture["activation"].config_path,
        market_root=fixture["market_root"],
        prediction_reader=public_reader if bookmark_state_reader is None else None,
        bookmark_state_reader=bookmark_state_reader,
        confirm_remove=confirm_remove,
    )


def _install_synthetic_h20_ports(monkeypatch, calls: dict[str, int] | None = None) -> None:
    from copy import deepcopy
    from scripts.scheduled import run_personal_current_observed_h20_daily as runner

    counts = calls if calls is not None else {"source": 0, "contract": 0}

    def source_verifier(binding):
        counts["source"] += 1
        return deepcopy(binding)

    def contract_verifier(binding):
        counts["contract"] += 1
        return deepcopy(binding)

    monkeypatch.setattr(runner, "personal_current_observed_h20_read_ports", lambda: {
        "source_verifier": source_verifier,
        "contract_verifier": contract_verifier,
    })


def _session_bookmark_reader(bookmark, *, config_path, market_root, cancel_callback=None):
    from scripts.scheduled.personal_h20_bookmark_read_session import (
        read_personal_h20_research_bookmark_with_session,
    )

    return read_personal_h20_research_bookmark_with_session(
        bookmark,
        config_path=config_path,
        market_root=market_root,
        cancel_callback=cancel_callback,
    )


def _close_widget(app: QApplication, widget: PersonalH20BookmarkControls) -> None:
    if not widget._closing:
        widget.close()
    _wait_for(app, lambda: widget._worker is None, timeout_seconds=20.0)
    app.processEvents()


def test_list_shows_invalid_rows_and_reopens_only_exact_typed_h20_state(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, fixture, _second = _make_watchlist(tmp_path)
    widget = _widget(service, fixture)
    emitted: list[object] = []
    widget.stateReady.connect(emitted.append)

    # 這個 UI 路徑不得查詢或替換 latest reference pointer。
    import app_module.recommendation.personal_h20_product_evidence as product_module

    def forbidden_latest(*_args: object, **_kwargs: object) -> None:
        pytest.fail("H20 收藏重開不得查詢 current/latest product reference")

    monkeypatch.setattr(product_module, "read_personal_h20_product_reference", forbidden_latest)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)

        assert widget.bookmarks.count() == 2
        valid_row = _entry_for(widget, fixture["bookmark"].bookmark_id)
        invalid_row = next(
            row
            for row in range(widget.bookmarks.count())
            if "收藏無法核驗" in widget.bookmarks.item(row).text()
        )
        assert "缺 payload 的 H20 列" not in widget.bookmarks.item(invalid_row).text()
        widget.bookmarks.setCurrentRow(invalid_row)
        assert not widget.open_button.isEnabled()
        assert not widget.remove_button.isEnabled()
        assert "personal_h20_bookmark" in widget.diagnostic_text.toPlainText()

        widget.bookmarks.setCurrentRow(valid_row)
        assert widget.open_button.isEnabled()
        assert widget.remove_button.isEnabled()
        widget.open_selected()
        _wait_for(app, lambda: widget._worker is None)

        assert len(emitted) == 1
        state = emitted[0]
        assert isinstance(state, PersonalH20ResearchBookmarkState)
        assert state.bookmark.bookmark_id == fixture["bookmark"].bookmark_id
        assert state.bookmark.manifest_sha256 == fixture["manifest_sha256"]
        assert state.selected_row.symbol == fixture["selection"].symbol
        assert state.selected_row.gross_return_bp == 684
        assert state.current_model_binding_status == "enabled_same_contract"
        assert service.get_research_bookmark(fixture["bookmark"].bookmark_id) == fixture["bookmark"]
    finally:
        _close_widget(app, widget)


def test_remove_uses_default_no_confirmation_and_never_changes_watchlist_on_decline(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, fixture, _second = _make_watchlist(tmp_path, include_invalid=False)
    widget = _widget(service, fixture)
    dialog: dict[str, object] = {}

    def answer_no(*args: object) -> QMessageBox.StandardButton:
        dialog["buttons"] = args[-2]
        dialog["default"] = args[-1]
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", answer_no)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        widget.bookmarks.setCurrentRow(_entry_for(widget, fixture["bookmark"].bookmark_id))
        watchlist_before = service.get_watchlist()
        assert watchlist_before is not None
        revision_before = watchlist_before.revision
        widget.remove_selected()

        assert dialog["default"] == QMessageBox.StandardButton.No
        assert dialog["buttons"] == (
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        assert widget._worker is None
        assert "已取消移除" in widget.status_label.text()
        assert service.get_research_bookmark(fixture["bookmark"].bookmark_id) == fixture["bookmark"]
        watchlist_after = service.get_watchlist()
        assert watchlist_after is not None and watchlist_after.revision == revision_before
    finally:
        _close_widget(app, widget)


def test_every_duplicate_identity_row_is_visible_and_inert(
    app: QApplication,
    tmp_path: Path,
) -> None:
    service, fixture, _second = _make_watchlist(
        tmp_path,
        include_invalid=False,
        include_same_stock_manual=False,
    )
    original_rows = service.get_stocks()
    saved_row = next(
        row for row in original_rows
        if row["source"] == PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE
    )

    class DuplicateIdentityRead:
        """只對真 COW get_stocks 回傳加一筆重複 identity 的 synthetic 錯列。"""

        def get_stocks(self, watchlist_id: str = "default") -> list[dict[str, Any]]:
            rows = service.get_stocks(watchlist_id)
            conflict = dict(saved_row)
            conflict.update(
                {
                    "source": "manual",
                    "stock_name": "同身份衝突列",
                    "research_bookmark": None,
                }
            )
            return [*rows, dict(saved_row), conflict]

        def get_research_bookmark(self, bookmark_id: str, watchlist_id: str = "default"):
            return service.get_research_bookmark(bookmark_id, watchlist_id)

        def __getattr__(self, name: str) -> Any:
            return getattr(service, name)

    widget = _widget(cast(WatchlistService, DuplicateIdentityRead()), fixture)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        assert widget.bookmarks.count() == 3
        for row in range(widget.bookmarks.count()):
            entry = widget.bookmarks.item(row).data(Qt.ItemDataRole.UserRole)
            assert entry.error_code in {
                "personal_h20_bookmark_identity_ambiguous",
                "personal_h20_bookmark_identity_conflict_with_other_watchlist_row",
            }
            assert entry.bookmark is None
            widget.bookmarks.setCurrentRow(row)
            assert not widget.open_button.isEnabled()
            assert not widget.remove_button.isEnabled()
        assert widget.restore_selection(fixture["bookmark"].bookmark_id) == "rejected"
        assert widget.bookmarks.currentRow() == -1
        assert "多筆或衝突" in widget.diagnostic_text.toPlainText()
    finally:
        _close_widget(app, widget)


class _BlockingWatchlistService:
    """在真 COW public reader 前設時序 barrier，之後仍委派原 service。"""

    def __init__(
        self,
        service: WatchlistService,
        *,
        open_entered: threading.Event | None = None,
        open_release: threading.Event | None = None,
        remove_entered: threading.Event | None = None,
        remove_release: threading.Event | None = None,
    ) -> None:
        self.service = service
        self.open_entered = open_entered
        self.open_release = open_release
        self.remove_entered = remove_entered
        self.remove_release = remove_release
        self._list_calls = 0

    @property
    def list_calls(self) -> int:
        return self._list_calls

    def get_stocks(self, watchlist_id: str = "default") -> list[dict[str, Any]]:
        self._list_calls += 1
        return self.service.get_stocks(watchlist_id)

    def get_research_bookmark(self, bookmark_id: str, watchlist_id: str = "default"):
        return self.service.get_research_bookmark(bookmark_id, watchlist_id)

    def get_personal_h20_research_bookmark_state(
        self,
        bookmark_id: str,
        watchlist_id: str = "default",
        *,
        config_path: str | Path,
        market_root: str | Path,
        prediction_reader,
        cancel_callback=None,
    ) -> PersonalH20ResearchBookmarkState:
        if self.open_entered is not None and self.open_release is not None:
            self.open_entered.set()
            if not self.open_release.wait(timeout=20):
                raise AssertionError("測試 H20 重開 barrier 未釋放")
        return self.service.get_personal_h20_research_bookmark_state(
            bookmark_id,
            watchlist_id,
            config_path=config_path,
            market_root=market_root,
            prediction_reader=prediction_reader,
            cancel_callback=cancel_callback,
        )

    def remove_research_bookmark(self, bookmark_id: str, watchlist_id: str = "default"):
        if self.remove_entered is not None and self.remove_release is not None:
            self.remove_entered.set()
            if not self.remove_release.wait(timeout=20):
                raise AssertionError("測試 H20 移除 barrier 未釋放")
        return self.service.remove_research_bookmark(bookmark_id, watchlist_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.service, name)


def test_remove_is_exact_cow_preserves_other_same_stock_item_and_restore_token(
    app: QApplication,
    tmp_path: Path,
) -> None:
    service, fixture, _second = _make_watchlist(tmp_path, include_invalid=False)
    entered = threading.Event()
    release = threading.Event()
    wrapper = _BlockingWatchlistService(
        service,
        remove_entered=entered,
        remove_release=release,
    )
    confirmations: list[tuple[str, str]] = []
    widget = _widget(
        cast(WatchlistService, wrapper),
        fixture,
        confirm_remove=lambda code, identity: _record_confirmation(
            confirmations, code, identity
        ),
    )
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        widget.bookmarks.setCurrentRow(_entry_for(widget, fixture["bookmark"].bookmark_id))
        widget.remove_selected()
        _wait_for(app, entered.is_set)

        assert confirmations == [
            (fixture["bookmark"].stock_code, fixture["bookmark"].bookmark_id)
        ]
        assert widget._operation == "remove"
        assert not widget.cancel_button.isEnabled()
        assert "移除已送出，正在保存" in widget.status_label.text()
        widget.cancel()
        assert "不能中途取消" in widget.status_label.text()
        assert service.get_research_bookmark(fixture["bookmark"].bookmark_id) == fixture["bookmark"]

        release.set()
        _wait_for(
            app,
            lambda: widget._worker is None
            and wrapper.list_calls == 2
            and widget.bookmarks.count() == 0,
        )
        assert service.get_research_bookmark(fixture["bookmark"].bookmark_id) is None
        rows = service.get_stocks()
        assert len(rows) == 1
        assert rows[0]["stock_code"] == fixture["bookmark"].stock_code
        assert rows[0]["source"] == "manual"
        assert isinstance(widget.last_restore_token, DailyMarketResearchBookmarkRestoreToken)
        assert widget.last_restore_token.bookmark_id == fixture["bookmark"].bookmark_id
    finally:
        release.set()
        _close_widget(app, widget)


def test_pending_refresh_coalesces_after_exact_reopen_and_preserves_selection(
    app: QApplication,
    tmp_path: Path,
) -> None:
    service, fixture, second = _make_watchlist(
        tmp_path,
        include_invalid=False,
        include_same_stock_manual=False,
        include_second_h20=True,
    )
    assert second is not None
    entered = threading.Event()
    release = threading.Event()
    wrapper = _BlockingWatchlistService(
        service,
        open_entered=entered,
        open_release=release,
    )
    widget = _widget(cast(WatchlistService, wrapper), fixture)
    emitted: list[object] = []
    widget.stateReady.connect(emitted.append)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        assert widget.bookmarks.count() == 2
        first_row = _entry_for(widget, fixture["bookmark"].bookmark_id)
        widget.bookmarks.setCurrentRow(first_row)
        widget.open_selected()
        _wait_for(app, entered.is_set)

        widget.refresh_bookmarks()
        widget.refresh_bookmarks()
        assert widget._refresh_pending
        assert wrapper.list_calls == 1
        release.set()
        _wait_for(app, lambda: widget._worker is None and wrapper.list_calls == 2)

        assert len(emitted) == 1
        assert isinstance(emitted[0], PersonalH20ResearchBookmarkState)
        assert emitted[0].bookmark.bookmark_id == fixture["bookmark"].bookmark_id
        assert widget.bookmarks.count() == 2
        selected = widget.bookmarks.currentItem().data(Qt.ItemDataRole.UserRole)
        assert getattr(selected, "bookmark_id", None) == fixture["bookmark"].bookmark_id
        assert service.get_research_bookmark(fixture["bookmark"].bookmark_id) == fixture["bookmark"]
    finally:
        release.set()
        _close_widget(app, widget)


def test_selection_change_drops_late_exact_reopen_without_substitution(
    app: QApplication,
    tmp_path: Path,
) -> None:
    service, fixture, second = _make_watchlist(
        tmp_path,
        include_invalid=False,
        include_same_stock_manual=False,
        include_second_h20=True,
    )
    assert second is not None
    second_bookmark = cast(PersonalH20ResearchBookmark, second)
    entered = threading.Event()
    release = threading.Event()
    wrapper = _BlockingWatchlistService(
        service,
        open_entered=entered,
        open_release=release,
    )
    widget = _widget(cast(WatchlistService, wrapper), fixture)
    emitted: list[object] = []
    widget.stateReady.connect(emitted.append)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        first_row = _entry_for(widget, fixture["bookmark"].bookmark_id)
        second_row = _entry_for(widget, second_bookmark.bookmark_id)
        widget.bookmarks.setCurrentRow(first_row)
        widget.open_selected()
        _wait_for(app, entered.is_set)
        widget.bookmarks.setCurrentRow(second_row)
        release.set()
        _wait_for(app, lambda: widget._worker is None)

        assert emitted == []
        assert "選取已變更" in widget.status_label.text()
        selected = widget.bookmarks.currentItem().data(Qt.ItemDataRole.UserRole)
        assert getattr(selected, "bookmark_id", None) == second_bookmark.bookmark_id
        assert service.get_research_bookmark(fixture["bookmark"].bookmark_id) == fixture["bookmark"]
        assert service.get_research_bookmark(second_bookmark.bookmark_id) == second_bookmark
    finally:
        release.set()
        _close_widget(app, widget)


@pytest.mark.parametrize("shutdown", (False, True))
def test_cancel_or_close_during_reopen_never_emits_late_state(
    app: QApplication,
    tmp_path: Path,
    shutdown: bool,
) -> None:
    service, fixture, _second = _make_watchlist(tmp_path, include_invalid=False)
    entered = threading.Event()
    release = threading.Event()
    wrapper = _BlockingWatchlistService(
        service,
        open_entered=entered,
        open_release=release,
    )
    widget = _widget(cast(WatchlistService, wrapper), fixture)
    emitted: list[object] = []
    widget.stateReady.connect(emitted.append)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        widget.bookmarks.setCurrentRow(_entry_for(widget, fixture["bookmark"].bookmark_id))
        widget.open_selected()
        _wait_for(app, entered.is_set)
        if shutdown:
            widget.close()
        else:
            widget.cancel()
        release.set()
        _wait_for(app, lambda: widget._worker is None)

        assert emitted == []
        if shutdown:
            assert widget._closing
        else:
            assert "已取消讀取" in widget.status_label.text()
    finally:
        release.set()
        _close_widget(app, widget)


def test_layout_remains_usable_at_narrow_width(app: QApplication, tmp_path: Path) -> None:
    service, fixture, _second = _make_watchlist(tmp_path, include_invalid=False)
    widget = _widget(service, fixture)
    widget.resize(320, 500)
    widget.show()
    app.processEvents()
    try:
        assert widget.width() <= 340
        for control in (
            widget.refresh_button,
            widget.open_button,
            widget.remove_button,
            widget.cancel_button,
            widget.status_label,
            widget.diagnostic_text,
        ):
            assert control.isVisible()
            assert widget.rect().contains(control.geometry())
            assert control.width() > 100
    finally:
        _close_widget(app, widget)


def test_typed_state_reader_uses_real_bookmark_session_and_exact_bookmark_identity(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, fixture, _second = _make_watchlist(tmp_path, include_invalid=False)
    calls = {"source": 0, "contract": 0}
    _install_synthetic_h20_ports(monkeypatch, calls)
    received: list[dict[str, Any]] = []

    def reader(bookmark, *, config_path, market_root, cancel_callback=None):
        received.append(bookmark.to_dict())
        return _session_bookmark_reader(
            bookmark,
            config_path=config_path,
            market_root=market_root,
            cancel_callback=cancel_callback,
        )

    widget = _widget(service, fixture, bookmark_state_reader=reader)
    emitted: list[object] = []
    widget.stateReady.connect(emitted.append)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        widget.bookmarks.setCurrentRow(_entry_for(widget, fixture["bookmark"].bookmark_id))
        widget.open_selected()
        _wait_for(app, lambda: widget._worker is None)

        assert len(emitted) == 1
        state = emitted[0]
        assert isinstance(state, PersonalH20ResearchBookmarkState)
        assert state.bookmark.to_dict() == fixture["bookmark"].to_dict()
        assert state.cohort.manifest_sha256 == fixture["manifest_sha256"]
        assert state.selected_row.symbol == fixture["selection"].symbol
        assert state.selected_row.gross_return_bp == 684
        assert received == [fixture["bookmark"].to_dict()]
        # 使用原 capture validator 與 synthetic verifier；不改寫私人 fixture。
        assert calls == {"source": 6, "contract": 2}
        assert service.get_research_bookmark(fixture["bookmark"].bookmark_id) == fixture["bookmark"]
    finally:
        _close_widget(app, widget)


@pytest.mark.parametrize("bad_result", ["wrong_type", "different_bookmark"])
def test_typed_state_reader_rejects_wrong_type_or_full_bookmark_identity(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_result: str,
) -> None:
    service, fixture, _second = _make_watchlist(tmp_path, include_invalid=False)
    _install_synthetic_h20_ports(monkeypatch)

    def reader(bookmark, *, config_path, market_root, cancel_callback=None):
        state = _session_bookmark_reader(
            bookmark,
            config_path=config_path,
            market_root=market_root,
            cancel_callback=cancel_callback,
        )
        if bad_result == "wrong_type":
            return object()
        different_bookmark = create_personal_h20_research_bookmark(
            fixture["reference"],
            fixture["cohort"],
            fixture["selection"],
            sort_descending=True,
            scroll_position=fixture["bookmark"].scroll_position + 1,
        )
        assert different_bookmark.bookmark_id != bookmark.bookmark_id
        return replace(state, bookmark=different_bookmark)

    widget = _widget(service, fixture, bookmark_state_reader=reader)
    emitted: list[object] = []
    widget.stateReady.connect(emitted.append)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        widget.bookmarks.setCurrentRow(_entry_for(widget, fixture["bookmark"].bookmark_id))
        widget.open_selected()
        _wait_for(app, lambda: widget._worker is None)

        assert emitted == []
        assert "personal_h20_bookmark_reopened_state_identity_mismatch" in widget.diagnostic_text.toPlainText()
    finally:
        _close_widget(app, widget)


def test_typed_reader_cannot_return_after_watchlist_bookmark_was_removed(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, fixture, _second = _make_watchlist(tmp_path, include_invalid=False)
    _install_synthetic_h20_ports(monkeypatch)

    def reader(bookmark, *, config_path, market_root, cancel_callback=None):
        state = _session_bookmark_reader(
            bookmark,
            config_path=config_path,
            market_root=market_root,
            cancel_callback=cancel_callback,
        )
        service.remove_research_bookmark(bookmark.bookmark_id)
        return state

    widget = _widget(service, fixture, bookmark_state_reader=reader)
    emitted: list[object] = []
    widget.stateReady.connect(emitted.append)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        widget.bookmarks.setCurrentRow(_entry_for(widget, fixture["bookmark"].bookmark_id))
        widget.open_selected()
        _wait_for(app, lambda: widget._worker is None)

        assert emitted == []
        assert "personal_h20_bookmark_changed_during_read" in widget.diagnostic_text.toPlainText()
    finally:
        _close_widget(app, widget)


def test_restore_selection_rejects_missing_target_without_fallback(
    app: QApplication,
    tmp_path: Path,
) -> None:
    service, fixture, _second = _make_watchlist(tmp_path, include_invalid=False)
    widget = _widget(service, fixture)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        missing = "sha256:" + "f" * 64

        assert widget.restore_selection(missing) == "rejected"
        assert widget.bookmarks.currentRow() == -1
        assert "未改選其他列" in widget.diagnostic_text.toPlainText()
        assert widget.restore_selection(fixture["bookmark"].bookmark_id) == "selected"
        selected = widget._current_entry()
        assert selected is not None and selected.bookmark_id == fixture["bookmark"].bookmark_id
    finally:
        _close_widget(app, widget)


def test_restore_selection_is_queued_across_open_then_refresh_and_uses_exact_id(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, fixture, second = _make_watchlist(
        tmp_path,
        include_invalid=False,
        include_same_stock_manual=False,
        include_second_h20=True,
    )
    assert second is not None
    second_bookmark = cast(PersonalH20ResearchBookmark, second)
    _install_synthetic_h20_ports(monkeypatch)
    entered = threading.Event()
    release = threading.Event()

    def reader(bookmark, *, config_path, market_root, cancel_callback=None):
        if bookmark.bookmark_id == fixture["bookmark"].bookmark_id:
            entered.set()
            if not release.wait(timeout=20):
                raise AssertionError("測試 H20 session barrier 未釋放")
        return _session_bookmark_reader(
            bookmark,
            config_path=config_path,
            market_root=market_root,
            cancel_callback=cancel_callback,
        )

    widget = _widget(service, fixture, bookmark_state_reader=reader)
    emitted: list[object] = []
    widget.stateReady.connect(emitted.append)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        assert widget.restore_selection(fixture["bookmark"].bookmark_id) == "selected"
        widget.open_selected()
        _wait_for(app, entered.is_set)
        widget.refresh_bookmarks()
        assert widget._refresh_pending
        assert widget.restore_selection(second_bookmark.bookmark_id) == "queued"
        assert _current_bookmark_id(widget) == fixture["bookmark"].bookmark_id

        release.set()
        _wait_for(
            app,
            lambda: widget._worker is None
            and widget.bookmarks.count() == 2
            and _current_bookmark_id(widget) == second_bookmark.bookmark_id,
        )
        assert len(emitted) == 1
        assert isinstance(emitted[0], PersonalH20ResearchBookmarkState)
        assert emitted[0].bookmark.bookmark_id == fixture["bookmark"].bookmark_id
        assert _current_bookmark_id(widget) == second_bookmark.bookmark_id
    finally:
        release.set()
        _close_widget(app, widget)


def test_cancelled_open_discards_queued_restore_and_refresh(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, fixture, second = _make_watchlist(
        tmp_path,
        include_invalid=False,
        include_same_stock_manual=False,
        include_second_h20=True,
    )
    assert second is not None
    second_bookmark = cast(PersonalH20ResearchBookmark, second)
    _install_synthetic_h20_ports(monkeypatch)
    entered = threading.Event()
    release = threading.Event()

    def reader(bookmark, *, config_path, market_root, cancel_callback=None):
        entered.set()
        if not release.wait(timeout=20):
            raise AssertionError("測試 H20 session barrier 未釋放")
        return _session_bookmark_reader(
            bookmark,
            config_path=config_path,
            market_root=market_root,
            cancel_callback=cancel_callback,
        )

    stock_reads = 0
    original_get_stocks = service.get_stocks

    def counted_get_stocks(*args, **kwargs):
        nonlocal stock_reads
        stock_reads += 1
        return original_get_stocks(*args, **kwargs)

    monkeypatch.setattr(service, "get_stocks", counted_get_stocks)
    widget = _widget(service, fixture, bookmark_state_reader=reader)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        assert stock_reads == 1
        assert widget.restore_selection(fixture["bookmark"].bookmark_id) == "selected"
        widget.open_selected()
        _wait_for(app, entered.is_set)
        widget.refresh_bookmarks()
        assert widget._refresh_pending
        assert widget.restore_selection(second_bookmark.bookmark_id) == "queued"

        widget.cancel()
        assert not widget._refresh_pending
        assert widget._restore_selection_id == ""
        release.set()
        _wait_for(app, lambda: widget._worker is None)

        assert stock_reads == 1
        assert _current_bookmark_id(widget) == fixture["bookmark"].bookmark_id
        assert widget._restore_selection_id == ""
    finally:
        release.set()
        _close_widget(app, widget)


@pytest.mark.parametrize("shutdown", [False, True])
def test_typed_reader_cancel_or_close_drops_late_session_result(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shutdown: bool,
) -> None:
    service, fixture, _second = _make_watchlist(tmp_path, include_invalid=False)
    _install_synthetic_h20_ports(monkeypatch)
    entered = threading.Event()
    release = threading.Event()

    def reader(bookmark, *, config_path, market_root, cancel_callback=None):
        entered.set()
        if not release.wait(timeout=20):
            raise AssertionError("測試 H20 session barrier 未釋放")
        return _session_bookmark_reader(
            bookmark,
            config_path=config_path,
            market_root=market_root,
            cancel_callback=cancel_callback,
        )

    widget = _widget(service, fixture, bookmark_state_reader=reader)
    emitted: list[object] = []
    widget.stateReady.connect(emitted.append)
    widget.show()
    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        widget.bookmarks.setCurrentRow(_entry_for(widget, fixture["bookmark"].bookmark_id))
        widget.open_selected()
        _wait_for(app, entered.is_set)
        if shutdown:
            widget.close()
        else:
            widget.cancel()
        release.set()
        _wait_for(app, lambda: widget._worker is None)

        assert emitted == []
        if shutdown:
            assert widget._closing
        else:
            assert "已取消讀取" in widget.status_label.text()
    finally:
        release.set()
        _close_widget(app, widget)
