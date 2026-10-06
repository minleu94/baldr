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

from data_module.formal_market_revision import RECEIPT_DIR, assert_market_revision_safe
from data_module.contracts.source_revision import (
    SourceEvidenceNamespaceV1,
    ValidatedNamespaceEvidenceV1,
)


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    data_root = tmp_path / "data_root"
    sqlite_dir = data_root / "sqlite"
    sqlite_dir.mkdir(parents=True)
    database_path = sqlite_dir / "twstock.db"
    database_path.write_bytes(b"synthetic database placeholder")
    receipt_root = data_root / RECEIPT_DIR
    return data_root, database_path, receipt_root


def _write_run(
    database_path: Path,
    receipt_root: Path,
    run_id: str,
    *,
    state: str = "applied",
    rollback_bytes: bytes = b'{"state":"rolled_back"}',
) -> Path:
    run_dir = receipt_root / run_id
    run_dir.mkdir(parents=True)
    database_identity = str(database_path.resolve())
    plan = {
        "schema_version": "formal-market-repair.v1",
        "database_path": database_identity,
        "source_start_date": "2024-01-02",
        "source_end_date": "2024-01-31",
    }
    plan_bytes = json.dumps(plan, sort_keys=True).encode("utf-8")
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    journal_bytes = json.dumps(
        {"schema_version": "formal-market-repair.v1", "plan_sha256": plan_sha},
        sort_keys=True,
    ).encode("utf-8")
    marker: dict[str, object] = {
        "schema_version": "formal-market-revision.v1",
        "database_path": database_identity,
        "source_start_date": "2024-01-02",
        "source_end_date": "2024-01-31",
        "state": state,
    }
    if state == "applied":
        receipt_bytes = json.dumps(
            {"schema_version": "formal-market-repair.v1", "plan_sha256": plan_sha},
            sort_keys=True,
        ).encode("utf-8")
        (run_dir / "receipt.json").write_bytes(receipt_bytes)
        marker["receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    elif state == "rolled_back":
        (run_dir / "rollback.json").write_bytes(rollback_bytes)
        marker["rollback_sha256"] = hashlib.sha256(rollback_bytes).hexdigest()
    (run_dir / "plan.json").write_bytes(plan_bytes)
    (run_dir / "journal.json").write_bytes(journal_bytes)
    (run_dir / "revision.json").write_text(
        json.dumps(marker, sort_keys=True), encoding="utf-8"
    )
    return run_dir


def _collect(
    database_path: Path, cutoff: date
) -> ValidatedNamespaceEvidenceV1:
    from data_module.formal_market_revision import collect_market_revision_evidence

    return collect_market_revision_evidence(database_path, cutoff)


def _write_json(path: Path, payload: dict[str, object]) -> bytes:
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    path.write_bytes(encoded)
    return encoded


def _run_token(run_id: str) -> str:
    encoded = base64.urlsafe_b64encode(run_id.encode("utf-8")).decode("ascii")
    return "run_" + encoded.rstrip("=")


def test_market_evidence_empty_and_applied_keep_legacy_cutoff_abi(tmp_path: Path) -> None:
    _, database_path, receipt_root = _paths(tmp_path)

    empty = _collect(database_path, date(2024, 1, 1))
    assert empty.namespace is SourceEvidenceNamespaceV1.MARKET_REVISION
    assert empty.presence.value == "empty"
    assert empty.files == ()
    assert_market_revision_safe(database_path, date(2024, 1, 1))
    receipt_root.mkdir(parents=True)
    complete_empty_scan = _collect(database_path, date(2024, 1, 1))
    assert complete_empty_scan.presence.value == "empty"
    assert complete_empty_scan.files == ()

    run_id = "修訂-run"
    run_dir = _write_run(database_path, receipt_root, run_id)
    present = _collect(database_path, date(2024, 1, 1))
    assert present.presence.value == "present"
    expected_roles = {
        f"{_run_token(run_id)}/{name}"
        for name in ("revision.json", "journal.json", "plan.json", "receipt.json")
    }
    by_role = {item.role_id: item.sha256 for item in present.files}
    assert set(by_role) == expected_roles
    for role_id, digest in by_role.items():
        filename = role_id.rsplit("/", 1)[1]
        assert digest == hashlib.sha256((run_dir / filename).read_bytes()).hexdigest()
    assert_market_revision_safe(database_path, date(2024, 1, 1))
    with pytest.raises(ValueError, match="historical PIT"):
        assert_market_revision_safe(database_path, date(2024, 1, 2))
    with pytest.raises(ValueError, match="historical PIT"):
        _collect(database_path, date(2024, 1, 2))


def test_rolled_back_is_present_and_rollback_remains_hash_link_only(
    tmp_path: Path,
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    run_id = "rollback"
    rollback_bytes = b"not JSON; existing guard verifies only its hash"
    run_dir = _write_run(
        database_path,
        receipt_root,
        run_id,
        state="rolled_back",
        rollback_bytes=rollback_bytes,
    )

    evidence = _collect(database_path, date(2099, 1, 1))

    assert evidence.presence.value == "present"
    assert {item.role_id for item in evidence.files} == {
        f"{_run_token(run_id)}/{name}"
        for name in ("revision.json", "journal.json", "plan.json", "rollback.json")
    }
    rollback_record = next(
        item for item in evidence.files if item.role_id.endswith("/rollback.json")
    )
    assert rollback_record.sha256 == hashlib.sha256(rollback_bytes).hexdigest()
    assert_market_revision_safe(database_path, date(2099, 1, 1))


def test_pending_before_start_is_present_and_cutoff_block_stays_fail_closed(
    tmp_path: Path,
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    run_id = "pending"
    _write_run(database_path, receipt_root, run_id, state="pending")

    evidence = _collect(database_path, date(2024, 1, 1))
    assert evidence.presence.value == "present"
    assert len(evidence.files) == 3
    assert_market_revision_safe(database_path, date(2024, 1, 1))
    with pytest.raises(ValueError, match="historical PIT"):
        _collect(database_path, date(2024, 1, 2))


def test_marker_parse_and_hash_use_the_same_captured_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    run_dir = _write_run(database_path, receipt_root, "swap")
    marker_path = run_dir / "revision.json"
    captured_marker = marker_path.read_bytes()
    replacement = json.loads(captured_marker.decode("utf-8"))
    replacement["schema_version"] = "unsupported-after-capture"
    replacement_path = run_dir / "replacement.tmp"
    replacement_path.write_text(json.dumps(replacement), encoding="utf-8")
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

    marker_record = next(
        item for item in evidence.files if item.role_id.endswith("/revision.json")
    )
    assert replaced
    assert marker_record.sha256 == hashlib.sha256(captured_marker).hexdigest()
    assert marker_path.read_bytes() != captured_marker


def test_run_role_ids_do_not_depend_on_order_and_encode_unicode_path(
    tmp_path: Path,
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    unicode_run = "修訂-甲"
    _write_run(database_path, receipt_root, unicode_run)
    _write_run(database_path, receipt_root, "z-run")
    first = _collect(database_path, date(2024, 1, 1))
    first_roles = {item.role_id for item in first.files}
    assert tuple(item.role_id for item in first.files) == tuple(sorted(first_roles))
    first_hashes = {item.role_id: item.sha256 for item in first.files}
    for filename in ("revision.json", "journal.json", "plan.json", "receipt.json"):
        assert first_hashes[f"{_run_token(unicode_run)}/{filename}"] == first_hashes[
            f"{_run_token('z-run')}/{filename}"
        ]

    _write_run(database_path, receipt_root, "a-run")
    second = _collect(database_path, date(2024, 1, 1))
    second_roles = {item.role_id for item in second.files}

    assert {role for role in first_roles if _run_token("a-run") not in role} <= second_roles
    assert f"{_run_token(unicode_run)}/revision.json" in first_roles
    assert _run_token(unicode_run) != _run_token("z-run")
    assert len(first_roles) == 8
    assert len(second_roles) == 12

    _, reverse_database, reverse_receipts = _paths(tmp_path / "reverse")
    _write_run(reverse_database, reverse_receipts, "a-run")
    _write_run(reverse_database, reverse_receipts, "z-run")
    _write_run(reverse_database, reverse_receipts, unicode_run)
    reverse = _collect(reverse_database, date(2024, 1, 1))
    assert tuple(item.role_id for item in reverse.files) == tuple(
        item.role_id for item in second.files
    )


def test_invalid_later_run_fails_without_returning_partial_evidence(
    tmp_path: Path,
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    _write_run(database_path, receipt_root, "a-valid")
    bad_dir = _write_run(database_path, receipt_root, "z-invalid")
    (bad_dir / "journal.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="無法驗證"):
        _collect(database_path, date(2024, 1, 1))


@pytest.mark.parametrize("member", ("plan", "journal", "receipt"))
def test_unknown_child_schema_fails_closed_after_hash_links_are_recomputed(
    tmp_path: Path, member: str
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    run_dir = _write_run(database_path, receipt_root, f"unknown-{member}")
    plan_path = run_dir / "plan.json"
    journal_path = run_dir / "journal.json"
    receipt_path = run_dir / "receipt.json"
    marker_path = run_dir / "revision.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    marker = json.loads(marker_path.read_text(encoding="utf-8"))

    payloads = {"plan": plan, "journal": journal, "receipt": receipt}
    payloads[member]["schema_version"] = "unsupported-formal-market-repair.v999"
    if member == "plan":
        plan_bytes = _write_json(plan_path, plan)
        plan_sha = hashlib.sha256(plan_bytes).hexdigest()
        journal["plan_sha256"] = plan_sha
        _write_json(journal_path, journal)
        receipt["plan_sha256"] = plan_sha
        receipt_bytes = _write_json(receipt_path, receipt)
        marker["receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
        _write_json(marker_path, marker)
    elif member == "journal":
        _write_json(journal_path, journal)
    else:
        receipt_bytes = _write_json(receipt_path, receipt)
        marker["receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
        _write_json(marker_path, marker)

    with pytest.raises(ValueError, match="無法驗證"):
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


def test_outside_root_junction_is_rejected_before_legacy_guard_returns(
    tmp_path: Path,
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    receipt_root.mkdir(parents=True)
    outside_run = tmp_path / "outside" / "run"
    _write_run(database_path, outside_run.parent, outside_run.name)
    link = receipt_root / "alias"
    if not _create_junction(link, outside_run):
        pytest.skip("此 Windows 環境無法建立隔離 TEMP junction")

    try:
        assert link.resolve() == outside_run.resolve()
        assert not link.is_symlink()
        with pytest.raises(ValueError, match="無法驗證"):
            assert_market_revision_safe(database_path, date(2024, 1, 1))
    finally:
        link.rmdir()


def test_dangling_receipt_root_junction_is_not_empty(
    tmp_path: Path,
) -> None:
    data_root, database_path, _ = _paths(tmp_path)
    target = tmp_path / "receipt-target"
    target.mkdir()
    link = data_root / "output"
    if not _create_junction(link, target):
        pytest.skip("此 Windows 環境無法建立隔離 TEMP junction")

    try:
        target.rmdir()
        with pytest.raises(ValueError, match="無法驗證"):
            _collect(database_path, date(2024, 1, 1))
    finally:
        link.rmdir()


def test_outside_root_receipt_ancestor_junction_is_rejected(
    tmp_path: Path,
) -> None:
    data_root, database_path, _ = _paths(tmp_path)
    outside_output = tmp_path / "outside-output"
    outside_output.mkdir()
    link = data_root / "output"
    if not _create_junction(link, outside_output):
        pytest.skip("此 Windows 環境無法建立隔離 TEMP junction")

    try:
        with pytest.raises(ValueError, match="無法驗證"):
            _collect(database_path, date(2024, 1, 1))
    finally:
        link.rmdir()


def test_dangling_run_junction_is_not_empty(tmp_path: Path) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    receipt_root.mkdir(parents=True)
    target = tmp_path / "run-target"
    target.mkdir()
    link = receipt_root / "dangling-run"
    if not _create_junction(link, target):
        pytest.skip("此 Windows 環境無法建立隔離 TEMP junction")

    try:
        target.rmdir()
        with pytest.raises(ValueError, match="無法驗證"):
            _collect(database_path, date(2024, 1, 1))
    finally:
        link.rmdir()


def test_outside_root_run_junction_without_marker_is_rejected(
    tmp_path: Path,
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    receipt_root.mkdir(parents=True)
    outside_run = tmp_path / "outside-empty-run"
    outside_run.mkdir()
    link = receipt_root / "external-empty-run"
    if not _create_junction(link, outside_run):
        pytest.skip("此 Windows 環境無法建立隔離 TEMP junction")

    try:
        with pytest.raises(ValueError, match="無法驗證"):
            _collect(database_path, date(2024, 1, 1))
    finally:
        link.rmdir()


def test_two_run_roles_resolving_to_the_same_directory_fail_closed(
    tmp_path: Path,
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    run_dir = _write_run(database_path, receipt_root, "real-run")
    alias = receipt_root / "alias-run"
    if not _create_junction(alias, run_dir):
        pytest.skip("此 Windows 環境無法建立隔離 TEMP junction")

    try:
        with pytest.raises(ValueError, match="無法驗證"):
            _collect(database_path, date(2024, 1, 1))
    finally:
        alias.rmdir()


def test_single_internal_run_junction_uses_lexical_role_and_is_accepted(
    tmp_path: Path,
) -> None:
    _, database_path, receipt_root = _paths(tmp_path)
    nested_receipts = receipt_root / "nested"
    target_run = _write_run(database_path, nested_receipts, "real-run")
    alias = receipt_root / "alias-run"
    if sys.platform != "win32":
        pytest.skip("Windows junction contract")
    assert _create_junction(alias, target_run), "Windows TEMP junction must be available"

    try:
        assert alias.resolve() == target_run.resolve()
        assert not alias.is_symlink()
        evidence = _collect(database_path, date(2024, 1, 1))

        assert evidence.presence.value == "present"
        expected_roles = {
            f"{_run_token('alias-run')}/{name}"
            for name in ("revision.json", "journal.json", "plan.json", "receipt.json")
        }
        assert {item.role_id for item in evidence.files} == expected_roles
        hashes = {item.role_id.rsplit("/", 1)[1]: item.sha256 for item in evidence.files}
        for filename, digest in hashes.items():
            assert digest == hashlib.sha256((target_run / filename).read_bytes()).hexdigest()
    finally:
        alias.rmdir()
