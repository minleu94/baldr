"""固定來源與依賴的建置證據；不安裝依賴、不碰正式資料或現有交付。"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import zipfile

LOCK_SCHEMA = "baldr-windows-dependency-lock.v1"
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


def installed_dependency_snapshot() -> dict[str, str]:
    """只讀目前環境的 distribution 版本；不呼叫 pip 或網路。"""
    return dict(sorted(
        (re.sub(r"[-_.]+", "-", item.metadata["Name"]).lower(), item.version)
        for item in importlib.metadata.distributions() if "Name" in item.metadata
    ))


def verify_dependency_lock(path: Path) -> str:
    """完整比對建置環境；不因版本不同而自行升級。回傳鎖檔 bytes SHA。"""
    raw = path.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("依賴鎖過大")
    value = json.loads(raw)
    if (not isinstance(value, dict) or value.get("schema") != LOCK_SCHEMA
            or not isinstance(value.get("dependencies"), dict)
            or not value["dependencies"]):
        raise ValueError("不支援的依賴鎖")
    if value.get("python") != platform.python_version():
        raise ValueError("Python 版本與依賴鎖不同")
    if value.get("machine") != platform.machine():
        raise ValueError("CPU 平台與依賴鎖不同")
    expected = value["dependencies"]
    if any(not isinstance(k, str) or not isinstance(v, str) or not v
           for k, v in expected.items()):
        raise ValueError("依賴鎖缺少有效版本")
    actual = installed_dependency_snapshot()
    differences = sorted(name for name in set(actual) | set(expected)
                         if actual.get(name) != expected.get(name))
    if differences:
        raise ValueError("依賴鎖不符：" + ", ".join(differences))
    return hashlib.sha256(raw).hexdigest()


def resolve_fixed_commit(repository: Path, commit: str) -> str:
    if not _COMMIT.fullmatch(commit):
        raise ValueError("建置必須明示完整 40 字元 commit，不接受分支或縮寫")
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=repository, capture_output=True, text=True, check=True,
    )
    if result.stdout.strip() != commit:
        raise ValueError("Git 解析的來源 commit 不符")
    return commit


def extract_source_archive(archive: Path, destination: Path) -> None:
    """只能建立新快照；拒絕路徑逸出、重複與 symlink archive entry。"""
    if destination.exists():
        raise ValueError("來源快照已存在，不能覆寫")
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        seen: set[str] = set()
        total = 0
        for item in entries:
            path = PurePosixPath(item.filename)
            normalized = item.filename.casefold().rstrip("/")
            if (path.is_absolute() or ".." in path.parts or "\\" in item.filename
                    or ":" in item.filename or normalized in seen
                    or ((item.external_attr >> 16) & 0o170000) == 0o120000):
                raise ValueError("來源 archive 含不安全或重複路徑")
            seen.add(normalized)
            total += item.file_size
            if total > 512 * 1024 * 1024:
                raise ValueError("來源 archive 超過 512 MiB 邊界")
        destination.mkdir(parents=True)
        source.extractall(destination)


def export_fixed_source(repository: Path, commit: str, job_root: Path) -> Path:
    resolve_fixed_commit(repository, commit)
    archive = job_root / "source.zip"
    if archive.exists() or (job_root / "source").exists():
        raise ValueError("建置工作已存在，請使用新 job")
    job_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "archive", "--format=zip", f"--output={archive}", commit],
        cwd=repository, check=True,
    )
    destination = job_root / "source"
    extract_source_archive(archive, destination)
    return destination


def verify_exported_source(archive: Path, source: Path) -> None:
    """逐檔核對固定 archive，避免建置後修改的 Python 快照冒充同版來源。"""
    with zipfile.ZipFile(archive) as stream:
        declared: set[str] = set()
        for item in stream.infolist():
            if item.is_dir():
                continue
            declared.add(item.filename)
            path = source / item.filename
            if path.is_symlink() or not path.is_file() or path.read_bytes() != stream.read(item):
                raise ValueError(f"固定來源快照已變更：{item.filename}")
    extras = [path.relative_to(source).as_posix() for path in source.rglob("*.py")
              if path.relative_to(source).as_posix() not in declared]
    if extras:
        raise ValueError("固定來源快照含額外程式：" + ", ".join(sorted(extras)))


def create_build_metadata(source: Path, commit: str, lock_sha256: str) -> dict[str, object]:
    if not _COMMIT.fullmatch(commit) or not re.fullmatch(r"[0-9a-f]{64}", lock_sha256):
        raise ValueError("建置來源或依賴身分錯誤")
    resource_hashes = {
        path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((source / "ui_qt").rglob("*"))
        if path.is_file() and path.suffix.lower() in {".png", ".ico", ".qss"}
    }
    # 研究來源需在 frozen 環境讀回原 kernel bytes；與固定 build 一起核身份，
    # 不用缺 source 時的假 hash，也不把市場／私人資料放進包內。
    kernels = (
        "analysis_module/technical_analysis/technical_indicators.py",
        "analysis_module/technical_analysis/indicator_kernels.py",
    )
    if any((source / relative).exists() for relative in kernels):
        if not all((source / relative).is_file() for relative in kernels):
            raise ValueError("kernel source 資料必須完整成對")
        resource_hashes.update({
            relative: hashlib.sha256((source / relative).read_bytes()).hexdigest()
            for relative in kernels
        })
    return {
        "schema": "baldr-application-build.v1",
        "version": f"2026.10.06+{commit[:12]}", "source_commit": commit,
        "channel": "release", "dirty": False,
        "dependency_lock_sha256": lock_sha256, "resource_sha256": resource_hashes,
    }
