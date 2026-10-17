"""研究封存移位後，只在新副本重綁路徑；不借原根或重算金融原件。"""
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from app_module import research_output_copy as copy
from test_research_output_copy import BUDGET, source, inventory, _add_recommendations


def _archive(source, tmp_path, *, recommendations=False):
    copied = tmp_path / "initial_copy"
    receipt = copy.copy_research_output(source, copied, budget=BUDGET, include_recommendations=recommendations)
    digest = sha256(receipt.read_bytes()).hexdigest()
    moved = tmp_path / "moved_archive"
    copied.rename(moved)
    return moved, digest


def test_moved_archive_restores_three_stores_without_original_io_or_reencoding(source, tmp_path, monkeypatch):
    old_result = copy._lookup(source, BUDGET).resolve(copy._lookup(source, BUDGET).select_registry_run("exact")).result
    archive, digest = _archive(source, tmp_path)
    before = inventory(archive)
    source.rename(tmp_path / "original_unavailable")
    original_open = Path.open
    original_connect = sqlite3.connect
    def guarded_open(path, *a, **kw):
        assert not path.absolute().is_relative_to(source.absolute()), "不可fallback至原根"
        return original_open(path, *a, **kw)
    def guarded_connect(path, *a, **kw):
        assert str(source).replace("\\", "/") not in str(path).replace("\\", "/"), "不可開原DB"
        return original_connect(path, *a, **kw)
    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    target = tmp_path / "restored"
    receipt = copy.restore_research_output(archive, digest, target, budget=BUDGET)
    proof = json.loads(receipt.read_bytes())
    assert proof["status"] == "restored_and_public_readers_verified"
    assert proof["archive_receipt_sha256"] == digest and proof["archive_unchanged"]
    assert proof["financial_artifacts_reencoded"] is False and len(proof["runs"]) == 3
    assert inventory(archive) == before
    reader = copy._lookup(target, BUDGET)
    result = reader.resolve(reader.select_registry_run("exact")).result
    expected = asdict(old_result.metadata)
    expected.update(equity_path=result.metadata.equity_path, trades_path=result.metadata.trades_path)
    assert asdict(result.metadata) == expected
    assert result.equity.equals(old_result.equity) and result.trades.equals(old_result.trades)
    for kind, identifier in (("legacy_backtest", "old"), ("legacy_recommendation_portfolio", "basket")):
        reader.resolve(reader.select_legacy_run(kind, identifier))
    for entry in proof["destination_files"]:
        if not entry["path"].endswith(".db"):
            assert sha256((target / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]


def test_recommendations_restore_legacy_and_canonical_payloads_without_old_root(source, tmp_path):
    _add_recommendations(source)
    expected = copy._recommendation_entries(source, BUDGET, None)
    archive, digest = _archive(source, tmp_path, recommendations=True)
    source.rename(tmp_path / "original_unavailable")
    target = tmp_path / "restored"
    copy.restore_research_output(archive, digest, target, budget=BUDGET)
    assert copy._recommendation_entries(target, BUDGET, None) == expected


@pytest.mark.parametrize("problem", ["wrong_sha", "tamper", "extra", "pending", "journal", "budget", "cancel"])
def test_bad_or_incomplete_archive_rejected_before_target_creation(source, tmp_path, problem):
    archive, digest = _archive(source, tmp_path)
    if problem == "wrong_sha":
        digest = "0" * 64
    elif problem == "tamper":
        path = next((archive / "research_runs/parquet").glob("*"))
        path.write_bytes(path.read_bytes() + b"changed")
    elif problem == "extra":
        (archive / "research_runs/unexpected.json").write_text("{}")
    elif problem == "pending":
        (archive / ".research_copy_pending.json").write_text("{}")
    elif problem == "journal":
        (archive / "research_runs/research_runs.db-wal").write_bytes(b"active")
    before = inventory(archive)
    target = tmp_path / "restored"
    with pytest.raises((copy.ResearchOutputCopyError, ValueError)):
        copy.restore_research_output(archive, digest, target,
            budget=replace(BUDGET, max_total_bytes=8) if problem == "budget" else BUDGET,
            check_cancel=(lambda: True) if problem == "cancel" else None)
    assert not target.exists() and inventory(archive) == before


def _rewrite_receipt(archive, update):
    receipt = archive / "RESEARCH_COPY_RECEIPT.json"
    payload = json.loads(receipt.read_bytes())
    update(payload)
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    return sha256(receipt.read_bytes()).hexdigest()


@pytest.mark.parametrize("problem", ["duplicate", "escape", "trigger", "wrong_scope", "wrong_count"])
def test_trusted_but_invalid_receipt_or_index_is_rejected(source, tmp_path, problem):
    archive, digest = _archive(source, tmp_path)
    if problem == "duplicate":
        digest = _rewrite_receipt(archive, lambda value: value["destination_files"].append(value["destination_files"][0]))
    elif problem in {"escape", "trigger"}:
        database = archive / "research_runs/research_runs.db"
        with sqlite3.connect(database) as db:
            if problem == "escape":
                db.execute("UPDATE research_runs SET equity_path=?", (str(tmp_path / "outside.parquet"),))
            else:
                db.execute("CREATE TRIGGER bad AFTER UPDATE ON research_runs BEGIN UPDATE research_runs SET run_name='changed'; END")
        db.close()
        def update(value):
            for row in value["destination_files"]:
                if row["path"] == "research_runs/research_runs.db":
                    row.update(bytes=database.stat().st_size, sha256=sha256(database.read_bytes()).hexdigest())
        digest = _rewrite_receipt(archive, update)
    elif problem == "wrong_scope":
        digest = _rewrite_receipt(archive, lambda value: value.update(selected_store_kinds=["unknown"]))
    else:
        digest = _rewrite_receipt(archive, lambda value: value["runs"].pop())
    before = inventory(archive)
    target = tmp_path / "restored"
    with pytest.raises((copy.ResearchOutputCopyError, ValueError)):
        copy.restore_research_output(archive, digest, target, budget=BUDGET)
    assert not target.exists() and inventory(archive) == before


def test_cli_archive_mode_keeps_original_copy_mode(source, tmp_path, capsys):
    from scripts.copy_research_output import main
    archive, digest = _archive(source, tmp_path)
    target = tmp_path / "restored"
    import sys
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "argv", ["copy_research_output.py", "--archive-directory", str(archive),
            "--archive-receipt-sha256", digest, "--destination-output-root", str(target)])
        assert main() == 0
    assert (target / "RESEARCH_COPY_RECEIPT.json").is_file()
