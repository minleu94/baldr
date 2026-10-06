"""consumer 僅使用 synthetic fixture；不存取正式 personal／DB 或網路。"""

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

import app_module.market_csv_export as consumer
from app_module.personal_data_paths import (
    PersonalDataPathError,
    plan_market_only_export,
    resolve_personal_data_paths,
)

pytestmark = pytest.mark.skipif(os.name != "nt", reason="本版 consumer 必須有 Windows handle sharing")


@pytest.fixture
def fixture_plan(tmp_path):
    market = tmp_path / "FA_Data"
    paths = resolve_personal_data_paths(market, personal_root=market / "personal", environ={})
    names = ("daily_price/20261006.csv", "meta_data/market_index.csv", "broker_flow/sub/a.csv")
    for name in names:
        source = market / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"date,stock,close\n20261006,1234,100\n")
    # 不在清單內的 synthetic 私人／output／DB 都保留，不讓 consumer 掃描。
    for name in ("personal/secret.csv", "output/watchlist.json", "sqlite/twstock.db"):
        excluded = market / name
        excluded.parent.mkdir(parents=True, exist_ok=True)
        excluded.write_bytes(b"synthetic excluded")
    return plan_market_only_export(paths, names, destination_root=tmp_path / "package")


def run_export(plan, **kwargs):
    # 測試 caller 只對自己生成的 synthetic CSV 明示 pins。
    hashes = kwargs.pop("expected_sha256", {e.relative_path: hashlib.sha256(b"date,stock,close\n20261006,1234,100\n").hexdigest() for e in plan.files})
    return consumer.export_market_csv(plan, expected_sha256=hashes, **kwargs)


def snapshot(plan):
    return {entry.source_path: (entry.source_path.read_bytes(), entry.source_path.stat()) for entry in plan.files}


def assert_unchanged(before):
    for path, (raw, info) in before.items():
        after = path.stat()
        assert path.read_bytes() == raw
        assert (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) == (
            info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def reject(plan, code, **kwargs):
    with pytest.raises(PersonalDataPathError) as caught:
        run_export(plan, **kwargs)
    assert caught.value.code == code
    assert not (plan.destination_root / consumer.RECEIPT_NAME).exists()


def junction(link, target):
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr


def test_exact_whitelist_copy_atomic_receipt_and_source_unchanged(fixture_plan):
    plan = fixture_plan
    before = snapshot(plan)
    receipt = run_export(plan)
    assert receipt.destination_root == plan.destination_root
    raw = receipt.receipt_path.read_bytes()
    assert receipt.receipt_sha256 == hashlib.sha256(raw).hexdigest()
    payload = json.loads(raw)
    assert payload["schema"] == "market-csv-export.v1"
    assert payload["status"] == "verified"
    assert payload["file_count"] == len(plan.files)
    assert len(receipt.files) == len(plan.files)
    assert not list(plan.destination_root.glob("*.pending"))
    copied = {p.relative_to(plan.destination_root).as_posix() for p in plan.destination_root.rglob("*") if p.is_file()}
    assert copied == {entry.relative_path for entry in plan.files} | {consumer.RECEIPT_NAME}
    for exported, entry in zip(receipt.files, plan.files):
        assert (plan.destination_root / entry.relative_path).read_bytes() == before[entry.source_path][0]
        assert exported.sha256 == hashlib.sha256(before[entry.source_path][0]).hexdigest()
        assert exported.source_identity == entry.identity
    assert_unchanged(before)


@pytest.mark.parametrize("existing", ["empty", "file", "data"])
def test_existing_target_never_overwritten(fixture_plan, existing):
    target = fixture_plan.destination_root
    if existing == "file":
        target.write_bytes(b"existing")
    else:
        target.mkdir()
        if existing == "data":
            (target / "keep.csv").write_bytes(b"existing")
    reject(fixture_plan, "directory_root_required" if existing == "file" else "export_destination_exists")
    assert target.read_bytes() == b"existing" if existing == "file" else target.is_dir()
    if existing == "data":
        assert (target / "keep.csv").read_bytes() == b"existing"


def test_repeat_completed_export_refused(fixture_plan):
    result = run_export(fixture_plan)
    before = result.receipt_path.read_bytes()
    with pytest.raises(consumer.MarketCsvExportError, match="export_destination_exists"):
        run_export(fixture_plan)
    assert result.receipt_path.read_bytes() == before


def test_handle_receipt_rename_supports_utf16_surrogate_paths(fixture_plan):
    plan = replace(fixture_plan, destination_root=fixture_plan.destination_root.with_name("市場_\U0001f4c8"))
    result = run_export(plan)
    assert result.receipt_path.is_file()
    assert result.receipt_sha256 == hashlib.sha256(result.receipt_path.read_bytes()).hexdigest()


def test_empty_plan_and_missing_parent_no_side_effect(fixture_plan):
    reject(replace(fixture_plan, files=()), "empty_market_export_plan")
    plan = replace(fixture_plan, destination_root=fixture_plan.destination_root / "missing" / "package")
    reject(plan, "export_parent_missing")
    assert not fixture_plan.destination_root.exists()


@pytest.mark.parametrize("name", ["personal/notes.csv", "output/a.csv", "sqlite/a.db", ".", "daily_price/../personal/a.csv",
                                 "daily_price/a.csv:secret", "daily_price/a.sqlite", "daily_price/a.csv\\other"])
def test_forged_plan_rejects_nonmarket_paths(fixture_plan, name):
    entry = replace(fixture_plan.files[0], relative_path=name)
    with pytest.raises(PersonalDataPathError):
        run_export(replace(fixture_plan, files=(entry,)))
    assert not fixture_plan.destination_root.exists()


@pytest.mark.parametrize("name", ["daily_price/personal/a.csv", "daily_price/Output/a.csv", "broker_flow/sqlite/a.csv",
                                 "daily_price/db.sqlite.csv", "daily_price/a.db.csv", "daily_price/a-wal.csv"])
def test_private_or_sqlite_disguised_names_rejected(fixture_plan, name):
    source = fixture_plan.paths.market_root / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"synthetic")
    plan = plan_market_only_export(fixture_plan.paths, [name], destination_root=fixture_plan.destination_root)
    reject(plan, "private_export_component" if "/personal/" in name or "/Output/" in name or "/sqlite/" in name else "sqlite_name_excluded")
    assert not plan.destination_root.exists()


@pytest.mark.parametrize("magic", [b"SQLite format 3\x00", b"\x37\x7f\x06\x82", b"\x37\x7f\x06\x83", b"\xd9\xd5\x05\xf9\x20\xa1\x63\xd7"])
def test_sqlite_magic_under_csv_rejected_before_mkdir(fixture_plan, magic):
    source = fixture_plan.files[0].source_path
    source.write_bytes(magic + b"synthetic fixture" * 30)
    plan = plan_market_only_export(fixture_plan.paths, [fixture_plan.files[0].relative_path], destination_root=fixture_plan.destination_root)
    reject(plan, "sqlite_content_excluded")
    assert not plan.destination_root.exists()


def test_binary_disguised_csv_rejected(fixture_plan):
    source = fixture_plan.files[0].source_path
    source.write_bytes(b"synthetic binary\x00SHM")
    plan = plan_market_only_export(fixture_plan.paths, [fixture_plan.files[0].relative_path], destination_root=fixture_plan.destination_root)
    reject(plan, "binary_csv_content_excluded")
    assert not plan.destination_root.exists()


def test_changed_source_after_plan_rejected(fixture_plan):
    fixture_plan.files[0].source_path.write_bytes(b"changed fixture")
    reject(fixture_plan, "export_file_changed")
    assert not fixture_plan.destination_root.exists()


@pytest.mark.parametrize("hashes", [{}, {"daily_price/20261006.csv": "0" * 64}, {"unexpected.csv": "a" * 64}])
def test_hash_keyset_must_exactly_match_plan(fixture_plan, hashes):
    reject(fixture_plan, "explicit_source_hashes_required", expected_sha256=hashes)
    assert not fixture_plan.destination_root.exists()


@pytest.mark.parametrize("value", ["X" * 64, "a" * 63, "", None])
def test_invalid_source_hash_rejected(fixture_plan, value):
    hashes = {e.relative_path: value for e in fixture_plan.files}
    reject(fixture_plan, "explicit_source_hashes_required", expected_sha256=hashes)


def test_source_hash_mismatch_even_when_metadata_matches(fixture_plan):
    hashes = {e.relative_path: "0" * 64 for e in fixture_plan.files}
    reject(fixture_plan, "export_source_hash_mismatch", expected_sha256=hashes)
    assert not fixture_plan.destination_root.exists()


def test_replaced_identity_and_forged_source_rejected(fixture_plan):
    wrong = replace(fixture_plan.files[0], identity=(0, 0, 0, 0, 0))
    reject(replace(fixture_plan, files=(wrong,)), "export_file_changed")
    wrong = replace(fixture_plan.files[0], source_path=fixture_plan.paths.personal_root / "secret.csv")
    reject(replace(fixture_plan, files=(wrong,)), "export_source_changed")


def test_new_source_hardlink_after_plan_rejected(fixture_plan):
    os.link(fixture_plan.files[0].source_path, fixture_plan.paths.personal_root / "alias.csv")
    reject(fixture_plan, "hardlinked_export_file")


def test_destination_parent_junction_escape_rejected(fixture_plan):
    link = fixture_plan.destination_root.parent / "linked"
    junction(link, fixture_plan.paths.personal_root)
    plan = replace(fixture_plan, destination_root=link / "package")
    reject(plan, "linked_path")
    assert not (fixture_plan.paths.personal_root / "package").exists()


def test_market_directory_replaced_by_junction_after_plan(fixture_plan):
    original = fixture_plan.files[0].source_path.parent
    original.rename(original.with_name("saved_daily_price"))
    junction(original, fixture_plan.paths.personal_root)
    reject(fixture_plan, "linked_path")


def test_cancel_before_copy_has_no_target(fixture_plan):
    reject(fixture_plan, "export_cancelled", cancelled=lambda: True)
    assert not fixture_plan.destination_root.exists()


def test_cancel_during_copy_preserves_partial_without_receipt(fixture_plan):
    before = snapshot(fixture_plan)
    def cancel():
        return any(fixture_plan.destination_root.glob("daily_price/*.csv"))
    reject(fixture_plan, "export_cancelled", cancelled=cancel)
    assert fixture_plan.destination_root.exists()
    assert_unchanged(before)
    reject(fixture_plan, "export_destination_exists")


def test_cancel_before_receipt_publication(fixture_plan):
    reject(fixture_plan, "export_cancelled", cancelled=lambda: bool(list(fixture_plan.destination_root.glob("*.pending"))))
    assert list(fixture_plan.destination_root.glob("*.pending"))
    assert all(json.loads(p.read_bytes())["status"] == "verified" for p in fixture_plan.destination_root.glob("*.pending"))
    assert not (fixture_plan.destination_root / consumer.RECEIPT_NAME).exists()


def test_injected_publication_failure_preserves_source_and_no_completion(fixture_plan, monkeypatch):
    before = snapshot(fixture_plan)
    def fail(*args):
        raise OSError("synthetic publication failure")
    monkeypatch.setattr(consumer, "_publish_receipt", fail)
    reject(fixture_plan, "export_io_failed")
    assert list(fixture_plan.destination_root.glob("*.pending"))
    assert_unchanged(before)


def test_final_callback_injected_artifact_rejected(fixture_plan):
    def callback():
        if list(fixture_plan.destination_root.glob("*.pending")):
            (fixture_plan.destination_root / "private.csv").write_bytes(b"synthetic injected")
        return False
    reject(fixture_plan, "unexpected_export_artifact", cancelled=callback)


def test_final_callback_pending_replacement_cannot_publish(fixture_plan):
    changed = []
    def callback():
        pending = list(fixture_plan.destination_root.glob("*.pending"))
        if pending and not changed:
            pending[0].rename(pending[0].with_suffix(".saved"))
            pending[0].write_bytes(b"synthetic replacement")
            changed.append(True)
        return False
    reject(fixture_plan, "export_receipt_identity_changed", cancelled=callback)
    assert changed == [True]


@pytest.mark.parametrize("kind", ["source", "output"])
def test_last_callback_hardlink_cannot_bypass_final_check(fixture_plan, kind):
    linked = []
    def callback():
        if list(fixture_plan.destination_root.glob("*.pending")) and not linked:
            source = fixture_plan.files[0].source_path if kind == "source" else fixture_plan.destination_root / fixture_plan.files[0].relative_path
            try:
                os.link(source, fixture_plan.destination_root.parent / "synthetic_alias.csv")
            except OSError:
                # 某 Windows filesystem 在 share lock 下直接拒絕 hardlink。
                linked.append(False)
            else:
                linked.append(True)
        return False
    try:
        run_export(fixture_plan, cancelled=callback)
    except PersonalDataPathError as exc:
        assert linked == [True]
        assert exc.code in {"hardlinked_export_file", "export_handle_alias"}
        assert not (fixture_plan.destination_root / consumer.RECEIPT_NAME).exists()
    else:
        assert linked == [False]


def test_streaming_large_csv_cancellation_keeps_only_partial(fixture_plan):
    source = fixture_plan.files[0].source_path
    source.write_bytes(b"date,stock,close\n" + b"20261006,1234,100\n" * 140000)
    plan = plan_market_only_export(fixture_plan.paths, [fixture_plan.files[0].relative_path], destination_root=fixture_plan.destination_root)
    pins = {plan.files[0].relative_path: hashlib.sha256(source.read_bytes()).hexdigest()}
    before = snapshot(plan)
    target = plan.destination_root / plan.files[0].relative_path
    reject(plan, "export_cancelled", expected_sha256=pins, cancelled=lambda: target.exists() and target.stat().st_size >= consumer._CHUNK_SIZE)
    assert 0 < target.stat().st_size < source.stat().st_size
    assert_unchanged(before)


def test_source_and_ancestor_windows_handles_block_mutation(fixture_plan):
    attempted = []
    def callback():
        if fixture_plan.destination_root.exists() and not attempted:
            for action in (lambda: fixture_plan.files[0].source_path.write_bytes(b"must not write"),
                           lambda: fixture_plan.files[0].source_path.parent.rename(fixture_plan.paths.market_root / "escape")):
                with pytest.raises(OSError):
                    action()
                attempted.append(True)
        return False
    before = snapshot(fixture_plan)
    run_export(fixture_plan, cancelled=callback)
    assert len(attempted) == 2
    assert_unchanged(before)


def test_output_handle_blocks_overwrite_during_copy(fixture_plan):
    attempts = []
    def callback():
        target = fixture_plan.destination_root / fixture_plan.files[0].relative_path
        if target.exists() and not attempts:
            with pytest.raises(OSError):
                target.write_bytes(b"must not overwrite")
            attempts.append(True)
        return False
    run_export(fixture_plan, cancelled=callback)
    assert attempts == [True]


def test_receipt_publication_refuses_racing_existing_receipt(fixture_plan, monkeypatch):
    publish = consumer._publish_receipt
    def race(pending, target):
        target.write_bytes(b"existing synthetic receipt")
        publish(pending, target)
    monkeypatch.setattr(consumer, "_publish_receipt", race)
    with pytest.raises(consumer.MarketCsvExportError, match="export_io_failed"):
        run_export(fixture_plan)
    assert (fixture_plan.destination_root / consumer.RECEIPT_NAME).read_bytes() == b"existing synthetic receipt"


def test_new_process_reads_same_bytes_and_receipt(fixture_plan):
    result = run_export(fixture_plan)
    script = "import hashlib,json,sys; from pathlib import Path; root=Path(sys.argv[1]); r=json.loads((root/sys.argv[2]).read_bytes()); assert r['status']=='verified'; assert all(hashlib.sha256((root/e['relative_path']).read_bytes()).hexdigest()==e['sha256'] for e in r['files']); print(r['file_count'])"
    completed = subprocess.run([sys.executable, "-c", script, str(result.destination_root), consumer.RECEIPT_NAME],
                               capture_output=True, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "3"
