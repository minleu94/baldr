"""驗證 v4 repository 的 fresh-process readback 與 fail-closed 行為。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from dataclasses import replace as dataclass_replace
import gc
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any
import weakref
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_snapshot_repository import (
    DailyMarketSnapshotRepository,
    DailyMarketSnapshotVerificationError,
)
from app_module.daily_market_technical_read_session import DailyMarketTechnicalReadSession
from app_module.daily_market_technical_snapshot_v4_producer import (
    write_daily_market_technical_snapshot_v4_batch,
)
from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
)
from app_module import daily_market_technical_snapshot_v4_repository as repository_module
from app_module.daily_market_technical_snapshot_v4_repository import (
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_BATCH_MANIFEST_SCHEMA,
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_STORE_DIRECTORY,
    DailyMarketTechnicalSnapshotV4Repository,
    DailyMarketTechnicalSnapshotV4RepositoryError,
    canonical_v4_json_bytes,
    sha256_bytes,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope


_TAIPEI = ZoneInfo("Asia/Taipei")
_START_DATE = date(2026, 7, 1)


def _make_source(path: Path, stock_codes: tuple[str, ...]) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows: list[tuple[str, str, str, str, str, str, int]] = []
            for stock_code in stock_codes:
                for offset in range(40):
                    close = 100 + offset
                    rows.append((
                        (_START_DATE + timedelta(days=offset)).isoformat(),
                        stock_code,
                        str(close),
                        str(close + 1),
                        str(close - 1),
                        str(close),
                        1000 + offset,
                    ))
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                rows,
            )
    finally:
        connection.close()


def _cohort(codes: tuple[str, ...]) -> dict[str, object]:
    core: dict[str, object] = {
        "schema_version": "daily-market-technical-cohort.v4",
        "universe_id": "repository-test",
        "population_version": "population.v1",
        "decision_date": (_START_DATE + timedelta(days=39)).isoformat(),
        "included_stock_codes": list(codes),
        "excluded_stock_codes": [],
        "exclusion_reasons": {},
        "declared_count": len(codes),
    }
    return {**core, "cohort_identity_sha256": sha256_bytes(canonical_v4_json_bytes(core))}


def _make_run(tmp_path: Path, stock_count: int = 16) -> tuple[Path, Any]:
    source_root = tmp_path / "source"
    output_root = tmp_path / "output"
    source_root.mkdir()
    output_root.mkdir()
    codes = tuple(f"R{index:04d}" for index in range(stock_count))
    database = source_root / "prices.sqlite"
    _make_source(database, codes)
    cutoff = datetime.combine(
        _START_DATE + timedelta(days=39),
        time(16, 0),
        tzinfo=_TAIPEI,
    )
    with DailyMarketTechnicalReadSession(database, cutoff) as session:
        clock = session.clock
        for start in range(0, len(codes), 16):
            session.load_batch(codes[start : start + 16])
        windows = session.finish()
    scope = ResearchCaptureWriteScope(output_root, database)
    batch_root = scope.root / "run"
    artifact = write_daily_market_technical_snapshot_v4_batch(
        output_root=batch_root,
        cohort=_cohort(codes),
        source_clock=clock,
        finished_windows=windows,
        research_scope=scope,
    ).artifact
    assert artifact is not None
    return batch_root, artifact


def _read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(_read_bytes(path).decode("utf-8"))


def _read_bytes(path: Path) -> bytes:
    with open(to_internal_io_path(path), "rb") as handle:
        return handle.read()


def _write_bytes(path: Path, raw: bytes) -> None:
    with open(to_internal_io_path(path), "wb") as handle:
        handle.write(raw)


def _mkdir(path: Path) -> None:
    os.makedirs(to_internal_io_path(path), exist_ok=False)


def _unlink(path: Path) -> None:
    os.unlink(to_internal_io_path(path))


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    _write_bytes(path, canonical_v4_json_bytes(payload))


def test_fresh_process_reads_exact_sixteen_stock_generation(tmp_path: Path) -> None:
    output_root, artifact = _make_run(tmp_path, stock_count=16)
    code = (
        "import sys; "
        "from app_module.daily_market_technical_snapshot_v4_repository import "
        "DailyMarketTechnicalSnapshotV4Repository; "
        "result=DailyMarketTechnicalSnapshotV4Repository(sys.argv[1]).read_exact("
        "sys.argv[2], expected_manifest_sha256=sys.argv[3]); "
        "print(result.generation_identity_sha256+'|'+str(len(result.snapshots)))"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(output_root),
            str(artifact.manifest_path),
            artifact.manifest_sha256,
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{artifact.generation_identity_sha256}|16"


def test_verified_batch_proof_survives_batch_gc_and_freshly_checks_all_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, produced = _make_run(tmp_path, stock_count=16)
    repository = DailyMarketTechnicalSnapshotV4Repository(output_root)
    decode_calls = 0
    original_from_json = DailyMarketTechnicalFeatureSnapshotV4.from_json

    def count_from_json(
        cls: type[DailyMarketTechnicalFeatureSnapshotV4],
        raw: bytes | str,
    ) -> DailyMarketTechnicalFeatureSnapshotV4:
        nonlocal decode_calls
        decode_calls += 1
        return original_from_json(raw)

    with monkeypatch.context() as patch:
        patch.setattr(
            DailyMarketTechnicalFeatureSnapshotV4,
            "from_json",
            classmethod(count_from_json),
        )
        batch = repository.read_exact(produced.manifest_path)
        assert decode_calls == 16
        proof = repository_module._semantic_proof_for_verified_batch(batch)
        assert proof.payload_size_bytes > 0
        assert not hasattr(proof, "snapshots")

        replaced_batch = dataclass_replace(batch)
        with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as copied_batch:
            repository_module._semantic_proof_for_verified_batch(replaced_batch)
        assert copied_batch.value.code == "technical_snapshot_v4_semantic_proof_origin_mismatch"

        replaced_proof = dataclass_replace(proof)
        with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as copied_proof:
            repository.read_selected_exact(
                replaced_proof,
                selected_stock_codes=(produced.expected_stock_codes[0],),
            )
        assert copied_proof.value.code == "technical_snapshot_v4_semantic_proof_not_reader_issued"

        batch_ref = weakref.ref(batch)
        del replaced_batch
        del batch
        gc.collect()
        assert batch_ref() is None

        decode_calls = 0
        selected_codes = (produced.expected_stock_codes[7], produced.expected_stock_codes[2])
        selected = repository.read_selected_exact(
            proof,
            selected_stock_codes=selected_codes,
        )
        assert tuple(snapshot.stock_code for snapshot in selected) == selected_codes
        assert decode_calls == len(selected_codes)

        decode_calls = 0
        assert repository.read_selected_exact(proof, selected_stock_codes=()) == ()
        assert decode_calls == 0

    sibling_ref = next(
        ref for ref in proof.manifest.artifact_refs if ref.stock_code not in selected_codes
    )
    sibling_path = proof.manifest.manifest_path.parent.joinpath(
        *Path(sibling_ref.relative_path).parts
    )
    original_bytes = _read_bytes(sibling_path)
    original_stat = os.stat(to_internal_io_path(sibling_path))
    try:
        changed = bytes((original_bytes[0] ^ 1,)) + original_bytes[1:]
        _write_bytes(sibling_path, changed)
        os.utime(
            to_internal_io_path(sibling_path),
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
        with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as tampered:
            repository.read_selected_exact(
                proof,
                selected_stock_codes=(produced.expected_stock_codes[0],),
            )
        assert tampered.value.code == "technical_snapshot_v4_artifact_sha_mismatch"
    finally:
        _write_bytes(sibling_path, original_bytes)
        os.utime(
            to_internal_io_path(sibling_path),
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )

    original_bounded_read = repository_module._read_bounded_file
    cancelled = False

    def cancel_after_first_artifact(path: Path, max_bytes: int) -> bytes:
        nonlocal cancelled
        raw = original_bounded_read(path, max_bytes)
        if path.parent.name == "artifacts":
            cancelled = True
        return raw

    with monkeypatch.context() as patch:
        patch.setattr(repository_module, "_read_bounded_file", cancel_after_first_artifact)
        with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as interrupted:
            repository.read_selected_exact(
                proof,
                selected_stock_codes=(produced.expected_stock_codes[0],),
                cancel_callback=lambda: cancelled,
            )
    assert interrupted.value.code == "technical_snapshot_v4_read_cancelled"


def test_artifact_byte_tampering_and_missing_file_are_rejected(tmp_path: Path) -> None:
    output_root, artifact = _make_run(tmp_path)
    target = artifact.manifest_path.parent / artifact.artifact_refs[0].relative_path
    raw = _read_bytes(target)
    _write_bytes(target, raw + b" ")
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as tamper_error:
        DailyMarketTechnicalSnapshotV4Repository(output_root).read_exact(artifact.manifest_path)
    assert tamper_error.value.code in {
        "technical_snapshot_v4_artifact_size_mismatch",
        "technical_snapshot_v4_artifact_sha_mismatch",
    }

    _write_bytes(target, raw)
    _unlink(target)
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as missing_error:
        DailyMarketTechnicalSnapshotV4Repository(output_root).read_exact(artifact.manifest_path)
    assert missing_error.value.code == "technical_snapshot_v4_file_type_rejected"


def test_repository_rejects_hardlinked_artifact(tmp_path: Path) -> None:
    output_root, artifact = _make_run(tmp_path, stock_count=1)
    target = artifact.manifest_path.parent / artifact.artifact_refs[0].relative_path
    alias = target.with_name("unexpected-hardlink.json")
    try:
        os.link(to_internal_io_path(target), to_internal_io_path(alias))
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"此環境無法建立硬連結測試夾具：{exc}")

    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as error_info:
        DailyMarketTechnicalSnapshotV4Repository(output_root).read_exact(artifact.manifest_path)
    assert error_info.value.code == "technical_snapshot_v4_file_type_rejected"


def test_repository_rejects_symlinked_artifact(tmp_path: Path) -> None:
    output_root, artifact = _make_run(tmp_path, stock_count=1)
    target = artifact.manifest_path.parent / artifact.artifact_refs[0].relative_path
    alias = target.with_name("unexpected-symlink.json")
    try:
        os.symlink(target.name, to_internal_io_path(alias))
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"此環境無法建立符號連結測試夾具：{exc}")

    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as error_info:
        DailyMarketTechnicalSnapshotV4Repository(output_root).read_exact(artifact.manifest_path)
    assert error_info.value.code == "technical_snapshot_v4_link_rejected"


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    (
        ("writer_version", "daily-market-technical-snapshot-v4-writer.v999", "technical_snapshot_v4_writer_version_unsupported"),
        ("schema_version", "daily-market-technical-snapshot-batch-manifest.v3", "technical_snapshot_v4_manifest_schema_unsupported"),
        ("source_clock_identity_sha256", "0" * 64, "technical_snapshot_v4_source_clock_identity_mismatch"),
        ("cohort_identity_sha256", "0" * 64, "technical_snapshot_v4_cohort_identity_mismatch"),
        ("method_contract_sha256", "0" * 64, "technical_snapshot_v4_method_contract_unsupported"),
    ),
)
def test_manifest_version_cohort_clock_and_method_tampering_fail_closed(
    tmp_path: Path,
    field: str,
    value: str,
    expected_code: str,
) -> None:
    output_root, artifact = _make_run(tmp_path, stock_count=1)
    manifest = _read_manifest(artifact.manifest_path)
    manifest[field] = value
    _write_manifest(artifact.manifest_path, manifest)
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as error_info:
        DailyMarketTechnicalSnapshotV4Repository(output_root).read_exact(artifact.manifest_path)
    assert error_info.value.code == expected_code


def test_wrong_expected_source_or_decision_date_is_rejected(tmp_path: Path) -> None:
    output_root, artifact = _make_run(tmp_path, stock_count=1)
    repository = DailyMarketTechnicalSnapshotV4Repository(output_root)
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as source_error:
        repository.read_exact(artifact.manifest_path, expected_source_clock_sha256="0" * 64)
    assert source_error.value.code == "technical_snapshot_v4_source_clock_identity_mismatch"
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as date_error:
        repository.read_exact(
            artifact.manifest_path,
            expected_decision_date=artifact.decision_date - timedelta(days=1),
        )
    assert date_error.value.code == "technical_snapshot_v4_decision_date_mismatch"


def test_artifact_ref_cannot_escape_or_mix_a_stock(tmp_path: Path) -> None:
    output_root, artifact = _make_run(tmp_path, stock_count=2)
    manifest = _read_manifest(artifact.manifest_path)
    manifest["artifact_refs"][0]["relative_path"] = "artifacts/../other.json"
    _write_manifest(artifact.manifest_path, manifest)
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as path_error:
        DailyMarketTechnicalSnapshotV4Repository(output_root).read_exact(artifact.manifest_path)
    assert path_error.value.code == "technical_snapshot_v4_artifact_path_invalid"

    manifest = _read_manifest(artifact.manifest_path)
    manifest["artifact_refs"][0]["stock_code"] = artifact.expected_stock_codes[1]
    _write_manifest(artifact.manifest_path, manifest)
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as stock_error:
        DailyMarketTechnicalSnapshotV4Repository(output_root).read_exact(artifact.manifest_path)
    assert stock_error.value.code == "technical_snapshot_v4_artifact_refs_invalid"


def test_v4_repository_rejects_old_manifest_and_old_reader_rejects_v4(
    tmp_path: Path,
) -> None:
    output_root, artifact = _make_run(tmp_path, stock_count=1)
    generation_dir = (
        output_root
        / DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_STORE_DIRECTORY
        / "generations"
        / ("a" * 64)
        / "batches"
        / ("b" * 64)
        / "attempts"
        / ("c" * 32)
    )
    _mkdir(generation_dir)
    old_manifest = {
        "schema_version": "daily-market-snapshot-manifest.v2",
        "manifest_identity_sha256": "d" * 64,
    }
    old_path = generation_dir / "manifest.json"
    _write_bytes(old_path, canonical_v4_json_bytes(old_manifest))
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as new_reader_error:
        DailyMarketTechnicalSnapshotV4Repository(output_root).read_exact(old_path)
    assert new_reader_error.value.code == "technical_snapshot_v4_manifest_schema_unsupported"

    old_root = tmp_path / "old-reader"
    (old_root / "manifests").mkdir(parents=True)
    raw_v4 = _read_bytes(artifact.manifest_path)
    digest_v4 = hashlib.sha256(raw_v4).hexdigest()
    _write_bytes(old_root / "manifests" / f"{digest_v4}.json", raw_v4)
    with pytest.raises(DailyMarketSnapshotVerificationError):
        DailyMarketSnapshotRepository(old_root).load_manifest(
            digest_v4,
            "repository-test",
            artifact.decision_date,
        )


def test_reader_requires_exact_v4_manifest_schema(tmp_path: Path) -> None:
    output_root, artifact = _make_run(tmp_path, stock_count=1)
    manifest = _read_manifest(artifact.manifest_path)
    assert manifest["schema_version"] == DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_BATCH_MANIFEST_SCHEMA
    manifest["unexpected"] = True
    _write_manifest(artifact.manifest_path, manifest)
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as error_info:
        DailyMarketTechnicalSnapshotV4Repository(output_root).read_exact(artifact.manifest_path)
    assert error_info.value.code == "technical_snapshot_v4_manifest_fields_invalid"
