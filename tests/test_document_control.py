from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import pytest

from scripts import document_control


REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTING_PATH = Path("docs/agents/ROLE_ROUTING.json")
FEATURE_MAP_PATH = Path("docs/00_core/FEATURE_DOCUMENT_MAP.json")
BOOTSTRAP_SCHEMA_PATH = REPO_ROOT / "examples/machine_bootstrap_manifest.schema.json"
BOOTSTRAP_EXAMPLE_PATH = REPO_ROOT / "examples/machine_bootstrap_manifest.example.json"
SCHEDULE_REGISTRATION_PATH = REPO_ROOT / "scripts/inspect_scheduled_task_registration.py"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(root: Path, relative: str | Path, content: str = "fixture\n") -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _seed_document_repo(tmp_path: Path) -> Path:
    """依提交中的路由與功能清冊建立可丟棄的隔離 repository。"""
    root = tmp_path / "document-repo"
    root.mkdir()
    routing = _read_json(REPO_ROOT / ROUTING_PATH)
    feature_map = _read_json(REPO_ROOT / FEATURE_MAP_PATH)
    _write_json(root / ROUTING_PATH, routing)
    _write_json(root / FEATURE_MAP_PATH, feature_map)

    for role_path in routing["roles"].values():
        _write_text(root, role_path)

    references: dict[str, set[str]] = {}
    for feature in feature_map["features"]:
        for key in ("requirements", "contracts", "manual", "evidence", "status", "sync_documents"):
            for reference in feature[key]:
                relative, _, anchor = reference.partition("#")
                references.setdefault(relative, set())
                if anchor:
                    references[relative].add(anchor)
        for key in ("code", "tests"):
            for relative in feature[key]:
                references.setdefault(relative, set())

    for relative, anchors in references.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        anchor_markup = "\n".join(f'<a id="{anchor}"></a>' for anchor in sorted(anchors))
        path.write_text(existing + anchor_markup + "\n", encoding="utf-8")
    return root


def _canonical_schedule_constants() -> tuple[tuple[dict[str, str], ...], dict[str, str]]:
    """以語法資料讀取現行排程契約，不匯入產品模組。"""
    tree = ast.parse(SCHEDULE_REGISTRATION_PATH.read_text(encoding="utf-8-sig"))
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in {"EXPECTED_TASKS", "TASK_WRAPPER_PATHS"}:
                assert node.value is not None
                values[node.target.id] = ast.literal_eval(node.value)
    expected = values["EXPECTED_TASKS"]
    wrappers = values["TASK_WRAPPER_PATHS"]
    assert isinstance(expected, tuple)
    assert isinstance(wrappers, dict)
    return expected, wrappers


def _seed_bootstrap_repo(tmp_path: Path) -> tuple[Path, tuple[dict[str, str], ...], dict[str, str]]:
    """計畫測試使用臨時 repository 與現行來源的 canonical wrapper 路徑。"""
    root = tmp_path / "bootstrap-repo"
    script = root / "scripts/inspect_scheduled_task_registration.py"
    script.parent.mkdir(parents=True)
    shutil.copyfile(SCHEDULE_REGISTRATION_PATH, script)
    expected, wrappers = _canonical_schedule_constants()
    for relative in wrappers.values():
        _write_text(root, relative, "@echo off\nrem temporary fixture\n")
    return root, expected, wrappers


def _schedule_row(
    repo_root: Path,
    expected: dict[str, str],
    wrappers: dict[str, str],
    *,
    enabled: bool = False,
) -> dict[str, object]:
    name = expected["name"]
    trigger = expected["schedule"]
    timezone = "Taipei Standard Time" if "+08:00" in trigger else "Pacific Standard Time"
    wrapper = wrappers[name]
    return {
        "id": name,
        "platform": "windows",
        "desired_enabled": enabled,
        "timezone": timezone,
        "trigger": trigger,
        "canonical_wrapper": wrapper,
        "argv": ["cmd.exe", "/c", wrapper],
        "working_directory": str(repo_root.resolve()),
    }


def _fresh_manifest(tmp_path: Path, repo_root: Path) -> dict[str, Any]:
    manifest = _read_json(BOOTSTRAP_EXAMPLE_PATH)
    manifest.update(
        {
            "repo_root": str(repo_root.resolve()),
            "runtime": "source",
            "timezone": "Pacific Standard Time",
            "roots": {
                "DATA_ROOT": str((tmp_path / "market-data").resolve()),
                "OUTPUT_ROOT": str((tmp_path / "derived-output").resolve()),
            },
            "assets": [],
            "schedules": [],
            "observed_schedules": [],
            "excluded_schedules": [],
        }
    )
    return manifest


def _valid_source_inventory(repo_root: Path, schedules: list[dict[str, object]]) -> dict[str, str]:
    schema = _read_json(BOOTSTRAP_SCHEMA_PATH)
    required = schema["properties"]["source_inventory"]["required"]
    assert set(required) == {"path", "sha256"}
    inventory = {
        "schema_version": "baldr-machine-inventory.v1",
        "schedules": schedules,
    }
    inventory_path = _write_text(
        repo_root,
        "output/tasks/source_inventory.json",
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
    )
    digest = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    return {"path": str(inventory_path.resolve()), "sha256": digest}


def _rewrite_inventory(manifest: dict[str, Any], inventory: dict[str, Any]) -> None:
    source = manifest["source_inventory"]
    inventory_path = Path(source["path"])
    _write_json(inventory_path, inventory)
    source["sha256"] = hashlib.sha256(inventory_path.read_bytes()).hexdigest()


def _owner_migration_manifest(
    tmp_path: Path,
    repo_root: Path,
    expected_tasks: tuple[dict[str, str], ...],
    wrappers: dict[str, str],
) -> dict[str, Any]:
    manifest = _fresh_manifest(tmp_path, repo_root)
    schedules = [_schedule_row(repo_root, item, wrappers) for item in expected_tasks]
    manifest.update(
        {
            "mode": "owner-migration",
            "old_machine_writer_stopped": True,
            "source_inventory": _valid_source_inventory(repo_root, schedules),
            "source_scheduler_runtime_verified": True,
            "schedules": schedules,
        }
    )
    return manifest


def _valid_done_ui_task(root: Path) -> dict[str, Any]:
    feature_map = _read_json(root / FEATURE_MAP_PATH)
    feature = next(item for item in feature_map["features"] if item["id"] == "workspace:workbench")
    required_documents = sorted({reference.split("#", 1)[0] for reference in feature["sync_documents"]})
    evidence = _write_text(root, "output/qa/workbench-regression.json", '{"result":"passed"}\n')
    return {
        "schema_version": "baldr-task.v1",
        "task_id": "workbench-change",
        "owner": "root",
        "status": "done",
        "request": "更新決策工作台",
        "scope_files": ["ui_qt/views/workbench_view.py"],
        "routing": {
            "kind": "ui",
            "required_roles": ["execution", "testing_qa", "documentation"],
        },
        "coverage": [{"path": path, "status": "updated", "reason": ""} for path in required_documents],
        "verification": [{"name": "mandatory_ui_regression", "category": "qa", "status": "passed", "evidence": str(evidence.relative_to(root)).replace("\\", "/")}],
        "remaining": [],
    }


def _check_task(root: Path, task: dict[str, Any]) -> dict[str, Any]:
    task_path = root / "output/tasks/workbench-change/task.json"
    _write_json(task_path, task)
    return document_control.check(root, paths=[], task_path="output/tasks/workbench-change/task.json")


def test_route_selects_ui_roles_and_requires_ui_regression(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)

    result = document_control.route(
        root,
        kind="ui",
        request="調整數據更新畫面",
        changed=["ui_qt/views/update_view.py"],
    )

    assert result["status"] == "classified"
    assert result["primary_role"] == "execution"
    assert {"testing_qa", "documentation"} <= set(result["required_roles"])
    assert result["risk"] == "medium"
    assert "mandatory_ui_regression" in result["gates"]
    assert result["changed_paths"] == ["ui_qt/views/update_view.py"]


@pytest.mark.parametrize("anchor,valid", [("L2", True), ("L1-L2", True), ("L99", False)])
def test_markdown_line_reference_checks_real_range(tmp_path: Path, anchor: str, valid: bool) -> None:
    _write_text(tmp_path, "target.md", "# 目標\n第二行\n")
    _write_text(tmp_path, "source.md", f"[行號](target.md#{anchor})\n")
    errors = document_control.check_links(tmp_path, ["source.md"])
    assert bool(errors) is not valid


def test_route_selects_data_audit_for_read_only_data_comparison(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)

    result = document_control.route(root, kind="data_audit", request="SQLite 與 CSV 資料一致性")

    assert result["status"] == "classified"
    assert result["primary_role"] == "data_audit"
    assert result["risk"] == "medium"
    assert result["gates"] == []


def test_route_promotes_financial_implementation_to_high_risk_review(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)

    result = document_control.route(
        root,
        kind="implementation",
        request="修正回測訊號",
        changed=["backtest_module/engine.py"],
    )

    assert result["status"] == "classified"
    assert result["primary_role"] == "execution"
    assert {"testing_qa", "documentation", "tech_lead", "data_audit"} <= set(result["required_roles"])
    assert result["risk"] == "high"
    assert {"lookahead", "decimal_or_integer", "source_qualification"} <= set(result["gates"])


def test_route_selects_architecture_role_and_documentation_review(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)

    result = document_control.route(
        root,
        kind="architecture",
        request="調整模組邊界",
        changed=["app_module/dtos/decision_desk_dtos.py"],
    )

    assert result["status"] == "classified"
    assert result["primary_role"] == "tech_lead"
    assert "documentation" in result["required_roles"]
    assert result["risk"] == "medium"


def test_route_adds_owner_migration_inventory_and_single_writer_gates(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)

    result = document_control.route(
        root,
        kind="bootstrap",
        request="owner-migration 接手舊電腦",
        changed=["examples/machine_bootstrap_manifest.example.json"],
    )

    assert result["status"] == "classified"
    assert result["primary_role"] == "execution"
    assert "data_audit" in result["required_roles"]
    assert {"asset_identity", "single_writer", "schedule_readback"} <= set(result["gates"])


def test_route_keeps_pure_documentation_change_in_documentation_scope(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)

    result = document_control.route(
        root,
        kind="documentation",
        request="更新 Coverage Map",
        changed=["docs/00_core/DOC_COVERAGE_MAP.md"],
    )

    assert result["status"] == "classified"
    assert result["primary_role"] == "documentation"
    assert result["required_roles"] == ["documentation"]
    assert result["risk"] == "medium"


@pytest.mark.parametrize(
    "request_text",
    ["修復 UI 並清理資料", "完全未知的維護工作"],
)
def test_route_leaves_mixed_or_unknown_request_unclassified(tmp_path: Path, request_text: str) -> None:
    root = _seed_document_repo(tmp_path)

    result = document_control.route(root, request=request_text)

    assert result["status"] == "needs_classification"
    if "清理" in request_text:
        assert {"ui", "implementation", "cleanup"} <= set(result["candidate_kinds"])
    else:
        assert result["candidate_kinds"] == []


@pytest.mark.parametrize("changed_path", ["../outside.md", "../../repo-sibling/file.py"])
def test_route_rejects_relative_path_escape(tmp_path: Path, changed_path: str) -> None:
    root = _seed_document_repo(tmp_path)

    with pytest.raises(ValueError):
        document_control.route(root, kind="documentation", changed=[changed_path])


def test_route_cli_accepts_repeatable_changed_file_argument(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _seed_document_repo(tmp_path)

    return_code = document_control.main(
        [
            "--repo-root",
            str(root),
            "route",
            "--kind",
            "ui",
            "--request",
            "更新畫面",
            "--changed-file",
            "ui_qt/views/update_view.py",
            "--changed-file",
            "ui_qt/views/workbench_view.py",
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert return_code == 0
    assert result["status"] == "classified"
    assert result["changed_paths"] == ["ui_qt/views/update_view.py", "ui_qt/views/workbench_view.py"]


def test_init_task_uses_distinct_paths_and_does_not_overwrite_same_id(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    scope = ["ui_qt/views/workbench_view.py"]

    first = document_control.init_task(root, task_id="workbench-one", kind="ui", owner="root", paths=scope)
    first_path = root / first["created"]
    original = first_path.read_bytes()
    with pytest.raises(FileExistsError):
        document_control.init_task(root, task_id="workbench-one", kind="ui", owner="other", paths=scope)
    second = document_control.init_task(root, task_id="workbench-two", kind="ui", owner="root", paths=scope)

    assert first_path.read_bytes() == original
    assert json.loads(first_path.read_text(encoding="utf-8"))["owner"] == "root"
    assert Path(second["created"]) != Path(first["created"])
    assert (root / second["created"]).is_file()
    assert first["record"]["task_id"] == "workbench-one"
    assert second["record"]["task_id"] == "workbench-two"


def _link_output_to_storage(root: Path, storage: Path) -> None:
    storage.mkdir(parents=True, exist_ok=True)
    try:
        (root / "output").symlink_to(storage, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"此環境不能建立 output junction 模擬：{exc}")


def test_task_state_and_own_evidence_work_through_output_junction(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    storage = tmp_path / "baldr-storage" / "repo-output"
    _link_output_to_storage(root, storage)

    scope = ["ui_qt/views/workbench_view.py"]
    first = document_control.init_task(
        root, task_id="workbench-change", kind="ui", owner="root", paths=scope
    )
    task_relative = "output/tasks/workbench-change/task.json"
    task_file = storage / "tasks/workbench-change/task.json"
    assert Path(first["created"]) == task_file
    assert task_file.is_file()
    assert document_control.check(root, paths=[], task_path=task_relative)["passed"]
    original = task_file.read_bytes()
    with pytest.raises(FileExistsError):
        document_control.init_task(
            root, task_id="workbench-change", kind="ui", owner="other", paths=scope
        )
    assert task_file.read_bytes() == original

    evidence_relative = "output/tasks/workbench-change/evidence/ui-regression.json"
    _write_text(root, evidence_relative, '{"result":"passed"}\n')
    task = _valid_done_ui_task(root)
    task["verification"][0]["evidence"] = evidence_relative
    result = _check_task(root, task)
    assert result["passed"]


def test_task_paths_reject_dotdot_and_child_symlink_escape(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    storage = tmp_path / "baldr-storage" / "repo-output"
    _link_output_to_storage(root, storage)

    with pytest.raises(ValueError, match="路徑片段"):
        document_control.check(
            root, paths=[], task_path="output/tasks/workbench/../other/task.json"
        )
    with pytest.raises(ValueError, match="repo 相對任務路徑"):
        document_control.check(
            root,
            paths=[],
            task_path=str(storage / "tasks/workbench-change/task.json"),
        )

    outside = tmp_path / "outside-task"
    outside.mkdir()
    task_parent = storage / "tasks"
    task_parent.mkdir(parents=True)
    try:
        (task_parent / "workbench-escape").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"此環境不能建立 task 子層 symlink 模擬：{exc}")
    with pytest.raises(ValueError, match="子層不接受"):
        document_control.init_task(
            root,
            task_id="workbench-escape",
            kind="ui",
            owner="root",
            paths=["ui_qt/views/workbench_view.py"],
        )


def test_check_missing_task_output_is_read_only(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    output = root / "output"
    assert not output.exists()

    with pytest.raises(FileNotFoundError):
        document_control.check(
            root,
            paths=[],
            task_path="output/tasks/workbench-missing/task.json",
        )

    assert not output.exists()


def test_task_evidence_rejects_symlink_below_its_task_directory(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    storage = tmp_path / "baldr-storage" / "repo-output"
    _link_output_to_storage(root, storage)
    outside = tmp_path / "outside-evidence.json"
    outside.write_text('{"result":"passed"}\n', encoding="utf-8")
    task_evidence = storage / "tasks/workbench-change/evidence"
    task_evidence.mkdir(parents=True)
    try:
        (task_evidence / "external.json").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"此環境不能建立 evidence symlink 模擬：{exc}")

    with pytest.raises(ValueError, match="子層不接受"):
        document_control._task_storage_path(
            root,
            "output/tasks/workbench-change/evidence/external.json",
            task_id="workbench-change",
            evidence=True,
        )


def test_ui_feature_coverage_includes_manual_and_user_visible_feature_docs(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)

    required = document_control.required_documents(root, ["ui_qt/views/workbench_view.py"])

    assert "docs/07_guides/APPLICATION_MANUAL.md" in required
    assert "docs/02_features/UI_FEATURES_DOCUMENTATION.md" in required
    assert "docs/00_core/PROJECT_SNAPSHOT.md" in required


def test_feature_entrypoints_route_to_their_own_and_shared_documents(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)

    backtest_path = "app_module/basic_strategy_saved_pair.py"
    backtest_impacts = document_control.feature_impacts(root, [backtest_path])
    assert [feature["id"] for feature in backtest_impacts] == ["workspace:backtest"]
    backtest_required = document_control.required_documents(root, [backtest_path])
    assert backtest_required
    assert "docs/01_architecture/system_architecture.md" in backtest_required

    shared_path = (
        "app_module/daily_market_technical_official_disposition_revenue_archived_bookmark_v3.py"
    )
    shared_impacts = document_control.feature_impacts(root, [shared_path])
    assert {feature["id"] for feature in shared_impacts} == {
        "workspace:recommendation",
        "workspace:watchlist",
        "workspace:update",
    }
    expected_documents = {
        reference.split("#", 1)[0]
        for feature in shared_impacts
        for reference in feature["sync_documents"]
    }
    assert document_control.required_documents(root, [shared_path]) == sorted(expected_documents)


def test_check_rejects_representative_path_missing_its_own_change_pattern(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    feature_map = _read_json(root / FEATURE_MAP_PATH)
    path = "app_module/daily_market_technical_official_disposition_revenue_archived_bookmark_v3.py"
    feature = next(item for item in feature_map["features"] if item["id"] == "workspace:recommendation")
    feature["change_patterns"] = [pattern for pattern in feature["change_patterns"] if pattern != path]
    _write_json(root / FEATURE_MAP_PATH, feature_map)

    result = document_control.check(root, paths=[])

    expected_error = (
        f"功能代表入口未命中自身 change_patterns：workspace:recommendation code {path}"
    )
    assert result["passed"] is False
    assert expected_error in result["errors"]


def test_check_rejects_done_task_missing_manual_coverage(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    task = _valid_done_ui_task(root)
    task["coverage"] = [entry for entry in task["coverage"] if entry["path"] != "docs/07_guides/APPLICATION_MANUAL.md"]

    result = _check_task(root, task)

    assert result["passed"] is False
    assert any("docs/07_guides/APPLICATION_MANUAL.md" in error for error in result["errors"])


def test_check_rejects_done_task_with_not_run_qa(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    task = _valid_done_ui_task(root)
    task["verification"][0]["status"] = "not_run"

    result = _check_task(root, task)

    assert result["passed"] is False
    assert result["errors"]


def test_check_rejects_passed_qa_without_evidence(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    task = _valid_done_ui_task(root)
    task["verification"][0].pop("evidence")

    result = _check_task(root, task)

    assert result["passed"] is False
    assert result["errors"]


def test_check_rejects_passed_qa_with_missing_evidence_file(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    task = _valid_done_ui_task(root)
    task["verification"][0]["evidence"] = "output/qa/not-created.json"

    result = _check_task(root, task)

    assert result["passed"] is False
    assert any("output/qa/not-created.json" in error for error in result["errors"])


def test_check_rejects_unknown_verification_and_coverage_statuses(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    task = _valid_done_ui_task(root)
    task["verification"][0]["status"] = "maybe_passed"
    task["coverage"][0]["status"] = "deferred"

    result = _check_task(root, task)

    assert result["passed"] is False
    assert result["errors"]


def test_check_rejects_unknown_task_status(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    task = _valid_done_ui_task(root)
    task["status"] = "almost_done"

    result = _check_task(root, task)

    assert result["passed"] is False
    assert any("status" in error.lower() or "狀態" in error for error in result["errors"])


def test_done_task_cannot_silently_ignore_unmapped_new_module(tmp_path: Path) -> None:
    root = _seed_document_repo(tmp_path)
    task = _valid_done_ui_task(root)
    task["scope_files"].append("new_domain/new_feature.py")
    result = _check_task(root, task)
    assert not result["passed"]
    assert any("new_domain/new_feature.py" in error for error in result["errors"])


def test_bootstrap_plan_reports_principal_and_power_changes(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _fresh_manifest(tmp_path, root)
    desired = _schedule_row(root, expected_tasks[0], wrappers)
    desired.update({"principal": "new-owner", "power_policy": "wake"})
    observed = dict(desired, principal="old-owner", power_policy="do-not-wake")
    manifest["schedules"] = [desired]
    manifest["observed_schedules"] = [observed]
    result = document_control.bootstrap_plan(root, manifest)
    assert {"principal", "power_policy"} <= set(result["actions"][0]["differences"])


def test_check_links_reports_missing_local_target(tmp_path: Path) -> None:
    root = tmp_path / "links"
    source = _write_text(root, "docs/topic.md", "[Missing](missing.md)\n")

    errors = document_control.check_links(root, [source.relative_to(root).as_posix()])

    assert len(errors) == 1
    assert "missing.md" in errors[0]


def test_check_links_accepts_generated_second_duplicate_heading_anchor(tmp_path: Path) -> None:
    root = tmp_path / "links"
    source = _write_text(root, "docs/topic.md", "# Status\n# Status\n[Second](#status-1)\n")

    assert document_control.check_links(root, [source.relative_to(root).as_posix()]) == []


def test_check_links_rejects_nonexistent_duplicate_heading_anchor(tmp_path: Path) -> None:
    root = tmp_path / "links"
    source = _write_text(root, "docs/topic.md", "# Status\n# Status\n[Third](#status-2)\n")

    errors = document_control.check_links(root, [source.relative_to(root).as_posix()])

    assert len(errors) == 1
    assert "#status-2" in errors[0]


def test_bootstrap_plan_accepts_fresh_public_example_without_mutations(tmp_path: Path) -> None:
    root, _, _ = _seed_bootstrap_repo(tmp_path)
    manifest = _fresh_manifest(tmp_path, root)

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is True
    assert result["mode"] == "fresh"
    assert result["mutations"] == []
    assert result["actions"] == []


def test_bootstrap_plan_accepts_owner_migration_with_complete_canonical_windows_set(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _owner_migration_manifest(tmp_path, root, expected_tasks, wrappers)
    expected_names = {item["name"] for item in expected_tasks}
    actual_names = {item["id"] for item in manifest["schedules"]}

    result = document_control.bootstrap_plan(root, manifest)

    assert len(expected_tasks) == 21
    assert actual_names == expected_names
    assert result["ready_for_configuration_review"] is True
    assert result["windows_catalog_size"] == len(expected_names)
    assert result["mutations"] == []


def test_owner_migration_requires_old_writer_stop_evidence(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _owner_migration_manifest(tmp_path, root, expected_tasks, wrappers)
    manifest["old_machine_writer_stopped"] = False

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is False
    assert result["errors"]


def test_owner_migration_rejects_enabling_task_disabled_on_old_machine(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _owner_migration_manifest(tmp_path, root, expected_tasks, wrappers)
    manifest["schedules"][0]["desired_enabled"] = True

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is False
    assert any("desired_enabled" in error for error in result["errors"])


def test_owner_migration_rejects_unreviewed_notification_and_model_changes(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _owner_migration_manifest(tmp_path, root, expected_tasks, wrappers)
    inventory_path = Path(manifest["source_inventory"]["path"])
    inventory = _read_json(inventory_path)
    inventory["schedules"][0].update(
        {
            "notification_policy": "failed_runs_only",
            "model": "gpt-6.1-sol",
            "reasoning_effort": "high",
        }
    )
    _rewrite_inventory(manifest, inventory)
    manifest["schedules"][0].update(
        {
            "notification_policy": None,
            "model": "gpt-5.6-luna",
            "reasoning_effort": "medium",
        }
    )

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is False
    assert any("notification_policy" in error for error in result["errors"])
    assert any("model" in error for error in result["errors"])
    assert any("reasoning_effort" in error for error in result["errors"])


def test_owner_migration_rejects_old_inventory_hash_conflict(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _owner_migration_manifest(tmp_path, root, expected_tasks, wrappers)
    manifest["source_inventory"]["sha256"] = "0" * 64

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is False
    assert result["errors"]


def test_owner_migration_rejects_missing_old_inventory_path(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _owner_migration_manifest(tmp_path, root, expected_tasks, wrappers)
    manifest["source_inventory"]["path"] = str((tmp_path / "missing-inventory.json").resolve())

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is False
    assert result["errors"]


def test_owner_migration_rejects_missing_canonical_task_without_exclusion(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _owner_migration_manifest(tmp_path, root, expected_tasks, wrappers)
    omitted = manifest["schedules"].pop()

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is False
    assert any(omitted["id"] in error for error in result["errors"])


def test_owner_migration_accepts_named_canonical_exclusion_with_reason(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _owner_migration_manifest(tmp_path, root, expected_tasks, wrappers)
    omitted = manifest["schedules"].pop()
    manifest["excluded_schedules"] = [
        {"id": omitted["id"], "platform": "windows", "reason": "舊 owner 已停用並決定不移交此排程。"}
    ]

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is True
    assert result["mutations"] == []


def test_owner_migration_rejects_canonical_task_trigger_drift(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _owner_migration_manifest(tmp_path, root, expected_tasks, wrappers)
    manifest["schedules"][0]["trigger"] = "DAILY 23:59"

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is False
    assert result["errors"]


@pytest.mark.parametrize("collection", ["schedules", "observed_schedules"])
def test_bootstrap_plan_rejects_duplicate_schedule_identity(tmp_path: Path, collection: str) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _fresh_manifest(tmp_path, root)
    schedule = _schedule_row(root, expected_tasks[0], wrappers)
    manifest[collection] = [schedule, dict(schedule)]

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is False
    assert result["errors"]


def test_bootstrap_plan_preserves_disabled_existing_schedule_without_changes(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _fresh_manifest(tmp_path, root)
    disabled = _schedule_row(root, expected_tasks[0], wrappers, enabled=False)
    manifest["schedules"] = [disabled]
    manifest["observed_schedules"] = [dict(disabled)]

    result = document_control.bootstrap_plan(root, manifest)
    action = result["actions"][0]

    assert result["ready_for_configuration_review"] is True
    assert action["action"] == "retain_existing"
    assert action["differences"] == []
    assert action["desired_enabled"] is False


def test_bootstrap_plan_reports_notification_and_model_differences_without_rewriting(tmp_path: Path) -> None:
    root, _, _ = _seed_bootstrap_repo(tmp_path)
    manifest = _fresh_manifest(tmp_path, root)
    desired = {
        "id": "baldr-morning-readonly-heartbeat",
        "platform": "codex-heartbeat",
        "desired_enabled": False,
        "timezone": "America/Los_Angeles",
        "trigger": "daily 05:30",
        "notification_policy": "failed_runs_only",
        "model": "gpt-6.1-sol",
        "reasoning_effort": "high",
        "target_thread": "thread-current",
    }
    observed = dict(desired)
    observed.update(
        {
            "notification_policy": None,
            "model": "gpt-5.6-luna",
            "reasoning_effort": "medium",
            "target_thread": "thread-observed",
        }
    )
    manifest["schedules"] = [desired]
    manifest["observed_schedules"] = [observed]

    result = document_control.bootstrap_plan(root, manifest)
    action = result["actions"][0]

    assert result["ready_for_configuration_review"] is True
    assert action["action"] == "review_difference"
    assert set(action["differences"]) == {
        "notification_policy",
        "model",
        "reasoning_effort",
        "target_thread",
    }
    assert action["desired_enabled"] is False
    assert result["mutations"] == []


def test_bootstrap_plan_rejects_taipei_machine_timezone_for_windows_registrar(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _fresh_manifest(tmp_path, root)
    manifest["timezone"] = "Taipei Standard Time"
    manifest["schedules"] = [_schedule_row(root, expected_tasks[0], wrappers)]

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is False
    assert result["errors"]


def test_portable_gui_does_not_imply_source_scheduler_runtime(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _fresh_manifest(tmp_path, root)
    manifest["runtime"] = "portable-gui"
    manifest["source_scheduler_runtime_verified"] = False
    manifest["schedules"] = [_schedule_row(root, expected_tasks[0], wrappers)]

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is False
    assert result["errors"]


def test_portable_gui_can_plan_windows_task_only_with_separate_runtime_evidence(tmp_path: Path) -> None:
    root, expected_tasks, wrappers = _seed_bootstrap_repo(tmp_path)
    manifest = _fresh_manifest(tmp_path, root)
    manifest["runtime"] = "portable-gui"
    manifest["source_scheduler_runtime_verified"] = True
    manifest["schedules"] = [_schedule_row(root, expected_tasks[0], wrappers)]

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is True
    assert result["actions"][0]["action"] == "create_disabled_for_review"
    assert result["mutations"] == []


def test_bootstrap_plan_detects_asset_hash_conflict(tmp_path: Path) -> None:
    root, _, _ = _seed_bootstrap_repo(tmp_path)
    manifest = _fresh_manifest(tmp_path, root)
    asset = _write_text(tmp_path, "assets/model.bin", "approved model bytes\n")
    manifest["assets"] = [
        {"id": "approved-model", "path": str(asset.resolve()), "required": True, "sha256": "0" * 64}
    ]

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is False
    assert any(action.get("status") == "hash_mismatch" for action in result["actions"])


def test_bootstrap_plan_refuses_credentials_as_migratable_assets(tmp_path: Path) -> None:
    root, _, _ = _seed_bootstrap_repo(tmp_path)
    manifest = _fresh_manifest(tmp_path, root)
    credential = _write_text(tmp_path, "private/auth.json", "fixture only; no credential\n")
    manifest["assets"] = [
        {"id": "codex-auth", "path": str(credential.resolve()), "required": True}
    ]

    result = document_control.bootstrap_plan(root, manifest)

    assert result["ready_for_configuration_review"] is False
    assert "auth.json" not in json.dumps(result)
    assert not any(action.get("asset") == "codex-auth" for action in result["actions"])
