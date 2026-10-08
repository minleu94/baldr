"""H20 UI 安全副本接線的合成端到端驗證。"""

from __future__ import annotations

import hashlib
from pathlib import Path
import socket
import sqlite3
from typing import Any, Mapping

import pytest


def _sqlite_file_group_pin(database: Path) -> tuple[tuple[str, object], ...]:
    result: list[tuple[str, object]] = []
    for role, suffix in (("main", ""), ("wal", "-wal"), ("shm", "-shm"), ("journal", "-journal")):
        path = database if not suffix else Path(str(database) + suffix)
        try:
            info = path.lstat()
        except FileNotFoundError:
            result.append((role, None))
            continue
        result.append((role, (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
            info.st_nlink,
            getattr(info, "st_ino", 0),
            info.st_mode,
            getattr(info, "st_file_attributes", 0),
        )))
    return tuple(result)


def _install_network_deny(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []

    def deny(*_args: object, **_kwargs: object) -> None:
        attempts.append("network")
        raise AssertionError("H20 合成讀取不得連線網路")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    return attempts


def test_secure_h20_cohort_selected_prepare_and_bookmark_use_one_operation_copy_each(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真實 source port、H20 readers 與 SQLite guard 共用隔離 fixture。"""

    import scripts.scheduled.run_personal_current_observed_h20_daily as runner
    from app_module.recommendation.personal_h20_read_session import PersonalH20ReadSession
    from app_module.recommendation.personal_h20_research_bookmark import (
        PersonalH20ResearchBookmark,
    )
    from app_module.recommendation.personal_h20_research_cohort import (
        PersonalH20ResearchSelection,
    )
    from scripts.scheduled import personal_h20_daily_hook as daily_hook
    from scripts.scheduled import personal_h20_sqlite_read_operation as operation_module
    from scripts.scheduled.personal_h20_bookmark_prepare import (
        prepare_personal_h20_research_bookmark,
    )
    from scripts.scheduled.personal_h20_bookmark_read_session import (
        read_personal_h20_research_bookmark_with_session,
    )
    from tests.test_ui_qt_h20_saved_source_journey import _build_saved_h20_store

    network_attempts = _install_network_deny(monkeypatch)
    saved = _build_saved_h20_store(tmp_path, monkeypatch)
    database = Path(saved["snapshot_database"]).resolve(strict=True)
    private_root = tmp_path / "explicit-h20-sqlite-read-root"
    private_root.mkdir()
    before = _sqlite_file_group_pin(database)
    private_root_text = str(private_root.resolve()).replace("\\", "/").casefold()
    database_text = str(database).replace("\\", "/").casefold()
    opened_targets: list[str] = []
    original_connect = sqlite3.connect

    def guarded_connect(target: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        target_text = str(target).replace("\\", "/").casefold()
        opened_targets.append(target_text)
        assert database_text not in target_text, "H20 verifier 不得連線原始 SQLite"
        assert "pinned-sqlite-" in target_text, target_text
        assert private_root_text in target_text, target_text
        return original_connect(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)

    actual_source_port = runner._source_port
    contract_verifier = saved["contract_fixture"]["verifier"]

    def public_ports(*, read_session_resolver=None):
        if read_session_resolver is None:
            source_verifier = actual_source_port
        else:
            def source_verifier(binding: Mapping[str, Any]) -> Mapping[str, Any]:
                return actual_source_port(
                    binding,
                    read_session_resolver=read_session_resolver,
                )
        return {
            "source_verifier": source_verifier,
            "contract_verifier": contract_verifier,
        }

    monkeypatch.setattr(runner, "personal_current_observed_h20_read_ports", public_ports)

    semantic_finishes: list[bool] = []
    operation_finishes: list[tuple[Any, ...]] = []
    original_semantic_finish = PersonalH20ReadSession.finish
    original_operation_type = operation_module.PersonalH20SQLiteReadOperation
    original_operation_finish = original_operation_type.finish

    def tracked_semantic_finish(self: PersonalH20ReadSession, *, finalizer=None) -> None:
        original_semantic_finish(self, finalizer=finalizer)
        semantic_finishes.append(True)

    def tracked_operation_finish(self: Any) -> tuple[Any, ...]:
        assert len(semantic_finishes) == len(operation_finishes) + 1
        bindings = original_operation_finish(self)
        operation_finishes.append(bindings)
        return bindings

    monkeypatch.setattr(PersonalH20ReadSession, "finish", tracked_semantic_finish)
    monkeypatch.setattr(original_operation_type, "finish", tracked_operation_finish)

    config_path = saved["activation"].config_path
    market_root = Path(saved["market_root"])
    progress: list[str] = []
    reference, cohort = daily_hook.read_personal_h20_product_cohort(
        config_path,
        market_root=market_root,
        sqlite_read_root=private_root,
        require_sqlite_copy=True,
        progress_callback=progress.append,
    )
    assert len(cohort.rows) == 1
    row = cohort.rows[0]
    assert row.symbol == "2382" and row.status == "available"
    assert row.gross_return_bp == 1234
    assert len(operation_finishes) == 1 and len(operation_finishes[-1]) == 1
    assert not list(private_root.iterdir())

    evidence = daily_hook.read_personal_h20_product_for_stock_with_session(
        config_path,
        stock_code="2382",
        market_root=market_root,
        expected_reference=reference,
        sqlite_read_root=private_root,
        require_sqlite_copy=True,
        progress_callback=progress.append,
    )
    assert evidence.status == "available" and evidence.gross_return_bp == 1234
    assert len(operation_finishes) == 2 and len(operation_finishes[-1]) == 1
    assert not list(private_root.iterdir())

    selection = PersonalH20ResearchSelection(
        manifest_sha256=cohort.manifest_sha256,
        candidate_id=cohort.candidate_id,
        contract_hash=cohort.contract_hash,
        cycle_id=cohort.cycle_id,
        symbol=row.symbol,
        sample_id=row.sample_id,
        prediction_id=row.prediction_id,
        capture_sha256=row.capture_sha256,
    )
    bookmark = prepare_personal_h20_research_bookmark(
        config_path,
        market_root=market_root,
        expected_reference=reference,
        selection=selection,
        sort_descending=False,
        scroll_position=11,
        sqlite_read_root=private_root,
        require_sqlite_copy=True,
        progress_callback=progress.append,
    )
    assert isinstance(bookmark, PersonalH20ResearchBookmark)
    assert bookmark.selected_row == selection
    assert len(operation_finishes) == 3 and len(operation_finishes[-1]) == 1
    assert not list(private_root.iterdir())

    state = read_personal_h20_research_bookmark_with_session(
        bookmark,
        config_path=config_path,
        market_root=market_root,
        sqlite_read_root=private_root,
        require_sqlite_copy=True,
        progress_callback=progress.append,
    )
    assert state.bookmark.to_dict() == bookmark.to_dict()
    assert state.selected_row.symbol == "2382"
    assert state.selected_row.status == "available"
    assert state.selected_row.gross_return_bp == 1234
    assert state.bookmark.sort_descending is False
    assert state.bookmark.scroll_position == 11
    assert len(operation_finishes) == 4 and all(len(item) == 1 for item in operation_finishes)
    assert len(semantic_finishes) == 4
    assert not list(private_root.iterdir())
    assert any("唯讀 SQLite 副本" in message for message in progress)
    assert opened_targets and all(private_root_text in target for target in opened_targets)
    assert _sqlite_file_group_pin(database) == before
    assert network_attempts == []


def test_secure_h20_ui_reader_requires_explicit_private_root_before_public_ports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.run_personal_current_observed_h20_daily as runner
    from scripts.scheduled.personal_h20_daily_hook import read_personal_h20_product_cohort

    calls: list[str] = []

    def forbidden_ports(*_args: object, **_kwargs: object) -> object:
        calls.append("ports")
        raise AssertionError("缺少私有 root 時不能讀來源 ports")

    monkeypatch.setattr(runner, "personal_current_observed_h20_read_ports", forbidden_ports)
    with pytest.raises(ValueError, match="personal_h20_sqlite_read_root_required"):
        read_personal_h20_product_cohort(
            tmp_path / "missing-activation.json",
            market_root=tmp_path / "market",
            require_sqlite_copy=True,
        )
    assert calls == []


def test_main_selected_h20_warm_projection_and_full_recheck_show_copy_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from threading import Event

    from tests.test_ui_qt_personal_h20_mainwindow_saved_journey import (
        _close_mainwindow,
        _double_click_selected_h20_row,
        _load_h20_list,
        _prepare_saved_h20_mainwindow,
        _wait_for,
    )

    entered = Event()
    release = Event()
    # 第一次完整名單讀取完成後，下鑽沿用 reader-issued view；只有明確
    # recheck 才會再建立唯讀 SQLite 副本並顯示複製進度。
    mode = {"block_cohort_operation_after": 2}
    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path,
        monkeypatch,
        source_mode=mode,
        source_entered=entered,
        source_release=release,
    )
    source = Path(saved["snapshot_database"])
    before = _sqlite_file_group_pin(source)
    workspace = None
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        assert mode.get("_cohort_operation_count") == 1
        signals = _double_click_selected_h20_row(app, window, widget)
        assert signals["research_requested"]
        workspace = window.stock_research_workspace
        assert workspace is not None
        _wait_for(
            app,
            lambda: getattr(workspace.personal_h20_saved_evidence, "status", None) == "available"
            and getattr(window, "_personal_h20_worker", None) is None
            and not workspace.personal_h20_saved_busy,
        )
        # warm double-click 完成個股投影，沒有重讀 SQLite／來源，也沒有重讀母體。
        assert mode.get("_warm_projection_count") == 1
        assert mode.get("_product_operation_count", 0) == 0
        assert mode.get("_cohort_operation_count") == 1

        workspace.personal_h20_saved_recheck_button.click()
        _wait_for(app, entered.is_set)
        assert mode.get("_cohort_operation_count") == 2
        assert mode.get("_product_operation_count", 0) == 0
        _wait_for(
            app,
            lambda: "唯讀 SQLite 副本" in window._personal_h20_loading_label.text(),
            timeout_seconds=15.0,
        )
        assert "未完成" in window._personal_h20_loading_label.text() or "已等待" in (
            window._personal_h20_loading_label.text()
        )
        release.set()
        _wait_for(
            app,
            lambda: getattr(workspace.personal_h20_saved_evidence, "status", None) == "available"
            and getattr(window, "_personal_h20_worker", None) is None
            and getattr(window, "_personal_h20_cohort_worker", None) is None
            and not workspace.personal_h20_saved_busy,
        )
        assert workspace is not None
        evidence = workspace.personal_h20_saved_evidence
        assert evidence is not None
        assert evidence.gross_return_bp == 1234
        assert mode.get("_cohort_operation_count") == 2
        assert mode.get("_warm_projection_count") == 2
        assert mode.get("_product_operation_count", 0) == 0
        assert network_attempts == []
        assert _sqlite_file_group_pin(source) == before
    finally:
        release.set()
        _close_mainwindow(app, window)
