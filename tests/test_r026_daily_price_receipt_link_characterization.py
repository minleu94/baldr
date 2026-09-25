"""R026 daily-price receipt 路徑連結的隔離安全特性測試。"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from data_module import excluded_daily_price_revision, formal_market_revision
from data_module import historical_session_revision
from data_module import ml_daily_price_revision_gate as gate


def _database_path(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data_root"
    database_path = data_root / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    database_path.write_bytes(b"synthetic isolated database placeholder")
    return data_root, database_path


def _receipt_bytes(source_date: str) -> bytes:
    payload = {
        "schema_version": gate.REPAIR_SCHEMA,
        "receipt_kind": "historical_price_spike_repair",
        "status": "applied",
        "source_date": source_date,
        "allowlist_count": 1,
        "rows": [{"symbol": "2330", "date": source_date}],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_receipt(path: Path, source_date: str = "2024-02-01") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_receipt_bytes(source_date))


def _isolate_other_revision_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    def allow(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(formal_market_revision, "assert_market_revision_safe", allow)
    monkeypatch.setattr(historical_session_revision, "assert_session_revision_safe", allow)
    monkeypatch.setattr(
        excluded_daily_price_revision,
        "assert_excluded_source_revision_safe",
        allow,
    )


def _check(
    database_path: Path,
    *,
    explicit_path: Path | None = None,
) -> dict[str, object] | None:
    return gate.check_daily_price_source_revision(
        database_path=database_path,
        decision_date="2024-01-23",
        symbols=["2330"],
        explicit_path=explicit_path,
    )


def _create_junction(link: Path, target: Path) -> None:
    assert sys.platform == "win32", "此特性測試需要 Windows 目錄 junction"
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    assert powershell is not None, "建立隔離 junction 需要 PowerShell"
    link.parent.mkdir(parents=True, exist_ok=True)

    def quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    script = (
        "$ErrorActionPreference='Stop'; "
        f"New-Item -ItemType Junction -Path {quote(str(link))} "
        f"-Target {quote(str(target))} | Out-Null"
    )
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    completed = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, (
        "隔離 junction 建立失敗；此環境不可把連結測試算作通過："
        f"{completed.stderr.strip()}"
    )


def _remove_junction(link: Path) -> None:
    link.rmdir()


def test_normal_absent_receipt_keeps_none_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    _, database_path = _database_path(tmp_path)

    assert _check(database_path) is None


def test_normal_in_root_receipt_still_blocks_relevant_pit_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    data_root, database_path = _database_path(tmp_path)
    receipt_path = data_root / gate.REPAIR_RECEIPT_RELATIVE_DIR / "receipt.json"
    _write_receipt(receipt_path, "2024-01-21")

    with pytest.raises(gate.DailyPriceSourceRevisionError, match="blocks this PIT prefix"):
        _check(database_path)


def test_internal_receipt_directory_junction_resolves_within_isolated_data_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    data_root, database_path = _database_path(tmp_path)
    internal_store = data_root / "internal_receipt_store"
    receipt_path = internal_store / "receipt.json"
    _write_receipt(receipt_path)
    receipt_dir = data_root / gate.REPAIR_RECEIPT_RELATIVE_DIR
    receipt_dir.parent.mkdir(parents=True, exist_ok=True)
    _create_junction(receipt_dir, internal_store)

    try:
        assert receipt_dir.is_symlink() is False
        assert receipt_dir.resolve() == internal_store.resolve()
        result = _check(database_path)
        assert result is not None
        assert result["checked_receipt_count"] == 1
        summaries = result["checked_receipts"]
        assert isinstance(summaries, list)
        assert summaries[0]["receipt_path"] == str(receipt_path.resolve())
    finally:
        _remove_junction(receipt_dir)


def test_internal_receipt_junction_retarget_during_read_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    data_root, database_path = _database_path(tmp_path)
    first_store = data_root / "receipt_store_a"
    second_store = data_root / "receipt_store_b"
    first_receipt = first_store / "receipt.json"
    _write_receipt(first_receipt)
    _write_receipt(second_store / "receipt.json")
    receipt_dir = data_root / gate.REPAIR_RECEIPT_RELATIVE_DIR
    receipt_dir.parent.mkdir(parents=True, exist_ok=True)
    _create_junction(receipt_dir, first_store)
    original_read_bytes = Path.read_bytes
    retargeted = False

    def retarget_before_read(path: Path) -> bytes:
        nonlocal retargeted
        if path == first_receipt.resolve() and not retargeted:
            _remove_junction(receipt_dir)
            _create_junction(receipt_dir, second_store)
            retargeted = True
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", retarget_before_read)
    try:
        with pytest.raises(
            gate.DailyPriceSourceRevisionError,
            match="changed during read",
        ):
            _check(database_path)
        assert retargeted is True
    finally:
        _remove_junction(receipt_dir)


@pytest.mark.parametrize("source_date", ["2024-02-01", "2024-01-21"])
def test_external_receipt_directory_junction_is_rejected_for_any_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_date: str,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    data_root, database_path = _database_path(tmp_path)
    outside_store = tmp_path / "outside_receipts"
    _write_receipt(outside_store / "receipt.json", source_date)
    receipt_dir = data_root / gate.REPAIR_RECEIPT_RELATIVE_DIR
    receipt_dir.parent.mkdir(parents=True, exist_ok=True)
    _create_junction(receipt_dir, outside_store)

    try:
        assert receipt_dir.is_symlink() is False
        assert receipt_dir.resolve() == outside_store.resolve()
        with pytest.raises(gate.DailyPriceSourceRevisionError, match="outside data root"):
            _check(database_path)
    finally:
        _remove_junction(receipt_dir)


def test_internal_explicit_directory_alias_is_deduplicated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    data_root, database_path = _database_path(tmp_path)
    receipt_dir = data_root / gate.REPAIR_RECEIPT_RELATIVE_DIR
    _write_receipt(receipt_dir / "receipt.json")
    alias = data_root / "receipt_alias"
    _create_junction(alias, receipt_dir)

    try:
        candidates = gate.source_revision_receipt_candidates(
            database_path=database_path,
            explicit_path=alias,
        )
        assert candidates == (receipt_dir / "receipt.json",)
        result = _check(database_path, explicit_path=alias)
        assert result is not None
        assert result["checked_receipt_count"] == 1
    finally:
        _remove_junction(alias)


def test_dangling_automatic_receipt_junction_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """自動搜尋根的 dangling junction 不得靜默視為沒有修訂。"""
    _isolate_other_revision_guards(monkeypatch)
    data_root, database_path = _database_path(tmp_path)
    outside_store = tmp_path / "removed_receipt_store"
    outside_store.mkdir()
    receipt_dir = data_root / gate.REPAIR_RECEIPT_RELATIVE_DIR
    receipt_dir.parent.mkdir(parents=True, exist_ok=True)
    _create_junction(receipt_dir, outside_store)

    try:
        outside_store.rmdir()
        assert receipt_dir.is_symlink() is False
        assert receipt_dir.exists() is False
        with pytest.raises(gate.DailyPriceSourceRevisionError, match="unresolved"):
            gate.source_revision_receipt_candidates(database_path=database_path)
        with pytest.raises(gate.DailyPriceSourceRevisionError):
            _check(database_path)
    finally:
        _remove_junction(receipt_dir)


def test_dangling_automatic_receipt_child_junction_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """存在但無目標的 receipt 子項不得被當成缺席。"""
    _isolate_other_revision_guards(monkeypatch)
    data_root, database_path = _database_path(tmp_path)
    receipt_dir = data_root / gate.REPAIR_RECEIPT_RELATIVE_DIR
    receipt_dir.mkdir(parents=True)
    outside_store = tmp_path / "removed_child_target"
    outside_store.mkdir()
    receipt_path = receipt_dir / "receipt.json"
    _create_junction(receipt_path, outside_store)

    try:
        outside_store.rmdir()
        assert receipt_path.exists() is False
        assert receipt_path.is_symlink() is False
        receipt_path.lstat()
        with pytest.raises(gate.DailyPriceSourceRevisionError, match="unresolved"):
            gate.source_revision_receipt_candidates(database_path=database_path)
        with pytest.raises(gate.DailyPriceSourceRevisionError):
            _check(database_path)
    finally:
        _remove_junction(receipt_path)


def test_explicit_dangling_receipt_junction_stays_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_other_revision_guards(monkeypatch)
    _, database_path = _database_path(tmp_path)
    outside_store = tmp_path / "removed_explicit_receipt_store"
    outside_store.mkdir()
    explicit_alias = tmp_path / "explicit_receipt_alias"
    _create_junction(explicit_alias, outside_store)

    try:
        outside_store.rmdir()
        with pytest.raises(gate.DailyPriceSourceRevisionError, match="receipt is missing"):
            _check(database_path, explicit_path=explicit_alias / "receipt.json")
    finally:
        _remove_junction(explicit_alias)
