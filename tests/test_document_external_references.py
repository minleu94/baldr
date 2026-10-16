"""冷封存分類應改善查找，同時保留未登記／漂移連結的拒絕邊界。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from scripts import document_control as dc
from scripts import document_external_references as external


def _seed(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "docs/03_data").mkdir(parents=True)
    (root / "docs/scope.md").write_text("# Scope\n\n| 相對目錄 | 用途 |\n|---|---|\n| `output/qa/history` | 原證據 |\n", encoding="utf-8")
    (root / "docs/terminal.md").write_text("# Terminal\n", encoding="utf-8")
    archive = tmp_path / "cold"
    target = archive / "output/qa/history"
    target.mkdir(parents=True)
    (target / "receipt.json").write_text('{"private_raw":"must_not_read"}', encoding="utf-8")
    data: dict[str, object] = {
        "schema_version": external.SCHEMA,
        "batches": [{"id": "batch", "archive_root": archive.as_posix(), "scope_document": "docs/scope.md", "reconciliation": "docs/terminal.md"}],
        "entries": [{"batch_id": "batch", "source_prefix": "output/qa/history", "archive_path": target.as_posix(), "tracking": "registered_external_evidence"}],
    }
    _write_registry(root, data)
    (root / "docs/source.md").write_text("[原證據](../output/qa/history/receipt.json)\n", encoding="utf-8")
    return root, target, data


def _write_registry(root: Path, data: dict[str, object]) -> None:
    (root / external.REGISTRY_PATH).write_text(json.dumps(data), encoding="utf-8")


def _junction(source: Path, target: Path) -> None:
    source.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(source), str(target)], check=True, capture_output=True)
    else:
        source.symlink_to(target, target_is_directory=True)


def test_registered_external_reference_is_reported_without_reading_raw_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, target, _ = _seed(tmp_path)
    _junction(root / "output/qa/history", target)
    original = Path.read_text

    def guarded_read(path: Path, *args: object, **kwargs: object) -> str:
        assert not path.resolve().is_relative_to(target), "不得讀取冷封存raw bytes"
        return original(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", guarded_read)
    report = dc.link_report(root, ["docs/source.md"])
    assert report["errors"] == []
    assert len(report["registered_external_references"]) == 1
    entry = report["registered_external_references"][0]
    assert entry["tracking"] == "registered_external_evidence"
    assert entry["availability"] == "metadata_available"
    assert entry["content_verified"] is False


def test_unregistered_external_junction_remains_an_error(tmp_path: Path) -> None:
    root, target, _ = _seed(tmp_path)
    _junction(root / "output/qa/unknown", target)
    (root / "docs/source.md").write_text("[未登記](../output/qa/unknown/receipt.json)\n", encoding="utf-8")
    report = dc.link_report(root, ["docs/source.md"])
    assert len(report["errors"]) == 1 and "連結越界" in report["errors"][0]
    assert report["registered_external_references"] == []


def test_registered_junction_retargeting_is_rejected(tmp_path: Path) -> None:
    root, _, _ = _seed(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    _junction(root / "output/qa/history", other)
    report = dc.link_report(root, ["docs/source.md"])
    assert len(report["errors"]) == 1 and "Junction目標漂移" in report["errors"][0]
    assert report["registered_external_references"] == []


def test_nested_external_escape_is_not_covered_by_registered_prefix(tmp_path: Path) -> None:
    root, target, _ = _seed(tmp_path)
    _junction(root / "output/qa/history", target)
    other = tmp_path / "other"
    other.mkdir()
    _junction(target / "escape", other)
    (root / "docs/source.md").write_text("[逃離](../output/qa/history/escape/receipt.json)\n", encoding="utf-8")
    report = dc.link_report(root, ["docs/source.md"])
    assert len(report["errors"]) == 1 and "冷封存內部連結越界" in report["errors"][0]


def test_unavailable_registered_receipt_is_known_but_not_verified(tmp_path: Path) -> None:
    root, target, _ = _seed(tmp_path)
    _junction(root / "output/qa/history", target)
    (target / "receipt.json").unlink()
    report = dc.link_report(root, ["docs/source.md"])
    assert report["errors"] == []
    entry = report["registered_external_references"][0]
    assert entry["availability"] == "external_target_unavailable"
    assert entry["target_exists"] is False and entry["content_verified"] is False


def test_missing_registered_source_stays_explicitly_unavailable(tmp_path: Path) -> None:
    root, _, _ = _seed(tmp_path)
    report = dc.link_report(root, ["docs/source.md"])
    assert report["registered_external_references"][0]["availability"] == "source_link_unavailable"


@pytest.mark.parametrize("change", ["source_escape", "empty_source", "whole_output", "whole_dist", "broad_prefix", "archive_inside_repo", "unknown_batch", "wrong_archive", "duplicate_source", "missing_registered_source"])
def test_invalid_registry_cannot_suppress_link_errors(tmp_path: Path, change: str) -> None:
    root, _, data = _seed(tmp_path)
    entries = data["entries"]
    assert isinstance(entries, list)
    if change == "source_escape":
        entries[0]["source_prefix"] = "../outside"
    elif change == "empty_source":
        entries[0]["source_prefix"] = "."
    elif change == "whole_output":
        entries[0]["source_prefix"] = "output"
    elif change == "whole_dist":
        entries[0]["source_prefix"] = "dist"
    elif change == "broad_prefix":
        entries[0]["source_prefix"] = "output/qa"
        entries[0]["archive_path"] = str(tmp_path / "cold/output/qa")
    elif change == "archive_inside_repo":
        batches = data["batches"]
        assert isinstance(batches, list)
        batches[0]["archive_root"] = str(root / "cold")
        entries[0]["archive_path"] = str(root / "cold/output/qa/history")
    elif change == "unknown_batch":
        entries[0]["batch_id"] = "unknown"
    elif change == "wrong_archive":
        entries[0]["archive_path"] = str(tmp_path / "wrong")
    elif change == "duplicate_source":
        entries.append(dict(entries[0]))
    else:
        entries.clear()
    _write_registry(root, data)
    report = dc.link_report(root, ["docs/source.md"])
    assert report["errors"] and "冷封存登記無效" in report["errors"][0]
    assert report["registered_external_references"] == []


def test_check_exposes_registered_reference_classification(tmp_path: Path) -> None:
    root, target, _ = _seed(tmp_path)
    _junction(root / "output/qa/history", target)
    (root / "docs/agents").mkdir()
    (root / "docs/00_core").mkdir()
    (root / dc.ROLE_CATALOG).write_text(json.dumps({"schema_version": "baldr-role-routing.v1", "roles": {}, "kinds": {}}), encoding="utf-8")
    (root / dc.FEATURE_MAP).write_text(json.dumps({"features": []}), encoding="utf-8")
    result = dc.check(root, paths=["docs/source.md"])
    assert result["passed"] is True
    assert result["registered_external_references"][0]["tracking"] == "registered_external_evidence"
    assert result["registered_external_references"][0]["content_verified"] is False


def test_archives_cli_locates_exact_registered_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root, target, _ = _seed(tmp_path)
    _junction(root / "output/qa/history", target)
    assert dc.main(["--repo-root", str(root), "archives", "--path", "output/qa/history/receipt.json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["count"] == 1
    assert result["entries"][0]["source_prefix"] == "output/qa/history"
    assert dc.main(["--repo-root", str(root), "archives", "--path", "output/qa/unregistered"]) == 2
