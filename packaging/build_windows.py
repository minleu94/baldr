"""從明示固定 commit 建置獨立 candidate；不安裝或下載依賴。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
from app_module.packaging_provenance import (
    create_build_metadata, export_fixed_source, verify_dependency_lock,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True, help="已驗證的完整 40 字元來源 commit")
    parser.add_argument("--candidate", action="store_true", help="相容舊參數；現在一律建置獨立 candidate")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("請使用依賴鎖指定的 Windows x64／Python 建置")
    job_id = f"{args.commit[:12]}_{uuid.uuid4().hex[:8]}"
    job_root = REPOSITORY / "output" / "packaging" / f"build_{job_id}"
    source = export_fixed_source(REPOSITORY, args.commit, job_root)
    required = (
        "app_module/application_bootstrap.py", "app_module/build_identity.py",
        "packaging/windows-dependencies.lock.json",
    )
    if any(not (source / name).is_file() for name in required):
        raise ValueError("此 commit 尚未包含共同啟動／版本／依賴鎖，不能建置本次 candidate")
    lock_sha = verify_dependency_lock(source / "packaging/windows-dependencies.lock.json")
    metadata = create_build_metadata(source, args.commit, lock_sha)
    (source / "application_build.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    dist = REPOSITORY / "dist" / f"candidate_{job_id}"
    if dist.exists():
        raise ValueError("candidate 已存在，不能覆寫")
    env = dict(os.environ)
    for name in tuple(env):
        if name.startswith("PERSONAL_") or name in {"DATA_ROOT", "OUTPUT_ROOT", "RESEARCH_STATE_ROOT", "BALDR_CONFIG", "MPLCONFIGDIR"}:
            env.pop(name)
    env.update(
        PYTHONUTF8="1", PYTHONNOUSERSITE="1",
        PYTHONUSERBASE=str(job_root / "empty-userbase"),
        DATA_ROOT=str(job_root / "empty-market"), OUTPUT_ROOT=str(job_root / "empty-output"),
        LOCALAPPDATA=str(job_root / "local"), BALDR_CONFIG=str(job_root / "empty-config.json"),
    )
    windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
    env["PATH"] = ";".join(map(str, (
        Path(sys.executable).parent, windows / "System32", windows,
        Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs",
    )))
    log = job_root / "pyinstaller.log"
    print(json.dumps({"source_commit": args.commit, "source": str(source),
                      "candidate": str(dist / "baldr"), "log": str(log)}, ensure_ascii=False), flush=True)
    with log.open("w", encoding="utf-8") as stream:
        completed = subprocess.run([
            sys.executable, "-m", "PyInstaller", str(source / "packaging/baldr.spec"),
            "--distpath", str(dist), "--workpath", str(job_root / "pyinstaller"),
            "--noconfirm",
        ], cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if completed.returncode:
        print(f"建置失敗：{log}", file=sys.stderr)
        return completed.returncode
    exe = dist / "baldr" / "baldr.exe"
    receipt = dict(metadata, built_at=datetime.now(timezone.utc).isoformat(),
                   source_archive_sha256=hashlib.sha256((job_root / "source.zip").read_bytes()).hexdigest(),
                   source_directory=str(source), candidate_directory=str(exe.parent),
                   exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(), exe_bytes=exe.stat().st_size,
                   validation="built_not_validated", signed=False, native_human_test=False)
    (exe.parent / "BUILD_INFO.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (job_root / "candidate_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"candidate 建置完成，尚待同版比較：{exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
