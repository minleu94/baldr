from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

from test_research_membership_lifecycle_read_model import _write_snapshot
from scripts.manage_membership_history_index import main


def _pins(root: Path):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_cli_rebuild_and_same_source_rollback_preserve_immutable_inputs(tmp_path, capsys):
    source, cache = tmp_path / "source", tmp_path / "index"
    _write_snapshot(source, date(2026, 10, 2), matches=False)
    _write_snapshot(source, date(2026, 10, 5), matches=True)
    before = _pins(source)
    args = ["--snapshot-root", str(source), "--index-root", str(cache)]
    assert main(["rebuild", *args]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["activated"] and first["manifest_count"] == 2
    assert first["research_only"] and not first["historical_pit_eligible"]
    assert main(["rebuild", *args]) == 0
    second = json.loads(capsys.readouterr().out)
    assert first["generation_id"] != second["generation_id"]
    assert main(["rollback", *args, "--generation-id", first["generation_id"]]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["generation_id"] == first["generation_id"]
    assert _pins(source) == before
    assert (cache / "generations" / (second["generation_id"] + ".sqlite")).exists()


def test_cli_fault_reports_not_completed_without_replacing_active(tmp_path, capsys):
    source, cache = tmp_path / "source", tmp_path / "index"
    _write_snapshot(source, date(2026, 10, 5), matches=True)
    args = ["--snapshot-root", str(source), "--index-root", str(cache)]
    assert main(["rebuild", *args]) == 0
    capsys.readouterr()
    before = (cache / "active.json").read_bytes()
    source_pins = _pins(source)
    assert main(["rollback", *args, "--generation-id", "f" * 32]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "not_completed"
    assert result["original_sources_preserved"]
    assert (cache / "active.json").read_bytes() == before
    assert _pins(source) == source_pins
