from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import pytest

from data_module import excluded_daily_price_revision as exclusions
from scripts import repair_excluded_daily_prices as repair
from test_excluded_daily_price_revision import (
    _make_database,
    _prepare_test_run,
    _write_evidence_archive,
)


_LEGACY_FIELDS = (
    "keys",
    "closed_dates",
    "plan_sha256",
    "receipt_sha256",
    "receipt_path",
    "acquired_at",
    "source_start_date",
    "evidence_archive_relative",
    "market_plan_sha256",
)


@pytest.fixture
def synthetic_data_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "FA_Data"
    root.mkdir(parents=True)
    return root, _write_evidence_archive(root)


def _prepared_run(
    root: Path,
    archive: Path,
    run_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    database_path = _make_database(root, run_id)
    run_dir = _prepare_test_run(root, archive, database_path, monkeypatch, run_id)
    return database_path, run_dir


def _applied_run(
    root: Path,
    archive: Path,
    run_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    database_path, run_dir = _prepared_run(root, archive, run_id, monkeypatch)
    repair.apply(
        run_dir / "plan.json",
        repair.file_hash(run_dir / "plan.json"),
        repair.CONFIRM,
    )
    return database_path, run_dir


def _create_directory_link(link: Path, target: Path) -> None:
    """在 Windows 建立實際 junction；其他平台使用目錄 symlink 對照。"""
    if os.name == "nt":
        command = f"mklink /J {link} {target}"
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", command],
            capture_output=True,
            check=False,
            text=True,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
    else:
        link.symlink_to(target, target_is_directory=True)


def _remove_directory_link(link: Path) -> None:
    if os.name == "nt":
        os.rmdir(link)
    else:
        link.unlink()


def test_prepare_only_writer_tree_is_a_valid_empty_control(
    synthetic_data_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, archive = synthetic_data_root
    database_path, run_dir = _prepared_run(root, archive, "prepare-only", monkeypatch)

    assert {path.name for path in run_dir.iterdir()} == {"before_rows.json", "plan.json"}
    assert exclusions.load_exclusion_evidence(database_path) == []


def test_missing_receipt_root_is_a_valid_empty_control(
    synthetic_data_root: tuple[Path, Path],
) -> None:
    root, _archive = synthetic_data_root
    database_path = _make_database(root, "missing-root")

    assert not (root / exclusions.RECEIPT_DIR).exists()
    assert exclusions.load_exclusion_evidence(database_path) == []


def test_unmarked_partial_writer_run_fails_closed(
    synthetic_data_root: tuple[Path, Path],
) -> None:
    root, _archive = synthetic_data_root
    database_path = _make_database(root, "partial-unmarked")
    run_dir = root / exclusions.RECEIPT_DIR / "partial-run"
    run_dir.mkdir(parents=True)
    (run_dir / "journal.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="未完成|標記|掃描"):
        exclusions.load_exclusion_evidence(database_path)


def test_formal_market_name_with_journal_only_fails_closed(
    synthetic_data_root: tuple[Path, Path],
) -> None:
    root, _archive = synthetic_data_root
    database_path = _make_database(root, "formal-market-journal-only")
    run_dir = root / exclusions.RECEIPT_DIR / "formal_market"
    run_dir.mkdir(parents=True)
    (run_dir / "journal.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="未完成|標記|prepare-only"):
        exclusions.load_exclusion_evidence(database_path)


def test_formal_market_name_with_partial_child_run_fails_closed(
    synthetic_data_root: tuple[Path, Path],
) -> None:
    root, _archive = synthetic_data_root
    database_path = _make_database(root, "formal-market-partial-child")
    child_run = root / exclusions.RECEIPT_DIR / "formal_market" / "partial-run"
    child_run.mkdir(parents=True)
    (child_run / "journal.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="未完成|標記|prepare-only"):
        exclusions.load_exclusion_evidence(database_path)


def test_formal_market_name_with_run_junction_fails_closed(
    synthetic_data_root: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    root, _archive = synthetic_data_root
    database_path = _make_database(root, "formal-market-run-junction")
    namespace = root / exclusions.RECEIPT_DIR / "formal_market"
    namespace.mkdir(parents=True)
    target = tmp_path / "market-run-target"
    target.mkdir()
    for name in ("plan.json", "journal.json", "receipt.json", "revision.json"):
        (target / name).write_text("{}", encoding="utf-8")
    _create_directory_link(namespace / "run-link", target)

    try:
        with pytest.raises(ValueError, match="未完成|標記|prepare-only"):
            exclusions.load_exclusion_evidence(database_path)
    finally:
        _remove_directory_link(namespace / "run-link")


def test_formal_market_name_with_prepare_only_files_remains_valid_empty(
    synthetic_data_root: tuple[Path, Path],
) -> None:
    root, _archive = synthetic_data_root
    database_path = _make_database(root, "formal-market-prepare-only")
    run_dir = root / exclusions.RECEIPT_DIR / "formal_market"
    run_dir.mkdir(parents=True)
    (run_dir / "before_rows.json").write_text("{}", encoding="utf-8")
    (run_dir / "plan.json").write_text("{}", encoding="utf-8")

    assert exclusions.load_exclusion_evidence(database_path) == []


def test_applied_writer_tree_preserves_the_nine_field_legacy_projection(
    synthetic_data_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, archive = synthetic_data_root
    database_path, _run_dir = _applied_run(root, archive, "applied-control", monkeypatch)

    evidence = exclusions.load_exclusion_evidence(database_path)
    assert len(evidence) == 1
    assert tuple(evidence[0]) == _LEGACY_FIELDS
    assert evidence[0]["keys"] == sorted(evidence[0]["keys"])
    assert evidence[0]["closed_dates"] == sorted(evidence[0]["closed_dates"])
    assert len(evidence[0]["keys"]) == 110
    assert exclusions.load_exclusions(database_path) == set(evidence[0]["keys"])
    assert exclusions.load_excluded_dates(database_path) == set(evidence[0]["closed_dates"])


def test_rolled_back_writer_tree_remains_empty_in_the_legacy_active_list(
    synthetic_data_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, archive = synthetic_data_root
    database_path, run_dir = _applied_run(root, archive, "rollback-control", monkeypatch)

    recovered = repair.recover(run_dir, rollback=True, confirm=repair.CONFIRM)

    assert recovered["state"] == "rolled_back"
    assert exclusions.load_exclusion_evidence(database_path) == []


def test_pending_writer_tree_fails_closed(
    synthetic_data_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, archive = synthetic_data_root
    database_path, run_dir = _prepared_run(root, archive, "pending-control", monkeypatch)
    write_receipt = repair._make_receipt

    def fail_before_applied_receipt(*args: object, **kwargs: object) -> dict[str, object]:
        state = args[3] if len(args) > 3 else kwargs.get("state")
        if state == "applied":
            raise OSError("合成 pending 控制：資料庫已提交但 receipt 尚未寫入")
        return write_receipt(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(repair, "_make_receipt", fail_before_applied_receipt)
    with pytest.raises(OSError, match="合成 pending 控制"):
        repair.apply(
            run_dir / "plan.json",
            repair.file_hash(run_dir / "plan.json"),
            repair.CONFIRM,
        )
    with pytest.raises(ValueError, match="進行中"):
        exclusions.load_exclusion_evidence(database_path)


def test_dangling_receipt_root_junction_is_not_reported_as_empty(
    synthetic_data_root: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    root, _archive = synthetic_data_root
    database_path = _make_database(root, "dangling-root")
    receipt_root = root / exclusions.RECEIPT_DIR
    receipt_root.parent.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "outside-empty"
    target.mkdir()
    _create_directory_link(receipt_root, target)
    target.rmdir()

    try:
        try:
            result = exclusions.load_exclusion_evidence(database_path)
        except (OSError, ValueError):
            return
        pytest.fail(f"失效的 receipt-root junction 被當成 EMPTY 接受：{result!r}")
    finally:
        _remove_directory_link(receipt_root)


def test_external_receipt_root_junction_is_not_reported_as_empty(
    synthetic_data_root: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    root, _archive = synthetic_data_root
    database_path = _make_database(root, "external-root")
    receipt_root = root / exclusions.RECEIPT_DIR
    receipt_root.parent.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "outside-receipts"
    target.mkdir()
    _create_directory_link(receipt_root, target)

    try:
        try:
            result = exclusions.load_exclusion_evidence(database_path)
        except (OSError, ValueError):
            return
        pytest.fail(f"超出資料根目錄的 receipt-root junction 被當成 EMPTY 接受：{result!r}")
    finally:
        _remove_directory_link(receipt_root)


def test_dangling_run_junction_is_not_reported_as_empty(
    synthetic_data_root: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    root, _archive = synthetic_data_root
    database_path = _make_database(root, "dangling-run")
    receipt_root = root / exclusions.RECEIPT_DIR
    receipt_root.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "removed-run-target"
    target.mkdir()
    run_link = receipt_root / "dangling-run"
    _create_directory_link(run_link, target)
    target.rmdir()

    try:
        try:
            result = exclusions.load_exclusion_evidence(database_path)
        except (OSError, ValueError):
            return
        pytest.fail(f"失效的 run junction 被當成 EMPTY 接受：{result!r}")
    finally:
        _remove_directory_link(run_link)


def test_receipt_root_permission_error_is_not_swallowed_as_empty(
    synthetic_data_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _archive = synthetic_data_root
    database_path = _make_database(root, "permission-control")
    receipt_root = root / exclusions.RECEIPT_DIR
    receipt_root.mkdir(parents=True, exist_ok=True)
    original_lstat = Path.lstat
    original_stat = Path.stat

    def deny_receipt_root(self: Path, *args: object, **kwargs: object):
        if self == receipt_root:
            raise PermissionError("合成 receipt-root 權限錯誤")
        return original_lstat(self, *args, **kwargs)  # type: ignore[arg-type]

    def deny_receipt_root_stat(self: Path, *args: object, **kwargs: object):
        if self == receipt_root:
            raise PermissionError("合成 receipt-root 權限錯誤")
        return original_stat(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "lstat", deny_receipt_root)
    monkeypatch.setattr(Path, "stat", deny_receipt_root_stat)
    with pytest.raises((OSError, ValueError), match="權限錯誤"):
        exclusions.load_exclusion_evidence(database_path)


def test_receipt_root_scandir_error_is_not_swallowed_as_empty(
    synthetic_data_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _archive = synthetic_data_root
    database_path = _make_database(root, "scandir-error")
    receipt_root = root / exclusions.RECEIPT_DIR
    receipt_root.mkdir(parents=True, exist_ok=True)
    original_scandir = os.scandir

    def deny_receipt_root_scandir(path: Any) -> Any:
        if Path(path) == receipt_root:
            raise PermissionError("合成 receipt-root scandir 權限錯誤")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", deny_receipt_root_scandir)
    with pytest.raises(ValueError, match="完整掃描|scandir 權限錯誤"):
        exclusions.load_exclusion_evidence(database_path)


def test_archive_manifest_is_hashed_and_parsed_from_the_same_bytes(
    synthetic_data_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, archive = synthetic_data_root
    database_path, _run_dir = _applied_run(root, archive, "archive-race", monkeypatch)
    archive_path = archive / "archive.json"
    original_bytes = archive_path.read_bytes()
    replacement = json.loads(original_bytes)
    replacement["archived_at"] = "2026-09-25T00:00:00+00:00"
    replacement_bytes = json.dumps(
        replacement,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    replacement_path = archive / "archive.swap.json"
    replacement_path.write_bytes(replacement_bytes)

    parsed_archive_hashes: list[str] = []
    first_hashed_bytes: list[bytes] = []
    original_read_bytes = Path.read_bytes
    original_json_loads = json.loads
    replaced = False

    def replace_after_archive_hash(self: Path) -> bytes:
        nonlocal replaced
        data = original_read_bytes(self)
        if self == archive_path and not replaced:
            replaced = True
            first_hashed_bytes.append(data)
            os.replace(replacement_path, archive_path)
        return data

    def observe_parsed_archive(data: str | bytes, *args: object, **kwargs: object):
        parsed = original_json_loads(data, *args, **kwargs)  # type: ignore[arg-type]
        if isinstance(parsed, dict) and "archived_at" in parsed and "files" in parsed:
            raw = data.encode("utf-8") if isinstance(data, str) else data
            parsed_archive_hashes.append(hashlib.sha256(raw).hexdigest())
        return parsed

    monkeypatch.setattr(Path, "read_bytes", replace_after_archive_hash)
    monkeypatch.setattr(json, "loads", observe_parsed_archive)
    try:
        evidence = exclusions.load_exclusion_evidence(database_path)
        assert evidence
        assert replaced
        assert hashlib.sha256(first_hashed_bytes[0]).hexdigest() == hashlib.sha256(
            original_bytes
        ).hexdigest()
        assert parsed_archive_hashes == [hashlib.sha256(first_hashed_bytes[0]).hexdigest()]
    finally:
        archive_path.write_bytes(original_bytes)
