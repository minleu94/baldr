"""固定來源與依賴的建置證據；不安裝依賴、不碰正式資料或現有交付。"""
from __future__ import annotations

import ast
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
    # 與原回測封存讀取的來源相同；frozen啟動身份也必須拒絕缺件或遭改寫的原檔。
    rule_sources = (
        "decision_module/strategies/baseline_score_executor.py",
        "decision_module/score_threshold_policy.py",
        "backtest_module/broker_simulator.py",
        "app_module/backtest_service.py",
    )
    if any((source / relative).exists() for relative in rule_sources):
        if not all((source / relative).is_file() for relative in rule_sources):
            raise ValueError("單股回測來源資料必須完整四檔")
        resource_hashes.update({
            relative: hashlib.sha256((source / relative).read_bytes()).hexdigest()
            for relative in rule_sources
        })
    # 舊固定 commit 的 spec 只收原四檔；僅對明示打包 v2 原件的 spec 加入新資源身份。
    v2_rule_sources = (
        "decision_module/strategies/stable_conservative_executor.py",
        "decision_module/strategies/momentum_aggressive_executor.py",
        "ui_qt/views/backtest/research_run_metadata.py",
    )
    spec = source / "packaging/baldr.spec"
    declared_sources: set[str] = set()
    if spec.is_file():
        # 只讀原 spec 的明示來源 tuple；不執行 spec，也不把註解或字串說明當打包宣告。
        tree = ast.parse(spec.read_text(encoding="utf-8"), filename=str(spec))
        for node in ast.walk(tree):
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "relative_source":
                declared = ast.literal_eval(node.iter)
                if not isinstance(declared, (tuple, list)) or any(not isinstance(item, str) for item in declared):
                    raise ValueError("單股回測原始來源宣告必須是明示路徑清單")
                declared_sources.update(declared)
    declared_v2 = [relative in declared_sources for relative in v2_rule_sources]
    if any(declared_v2):
        if not all(declared_v2) or not all((source / relative).is_file() for relative in v2_rule_sources):
            raise ValueError("單股回測 v2 原始來源宣告與檔案必須完整三檔")
        resource_hashes.update({
            relative: hashlib.sha256((source / relative).read_bytes()).hexdigest()
            for relative in v2_rule_sources
        })
    p07_rule_sources = (
        "decision_module/strategies/baldr_bollinger_executor.py",
        "decision_module/strategies/baldr_bollinger_contract.py",
        "decision_module/strategies/baldr_w_bottom_executor.py",
        "decision_module/strategies/baldr_w_bottom_contract.py",
        "analysis_module/pattern_analysis/causal_w_bottom.py",
        "analysis_module/technical_analysis/technical_date_support.py",
        "backtest_module/conservative_fill_policy.py",
        "financial_module/units.py",
    )
    declared_p07 = [relative in declared_sources for relative in p07_rule_sources]
    if any(declared_p07):
        if not all(declared_p07) or not all((source / relative).is_file() for relative in p07_rule_sources):
            raise ValueError("P07 研究策略原始來源宣告與檔案必須完整八檔")
        resource_hashes.update({
            relative: hashlib.sha256((source / relative).read_bytes()).hexdigest()
            for relative in p07_rule_sources
        })
    ma_rule_sources = (
        "decision_module/strategies/baldr_ma_alignment_executor.py",
        "decision_module/strategies/baldr_ma_alignment_contract.py",
    )
    declared_ma = [relative in declared_sources for relative in ma_rule_sources]
    if any(declared_ma):
        if (not all(declared_ma) or not all(declared_p07)
                or not all((source / relative).is_file() for relative in ma_rule_sources)):
            raise ValueError("四均線研究原始來源宣告須完整兩檔及原P07共用來源")
        resource_hashes.update({
            relative: hashlib.sha256((source / relative).read_bytes()).hexdigest()
            for relative in ma_rule_sources
        })
    causal_score_sources = (
        "analysis_module/technical_analysis/causal_score_input.py",
        "decision_module/indicator_reuse.py", "decision_module/strategy_configurator.py",
        "decision_module/scoring_engine.py",
        "decision_module/causal_score_pipeline.py",
    )
    declared_causal = [relative in declared_sources for relative in causal_score_sources]
    if any(declared_causal):
        if (not all(declared_causal) or not all(declared_v2)
                or not all((source / relative).is_file() for relative in causal_score_sources)):
            raise ValueError("因果計分原始來源宣告須完整五檔及原v2共用來源")
        resource_hashes.update({relative: hashlib.sha256((source / relative).read_bytes()).hexdigest()
                                for relative in causal_score_sources})
    return {
        "schema": "baldr-application-build.v1",
        "version": f"2026.10.06+{commit[:12]}", "source_commit": commit,
        "channel": "release", "dirty": False,
        "dependency_lock_sha256": lock_sha256, "resource_sha256": resource_hashes,
    }
