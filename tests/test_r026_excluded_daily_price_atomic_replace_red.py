from __future__ import annotations

import base64
from datetime import date
import hashlib
import json
import os
from pathlib import Path

import pytest

from data_module import excluded_daily_price_revision as exclusions
from data_module.contracts.source_revision import (
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
)
from scripts import repair_excluded_daily_prices as repair
from test_excluded_daily_price_revision import (
    _make_database,
    _prepare_test_run,
    _write_evidence_archive,
    _write_market_receipt,
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _applied_run(
    root: Path,
    archive: Path,
    run_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, object]:
    database_path = _make_database(root, run_id)
    original_market_validator = exclusions._validate_market_chain
    run_dir = _prepare_test_run(
        root, archive, database_path, monkeypatch, run_id
    )
    repair.apply(
        run_dir / "plan.json",
        repair.file_hash(run_dir / "plan.json"),
        repair.CONFIRM,
    )
    monkeypatch.setattr(
        exclusions, "_validate_market_chain", original_market_validator
    )
    return database_path, run_dir, original_market_validator


@pytest.mark.parametrize("race_target", ["payload", "receipt"])
def test_archive_payload_or_receipt_hash_parse_same_atomic_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    race_target: str,
) -> None:
    root = tmp_path / "FA_Data"
    root.mkdir()
    archive = _write_evidence_archive(root)
    database_path, _run_dir, _validator = _applied_run(
        root, archive, "archive-payload-receipt-race", monkeypatch
    )

    payload_path = archive / "twse-20260520.json"
    receipt_path = archive / "twse-20260520.receipt.json"
    archive_evidence_paths = {archive / name for name in exclusions._EVIDENCE_FILES}
    payload_paths = {
        archive / f"{venue}-{day}.json"
        for day in exclusions.OFFICIAL_DATES
        for venue in ("twse", "tpex")
    }
    old_payload = payload_path.read_bytes()
    old_receipt = receipt_path.read_bytes()
    replacement_payload_obj = json.loads(old_payload.decode("utf-8"))
    replacement_payload_obj["atomic_replace_probe"] = "parsed-after-hash"
    replacement_payload = _json_bytes(replacement_payload_obj)
    replacement_receipt_obj = json.loads(old_receipt.decode("utf-8"))
    if race_target == "payload":
        replacement_receipt_obj["sha256"] = _sha256(replacement_payload)
    else:
        replacement_receipt_obj["atomic_replace_probe"] = "parsed-after-hash"
    replacement_receipt = _json_bytes(replacement_receipt_obj)
    payload_swap = archive / "twse-20260520.json.swap"
    receipt_swap = archive / "twse-20260520.receipt.json.swap"
    if race_target == "payload":
        payload_swap.write_bytes(replacement_payload)
    receipt_swap.write_bytes(replacement_receipt)

    hashed_bytes: dict[Path, bytes] = {}
    parsed_bytes: dict[Path, bytes] = {}
    read_counts: dict[Path, int] = {}
    payload_rehashes = 0
    original_read_bytes = Path.read_bytes
    original_hash_file = exclusions._hash_file
    original_json_from_bytes = exclusions._json_from_bytes
    replaced = False

    def read_then_replace(path: Path) -> bytes:
        nonlocal replaced
        payload = original_read_bytes(path)
        if path in archive_evidence_paths:
            read_counts[path] = read_counts.get(path, 0) + 1
            if path not in hashed_bytes:
                hashed_bytes[path] = payload
        if path == receipt_path and not replaced:
            # 所有 hash/size 讀取完後、parse 前原子替換；舊實作會重開新檔。
            if race_target == "payload":
                os.replace(payload_swap, payload_path)
            os.replace(receipt_swap, receipt_path)
            replaced = True
        return payload

    def record_payload_rehash(path: Path) -> str:
        nonlocal payload_rehashes
        if path in payload_paths:
            payload_rehashes += 1
        return original_hash_file(path)

    def record_parse(payload: bytes, path: Path) -> dict[str, object]:
        if path in archive_evidence_paths:
            parsed_bytes[path] = payload
        return original_json_from_bytes(payload, path)

    monkeypatch.setattr(Path, "read_bytes", read_then_replace)
    monkeypatch.setattr(exclusions, "_hash_file", record_payload_rehash)
    monkeypatch.setattr(exclusions, "_json_from_bytes", record_parse)

    # 同一檔案的 hash、大小與 JSON 解析應使用同一份 bytes。
    exclusions.load_exclusion_evidence(database_path)

    assert replaced
    assert read_counts == {path: 1 for path in archive_evidence_paths}
    assert payload_rehashes == 0
    assert set(parsed_bytes) == archive_evidence_paths
    mismatches = {
        path.name: (_sha256(hashed_bytes[path]), _sha256(parsed_bytes[path]))
        for path in archive_evidence_paths
        if hashed_bytes.get(path) != parsed_bytes.get(path)
    }
    assert not mismatches, (
        f"archive {race_target} hash bytes 與 parsed bytes 不同：{mismatches!r}"
    )


def test_market_source_manifest_hash_and_parse_use_same_atomic_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "FA_Data"
    root.mkdir()
    database_path = _make_database(root, "market-manifest-race")
    market_dir = _write_market_receipt(root, database_path, "market-manifest-race")
    market_plan = json.loads((market_dir / "plan.json").read_text(encoding="utf-8"))
    manifest_path = Path(market_plan["sources"][0]["path"])
    original_manifest = manifest_path.read_bytes()
    replacement_obj = json.loads(original_manifest.decode("utf-8"))
    replacement_obj["atomic_replace_probe"] = "parsed-after-hash"
    replacement_manifest = _json_bytes(replacement_obj)
    replacement_path = manifest_path.with_name(manifest_path.name + ".swap")
    replacement_path.write_bytes(replacement_manifest)

    hashed_sha256: list[str] = []
    parsed_bytes: list[bytes] = []
    read_count = 0
    original_hash_file = exclusions._hash_file
    original_read_bytes = Path.read_bytes
    original_json_from_bytes = exclusions._json_from_bytes
    replaced = False

    def hash_then_replace(path: Path) -> str:
        nonlocal replaced
        digest = original_hash_file(path)
        if path == manifest_path and not replaced:
            hashed_sha256.append(digest)
            os.replace(replacement_path, manifest_path)
            replaced = True
        return digest

    def read_then_replace(path: Path) -> bytes:
        nonlocal read_count, replaced
        payload = original_read_bytes(path)
        if path == manifest_path:
            read_count += 1
            if not replaced:
                hashed_sha256.append(_sha256(payload))
                os.replace(replacement_path, manifest_path)
                replaced = True
        return payload

    def record_parse(payload: bytes, path: Path) -> dict[str, object]:
        if path == manifest_path:
            parsed_bytes.append(payload)
        return original_json_from_bytes(payload, path)

    monkeypatch.setattr(exclusions, "_hash_file", hash_then_replace)
    monkeypatch.setattr(Path, "read_bytes", read_then_replace)
    monkeypatch.setattr(exclusions, "_json_from_bytes", record_parse)

    exclusions._validate_market_chain(
        database_path,
        root,
        market_dir.relative_to(root).as_posix(),
        full_source_validation=False,
    )

    assert replaced
    assert len(hashed_sha256) == 1 and len(parsed_bytes) == 1
    assert read_count == 1
    assert hashed_sha256[0] == _sha256(parsed_bytes[0]), (
        "market source manifest hash bytes 與 parsed bytes 不同："
        f"hash={hashed_sha256[0]} parsed={_sha256(parsed_bytes[0])}"
    )


def test_rolled_back_run_is_legacy_empty_but_typed_namespace_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "FA_Data"
    root.mkdir()
    archive = _write_evidence_archive(root)
    database_path, run_dir, _validator = _applied_run(
        root, archive, "rollback-presence-distinction", monkeypatch
    )

    recovered = repair.recover(
        run_dir, rollback=True, confirm=repair.CONFIRM
    )
    assert recovered["state"] == "rolled_back"
    assert exclusions.load_exclusion_evidence(database_path) == []

    collector = getattr(
        exclusions, "collect_excluded_daily_price_revision_evidence", None
    )
    assert callable(collector), "excluded revision typed collector 尚未實作"
    namespace = collector(database_path, date(2016, 1, 1))
    assert namespace.namespace is SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION
    assert namespace.presence is SourceEvidencePresenceV1.PRESENT
    assert any(item.role_id.endswith("/rollback.json") for item in namespace.files)


def test_typed_collector_returns_empty_for_missing_root_and_prepare_only(
    tmp_path: Path,
) -> None:
    root = tmp_path / "FA_Data"
    root.mkdir()
    database_path = _make_database(root, "empty-revision-namespace")
    collector = getattr(
        exclusions, "collect_excluded_daily_price_revision_evidence", None
    )
    assert callable(collector), "excluded revision typed collector 尚未實作"

    missing = collector(database_path, date(2016, 1, 1))
    assert missing.namespace is SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION
    assert missing.presence is SourceEvidencePresenceV1.EMPTY
    assert missing.files == ()

    prepared = root / exclusions.RECEIPT_DIR / "prepare-only"
    prepared.mkdir(parents=True)
    (prepared / "before_rows.json").write_text("{}", encoding="utf-8")
    (prepared / "plan.json").write_text("{}", encoding="utf-8")
    empty = collector(database_path, date(2016, 1, 1))
    assert empty.presence is SourceEvidencePresenceV1.EMPTY
    assert empty.files == ()
    assert exclusions.load_exclusion_evidence(database_path) == []


def test_typed_collector_applied_roles_are_stable_and_cutoff_matches_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "FA_Data"
    root.mkdir()
    archive = _write_evidence_archive(root)
    database_path, run_dir, _validator = _applied_run(
        root, archive, "typed-role-fixture", monkeypatch
    )
    collector = getattr(
        exclusions, "collect_excluded_daily_price_revision_evidence", None
    )
    assert callable(collector), "excluded revision typed collector 尚未實作"

    legacy = exclusions.load_exclusion_evidence(database_path)
    assert len(legacy) == 1
    assert tuple(legacy[0]) == (
        "keys",
        "closed_dates",
        "plan_sha256",
        "receipt_sha256",
        "receipt_path",
        "acquired_at",
        "source_start_date",
        "evidence_archive_relative",
        "market_plan_sha256",
    )
    namespace = collector(database_path, date(2016, 1, 1))
    assert namespace.presence is SourceEvidencePresenceV1.PRESENT
    prefix = "run_" + base64.urlsafe_b64encode(b"typed-role-fixture").decode("ascii").rstrip("=")
    role_ids = {item.role_id for item in namespace.files}
    assert {
        f"{prefix}/revision.json",
        f"{prefix}/plan.json",
        f"{prefix}/journal.json",
        f"{prefix}/receipt.json",
        f"{prefix}/archive/archive.json",
        f"{prefix}/market/revision.json",
        f"{prefix}/market/journal.json",
        f"{prefix}/market/plan.json",
        f"{prefix}/market/receipt.json",
    } <= role_ids
    assert sum(role.startswith(f"{prefix}/archive/files/") for role in role_ids) == 16
    market_plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    market_dir = root / market_plan["market_receipt_relative_dir"]
    market_plan_obj = json.loads((market_dir / "plan.json").read_text(encoding="utf-8"))
    source_count = len(market_plan_obj["sources"])
    assert sum(role.startswith(f"{prefix}/market/sources/") for role in role_ids) == source_count

    cutoff = date(2016, 2, 11)
    with pytest.raises(ValueError, match="blocks historical PIT"):
        collector(database_path, cutoff)
    with pytest.raises(ValueError, match="blocks historical PIT"):
        exclusions.assert_excluded_source_revision_safe(database_path, cutoff)


@pytest.mark.parametrize("broken_piece", ["pending", "plan"])
def test_typed_collector_fails_closed_for_pending_or_broken_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    broken_piece: str,
) -> None:
    root = tmp_path / "FA_Data"
    root.mkdir()
    archive = _write_evidence_archive(root)
    database_path, run_dir, _validator = _applied_run(
        root, archive, f"typed-broken-{broken_piece}", monkeypatch
    )
    collector = getattr(
        exclusions, "collect_excluded_daily_price_revision_evidence", None
    )
    assert callable(collector), "excluded revision typed collector 尚未實作"

    if broken_piece == "pending":
        marker_path = run_dir / "revision.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["state"] = "pending"
        marker_path.write_bytes(_json_bytes(marker))
        expected = "進行中"
    else:
        (run_dir / "plan.json").write_text("{bad", encoding="utf-8")
        expected = "無法驗證"

    with pytest.raises(ValueError, match=expected):
        collector(database_path, date(2016, 1, 1))


def test_typed_collector_scan_error_is_not_reported_as_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "FA_Data"
    root.mkdir()
    database_path = _make_database(root, "typed-scan-error")
    receipt_root = root / exclusions.RECEIPT_DIR
    receipt_root.mkdir(parents=True)
    original_scandir = os.scandir

    def deny_receipt_root(path: str | os.PathLike[str]):
        if Path(path) == receipt_root:
            raise PermissionError("合成 typed receipt-root 權限錯誤")
        return original_scandir(path)

    collector = getattr(
        exclusions, "collect_excluded_daily_price_revision_evidence", None
    )
    assert callable(collector), "excluded revision typed collector 尚未實作"
    monkeypatch.setattr(os, "scandir", deny_receipt_root)
    with pytest.raises(ValueError, match="完整掃描|權限錯誤"):
        collector(database_path, date(2016, 1, 1))


def test_typed_collector_captures_each_validated_file_from_one_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "FA_Data"
    root.mkdir()
    archive = _write_evidence_archive(root)
    database_path, run_dir, _validator = _applied_run(
        root, archive, "typed-single-read", monkeypatch
    )
    collector = getattr(
        exclusions, "collect_excluded_daily_price_revision_evidence", None
    )
    assert callable(collector), "excluded revision typed collector 尚未實作"

    marker = json.loads((run_dir / "revision.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    market_dir = root / plan["market_receipt_relative_dir"]
    market_plan = json.loads((market_dir / "plan.json").read_text(encoding="utf-8"))
    archive_dir = root / plan["evidence_archive_relative"]
    expected_paths = {
        run_dir / name
        for name in ("revision.json", "plan.json", "journal.json", "receipt.json")
    }
    expected_paths.add(archive_dir / "archive.json")
    expected_paths.update(archive_dir / name for name in exclusions._EVIDENCE_FILES)
    expected_paths.update(
        market_dir / name
        for name in ("revision.json", "journal.json", "plan.json", "receipt.json")
    )
    expected_paths.update(Path(source["path"]).resolve() for source in market_plan["sources"])

    reads: dict[Path, list[bytes]] = {}
    parsed: dict[Path, list[bytes]] = {}
    original_read_bytes = Path.read_bytes
    original_json_from_bytes = exclusions._json_from_bytes
    original_marker_paths = exclusions._marker_paths
    marker_path_calls = 0

    def record_read(path: Path) -> bytes:
        payload = original_read_bytes(path)
        if path in expected_paths:
            reads.setdefault(path, []).append(payload)
        return payload

    def record_parse(payload: bytes, path: Path) -> dict[str, object]:
        if path in expected_paths:
            parsed.setdefault(path, []).append(payload)
        return original_json_from_bytes(payload, path)

    def record_marker_paths(path: Path):
        nonlocal marker_path_calls
        marker_path_calls += 1
        return original_marker_paths(path)

    monkeypatch.setattr(Path, "read_bytes", record_read)
    monkeypatch.setattr(exclusions, "_json_from_bytes", record_parse)
    monkeypatch.setattr(exclusions, "_marker_paths", record_marker_paths)
    namespace = collector(database_path, date(2016, 1, 1))

    assert namespace.presence is SourceEvidencePresenceV1.PRESENT
    assert marker_path_calls == 1
    assert set(reads) == expected_paths
    assert all(len(payloads) == 1 for payloads in reads.values())
    assert set(parsed) == expected_paths
    assert all(len(payloads) == 1 for payloads in parsed.values())
    assert all(reads[path][0] == parsed[path][0] for path in expected_paths)
    assert len(namespace.files) == len(expected_paths)
    assert marker["state"] == "applied"

    prefix = "run_" + base64.urlsafe_b64encode(b"typed-single-read").decode("ascii").rstrip("=")
    roles_by_path = {
        run_dir / "revision.json": f"{prefix}/revision.json",
        run_dir / "plan.json": f"{prefix}/plan.json",
        run_dir / "journal.json": f"{prefix}/journal.json",
        run_dir / "receipt.json": f"{prefix}/receipt.json",
        archive_dir / "archive.json": f"{prefix}/archive/archive.json",
        market_dir / "revision.json": f"{prefix}/market/revision.json",
        market_dir / "journal.json": f"{prefix}/market/journal.json",
        market_dir / "plan.json": f"{prefix}/market/plan.json",
        market_dir / "receipt.json": f"{prefix}/market/receipt.json",
    }
    roles_by_path.update(
        {
            archive_dir / name: f"{prefix}/archive/files/{name}"
            for name in exclusions._EVIDENCE_FILES
        }
    )
    roles_by_path.update(
        {
            Path(source["path"]).resolve(): (
                f"{prefix}/market/sources/source-{index:06d}.json"
            )
            for index, source in enumerate(market_plan["sources"])
        }
    )
    assert set(roles_by_path) == expected_paths
    expected_hashes = {
        role: _sha256(reads[path][0]) for path, role in roles_by_path.items()
    }
    actual_hashes = {item.role_id: item.sha256 for item in namespace.files}
    assert actual_hashes == expected_hashes
