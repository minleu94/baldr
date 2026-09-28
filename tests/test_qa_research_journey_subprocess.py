"""受控 Qt QA launcher 的純 Python process contract 測試。"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import hashlib
import os
import sqlite3

import pytest

from scripts import qa_run_research_journey_qt_subprocess as runner
from scripts import qa_personal_research_ui as personal_ui


class _CompletedChild:
    def __init__(self, return_code: int) -> None:
        self.pid = 42_424
        self.returncode = return_code
        self.wait_calls: list[float | None] = []
        self.terminate_calls = 0
        self.kill_calls = 0

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        return self.returncode

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1


class _TimeoutChild(_CompletedChild):
    def __init__(self, return_code: int) -> None:
        super().__init__(return_code)
        self._wait_count = 0
        self._terminated = False

    def poll(self) -> int | None:
        return self.returncode if self._terminated else None

    def wait(self, timeout: float | None = None) -> int:
        self._wait_count += 1
        self.wait_calls.append(timeout)
        if self._wait_count == 1:
            assert timeout is not None
            raise subprocess.TimeoutExpired("research-journey-child", timeout)
        return self.returncode

    def terminate(self) -> None:
        self._terminated = True
        super().terminate()


class _FakeOwnedProcessTree:
    management_mode = "test_owned_process_tree"

    def __init__(self) -> None:
        self.attached = False
        self.closed = False

    def mark_attached(self) -> None:
        self.attached = True

    def close(self) -> None:
        self.closed = True


def _read_metadata(output_dir: Path) -> dict[str, object]:
    metadata_paths = sorted(output_dir.glob("controlled_run_*/process.json"))
    assert len(metadata_paths) == 1
    return json.loads(metadata_paths[0].read_text(encoding="utf-8"))


def test_launcher_finds_nested_child_pid_receipt(tmp_path):
    run_dir = tmp_path / "controlled_run"
    nested = run_dir / "run_20260915_000000_abcd1234"
    nested.mkdir(parents=True)
    receipt = nested / "child_process.json"
    receipt.write_text("{\"pid\": 1234}", encoding="utf-8")

    assert runner._find_child_process_metadata_path(run_dir) == receipt


def _fake_spawn(child):
    def spawn(command, **kwargs):
        output_dir = Path(command[command.index("--output-dir") + 1])
        (output_dir / "child_process.json").write_text(
            json.dumps(
                {
                    "pid": child.pid,
                    "ppid": 1,
                    "status": "running",
                }
            ),
            encoding="utf-8",
        )
        kwargs["owned_process_tree"].mark_attached()
        return child

    return spawn


def test_launcher_preserves_nonzero_child_exit_without_retry(tmp_path, monkeypatch):
    output_dir = tmp_path / "evidence"
    child = _CompletedChild(3221225477)
    popen_calls: list[tuple[object, dict[str, object]]] = []

    def fake_spawn(command, **kwargs):
        popen_calls.append((command, kwargs))
        output_dir = Path(command[command.index("--output-dir") + 1])
        (output_dir / "child_process.json").write_text(
            json.dumps({"pid": child.pid, "ppid": 1, "status": "passed"}),
            encoding="utf-8",
        )
        kwargs["owned_process_tree"].mark_attached()
        return child

    monkeypatch.setattr(runner, "_spawn_owned_child", fake_spawn)
    monkeypatch.setattr(runner, "_OwnedProcessTree", _FakeOwnedProcessTree)

    exit_code = runner.run(["--output-dir", str(output_dir)])

    metadata = _read_metadata(output_dir)
    assert exit_code == 3221225477
    assert metadata["status"] == "child_failed"
    assert metadata["exit_code"] == 3221225477
    assert metadata["automatic_retries"] == 0
    assert metadata["runner_pid"] == 42424
    assert metadata["owned_process_tree_attached"] is True
    assert metadata["owned_process_tree_closed"] is True
    assert len(popen_calls) == 1
    assert child.terminate_calls == 0
    assert child.kill_calls == 0


def test_launcher_timeout_only_terminates_owned_child_and_records_exit_code(
    tmp_path,
    monkeypatch,
):
    output_dir = tmp_path / "evidence"
    child = _TimeoutChild(3221225477)

    monkeypatch.setattr(runner, "_spawn_owned_child", _fake_spawn(child))
    monkeypatch.setattr(runner, "_OwnedProcessTree", _FakeOwnedProcessTree)
    monkeypatch.setattr(runner, "_is_process_pid_running", lambda _pid: False)

    exit_code = runner.run(
        [
            "--output-dir",
            str(output_dir),
            "--timeout-seconds",
            "0.01",
            "--terminate-grace-seconds",
            "0.01",
        ]
    )

    metadata = _read_metadata(output_dir)
    assert exit_code == runner.DEFAULT_TIMEOUT_EXIT_CODE
    assert metadata["status"] == "timed_out"
    assert metadata["timed_out"] is True
    assert metadata["exit_code"] == 3221225477
    assert metadata["termination_scope"] == "owned_windows_job_object_process_tree"
    assert metadata["owned_process_tree_attached"] is True
    assert metadata["owned_process_tree_closed"] is True
    assert metadata["reported_child_pid_exit_proof"] == "pid_not_running_after_tree_close"
    assert child.terminate_calls == 1
    assert child.kill_calls == 0


class _FailingCloseProcessTree(_FakeOwnedProcessTree):
    def close(self) -> None:
        raise OSError("simulated Job Object close failure")


def test_launcher_treats_owned_process_tree_close_failure_as_launcher_error(
    tmp_path,
    monkeypatch,
):
    output_dir = tmp_path / "evidence"
    child = _CompletedChild(0)

    monkeypatch.setattr(runner, "_spawn_owned_child", _fake_spawn(child))
    monkeypatch.setattr(runner, "_OwnedProcessTree", _FailingCloseProcessTree)

    exit_code = runner.run(["--output-dir", str(output_dir)])

    metadata = _read_metadata(output_dir)
    assert exit_code == 1
    assert metadata["status"] == "launcher_error"
    assert metadata["owned_process_tree_closed"] is False
    assert "owned process tree close failed" in str(metadata["error"])


def _personal_ui_fixture(tmp_path: Path):
    repo_qa_root = tmp_path / "output" / "qa"
    qa_root = repo_qa_root / "personal_daily_product_20261006"
    source_dir = qa_root / "source"
    source_dir.mkdir(parents=True)
    source_db = source_dir / "twstock.db"
    connection = sqlite3.connect(source_db)
    try:
        connection.executescript(
            "CREATE TABLE daily_prices (symbol TEXT NOT NULL, date TEXT NOT NULL, close TEXT NOT NULL);"
            "CREATE TABLE companies (symbol TEXT PRIMARY KEY, name TEXT NOT NULL);"
            "INSERT INTO daily_prices VALUES ('SYN001', '2026-09-25', '100.00');"
            "INSERT INTO daily_prices VALUES ('SYN002', '2026-09-25', '200.00');"
            "INSERT INTO companies VALUES ('SYN001', '合成公司一');"
            "INSERT INTO companies VALUES ('SYN002', '合成公司二');"
        )
        connection.commit()
    finally:
        connection.close()
    receipt_path = source_dir / "snapshot_receipt.json"
    receipt_path.write_text("{}\n", encoding="utf-8")
    summary = personal_ui._sqlite_summary(source_db)
    snapshot_sha256, snapshot_size = personal_ui._sha256_regular_file(source_db)
    authority = personal_ui.SnapshotAuthority(
        snapshot_path=source_db,
        receipt_path=receipt_path,
        snapshot_sha256=snapshot_sha256,
        receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        snapshot_size_bytes=snapshot_size,
        schema_sha256=summary["schema_sha256"],
        schema_object_count=summary["schema_object_count"],
        table_row_counts=summary["table_row_counts"],
    )
    learning_output_root = repo_qa_root / "pc-fit-v7"
    learning_root = learning_output_root / "recommendation_learning"
    learning_root.mkdir(parents=True)
    (learning_root / "candidate-index.json").write_text("[]\n", encoding="utf-8")
    run_root = qa_root / "personal_research_ui" / "run_01"
    policy_config_path = run_root / "app_config" / "personal_use_policy.json"
    return (
        repo_qa_root,
        qa_root,
        run_root,
        policy_config_path,
        learning_output_root,
        authority,
    )


def test_personal_ui_prepare_copies_pinned_db_to_exact_profile_test_path(tmp_path):
    (
        repo_qa_root,
        qa_root,
        run_root,
        policy_path,
        learning_root,
        authority,
    ) = _personal_ui_fixture(tmp_path)

    manifest_path, manifest = personal_ui.prepare_isolated_workspace(
        run_root=run_root,
        policy_config_path=policy_path,
        learning_output_root=learning_root,
        authority=authority,
        qa_root=qa_root,
        learning_qa_root=repo_qa_root,
        minimum_free_space_bytes=0,
    )

    working_db = run_root / "data" / "_test" / "sqlite" / "twstock.db"
    assert Path(manifest["working_db_path"]) == working_db.resolve()
    assert manifest["profile"] == "test"
    assert Path(manifest["data_root_actual"]) == (run_root / "data" / "_test").resolve()
    assert Path(manifest["output_root_actual"]) == (run_root / "output" / "_test").resolve()
    assert Path(manifest["policy_config_path"]) == policy_path.resolve(strict=False)
    assert manifest["working_copy"]["working_sha256"] == authority.snapshot_sha256
    assert manifest["working_copy"]["same_file_identity"] is False
    assert manifest["working_copy"]["hardlink_or_symlink"] is False
    assert manifest["working_sqlite_scope"]["query_only"] is True
    assert manifest["working_sqlite_scope"]["table_row_counts"] == {
        "companies": 2,
        "daily_prices": 2,
    }
    assert manifest["launcher_actions"]["native_window_started"] is False
    assert Path(manifest["learning_root_read_only_pin"]["learning_output_root"]) == (
        repo_qa_root / "pc-fit-v7"
    ).resolve()
    assert not personal_ui._is_within(
        Path(manifest["learning_root_read_only_pin"]["learning_root"]),
        qa_root,
    )
    assert manifest_path.is_file()
    assert personal_ui._read_manifest(manifest_path)["manifest_sha256"] == manifest[
        "manifest_sha256"
    ]
    assert not policy_path.exists()
    assert not os.path.samefile(authority.snapshot_path, working_db)


def test_personal_ui_snapshot_copy_is_create_only_and_digest_pinned(tmp_path):
    repo_qa_root, _qa_root, _run_root, _policy_path, _learning_root, authority = (
        _personal_ui_fixture(tmp_path)
    )
    destination = repo_qa_root / "copy" / "twstock.db"
    destination.parent.mkdir()
    destination.write_bytes(b"pre-existing")

    with pytest.raises(FileExistsError):
        personal_ui._copy_snapshot_create_only(
            authority.snapshot_path,
            destination,
            expected_sha256=authority.snapshot_sha256,
            expected_size_bytes=authority.snapshot_size_bytes,
            minimum_free_space_bytes=0,
        )
    assert destination.read_bytes() == b"pre-existing"

    with pytest.raises(personal_ui.IsolationError, match="SHA-256"):
        personal_ui._copy_snapshot_create_only(
            authority.snapshot_path,
            repo_qa_root / "bad-copy" / "twstock.db",
            expected_sha256="0" * 64,
            expected_size_bytes=authority.snapshot_size_bytes,
            minimum_free_space_bytes=0,
        )


def test_personal_ui_prepare_refuses_existing_run_root_without_overwriting(tmp_path):
    repo_qa_root, qa_root, run_root, policy_path, learning_root, authority = (
        _personal_ui_fixture(tmp_path)
    )
    run_root.mkdir(parents=True)
    marker = run_root / "keep.txt"
    marker.write_text("保留", encoding="utf-8")

    with pytest.raises(personal_ui.IsolationError, match="run root 已存在"):
        personal_ui.prepare_isolated_workspace(
            run_root=run_root,
            policy_config_path=policy_path,
            learning_output_root=learning_root,
            authority=authority,
            qa_root=qa_root,
            learning_qa_root=repo_qa_root,
            minimum_free_space_bytes=0,
        )
    assert marker.read_text(encoding="utf-8") == "保留"


def test_personal_ui_learning_root_read_only_pin_detects_candidate_change(tmp_path):
    root = tmp_path / "learning" / "recommendation_learning"
    root.mkdir(parents=True)
    candidate = root / "candidate.json"
    candidate.write_text('{"candidate_id":"qa-1"}\n', encoding="utf-8")

    before = personal_ui._directory_tree_pin(root)
    candidate.write_text('{"candidate_id":"qa-2"}\n', encoding="utf-8")
    after = personal_ui._directory_tree_pin(root)

    assert before["tree_sha256"] != after["tree_sha256"]
    assert before["file_count"] == after["file_count"] == 1


def test_personal_ui_learning_root_rejects_path_escape_without_statting_formal_drive(
    tmp_path, monkeypatch, capsys
):
    repo_qa_root, qa_root, run_root, policy_path, _learning_root, authority = (
        _personal_ui_fixture(tmp_path)
    )
    copy_called = False

    def reject_copy(*_args, **_kwargs):
        nonlocal copy_called
        copy_called = True
        raise AssertionError("不應在隔離路徑驗證前複製 snapshot")

    monkeypatch.setattr(personal_ui, "_copy_snapshot_create_only", reject_copy)
    with pytest.raises(personal_ui.IsolationError, match="repo-ignored output/qa root"):
        personal_ui.prepare_isolated_workspace(
            run_root=run_root,
            policy_config_path=policy_path,
            learning_output_root=Path("D:/Min/Python/Project/FA_Data"),
            authority=authority,
            qa_root=qa_root,
            learning_qa_root=repo_qa_root,
            minimum_free_space_bytes=0,
        )
    assert copy_called is False
    assert not run_root.exists()
    assert capsys.readouterr().out == ""


def test_personal_ui_learning_root_rejects_run_and_snapshot_ancestors(tmp_path):
    repo_qa_root, qa_root, run_root, policy_path, _learning_root, authority = (
        _personal_ui_fixture(tmp_path)
    )
    with pytest.raises(personal_ui.IsolationError, match="run root"):
        personal_ui.prepare_isolated_workspace(
            run_root=run_root,
            policy_config_path=policy_path,
            learning_output_root=run_root,
            authority=authority,
            qa_root=qa_root,
            learning_qa_root=repo_qa_root,
            minimum_free_space_bytes=0,
        )
    assert not run_root.exists()

    with pytest.raises(personal_ui.IsolationError, match="fixed QA snapshot"):
        personal_ui.prepare_isolated_workspace(
            run_root=run_root,
            policy_config_path=policy_path,
            learning_output_root=authority.snapshot_path.parent,
            authority=authority,
            qa_root=qa_root,
            learning_qa_root=repo_qa_root,
            minimum_free_space_bytes=0,
        )
    assert not run_root.exists()


def test_personal_ui_launch_environment_uses_only_isolated_roots(tmp_path, monkeypatch):
    repo_qa_root, _qa_root, run_root, _policy_path, learning_output_root, _authority = (
        _personal_ui_fixture(tmp_path)
    )
    data_root_base = run_root / "data"
    output_root_base = run_root / "output"
    layout = personal_ui.RuntimeLayout(
        run_root=run_root,
        data_root_base=data_root_base,
        output_root_base=output_root_base,
        data_root_actual=data_root_base / "_test",
        output_root_actual=output_root_base / "_test",
        working_db_path=data_root_base / "_test" / "sqlite" / "twstock.db",
        policy_config_path=run_root / "app_config" / "personal_use_policy.json",
        receipts_dir=run_root / "receipts",
    )
    monkeypatch.setenv("FORMAL_DAILY_DUMMY_BINDING", "must be removed")
    monkeypatch.setenv("DATA_ROOT", "D:/Min/Python/Project/FA_Data")
    monkeypatch.setenv("OUTPUT_ROOT", "D:/Min/Python/Project/FA_Data/output")

    personal_ui._configure_isolated_environment(layout, learning_output_root)

    assert Path(os.environ["DATA_ROOT"]) == data_root_base.resolve()
    assert Path(os.environ["OUTPUT_ROOT"]) == output_root_base.resolve()
    assert os.environ["PROFILE"] == "test"
    assert Path(os.environ["RECOMMENDATION_LEARNING_OUTPUT_ROOT"]) == learning_output_root.resolve()
    assert os.environ["QT_QPA_PLATFORM"] == "windows"
    assert "FORMAL_DAILY_DUMMY_BINDING" not in os.environ


def test_personal_ui_launch_summary_reads_nested_tree_pin_and_compares_same_shape():
    tree_pin = {
        "tree_sha256": "a" * 64,
        "file_count": 3,
        "total_bytes": 42,
    }
    verified_learning_pin = {
        "learning_output_root": "C:/qa/learning",
        "learning_root": "C:/qa/learning/recommendation_learning",
        "directory_identity": {"device": 1, "inode": 2},
        "directory_mtime_ns": 3,
        "tree_pin": tree_pin,
    }

    before_summary = personal_ui._launch_learning_pin_summary(verified_learning_pin)
    same_after_summary = personal_ui._launch_learning_pin_summary(
        verified_learning_pin, dict(tree_pin)
    )
    changed_tree_pin = {**tree_pin, "tree_sha256": "b" * 64}
    changed_after_summary = personal_ui._launch_learning_pin_summary(
        verified_learning_pin, changed_tree_pin
    )

    assert before_summary == {"learning_root_tree_sha256_before_ui": "a" * 64}
    assert same_after_summary == {
        "learning_root_tree_sha256_before_ui": "a" * 64,
        "learning_root_tree_sha256_after_ui": "a" * 64,
        "learning_root_unchanged": True,
    }
    assert changed_after_summary == {
        "learning_root_tree_sha256_before_ui": "a" * 64,
        "learning_root_tree_sha256_after_ui": "b" * 64,
        "learning_root_unchanged": False,
    }


def test_personal_ui_prepare_cli_rejects_wrong_snapshot_or_receipt_before_copy(
    tmp_path, monkeypatch, capsys
):
    (
        repo_qa_root,
        _qa_root,
        _run_root,
        _policy_path,
        _learning_output_root,
        authority,
    ) = _personal_ui_fixture(tmp_path)
    fake_repo = tmp_path / "repository"
    snapshot_relative = Path("output/qa/pinned/snapshot.db")
    receipt_relative = snapshot_relative.parent / "snapshot_receipt.json"
    pinned_snapshot = fake_repo / snapshot_relative
    pinned_receipt = fake_repo / receipt_relative
    pinned_snapshot.parent.mkdir(parents=True)
    pinned_snapshot.write_bytes(authority.snapshot_path.read_bytes())
    summary = personal_ui._sqlite_summary(pinned_snapshot)
    snapshot_sha256, snapshot_size = personal_ui._sha256_regular_file(pinned_snapshot)
    payload = {
        "schema_version": "formal-sqlite-source-snapshot.v1",
        "method": "sqlite3.Connection.backup from mode=ro source with query_only=ON",
        "snapshot_scope": "repo-ignored QA only; no formal-data writes",
        "snapshot_path": str(pinned_snapshot.resolve()),
        "snapshot_sha256": snapshot_sha256,
        "snapshot_integrity_check": ["ok"],
        "snapshot_data_version_stable": True,
        "snapshot_schema": {
            "schema_sha256": summary["schema_sha256"],
            "logical_size_bytes": snapshot_size,
            "table_count": summary["table_count"],
            "table_row_counts": summary["table_row_counts"],
            "schema_object_count": summary["schema_object_count"],
        },
    }
    pinned_receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt_bytes = personal_ui._canonical_json_bytes(payload)
    pinned_receipt.write_bytes(receipt_bytes)
    monkeypatch.setattr(personal_ui, "REPOSITORY_ROOT", fake_repo)
    monkeypatch.setattr(personal_ui, "PINNED_SNAPSHOT_RELATIVE", snapshot_relative)
    monkeypatch.setattr(personal_ui, "PINNED_SNAPSHOT_RECEIPT_RELATIVE", receipt_relative)
    monkeypatch.setattr(personal_ui, "PINNED_SNAPSHOT_SHA256", snapshot_sha256)
    monkeypatch.setattr(
        personal_ui,
        "PINNED_SNAPSHOT_RECEIPT_SHA256",
        hashlib.sha256(receipt_bytes).hexdigest(),
    )
    monkeypatch.setattr(personal_ui, "PINNED_SNAPSHOT_SIZE_BYTES", snapshot_size)
    monkeypatch.setattr(personal_ui, "PINNED_SCHEMA_SHA256", summary["schema_sha256"])

    prepare_called = False

    def refuse_prepare(*_args, **_kwargs):
        nonlocal prepare_called
        prepare_called = True
        raise AssertionError("錯誤來源不應進入 prepare/copy")

    monkeypatch.setattr(personal_ui, "prepare_isolated_workspace", refuse_prepare)
    run_root = tmp_path / "not-created" / "run_01"
    policy_path = run_root / "app_config" / "personal_use_policy.json"
    learning_root = repo_qa_root / "pc-fit-v7"

    wrong_snapshot_exit = personal_ui.main(
        [
            "prepare",
            "--run-root",
            str(run_root),
            "--source-snapshot",
            str(authority.snapshot_path),
            "--snapshot-receipt",
            str(pinned_receipt),
            "--learning-output-root",
            str(learning_root),
            "--policy-config-path",
            str(policy_path),
        ]
    )
    assert wrong_snapshot_exit == 2
    assert "來源 DB 必須是固定 QA snapshot" in capsys.readouterr().err

    pinned_receipt.write_bytes(b"{}\n")
    wrong_receipt_exit = personal_ui.main(
        [
            "prepare",
            "--run-root",
            str(run_root),
            "--source-snapshot",
            str(pinned_snapshot),
            "--snapshot-receipt",
            str(pinned_receipt),
            "--learning-output-root",
            str(learning_root),
            "--policy-config-path",
            str(policy_path),
        ]
    )
    assert wrong_receipt_exit == 2
    assert "snapshot receipt SHA 不符" in capsys.readouterr().err
    assert prepare_called is False
    assert not run_root.exists()


def test_personal_ui_prepare_cli_success_prints_nested_learning_tree_pin(
    tmp_path, monkeypatch, capsys
):
    (
        repo_qa_root,
        qa_root,
        run_root,
        policy_path,
        learning_output_root,
        authority,
    ) = _personal_ui_fixture(tmp_path)
    prepare = personal_ui.prepare_isolated_workspace

    def prepare_in_test_qa(**kwargs):
        return prepare(
            **kwargs,
            qa_root=qa_root,
            learning_qa_root=repo_qa_root,
            minimum_free_space_bytes=0,
        )

    monkeypatch.setattr(personal_ui, "_verify_source_snapshot_cli_inputs", lambda *_args: authority)
    monkeypatch.setattr(personal_ui, "prepare_isolated_workspace", prepare_in_test_qa)

    exit_code = personal_ui.main(
        [
            "prepare",
            "--run-root",
            str(run_root),
            "--source-snapshot",
            str(authority.snapshot_path),
            "--snapshot-receipt",
            str(authority.receipt_path),
            "--learning-output-root",
            str(learning_output_root),
            "--policy-config-path",
            str(policy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["mode"] == "prepare_only_no_window"
    assert output["working_db_sha256"] == authority.snapshot_sha256
    assert output["learning_root_tree_sha256"] == personal_ui._read_manifest(
        Path(output["manifest_path"])
    )["learning_root_read_only_pin"]["tree_pin"]["tree_sha256"]
    assert Path(output["manifest_path"]).is_file()
    assert output["learning_root_tree_sha256"]
