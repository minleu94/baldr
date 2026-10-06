from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import traceback
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[1]
COHORT_ID = "original-rank-test-universe"
STOCK_CODE = "2317"
DECISION_DATE = "2026-10-05"


def _within(case: Path, value: object) -> bool:
    if isinstance(value, int):
        return True
    try:
        return Path(os.fsdecode(value)).resolve().is_relative_to(case)
    except (TypeError, ValueError, OSError):
        return False


def _install_isolation_guard(case: Path, violations: list[dict[str, str]], writes: list[str]) -> None:
    def refuse(event: str, value: object) -> None:
        violations.append(
            {
                "event": event,
                "target": str(value),
                "caller": "".join(traceback.format_stack(limit=8)),
            }
        )
        raise PermissionError(f"F4 isolated-app guard: {event}")

    def audit(event: str, args: tuple[object, ...]) -> None:
        if event == "open":
            path, mode, flags = args
            if isinstance(path, str) and path.casefold() == os.devnull.casefold():
                return
            writing = (isinstance(mode, str) and any(char in mode for char in "wax+")) or bool(
                isinstance(flags, int)
                and flags
                & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            if writing:
                if not _within(case, path):
                    refuse(event, path)
                writes.append(str(path))
        elif event in {"os.mkdir", "os.remove", "os.rmdir"}:
            if not _within(case, args[0]):
                refuse(event, args[0])
        elif event in {"os.rename", "os.replace"}:
            if not _within(case, args[0]) or not _within(case, args[1]):
                refuse(event, args[:2])
        elif event in {"socket.connect", "subprocess.Popen"}:
            refuse(event, args[:2])
        elif event == "sqlite3.connect":
            raw = str(args[0])
            if raw != ":memory:":
                if raw.startswith("file:"):
                    from urllib.parse import unquote

                    raw = unquote(raw[5:].split("?", 1)[0]).lstrip("/")
                if not _within(case, raw):
                    refuse(event, raw)

    sys.addaudithook(audit)


def _wait_for(app: object, predicate, label: str, timeout_seconds: float = 35.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()  # type: ignore[attr-defined]
        if predicate():
            app.processEvents()  # type: ignore[attr-defined]
            return
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {label}")


def _row_for_code(view: object, code: str) -> int:
    from PySide6.QtCore import Qt

    table = view.results_table  # type: ignore[attr-defined]
    for index in range(table.rowCount()):
        item = table.item(index, 0)
        row = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if str(getattr(row, "stock_code", "") or "") == code:
            return index
    raise AssertionError(f"stock code {code} missing from research result table")


def _select_code(view: object, code: str) -> None:
    view.results_table.selectRow(_row_for_code(view, code))  # type: ignore[attr-defined]


def _selected_code(view: object) -> str:
    from PySide6.QtCore import Qt

    table = view.results_table  # type: ignore[attr-defined]
    selected = table.selectionModel().selectedRows()
    assert len(selected) == 1
    item = table.item(selected[0].row(), 0)
    row = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
    return str(getattr(row, "stock_code", "") or "")


def _seed_main_profile_database(db_path: Path) -> None:
    """Seed only the three-stock fixture into the isolated app's initialized schema."""
    from decimal import Decimal

    from test_original_stock_ranking import DECISION_DATE as fixture_date
    from test_original_stock_ranking import STOCK_CODES, _dates

    expected_price_columns = {
        "日期",
        "證券代號",
        "證券名稱",
        "開盤價",
        "最高價",
        "最低價",
        "收盤價",
        "成交股數",
        "成交金額",
        "漲跌價差",
    }
    connection = sqlite3.connect(db_path)
    try:
        price_columns = {
            str(row[1]) for row in connection.execute('PRAGMA table_info("daily_prices")')
        }
        technical_columns = {
            str(row[1])
            for row in connection.execute('PRAGMA table_info("technical_indicators")')
        }
        assert expected_price_columns <= price_columns
        assert {"日期", "證券代號", "MA20", "MA60"} <= technical_columns
        for code in STOCK_CODES:
            for index, market_date in enumerate(_dates()):
                if code == "1101":
                    close = Decimal("4.80")
                    volume = 1000 + index
                elif code == "2317":
                    close = Decimal("180") + Decimal(index) * Decimal("0.15")
                    volume = 3000 + index * 7
                else:
                    close = Decimal("100") + Decimal(index) * Decimal("0.75")
                    volume = 1200 + index * 90
                open_price = close - Decimal("0.10")
                high = close + Decimal("0.50")
                low = close - Decimal("0.50")
                connection.execute(
                    'INSERT INTO daily_prices '
                    '("日期", "證券代號", "證券名稱", "開盤價", "最高價", '
                    '"最低價", "收盤價", "成交股數", "成交金額", "漲跌價差") '
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        market_date.isoformat(),
                        code,
                        f"Stock {code}",
                        float(open_price),
                        float(high),
                        float(low),
                        float(close),
                        volume,
                        float(close * volume),
                        0,
                    ),
                )
            connection.execute(
                'INSERT INTO technical_indicators '
                '("日期", "證券代號", "MA20", "MA60") VALUES (?, ?, ?, ?)',
                (fixture_date.isoformat(), code, "100", "95"),
            )
        connection.commit()
    finally:
        connection.close()


def _published_source_inventory(case: Path) -> dict[str, list[dict[str, object]]]:
    roots = {
        "daily_snapshot": case / "controlled-publisher" / "feature-snapshots",
        "original_ranking": case / "controlled-publisher" / "rankings",
    }
    inventory: dict[str, list[dict[str, object]]] = {}
    for source, root in roots.items():
        entries: list[dict[str, object]] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            payload = path.read_bytes()
            entries.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        assert entries, f"published source inventory is empty: {source}"
        inventory[source] = entries
    return inventory


def _load_report(window: object, expected_code: str, expected_context: object) -> object:
    report_view = window.stock_research_workspace.report_view  # type: ignore[attr-defined]
    errors: list[str] = []
    report_view.reportFailed.connect(errors.append)
    try:
        _wait_for(
            window._f4_app,  # type: ignore[attr-defined]
            lambda: (
                report_view._loaded_report is not None
                and str(report_view._loaded_report.stock_code).strip() == expected_code
                and report_view._loaded_context_identity
                == report_view._context_identity(report_view.context, expected_code)
                and (report_view._active_worker is None or not report_view._active_worker.isRunning())
            ),
            f"actual stock report for {expected_code}",
            timeout_seconds=18,
        )
    except AssertionError as exc:
        raise AssertionError(
            f"{exc}; status={report_view.status_label.text()!r}; "
            f"errors={errors!r}; context={report_view.context!r}; "
            f"loaded={getattr(report_view._loaded_report, 'stock_code', None)!r}; "
            f"expected_source={getattr(expected_context, 'source_kind', None)!r}"
        ) from exc
    return report_view._loaded_report


def _assert_return_to_exact_source(window: object, context: object, expected_hash: str) -> None:
    report_view = window.stock_research_workspace.report_view  # type: ignore[attr-defined]
    assert report_view.context.source_kind == context.source_kind
    report_view.return_button.click()
    window._f4_app.processEvents()  # type: ignore[attr-defined]
    daily = window.recommendation_view.daily_market_research_view  # type: ignore[attr-defined]
    assert daily._snapshot is not None
    assert daily._snapshot.manifest_sha256 == expected_hash
    assert _selected_code(daily) == STOCK_CODE
    rank_context = getattr(context, "rank_context", None)
    if rank_context is not None:
        assert daily._original_ranking is not None
        assert daily._original_ranking.manifest_sha256 == rank_context.source_hash
        assert daily._original_ranking.manifest_identity_sha256 == rank_context.rank_snapshot_id
        assert daily.sort_key_combo.currentData() == "original_strength_rank"
        selected_rank = next(
            row["rank"]
            for row in daily._original_ranking.rows
            if str(row["stock_code"]) == STOCK_CODE
        )
        assert selected_rank == rank_context.selected_rank


def _child_main(phase: str, case: Path) -> int:
    case = case.resolve()
    case.mkdir(parents=True, exist_ok=True)
    (case / "owned_child.json").write_text(
        json.dumps({"pid": os.getpid(), "parent_pid": os.getppid()}), encoding="utf-8"
    )
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    violations: list[dict[str, str]] = []
    writes: list[str] = []
    _install_isolation_guard(case, violations, writes)

    receipt: dict[str, object] = {
        "phase": phase,
        "pid": os.getpid(),
        "case": str(case),
        "status": "failed",
        "public_config": None if phase == "defaults" else {
            "daily_market_snapshot_root": str(case / "controlled-publisher" / "feature-snapshots"),
            "daily_market_snapshot_cohort_id": COHORT_ID,
            "original_stock_ranking_root": str(case / "controlled-publisher" / "rankings"),
        },
    }
    app = None
    window = None
    started = time.monotonic()
    try:
        if sys.platform == "win32":
            import platform

            def native_system_version(system="", release="", version="", supported_platforms=("win32",)):
                value = sys.getwindowsversion()
                return system, release, f"{value.major}.{value.minor}.{value.build}"

            platform._syscmd_ver = native_system_version

        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

        import ui_qt.main as main_module
        from app_module.daily_market_research_bookmark import (
            DailyMarketResearchBookmarkError,
            OriginalStockRankingBookmark,
            decode_daily_market_research_bookmark,
        )
        from app_module.stock_research_report_provider_adapters import CurrentRestatedMLRunRegistry

        main_module.project_root = case / "repository"
        main_module.CurrentRestatedMLRunRegistry = lambda: CurrentRestatedMLRunRegistry(
            repository_root=case / "repository"
        )

        # Configuration mistakes must be rejected before constructing QWidget/QApplication state.
        for invalid_kwargs in (
            {"daily_market_snapshot_root": case / "snapshot-only"},
            {"daily_market_snapshot_cohort_id": COHORT_ID},
            {"original_stock_ranking_root": case / "rank-only"},
            {
                "daily_market_snapshot_root": "",
                "daily_market_snapshot_cohort_id": COHORT_ID,
            },
            {
                "daily_market_snapshot_root": case / "empty-cohort",
                "daily_market_snapshot_cohort_id": " ",
            },
        ):
            try:
                main_module.MainWindow(**invalid_kwargs)
            except ValueError:
                pass
            else:
                raise AssertionError(f"partial public source config accepted: {invalid_kwargs}")

        app = QApplication([])
        main_module.apply_app_theme(app)
        if phase == "defaults":
            # Exercise the unchanged, no-argument manual/on-demand startup path.
            window = main_module.MainWindow()
        else:
            window = main_module.MainWindow(
                policy_config_path=case / "personal_policy.json",
                daily_market_snapshot_root=case / "controlled-publisher" / "feature-snapshots",
                daily_market_snapshot_cohort_id=COHORT_ID,
                original_stock_ranking_root=case / "controlled-publisher" / "rankings",
            )
        window._f4_app = app
        _wait_for(
            app,
            lambda: (
                getattr(getattr(window, "portfolio_view", None), "_refresh_worker", None)
                is None
                or not window.portfolio_view._refresh_worker.isRunning()
            ),
            "startup portfolio read to finish before controlled DB publish",
            timeout_seconds=10,
        )
        expected_workspaces = {definition.key for definition in main_module.WORKSPACE_DEFINITIONS}
        assert set(window.workspace_widgets) == expected_workspaces
        assert not [
            key for key, view in window.workspace_widgets.items() if isinstance(view, QLabel)
        ]
        assert window.config.profile == "test"
        assert Path(window.config.data_root).resolve().is_relative_to(case)
        assert Path(window.config.output_root).resolve().is_relative_to(case)
        if phase == "defaults":
            default_snapshot_root = (
                ROOT / "output" / "research_snapshots" / "daily_market"
            ).resolve()
            assert window.daily_market_research_screener_service.snapshot_root == default_snapshot_root
            assert window.stock_research_report_service.daily_market_snapshot_cohort_id is None
            assert window.stock_research_report_service.daily_market_snapshot_repository is None
        else:
            assert window.daily_market_research_screener_service.snapshot_root == (
                case / "controlled-publisher" / "feature-snapshots"
            ).resolve()
            assert window.daily_market_research_screener_service.original_ranking_repository.ranking_root == (
                case / "controlled-publisher" / "rankings"
            ).resolve()
            assert window.stock_research_report_service.daily_market_snapshot_cohort_id == COHORT_ID
            assert window.stock_research_report_service.daily_market_snapshot_repository.output_root.resolve() == (
                case / "controlled-publisher" / "feature-snapshots"
            ).resolve()
        daily = window.recommendation_view.daily_market_research_view
        if phase == "defaults":
            assert daily.cohort_id_input.text() == "daily-market-research"
        else:
            assert daily.cohort_id_input.text() == COHORT_ID
        receipt["workspace_types"] = {
            key: type(view).__name__ for key, view in window.workspace_widgets.items()
        }
        receipt["resolved_config"] = {
            "profile": window.config.profile,
            "data_root": str(window.config.data_root),
            "output_root": str(window.config.output_root),
            "db_file": str(window.config.db_file),
        }
        receipt["service_config"] = {
            "daily_market_snapshot_root": str(window.daily_market_research_screener_service.snapshot_root),
            "daily_market_snapshot_cohort_id": daily.cohort_id_input.text(),
            "stock_report_snapshot_root": (
                str(window.stock_research_report_service.daily_market_snapshot_repository.output_root.resolve())
                if window.stock_research_report_service.daily_market_snapshot_repository is not None
                else None
            ),
            "stock_report_cohort_id": window.stock_research_report_service.daily_market_snapshot_cohort_id,
            "original_stock_ranking_root": str(window.daily_market_research_screener_service.original_ranking_repository.ranking_root),
            "feature_cache_max_entries": window.stock_research_report_service.daily_market_feature_snapshot_service._max_entries,
        }
        assert window.watchlist_service is not None
        assert window.stock_research_report_service.daily_market_feature_snapshot_service._max_entries == 4

        if phase == "setup":
            import test_original_stock_ranking as ranking_fixture
            from data_module.db_manager import DBManager

            (case / "controlled-publisher").mkdir(parents=True, exist_ok=True)
            # MainWindow itself does not eagerly create SQLite schema. Initialize
            # the normal isolated DBManager schema after actual app startup, then
            # add only the MA columns required by the existing publisher fixture.
            db_manager = DBManager(window.config)
            db_manager.ensure_columns("technical_indicators", ["MA20", "MA60"])
            isolated_db = Path(window.config.db_file).resolve()
            patcher = pytest.MonkeyPatch()
            try:
                source_type = ranking_fixture.SQLiteDailyMarketSnapshotSource
                patcher.setattr(
                    ranking_fixture,
                    "_create_database",
                    lambda _scratch_db: _seed_main_profile_database(isolated_db),
                )
                patcher.setattr(
                    ranking_fixture,
                    "SQLiteDailyMarketSnapshotSource",
                    lambda _scratch_db, selected_date: source_type(
                        isolated_db, selected_date
                    ),
                )
                market = ranking_fixture.market.__wrapped__(
                    case / "controlled-publisher", patcher
                )
                market["db_path"] = isolated_db
                rank_publication = ranking_fixture._publish(
                    market, period="day", direction="strong"
                )
            finally:
                patcher.undo()
            assert rank_publication["status"] == "published", rank_publication
            snapshot = market["snapshot"]
            snapshot_hash = snapshot.manifest_sha256
            published_inventory = _published_source_inventory(case)
            receipt["source_identities"] = {
                "daily": {
                    "cohort_id": snapshot.cohort_id,
                    "decision_date": snapshot.decision_date.isoformat(),
                    "manifest_identity": snapshot.manifest_identity_sha256,
                    "manifest_sha256": snapshot_hash,
                },
                "rank": {
                    "period": "day",
                    "direction": "strong",
                    "rank_snapshot_id": rank_publication["manifest_identity_sha256"],
                    "manifest_sha256": rank_publication["manifest_sha256"],
                    "parent_snapshot_sha256": snapshot_hash,
                    "method": "StockScreener._build_stock_screen_from_frame",
                },
            }

            assert daily.cohort_id_input.text() == COHORT_ID
            window._select_main_workspace("recommendation")
            window.recommendation_view.result_source_tabs.setCurrentWidget(daily)
            _wait_for(
                app,
                lambda: (
                    daily._snapshot is not None
                    and daily._original_ranking is not None
                    and not daily._original_ranking_pending
                    and (daily._worker is None or not daily._worker.isRunning())
                ),
                "actual daily view first-open snapshot and original-rank query",
            )
            assert daily._snapshot.manifest_sha256 == snapshot_hash
            assert daily._original_ranking.manifest_sha256 == rank_publication["manifest_sha256"]
            assert len(daily._snapshot.stock_snapshots) <= 16

            # Exercise report review -> exact return -> source-page v1 bookmark -> reopen -> return.
            QMessageBox.question = staticmethod(lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes)
            daily_bookmark_signal: list[object] = []
            daily.bookmarkSaved.connect(daily_bookmark_signal.append)
            _select_code(daily, STOCK_CODE)
            daily.open_selected_stock_button.click()
            daily_context = window.stock_research_workspace.report_view.context
            assert daily_context.source_kind == "daily_market_research_snapshot"
            daily_report = _load_report(window, STOCK_CODE, daily_context)
            assert daily_report.stock_code == STOCK_CODE
            _assert_return_to_exact_source(window, daily_context, snapshot_hash)
            assert daily.bookmark_selected_research_button.isEnabled(), {
                "worker_running": bool(daily._worker and daily._worker.isRunning()),
                "worker_present": daily._worker is not None,
                "watchlist_present": daily.watchlist_service is not None,
                "snapshot_present": daily._snapshot is not None,
                "sort_key": daily.sort_key_combo.currentData(),
                "selected_code": _selected_code(daily),
                "shutting_down": daily._shutting_down,
                "status": daily.status_label.text(),
            }
            daily.bookmark_selected_research_button.click()
            assert len(daily_bookmark_signal) == 1
            daily_bookmark = daily_bookmark_signal[0]
            daily_payload = daily_bookmark.to_dict()
            assert daily_payload["schema_version"] == "daily-market-research-bookmark.v1"
            assert decode_daily_market_research_bookmark(daily_payload).bookmark_id == daily_bookmark.bookmark_id
            daily.open_selected_stock_button.click()
            _load_report(window, STOCK_CODE, daily_context)
            _assert_return_to_exact_source(window, daily_context, snapshot_hash)

            # Exercise the actual original-rank report action, saving an immutable v2 pin.
            rank_index = daily.sort_key_combo.findData("original_strength_rank")
            assert rank_index >= 0
            daily.sort_key_combo.setCurrentIndex(rank_index)
            _wait_for(
                app,
                lambda: (
                    daily._original_ranking is not None
                    and daily._original_ranking.manifest_sha256 == rank_publication["manifest_sha256"]
                    and not daily._original_ranking_pending
                ),
                "rank-aware source view",
            )
            _select_code(daily, STOCK_CODE)
            daily.open_selected_stock_button.click()
            rank_context = window.stock_research_workspace.report_view.context
            assert rank_context.source_kind == "original_stock_ranking"
            assert rank_context.rank_context.source_hash == rank_publication["manifest_sha256"]
            rank_report = _load_report(window, STOCK_CODE, rank_context)
            assert rank_report.original_ranking.status == "available"
            source_rank_row = next(
                row
                for row in daily._original_ranking.rows
                if str(row["stock_code"]) == STOCK_CODE
            )
            assert rank_report.original_ranking.rank == source_rank_row["rank"]
            assert window.stock_research_workspace.report_view.favorite_original_ranking_button.isEnabled()
            window.stock_research_workspace.report_view.favorite_original_ranking_button.click()
            saved_items = window.watchlist_service.get_stocks()
            rank_items = [
                item["research_bookmark"]
                for item in saved_items
                if isinstance(item.get("research_bookmark"), dict)
                and item["research_bookmark"].get("schema_version")
                == "daily-market-research-bookmark.v2"
            ]
            assert len(rank_items) == 1
            rank_payload = rank_items[0]
            assert rank_payload["context"]["rank_context"]["source_hash"] == rank_publication["manifest_sha256"]
            rank_bookmark = decode_daily_market_research_bookmark(rank_payload)
            assert isinstance(rank_bookmark, OriginalStockRankingBookmark)
            assert rank_bookmark.context.rank_context.parent_snapshot_hash == snapshot_hash
            unsupported = dict(rank_payload)
            unsupported["schema_version"] = "daily-market-research-bookmark.v3"
            with pytest.raises(DailyMarketResearchBookmarkError) as version_error:
                decode_daily_market_research_bookmark(unsupported)
            assert version_error.value.code == "bookmark_schema_mismatch"
            _assert_return_to_exact_source(window, rank_context, snapshot_hash)

            # Cancel an actual immutable-source read after the reader has returned;
            # the previously accepted snapshot remains the last-good UI state.
            last_good = daily._snapshot
            actual_read = daily.service.read_snapshot
            read_finished = __import__("threading").Event()
            release = __import__("threading").Event()

            def delayed_actual_read(cohort_id, selected_date, *, cancel_callback=None):
                result = actual_read(
                    cohort_id, selected_date, cancel_callback=cancel_callback
                )
                read_finished.set()
                while not release.wait(0.01):
                    if cancel_callback is not None and cancel_callback():
                        return {"cancelled": True}
                return result

            daily.service.read_snapshot = delayed_actual_read
            try:
                daily.reload_published_snapshot()
                _wait_for(app, read_finished.is_set, "reader reaches cancellation checkpoint")
                daily.cancel_button.click()
                release.set()
                _wait_for(
                    app,
                    lambda: daily._worker is None or not daily._worker.isRunning(),
                    "cancelled snapshot reader to finish",
                )
            finally:
                release.set()
                daily.service.read_snapshot = actual_read
            assert daily._snapshot is last_good
            current_generation = daily._operation_generation
            daily._on_operation_finished(current_generation - 1, "read", object())
            assert daily._snapshot is last_good
            final_setup_inventory = _published_source_inventory(case)
            assert final_setup_inventory == published_inventory

            receipt["bookmark_identities"] = {
                "daily_v1": {
                    "bookmark_id": daily_bookmark.bookmark_id,
                    "schema_version": daily_payload["schema_version"],
                    "stock_code": daily_bookmark.stock_code,
                    "source_snapshot_sha256": daily_payload["source_snapshot_hash"],
                },
                "rank_v2": {
                    "bookmark_id": rank_bookmark.bookmark_id,
                    "schema_version": rank_payload["schema_version"],
                    "stock_code": rank_bookmark.stock_code,
                    "rank_snapshot_id": rank_bookmark.context.rank_context.rank_snapshot_id,
                    "source_hash": rank_bookmark.context.rank_context.source_hash,
                },
            }
            receipt["safety"] = {
                "supported_bookmark_schemas": [daily_payload["schema_version"], rank_payload["schema_version"]],
                "unsupported_schema_result": version_error.value.code,
                "cancel_preserved_last_good": daily._snapshot is last_good,
                "stale_callback_preserved_last_good": daily._snapshot is last_good,
                "bounded_cohort_stock_limit": 16,
                "feature_snapshot_cache_max_entries": window.stock_research_report_service.daily_market_feature_snapshot_service._max_entries,
                "publisher_capacity_probe_simulated": True,
                "single_active_reader": daily._worker is None or not daily._worker.isRunning(),
                "published_source_inventory_unchanged": final_setup_inventory == published_inventory,
            }
            receipt["published_source_inventory"] = {
                "after_controlled_publish": published_inventory,
                "after_ui_read_bookmark_return_cancel": final_setup_inventory,
            }
        elif phase == "readback":
            state = json.loads((case / "setup_receipt.json").read_text(encoding="utf-8"))
            current_inventory = _published_source_inventory(case)
            assert current_inventory == state["published_source_inventory"]["after_controlled_publish"]
            identities = state["bookmark_identities"]
            daily_id = identities["daily_v1"]["bookmark_id"]
            daily_context = window.watchlist_service.get_research_bookmark_context(
                daily_id, db_path=window.config.db_file
            )
            assert daily_context is not None
            assert daily_context.source_kind == "daily_market_research_snapshot"
            assert daily_context.daily_snapshot_cohort_id == COHORT_ID
            assert daily_context.source_snapshot_hash == state["source_identities"]["daily"]["manifest_sha256"]
            daily_report = window.stock_research_report_service.read_report(
                daily_context.stock_code, context=daily_context
            )
            assert daily_report.stock_code == identities["daily_v1"]["stock_code"]

            rank_id = identities["rank_v2"]["bookmark_id"]
            rank_result = window.watchlist_service.get_rank_research_bookmark_context(
                rank_id, db_path=window.config.db_file
            )
            assert rank_result.succeeded, rank_result.to_dict()
            rank_context = rank_result.context
            assert rank_context is not None and rank_context.rank_context is not None
            assert rank_context.source_kind == "original_stock_ranking_bookmark"
            assert rank_context.rank_context.rank_snapshot_id == identities["rank_v2"]["rank_snapshot_id"]
            assert rank_context.rank_context.source_hash == identities["rank_v2"]["source_hash"]
            assert rank_context.rank_context.parent_snapshot_hash == state["source_identities"]["daily"]["manifest_sha256"]
            rank_report = window.stock_research_report_service.read_report(
                rank_context.stock_code, context=rank_context
            )
            assert rank_report.stock_code == identities["rank_v2"]["stock_code"]
            assert rank_report.original_ranking.status == "available"
            assert rank_report.original_ranking.rank_manifest_sha256 == identities["rank_v2"]["source_hash"]
            assert rank_report.original_ranking.rank_manifest_identity_sha256 == identities["rank_v2"]["rank_snapshot_id"]
            receipt["fresh_process_readback"] = {
                "daily_v1": {
                    "bookmark_id": daily_id,
                    "source_kind": daily_context.source_kind,
                    "source_snapshot_sha256": daily_context.source_snapshot_hash,
                    "report_stock_code": daily_report.stock_code,
                },
                "rank_v2": {
                    "bookmark_id": rank_id,
                    "source_kind": rank_context.source_kind,
                    "rank_snapshot_id": rank_context.rank_context.rank_snapshot_id,
                    "source_hash": rank_context.rank_context.source_hash,
                    "report_stock_code": rank_report.stock_code,
                    "report_rank_manifest_sha256": rank_report.original_ranking.rank_manifest_sha256,
                    "report_rank_manifest_identity_sha256": rank_report.original_ranking.rank_manifest_identity_sha256,
                },
                "published_source_inventory_unchanged": current_inventory
                == state["published_source_inventory"]["after_controlled_publish"],
            }
        elif phase == "defaults":
            state = json.loads((case / "setup_receipt.json").read_text(encoding="utf-8"))
            current_inventory = _published_source_inventory(case)
            assert current_inventory == state["published_source_inventory"]["after_controlled_publish"]
            identities = state["bookmark_identities"]
            before = window.watchlist_service.get_stocks()
            bookmark_payloads_before = sorted(
                json.dumps(item["research_bookmark"], sort_keys=True, ensure_ascii=False)
                for item in before
                if isinstance(item.get("research_bookmark"), dict)
                and item["research_bookmark"].get("schema_version")
                in {"daily-market-research-bookmark.v1", "daily-market-research-bookmark.v2"}
            )
            by_id = {
                item["research_bookmark"].get("bookmark_id"): item["research_bookmark"]
                for item in before
                if isinstance(item.get("research_bookmark"), dict)
            }
            assert identities["daily_v1"]["bookmark_id"] in by_id
            assert identities["rank_v2"]["bookmark_id"] in by_id
            assert by_id[identities["daily_v1"]["bookmark_id"]]["source_snapshot_hash"] == (
                state["source_identities"]["daily"]["manifest_sha256"]
            )
            assert by_id[identities["rank_v2"]["bookmark_id"]]["context"]["rank_context"]["source_hash"] == (
                identities["rank_v2"]["source_hash"]
            )
            after = window.watchlist_service.get_stocks()
            bookmark_payloads_after = sorted(
                json.dumps(item["research_bookmark"], sort_keys=True, ensure_ascii=False)
                for item in after
                if isinstance(item.get("research_bookmark"), dict)
                and item["research_bookmark"].get("schema_version")
                in {"daily-market-research-bookmark.v1", "daily-market-research-bookmark.v2"}
            )
            assert bookmark_payloads_after == bookmark_payloads_before
            receipt["default_startup"] = {
                "no_arg_mainwindow": True,
                "default_daily_snapshot_root": str(window.daily_market_research_screener_service.snapshot_root),
                "default_daily_cohort_input": daily.cohort_id_input.text(),
                "custom_source_read_started": bool(daily._worker and daily._worker.isRunning()),
                "bookmarks_preserved": bookmark_payloads_after == bookmark_payloads_before,
                "published_source_inventory_unchanged": current_inventory
                == state["published_source_inventory"]["after_controlled_publish"],
                "source_inventory_sha256": hashlib.sha256(
                    json.dumps(current_inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "bookmark_ids": [
                    identities["daily_v1"]["bookmark_id"],
                    identities["rank_v2"]["bookmark_id"],
                ],
            }
        else:
            raise AssertionError(f"unknown child phase: {phase}")

        receipt["status"] = "passed"
    except Exception:
        receipt["error"] = traceback.format_exc()
    finally:
        if violations:
            receipt["status"] = "failed"
            receipt["isolation_violations"] = violations
        receipt["write_paths"] = sorted(set(writes))
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
        if window is not None and app is not None:
            try:
                startup_deadline = time.monotonic() + 8
                while time.monotonic() < startup_deadline:
                    app.processEvents()
                    refresh_worker = getattr(
                        getattr(window, "portfolio_view", None), "_refresh_worker", None
                    )
                    if refresh_worker is None or not refresh_worker.isRunning():
                        break
                    time.sleep(0.01)
                window.close()
                finish_timer = QTimer()
                finish_timer.setInterval(50)
                finish_timer.timeout.connect(
                    lambda: app.quit() if window._shutdown_close_finalizing else None
                )
                finish_timer.start()
                deadline_timer = QTimer()
                deadline_timer.setSingleShot(True)
                deadline_timer.timeout.connect(app.quit)
                deadline_timer.start(25_000)
                app.exec()
                if not window._shutdown_close_finalizing:
                    raise AssertionError("actual MainWindow did not complete cooperative shutdown")
                workers, background = main_module.MainWindow._request_shutdown_dependencies(
                    window, send_cancel=False
                )
                assert not workers and not background
                main_module._drain_qt_deferred_deletes(app, (window,))
                if receipt.get("status") == "passed" and phase in {"setup", "readback", "defaults"}:
                    expected_inventory = (
                        receipt["published_source_inventory"]["after_controlled_publish"]
                        if phase == "setup"
                        else json.loads((case / "setup_receipt.json").read_text(encoding="utf-8"))[
                            "published_source_inventory"
                        ]["after_controlled_publish"]
                    )
                    after_close_inventory = _published_source_inventory(case)
                    assert after_close_inventory == expected_inventory
                    receipt["source_inventory_recheck_after_close"] = {
                        "unchanged": True,
                        "inventory": after_close_inventory,
                    }
            except Exception:
                receipt["status"] = "failed"
                receipt["shutdown_error"] = traceback.format_exc()
        target = case / f"{phase}_receipt.json"
        target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({key: receipt.get(key) for key in ("phase", "status", "error", "shutdown_error", "elapsed_seconds")}, ensure_ascii=False), flush=True)
    return 0 if receipt.get("status") == "passed" and not violations else 1


def _run_child(phase: str, case: Path) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "DATA_ROOT": str(case / "data"),
        "OUTPUT_ROOT": str(case / "output"),
        "PROFILE": "test",
        "QT_QPA_PLATFORM": "offscreen",
        "MPLCONFIGDIR": str(case / "matplotlib"),
        "APPDATA": str(case / "appdata"),
        "LOCALAPPDATA": str(case / "localappdata"),
        "USERPROFILE": str(case / "userprofile"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--f4-child", phase, str(case)],
        cwd=case,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def test_f4_actual_app_bookmark_round_trip_and_fresh_process_readback() -> None:
    artifact_root = ROOT / "output" / "qa" / "f4_release_integration_20261005" / "integration_agent"
    artifact_root.mkdir(parents=True, exist_ok=True)
    case = artifact_root / f"run-{uuid.uuid4().hex[:12]}"
    case.mkdir(parents=True, exist_ok=False)
    phase_receipts: dict[str, object] = {}
    try:
        setup = _run_child("setup", case)
        phase_receipts["setup"] = {"exit_code": setup.returncode}
        if setup.returncode != 0:
            phase_receipts["setup"]["output_tail"] = (setup.stdout + setup.stderr)[-12000:]  # type: ignore[index]
            pytest.fail(f"isolated actual MainWindow setup phase failed: {setup.stdout}\n{setup.stderr}")
        setup_receipt = json.loads((case / "setup_receipt.json").read_text(encoding="utf-8"))
        assert setup_receipt["status"] == "passed"

        readback = _run_child("readback", case)
        phase_receipts["readback"] = {"exit_code": readback.returncode}
        if readback.returncode != 0:
            phase_receipts["readback"]["output_tail"] = (readback.stdout + readback.stderr)[-12000:]  # type: ignore[index]
            pytest.fail(f"fresh-process bookmark readback failed: {readback.stdout}\n{readback.stderr}")
        readback_receipt = json.loads((case / "readback_receipt.json").read_text(encoding="utf-8"))
        assert readback_receipt["status"] == "passed"
        assert setup_receipt["bookmark_identities"]["daily_v1"]["bookmark_id"] == readback_receipt["fresh_process_readback"]["daily_v1"]["bookmark_id"]
        assert setup_receipt["bookmark_identities"]["rank_v2"]["bookmark_id"] == readback_receipt["fresh_process_readback"]["rank_v2"]["bookmark_id"]
        assert setup_receipt["bookmark_identities"]["rank_v2"]["source_hash"] == readback_receipt["fresh_process_readback"]["rank_v2"]["source_hash"]

        defaults = _run_child("defaults", case)
        phase_receipts["defaults"] = {"exit_code": defaults.returncode}
        if defaults.returncode != 0:
            phase_receipts["defaults"]["output_tail"] = (defaults.stdout + defaults.stderr)[-12000:]  # type: ignore[index]
            pytest.fail(f"no-arg default MainWindow phase failed: {defaults.stdout}\n{defaults.stderr}")
        defaults_receipt = json.loads((case / "defaults_receipt.json").read_text(encoding="utf-8"))
        assert defaults_receipt["status"] == "passed"
        assert defaults_receipt["default_startup"]["no_arg_mainwindow"] is True
        assert defaults_receipt["default_startup"]["bookmarks_preserved"] is True
        assert defaults_receipt["default_startup"]["custom_source_read_started"] is False

        final_receipt = {
            "status": "passed",
            "head": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip(),
            "changed_paths": ["ui_qt/main.py", "tests/test_f4_research_release_integration.py"],
            "rollback_scope": "Reverse only this package's ui_qt/main.py hunk and new integration test file; preserve all unrelated/shared worktree changes.",
            "phase_receipts": phase_receipts,
            "actual_mainwindow_setup": {
                "workspace_types": setup_receipt["workspace_types"],
                "service_config": setup_receipt["service_config"],
                "source_identities": setup_receipt["source_identities"],
                "bookmark_identities": setup_receipt["bookmark_identities"],
            "safety": setup_receipt["safety"],
            "published_source_inventory": setup_receipt["published_source_inventory"],
        },
        "fresh_child_readback": readback_receipt["fresh_process_readback"],
        "no_arg_default_startup": defaults_receipt["default_startup"],
        "source_inventory_recheck_after_close": {
            phase: json.loads((case / f"{phase}_receipt.json").read_text(encoding="utf-8"))["source_inventory_recheck_after_close"]
            for phase in ("setup", "readback", "defaults")
        },
            "fixture": "tests/test_original_stock_ranking.market.__wrapped__ (3 securities x 120 rows; controlled publisher)",
            "bookmark_entry_paths": {
                "daily_v1": "report review -> exact return -> visible daily source bookmark button -> reopen report -> exact return",
                "rank_v2": "rank report -> visible favorite rank button -> exact return",
            },
            "fixture_case_retained": True,
            "retained_source_pins": True,
        }
        receipt_path = artifact_root / "f4_actual_app_round_trip_receipt.json"
        receipt_path.write_text(json.dumps(final_receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        assert setup_receipt["safety"]["cancel_preserved_last_good"]
        assert setup_receipt["safety"]["stale_callback_preserved_last_good"]
        assert setup_receipt["safety"]["unsupported_schema_result"] == "bookmark_schema_mismatch"
        assert (case / "setup_receipt.json").is_file()
    except Exception:
        failure = {
            "status": "failed",
            "phase_receipts": phase_receipts,
            "case": str(case),
        }
        (artifact_root / "f4_actual_app_round_trip_failure.json").write_text(
            json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        raise


if __name__ == "__main__" and "--f4-child" in sys.argv:
    child_parser = argparse.ArgumentParser()
    child_parser.add_argument("--f4-child", nargs=2, metavar=("PHASE", "CASE"))
    child_args, _ = child_parser.parse_known_args()
    raise SystemExit(_child_main(child_args.f4_child[0], Path(child_args.f4_child[1])))
