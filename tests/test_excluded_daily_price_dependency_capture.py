from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from data_module import excluded_daily_price_revision as exclusions
from scripts import repair_excluded_daily_prices as repair
from test_excluded_daily_price_revision import (
    _make_database,
    _prepare_test_run,
    _write_evidence_archive,
)


def _applied_run(
    root: Path,
    archive: Path,
    run_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    database_path = _make_database(root, run_id)
    original_validator = exclusions._validate_market_chain
    run_dir = _prepare_test_run(
        root, archive, database_path, monkeypatch, run_id
    )
    repair.apply(
        run_dir / "plan.json",
        repair.file_hash(run_dir / "plan.json"),
        repair.CONFIRM,
    )
    monkeypatch.setattr(
        exclusions, "_validate_market_chain", original_validator
    )
    return database_path, run_dir


def test_typed_capture_pins_every_dependency_read_by_existing_validator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "FA_Data"
    root.mkdir()
    archive = _write_evidence_archive(root)
    database_path, run_dir = _applied_run(
        root, archive, "dependency-capture", monkeypatch
    )

    captured = exclusions.collect_excluded_revision_capture(database_path)

    assert captured.dependencies
    assert len(captured.dependencies) == len(captured.evidence.files)
    evidence_by_role = {
        item.role_id: item.sha256 for item in captured.evidence.files
    }
    assert len(evidence_by_role) == len(captured.dependencies)
    assert {item.role_id for item in captured.dependencies} == set(evidence_by_role)

    dependencies_by_role = {
        item.role_id: item for item in captured.dependencies
    }
    run_prefix = (
        "run_"
        + base64.urlsafe_b64encode(b"dependency-capture")
        .decode("ascii")
        .rstrip("=")
    )
    assert f"{run_prefix}/archive/archive.json" in dependencies_by_role
    assert sum(
        role.startswith(f"{run_prefix}/archive/files/")
        for role in dependencies_by_role
    ) == 16
    market_source_roles = [
        role
        for role in dependencies_by_role
        if role.startswith(f"{run_prefix}/market/sources/")
    ]
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    market_dir = root / str(plan["market_receipt_relative_dir"])
    market_plan = json.loads(
        (market_dir / "plan.json").read_text(encoding="utf-8")
    )
    assert len(market_source_roles) == len(market_plan["sources"])

    external_paths: set[Path] = set()
    for role_id, item in dependencies_by_role.items():
        resolved = Path(item.path)
        assert resolved == resolved.resolve(strict=True)
        assert resolved.is_relative_to(root.resolve())
        raw = resolved.read_bytes()
        info = resolved.stat()
        assert len(raw) == item.bytes == info.st_size
        assert info.st_mtime_ns == item.mtime_ns
        assert hashlib.sha256(raw).hexdigest() == item.sha256.removeprefix(
            "sha256:"
        )
        assert item.sha256.removeprefix("sha256:") == evidence_by_role[role_id]
        assert item.namespace == "excluded_daily_price_revision"
        assert item.captured_at.tzinfo is not None
        assert item.captured_at.utcoffset() is not None
        if role_id in market_source_roles:
            external_paths.add(resolved)
    assert external_paths
    assert all(run_dir not in path.parents for path in external_paths)
    assert all(path.parent != run_dir for path in external_paths)


def test_excluded_capture_rejects_reparse_alias_when_supported(
    tmp_path: Path,
) -> None:
    root = tmp_path / "FA_Data"
    root.mkdir()
    target = root / "target.bin"
    target.write_bytes(b"safe evidence")
    alias = root / "alias.bin"
    try:
        alias.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"此 Windows 環境不允許建立 symlink：{exc}")

    capture = exclusions._ExcludedEvidenceCapture(root)
    with pytest.raises(ValueError, match="連結或 junction"):
        capture.read_bytes(alias, "run/test", expected_directory=root)
