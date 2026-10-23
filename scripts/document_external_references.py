"""文件冷封存與精確 output 導航登記；只查 metadata，不讀外部證據內容。"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
from typing import Any
import json
import re

REGISTRY_PATH = "docs/03_data/COLD_ARCHIVE_REFERENCE_REGISTRY.json"
SCHEMA = "baldr-cold-archive-registry.v1"


def _normalized(value: str | Path) -> str:
    text = str(value)
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return os.path.normcase(os.path.normpath(text)).replace("\\", "/").rstrip("/")


def _relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or not path.parts or "\\" in value or path.is_absolute() or ".." in path.parts or ":" in value:
        raise ValueError(f"冷封存登記需要安全的repo相對路徑：{value}")
    return path


def load_registry(root: Path) -> dict[str, Any]:
    """只接受repo內普通治理檔；沒有登記時維持原越界檢查。"""
    source = root / REGISTRY_PATH
    if not source.exists():
        return {"schema_version": SCHEMA, "batches": [], "entries": [], "registry_available": False}
    cursor = source
    while cursor != root:
        info = cursor.lstat()
        if cursor.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("冷封存登記不接受symlink／reparse治理檔")
        cursor = cursor.parent
    data = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA:
        raise ValueError("冷封存登記schema_version不符")
    batches = {row["id"]: row for row in data.get("batches", [])}
    if len(batches) != len(data.get("batches", [])):
        raise ValueError("冷封存批次ID重複")
    authority_sources: dict[str, set[str]] = {}
    for batch in batches.values():
        archive = str(batch["archive_root"])
        if not (Path(archive).is_absolute() or PureWindowsPath(archive).is_absolute()) or ".." in PurePosixPath(archive.replace("\\", "/")).parts:
            raise ValueError("冷封存批次需要絕對且無跳脫的archive_root")
        if Path(archive).resolve().is_relative_to(root.resolve()):
            raise ValueError("冷封存archive_root必須在repo外")
        for key in ("scope_document", "reconciliation"):
            rel = _relative(str(batch[key]))
            target = root.joinpath(*rel.parts).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                raise ValueError(f"冷封存權威文件缺件或越界：{batch[key]}")
        scope = (root / batch["scope_document"]).read_text(encoding="utf-8-sig")
        authority_sources[batch["id"]] = set(re.findall(r"^\|\s*`?((?:output|dist)/[^|`\s]+)`?\s*\|", scope, flags=re.M))
        if not authority_sources[batch["id"]]:
            raise ValueError(f"冷封存權威範圍表沒有精確來源：{batch['id']}")
    seen: set[str] = set()
    for entry in data.get("entries", []):
        relative = _relative(str(entry["source_prefix"]))
        if len(relative.parts) < 2 or relative.parts[0] not in {"output", "dist"}:
            raise ValueError("冷封存只登記明示output／dist歷史根")
        if str(relative) in seen:
            raise ValueError("冷封存來源根重複")
        seen.add(str(relative))
        if entry.get("batch_id") not in batches:
            raise ValueError("冷封存來源引用未知批次")
        batch = batches[entry["batch_id"]]
        if str(relative) not in authority_sources[entry["batch_id"]]:
            raise ValueError(f"冷封存來源未列於批次權威範圍：{relative}")
        expected = str(batch["archive_root"]).rstrip("/\\") + "/" + str(relative)
        if _normalized(str(entry["archive_path"])) != _normalized(expected):
            raise ValueError(f"冷封存目標與批次／來源不符：{relative}")
        if entry.get("tracking") != "registered_external_evidence":
            raise ValueError("冷封存tracking狀態不符")
    for batch_id, expected_sources in authority_sources.items():
        actual_sources = {row["source_prefix"] for row in data["entries"] if row["batch_id"] == batch_id}
        if actual_sources != expected_sources:
            raise ValueError(f"冷封存登記與批次權威來源不完整：{batch_id}")
    data["registry_available"] = True
    _validate_output_registry(root, data)
    return data


def _validate_output_registry(root: Path, registry: dict[str, Any]) -> None:
    """普通 output 掛載導航獨立於冷封存批次，逐檔與引用文件登記。"""
    group = registry.get("repository_output_references")
    if group is None:
        return
    if not isinstance(group, dict) or group.get("mount_relative") != "output":
        raise ValueError("output 導航登記掛載範圍不符")
    mount_target = Path(str(group["mount_target"]))
    if not mount_target.is_absolute() or ".." in mount_target.parts:
        raise ValueError("output 掛載目標必須為固定絕對路徑")
    scope_rel = _relative(str(group["scope_document"]))
    scope = root.joinpath(*scope_rel.parts)
    _ordinary_repo_file(root, scope)
    listed = set(re.findall(r"^\|\s*`?((?:output)/[^|`\s]+)`?\s*\|", scope.read_text(encoding="utf-8-sig"), flags=re.M))
    rows = group.get("references")
    if not isinstance(rows, list) or not rows:
        raise ValueError("output 導航需要精確檔案清冊")
    seen: set[tuple[str, str]] = set()
    for row in rows:
        relative = _relative(str(row["source_file"]))
        document = _relative(str(row["source_document"]))
        _ordinary_repo_file(root, root.joinpath(*document.parts))
        key = (str(document), str(relative))
        if key in seen or len(relative.parts) < 2 or relative.parts[0] != "output":
            raise ValueError("output 導航來源重複或不在掛載內")
        seen.add(key)
        if str(relative) not in listed:
            raise ValueError("output 導航來源未列權威表")
        expected = mount_target.joinpath(*relative.parts[1:])
        if _normalized(str(row["target_path"])) != _normalized(expected):
            raise ValueError("output 導航目標不符固定掛載與來源")


def _ordinary_repo_file(root: Path, target: Path) -> None:
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("output 導航權威文件缺件或越界")
    cursor = target
    while cursor != root:
        info = cursor.lstat()
        if cursor.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("output 導航權威文件不得經連結")
        cursor = cursor.parent


def registered_output_reference(root: Path, lexical: Path, resolved: Path,
                                registry: dict[str, Any], source_document: str) -> dict[str, Any] | None:
    """只核已登記普通 output 檔的掛載與存在性，不讀內容或授金融資格。"""
    group = registry.get("repository_output_references")
    if not group or not lexical.is_relative_to(root):
        return None
    relative = lexical.relative_to(root).as_posix()
    matched = next((row for row in group["references"]
                    if row["source_file"] == relative and row["source_document"] == source_document), None)
    if matched is None:
        return None
    mount = root / "output"
    expected_mount = Path(group["mount_target"])
    if _normalized(mount.resolve(strict=True)) != _normalized(expected_mount):
        raise ValueError("output 掛載物理目標漂移")
    # 掛載點本身可以是既定 junction，下面每層只允許普通檔案／目錄。
    cursor = mount
    for part in lexical.relative_to(mount).parts:
        cursor = cursor / part
        info = cursor.lstat()
        if cursor.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("output 導航內部不得含連結")
    actual = lexical.resolve(strict=True)
    if (_normalized(actual) != _normalized(matched["target_path"])
            or _normalized(actual) != _normalized(resolved)
            or not actual.is_relative_to(expected_mount) or not actual.is_file()):
        raise ValueError("output 導航目標缺件或身份不符")
    if _normalized(mount.resolve(strict=True)) != _normalized(expected_mount):
        raise ValueError("output 掛載查詢期間漂移")
    return {"registry": REGISTRY_PATH, "source_file": relative,
            "target_path": matched["target_path"], "tracking": "registered_repository_output_navigation",
            "availability": "metadata_available", "target_exists": True,
            "content_verified": False, "financial_acceptance": False}


def registered_reference(root: Path, lexical: Path, resolved: Path, registry: dict[str, Any]) -> dict[str, Any] | None:
    """只分類精確登記且目標相符的連結；不准登記吞掉任意外部路徑。"""
    if not lexical.is_relative_to(root.absolute()):
        return None
    for entry in registry["entries"]:
        junction = root.joinpath(*PurePosixPath(entry["source_prefix"]).parts)
        if not lexical.is_relative_to(junction):
            continue
        suffix = lexical.relative_to(junction)
        record = {"registry": REGISTRY_PATH, "source_prefix": entry["source_prefix"],
                  "archive_path": entry["archive_path"], "batch_id": entry["batch_id"],
                  "tracking": "registered_external_evidence", "content_verified": False}
        try:
            info = junction.lstat()
        except FileNotFoundError:
            return {**record, "availability": "source_link_unavailable", "target_exists": False}
        reparse = junction.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        if not reparse:
            return None
        actual = os.readlink(junction)
        if _normalized(actual) != _normalized(entry["archive_path"]):
            raise ValueError(f"冷封存Junction目標漂移：{entry['source_prefix']}")
        expected = Path(entry["archive_path"]) / suffix
        if _normalized(resolved) != _normalized(expected):
            raise ValueError(f"冷封存內部連結越界：{entry['source_prefix']}/{suffix.as_posix()}")
        exists = resolved.exists()
        return {**record, "availability": "metadata_available" if exists else "external_target_unavailable", "target_exists": exists}
    return None


def archive_view(root: Path, path: str | None = None) -> dict[str, Any]:
    """從明示登記查原位置／封存位置；只讀連結及存在性metadata。"""
    registry = load_registry(root)
    selected = registry["entries"]
    if path:
        needle = _relative(path).as_posix()
        selected = [entry for entry in selected if needle == entry["source_prefix"] or needle.startswith(entry["source_prefix"] + "/")]
    rows = []
    for entry in selected:
        relative = path or entry["source_prefix"]
        lexical = Path(os.path.abspath(root / relative))
        observed = registered_reference(root, lexical, lexical.resolve(), registry)
        rows.append(observed or {**entry, "availability": "ordinary_directory_or_not_linked", "content_verified": False})
    return {"schema_version": "baldr-cold-archive-view.v1", "registry": REGISTRY_PATH,
            "registry_available": registry["registry_available"], "entries": rows, "count": len(rows),
            "limitation": "已登記外部證據不等於Git來源、內容核驗或產品接受；不讀raw bytes，不新增搬移／清理授權。"}
