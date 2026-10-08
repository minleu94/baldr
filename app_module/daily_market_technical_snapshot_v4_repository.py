"""v4 技術快照批次的嚴格唯讀儲存契約。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import weakref
from typing import Any, NoReturn, cast

from app_module.daily_market_technical_feature_snapshot_v4 import (
    DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES,
    DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_SCHEMA_V4,
    DailyMarketTechnicalFeatureSnapshotV4,
)
from app_module.daily_market_technical_method_contract_v4 import (
    daily_market_technical_method_contract_v4_sha256,
)
from app_module.daily_market_technical_read_session import (
    DAILY_MARKET_TECHNICAL_READ_SESSION_BATCH_MAX_STOCKS,
    DailyMarketTechnicalSourceClockV4,
)
from app_module.personal_data_paths import to_internal_io_path


DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_BATCH_MANIFEST_SCHEMA = (
    "daily-market-technical-snapshot-batch-manifest.v4"
)
DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_WRITER_VERSION = (
    "daily-market-technical-snapshot-v4-writer.v1"
)
DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_STORE_DIRECTORY = (
    "daily_market_technical_v4"
)
DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_BATCH_ARTIFACT_BYTES = 4 * 1024 * 1024
DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_RETAINED_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_COHORT_CODES = 256
DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_FILES_PER_ATTEMPT = 64

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")
_COHORT_KEYS = frozenset({
    "schema_version",
    "universe_id",
    "population_version",
    "decision_date",
    "included_stock_codes",
    "excluded_stock_codes",
    "exclusion_reasons",
    "declared_count",
    "cohort_identity_sha256",
})
_COHORT_IDENTITY_KEYS = (
    "schema_version",
    "universe_id",
    "population_version",
    "decision_date",
    "included_stock_codes",
    "excluded_stock_codes",
    "exclusion_reasons",
    "declared_count",
)
_CLOCK_KEYS = frozenset({
    "database_path",
    "source_id",
    "schema_identity_sha256",
    "source_file_pin",
    "source_pin_sha256",
    "decision_date",
    "decision_cutoff",
    "cutoff_guard_version",
    "source_available_at",
    "availability_status",
    "historical_pit_eligible",
})
_MANIFEST_KEYS = frozenset({
    "schema_version",
    "writer_version",
    "generation_identity_sha256",
    "cohort",
    "cohort_identity_sha256",
    "source_clock",
    "source_clock_identity_sha256",
    "method_contract_sha256",
    "decision_date",
    "expected_stock_codes",
    "expected_stock_set_sha256",
    "artifact_refs",
})
_ARTIFACT_REF_KEYS = frozenset({
    "stock_code",
    "relative_path",
    "byte_size",
    "sha256",
    "snapshot_identity_sha256",
    "source_identity",
    "raw_source_window_fingerprint_sha256",
    "source_window_fingerprint_sha256",
    "calculation_identity_sha256",
})


class DailyMarketTechnicalSnapshotV4RepositoryError(ValueError):
    """v4 manifest、路徑或保存 artifact 不符合讀取契約。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalSnapshotV4ArtifactRef:
    """經 manifest 與 artifact bytes 共同驗證的逐股引用。"""

    stock_code: str
    relative_path: str
    byte_size: int
    sha256: str
    snapshot_identity_sha256: str
    source_identity: str
    raw_source_window_fingerprint_sha256: str
    source_window_fingerprint_sha256: str
    calculation_identity_sha256: str


@dataclass(frozen=True, slots=True)
class _ValidatedSnapshotBatchManifestV4:
    """一次完整 manifest 語義核驗後的精簡、不可變 metadata。"""

    repository_output_root: Path
    manifest_path: Path
    manifest_sha256: str
    generation_identity_sha256: str
    cohort_identity_sha256: str
    source_clock_identity_sha256: str
    method_contract_sha256: str
    decision_date: date
    universe_id: str
    population_version: str
    included_stock_codes: tuple[str, ...]
    excluded_stock_codes: tuple[str, ...]
    exclusion_reasons: tuple[tuple[str, str], ...]
    expected_stock_codes: tuple[str, ...]
    expected_stock_set_sha256: str
    artifact_refs: tuple[DailyMarketTechnicalSnapshotV4ArtifactRef, ...]
    source_clock: DailyMarketTechnicalSourceClockV4
    writer_version: str


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class _VerifiedBatchSemanticProofV4:
    """repository 發行的全 batch 語義證明；不保留任何 snapshot。"""

    manifest: _ValidatedSnapshotBatchManifestV4
    identity_sha256: str
    payload_size_bytes: int
    _origin_ref: weakref.ReferenceType[DailyMarketTechnicalBatchArtifactV4] = field(
        repr=False, compare=False
    )
    _seal: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True, weakref_slot=True)
class DailyMarketTechnicalBatchArtifactV4:
    """由 ``read_exact`` 驗證完成的不可變子批次保存結果。"""

    repository_output_root: Path
    manifest_path: Path
    manifest_sha256: str
    generation_identity_sha256: str
    cohort_identity_sha256: str
    source_clock_identity_sha256: str
    method_contract_sha256: str
    decision_date: date
    universe_id: str
    population_version: str
    included_stock_codes: tuple[str, ...]
    excluded_stock_codes: tuple[str, ...]
    exclusion_reasons: tuple[tuple[str, str], ...]
    expected_stock_codes: tuple[str, ...]
    expected_stock_set_sha256: str
    artifact_refs: tuple[DailyMarketTechnicalSnapshotV4ArtifactRef, ...]
    snapshots: tuple[DailyMarketTechnicalFeatureSnapshotV4, ...]
    source_clock: DailyMarketTechnicalSourceClockV4
    writer_version: str


_SEMANTIC_PROOF_SEAL = object()
_ISSUED_SEMANTIC_PROOFS: weakref.WeakSet[_VerifiedBatchSemanticProofV4] = weakref.WeakSet()
_ISSUED_BATCH_PROOFS: dict[
    int,
    tuple[
        weakref.ReferenceType[DailyMarketTechnicalBatchArtifactV4],
        _VerifiedBatchSemanticProofV4,
    ],
] = {}


def canonical_v4_json_bytes(value: Any) -> bytes:
    """編碼不含換行的 canonical UTF-8 JSON。"""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_json_invalid", str(exc)
        ) from exc


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _artifact_ref_payload(ref: DailyMarketTechnicalSnapshotV4ArtifactRef) -> dict[str, object]:
    return {
        "stock_code": ref.stock_code,
        "relative_path": ref.relative_path,
        "byte_size": ref.byte_size,
        "sha256": ref.sha256,
        "snapshot_identity_sha256": ref.snapshot_identity_sha256,
        "source_identity": ref.source_identity,
        "raw_source_window_fingerprint_sha256": ref.raw_source_window_fingerprint_sha256,
        "source_window_fingerprint_sha256": ref.source_window_fingerprint_sha256,
        "calculation_identity_sha256": ref.calculation_identity_sha256,
    }


def _validated_manifest_proof_payload(
    manifest: _ValidatedSnapshotBatchManifestV4,
) -> dict[str, object]:
    return {
        "schema": "daily-market-technical-snapshot-v4-semantic-proof.v1",
        "repository_output_root": str(manifest.repository_output_root),
        "manifest_path": str(manifest.manifest_path),
        "manifest_sha256": manifest.manifest_sha256,
        "generation_identity_sha256": manifest.generation_identity_sha256,
        "cohort_identity_sha256": manifest.cohort_identity_sha256,
        "source_clock_identity_sha256": manifest.source_clock_identity_sha256,
        "method_contract_sha256": manifest.method_contract_sha256,
        "decision_date": manifest.decision_date.isoformat(),
        "universe_id": manifest.universe_id,
        "population_version": manifest.population_version,
        "included_stock_codes": list(manifest.included_stock_codes),
        "excluded_stock_codes": list(manifest.excluded_stock_codes),
        "exclusion_reasons": [list(item) for item in manifest.exclusion_reasons],
        "expected_stock_codes": list(manifest.expected_stock_codes),
        "expected_stock_set_sha256": manifest.expected_stock_set_sha256,
        "artifact_refs": [_artifact_ref_payload(ref) for ref in manifest.artifact_refs],
        "source_clock": manifest.source_clock.to_dict(),
        "writer_version": manifest.writer_version,
    }


def _batch_matches_validated_manifest(
    batch: DailyMarketTechnicalBatchArtifactV4,
    manifest: _ValidatedSnapshotBatchManifestV4,
) -> bool:
    return (
        batch.repository_output_root == manifest.repository_output_root
        and batch.manifest_path == manifest.manifest_path
        and batch.manifest_sha256 == manifest.manifest_sha256
        and batch.generation_identity_sha256 == manifest.generation_identity_sha256
        and batch.cohort_identity_sha256 == manifest.cohort_identity_sha256
        and batch.source_clock_identity_sha256 == manifest.source_clock_identity_sha256
        and batch.method_contract_sha256 == manifest.method_contract_sha256
        and batch.decision_date == manifest.decision_date
        and batch.universe_id == manifest.universe_id
        and batch.population_version == manifest.population_version
        and batch.included_stock_codes == manifest.included_stock_codes
        and batch.excluded_stock_codes == manifest.excluded_stock_codes
        and batch.exclusion_reasons == manifest.exclusion_reasons
        and batch.expected_stock_codes == manifest.expected_stock_codes
        and batch.expected_stock_set_sha256 == manifest.expected_stock_set_sha256
        and batch.artifact_refs == manifest.artifact_refs
        and batch.source_clock == manifest.source_clock
        and batch.writer_version == manifest.writer_version
        and tuple(snapshot.stock_code for snapshot in batch.snapshots)
        == manifest.expected_stock_codes
        and len(batch.snapshots) == len(manifest.artifact_refs)
    )


def _verify_issued_semantic_proof(
    proof: object,
    *,
    require_live_origin: bool,
) -> _VerifiedBatchSemanticProofV4:
    if (
        type(proof) is not _VerifiedBatchSemanticProofV4
        or proof not in _ISSUED_SEMANTIC_PROOFS
        or proof._seal is not _SEMANTIC_PROOF_SEAL
    ):
        _fail("technical_snapshot_v4_semantic_proof_not_reader_issued")
    payload = canonical_v4_json_bytes(_validated_manifest_proof_payload(proof.manifest))
    if (
        sha256_bytes(payload) != proof.identity_sha256
        or len(payload) != proof.payload_size_bytes
    ):
        _fail("technical_snapshot_v4_semantic_proof_invalid")
    if require_live_origin:
        origin = proof._origin_ref()
        registration = None if origin is None else _ISSUED_BATCH_PROOFS.get(id(origin))
        if (
            origin is None
            or registration is None
            or registration[0]() is not origin
            or registration[1] is not proof
            or not _batch_matches_validated_manifest(origin, proof.manifest)
        ):
            _fail("technical_snapshot_v4_semantic_proof_origin_mismatch")
    return proof


def _semantic_proof_for_verified_batch(
    batch: DailyMarketTechnicalBatchArtifactV4,
) -> _VerifiedBatchSemanticProofV4:
    """僅從仍存活的原始 repository 結果取出同一批的語義證明。"""

    if type(batch) is not DailyMarketTechnicalBatchArtifactV4:
        _fail("technical_snapshot_v4_semantic_proof_origin_mismatch")
    registration = _ISSUED_BATCH_PROOFS.get(id(batch))
    if registration is None or registration[0]() is not batch:
        _fail("technical_snapshot_v4_semantic_proof_origin_mismatch")
    proof = _verify_issued_semantic_proof(registration[1], require_live_origin=True)
    if proof._origin_ref() is not batch:
        _fail("technical_snapshot_v4_semantic_proof_origin_mismatch")
    return proof


def _issue_semantic_proof(
    batch: DailyMarketTechnicalBatchArtifactV4,
    manifest: _ValidatedSnapshotBatchManifestV4,
) -> _VerifiedBatchSemanticProofV4:
    payload = canonical_v4_json_bytes(_validated_manifest_proof_payload(manifest))
    batch_identity = id(batch)

    def discard_batch_registration(
        origin_ref: weakref.ReferenceType[DailyMarketTechnicalBatchArtifactV4],
    ) -> None:
        current = _ISSUED_BATCH_PROOFS.get(batch_identity)
        if current is not None and current[0] is origin_ref:
            _ISSUED_BATCH_PROOFS.pop(batch_identity, None)

    origin_ref = weakref.ref(batch, discard_batch_registration)
    proof = _VerifiedBatchSemanticProofV4(
        manifest=manifest,
        identity_sha256=sha256_bytes(payload),
        payload_size_bytes=len(payload),
        _origin_ref=origin_ref,
        _seal=_SEMANTIC_PROOF_SEAL,
    )
    _ISSUED_SEMANTIC_PROOFS.add(proof)
    _ISSUED_BATCH_PROOFS[batch_identity] = (origin_ref, proof)
    return proof


def _is_cancelled(cancel_callback: Callable[[], bool] | None) -> bool:
    if cancel_callback is None:
        return False
    try:
        cancelled = cancel_callback()
    except Exception as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_cancel_check_failed", str(exc)
        ) from exc
    if type(cancelled) is not bool:
        _fail("technical_snapshot_v4_cancel_callback_invalid")
    return cancelled


def _check_cancelled(cancel_callback: Callable[[], bool] | None) -> None:
    if _is_cancelled(cancel_callback):
        _fail("technical_snapshot_v4_read_cancelled")


def generation_identity_sha256(
    *,
    cohort_identity_sha256: str,
    source_clock_identity_sha256: str,
    method_contract_sha256: str,
) -> str:
    """計算固定 cohort、來源時計與技術方法的 generation identity。"""

    for value in (
        cohort_identity_sha256,
        source_clock_identity_sha256,
        method_contract_sha256,
    ):
        _require_sha(value, "technical_snapshot_v4_identity_invalid")
    return sha256_bytes(canonical_v4_json_bytes({
        "schema_version": "daily-market-technical-snapshot-v4-generation-identity.v1",
        "cohort_identity_sha256": cohort_identity_sha256,
        "source_clock_identity_sha256": source_clock_identity_sha256,
        "method_contract_sha256": method_contract_sha256,
    }))


def expected_stock_set_sha256(stock_codes: Sequence[str]) -> str:
    """雜湊已排序且無重複的逐批股票清單。"""

    codes = tuple(stock_codes)
    if codes != tuple(sorted(set(codes))):
        _fail("technical_snapshot_v4_expected_stock_set_invalid")
    for code in codes:
        _validate_stock_code(code)
    return sha256_bytes(canonical_v4_json_bytes(list(codes)))


class DailyMarketTechnicalSnapshotV4Repository:
    """只讀載入 v4 批次；必須指定精確 manifest，沒有 latest 選擇。"""

    def __init__(self, output_root: str | Path) -> None:
        self.output_root = _canonical_directory(output_root, must_exist=True)
        self.store_root = self.output_root / DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_STORE_DIRECTORY

    def _read_validated_manifest(
        self,
        manifest_path: str | Path,
        *,
        expected_manifest_sha256: str | None = None,
        expected_cohort_identity_sha256: str | None = None,
        expected_source_clock_sha256: str | None = None,
        expected_method_contract_sha256: str | None = None,
        expected_decision_date: date | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> _ValidatedSnapshotBatchManifestV4:
        """重新讀取並完整驗證 manifest metadata，不解析 snapshot 內容。"""

        _check_cancelled(cancel_callback)
        path = _canonical_file(manifest_path)
        if path.name != "manifest.json":
            _fail("technical_snapshot_v4_manifest_path_invalid")
        if not path.is_relative_to(self.store_root):
            _fail("technical_snapshot_v4_manifest_outside_repository")
        _validate_manifest_location(path, self.store_root)
        manifest_raw = _read_bounded_file(
            path, DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_MANIFEST_BYTES
        )
        _check_cancelled(cancel_callback)
        manifest_sha = sha256_bytes(manifest_raw)
        if expected_manifest_sha256 is not None:
            _require_sha(expected_manifest_sha256, "technical_snapshot_v4_expected_manifest_sha_invalid")
            if manifest_sha != expected_manifest_sha256:
                _fail("technical_snapshot_v4_manifest_sha_mismatch")
        manifest = _parse_canonical_object(manifest_raw, "technical_snapshot_v4_manifest_invalid")
        if manifest.get("schema_version") != DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_BATCH_MANIFEST_SCHEMA:
            _fail("technical_snapshot_v4_manifest_schema_unsupported")
        if manifest.get("writer_version") != DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_WRITER_VERSION:
            _fail("technical_snapshot_v4_writer_version_unsupported")
        if frozenset(manifest) != _MANIFEST_KEYS:
            _fail("technical_snapshot_v4_manifest_fields_invalid")

        cohort = _verified_cohort_payload(manifest.get("cohort"))
        cohort_sha = cast(str, cohort["cohort_identity_sha256"])
        if manifest.get("cohort_identity_sha256") != cohort_sha:
            _fail("technical_snapshot_v4_cohort_identity_mismatch")
        if expected_cohort_identity_sha256 is not None:
            _require_sha(expected_cohort_identity_sha256, "technical_snapshot_v4_expected_cohort_sha_invalid")
            if cohort_sha != expected_cohort_identity_sha256:
                _fail("technical_snapshot_v4_cohort_identity_mismatch")

        clock = _source_clock_from_payload(manifest.get("source_clock"))
        clock_sha = clock.identity_sha256
        if manifest.get("source_clock_identity_sha256") != clock_sha:
            _fail("technical_snapshot_v4_source_clock_identity_mismatch")
        if expected_source_clock_sha256 is not None:
            _require_sha(expected_source_clock_sha256, "technical_snapshot_v4_expected_clock_sha_invalid")
            if clock_sha != expected_source_clock_sha256:
                _fail("technical_snapshot_v4_source_clock_identity_mismatch")

        method_sha = _require_sha(
            manifest.get("method_contract_sha256"),
            "technical_snapshot_v4_method_contract_invalid",
        )
        current_method_sha = daily_market_technical_method_contract_v4_sha256()
        if method_sha != current_method_sha:
            _fail("technical_snapshot_v4_method_contract_unsupported")
        if expected_method_contract_sha256 is not None:
            _require_sha(expected_method_contract_sha256, "technical_snapshot_v4_expected_method_sha_invalid")
            if method_sha != expected_method_contract_sha256:
                _fail("technical_snapshot_v4_method_contract_mismatch")

        decision_date = _parse_iso_date(manifest.get("decision_date"))
        if decision_date != cast(date, cohort["decision_date"]) or decision_date != clock.decision_date:
            _fail("technical_snapshot_v4_decision_date_mismatch")
        if expected_decision_date is not None and decision_date != expected_decision_date:
            _fail("technical_snapshot_v4_decision_date_mismatch")
        generation_sha = generation_identity_sha256(
            cohort_identity_sha256=cohort_sha,
            source_clock_identity_sha256=clock_sha,
            method_contract_sha256=method_sha,
        )
        if manifest.get("generation_identity_sha256") != generation_sha:
            _fail("technical_snapshot_v4_generation_identity_mismatch")
        if path.parents[4].name != generation_sha:
            _fail("technical_snapshot_v4_generation_path_mismatch")

        expected_codes = _validate_code_list(
            manifest.get("expected_stock_codes"),
            minimum=1,
            maximum=DAILY_MARKET_TECHNICAL_READ_SESSION_BATCH_MAX_STOCKS,
            code="technical_snapshot_v4_expected_stock_set_invalid",
        )
        expected_set_sha = expected_stock_set_sha256(expected_codes)
        if manifest.get("expected_stock_set_sha256") != expected_set_sha:
            _fail("technical_snapshot_v4_expected_stock_set_hash_mismatch")
        included_codes = cast(tuple[str, ...], cohort["included_stock_codes"])
        if any(code not in included_codes for code in expected_codes):
            _fail("technical_snapshot_v4_expected_stock_outside_cohort")

        refs_raw = manifest.get("artifact_refs")
        if not isinstance(refs_raw, list) or len(refs_raw) != len(expected_codes):
            _fail("technical_snapshot_v4_artifact_refs_invalid")
        refs: list[DailyMarketTechnicalSnapshotV4ArtifactRef] = []
        for index, raw_ref in enumerate(refs_raw):
            _check_cancelled(cancel_callback)
            ref = _parse_artifact_ref(raw_ref)
            if ref.stock_code != expected_codes[index]:
                _fail("technical_snapshot_v4_artifact_refs_invalid")
            relative = _validate_artifact_relpath(ref.relative_path, ref.stock_code)
            artifact_path = path.parent.joinpath(*relative.parts)
            if not artifact_path.is_relative_to(path.parent):
                _fail("technical_snapshot_v4_artifact_path_invalid")
            refs.append(ref)

        _check_cancelled(cancel_callback)
        reasons = cast(dict[str, str], cohort["exclusion_reason_map"])
        return _ValidatedSnapshotBatchManifestV4(
            repository_output_root=self.output_root,
            manifest_path=path,
            manifest_sha256=manifest_sha,
            generation_identity_sha256=generation_sha,
            cohort_identity_sha256=cohort_sha,
            source_clock_identity_sha256=clock_sha,
            method_contract_sha256=method_sha,
            decision_date=decision_date,
            universe_id=cast(str, cohort["universe_id"]),
            population_version=cast(str, cohort["population_version"]),
            included_stock_codes=included_codes,
            excluded_stock_codes=cast(tuple[str, ...], cohort["excluded_stock_codes"]),
            exclusion_reasons=tuple(sorted(reasons.items())),
            expected_stock_codes=expected_codes,
            expected_stock_set_sha256=expected_set_sha,
            artifact_refs=tuple(refs),
            source_clock=clock,
            writer_version=DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_WRITER_VERSION,
        )

    def read_exact(
        self,
        manifest_path: str | Path,
        *,
        expected_manifest_sha256: str | None = None,
        expected_cohort_identity_sha256: str | None = None,
        expected_source_clock_sha256: str | None = None,
        expected_method_contract_sha256: str | None = None,
        expected_decision_date: date | None = None,
    ) -> DailyMarketTechnicalBatchArtifactV4:
        """讀取指定 manifest、核對全部引用並回傳已驗證的逐股 snapshot。"""

        manifest = self._read_validated_manifest(
            manifest_path,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_cohort_identity_sha256=expected_cohort_identity_sha256,
            expected_source_clock_sha256=expected_source_clock_sha256,
            expected_method_contract_sha256=expected_method_contract_sha256,
            expected_decision_date=expected_decision_date,
        )
        snapshots: list[DailyMarketTechnicalFeatureSnapshotV4] = []
        batch_root = manifest.manifest_path.parent
        for ref in manifest.artifact_refs:
            relative = _validate_artifact_relpath(ref.relative_path, ref.stock_code)
            artifact_path = batch_root.joinpath(*relative.parts)
            artifact_raw = _read_bounded_file(
                artifact_path, DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES
            )
            if len(artifact_raw) != ref.byte_size:
                _fail("technical_snapshot_v4_artifact_size_mismatch")
            if sha256_bytes(artifact_raw) != ref.sha256:
                _fail("technical_snapshot_v4_artifact_sha_mismatch")
            snapshot = _decode_and_validate_snapshot(artifact_raw, ref, manifest)
            snapshots.append(snapshot)

        _validate_attempt_layout(batch_root, manifest.expected_stock_codes)
        batch = DailyMarketTechnicalBatchArtifactV4(
            repository_output_root=manifest.repository_output_root,
            manifest_path=manifest.manifest_path,
            manifest_sha256=manifest.manifest_sha256,
            generation_identity_sha256=manifest.generation_identity_sha256,
            cohort_identity_sha256=manifest.cohort_identity_sha256,
            source_clock_identity_sha256=manifest.source_clock_identity_sha256,
            method_contract_sha256=manifest.method_contract_sha256,
            decision_date=manifest.decision_date,
            universe_id=manifest.universe_id,
            population_version=manifest.population_version,
            included_stock_codes=manifest.included_stock_codes,
            excluded_stock_codes=manifest.excluded_stock_codes,
            exclusion_reasons=manifest.exclusion_reasons,
            expected_stock_codes=manifest.expected_stock_codes,
            expected_stock_set_sha256=manifest.expected_stock_set_sha256,
            artifact_refs=manifest.artifact_refs,
            snapshots=tuple(snapshots),
            source_clock=manifest.source_clock,
            writer_version=manifest.writer_version,
        )
        _issue_semantic_proof(batch, manifest)
        return batch

    def read_selected_exact(
        self,
        proof: _VerifiedBatchSemanticProofV4,
        *,
        selected_stock_codes: Sequence[str],
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[DailyMarketTechnicalFeatureSnapshotV4, ...]:
        """fresh 核完整 batch bytes/layout，只重解碼明示選取的 snapshot。"""

        issued = _verify_issued_semantic_proof(proof, require_live_origin=False)
        pinned = issued.manifest
        if pinned.repository_output_root != self.output_root:
            _fail("technical_snapshot_v4_semantic_proof_repository_mismatch")
        codes = _normalize_selected_stock_codes(
            selected_stock_codes, cancel_callback=cancel_callback
        )
        allowed_codes = set(pinned.expected_stock_codes)
        if any(code not in allowed_codes for code in codes):
            _fail("technical_snapshot_v4_selected_stock_not_in_batch")
        current = self._read_validated_manifest(
            pinned.manifest_path,
            expected_manifest_sha256=pinned.manifest_sha256,
            expected_cohort_identity_sha256=pinned.cohort_identity_sha256,
            expected_source_clock_sha256=pinned.source_clock_identity_sha256,
            expected_method_contract_sha256=pinned.method_contract_sha256,
            expected_decision_date=pinned.decision_date,
            cancel_callback=cancel_callback,
        )
        if current != pinned:
            _fail("technical_snapshot_v4_semantic_proof_manifest_mismatch")

        selected_set = set(codes)
        selected_snapshots: dict[str, DailyMarketTechnicalFeatureSnapshotV4] = {}
        batch_root = current.manifest_path.parent
        for ref in current.artifact_refs:
            _check_cancelled(cancel_callback)
            relative = _validate_artifact_relpath(ref.relative_path, ref.stock_code)
            artifact_path = batch_root.joinpath(*relative.parts)
            if not artifact_path.is_relative_to(batch_root):
                _fail("technical_snapshot_v4_artifact_path_invalid")
            artifact_raw = _read_bounded_file(
                artifact_path, DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES
            )
            _check_cancelled(cancel_callback)
            if len(artifact_raw) != ref.byte_size:
                _fail("technical_snapshot_v4_artifact_size_mismatch")
            if sha256_bytes(artifact_raw) != ref.sha256:
                _fail("technical_snapshot_v4_artifact_sha_mismatch")
            if ref.stock_code not in selected_set:
                continue
            snapshot = _decode_and_validate_snapshot(artifact_raw, ref, current)
            _check_cancelled(cancel_callback)
            selected_snapshots[ref.stock_code] = snapshot

        _validate_attempt_layout(
            batch_root,
            current.expected_stock_codes,
            cancel_callback=cancel_callback,
        )
        _check_cancelled(cancel_callback)
        if set(selected_snapshots) != selected_set:
            _fail("technical_snapshot_v4_selected_stock_missing")
        return tuple(selected_snapshots[code] for code in codes)


def _validate_snapshot_binding(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    *,
    ref: DailyMarketTechnicalSnapshotV4ArtifactRef,
    clock: DailyMarketTechnicalSourceClockV4,
    clock_sha: str,
    method_sha: str,
    decision_date: date,
) -> None:
    if snapshot.stock_code != ref.stock_code:
        _fail("technical_snapshot_v4_artifact_stock_mismatch")
    if snapshot.decision_date != decision_date or snapshot.decision_cutoff != clock.decision_cutoff:
        _fail("technical_snapshot_v4_artifact_clock_mismatch")
    if snapshot.source_clock_sha256 != clock_sha or snapshot.source_clock != clock.to_dict():
        _fail("technical_snapshot_v4_artifact_clock_mismatch")
    if snapshot.method_contracts_sha256 != method_sha:
        _fail("technical_snapshot_v4_artifact_method_mismatch")
    if snapshot.source_id != clock.source_id:
        _fail("technical_snapshot_v4_artifact_source_mismatch")
    if (
        snapshot.schema_identity_sha256 != clock.schema_identity_sha256
        or snapshot.source_pin_sha256 != clock.source_pin_sha256
        or snapshot.source_identity != ref.source_identity
        or snapshot.raw_source_window_fingerprint_sha256
        != ref.raw_source_window_fingerprint_sha256
        or snapshot.source_window_fingerprint_sha256
        != ref.source_window_fingerprint_sha256
        or snapshot.calculation_identity_sha256 != ref.calculation_identity_sha256
        or snapshot.snapshot_identity_sha256 != ref.snapshot_identity_sha256
    ):
        _fail("technical_snapshot_v4_artifact_identity_mismatch")


def _decode_and_validate_snapshot(
    raw: bytes,
    ref: DailyMarketTechnicalSnapshotV4ArtifactRef,
    manifest: _ValidatedSnapshotBatchManifestV4,
) -> DailyMarketTechnicalFeatureSnapshotV4:
    try:
        snapshot = DailyMarketTechnicalFeatureSnapshotV4.from_json(raw)
    except (TypeError, ValueError) as exc:
        reason = str(exc)
        code = reason if reason.startswith("technical_snapshot_v4_") else (
            "technical_snapshot_v4_snapshot_invalid"
        )
        raise DailyMarketTechnicalSnapshotV4RepositoryError(code, reason) from exc
    _validate_snapshot_binding(
        snapshot,
        ref=ref,
        clock=manifest.source_clock,
        clock_sha=manifest.source_clock_identity_sha256,
        method_sha=manifest.method_contract_sha256,
        decision_date=manifest.decision_date,
    )
    return snapshot


def _normalize_selected_stock_codes(
    value: Sequence[str],
    *,
    cancel_callback: Callable[[], bool] | None,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail("technical_snapshot_v4_selected_stock_codes_invalid")
    codes: list[str] = []
    seen: set[str] = set()
    try:
        for code in value:
            _check_cancelled(cancel_callback)
            if len(codes) >= DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_COHORT_CODES:
                _fail("technical_snapshot_v4_selected_stock_code_limit")
            if not isinstance(code, str):
                _fail("technical_snapshot_v4_selected_stock_codes_invalid")
            _validate_stock_code(code)
            if code in seen:
                _fail("technical_snapshot_v4_selected_stock_duplicate_code")
            seen.add(code)
            codes.append(code)
    except DailyMarketTechnicalSnapshotV4RepositoryError:
        raise
    except Exception as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_selected_stock_codes_invalid", str(exc)
        ) from exc
    _check_cancelled(cancel_callback)
    return tuple(codes)


def _parse_artifact_ref(value: object) -> DailyMarketTechnicalSnapshotV4ArtifactRef:
    if not isinstance(value, Mapping) or frozenset(value) != _ARTIFACT_REF_KEYS:
        _fail("technical_snapshot_v4_artifact_ref_invalid")
    stock_code = _validate_stock_code(value.get("stock_code"))
    relative_path = value.get("relative_path")
    if not isinstance(relative_path, str):
        _fail("technical_snapshot_v4_artifact_ref_invalid")
    byte_size = value.get("byte_size")
    if isinstance(byte_size, bool) or not isinstance(byte_size, int) or not (
        0 < byte_size <= DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES
    ):
        _fail("technical_snapshot_v4_artifact_ref_invalid")
    source_identity = value.get("source_identity")
    if not isinstance(source_identity, str) or not source_identity or len(source_identity) > 4096:
        _fail("technical_snapshot_v4_artifact_ref_invalid")
    return DailyMarketTechnicalSnapshotV4ArtifactRef(
        stock_code=stock_code,
        relative_path=relative_path,
        byte_size=byte_size,
        sha256=_require_sha(value.get("sha256"), "technical_snapshot_v4_artifact_ref_invalid"),
        snapshot_identity_sha256=_require_sha(
            value.get("snapshot_identity_sha256"),
            "technical_snapshot_v4_artifact_ref_invalid",
        ),
        source_identity=source_identity,
        raw_source_window_fingerprint_sha256=_require_sha(
            value.get("raw_source_window_fingerprint_sha256"),
            "technical_snapshot_v4_artifact_ref_invalid",
        ),
        source_window_fingerprint_sha256=_require_sha(
            value.get("source_window_fingerprint_sha256"),
            "technical_snapshot_v4_artifact_ref_invalid",
        ),
        calculation_identity_sha256=_require_sha(
            value.get("calculation_identity_sha256"),
            "technical_snapshot_v4_artifact_ref_invalid",
        ),
    )


def _validate_artifact_relpath(value: str, stock_code: str) -> PurePosixPath:
    if "\\" in value or ":" in value or value.startswith("/"):
        _fail("technical_snapshot_v4_artifact_path_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or path.parts != ("artifacts", f"{stock_code}.json"):
        _fail("technical_snapshot_v4_artifact_path_invalid")
    if any(part in {"", ".", ".."} for part in path.parts):
        _fail("technical_snapshot_v4_artifact_path_invalid")
    return path


def _verified_cohort_payload(value: object) -> dict[str, object]:
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        value = value.to_dict()
    if not isinstance(value, Mapping) or frozenset(value) != _COHORT_KEYS:
        _fail("technical_snapshot_v4_cohort_invalid")
    if value.get("schema_version") != "daily-market-technical-cohort.v4":
        _fail("technical_snapshot_v4_cohort_schema_unsupported")
    universe_id = _bounded_text(value.get("universe_id"), 128)
    population_version = _bounded_text(value.get("population_version"), 128)
    decision_date = _parse_iso_date(value.get("decision_date"))
    included = _validate_code_list(
        value.get("included_stock_codes"),
        minimum=0,
        maximum=DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_COHORT_CODES,
        code="technical_snapshot_v4_cohort_invalid",
    )
    excluded = _validate_code_list(
        value.get("excluded_stock_codes"),
        minimum=0,
        maximum=DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_COHORT_CODES,
        code="technical_snapshot_v4_cohort_invalid",
    )
    if set(included).intersection(excluded):
        _fail("technical_snapshot_v4_cohort_membership_overlap")
    reason_map = value.get("exclusion_reasons")
    if not isinstance(reason_map, Mapping) or set(reason_map) != set(excluded):
        _fail("technical_snapshot_v4_exclusion_reasons_mismatch")
    normalized_reasons: dict[str, str] = {}
    for code in excluded:
        reason = reason_map.get(code)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 512:
            _fail("technical_snapshot_v4_exclusion_reasons_mismatch")
        normalized_reasons[code] = reason
    declared_count = value.get("declared_count")
    if isinstance(declared_count, bool) or not isinstance(declared_count, int):
        _fail("technical_snapshot_v4_cohort_invalid")
    if declared_count != len(included) + len(excluded):
        _fail("technical_snapshot_v4_cohort_count_mismatch")
    core: dict[str, object] = {
        "schema_version": "daily-market-technical-cohort.v4",
        "universe_id": universe_id,
        "population_version": population_version,
        "decision_date": decision_date.isoformat(),
        "included_stock_codes": list(included),
        "excluded_stock_codes": list(excluded),
        "exclusion_reasons": normalized_reasons,
        "declared_count": declared_count,
    }
    identity = sha256_bytes(canonical_v4_json_bytes(core))
    if value.get("cohort_identity_sha256") != identity:
        _fail("technical_snapshot_v4_cohort_identity_mismatch")
    return {
        **core,
        "cohort_identity_sha256": identity,
        "decision_date": decision_date,
        "included_stock_codes": included,
        "excluded_stock_codes": excluded,
        "exclusion_reason_map": normalized_reasons,
    }


def _source_clock_from_payload(value: object) -> DailyMarketTechnicalSourceClockV4:
    if not isinstance(value, Mapping) or frozenset(value) != _CLOCK_KEYS:
        _fail("technical_snapshot_v4_source_clock_invalid")
    raw_pins = value.get("source_file_pin")
    if not isinstance(raw_pins, list) or len(raw_pins) != 2:
        _fail("technical_snapshot_v4_source_clock_invalid")
    pins: list[tuple[str, ...] | tuple[str, int, int, int, int]] = []
    for raw_pin in raw_pins:
        if not isinstance(raw_pin, list) or not raw_pin or not isinstance(raw_pin[0], str):
            _fail("technical_snapshot_v4_source_clock_invalid")
        if len(raw_pin) == 1:
            pins.append((raw_pin[0],))
        elif len(raw_pin) == 5:
            values = raw_pin[1:]
            if any(isinstance(item, bool) or not isinstance(item, int) for item in values):
                _fail("technical_snapshot_v4_source_clock_invalid")
            pins.append((raw_pin[0], values[0], values[1], values[2], values[3]))
        else:
            _fail("technical_snapshot_v4_source_clock_invalid")
    date_value = _parse_iso_date(value.get("decision_date"))
    cutoff_value = value.get("decision_cutoff")
    if not isinstance(cutoff_value, str):
        _fail("technical_snapshot_v4_source_clock_invalid")
    try:
        cutoff = datetime.fromisoformat(cutoff_value)
    except ValueError as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_source_clock_invalid"
        ) from exc
    try:
        clock = DailyMarketTechnicalSourceClockV4(
            database_path=cast(str, value.get("database_path")),
            schema_identity_sha256=cast(str, value.get("schema_identity_sha256")),
            source_file_pin=tuple(cast(Any, tuple(item)) for item in pins),
            source_pin_sha256=cast(str, value.get("source_pin_sha256")),
            decision_date=date_value,
            decision_cutoff=cutoff,
            cutoff_guard_version=cast(str, value.get("cutoff_guard_version")),
            source_id=cast(Any, value.get("source_id")),
            source_available_at=cast(Any, value.get("source_available_at")),
            availability_status=cast(Any, value.get("availability_status")),
            historical_pit_eligible=cast(Any, value.get("historical_pit_eligible")),
        )
    except (TypeError, ValueError) as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_source_clock_invalid", str(exc)
        ) from exc
    if clock.to_dict() != dict(value):
        _fail("technical_snapshot_v4_source_clock_noncanonical")
    return clock


def _validate_manifest_location(path: Path, store_root: Path) -> None:
    try:
        relative = path.relative_to(store_root)
    except ValueError:
        _fail("technical_snapshot_v4_manifest_outside_repository")
    parts = relative.parts
    if (
        len(parts) != 7
        or parts[0] != "generations"
        or not _SHA256_RE.fullmatch(parts[1])
        or parts[2] != "batches"
        or not _SHA256_RE.fullmatch(parts[3])
        or parts[4] != "attempts"
        or not re.fullmatch(r"[0-9a-f]{32}", parts[5])
        or parts[6] != "manifest.json"
    ):
        _fail("technical_snapshot_v4_manifest_path_invalid")


def _validate_attempt_layout(
    batch_root: Path,
    expected_codes: tuple[str, ...],
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> None:
    _check_cancelled(cancel_callback)
    files = _enumerate_files(
        batch_root,
        DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_FILES_PER_ATTEMPT,
        cancel_callback=cancel_callback,
    )
    expected = {"manifest.json"}
    expected.update(f"artifacts/{code}.json" for code in expected_codes)
    if set(files) != expected:
        _fail("technical_snapshot_v4_attempt_layout_invalid")
    _check_cancelled(cancel_callback)


def _enumerate_files(
    root: Path,
    max_files: int,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> dict[str, int]:
    result: dict[str, int] = {}
    stack: list[tuple[Path, str]] = [(root, "")]
    while stack:
        _check_cancelled(cancel_callback)
        current, prefix = stack.pop()
        _validate_existing_directory(current)
        try:
            entries = list(os.scandir(to_internal_io_path(current)))
        except OSError as exc:
            raise DailyMarketTechnicalSnapshotV4RepositoryError(
                "technical_snapshot_v4_attempt_layout_invalid", str(exc)
            ) from exc
        if len(entries) > max_files + 1:
            _fail("technical_snapshot_v4_attempt_layout_invalid")
        for entry in entries:
            _check_cancelled(cancel_callback)
            child = current / entry.name
            relative = f"{prefix}{entry.name}"
            info = _lstat_optional(child)
            if info is None:
                _fail("technical_snapshot_v4_file_changed_during_read")
            if _is_link_or_reparse(info):
                _fail("technical_snapshot_v4_link_rejected")
            if stat.S_ISDIR(info.st_mode):
                if relative != "artifacts":
                    _fail("technical_snapshot_v4_attempt_layout_invalid")
                stack.append((child, f"{relative}/"))
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                result[relative] = info.st_size
                if len(result) > max_files:
                    _fail("technical_snapshot_v4_attempt_layout_invalid")
            else:
                _fail("technical_snapshot_v4_file_type_rejected")
    return result


def _canonical_directory(path: str | Path, *, must_exist: bool) -> Path:
    raw = Path(path).expanduser()
    if not raw.is_absolute() or ".." in raw.parts:
        _fail("technical_snapshot_v4_absolute_root_required")
    _reject_link_components(raw)
    canonical = _canonical_realpath(raw)
    if canonical != raw:
        _fail("technical_snapshot_v4_root_not_canonical")
    info = _lstat_optional(canonical)
    if must_exist:
        if info is None or not stat.S_ISDIR(info.st_mode):
            _fail("technical_snapshot_v4_repository_root_missing")
    elif info is not None and not stat.S_ISDIR(info.st_mode):
        _fail("technical_snapshot_v4_output_root_not_directory")
    return canonical


def _canonical_file(path: str | Path) -> Path:
    raw = Path(path).expanduser()
    if not raw.is_absolute() or ".." in raw.parts:
        _fail("technical_snapshot_v4_absolute_path_required")
    _reject_link_components(raw)
    canonical = _canonical_realpath(raw)
    if canonical != raw:
        _fail("technical_snapshot_v4_path_not_canonical")
    info = _lstat_optional(canonical)
    if info is None or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        _fail("technical_snapshot_v4_file_type_rejected")
    return canonical


def _canonical_realpath(path: Path) -> Path:
    try:
        rendered = os.path.realpath(to_internal_io_path(path))
    except (OSError, ValueError) as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_path_unavailable", str(exc)
        ) from exc
    return Path(_strip_io_prefix(rendered))


def _strip_io_prefix(value: str) -> str:
    if os.name != "nt":
        return value
    folded = value.casefold()
    if folded.startswith("\\\\?\\unc\\"):
        return "\\\\" + value[len("\\\\?\\unc\\"):]
    if folded.startswith("\\\\?\\"):
        return value[4:]
    return value


def _reject_link_components(path: Path) -> None:
    for component in reversed((path, *path.parents)):
        info = _lstat_optional(component)
        if info is not None and _is_link_or_reparse(info):
            _fail("technical_snapshot_v4_link_rejected")


def _validate_existing_directory(path: Path) -> None:
    info = _lstat_optional(path)
    if info is None or not stat.S_ISDIR(info.st_mode) or _is_link_or_reparse(info):
        _fail("technical_snapshot_v4_directory_invalid")


def _lstat_optional(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(to_internal_io_path(path))
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_path_unavailable", str(exc)
        ) from exc


def _is_link_or_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400
    )


def _read_bounded_file(path: Path, limit: int) -> bytes:
    _reject_link_components(path)
    before = _lstat_optional(path)
    if before is None or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        _fail("technical_snapshot_v4_file_type_rejected")
    if before.st_size > limit:
        _fail("technical_snapshot_v4_byte_limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(to_internal_io_path(path), flags)
        with os.fdopen(descriptor, "rb") as handle:
            raw = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_read_failed", str(exc)
        ) from exc
    current = _lstat_optional(path)
    if current is None or _is_link_or_reparse(current):
        _fail("technical_snapshot_v4_file_changed_during_read")
    signature = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_nlink)
    if signature(before) != signature(after) or signature(after) != signature(current):
        _fail("technical_snapshot_v4_file_changed_during_read")
    if len(raw) > limit or len(raw) != before.st_size:
        _fail("technical_snapshot_v4_byte_limit")
    return raw


def _scan_tree_size(root: Path, *, limit: int) -> int:
    """有界計算 v4 store 內所有已保存與未完成檔案大小。"""

    if _lstat_optional(root) is None:
        return 0
    total = 0
    seen_files = 0
    stack = [root]
    while stack:
        current = stack.pop()
        _validate_existing_directory(current)
        try:
            entries = list(os.scandir(to_internal_io_path(current)))
        except OSError as exc:
            raise DailyMarketTechnicalSnapshotV4RepositoryError(
                "technical_snapshot_v4_store_scan_failed", str(exc)
            ) from exc
        if len(entries) > 100_000:
            _fail("technical_snapshot_v4_store_entry_limit")
        for entry in entries:
            info = _lstat_optional(current / entry.name)
            if info is None:
                _fail("technical_snapshot_v4_file_changed_during_read")
            if _is_link_or_reparse(info):
                _fail("technical_snapshot_v4_link_rejected")
            if stat.S_ISDIR(info.st_mode):
                stack.append(current / entry.name)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                total += info.st_size
                seen_files += 1
                if total > limit:
                    _fail("technical_snapshot_v4_retention_limit")
                if seen_files > 100_000:
                    _fail("technical_snapshot_v4_store_entry_limit")
            else:
                _fail("technical_snapshot_v4_file_type_rejected")
    return total


def _find_manifests(root: Path, *, max_files: int = 100_000) -> tuple[Path, ...]:
    """在單一 generation 內以有界目錄走訪尋找已發布 manifest。"""

    if _lstat_optional(root) is None:
        return ()
    found: list[Path] = []
    seen = 0
    stack = [root]
    while stack:
        current = stack.pop()
        _validate_existing_directory(current)
        try:
            entries = list(os.scandir(to_internal_io_path(current)))
        except OSError as exc:
            raise DailyMarketTechnicalSnapshotV4RepositoryError(
                "technical_snapshot_v4_store_scan_failed", str(exc)
            ) from exc
        if len(entries) > max_files:
            _fail("technical_snapshot_v4_store_entry_limit")
        for entry in entries:
            seen += 1
            if seen > max_files:
                _fail("technical_snapshot_v4_store_entry_limit")
            child = current / entry.name
            info = _lstat_optional(child)
            if info is None:
                _fail("technical_snapshot_v4_file_changed_during_read")
            if _is_link_or_reparse(info):
                _fail("technical_snapshot_v4_link_rejected")
            if stat.S_ISDIR(info.st_mode):
                stack.append(child)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                if entry.name == "manifest.json":
                    found.append(child)
            else:
                _fail("technical_snapshot_v4_file_type_rejected")
    return tuple(sorted(found, key=lambda item: str(item)))


def _ensure_directory(path: Path) -> None:
    """建立新輸出目錄並檢查所有既有祖先沒有連結。"""

    _reject_link_components(path)
    try:
        os.makedirs(to_internal_io_path(path), exist_ok=True)
    except OSError as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_directory_create_failed", str(exc)
        ) from exc
    _validate_existing_directory(path)
    _reject_link_components(path)


def _write_new_temp(path: Path, raw: bytes, *, max_bytes: int) -> Path:
    """以 exclusive create 寫入同目錄暫存檔，並同步內容到儲存裝置。"""

    if len(raw) > max_bytes:
        _fail("technical_snapshot_v4_byte_limit")
    _reject_link_components(path.parent)
    _validate_existing_directory(path.parent)
    temp_path = path.with_name(path.name + ".tmp")
    if _lstat_optional(path) is not None or _lstat_optional(temp_path) is not None:
        _fail("technical_snapshot_v4_history_exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(to_internal_io_path(temp_path), flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            view = memoryview(raw)
            written = 0
            while written < len(view):
                written += handle.write(view[written:])
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_write_failed", str(exc)
        ) from exc
    info = _lstat_optional(temp_path)
    if info is None or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != len(raw):
        _fail("technical_snapshot_v4_temporary_file_invalid")
    return temp_path


def _publish_temp_no_replace(temp_path: Path, final_path: Path) -> None:
    """以同目錄 rename 原子發布；存在任何目標時拒絕覆寫。"""

    _reject_link_components(final_path.parent)
    _validate_existing_directory(final_path.parent)
    if _lstat_optional(final_path) is not None:
        _fail("technical_snapshot_v4_history_exists")
    if _lstat_optional(temp_path) is None:
        _fail("technical_snapshot_v4_temporary_file_missing")
    try:
        os.rename(to_internal_io_path(temp_path), to_internal_io_path(final_path))
    except OSError as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_atomic_publish_failed", str(exc)
        ) from exc
    info = _lstat_optional(final_path)
    if info is None or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        _fail("technical_snapshot_v4_published_file_invalid")


def _available_bytes(path: Path) -> int:
    current = path
    while _lstat_optional(current) is None:
        parent = current.parent
        if parent == current:
            _fail("technical_snapshot_v4_capacity_unavailable")
        current = parent
    _validate_existing_directory(current)
    try:
        return shutil.disk_usage(to_internal_io_path(current)).free
    except OSError as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_capacity_unavailable", str(exc)
        ) from exc


def _parse_canonical_object(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(code, str(exc)) from exc
    if not isinstance(value, dict) or canonical_v4_json_bytes(value) != raw:
        _fail("technical_snapshot_v4_noncanonical_json")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"invalid_json_constant:{value}")


def _validate_code_list(
    value: object,
    *,
    minimum: int,
    maximum: int,
    code: str,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        _fail(code)
    codes = tuple(_validate_stock_code(item) for item in value)
    if codes != tuple(sorted(set(codes))):
        _fail(code)
    return codes


def _validate_stock_code(value: object) -> str:
    if not isinstance(value, str) or not _STOCK_CODE_RE.fullmatch(value):
        _fail("technical_snapshot_v4_stock_code_invalid")
    return value


def _bounded_text(value: object, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        _fail("technical_snapshot_v4_cohort_invalid")
    return value


def _parse_iso_date(value: object) -> date:
    if not isinstance(value, str):
        _fail("technical_snapshot_v4_date_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DailyMarketTechnicalSnapshotV4RepositoryError(
            "technical_snapshot_v4_date_invalid"
        ) from exc
    if parsed.isoformat() != value:
        _fail("technical_snapshot_v4_date_invalid")
    return parsed


def _require_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail(code)
    return value


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalSnapshotV4RepositoryError(code, message)
