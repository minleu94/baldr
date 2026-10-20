"""有界量測正常 MainWindow 啟動與 StrongStocks 真實列選取。"""

from __future__ import annotations

import argparse
import faulthandler
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import traceback
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
QA_BASE = ROOT / "output" / "qa" / "astra_engineering_20261003" / "native_final_v4"
ALLOWED_DATA_ROOT = QA_BASE / "data"
ALLOWED_SOURCE_OUTPUT_ROOT = (
    QA_BASE / "app_output" / "source_recovery_native_v23_b4r"
)
ALLOWED_CANDIDATE_DB = QA_BASE / "candidate_data" / "phase3c_candidate.db"
ALLOWED_RECEIPT = (
    QA_BASE
    / "native_harness"
    / "receipts"
    / "source-recovery-20261005T030746-5374d688d0.json"
)
ALLOWED_OUTPUT_ROOT = (
    ROOT / "output" / "qa" / "product_stage01_20261005" / "baseline_agent"
)
FORMAL_DATA_ROOT = Path("F:/Min/Python/Project/FA_Data")
MAX_CHILD_SECONDS = 90.0
CHILD_SELF_CLOSE_SECONDS = 78.0
READY_WAIT_SECONDS = 72.0
DATA_READY_WAIT_SECONDS = 68.0
MAX_SQLITE_SIDECAR_HASH_BYTES = 1024 * 1024


class ProfileError(RuntimeError):
    pass


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    return bool(checker()) if callable(checker) else False


def _require_exact_path(actual: Path, expected: Path, label: str) -> Path:
    resolved = _resolved(actual)
    if resolved != _resolved(expected):
        raise ProfileError(
            f"{label} 不在此 QA 包允許範圍；收到 {resolved}，僅允許 {_resolved(expected)}"
        )
    return resolved


def _reject_reparse_components(path: Path) -> None:
    current = path
    while current != current.parent:
        if current.exists() and (current.is_symlink() or _is_junction(current)):
            raise ProfileError(f"拒絕透過 symlink/junction 存取：{current}")
        current = current.parent


def _file_record(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "device": stat.st_dev,
        "inode": stat.st_ino,
        "is_file": path.is_file(),
    }


def _tree_stat(root: Path) -> dict[str, dict[str, Any]]:
    if not root.is_dir():
        raise ProfileError(f"輸入資料根不存在或不是目錄：{root}")
    entries: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or _is_junction(path):
            raise ProfileError(f"資料根包含 reparse alias：{path}")
        if path.is_file():
            entries[str(path.relative_to(root))] = _file_record(path)
    return entries


def _tree_digest(root: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    files = 0
    total_bytes = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.is_symlink() or _is_junction(path):
            raise ProfileError(f"QA output 輸入包含 reparse alias：{path}")
        rel = str(path.relative_to(root)).replace("\\", "/")
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                total_bytes += len(chunk)
        digest.update(b"\0")
        files += 1
    return digest.hexdigest(), files, total_bytes


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_sidecar_records(data_root: Path) -> dict[str, dict[str, Any]]:
    db_path = data_root / "sqlite" / "twstock.db"
    records: dict[str, dict[str, Any]] = {}
    for name, path in (
        ("db", db_path),
        ("wal", db_path.with_name(db_path.name + "-wal")),
        ("shm", db_path.with_name(db_path.name + "-shm")),
    ):
        record = _file_record(path)
        if name in {"wal", "shm"}:
            if record["size_bytes"] > MAX_SQLITE_SIDECAR_HASH_BYTES:
                raise ProfileError(
                    f"SQLite {name} sidecar exceeds bounded hash limit: {record['size_bytes']} bytes"
                )
            record["sha256"] = _sha256_file(path)
        records[name] = record
    return records


def _capture_input_identity(
    data_root: Path,
    candidate_db: Path,
    source_output_root: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    output_digest, output_count, output_bytes = _tree_digest(source_output_root)
    return {
        "data_tree": _tree_stat(data_root),
        "sqlite_sidecars": _sqlite_sidecar_records(data_root),
        "candidate_tree": _tree_stat(candidate_db.parent),
        "candidate_db": _file_record(candidate_db),
        "source_output": {
            "sha256": output_digest,
            "file_count": output_count,
            "bytes": output_bytes,
        },
        "receipt_sha256": _sha256_file(receipt_path),
    }


def _preflight(args: argparse.Namespace) -> dict[str, Any]:
    for raw_path in (
        args.data_root,
        args.source_output_root,
        args.candidate_db,
        args.receipt,
        args.output_dir,
    ):
        _reject_reparse_components(raw_path)
    data_root = _require_exact_path(args.data_root, ALLOWED_DATA_ROOT, "data-root")
    output_root = _require_exact_path(
        args.source_output_root, ALLOWED_SOURCE_OUTPUT_ROOT, "source-output-root"
    )
    candidate_db = _require_exact_path(
        args.candidate_db, ALLOWED_CANDIDATE_DB, "candidate-db"
    )
    receipt_path = _require_exact_path(args.receipt, ALLOWED_RECEIPT, "receipt")
    _require_exact_path(args.output_dir, ALLOWED_OUTPUT_ROOT, "output-dir")
    if _resolved(data_root) == _resolved(FORMAL_DATA_ROOT):
        raise ProfileError("拒絕正式 FA_Data 資料根")
    for path in (data_root, output_root, candidate_db, receipt_path):
        _reject_reparse_components(path)
    for required in (
        data_root / "sqlite" / "twstock.db",
        data_root / "meta_data" / "stock_data_whole.csv",
        output_root,
        candidate_db,
        receipt_path,
    ):
        if not required.exists():
            raise ProfileError(f"必要 QA 輸入不存在：{required}")
    for required_dir in (
        data_root / "daily_price",
        data_root / "daily_price_tpex",
        data_root / "meta_data",
        data_root / "meta_data" / "backup",
        data_root / "technical_analysis",
        data_root / "logs",
        data_root / "sqlite",
    ):
        if not required_dir.is_dir():
            raise ProfileError(f"TWStockConfig 可能會在來源根建立目錄，拒絕啟動：{required_dir}")
    data_tree = _tree_stat(data_root)
    sqlite_sidecars = _sqlite_sidecar_records(data_root)
    if not data_tree:
        raise ProfileError("QA data root 沒有既有檔案")
    output_sha, output_files, output_bytes = _tree_digest(output_root)
    candidate_tree = _tree_stat(candidate_db.parent)
    receipt_bytes = receipt_path.read_bytes()
    try:
        receipt = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProfileError(f"QA receipt 無法解析：{exc}") from exc
    receipt_data_root = _resolved(Path(receipt.get("data_root", "")))
    receipt_candidate_db = _resolved(Path(receipt.get("candidate_db_path", "")))
    receipt_output_root = _resolved(Path(receipt.get("phase_output_root", "")))
    if receipt_data_root != data_root or receipt_candidate_db != candidate_db:
        raise ProfileError("QA receipt 宣告的 data/candidate 輸入與固定路徑不一致")
    if receipt_output_root != output_root:
        raise ProfileError("QA receipt 宣告的 phase output 與固定來源 output 不一致")
    return {
        "data_root": str(data_root),
        "data_tree_before": data_tree,
        "sqlite_sidecars_before": sqlite_sidecars,
        "db": _file_record(data_root / "sqlite" / "twstock.db"),
        "stock_csv": _file_record(data_root / "meta_data" / "stock_data_whole.csv"),
        "candidate_db": _file_record(candidate_db),
        "candidate_tree_before": candidate_tree,
        "source_output_root": str(output_root),
        "source_output_sha256": output_sha,
        "source_output_file_count": output_files,
        "source_output_bytes": output_bytes,
        "receipt_path": str(receipt_path),
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "source_identity": {
            "source_capture_id": receipt.get("source_capture_id"),
            "phase_output_root": str(receipt_output_root),
            "candidate_db_path": str(receipt_candidate_db),
        },
        "database_policy": "SQLite URI mode=ro; PRAGMA query_only=ON; 不複製 4GB QA DB",
    }


def _input_identity_changes(
    preflight: dict[str, Any],
    data_root: Path,
    candidate_db: Path,
    source_output_root: Path,
    receipt_path: Path,
    observed: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    changes: dict[str, Any] = {}
    observed = observed or _capture_input_identity(
        data_root, candidate_db, source_output_root, receipt_path
    )
    data_tree = observed["data_tree"]
    data_diff = _tree_diff(preflight["data_tree_before"], data_tree)
    allowed_shm_mtime: dict[str, Any] | None = None
    if data_diff["changed_paths"]:
        shm_key = str(Path("sqlite") / "twstock.db-shm")
        before_tree = preflight["data_tree_before"]
        after_tree = data_tree
        before_shm = before_tree.get(shm_key)
        after_shm = after_tree.get(shm_key)
        before_shm_hash = preflight["sqlite_sidecars_before"]["shm"].get("sha256")
        after_shm_hash = observed["sqlite_sidecars"]["shm"].get("sha256")
        if (
            data_diff["changed_paths"] == [shm_key]
            and before_shm is not None
            and after_shm is not None
            and {key: value for key, value in before_shm.items() if key != "mtime_ns"}
            == {key: value for key, value in after_shm.items() if key != "mtime_ns"}
            and before_shm_hash == after_shm_hash
        ):
            allowed_shm_mtime = {
                "path": after_shm["path"],
                "before_mtime_ns": before_shm["mtime_ns"],
                "after_mtime_ns": after_shm["mtime_ns"],
                "size_bytes": after_shm["size_bytes"],
                "device": after_shm["device"],
                "inode": after_shm["inode"],
                "sha256_unchanged": after_shm_hash,
                "classification": "SQLite WAL SHM coordination metadata mtime only; no bytes or file identity changed",
            }
        else:
            changes["data_root_stat_tree"] = data_diff

    before_sidecars = preflight["sqlite_sidecars_before"]
    after_sidecars = observed["sqlite_sidecars"]
    for name in ("db", "wal"):
        if before_sidecars[name] != after_sidecars[name]:
            changes[f"sqlite_{name}_identity"] = {
                "before": before_sidecars[name],
                "after": after_sidecars[name],
            }
    if before_sidecars["shm"] != after_sidecars["shm"]:
        before_shm_stat = before_sidecars["shm"]
        after_shm_stat = after_sidecars["shm"]
        if (
            {key: value for key, value in before_shm_stat.items() if key != "mtime_ns"}
            != {key: value for key, value in after_shm_stat.items() if key != "mtime_ns"}
            or before_shm_stat.get("sha256") != after_shm_stat.get("sha256")
        ):
            changes["sqlite_shm_identity"] = {
                "before": before_shm_stat,
                "after": after_shm_stat,
            }

    if observed["candidate_tree"] != preflight["candidate_tree_before"]:
        changes["candidate_db_parent_stat_tree"] = _tree_diff(
            preflight["candidate_tree_before"], observed["candidate_tree"]
        )
    if observed["candidate_db"] != preflight["candidate_db"]:
        changes["candidate_db_stat"] = {
            "before": preflight["candidate_db"],
            "after": observed["candidate_db"],
        }
    before_output = {
        "sha256": preflight["source_output_sha256"],
        "file_count": preflight["source_output_file_count"],
        "bytes": preflight["source_output_bytes"],
    }
    if observed["source_output"] != before_output:
        changes["source_output_tree"] = {
            "before": before_output,
            "after": observed["source_output"],
        }
    if observed["receipt_sha256"] != preflight["receipt_sha256"]:
        changes["receipt_sha256"] = {
            "before": preflight["receipt_sha256"],
            "after": observed["receipt_sha256"],
        }
    return changes, allowed_shm_mtime


def _tree_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        "before_count": len(before),
        "after_count": len(after),
        "changed_paths": [
            key for key in set(before) | set(after) if before.get(key) != after.get(key)
        ][:30],
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * p) - 1)]


def _run_child(
    *,
    python: Path,
    run_dir: Path,
    data_root: Path,
    source_output_root: Path,
    candidate_db: Path,
    receipt_path: Path,
    platform: str,
    loaded_selections: int,
    label: str,
    run_number: int,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=False)
    private_output = run_dir / "app_output"
    shutil.copytree(source_output_root, private_output)
    private = run_dir / "private"
    settings_dir = private / "settings"
    temp_dir = private / "temp"
    mpl_dir = private / "mpl"
    app_config = private / "app_config"
    app_data = private / "app_data"
    app_cache = private / "app_cache"
    qstandard_roaming = private / "qstandard_roaming"
    qstandard_local = private / "qstandard_local"
    for path in (
        settings_dir,
        temp_dir,
        mpl_dir,
        app_config,
        app_data,
        app_cache,
        qstandard_roaming,
        qstandard_local,
    ):
        path.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "DATA_ROOT": str(data_root),
            "OUTPUT_ROOT": str(private_output),
            "PHASE3C_CANDIDATE_DB_PATH": str(candidate_db),
            "PROFILE": "integration_qa",
            "QT_QPA_PLATFORM": platform,
            "QT_SCALE_FACTOR": "1.25",
            "DATA_FRESHNESS_STATUS_ARTIFACT": str(
                QA_BASE
                / "app_output"
                / "scheduled"
                / "data_freshness"
                / "native_v4_root_freshness_20261005b.json"
            ),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "MPLCONFIGDIR": str(mpl_dir),
            "TEMP": str(temp_dir),
            "TMP": str(temp_dir),
            "TMPDIR": str(temp_dir),
            "XDG_CACHE_HOME": str(app_cache),
            "XDG_CONFIG_HOME": str(app_config),
            "XDG_DATA_HOME": str(app_data),
            "APPDATA": str(qstandard_roaming),
            "LOCALAPPDATA": str(qstandard_local),
            "APPDATA": str(private / "qstandard_roaming"),
            "LOCALAPPDATA": str(private / "qstandard_local"),
            "QA_PROFILE_CHILD": "1",
            "QA_PROFILE_RUN_DIR": str(run_dir),
            "QA_PROFILE_SELECTIONS": str(loaded_selections),
            "QA_PROFILE_PLATFORM": platform,
            "QA_PROFILE_LABEL": label,
            "QA_PROFILE_RUN_NUMBER": str(run_number),
            "QA_PROFILE_SOURCE_OUTPUT_ROOT": str(source_output_root),
            "QA_PROFILE_SOURCE_OUTPUT_SHA256": _tree_digest(source_output_root)[0],
            "QA_PROFILE_RECEIPT": str(receipt_path),
            "QA_PROFILE_CLOSE_REQUEST": str(run_dir / "COOPERATIVE_CLOSE"),
        }
    )
    result_path = run_dir / "result.json"
    marker_path = run_dir / "first_screen.json"
    env["QA_PROFILE_RESULT"] = str(result_path)
    env["QA_PROFILE_FIRST_SCREEN"] = str(marker_path)
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "importtime_stderr.txt"
    command = [
        str(python),
        "-X",
        "importtime",
        str(Path(__file__).resolve()),
        "--child",
    ]
    start = time.perf_counter()
    with stdout_path.open("w", encoding="utf-8", errors="backslashreplace") as out, stderr_path.open(
        "w", encoding="utf-8", errors="backslashreplace"
    ) as err:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=out,
            stderr=err,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
        )
        first_screen_wall_s: float | None = None
        try:
            while process.poll() is None:
                if marker_path.exists() and first_screen_wall_s is None:
                    first_screen_wall_s = time.perf_counter() - start
                elapsed = time.perf_counter() - start
                if elapsed >= MAX_CHILD_SECONDS:
                    (run_dir / "COOPERATIVE_CLOSE").write_text(
                        "parent 90s cap reached; request normal MainWindow.close()\n",
                        encoding="utf-8",
                    )
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        _write_json(
                            run_dir / "timeout.json",
                            {
                                "status": "child_still_running_after_cooperative_close_request",
                                "pid": process.pid,
                                "elapsed_s": elapsed,
                                "action": "no terminate/kill was issued",
                            },
                        )
                        raise ProfileError(
                            f"child pid={process.pid} 超過90秒且合作式關閉尚未完成；未終止程序，停止整批量測"
                        )
                    break
                time.sleep(0.1)
            return_code = process.wait()
        except BaseException:
            if process.poll() is None:
                try:
                    (run_dir / "COOPERATIVE_CLOSE").write_text(
                        "parent exception; request normal MainWindow.close()\n",
                        encoding="utf-8",
                    )
                except OSError:
                    pass
            raise
    wall_s = time.perf_counter() - start
    child_result = None
    if result_path.exists():
        child_result = json.loads(result_path.read_text(encoding="utf-8"))
    imports = _summarize_importtime(stderr_path)
    result = {
        "label": label,
        "run_number": run_number,
        "platform": platform,
        "pid": process.pid,
        "external_process_wall_s": wall_s,
        "parent_observed_first_screen_s": first_screen_wall_s,
        "return_code": return_code,
        "child": child_result,
        "importtime_summary": imports,
        "source_output_copy": {
            "sha256": env["QA_PROFILE_SOURCE_OUTPUT_SHA256"],
            "path": str(private_output),
        },
        "files": {
            "stdout": str(stdout_path),
            "importtime_stderr": str(stderr_path),
            "child_result": str(result_path),
        },
    }
    _write_json(run_dir / "run.json", result)
    if return_code != 0:
        raise ProfileError(
            f"child run {run_number} 結束碼 {return_code}; 檢視 {stdout_path} 與 {stderr_path}"
        )
    if not child_result or child_result.get("first_screen", {}).get("status") != "operable":
        raise ProfileError(f"child run {run_number} 未達可操作首屏：{result_path}")
    if (
        child_result.get("first_screen", {})
        .get("workbench_first_data", {})
        .get("status")
        != "complete"
    ):
        raise ProfileError(
            f"child run {run_number} Workbench 首次資料未完成：{result_path}"
        )
    return result


def _summarize_importtime(path: Path) -> dict[str, Any]:
    groups: dict[str, int] = {"ui_qt.views": 0, "application_services": 0, "other": 0}
    count = 0
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.startswith("import time:"):
                continue
            parts = line.split("|", 2)
            if len(parts) != 3:
                continue
            try:
                self_us = int(parts[0].split(":", 1)[1].strip())
            except ValueError:
                continue
            module = parts[2].strip()
            if module.startswith("ui_qt.views"):
                group = "ui_qt.views"
            elif module.startswith(("app_module", "data_module", "decision_module", "backtest_module", "portfolio_module", "runtime")):
                group = "application_services"
            else:
                group = "other"
            groups[group] += self_us
            count += 1
    except OSError:
        pass
    return {
        "measurement": "-X importtime self-time grouped by module prefix; excludes cumulative double counting",
        "module_count": count,
        "group_self_time_ms": {key: value / 1000 for key, value in groups.items()},
    }


def _validate_child_environment() -> Path:
    required_env = (
        "DATA_ROOT",
        "OUTPUT_ROOT",
        "PHASE3C_CANDIDATE_DB_PATH",
        "PROFILE",
        "QT_QPA_PLATFORM",
        "QA_PROFILE_RUN_DIR",
        "QA_PROFILE_LABEL",
        "QA_PROFILE_RUN_NUMBER",
        "QA_PROFILE_SOURCE_OUTPUT_ROOT",
        "QA_PROFILE_SOURCE_OUTPUT_SHA256",
        "QA_PROFILE_RECEIPT",
        "QA_PROFILE_RESULT",
        "QA_PROFILE_FIRST_SCREEN",
    )
    missing = [name for name in required_env if not os.environ.get(name)]
    if missing:
        raise ProfileError(f"child mode missing required isolated QA environment: {missing}")
    label = os.environ["QA_PROFILE_LABEL"]
    if not label.replace("-", "").replace("_", "").isalnum():
        raise ProfileError("child label is invalid")
    try:
        run_number = int(os.environ["QA_PROFILE_RUN_NUMBER"])
    except ValueError as exc:
        raise ProfileError("child run number is invalid") from exc
    expected_run_dir = ALLOWED_OUTPUT_ROOT / label / f"run-{run_number:02d}"
    raw_run_dir = Path(os.environ["QA_PROFILE_RUN_DIR"])
    for path in (
        raw_run_dir,
        Path(os.environ["DATA_ROOT"]),
        Path(os.environ["OUTPUT_ROOT"]),
        Path(os.environ["PHASE3C_CANDIDATE_DB_PATH"]),
        Path(os.environ["QA_PROFILE_SOURCE_OUTPUT_ROOT"]),
        Path(os.environ["QA_PROFILE_RECEIPT"]),
    ):
        _reject_reparse_components(path)
    run_dir = _require_exact_path(raw_run_dir, expected_run_dir, "child run dir")
    _require_exact_path(Path(os.environ["DATA_ROOT"]), ALLOWED_DATA_ROOT, "child DATA_ROOT")
    _require_exact_path(
        Path(os.environ["PHASE3C_CANDIDATE_DB_PATH"]),
        ALLOWED_CANDIDATE_DB,
        "child candidate DB",
    )
    _require_exact_path(
        Path(os.environ["QA_PROFILE_SOURCE_OUTPUT_ROOT"]),
        ALLOWED_SOURCE_OUTPUT_ROOT,
        "child source output root",
    )
    _require_exact_path(Path(os.environ["QA_PROFILE_RECEIPT"]), ALLOWED_RECEIPT, "child receipt")
    _require_exact_path(Path(os.environ["OUTPUT_ROOT"]), run_dir / "app_output", "child OUTPUT_ROOT")
    _require_exact_path(
        Path(os.environ["QA_PROFILE_CLOSE_REQUEST"]),
        run_dir / "COOPERATIVE_CLOSE",
        "child close-request path",
    )
    _require_exact_path(Path(os.environ["QA_PROFILE_RESULT"]), run_dir / "result.json", "child result path")
    _require_exact_path(
        Path(os.environ["QA_PROFILE_FIRST_SCREEN"]),
        run_dir / "first_screen.json",
        "child first-screen path",
    )
    if os.environ["PROFILE"] != "integration_qa":
        raise ProfileError("child PROFILE must be integration_qa")
    if os.environ["QT_QPA_PLATFORM"] not in ("offscreen", "windows"):
        raise ProfileError("child Qt platform is outside the supported set")
    if not run_dir.is_dir() or not Path(os.environ["OUTPUT_ROOT"]).is_dir():
        raise ProfileError("child run/output directories must already exist")
    expected_digest = os.environ["QA_PROFILE_SOURCE_OUTPUT_SHA256"]
    source_digest, source_count, source_bytes = _tree_digest(ALLOWED_SOURCE_OUTPUT_ROOT)
    copy_digest, copy_count, copy_bytes = _tree_digest(Path(os.environ["OUTPUT_ROOT"]))
    if source_digest != expected_digest:
        raise ProfileError("child source output SHA-256 differs from parent pin")
    if (copy_digest, copy_count, copy_bytes) != (expected_digest, source_count, source_bytes):
        raise ProfileError("child private output copy differs from pinned QA source output")
    return run_dir


def _child_mode() -> int:
    import json
    import logging
    import threading
    from collections import defaultdict

    import psutil

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    run_dir = _validate_child_environment()
    result_path = Path(os.environ["QA_PROFILE_RESULT"])
    first_screen_path = Path(os.environ["QA_PROFILE_FIRST_SCREEN"])
    close_request_path = Path(os.environ["QA_PROFILE_CLOSE_REQUEST"])
    launch_perf = time.perf_counter()
    process = psutil.Process(os.getpid())
    cpu_start = time.process_time()

    def _process_read_bytes(target: Any) -> int | None:
        try:
            value = target.io_counters().read_bytes
            return int(value) if value is not None else None
        except (AttributeError, psutil.Error, OSError):
            return None

    def _rss_bytes(target: Any) -> int:
        try:
            return int(target.memory_info().rss)
        except (psutil.Error, OSError):
            return 0

    def _process_tree_sample(target: Any) -> tuple[int, int, int | None]:
        total_rss = _rss_bytes(target)
        descendant_count = 0
        total_read_bytes = _process_read_bytes(target)
        try:
            descendants = target.children(recursive=True)
        except (psutil.Error, OSError):
            descendants = []
        for child in descendants:
            try:
                total_rss += _rss_bytes(child)
                child_read = _process_read_bytes(child)
                if total_read_bytes is not None and child_read is not None:
                    total_read_bytes += child_read
                elif child_read is not None:
                    total_read_bytes = child_read
                descendant_count += 1
            except (psutil.Error, OSError):
                continue
        return total_rss, descendant_count, total_read_bytes

    read_start = _process_read_bytes(process)
    current_rss = _rss_bytes(process)
    sampler_stop = threading.Event()
    sampler = {
        "peak_process_tree_rss_bytes": current_rss,
        "peak_process_rss_bytes": current_rss,
        "sampled_descendant_count_max": 0,
        "samples": 1,
        "read_bytes_max": read_start,
    }

    def sample_process() -> None:
        while not sampler_stop.wait(0.02):
            try:
                tree_rss, descendants, read_bytes = _process_tree_sample(process)
                sampler["peak_process_tree_rss_bytes"] = max(
                    sampler["peak_process_tree_rss_bytes"], tree_rss
                )
                sampler["peak_process_rss_bytes"] = max(
                    sampler["peak_process_rss_bytes"], _rss_bytes(process)
                )
                sampler["sampled_descendant_count_max"] = max(
                    sampler["sampled_descendant_count_max"], descendants
                )
                if read_bytes is not None:
                    previous = sampler["read_bytes_max"]
                    sampler["read_bytes_max"] = (
                        read_bytes if previous is None else max(previous, read_bytes)
                    )
                sampler["samples"] += 1
            except (psutil.Error, OSError):
                continue

    sampler_thread = threading.Thread(target=sample_process, daemon=True, name="qa-profile-sampler")
    sampler_thread.start()
    timeline: list[dict[str, Any]] = []
    calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
    window: Any = None
    app: Any = None
    qstandard_paths: dict[str, str] = {}
    runtime_workers: list[str] = []
    industry_mapper_observation: dict[str, Any] = {
        "status": "not_captured",
        "source": "existing IndustryMapper.industry_index_df.attrs value; no rowset hash recomputation",
    }
    strong_stocks_source_observation: dict[str, Any] = {"status": "not_loaded"}
    failure: str | None = None
    selection_result: dict[str, Any] | None = None
    ready_state: dict[str, Any] = {
        "done": False,
        "status": "not_started",
        "workbench_first_data": {"status": "not_started"},
    }

    def _measure(label: str, callback: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            wall0 = time.perf_counter()
            cpu0 = time.process_time()
            read0 = _process_read_bytes(process)
            rss0 = _rss_bytes(process)
            try:
                return callback(*args, **kwargs)
            finally:
                read1 = _process_read_bytes(process)
                calls[label].append(
                    {
                        "wall_ms": (time.perf_counter() - wall0) * 1000,
                        "cpu_ms": (time.process_time() - cpu0) * 1000,
                        "read_bytes_delta": (
                            None if read0 is None or read1 is None else read1 - read0
                        ),
                        "rss_before_bytes": rss0,
                        "rss_after_bytes": _rss_bytes(process),
                    }
                )

        return wrapped

    try:
        # 將所有會自行建立檔案 handler 的舊模組 logger 關閉在子程序記憶體內。
        for logger_name in (
            "data_module.config",
            "data_module.db_manager",
            "data_module.data_loader",
            "data_module.data_processor",
        ):
            logger = logging.getLogger(logger_name)
            logger.handlers.clear()
            logger.addHandler(logging.NullHandler())
            logger.propagate = False

        import PySide6
        from PySide6.QtCore import QCoreApplication, QSettings, QStandardPaths, Qt, QTimer
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QAbstractButton, QApplication, QMessageBox

        stage_start = time.perf_counter()
        from ui_qt import main as main_module
        timeline.append(
            {
                "phase": "ui_qt.main_and_eager_product_imports",
                "wall_ms": (time.perf_counter() - stage_start) * 1000,
                "cpu_ms": (time.process_time() - cpu_start) * 1000,
                "rss_bytes": _rss_bytes(process),
                "read_bytes_delta": _read_delta(read_start, _process_read_bytes(process)),
            }
        )

        from ui_qt.views.portfolio_view import PortfolioView
        view_types = [
            getattr(main_module, name, None)
            for name in (
                "StrongStocksView",
                "WeakStocksView",
                "MarketRegimeView",
                "StrongIndustriesView",
                "WeakIndustriesView",
                "RecommendationView",
                "UpdateView",
                "BacktestView",
                "WatchlistView",
                "StockResearchWorkspace",
                "SmartMoneyFlowView",
                "DecisionDeskView",
                "UnifiedDecisionWorkbenchView",
                "RuntimeView",
            )
        ] + [PortfolioView]
        service_types: list[Any] = []
        for name in (
            "TWStockConfig",
            "UpdateService",
            "BacktestService",
            "BrokerFlowService",
            "WatchlistService",
            "UniverseService",
            "CurrentRestatedMLRunRegistry",
            "StockResearchReportReadService",
            "DecisionOutcomeJourneyService",
            "PortfolioService",
            "JournalService",
            "IndustryStrengthService",
            "ScreeningService",
            "RegimeService",
            "RecommendationService",
        ):
            candidate = getattr(main_module, name, None)
            if candidate is not None:
                service_types.append(candidate)
        # composition 內部的真實 constructors 也單獨計時。
        from decision_module.industry_mapper import IndustryMapper
        from decision_module.stock_screener import StockScreener
        from decision_module.market_regime_detector import MarketRegimeDetector
        from app_module.screening_service import ScreeningService
        from app_module.regime_service import RegimeService
        from app_module.recommendation_service import RecommendationService
        from app_module.portfolio_service import PortfolioService
        from app_module.journal_service import JournalService
        service_types.extend((IndustryMapper, StockScreener, MarketRegimeDetector))
        service_types.extend(
            (
                ScreeningService,
                RegimeService,
                RecommendationService,
                PortfolioService,
                JournalService,
            )
        )

        seen: set[int] = set()
        for cls in service_types:
            if not isinstance(cls, type) or id(cls) in seen:
                continue
            seen.add(id(cls))
            original = getattr(cls, "__init__", None)
            if not callable(original):
                continue
            setattr(cls, "__init__", _measure(f"service.{cls.__module__}.{cls.__name__}", original))
        for cls in view_types:
            if not isinstance(cls, type) or id(cls) in seen:
                continue
            seen.add(id(cls))
            original = getattr(cls, "__init__", None)
            if callable(original):
                setattr(cls, "__init__", _measure(f"view.{cls.__module__}.{cls.__name__}", original))

        main_module.build_decision_service_composition = _measure(
            "service.build_decision_service_composition",
            main_module.build_decision_service_composition,
        )
        main_module.build_runtime_ui_composition = _measure(
            "service.build_runtime_ui_composition",
            main_module.build_runtime_ui_composition,
        )
        original_setup_ui = main_module.MainWindow._setup_ui
        main_module.MainWindow._setup_ui = _measure("ui.MainWindow._setup_ui", original_setup_ui)

        # Fail closed if normal startup unexpectedly enters the legacy writable DBManager.
        # No constructor is substituted unless that forbidden path is reached.
        from data_module.db_manager import DBManager

        def _reject_writable_dbmanager(self: Any, *_: Any, **__: Any) -> None:
            _write_json(
                run_dir / "unsafe_dbmanager_reached.json",
                {
                    "status": "rejected_before_original_init",
                    "message": "MainWindow startup attempted the writable DBManager path against the QA input root",
                    "stack": traceback.format_stack(),
                },
            )
            raise ProfileError("startup attempted writable DBManager; QA input was protected")

        DBManager.__init__ = _reject_writable_dbmanager

        settings_dir = str(Path(os.environ["TEMP"]).parent / "settings")
        Path(settings_dir).mkdir(parents=True, exist_ok=True)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            settings_dir,
        )

        stage_start = time.perf_counter()
        app = QApplication([])
        QCoreApplication.setOrganizationName("BaldrQA")
        QCoreApplication.setApplicationName("ProductStage01Baseline")
        qstandard_paths = {
            "AppConfigLocation": QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppConfigLocation
            ),
            "AppDataLocation": QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppDataLocation
            ),
            "AppLocalDataLocation": QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppLocalDataLocation
            ),
            "CacheLocation": QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.CacheLocation
            ),
            "GenericCacheLocation": QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.GenericCacheLocation
            ),
        }
        main_module.apply_app_theme(app)
        timeline.append(
            {
                "phase": "QApplication_and_theme_ready",
                "wall_ms": (time.perf_counter() - stage_start) * 1000,
                "cpu_ms": (time.process_time() - cpu_start) * 1000,
                "rss_bytes": _rss_bytes(process),
                "read_bytes_delta": _read_delta(read_start, _process_read_bytes(process)),
            }
        )

        policy_path = run_dir / "private" / "settings" / "personal_policy.json"
        stage_start = time.perf_counter()
        window = main_module.MainWindow(policy_config_path=policy_path)
        screening_service = getattr(window, "screening_service", None)
        stock_screener = getattr(screening_service, "stock_screener", None)
        recent_stock_provider = getattr(stock_screener, "recent_stock_provider", None)
        if callable(recent_stock_provider):
            original_recent_stock_provider = recent_stock_provider

            def _capture_real_stock_source(
                period: str, volume_lookback: int
            ) -> Any:
                nonlocal strong_stocks_source_observation
                frame = original_recent_stock_provider(period, volume_lookback)
                if frame is not None:
                    date_range: dict[str, str | None] = {"from": None, "through": None}
                    if "日期" in getattr(frame, "columns", ()):
                        observed_dates = frame["日期"].dropna()
                        if len(observed_dates):
                            date_range = {
                                "from": str(observed_dates.min()),
                                "through": str(observed_dates.max()),
                            }
                    strong_stocks_source_observation = {
                        "status": "captured_real_reader_result",
                        "source": "existing StockScreener.recent_stock_provider; returned real frame unchanged",
                        "data_root": os.environ["DATA_ROOT"],
                        "database_path": str(Path(os.environ["DATA_ROOT"]) / "sqlite" / "twstock.db"),
                        "provider_period": period,
                        "volume_lookback": volume_lookback,
                        "frame_rows": len(frame.index),
                        "frame_columns": [str(column) for column in frame.columns],
                        "date_range": date_range,
                    }
                else:
                    strong_stocks_source_observation = {
                        "status": "real_reader_returned_none",
                        "data_root": os.environ["DATA_ROOT"],
                        "database_path": str(Path(os.environ["DATA_ROOT"]) / "sqlite" / "twstock.db"),
                        "provider_period": period,
                        "volume_lookback": volume_lookback,
                    }
                return frame

            stock_screener.recent_stock_provider = _capture_real_stock_source
        industry_mapper = getattr(screening_service, "industry_mapper", None)
        industry_frame = getattr(industry_mapper, "industry_index_df", None)
        if industry_frame is not None:
            existing_observation = getattr(industry_frame, "attrs", {}).get(
                "industry_index_source_observation"
            )
            if isinstance(existing_observation, dict):
                industry_mapper_observation = {
                    "status": "captured_existing_observation",
                    "source": "existing IndustryMapper.industry_index_df.attrs value; no rowset hash recomputation",
                    "frame_rows": len(industry_frame.index),
                    "row_count": existing_observation.get("row_count"),
                    "rowset_sha256": existing_observation.get("rowset_sha256"),
                    "date_range": existing_observation.get("date_range"),
                    "source_id": existing_observation.get("source_id"),
                    "storage_kind": existing_observation.get("storage_kind"),
                    "status_value": existing_observation.get("status"),
                    "observation_sha256": existing_observation.get("observation_sha256"),
                }
            else:
                industry_mapper_observation = {
                    "status": "frame_present_observation_missing",
                    "source": "existing IndustryMapper.industry_index_df.attrs value; no rowset hash recomputation",
                    "frame_rows": len(industry_frame.index),
                    "attrs_keys": sorted(str(key) for key in getattr(industry_frame, "attrs", {})),
                }
        source_service = getattr(window, "workbench_source_service", None)
        if source_service is not None and callable(getattr(source_service, "inspect", None)):
            source_service.inspect = _measure(
                "service.WorkbenchSourceService.inspect",
                source_service.inspect,
            )
        window.show()
        timeline.append(
            {
                "phase": "MainWindow_constructed_and_show_called",
                "wall_ms": (time.perf_counter() - stage_start) * 1000,
                "cpu_ms": (time.process_time() - cpu_start) * 1000,
                "rss_bytes": _rss_bytes(process),
                "read_bytes_delta": _read_delta(read_start, _process_read_bytes(process)),
            }
        )

        ready_state.update(done=False, status="waiting")
        ready_deadline = time.perf_counter() + READY_WAIT_SECONDS
        completion_deadline = time.perf_counter() + CHILD_SELF_CLOSE_SECONDS
        data_ready_deadline = time.perf_counter() + DATA_READY_WAIT_SECONDS

        def _ready_check() -> bool:
            if window is None or not window.isVisible():
                return False
            nav = getattr(window, "left_navigation", None)
            stack = getattr(window, "workspace_stack", None)
            workbench = getattr(window, "workbench_view", None)
            if nav is None or stack is None or workbench is None:
                return False
            if not isinstance(workbench, main_module.UnifiedDecisionWorkbenchView):
                ready_state["shell_fallback_type"] = type(workbench).__name__
                return False
            if not nav.isVisible() or not stack.isVisible() or not workbench.isVisible():
                return False
            if stack.currentWidget() is not workbench:
                return False
            enabled_visible = [
                widget
                for widget in window.findChildren(QAbstractButton)
                if widget.isVisible() and widget.isEnabled()
            ]
            return bool(enabled_visible)

        def _first_screen_payload() -> dict[str, Any]:
            return {
                "status": "operable",
                "definition": "shown MainWindow + visible selected Workbench + visible enabled Qt button + visible navigation/workspace stack",
                "active_workspace": getattr(window, "_current_workspace_key", "workbench"),
                "main_window_visible": bool(window.isVisible()),
                "workbench_visible": bool(window.workbench_view.isVisible()),
                "visible_enabled_button_count": sum(
                    1
                    for widget in window.findChildren(QAbstractButton)
                    if widget.isVisible() and widget.isEnabled()
                ),
                "workbench_refresh_worker_running": bool(
                    getattr(getattr(window, "workbench_view", None), "_refresh_worker", None)
                    and window.workbench_view._refresh_worker.isRunning()
                ),
                "workbench_refresh_pending": bool(
                    getattr(getattr(window, "workbench_view", None), "_refresh_pending", False)
                ),
                "workbench_last_good_dashboard_present": bool(
                    getattr(getattr(window, "workbench_view", None), "_last_good_dashboard", None)
                ),
                "elapsed_since_child_start_s": time.perf_counter() - launch_perf,
            }

        def _watch_workbench_data() -> None:
            workbench = getattr(window, "workbench_view", None)
            worker = getattr(workbench, "_refresh_worker", None)
            worker_running = False
            if worker is not None:
                try:
                    worker_running = bool(worker.isRunning())
                except RuntimeError:
                    worker_running = False
            pending = bool(getattr(workbench, "_refresh_pending", False))
            dashboard = getattr(workbench, "_last_good_dashboard", None)
            if dashboard is not None and not worker_running and not pending:
                ready_state["workbench_first_data"] = {
                    "status": "complete",
                    "elapsed_since_child_start_s": time.perf_counter() - launch_perf,
                    "dashboard_type": type(dashboard).__name__,
                    "decision_date": str(getattr(dashboard, "as_of_date", "")),
                    "refresh_worker_running": worker_running,
                    "refresh_pending": pending,
                    "meta_label": str(getattr(getattr(workbench, "meta_label", None), "text", lambda: "")()),
                }
                if int(os.environ.get("QA_PROFILE_SELECTIONS", "0")) > 0:
                    QTimer.singleShot(0, _run_loaded_selection_measurement)
                else:
                    QTimer.singleShot(800, _close_owned_window)
                return
            if (
                worker is None
                and not worker_running
                and not pending
                and time.perf_counter() >= ready_deadline + 2.0
            ):
                ready_state["workbench_first_data"] = {
                    "status": "failed_no_good_dashboard",
                    "elapsed_since_child_start_s": time.perf_counter() - launch_perf,
                    "refresh_worker_present": worker is not None,
                    "refresh_worker_running": worker_running,
                    "refresh_pending": pending,
                    "meta_label": str(getattr(getattr(workbench, "meta_label", None), "text", lambda: "")()),
                }
                QTimer.singleShot(0, _close_owned_window)
                return
            if time.perf_counter() >= data_ready_deadline:
                ready_state["workbench_first_data"] = {
                    "status": "timeout",
                    "elapsed_since_child_start_s": time.perf_counter() - launch_perf,
                    "refresh_worker_present": worker is not None,
                    "refresh_worker_running": worker_running,
                    "refresh_pending": pending,
                }
                QTimer.singleShot(0, _close_owned_window)
                return
            QTimer.singleShot(50, _watch_workbench_data)

        def _mark_ready() -> None:
            if ready_state["done"]:
                return
            if _ready_check():
                ready_state.update(done=True, status="operable")
                payload = _first_screen_payload()
                _write_json(first_screen_path, payload)
                QTimer.singleShot(0, _watch_workbench_data)
                return
            if time.perf_counter() >= ready_deadline:
                ready_state.update(done=True, status="not_operable_timeout")
                ready_state["detail"] = "window did not meet operable predicate within 72s"
                QTimer.singleShot(0, _close_owned_window)
                return
            QTimer.singleShot(25, _mark_ready)

        def _close_owned_window() -> None:
            if window is not None:
                try:
                    window.close()
                except RuntimeError:
                    pass

        def _cooperative_watch() -> None:
            if close_request_path.exists():
                if not ready_state.get("cooperative_close_requested"):
                    runtime_workers.extend(_worker_state())
                    ready_state["cooperative_close_requested"] = True
                if window is not None:
                    try:
                        window.close()
                    except RuntimeError:
                        pass
                QTimer.singleShot(100, _cooperative_watch)
                return
            if time.perf_counter() >= completion_deadline:
                if not ready_state.get("cooperative_close_requested"):
                    runtime_workers.extend(_worker_state())
                    try:
                        with (run_dir / "stack_at_78s.txt").open("w", encoding="utf-8") as handle:
                            faulthandler.dump_traceback(file=handle, all_threads=True)
                        close_request_path.write_text(
                            "child 78s self-limit; request normal MainWindow.close()\n",
                            encoding="utf-8",
                        )
                    except OSError:
                        pass
                    ready_state["cooperative_close_requested"] = True
                _close_owned_window()
                QTimer.singleShot(100, _cooperative_watch)
                return
            QTimer.singleShot(100, _cooperative_watch)

        def _run_loaded_selection_measurement() -> None:
            nonlocal selection_result
            try:
                result = _measure_strong_stock_selections(
                    window,
                    app,
                    QTest,
                    QMessageBox,
                    QTimer,
                    loaded_count=int(os.environ.get("QA_PROFILE_SELECTIONS", "0")),
                )
                selection_result = result
            except BaseException as exc:  # record then close own window
                selection_result = {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                }
            QTimer.singleShot(0, _close_owned_window)

        QTimer.singleShot(0, _mark_ready)
        QTimer.singleShot(100, _cooperative_watch)
        stage_start = time.perf_counter()
        app.exec()
        timeline.append(
            {
                "phase": "Qt_event_loop_until_cooperative_close",
                "wall_ms": (time.perf_counter() - stage_start) * 1000,
                "cpu_ms": (time.process_time() - cpu_start) * 1000,
                "rss_bytes": _rss_bytes(process),
                "read_bytes_delta": _read_delta(read_start, _process_read_bytes(process)),
            }
        )
        if not ready_state["done"]:
            ready_state["status"] = "event_loop_ended_before_operable"
        if window is not None:
            runtime_workers.extend(_worker_state())
        if hasattr(window, "runtime_timer"):
            try:
                window.runtime_timer.stop()
            except RuntimeError:
                pass
        from ui_qt.main import _drain_qt_deferred_deletes
        _drain_qt_deferred_deletes(app, (window,))
    except BaseException as exc:
        failure = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        try:
            if window is not None:
                window.close()
                if app is not None:
                    app.processEvents()
        except BaseException:
            pass
    finally:
        sampler_stop.set()
        sampler_thread.join(timeout=1.0)

    final_read = _process_read_bytes(process)
    if (run_dir / "unsafe_dbmanager_reached.json").exists() and failure is None:
        failure = "writable DBManager path was reached during startup; guarded before database connection"
    result = {
        "status": "failed" if failure else "completed",
        "failure": failure,
        "platform": os.environ.get("QA_PROFILE_PLATFORM"),
        "label": os.environ.get("QA_PROFILE_LABEL"),
        "run_number": int(os.environ.get("QA_PROFILE_RUN_NUMBER", "0")),
        "python": sys.version,
        "pyside6": _pyside_version(),
        "process": {
            "pid": os.getpid(),
            "elapsed_s": time.perf_counter() - launch_perf,
            "cpu_s": time.process_time() - cpu_start,
            "rss_current_bytes": _rss_bytes(process),
            "rss_peak_sampled_process_tree_bytes": sampler["peak_process_tree_rss_bytes"],
            "rss_peak_sampled_process_bytes": sampler["peak_process_rss_bytes"],
            "process_tree_descendants_sampled_max": sampler["sampled_descendant_count_max"],
            "rss_sampler_interval_ms": 20,
            "rss_sampler_samples": sampler["samples"],
            "read_bytes_delta": _read_delta(read_start, final_read),
            "read_bytes_source": "main child process psutil io_counters().read_bytes; descendants are sampled for peak RSS, read-byte aggregation is not included in total",
            "peak_rss_scope": "main process plus recursively enumerated descendants per 20ms sample; if none, process-only; short-lived descendants can fall between samples",
        },
        "first_screen": {
            **ready_state,
            "elapsed_since_child_start_s": (
                time.perf_counter() - launch_perf
                if ready_state.get("status") != "operable"
                else json.loads(first_screen_path.read_text(encoding="utf-8"))["elapsed_since_child_start_s"]
            ),
        },
        "timeline": timeline,
        "constructor_calls": dict(calls),
        "industry_mapper_source_observation": industry_mapper_observation,
        "strong_stocks_source_observation": strong_stocks_source_observation,
        "loaded_row_selection": selection_result,
        "worker_state_at_close": runtime_workers,
        "private_roots": {
            "output": str(Path(os.environ["OUTPUT_ROOT"])),
            "settings": str(Path(os.environ["TEMP"]).parent / "settings"),
            "temp": os.environ["TEMP"],
            "mplconfigdir": os.environ["MPLCONFIGDIR"],
            "qsettings_ini": str(Path(os.environ["TEMP"]).parent / "settings"),
            "qstandard_paths_isolated_by_env": {
                "APPDATA": os.environ.get("APPDATA"),
                "LOCALAPPDATA": os.environ.get("LOCALAPPDATA"),
            },
            "qstandard_paths_actual": qstandard_paths if app is not None else {},
            "qstandard_paths_note": "This PySide6 build has no QStandardPaths.setPath; actual runtime paths are recorded. QSettings IniFormat and explicit personal-policy path are private.",
            "logging_note": "File-writing data_module logger handlers are replaced with per-process NullHandler; no global logging changes persist after child exit.",
            "writable_dbmanager_guard": "fail-closed pre-init guard installed; successful receipt requires it was not reached",
        },
        "input_roots": {
            "data": os.environ["DATA_ROOT"],
            "candidate_db": os.environ["PHASE3C_CANDIDATE_DB_PATH"],
        },
    }
    _write_json(result_path, result)
    if ready_state.get("workbench_first_data", {}).get("status") != "complete":
        failure = failure or "Workbench first data phase did not complete"
    return 1 if failure or ready_state.get("status") != "operable" else 0


def _read_delta(before: int | None, after: int | None) -> int | None:
    if before is None or after is None:
        return None
    return after - before


def _worker_state() -> list[str]:
    try:
        from ui_qt.workers.task_worker import running_task_workers

        workers = running_task_workers()
        if not workers:
            return ["registered_running_task_workers=0"]
        return [
            (
                f"{type(worker).__module__}.{type(worker).__name__}:"
                f"running={worker.isRunning()}:finished={worker.isFinished()}:"
                f"object_name={worker.objectName()}"
            )
            for worker in workers
        ]
    except BaseException as exc:
        return [f"worker_state_error:{type(exc).__name__}:{exc}"]


def _pyside_version() -> str:
    try:
        import PySide6

        return str(PySide6.__version__)
    except Exception:
        return "unknown"


def _measure_strong_stock_selections(
    window: Any,
    app: Any,
    qtest: Any,
    message_box: Any,
    timer_type: Any,
    *,
    loaded_count: int,
) -> dict[str, Any]:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QAbstractItemView

    market_tabs = getattr(window, "market_tabs", None)
    if market_tabs is None:
        return {"status": "unavailable", "reason": "MainWindow has no market_tabs"}
    strong_view = None
    for index in range(market_tabs.count()):
        candidate = market_tabs.widget(index)
        if type(candidate).__name__ == "StrongStocksView":
            strong_view = candidate
            strong_index = index
            break
    if strong_view is None:
        return {"status": "unavailable", "reason": "StrongStocksView not found"}

    # 使用真實左側導覽及市場頁籤；不啟動推薦/更新/訓練或 watchlist 寫入。
    window._select_main_workspace("market_explore")
    market_tabs.setCurrentIndex(strong_index)
    app.processEvents()

    # 真實 UI load action；DB reader/provider 以唯讀模式取 QA source。
    dismiss_deadline = time.perf_counter() + 2.0

    def _dismiss_error_dialog() -> None:
        for widget in app.topLevelWidgets():
            if isinstance(widget, message_box) and widget.isVisible():
                widget.accept()
        if time.perf_counter() < dismiss_deadline:
            timer_type.singleShot(50, _dismiss_error_dialog)

    timer_type.singleShot(50, _dismiss_error_dialog)
    load_start = time.perf_counter()
    strong_view.load_btn.click()
    load_ms = (time.perf_counter() - load_start) * 1000
    app.processEvents()
    model = strong_view.stocks_table.model()
    row_count = int(model.rowCount()) if model is not None else 0
    if row_count <= 0:
        return {
            "status": "no_rows",
            "load_ms": load_ms,
            "row_count": row_count,
            "universe_label": strong_view.universe_label.text(),
            "status_label": strong_view.status_label.text(),
            "source": "StrongStocksView.load_btn -> real ScreeningService and existing readonly QA database provider",
        }

    table = strong_view.stocks_table
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.show()
    strong_view.show()
    app.processEvents()
    durations_ms: list[float] = []
    row_ids: list[str] = []
    completed = 0
    for ordinal in range(max(0, loaded_count)):
        row = ordinal % row_count
        index = model.index(row, 0)
        table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
        app.processEvents()
        rect = table.visualRect(index)
        if not rect.isValid() or not table.viewport().rect().intersects(rect):
            raise ProfileError(f"第 {row} 列沒有進入可視範圍，不能量測真實可視選取")
        start = time.perf_counter()
        qtest.mouseClick(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            rect.center(),
        )
        app.processEvents()
        table.viewport().repaint()
        app.processEvents()
        selected_rows = table.selectionModel().selectedRows(0)
        elapsed = (time.perf_counter() - start) * 1000
        if len(selected_rows) != 1 or selected_rows[0].row() != row:
            raise ProfileError(
                f"第 {ordinal + 1} 次 selection 未提交到指定可見列 {row}: "
                f"{[idx.row() for idx in selected_rows]}"
            )
        durations_ms.append(elapsed)
        row_ids.append(_model_row_identity(model, row))
        completed += 1

    visible_codes = list(dict.fromkeys(row_ids))
    return {
        "status": "completed" if completed == loaded_count else "partial",
        "interaction": "QtTest mouse-click on visible StrongStocksView table row; wait for processEvents + synchronous viewport.repaint + exact selectedRows identity",
        "selection_handler": "StrongStocksView._on_selection_changed is an empty pass; measured visible row-selection highlight only, no dependent details/filter/chart",
        "load_ms": load_ms,
        "row_count": row_count,
        "selection_count": completed,
        "distinct_selected_row_ids": visible_codes,
        "repeats_rows_if_needed": row_count < loaded_count,
        "p50_ms": _percentile(durations_ms, 0.50),
        "p95_ms_nearest_rank": _percentile(durations_ms, 0.95),
        "min_ms": min(durations_ms) if durations_ms else None,
        "max_ms": max(durations_ms) if durations_ms else None,
        "durations_ms": durations_ms,
        "universe_label": strong_view.universe_label.text(),
        "status_label": strong_view.status_label.text(),
        "source": "StrongStocksView.load_btn -> real ScreeningService.get_strong_stocks_dto(period=day, top_n=50) -> existing readonly QA database provider; no watchlist action",
    }


def _model_row_identity(model: Any, row: int) -> str:
    getter = getattr(model, "getDataFrame", None)
    if not callable(getter):
        raise ProfileError("StrongStocks model has no getDataFrame API")
    frame = getter()
    record = frame.iloc[row]
    for key in ("證券代號", "股票代號", "stock_code", "代號", "code"):
        if key in record.index:
            value = record[key]
            identity = str(value).strip()
            if identity and identity.lower() not in ("nan", "none", "nat"):
                return identity
    raise ProfileError("StrongStocks row has no real stock-code identity")


def _write_budget_reference(output_root: Path) -> dict[str, Any] | None:
    path = ROOT / "output" / "qa" / "product_stage01_20261005" / "BUDGET_BEFORE_PRODUCT_CHANGE.md"
    if not path.exists():
        return None
    return {"path": str(path), "sha256": _sha256_file(path)}


def _aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    def values(path: tuple[str, ...]) -> list[float]:
        result: list[float] = []
        for run in runs:
            item: Any = run
            for segment in path:
                if not isinstance(item, dict):
                    item = None
                    break
                item = item.get(segment)
            if isinstance(item, (int, float)):
                result.append(float(item))
        return result

    specs = {
        "first_screen_external_s": ("parent_observed_first_screen_s",),
        "workbench_first_data_child_s": (
            "child",
            "first_screen",
            "workbench_first_data",
            "elapsed_since_child_start_s",
        ),
        "window_construct_show_ms": ("child", "timeline"),
        "peak_rss_bytes": ("child", "process", "rss_peak_sampled_process_tree_bytes"),
        "process_read_bytes": ("child", "process", "read_bytes_delta"),
        "process_total_cpu_s": ("child", "process", "cpu_s"),
    }
    summary: dict[str, Any] = {"run_count": len(runs), "metrics": {}}
    for name, path in specs.items():
        if name == "window_construct_show_ms":
            vals = []
            for run in runs:
                timeline = run.get("child", {}).get("timeline", [])
                for item in timeline:
                    if item.get("phase") == "MainWindow_constructed_and_show_called":
                        vals.append(float(item["wall_ms"]))
                        break
        else:
            vals = values(path)
        summary["metrics"][name] = {
            "median": _percentile(vals, 0.50),
            "p95_nearest_rank": _percentile(vals, 0.95),
            "min": min(vals) if vals else None,
            "max": max(vals) if vals else None,
            "range": max(vals) - min(vals) if vals else None,
            "values": vals,
        }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="固定 QA 輸入下，執行 bounded MainWindow startup profiling。"
    )
    parser.add_argument("--data-root", type=Path, default=ALLOWED_DATA_ROOT)
    parser.add_argument("--source-output-root", type=Path, default=ALLOWED_SOURCE_OUTPUT_ROOT)
    parser.add_argument("--candidate-db", type=Path, default=ALLOWED_CANDIDATE_DB)
    parser.add_argument("--receipt", type=Path, default=ALLOWED_RECEIPT)
    parser.add_argument("--output-dir", type=Path, default=ALLOWED_OUTPUT_ROOT)
    parser.add_argument("--platform", choices=("offscreen", "windows"), default="offscreen")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--loaded-selections", type=int, default=0)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.child:
        return _child_mode()
    if not 1 <= args.runs <= 5:
        raise ProfileError("runs 限制在 1–5，避免超出此 QA 包的有界基線")
    if not 0 <= args.loaded_selections <= 30:
        raise ProfileError("loaded-selections 限制在 0–30")
    if not args.label.replace("-", "").replace("_", "").isalnum():
        raise ProfileError("label 僅接受英數、底線或連字號")
    _require_exact_path(args.output_dir, ALLOWED_OUTPUT_ROOT, "output-dir")
    preflight = _preflight(args)
    label_root = args.output_dir / args.label
    if label_root.exists():
        raise ProfileError(f"拒絕覆寫既有量測目錄：{label_root}")
    label_root.mkdir(parents=True, exist_ok=False)
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        raise ProfileError(f"找不到專案 venv Python：{python}")
    budget = _write_budget_reference(args.output_dir)
    run_results: list[dict[str, Any]] = []
    for index in range(1, args.runs + 1):
        selections = args.loaded_selections if index == 1 else 0
        run_dir = label_root / f"run-{index:02d}"
        before_identity = _capture_input_identity(
            args.data_root, args.candidate_db, args.source_output_root, args.receipt
        )
        before_changes, before_allowed_shm = _input_identity_changes(
            preflight,
            args.data_root,
            args.candidate_db,
            args.source_output_root,
            args.receipt,
            before_identity,
        )
        if before_changes:
            _write_json(
                label_root / "input_integrity_failure.json",
                {
                    "stage": "before_run",
                    "run_number": index,
                    "errors": before_changes,
                    "observed_identity": before_identity,
                },
            )
            raise ProfileError(f"QA input changed before run {index}: {before_changes}")
        try:
            result = _run_child(
                python=python,
                run_dir=run_dir,
                data_root=args.data_root,
                source_output_root=args.source_output_root,
                candidate_db=args.candidate_db,
                receipt_path=args.receipt,
                platform=args.platform,
                loaded_selections=selections,
                label=args.label,
                run_number=index,
            )
        except BaseException as exc:
            after_identity = _capture_input_identity(
                args.data_root, args.candidate_db, args.source_output_root, args.receipt
            )
            after_changes, after_allowed_shm = _input_identity_changes(
                preflight,
                args.data_root,
                args.candidate_db,
                args.source_output_root,
                args.receipt,
                after_identity,
            )
            if run_dir.exists():
                _write_json(
                    run_dir / "input_integrity.json",
                    {
                        "run_number": index,
                        "before": before_identity,
                        "after": after_identity,
                        "allowed_shm_coordination_mtime_only": after_allowed_shm,
                        "errors": after_changes,
                        "run_error": f"{type(exc).__name__}: {exc}",
                    },
                )
            if after_changes:
                _write_json(
                    label_root / "input_integrity_failure.json",
                    {
                        "stage": "after_failed_run",
                        "run_number": index,
                        "errors": after_changes,
                        "before_identity": before_identity,
                        "after_identity": after_identity,
                    },
                )
            raise
        after_identity = _capture_input_identity(
            args.data_root, args.candidate_db, args.source_output_root, args.receipt
        )
        after_changes, after_allowed_shm = _input_identity_changes(
            preflight,
            args.data_root,
            args.candidate_db,
            args.source_output_root,
            args.receipt,
            after_identity,
        )
        _write_json(
            run_dir / "input_integrity.json",
            {
                "run_number": index,
                "before": before_identity,
                "after": after_identity,
                "allowed_shm_coordination_mtime_only": after_allowed_shm,
                "allowed_shm_coordination_mtime_before_run": before_allowed_shm,
                "errors": after_changes,
                "content_policy": "Main DB and candidate DB are stat-pinned without full hashing; WAL/SHM/source output/receipt are hashed; only SHM mtime may vary when size/device/inode/content hash are unchanged.",
            },
        )
        if after_changes:
            _write_json(
                label_root / "input_integrity_failure.json",
                {
                    "stage": "after_run",
                    "run_number": index,
                    "errors": after_changes,
                    "before_identity": before_identity,
                    "after_identity": after_identity,
                },
            )
            raise ProfileError(f"QA input changed after run {index}: {after_changes}")
        run_results.append(result)

    final_identity = _capture_input_identity(
        args.data_root, args.candidate_db, args.source_output_root, args.receipt
    )
    diff, final_allowed_shm = _input_identity_changes(
        preflight,
        args.data_root,
        args.candidate_db,
        args.source_output_root,
        args.receipt,
        final_identity,
    )
    if diff:
        _write_json(
            label_root / "input_integrity_failure.json",
            {"stage": "final", "errors": diff, "observed_identity": final_identity},
        )
        raise ProfileError(f"QA input identity changed after final run: {diff}")
    _write_json(
        label_root / "input_integrity_final.json",
        {
            "status": "unchanged_except_possible_shm_mtime_only",
            "observed_identity": final_identity,
            "allowed_shm_coordination_mtime_only": final_allowed_shm,
        },
    )

    summary = {
        "status": "completed",
        "label": args.label,
        "platform": args.platform,
        "runs_requested": args.runs,
        "loaded_selections_requested": args.loaded_selections,
        "preflight": {key: value for key, value in preflight.items() if key not in ("data_tree_before", "candidate_tree_before")},
        "input_integrity_after_each_run": "Full before/after QA data, candidate, source output, and receipt identities. Main/candidate databases use size/mtime/device/inode stat pins; WAL/SHM/source output/receipt hashes are recorded. Only twstock.db-shm mtime can vary when its size/device/inode/content hash remain identical; all other changes fail closed.",
        "large_db_copy": "none; DB used in place through existing SQLite readonly readers; 3,976,314,880-byte DB stat identity checked before and after each run",
        "per_run_small_output_copy": {
            "source_root": str(args.source_output_root),
            "sha256": preflight["source_output_sha256"],
            "file_count": preflight["source_output_file_count"],
            "bytes": preflight["source_output_bytes"],
            "copies": args.runs,
        },
        "cpu_rss_disk_read_metrics": "each child records process CPU/read_bytes and 20ms sampled process-tree peak RSS; no OS cache-cold claim",
        "budget_reference": budget,
        "aggregate": _aggregate(run_results),
        "runs": run_results,
    }
    _write_json(label_root / "summary.json", summary)
    print(json.dumps(summary["aggregate"], ensure_ascii=False, indent=2))
    print(f"\n收據：{label_root / 'summary.json'}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass
    try:
        raise SystemExit(main())
    except ProfileError as exc:
        print(f"QA profile stopped: {exc}", file=sys.stderr)
        raise SystemExit(2)
