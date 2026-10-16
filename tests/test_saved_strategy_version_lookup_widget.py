"""保存策略版本 lookup 的明示操作與 worker 生命週期契約。"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel
import pytest

from app_module.research_history_lookup import ResearchHistoryEntry, ResearchHistoryResult
from app_module.saved_strategy_version_reader import (
    SavedStrategyVersionEntry,
    SavedStrategyVersionPage,
    SavedStrategyVersionSource,
)
from ui_qt.widgets.saved_strategy_version_lookup import SavedStrategyVersionLookupWidget


def _app() -> QApplication:
    instance = QApplication.instance()
    return instance if instance is not None else QApplication([])


def _wait_until(app: QApplication, condition: Callable[[], bool], timeout_seconds: float = 8.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.005)
    app.processEvents()
    assert condition(), "Qt worker did not settle before the bounded test deadline"


def _entry(
    *,
    version_id: str = "saved-v1",
    run_id: str = "run-1",
    saved_version: str = "2.1.0",
    execution_version: str = "1.4.2",
    source_present: bool = True,
    diagnostics: tuple[str, ...] = (),
) -> SavedStrategyVersionEntry:
    source_entry = None
    if source_present:
        source_entry = ResearchHistoryEntry(
            source_kind="registry",
            run_type="single_backtest",
            run_id=run_id,
            run_name="保存在回測時的策略名稱",
            stock_code="2330",
            start_date="2026-08-01",
            end_date="2026-08-31",
            created_at="2026-09-01T00:00:00+00:00",
            metadata_sha256="a" * 64,
            context_sha256="b" * 64,
            metadata_json=json.dumps({"strategy_version": execution_version}),
            result_supported=True,
            unsupported_reason="",
        )
    return SavedStrategyVersionEntry(
        version_id=version_id,
        strategy_id="strategy.sample",
        strategy_version=saved_version,
        source_run_id=run_id,
        promoted_at="2026-09-02T00:00:00+00:00",
        validation_status="pending",
        version_json=json.dumps({"version_id": version_id, "strategy_version": saved_version}),
        source_entry=source_entry,
        diagnostics=diagnostics,
    )


def _source(entry: SavedStrategyVersionEntry) -> SavedStrategyVersionSource:
    history_entry = entry.source_entry
    assert history_entry is not None
    history_result = ResearchHistoryResult(history_entry, {"saved_result": entry.source_run_id})
    rule_card_marker = object()
    saved_rule = SimpleNamespace(rule_card=rule_card_marker)
    result = SavedStrategyVersionSource(entry, history_result, saved_rule)
    return result


class _Reader:
    def __init__(self, entries: tuple[SavedStrategyVersionEntry, ...]) -> None:
        self.entries = entries
        self.sources = {entry.version_id: _source(entry) for entry in entries if entry.source_entry}
        self.list_calls = 0
        self.read_calls: list[str] = []
        self.list_started = threading.Event()
        self.read_started = threading.Event()
        self.release_list = threading.Event()
        self.release_read = threading.Event()
        self.delay_list = False
        self.delay_read = False
        self.cancel_seen = False

    def list_versions(self, *, limit: int = 200, offset: int = 0, check_cancel=None) -> SavedStrategyVersionPage:
        self.list_calls += 1
        self.list_started.set()
        if self.delay_list:
            self.release_list.wait(4.0)
        if check_cancel is not None:
            self.cancel_seen = bool(check_cancel())
        return SavedStrategyVersionPage(self.entries[offset:offset + limit], (), len(self.entries), limit, offset)

    def read_source(self, selected: SavedStrategyVersionEntry, *, check_cancel=None) -> SavedStrategyVersionSource:
        self.read_calls.append(selected.version_id)
        self.read_started.set()
        if self.delay_read:
            self.release_read.wait(4.0)
        if check_cancel is not None:
            self.cancel_seen = bool(check_cancel())
        return self.sources[selected.version_id]


def _load(app: QApplication, widget: SavedStrategyVersionLookupWidget) -> None:
    widget.refresh.click()
    _wait_until(app, lambda: not widget.has_running_worker())


def test_refresh_is_explicit_and_result_open_returns_the_original_history_result() -> None:
    app = _app()
    entry = _entry(saved_version="2.1.0", execution_version="1.4.2")
    reader = _Reader((entry,))
    opened: list[object] = []
    widget = SavedStrategyVersionLookupWidget(reader, opened.append)

    assert reader.list_calls == 0
    assert widget.entries.count() == 0
    assert widget.open_result.isEnabled() is False
    assert widget.open_rule.isEnabled() is False
    widget.open_selected_source()
    assert reader.read_calls == []

    _load(app, widget)
    assert reader.list_calls == 1
    assert widget.entries.count() == 1
    assert widget.entries.currentItem() is None
    assert widget.entries.item(0).data(Qt.ItemDataRole.UserRole) == entry
    assert "保存版本 2.1.0" in widget.entries.item(0).text()
    assert "來源執行版本 1.4.2" in widget.entries.item(0).text()
    assert "pending（不代表資格）" in widget.entries.item(0).text()
    assert opened == []

    widget.entries.setCurrentRow(0)
    assert widget.open_result.isEnabled()
    widget.open_result.click()
    _wait_until(app, lambda: not widget.has_running_worker())

    assert opened == [reader.sources[entry.version_id].history_result]
    widget.close()


def test_rule_open_uses_saved_rule_card_and_discloses_both_version_labels(monkeypatch) -> None:
    app = _app()
    entry = _entry(saved_version="2.1.0", execution_version="1.4.2")
    reader = _Reader((entry,))
    opened: list[object] = []
    widget = SavedStrategyVersionLookupWidget(reader, opened.append)
    _load(app, widget)
    widget.entries.setCurrentRow(0)

    dialogs: list[object] = []

    class Dialog:
        def __init__(self, card, parent=None, *, result=None) -> None:
            self.card = card
            self.parent = parent
            self.result = result
            self.summary = QLabel()
            dialogs.append(self)

        def exec(self) -> int:
            return 0

    from ui_qt.widgets import strategy_rule_card_dialog

    monkeypatch.setattr(strategy_rule_card_dialog, "StrategyRuleCardDialog", Dialog)
    widget.open_rule.click()
    _wait_until(app, lambda: not widget.has_running_worker())

    source = reader.sources[entry.version_id]
    assert len(dialogs) == 1
    assert dialogs[0].card is source.rule_card.rule_card
    assert dialogs[0].result is source.rule_card
    assert "保存版號：2.1.0" in dialogs[0].summary.text()
    assert "來源執行版號：1.4.2" in dialogs[0].summary.text()
    assert opened == []
    widget.close()


@pytest.mark.parametrize(
    "entry",
    (
        _entry(source_present=False),
        _entry(diagnostics=("registry:run_missing",)),
    ),
    ids=("missing-source", "source-diagnostic"),
)
def test_missing_source_or_reader_diagnostics_cannot_be_opened(entry) -> None:
    app = _app()
    reader = _Reader((entry,))
    opened: list[object] = []
    widget = SavedStrategyVersionLookupWidget(reader, opened.append)
    _load(app, widget)
    widget.entries.setCurrentRow(0)

    assert widget.open_result.isEnabled() is False
    assert widget.open_rule.isEnabled() is False
    widget.open_selected_source()
    assert reader.read_calls == []
    assert opened == []
    widget.close()


def test_selection_change_cooperatively_cancels_and_discards_delayed_source() -> None:
    app = _app()
    first = _entry(version_id="saved-a", run_id="run-a")
    second = _entry(version_id="saved-b", run_id="run-b", saved_version="3.0.0")
    reader = _Reader((first, second))
    reader.delay_read = True
    opened: list[object] = []
    widget = SavedStrategyVersionLookupWidget(reader, opened.append)
    _load(app, widget)
    widget.entries.setCurrentRow(0)
    widget.open_result.click()
    assert reader.read_started.wait(2.0)

    widget.entries.setCurrentRow(1)
    reader.release_read.set()
    _wait_until(app, lambda: not widget.has_running_worker())

    assert reader.read_calls == [first.version_id]
    assert reader.cancel_seen is True
    assert widget._selected_entry() == second
    assert opened == []
    widget.close()


def test_owner_generation_change_discards_delayed_result() -> None:
    app = _app()
    entry = _entry()
    reader = _Reader((entry,))
    reader.delay_read = True
    opened: list[object] = []
    owner = SimpleNamespace(_execution_generation=7)
    widget = SavedStrategyVersionLookupWidget(reader, opened.append, owner=owner)
    _load(app, widget)
    widget.entries.setCurrentRow(0)
    widget.open_result.click()
    assert reader.read_started.wait(2.0)

    owner._execution_generation += 1
    reader.release_read.set()
    _wait_until(app, lambda: not widget.has_running_worker())

    assert reader.cancel_seen is True
    assert opened == []
    widget.close()


def test_source_for_another_saved_entry_is_rejected() -> None:
    app = _app()
    selected = _entry(version_id="selected", run_id="run-selected")
    other = _entry(version_id="other", run_id="run-other", saved_version="3.0.0")
    reader = _Reader((selected, other))
    reader.sources[selected.version_id] = _source(other)
    opened: list[object] = []
    widget = SavedStrategyVersionLookupWidget(reader, opened.append)
    _load(app, widget)
    widget.entries.setCurrentRow(0)
    widget.open_result.click()
    _wait_until(app, lambda: not widget.has_running_worker())

    assert opened == []
    assert "已變更" in widget.status.text()
    widget.close()


def test_history_result_entry_must_match_selected_saved_source() -> None:
    app = _app()
    selected = _entry(version_id="selected", run_id="run-selected")
    other = _entry(version_id="other", run_id="run-other", saved_version="3.0.0")
    reader = _Reader((selected,))
    valid = reader.sources[selected.version_id]
    assert other.source_entry is not None
    wrong_history = ResearchHistoryResult(other.source_entry, {"saved_result": "wrong-run"})
    reader.sources[selected.version_id] = SavedStrategyVersionSource(
        selected, wrong_history, valid.rule_card
    )
    opened: list[object] = []
    widget = SavedStrategyVersionLookupWidget(reader, opened.append)
    _load(app, widget)
    widget.entries.setCurrentRow(0)
    widget.open_result.click()
    _wait_until(app, lambda: not widget.has_running_worker())

    assert opened == []
    assert "已變更" in widget.status.text()
    widget.close()


def test_close_waits_for_native_worker_cleanup_and_never_applies_late_list() -> None:
    app = _app()
    reader = _Reader((_entry(),))
    reader.delay_list = True
    widget = SavedStrategyVersionLookupWidget(reader, lambda _result: None)
    widget.show()
    widget.refresh.click()
    assert reader.list_started.wait(2.0)

    widget.close()
    assert widget.has_running_worker()
    assert widget.isVisible()
    reader.release_list.set()
    _wait_until(app, lambda: not widget.has_running_worker())

    assert widget.entries.count() == 0
    assert reader.cancel_seen is True
    widget.close()
    assert widget.isVisible() is False


def test_next_and_previous_pages_reach_older_version_and_keep_explicit_selection() -> None:
    app = _app()
    entries = tuple(_entry(version_id=f"saved-{i}", run_id=f"run-{i}") for i in range(201))
    reader = _Reader(entries)
    opened: list[object] = []
    widget = SavedStrategyVersionLookupWidget(reader, opened.append)
    _load(app, widget)
    assert widget.entries.count() == 200 and widget.next_page.isEnabled()
    assert not widget.previous_page.isEnabled()
    widget.next_page.click()
    _wait_until(app, lambda: not widget.has_running_worker())
    assert widget.entries.count() == 1 and widget.entries.item(0).data(Qt.UserRole) == entries[200]
    assert not widget.open_result.isEnabled()
    widget.entries.setCurrentRow(0)
    widget.open_result.click()
    _wait_until(app, lambda: not widget.has_running_worker())
    assert opened == [reader.sources[entries[200].version_id].history_result]
    widget.previous_page.click()
    _wait_until(app, lambda: not widget.has_running_worker())
    assert widget.entries.count() == 200 and not widget.open_result.isEnabled()
    widget.close()
