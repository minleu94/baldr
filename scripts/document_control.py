"""baldr 文件關聯、角色分流與移機計畫的標準函式庫工具。

route/check/context/trace/inventory/issues/archives/bootstrap-plan 只讀來源；init-task 建立獨立 ignored 任務紀錄。
工具不啟動 Agent、排程、資料更新、模型訓練或產品 import。
"""

from __future__ import annotations

import argparse
import ast
from fnmatch import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any
from urllib.parse import unquote

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import document_external_references as external_references

REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_CATALOG = "docs/agents/ROLE_ROUTING.json"
FEATURE_MAP = "docs/00_core/FEATURE_DOCUMENT_MAP.json"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根節點必須為物件：{path}")
    return value


def confined(root: Path, relative: str) -> Path:
    """拒絕越界、絕對路徑及經 symlink 逃離 repository 的來源。"""
    if not relative or Path(relative).is_absolute() or re.match(r"^[A-Za-z]:", relative):
        raise ValueError(f"必須提供 repo 相對路徑：{relative}")
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError(f"路徑超出 repository：{relative}")
    return candidate


def match_paths(paths: list[str], patterns: list[str]) -> bool:
    return any(fnmatch(path, pattern) for path in paths for pattern in patterns)


def read_config(root: Path, relative: str) -> dict[str, Any]:
    """治理 config 必須是 repo 內普通檔，拒絕 lexical symlink／reparse。"""
    target = confined(root, relative)
    current = root / relative
    while current != root:
        if current.is_symlink() or getattr(current.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"治理 config 不接受連結：{relative}")
        current = current.parent
    return read_json(target)


def route(root: Path, *, kind: str | None = None, request: str = "", changed: list[str] | None = None) -> dict[str, Any]:
    explicit_kind = kind is not None
    catalog = read_config(root, ROLE_CATALOG)
    paths = [(value.replace("\\", "/")) for value in (changed or [])]
    for path in paths:
        confined(root, path)
    hints = [name for name, terms in catalog["request_hints"].items() if any(term in request.casefold() for term in terms)]
    # 自然語言只做候選辨識，混合意圖由總負責者明示分類。
    if kind is None:
        if len(hints) != 1:
            return {"status": "needs_classification", "candidate_kinds": hints, "reason": "請由總負責者指定 --kind；文字提示不代表授權或完整任務分類。"}
        kind = hints[0]
    if kind not in catalog["kinds"]:
        raise ValueError(f"未知任務類型：{kind}")
    rule = catalog["kinds"][kind]
    roles = list(dict.fromkeys([rule["primary"], *rule["required"]]))
    gates: list[str] = []
    risk = rule["risk"]
    mutating = kind in catalog["mutating_kinds"]
    if mutating and match_paths(paths, catalog["financial_paths"]):
        roles = list(dict.fromkeys([*roles, "tech_lead", "data_audit"]))
        gates.extend(["lookahead", "decimal_or_integer", "source_qualification"])
        risk = "high"
    if mutating and match_paths(paths, catalog["architecture_paths"]):
        roles = list(dict.fromkeys([*roles, "tech_lead"]))
    if mutating and (kind == "ui" or match_paths(paths, catalog["ui_paths"])):
        gates.append("mandatory_ui_regression")
    if kind == "bootstrap" and any(term in request.casefold() for term in ["移機", "搬機", "換電腦", "owner-migration"]):
        roles = list(dict.fromkeys([*roles, "data_audit"]))
        gates.extend(["asset_identity", "single_writer", "schedule_readback"])
    return {
        "status": "classified", "kind": kind, "primary_role": rule["primary"],
        "required_roles": roles, "guides": [catalog["roles"][role] for role in roles],
        "risk": risk, "gates": gates, "changed_paths": paths,
        "classification_source": "explicit_kind" if explicit_kind else "request_hint",
        "execution": "角色履職建議；獨立 Agent 必須另經可用平台調用並記錄，不由本工具啟動。",
    }


def feature_impacts(root: Path, paths: list[str]) -> list[dict[str, Any]]:
    mapping = read_config(root, FEATURE_MAP)
    return [feature for feature in mapping["features"] if match_paths(paths, feature["change_patterns"])]


def required_documents(root: Path, paths: list[str]) -> list[str]:
    return sorted({value.split("#", 1)[0] for feature in feature_impacts(root, paths) for value in feature["sync_documents"]})


def init_task(root: Path, *, task_id: str, kind: str, owner: str, paths: list[str], request: str = "") -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", task_id):
        raise ValueError("task_id 必須是 1–96 位小寫英數、底線或連字號。")
    if not owner.strip():
        raise ValueError("必須指定任務 owner。")
    classified = route(root, kind=kind, request=request, changed=paths)
    directory = confined(root, f"output/tasks/{task_id}")
    directory.mkdir(parents=True, exist_ok=True)
    target = confined(root, f"output/tasks/{task_id}/task.json")
    baseline = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False).stdout.strip()
    record = {
        "schema_version": "baldr-task.v1", "task_id": task_id, "owner": owner,
        "status": "planning", "baseline_commit": baseline or "unknown", "request": request,
        "routing": classified, "scope_files": paths, "read_files": [], "inspection_scope": [],
        "features": [item["id"] for item in feature_impacts(root, paths)],
        "coverage": [{"path": path, "status": "pending", "reason": ""} for path in required_documents(root, paths)],
        "verification": [], "remaining": [], "safe_resume_point": "",
    }
    # O_EXCL 保證同一 task ID 的重跑不覆寫既有 owner 或進度。
    with target.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return {"created": str(target), "record": record}


def heading_anchors(content: str) -> set[str]:
    content = re.sub(r"```[^\n]*\n.*?```", "", content, flags=re.S)
    anchors = set(re.findall(r"\bid=[\"']([^\"']+)[\"']", content))
    seen: dict[str, int] = {}
    for line in content.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not heading:
            continue
        label = re.sub(r"<[^>]+>", "", heading.group(1)).lower()
        label = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", label)
        base = re.sub(r"[^\w\- ]", "", label).replace(" ", "-")
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def link_report(root: Path, paths: list[str]) -> dict[str, Any]:
    """驗證本地連結，並將精確登記的冷封存另列為外部證據。"""
    errors: list[str] = []
    registered: list[dict[str, Any]] = []
    try:
        registry = external_references.load_registry(root)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return {"errors": [f"冷封存登記無效：{exc}"], "registered_external_references": []}
    content_cache: dict[Path, str] = {}
    anchor_cache: dict[Path, set[str]] = {}
    root = root.resolve()
    pattern = re.compile(r"\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+\"[^\"]*\")?\)")
    for relative in paths:
        source = confined(root, relative)
        if not source.is_file() or source.suffix != ".md":
            continue
        # 原 bytes 封存不是現行導航；其連結必須按原路徑語境解讀。
        if "/documentation_productization_20261012/originals/" in source.as_posix():
            continue
        content = re.sub(r"```[^\n]*\n.*?```", "", source.read_text(encoding="utf-8-sig"), flags=re.S)
        for match in pattern.finditer(content):
            target = unquote(match.group(1) or match.group(2))
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
                continue
            location, _, anchor = target.partition("#")
            lexical = Path(os.path.abspath(source.parent / location)) if location else source
            if not lexical.is_relative_to(root):
                errors.append(f"{relative}: 連結越界 {target}")
                continue
            candidate = lexical.resolve()
            try:
                archived = external_references.registered_reference(root, lexical, candidate, registry)
            except (ValueError, OSError) as exc:
                errors.append(f"{relative}: 冷封存連結無效 {target}：{exc}")
                continue
            if archived:
                registered.append({"source": relative, "link": target, **archived})
                continue
            if not candidate.is_relative_to(root):
                errors.append(f"{relative}: 連結越界 {target}")
            elif not candidate.exists():
                errors.append(f"{relative}: 連結缺件 {target}")
            elif anchor and candidate.is_file() and candidate.suffix == ".md":
                if candidate not in content_cache:
                    content_cache[candidate] = candidate.read_text(encoding="utf-8-sig")
                target_content = content_cache[candidate]
                line_reference = re.fullmatch(r"L([1-9][0-9]*)(?:-L([1-9][0-9]*))?", anchor)
                if line_reference:
                    first = int(line_reference.group(1))
                    last = int(line_reference.group(2) or first)
                    if not first <= last <= len(target_content.splitlines()):
                        errors.append(f"{relative}: 行號範圍缺件 {target}")
                else:
                    if candidate not in anchor_cache:
                        anchor_cache[candidate] = heading_anchors(target_content)
                    if anchor not in anchor_cache[candidate]:
                        errors.append(f"{relative}: 錨點缺件 {target}")
    return {"errors": errors, "registered_external_references": registered,
            "external_content_verification": "not_run; 只核登記、Junction目標及存在性metadata"}


def check_links(root: Path, paths: list[str]) -> list[str]:
    return list(link_report(root, paths)["errors"])


def check_task(root: Path, task: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if task.get("schema_version") != "baldr-task.v1" or not task.get("owner"):
        errors.append("任務缺 schema_version 或 owner")
    if task.get("status") not in {"planning", "in_progress", "review", "verification", "documentation", "blocked", "paused", "done"}:
        errors.append("未知 task status")
    paths = task.get("scope_files", [])
    for path in [*task.get("read_files", []), *task.get("inspection_scope", [])]:
        confined(root, path)
    expected = route(root, kind=task.get("routing", {}).get("kind"), request=task.get("request", ""), changed=paths)
    if expected.get("status") != "classified":
        errors.append("任務尚未完成分類")
    elif set(expected["required_roles"]) - set(task.get("routing", {}).get("required_roles", [])):
        errors.append("任務漏列必要角色")
    coverage = {entry["path"]: entry for entry in task.get("coverage", [])}
    for path in required_documents(root, paths):
        if path not in coverage:
            errors.append(f"漏列必要文件：{path}")
    if task.get("status") == "done":
        patterns = [pattern for feature in read_config(root, FEATURE_MAP)["features"] for pattern in feature["change_patterns"]]
        decisions = {item.get("path"): item for item in task.get("impact_decisions", [])}
        for path in paths:
            if not match_paths([path], patterns) and not decisions.get(path, {}).get("reason", "").strip():
                errors.append(f"未匹配的變更缺影響判斷：{path}")
        for path, entry in coverage.items():
            confined(root, path)
            if entry.get("status") == "updated" and not confined(root, path).is_file():
                errors.append(f"更新文件缺件：{path}")
            elif entry.get("status") == "not_required" and not entry.get("reason", "").strip():
                errors.append(f"無需更新未附理由：{path}")
            elif entry.get("status") not in {"updated", "not_required"}:
                errors.append(f"文件同步未完成：{path}")
        if task.get("remaining"):
            errors.append("仍有未完成事項，不能標 done")
        results = task.get("verification", [])
        if not results:
            errors.append("交付缺驗證紀錄")
        for result in results:
            if result.get("status") not in {"passed", "not_required"}:
                errors.append(f"驗證未通過：{result.get('name', 'unknown')}")
            if result.get("status") == "passed" and not result.get("evidence"):
                errors.append("驗證通過卻缺證據位置")
            if result.get("status") == "not_required" and not result.get("reason"):
                errors.append("免驗證未附理由")
            if result.get("evidence") and not confined(root, result["evidence"]).is_file():
                errors.append(f"驗證證據缺件：{result['evidence']}")
        required_gates = set(expected.get("gates", []))
        represented = {result.get("name") for result in results}
        for gate in sorted(required_gates - represented):
            errors.append(f"必要風險／UI驗證未列：{gate}")
        if "testing_qa" in expected.get("required_roles", []) and not any(result.get("category") == "qa" for result in results):
            errors.append("必要 QA 缺驗證紀錄；以 category=qa 指明實際結果或不適用理由")
    return errors


def feature_map_coverage_errors(mapping: dict[str, Any]) -> list[str]:
    """確保每個明示的程式與測試代表入口都映射回所屬功能。"""
    errors: list[str] = []
    for feature in mapping.get("features", []):
        patterns = feature.get("change_patterns", [])
        for kind in ("code", "tests"):
            for relative in feature.get(kind, []):
                if not match_paths([relative], patterns):
                    errors.append(
                        f"功能代表入口未命中自身 change_patterns：{feature.get('id', 'unknown')} {kind} {relative}"
                    )
    return errors


def check(root: Path, *, paths: list[str] | None = None, task_path: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    catalog = read_config(root, ROLE_CATALOG)
    if catalog.get("schema_version") != "baldr-role-routing.v1":
        errors.append("路由 schema_version 不符")
    for role, guide in catalog["roles"].items():
        if not confined(root, guide).is_file():
            errors.append(f"角色文件缺件：{role} {guide}")
    for kind, rule in catalog["kinds"].items():
        for role in [rule["primary"], *rule["required"]]:
            if role not in catalog["roles"]:
                errors.append(f"路由引用未知角色：{kind} {role}")
    mapping = read_config(root, FEATURE_MAP)
    errors.extend(feature_map_coverage_errors(mapping))
    ids: set[str] = set()
    map_documents: set[str] = set()
    for feature in mapping["features"]:
        if feature["id"] in ids:
            errors.append(f"功能 ID 重複：{feature['id']}")
        ids.add(feature["id"])
        for key in ["requirements", "contracts", "manual", "evidence", "status", "sync_documents"]:
            values = feature.get(key, [])
            if not values:
                errors.append(f"功能關聯缺 {key}：{feature['id']}")
            for reference in values:
                relative, _, anchor = reference.partition("#")
                target = confined(root, relative)
                if not target.is_file():
                    errors.append(f"功能引用缺件：{feature['id']} {reference}")
                elif anchor and anchor not in heading_anchors(target.read_text(encoding="utf-8-sig")):
                    errors.append(f"功能引用錨點缺件：{feature['id']} {reference}")
                map_documents.add(relative)
        for key in ["code", "tests"]:
            if not feature.get(key):
                errors.append(f"功能關聯缺 {key}：{feature['id']}")
            for relative in feature.get(key, []):
                if not confined(root, relative).is_file():
                    errors.append(f"功能{key}缺件：{feature['id']} {relative}")
    link_scope = sorted(set(paths if paths is not None else ["README.md", "AGENTS.md", "docs/agents/skills_registry.md", *map_documents]))
    links = link_report(root, link_scope)
    errors.extend(links["errors"])
    if task_path:
        errors.extend(check_task(root, read_json(confined(root, task_path))))
    return {"schema_version": "baldr-document-check.v1", "passed": not errors, "errors": errors, "checked_features": len(ids), "checked_link_sources": len(link_scope), "registered_external_references": links["registered_external_references"], "limitation": "結構與紀錄核對；已登記冷封存另列且不讀raw bytes，不證明外部內容、文件語意、產品Gate、真安裝或自然排程成功。"}


def windows_schedule_catalog(root: Path) -> dict[str, str]:
    """從現行稽核器讀常數，不 import 產品或維護另一份 21-task 清單。"""
    tree = ast.parse((root / "scripts/inspect_scheduled_task_registration.py").read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "TASK_WRAPPER_PATHS":
            if node.value is None:
                raise ValueError("TASK_WRAPPER_PATHS 缺常數值")
            value = ast.literal_eval(node.value)
            if isinstance(value, dict):
                return value
    raise ValueError("現行 Task 稽核器缺 TASK_WRAPPER_PATHS 常數")


def windows_schedule_triggers(root: Path) -> dict[str, str]:
    tree = ast.parse((root / "scripts/inspect_scheduled_task_registration.py").read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "EXPECTED_TASKS":
            if node.value is None:
                raise ValueError("EXPECTED_TASKS 缺常數值")
            values = ast.literal_eval(node.value)
            return {item["name"]: item["schedule"] for item in values}
    raise ValueError("現行 Task 稽核器缺 EXPECTED_TASKS 常數")


def bootstrap_plan(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    actions: list[dict[str, Any]] = []
    if manifest.get("schema_version") != "baldr-bootstrap.v1":
        errors.append("移機清冊 schema_version 不符")
    mode = manifest.get("mode")
    if mode not in {"fresh", "owner-migration"}:
        errors.append("mode 必須是 fresh 或 owner-migration")
    if manifest.get("runtime") not in {"source", "portable-gui"}:
        errors.append("runtime 必須是 source 或 portable-gui")
    roots = manifest.get("roots", {})
    if not all(isinstance(roots.get(name), str) and roots[name] and "<" not in roots[name] for name in ["DATA_ROOT", "OUTPUT_ROOT"]):
        errors.append("請填 DATA_ROOT 與 OUTPUT_ROOT，兩者獨立設定")
    elif Path(roots["DATA_ROOT"]).resolve() == Path(roots["OUTPUT_ROOT"]).resolve():
        errors.append("DATA_ROOT 與 OUTPUT_ROOT 不可混成同一根")
    if manifest.get("repo_root") != str(root.resolve()):
        errors.append("repo_root 尚未核對目前工作目錄")
    if mode == "owner-migration" and not manifest.get("old_machine_writer_stopped"):
        errors.append("舊機 writer 尚未確認停用，不能啟用新機 writer")
    old_inventory: dict[str, Any] | None = None
    inventory = manifest.get("source_inventory")
    if mode == "owner-migration":
        if not isinstance(inventory, dict) or not inventory.get("path") or not re.fullmatch(r"[a-f0-9]{64}", inventory.get("sha256", "")):
            errors.append("完整移機缺可回驗的舊機清冊 path／sha256")
        else:
            inventory_path = Path(inventory["path"])
            if not inventory_path.is_file():
                errors.append("舊機清冊缺件")
            else:
                with inventory_path.open("rb") as handle:
                    inventory_hash = hashlib.file_digest(handle, "sha256").hexdigest()
                if inventory_hash != inventory["sha256"]:
                    errors.append("舊機清冊 hash 不符")
                else:
                    old_inventory = read_json(inventory_path)
                    if old_inventory.get("schema_version") != "baldr-machine-inventory.v1" or not isinstance(old_inventory.get("schedules"), list):
                        errors.append("舊機清冊必須先正規化為 baldr-machine-inventory.v1，保留原始匯出來源與 SHA")
    for asset in manifest.get("assets", []):
        path = Path(asset.get("path", ""))
        if re.search(r"auth\.json|credential|password|token", asset.get("id", "") + str(path), re.I):
            errors.append(f"憑證須在新機重新授權，不能搬移：{asset.get('id')}")
            continue
        if not asset.get("path") or "<" in str(path) or not path.exists():
            if asset.get("required"):
                errors.append(f"必要資產缺件：{asset.get('id')}")
            actions.append({"asset": asset.get("id"), "status": "missing"})
        elif asset.get("sha256"):
            if not path.is_file():
                errors.append(f"hash 資產必須是檔案：{asset.get('id')}")
            else:
                with path.open("rb") as handle:
                    actual = hashlib.file_digest(handle, "sha256").hexdigest()
                if actual != asset["sha256"]:
                    errors.append(f"資產 hash 不符：{asset.get('id')}")
                actions.append({"asset": asset.get("id"), "status": "hash_checked" if actual == asset["sha256"] else "hash_mismatch"})
        else:
            actions.append({"asset": asset.get("id"), "status": "exists_identity_pending"})
    catalog = windows_schedule_catalog(root)
    triggers = windows_schedule_triggers(root)
    desired = manifest.get("schedules", [])
    observed_list = manifest.get("observed_schedules", [])
    observed: dict[str, dict[str, Any]] = {}
    for item in observed_list:
        key = item["platform"] + ":" + item["id"]
        if key in observed:
            errors.append(f"觀測清冊重複：{key}")
        observed[key] = item
    seen: set[str] = set()
    excluded: set[str] = set()
    for item in manifest.get("excluded_schedules", []):
        key = item["platform"] + ":" + item["id"]
        if not item.get("reason", "").strip():
            errors.append(f"排除排程缺具名決議：{key}")
        elif key in excluded:
            errors.append(f"排除清冊重複：{key}")
        else:
            excluded.add(key)
    for item in desired:
        key = item["platform"] + ":" + item["id"]
        if key in seen:
            errors.append(f"目標清冊重複：{key}")
        if key in excluded:
            errors.append(f"排程不能同時復原與排除：{key}")
        seen.add(key)
        if not isinstance(item.get("desired_enabled"), bool):
            errors.append(f"排程缺明確啟用／停用狀態：{key}")
        if item["platform"] not in {"windows", "codex-cron", "codex-heartbeat"}:
            errors.append(f"未知排程平台：{key}")
        if not item.get("timezone") or not item.get("trigger"):
            errors.append(f"排程缺時區或 trigger：{key}")
        if item["platform"] == "windows":
            if triggers.get(item["id"]) != item.get("trigger"):
                errors.append(f"Windows trigger 與現行 EXPECTED_TASKS 不符：{key}")
            if catalog.get(item["id"]) != item.get("canonical_wrapper"):
                errors.append(f"Windows wrapper 與現行稽核器不符：{key}")
            elif not confined(root, item["canonical_wrapper"]).is_file():
                errors.append(f"Windows wrapper 缺件：{key}")
            if manifest.get("timezone") not in {"Pacific Standard Time", "America/Los_Angeles"}:
                errors.append(f"目前 generic registrar 不支援新機時區，需先逐項轉換審查：{key}")
        if manifest.get("runtime") == "portable-gui" and item["platform"] == "windows" and not manifest.get("source_scheduler_runtime_verified"):
            errors.append(f"可攜 GUI 不代表 source 排程 runtime 已驗：{key}")
        actual_schedule = observed.get(key)
        compared_fields = ["desired_enabled", "timezone", "trigger", "canonical_wrapper", "argv", "working_directory", "principal", "logon_type", "run_level", "execution_time_limit", "multiple_instances", "missed_start", "retry_policy", "power_policy", "notification_policy", "model", "reasoning_effort", "target_thread", "prompt_sha256"]
        differences = [] if actual_schedule is None else [field for field in compared_fields if item.get(field) != actual_schedule.get(field)]
        actions.append({"schedule": key, "action": "create_disabled_for_review" if actual_schedule is None else ("review_difference" if differences else "retain_existing"), "differences": differences, "desired_enabled": item.get("desired_enabled"), "natural_run": "not_verified"})
    if mode == "owner-migration":
        missing = {"windows:" + task_id for task_id in catalog} - seen - excluded
        if missing:
            errors.append("完整移機缺現行 Windows 任務或未提供明確排除決議：" + ", ".join(sorted(missing)))
        if old_inventory is not None:
            old_seen: set[str] = set()
            desired_by_key = {item["platform"] + ":" + item["id"]: item for item in desired}
            for old in old_inventory["schedules"]:
                key = old["platform"] + ":" + old["id"]
                if key in old_seen:
                    errors.append(f"舊機清冊重複：{key}")
                old_seen.add(key)
                if key not in seen and key not in excluded:
                    errors.append(f"舊機排程未復原或具名排除：{key}")
                if key in desired_by_key:
                    item = desired_by_key[key]
                    for field in ["desired_enabled", "notification_policy", "model", "reasoning_effort"]:
                        if old.get(field) != item.get(field):
                            errors.append(f"舊機 {field} 不應默默改變：{key}；另作具名變更決議後更新來源清冊")
    return {"schema_version": "baldr-bootstrap-plan.v1", "ready_for_configuration_review": not errors, "mode": mode, "errors": errors, "actions": actions, "windows_catalog_size": len(catalog), "mutations": [], "runtime_preflight": {"source_venv_exists": (root / ".venv/Scripts/python.exe").is_file(), "dependency_imports": "not_run", "ui_launch": "not_run", "scheduled_natural_run": "not_run"}, "verification": "計畫與存在／hash 核對；未安裝、註冊、啟用、觸發、搬資料或驗自然 run。"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    route_parser = commands.add_parser("route")
    route_parser.add_argument("--kind")
    route_parser.add_argument("--request", default="")
    route_parser.add_argument("--changed-file", action="append", default=[])
    init_parser = commands.add_parser("init-task")
    init_parser.add_argument("--task-id", required=True)
    init_parser.add_argument("--owner", required=True)
    init_parser.add_argument("--kind", required=True)
    init_parser.add_argument("--request", default="")
    init_parser.add_argument("--changed-file", action="append", default=[])
    check_parser = commands.add_parser("check")
    check_parser.add_argument("--task")
    check_parser.add_argument("--path", action="append")
    check_parser.add_argument("--context-metadata", action="store_true")
    context_parser = commands.add_parser("context")
    context_parser.add_argument("--domain", required=True)
    context_parser.add_argument("--request", default="")
    context_parser.add_argument("--level", type=int, default=2)
    context_parser.add_argument("--max-chars", type=int, default=12000)
    context_parser.add_argument("--inspect-file", action="append", default=[])
    context_parser.add_argument("--changed-file", action="append", default=[])
    context_parser.add_argument("--include-history", action="store_true")
    context_parser.add_argument("--format", choices=["json", "text"], default="json")
    inventory_parser = commands.add_parser("inventory")
    inventory_parser.add_argument("--base")
    inventory_parser.add_argument("--details", action="store_true")
    trace_parser = commands.add_parser("trace")
    trace_parser.add_argument("--inspect-file", action="append", required=True)
    trace_parser.add_argument("--symbol")
    commands.add_parser("issues")
    archives_parser = commands.add_parser("archives")
    archives_parser.add_argument("--path")
    bootstrap_parser = commands.add_parser("bootstrap-plan")
    bootstrap_parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    try:
        if args.command in {"context", "inventory", "trace", "issues"} or (args.command == "check" and args.context_metadata):
            # 直接執行 scripts/document_control.py 時仍只載入本 repo 的唯讀 helper。
            if not __package__:
                sys.path.insert(0, str(REPO_ROOT))
            from scripts import document_context
        if args.command == "route":
            result = route(root, kind=args.kind, request=args.request, changed=args.changed_file)
            passed = result["status"] == "classified"
        elif args.command == "init-task":
            result = init_task(root, task_id=args.task_id, kind=args.kind, owner=args.owner, paths=args.changed_file, request=args.request)
            passed = True
        elif args.command == "bootstrap-plan":
            result = bootstrap_plan(root, read_json(args.manifest))
            passed = result["ready_for_configuration_review"]
        elif args.command == "context":
            result = document_context.context(root, domain=args.domain, request=args.request, level=args.level,
                inspect=args.inspect_file, changed=args.changed_file, max_chars=args.max_chars, include_history=args.include_history)
            passed = True
        elif args.command == "inventory":
            result = document_context.inventory(root, base=args.base, details=args.details)
            passed = True
        elif args.command == "trace":
            result = document_context.trace(root, args.inspect_file, args.symbol)
            passed = not any(item["unknown"] for item in result["records"])
        elif args.command == "issues":
            result = document_context.issue_view(root)
            passed = True
        elif args.command == "archives":
            result = external_references.archive_view(root, path=args.path)
            passed = result["registry_available"] and (not args.path or bool(result["entries"]))
        else:
            result = check(root, paths=args.path, task_path=args.task)
            if args.context_metadata:
                result["errors"].extend(document_context.check_metadata(root))
                result["passed"] = not result["errors"]
            passed = result["passed"]
        if args.command == "context" and args.format == "text":
            print(document_context.render_context(result), end="")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if passed else 2
    except (ValueError, OSError, KeyError, TypeError, SyntaxError, UnicodeError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
