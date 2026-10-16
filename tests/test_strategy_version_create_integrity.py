"""只在隔離版本目錄驗證新建保留前版與失敗原子性，不變更升級資格。"""
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest

from app_module import strategy_version_service as version_module
from app_module.strategy_version_service import StrategyVersionService


class _Config:
    def __init__(self, root: Path):
        self.root = root

    def resolve_output_path(self, relative_path: str) -> Path:
        return self.root / relative_path


class _Clock:
    @staticmethod
    def now():
        return datetime(2026, 10, 15, 18, 0, 0)


def _service(tmp_path):
    return StrategyVersionService(_Config(tmp_path))


def _create(service, source, *, version_id=None):
    return service.create_version(strategy_id="fixture-strategy", source_run_id=source,
        params={"marker": source}, config={"source": "isolated-fixture"},
        validation_status="pending", version_id=version_id)


def _pin(path):
    info = path.stat()
    return path.read_bytes(), info.st_mtime_ns, info.st_ctime_ns


def test_two_default_creates_in_same_second_preserve_both_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(version_module, "datetime", _Clock)
    service = _service(tmp_path)
    first = _create(service, "source-one")
    first_path = service.versions_dir / f"{first}.json"
    before = _pin(first_path)
    second = _create(service, "source-two")
    assert first != second
    assert _pin(first_path) == before
    assert service.get_version(first).source_run_id == "source-one"
    assert service.get_version(second).source_run_id == "source-two"
    assert len(service.list_versions()) == 2


def test_reused_explicit_id_refused_without_replacing_original(tmp_path):
    service = _service(tmp_path)
    _create(service, "source-one", version_id="explicit-id")
    original = service.versions_dir / "explicit-id.json"
    before = _pin(original)
    with pytest.raises(FileExistsError):
        _create(service, "source-two", version_id="explicit-id")
    assert _pin(original) == before
    assert service.get_version("explicit-id").source_run_id == "source-one"


def test_unpublished_temp_not_exposed_as_a_saved_version(tmp_path, monkeypatch):
    service = _service(tmp_path)
    fsync = version_module.os.fsync
    seen = []
    def observe(descriptor):
        seen.append(tuple(row["version_id"] for row in service.list_versions()))
        fsync(descriptor)
    monkeypatch.setattr(version_module.os, "fsync", observe)
    created = _create(service, "source-one")
    assert seen == [()]
    assert [row["version_id"] for row in service.list_versions()] == [created]
    assert [path.name for path in service.versions_dir.iterdir()] == [f"{created}.json"]


def test_failed_flush_does_not_publish_or_leave_owned_temp(tmp_path, monkeypatch):
    service = _service(tmp_path)
    def failed_flush(_descriptor):
        raise OSError("isolated flush failure")
    monkeypatch.setattr(version_module.os, "fsync", failed_flush)
    with pytest.raises(OSError, match="isolated flush failure"):
        _create(service, "source-one", version_id="failed-write")
    assert list(service.versions_dir.iterdir()) == []


def test_legacy_unpublished_json_not_listed_or_modified(tmp_path):
    service = _service(tmp_path)
    created = _create(service, "original", version_id="legacy")
    pending = service.versions_dir / "legacy.tmp.json"
    pending.write_bytes((service.versions_dir / f"{created}.json").read_bytes())
    before = _pin(pending)
    assert [row["version_id"] for row in service.list_versions()] == [created]
    assert _pin(pending) == before


@pytest.mark.parametrize("version_id", ["../outside", "a/b", r"a\b", "", ".", "x" * 201])
def test_new_id_must_remain_a_safe_basename(tmp_path, version_id):
    service = _service(tmp_path)
    with pytest.raises(ValueError, match="策略版本 ID"):
        _create(service, "invalid", version_id=version_id)
    assert list(service.versions_dir.iterdir()) == []


def test_serialization_failure_leaves_previous_version_and_no_temp(tmp_path):
    service = _service(tmp_path)
    created = _create(service, "original")
    before = _pin(service.versions_dir / f"{created}.json")
    with pytest.raises(TypeError):
        service.create_version(strategy_id="fixture", params={"invalid": object()})
    assert _pin(service.versions_dir / f"{created}.json") == before
    assert len(list(service.versions_dir.iterdir())) == 1


def test_unowned_existing_temp_is_never_deleted(tmp_path, monkeypatch):
    service = _service(tmp_path)
    monkeypatch.setattr(version_module, "uuid4", lambda: SimpleNamespace(hex="owned-elsewhere"))
    unowned = service.versions_dir / ".owned-elsewhere.tmp"
    unowned.write_bytes(b"other writer bytes")
    before = _pin(unowned)
    with pytest.raises(FileExistsError):
        _create(service, "new", version_id="new-id")
    assert _pin(unowned) == before
    assert list(service.versions_dir.iterdir()) == [unowned]


def test_publish_failure_only_cleans_owned_temp(tmp_path, monkeypatch):
    service = _service(tmp_path)
    def failed_publish(*_args):
        raise PermissionError("isolated publish refusal")
    publisher = "rename" if version_module.os.name == "nt" else "link"
    monkeypatch.setattr(version_module.os, publisher, failed_publish)
    with pytest.raises(PermissionError, match="isolated publish refusal"):
        _create(service, "new")
    assert list(service.versions_dir.iterdir()) == []


def test_competing_create_at_publication_preserves_winner(tmp_path, monkeypatch):
    service = _service(tmp_path)
    publisher = "rename" if version_module.os.name == "nt" else "link"
    publish = getattr(version_module.os, publisher)
    captured = []
    def competing_publish(temporary, final):
        if not captured:
            captured.append(None)
            _create(service, "competitor", version_id="shared")
            captured[0] = _pin(final)
        publish(temporary, final)
    monkeypatch.setattr(version_module.os, publisher, competing_publish)
    with pytest.raises(FileExistsError):
        _create(service, "loser", version_id="shared")
    assert service.get_version("shared").source_run_id == "competitor"
    assert _pin(service.versions_dir / "shared.json") == captured[0]
    assert [path.name for path in service.versions_dir.iterdir()] == ["shared.json"]


def test_concurrent_same_id_has_one_complete_winner(tmp_path, monkeypatch):
    service = _service(tmp_path)
    barrier = Barrier(4, timeout=10)
    fsync = version_module.os.fsync
    def synchronize(descriptor):
        fsync(descriptor)
        barrier.wait()
    monkeypatch.setattr(version_module.os, "fsync", synchronize)
    def create(source):
        try:
            return _create(service, source, version_id="shared"), source
        except FileExistsError:
            return None, source
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(create, ("one", "two", "three", "four")))
    winners = [(version, source) for version, source in results if version is not None]
    assert len(winners) == 1
    assert service.get_version("shared").source_run_id == winners[0][1]
    assert service.get_version("shared").params == {"marker": winners[0][1]}
    assert len(service.list_versions()) == 1
    assert [path.name for path in service.versions_dir.iterdir()] == ["shared.json"]


def test_explicit_update_remains_an_intentional_mutable_operation(tmp_path):
    service = _service(tmp_path)
    created = _create(service, "original", version_id="version-legacy.1")
    assert service.update_version(created, notes="明確更新既有聲明")
    assert service.get_version(created).notes == "明確更新既有聲明"
    assert service.get_version(created).source_run_id == "original"
    assert [row["version_id"] for row in service.list_versions()] == [created]


@pytest.mark.parametrize("failed_phase", ["flush", "publication"])
def test_cleanup_error_never_masks_original_failure(tmp_path, monkeypatch, caplog, failed_phase):
    service = _service(tmp_path)
    unlink = Path.unlink
    def cleanup_failed(path, *args, **kwargs):
        if path.suffix == ".tmp":
            raise PermissionError("isolated cleanup failure")
        return unlink(path, *args, **kwargs)
    def operation_failed(*_args):
        raise OSError("isolated original failure")
    monkeypatch.setattr(Path, "unlink", cleanup_failed)
    operation = "fsync" if failed_phase == "flush" else (
        "rename" if version_module.os.name == "nt" else "link")
    monkeypatch.setattr(version_module.os, operation, operation_failed)
    with pytest.raises(OSError, match="isolated original failure"):
        _create(service, "new", version_id="failed")
    assert service.get_version("failed") is None
    assert service.list_versions() == []
    assert [path.suffix for path in service.versions_dir.iterdir()] == [".tmp"]
    assert "專屬版本暫存無法清理" in caplog.text


def test_cleanup_failure_after_publication_still_returns_exact_version(tmp_path, monkeypatch, caplog):
    service = _service(tmp_path)
    unlink = Path.unlink
    def cleanup_failed(path, *args, **kwargs):
        if path.suffix == ".tmp":
            raise PermissionError("isolated cleanup failure")
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", cleanup_failed)
    created = _create(service, "published", version_id="published")
    assert created == "published"
    assert service.get_version(created).source_run_id == "published"
    assert [row["version_id"] for row in service.list_versions()] == [created]
    assert "專屬版本暫存無法清理" in caplog.text
