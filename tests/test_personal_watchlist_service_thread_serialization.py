"""個人 Watchlist 同一服務實例的執行緒序列化回歸。"""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app_module.personal_watchlist_service import (
    PersonalWatchlistService,
    build_watchlist_service,
)
from app_module import watchlist_cow_activation
from app_module.watchlist_cow_activation import WatchlistCowActivationError


def _build_active_service(tmp_path: Path) -> PersonalWatchlistService:
    """建立真實的合成 JSON COW 來源並明示升級至個人 SQLite。"""

    market_root = tmp_path / "market"
    output_root = market_root / "output"
    source_path = output_root / "watchlist" / "default.json"
    source_path.parent.mkdir(parents=True)
    source_payload: dict[str, Any] = {
        "version": 1,
        "name": "合成個人清單",
        "description": "執行緒序列化測試資料",
        "created_at": "2026-10-07T09:00:00+00:00",
        "updated_at": "2026-10-07T09:00:00+00:00",
        "items": [
            {
                "stock_code": "2330",
                "stock_name": "合成股票甲",
                "added_at": "2026-10-07T09:00:00+00:00",
                "source": "manual",
                "notes": "synthetic fixture",
                "tags": ["fixture"],
            }
        ],
    }
    source_path.write_text(
        json.dumps(source_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    config = SimpleNamespace(
        data_root=market_root,
        output_root=output_root,
        personal_data_root=tmp_path / "personal",
        personal_watchlist_source=source_path,
    )

    service = build_watchlist_service(config)
    assert isinstance(service, PersonalWatchlistService)
    status = service.upgrade_to_repository()
    assert status.mode == "repository"
    assert service.get_stock_codes() == ["2330"]
    return service


def _source_and_activation_bytes(service: PersonalWatchlistService) -> dict[str, bytes]:
    """保存來源、啟用 marker、轉換收據與來源備份的原始 bytes。"""

    controls = service.control_paths
    return {
        "source": controls.source_path.read_bytes(),
        "activation_marker": controls.marker_path.read_bytes(),
        "conversion_receipt": controls.receipt_path.read_bytes(),
        "source_backup": controls.source_backup_path.read_bytes(),
    }


@pytest.mark.parametrize("reader_name", ["get_stocks", "get_research_bookmark"])
def test_same_instance_reader_waits_for_local_writer_and_preserves_cow_bytes(
    tmp_path: Path,
    reader_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一服務的讀取應等待本地 writer 完成，再沿公開 API 成功讀取。"""

    service = _build_active_service(tmp_path)
    pinned_bytes = _source_and_activation_bytes(service)
    writer_entered = threading.Event()
    release_writer = threading.Event()
    reader_started = threading.Event()
    reader_guard_entered = threading.Event()
    allow_reader_guard = threading.Event()
    reader_marker_lock_attempted = threading.Event()
    reader_finished = threading.Event()
    failures: queue.Queue[tuple[str, BaseException]] = queue.Queue()
    results: queue.Queue[object] = queue.Queue()

    def hold_writer_guard() -> None:
        try:
            with service._writer_guard():
                writer_entered.set()
                if not release_writer.wait(timeout=10):
                    raise TimeoutError("測試未能及時釋放 writer guard")
        except BaseException as exc:
            failures.put(("writer", exc))

    def read_through_public_api() -> None:
        reader_started.set()
        try:
            if reader_name == "get_stocks":
                results.put(service.get_stocks())
            else:
                results.put(service.get_research_bookmark("missing-synthetic-bookmark"))
        except BaseException as exc:
            failures.put(("reader", exc))
        finally:
            reader_finished.set()

    reader_thread = threading.Thread(
        target=read_through_public_api,
        name="personal-watchlist-reader-fixture",
    )
    original_service_guard = service._writer_guard

    def observe_service_guard_entry() -> Any:
        if threading.current_thread() is reader_thread:
            reader_guard_entered.set()
            if not allow_reader_guard.wait(timeout=10):
                raise TimeoutError("測試未能放行 reader guard")
        return original_service_guard()

    original_marker_lock = watchlist_cow_activation._marker_lock

    def observe_marker_lock_attempt(*args: Any, **kwargs: Any) -> Any:
        if threading.current_thread() is reader_thread:
            reader_marker_lock_attempted.set()
        return original_marker_lock(*args, **kwargs)

    monkeypatch.setattr(service, "_writer_guard", observe_service_guard_entry)
    monkeypatch.setattr(
        watchlist_cow_activation,
        "_marker_lock",
        observe_marker_lock_attempt,
    )

    writer_thread = threading.Thread(
        target=hold_writer_guard,
        name="personal-watchlist-writer-fixture",
    )
    writer_thread.start()
    reader_completed_before_release = False
    reader_reached_external_marker_lock = False
    try:
        assert writer_entered.wait(timeout=5), "writer guard 未成功取得 marker lock"
        reader_thread.start()
        assert reader_started.wait(timeout=5), "reader thread 未開始執行"
        assert reader_guard_entered.wait(timeout=5), "公開讀取未進入服務 guard"
        allow_reader_guard.set()
        reader_reached_external_marker_lock = reader_marker_lock_attempted.wait(
            timeout=2
        )
        reader_completed_before_release = reader_finished.is_set()
    finally:
        allow_reader_guard.set()
        release_writer.set()
        writer_thread.join(timeout=10)
        if reader_thread.ident is not None:
            reader_thread.join(timeout=10)

    assert not writer_thread.is_alive(), "writer thread 未安全結束"
    assert not reader_thread.is_alive(), "reader thread 未安全結束"
    assert _source_and_activation_bytes(service) == pinned_bytes
    assert not service.control_paths.lock_path.exists()

    failure_details: list[str] = []
    while not failures.empty():
        role, error = failures.get_nowait()
        failure_details.append(f"{role}: {type(error).__name__}: {error}")
    assert (
        not reader_completed_before_release
        and not reader_reached_external_marker_lock
        and not failure_details
    ), (
        "同一服務的 reader 必須等待本地 writer 釋放 lock 後再成功；"
        "reader 不應在本地序列器前碰撞 COW marker；"
        f"reader 在釋放前完成={reader_completed_before_release}，"
        f"marker lock 嘗試={reader_reached_external_marker_lock}，"
        f"錯誤={failure_details}"
    )

    result = results.get_nowait()
    if reader_name == "get_stocks":
        assert isinstance(result, list)
        assert [row["stock_code"] for row in result] == ["2330"]
    else:
        assert result is None


def test_another_service_instance_still_rejects_a_held_activation_lock(
    tmp_path: Path,
) -> None:
    """另一服務實例不共用本地序列器，仍由 COW marker lock fail closed。"""

    service = _build_active_service(tmp_path)
    other_service = build_watchlist_service(service.config)
    assert isinstance(other_service, PersonalWatchlistService)
    pinned_bytes = _source_and_activation_bytes(service)

    with service._writer_guard():
        with pytest.raises(WatchlistCowActivationError) as exc_info:
            other_service.get_stocks()

    assert exc_info.value.code == "active_writer"
    assert _source_and_activation_bytes(service) == pinned_bytes
    assert not service.control_paths.lock_path.exists()


def test_same_thread_nested_guard_remains_rejected_by_marker_protocol(
    tmp_path: Path,
) -> None:
    """RLock 不得讓同一執行緒的巢狀 writer 越過 marker guard。"""

    service = _build_active_service(tmp_path)
    pinned_bytes = _source_and_activation_bytes(service)

    with service._writer_guard():
        with pytest.raises(WatchlistCowActivationError) as exc_info:
            service.get_stocks()

    assert exc_info.value.code == "active_writer"
    assert _source_and_activation_bytes(service) == pinned_bytes
    assert not service.control_paths.lock_path.exists()
