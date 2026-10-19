"""語義證明範圍的完整來源讀回與拒絕失配回歸。"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import Any

import pytest

from app_module import daily_market_technical_snapshot_v4_repository as repository_module
from app_module.daily_market_technical_snapshot_v4_repository import (
    DAILY_MARKET_TECHNICAL_PROOF_SCOPE_MAX_BATCHES,
    DailyMarketTechnicalSnapshotProofScope,
    DailyMarketTechnicalSnapshotV4Repository,
    DailyMarketTechnicalSnapshotV4RepositoryError,
    canonical_v4_json_bytes,
)


from tests.test_daily_market_technical_snapshot_v4_repository import (
    _make_run,
    _read_bytes,
    _unlink,
    _write_bytes,
)


def _read_pinned(
    repository: DailyMarketTechnicalSnapshotV4Repository,
    produced: Any,
    **pin_overrides: object,
) -> Any:
    pins: dict[str, object] = {
        "expected_manifest_sha256": produced.manifest_sha256,
        "expected_cohort_identity_sha256": produced.cohort_identity_sha256,
        "expected_source_clock_sha256": produced.source_clock_identity_sha256,
        "expected_method_contract_sha256": produced.method_contract_sha256,
        "expected_decision_date": produced.decision_date,
    }
    pins.update(pin_overrides)
    return repository.read_exact(produced.manifest_path, **pins)


def _artifact_path(produced: Any, ref: Any) -> Path:
    return produced.manifest_path.parent.joinpath(*Path(ref.relative_path).parts)


def _named_run(tmp_path: Path, name: str) -> tuple[Path, Any]:
    case_root = tmp_path / name
    case_root.mkdir()
    return _make_run(case_root, stock_count=1)


def test_scope_cold_and_warm_reads_rebuild_dtos_and_freshly_read_every_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, produced = _make_run(tmp_path, stock_count=16)
    repository = DailyMarketTechnicalSnapshotV4Repository(output_root)
    scope = DailyMarketTechnicalSnapshotProofScope()

    strict_decode_calls = 0
    scope_decode_calls = 0
    bounded_reads: Counter[Path] = Counter()
    validator_calls: list[tuple[object, str, str]] = []
    original_strict_decoder = repository_module._decode_and_validate_snapshot
    original_scope_decoder = repository_module._rehydrate_snapshot_from_reader_issued_bytes
    original_bounded_reader = repository_module._read_bounded_file
    original_binding_validator = repository_module.validate_daily_market_technical_calculation_binding

    def count_strict_decode(*args: Any, **kwargs: Any) -> Any:
        nonlocal strict_decode_calls
        strict_decode_calls += 1
        return original_strict_decoder(*args, **kwargs)

    def count_scope_decode(raw: bytes) -> Any:
        nonlocal scope_decode_calls
        scope_decode_calls += 1
        return original_scope_decoder(raw)

    def count_bounded_read(path: Path, limit: int) -> bytes:
        bounded_reads[path.resolve()] += 1
        return original_bounded_reader(path, limit)

    def count_binding_validation(
        payload: object,
        *,
        expected_identity: str,
        expected_talib_version: str,
    ) -> None:
        validator_calls.append((payload, expected_identity, expected_talib_version))
        original_binding_validator(
            payload,
            expected_identity=expected_identity,
            expected_talib_version=expected_talib_version,
        )

    monkeypatch.setattr(repository_module, "_decode_and_validate_snapshot", count_strict_decode)
    monkeypatch.setattr(
        repository_module,
        "_rehydrate_snapshot_from_reader_issued_bytes",
        count_scope_decode,
    )
    monkeypatch.setattr(repository_module, "_read_bounded_file", count_bounded_read)
    monkeypatch.setattr(
        repository_module,
        "validate_daily_market_technical_calculation_binding",
        count_binding_validation,
    )

    expected_read_paths = {
        produced.manifest_path.resolve(),
        *(_artifact_path(produced, ref).resolve() for ref in produced.artifact_refs),
    }
    expected_read_counts = Counter({path: 1 for path in expected_read_paths})

    with scope.activate():
        cold = _read_pinned(repository, produced)
    assert strict_decode_calls == len(produced.artifact_refs)
    assert scope_decode_calls == 0
    assert bounded_reads == expected_read_counts

    bounded_reads.clear()
    strict_decode_calls = 0
    validator_calls.clear()
    with scope.activate():
        warm = _read_pinned(repository, produced)

    assert strict_decode_calls == 0
    assert scope_decode_calls == len(produced.artifact_refs)
    assert bounded_reads == expected_read_counts
    assert warm is not cold
    assert warm.generation_identity_sha256 == cold.generation_identity_sha256
    assert len(warm.snapshots) == len(cold.snapshots)
    for old_snapshot, fresh_snapshot in zip(cold.snapshots, warm.snapshots, strict=True):
        assert fresh_snapshot is not old_snapshot
        assert fresh_snapshot == old_snapshot
        assert fresh_snapshot.stock_code == old_snapshot.stock_code
        assert fresh_snapshot.snapshot_identity_sha256 == old_snapshot.snapshot_identity_sha256
        assert fresh_snapshot.calculation_binding_json == old_snapshot.calculation_binding_json

    expected_bindings = {
        (
            snapshot.calculation_binding_json,
            snapshot.calculation_identity_sha256,
            snapshot.talib_version,
        )
        for snapshot in cold.snapshots
    }
    actual_bindings = {
        (
            canonical_v4_json_bytes(payload).decode("utf-8"),
            expected_identity,
            expected_talib_version,
        )
        for payload, expected_identity, expected_talib_version in validator_calls
    }
    assert actual_bindings == expected_bindings
    assert len(validator_calls) == len(expected_bindings)


def test_scope_warm_read_fails_closed_for_raw_manifest_pins_and_layout_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, produced = _make_run(tmp_path, stock_count=2)
    repository = DailyMarketTechnicalSnapshotV4Repository(output_root)
    scope = DailyMarketTechnicalSnapshotProofScope()
    with scope.activate():
        _read_pinned(repository, produced)

    def must_not_fall_back_to_full_decoder(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("matching Scope proof unexpectedly fell back to the cold full decoder")

    monkeypatch.setattr(
        repository_module,
        "_decode_and_validate_snapshot",
        must_not_fall_back_to_full_decoder,
    )
    sibling_path = _artifact_path(produced, produced.artifact_refs[-1])
    sibling_original = _read_bytes(sibling_path)
    changed = bytearray(sibling_original)
    changed[-1] ^= 1
    try:
        _write_bytes(sibling_path, bytes(changed))
        with scope.activate():
            with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as raw_error:
                _read_pinned(repository, produced)
        assert raw_error.value.code == "technical_snapshot_v4_artifact_sha_mismatch"
    finally:
        _write_bytes(sibling_path, sibling_original)

    try:
        _unlink(sibling_path)
        with scope.activate():
            with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError):
                _read_pinned(repository, produced)
    finally:
        _write_bytes(sibling_path, sibling_original)

    extra_path = produced.manifest_path.parent / "unexpected.json"
    try:
        _write_bytes(extra_path, b"{}")
        with scope.activate():
            with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as layout_error:
                _read_pinned(repository, produced)
        assert layout_error.value.code == "technical_snapshot_v4_attempt_layout_invalid"
    finally:
        if extra_path.exists():
            _unlink(extra_path)

    manifest_original = _read_bytes(produced.manifest_path)
    try:
        _write_bytes(produced.manifest_path, manifest_original + b" ")
        with scope.activate():
            with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as manifest_error:
                _read_pinned(repository, produced)
        assert manifest_error.value.code == "technical_snapshot_v4_manifest_sha_mismatch"
    finally:
        _write_bytes(produced.manifest_path, manifest_original)

    with scope.activate():
        with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as changed_pin_error:
            _read_pinned(repository, produced, expected_source_clock_sha256="0" * 64)
    assert changed_pin_error.value.code == "technical_snapshot_v4_source_clock_identity_mismatch"


def test_scope_proofs_are_bound_to_repository_and_activation_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_a, produced_a = _named_run(tmp_path, "run-a")
    output_b, produced_b = _named_run(tmp_path, "run-b")
    repository_a = DailyMarketTechnicalSnapshotV4Repository(output_a)
    repository_b = DailyMarketTechnicalSnapshotV4Repository(output_b)
    scope_a = DailyMarketTechnicalSnapshotProofScope()
    scope_b = DailyMarketTechnicalSnapshotProofScope()

    strict_decode_calls = 0
    original_decoder = repository_module._decode_and_validate_snapshot

    def count_decode(*args: Any, **kwargs: Any) -> Any:
        nonlocal strict_decode_calls
        strict_decode_calls += 1
        return original_decoder(*args, **kwargs)

    monkeypatch.setattr(repository_module, "_decode_and_validate_snapshot", count_decode)

    with scope_a.activate():
        _read_pinned(repository_a, produced_a)
        _read_pinned(repository_a, produced_a)
        assert strict_decode_calls == 1

        # 同一 Scope 的另一 repository 必須 cold-read，不能以同 SHA/名稱跨 root 命中。
        _read_pinned(repository_b, produced_b)
        assert strict_decode_calls == 2
        _read_pinned(repository_b, produced_b)
        assert strict_decode_calls == 2

        with scope_b.activate():
            _read_pinned(repository_a, produced_a)
            assert strict_decode_calls == 3
        _read_pinned(repository_a, produced_a)
        assert strict_decode_calls == 3

        with pytest.raises(RuntimeError, match="scope reset probe"):
            with scope_a.activate():
                _read_pinned(repository_a, produced_a)
                raise RuntimeError("scope reset probe")

    # activate() 的例外退出須還原 ContextVar；沒有作用中的 Scope 就走原 strict decoder。
    _read_pinned(repository_a, produced_a)
    assert strict_decode_calls == 4


def test_scope_rejects_forged_and_modified_cached_proofs(
    tmp_path: Path,
) -> None:
    output_root, produced = _make_run(tmp_path, stock_count=1)
    repository = DailyMarketTechnicalSnapshotV4Repository(output_root)
    scope = DailyMarketTechnicalSnapshotProofScope()
    with scope.activate():
        _read_pinned(repository, produced)

    key = next(iter(scope._proofs))
    issued_proof = scope._proofs[key]
    scope._proofs[key] = dataclass_replace(issued_proof)
    with scope.activate():
        with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as forged_error:
            _read_pinned(repository, produced)
    assert forged_error.value.code == "technical_snapshot_v4_semantic_proof_not_reader_issued"

    scope._proofs[key] = issued_proof
    object.__setattr__(issued_proof, "identity_sha256", "0" * 64)
    with scope.activate():
        with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as changed_error:
            _read_pinned(repository, produced)
    assert changed_error.value.code == "technical_snapshot_v4_semantic_proof_invalid"


def test_scope_lru_is_bounded_and_evicts_the_least_recent_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert DAILY_MARKET_TECHNICAL_PROOF_SCOPE_MAX_BATCHES == 128
    monkeypatch.setattr(repository_module, "DAILY_MARKET_TECHNICAL_PROOF_SCOPE_MAX_BATCHES", 2)
    runs = [_named_run(tmp_path, name) for name in ("run-a", "run-b", "run-c")]
    repositories = [DailyMarketTechnicalSnapshotV4Repository(root) for root, _ in runs]
    produced = [artifact for _, artifact in runs]
    scope = DailyMarketTechnicalSnapshotProofScope()
    strict_decode_calls = 0
    original_decoder = repository_module._decode_and_validate_snapshot

    def count_decode(*args: Any, **kwargs: Any) -> Any:
        nonlocal strict_decode_calls
        strict_decode_calls += 1
        return original_decoder(*args, **kwargs)

    monkeypatch.setattr(repository_module, "_decode_and_validate_snapshot", count_decode)

    with scope.activate():
        for repository, artifact in zip(repositories, produced, strict=True):
            _read_pinned(repository, artifact)
        assert strict_decode_calls == 3
        assert len(scope._proofs) == 2

        # A 最舊，應已被 C 插入時逐出；C 則仍是最近使用項目。
        _read_pinned(repositories[0], produced[0])
        assert strict_decode_calls == 4
        _read_pinned(repositories[2], produced[2])
        assert strict_decode_calls == 4
