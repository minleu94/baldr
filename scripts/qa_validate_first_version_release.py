"""UX24：既有第一版收據唯讀重驗與隔離 App 新程序返回。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def child(phase: str, case: Path) -> int:
    case.resolve().relative_to(ROOT / "output" / "qa")
    if phase not in {"setup", "readback", "defaults"}:
        raise ValueError("未知驗證階段")
    # 既有 child 已拒絕案例外寫入、SQLite、網路及子程序；再拒絕正式資料讀取。
    def audit(event: str, args: tuple[object, ...]) -> None:
        if event == "open" and isinstance(args[0], (str, Path)):
            value = str(args[0]).replace("\\", "/").casefold()
            if "fa_data/" in value:
                raise PermissionError("UX24 不得讀取正式或個人資料")

    sys.addaudithook(audit)
    sys.path.insert(0, str(ROOT / "tests"))
    from tests.test_f4_research_release_integration import _child_main

    return _child_main(phase, case)


def validate(output: Path) -> dict[str, object]:
    from app_module.research_snapshot_storage_governance import diagnose_research_snapshot_storage
    from data_module.watchlist_repository import WatchlistRepository

    output = output.resolve()
    output.relative_to(ROOT / "output" / "qa")
    output.mkdir(parents=True, exist_ok=False)
    checked_sources = [ROOT / name for name in (
        "ui_qt/main.py", "ui_qt/views/stock_research_report_view.py",
        "data_module/watchlist_repository.py", "data_module/watchlist_item_storage.py",
        "app_module/watchlist_service.py", "app_module/research_snapshot_storage_governance.py",
        "data_module/ml_storage_capacity.py", "tests/test_f4_research_release_integration.py",
    )]
    implementation = {str(path.relative_to(ROOT)): digest(path) for path in checked_sources}
    prior = ROOT / "output/qa/f4_item_revision_storage_20261005"
    guard_path = prior / "final_guard_readonly_revalidation.json"
    guard = json.loads(guard_path.read_text(encoding="utf-8"))
    roots = {name: Path(value) for name, value in guard["diagnosis"]["roots"].items()}
    for path in roots.values():
        path.resolve().relative_to(prior.resolve())
    source_files = [path for root in roots.values() for path in root.rglob("*") if path.is_file()]
    before = {str(path): digest(path) for path in source_files}
    database = roots["watchlist_dir"] / "watchlists.db"
    assert digest(database) == guard["actual250_database_sha256"]
    repository = WatchlistRepository(database)
    revisions = sum(sum(1 for _ in repository.iter_revisions(name)) for name in repository.list_ids())
    assert revisions == 250
    diagnosis = diagnose_research_snapshot_storage(
        roots["snapshot_root"], rank_root=roots["rank_root"],
        watchlist_dir=roots["watchlist_dir"], watchlist_inventory_complete=True,
    )
    assert diagnosis["storage"]["scan_complete"] and diagnosis["storage"]["references_complete"]
    assert diagnosis["capacity"]["within_budget"] and not diagnosis["issues"]
    assert before == {str(path): digest(path) for root in roots.values() for path in root.rglob("*") if path.is_file()}
    case = output / "app"
    case.mkdir()
    WatchlistRepository(case / "output/_test/watchlist/watchlists.db", initialize=True)
    receipts = {}
    for phase in ("setup", "readback", "defaults"):
        environment = {
            **os.environ, "DATA_ROOT": str(case / "data"), "OUTPUT_ROOT": str(case / "output"),
            "PROFILE": "test", "QT_QPA_PLATFORM": "offscreen", "MPLCONFIGDIR": str(case / "matplotlib"),
            "APPDATA": str(case / "appdata"), "LOCALAPPDATA": str(case / "localappdata"),
            "USERPROFILE": str(case / "userprofile"), "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
        }
        process = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--child", phase, str(case)],
            cwd=case, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        (output / f"{phase}.log").write_text(process.stdout + process.stderr, encoding="utf-8")
        assert process.returncode == 0, f"{phase}: 見 {output / (phase + '.log')}"
        receipts[phase] = json.loads((case / f"{phase}_receipt.json").read_text(encoding="utf-8"))
        assert receipts[phase]["status"] == "passed"
    for name in ("daily_v1", "rank_v2"):
        assert receipts["setup"]["bookmark_identities"][name]["bookmark_id"] == receipts["readback"]["fresh_process_readback"][name]["bookmark_id"]
    assert receipts["setup"]["bookmark_identities"]["rank_v2"]["source_hash"] == receipts["readback"]["fresh_process_readback"]["rank_v2"]["source_hash"]
    assert implementation == {str(path.relative_to(ROOT)): digest(path) for path in checked_sources}
    result: dict[str, object] = {
        "status": "passed", "schema_version": "ux24-first-version-engineering-seal.v1",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "implementation_pins_before_and_after": implementation,
        "scope": "stage1–3 已接受範圍；隔離 offscreen，不含 Native／真人／正式啟用",
        "actual_app": receipts, "retention_replayed": revisions, "retention_diagnosis": diagnosis,
        "prior_receipt_sha256": digest(guard_path), "prior_files_unchanged": True,
        "prior_file_count": len(before), "source_file_pins": before,
        "producer_retention_rerun": False, "formal_deployment": False, "natural_qualification": False,
    }
    (output / "receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", nargs=2, metavar=("PHASE", "CASE"))
    parser.add_argument("--output-root", type=Path)
    arguments = parser.parse_args()
    if arguments.child:
        raise SystemExit(child(arguments.child[0], Path(arguments.child[1])))
    target = arguments.output_root or ROOT / "output/qa/ux24_first_version_20261006" / uuid4().hex[:8]
    validate(target)
    print(f"第一版有限工程驗證通過：{target / 'receipt.json'}")
