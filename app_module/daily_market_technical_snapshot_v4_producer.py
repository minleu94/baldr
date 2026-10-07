"""以已完成的來源窗口產製有界 v4 技術快照批次。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Literal, cast
import uuid

from app_module.daily_market_technical_feature_snapshot_v4 import (
    DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES,
    DailyMarketTechnicalFeatureSnapshotV4,
    build_daily_market_technical_feature_snapshot_v4,
    validate_daily_market_technical_feature_snapshot_v4,
)
from app_module.daily_market_technical_method_contract_v4 import (
    daily_market_technical_method_contract_v4_sha256,
)
from app_module.daily_market_technical_read_session import (
    DAILY_MARKET_TECHNICAL_READ_SESSION_BATCH_MAX_STOCKS,
    DailyMarketTechnicalSourceClockV4,
)
from app_module.daily_market_technical_source import DailyMarketTechnicalSourceWindow
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope

from app_module.daily_market_technical_snapshot_v4_repository import (
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_BATCH_MANIFEST_SCHEMA,
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_BATCH_ARTIFACT_BYTES,
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_COHORT_CODES,
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_MANIFEST_BYTES,
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_RETAINED_BYTES,
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_STORE_DIRECTORY,
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_WRITER_VERSION,
    DailyMarketTechnicalBatchArtifactV4,
    DailyMarketTechnicalSnapshotV4Repository,
    DailyMarketTechnicalSnapshotV4RepositoryError,
    _available_bytes,
    _canonical_directory,
    _canonical_realpath,
    _ensure_directory,
    _find_manifests,
    _publish_temp_no_replace,
    _scan_tree_size,
    _source_clock_from_payload,
    _verified_cohort_payload,
    _write_new_temp,
    canonical_v4_json_bytes,
    expected_stock_set_sha256,
    generation_identity_sha256,
    sha256_bytes,
)


DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_BATCH_TEMP_BYTES = (
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_BATCH_ARTIFACT_BYTES
    + DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_MANIFEST_BYTES
)
_PUBLICATION_GATE = threading.Lock()


class DailyMarketTechnicalSnapshotV4ProducerError(ValueError):
    """批次輸入、保存範圍或容量不符合 v4 producer 契約。"""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        published: bool = False,
    ) -> None:
        self.code = code
        self.published = published
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalSnapshotV4BatchWriteResult:
    """批次發布狀態；取消結果永遠不代表 manifest 已完成。"""

    status: Literal["complete", "cancelled"]
    artifact: DailyMarketTechnicalBatchArtifactV4 | None
    error_code: str | None = None
    reused_existing: bool = False


@dataclass(frozen=True, slots=True)
class _PreparedArtifact:
    stock_code: str
    snapshot: DailyMarketTechnicalFeatureSnapshotV4
    raw: bytes


def write_daily_market_technical_snapshot_v4_batch(
    *,
    output_root: str | Path,
    cohort: object,
    source_clock: DailyMarketTechnicalSourceClockV4,
    finished_windows: Sequence[DailyMarketTechnicalSourceWindow],
    cancel_callback: Callable[[], bool] | None = None,
    research_scope: ResearchCaptureWriteScope | None = None,
) -> DailyMarketTechnicalSnapshotV4BatchWriteResult:
    """保存一批最多 16 股的完成窗口，manifest 是唯一完整發布標記。

    ``finished_windows`` 必須來自 ``DailyMarketTechnicalReadSession.finish``；
    此函式不開啟 source DB、不重算來源窗口，也不會選取 latest run。
    """

    if cancel_callback is not None and not callable(cancel_callback):
        _raise("technical_snapshot_v4_cancel_callback_invalid")
    if _is_cancelled(cancel_callback):
        return _cancelled()
    if not isinstance(source_clock, DailyMarketTechnicalSourceClockV4):
        _raise("technical_snapshot_v4_source_clock_invalid")
    cohort_payload = _cohort_manifest_payload(cohort)
    cohort_sha = cast(str, cohort_payload["cohort_identity_sha256"])
    clock_payload = source_clock.to_dict()
    try:
        verified_clock = _source_clock_from_payload(clock_payload)
    except DailyMarketTechnicalSnapshotV4RepositoryError as exc:
        _raise(exc.code, str(exc))
    clock_sha = source_clock.identity_sha256
    if verified_clock.identity_sha256 != clock_sha:
        _raise("technical_snapshot_v4_source_clock_identity_mismatch")
    try:
        decision_date = date.fromisoformat(cast(str, cohort_payload["decision_date"]))
    except ValueError as exc:
        raise DailyMarketTechnicalSnapshotV4ProducerError(
            "technical_snapshot_v4_decision_date_mismatch"
        ) from exc
    if decision_date != source_clock.decision_date:
        _raise("technical_snapshot_v4_decision_date_mismatch")
    method_sha = daily_market_technical_method_contract_v4_sha256()
    generation_sha = generation_identity_sha256(
        cohort_identity_sha256=cohort_sha,
        source_clock_identity_sha256=clock_sha,
        method_contract_sha256=method_sha,
    )

    prepared = _prepare_artifacts(
        finished_windows=finished_windows,
        included_stock_codes=cast(tuple[str, ...], cohort_payload["included_stock_codes"]),
        decision_date=decision_date,
        source_clock=source_clock,
        method_sha=method_sha,
    )
    if _is_cancelled(cancel_callback):
        return _cancelled()
    artifact_bytes = sum(len(item.raw) for item in prepared)
    if artifact_bytes > DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_BATCH_ARTIFACT_BYTES:
        _raise("technical_snapshot_v4_batch_artifact_limit")
    batch_codes = tuple(item.stock_code for item in prepared)
    batch_set_sha = expected_stock_set_sha256(batch_codes)
    ref_payloads = [
        _artifact_ref_payload(item)
        for item in prepared
    ]
    manifest_payload: dict[str, object] = {
        "schema_version": DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_BATCH_MANIFEST_SCHEMA,
        "writer_version": DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_WRITER_VERSION,
        "generation_identity_sha256": generation_sha,
        "cohort": cohort_payload,
        "cohort_identity_sha256": cohort_sha,
        "source_clock": clock_payload,
        "source_clock_identity_sha256": clock_sha,
        "method_contract_sha256": method_sha,
        "decision_date": decision_date.isoformat(),
        "expected_stock_codes": list(batch_codes),
        "expected_stock_set_sha256": batch_set_sha,
        "artifact_refs": ref_payloads,
    }
    manifest_raw = canonical_v4_json_bytes(manifest_payload)
    if len(manifest_raw) > DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_MANIFEST_BYTES:
        _raise("technical_snapshot_v4_manifest_byte_limit")
    planned_bytes = artifact_bytes + len(manifest_raw)
    if planned_bytes > DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_BATCH_TEMP_BYTES:
        _raise("technical_snapshot_v4_batch_temporary_limit")

    root = _preflight_output_root(
        output_root,
        source_clock=source_clock,
        research_scope=research_scope,
    )
    store_root = root / DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_STORE_DIRECTORY
    generation_root = store_root / "generations" / generation_sha
    batch_root = generation_root / "batches" / batch_set_sha
    existing = _reuse_or_reject_existing(
        output_root=root,
        generation_root=generation_root,
        requested_codes=batch_codes,
        requested_cohort_sha=cohort_sha,
        requested_clock_sha=clock_sha,
        requested_method_sha=method_sha,
        decision_date=decision_date,
        prepared=prepared,
    )
    if existing is not None:
        return DailyMarketTechnicalSnapshotV4BatchWriteResult(
            status="complete",
            artifact=existing,
            reused_existing=True,
        )
    try:
        retained_bytes = _scan_tree_size(
            store_root,
            limit=DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_RETAINED_BYTES,
        )
        if retained_bytes + planned_bytes > DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_RETAINED_BYTES:
            _raise("technical_snapshot_v4_retention_limit")
        if _available_bytes(root) < planned_bytes:
            _raise("technical_snapshot_v4_capacity_insufficient")
    except DailyMarketTechnicalSnapshotV4RepositoryError as exc:
        _raise(exc.code, str(exc))
    if _is_cancelled(cancel_callback):
        return _cancelled()

    attempt_root = batch_root / "attempts" / uuid.uuid4().hex
    artifact_dir = attempt_root / "artifacts"
    manifest_path = attempt_root / "manifest.json"
    try:
        _ensure_directory(root)
        _ensure_directory(store_root)
        _ensure_directory(store_root / "generations")
        _ensure_directory(generation_root)
        _ensure_directory(generation_root / "batches")
        _ensure_directory(batch_root)
        _ensure_directory(batch_root / "attempts")
        _ensure_directory(attempt_root)
        _ensure_directory(artifact_dir)
        if _is_cancelled(cancel_callback):
            return _cancelled()
        for item in prepared:
            if _is_cancelled(cancel_callback):
                return _cancelled()
            artifact_path = artifact_dir / f"{item.stock_code}.json"
            temp_path = _write_new_temp(
                artifact_path,
                item.raw,
                max_bytes=DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES,
            )
            _publish_temp_no_replace(temp_path, artifact_path)
        if _is_cancelled(cancel_callback):
            return _cancelled()
        manifest_temp = _write_new_temp(
            manifest_path,
            manifest_raw,
            max_bytes=DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_MANIFEST_BYTES,
        )
        with _PUBLICATION_GATE:
            if _is_cancelled(cancel_callback):
                return _cancelled()
            _publish_temp_no_replace(manifest_temp, manifest_path)
        repository = DailyMarketTechnicalSnapshotV4Repository(root)
        verified = repository.read_exact(
            manifest_path,
            expected_cohort_identity_sha256=cohort_sha,
            expected_source_clock_sha256=clock_sha,
            expected_method_contract_sha256=method_sha,
            expected_decision_date=decision_date,
        )
        return DailyMarketTechnicalSnapshotV4BatchWriteResult(
            status="complete",
            artifact=verified,
        )
    except DailyMarketTechnicalSnapshotV4ProducerError:
        raise
    except DailyMarketTechnicalSnapshotV4RepositoryError as exc:
        raise DailyMarketTechnicalSnapshotV4ProducerError(
            exc.code,
            str(exc),
            published=_file_exists(manifest_path),
        ) from exc
    except (OSError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalSnapshotV4ProducerError(
            _reason_code(exc),
            str(exc),
            published=_file_exists(manifest_path),
        ) from exc


def _prepare_artifacts(
    *,
    finished_windows: Sequence[DailyMarketTechnicalSourceWindow],
    included_stock_codes: tuple[str, ...],
    decision_date: date,
    source_clock: DailyMarketTechnicalSourceClockV4,
    method_sha: str,
) -> tuple[_PreparedArtifact, ...]:
    if isinstance(finished_windows, (str, bytes)):
        _raise("technical_snapshot_v4_windows_invalid")
    if not 1 <= len(finished_windows) <= DAILY_MARKET_TECHNICAL_READ_SESSION_BATCH_MAX_STOCKS:
        _raise("technical_snapshot_v4_batch_stock_limit")
    windows = tuple(finished_windows)
    if any(not isinstance(item, DailyMarketTechnicalSourceWindow) for item in windows):
        _raise("technical_snapshot_v4_windows_invalid")
    codes = tuple(item.stock_code for item in windows)
    if codes != tuple(sorted(set(codes))):
        _raise("technical_snapshot_v4_batch_stock_set_invalid")
    if any(code not in included_stock_codes for code in codes):
        _raise("technical_snapshot_v4_batch_stock_outside_cohort")
    prepared: list[_PreparedArtifact] = []
    for window in windows:
        if (
            window.database_path != source_clock.database_path
            or window.source_id != source_clock.source_id
            or window.source_file_pin != source_clock.source_file_pin
            or window.source_pin_sha256 != source_clock.source_pin_sha256
            or window.schema_identity_sha256 != source_clock.schema_identity_sha256
            or window.decision_date != decision_date
            or window.decision_cutoff != source_clock.decision_cutoff
        ):
            _raise("technical_snapshot_v4_window_clock_mismatch")
        try:
            snapshot = build_daily_market_technical_feature_snapshot_v4(
                window,
                source_clock=source_clock,
            )
            snapshot = validate_daily_market_technical_feature_snapshot_v4(snapshot.to_dict())
            raw = snapshot.to_json().encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise DailyMarketTechnicalSnapshotV4ProducerError(
                _reason_code(exc), str(exc)
            ) from exc
        if len(raw) > DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES:
            _raise("technical_snapshot_v4_artifact_byte_limit")
        if snapshot.method_contracts_sha256 != method_sha:
            _raise("technical_snapshot_v4_method_contract_mismatch")
        prepared.append(_PreparedArtifact(window.stock_code, snapshot, raw))
    return tuple(prepared)


def _artifact_ref_payload(item: _PreparedArtifact) -> dict[str, object]:
    snapshot = item.snapshot
    return {
        "stock_code": item.stock_code,
        "relative_path": f"artifacts/{item.stock_code}.json",
        "byte_size": len(item.raw),
        "sha256": sha256_bytes(item.raw),
        "snapshot_identity_sha256": snapshot.snapshot_identity_sha256,
        "source_identity": snapshot.source_identity,
        "raw_source_window_fingerprint_sha256": (
            snapshot.raw_source_window_fingerprint_sha256
        ),
        "source_window_fingerprint_sha256": snapshot.source_window_fingerprint_sha256,
        "calculation_identity_sha256": snapshot.calculation_identity_sha256,
    }


def _cohort_manifest_payload(value: object) -> dict[str, object]:
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        value = value.to_dict()
    verified = _verified_cohort_payload(value)
    return {
        "schema_version": "daily-market-technical-cohort.v4",
        "universe_id": cast(str, verified["universe_id"]),
        "population_version": cast(str, verified["population_version"]),
        "decision_date": cast(date, verified["decision_date"]).isoformat(),
        "included_stock_codes": list(cast(tuple[str, ...], verified["included_stock_codes"])),
        "excluded_stock_codes": list(cast(tuple[str, ...], verified["excluded_stock_codes"])),
        "exclusion_reasons": dict(cast(dict[str, str], verified["exclusion_reason_map"])),
        "declared_count": cast(int, verified["declared_count"]),
        "cohort_identity_sha256": cast(str, verified["cohort_identity_sha256"]),
    }


def _preflight_output_root(
    output_root: str | Path,
    *,
    source_clock: DailyMarketTechnicalSourceClockV4,
    research_scope: ResearchCaptureWriteScope | None,
) -> Path:
    try:
        root = _canonical_directory(output_root, must_exist=False)
    except DailyMarketTechnicalSnapshotV4RepositoryError as exc:
        _raise(exc.code, str(exc))
    source_db = Path(source_clock.database_path)
    if source_db.is_relative_to(root):
        _raise("technical_snapshot_v4_source_output_overlap")
    if root.is_relative_to(source_db):
        _raise("technical_snapshot_v4_source_output_overlap")
    wal_path = Path(f"{source_clock.database_path}-wal")
    if wal_path.is_relative_to(root) or root.is_relative_to(wal_path):
        _raise("technical_snapshot_v4_source_output_overlap")

    if research_scope is not None:
        if not isinstance(research_scope, ResearchCaptureWriteScope):
            _raise("technical_snapshot_v4_research_scope_invalid")
        try:
            research_scope.validate()
        except (OSError, TypeError, ValueError) as exc:
            raise DailyMarketTechnicalSnapshotV4ProducerError(
                _reason_code(exc), str(exc)
            ) from exc
        if str(research_scope.source_database) != source_clock.database_path:
            _raise("technical_snapshot_v4_research_scope_source_mismatch")
        scope_root = _canonical_realpath(Path(research_scope.root))
        if root == scope_root or not root.is_relative_to(scope_root):
            _raise("technical_snapshot_v4_research_scope_escape")
        return root

    repository_root = _canonical_realpath(Path(__file__).parents[1])
    qa_root = _canonical_realpath(repository_root / "output" / "qa")
    temp_root = _canonical_realpath(Path(tempfile.gettempdir()))
    if not any(
        root != allowed and root.is_relative_to(allowed)
        for allowed in (qa_root, temp_root)
    ):
        _raise("technical_snapshot_v4_isolated_output_required")
    return root


def _reuse_or_reject_existing(
    *,
    output_root: Path,
    generation_root: Path,
    requested_codes: tuple[str, ...],
    requested_cohort_sha: str,
    requested_clock_sha: str,
    requested_method_sha: str,
    decision_date: date,
    prepared: tuple[_PreparedArtifact, ...],
) -> DailyMarketTechnicalBatchArtifactV4 | None:
    manifests = _find_manifests(generation_root)
    if not manifests:
        return None
    repository = DailyMarketTechnicalSnapshotV4Repository(output_root)
    all_existing_codes: set[str] = set()
    exact_match: DailyMarketTechnicalBatchArtifactV4 | None = None
    requested_identities = {
        item.stock_code: (
            len(item.raw),
            sha256_bytes(item.raw),
            item.snapshot.snapshot_identity_sha256,
        )
        for item in prepared
    }
    for manifest_path in manifests:
        artifact = repository.read_exact(manifest_path)
        if (
            artifact.generation_identity_sha256 != generation_root.name
            or artifact.cohort_identity_sha256 != requested_cohort_sha
            or artifact.source_clock_identity_sha256 != requested_clock_sha
            or artifact.method_contract_sha256 != requested_method_sha
            or artifact.decision_date != decision_date
        ):
            _raise("technical_snapshot_v4_generation_conflict")
        existing_codes = set(artifact.expected_stock_codes)
        overlap = all_existing_codes.intersection(existing_codes)
        if overlap:
            _raise("technical_snapshot_v4_generation_duplicate_stock")
        all_existing_codes.update(existing_codes)
        if artifact.expected_stock_codes == requested_codes:
            actual_identities = {
                ref.stock_code: (ref.byte_size, ref.sha256, ref.snapshot_identity_sha256)
                for ref in artifact.artifact_refs
            }
            if actual_identities != requested_identities:
                _raise("technical_snapshot_v4_completed_generation_conflict")
            exact_match = artifact
    if exact_match is not None:
        return exact_match
    if all_existing_codes.intersection(requested_codes):
        _raise("technical_snapshot_v4_generation_duplicate_stock")
    return None


def _is_cancelled(callback: Callable[[], bool] | None) -> bool:
    if callback is None:
        return False
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalSnapshotV4ProducerError(
            "technical_snapshot_v4_cancel_check_failed", str(exc)
        ) from exc
    if not isinstance(value, bool):
        _raise("technical_snapshot_v4_cancel_callback_invalid")
    return value


def _cancelled() -> DailyMarketTechnicalSnapshotV4BatchWriteResult:
    return DailyMarketTechnicalSnapshotV4BatchWriteResult(
        status="cancelled",
        artifact=None,
        error_code="technical_snapshot_v4_cancelled",
    )


def _file_exists(path: Path) -> bool:
    try:
        return os.path.exists(to_internal_io_path(path))
    except (OSError, ValueError):
        return False


def _reason_code(exc: BaseException) -> str:
    candidate = getattr(exc, "code", None)
    if isinstance(candidate, str) and candidate.startswith("technical_snapshot_v4_"):
        return candidate
    return "technical_snapshot_v4_producer_failed"


def _raise(code: str, message: str | None = None) -> None:
    raise DailyMarketTechnicalSnapshotV4ProducerError(code, message)
