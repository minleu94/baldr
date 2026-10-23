"""output 導航登記的有限身份與拒絕邊界。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import document_external_references as references
from scripts.document_control import link_report


@pytest.fixture
def navigation(tmp_path: Path) -> tuple[Path, dict]:
    root = tmp_path / "repo"
    target = root / "output" / "trial" / "guide.md"
    target.parent.mkdir(parents=True)
    target.write_text("外部內容不應被導航檢查讀入", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs/source.md").write_text("[導航](../output/trial/guide.md)", encoding="utf-8")
    (root / "docs/scope.md").write_text("| `output/trial/guide.md` | 歷史導航 |", encoding="utf-8")
    registry = {"schema_version": references.SCHEMA, "batches": [], "entries": [],
                "repository_output_references": {
                    "scope_document": "docs/scope.md", "mount_relative": "output",
                    "mount_target": str(root / "output"), "references": [{
                        "source_document": "docs/source.md", "source_file": "output/trial/guide.md",
                        "target_path": str(target)}]}}
    registry_path = root / references.REGISTRY_PATH
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    return root, registry


def read(root: Path, registry: dict, document: str = "docs/source.md") -> dict | None:
    target = root / "output/trial/guide.md"
    references._validate_output_registry(root, registry)
    return references.registered_output_reference(root, target, target.resolve(), registry, document)


def test_exact_navigation_metadata_is_not_financial_acceptance(navigation: tuple[Path, dict], monkeypatch: pytest.MonkeyPatch) -> None:
    root, registry = navigation
    result = read(root, registry)
    assert result and result["target_exists"]
    assert result["content_verified"] is False
    assert result["financial_acceptance"] is False
    original_read = Path.read_text
    external = root / "output/trial/guide.md"

    def guarded_read(self: Path, *args: object, **kwargs: object) -> str:
        assert self != external, "metadata 導航不得讀取外部內容"
        return original_read(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", guarded_read)
    report = link_report(root, ["docs/source.md"])
    assert not report["errors"]
    assert len(report["registered_repository_output_references"]) == 1
    assert report["registered_external_references"] == []


def test_other_document_cannot_borrow_registration(navigation: tuple[Path, dict]) -> None:
    root, registry = navigation
    assert read(root, registry, "docs/other.md") is None
    target = root / "output/trial/other.md"
    target.write_text("其他", encoding="utf-8")
    assert references.registered_output_reference(root, target, target.resolve(), registry, "docs/source.md") is None


@pytest.mark.parametrize("change", ["missing", "mount_drift", "target_drift", "unlisted", "escape"])
def test_invalid_navigation_rejected(navigation: tuple[Path, dict], change: str) -> None:
    root, registry = navigation
    group = registry["repository_output_references"]
    row = group["references"][0]
    if change == "missing":
        (root / "output/trial/guide.md").unlink()
    elif change == "mount_drift":
        group["mount_target"] = str(root / "elsewhere")
        row["target_path"] = str(root / "elsewhere/trial/guide.md")
    elif change == "target_drift":
        row["target_path"] = str(root / "outside.md")
    elif change == "unlisted":
        (root / "docs/scope.md").write_text("無登記表", encoding="utf-8")
    else:
        row["source_file"] = "output/../outside.md"
    with pytest.raises((ValueError, OSError)):
        read(root, registry)


def test_nested_reparse_rejected_without_link_creation(navigation: tuple[Path, dict], monkeypatch: pytest.MonkeyPatch) -> None:
    root, registry = navigation
    original = Path.is_symlink
    nested = root / "output/trial"
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == nested or original(self))
    with pytest.raises(ValueError, match="內部不得含連結"):
        read(root, registry)


def test_old_cold_registry_without_optional_branch_remains_valid(navigation: tuple[Path, dict]) -> None:
    root, registry = navigation
    del registry["repository_output_references"]
    (root / references.REGISTRY_PATH).write_text(json.dumps(registry), encoding="utf-8")
    assert references.load_registry(root)["entries"] == []
    assert read(root, registry) is None
