from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_weekly_runbook_manifest as builder


def _artifact(path: Path, payload: str = '{"ok":true}\n') -> Path:
    path.write_text(payload, encoding="utf-8")
    return path


def test_manifest_pins_artifact_hash_with_relative_path_and_collection_identity(tmp_path: Path) -> None:
    artifact_path = _artifact(tmp_path / "smoke.json")
    output_path = tmp_path / "manifest.json"

    result = builder.build_manifest(
        collection_id="ewc_example",
        period_start="2026-10-19",
        period_end="2026-10-25",
        output_path=output_path,
        artifacts=[("working_copy_smoke", str(artifact_path))],
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert result == saved
    assert saved["schema_version"] == "baldr-weekly-runbook-manifest.v1"
    assert saved["collection_id"] == "ewc_example"
    assert saved["period_start"] == "2026-10-19"
    assert saved["period_end"] == "2026-10-25"
    assert saved["artifacts"] == [
        {
            "artifact_role": "working_copy_smoke",
            "path": "smoke.json",
            "sha256": "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        }
    ]


def test_manifest_rejects_duplicate_or_unsupported_role(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path / "smoke.json")
    with pytest.raises(ValueError, match="duplicate artifact role"):
        builder.build_manifest(
            collection_id="ewc_example",
            period_start="2026-10-19",
            period_end="2026-10-25",
            output_path=tmp_path / "duplicates.json",
            artifacts=[
                ("working_copy_smoke", str(artifact)),
                ("working_copy_smoke", str(artifact)),
            ],
        )

    with pytest.raises(ValueError, match="unsupported artifact role"):
        builder.build_manifest(
            collection_id="ewc_example",
            period_start="2026-10-19",
            period_end="2026-10-25",
            output_path=tmp_path / "unsupported.json",
            artifacts=[("backup_rollback_recovery", str(artifact))],
        )


def test_manifest_rejects_artifacts_outside_its_parent(tmp_path: Path) -> None:
    receipt_root = tmp_path / "receipts"
    receipt_root.mkdir()
    outside_artifact = _artifact(tmp_path / "outside.json")

    with pytest.raises(ValueError, match="inside the manifest directory|stay below"):
        builder.build_manifest(
            collection_id="ewc_example",
            period_start="2026-10-19",
            period_end="2026-10-25",
            output_path=receipt_root / "manifest.json",
            artifacts=[("working_copy_smoke", str(outside_artifact))],
        )


def test_manifest_rejects_traversal_components_even_when_they_normalize_inside(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path / "smoke.json")
    traversing_path = tmp_path / "nested" / ".." / artifact.name

    with pytest.raises(ValueError, match="traversal"):
        builder.build_manifest(
            collection_id="ewc_example",
            period_start="2026-10-19",
            period_end="2026-10-25",
            output_path=tmp_path / "manifest.json",
            artifacts=[("working_copy_smoke", str(traversing_path))],
        )


def test_manifest_refuses_to_overwrite_existing_file(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path / "smoke.json")
    output = tmp_path / "manifest.json"
    output.write_text("existing\n", encoding="utf-8")
    before = output.read_bytes()

    with pytest.raises(FileExistsError):
        builder.build_manifest(
            collection_id="ewc_example",
            period_start="2026-10-19",
            period_end="2026-10-25",
            output_path=output,
            artifacts=[("working_copy_smoke", str(artifact))],
        )

    assert output.read_bytes() == before


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-10-19", "2026-10-18"),
        ("2026-1-19", "2026-10-25"),
        ("2026-10-19", "2026-10-25T00:00:00"),
    ],
)
def test_manifest_requires_canonical_ordered_periods(tmp_path: Path, start: str, end: str) -> None:
    artifact = _artifact(tmp_path / "smoke.json")
    with pytest.raises(ValueError):
        builder.build_manifest(
            collection_id="ewc_example",
            period_start=start,
            period_end=end,
            output_path=tmp_path / "manifest.json",
            artifacts=[("working_copy_smoke", str(artifact))],
        )


def test_manifest_rejects_symlink_artifact_when_supported(tmp_path: Path) -> None:
    source = _artifact(tmp_path / "source.json")
    linked = tmp_path / "linked.json"
    try:
        linked.symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic link creation is unavailable")

    with pytest.raises(ValueError, match="symbolic link|regular file"):
        builder.build_manifest(
            collection_id="ewc_example",
            period_start="2026-10-19",
            period_end="2026-10-25",
            output_path=tmp_path / "manifest.json",
            artifacts=[("working_copy_smoke", str(linked))],
        )
