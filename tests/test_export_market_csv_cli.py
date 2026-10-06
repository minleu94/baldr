"""CLI 僅用 synthetic 資料；不讀正式 personal／DB，不觸發網路／Task。"""

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from app_module.market_csv_export import RECEIPT_NAME
from scripts import export_market_csv as cli

pytestmark = pytest.mark.skipif(os.name != "nt", reason="本版 CLI 明示 Windows handle backend")


@pytest.fixture
def layout(tmp_path):
    market = tmp_path / "FA_Data"
    files = ("daily_price/20261006.csv", "meta_data/market_index.csv")
    for name in files:
        path = market / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"date,stock,close\n20261006,1234,100\n")
    for name in ("personal/notes.csv", "output/private.json", "sqlite/twstock.db"):
        path = market / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic excluded")
    return market, files, tmp_path / "package", tmp_path / "accepted-preview.json"


def arguments(layout, *, destination=None, files=None):
    market, listed, target, _ = layout
    args = ["--market-root", str(market), "--destination-root", str(destination or target)]
    for name in listed if files is None else files:
        args.extend(["--file", name])
    return args


def run(args):
    result = subprocess.run([sys.executable, str(Path(cli.__file__)), *args], capture_output=True,
                            text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
    return result.returncode, json.loads(result.stdout), result.stderr


def accept(layout):
    code, preview, stderr = run(arguments(layout))
    assert code == 0, stderr
    layout[3].write_text(json.dumps(preview), encoding="utf-8")
    return preview


def test_default_preview_no_writes_and_explicit_scope(layout):
    market, files, target, _ = layout
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ctime_ns) for p in market.rglob("*") if p.is_file()}
    code, preview, stderr = run(arguments(layout))
    assert code == 0, stderr
    assert preview["status"] == "preview"
    assert preview["writes_performed"] is False
    assert preview["source_hashes_accepted"] is False
    assert preview["platform"] == "Windows handle sharing required"
    assert preview["source_roots"]["personal_root"] == str(market / "personal")
    assert preview["destination_root"] == str(target)
    assert preview["file_count"] == 2
    assert {pin["relative_path"] for pin in preview["observed_source_pins"]} == set(files)
    assert preview["total_size_bytes"] == sum((market / name).stat().st_size for name in files)
    assert len(preview["excluded"]) == 4
    assert not target.exists()
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ctime_ns) for p in market.rglob("*") if p.is_file()}
    assert not layout[3].exists()


def test_execute_requires_explicit_accepted_preview(layout):
    code, result, _ = run(arguments(layout) + ["--execute"])
    assert code == 2
    assert result["code"] == "execute_requires_accepted_preview"
    assert not layout[2].exists()


def test_preview_cannot_implicitly_execute_accepted_file(layout):
    accept(layout)
    code, result, _ = run(arguments(layout) + ["--accepted-preview", str(layout[3])])
    assert code == 2
    assert result["code"] == "accepted_preview_requires_execute"
    assert not layout[2].exists()


def test_execute_new_target_receipt_and_retry_no_overwrite(layout):
    preview = accept(layout)
    args = arguments(layout) + ["--execute", "--accepted-preview", str(layout[3])]
    code, result, stderr = run(args)
    assert code == 0, stderr
    assert result["status"] == "completed"
    assert result["uploaded"] is False and result["shared"] is False
    assert result["receipt_sha256"] == hashlib.sha256((layout[2] / RECEIPT_NAME).read_bytes()).hexdigest()
    for pin in preview["observed_source_pins"]:
        assert hashlib.sha256((layout[2] / pin["relative_path"]).read_bytes()).hexdigest() == pin["sha256"]
    before = (layout[2] / RECEIPT_NAME).read_bytes()
    code, result, _ = run(args)
    assert code == 2 and result["code"] == "export_destination_exists"
    assert (layout[2] / RECEIPT_NAME).read_bytes() == before
    code, result, _ = run(arguments(layout, destination=layout[2].with_name("new_package")) + ["--execute", "--accepted-preview", str(layout[3])])
    assert code == 0 and result["status"] == "completed"


@pytest.mark.parametrize("name", [".", "FA_Data", "*", "daily_price/*.csv", "personal/notes.csv", "output/private.json", "sqlite/twstock.db"])
def test_no_whole_root_glob_personal_output_or_sqlite(layout, name):
    code, result, _ = run(arguments(layout, files=[name]))
    assert code == 2 and result["status"] == "blocked"
    assert not layout[2].exists()


@pytest.mark.parametrize("kind", ["sqlite", "nested_personal", "db_name"])
def test_preview_rejects_disguised_private_or_database(layout, kind):
    name = {"sqlite": "daily_price/db.csv", "nested_personal": "daily_price/personal/a.csv", "db_name": "daily_price/a.db.csv"}[kind]
    source = layout[0] / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"SQLite format 3\x00synthetic" if kind == "sqlite" else b"synthetic")
    code, result, _ = run(arguments(layout, files=[name]))
    assert code == 2
    assert result["code"] == {"sqlite": "sqlite_content_excluded", "nested_personal": "private_export_component", "db_name": "sqlite_name_excluded"}[kind]
    assert not layout[2].exists()


def test_preview_accepted_identity_rejects_source_changed_between_processes(layout):
    accept(layout)
    (layout[0] / layout[1][0]).write_bytes(b"changed synthetic")
    code, result, _ = run(arguments(layout) + ["--execute", "--accepted-preview", str(layout[3])])
    assert code == 2 and result["code"] == "accepted_preview_source_changed"
    assert not layout[2].exists()


def test_accepted_hash_mismatch_rejected_without_target(layout):
    preview = accept(layout)
    preview["observed_source_pins"][0]["sha256"] = "0" * 64
    layout[3].write_text(json.dumps(preview), encoding="utf-8")
    code, result, _ = run(arguments(layout) + ["--execute", "--accepted-preview", str(layout[3])])
    assert code == 2 and result["code"] == "export_source_hash_mismatch"
    assert not layout[2].exists()


@pytest.mark.parametrize("kind", ["roots", "files", "schema", "hash", "duplicate"])
def test_tampered_accepted_preview_rejected(layout, kind):
    preview = accept(layout)
    if kind == "roots":
        preview["source_roots"]["market_root"] = "wrong"
    elif kind == "files":
        preview["observed_source_pins"].pop()
    elif kind == "schema":
        preview["schema"] = "wrong"
    elif kind == "hash":
        preview["observed_source_pins"][0]["sha256"] = None
    else:
        preview["observed_source_pins"][1] = preview["observed_source_pins"][0]
    layout[3].write_text(json.dumps(preview), encoding="utf-8")
    code, result, _ = run(arguments(layout) + ["--execute", "--accepted-preview", str(layout[3])])
    assert code == 2 and result["status"] == "blocked"
    assert not layout[2].exists()


def test_cancel_execute_partial_then_retry_new_target(layout, capsys):
    accept(layout)
    args = arguments(layout) + ["--execute", "--accepted-preview", str(layout[3])]
    code = cli.main(args, cancelled=lambda: any(layout[2].glob("daily_price/*.csv")))
    result = json.loads(capsys.readouterr().out)
    assert code == 130 and result["status"] == "cancelled"
    assert result["completion_published"] is False
    assert layout[2].exists() and not (layout[2] / RECEIPT_NAME).exists()
    code, result, _ = run(args)
    assert code == 2 and result["code"] == "export_destination_exists"
    code, result, _ = run(arguments(layout, destination=layout[2].with_name("retry_package")) + ["--execute", "--accepted-preview", str(layout[3])])
    assert code == 0 and result["status"] == "completed"


def test_sigint_becomes_cooperative_cancel_and_handler_restored(layout, capsys):
    accept(layout)
    old_handler = signal.getsignal(signal.SIGINT)
    raised = []
    def request_stop():
        if layout[2].exists() and not raised:
            raised.append(True)
            signal.raise_signal(signal.SIGINT)
        return False
    code = cli.main(arguments(layout) + ["--execute", "--accepted-preview", str(layout[3])], cancelled=request_stop)
    result = json.loads(capsys.readouterr().out)
    assert code == 130 and result["status"] == "cancelled"
    assert raised == [True]
    assert signal.getsignal(signal.SIGINT) == old_handler
    assert not (layout[2] / RECEIPT_NAME).exists()


def test_cancel_preview_is_readonly(layout, capsys):
    assert cli.main(arguments(layout), cancelled=lambda: True) == 130
    assert json.loads(capsys.readouterr().out)["status"] == "cancelled"
    assert not layout[2].exists()


def test_publication_error_report_keeps_no_completed_receipt(layout, capsys, monkeypatch):
    import app_module.market_csv_export as consumer
    accept(layout)
    def fail(*args):
        raise OSError("synthetic failure")
    monkeypatch.setattr(consumer, "_publish_receipt", fail)
    assert cli.main(arguments(layout) + ["--execute", "--accepted-preview", str(layout[3])]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["code"] == "export_io_failed" and result["completion_published"] is False
    assert list(layout[2].glob("*.pending"))
    assert not (layout[2] / RECEIPT_NAME).exists()


def test_help_explicit_windows_restriction():
    result = subprocess.run([sys.executable, str(Path(cli.__file__)), "--help"], capture_output=True,
                            text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0
    assert "Windows handle sharing" in result.stdout
    assert "--execute" in result.stdout and "--accepted-preview" in result.stdout
