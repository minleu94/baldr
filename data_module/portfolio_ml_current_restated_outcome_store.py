"""從已驗證的年度 current-restated raw shards 建立結果標籤研究數值庫。

這個隔離 lane 保留事件參考日與實際研究可得時鐘，永不轉成 PIT row、教師
target 或正式 allocation artifact。所有特徵與標籤均以整數／十進位指數保存。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import tempfile
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np

from data_module import ml_daily_price_revision_gate as revision_gate
from data_module import ml_pit_year_shard_exporter as raw_exporter
from data_module import portfolio_ml_dataset_assembler as label_math
from data_module.ml_price_availability_contract import (
    validate_price_unavailable_research_contract,
)
from data_module.ml_research_output_boundary import resolve_ml_research_output_path
from data_module.ml_storage_capacity import (
    heavy_chain_capacity_budget,
    preflight_capacity,
)


OUTCOME_STORE_SCHEMA_V1 = "portfolio-ml-current-restated-outcome-store.v1"
OUTCOME_STORE_STATUS_READY = "current_restated_outcome_numeric_ready"
OUTCOME_STORE_PROFILE = "core_current_restated_outcome_only"
_DAILY_TRANSACTION_AMOUNT_UNIT_CONTRACT = "tw-daily-price-transaction-amount-twd.v1"
_OUTCOME_BUY_SIDE_COST_BP = 25
_OUTCOME_SELL_SIDE_COST_BP = 55
_OUTCOME_TOTAL_ROUND_TRIP_COST_BP = (
    _OUTCOME_BUY_SIDE_COST_BP + _OUTCOME_SELL_SIDE_COST_BP
)
SUPPORTED_HORIZONS = (5, 10, 20, 60)
LABEL_METRICS = (
    "stock_return_bp",
    "benchmark_return_bp",
    "benchmark_excess_return_bp",
    "mae_loss_bp",
    "mfe_gain_bp",
    "realized_volatility_bp",
    "max_drawdown_bp",
    "tail_loss_bp",
    "downside_observed",
    "fill_feasible_observed",
)
_TAIPEI = ZoneInfo("Asia/Taipei")
_MAX_TARGET_SYMBOLS = 20
_MAX_RAW_ROWS = 1_000_000
_MAX_FEATURE_CELLS = 5_000_000
_MAX_ARRAY_BYTES = 2 * 1024 * 1024 * 1024
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


class CurrentRestatedOutcomeStoreError(ValueError):
    """年度 current-restated raw 或 outcome 數值契約無效。"""

    classification = "current_restated_outcome_store_invalid"


class InsufficientMatureCurrentRestatedHistoryError(
    CurrentRestatedOutcomeStoreError
):
    """真實成熟標籤不足以產生受 purge 約束的 walk-forward folds。"""

    classification = "insufficient_mature_current_restated_history"


@dataclass(frozen=True, slots=True)
class CurrentRestatedOutcomeStoreRequest:
    raw_publication_manifest_path: Path
    expected_raw_publication_manifest_sha256: str
    expected_raw_dataset_manifest_sha256: str
    output_root: Path
    benchmark_entity_id: str
    target_symbols: tuple[str, ...]
    minimum_train_dates: int = 125
    test_date_count: int = 63
    purge_trading_days: int = 60
    embargo_trading_days: int = 5
    max_raw_rows: int = _MAX_RAW_ROWS
    repository_root: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.benchmark_entity_id, str) or not self.benchmark_entity_id.strip():
            raise ValueError("benchmark_entity_id must be non-empty")
        _hash_pin(
            self.expected_raw_publication_manifest_sha256,
            "expected_raw_publication_manifest_sha256",
        )
        _hash_pin(
            self.expected_raw_dataset_manifest_sha256,
            "expected_raw_dataset_manifest_sha256",
        )
        normalized = tuple(sorted({str(item).strip() for item in self.target_symbols}))
        if not normalized or any(not item for item in normalized):
            raise ValueError("target_symbols must contain explicit non-empty symbols")
        if len(normalized) > _MAX_TARGET_SYMBOLS:
            raise ValueError("target_symbols exceeds the bounded research limit")
        object.__setattr__(self, "target_symbols", normalized)
        for field_name in (
            "minimum_train_dates",
            "test_date_count",
            "purge_trading_days",
            "embargo_trading_days",
            "max_raw_rows",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
        if self.purge_trading_days < 60 or self.embargo_trading_days < 5:
            raise ValueError("research folds require purge>=60 and embargo>=5")
        if self.minimum_train_dates < 125 or self.test_date_count < 63:
            raise ValueError("research folds require at least 125 train and 63 test dates")
        if self.max_raw_rows > _MAX_RAW_ROWS:
            raise ValueError("max_raw_rows exceeds the bounded parser limit")


@dataclass(frozen=True, slots=True)
class CurrentRestatedOutcomeFeatureV1:
    feature_id: str
    source_feature_id: str
    source_table: str
    role: str
    unit: str
    decimal_exponent: int
    eligibility_status: str


@dataclass(frozen=True, slots=True)
class CurrentRestatedOutcomeLabelV1:
    horizon: int
    next_entry_date: date
    horizon_end_date: date
    stock_return_bp: int
    benchmark_return_bp: int
    benchmark_excess_return_bp: int
    stock_next_entry_open_value_int: int
    stock_next_entry_open_decimal_exponent: int
    stock_exit_close_value_int: int
    stock_exit_close_decimal_exponent: int
    benchmark_next_entry_open_value_int: int
    benchmark_next_entry_open_decimal_exponent: int
    benchmark_exit_close_value_int: int
    benchmark_exit_close_decimal_exponent: int
    stock_entry_source_hash: str
    stock_exit_source_hash: str
    benchmark_entry_source_hash: str
    benchmark_exit_source_hash: str
    stock_path_source_hashes: tuple[str, ...]
    benchmark_path_source_hashes: tuple[str, ...]
    source_row_hashes: tuple[str, ...]
    mae_loss_bp: int
    mfe_gain_bp: int
    realized_volatility_bp: int
    max_drawdown_bp: int
    tail_loss_bp: int
    downside_observed: bool
    fill_feasible_observed: bool
    inputs_available_at: datetime
    source_hash: str
    label_math_source_hash: str


@dataclass(frozen=True, slots=True)
class CurrentRestatedOutcomeObservationV1:
    sample_id: str
    symbol: str
    event_date: date
    feature_values: tuple[int, ...]
    missing_mask: tuple[bool, ...]
    quality_blocked_mask: tuple[bool, ...]
    staleness_mask: tuple[bool, ...]
    source_row_identity_hash: str
    source_rows: tuple[CurrentRestatedOutcomeSourceRowV1, ...]
    current_value_available_at: datetime
    labels: tuple[CurrentRestatedOutcomeLabelV1, ...]
    event_reference_only: bool = True
    original_source_available_at: None = None
    historical_pit_eligible: bool = False
    formal_training_eligible: bool = False


@dataclass(frozen=True, slots=True)
class CurrentRestatedOutcomeSourceRowV1:
    source_table: str
    source_id: str
    entity_id: str
    event_date: date
    source_row_hash: str


@dataclass(frozen=True, slots=True)
class CurrentRestatedOutcomeFoldV1:
    fold_id: str
    train_sample_ids: tuple[str, ...]
    test_sample_ids: tuple[str, ...]
    train_date_count: int
    test_date_count: int
    train_end_date: date
    test_start_date: date
    test_end_date: date
    purge_trading_days: int
    embargo_trading_days: int
    max_train_label_end_date: date
    train_date_indices: tuple[int, ...]
    test_date_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CurrentRestatedOutcomeRawPinV1:
    role_id: str
    path: str
    bytes: int
    mtime_ns: int
    sha256: str
    content_sha256: str | None
    row_count: int | None


@dataclass(frozen=True, slots=True)
class CurrentRestatedOutcomeArrayPinV1:
    name: str
    path: str
    bytes: int
    sha256: str
    dtype: str
    shape: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CurrentRestatedOutcomeCostContractV1:
    schema_version: str
    cost_unit: str
    buy_side_cost_bp: int
    sell_side_cost_bp: int
    total_round_trip_cost_bp: int
    gross_stock_return_metric: str
    gross_benchmark_return_metric: str
    net_excess_metric: str
    net_excess_formula: str
    source: str


@dataclass(frozen=True, slots=True)
class VerifiedCurrentRestatedOutcomeArtifact:
    status: str
    observations: tuple[CurrentRestatedOutcomeObservationV1, ...]
    feature_registry: tuple[CurrentRestatedOutcomeFeatureV1, ...]
    feature_registry_sha256: str
    labels_registry: tuple[str, ...]
    outcome_cost_contract: CurrentRestatedOutcomeCostContractV1
    raw_publication_manifest_path: str
    raw_publication_manifest_bytes_sha256: str
    raw_dataset_manifest_path: str
    raw_dataset_manifest_bytes_sha256: str
    artifact_receipt_path: str
    artifact_receipt_bytes_sha256: str
    run_id: str
    array_pins: tuple[CurrentRestatedOutcomeArrayPinV1, ...]
    raw_shard_pins: tuple[CurrentRestatedOutcomeRawPinV1, ...]
    source_database_path: str
    source_database_sha256: str
    snapshot_database_path: str
    snapshot_database_sha256: str
    snapshot_receipt_path: str
    snapshot_receipt_sha256: str
    source_observed_at: datetime
    revision_dependencies_verified_at: datetime
    raw_revision_dependencies_verified_at: datetime
    revision_dependency_bundle_sha256: str
    raw_generated_at: datetime
    current_observation_freeze: datetime
    artifact_available_at: datetime
    target_symbols: tuple[str, ...]
    benchmark_entity_id: str
    horizons: tuple[int, ...]
    event_date_calendar: tuple[date, ...]
    event_date_calendar_sha256: str
    folds: tuple[CurrentRestatedOutcomeFoldV1, ...]
    source_context_revalidation_json: bytes
    source_context_revalidation_sha256: str
    historical_pit_eligible: bool = False
    formal_training_eligible: bool = False
    full_teacher_qualified: bool = False
    teacher_targets_present: bool = False


@dataclass(frozen=True, slots=True)
class CurrentRestatedOutcomePublication:
    run_id: str
    manifest_path: Path
    latest_manifest_path: Path
    manifest_sha256: str
    raw_publication_manifest_sha256: str
    raw_dataset_manifest_sha256: str
    feature_registry_sha256: str
    observation_count: int
    feature_count: int
    fold_count: int
    artifact_available_at: datetime


@dataclass(frozen=True, slots=True)
class _CapturedFile:
    path: Path
    raw: bytes
    sha256: str
    byte_count: int
    mtime_ns: int


@dataclass(slots=True)
class _SampleDraft:
    symbol: str
    event_date: date
    values: dict[str, int | None]
    missing: dict[str, bool]
    quality_blocked: dict[str, bool]
    stale: dict[str, bool]
    source_rows: list[CurrentRestatedOutcomeSourceRowV1]
    assigned_feature_ids: set[str]


class PortfolioMLCurrentRestatedOutcomeStoreBuilder:
    """驗證年度 raw shard 並以獨立 current-restated lane 建立 outcomes。"""

    def build(
        self, request: CurrentRestatedOutcomeStoreRequest
    ) -> CurrentRestatedOutcomePublication:
        repository_root = request.repository_root
        output_root = resolve_ml_research_output_path(
            request.output_root,
            repository_root=repository_root,
            access="write",
        )
        raw_publication_path = _resolve_research_input_path(
            request.raw_publication_manifest_path,
            repository_root=repository_root,
        )
        budget = heavy_chain_capacity_budget(
            persistent_new_bytes_budget=2 * 1024**3,
            temporary_peak_bytes_budget=2 * 1024**3,
        )
        preflight_capacity(
            probe_path=output_root,
            budget=budget,
            stage="current_restated_direct_before_output",
            persistent_roots=(output_root,),
            temporary_roots=(output_root,),
            persistent_new_bytes_estimate=64 * 1024**2,
            temporary_peak_bytes_observed=0,
        )

        build_started_at = datetime.now(timezone.utc)
        outcome_cost_contract = _outcome_cost_contract_payload()
        publication_file = _capture_file(raw_publication_path)
        if publication_file.sha256 != _hash_pin(
            request.expected_raw_publication_manifest_sha256,
            "expected_raw_publication_manifest_sha256",
        ):
            raise CurrentRestatedOutcomeStoreError(
                "raw publication manifest does not match its caller-pinned bytes"
            )
        publication_manifest = _load_object(publication_file.raw, "raw publication manifest")
        _verify_manifest_hash(publication_manifest, label="raw publication manifest")
        _verify_publication_contract(
            publication_manifest,
            publication_path=publication_file.path,
            target_symbols=request.target_symbols,
            benchmark_entity_id=request.benchmark_entity_id,
            repository_root=repository_root,
        )
        dataset_path = publication_file.path.parent / "core_long_history" / "manifest.json"
        dataset_file = _capture_file(
            _resolve_research_input_path(dataset_path, repository_root=repository_root)
        )
        if dataset_file.sha256 != _hash_pin(
            request.expected_raw_dataset_manifest_sha256,
            "expected_raw_dataset_manifest_sha256",
        ):
            raise CurrentRestatedOutcomeStoreError(
                "core dataset manifest does not match its caller-pinned bytes"
            )
        dataset_manifest = _load_object(dataset_file.raw, "core raw dataset manifest")
        _verify_manifest_hash(dataset_manifest, label="core raw dataset manifest")
        _verify_dataset_contract(
            publication_manifest,
            dataset_manifest,
            dataset_path=dataset_file.path,
            repository_root=repository_root,
        )

        raw_context = _mapping(publication_manifest.get("source_context"), "source_context")
        raw_context_hash = _hash_json(raw_context)
        if raw_context_hash != publication_manifest.get("source_context_bundle_sha256"):
            raise CurrentRestatedOutcomeStoreError(
                "raw publication source-context canonical pin mismatch"
            )
        if dataset_manifest.get("source_context") != raw_context:
            raise CurrentRestatedOutcomeStoreError(
                "raw child dataset source context differs from its publication"
            )
        if dataset_manifest.get("source_context_bundle_sha256") != raw_context_hash:
            raise CurrentRestatedOutcomeStoreError(
                "raw child dataset source-context bundle hash mismatch"
            )
        verified_context = _revalidate_source_context(raw_context)
        _assert_context_stable(raw_context, verified_context)
        source_observed_at = verified_context.source_observed_at
        dependency_verified_at = verified_context.revision_dependencies_verified_at
        raw_dependency_verified_at = _aware_datetime(
            raw_context.get("revision_dependencies_verified_at"),
            "raw.revision_dependencies_verified_at",
        )
        if dependency_verified_at < build_started_at:
            # The collector clock is captured after all files are rechecked;
            # a monotonic ordering violation means the injected/request clock
            # is not the actual process clock or the evidence is invalid.
            raise CurrentRestatedOutcomeStoreError(
                "source dependency verification clock precedes Direct build start"
            )

        raw_generated_at = _aware_datetime(
            publication_manifest.get("raw_generated_at"), "raw_generated_at"
        )
        if raw_generated_at > build_started_at:
            raise CurrentRestatedOutcomeStoreError(
                "raw publication was generated after Direct build start"
            )
        selection_as_of = _aware_datetime(
            raw_context.get("data_selection_as_of"), "data_selection_as_of"
        )
        if selection_as_of > build_started_at:
            raise CurrentRestatedOutcomeStoreError(
                "raw source-selection cutoff is later than actual Direct build start"
            )

        feature_registry, registry_payload = _build_feature_registry(
            dataset_manifest, benchmark_entity_id=request.benchmark_entity_id
        )
        registry_sha = _hash_json(registry_payload)
        (
            raw_pins,
            drafts,
            price_rows,
            gap_rows,
            _raw_source_rows,
            raw_content_sha,
        ) = _read_raw_shards(
            raw_manifest_path=dataset_file.path,
            raw_manifest=dataset_manifest,
            publication_manifest=publication_manifest,
            feature_registry=feature_registry,
            target_symbols=request.target_symbols,
            benchmark_entity_id=request.benchmark_entity_id,
            raw_generated_at=raw_generated_at,
            source_observed_at=source_observed_at,
            dependency_verified_at=raw_dependency_verified_at,
            max_raw_rows=request.max_raw_rows,
            repository_root=repository_root,
        )
        source_verified_at = datetime.now(timezone.utc)
        actual_current_available_at = max(
            source_verified_at,
            raw_generated_at,
            source_observed_at,
            dependency_verified_at,
        )
        labels_by_key, benchmark_event_calendar = _build_benchmark_outcomes(
            price_rows=price_rows,
            gap_rows=gap_rows,
            target_symbols=request.target_symbols,
            benchmark_entity_id=request.benchmark_entity_id,
            input_available_at=actual_current_available_at,
        )
        observations, observation_rows = _materialize_observations(
            drafts=drafts,
            feature_registry=feature_registry,
            benchmark_entity_id=request.benchmark_entity_id,
            labels_by_key=labels_by_key,
            current_value_available_at=actual_current_available_at,
            source_context=verified_context,
            registry_sha256=registry_sha,
        )
        event_date_calendar, folds = _build_research_folds(
            observations=observations,
            minimum_train_dates=request.minimum_train_dates,
            test_date_count=request.test_date_count,
            purge_trading_days=request.purge_trading_days,
            embargo_trading_days=request.embargo_trading_days,
            benchmark_event_calendar=benchmark_event_calendar,
            target_symbols=request.target_symbols,
        )
        if len(folds) < 4:
            raise InsufficientMatureCurrentRestatedHistoryError(
                "fewer than four real folds have complete 5/10/20/60-session outcomes"
            )

        source_context_payload = raw_exporter._current_restated_context_payload(
            verified_context
        )
        source_context_revalidation_sha = _hash_json(source_context_payload)
        source_pins = {
            "raw_publication_manifest": _file_pin_payload(publication_file),
            "raw_dataset_manifest": _file_pin_payload(dataset_file),
            "raw_shards": [asdict(pin) for pin in raw_pins],
            "raw_content_sha256": raw_content_sha,
            "raw_context_bundle_sha256": raw_context_hash,
            "revalidated_context_bundle_sha256": source_context_revalidation_sha,
        }
        run_identity = {
            "schema_version": OUTCOME_STORE_SCHEMA_V1,
            "raw_publication_manifest_sha256": publication_file.sha256,
            "raw_dataset_manifest_sha256": dataset_file.sha256,
            "raw_content_sha256": raw_content_sha,
            "feature_registry_sha256": registry_sha,
            "outcome_cost_contract": outcome_cost_contract,
            "target_symbols": list(request.target_symbols),
            "benchmark_entity_id": request.benchmark_entity_id,
            "minimum_train_dates": request.minimum_train_dates,
            "test_date_count": request.test_date_count,
            "purge_trading_days": request.purge_trading_days,
            "embargo_trading_days": request.embargo_trading_days,
            "source_context_revalidation_sha256": source_context_revalidation_sha,
            "build_started_at": build_started_at.isoformat(),
        }
        run_id = "current-restated-outcome-" + _hash_json(run_identity).split(":", 1)[1][:24]
        output_root.mkdir(parents=True, exist_ok=True)
        runs_root = output_root / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        run_directory = runs_root / run_id
        if run_directory.exists():
            raise FileExistsError(f"current-restated Direct run already exists: {run_directory}")

        with tempfile.TemporaryDirectory(prefix=f".{run_id}-", dir=output_root) as temp_name:
            staging = Path(temp_name)
            arrays_manifest = _write_numeric_arrays(
                staging=staging,
                observations=observations,
                feature_count=len(feature_registry),
            )
            sample_metadata = _write_jsonl(
                staging / "observations.jsonl",
                observation_rows,
            )
            fold_payloads = [_fold_payload(item) for item in folds]
            completed_at = datetime.now(timezone.utc)
            manifest: dict[str, Any] = {
                "schema_version": OUTCOME_STORE_SCHEMA_V1,
                "status": OUTCOME_STORE_STATUS_READY,
                "run_id": run_id,
                "profile": OUTCOME_STORE_PROFILE,
                "data_temporality": "current_restated_research",
                "current_restated": True,
                "historical_pit_eligible": False,
                "formal_training_eligible": False,
                "full_teacher_qualified": False,
                "teacher_targets_present": False,
                "training_claim": "base_outcome_research_only",
                "publication_identity": run_identity,
                "publication_identity_sha256": _hash_json(run_identity),
                "source_pins": source_pins,
                "source_context_revalidation": source_context_payload,
                "source_observed_at": source_observed_at.isoformat(),
                "revision_dependencies_verified_at": dependency_verified_at.isoformat(),
                "raw_revision_dependencies_verified_at": raw_dependency_verified_at.isoformat(),
                "revision_dependency_bundle_sha256": verified_context.revision_dependency_bundle_sha256,
                "raw_generated_at": raw_generated_at.isoformat(),
                "current_observation_freeze": actual_current_available_at.isoformat(),
                "artifact_available_at": completed_at.isoformat(),
                "data_selection_as_of": selection_as_of.isoformat(),
                "source_available_time_is_distinct_from_event_date": True,
                "original_source_available_at": None,
                "target_symbols": list(request.target_symbols),
                "benchmark_entity_id": request.benchmark_entity_id,
                "included_feature_roles": ["stock", "benchmark"],
                "excluded_core_tables": {
                    "industry_indices": "no verified symbol-to-industry membership projection in this outcome lane"
                },
                "feature_registry": registry_payload,
                "feature_registry_sha256": registry_sha,
                "label_registry": list(LABEL_METRICS),
                "outcome_cost_contract": outcome_cost_contract,
                "label_time_contract": {
                    "feature_event_reference": "Taiwan-session close; raw event dates remain unchanged",
                    "entry_session_offset": 1,
                    "horizon_sessions": "next N benchmark sessions after the feature event date",
                    "label_end_dates": "true unshifted source event dates",
                    "spool_projection": "in-memory only; future source rows are keyed to the prior event reference date for shared outcome arithmetic",
                    "historical_pit_eligible": False,
                },
                "horizons": list(SUPPORTED_HORIZONS),
                "event_date_calendar": [item.isoformat() for item in event_date_calendar],
                "event_date_calendar_sha256": _hash_json(
                    [item.isoformat() for item in event_date_calendar]
                ),
                "benchmark_event_date_calendar": [
                    item.isoformat() for item in benchmark_event_calendar
                ],
                "benchmark_event_date_calendar_sha256": _hash_json(
                    [item.isoformat() for item in benchmark_event_calendar]
                ),
                "observation_count": len(observations),
                "feature_count": len(feature_registry),
                "observations_metadata": sample_metadata,
                "arrays": arrays_manifest,
                "fold_policy": {
                    "method": "expanding_event_reference_walk_forward",
                    "minimum_train_dates_after_purge": request.minimum_train_dates,
                    "test_date_count": request.test_date_count,
                    "purge_trading_days": request.purge_trading_days,
                    "embargo_trading_days": request.embargo_trading_days,
                    "minimum_fold_count": 4,
                    "label_end_must_be_strictly_before_test_start": True,
                    "folds": fold_payloads,
                },
                "safety": {
                    "research_only": True,
                    "historical_pit_eligible": False,
                    "formal_training_allowed": False,
                    "formal_oos_allowed": False,
                    "full_allocation_teacher_qualified": False,
                    "unreviewed_included": False,
                    "unknown_financial_statement_basis_included": False,
                    "raw_float_persistence_allowed": False,
                },
            }
            manifest["manifest_hash"] = _hash_json(manifest)
            manifest_file = _write_json(staging / "manifest.json", manifest)
            _verify_staging_size(staging, output_root, budget)
            os.replace(staging, run_directory)
            latest = {
                "schema_version": "portfolio-ml-current-restated-outcome-pointer.v1",
                "run_id": run_id,
                "manifest_path": f"runs/{run_id}/manifest.json",
                "manifest_sha256": manifest_file.sha256,
                "historical_pit_eligible": False,
                "formal_training_eligible": False,
            }
            _atomic_write_json(output_root / "latest_manifest.json", latest)
        return CurrentRestatedOutcomePublication(
            run_id=run_id,
            manifest_path=run_directory / "manifest.json",
            latest_manifest_path=output_root / "latest_manifest.json",
            manifest_sha256=manifest_file.sha256,
            raw_publication_manifest_sha256=publication_file.sha256,
            raw_dataset_manifest_sha256=dataset_file.sha256,
            feature_registry_sha256=registry_sha,
            observation_count=len(observations),
            feature_count=len(feature_registry),
            fold_count=len(folds),
            artifact_available_at=completed_at,
        )


def load_verified_current_restated_outcome_artifact(
    artifact_receipt_path: Path,
    *,
    expected_artifact_receipt_sha256: str,
    expected_raw_publication_manifest_sha256: str,
    expected_raw_dataset_manifest_sha256: str,
    expected_feature_registry_sha256: str,
    available_at_or_before: datetime,
    repository_root: Path | None = None,
) -> VerifiedCurrentRestatedOutcomeArtifact:
    """重驗 artifact／raw source pins，回傳不可變的 outcome-only 數值資料。"""

    consumer_freeze = _aware_datetime(available_at_or_before, "available_at_or_before")
    receipt_path = _resolve_research_input_path(
        artifact_receipt_path, repository_root=repository_root
    )
    receipt_file = _capture_file(receipt_path)
    if receipt_file.sha256 != _hash_pin(
        expected_artifact_receipt_sha256, "expected_artifact_receipt_sha256"
    ):
        raise CurrentRestatedOutcomeStoreError("artifact manifest actual-byte hash mismatch")
    manifest = _load_object(receipt_file.raw, "outcome artifact manifest")
    _verify_manifest_hash(manifest, label="outcome artifact manifest")
    if (
        manifest.get("schema_version") != OUTCOME_STORE_SCHEMA_V1
        or manifest.get("status") != OUTCOME_STORE_STATUS_READY
        or manifest.get("data_temporality") != "current_restated_research"
        or manifest.get("current_restated") is not True
        or manifest.get("historical_pit_eligible") is not False
        or manifest.get("formal_training_eligible") is not False
        or manifest.get("full_teacher_qualified") is not False
        or manifest.get("teacher_targets_present") is not False
        or manifest.get("training_claim") != "base_outcome_research_only"
    ):
        raise CurrentRestatedOutcomeStoreError("outcome artifact status/safety contract mismatch")
    outcome_cost_contract = _parse_outcome_cost_contract(
        manifest.get("outcome_cost_contract")
    )
    source_pins = _mapping(manifest.get("source_pins"), "source_pins")
    raw_publication_pin = _mapping(
        source_pins.get("raw_publication_manifest"), "raw publication pin"
    )
    raw_dataset_pin = _mapping(source_pins.get("raw_dataset_manifest"), "raw dataset pin")
    if raw_publication_pin.get("sha256") != _hash_pin(
        expected_raw_publication_manifest_sha256,
        "expected_raw_publication_manifest_sha256",
    ):
        raise CurrentRestatedOutcomeStoreError("raw publication manifest pin mismatch")
    if raw_dataset_pin.get("sha256") != _hash_pin(
        expected_raw_dataset_manifest_sha256,
        "expected_raw_dataset_manifest_sha256",
    ):
        raise CurrentRestatedOutcomeStoreError("raw dataset manifest pin mismatch")
    expected_registry_sha = _hash_pin(
        expected_feature_registry_sha256, "expected_feature_registry_sha256"
    )
    if _hash_pin(
        manifest.get("feature_registry_sha256"), "feature_registry_sha256"
    ) != expected_registry_sha:
        raise CurrentRestatedOutcomeStoreError("feature registry pin mismatch")
    if _hash_json(manifest.get("feature_registry")) != "sha256:" + expected_registry_sha:
        raise CurrentRestatedOutcomeStoreError("feature registry canonical bytes mismatch")

    artifact_available_at = _aware_datetime(
        manifest.get("artifact_available_at"), "artifact_available_at"
    )
    current_freeze = _aware_datetime(
        manifest.get("current_observation_freeze"), "current_observation_freeze"
    )
    source_observed_at = _aware_datetime(
        manifest.get("source_observed_at"), "source_observed_at"
    )
    dependency_verified_at = _aware_datetime(
        manifest.get("revision_dependencies_verified_at"),
        "revision_dependencies_verified_at",
    )
    raw_dependency_verified_at = _aware_datetime(
        manifest.get("raw_revision_dependencies_verified_at"),
        "raw_revision_dependencies_verified_at",
    )
    raw_generated_at = _aware_datetime(
        manifest.get("raw_generated_at"), "raw_generated_at"
    )
    if consumer_freeze < artifact_available_at:
        raise CurrentRestatedOutcomeStoreError(
            "consumer freeze precedes outcome artifact completion"
        )
    if min(current_freeze, dependency_verified_at, raw_generated_at) < source_observed_at:
        raise CurrentRestatedOutcomeStoreError("source clock ordering is invalid")
    if current_freeze < max(source_observed_at, dependency_verified_at, raw_generated_at):
        raise CurrentRestatedOutcomeStoreError("current-observation freeze precedes source custody")
    if (
        raw_dependency_verified_at < source_observed_at
        or dependency_verified_at < raw_dependency_verified_at
    ):
        raise CurrentRestatedOutcomeStoreError("raw/fresh dependency clocks are invalid")
    if artifact_available_at < current_freeze:
        raise CurrentRestatedOutcomeStoreError("artifact completion precedes current observation freeze")

    artifact_root = receipt_path.parent
    target_symbols = _string_sequence(manifest.get("target_symbols"), "target_symbols")
    if tuple(sorted(set(target_symbols))) != target_symbols:
        raise CurrentRestatedOutcomeStoreError("target_symbols are not canonical")
    benchmark_entity_id = manifest.get("benchmark_entity_id")
    if type(benchmark_entity_id) is not str or benchmark_entity_id != "TAIEX":
        raise CurrentRestatedOutcomeStoreError("outcome artifact benchmark identity is invalid")
    feature_registry = _parse_feature_registry(manifest.get("feature_registry"))
    raw_source_rows = _verify_raw_source_pins(
        source_pins,
        repository_root=repository_root,
        target_symbols=target_symbols,
        benchmark_entity_id=benchmark_entity_id,
    )
    source_context = _mapping(
        manifest.get("source_context_revalidation"), "source_context_revalidation"
    )
    source_context_revalidation_json = _canonical_json(source_context).encode("utf-8")
    if len(source_context_revalidation_json) > 4 * 1024 * 1024:
        raise CurrentRestatedOutcomeStoreError(
            "verified source-context proof exceeds its 4 MiB envelope bound"
        )
    source_context_bundle_sha = _hash_json(source_context)
    if source_context_bundle_sha != source_pins.get("revalidated_context_bundle_sha256"):
        raise CurrentRestatedOutcomeStoreError(
            "revalidated current-restated context bundle pin mismatch"
        )
    if (
        source_context.get("revision_dependency_bundle_sha256")
        != manifest.get("revision_dependency_bundle_sha256")
    ):
        raise CurrentRestatedOutcomeStoreError(
            "revision dependency bundle differs from the revalidated source context"
        )
    freshly_verified_context = _revalidate_source_context(source_context)
    _assert_context_stable(source_context, freshly_verified_context)
    if freshly_verified_context.revision_dependencies_verified_at < dependency_verified_at:
        raise CurrentRestatedOutcomeStoreError(
            "fresh source dependency verification clock moved backward"
        )
    rebuilt_price_rows, rebuilt_gap_rows = _price_inputs_from_raw_rows(
        raw_source_rows,
        target_symbols=target_symbols,
        benchmark_entity_id=benchmark_entity_id,
    )
    expected_labels, rebuilt_benchmark_calendar = _build_benchmark_outcomes(
        price_rows=rebuilt_price_rows,
        gap_rows=rebuilt_gap_rows,
        target_symbols=target_symbols,
        benchmark_entity_id=benchmark_entity_id,
        input_available_at=current_freeze,
    )
    calendar_text = _string_sequence(
        manifest.get("event_date_calendar"), "event_date_calendar"
    )
    event_date_calendar = tuple(
        _iso_date(item, "event_date_calendar") for item in calendar_text
    )
    if (
        not event_date_calendar
        or tuple(sorted(set(event_date_calendar))) != event_date_calendar
        or _hash_json([item.isoformat() for item in event_date_calendar])
        != manifest.get("event_date_calendar_sha256")
    ):
        raise CurrentRestatedOutcomeStoreError("event-date calendar order or hash is invalid")
    benchmark_calendar_text = _string_sequence(
        manifest.get("benchmark_event_date_calendar"),
        "benchmark_event_date_calendar",
    )
    benchmark_event_calendar = tuple(
        _iso_date(item, "benchmark_event_date_calendar")
        for item in benchmark_calendar_text
    )
    if (
        not benchmark_event_calendar
        or tuple(sorted(set(benchmark_event_calendar))) != benchmark_event_calendar
        or _hash_json([item.isoformat() for item in benchmark_event_calendar])
        != manifest.get("benchmark_event_date_calendar_sha256")
        or rebuilt_benchmark_calendar != benchmark_event_calendar
    ):
        raise CurrentRestatedOutcomeStoreError(
            "benchmark event calendar is incomplete, changed, or not source-backed"
        )
    arrays = _mapping(manifest.get("arrays"), "arrays")
    values = _read_array(artifact_root, arrays, "feature_values", dtype="<i8", repository_root=repository_root)
    missing = _read_array(artifact_root, arrays, "feature_missing_mask", dtype="u1", repository_root=repository_root)
    quality = _read_array(artifact_root, arrays, "feature_quality_blocked_mask", dtype="u1", repository_root=repository_root)
    stale = _read_array(artifact_root, arrays, "feature_staleness_mask", dtype="u1", repository_root=repository_root)
    labels = _read_array(artifact_root, arrays, "label_values", dtype="<i4", repository_root=repository_root)
    label_missing = _read_array(artifact_root, arrays, "label_missing_mask", dtype="u1", repository_root=repository_root)
    array_pins = _parse_array_pins(arrays, artifact_root=artifact_root, repository_root=repository_root)
    row_file_pin = _mapping(manifest.get("observations_metadata"), "observations_metadata")
    row_path = _resolve_pinned_artifact_file(
        artifact_root, row_file_pin, repository_root=repository_root
    )
    rows = _read_jsonl_rows(row_path, expected_count=_exact_int(manifest.get("observation_count"), "observation_count"))
    sample_count = len(rows)
    feature_count = len(feature_registry)
    if values.shape != (sample_count, feature_count):
        raise CurrentRestatedOutcomeStoreError("feature values array shape mismatch")
    for mask_array in (missing, quality, stale):
        if mask_array.shape != (sample_count, feature_count) or np.any(mask_array > 1):
            raise CurrentRestatedOutcomeStoreError("feature mask array shape/value mismatch")
    horizon_count = len(SUPPORTED_HORIZONS)
    metric_count = len(LABEL_METRICS)
    expected_label_shape = (sample_count, horizon_count, metric_count)
    if labels.shape != expected_label_shape or label_missing.shape != expected_label_shape:
        raise CurrentRestatedOutcomeStoreError("outcome label array shape mismatch")
    if np.any(label_missing > 1):
        raise CurrentRestatedOutcomeStoreError("label missing mask contains non-boolean bytes")
    observations = _rebuild_verified_observations(
        rows=rows,
        values=values,
        missing=missing,
        quality=quality,
        stale=stale,
        labels=labels,
        label_missing=label_missing,
        feature_registry=feature_registry,
        label_registry=tuple(str(item) for item in _string_sequence(manifest.get("label_registry"), "label_registry")),
        raw_source_rows=raw_source_rows,
        expected_labels=expected_labels,
        feature_registry_sha256="sha256:" + expected_registry_sha,
        source_context_bundle_sha256=source_context_bundle_sha,
        benchmark_entity_id=benchmark_entity_id,
        current_freeze=current_freeze,
        artifact_available_at=artifact_available_at,
    )
    folds = _parse_folds(
        _mapping(manifest.get("fold_policy"), "fold_policy"),
        observations,
        event_date_calendar=event_date_calendar,
        benchmark_event_calendar=benchmark_event_calendar,
        target_symbols=target_symbols,
    )
    if len(folds) < 4:
        raise CurrentRestatedOutcomeStoreError("verified artifact has fewer than four folds")
    return VerifiedCurrentRestatedOutcomeArtifact(
        status=OUTCOME_STORE_STATUS_READY,
        observations=observations,
        feature_registry=feature_registry,
        feature_registry_sha256=expected_registry_sha,
        labels_registry=tuple(LABEL_METRICS),
        outcome_cost_contract=outcome_cost_contract,
        raw_publication_manifest_path=str(raw_publication_pin["path"]),
        raw_publication_manifest_bytes_sha256=expected_raw_publication_manifest_sha256.removeprefix("sha256:"),
        raw_dataset_manifest_path=str(raw_dataset_pin["path"]),
        raw_dataset_manifest_bytes_sha256=expected_raw_dataset_manifest_sha256.removeprefix("sha256:"),
        artifact_receipt_path=str(receipt_file.path),
        artifact_receipt_bytes_sha256=receipt_file.sha256,
        run_id=str(manifest["run_id"]),
        array_pins=array_pins,
        raw_shard_pins=_parse_raw_shard_pins(source_pins.get("raw_shards")),
        source_database_path=str(source_context["source_database_path"]),
        source_database_sha256=str(source_context["source_database_sha256"]),
        snapshot_database_path=str(source_context["snapshot_database_path"]),
        snapshot_database_sha256=str(source_context["snapshot_database_sha256"]),
        snapshot_receipt_path=str(source_context["snapshot_receipt_path"]),
        snapshot_receipt_sha256=str(source_context["snapshot_receipt_sha256"]),
        source_observed_at=source_observed_at,
        revision_dependencies_verified_at=dependency_verified_at,
        raw_revision_dependencies_verified_at=raw_dependency_verified_at,
        revision_dependency_bundle_sha256=str(manifest["revision_dependency_bundle_sha256"]),
        raw_generated_at=raw_generated_at,
        current_observation_freeze=current_freeze,
        artifact_available_at=artifact_available_at,
        target_symbols=target_symbols,
        benchmark_entity_id=benchmark_entity_id,
        horizons=SUPPORTED_HORIZONS,
        event_date_calendar=event_date_calendar,
        event_date_calendar_sha256=str(manifest["event_date_calendar_sha256"]),
        folds=folds,
        source_context_revalidation_json=source_context_revalidation_json,
        source_context_revalidation_sha256=source_context_bundle_sha.removeprefix("sha256:"),
    )


def _read_raw_shards(
    *,
    raw_manifest_path: Path,
    raw_manifest: Mapping[str, Any],
    publication_manifest: Mapping[str, Any],
    feature_registry: tuple[CurrentRestatedOutcomeFeatureV1, ...],
    target_symbols: tuple[str, ...],
    benchmark_entity_id: str,
    raw_generated_at: datetime,
    source_observed_at: datetime,
    dependency_verified_at: datetime,
    max_raw_rows: int,
    repository_root: Path | None,
) -> tuple[
    tuple[CurrentRestatedOutcomeRawPinV1, ...],
    dict[tuple[str, date], _SampleDraft],
    list[tuple[object, ...]],
    list[tuple[object, ...]],
    dict[tuple[str, str, str, date], dict[str, Any]],
    str,
]:
    feature_ids_by_role: dict[tuple[str, str], str] = {
        (item.role, item.source_feature_id): item.feature_id
        for item in feature_registry
    }
    value_registry = _feature_value_registry(raw_manifest)
    raw_context = _mapping(publication_manifest.get("source_context"), "source_context")
    expected_context_hash = _hash_json(raw_context)
    target_set = set(target_symbols)
    drafts: dict[tuple[str, date], _SampleDraft] = {}
    benchmark_rows: dict[date, list[tuple[object, str, str, str]]] = {}
    raw_source_rows: dict[tuple[str, str, str, date], dict[str, Any]] = {}
    price_rows: list[tuple[object, ...]] = []
    gap_rows: list[tuple[object, ...]] = []
    seen_price_keys: set[tuple[str, str, str]] = set()
    source_digest = hashlib.sha256()
    pins: list[CurrentRestatedOutcomeRawPinV1] = []
    total_rows = 0
    total_values = 0
    publication_root = raw_manifest_path.parent.parent.resolve(strict=True)
    raw_shards = _mapping_sequence(raw_manifest.get("shards"), "shards")
    if _exact_int(raw_manifest.get("shard_count"), "raw.shard_count") != len(raw_shards):
        raise CurrentRestatedOutcomeStoreError("raw shard_count does not match shard inventory")
    seen_years: set[int] = set()
    for index, raw_shard in enumerate(sorted(raw_shards, key=lambda item: _exact_int(item.get("year"), "shard.year"))):
        year = _exact_int(raw_shard.get("year"), "shard.year")
        if year in seen_years:
            raise CurrentRestatedOutcomeStoreError("raw manifest repeats an annual shard")
        seen_years.add(year)
        relative = raw_shard.get("path")
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise CurrentRestatedOutcomeStoreError("raw shard path must be a relative POSIX path")
        relative_path = PurePosixPath(relative)
        if relative_path.is_absolute() or any(part in {"", ".", ".."} for part in relative_path.parts):
            raise CurrentRestatedOutcomeStoreError("raw shard path contains an unsafe component")
        shard_path = (publication_root / relative).resolve(strict=True)
        if not shard_path.is_relative_to(publication_root):
            raise CurrentRestatedOutcomeStoreError("raw shard path escapes its publication")
        shard_path = _resolve_research_input_path(
            shard_path, repository_root=repository_root
        )
        info_before = shard_path.stat()
        if not stat.S_ISREG(info_before.st_mode):
            raise CurrentRestatedOutcomeStoreError("raw shard is not a regular file")
        compressed_digest = hashlib.sha256()
        content_digest = hashlib.sha256()
        shard_rows = 0
        shard_values = 0
        shard_source_tables: set[str] = set()
        pin_role = f"raw_shard_year_{year}"
        try:
            with shard_path.open("rb") as compressed_stream:
                for block in iter(lambda: compressed_stream.read(1024 * 1024), b""):
                    compressed_digest.update(block)
            compressed_sha = compressed_digest.hexdigest()
            expected_compressed = _hash_pin(raw_shard.get("compressed_sha256"), "shard.compressed_sha256")
            if compressed_sha != expected_compressed:
                raise CurrentRestatedOutcomeStoreError("raw shard compressed SHA-256 mismatch")
            with gzip.open(shard_path, "rb") as stream:
                for line_number, raw_line in enumerate(stream, start=1):
                    if not raw_line.strip():
                        continue
                    content_digest.update(raw_line)
                    source_digest.update(raw_line)
                    row = _load_object(raw_line, f"raw shard row {year}:{line_number}")
                    total_rows += 1
                    shard_rows += 1
                    if total_rows > max_raw_rows:
                        raise CurrentRestatedOutcomeStoreError("raw shard row limit exceeded")
                    shard_values += _validate_raw_observation(
                        row=row,
                        dataset_id=str(raw_manifest["dataset_id"]),
                        feature_registry=value_registry,
                        expected_context_hash=expected_context_hash,
                        raw_generated_at=raw_generated_at,
                        source_observed_at=source_observed_at,
                        dependency_verified_at=dependency_verified_at,
                    )
                    source_table = str(row["source_table"])
                    source_id = row.get("source_id")
                    entity_id = str(row["entity_id"])
                    if type(source_id) is not str or not source_id:
                        raise CurrentRestatedOutcomeStoreError(
                            "raw source row source_id must be non-empty text"
                        )
                    event_date = _iso_date(row.get("event_date"), "event_date")
                    if event_date.year != year:
                        raise CurrentRestatedOutcomeStoreError(
                            "raw annual shard contains an event from another year"
                        )
                    shard_source_tables.add(source_table)
                    values = _value_map(row["values"])
                    source_row_hash = _hash_pin(row.get("source_row_hash"), "source_row_hash")
                    symbol = entity_id.split("|", 1)[0]
                    selected_source_row = (
                        source_table == "daily_prices" and symbol in target_set
                    ) or (
                        source_table == "technical_indicators" and symbol in target_set
                    ) or (
                        source_table == "market_indices"
                        and entity_id == benchmark_entity_id
                    )
                    if selected_source_row:
                        source_key = (source_table, source_id, entity_id, event_date)
                        if source_key in raw_source_rows:
                            raise CurrentRestatedOutcomeStoreError(
                                "raw source repeats a selected table/source/entity/date identity"
                            )
                        raw_source_rows[source_key] = row
                    if source_table == "daily_prices":
                        if symbol not in target_set:
                            continue
                        if source_id == "derived:daily_prices.ohlc":
                            current_value_available_at = _aware_datetime(
                                row.get("current_value_available_at"),
                                "derived.current_value_available_at",
                            )
                            if not _is_reviewed_daily_technical_source_row(
                                row=row,
                                current_value_available_at=current_value_available_at,
                            ):
                                raise CurrentRestatedOutcomeStoreError(
                                    "daily-derived source row is outside the pinned ATR/ADX contract"
                                )
                            draft = drafts.setdefault(
                                (symbol, event_date),
                                _new_sample_draft(symbol, event_date, feature_registry),
                            )
                            _merge_stock_features(
                                draft=draft,
                                values=row["values"],
                                feature_ids_by_role=feature_ids_by_role,
                                row_hash=source_row_hash,
                                source_table=source_table,
                                source_id=source_id,
                                entity_id=entity_id,
                                event_date=event_date,
                            )
                            continue
                        if source_id != "sqlite.daily_prices":
                            raise CurrentRestatedOutcomeStoreError(
                                "daily-price label input has an unsupported source identity"
                            )
                        price_record = label_math._price_record(
                            table_name="daily_prices",
                            entity_key=symbol,
                            event_at=event_date.isoformat(),
                            available_at="",
                            source_row_hash=source_row_hash,
                            values=_as_legacy_price_scale(values),
                        )
                        if price_record is not None:
                            key = ("stock", symbol, event_date.isoformat())
                            if key in seen_price_keys:
                                raise CurrentRestatedOutcomeStoreError("duplicate stock price event in raw shards")
                            seen_price_keys.add(key)
                            price_rows.append(price_record)
                        contract = row.get("price_availability_contract")
                        if contract is not None:
                            contract_map = _mapping(contract, "price_availability_contract")
                            contract_symbol, contract_date, _reason = validate_price_unavailable_research_contract(contract_map)
                            if contract_symbol != symbol or contract_date != event_date.isoformat():
                                raise CurrentRestatedOutcomeStoreError("price availability contract identity mismatch")
                            gap_rows.append(("stock", symbol, event_date.isoformat(), _hash_json(contract_map)))
                        draft = drafts.setdefault(
                            (symbol, event_date),
                            _new_sample_draft(symbol, event_date, feature_registry),
                        )
                        _merge_stock_features(
                            draft=draft,
                            values=row["values"],
                            feature_ids_by_role=feature_ids_by_role,
                            row_hash=source_row_hash,
                            source_table=source_table,
                            source_id=source_id,
                            entity_id=entity_id,
                            event_date=event_date,
                        )
                    elif source_table == "market_indices" and entity_id == benchmark_entity_id:
                        price_record = label_math._price_record(
                            table_name="market_indices",
                            entity_key=benchmark_entity_id,
                            event_at=event_date.isoformat(),
                            available_at="",
                            source_row_hash=source_row_hash,
                            values=_as_legacy_price_scale(values),
                        )
                        if price_record is not None:
                            key = ("market", benchmark_entity_id, event_date.isoformat())
                            if key in seen_price_keys:
                                raise CurrentRestatedOutcomeStoreError("duplicate benchmark event in raw shards")
                            seen_price_keys.add(key)
                            price_rows.append(price_record)
                        else:
                            # Keep a benchmark session on the true event calendar
                            # even when both open and close are unavailable.
                            key = ("market", benchmark_entity_id, event_date.isoformat())
                            if key in seen_price_keys:
                                raise CurrentRestatedOutcomeStoreError("duplicate benchmark event in raw shards")
                            seen_price_keys.add(key)
                            price_rows.append(
                                (
                                    "market",
                                    benchmark_entity_id,
                                    event_date.isoformat(),
                                    "",
                                    None,
                                    None,
                                    None,
                                    None,
                                    None,
                                    None,
                                    None,
                                    None,
                                    source_row_hash,
                                )
                            )
                        benchmark_rows.setdefault(event_date, []).append(
                            (row["values"], source_row_hash, source_id, entity_id)
                        )
                    elif source_table == "technical_indicators":
                        if symbol not in target_set:
                            continue
                        draft = drafts.setdefault(
                            (symbol, event_date),
                            _new_sample_draft(symbol, event_date, feature_registry),
                        )
                        _merge_stock_features(
                            draft=draft,
                            values=row["values"],
                            feature_ids_by_role=feature_ids_by_role,
                            row_hash=source_row_hash,
                            source_table=source_table,
                            source_id=source_id,
                            entity_id=entity_id,
                            event_date=event_date,
                        )
            info_after = shard_path.stat()
        except (OSError, EOFError, gzip.BadGzipFile) as exc:
            raise CurrentRestatedOutcomeStoreError(f"raw shard cannot be read: {shard_path}") from exc
        content_sha = "sha256:" + content_digest.hexdigest()
        if content_sha != "sha256:" + _hash_pin(raw_shard.get("content_sha256"), "shard.content_sha256"):
            raise CurrentRestatedOutcomeStoreError("raw shard content SHA-256 mismatch")
        if compressed_sha != expected_compressed:
            raise CurrentRestatedOutcomeStoreError("raw shard compressed SHA-256 changed")
        if (
            info_before.st_size != info_after.st_size
            or info_before.st_mtime_ns != info_after.st_mtime_ns
            or shard_path.stat().st_size != info_after.st_size
        ):
            raise CurrentRestatedOutcomeStoreError("raw shard changed during capture")
        if shard_rows != _exact_int(raw_shard.get("row_count"), "shard.row_count"):
            raise CurrentRestatedOutcomeStoreError("raw shard row_count mismatch")
        if info_after.st_size != _exact_int(raw_shard.get("compressed_bytes"), "shard.compressed_bytes"):
            raise CurrentRestatedOutcomeStoreError("raw shard compressed byte count mismatch")
        if shard_values != _exact_int(raw_shard.get("feature_value_count"), "shard.feature_value_count"):
            raise CurrentRestatedOutcomeStoreError("raw shard feature_value_count mismatch")
        if tuple(sorted(shard_source_tables)) != _string_sequence(
            raw_shard.get("source_tables"), "shard.source_tables"
        ):
            raise CurrentRestatedOutcomeStoreError("raw shard source-table inventory mismatch")
        total_values += shard_values
        pins.append(
            CurrentRestatedOutcomeRawPinV1(
                role_id=pin_role,
                path=str(shard_path),
                bytes=info_after.st_size,
                mtime_ns=info_after.st_mtime_ns,
                sha256=compressed_sha,
                content_sha256=content_sha,
                row_count=shard_rows,
            )
        )
    if total_rows != _exact_int(raw_manifest.get("row_count"), "raw.row_count"):
        raise CurrentRestatedOutcomeStoreError("raw dataset row_count does not match annual shards")
    if total_values != _exact_int(raw_manifest.get("feature_value_count"), "raw.feature_value_count"):
        raise CurrentRestatedOutcomeStoreError("raw dataset feature_value_count does not match annual shards")
    if not drafts:
        raise InsufficientMatureCurrentRestatedHistoryError("raw annual shards contain no target stock observations")
    for (symbol, event_day), draft in drafts.items():
        if event_day not in benchmark_rows:
            raise CurrentRestatedOutcomeStoreError(
                f"target stock date has no pinned benchmark context: {symbol} {event_day.isoformat()}"
            )
        for benchmark_feature_values, row_hash, source_id, entity_id in benchmark_rows[event_day]:
            _merge_benchmark_features(
                draft=draft,
                values=benchmark_feature_values,
                feature_ids_by_role=feature_ids_by_role,
                row_hash=row_hash,
                source_id=source_id,
                entity_id=entity_id,
                event_date=event_day,
            )
    return (
        tuple(pins),
        drafts,
        price_rows,
        gap_rows,
        raw_source_rows,
        "sha256:" + source_digest.hexdigest(),
    )


def _build_benchmark_outcomes(
    *,
    price_rows: Sequence[tuple[object, ...]],
    gap_rows: Sequence[tuple[object, ...]],
    target_symbols: tuple[str, ...],
    benchmark_entity_id: str,
    input_available_at: datetime,
) -> tuple[
    dict[tuple[str, date], tuple[CurrentRestatedOutcomeLabelV1, ...]],
    tuple[date, ...],
]:
    _outcome_cost_contract_payload()
    actual_benchmark_calendar = tuple(
        sorted(
            {
                _iso_date(row[2], "benchmark.event_date")
                for row in price_rows
                if row[0] == "market" and row[1] == benchmark_entity_id
            }
        )
    )
    if len(actual_benchmark_calendar) <= max(SUPPORTED_HORIZONS):
        raise InsufficientMatureCurrentRestatedHistoryError(
            "pinned benchmark calendar is too short for outcome horizons"
        )
    previous_event_by_source_date = {
        actual_benchmark_calendar[index]: actual_benchmark_calendar[index - 1]
        for index in range(1, len(actual_benchmark_calendar))
    }
    shifted_to_actual_event_date = {
        shifted: source for source, shifted in previous_event_by_source_date.items()
    }
    shifted_price_rows: list[tuple[object, ...]] = []
    for row in price_rows:
        event_day = _iso_date(row[2], "price.event_date")
        shifted_event_day = previous_event_by_source_date.get(event_day)
        if shifted_event_day is None:
            continue
        shifted_price_rows.append((*row[:2], shifted_event_day.isoformat(), *row[3:]))
    shifted_gap_rows: list[tuple[object, ...]] = []
    for row in gap_rows:
        event_day = _iso_date(row[2], "price_gap.event_date")
        shifted_event_day = previous_event_by_source_date.get(event_day)
        if shifted_event_day is None:
            continue
        shifted_gap_rows.append((*row[:2], shifted_event_day.isoformat(), *row[3:]))
    shifted_price_by_key = {
        (str(row[0]), str(row[1]), str(row[2])): row
        for row in shifted_price_rows
    }
    if len(shifted_price_by_key) != len(shifted_price_rows):
        raise CurrentRestatedOutcomeStoreError("shifted label price inputs contain duplicate keys")
    shifted_calendar = tuple(
        day.isoformat() for day in actual_benchmark_calendar[:-1]
    )
    shifted_index_by_date = {day: index for index, day in enumerate(shifted_calendar)}
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    label_math._initialize_spool(connection)
    available = input_available_at.isoformat()
    normalized_price_rows = [
        (*row[:3], available, *row[4:]) for row in shifted_price_rows
    ]
    label_math._insert_prices(connection, normalized_price_rows)
    label_math._insert_price_availability_gaps(connection, shifted_gap_rows)
    try:
        label_math._build_label_spool(
            connection=connection,
            benchmark_entity_id=benchmark_entity_id,
            cutoff=input_available_at,
            horizons=SUPPORTED_HORIZONS,
            batch_size=2_048,
        )
        expected_symbols = set(target_symbols)
        actual_symbols = {
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT entity_key FROM prices WHERE scope='stock'"
            )
        }
        if actual_symbols != expected_symbols:
            raise CurrentRestatedOutcomeStoreError("raw stock price universe does not match explicit target symbols")
        results: dict[tuple[str, date], list[CurrentRestatedOutcomeLabelV1]] = {}
        for row in connection.execute(
            "SELECT * FROM labels ORDER BY symbol, decision_date, horizon"
        ):
            if str(row["symbol"]) not in expected_symbols:
                continue
            horizon = _exact_int(row["horizon"], "label.horizon")
            shifted_entry_day = str(row["decision_date"])
            shifted_end_day = str(row["horizon_end_date"])
            stock_entry = shifted_price_by_key.get(
                ("stock", str(row["symbol"]), shifted_entry_day)
            )
            stock_exit = shifted_price_by_key.get(
                ("stock", str(row["symbol"]), shifted_end_day)
            )
            benchmark_entry = shifted_price_by_key.get(
                ("market", benchmark_entity_id, shifted_entry_day)
            )
            benchmark_exit = shifted_price_by_key.get(
                ("market", benchmark_entity_id, shifted_end_day)
            )
            if any(item is None for item in (stock_entry, stock_exit, benchmark_entry, benchmark_exit)):
                raise CurrentRestatedOutcomeStoreError(
                    "label math output is missing a pinned T+1 stock or benchmark price"
                )
            assert stock_entry is not None
            assert stock_exit is not None
            assert benchmark_entry is not None
            assert benchmark_exit is not None
            entry_date = shifted_to_actual_event_date.get(
                date.fromisoformat(shifted_entry_day)
            )
            end_date = shifted_to_actual_event_date.get(
                date.fromisoformat(shifted_end_day)
            )
            if entry_date is None or end_date is None:
                raise CurrentRestatedOutcomeStoreError(
                    "T+1 entry or label end cannot map to the true source calendar"
                )
            event_day = date.fromisoformat(shifted_entry_day)
            event_index = shifted_index_by_date.get(shifted_entry_day)
            if event_index is None or event_index + horizon >= len(actual_benchmark_calendar):
                raise CurrentRestatedOutcomeStoreError(
                    "label event cannot map to a complete true benchmark calendar window"
                )
            expected_entry_date = actual_benchmark_calendar[event_index + 1]
            expected_end_date = actual_benchmark_calendar[event_index + horizon]
            if entry_date != expected_entry_date or end_date != expected_end_date:
                raise CurrentRestatedOutcomeStoreError(
                    "shared label spool did not use next-session entry and horizon-session exit"
                )
            stock_entry_open = _price_component(stock_entry, 4, "stock entry open")
            stock_exit_close = _price_component(stock_exit, 10, "stock exit close")
            benchmark_entry_open = _price_component(
                benchmark_entry, 4, "benchmark entry open"
            )
            benchmark_exit_close = _price_component(
                benchmark_exit, 10, "benchmark exit close"
            )
            stock_return = label_math._return_bp(
                entry_int=stock_entry_open[0],
                entry_scale=10**stock_entry_open[1],
                exit_int=stock_exit_close[0],
                exit_scale=10**stock_exit_close[1],
            )
            benchmark_return = label_math._return_bp(
                entry_int=benchmark_entry_open[0],
                entry_scale=10**benchmark_entry_open[1],
                exit_int=benchmark_exit_close[0],
                exit_scale=10**benchmark_exit_close[1],
            )
            benchmark_excess = _exact_signed_int32(
                row["excess_return_bp"], "excess_return_bp"
            )
            _assert_outcome_cost_difference(
                stock_return_bp=stock_return,
                benchmark_return_bp=benchmark_return,
                benchmark_excess_return_bp=benchmark_excess,
            )
            actual_path_dates = actual_benchmark_calendar[
                event_index + 1 : event_index + horizon + 1
            ]
            shifted_path_dates = tuple(
                previous_event_by_source_date[item].isoformat()
                for item in actual_path_dates
            )
            stock_path_rows = tuple(
                shifted_price_by_key.get(
                    ("stock", str(row["symbol"]), shifted_day)
                )
                for shifted_day in shifted_path_dates
            )
            benchmark_path_rows = tuple(
                shifted_price_by_key.get(("market", benchmark_entity_id, shifted_day))
                for shifted_day in shifted_path_dates
            )
            if (
                len(stock_path_rows) != horizon
                or len(benchmark_path_rows) != horizon
                or any(item is None for item in stock_path_rows)
                or any(item is None for item in benchmark_path_rows)
            ):
                raise CurrentRestatedOutcomeStoreError(
                    "label source-hash path is incomplete for its true session horizon"
                )
            concrete_stock_path = tuple(
                item for item in stock_path_rows if item is not None
            )
            concrete_benchmark_path = tuple(
                item for item in benchmark_path_rows if item is not None
            )
            stock_path_hashes = tuple(
                "sha256:" + _hash_pin(item[12], "stock_path.source_row_hash")
                for item in concrete_stock_path
            )
            benchmark_path_hashes = tuple(
                "sha256:" + _hash_pin(item[12], "benchmark_path.source_row_hash")
                for item in concrete_benchmark_path
            )
            all_input_hashes = tuple(
                sorted(set((*stock_path_hashes, *benchmark_path_hashes)))
            )
            source_hash = _hash_pin(row["source_hash"], "label.source_hash")
            label = CurrentRestatedOutcomeLabelV1(
                horizon=horizon,
                next_entry_date=entry_date,
                horizon_end_date=end_date,
                stock_return_bp=_exact_signed_int32(stock_return, "stock_return_bp"),
                benchmark_return_bp=_exact_signed_int32(benchmark_return, "benchmark_return_bp"),
                benchmark_excess_return_bp=benchmark_excess,
                stock_next_entry_open_value_int=stock_entry_open[0],
                stock_next_entry_open_decimal_exponent=stock_entry_open[1],
                stock_exit_close_value_int=stock_exit_close[0],
                stock_exit_close_decimal_exponent=stock_exit_close[1],
                benchmark_next_entry_open_value_int=benchmark_entry_open[0],
                benchmark_next_entry_open_decimal_exponent=benchmark_entry_open[1],
                benchmark_exit_close_value_int=benchmark_exit_close[0],
                benchmark_exit_close_decimal_exponent=benchmark_exit_close[1],
                stock_entry_source_hash="sha256:" + _hash_pin(stock_entry[12], "stock_entry.source_row_hash"),
                stock_exit_source_hash="sha256:" + _hash_pin(stock_exit[12], "stock_exit.source_row_hash"),
                benchmark_entry_source_hash="sha256:" + _hash_pin(benchmark_entry[12], "benchmark_entry.source_row_hash"),
                benchmark_exit_source_hash="sha256:" + _hash_pin(benchmark_exit[12], "benchmark_exit.source_row_hash"),
                stock_path_source_hashes=stock_path_hashes,
                benchmark_path_source_hashes=benchmark_path_hashes,
                source_row_hashes=all_input_hashes,
                mae_loss_bp=_exact_signed_int32(row["mae_loss_bp"], "mae_loss_bp"),
                mfe_gain_bp=_exact_signed_int32(row["mfe_gain_bp"], "mfe_gain_bp"),
                realized_volatility_bp=_exact_signed_int32(
                    row["realized_volatility_bp"], "realized_volatility_bp"
                ),
                max_drawdown_bp=_exact_signed_int32(
                    row["max_drawdown_bp"], "max_drawdown_bp"
                ),
                tail_loss_bp=_exact_signed_int32(row["tail_loss_bp"], "tail_loss_bp"),
                downside_observed=_strict_sql_bool(row["downside_observed"], "downside_observed"),
                fill_feasible_observed=_strict_sql_bool(
                    row["fill_feasible_observed"], "fill_feasible_observed"
                ),
                inputs_available_at=_aware_datetime(row["available_at"], "label.available_at"),
                source_hash="sha256:" + source_hash,
                label_math_source_hash="sha256:" + source_hash,
            )
            key = (str(row["symbol"]), event_day)
            results.setdefault(key, []).append(label)
        return (
            {
                key: tuple(sorted(items, key=lambda item: item.horizon))
                for key, items in results.items()
            },
            actual_benchmark_calendar,
        )
    finally:
        connection.close()


def _materialize_observations(
    *,
    drafts: Mapping[tuple[str, date], _SampleDraft],
    feature_registry: tuple[CurrentRestatedOutcomeFeatureV1, ...],
    benchmark_entity_id: str,
    labels_by_key: Mapping[tuple[str, date], tuple[CurrentRestatedOutcomeLabelV1, ...]],
    current_value_available_at: datetime,
    source_context: revision_gate.VerifiedCurrentRestatedSourceContext,
    registry_sha256: str,
) -> tuple[tuple[CurrentRestatedOutcomeObservationV1, ...], tuple[dict[str, Any], ...]]:
    feature_ids = tuple(item.feature_id for item in feature_registry)
    observations: list[CurrentRestatedOutcomeObservationV1] = []
    metadata_rows: list[dict[str, Any]] = []
    context_payload = raw_exporter._current_restated_context_payload(source_context)
    context_hash = _hash_json(context_payload)
    for key in sorted(drafts, key=lambda item: (item[1], item[0])):
        draft = drafts[key]
        values = dict(draft.values)
        missing = dict(draft.missing)
        quality = dict(draft.quality_blocked)
        stale = dict(draft.stale)
        if not any(
            item.role == "benchmark" and item.feature_id in values
            for item in feature_registry
        ):
            raise CurrentRestatedOutcomeStoreError(
                "benchmark feature row is missing for a stock sample"
            )
        for feature_id in feature_ids:
            values.setdefault(feature_id, None)
            missing.setdefault(feature_id, True)
            quality.setdefault(feature_id, False)
            stale.setdefault(feature_id, False)
        ordered_values = tuple(_exact_signed_int64(values[item], f"feature {item}") if values[item] is not None else 0 for item in feature_ids)
        ordered_missing = tuple(bool(missing[item]) for item in feature_ids)
        ordered_quality = tuple(bool(quality[item]) for item in feature_ids)
        ordered_stale = tuple(bool(stale[item]) for item in feature_ids)
        if any(not flag and values[item] is None for item, flag in zip(feature_ids, ordered_missing)):
            raise CurrentRestatedOutcomeStoreError("null feature lacks a missing mask")
        labels = labels_by_key.get(key, ())
        source_hash = _hash_json(
            {
                "schema_version": "current-restated-outcome-sample-identity.v1",
                "symbol": draft.symbol,
                "event_date": draft.event_date.isoformat(),
                "benchmark_entity_id": benchmark_entity_id,
                "source_rows": [
                    _source_row_payload(item)
                    for item in sorted(
                        draft.source_rows,
                        key=lambda item: (
                            item.source_table,
                            item.source_id,
                            item.entity_id,
                            item.event_date,
                        ),
                    )
                ],
                "feature_registry_sha256": registry_sha256,
                "source_context_bundle_sha256": context_hash,
            }
        )
        sample_id = _hash_json(
            {"symbol": draft.symbol, "event_date": draft.event_date.isoformat(), "source_row_identity_hash": source_hash}
        )
        observation = CurrentRestatedOutcomeObservationV1(
            sample_id=sample_id,
            symbol=draft.symbol,
            event_date=draft.event_date,
            feature_values=ordered_values,
            missing_mask=ordered_missing,
            quality_blocked_mask=ordered_quality,
            staleness_mask=ordered_stale,
            source_row_identity_hash=source_hash,
            source_rows=tuple(
                sorted(
                    draft.source_rows,
                    key=lambda item: (
                        item.source_table,
                        item.source_id,
                        item.entity_id,
                        item.event_date,
                    ),
                )
            ),
            current_value_available_at=current_value_available_at,
            labels=labels,
        )
        observations.append(observation)
        metadata_rows.append(
            {
                "sample_id": sample_id,
                "symbol": draft.symbol,
                "event_date": draft.event_date.isoformat(),
                "event_reference_only": True,
                "original_source_available_at": None,
                "current_value_available_at": current_value_available_at.isoformat(),
                "source_observed_at": source_context.source_observed_at.isoformat(),
                "revision_dependencies_verified_at": source_context.revision_dependencies_verified_at.isoformat(),
                "source_context_bundle_sha256": context_hash,
                "feature_registry_sha256": registry_sha256,
                "source_row_identity_hash": source_hash,
                "source_rows": [
                    _source_row_payload(item)
                    for item in sorted(
                        draft.source_rows,
                        key=lambda item: (
                            item.source_table,
                            item.source_id,
                            item.entity_id,
                            item.event_date,
                        ),
                    )
                ],
                "source_row_hashes": sorted(
                    {item.source_row_hash for item in draft.source_rows}
                ),
                "labels": [
                    {
                        "horizon": item.horizon,
                        "next_entry_date": item.next_entry_date.isoformat(),
                        "horizon_end_date": item.horizon_end_date.isoformat(),
                        "stock_return_bp": item.stock_return_bp,
                        "benchmark_return_bp": item.benchmark_return_bp,
                        "benchmark_excess_return_bp": item.benchmark_excess_return_bp,
                        "mae_loss_bp": item.mae_loss_bp,
                        "mfe_gain_bp": item.mfe_gain_bp,
                        "realized_volatility_bp": item.realized_volatility_bp,
                        "max_drawdown_bp": item.max_drawdown_bp,
                        "tail_loss_bp": item.tail_loss_bp,
                        "downside_observed": item.downside_observed,
                        "fill_feasible_observed": item.fill_feasible_observed,
                        "stock_next_entry_open_value_int": item.stock_next_entry_open_value_int,
                        "stock_next_entry_open_decimal_exponent": item.stock_next_entry_open_decimal_exponent,
                        "stock_exit_close_value_int": item.stock_exit_close_value_int,
                        "stock_exit_close_decimal_exponent": item.stock_exit_close_decimal_exponent,
                        "benchmark_next_entry_open_value_int": item.benchmark_next_entry_open_value_int,
                        "benchmark_next_entry_open_decimal_exponent": item.benchmark_next_entry_open_decimal_exponent,
                        "benchmark_exit_close_value_int": item.benchmark_exit_close_value_int,
                        "benchmark_exit_close_decimal_exponent": item.benchmark_exit_close_decimal_exponent,
                        "stock_entry_source_hash": item.stock_entry_source_hash,
                        "stock_exit_source_hash": item.stock_exit_source_hash,
                        "benchmark_entry_source_hash": item.benchmark_entry_source_hash,
                        "benchmark_exit_source_hash": item.benchmark_exit_source_hash,
                        "stock_path_source_hashes": list(item.stock_path_source_hashes),
                        "benchmark_path_source_hashes": list(item.benchmark_path_source_hashes),
                        "source_row_hashes": list(item.source_row_hashes),
                        "inputs_available_at": item.inputs_available_at.isoformat(),
                        "source_hash": item.source_hash,
                        "label_math_source_hash": item.label_math_source_hash,
                    }
                    for item in labels
                ],
            }
        )
    return tuple(observations), tuple(metadata_rows)


def _build_research_folds(
    *,
    observations: tuple[CurrentRestatedOutcomeObservationV1, ...],
    minimum_train_dates: int,
    test_date_count: int,
    purge_trading_days: int,
    embargo_trading_days: int,
    benchmark_event_calendar: tuple[date, ...],
    target_symbols: tuple[str, ...],
) -> tuple[tuple[date, ...], tuple[CurrentRestatedOutcomeFoldV1, ...]]:
    by_symbol_date = {(row.symbol, row.event_date): row for row in observations}
    complete_dates_by_symbol: dict[str, set[date]] = {}
    for row in observations:
        if tuple(item.horizon for item in row.labels) == SUPPORTED_HORIZONS:
            complete_dates_by_symbol.setdefault(row.symbol, set()).add(row.event_date)
    if set(complete_dates_by_symbol) != set(target_symbols):
        raise InsufficientMatureCurrentRestatedHistoryError("no fully mature outcome rows")
    calendar = tuple(benchmark_event_calendar)
    if (
        not calendar
        or tuple(sorted(set(calendar))) != calendar
        or not set.union(*(dates for dates in complete_dates_by_symbol.values())).issubset(
            set(calendar)
        )
    ):
        raise CurrentRestatedOutcomeStoreError(
            "global event calendar is not the ordered, complete pinned benchmark calendar"
        )
    complete_dates = set.union(*(dates for dates in complete_dates_by_symbol.values()))
    windows: list[CurrentRestatedOutcomeFoldV1] = []
    start_index = minimum_train_dates + purge_trading_days
    while start_index + test_date_count <= len(calendar):
        train_indices = tuple(range(0, start_index - purge_trading_days))
        test_indices = tuple(range(start_index, start_index + test_date_count))
        train_dates = tuple(calendar[index] for index in train_indices)
        test_dates = tuple(calendar[index] for index in test_indices)
        if not set(test_dates).issubset(complete_dates):
            start_index += test_date_count + embargo_trading_days
            continue
        train_rows = tuple(
            by_symbol_date[(symbol, event_day)]
            for event_day in train_dates
            for symbol in target_symbols
            if (symbol, event_day) in by_symbol_date
            and tuple(
                item.horizon for item in by_symbol_date[(symbol, event_day)].labels
            )
            == SUPPORTED_HORIZONS
        )
        test_rows = tuple(
            by_symbol_date[(symbol, event_day)]
            for event_day in test_dates
            for symbol in target_symbols
            if (symbol, event_day) in by_symbol_date
            and tuple(
                item.horizon for item in by_symbol_date[(symbol, event_day)].labels
            )
            == SUPPORTED_HORIZONS
        )
        if not train_rows or not test_rows:
            raise CurrentRestatedOutcomeStoreError("fold has no real observations")
        train_observed_dates = {row.event_date for row in train_rows}
        if len(train_observed_dates) < minimum_train_dates:
            raise CurrentRestatedOutcomeStoreError(
                "fold has fewer than the required observed training dates"
            )
        if {row.event_date for row in test_rows} != set(test_dates):
            raise CurrentRestatedOutcomeStoreError(
                "test fold does not contain observations for every global calendar session"
            )
        test_start = test_dates[0]
        train_label_ends = [
            label.horizon_end_date
            for row in train_rows
            for label in row.labels
        ]
        if not train_label_ends or max(train_label_ends) >= test_start:
            raise CurrentRestatedOutcomeStoreError(
                "train label_end must be strictly before fold test_start"
            )
        windows.append(
            CurrentRestatedOutcomeFoldV1(
                fold_id=f"fold-{len(windows) + 1:03d}",
                train_sample_ids=tuple(item.sample_id for item in train_rows),
                test_sample_ids=tuple(item.sample_id for item in test_rows),
                train_date_count=len(train_observed_dates),
                test_date_count=len(test_dates),
                train_end_date=train_dates[-1],
                test_start_date=test_start,
                test_end_date=test_dates[-1],
                purge_trading_days=purge_trading_days,
                embargo_trading_days=embargo_trading_days,
                max_train_label_end_date=max(train_label_ends),
                train_date_indices=train_indices,
                test_date_indices=test_indices,
            )
        )
        start_index += test_date_count + embargo_trading_days
    return calendar, tuple(windows)


def _write_numeric_arrays(
    *,
    staging: Path,
    observations: tuple[CurrentRestatedOutcomeObservationV1, ...],
    feature_count: int,
) -> dict[str, dict[str, Any]]:
    count = len(observations)
    feature_cells = count * feature_count
    label_cells = count * len(SUPPORTED_HORIZONS) * len(LABEL_METRICS)
    total_bytes = feature_cells * 8 * 4 + label_cells * 4 * 2
    if total_bytes > _MAX_ARRAY_BYTES:
        raise CurrentRestatedOutcomeStoreError("numeric arrays exceed the bounded artifact size")
    feature_values = np.zeros((count, feature_count), dtype="<i8")
    feature_missing = np.ones((count, feature_count), dtype="u1")
    feature_quality = np.zeros((count, feature_count), dtype="u1")
    feature_stale = np.zeros((count, feature_count), dtype="u1")
    label_values = np.zeros(
        (count, len(SUPPORTED_HORIZONS), len(LABEL_METRICS)), dtype="<i4"
    )
    label_missing = np.ones_like(label_values, dtype="u1")
    for row_index, row in enumerate(observations):
        if len(row.feature_values) != feature_count:
            raise CurrentRestatedOutcomeStoreError("feature row dimension mismatch")
        if feature_cells > _MAX_FEATURE_CELLS:
            raise CurrentRestatedOutcomeStoreError("feature matrix exceeds bounded cell count")
        feature_values[row_index, :] = row.feature_values
        feature_missing[row_index, :] = row.missing_mask
        feature_quality[row_index, :] = row.quality_blocked_mask
        feature_stale[row_index, :] = row.staleness_mask
        labels_by_horizon = {item.horizon: item for item in row.labels}
        for horizon_index, horizon in enumerate(SUPPORTED_HORIZONS):
            label = labels_by_horizon.get(horizon)
            if label is None:
                continue
            payload_values = (
                label.stock_return_bp,
                label.benchmark_return_bp,
                label.benchmark_excess_return_bp,
                label.mae_loss_bp,
                label.mfe_gain_bp,
                label.realized_volatility_bp,
                label.max_drawdown_bp,
                label.tail_loss_bp,
                int(label.downside_observed),
                int(label.fill_feasible_observed),
            )
            label_values[row_index, horizon_index, :] = payload_values
            label_missing[row_index, horizon_index, :] = 0
    arrays = {
        "feature_values": ("feature_values.i64", feature_values),
        "feature_missing_mask": ("feature_missing.u8", feature_missing),
        "feature_quality_blocked_mask": ("feature_quality_blocked.u8", feature_quality),
        "feature_staleness_mask": ("feature_staleness.u8", feature_stale),
        "label_values": ("label_values.i32", label_values),
        "label_missing_mask": ("label_missing.u8", label_missing),
    }
    result: dict[str, dict[str, Any]] = {}
    for name, (filename, array) in arrays.items():
        path = staging / filename
        raw = array.tobytes(order="C")
        path.write_bytes(raw)
        result[name] = {
            "path": filename,
            "dtype": array.dtype.str,
            "shape": list(array.shape),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    return result


def _verify_raw_source_pins(
    source_pins: Mapping[str, Any],
    *,
    repository_root: Path | None,
    target_symbols: tuple[str, ...],
    benchmark_entity_id: str,
) -> dict[tuple[str, str, str, date], dict[str, Any]]:
    publication_pin = _mapping(
        source_pins.get("raw_publication_manifest"), "raw_publication_manifest"
    )
    publication_path = _resolve_research_input_path(
        Path(str(publication_pin.get("path", ""))), repository_root=repository_root
    )
    publication_file = _capture_file(publication_path)
    if (
        publication_file.byte_count != _exact_int(publication_pin.get("bytes"), "raw_publication_manifest.bytes")
        or publication_file.mtime_ns != _exact_int(publication_pin.get("mtime_ns"), "raw_publication_manifest.mtime_ns")
        or publication_file.sha256 != _hash_pin(publication_pin.get("sha256"), "raw_publication_manifest.sha256")
    ):
        raise CurrentRestatedOutcomeStoreError("raw publication manifest actual bytes changed")
    publication_manifest = _load_object(publication_file.raw, "raw publication manifest")
    _verify_manifest_hash(publication_manifest, label="raw publication manifest")
    _verify_publication_contract(
        publication_manifest,
        publication_path=publication_file.path,
        target_symbols=target_symbols,
        benchmark_entity_id=benchmark_entity_id,
        repository_root=repository_root,
    )

    dataset_pin = _mapping(source_pins.get("raw_dataset_manifest"), "raw_dataset_manifest")
    dataset_path = _resolve_research_input_path(
        Path(str(dataset_pin.get("path", ""))), repository_root=repository_root
    )
    expected_dataset_path = publication_file.path.parent / "core_long_history" / "manifest.json"
    if dataset_path != expected_dataset_path.resolve(strict=True):
        raise CurrentRestatedOutcomeStoreError("raw child dataset path differs from publication structure")
    dataset_file = _capture_file(dataset_path)
    if (
        dataset_file.byte_count != _exact_int(dataset_pin.get("bytes"), "raw_dataset_manifest.bytes")
        or dataset_file.mtime_ns != _exact_int(dataset_pin.get("mtime_ns"), "raw_dataset_manifest.mtime_ns")
        or dataset_file.sha256 != _hash_pin(dataset_pin.get("sha256"), "raw_dataset_manifest.sha256")
    ):
        raise CurrentRestatedOutcomeStoreError("raw child dataset actual bytes changed")
    dataset_manifest = _load_object(dataset_file.raw, "raw child dataset manifest")
    _verify_manifest_hash(dataset_manifest, label="raw child dataset manifest")
    _verify_dataset_contract(
        publication_manifest,
        dataset_manifest,
        dataset_path=dataset_file.path,
        repository_root=repository_root,
    )

    raw_shards = _parse_raw_shard_pins(source_pins.get("raw_shards"))
    manifest_shards = _mapping_sequence(dataset_manifest.get("shards"), "raw child shards")
    if len(raw_shards) != len(manifest_shards):
        raise CurrentRestatedOutcomeStoreError("raw shard pins do not cover the complete child inventory")
    publication_root = publication_file.path.parent.resolve(strict=True)
    raw_context = _mapping(publication_manifest.get("source_context"), "raw source context")
    expected_context_hash = _hash_json(raw_context)
    source_observed_at = _aware_datetime(
        raw_context.get("source_observed_at"), "raw.source_observed_at"
    )
    raw_dependency_verified_at = _aware_datetime(
        raw_context.get("revision_dependencies_verified_at"),
        "raw.revision_dependencies_verified_at",
    )
    raw_generated_at = _aware_datetime(
        publication_manifest.get("raw_generated_at"), "raw.raw_generated_at"
    )
    value_registry = _feature_value_registry(dataset_manifest)
    dataset_id = dataset_manifest.get("dataset_id")
    if type(dataset_id) is not str:
        raise CurrentRestatedOutcomeStoreError("raw child dataset id is invalid")
    indexed_rows: dict[tuple[str, str, str, date], dict[str, Any]] = {}
    total_rows = 0
    total_values = 0
    target_symbol_set = set(target_symbols)
    by_year: dict[int, CurrentRestatedOutcomeRawPinV1] = {}
    for pin in raw_shards:
        if pin.role_id.startswith("raw_shard_year_"):
            year_text = pin.role_id.removeprefix("raw_shard_year_")
            if not year_text.isdecimal() or int(year_text) in by_year:
                raise CurrentRestatedOutcomeStoreError("raw shard role ids are invalid or repeated")
            by_year[int(year_text)] = pin
        else:
            raise CurrentRestatedOutcomeStoreError("raw shard role id is unsupported")
    seen_manifest_years: set[int] = set()
    for entry in manifest_shards:
        year = _exact_int(entry.get("year"), "raw shard.year")
        if year in seen_manifest_years or year not in by_year:
            raise CurrentRestatedOutcomeStoreError("raw shard manifest years are repeated or unpinned")
        seen_manifest_years.add(year)
        pin = by_year[year]
        relative = entry.get("path")
        if type(relative) is not str or Path(relative).is_absolute() or ".." in Path(relative).parts or "\\" in relative:
            raise CurrentRestatedOutcomeStoreError("raw shard manifest path is unsafe")
        expected_path = _resolve_research_input_path(
            publication_root / relative, repository_root=repository_root
        )
        if (
            Path(pin.path) != expected_path
            or pin.bytes != _exact_int(entry.get("compressed_bytes"), "raw shard.compressed_bytes")
            or pin.sha256 != _hash_pin(entry.get("compressed_sha256"), "raw shard.compressed_sha256")
            or pin.content_sha256 != str(entry.get("content_sha256"))
            or pin.row_count != _exact_int(entry.get("row_count"), "raw shard.row_count")
        ):
            raise CurrentRestatedOutcomeStoreError("raw shard receipt differs from child manifest")
        path = expected_path
        info_before = path.stat()
        if not stat.S_ISREG(info_before.st_mode) or info_before.st_size != pin.bytes or info_before.st_mtime_ns != pin.mtime_ns:
            raise CurrentRestatedOutcomeStoreError("raw shard file metadata differs from its pin")
        digest = hashlib.sha256()
        content = hashlib.sha256()
        shard_rows = 0
        shard_values = 0
        shard_source_tables: set[str] = set()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        with gzip.open(path, "rb") as stream:
            for line_number, line in enumerate(stream, start=1):
                if line.strip():
                    content.update(line)
                    row = _load_object(line, f"verified raw shard {year}:{line_number}")
                    shard_rows += 1
                    total_rows += 1
                    if total_rows > _MAX_RAW_ROWS:
                        raise CurrentRestatedOutcomeStoreError(
                            "verified raw source exceeds the row-count bound"
                        )
                    shard_values += _validate_raw_observation(
                        row=row,
                        dataset_id=dataset_id,
                        feature_registry=value_registry,
                        expected_context_hash=expected_context_hash,
                        raw_generated_at=raw_generated_at,
                        source_observed_at=source_observed_at,
                        dependency_verified_at=raw_dependency_verified_at,
                    )
                    event_date = _iso_date(row.get("event_date"), "raw.event_date")
                    if event_date.year != year:
                        raise CurrentRestatedOutcomeStoreError(
                            "raw shard contains a row outside its declared event year"
                        )
                    source_table = row.get("source_table")
                    source_id = row.get("source_id")
                    entity_id = row.get("entity_id")
                    if (
                        type(source_table) is not str
                        or type(source_id) is not str
                        or not source_id
                        or type(entity_id) is not str
                    ):
                        raise CurrentRestatedOutcomeStoreError(
                            "raw source row table/source/entity identity is invalid"
                        )
                    shard_source_tables.add(source_table)
                    symbol = entity_id.split("|", 1)[0]
                    selected = (
                        source_table in {"daily_prices", "technical_indicators"}
                        and symbol in target_symbol_set
                    ) or (
                        source_table == "market_indices"
                        and entity_id == benchmark_entity_id
                    )
                    if selected:
                        identity = (source_table, source_id, entity_id, event_date)
                        if identity in indexed_rows:
                            raise CurrentRestatedOutcomeStoreError(
                                "raw source has duplicate selected table/source/entity/date rows"
                            )
                        indexed_rows[identity] = row
        info_after = path.stat()
        if shard_rows != pin.row_count:
            raise CurrentRestatedOutcomeStoreError("raw shard actual row count differs from its pin")
        if shard_rows != _exact_int(entry.get("row_count"), "raw child shard.row_count"):
            raise CurrentRestatedOutcomeStoreError("raw shard row count differs from its child manifest")
        if shard_values != _exact_int(
            entry.get("feature_value_count"), "raw child shard.feature_value_count"
        ):
            raise CurrentRestatedOutcomeStoreError(
                "raw shard feature-value count differs from its child manifest"
            )
        if tuple(sorted(shard_source_tables)) != _string_sequence(
            entry.get("source_tables"), "raw child shard.source_tables"
        ):
            raise CurrentRestatedOutcomeStoreError(
                "raw shard source-table inventory differs from its child manifest"
            )
        total_values += shard_values
        if (
            info_before.st_size != info_after.st_size
            or info_before.st_mtime_ns != info_after.st_mtime_ns
            or digest.hexdigest() != pin.sha256
            or "sha256:" + content.hexdigest() != pin.content_sha256
        ):
            raise CurrentRestatedOutcomeStoreError(f"raw shard bytes changed: {path}")
    if seen_manifest_years != set(by_year):
        raise CurrentRestatedOutcomeStoreError("raw shard pin inventory contains extra years")
    if total_rows != _exact_int(dataset_manifest.get("row_count"), "raw child row_count"):
        raise CurrentRestatedOutcomeStoreError("actual raw row count differs from child manifest")
    if total_values != _exact_int(
        dataset_manifest.get("feature_value_count"), "raw child feature_value_count"
    ):
        raise CurrentRestatedOutcomeStoreError(
            "actual raw feature-value count differs from child manifest"
        )
    return indexed_rows


def _price_inputs_from_raw_rows(
    raw_rows: Mapping[tuple[str, str, str, date], Mapping[str, Any]],
    *,
    target_symbols: tuple[str, ...],
    benchmark_entity_id: str,
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    target_set = set(target_symbols)
    price_rows: list[tuple[object, ...]] = []
    gap_rows: list[tuple[object, ...]] = []
    for (source_table, source_id, entity_id, event_date), row in sorted(
        raw_rows.items(), key=lambda item: item[0]
    ):
        if source_table == "daily_prices" and source_id == "derived:daily_prices.ohlc":
            continue
        source_hash = _hash_pin(row.get("source_row_hash"), "raw.source_row_hash")
        values = _as_legacy_price_scale(_value_map(row.get("values")))
        if source_table == "daily_prices":
            if source_id != "sqlite.daily_prices":
                raise CurrentRestatedOutcomeStoreError(
                    "daily-price label input has an unsupported source identity"
                )
            symbol = entity_id.split("|", 1)[0]
            if symbol not in target_set:
                raise CurrentRestatedOutcomeStoreError(
                    "selected daily-price row is outside the pinned target universe"
                )
            record = label_math._price_record(
                table_name="daily_prices",
                entity_key=symbol,
                event_at=event_date.isoformat(),
                available_at="",
                source_row_hash=source_hash,
                values=values,
            )
            if record is not None:
                price_rows.append(record)
            contract = row.get("price_availability_contract")
            if contract is not None:
                contract_map = _mapping(contract, "price_availability_contract")
                contract_symbol, contract_date, _reason = (
                    validate_price_unavailable_research_contract(contract_map)
                )
                if contract_symbol != entity_id or contract_date != event_date.isoformat():
                    raise CurrentRestatedOutcomeStoreError(
                        "pinned raw price-availability contract identity mismatch"
                    )
                gap_rows.append(
                    ("stock", symbol, event_date.isoformat(), _hash_json(contract_map))
                )
        elif source_table == "market_indices":
            if entity_id != benchmark_entity_id:
                raise CurrentRestatedOutcomeStoreError(
                    "selected market row is outside the pinned benchmark identity"
                )
            record = label_math._price_record(
                table_name="market_indices",
                entity_key=benchmark_entity_id,
                event_at=event_date.isoformat(),
                available_at="",
                source_row_hash=source_hash,
                values=values,
            )
            if record is None:
                # Keep every benchmark source session in the global calendar;
                # an unusable price blocks labels but never removes a date.
                record = (
                    "market",
                    benchmark_entity_id,
                    event_date.isoformat(),
                    "",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    source_hash,
                )
            price_rows.append(record)
    return price_rows, gap_rows


def _verify_publication_contract(
    manifest: Mapping[str, Any],
    *,
    publication_path: Path,
    target_symbols: tuple[str, ...],
    benchmark_entity_id: str,
    repository_root: Path | None,
) -> None:
    expected_flags = {
        "schema_version": "ml-current-restated-year-shards.v1",
        "stage": "raw_current_restated_research_observations",
        "partition_basis": "event_date_calendar_year",
        "numeric_contract": "value_int_plus_decimal_exponent",
        "data_temporality": "current_restated_research",
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
    }
    for key, expected in expected_flags.items():
        if manifest.get(key) != expected:
            raise CurrentRestatedOutcomeStoreError(f"raw publication {key} contract mismatch")
    profile = _mapping(manifest.get("profile"), "raw profile")
    expected_core_tables = (
        "daily_prices",
        "technical_indicators",
        "market_indices",
        "industry_indices",
    )
    included_tables = _string_sequence(profile.get("included_tables"), "profile.included_tables")
    excluded_tables = _string_sequence(profile.get("excluded_tables"), "profile.excluded_tables")
    if (
        profile.get("id") != "core_long_history_current_restated_outcome_only"
        or profile.get("unknown_financial_statement_basis_included") is not False
        or included_tables != expected_core_tables
        or set(excluded_tables) & set(included_tables)
    ):
        raise CurrentRestatedOutcomeStoreError("raw profile is not explicit CORE current-restated")
    safety = _mapping(manifest.get("safety"), "raw safety")
    pit = _mapping(manifest.get("pit"), "raw PIT safety")
    if (
        safety.get("research_only") is not True
        or safety.get("formal_training_allowed") is not False
        or safety.get("formal_oos_allowed") is not False
        or pit.get("unknown_columns_fail_closed") is not True
        or _exact_int(pit.get("source_unreviewed_count"), "source_unreviewed_count") != 0
    ):
        raise CurrentRestatedOutcomeStoreError("raw publication safety contract is invalid")
    scope = _mapping(manifest.get("scope"), "raw scope")
    raw_symbols = _string_sequence(scope.get("symbols"), "raw scope symbols")
    if scope.get("all_universe") is not False or tuple(sorted(raw_symbols)) != target_symbols:
        raise CurrentRestatedOutcomeStoreError("raw source universe differs from explicit target_symbols")
    if benchmark_entity_id != "TAIEX":
        raise CurrentRestatedOutcomeStoreError("current-restated CORE outcome lane requires TAIEX benchmark context")
    _resolve_research_input_path(publication_path, repository_root=repository_root)
    generated = _aware_datetime(manifest.get("raw_generated_at"), "raw_generated_at")
    if manifest.get("generated_at") != generated.isoformat():
        raise CurrentRestatedOutcomeStoreError("raw generated_at and raw_generated_at differ")
    if manifest.get("source_context_bundle_sha256") != _hash_json(
        manifest.get("source_context")
    ):
        raise CurrentRestatedOutcomeStoreError("raw publication source-context pin mismatch")
    datasets = _mapping(manifest.get("datasets"), "publication.datasets")
    core = _mapping(datasets.get("core_long_history"), "publication.core_long_history")
    if core.get("manifest_path") != "core_long_history/manifest.json":
        raise CurrentRestatedOutcomeStoreError("publication does not pin the expected CORE child manifest")


def _verify_dataset_contract(
    publication: Mapping[str, Any],
    dataset: Mapping[str, Any],
    *,
    dataset_path: Path,
    repository_root: Path | None,
) -> None:
    expected = {
        "schema_version": "ml-current-restated-year-shard-dataset.v1",
        "stage": "raw_current_restated_research_observations",
        "dataset_id": "core_long_history",
        "partition_basis": "event_date_calendar_year",
        "format": "gzip_jsonl",
    }
    for key, value in expected.items():
        if dataset.get(key) != value:
            raise CurrentRestatedOutcomeStoreError(f"raw child dataset {key} contract mismatch")
    if dataset.get("data_temporality") != "current_restated_research" or dataset.get("historical_pit_eligible") is not False:
        raise CurrentRestatedOutcomeStoreError("raw child dataset is not current-restated research")
    if dataset.get("formal_training_eligible") is not False:
        raise CurrentRestatedOutcomeStoreError("raw child dataset claims formal eligibility")
    if dataset.get("source_context_bundle_sha256") != publication.get("source_context_bundle_sha256"):
        raise CurrentRestatedOutcomeStoreError("raw child source-context pin differs from publication")
    safety = _mapping(dataset.get("safety"), "raw child safety")
    if (
        safety.get("unreviewed_included") is not False
        or safety.get("excluded_leakage_included") is not False
        or safety.get("research_only") is not True
        or safety.get("formal_training_allowed") is not False
    ):
        raise CurrentRestatedOutcomeStoreError("raw child safety contract is invalid")
    if dataset_path.parent.name != "core_long_history":
        raise CurrentRestatedOutcomeStoreError("raw child manifest path is not core_long_history")
    datasets = _mapping(publication.get("datasets"), "publication.datasets")
    core = _mapping(datasets.get("core_long_history"), "publication.core_long_history")
    if core.get("manifest_hash") != dataset.get("manifest_hash"):
        raise CurrentRestatedOutcomeStoreError("publication child manifest hash differs from the captured child")
    if _hash_json(dataset.get("source_context")) != publication.get("source_context_bundle_sha256"):
        raise CurrentRestatedOutcomeStoreError("child source context bytes differ from publication")
    _resolve_research_input_path(dataset_path, repository_root=repository_root)


def _build_feature_registry(
    dataset: Mapping[str, Any], *, benchmark_entity_id: str
) -> tuple[tuple[CurrentRestatedOutcomeFeatureV1, ...], list[dict[str, Any]]]:
    definitions = _mapping_sequence(dataset.get("features"), "feature registry")
    selected: dict[str, CurrentRestatedOutcomeFeatureV1] = {}
    core_tables = {"daily_prices", "technical_indicators", "market_indices", "industry_indices"}
    selected_tables = {"daily_prices", "technical_indicators", "market_indices"}
    seen_source_ids: set[str] = set()
    for item in definitions:
        table = item.get("table_name")
        if not isinstance(table, str) or table not in core_tables:
            raise CurrentRestatedOutcomeStoreError("raw feature registry contains an unsupported table")
        status = item.get("eligibility_status")
        if status not in {"formal_backfill", "first_seen_only"}:
            raise CurrentRestatedOutcomeStoreError(
                f"raw feature is not reviewed for CORE research: {item.get('feature_id')}"
            )
        source_feature_id = item.get("feature_id")
        exponent = _scale_exponent(item.get("scale"), "feature.scale")
        unit = item.get("unit")
        if not isinstance(source_feature_id, str) or not source_feature_id.startswith(table + "."):
            raise CurrentRestatedOutcomeStoreError("feature id does not match its source table")
        if source_feature_id in seen_source_ids:
            raise CurrentRestatedOutcomeStoreError("raw feature registry repeats a source feature id")
        seen_source_ids.add(source_feature_id)
        if not isinstance(unit, str) or not unit:
            raise CurrentRestatedOutcomeStoreError("feature unit is missing")
        if source_feature_id == "daily_prices.成交金額" and (
            unit != "TWD"
            or item.get("unit_contract") != _DAILY_TRANSACTION_AMOUNT_UNIT_CONTRACT
        ):
            raise CurrentRestatedOutcomeStoreError(
                "current-restated daily transaction amount lacks its verified TWD unit contract"
            )
        denominator = _exact_int(item.get("source_scale_denominator"), "feature.source_scale_denominator")
        if denominator != 10**exponent:
            raise CurrentRestatedOutcomeStoreError("raw feature exponent differs from its original scale denominator")
        if table not in selected_tables:
            continue
        role = "benchmark" if table == "market_indices" else "stock"
        stable_id = f"{role}/{source_feature_id}"
        if stable_id in selected:
            raise CurrentRestatedOutcomeStoreError("selected outcome registry repeats a feature")
        selected[stable_id] = CurrentRestatedOutcomeFeatureV1(
            feature_id=stable_id,
            source_feature_id=source_feature_id,
            source_table=table,
            role=role,
            unit=unit,
            decimal_exponent=exponent,
            eligibility_status=str(status),
        )
    if not any(item.role == "stock" and item.source_table == "daily_prices" for item in selected.values()):
        raise CurrentRestatedOutcomeStoreError("raw registry lacks reviewed stock price features")
    if not any(item.role == "benchmark" for item in selected.values()):
        raise CurrentRestatedOutcomeStoreError("raw registry lacks reviewed benchmark features")
    registry = tuple(sorted(selected.values(), key=lambda item: item.feature_id))
    payload = [
        {
            "feature_id": item.feature_id,
            "source_feature_id": item.source_feature_id,
            "source_table": item.source_table,
            "role": item.role,
            "unit": item.unit,
            "decimal_exponent": item.decimal_exponent,
            "eligibility_status": item.eligibility_status,
        }
        for item in registry
    ]
    return registry, payload


def _feature_value_registry(
    raw_manifest: Mapping[str, Any],
) -> dict[str, tuple[str, str, int, str]]:
    registry: dict[str, tuple[str, str, int, str]] = {}
    for item in _mapping_sequence(raw_manifest.get("features"), "raw source feature registry"):
        feature_id = item.get("feature_id")
        table = item.get("table_name")
        unit = item.get("unit")
        status = item.get("eligibility_status")
        if (
            type(feature_id) is not str
            or type(table) is not str
            or type(unit) is not str
            or type(status) is not str
        ):
            raise CurrentRestatedOutcomeStoreError("raw source feature registry has invalid field types")
        if feature_id == "daily_prices.成交金額" and (
            unit != "TWD"
            or item.get("unit_contract") != _DAILY_TRANSACTION_AMOUNT_UNIT_CONTRACT
        ):
            raise CurrentRestatedOutcomeStoreError(
                "raw daily transaction amount registry lacks its verified TWD unit contract"
            )
        if feature_id != "daily_prices.成交金額" and item.get("unit_contract") is not None:
            raise CurrentRestatedOutcomeStoreError("raw source feature has an unsupported unit contract")
        exponent = _scale_exponent(item.get("scale"), "feature.scale")
        if feature_id in registry:
            raise CurrentRestatedOutcomeStoreError("raw source feature registry repeats a feature id")
        registry[feature_id] = (table, unit, exponent, status)
    if not registry:
        raise CurrentRestatedOutcomeStoreError("raw source feature registry is empty")
    return registry


def _validate_raw_observation(
    *,
    row: Mapping[str, Any],
    dataset_id: str,
    feature_registry: Mapping[str, tuple[str, str, int, str]],
    expected_context_hash: str,
    raw_generated_at: datetime,
    source_observed_at: datetime,
    dependency_verified_at: datetime,
) -> int:
    if (
        row.get("schema_version") != "ml-current-restated-observation.v1"
        or row.get("dataset_id") != dataset_id
        or row.get("pit_status") != "current_observed_non_pit"
        or row.get("current_restated") is not True
        or row.get("historical_pit_eligible") is not False
        or row.get("formal_training_eligible") is not False
        or row.get("event_reference_only") is not True
        or row.get("source_available_at") is not None
        or row.get("source_context_bundle_sha256") != expected_context_hash
    ):
        raise CurrentRestatedOutcomeStoreError("raw observation safety or context contract mismatch")
    expected_row_hash = _hash_pin(row.get("source_row_hash"), "source_row_hash")
    body = dict(row)
    body.pop("source_row_hash", None)
    if _hash_json(body) != "sha256:" + expected_row_hash:
        raise CurrentRestatedOutcomeStoreError("raw source_row_hash mismatch")
    event_date = _iso_date(row.get("event_date"), "event_date")
    source_table = row.get("source_table")
    entity_id = row.get("entity_id")
    if type(source_table) is not str or type(entity_id) is not str or not entity_id:
        raise CurrentRestatedOutcomeStoreError("raw source table/entity identity is invalid")
    if source_table not in {"daily_prices", "technical_indicators", "market_indices", "industry_indices"}:
        raise CurrentRestatedOutcomeStoreError("raw observation contains a non-CORE table")
    event_at_value = row.get("event_at")
    if type(event_at_value) is not str:
        raise CurrentRestatedOutcomeStoreError("raw event_at must be ISO text")
    event_at = _aware_datetime(event_at_value, "event_at")
    if event_at.date() != event_date or event_at_value[:10] != event_date.isoformat():
        raise CurrentRestatedOutcomeStoreError("raw event reference clocks disagree")
    source_observed = _aware_datetime(row.get("source_observed_at"), "row.source_observed_at")
    dependency_verified = _aware_datetime(
        row.get("revision_dependencies_verified_at"),
        "row.revision_dependencies_verified_at",
    )
    current_value_available = _aware_datetime(
        row.get("current_value_available_at"), "row.current_value_available_at"
    )
    available = _aware_datetime(row.get("available_at"), "row.available_at")
    if (
        source_observed != source_observed_at
        or dependency_verified != dependency_verified_at
        or available != current_value_available
        or current_value_available < max(source_observed, dependency_verified)
        or current_value_available > raw_generated_at
    ):
        raise CurrentRestatedOutcomeStoreError("raw current-value availability clock is invalid")
    values = _mapping_sequence(row.get("values"), "raw observation values")
    seen: set[str] = set()
    for value in values:
        feature_id = value.get("feature_id")
        if not isinstance(feature_id, str) or feature_id in seen:
            raise CurrentRestatedOutcomeStoreError("raw observation repeats or omits feature_id")
        seen.add(feature_id)
        if feature_id not in feature_registry:
            raise CurrentRestatedOutcomeStoreError("raw value is absent from the explicit feature registry")
        expected_table, unit, expected_exponent, expected_status = feature_registry[feature_id]
        if source_table != expected_table and not _is_reviewed_daily_technical_derivation(
            row=row,
            value=value,
            feature_id=feature_id,
            expected_table=expected_table,
            source_table=source_table,
            current_value_available_at=current_value_available,
        ):
            raise CurrentRestatedOutcomeStoreError(
                f"raw source feature {feature_id!r} is filed under table "
                f"{source_table!r}, expected {expected_table!r}"
            )
        if value.get("unit") != unit:
            raise CurrentRestatedOutcomeStoreError("raw value unit differs from registry")
        if feature_id == "daily_prices.成交金額":
            if (
                value.get("unit") != "TWD"
                or value.get("unit_contract")
                != _DAILY_TRANSACTION_AMOUNT_UNIT_CONTRACT
            ):
                raise CurrentRestatedOutcomeStoreError(
                    "raw transaction amount unit differs from its verified TWD contract"
                )
        elif value.get("unit_contract") is not None:
            raise CurrentRestatedOutcomeStoreError("raw value declares an unsupported unit contract")
        if _scale_exponent(value.get("scale"), "value.scale") != expected_exponent:
            raise CurrentRestatedOutcomeStoreError("raw value decimal exponent differs from registry")
        if value.get("formal_training_eligible") is not False:
            raise CurrentRestatedOutcomeStoreError("current-restated raw value claims formal eligibility")
        if value.get("eligibility_status") != expected_status:
            raise CurrentRestatedOutcomeStoreError("raw value eligibility differs from the pinned registry")
        if value.get("current_value_available_at") != current_value_available.isoformat():
            raise CurrentRestatedOutcomeStoreError("raw feature current-value clock differs from its row clock")
        integer = value.get("value_int")
        missing = value.get("missing_mask")
        quality = value.get("quality_blocked_mask")
        stale = value.get("staleness_mask")
        if integer is not None:
            _exact_signed_int64(integer, "value_int")
        if type(missing) is not bool or missing != (integer is None):
            raise CurrentRestatedOutcomeStoreError("raw missing mask disagrees with value")
        if type(quality) is not bool or type(stale) is not bool:
            raise CurrentRestatedOutcomeStoreError("raw value masks must be booleans")
        _hash_pin(value.get("source_value_hash"), "source_value_hash")
        if value.get("source_value_hash_semantics") != "current_restated_feature_value_plus_verified_source_context.v1":
            raise CurrentRestatedOutcomeStoreError("raw feature hash semantics are unsupported")
        derivation = value.get("derivation")
        if derivation is not None:
            derivation_map = _mapping(derivation, "raw derivation")
            if (
                derivation_map.get("method") != "causal_wilder_prefix"
                or derivation_map.get("causal_prefix_only") is not True
                or derivation_map.get("raw_feature_value_ignored") is not True
                or _aware_datetime(derivation_map.get("usable_from"), "derivation.usable_from")
                != current_value_available
            ):
                raise CurrentRestatedOutcomeStoreError("raw derived feature contract is invalid")
    return len(values)


def _is_reviewed_daily_technical_derivation(
    *,
    row: Mapping[str, Any],
    value: Mapping[str, Any],
    feature_id: str,
    expected_table: str,
    source_table: str,
    current_value_available_at: datetime,
) -> bool:
    if (
        expected_table != "technical_indicators"
        or source_table != "daily_prices"
        or feature_id not in {"technical_indicators.ATR", "technical_indicators.ADX"}
        or row.get("source_id") != "derived:daily_prices.ohlc"
        or row.get("family") != "price_liquidity_technical"
    ):
        return False
    derivation = value.get("derivation")
    if not isinstance(derivation, Mapping):
        return False
    input_columns = derivation.get("input_columns")
    return (
        derivation.get("method") == "causal_wilder_prefix"
        and derivation.get("causal_prefix_only") is True
        and derivation.get("raw_feature_value_ignored") is True
        and type(derivation.get("period")) is int
        and derivation.get("period") == 14
        and input_columns == ["最高價", "最低價", "收盤價"]
        and bool(_hash_pin(derivation.get("derivation_hash"), "derivation.derivation_hash"))
        and derivation.get("usable_from") == current_value_available_at.isoformat()
        and (
            derivation.get("blocker") is None
            or type(derivation.get("blocker")) is str
        )
    )


def _is_reviewed_daily_technical_source_row(
    *,
    row: Mapping[str, Any],
    current_value_available_at: datetime,
) -> bool:
    values = _mapping_sequence(row.get("values"), "daily-derived source values")
    by_feature_id = {
        str(value.get("feature_id")): value
        for value in values
    }
    if set(by_feature_id) != {
        "technical_indicators.ADX",
        "technical_indicators.ATR",
    }:
        return False
    return all(
        _is_reviewed_daily_technical_derivation(
            row=row,
            value=value,
            feature_id=feature_id,
            expected_table="technical_indicators",
            source_table="daily_prices",
            current_value_available_at=current_value_available_at,
        )
        for feature_id, value in by_feature_id.items()
    )


def _value_map(values: object) -> dict[str, tuple[int | None, int]]:
    result: dict[str, tuple[int | None, int]] = {}
    for item in _mapping_sequence(values, "price values"):
        feature_id = str(item["feature_id"])
        value = item.get("value_int")
        if value is not None:
            value = _exact_signed_int64(value, f"{feature_id}.value_int")
        exponent = _scale_exponent(item.get("scale"), f"{feature_id}.scale")
        if feature_id in result:
            raise CurrentRestatedOutcomeStoreError("price row repeats a feature id")
        result[feature_id] = (value, exponent)
    return result


def _as_legacy_price_scale(
    values: Mapping[str, tuple[int | None, int]],
) -> dict[str, tuple[int | None, int]]:
    """在舊 label helper 邊界將十進位指數轉成其正整數分母。"""
    return {
        feature_id: (integer, 10**exponent)
        for feature_id, (integer, exponent) in values.items()
    }


def _price_component(
    row: tuple[object, ...], value_index: int, label: str
) -> tuple[int, int]:
    value = row[value_index]
    denominator = row[value_index + 1]
    if value is None:
        raise CurrentRestatedOutcomeStoreError(f"{label} is missing")
    integer = _exact_signed_int64(value, f"{label}.value_int")
    if integer <= 0:
        raise CurrentRestatedOutcomeStoreError(f"{label} must be positive")
    scale = _exact_int(denominator, f"{label}.legacy_scale")
    exponent = 0
    remaining = scale
    while remaining > 1 and remaining % 10 == 0:
        remaining //= 10
        exponent += 1
    if remaining != 1 or exponent > 18:
        raise CurrentRestatedOutcomeStoreError(
            f"{label} legacy scale is not a supported power of ten"
        )
    return integer, exponent


def _new_sample_draft(
    symbol: str,
    event_date: date,
    feature_registry: tuple[CurrentRestatedOutcomeFeatureV1, ...],
) -> _SampleDraft:
    stock_features = [item for item in feature_registry if item.role == "stock"]
    return _SampleDraft(
        symbol=symbol,
        event_date=event_date,
        values={item.feature_id: None for item in stock_features},
        missing={item.feature_id: True for item in stock_features},
        quality_blocked={item.feature_id: False for item in stock_features},
        stale={item.feature_id: False for item in stock_features},
        source_rows=[],
        assigned_feature_ids=set(),
    )


def _source_row_payload(
    row: CurrentRestatedOutcomeSourceRowV1,
) -> dict[str, Any]:
    return {
        "source_table": row.source_table,
        "source_id": row.source_id,
        "entity_id": row.entity_id,
        "event_date": row.event_date.isoformat(),
        "source_row_hash": row.source_row_hash,
    }


def _label_metric_values(label: CurrentRestatedOutcomeLabelV1) -> tuple[int, ...]:
    return (
        label.stock_return_bp,
        label.benchmark_return_bp,
        label.benchmark_excess_return_bp,
        label.mae_loss_bp,
        label.mfe_gain_bp,
        label.realized_volatility_bp,
        label.max_drawdown_bp,
        label.tail_loss_bp,
        int(label.downside_observed),
        int(label.fill_feasible_observed),
    )


def _outcome_label_payload(
    label: CurrentRestatedOutcomeLabelV1,
) -> dict[str, Any]:
    return {
        "horizon": label.horizon,
        "next_entry_date": label.next_entry_date.isoformat(),
        "horizon_end_date": label.horizon_end_date.isoformat(),
        "stock_return_bp": label.stock_return_bp,
        "benchmark_return_bp": label.benchmark_return_bp,
        "benchmark_excess_return_bp": label.benchmark_excess_return_bp,
        "mae_loss_bp": label.mae_loss_bp,
        "mfe_gain_bp": label.mfe_gain_bp,
        "realized_volatility_bp": label.realized_volatility_bp,
        "max_drawdown_bp": label.max_drawdown_bp,
        "tail_loss_bp": label.tail_loss_bp,
        "downside_observed": label.downside_observed,
        "fill_feasible_observed": label.fill_feasible_observed,
        "stock_next_entry_open_value_int": label.stock_next_entry_open_value_int,
        "stock_next_entry_open_decimal_exponent": label.stock_next_entry_open_decimal_exponent,
        "stock_exit_close_value_int": label.stock_exit_close_value_int,
        "stock_exit_close_decimal_exponent": label.stock_exit_close_decimal_exponent,
        "benchmark_next_entry_open_value_int": label.benchmark_next_entry_open_value_int,
        "benchmark_next_entry_open_decimal_exponent": label.benchmark_next_entry_open_decimal_exponent,
        "benchmark_exit_close_value_int": label.benchmark_exit_close_value_int,
        "benchmark_exit_close_decimal_exponent": label.benchmark_exit_close_decimal_exponent,
        "stock_entry_source_hash": label.stock_entry_source_hash,
        "stock_exit_source_hash": label.stock_exit_source_hash,
        "benchmark_entry_source_hash": label.benchmark_entry_source_hash,
        "benchmark_exit_source_hash": label.benchmark_exit_source_hash,
        "stock_path_source_hashes": list(label.stock_path_source_hashes),
        "benchmark_path_source_hashes": list(label.benchmark_path_source_hashes),
        "source_row_hashes": list(label.source_row_hashes),
        "inputs_available_at": label.inputs_available_at.isoformat(),
        "source_hash": label.source_hash,
        "label_math_source_hash": label.label_math_source_hash,
    }


def _merge_stock_features(
    *,
    draft: _SampleDraft,
    values: object,
    feature_ids_by_role: Mapping[tuple[str, str], str],
    row_hash: str,
    source_table: str,
    source_id: str,
    entity_id: str,
    event_date: date,
) -> None:
    for value in _mapping_sequence(values, "stock values"):
        feature_source_id = str(value["feature_id"])
        stable_id = feature_ids_by_role.get(("stock", feature_source_id))
        if stable_id is None:
            continue
        if stable_id in draft.assigned_feature_ids:
            raise CurrentRestatedOutcomeStoreError("duplicate stock feature across raw rows")
        draft.assigned_feature_ids.add(stable_id)
        integer = value.get("value_int")
        draft.values[stable_id] = None if integer is None else _exact_signed_int64(integer, stable_id)
        draft.missing[stable_id] = bool(value["missing_mask"])
        draft.quality_blocked[stable_id] = bool(value["quality_blocked_mask"])
        draft.stale[stable_id] = bool(value["staleness_mask"])
    draft.source_rows.append(
        CurrentRestatedOutcomeSourceRowV1(
            source_table=source_table,
            source_id=source_id,
            entity_id=entity_id,
            event_date=event_date,
            source_row_hash="sha256:" + row_hash,
        )
    )


def _merge_benchmark_features(
    *,
    draft: _SampleDraft,
    values: object,
    feature_ids_by_role: Mapping[tuple[str, str], str],
    row_hash: str,
    source_id: str,
    entity_id: str,
    event_date: date,
) -> None:
    for value in _mapping_sequence(values, "benchmark values"):
        feature_source_id = str(value["feature_id"])
        stable_id = feature_ids_by_role.get(("benchmark", feature_source_id))
        if stable_id is None:
            continue
        if stable_id in draft.assigned_feature_ids:
            raise CurrentRestatedOutcomeStoreError("duplicate benchmark feature across raw rows")
        draft.assigned_feature_ids.add(stable_id)
        integer = value.get("value_int")
        draft.values[stable_id] = None if integer is None else _exact_signed_int64(integer, stable_id)
        draft.missing[stable_id] = bool(value["missing_mask"])
        draft.quality_blocked[stable_id] = bool(value["quality_blocked_mask"])
        draft.stale[stable_id] = bool(value["staleness_mask"])
    draft.source_rows.append(
        CurrentRestatedOutcomeSourceRowV1(
            source_table="market_indices",
            source_id=source_id,
            entity_id=entity_id,
            event_date=event_date,
            source_row_hash="sha256:" + row_hash,
        )
    )


def _revalidate_source_context(
    raw_context: Mapping[str, Any],
) -> revision_gate.VerifiedCurrentRestatedSourceContext:
    try:
        return revision_gate.load_verified_current_restated_source_context(
            Path(str(raw_context["snapshot_database_path"])),
            Path(str(raw_context["snapshot_receipt_path"])),
            expected_snapshot_database_sha256=str(raw_context["snapshot_database_sha256"]),
            expected_snapshot_receipt_sha256=str(raw_context["snapshot_receipt_sha256"]),
            original_database_path=Path(str(raw_context["source_database_path"])),
            decision_at=str(raw_context["decision_at"]),
            training_as_of=str(raw_context["data_selection_as_of"]),
        )
    except (OSError, RuntimeError, KeyError, TypeError, ValueError) as exc:
        raise CurrentRestatedOutcomeStoreError(
            f"verified original-source context could not be revalidated: {exc}"
        ) from exc


def _assert_context_stable(
    old: Mapping[str, Any],
    new: revision_gate.VerifiedCurrentRestatedSourceContext,
) -> None:
    current = raw_exporter._current_restated_context_payload(new)
    scalar_fields = (
        "schema_version",
        "current_restated",
        "historical_pit_eligible",
        "source_database_path",
        "source_database_sha256",
        "source_wal_path",
        "source_wal_sha256",
        "source_wal_present",
        "snapshot_database_path",
        "snapshot_database_sha256",
        "snapshot_receipt_path",
        "snapshot_receipt_sha256",
        "decision_at",
        "data_selection_as_of",
        "source_generation",
        "revision_namespace_bundle_sha256",
        "source_revision_evidence",
    )
    if any(old.get(field) != current.get(field) for field in scalar_fields):
        raise CurrentRestatedOutcomeStoreError("revalidated current-restated context identity changed")
    for field in ("revision_namespace_files", "revision_dependency_files"):
        if _stable_file_pins(old.get(field), field) != _stable_file_pins(current.get(field), field):
            raise CurrentRestatedOutcomeStoreError(f"revalidated {field} differ from raw lineage")
    if new.revision_dependencies_verified_at < _aware_datetime(
        old.get("revision_dependencies_verified_at"), "raw.revision_dependencies_verified_at"
    ):
        raise CurrentRestatedOutcomeStoreError("revision dependency verification clock moved backward")


def _stable_file_pins(value: object, label: str) -> tuple[tuple[str, str, int, int, str], ...]:
    rows = _mapping_sequence(value, label)
    normalized: list[tuple[str, str, int, int, str]] = []
    for item in rows:
        namespace = str(item.get("namespace", ""))
        role_id = str(item.get("role_id", ""))
        path = str(item.get("path", ""))
        byte_count = _exact_int(item.get("bytes"), f"{label}.bytes")
        mtime_ns = _exact_int(item.get("mtime_ns"), f"{label}.mtime_ns")
        sha256 = _hash_pin(item.get("sha256"), f"{label}.sha256")
        normalized.append((namespace, role_id + "|" + path, byte_count, mtime_ns, sha256))
    return tuple(sorted(normalized))


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    with path.open("wb") as stream:
        for row in rows:
            raw = (_canonical_json(row) + "\n").encode("utf-8")
            stream.write(raw)
            digest.update(raw)
            count += 1
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": path.name, "bytes": path.stat().st_size, "sha256": digest.hexdigest(), "row_count": count}


def _read_jsonl_rows(path: Path, *, expected_count: int) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    with path.open("rb") as stream:
        for line_no, raw in enumerate(stream, start=1):
            if not raw.strip():
                raise CurrentRestatedOutcomeStoreError(f"blank observations metadata row {line_no}")
            rows.append(_load_object(raw, f"observations metadata {line_no}"))
    if len(rows) != expected_count:
        raise CurrentRestatedOutcomeStoreError("observations metadata count mismatch")
    return tuple(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> _CapturedFile:
    raw = (_canonical_json(payload) + "\n").encode("utf-8")
    with path.open("wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return _CapturedFile(path, raw, hashlib.sha256(raw).hexdigest(), len(raw), path.stat().st_mtime_ns)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    _write_json(temporary, payload)
    os.replace(temporary, path)


def _verify_staging_size(staging: Path, output_root: Path, budget: Any) -> None:
    size = sum(path.stat().st_size for path in staging.rglob("*") if path.is_file())
    if size > _MAX_ARRAY_BYTES:
        raise CurrentRestatedOutcomeStoreError("staged outcome artifact exceeds 2 GiB bound")
    preflight_capacity(
        probe_path=output_root,
        budget=budget,
        stage="current_restated_direct_before_publish",
        persistent_roots=(output_root,),
        temporary_roots=(staging,),
        persistent_new_bytes_estimate=size,
        temporary_peak_bytes_observed=size,
    )


def _fold_payload(fold: CurrentRestatedOutcomeFoldV1) -> dict[str, Any]:
    return {
        "fold_id": fold.fold_id,
        "train_sample_ids": list(fold.train_sample_ids),
        "test_sample_ids": list(fold.test_sample_ids),
        "train_date_count": fold.train_date_count,
        "test_date_count": fold.test_date_count,
        "train_end_date": fold.train_end_date.isoformat(),
        "test_start_date": fold.test_start_date.isoformat(),
        "test_end_date": fold.test_end_date.isoformat(),
        "purge_trading_days": fold.purge_trading_days,
        "embargo_trading_days": fold.embargo_trading_days,
        "max_train_label_end_date": fold.max_train_label_end_date.isoformat(),
        "train_date_indices": list(fold.train_date_indices),
        "test_date_indices": list(fold.test_date_indices),
    }


def _parse_folds(
    policy: Mapping[str, Any],
    observations: tuple[CurrentRestatedOutcomeObservationV1, ...],
    *,
    event_date_calendar: tuple[date, ...],
    benchmark_event_calendar: tuple[date, ...],
    target_symbols: tuple[str, ...],
) -> tuple[CurrentRestatedOutcomeFoldV1, ...]:
    fold_policy = _mapping(policy, "fold_policy")
    if fold_policy.get("label_end_must_be_strictly_before_test_start") is not True:
        raise CurrentRestatedOutcomeStoreError("fold policy does not require strict label purge")
    minimum_train_dates = _exact_int(
        fold_policy.get("minimum_train_dates_after_purge"),
        "minimum_train_dates_after_purge",
    )
    test_date_count = _exact_int(fold_policy.get("test_date_count"), "test_date_count")
    purge = _exact_int(fold_policy.get("purge_trading_days"), "purge_trading_days")
    embargo = _exact_int(fold_policy.get("embargo_trading_days"), "embargo_trading_days")
    if minimum_train_dates < 125 or test_date_count < 63 or purge < 60 or embargo < 5:
        raise CurrentRestatedOutcomeStoreError("fold policy is below the research minimum")
    if _exact_int(fold_policy.get("minimum_fold_count"), "minimum_fold_count") != 4:
        raise CurrentRestatedOutcomeStoreError("fold policy minimum count is invalid")

    by_id = {item.sample_id: item for item in observations}
    by_symbol_date = {(item.symbol, item.event_date): item for item in observations}
    if len(by_id) != len(observations) or len(by_symbol_date) != len(observations):
        raise CurrentRestatedOutcomeStoreError("sample identities are duplicated")
    complete_dates_by_symbol: dict[str, set[date]] = {}
    for row in observations:
        if tuple(label.horizon for label in row.labels) == SUPPORTED_HORIZONS:
            complete_dates_by_symbol.setdefault(row.symbol, set()).add(row.event_date)
    if set(complete_dates_by_symbol) != set(target_symbols):
        raise CurrentRestatedOutcomeStoreError("outcome artifact omits a target symbol")
    if (
        not benchmark_event_calendar
        or tuple(sorted(set(benchmark_event_calendar))) != benchmark_event_calendar
        or event_date_calendar != benchmark_event_calendar
    ):
        raise CurrentRestatedOutcomeStoreError(
            "global event-date calendar is not the complete pinned benchmark calendar"
        )
    complete_dates = set.union(
        *(complete_dates_by_symbol[symbol] for symbol in target_symbols)
    )
    if not complete_dates.issubset(set(event_date_calendar)):
        raise CurrentRestatedOutcomeStoreError(
            "complete outcome dates are outside the pinned global event calendar"
        )

    raw_folds = _mapping_sequence(fold_policy.get("folds"), "folds")
    expected_specs: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    start_index = minimum_train_dates + purge
    while start_index + test_date_count <= len(event_date_calendar):
        train_indices = tuple(range(0, start_index - purge))
        test_indices = tuple(range(start_index, start_index + test_date_count))
        test_date_set = {event_date_calendar[index] for index in test_indices}
        if test_date_set.issubset(complete_dates):
            expected_specs.append((train_indices, test_indices))
        start_index += test_date_count + embargo
    if len(raw_folds) < 4 or len(raw_folds) != len(expected_specs):
        raise CurrentRestatedOutcomeStoreError("fold count does not match the global calendar policy")

    folds: list[CurrentRestatedOutcomeFoldV1] = []
    for fold_index, (raw, (expected_train_indices, expected_test_indices)) in enumerate(
        zip(raw_folds, expected_specs, strict=True), start=1
    ):
        train_indices = tuple(
            _exact_int(item, "fold.train_date_indices[]")
            for item in _sequence(raw.get("train_date_indices"), "fold.train_date_indices")
        )
        test_indices = tuple(
            _exact_int(item, "fold.test_date_indices[]")
            for item in _sequence(raw.get("test_date_indices"), "fold.test_date_indices")
        )
        if train_indices != expected_train_indices or test_indices != expected_test_indices:
            raise CurrentRestatedOutcomeStoreError("fold indices do not enforce actual purge/embargo")
        if any(index >= len(event_date_calendar) for index in (*train_indices, *test_indices)):
            raise CurrentRestatedOutcomeStoreError("fold index exceeds the pinned calendar")
        train_dates = tuple(event_date_calendar[index] for index in train_indices)
        test_dates = tuple(event_date_calendar[index] for index in test_indices)
        expected_train_ids = tuple(
            by_symbol_date[(symbol, event_day)].sample_id
            for event_day in train_dates
            for symbol in target_symbols
            if (symbol, event_day) in by_symbol_date
            and tuple(
                label.horizon for label in by_symbol_date[(symbol, event_day)].labels
            )
            == SUPPORTED_HORIZONS
        )
        expected_test_ids = tuple(
            by_symbol_date[(symbol, event_day)].sample_id
            for event_day in test_dates
            for symbol in target_symbols
            if (symbol, event_day) in by_symbol_date
            and tuple(
                label.horizon for label in by_symbol_date[(symbol, event_day)].labels
            )
            == SUPPORTED_HORIZONS
        )
        train_ids = _string_sequence(raw.get("train_sample_ids"), "fold.train_sample_ids")
        test_ids = _string_sequence(raw.get("test_sample_ids"), "fold.test_sample_ids")
        if train_ids != expected_train_ids or test_ids != expected_test_ids:
            raise CurrentRestatedOutcomeStoreError("fold sample ids do not match the pinned global calendar")
        if set(train_ids) & set(test_ids):
            raise CurrentRestatedOutcomeStoreError("fold train/test samples overlap")
        train_rows = [by_id[item] for item in train_ids]
        test_rows = [by_id[item] for item in test_ids]
        observed_train_dates = {row.event_date for row in train_rows}
        observed_test_dates = {row.event_date for row in test_rows}
        if len(observed_train_dates) < minimum_train_dates:
            raise CurrentRestatedOutcomeStoreError(
                "fold has fewer than the required observed training dates"
            )
        if observed_test_dates != set(test_dates):
            raise CurrentRestatedOutcomeStoreError(
                "test fold omits a global calendar session"
            )
        train_ends = [label.horizon_end_date for row in train_rows for label in row.labels]
        max_end = max(train_ends, default=date.min)
        test_start = test_dates[0]
        if (
            max_end >= test_start
            or _iso_date(raw.get("max_train_label_end_date"), "max_train_label_end_date") != max_end
            or _iso_date(raw.get("train_end_date"), "train_end_date") != train_dates[-1]
            or _iso_date(raw.get("test_start_date"), "test_start_date") != test_start
            or _iso_date(raw.get("test_end_date"), "test_end_date") != test_dates[-1]
        ):
            raise CurrentRestatedOutcomeStoreError("fold date bounds or matured labels are invalid")
        if (
            _exact_int(raw.get("train_date_count"), "train_date_count") != len(observed_train_dates)
            or len(observed_train_dates) < minimum_train_dates
            or _exact_int(raw.get("test_date_count"), "test_date_count") != len(test_dates)
            or len(observed_test_dates) != test_date_count
            or _exact_int(raw.get("purge_trading_days"), "purge_trading_days") != purge
            or _exact_int(raw.get("embargo_trading_days"), "embargo_trading_days") != embargo
        ):
            raise CurrentRestatedOutcomeStoreError("fold date counts/policy do not match actual indices")
        fold_id = raw.get("fold_id")
        if type(fold_id) is not str or fold_id != f"fold-{fold_index:03d}":
            raise CurrentRestatedOutcomeStoreError("fold ids are not canonical")
        folds.append(
            CurrentRestatedOutcomeFoldV1(
                fold_id=fold_id,
                train_sample_ids=train_ids,
                test_sample_ids=test_ids,
                train_date_count=len(observed_train_dates),
                test_date_count=len(test_dates),
                train_end_date=train_dates[-1],
                test_start_date=test_start,
                test_end_date=test_dates[-1],
                purge_trading_days=purge,
                embargo_trading_days=embargo,
                max_train_label_end_date=max_end,
                train_date_indices=train_indices,
                test_date_indices=test_indices,
            )
        )
    return tuple(folds)


def _rebuild_verified_observations(
    *,
    rows: tuple[dict[str, Any], ...],
    values: np.ndarray[Any, Any],
    missing: np.ndarray[Any, Any],
    quality: np.ndarray[Any, Any],
    stale: np.ndarray[Any, Any],
    labels: np.ndarray[Any, Any],
    label_missing: np.ndarray[Any, Any],
    feature_registry: tuple[CurrentRestatedOutcomeFeatureV1, ...],
    label_registry: tuple[str, ...],
    raw_source_rows: Mapping[tuple[str, str, str, date], Mapping[str, Any]],
    expected_labels: Mapping[tuple[str, date], tuple[CurrentRestatedOutcomeLabelV1, ...]],
    feature_registry_sha256: str,
    source_context_bundle_sha256: str,
    benchmark_entity_id: str,
    current_freeze: datetime,
    artifact_available_at: datetime,
) -> tuple[CurrentRestatedOutcomeObservationV1, ...]:
    if label_registry != LABEL_METRICS:
        raise CurrentRestatedOutcomeStoreError("label registry order is unsupported")
    result: list[CurrentRestatedOutcomeObservationV1] = []
    seen_sample_ids: set[str] = set()
    seen_symbol_dates: set[tuple[str, date]] = set()
    for index, row in enumerate(rows):
        event_date = _iso_date(row.get("event_date"), "observation.event_date")
        symbol = row.get("symbol")
        if type(symbol) is not str or not symbol:
            raise CurrentRestatedOutcomeStoreError("observation symbol is invalid")
        identity_key = (symbol, event_date)
        if identity_key in seen_symbol_dates:
            raise CurrentRestatedOutcomeStoreError("observation repeats a symbol/event date")
        seen_symbol_dates.add(identity_key)
        if row.get("event_reference_only") is not True or row.get("original_source_available_at") is not None:
            raise CurrentRestatedOutcomeStoreError("stored observation clock semantics are invalid")
        if row.get("feature_registry_sha256") != feature_registry_sha256:
            raise CurrentRestatedOutcomeStoreError("observation feature registry pin mismatch")
        if row.get("source_context_bundle_sha256") != source_context_bundle_sha256:
            raise CurrentRestatedOutcomeStoreError("observation source context pin mismatch")
        available = _aware_datetime(row.get("current_value_available_at"), "current_value_available_at")
        if available != current_freeze or available > artifact_available_at:
            raise CurrentRestatedOutcomeStoreError("stored observation availability does not match frozen source capture")
        raw_source_refs: list[CurrentRestatedOutcomeSourceRowV1] = []
        raw_ref_keys: set[tuple[str, str, str, date]] = set()
        for source_ref in _mapping_sequence(row.get("source_rows"), "observation.source_rows"):
            source_table = source_ref.get("source_table")
            source_id = source_ref.get("source_id")
            entity_id = source_ref.get("entity_id")
            if (
                type(source_table) is not str
                or type(source_id) is not str
                or not source_id
                or type(entity_id) is not str
            ):
                raise CurrentRestatedOutcomeStoreError("observation source-row identity has invalid types")
            source_date = _iso_date(source_ref.get("event_date"), "source_row.event_date")
            key = (source_table, source_id, entity_id, source_date)
            if key in raw_ref_keys:
                raise CurrentRestatedOutcomeStoreError("observation repeats a source-row reference")
            raw_ref_keys.add(key)
            raw_row = raw_source_rows.get(key)
            if raw_row is None:
                raise CurrentRestatedOutcomeStoreError("observation source-row reference is not in pinned raw shards")
            source_hash = "sha256:" + _hash_pin(
                source_ref.get("source_row_hash"), "source_row.source_row_hash"
            )
            if source_hash != "sha256:" + _hash_pin(
                raw_row.get("source_row_hash"), "raw.source_row_hash"
            ):
                raise CurrentRestatedOutcomeStoreError("observation source-row hash differs from pinned raw row")
            stock_source_in_scope = (
                source_table in {"daily_prices", "technical_indicators"}
                and entity_id.split("|", 1)[0] == symbol
            )
            benchmark_source_in_scope = (
                source_table == "market_indices" and entity_id == benchmark_entity_id
            )
            derived_technical_source_in_scope = (
                source_table == "daily_prices"
                and source_id == "derived:daily_prices.ohlc"
                and stock_source_in_scope
                and _is_reviewed_daily_technical_source_row(
                    row=raw_row,
                    current_value_available_at=_aware_datetime(
                        raw_row.get("current_value_available_at"),
                        "raw_source.current_value_available_at",
                    ),
                )
            )
            if source_date != event_date or not (
                (stock_source_in_scope and source_id != "derived:daily_prices.ohlc")
                or derived_technical_source_in_scope
                or benchmark_source_in_scope
            ):
                raise CurrentRestatedOutcomeStoreError("observation source-row reference identity is out of scope")
            raw_source_refs.append(
                CurrentRestatedOutcomeSourceRowV1(
                    source_table=source_table,
                    source_id=source_id,
                    entity_id=entity_id,
                    event_date=source_date,
                    source_row_hash=source_hash,
                )
            )
        expected_ref_keys = {
            key
            for key in raw_source_rows
            if key[3] == event_date
            and (
                (
                    key[0] in {"daily_prices", "technical_indicators"}
                    and key[2].split("|", 1)[0] == symbol
                )
                or (key[0] == "market_indices" and key[2] == benchmark_entity_id)
            )
        }
        if raw_ref_keys != expected_ref_keys:
            raise CurrentRestatedOutcomeStoreError("observation source-row references omit or add raw rows")
        typed_source_rows = tuple(
            sorted(
                raw_source_refs,
                key=lambda item: (
                    item.source_table,
                    item.source_id,
                    item.entity_id,
                    item.event_date,
                ),
            )
        )
        source_row_hashes = sorted({item.source_row_hash for item in typed_source_rows})
        if _string_sequence(row.get("source_row_hashes"), "observation.source_row_hashes") != tuple(source_row_hashes):
            raise CurrentRestatedOutcomeStoreError("observation source-row hash inventory mismatch")
        source_payloads = [_source_row_payload(item) for item in typed_source_rows]
        expected_identity_hash = _hash_json(
            {
                "schema_version": "current-restated-outcome-sample-identity.v1",
                "symbol": symbol,
                "event_date": event_date.isoformat(),
                "benchmark_entity_id": benchmark_entity_id,
                "source_rows": source_payloads,
                "feature_registry_sha256": feature_registry_sha256,
                "source_context_bundle_sha256": source_context_bundle_sha256,
            }
        )
        source_identity_hash = row.get("source_row_identity_hash")
        if source_identity_hash != expected_identity_hash:
            raise CurrentRestatedOutcomeStoreError("observation source identity hash does not match raw row custody")
        expected_sample_id = _hash_json(
            {
                "symbol": symbol,
                "event_date": event_date.isoformat(),
                "source_row_identity_hash": expected_identity_hash,
            }
        )
        sample_id = row.get("sample_id")
        if type(sample_id) is not str or sample_id != expected_sample_id or sample_id in seen_sample_ids:
            raise CurrentRestatedOutcomeStoreError("observation sample id is invalid or duplicated")
        seen_sample_ids.add(sample_id)

        expected_feature_values: dict[str, int] = {
            item.feature_id: 0 for item in feature_registry
        }
        expected_feature_missing: dict[str, bool] = {
            item.feature_id: True for item in feature_registry
        }
        expected_feature_quality: dict[str, bool] = {
            item.feature_id: False for item in feature_registry
        }
        expected_feature_stale: dict[str, bool] = {
            item.feature_id: False for item in feature_registry
        }
        assigned_features: set[str] = set()
        for source_row_ref in typed_source_rows:
            raw_row = raw_source_rows[
                (
                    source_row_ref.source_table,
                    source_row_ref.source_id,
                    source_row_ref.entity_id,
                    source_row_ref.event_date,
                )
            ]
            raw_values = {
                str(item.get("feature_id")): item
                for item in _mapping_sequence(raw_row.get("values"), "raw source row values")
            }
            for feature in feature_registry:
                value = raw_values.get(feature.source_feature_id)
                source_role_matches = (
                    feature.role == "stock"
                    and feature.source_table == source_row_ref.source_table
                    and source_row_ref.entity_id.split("|", 1)[0] == symbol
                ) or (
                    feature.role == "benchmark"
                    and feature.source_table == "market_indices"
                    and source_row_ref.entity_id == benchmark_entity_id
                ) or (
                    feature.role == "stock"
                    and feature.source_table == "technical_indicators"
                    and source_row_ref.source_table == "daily_prices"
                    and source_row_ref.source_id == "derived:daily_prices.ohlc"
                    and source_row_ref.entity_id.split("|", 1)[0] == symbol
                    and value is not None
                    and _is_reviewed_daily_technical_derivation(
                        row=raw_row,
                        value=value,
                        feature_id=feature.source_feature_id,
                        expected_table=feature.source_table,
                        source_table=source_row_ref.source_table,
                        current_value_available_at=_aware_datetime(
                            raw_row.get("current_value_available_at"),
                            "raw_source.current_value_available_at",
                        ),
                    )
                )
                if not source_role_matches:
                    continue
                if value is None:
                    continue
                if feature.feature_id in assigned_features:
                    raise CurrentRestatedOutcomeStoreError("raw source assigned one feature more than once")
                assigned_features.add(feature.feature_id)
                integer = value.get("value_int")
                missing_flag = value.get("missing_mask")
                quality_flag = value.get("quality_blocked_mask")
                stale_flag = value.get("staleness_mask")
                if type(missing_flag) is not bool or missing_flag != (integer is None):
                    raise CurrentRestatedOutcomeStoreError("raw source feature value/missing mask mismatch")
                if type(quality_flag) is not bool or type(stale_flag) is not bool:
                    raise CurrentRestatedOutcomeStoreError("raw source feature masks are not boolean")
                expected_feature_values[feature.feature_id] = (
                    0 if integer is None else _exact_signed_int64(integer, "raw feature value_int")
                )
                expected_feature_missing[feature.feature_id] = missing_flag
                expected_feature_quality[feature.feature_id] = quality_flag
                expected_feature_stale[feature.feature_id] = stale_flag

        feature_values = tuple(_exact_signed_int64(item, "feature value") for item in values[index, :].tolist())
        feature_missing = tuple(bool(item) for item in missing[index, :].tolist())
        feature_quality = tuple(bool(item) for item in quality[index, :].tolist())
        feature_stale = tuple(bool(item) for item in stale[index, :].tolist())
        for feature_index, feature in enumerate(feature_registry):
            if (
                feature_values[feature_index] != expected_feature_values[feature.feature_id]
                or feature_missing[feature_index] != expected_feature_missing[feature.feature_id]
                or feature_quality[feature_index] != expected_feature_quality[feature.feature_id]
                or feature_stale[feature_index] != expected_feature_stale[feature.feature_id]
                or (feature_missing[feature_index] and feature_values[feature_index] != 0)
            ):
                raise CurrentRestatedOutcomeStoreError("numeric feature/mask arrays differ from pinned raw rows")

        row_labels = _mapping_sequence(row.get("labels"), "observation labels")
        label_by_horizon = {_exact_int(item.get("horizon"), "label.horizon"): item for item in row_labels}
        if len(label_by_horizon) != len(row_labels):
            raise CurrentRestatedOutcomeStoreError("observation repeats a label horizon")
        expected_row_labels = expected_labels.get(identity_key, ())
        expected_label_by_horizon = {item.horizon: item for item in expected_row_labels}
        if set(label_by_horizon) != set(expected_label_by_horizon):
            raise CurrentRestatedOutcomeStoreError("serialized labels differ from complete pinned T+1 paths")
        for horizon_index, horizon in enumerate(SUPPORTED_HORIZONS):
            metadata = label_by_horizon.get(horizon)
            mask = label_missing[index, horizon_index, :]
            if metadata is None:
                if not np.all(mask == 1):
                    raise CurrentRestatedOutcomeStoreError("missing horizon has observed numeric labels")
                continue
            if np.any(mask != 0):
                raise CurrentRestatedOutcomeStoreError("label row has partial metric masks")
            row_values = tuple(_exact_signed_int32(item, "label metric") for item in labels[index, horizon_index, :].tolist())
            expected_label = expected_label_by_horizon[horizon]
            if row_values != _label_metric_values(expected_label):
                raise CurrentRestatedOutcomeStoreError("numeric label array differs from recomputed raw-price outcomes")
            if metadata != _outcome_label_payload(expected_label):
                raise CurrentRestatedOutcomeStoreError("serialized label metadata differs from recomputed raw-price outcomes")
        result.append(
            CurrentRestatedOutcomeObservationV1(
                sample_id=sample_id,
                symbol=symbol,
                event_date=event_date,
                feature_values=feature_values,
                missing_mask=feature_missing,
                quality_blocked_mask=feature_quality,
                staleness_mask=feature_stale,
                source_row_identity_hash=expected_identity_hash,
                source_rows=typed_source_rows,
                current_value_available_at=available,
                labels=tuple(expected_row_labels),
            )
        )
    return tuple(result)


def _parse_feature_registry(value: object) -> tuple[CurrentRestatedOutcomeFeatureV1, ...]:
    result: list[CurrentRestatedOutcomeFeatureV1] = []
    for item in _mapping_sequence(value, "feature_registry"):
        result.append(
            CurrentRestatedOutcomeFeatureV1(
                feature_id=str(item["feature_id"]),
                source_feature_id=str(item["source_feature_id"]),
                source_table=str(item["source_table"]),
                role=str(item["role"]),
                unit=str(item["unit"]),
                decimal_exponent=_scale_exponent(item.get("decimal_exponent"), "decimal_exponent"),
                eligibility_status=str(item["eligibility_status"]),
            )
        )
    if not result or len({item.feature_id for item in result}) != len(result):
        raise CurrentRestatedOutcomeStoreError("feature registry is empty or duplicated")
    return tuple(result)


def _read_array(
    root: Path,
    arrays: Mapping[str, Any],
    name: str,
    *,
    dtype: str,
    repository_root: Path | None,
) -> np.ndarray[Any, Any]:
    item = _mapping(arrays.get(name), f"arrays.{name}")
    path = _resolve_pinned_artifact_file(
        root, item, repository_root=repository_root
    )
    raw = path.read_bytes()
    if len(raw) != _exact_int(item.get("bytes"), f"arrays.{name}.bytes"):
        raise CurrentRestatedOutcomeStoreError(f"array {name} byte count mismatch")
    if hashlib.sha256(raw).hexdigest() != _hash_pin(item.get("sha256"), f"arrays.{name}.sha256"):
        raise CurrentRestatedOutcomeStoreError(f"array {name} hash mismatch")
    shape = tuple(_exact_int(dimension, f"arrays.{name}.shape") for dimension in _sequence(item.get("shape"), f"arrays.{name}.shape"))
    array = np.frombuffer(raw, dtype=dtype)
    expected_cells = 1
    for dimension in shape:
        expected_cells *= dimension
    if array.size != expected_cells or str(array.dtype.str) != np.dtype(dtype).str:
        raise CurrentRestatedOutcomeStoreError(f"array {name} shape/dtype mismatch")
    return array.reshape(shape)


def _verify_staged_hash(record: Mapping[str, Any]) -> None:
    del record


def _parse_array_pins(
    arrays: Mapping[str, Any],
    *,
    artifact_root: Path,
    repository_root: Path | None,
) -> tuple[CurrentRestatedOutcomeArrayPinV1, ...]:
    required = {
        "feature_values": "<i8",
        "feature_missing_mask": "|u1",
        "feature_quality_blocked_mask": "|u1",
        "feature_staleness_mask": "|u1",
        "label_values": "<i4",
        "label_missing_mask": "|u1",
    }
    if set(arrays) != set(required):
        raise CurrentRestatedOutcomeStoreError("numeric array inventory is incomplete or has extra entries")
    result: list[CurrentRestatedOutcomeArrayPinV1] = []
    for name in sorted(required):
        item = _mapping(arrays.get(name), f"arrays.{name}")
        dtype = item.get("dtype")
        if dtype != required[name]:
            raise CurrentRestatedOutcomeStoreError(f"array {name} dtype is unsupported")
        path = _resolve_pinned_artifact_file(
            artifact_root, item, repository_root=repository_root
        )
        shape = tuple(
            _exact_int(dimension, f"arrays.{name}.shape")
            for dimension in _sequence(item.get("shape"), f"arrays.{name}.shape")
        )
        result.append(
            CurrentRestatedOutcomeArrayPinV1(
                name=name,
                path=str(path),
                bytes=_exact_int(item.get("bytes"), f"arrays.{name}.bytes"),
                sha256=_hash_pin(item.get("sha256"), f"arrays.{name}.sha256"),
                dtype=str(dtype),
                shape=shape,
            )
        )
    return tuple(result)


def _verify_pinned_artifact_file(
    root: Path,
    item: Mapping[str, Any],
    *,
    repository_root: Path | None,
) -> Path:
    relative = item.get("path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise CurrentRestatedOutcomeStoreError("artifact file path must be a safe relative path")
    path = _resolve_research_input_path(root / relative, repository_root=repository_root)
    if not path.is_relative_to(root.resolve(strict=True)):
        raise CurrentRestatedOutcomeStoreError("artifact file path escapes its run directory")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise CurrentRestatedOutcomeStoreError("artifact file is not regular")
    return path


def _resolve_pinned_artifact_file(
    root: Path,
    item: Mapping[str, Any],
    *,
    repository_root: Path | None,
) -> Path:
    path = _verify_pinned_artifact_file(
        root, item, repository_root=repository_root
    )
    info_before = path.stat()
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            count += len(block)
    info_after = path.stat()
    if (
        count != _exact_int(item.get("bytes"), "artifact file bytes")
        or digest.hexdigest() != _hash_pin(item.get("sha256"), "artifact file sha256")
        or info_before.st_size != info_after.st_size
        or info_before.st_mtime_ns != info_after.st_mtime_ns
    ):
        raise CurrentRestatedOutcomeStoreError("artifact file actual bytes changed")
    return path


def _capture_file(path: Path) -> _CapturedFile:
    lexical = Path(os.path.abspath(path))
    try:
        resolved = lexical.resolve(strict=True)
        info_before = resolved.stat()
        if not stat.S_ISREG(info_before.st_mode) or lexical.is_symlink():
            raise CurrentRestatedOutcomeStoreError(f"source pin is not a regular file: {lexical}")
        raw = resolved.read_bytes()
        info_after = resolved.stat()
        resolved_after = lexical.resolve(strict=True)
    except CurrentRestatedOutcomeStoreError:
        raise
    except (OSError, RuntimeError) as exc:
        raise CurrentRestatedOutcomeStoreError(f"source pin cannot be captured: {lexical}") from exc
    if (
        resolved_after != resolved
        or len(raw) != info_before.st_size
        or info_before.st_size != info_after.st_size
        or info_before.st_mtime_ns != info_after.st_mtime_ns
    ):
        raise CurrentRestatedOutcomeStoreError(f"source file changed while capturing: {lexical}")
    return _CapturedFile(resolved, raw, hashlib.sha256(raw).hexdigest(), len(raw), info_after.st_mtime_ns)


def _resolve_research_input_path(
    path: Path,
    *,
    repository_root: Path | None,
) -> Path:
    resolved = resolve_ml_research_output_path(
        path,
        repository_root=repository_root,
        access="read",
    )
    try:
        return resolved.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CurrentRestatedOutcomeStoreError(f"research input does not exist: {resolved}") from exc


def _verify_manifest_hash(manifest: Mapping[str, Any], *, label: str) -> None:
    recorded = _hash_pin(manifest.get("manifest_hash"), f"{label}.manifest_hash")
    unsigned = dict(manifest)
    unsigned.pop("manifest_hash", None)
    if _hash_json(unsigned) != "sha256:" + recorded:
        raise CurrentRestatedOutcomeStoreError(f"{label} canonical hash mismatch")


def _file_pin_payload(captured: _CapturedFile) -> dict[str, Any]:
    return {
        "path": str(captured.path),
        "bytes": captured.byte_count,
        "mtime_ns": captured.mtime_ns,
        "sha256": captured.sha256,
    }


def _parse_raw_shard_pins(value: object) -> tuple[CurrentRestatedOutcomeRawPinV1, ...]:
    result: list[CurrentRestatedOutcomeRawPinV1] = []
    for item in _mapping_sequence(value, "raw_shards"):
        result.append(
            CurrentRestatedOutcomeRawPinV1(
                role_id=str(item["role_id"]),
                path=str(item["path"]),
                bytes=_exact_int(item.get("bytes"), "raw_shard.bytes"),
                mtime_ns=_exact_int(item.get("mtime_ns"), "raw_shard.mtime_ns"),
                sha256=_hash_pin(item.get("sha256"), "raw_shard.sha256"),
                content_sha256=(
                    None if item.get("content_sha256") is None else "sha256:" + _hash_pin(item.get("content_sha256"), "raw_shard.content_sha256")
                ),
                row_count=(
                    None if item.get("row_count") is None else _exact_int(item.get("row_count"), "raw_shard.row_count")
                ),
            )
        )
    if not result:
        raise CurrentRestatedOutcomeStoreError("raw shard pin inventory is empty")
    return tuple(result)


def _load_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CurrentRestatedOutcomeStoreError(f"{label} is invalid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise CurrentRestatedOutcomeStoreError(f"{label} root must be an object")
    return value


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CurrentRestatedOutcomeStoreError(f"{label} must be an object")
    return dict(value)


def _mapping_sequence(value: object, label: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise CurrentRestatedOutcomeStoreError(f"{label} must be a list of objects")
    return tuple(dict(item) for item in value)


def _sequence(value: object, label: str) -> tuple[Any, ...]:
    if not isinstance(value, list):
        raise CurrentRestatedOutcomeStoreError(f"{label} must be a list")
    return tuple(value)


def _string_sequence(value: object, label: str) -> tuple[str, ...]:
    items = _sequence(value, label)
    if any(type(item) is not str or not item for item in items):
        raise CurrentRestatedOutcomeStoreError(f"{label} must contain non-empty strings")
    return tuple(items)


def _exact_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CurrentRestatedOutcomeStoreError(f"{label} must be a non-negative integer")
    return value


def _exact_signed_int64(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not _INT64_MIN <= value <= _INT64_MAX:
        raise CurrentRestatedOutcomeStoreError(f"{label} must fit signed int64")
    return value


def _exact_signed_int32(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not _INT32_MIN <= value <= _INT32_MAX:
        raise CurrentRestatedOutcomeStoreError(f"{label} must fit signed int32")
    return value


def _outcome_cost_contract_payload() -> dict[str, Any]:
    source_buy_cost = getattr(label_math, "_BUY_COST_BP", None)
    source_sell_cost = getattr(label_math, "_SELL_COST_BP", None)
    if (
        type(source_buy_cost) is not int
        or type(source_sell_cost) is not int
        or source_buy_cost != _OUTCOME_BUY_SIDE_COST_BP
        or source_sell_cost != _OUTCOME_SELL_SIDE_COST_BP
    ):
        raise CurrentRestatedOutcomeStoreError(
            "shared label-spool cost constants differ from the pinned outcome contract"
        )
    return {
        "schema_version": "portfolio-ml-outcome-cost-contract.v1",
        "cost_unit": "basis_points",
        "buy_side_cost_bp": _OUTCOME_BUY_SIDE_COST_BP,
        "sell_side_cost_bp": _OUTCOME_SELL_SIDE_COST_BP,
        "total_round_trip_cost_bp": _OUTCOME_TOTAL_ROUND_TRIP_COST_BP,
        "gross_stock_return_metric": "stock_return_bp",
        "gross_benchmark_return_metric": "benchmark_return_bp",
        "net_excess_metric": "benchmark_excess_return_bp",
        "net_excess_formula": (
            "stock_return_bp - benchmark_return_bp - buy_side_cost_bp - sell_side_cost_bp"
        ),
        "source": "data_module.portfolio_ml_dataset_assembler._build_label_spool",
    }


def _parse_outcome_cost_contract(
    value: object,
) -> CurrentRestatedOutcomeCostContractV1:
    payload = _mapping(value, "outcome_cost_contract")
    expected = _outcome_cost_contract_payload()
    for key in (
        "buy_side_cost_bp",
        "sell_side_cost_bp",
        "total_round_trip_cost_bp",
    ):
        if type(payload.get(key)) is not int:
            raise CurrentRestatedOutcomeStoreError(
                f"outcome cost contract {key} must be an exact integer"
            )
    if payload != expected:
        raise CurrentRestatedOutcomeStoreError(
            "outcome cost contract differs from the pinned standard round-trip cost semantics"
        )
    return CurrentRestatedOutcomeCostContractV1(
        schema_version=str(payload["schema_version"]),
        cost_unit=str(payload["cost_unit"]),
        buy_side_cost_bp=_exact_int(payload["buy_side_cost_bp"], "buy_side_cost_bp"),
        sell_side_cost_bp=_exact_int(payload["sell_side_cost_bp"], "sell_side_cost_bp"),
        total_round_trip_cost_bp=_exact_int(
            payload["total_round_trip_cost_bp"], "total_round_trip_cost_bp"
        ),
        gross_stock_return_metric=str(payload["gross_stock_return_metric"]),
        gross_benchmark_return_metric=str(payload["gross_benchmark_return_metric"]),
        net_excess_metric=str(payload["net_excess_metric"]),
        net_excess_formula=str(payload["net_excess_formula"]),
        source=str(payload["source"]),
    )


def _assert_outcome_cost_difference(
    *,
    stock_return_bp: int,
    benchmark_return_bp: int,
    benchmark_excess_return_bp: int,
) -> None:
    expected = (
        stock_return_bp
        - benchmark_return_bp
        - _OUTCOME_BUY_SIDE_COST_BP
        - _OUTCOME_SELL_SIDE_COST_BP
    )
    if benchmark_excess_return_bp != expected:
        raise CurrentRestatedOutcomeStoreError(
            "benchmark_excess_return_bp differs from gross returns less the pinned 80bp round-trip cost"
        )


def _strict_sql_bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    raise CurrentRestatedOutcomeStoreError(f"{label} must be SQL integer 0 or 1")


def _scale_exponent(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 18:
        raise CurrentRestatedOutcomeStoreError(f"{label} must be integer decimal exponent 0..18")
    return value


def _iso_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise CurrentRestatedOutcomeStoreError(f"{label} must be ISO date text")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise CurrentRestatedOutcomeStoreError(f"{label} is not an ISO date") from exc
    if result.isoformat() != value:
        raise CurrentRestatedOutcomeStoreError(f"{label} must use canonical ISO date")
    return result


def _aware_datetime(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise CurrentRestatedOutcomeStoreError(f"{label} is not ISO datetime") from exc
    else:
        raise CurrentRestatedOutcomeStoreError(f"{label} must be aware datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CurrentRestatedOutcomeStoreError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _hash_pin(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise CurrentRestatedOutcomeStoreError(f"{label} must be a SHA-256 pin")
    result = value.removeprefix("sha256:")
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result.casefold()):
        raise CurrentRestatedOutcomeStoreError(f"{label} must be a SHA-256 pin")
    return result.lower()


def _hash_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


__all__ = [
    "CurrentRestatedOutcomeFeatureV1",
    "CurrentRestatedOutcomeFoldV1",
    "CurrentRestatedOutcomeLabelV1",
    "CurrentRestatedOutcomeObservationV1",
    "CurrentRestatedOutcomePublication",
    "CurrentRestatedOutcomeStoreError",
    "CurrentRestatedOutcomeStoreRequest",
    "InsufficientMatureCurrentRestatedHistoryError",
    "PortfolioMLCurrentRestatedOutcomeStoreBuilder",
    "VerifiedCurrentRestatedOutcomeArtifact",
    "load_verified_current_restated_outcome_artifact",
]
