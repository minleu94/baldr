from __future__ import annotations

from datetime import date
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from data_module.contracts.source_revision import (
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
)
from data_module.historical_session_revision import (
    RECEIPT_DIR,
    _plan,
    assert_session_revision_safe,
)


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    data_root = tmp_path / "data_root"
    sqlite_dir = data_root / "sqlite"
    sqlite_dir.mkdir(parents=True)
    database_path = sqlite_dir / "twstock.db"
    database_path.write_bytes(b"synthetic database placeholder")
    return data_root, database_path, data_root / RECEIPT_DIR


def _encoded(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _write_run(
    database_path: Path,
    receipt_root: Path,
    run_path: str,
    *,
    state: str = "applied",
    plan_state: str | None = None,
) -> Path:
    run_dir = receipt_root / run_path
    run_dir.mkdir(parents=True)
    database_identity = str(database_path.resolve())
    plan: dict[str, object] = {
        "schema_version": "historical-session-repair.v1",
        "database_path": database_identity,
        "dates": ["20240102", "20240103"],
        "source_start_date": "2024-01-02",
        "source_end_date": "2024-01-03",
        "rows": [],
    }
    plan_bytes = _encoded(plan)
    (run_dir / "plan.json").write_bytes(plan_bytes)
    plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    marker: dict[str, object] = {
        "schema_version": "historical-session-revision.v1",
        "database_path": database_identity,
        "historical_pit": False,
        "plan_sha256": plan_sha256,
        "state": state,
    }
    receipt_state = plan_state or state
    if state in {"applied", "rolled_back"}:
        receipt_name = "receipt.json" if state == "applied" else "rollback.json"
        receipt = {
            "state": receipt_state,
            "plan_sha256": plan_sha256,
            "dates": plan["dates"],
        }
        receipt_bytes = _encoded(receipt)
        (run_dir / receipt_name).write_bytes(receipt_bytes)
        marker["receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    marker_bytes = _encoded(marker)
    (run_dir / "revision.json").write_bytes(marker_bytes)
    return run_dir


def _collect(database_path: Path, cutoff: date):
    from data_module.historical_session_revision import (
        collect_session_revision_evidence,
    )

    return collect_session_revision_evidence(database_path, cutoff)


def _run_role(run_path: str) -> str:
    encoded = base64.urlsafe_b64encode(run_path.encode("utf-8")).decode("ascii")
    return "run_" + encoded.rstrip("=")


def test_empty_receipt_root_and_complete_empty_scan_are_explicit(tmp_path: Path) -> None:
    _, database_path, receipt_root = _paths(tmp_path)

    absent = _collect(database_path, date(2024, 1, 1))
    assert absent.namespace is SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION
    assert absent.presence is SourceEvidencePresenceV1.EMPTY
    assert absent.files == ()
    assert_session_revision_safe(database_path, date(2024, 1, 1))

    receipt_root.mkdir(parents=True)
    empty = _collect(database_path, date(2024, 1, 1))
    assert empty.presence is SourceEvidencePresenceV1.EMPTY
    assert empty.files == ()
    assert_session_revision_safe(database_path, date(2024, 1, 1))


def test_applied_chain_captures_exact_bytes_and_preserves_cutoff_and_plan_abi(
    tmp_path: Path,
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    run_path = "修復-run01"
    run_dir = _write_run(database_path, receipt_root, run_path)
    marker_path = run_dir / "revision.json"

    evidence = _collect(database_path, date(2024, 1, 1))
    assert evidence.presence is SourceEvidencePresenceV1.PRESENT
    expected_names = ("revision.json", "plan.json", "receipt.json")
    expected_roles = {f"{_run_role(run_path)}/{name}" for name in expected_names}
    actual = {item.role_id: item.sha256 for item in evidence.files}
    assert set(actual) == expected_roles
    for name in expected_names:
        assert actual[f"{_run_role(run_path)}/{name}"] == hashlib.sha256(
            (run_dir / name).read_bytes()
        ).hexdigest()

    marker, plan = _plan(marker_path, database_path)
    assert marker["state"] == "applied"
    assert plan["dates"] == ["20240102", "20240103"]
    assert_session_revision_safe(database_path, date(2024, 1, 1))
    with pytest.raises(ValueError, match="historical session source revision blocks"):
        assert_session_revision_safe(database_path, date(2024, 1, 2))
    with pytest.raises(ValueError, match="historical session source revision blocks"):
        _collect(database_path, date(2024, 1, 2))


def test_pending_is_present_and_blocks_only_from_source_start(tmp_path: Path) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    _write_run(database_path, receipt_root, "pending", state="pending")

    evidence = _collect(database_path, date(2024, 1, 1))
    assert evidence.presence is SourceEvidencePresenceV1.PRESENT
    assert len(evidence.files) == 2
    assert_session_revision_safe(database_path, date(2024, 1, 1))
    with pytest.raises(ValueError, match="historical session source revision blocks"):
        _collect(database_path, date(2024, 1, 2))


def test_rolled_back_is_present_and_keeps_existing_json_validation(tmp_path: Path) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    run_path = "rolled-back"
    run_dir = _write_run(database_path, receipt_root, run_path, state="rolled_back")

    evidence = _collect(database_path, date(2024, 1, 2))
    assert evidence.presence is SourceEvidencePresenceV1.PRESENT
    expected_roles = {
        f"{_run_role(run_path)}/revision.json",
        f"{_run_role(run_path)}/plan.json",
        f"{_run_role(run_path)}/rollback.json",
    }
    assert {item.role_id for item in evidence.files} == expected_roles
    rollback = next(item for item in evidence.files if item.role_id.endswith("/rollback.json"))
    assert rollback.sha256 == hashlib.sha256((run_dir / "rollback.json").read_bytes()).hexdigest()
    assert_session_revision_safe(database_path, date(2024, 1, 2))

    payload = json.loads((run_dir / "rollback.json").read_text(encoding="utf-8"))
    assert "schema_version" not in payload


def test_marker_parse_and_sha_use_the_same_captured_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    run_dir = _write_run(database_path, receipt_root, "atomic-swap")
    marker_path = run_dir / "revision.json"
    captured = marker_path.read_bytes()
    replacement = json.loads(captured.decode("utf-8"))
    replacement["schema_version"] = "unsupported-after-read"
    replacement_path = run_dir / "replacement.tmp"
    replacement_path.write_bytes(_encoded(replacement))
    original_read_bytes = Path.read_bytes
    replaced = False

    def read_then_replace(path: Path) -> bytes:
        nonlocal replaced
        payload = original_read_bytes(path)
        if path == marker_path and not replaced:
            os.replace(replacement_path, marker_path)
            replaced = True
        return payload

    monkeypatch.setattr(Path, "read_bytes", read_then_replace)
    evidence = _collect(database_path, date(2024, 1, 1))

    marker_sha = next(
        item.sha256 for item in evidence.files if item.role_id.endswith("/revision.json")
    )
    assert replaced
    assert marker_sha == hashlib.sha256(captured).hexdigest()
    assert marker_path.read_bytes() != captured


def test_later_invalid_chain_fails_without_returning_partial_evidence(
    tmp_path: Path,
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    _write_run(database_path, receipt_root, "a-valid")
    bad_run = _write_run(database_path, receipt_root, "z-invalid")
    (bad_run / "plan.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="歷史交易日修訂證據無法驗證"):
        _collect(database_path, date(2024, 1, 1))


def test_role_identity_uses_lexical_run_path_not_order_or_file_hash(
    tmp_path: Path,
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    for run_name in ("修復-run01", "z-run"):
        _write_run(database_path, receipt_root, run_name)

    before = _collect(database_path, date(2024, 1, 1))
    before_by_role = {item.role_id: item.sha256 for item in before.files}
    assert tuple(item.role_id for item in before.files) == tuple(
        sorted(before_by_role)
    )
    assert len(before_by_role) == 6
    for name in ("修復-run01", "z-run"):
        assert all(
            f"{_run_role(name)}/{filename}" in before_by_role
            for filename in ("revision.json", "plan.json", "receipt.json")
        )
    assert before_by_role[f"{_run_role('修復-run01')}/plan.json"] == before_by_role[
        f"{_run_role('z-run')}/plan.json"
    ]

    _write_run(database_path, receipt_root, "a-run")
    after = _collect(database_path, date(2024, 1, 1))
    after_by_role = {item.role_id: item.sha256 for item in after.files}
    assert len(after_by_role) == 9
    assert all(after_by_role[role] == digest for role, digest in before_by_role.items())


def test_incomplete_scan_permission_error_is_not_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    receipt_root.mkdir(parents=True)
    import data_module.historical_session_revision as session_revision

    original_scandir = os.scandir

    def fail_scan(path: str | os.PathLike[str]):
        if Path(path) == receipt_root.resolve():
            raise PermissionError("synthetic scan denial")
        return original_scandir(path)

    monkeypatch.setattr(session_revision.os, "scandir", fail_scan)
    with pytest.raises(ValueError, match="歷史交易日修訂證據無法驗證"):
        _collect(database_path, date(2024, 1, 1))


def _create_junction(link: Path, target: Path) -> bool:
    if sys.platform != "win32":
        return False
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        return False

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
    return completed.returncode == 0


def _require_windows_junction(link: Path, target: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows junction containment 合約")
    assert _create_junction(link, target), "隔離 TEMP junction 建立失敗"


def test_outside_receipt_root_junction_fails_closed(tmp_path: Path) -> None:
    data_root, database_path, _ = _paths(tmp_path)
    outside = tmp_path / "outside-output"
    outside.mkdir()
    link = data_root / "output"
    _require_windows_junction(link, outside)

    try:
        assert not link.is_symlink()
        assert link.resolve() == outside.resolve()
        with pytest.raises(ValueError, match="歷史交易日修訂證據無法驗證"):
            _collect(database_path, date(2024, 1, 1))
    finally:
        link.rmdir()


def test_dangling_receipt_root_junction_fails_closed(tmp_path: Path) -> None:
    data_root, database_path, _ = _paths(tmp_path)
    target = tmp_path / "receipt-target"
    target.mkdir()
    link = data_root / "output"
    _require_windows_junction(link, target)
    target.rmdir()

    try:
        with pytest.raises(ValueError, match="歷史交易日修訂證據無法驗證"):
            _collect(database_path, date(2024, 1, 1))
    finally:
        link.rmdir()


def test_outside_run_and_dangling_run_junctions_fail_closed(tmp_path: Path) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    receipt_root.mkdir(parents=True)
    outside_run = tmp_path / "outside-run"
    _write_run(database_path, outside_run.parent, outside_run.name)
    link = receipt_root / "outside-alias"
    _require_windows_junction(link, outside_run)

    try:
        with pytest.raises(ValueError, match="歷史交易日修訂證據無法驗證"):
            _collect(database_path, date(2024, 1, 1))
    finally:
        link.rmdir()

    target = tmp_path / "dangling-run-target"
    target.mkdir()
    dangling = receipt_root / "dangling-alias"
    _require_windows_junction(dangling, target)
    target.rmdir()
    try:
        with pytest.raises(ValueError, match="歷史交易日修訂證據無法驗證"):
            _collect(database_path, date(2024, 1, 1))
    finally:
        dangling.rmdir()


def test_duplicate_run_junction_fails_but_internal_alias_keeps_lexical_role(
    tmp_path: Path,
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    real_run = _write_run(database_path, receipt_root, "real-run")
    alias = receipt_root / "alias-run"
    _require_windows_junction(alias, real_run)

    try:
        with pytest.raises(ValueError, match="歷史交易日修訂證據無法驗證"):
            _collect(database_path, date(2024, 1, 1))
    finally:
        alias.rmdir()

    nested_run = _write_run(database_path, receipt_root / "nested", "run-甲")
    internal_alias = receipt_root / "internal-alias"
    _require_windows_junction(internal_alias, nested_run)
    try:
        evidence = _collect(database_path, date(2024, 1, 1))
        expected = {
            f"{_run_role(run_name)}/{name}"
            for run_name in ("real-run", "internal-alias")
            for name in ("revision.json", "plan.json", "receipt.json")
        }
        assert {item.role_id for item in evidence.files} == expected
        assert internal_alias.resolve() == nested_run.resolve()
        assert not internal_alias.is_symlink()
    finally:
        internal_alias.rmdir()


def test_run_junction_retarget_during_read_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    target_a = _write_run(database_path, receipt_root / "nested", "run-a")
    target_b = _write_run(database_path, receipt_root / "nested", "run-b")
    alias = receipt_root / "alias-run"
    _require_windows_junction(alias, target_a)
    marker_path = alias / "revision.json"
    original_read_bytes = Path.read_bytes
    switched = False

    def read_then_retarget(path: Path) -> bytes:
        nonlocal switched
        payload = original_read_bytes(path)
        if path == marker_path and not switched:
            alias.rmdir()
            assert _create_junction(alias, target_b)
            switched = True
        return payload

    monkeypatch.setattr(Path, "read_bytes", read_then_retarget)
    try:
        with pytest.raises(ValueError, match="歷史交易日修訂證據無法驗證"):
            _collect(database_path, date(2024, 1, 1))
        assert switched
    finally:
        monkeypatch.setattr(Path, "read_bytes", original_read_bytes)
        alias.rmdir()
