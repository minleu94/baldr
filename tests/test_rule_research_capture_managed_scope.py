"""受控研究保存範圍與唯讀重開驗證。"""

import os
import sqlite3
from pathlib import Path

import pytest

from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter,
    ResearchCaptureWriteScope,
    RuleResearchCapture,
    RuleSampleCaptureError,
    SAFETY_RESERVE_BYTES,
)
from tests.test_daily_market_snapshot_repository import DECISION_DATE, PUBLISHED_AT
from tests.test_rule_research_sample_capture import _fixture


def _source_database(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE source_probe (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    return path.resolve(strict=True)


def _scope(tmp_path: Path) -> ResearchCaptureWriteScope:
    output_root = tmp_path / "configured-output"
    source_database = _source_database(tmp_path / "source" / "market.sqlite")
    return ResearchCaptureWriteScope(output_root, source_database)


def _expect(code: str, operation) -> None:
    with pytest.raises(RuleSampleCaptureError) as error:
        operation()
    assert error.value.code == code


def test_default_writer_still_rejects_external_persistent_root():
    external_root = Path(__file__).resolve().parents[1] / ".tmp-managed-capture-default-external"
    _expect("isolated_output_required", lambda: BoundedRuleResearchCaptureWriter(external_root))
    assert not external_root.exists()


def test_scope_requires_absolute_inputs_and_external_readonly_source(tmp_path):
    source_database = _source_database(tmp_path / "source" / "market.sqlite")
    _expect(
        "research_scope_path_absolute_required",
        lambda: ResearchCaptureWriteScope("relative-output", source_database),
    )
    _expect(
        "research_scope_path_absolute_required",
        lambda: ResearchCaptureWriteScope(tmp_path / "output", Path("relative-market.sqlite")),
    )

    overlapping_output = tmp_path / "overlapping-output"
    source_inside_output = _source_database(overlapping_output / "market.sqlite")
    _expect(
        "source_output_overlap",
        lambda: ResearchCaptureWriteScope(overlapping_output, source_inside_output),
    )


def test_scope_rejects_wal_path_inside_configured_output_root(tmp_path):
    source_database = _source_database(tmp_path / "source" / "market.sqlite")
    configured_output_root = Path(f"{source_database}-wal")
    _expect(
        "source_output_overlap",
        lambda: ResearchCaptureWriteScope(configured_output_root, source_database),
    )


def test_scoped_writer_only_accepts_strict_descendants(tmp_path):
    scope = _scope(tmp_path)
    _expect(
        "research_scope_escape",
        lambda: BoundedRuleResearchCaptureWriter(
            scope.root, research_scope=scope
        ),
    )
    _expect(
        "research_scope_escape",
        lambda: BoundedRuleResearchCaptureWriter(
            tmp_path / "outside" / "captures", research_scope=scope
        ),
    )
    _expect(
        "writer_mode_conflict",
        lambda: BoundedRuleResearchCaptureWriter(
            scope.root / "captures", research_scope=scope, read_only=True
        ),
    )


def test_readonly_writer_rejects_before_serialization_lock_or_directory(tmp_path, monkeypatch):
    output_root = tmp_path / "readonly-only" / "captures"
    writer = BoundedRuleResearchCaptureWriter(output_root, read_only=True)
    _, _, capture = _fixture(tmp_path)
    monkeypatch.setattr(
        RuleResearchCapture,
        "to_dict",
        lambda self: pytest.fail("read-only writer touched capture serialization"),
    )

    _expect(
        "read_only_writer_forbidden",
        lambda: writer.write(capture, revalidate=lambda: pytest.fail("unexpected revalidation")),
    )
    assert not output_root.exists()
    assert not (output_root / ".writer.lock").exists()


def test_scoped_real_capture_reopens_with_readonly_writer(tmp_path, monkeypatch):
    repository, snapshot, _ = _fixture(tmp_path)
    scope = _scope(tmp_path)
    output_root = scope.root / "captures"
    writer = BoundedRuleResearchCaptureWriter(output_root, research_scope=scope)
    monkeypatch.setattr(
        writer, "_free_bytes", lambda: SAFETY_RESERVE_BYTES + 1024**3
    )

    published = writer.capture_pinned(
        repository,
        manifest_sha256=snapshot.manifest_sha256,
        cohort_id=snapshot.cohort_id,
        decision_date=DECISION_DATE,
        as_of=PUBLISHED_AT,
    )
    assert published["status"] == "published"

    readonly_reader = BoundedRuleResearchCaptureWriter(output_root, read_only=True)
    reopened = readonly_reader.read(published["receipt"]["capture_identity_sha256"])
    assert reopened["receipt"] == published["receipt"]
    assert reopened["capture"]["capture_identity_sha256"] == (
        published["receipt"]["capture_identity_sha256"]
    )
    assert not (output_root / ".writer.lock").exists()


def test_scoped_capture_roundtrip_supports_windows_long_paths(tmp_path, monkeypatch):
    repository, snapshot, capture = _fixture(tmp_path)
    scope = _scope(tmp_path)
    output_root = scope.root / "universe_jobs" / "24" / "c0" / "samples" / "64"
    depth = 0
    while len(str(output_root / capture.identity_sha256 / "capture.json")) <= 270:
        output_root = output_root / f"research-parent-{depth}-{'x' * 25}"
        depth += 1
    assert len(str(output_root / capture.identity_sha256 / "capture.json")) > 260

    writer = BoundedRuleResearchCaptureWriter(output_root, research_scope=scope)
    monkeypatch.setattr(
        writer, "_free_bytes", lambda: SAFETY_RESERVE_BYTES + 1024**3
    )
    published = writer.capture_pinned(
        repository,
        manifest_sha256=snapshot.manifest_sha256,
        cohort_id=snapshot.cohort_id,
        decision_date=DECISION_DATE,
        as_of=PUBLISHED_AT,
    )
    assert published["status"] == "published"
    assert len(str(Path(published["directory"]) / "capture.json")) > 260

    reopened = BoundedRuleResearchCaptureWriter(output_root, read_only=True).read(
        published["receipt"]["capture_identity_sha256"]
    )
    assert reopened["receipt"] == published["receipt"]
    assert reopened["capture"]["capture_identity_sha256"] == (
        published["receipt"]["capture_identity_sha256"]
    )


def test_source_hardlink_added_after_writer_construction_is_rejected(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    output_root = scope.root / "captures"
    writer = BoundedRuleResearchCaptureWriter(output_root, research_scope=scope)
    _, _, capture = _fixture(tmp_path)
    source_database = Path(scope.source_database)
    alias = source_database.with_name("market-alias.sqlite")
    try:
        os.link(source_database, alias)
    except OSError as exc:
        pytest.skip(f"本機檔案系統不支援 hardlink fixture：{exc}")
    monkeypatch.setattr(
        RuleResearchCapture,
        "to_dict",
        lambda self: pytest.fail("scope revalidation must precede serialization"),
    )

    _expect(
        "path_hardlink_rejected",
        lambda: writer.write(capture, revalidate=lambda: pytest.fail("unexpected revalidation")),
    )
    assert not output_root.exists()


def test_output_root_symlink_added_after_writer_construction_is_rejected(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    output_root = scope.root / "captures"
    output_root.mkdir(parents=True)
    writer = BoundedRuleResearchCaptureWriter(output_root, research_scope=scope)
    _, _, capture = _fixture(tmp_path)
    moved_root = scope.root / "captures-original"
    output_root.rename(moved_root)
    outside_root = tmp_path / "outside-target"
    outside_root.mkdir()
    try:
        output_root.symlink_to(outside_root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"本機不允許建立 symlink fixture：{exc}")
    monkeypatch.setattr(
        RuleResearchCapture,
        "to_dict",
        lambda self: pytest.fail("scope revalidation must precede serialization"),
    )

    _expect(
        "path_link_rejected",
        lambda: writer.write(capture, revalidate=lambda: pytest.fail("unexpected revalidation")),
    )
    assert not (outside_root / ".writer.lock").exists()
