"""恢復只重用已驗原件；容量、closed映射及前後來源變動守衛仍生效。"""
from hashlib import sha256
import json

import pytest

import app_module.technical_source_copy as module
from app_module.personal_data_paths import to_internal_io_path
from app_module.research_output_copy import ResearchOutputCopyBudget
from tests.test_price_bookmark_copy import _prepare, BUDGET
from tests.test_daily_market_technical_universe_price_query_v1 import exact_price_store


@pytest.fixture
def archive_source(tmp_path):
    root = tmp_path / "archive"
    root.mkdir()
    members = {"a.json": b"1234", "b.json": b"123456", "c.json": b"123", "d.json": b"123456789"}
    for name, raw in members.items():
        (root / name).write_bytes(raw)
    pin = {key: "a" * 64 for key in module.TechnicalSourcePin.__dataclass_fields__}
    pin["store_output_root"] = str(tmp_path / "unavailable-original/live/universe")
    body = {"schema": module.SCHEMA, "status": "copied_and_strict_readers_verified", "copied_pin": pin,
            "destination_files": [{"path": name, "bytes": len(raw), "sha256": sha256(raw).hexdigest()}
                                  for name, raw in members.items()]}
    raw = json.dumps(body).encode()
    (root / "TECHNICAL_COPY_RECEIPT.json").write_bytes(raw)
    return root, sha256(raw).hexdigest(), ResearchOutputCopyBudget(4096, 16384, 32, 8), members


@pytest.mark.parametrize("retain", [False, True])
def test_reuse_has_explicit_total_and_per_file_bounds(archive_source, monkeypatch, retain):
    root, digest, budget, members = archive_source
    monkeypatch.setattr(module, "_ARCHIVE_REUSE_FILE_BYTES", 8)
    monkeypatch.setattr(module, "_ARCHIVE_REUSE_TOTAL_BYTES", 10)
    archive = module._Archive(root, digest, budget, None, retain_verified_bytes=retain)
    retained = {name: archive.retained_bytes(archive.logical_root / name) for name in members}
    assert retained == {"a.json": b"1234" if retain else None,
                        "b.json": b"123456" if retain else None, "c.json": None, "d.json": None}
    assert sum(len(raw) for raw in retained.values() if raw is not None) <= 10


def test_cached_reads_keep_hash_mapping_cancel_and_full_disk_verification(archive_source, monkeypatch):
    root, digest, budget, members = archive_source
    archive = module._Archive(root, digest, budget, None, retain_verified_bytes=True)
    files = module._Files(budget, None, archive)
    actual_read = module._read_bounded_file
    opened = []
    def read(path, maximum):
        opened.append(path)
        return actual_read(path, maximum)
    monkeypatch.setattr(module, "_read_bounded_file", read)
    logical = archive.logical_root / "a.json"
    for _ in range(2):
        assert files.read(logical, sha256(members["a.json"]).hexdigest()) == members["a.json"]
    assert opened == []
    with pytest.raises(module.TechnicalSourceCopyError, match="source_sha_mismatch"):
        files.read(logical, "0" * 64)
    with pytest.raises(module.TechnicalSourceCopyError, match="outside_closed_map"):
        files.read(archive.logical_root.parent / "unlisted.json")
    files.cancel = lambda: True
    with pytest.raises(module.TechnicalSourceCopyError, match="cancelled"):
        files.read(logical)
    files.cancel = None
    files.finish()
    assert set(opened) == {root / name for name in members} | {root / "TECHNICAL_COPY_RECEIPT.json"}
    assert len(opened) == len(members) + 1
    (root / "a.json").write_bytes(b"9999")
    assert files.read(logical) == b"1234"
    with pytest.raises(module.TechnicalSourceCopyError, match="source_sha_mismatch"):
        files.finish()


def test_initial_verification_does_not_cache_tampered_member(archive_source):
    root, digest, budget, _ = archive_source
    (root / "a.json").write_bytes(b"9999")
    with pytest.raises(module.TechnicalSourceCopyError, match="archive_member_sha_mismatch"):
        module._Archive(root, digest, budget, None, retain_verified_bytes=True)


def test_restore_cannot_publish_when_cached_source_changes_during_copy(exact_price_store, tmp_path, monkeypatch):
    _, bundle, _, _ = _prepare(exact_price_store, tmp_path)
    master = bundle / "TECHNICAL_COPY_RECEIPT.json"
    body = json.loads(master.read_bytes())
    member = next(item for item in body["destination_files"]
                  if item["bytes"] and item["bytes"] <= module._ARCHIVE_REUSE_FILE_BYTES)
    changed = bundle / member["path"]
    with open(to_internal_io_path(changed), "rb") as stream:
        original = stream.read()
    actual_finish = module._Files.finish
    finishes = 0
    def finish(files):
        nonlocal finishes
        finishes += 1
        if finishes == 2:
            assert files.archive is not None
            assert files.archive.retained_bytes(files.archive.logical_root / member["path"]) == original
            with open(to_internal_io_path(changed), "wb") as stream:
                stream.write(bytes([original[0] ^ 1]) + original[1:])
        return actual_finish(files)
    monkeypatch.setattr(module._Files, "finish", finish)
    target = tmp_path / "restored"
    with pytest.raises(module.TechnicalSourceCopyError, match="source_sha_mismatch"):
        module.restore_technical_source(bundle, sha256(master.read_bytes()).hexdigest(), target, budget=BUDGET)
    assert finishes == 2
    assert not (target / "TECHNICAL_COPY_RECEIPT.json").exists()
    assert (target / ".technical_copy_pending.json").is_file()
    assert (target / "TECHNICAL_COPY_FAILURE.json").is_file()


@pytest.mark.parametrize("option", [None, 1, "yes"])
def test_reuse_option_requires_boolean(archive_source, option):
    root, digest, budget, _ = archive_source
    with pytest.raises(module.TechnicalSourceCopyError, match="reuse_option_invalid"):
        module._Archive(root, digest, budget, None, retain_verified_bytes=option)
