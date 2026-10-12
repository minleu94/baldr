from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import auto_state_sync


def _write_task(root: Path, task_id: str, owner: str) -> Path:
    task_path = root / "output" / "tasks" / task_id / "task.json"
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(
        json.dumps(
            {
                "schema_version": "baldr-task.v1",
                "task_id": task_id,
                "owner": owner,
                "status": "in_progress",
                "request": "fixture request",
                "routing": {"kind": "implementation", "required_roles": ["execution"]},
                "coverage": [{"path": "docs/example.md", "status": "pending"}],
                "verification": [{"name": "fixture", "status": "not_run"}],
                "custom_state": {"keep": [1, 2, 3]},
                "git_status": {"clean": True, "modified_files": [], "warnings": []},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return task_path


def test_no_arguments_only_lists_status_and_leaves_task_and_legacy_state_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_path = _write_task(tmp_path, "task-one", "root")
    task_before = task_path.read_bytes()
    legacy_path = tmp_path / "docs" / "agents" / "shared_state" / "active_task.yaml"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text("owner: legacy-owner\nprogress: keep\n", encoding="utf-8")
    legacy_before = legacy_path.read_bytes()
    calls: list[Path] = []

    monkeypatch.setattr(auto_state_sync, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(auto_state_sync, "run_git_status", lambda: calls.append(tmp_path) or ["src/change.py"])
    monkeypatch.setattr(
        auto_state_sync.os,
        "replace",
        lambda *args, **kwargs: pytest.fail("read-only default must not atomically replace state"),
    )

    result = auto_state_sync.main([])

    assert result == 0
    assert calls == [tmp_path]
    assert task_path.read_bytes() == task_before
    assert legacy_path.read_bytes() == legacy_before


def test_matching_owner_updates_only_selected_task_and_preserves_other_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = _write_task(tmp_path, "task-one", "root")
    other = _write_task(tmp_path, "task-two", "other-owner")
    other_before = other.read_bytes()
    legacy_path = tmp_path / "docs" / "agents" / "shared_state" / "active_task.yaml"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text("legacy: untouched\n", encoding="utf-8")
    legacy_before = legacy_path.read_bytes()
    original = json.loads(selected.read_text(encoding="utf-8"))
    replaced_in_same_directory: list[tuple[Path, Path]] = []
    real_replace = auto_state_sync.os.replace

    def capture_atomic_replace(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        replaced_in_same_directory.append((source_path.parent, destination_path.parent))
        real_replace(source, destination)

    monkeypatch.setattr(auto_state_sync, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(auto_state_sync, "run_git_status", lambda: ["src/change.py", ".env.example"])
    monkeypatch.setattr(auto_state_sync.os, "replace", capture_atomic_replace)

    result = auto_state_sync.main(
        ["--task", "output/tasks/task-one/task.json", "--owner", "root"]
    )

    updated = json.loads(selected.read_text(encoding="utf-8"))
    assert result == 0
    assert updated["git_status"] == {
        "clean": False,
        "modified_files": ["src/change.py", ".env.example"],
        "warnings": [],
    }
    for field, value in original.items():
        if field != "git_status":
            assert updated[field] == value
    assert other.read_bytes() == other_before
    assert legacy_path.read_bytes() == legacy_before
    assert replaced_in_same_directory == [(selected.parent, selected.parent)]
    assert list(selected.parent.glob(".task.json.*.tmp")) == []


def test_owner_schema_and_directory_identity_mismatches_reject_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong_owner = _write_task(tmp_path, "wrong-owner", "alice")
    wrong_owner_before = wrong_owner.read_bytes()
    bad_schema = _write_task(tmp_path, "bad-schema", "root")
    bad_schema_record = json.loads(bad_schema.read_text(encoding="utf-8"))
    bad_schema_record["schema_version"] = "unknown.v9"
    bad_schema.write_text(json.dumps(bad_schema_record, indent=2) + "\n", encoding="utf-8")
    bad_schema_before = bad_schema.read_bytes()
    wrong_identity = _write_task(tmp_path, "wrong-identity", "root")
    wrong_identity_record = json.loads(wrong_identity.read_text(encoding="utf-8"))
    wrong_identity_record["task_id"] = "somebody-elses-task"
    wrong_identity.write_text(json.dumps(wrong_identity_record, indent=2) + "\n", encoding="utf-8")
    wrong_identity_before = wrong_identity.read_bytes()
    monkeypatch.setattr(auto_state_sync, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(auto_state_sync, "run_git_status", lambda: ["src/change.py"])

    assert auto_state_sync.main(
        ["--task", "output/tasks/wrong-owner/task.json", "--owner", "root"]
    ) == 1
    assert auto_state_sync.main(
        ["--task", "output/tasks/bad-schema/task.json", "--owner", "root"]
    ) == 1
    assert auto_state_sync.main(
        ["--task", "output/tasks/wrong-identity/task.json", "--owner", "root"]
    ) == 1

    assert wrong_owner.read_bytes() == wrong_owner_before
    assert bad_schema.read_bytes() == bad_schema_before
    assert wrong_identity.read_bytes() == wrong_identity_before


def test_outside_or_legacy_path_is_rejected_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_path = tmp_path / "docs" / "agents" / "shared_state" / "active_task.yaml"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text("legacy: untouched\n", encoding="utf-8")
    before = legacy_path.read_bytes()
    monkeypatch.setattr(auto_state_sync, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(auto_state_sync, "run_git_status", lambda: [])

    for task_argument in ["../docs/agents/shared_state/active_task.yaml", "docs/agents/shared_state/active_task.yaml"]:
        result = auto_state_sync.main(["--task", task_argument, "--owner", "root"])
        assert result == 1
        assert legacy_path.read_bytes() == before



def test_git_exclusion_keeps_original_rules_and_allows_env_example() -> None:
    files = [
        ".env",
        ".env.local",
        ".env.example",
        "docs/agents/shared_state/active_task.yaml",
        "logs/run.log",
    ]

    assert auto_state_sync.check_exclusions(files) == [
        ".env",
        ".env.local",
        "docs/agents/shared_state/active_task.yaml",
        "logs/run.log",
    ]
