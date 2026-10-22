"""使用固定 commit 的腳本與同一隔離設定比較 Python／candidate exe。"""
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
from app_module.packaging_provenance import verify_dependency_lock, verify_exported_source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path, help="candidate 的 BUILD_INFO.json")
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    source = Path(receipt["source_directory"]).resolve(strict=True)
    exe = Path(receipt["candidate_directory"]).resolve(strict=True) / "baldr.exe"
    if hashlib.sha256(exe.read_bytes()).hexdigest() != receipt["exe_sha256"]:
        raise ValueError("candidate exe 已變更，拒絕沿用建置收據")
    archive = source.parent / "source.zip"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != receipt["source_archive_sha256"]:
        raise ValueError("固定來源 archive 已變更")
    verify_exported_source(archive, source)
    lock_sha = verify_dependency_lock(source / "packaging/windows-dependencies.lock.json")
    if lock_sha != receipt["dependency_lock_sha256"]:
        raise ValueError("建置依賴鎖與本次 Python 環境不符")
    # Probe 必須來自收據的固定 archive，而非正在修改中的 checkout。
    probe = source / "packaging/same_version_product_probe.py"
    if not probe.is_file():
        raise ValueError("來源 commit 尚未包含同版產品 probe")
    qa = REPOSITORY / "output/qa" / f"baldr_same_version_{receipt['source_commit'][:12]}_{uuid.uuid4().hex[:8]}"
    case = qa / "中文 空白 fixture"
    case.mkdir(parents=True, exist_ok=False)
    roots = {name: str(case / directory) for name, directory in (
        ("DATA_ROOT", "market"), ("OUTPUT_ROOT", "output"), ("RESEARCH_STATE_ROOT", "research"),
    )}
    for root in roots.values():
        Path(root).mkdir()
    config = case / "共用設定.json"
    config.write_text(json.dumps(roots, ensure_ascii=False, indent=2), encoding="utf-8")
    env = dict(os.environ)
    for name in tuple(env):
        if name.startswith(("PERSONAL_", "DAILY_MARKET_", "CURRENT_RESTATED_", "PIT_", "RESEARCH_PAPER_", "PAPER_")) or name in {
            "DATA_ROOT", "OUTPUT_ROOT", "RESEARCH_STATE_ROOT", "BALDR_CONFIG", "MPLCONFIGDIR", "PYTHONPATH",
        }:
            env.pop(name)
    env.update(BALDR_CONFIG=str(config), LOCALAPPDATA=str(case / "local"),
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONNOUSERSITE="1",
               PYTHONUSERBASE=str(case / "empty-userbase"), QT_QPA_PLATFORM="offscreen")
    windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
    env["PATH"] = ";".join(map(str, (Path(sys.executable).parent, windows / "System32", windows,
                                     Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs")))
    commands = {"python": [sys.executable, str(source / "baldr_launcher.py")], "exe": [str(exe)]}
    results: dict[str, dict] = {"python": {}, "exe": {}}
    report = {"source_commit": receipt["source_commit"], "version": receipt["version"],
              "exe_sha256": receipt["exe_sha256"], "dependency_lock_sha256": lock_sha,
              "config_path": str(config), "case_root": str(case), "status": "running",
              "native_human_test": False, "signed": False, "results": results}
    report_path = qa / "same_version_receipt.json"

    def persist():
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def run(label, command, arguments, *, override=None, cwd=None, expect_error=False):
        completed = subprocess.run([*command, *arguments], cwd=cwd or case, env=override or env,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        (qa / f"{label}.stdout.log").write_text(completed.stdout, encoding="utf-8")
        (qa / f"{label}.stderr.log").write_text(completed.stderr, encoding="utf-8")
        if expect_error:
            if completed.returncode == 0 or "DATA_ROOT" not in completed.stderr:
                raise RuntimeError(f"{label} 未拒絕無效設定；請讀 raw log")
            return {"rejected": True, "field": "DATA_ROOT"}
        if completed.returncode:
            raise RuntimeError(f"{label} exit={completed.returncode}；請讀 {qa / (label + '.stderr.log')}")
        return json.loads(completed.stdout.strip().splitlines()[-1])

    try:
        persist()
        for mode, command in commands.items():
            print(f"核對 {mode} 固定版本／路徑", flush=True)
            info = run(f"{mode}_launch", command, ["--launch-info"])
            if (info["build"]["source_commit"] != receipt["source_commit"]
                    or info["build"]["channel"] != "release" or info["build"]["dirty"]
                    or info["build"]["version"] != receipt["version"]
                    or info["build"]["dependency_lock_sha256"] != lock_sha):
                raise ValueError(f"{mode} 沒有通過固定發布身分核對")
            results[mode]["launch"] = info
            for workflow in ("journey", "model", "h20", "v2-contracts"):
                print(f"執行 {mode} {workflow}", flush=True)
                results[mode][workflow] = run(f"{mode}_{workflow}", command, [str(probe), str(case), workflow])
                persist()
        # 另外從直接 Qt script 與 -m 啟動同 archive，不能繞過共同解析。
        direct = run("python_direct_qt", [sys.executable, str(source / "ui_qt/main.py")], ["--launch-info"])
        module = run("python_module_qt", [sys.executable], ["-m", "ui_qt.main", "--launch-info"], cwd=source)
        if direct != results["python"]["launch"] or module != direct:
            raise ValueError("直接 Qt 入口與 launcher 不一致")
        bad = case / "無效設定.json"
        bad.write_text('{"DATA_ROOT":"relative/market"}', encoding="utf-8")
        for mode, command in commands.items():
            results[mode]["invalid_config"] = run(f"{mode}_invalid_config", command, ["--launch-info"],
                                                  override=dict(env, BALDR_CONFIG=str(bad)), expect_error=True)
        # 只排除已明示的實體資源位置與 screenshot 檔名；其餘可觀察資料逐值比對。
        def comparable(value):
            value = json.loads(json.dumps(value))
            value["launch"]["settings"].pop("resource_root")
            value["model"]["settings"].pop("resource_root")
            value["journey"].pop("bundle_root")
            value["journey"].pop("frozen")
            value["h20"].pop("screenshot")
            return value
        python_result, exe_result = comparable(results["python"]), comparable(results["exe"])
        if python_result != exe_result:
            report["difference"] = {"python": python_result, "exe": exe_result}
            raise ValueError("同版可觀察結果不同，請讀 receipt 的 difference")
        report.update(status="passed_isolated_fixture", completed_at=datetime.now(timezone.utc).isoformat(),
                      necessary_differences={"resource_root": "Python 固定 archive；exe 的 _internal bundle，介面提示列顯示實體路徑",
                                             "frozen": "啟動形態與 screenshot 證據檔名不同"},
                      direct_qt_entries_equal=True, true_market_database_used=False, provider_network_allowed=False,
                      limitations=["H20 為呈現 fixture，沒有替代原模型 capture／activation 驗收",
                                   "推薦為 synthetic execution display；canonical 保存推薦讀回的既有 nofollow blocker 保留",
                                   "取消驗 TaskWorker；正式 Task、Native 真人、自然成熟與全母體 UI 尚未驗收"])
        persist()
        print(f"同版隔離比較通過：{report_path}", flush=True)
        return 0
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        persist()
        print(f"同版比較失敗：{exc}\n收據：{report_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
