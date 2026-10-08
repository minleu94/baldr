"""真 MainWindow 以正式唯讀根瀏覽固定 full-N 技術研究來源。"""

from __future__ import annotations

from datetime import datetime, time
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import tempfile
from typing import Any
from urllib.parse import unquote
from zoneinfo import ZoneInfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_parent_v4_producer import (
    produce_daily_market_technical_parent_v4,
)
from app_module.daily_market_technical_universe_v4_bookmark import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE,
    DailyMarketTechnicalUniverseV4Bookmark,
    DailyMarketTechnicalUniverseV4BookmarkState,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4ParentReceiptReference,
    DailyMarketTechnicalUniverseV4Plan,
    DailyMarketTechnicalUniverseV4StoreWriter,
    daily_market_technical_source_clock_v4_from_dict,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from tests.test_daily_market_technical_universe_v4_query import (
    _DECISION_DATE,
    _EXCLUDED,
    _INCLUDED,
    _full_cohort,
    _long_configured_root,
    _segment_cohorts,
    _write_source,
)
from tests.test_ui_qt_main_fulln_bookmark_journey import (
    _ISOLATED_ENVIRONMENT_KEYS,
    _bookmark_row_number,
    _drain_qt_deferred_deletes,
    _wait_for,
    _window_is_closed,
)
from ui_qt.main import MainWindow
from ui_qt.views.daily_market_research_view import DailyMarketResearchView
from ui_qt.views.daily_market_technical_stock_v4_view import (
    DailyMarketTechnicalStockV4View,
)
from ui_qt.views.daily_market_technical_universe_v4_view import (
    DailyMarketTechnicalUniverseV4View,
)
from ui_qt.views.watchlist_view import WatchlistView
from ui_qt.widgets.technical_universe_bookmark_controls import (
    DailyMarketTechnicalUniverseV4BookmarkControls,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_READ_ROOT_ENV = "TECHNICAL_UNIVERSE_READ_ROOT"


def _file_pin(path: Path) -> tuple[int, int, int, int, str]:
    info = os.stat(to_internal_io_path(path), follow_symlinks=False)
    assert stat.S_ISREG(info.st_mode)
    digest = hashlib.sha256()
    with open(to_internal_io_path(path), "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return (
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
        digest.hexdigest(),
    )


def _source_sqlite_inventory(
    database: Path,
) -> dict[str, tuple[int, int, int, int, str] | None]:
    result: dict[str, tuple[int, int, int, int, str] | None] = {}
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = Path(f"{database}{suffix}")
        key = path.name
        if os.path.isfile(to_internal_io_path(path)):
            result[key] = _file_pin(path)
        else:
            result[key] = None
    return result


def _path_key(path: str | Path) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _tree_inventory(root: Path) -> dict[str, tuple[str, int, int, int, int, str]]:
    """固定保存樹的路徑、型別與 bytes，並拒絕連結或非一般檔案。"""

    canonical_root = Path(os.path.abspath(root))
    assert canonical_root.is_absolute()
    assert os.path.isdir(to_internal_io_path(canonical_root))
    result: dict[str, tuple[str, int, int, int, int, str]] = {}

    def visit(directory: Path, relative_parts: tuple[str, ...]) -> None:
        with os.scandir(to_internal_io_path(directory)) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
        for entry in entries:
            child = directory / entry.name
            info = entry.stat(follow_symlinks=False)
            assert not stat.S_ISLNK(info.st_mode)
            assert not (getattr(info, "st_file_attributes", 0) & 0x400)
            child_parts = (*relative_parts, entry.name)
            relative = Path(*child_parts).as_posix()
            if stat.S_ISDIR(info.st_mode):
                result[relative] = ("directory", 0, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink, "")
                visit(child, child_parts)
                continue
            assert stat.S_ISREG(info.st_mode)
            digest = hashlib.sha256()
            with open(to_internal_io_path(child), "rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            result[relative] = (
                "file",
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
                info.st_nlink,
                digest.hexdigest(),
            )

    visit(canonical_root, ())
    return result


def _source_database_target(database: object) -> Path | None:
    if not isinstance(database, (str, bytes, os.PathLike)):
        return None
    raw = os.fsdecode(database)
    if raw.casefold().startswith("file:"):
        raw = unquote(raw[5:].split("?", 1)[0])
    if os.name == "nt" and raw.startswith("\\\\?\\"):
        raw = raw[4:]
    try:
        return Path(raw).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _produce_full_n_store_with_source(
    fixture_root: Path,
) -> tuple[Path, Path, Any, Any]:
    """用真 source producer 建立 257 納入＋1 排除保存，保留 SQLite 原檔。"""

    database = fixture_root / "synthetic-prices.sqlite"
    _write_source(database, (*_INCLUDED, *_EXCLUDED), missing_code="S0000")
    source_before = _source_sqlite_inventory(database)
    scope = ResearchCaptureWriteScope(_long_configured_root(fixture_root), database)
    cohort = _full_cohort()
    parent_references: list[DailyMarketTechnicalUniverseV4ParentReceiptReference] = []
    source_clock_payload: dict[str, object] | None = None

    for segment_index, segment_cohort in enumerate(_segment_cohorts(cohort)):
        parent_root = scope.root / "parents" / f"segment-{segment_index + 1:06d}"
        child_root = scope.root / "children" / f"segment-{segment_index + 1:06d}"
        parent_result = produce_daily_market_technical_parent_v4(
            source_database=database,
            cohort=segment_cohort,
            decision_cutoff=datetime.combine(
                _DECISION_DATE,
                time(16, 0),
                tzinfo=_TAIPEI,
            ),
            child_output_root=child_root,
            parent_root=parent_root,
            research_scope=scope,
        )
        assert parent_result.status == "complete", parent_result.error_code
        assert parent_result.plan is not None
        assert parent_result.receipt is not None
        current_clock = parent_result.plan.to_dict()["source_clock"]
        assert isinstance(current_clock, dict)
        if source_clock_payload is None:
            source_clock_payload = current_clock
        else:
            assert current_clock == source_clock_payload
        parent_references.append(
            DailyMarketTechnicalUniverseV4ParentReceiptReference.create(
                parent_root,
                parent_plan_identity_sha256=parent_result.plan.identity_sha256,
                parent_plan_sha256=parent_result.plan.content_sha256,
                parent_receipt_identity_sha256=parent_result.receipt.identity_sha256,
                parent_receipt_sha256=parent_result.receipt.content_sha256,
            )
        )

    assert source_clock_payload is not None
    assert len(parent_references) == 2
    plan = DailyMarketTechnicalUniverseV4Plan.build(
        cohort,
        source_clock=daily_market_technical_source_clock_v4_from_dict(
            source_clock_payload
        ),
    )
    assert tuple(
        (
            len(plan.segment_cohort(index).included_stock_codes),
            len(plan.segment_cohort(index).excluded_stock_codes),
        )
        for index in range(len(plan.segments))
    ) == ((256, 1), (1, 0))

    store_root = scope.root / "full-store"
    writer = DailyMarketTechnicalUniverseV4StoreWriter(
        store_root,
        research_scope=scope,
    )
    previous = writer.start(plan)
    for segment_index, reference in enumerate(parent_references):
        previous = writer.record_segment_parent(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            previous.identity_sha256,
            expected_previous_receipt_sha256=previous.content_sha256,
            segment_index=segment_index,
            parent_reference=reference,
        )
    complete = writer.complete(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        previous.identity_sha256,
        expected_previous_receipt_sha256=previous.content_sha256,
    )
    assert complete.status == "complete"
    assert _source_sqlite_inventory(database) == source_before
    return database, store_root, plan, complete


def _configure_main_environment(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fixture_root: Path,
    output_root: Path,
    data_root: Path,
    research_store_root: Path,
) -> None:
    temporary_root = fixture_root / "application-temp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(temporary_root))
    for name in {*_ISOLATED_ENVIRONMENT_KEYS, _READ_ROOT_ENV}:
        monkeypatch.delenv(name, raising=False)

    research_state_root = fixture_root / "research-state"
    active_ml_root = fixture_root / "ml-research"
    local_app_root = fixture_root / "localapp"
    roaming_app_root = fixture_root / "appdata"
    config_path = fixture_root / "baldr-config.json"
    ml_storage_config = fixture_root / "ml-research-storage.json"
    ml_storage_config.write_text(
        json.dumps(
            {
                "schema_version": "ml-research-storage.v1",
                "active_root": str(active_ml_root),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv(_READ_ROOT_ENV, str(research_store_root))
    monkeypatch.setenv("RESEARCH_STATE_ROOT", str(research_state_root))
    monkeypatch.setenv("TEMP", str(temporary_root))
    monkeypatch.setenv("TMP", str(temporary_root))
    monkeypatch.setenv("MPLCONFIGDIR", str(output_root / "application_state" / "matplotlib"))
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_root))
    monkeypatch.setenv("APPDATA", str(roaming_app_root))
    monkeypatch.setenv("BALDR_CONFIG", str(config_path))
    monkeypatch.setenv("BALDR_ML_RESEARCH_STORAGE_CONFIG", str(ml_storage_config))
    monkeypatch.setenv("PROFILE", "prod")
    monkeypatch.setenv(
        "PERSONAL_MODEL_POLICY_PATH",
        str(research_state_root / "personal-use-policy.json"),
    )
    monkeypatch.setenv(
        "PERSONAL_H20_ACTIVATION_CONFIG",
        str(data_root / "personal" / "recommendation_h20" / "activation.json"),
    )
    monkeypatch.setenv(
        "OFFICIAL_CALENDAR_CACHE_PATH",
        str(data_root / "official-calendar-cache.json"),
    )
    monkeypatch.setenv(
        "RECOMMENDATION_LEARNING_OUTPUT_ROOT",
        str(research_state_root / "recommendation-learning"),
    )
    monkeypatch.setenv(
        "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT",
        str(research_state_root / "bank-taiwan-recommendation-learning"),
    )


def test_mainwindow_uses_external_read_root_for_full_n_stock_return_and_bookmark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正常 Main 設定以外部固定根完成瀏覽、下鑽、返回與收藏重開。"""

    fixture_root = tmp_path / "technical-read-root-main"
    fixture_root.mkdir()
    source_database, store_root, plan, complete = _produce_full_n_store_with_source(
        fixture_root
    )
    source_pin = _source_sqlite_inventory(source_database)
    store_inventory = _tree_inventory(store_root.parent)
    assert store_inventory

    data_root = fixture_root / "main-data"
    output_root = fixture_root / "main-output"
    _configure_main_environment(
        monkeypatch,
        fixture_root=fixture_root,
        output_root=output_root,
        data_root=data_root,
        research_store_root=store_root,
    )

    network_attempts: list[str] = []

    def forbid_network(*_args: object, **_kwargs: object) -> None:
        network_attempts.append("socket connection attempted")
        raise AssertionError("full-N 唯讀 MainWindow journey 不得連接 provider 網路")

    monkeypatch.setattr(socket.socket, "connect", forbid_network)
    monkeypatch.setattr(socket.socket, "connect_ex", forbid_network)
    monkeypatch.setattr(socket, "create_connection", forbid_network)

    real_sqlite_connect = sqlite3.connect
    source_connection_modes: list[str] = []

    def guarded_sqlite_connect(
        database: Any,
        *args: Any,
        **kwargs: Any,
    ) -> sqlite3.Connection:
        target = _source_database_target(database)
        if target == source_database.resolve(strict=True):
            uri_value = kwargs.get("uri", args[6] if len(args) > 6 else False)
            raw = unquote(os.fsdecode(database)).casefold()
            if not uri_value or "mode=ro" not in raw:
                source_connection_modes.append("write_or_unqualified_open_rejected")
                raise AssertionError("synthetic source SQLite 只能以 mode=ro 開啟")
            source_connection_modes.append("mode=ro")
        return real_sqlite_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_sqlite_connect)

    app = QApplication.instance() or QApplication([])
    window: MainWindow | None = None
    stock_dialog: Any | None = None
    bookmark_confirmations: list[DailyMarketTechnicalUniverseV4Bookmark] = []
    bookmark_saved: list[object] = []
    reopened_states: list[object] = []

    try:
        window = MainWindow()
        assert window.config.data_root.resolve() == data_root.resolve()
        assert window.config.output_root.resolve() == output_root.resolve()
        configured_read_root = window.config.technical_universe_read_root
        assert configured_read_root is not None
        assert _path_key(configured_read_root) == _path_key(store_root)
        assert window.application_settings.environment[_READ_ROOT_ENV] == str(store_root)
        assert not Path(_path_key(output_root)).is_relative_to(Path(_path_key(store_root)))
        assert not Path(_path_key(store_root)).is_relative_to(Path(_path_key(output_root)))
        assert window.watchlist_service is not None
        assert window.watchlist_service.default_watchlist_file.resolve().is_relative_to(
            output_root.resolve()
        )
        assert isinstance(window.watchlist_view, WatchlistView)

        window.show()
        app.processEvents()
        window.left_navigation.button_for_key("recommendation").click()
        recommendation = window.recommendation_view
        daily = recommendation.daily_market_research_view
        assert isinstance(daily, DailyMarketResearchView)
        recommendation.result_source_tabs.setCurrentWidget(daily)

        browser = daily.technical_universe_view
        assert isinstance(browser, DailyMarketTechnicalUniverseV4View)
        assert _path_key(browser.store_output_root) == _path_key(store_root)
        assert browser.production_request_factory is None
        assert not browser.produce_button.isEnabled()
        assert not browser.resume_button.isEnabled()

        browser.refresh_button.click()
        _wait_for(app, lambda: browser._worker is None and browser.sources.count() == 1)
        entry = browser.selected_source
        assert entry is not None and entry.is_selectable
        assert entry.source_status == "complete"
        browser.load_button.click()
        _wait_for(
            app,
            lambda: browser._worker is None and browser.current_page is not None,
            timeout_seconds=120,
        )
        page = browser.current_page
        query = browser.current_query
        assert page is not None and query is not None
        assert page.is_complete
        assert page.counts.declared_count == 258
        assert page.counts.included_count == 257
        assert page.counts.excluded_count == 1
        assert page.counts.processed_count == 257
        assert page.counts.pending_count == 0
        assert page.counts.missing_data_count == 1
        assert query.generation_identity_sha256 == plan.generation_identity_sha256
        assert query.receipt_identity_sha256 == complete.identity_sha256
        assert "來源已通過 strict 核驗" in browser.verified_pins.text()
        assert query.generation_identity_sha256 in browser.verified_pins.text()
        assert query.receipt_sha256 in browser.verified_pins.text()
        assert "資料可得時間未知" in browser.disclaimer.text()
        assert "不授歷史 PIT／可交易資格" in browser.verified_pins.text()

        selected_code = "S0001"
        assert browser._select_stock_code(selected_code)
        selected_row = browser._selected_row()
        assert selected_row is not None and selected_row.stock_code == selected_code
        browser.open_button.click()
        _wait_for(
            app,
            lambda: browser._worker is None and daily._technical_stock_dialog is not None,
            timeout_seconds=90,
        )
        stock_dialog = daily._technical_stock_dialog
        assert stock_dialog is not None
        details = stock_dialog.findChild(DailyMarketTechnicalStockV4View)
        assert details is not None and details._stock is not None
        assert details._stock.origin_query == query
        assert details._stock.snapshot.stock_code == selected_code
        assert details._stock.snapshot.snapshot_identity_sha256 == (
            selected_row.snapshot_identity_sha256
        )
        details.return_button.click()
        _wait_for(app, lambda: not stock_dialog.isVisible())
        app.processEvents()
        assert browser.current_query == query
        assert daily._technical_stock_dialog is None
        stock_dialog = None

        assert browser._select_stock_code("S0001")
        browser.add_selected_to_comparison()
        _wait_for(app, lambda: browser._worker is None)
        assert browser._select_stock_code("S0002")
        browser.add_selected_to_comparison()
        _wait_for(app, lambda: browser._worker is None)
        assert [item.row.stock_code for item in browser._comparison_basket] == [
            "S0001",
            "S0002",
        ]
        assert browser._select_stock_code(selected_code)

        def confirm_bookmark(value: object) -> bool:
            assert isinstance(value, DailyMarketTechnicalUniverseV4Bookmark)
            assert value.origin_query == query
            assert value.selected_stock_code == selected_code
            assert tuple(
                item.stock_code for item in value.comparison_selections
            ) == ("S0001", "S0002")
            bookmark_confirmations.append(value)
            return True

        daily.bookmark_confirmation_callback = confirm_bookmark
        daily.bookmarkSaved.connect(bookmark_saved.append)
        browser.bookmark_button.click()
        _wait_for(
            app,
            lambda: browser._worker is None and len(bookmark_confirmations) == 1,
            timeout_seconds=90,
        )
        bookmark = bookmark_confirmations[0]
        assert bookmark.source == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE
        assert len(bookmark_saved) == 1
        assert getattr(bookmark_saved[0], "status", None) == "added"
        persisted = window.watchlist_service.get_research_bookmark(bookmark.bookmark_id)
        assert persisted == bookmark
        assert bookmark.origin_query == query

        controls = window.watchlist_view.technical_bookmark_controls
        assert isinstance(controls, DailyMarketTechnicalUniverseV4BookmarkControls)
        _wait_for(
            app,
            lambda: controls._worker is None
            and controls.bookmarks.count() == 1,
            timeout_seconds=60,
        )
        controls.bookmarks.setCurrentRow(
            _bookmark_row_number(controls, bookmark.bookmark_id)
        )
        assert controls.open_button.isEnabled()
        window.watchlist_view.technicalBookmarkStateReady.connect(
            reopened_states.append
        )
        controls.open_button.click()
        _wait_for(
            app,
            lambda: controls._worker is None
            and browser._worker is None
            and bool(reopened_states)
            and browser.current_query == query,
            timeout_seconds=120,
        )
        assert len(reopened_states) == 1
        state = reopened_states[0]
        assert isinstance(state, DailyMarketTechnicalUniverseV4BookmarkState)
        assert state.bookmark == bookmark
        assert browser.current_query == bookmark.origin_query == query
        assert browser.current_query.generation_identity_sha256 == query.generation_identity_sha256
        assert browser.current_query.receipt_identity_sha256 == query.receipt_identity_sha256
        assert browser.current_query.source_clock_identity_sha256 == query.source_clock_identity_sha256
        assert browser.current_query.method_contracts_sha256 == query.method_contracts_sha256
        assert browser.current_query.plan_sha256 == query.plan_sha256
        assert browser.current_query.receipt_sha256 == query.receipt_sha256
        restored_row = browser._selected_row()
        assert restored_row is not None and restored_row.stock_code == selected_code
        assert [item.row.stock_code for item in browser._comparison_basket] == [
            "S0001",
            "S0002",
        ]
        assert all(item.query == query for item in browser._comparison_basket)
    finally:
        if stock_dialog is not None:
            try:
                dialog_is_visible = stock_dialog.isVisible()
            except RuntimeError:
                dialog_is_visible = False
            if dialog_is_visible:
                stock_dialog.close()
        if window is not None:
            if not _window_is_closed(window):
                window.close()
                _wait_for(app, lambda: _window_is_closed(window), timeout_seconds=90)
            _drain_qt_deferred_deletes(app, (window,))
        assert _source_sqlite_inventory(source_database) == source_pin
        assert source_connection_modes == []
        assert _tree_inventory(store_root.parent) == store_inventory
        assert network_attempts == []
