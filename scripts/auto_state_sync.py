"""唯讀列出 Git 工作區狀態，或由指定 task owner 更新其 task.json。"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# 常見不應提交的排除規則 (對應 git_exclusions.md)
EXCLUSION_PATTERNS = [
    r"^\.superpowers/",
    r"(^|/)\.tmp\.driveupload/",
    r"^docs/agents/shared_state/(active_task\.yaml|handoff_log\.md)$",
    r"(^|/)\.pytest_cache/",
    r"(^|/)\.coverage$",
    r"(^|/)htmlcov/",
    r"(^|/)\.tox/",
    r"(^|/)\.cache/",
    r"\.log$",
    r"^logs/",
    r"^(venv|env|ENV)/",
    r"^\.env(?!\.example$)",
    r"^downloads/",
    r"^temp_downloads/",
    r"^(tmp|temp)/",
    r"^output/qa/update_tab/RUN_LOG\.txt$",
    r"^output/qa/update_tab/VALIDATION_REPORT\.md$",
    r"\.db$",
    r"\.sqlite",
]

def run_git_status(repo_root: Path | None = None) -> list[str]:
    """獲取 Git status 輸出的檔案清單。"""
    root = (repo_root or REPO_ROOT).resolve()
    try:
        res = subprocess.run(
            ["git", "status", "--short", "-z", "--untracked-files=all"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Git status 執行失敗: {res.stderr.strip()}")
        entries = res.stdout.split("\0")
        files: list[str] = []
        index = 0
        while index < len(entries) and entries[index]:
            entry = entries[index]
            status = entry[:2]
            path = entry[3:]
            files.append(path)
            index += 1
            if "R" in status or "C" in status:
                index += 1
        return files
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"無法執行 Git status: {exc}") from exc

def check_exclusions(files: list[str]) -> list[str]:
    """比對排除清單，檢查是否有不應被 stage 的檔案被變更或新增。"""
    warnings = []
    for file in files:
        normalized = file.replace("\\", "/")
        if normalized == ".env.example":
            continue
        for pattern in EXCLUSION_PATTERNS:
            if re.search(pattern, normalized):
                warnings.append(file)
                break
    return warnings

def build_active_task_content(
    content: str,
    files: list[str],
    warnings: list[str],
) -> str:
    """相容舊呼叫端的 YAML renderer；CLI 不會讀寫舊 singleton。"""
    block_lines = [
        "git_status:",
        f"  clean: {'true' if not files else 'false'}",
    ]
    if files:
        block_lines.append("  modified_files:")
        block_lines.extend(
            f"    - {json.dumps(file, ensure_ascii=False)}" for file in files
        )
    if warnings:
        block_lines.append("  warnings:")
        block_lines.extend(
            "    - "
            + json.dumps(
                f"不應 stage 的排除檔案已修改: {warning}",
                ensure_ascii=False,
            )
            for warning in warnings
        )
    else:
        block_lines.append("  warnings: []")
    new_block = "\n".join(block_lines) + "\n"

    pattern = re.compile(
        r"^git_status:\r?\n(?:^[ \t][^\r\n]*(?:\r?\n|$))*",
        re.MULTILINE,
    )
    if pattern.search(content):
        return pattern.sub(new_block, content, count=1)
    return content.rstrip() + "\n\n" + new_block


def resolve_task_path(task_argument: str, repo_root: Path | None = None) -> tuple[Path, str]:
    """只接受 repo 內 output/tasks/<task_id>/task.json 的明確相對路徑。"""
    root = (repo_root or REPO_ROOT).resolve()
    relative = Path(task_argument)
    if relative.is_absolute() or relative.drive:
        raise ValueError("--task 必須是 output/tasks/<task_id>/task.json repo 相對路徑")
    parts = relative.parts
    if (
        len(parts) != 4
        or parts[0] != "output"
        or parts[1] != "tasks"
        or parts[3] != "task.json"
        or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", parts[2])
    ):
        raise ValueError("--task 必須是 output/tasks/<task_id>/task.json repo 相對路徑")

    declared_tasks_root = root / "output" / "tasks"
    tasks_root = declared_tasks_root.resolve()
    declared_target = root / relative
    target = declared_target.resolve()
    if tasks_root != declared_tasks_root or target != declared_target:
        raise ValueError("--task 路徑不得經由 symlink／junction 別名解析")
    if not target.is_relative_to(tasks_root):
        raise ValueError("--task 路徑不得離開 repository 的 output/tasks")
    if target.parent.parent != tasks_root or target.parent.name != parts[2] or target.name != "task.json":
        raise ValueError("--task 路徑解析到不同 task；拒絕 symlink 或路徑別名")
    return target, parts[2]


def update_task_git_status(
    task_argument: str,
    owner: str,
    files: list[str],
    warnings: list[str],
    repo_root: Path | None = None,
) -> None:
    """驗證單一 task owner 後，以同目錄原子替換更新其 git_status 欄位。"""
    if not owner.strip():
        raise ValueError("--owner 必須是 task.json 內完全相同的非空 owner")
    task_path, task_id = resolve_task_path(task_argument, repo_root)
    if not task_path.is_file():
        raise FileNotFoundError(f"指定 task.json 不存在：{task_argument}")

    try:
        record = json.loads(task_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"指定 task.json 無法讀取：{task_argument}") from exc
    if not isinstance(record, dict) or record.get("schema_version") != "baldr-task.v1":
        raise ValueError("指定檔案不是支援的 baldr-task.v1 task.json")
    if record.get("task_id") != task_id:
        raise ValueError("task.json 的 task_id 與 output/tasks 目錄不符")
    if not isinstance(record.get("owner"), str) or record["owner"] != owner:
        raise ValueError("--owner 與 task.json owner 不完全相符；拒絕更新")
    if "git_status" in record and not isinstance(record["git_status"], dict):
        raise ValueError("task.json 的 git_status 欄位不是物件；拒絕覆寫")

    record["git_status"] = {
        "clean": not files,
        "modified_files": files,
        "warnings": [f"不應 stage 的排除檔案已修改: {warning}" for warning in warnings],
    }

    temp_path: Path | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=".task.json.",
            suffix=".tmp",
            dir=task_path.parent,
        )
        temp_path = Path(temp_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, task_path)
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"無法原子更新指定 task.json：{task_argument}") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure") and str(getattr(sys.stdout, "encoding", "")).lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", help="明確指定 output/tasks/<task_id>/task.json 才更新該 task")
    parser.add_argument("--owner", help="必須與指定 task.json 的 owner 完全相同")
    args = parser.parse_args(argv)
    if (args.task is None) != (args.owner is None):
        print("❌ --task 與 --owner 必須同時提供。", file=sys.stderr)
        return 2

    print("🔍 檢查 Git 工作區狀態與 exclusions...")
    try:
        files = run_git_status()
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    warnings = check_exclusions(files)

    if files:
        print(f"   發現已修改/新增的檔案 ({len(files)} 個)：")
        for file in files:
            prefix = "🔴 [警告/不應提交]" if file in warnings else "📝 [合規變更]"
            print(f"     {prefix} {file}")
    else:
        print("   ✅ Git 工作區乾淨，無未提交變更。")

    if warnings:
        print(f"\n⚠️ 警告：發現 {len(warnings)} 個不應提交的暫存/日誌/資料檔案被修改！")
        print("   請參考 docs/agents/git_exclusions.md 處理，不要將它們 stage！")

    if args.task is not None and args.owner is not None:
        try:
            update_task_git_status(args.task, args.owner, files, warnings)
            print(f"✅ 已更新指定 task 的 Git 狀態：{args.task}")
        except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1
    return 1 if warnings else 0

if __name__ == "__main__":
    raise SystemExit(main())
