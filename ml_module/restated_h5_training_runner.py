"""由封存的重述資料列訓練並發布明確的研究版 release。

輸入中的歷史列不是歷史 point-in-time 資料。Runner 會驗證修訂快照確實在
``training_as_of`` 前觀測，僅以成熟且依時間切分的訓練列 fit 前處理與 heads，
並將 2026-05-20 之後的 heldout 評估與供當前研究使用的 final fit 分開。這條
路徑不修改 production pointer，也不開啟 formal OOS、alpha、portfolio action
或 broker order。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence, cast
from zoneinfo import ZoneInfo

# 這些限制只寫入目前訓練程序，並在數值套件匯入前設定。
for _thread_limit_name in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ[_thread_limit_name] = "2"

import joblib
import numpy as np
from numpy.typing import NDArray

from ml_module.allocation_out_of_core_training_service import (
    FLOAT_DTYPE,
    OOF_DTYPE,
    _LinearBoundaryModel,
    _deterministic_bounded_indexes,
    _fit_linear_base_expert,
    _quantize_head,
    _close_memmap,
    _current_rss_bytes,
)
from ml_module.allocation_release_contract import (
    AllocationReleaseManifest,
    CalibrationBinding,
    IntegerProbabilityCalibrator,
    MissingPolicyBinding,
    PreprocessorBinding,
    bytes_hash,
    canonical_json,
    feature_order_hash,
    payload_hash,
)
from ml_module.allocation_training_service import (
    CLASSIFICATION_EXPERT_HEADS,
    EXPERT_HEAD_IDS,
    REGRESSION_EXPERT_HEADS,
)
from ml_module.allocation_v3_linear_release import (
    _ConstantProbabilityModel,
    _ConstantRegressionModel,
)
from ml_module.allocation_family_weight_contract import (
    FAMILY_WEIGHT_POLICY_DEGENERATE_EQUAL_V1,
    FAMILY_WEIGHT_STATUS_DEGENERATE_UNIDENTIFIED_EQUAL,
)
from ml_module.allocation_rank_contract import RANK_CONTRACT_V2
from ml_module.ooc_cross_fitted_calibration import _fit_isotonic_mapping_bp


TAIPEI = ZoneInfo("Asia/Taipei")
FEATURE_COUNT = 62
LABEL_FIELDS = (
    "benchmark_excess_return_bp",
    "sector_excess_return_bp",
    "downside_observed",
    "mae_bp",
    "mfe_bp",
    "realized_volatility_bp",
    "max_drawdown_bp",
    "tail_loss_bp",
    "fill_feasible_observed",
)
REGRESSION_LABEL_POSITIONS = (0, 1, 3, 4, 5, 6, 7)
CLASSIFICATION_LABEL_POSITIONS = (2, 8)
HORIZONS = (5, 10, 20, 60)
REPAIR_HELDOUT_START = date(2026, 5, 20)
TRAINING_PROFILE = "sealed_restated_linear_shadow_v1"
PREPROCESSOR_STRATEGY = "train_only_bounded_median_standardize_missing_indicators_v1"
TARGET_AUDIT_MANIFEST_HASH = (
    "sha256:61d806ef005d0881911201104079c1acc92826a26bd8a331b9bd79156983ffe8"
)
TARGET_VALUES_AUDIT_HASH = (
    "sha256:4abe164961842e047cbbb96d2d980eb4241376f28c845253940ed5e79ecc937c"
)
ORIGINAL_DIRECT_TARGET_ROW_COUNT = 3_353_096
CORRECTED_SUBSET_APPENDED_ROW_COUNT = 1_533
_META_FIELDS = (
    "target_weight_bp",
    "delta_weight_bp",
    "risk_contribution_bp",
    "risky_budget_bp",
    "cash_bp",
)
_REGRESSION_COLUMN = {
    "expected_excess_return_bp": 0,
    "expected_sector_excess_return_bp": 1,
    "predicted_mae_bp": 3,
    "predicted_mfe_bp": 4,
    "predicted_realized_volatility_bp": 5,
    "predicted_max_drawdown_bp": 6,
    "predicted_tail_loss_bp": 7,
}
_CLASSIFICATION_COLUMN = {
    "downside_probability_bp": 2,
    "fill_feasibility_probability_bp": 8,
}
_TRAINING_SOURCE_FILES = (
    "ml_module/restated_h5_training_runner.py",
    "scripts/train_ml_allocation_restated_research.py",
    "data_module/ml_restatement_research_dataset.py",
    "data_module/ml_restatement_current_inputs.py",
    "ml_module/restated_research_input_contract.py",
    "app_module/restated_allocation_shadow_service.py",
    "scripts/run_ml_allocation_restated_shadow.py",
    "ml_module/allocation_out_of_core_training_service.py",
    "ml_module/allocation_v3_linear_release.py",
    "ml_module/ooc_cross_fitted_calibration.py",
    "ml_module/allocation_release_contract.py",
    "ml_module/allocation_family_weight_contract.py",
    "ml_module/allocation_rank_contract.py",
    "ml_module/allocation_training_service.py",
    "app_module/allocation_release_adapter.py",
    "app_module/ml_allocation_inference_service.py",
)
_V2_TRAINING_SOURCE_FILES = (
    "data_module/ml_restatement_research_dataset_v2_merge.py",
)
_TRAINING_DISTRIBUTIONS = (
    "numpy",
    "scikit-learn",
    "scipy",
    "joblib",
    "pyarrow",
    "threadpoolctl",
)


@dataclass
class ResearchArrays:
    """One validated, disk-backed snapshot; numeric fields stay in fixed ABI order."""

    root: Path
    manifest_path: Path
    manifest: dict[str, Any]
    manifest_file_hash: str
    partition_files: tuple[Path, ...]
    source_custody_path: Path | None
    source_custody_hash: str | None
    source_custody: dict[str, Any] | None
    feature_ids: tuple[str, ...]
    feature_scales: tuple[int, ...]
    feature_packs: tuple[tuple[str, tuple[str, ...]], ...]
    label_scales: tuple[int, ...]
    dataset_id: str
    dataset_identity_hash: str
    feature_registry_hash: str
    source_manifest_hashes: tuple[tuple[str, str], ...]
    training_as_of: str
    row_count: int
    features: np.memmap
    feature_values_i64: np.memmap
    row_ids: np.memmap
    symbols: np.memmap
    decision_days: np.memmap
    event_days: np.memmap
    event_at: np.memmap
    revision_at: np.memmap
    revision_ids: np.memmap
    heldout_flags: np.memmap
    labels: dict[int, np.memmap]
    label_masks: dict[int, np.memmap]
    label_maturities: dict[int, np.memmap]

    def verify_source_integrity(self, *, phase: str) -> None:
        """在載入、fit 前及 fit 後重驗封存來源與外部 custody sidecar。"""

        current_manifest = self.manifest_path.read_bytes()
        if _sha256(current_manifest) != self.manifest_file_hash:
            raise RuntimeError(f"sealed manifest changed during {phase}")
        current_payload = _json_object(current_manifest, field_name="research manifest")
        if current_payload != self.manifest:
            raise RuntimeError(f"sealed manifest content changed during {phase}")
        current_files = _dataset_files(self.root, self.manifest)
        if current_files != self.partition_files:
            raise RuntimeError(f"sealed partition inventory changed during {phase}")
        _verify_file_inventory(self.root, self.manifest, current_files)
        row_count = _verify_partition_metadata(self.root, self.manifest, current_files)
        if row_count != self.row_count:
            raise RuntimeError(f"sealed partition row count changed during {phase}")
        if self.source_custody_path is not None:
            if self.source_custody_hash is None:
                raise RuntimeError("source custody hash is missing")
            _load_and_validate_source_custody(
                self.source_custody_path,
                expected_hash=self.source_custody_hash,
                manifest_path=self.manifest_path,
                manifest_hash=self.manifest_file_hash,
                manifest=self.manifest,
                row_count=self.row_count,
            )
        if self.manifest.get("schema_version") == "portfolio-ml-restated-research-dataset.v2":
            _verify_v2_lineage_manifest_files(self.manifest)


class _ResearchLabelStore:
    """Duck-typed subset of the frozen numeric store reader protocol."""

    def __init__(self, data: ResearchArrays) -> None:
        self._data = data

    def read_label_batch(
        self,
        refs: NDArray[np.integer[Any]],
        horizon: int,
    ) -> tuple[NDArray[np.int32], NDArray[np.uint8]]:
        selected = np.asarray(refs, dtype=np.int64)
        wide_labels = np.asarray(self._data.labels[horizon][selected], dtype=np.int64)
        masks = np.asarray(self._data.label_masks[horizon][selected], dtype=np.uint8)
        observed = masks == 0
        limits = np.iinfo(np.int32)
        if np.any(observed & ((wide_labels < limits.min) | (wide_labels > limits.max))):
            raise OverflowError(f"h{horizon} observed label exceeds frozen int32 model ABI")
        for position in CLASSIFICATION_LABEL_POSITIONS:
            valid_class = observed[:, position]
            if np.any(valid_class & ~np.isin(wide_labels[:, position], (0, 1))):
                raise ValueError(f"h{horizon} classification label is outside 0/1")
        return (
            wide_labels.astype(np.int32, copy=False),
            masks,
        )


def load_sealed_research_rows(
    manifest_path: Path,
    *,
    scratch_root: Path,
    observed_as_of: datetime | None = None,
    source_custody_path: Path | None = None,
    source_custody_hash: str | None = None,
) -> ResearchArrays:
    """Validate the sealed Arrow interchange and materialize bounded memmaps."""

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - covered by runtime preflight
        raise RuntimeError("pyarrow is required for the sealed research dataset") from exc

    manifest_path = manifest_path.resolve()
    root = manifest_path.parent
    raw_manifest = manifest_path.read_bytes()
    manifest_file_hash = _sha256(raw_manifest)
    manifest = _json_object(raw_manifest, field_name="research manifest")
    feature_ids, feature_scales, feature_packs, label_scales = (
        _validate_complete_restatement_manifest(manifest)
    )
    lineage_revision_clocks: tuple[datetime, datetime] | None = None
    if manifest.get("schema_version") == "portfolio-ml-restated-research-dataset.v2":
        lineage_revision_clocks = _verify_v2_lineage_manifest_files(manifest)
    source_hashes_list = list(_read_source_hashes(manifest))
    dataset_source_id = "sealed_restated_research_dataset"
    if dataset_source_id in {source_id for source_id, _digest in source_hashes_list}:
        raise ValueError("source_manifest_hashes reserves the sealed dataset source id")
    source_hashes_list.append((dataset_source_id, manifest_file_hash))
    source_hashes = tuple(sorted(source_hashes_list))
    training_as_of = _read_text(
        manifest,
        "training_as_of",
        alternate=("revision_observed_at",),
    )
    cutoff = _aware_datetime(training_as_of, field_name="training_as_of")
    now = observed_as_of or datetime.now(TAIPEI)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("observed_as_of must be timezone-aware")
    if cutoff > now.astimezone(cutoff.tzinfo):
        raise ValueError("sealed dataset was observed after this training run")

    files = _dataset_files(root, manifest)
    _verify_file_inventory(root, manifest, files)
    row_count = _verify_partition_metadata(root, manifest, files)
    expected_manifest_row_count = manifest["row_count"]
    if row_count != expected_manifest_row_count:
        raise ValueError("manifest row_count differs from complete partition inventory")
    if row_count < 2:
        raise ValueError("sealed research dataset has too few rows")
    custody_path, custody_hash, source_custody = _load_source_custody_args(
        source_custody_path=source_custody_path,
        source_custody_hash=source_custody_hash,
        manifest_path=manifest_path,
        manifest_hash=manifest_file_hash,
        manifest=manifest,
        row_count=row_count,
    )
    _require_source_custody_for_row_count(row_count, custody_path)
    scratch_root = scratch_root.resolve()
    scratch_root.mkdir(parents=True, exist_ok=True)

    features = _open_memmap(scratch_root / "features.f32", np.dtype("<f4"), (row_count, FEATURE_COUNT))
    feature_values_i64 = _open_memmap(
        scratch_root / "feature_values.i8",
        np.dtype("<i8"),
        (row_count, FEATURE_COUNT),
    )
    row_ids = _open_memmap(scratch_root / "row_ids.s128", np.dtype("S128"), (row_count,))
    symbols = _open_memmap(scratch_root / "symbols.s32", np.dtype("S32"), (row_count,))
    decision_days = _open_memmap(scratch_root / "decision_days.i4", np.dtype("<i4"), (row_count,))
    event_days = _open_memmap(scratch_root / "event_days.i4", np.dtype("<i4"), (row_count,))
    event_at = _open_memmap(scratch_root / "event_at.s48", np.dtype("S48"), (row_count,))
    revision_at = _open_memmap(scratch_root / "revision_at.s48", np.dtype("S48"), (row_count,))
    revision_ids = _open_memmap(scratch_root / "revision_ids.s128", np.dtype("S128"), (row_count,))
    heldout_flags = _open_memmap(scratch_root / "heldout_flags.u1", np.dtype("u1"), (row_count,))
    labels: dict[int, np.memmap] = {}
    label_masks: dict[int, np.memmap] = {}
    label_maturities: dict[int, np.memmap] = {}
    for horizon in HORIZONS:
        labels[horizon] = _open_memmap(
            scratch_root / f"labels_h{horizon}.i8",
            np.dtype("<i8"),
            (row_count, len(LABEL_FIELDS)),
        )
        label_masks[horizon] = _open_memmap(
            scratch_root / f"label_masks_h{horizon}.u1",
            np.dtype("u1"),
            (row_count, len(LABEL_FIELDS)),
        )
        label_maturities[horizon] = _open_memmap(
            scratch_root / f"label_maturities_h{horizon}.i4",
            np.dtype("<i4"),
            (row_count,),
        )

    feature_scales_array = np.asarray(feature_scales, dtype=np.float64)
    label_scales_array = np.asarray(label_scales, dtype=np.int64)
    corrected_symbols = frozenset(
        manifest["dataset_lineage"]["corrected_subset"]["symbols"]
        if lineage_revision_clocks is not None
        else ()
    )
    offset = 0
    v2_target_observed_rows = 0
    seen_ids: set[str] = set()
    for path in files:
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=4096):
            count = batch.num_rows
            fields = batch.schema.names
            required = {
                "row_id", "symbol", "decision_date", "decision_at",
                "feature_event_asof_at", "feature_available_at",
                "revision_observed_at", "fold_role", "source_revision_id",
                "features_scaled_i64", "feature_missing_mask",
            }
            missing = required - set(fields)
            if missing:
                raise ValueError(f"sealed parquet lacks required columns: {sorted(missing)}")
            column = {name: batch.column(batch.schema.get_field_index(name)) for name in fields}
            row_id_values = column["row_id"].to_pylist()
            symbol_values = column["symbol"].to_pylist()
            decision_values = column["decision_date"].to_pylist()
            decision_at_values = column["decision_at"].to_pylist()
            event_values = column["feature_event_asof_at"].to_pylist()
            stock_event_values = column["stock_event_date"].to_pylist()
            market_event_values = column["market_event_date"].to_pylist()
            feature_available_values = column["feature_available_at"].to_pylist()
            revision_values = column["revision_observed_at"].to_pylist()
            revision_ids_values = column["source_revision_id"].to_pylist()
            fold_values = column["fold_role"].to_pylist()

            feature_raw = _fixed_list_values(column["features_scaled_i64"], count, FEATURE_COUNT)
            feature_mask = _fixed_list_values(column["feature_missing_mask"], count, FEATURE_COUNT)
            if np.any((feature_mask != 0) & (feature_mask != 1)):
                raise ValueError("feature_missing_mask must use 0=observed and 1=missing")
            feature_null = _fixed_list_null_mask(column["features_scaled_i64"], count, FEATURE_COUNT)
            if np.any(feature_null != feature_mask.astype(bool)):
                raise ValueError("feature null values and feature_missing_mask disagree")
            scaled_features = feature_raw.astype(np.float64) / feature_scales_array[None, :]
            scaled_features[feature_mask.astype(bool)] = np.nan
            stored_raw = feature_raw.astype(np.int64)
            stored_raw[feature_mask.astype(bool)] = 0
            feature_values_i64[offset : offset + count, :] = stored_raw
            if np.any(~np.isfinite(scaled_features[feature_mask == 0])):
                raise ValueError("observed features must be finite")
            features[offset : offset + count, :] = scaled_features.astype(FLOAT_DTYPE)

            if manifest.get("schema_version") == "portfolio-ml-restated-research-dataset.v2":
                target_values = _fixed_list_values(column["target_values_i32"], count, 6)
                target_masks = _fixed_list_values(column["target_missing_mask"], count, 6)
                if np.any((target_masks != 0) & (target_masks != 1)):
                    raise ValueError("target_missing_mask must use 0=observed and 1=missing")
                target_nulls = _fixed_list_null_mask(column["target_values_i32"], count, 6)
                if np.any(target_nulls != target_masks.astype(bool)):
                    raise ValueError("v2 target null values and missing mask disagree")
                all_missing = np.all(target_masks == 1, axis=1)
                all_observed = np.all(target_masks == 0, axis=1)
                if np.any(~(all_missing | all_observed)):
                    raise ValueError("v2 target rows must be wholly observed or wholly missing")
                expected_cash_only = np.asarray([0, 0, 0, 0, 10_000, 0], dtype=np.int64)
                if np.any(
                    all_observed
                    & np.any(target_values != expected_cash_only[None, :], axis=1)
                ):
                    raise ValueError("v2 observed original target rows must preserve exact cash-only values")
                v2_target_observed_rows += int(np.sum(all_observed))

            canonical_ids: list[str] = []
            decision_ordinals = np.empty(count, dtype=np.int32)
            event_ordinals = np.empty(count, dtype=np.int32)
            heldout_batch = np.zeros(count, dtype=np.uint8)
            for index in range(count):
                row_id = _required_row_text(row_id_values[index], "row_id")
                if row_id in seen_ids:
                    raise ValueError(f"duplicate sealed research row id: {row_id}")
                seen_ids.add(row_id)
                canonical_ids.append(row_id)
                symbol = _required_row_text(symbol_values[index], "symbol")
                decision_date = _as_date(decision_values[index], "decision_date")
                decision_at = _aware_datetime(str(decision_at_values[index]), field_name="decision_at")
                expected_decision_at = datetime.combine(
                    decision_date, time(8, 30), TAIPEI
                )
                if decision_at != expected_decision_at:
                    raise ValueError(f"decision_at is not 08:30 Taipei on decision_date: {row_id}")
                feature_available = _aware_datetime(
                    str(feature_available_values[index]), field_name="feature_available_at"
                )
                revision_time = _aware_datetime(
                    str(revision_values[index]), field_name="revision_observed_at"
                )
                revision_id = _required_row_text(revision_ids_values[index], "source_revision_id")
                if (
                    manifest.get("schema_version")
                    == "portfolio-ml-restated-research-dataset.v2"
                    and revision_id != manifest.get("revision")
                ):
                    raise ValueError(
                        f"v2 row revision id differs from the sealed source snapshot: {row_id}"
                    )
                if lineage_revision_clocks is not None:
                    parent_clock, corrected_clock = lineage_revision_clocks
                    expected_row_clock = (
                        corrected_clock if symbol in corrected_symbols else parent_clock
                    )
                    if revision_time != expected_row_clock or feature_available != revision_time:
                        raise ValueError(
                            f"v2 row clocks differ from the truthful parent/subset source clock: {row_id}"
                        )
                stock_event_date = (
                    None
                    if stock_event_values[index] is None
                    else _as_date(stock_event_values[index], "stock_event_date")
                )
                market_event_date = (
                    None
                    if market_event_values[index] is None
                    else _as_date(market_event_values[index], "market_event_date")
                )
                raw_event_at = event_values[index]
                if (stock_event_date is None) != (raw_event_at is None):
                    raise ValueError(
                        f"stock event date and feature_event_asof_at disagree: {row_id}"
                    )
                if stock_event_date is None:
                    if np.any(feature_mask[index, 21:] == 0):
                        raise ValueError(
                            f"row without a stock event has observed stock-only features: {row_id}"
                        )
                    event_time = None
                else:
                    event_time = _aware_datetime(
                        raw_event_at, field_name="feature_event_asof_at"
                    )
                    expected_stock_close = datetime.combine(
                        stock_event_date, time(14, 30), TAIPEI
                    )
                    if event_time != expected_stock_close:
                        raise ValueError(
                            f"feature event clock does not match stock_event_date close: {row_id}"
                        )
                    if event_time >= decision_at:
                        raise ValueError(f"feature event is not strictly before decision: {row_id}")
                if stock_event_date is not None and stock_event_date >= decision_date:
                    raise ValueError(f"stock event date is not before decision: {row_id}")
                if market_event_date is not None and market_event_date >= decision_date:
                    raise ValueError(f"market event date is not before decision: {row_id}")
                if market_event_date is None and np.any(feature_mask[index, 10:21] == 0):
                    raise ValueError(
                        f"row without a market event has observed market/sector features: {row_id}"
                    )
                if feature_available > cutoff or revision_time > cutoff:
                    raise ValueError(f"row revision is newer than training_as_of: {row_id}")
                if feature_available > revision_time:
                    raise ValueError(f"feature availability follows its revision observation: {row_id}")
                if revision_time > now.astimezone(revision_time.tzinfo):
                    raise ValueError(f"row revision was observed in the future: {row_id}")
                decision_ordinals[index] = decision_date.toordinal()
                event_ordinals[index] = (
                    -1 if event_time is None else event_time.astimezone(TAIPEI).date().toordinal()
                )
                heldout_batch[index] = int(
                    str(fold_values[index]) == "heldout_revision"
                    or decision_date >= REPAIR_HELDOUT_START
                )
                row_ids[offset + index] = row_id.encode("utf-8")
                symbols[offset + index] = symbol.encode("utf-8")
                event_at[offset + index] = (
                    b"" if raw_event_at is None else str(raw_event_at).encode("utf-8")
                )
                revision_at[offset + index] = str(revision_values[index]).encode("utf-8")
                revision_ids[offset + index] = revision_id.encode("utf-8")
            if len(canonical_ids) != count:
                raise AssertionError("row id batch length mismatch")
            decision_days[offset : offset + count] = decision_ordinals
            event_days[offset : offset + count] = event_ordinals
            heldout_flags[offset : offset + count] = heldout_batch

            label_end_values_by_horizon = {
                horizon: column[f"label_end_date_h{horizon}"].to_pylist()
                for horizon in HORIZONS
                if f"label_end_date_h{horizon}" in column
            }
            for horizon in HORIZONS:
                label_name = f"labels_h{horizon}_i64"
                mask_name = f"labels_h{horizon}_missing_mask"
                maturity_name = f"maturity_at_h{horizon}"
                if label_name not in column or mask_name not in column or maturity_name not in column:
                    raise ValueError(f"sealed parquet lacks the h{horizon} label contract")
                raw_labels = _fixed_list_values(column[label_name], count, len(LABEL_FIELDS))
                masks = _fixed_list_values(column[mask_name], count, len(LABEL_FIELDS))
                if np.any((masks != 0) & (masks != 1)):
                    raise ValueError(f"{mask_name} must use 0=observed and 1=missing")
                nulls = _fixed_list_null_mask(column[label_name], count, len(LABEL_FIELDS))
                if np.any(nulls != masks.astype(bool)):
                    raise ValueError(f"{label_name} null values and missing mask disagree")
                values = raw_labels.astype(np.int64)
                for label_position, scale in enumerate(label_scales_array):
                    selected = values[:, label_position]
                    valid = masks[:, label_position] == 0
                    if np.any(selected[valid] % scale != 0):
                        raise ValueError(f"{label_name} cannot be represented exactly in bp")
                    selected[valid] //= scale
                    values[:, label_position] = selected
                maturity_values = column[maturity_name].to_pylist()
                label_end_values = label_end_values_by_horizon[horizon]
                maturity_ordinals = np.full(count, -1, dtype=np.int32)
                for index, value in enumerate(maturity_values):
                    if value is not None:
                        maturity_time = _aware_datetime(value, field_name=f"{maturity_name}[{index}]")
                        maturity_date = maturity_time.astimezone(TAIPEI).date()
                        if maturity_date < _as_date(
                            label_end_values[index],
                            f"label_end_date_h{horizon}",
                        ):
                            raise ValueError(f"h{horizon} label maturity precedes label end")
                        if np.any(masks[index] == 0) and maturity_time > cutoff:
                            raise ValueError(
                                f"unmatured h{horizon} labels cannot enter this training snapshot"
                            )
                        maturity_ordinals[index] = maturity_date.toordinal()
                observed = masks == 0
                if np.any(observed & (maturity_ordinals[:, None] < 0)):
                    raise ValueError(f"observed h{horizon} labels require maturity timestamps")
                labels[horizon][offset : offset + count, :] = values
                label_masks[horizon][offset : offset + count, :] = masks
                label_maturities[horizon][offset : offset + count] = maturity_ordinals
            offset += count

    if offset != row_count:
        raise ValueError("parquet row count changed while loading sealed dataset")
    if manifest.get("schema_version") == "portfolio-ml-restated-research-dataset.v2":
        expected_target_rows = int(
            manifest["original_row_target_audit"]["target_observed_row_count"]
        )
        if v2_target_observed_rows != expected_target_rows:
            raise ValueError(
                "v2 observed original targets do not account for all preserved parent rows"
            )
    for item in (
        features, row_ids, symbols, decision_days, event_days, event_at,
        revision_at, revision_ids, heldout_flags, feature_values_i64,
        *labels.values(), *label_masks.values(), *label_maturities.values(),
    ):
        item.flush()

    dataset_id = str(manifest["dataset_id"])
    dataset_identity_hash = str(manifest["dataset_identity_hash"])
    feature_registry_hash = _normalize_sha(
        manifest["feature_registry_hash"], "manifest.feature_registry_hash"
    )
    result = ResearchArrays(
        root=root,
        manifest_path=manifest_path,
        manifest=manifest,
        manifest_file_hash=manifest_file_hash,
        partition_files=files,
        source_custody_path=custody_path,
        source_custody_hash=custody_hash,
        source_custody=source_custody,
        feature_ids=feature_ids,
        feature_scales=feature_scales,
        feature_packs=feature_packs,
        label_scales=label_scales,
        dataset_id=dataset_id,
        dataset_identity_hash=dataset_identity_hash,
        feature_registry_hash=feature_registry_hash,
        source_manifest_hashes=source_hashes,
        training_as_of=training_as_of,
        row_count=row_count,
        features=features,
        feature_values_i64=feature_values_i64,
        row_ids=row_ids,
        symbols=symbols,
        decision_days=decision_days,
        event_days=event_days,
        event_at=event_at,
        revision_at=revision_at,
        revision_ids=revision_ids,
        heldout_flags=heldout_flags,
        labels=labels,
        label_masks=label_masks,
        label_maturities=label_maturities,
    )
    result.verify_source_integrity(phase="materialization")
    return result


def chronological_split(
    data: ResearchArrays,
    *,
    horizon: int,
) -> dict[str, Any]:
    """Freeze train/calibration/heldout by event sessions, maturity, and purge."""

    if horizon not in HORIZONS:
        raise ValueError("unsupported horizon")
    unique_days = np.unique(np.asarray(data.decision_days, dtype=np.int32))
    heldout_candidates = unique_days[
        (unique_days >= REPAIR_HELDOUT_START.toordinal())
        & (np.bincount(
            np.searchsorted(unique_days, np.asarray(data.decision_days, dtype=np.int32)),
            weights=np.asarray(data.heldout_flags, dtype=np.int64),
            minlength=len(unique_days),
        ) > 0)
    ]
    if len(heldout_candidates) == 0:
        raise ValueError("repair heldout has no rows on/after 2026-05-20")
    heldout_start_ordinal = int(heldout_candidates[0])
    heldout_start_index = int(np.searchsorted(unique_days, heldout_start_ordinal))
    max_requested_horizon = horizon
    if heldout_start_index < 60 + 5 + 30 + 5 + 30 + 60:
        raise ValueError(
            "insufficient pre-heldout sessions for horizon maturity, calibration windows, and 60-session purge"
        )

    # Both calibration windows must be fully label-mature before heldout.
    # For H60, the latest calibration decision is 65 sessions before heldout:
    # 60 outcome sessions plus a five-session embargo.  The earlier window is
    # separated by a five-session inter-fold embargo.
    cal2_stop_index = heldout_start_index - max_requested_horizon - 5
    cal2_start_index = cal2_stop_index - 29
    cal1_stop_index = cal2_start_index - 6
    cal1_start_index = cal1_stop_index - 29
    train_stop_index = cal1_start_index - 60
    if train_stop_index <= 1:
        raise ValueError("insufficient train sessions after the frozen 60-session purge")
    train_maturity_cutoff = int(unique_days[train_stop_index])
    cal1_first = int(unique_days[cal1_start_index])
    cal1_last = int(unique_days[cal1_stop_index])
    cal2_first = int(unique_days[cal2_start_index])
    cal2_last = int(unique_days[cal2_stop_index])
    asof_day = _aware_datetime(data.training_as_of, field_name="training_as_of").astimezone(TAIPEI).date().toordinal()

    decisions = np.asarray(data.decision_days, dtype=np.int32)
    maturities = np.asarray(data.label_maturities[horizon], dtype=np.int32)
    masks = np.asarray(data.label_masks[horizon], dtype=np.uint8)
    any_observed = np.any(masks == 0, axis=1)
    matured = (maturities >= 0) & (maturities <= asof_day)
    train_mask = (
        (decisions < train_maturity_cutoff)
        & (maturities < train_maturity_cutoff)
        & any_observed
        & matured
    )
    cal1_mask = (
        (decisions >= cal1_first)
        & (decisions <= cal1_last)
        & (maturities < heldout_start_ordinal)
        & matured
    )
    cal2_mask = (
        (decisions >= cal2_first)
        & (decisions <= cal2_last)
        & (maturities < heldout_start_ordinal)
        & matured
    )
    heldout_mask = (
        (decisions >= heldout_start_ordinal)
        & (np.asarray(data.heldout_flags, dtype=np.uint8) == 1)
        & matured
        & any_observed
    )
    train_refs = np.flatnonzero(train_mask).astype(np.int64)
    cal1_refs = np.flatnonzero(cal1_mask).astype(np.int64)
    cal2_refs = np.flatnonzero(cal2_mask).astype(np.int64)
    heldout_refs = np.flatnonzero(heldout_mask).astype(np.int64)
    if len(train_refs) < 2 or len(cal1_refs) == 0 or len(cal2_refs) == 0 or len(heldout_refs) == 0:
        raise ValueError(
            "chronological split is incomplete: need matured train, both calibration folds, and heldout rows"
        )
    return {
        "horizon": horizon,
        "session_count": int(len(unique_days)),
        "heldout_start": date.fromordinal(heldout_start_ordinal).isoformat(),
        "train_last_decision": date.fromordinal(int(unique_days[train_stop_index - 1])).isoformat(),
        "train_maturity_cutoff_exclusive": date.fromordinal(train_maturity_cutoff).isoformat(),
        "calibration_folds": {
            "calibration-pre-heldout-a": {
                "start": date.fromordinal(cal1_first).isoformat(),
                "end": date.fromordinal(cal1_last).isoformat(),
                "row_count": int(len(cal1_refs)),
            },
            "calibration-pre-heldout-b": {
                "start": date.fromordinal(cal2_first).isoformat(),
                "end": date.fromordinal(cal2_last).isoformat(),
                "row_count": int(len(cal2_refs)),
            },
        },
        "purge_sessions": 60,
        "calibration_interfold_embargo_sessions": 5,
        "heldout_embargo_sessions": 5,
        "calibration_maturity_horizon_sessions": horizon,
        "heldout_label_maturity_before_start": True,
        "feature_event_missing_stock_event_rows": {
            "dataset": int(np.sum(np.asarray(data.event_days, dtype=np.int32) < 0)),
            "training_candidates": int(np.sum(np.asarray(data.event_days[train_refs]) < 0)),
            "calibration_a": int(np.sum(np.asarray(data.event_days[cal1_refs]) < 0)),
            "calibration_b": int(np.sum(np.asarray(data.event_days[cal2_refs]) < 0)),
            "heldout": int(np.sum(np.asarray(data.event_days[heldout_refs]) < 0)),
        },
        "train_refs": train_refs,
        "calibration_a_refs": cal1_refs,
        "calibration_b_refs": cal2_refs,
        "heldout_refs": heldout_refs,
        "matured_row_count": int(np.sum(matured)),
    }


def train_and_publish(
    *,
    manifest_path: Path,
    output_root: Path,
    horizons: Sequence[int] = (5,),
    max_fit_rows: int | None = None,
    batch_size: int = 8_192,
    logistic_iterations: int = 6,
    run_current_smoke: bool = True,
    observed_as_of: datetime | None = None,
    invocation_argv: Sequence[str] | None = None,
    source_custody_path: Path | None = None,
    source_custody_hash: str | None = None,
) -> dict[str, Any]:
    """Run fixed chronological evaluation, mature-row final fit, and release readback."""

    normalized_horizons = tuple(sorted(set(int(value) for value in horizons)))
    if not normalized_horizons or any(value not in HORIZONS for value in normalized_horizons):
        raise ValueError("horizons must be a non-empty subset of 5/10/20/60")
    if max_fit_rows is not None and (max_fit_rows < 100 or max_fit_rows > 100_000):
        raise ValueError("max_fit_rows must be within 100..100000 when set")
    effective_fit_limit = max_fit_rows
    if effective_fit_limit is None and normalized_horizons != (5,):
        effective_fit_limit = 100_000
    if batch_size <= 0 or batch_size > 65_536:
        raise ValueError("batch_size must be within 1..65536")
    if logistic_iterations <= 0 or logistic_iterations > 100:
        raise ValueError("logistic_iterations must be within 1..100")
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    from threadpoolctl import threadpool_info, threadpool_limits

    dataset_schema_version = _read_declared_dataset_schema_version(manifest_path)

    thread_limit_context = threadpool_limits(limits=2)
    thread_limit_context.__enter__()
    staging: Path | None = None
    try:
        runtime_binding = _collect_training_runtime_binding(
            invocation_argv=invocation_argv,
            dataset_schema_version=dataset_schema_version,
        )
        runtime_binding["threadpool_info_after_limit"] = threadpool_info()
        runtime_binding["threadpool_limit"] = 2
        if any(
            int(pool.get("num_threads", 0)) > 2
            for pool in runtime_binding["threadpool_info_after_limit"]
        ):
            raise RuntimeError("native numerical thread pool exceeded the two-thread cap")
        runtime_binding_at_start = json.loads(canonical_json(runtime_binding))
        staging = Path(tempfile.mkdtemp(prefix=".restated-fit-", dir=output_root))
    except BaseException:
        if staging is not None:
            _safe_remove_scratch(staging, output_root)
        thread_limit_context.__exit__(None, None, None)
        raise
    assert staging is not None
    runtime_resources = {
        "snapshots": [],
        "thread_limit": 2,
        "process_environment": {
            name: os.environ.get(name)
            for name in (
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
        "threadpool_info": runtime_binding["threadpool_info_after_limit"],
    }
    _record_runtime_memory(runtime_resources, "runner_start")
    try:
        data = load_sealed_research_rows(
            manifest_path,
            scratch_root=staging / "scratch",
            observed_as_of=observed_as_of,
            source_custody_path=source_custody_path,
            source_custody_hash=source_custody_hash,
        )
        _record_runtime_memory(runtime_resources, "sealed_snapshot_loaded")
        split_by_horizon: dict[int, dict[str, Any]] = {}
        evaluation_evidence: dict[int, dict[str, Any]] = {}
        evaluation_models_by_horizon: dict[int, dict[str, dict[str, Any]]] = {}
        final_models: dict[str, dict[str, Any]] = {}
        final_fit_evidence: dict[int, dict[str, Any]] = {}
        calibration_horizon_counts: dict[int, int] = {
            horizon: 0 for horizon in normalized_horizons
        }
        receipt_sources: dict[tuple[int, str], Path] = {}
        calibration_counts = np.zeros(10_001, dtype=np.int64)
        calibration_positive = np.zeros(10_001, dtype=np.int64)
        calibration_fold_counts: dict[str, int] = {
            "calibration-pre-heldout-a": 0,
            "calibration-pre-heldout-b": 0,
        }
        calibration_event_missing_counts: dict[int, dict[str, int]] = {
            horizon: {
                "calibration-pre-heldout-a": 0,
                "calibration-pre-heldout-b": 0,
            }
            for horizon in normalized_horizons
        }
        store = _ResearchLabelStore(data)

        data.verify_source_integrity(phase="pre-fit")
        for horizon in normalized_horizons:
            split = chronological_split(data, horizon=horizon)
            split_by_horizon[horizon] = split
            all_train_refs = np.asarray(split["train_refs"], dtype=np.int64)
            train_refs = _bounded_fit_refs(all_train_refs, effective_fit_limit)
            cal_sets = (
                ("calibration-pre-heldout-a", np.asarray(split["calibration_a_refs"], dtype=np.int64)),
                ("calibration-pre-heldout-b", np.asarray(split["calibration_b_refs"], dtype=np.int64)),
            )
            heldout_refs = np.asarray(split["heldout_refs"], dtype=np.int64)
            evaluation_evidence[horizon] = {
                key: value
                for key, value in split.items()
                if key.endswith("refs") is False
            }
            evaluation_evidence[horizon]["full_training_candidate_count"] = len(all_train_refs)
            evaluation_evidence[horizon]["evaluation_fit_row_count"] = len(train_refs)
            evaluation_evidence[horizon]["evaluation_fit_missing_stock_event_rows"] = int(
                np.sum(np.asarray(data.event_days[train_refs], dtype=np.int32) < 0)
            )
            evaluation_evidence[horizon]["evaluation_fit_row_ids_hash"] = _row_id_hash(
                data, train_refs
            )
            evaluation_evidence[horizon]["heldout_missing_stock_event_rows"] = int(
                np.sum(np.asarray(data.event_days[heldout_refs], dtype=np.int32) < 0)
            )

            horizon_models: dict[str, dict[str, Any]] = {}
            naive_predictions, naive_summary = _fit_naive_baseline(
                store=store,
                horizon=horizon,
                train_refs=train_refs,
                prediction_count=len(heldout_refs),
                batch_size=batch_size,
            )
            for pack_id, pack_features in data.feature_packs:
                columns = np.asarray(
                    [data.feature_ids.index(feature_id) for feature_id in pack_features],
                    dtype=np.int64,
                )
                eval_dir = staging / "evaluation" / f"h{horizon}" / pack_id
                eval_dir.mkdir(parents=True, exist_ok=True)
                train_matrix = _materialize_feature_matrix(
                    data=data,
                    refs=train_refs,
                    columns=columns,
                    path=eval_dir / "train.raw.f32",
                    batch_size=batch_size,
                )
                heldout_matrix = _materialize_feature_matrix(
                    data=data,
                    refs=heldout_refs,
                    columns=columns,
                    path=eval_dir / "heldout.raw.f32",
                    batch_size=batch_size,
                )
                oof = np.zeros((len(heldout_refs), len(EXPERT_HEAD_IDS) * 2 + 1), dtype=OOF_DTYPE)
                try:
                    eval_records = _fit_linear_base_expert(
                        store=store,  # type: ignore[arg-type]
                        horizon=horizon,
                        train_refs=train_refs,
                        test_refs=heldout_refs,
                        train_matrix=train_matrix,
                        test_matrix=heldout_matrix,
                        # 凍結 fit helper 只以索引寫入 OOF buffer；ndarray 符合其執行期需求。
                        oof=cast(np.memmap | None, oof),
                        output_directory=eval_dir,
                        ridge_alpha=Decimal(100) / Decimal(10_000),
                        logistic_iterations=logistic_iterations,
                        batch_size=batch_size,
                    )
                finally:
                    _close_memmap(train_matrix)
                    _close_memmap(heldout_matrix)
                eval_models = _load_head_models(eval_dir, eval_records)
                _record_runtime_memory(
                    runtime_resources, f"h{horizon}_{pack_id}_evaluation_fit"
                )
                horizon_models[pack_id] = {"models": eval_models, "records": eval_records}
                evaluation_evidence[horizon].setdefault("packs", {})[pack_id] = {
                    "fit_records": eval_records,
                    "heldout_metrics": _score_oof(
                        store, data, horizon, heldout_refs, oof
                    ),
                    "heldout_train_only_naive_baseline": _score_oof(
                        store, data, horizon, heldout_refs, naive_predictions
                    ),
                    "train_only_naive_fit": naive_summary,
                    "heldout_row_count": int(len(heldout_refs)),
                }
                receipt_path = (
                    staging
                    / "evaluation_receipts"
                    / f"h{horizon}-{pack_id}.parquet"
                )
                receipt_path.parent.mkdir(parents=True, exist_ok=True)
                receipt_rows = _write_heldout_prediction_receipt(
                    path=receipt_path,
                    data=data,
                    store=store,
                    horizon=horizon,
                    pack_id=pack_id,
                    refs=heldout_refs,
                    predictions=np.asarray(oof[:, : len(EXPERT_HEAD_IDS)], dtype=np.int32),
                    naive_predictions=naive_predictions,
                    batch_size=batch_size,
                )
                receipt_file = f"heldout/h{horizon}-{pack_id}.parquet"
                receipt_sources[(horizon, pack_id)] = receipt_path
                evaluation_evidence[horizon]["packs"][pack_id][
                    "heldout_prediction_receipt"
                ] = {
                    "file": receipt_file,
                    "sha256": _file_sha256(receipt_path),
                    "row_count": receipt_rows,
                    "contains": [
                        "heldout row ids and dates",
                        "nine label bp values and per-label missing mask",
                        "nine ridge-logistic heldout predictions",
                        "nine train-only naive baseline predictions",
                    ],
                }

                for fold_id, refs in cal_sets:
                    _accumulate_calibration(
                        data=data,
                        horizon=horizon,
                        refs=refs,
                        models=eval_models,
                        feature_columns=columns,
                        counts=calibration_counts,
                        positives=calibration_positive,
                        batch_size=batch_size,
                    )
                    masks = np.asarray(data.label_masks[horizon][refs, 2], dtype=np.uint8)
                    valid_count = int(np.sum(masks == 0))
                    calibration_fold_counts[fold_id] += valid_count
                    calibration_horizon_counts[horizon] += valid_count
                    calibration_event_missing_counts[horizon][fold_id] += int(
                        np.sum(np.asarray(data.event_days[refs], dtype=np.int32) < 0)
                    )
            evaluation_models_by_horizon[horizon] = horizon_models

            mature_refs = _mature_training_refs(data, horizon)
            final_refs = _bounded_fit_refs(mature_refs, effective_fit_limit)
            if len(final_refs) < 2:
                raise ValueError(f"h{horizon} final fit has fewer than two mature rows")
            final_fit_evidence[horizon] = {
                "mature_row_candidate_count": int(len(mature_refs)),
                "mature_row_candidate_missing_stock_event_count": int(
                    np.sum(np.asarray(data.event_days[mature_refs], dtype=np.int32) < 0)
                ),
                "final_fit_row_count": int(len(final_refs)),
                "final_fit_missing_stock_event_count": int(
                    np.sum(np.asarray(data.event_days[final_refs], dtype=np.int32) < 0)
                ),
                "final_fit_row_ids_hash": _row_id_hash(data, final_refs),
            }
            final_pack_records: dict[str, Any] = {}
            for pack_id, pack_features in data.feature_packs:
                columns = np.asarray(
                    [data.feature_ids.index(feature_id) for feature_id in pack_features],
                    dtype=np.int64,
                )
                final_dir = staging / "final" / f"h{horizon}" / pack_id
                final_dir.mkdir(parents=True, exist_ok=True)
                final_matrix = _materialize_feature_matrix(
                    data=data,
                    refs=final_refs,
                    columns=columns,
                    path=final_dir / "train.raw.f32",
                    batch_size=batch_size,
                )
                try:
                    records = _fit_linear_base_expert(
                        store=store,  # type: ignore[arg-type]
                        horizon=horizon,
                        train_refs=final_refs,
                        test_refs=None,
                        train_matrix=final_matrix,
                        test_matrix=None,
                        oof=None,
                        output_directory=final_dir,
                        ridge_alpha=Decimal(100) / Decimal(10_000),
                        logistic_iterations=logistic_iterations,
                        batch_size=batch_size,
                    )
                finally:
                    _close_memmap(final_matrix)
                models = _load_head_models(final_dir, records)
                _record_runtime_memory(
                    runtime_resources, f"h{horizon}_{pack_id}_final_fit"
                )
                final_pack_records[pack_id] = {
                    "models": models,
                    "records": records,
                    "fit_refs": final_refs,
                }
            final_models[str(horizon)] = final_pack_records

        if calibration_fold_counts["calibration-pre-heldout-a"] < 2 or calibration_fold_counts[
            "calibration-pre-heldout-b"
        ] < 2:
            raise ValueError("both pre-heldout calibration folds need matured downside labels")
        if int(np.sum(calibration_positive)) == 0 or int(
            np.sum(calibration_counts - calibration_positive)
        ) == 0:
            raise ValueError("downside calibration requires both classes")
        mapping = _fit_isotonic_mapping_bp(calibration_counts, calibration_positive)
        for horizon in normalized_horizons:
            heldout_refs = np.asarray(split_by_horizon[horizon]["heldout_refs"], dtype=np.int64)
            for pack_id, _feature_ids in data.feature_packs:
                downside_model = evaluation_models_by_horizon[horizon][pack_id]["models"].get(
                    "downside_probability_bp"
                )
                if downside_model is None:
                    evaluation_evidence[horizon]["packs"][pack_id][
                        "heldout_calibrated_downside"
                    ] = {"status": "head_missing"}
                    continue
                columns = np.asarray(
                    [data.feature_ids.index(feature_id) for feature_id in _feature_ids],
                    dtype=np.int64,
                )
                raw_bp = _predict_probability_bp(
                    model=downside_model,
                    data=data,
                    refs=heldout_refs,
                    columns=columns,
                    batch_size=batch_size,
                )
                calibrated_bp = np.asarray(mapping[raw_bp], dtype=np.int64)
                label_values = np.asarray(data.labels[horizon][heldout_refs, 2], dtype=np.int64)
                label_mask = np.asarray(data.label_masks[horizon][heldout_refs, 2], dtype=np.uint8)
                valid = (label_mask == 0) & np.isin(label_values, (0, 1))
                if not np.any(valid):
                    calibrated_metrics = {"status": "no_mature_labels", "observation_count": 0}
                else:
                    observed_bp = label_values[valid] * 10_000
                    calibrated_metrics = {
                        "status": "evaluated",
                        "observation_count": int(np.sum(valid)),
                        "raw_brier_score_bp2": _mean_square_int(raw_bp[valid] - observed_bp),
                        "calibrated_brier_score_bp2": _mean_square_int(
                            calibrated_bp[valid] - observed_bp
                        ),
                        "calibrated_ece_bp": _calibration_ece_bp(
                            calibrated_bp[valid], label_values[valid]
                        ),
                    }
                evaluation_evidence[horizon]["packs"][pack_id][
                    "heldout_calibrated_downside"
                ] = calibrated_metrics
        data.verify_source_integrity(phase="fit-complete")
        runtime_binding_at_fit_complete = _collect_training_runtime_binding(
            invocation_argv=invocation_argv,
            dataset_schema_version=dataset_schema_version,
        )
        binding_keys = (
            "dataset_schema_version",
            "source_file_sha256",
            "software_versions",
            "python",
            "invocation_argv",
        )
        if any(
            runtime_binding_at_fit_complete[key] != runtime_binding_at_start[key]
            for key in binding_keys
        ):
            raise RuntimeError("training code or runtime dependency binding changed during fit")
        runtime_binding_at_start["source_rechecked_at_fit_complete"] = True
        runtime_binding_at_start["threadpool_info_at_fit_complete"] = threadpool_info()
        training_identity = _build_training_identity(
            data=data,
            horizons=normalized_horizons,
            evaluation=evaluation_evidence,
            final_fit=final_fit_evidence,
            calibration_counts=calibration_fold_counts,
            calibration_horizon_counts=calibration_horizon_counts,
            calibration_event_missing_counts=calibration_event_missing_counts,
            runtime_binding=runtime_binding_at_start,
            max_fit_rows=effective_fit_limit,
            batch_size=batch_size,
            logistic_iterations=logistic_iterations,
        )
        training_hash = payload_hash(training_identity)
        target_summary = _verified_cash_only_target_summary(training_hash)
        artifact_payload = _build_artifact_payload(
            data=data,
            horizons=normalized_horizons,
            final_models=final_models,
            training_hash=training_hash,
            target_summary=target_summary,
        )
        artifact_bytes = _joblib_bytes(artifact_payload)
        _record_runtime_memory(runtime_resources, "all_heads_fit_and_serialized")
        artifact_hash = bytes_hash(artifact_bytes)
        order_hash = feature_order_hash(data.feature_ids)
        model_id = _model_id(normalized_horizons)
        fold_ids = tuple(calibration_fold_counts)
        calibrator = IntegerProbabilityCalibrator.create(
            calibration_id="restated-calibration-" + payload_hash(
                {"training_hash": training_hash, "horizons": list(normalized_horizons)}
            )[7:23],
            model_id=model_id,
            feature_order_hash=order_hash,
            mapping_bp=tuple(int(value) for value in mapping),
            fit_fold_ids=fold_ids,
        )
        calibrator_bytes = (canonical_json(calibrator.to_dict()) + "\n").encode("utf-8")
        preprocessor_binding, preprocessor_bytes = _build_preprocessor_binding(
            model_id=model_id,
            order_hash=order_hash,
            training_hash=training_hash,
        )
        calibration_binding = CalibrationBinding(
            calibration_id=calibrator.calibration_id,
            model_id=model_id,
            method=calibrator.method,
            application="external_integer_bp",
            feature_order_hash=order_hash,
            artifact_file="calibrator.json",
            artifact_hash=bytes_hash(calibrator_bytes),
            fit_fold_ids=calibrator.fit_fold_ids,
        )
        missing_policy = MissingPolicyBinding.create(
            policy_id="restated-revision-aware-explicit-mask-cash-only-v1"
        )
        seed = {
            "training_hash": training_hash,
            "artifact_hash": artifact_hash,
            "calibrator_hash": calibration_binding.artifact_hash,
            "dataset_manifest_hash": data.manifest_file_hash,
        }
        release_id = "restated-repair-" + payload_hash(seed)[7:23]
        release = AllocationReleaseManifest.create(
            release_id=release_id,
            model_id=model_id,
            dataset_id=data.dataset_id,
            training_manifest_hash=training_hash,
            artifact_file="model.joblib",
            artifact_hash=artifact_hash,
            dataset_identity_hash=data.dataset_identity_hash,
            feature_registry_hash=data.feature_registry_hash,
            source_manifest_hashes=data.source_manifest_hashes,
            feature_order=data.feature_ids,
            preprocessor=preprocessor_binding,
            calibration=calibration_binding,
            missing_policy=missing_policy,
        )
        metrics_payload = {
            "schema_version": "restated-linear-shadow-heldout-metrics.v1",
            "evaluation_models_only": True,
            "final_fit_scores_are_not_oos": True,
            "horizons": {
                str(horizon): _jsonable(evaluation_evidence[horizon])
                for horizon in normalized_horizons
            },
            "calibration": {
                "fit_fold_counts": calibration_fold_counts,
                "fit_fold_ids": list(fold_ids),
                "downside_mature_observation_count": int(np.sum(calibration_counts)),
                "mapping_bp_hash": payload_hash(mapping.tolist()),
                "fit_observation_counts_by_horizon": {
                    str(horizon): count
                    for horizon, count in calibration_horizon_counts.items()
                },
                "mapping_population": (
                    "one downside forecast per available feature_pack by horizon by matured calibration row"
                ),
                "mapping_scope": (
                    "one shared isotonic mapping across all listed horizons and feature packs"
                ),
            },
        }
        training_payload = {
            **training_identity,
            "manifest_hash": training_hash,
            "artifact_hash": artifact_hash,
            "release_id": release_id,
            "release_identity_hash": release.release_identity_hash,
            "calibration": metrics_payload["calibration"],
            "target_summary": target_summary,
            "runtime_resources": runtime_resources,
        }
        run_root = output_root / "runs" / release_id
        run_root.parent.mkdir(parents=True, exist_ok=True)
        if run_root.exists():
            raise FileExistsError(f"immutable release already exists: {run_root}")
        release_stage = staging / "release"
        release_stage.mkdir()
        for (horizon, pack_id), source_path in receipt_sources.items():
            evidence = evaluation_evidence[horizon]["packs"][pack_id][
                "heldout_prediction_receipt"
            ]
            destination = release_stage / Path(str(evidence["file"]))
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination)
        _write_bytes(release_stage / "model.joblib", artifact_bytes)
        _write_bytes(release_stage / "preprocessor.json", preprocessor_bytes)
        _write_bytes(release_stage / "calibrator.json", calibrator_bytes)
        _write_json(release_stage / "training_manifest.json", training_payload)
        _write_json(release_stage / "evaluation_metrics.json", metrics_payload)
        _write_json(release_stage / "release_manifest.json", release.to_dict())
        from app_module.allocation_release_adapter import AllocationReleaseAdapter

        staged_loaded = AllocationReleaseAdapter().load(
            release_stage,
            expected_release_identity_hash=release.release_identity_hash,
        )
        staged_smoke = None
        if run_current_smoke:
            staged_smoke = _run_current_inference_smoke(
                data=data,
                loaded=staged_loaded,
                observed_as_of=observed_as_of or datetime.now(TAIPEI),
            )
            _write_json(release_stage / "latest_inference_smoke.json", staged_smoke)
        run_root.parent.mkdir(parents=True, exist_ok=True)
        os.replace(release_stage, run_root)
        final_loaded = AllocationReleaseAdapter().load(
            run_root,
            expected_release_identity_hash=release.release_identity_hash,
        )
        final_smoke = None
        if run_current_smoke:
            final_smoke = _run_current_inference_smoke(
                data=data,
                loaded=final_loaded,
                observed_as_of=observed_as_of or datetime.now(TAIPEI),
            )
        return {
            "status": "release_written",
            "release_root": str(run_root),
            "release_id": release_id,
            "model_id": model_id,
            "training_manifest_hash": training_hash,
            "artifact_hash": artifact_hash,
            "release_identity_hash": release.release_identity_hash,
            "manifest_file_hash": data.manifest_file_hash,
            "row_count": data.row_count,
            "horizons": list(normalized_horizons),
            "heldout_metrics_path": str(run_root / "evaluation_metrics.json"),
            "staged_loader_verified": staged_loaded.release_id == release_id,
            "final_loader_verified": final_loaded.release_id == release_id,
            "latest_inference_smoke": final_smoke or staged_smoke,
            "formal_oos_allowed": False,
            "production_alpha_bp": 0,
            "production_action_allowed": False,
            "broker_order_allowed": False,
            "active_pointer_modified": False,
        }
    finally:
        try:
            loaded_data = locals().get("data")
            if isinstance(loaded_data, ResearchArrays):
                _close_research_arrays(loaded_data)
            _safe_remove_scratch(staging, output_root)
        finally:
            thread_limit_context.__exit__(None, None, None)


def _close_research_arrays(data: ResearchArrays) -> None:
    """Close dataset mmaps before scratch cleanup (required by Windows)."""

    for value in (
        data.features,
        data.feature_values_i64,
        data.row_ids,
        data.symbols,
        data.decision_days,
        data.event_days,
        data.event_at,
        data.revision_at,
        data.revision_ids,
        data.heldout_flags,
        *data.labels.values(),
        *data.label_masks.values(),
        *data.label_maturities.values(),
    ):
        _close_memmap(value)


def _load_head_models(directory: Path, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    expected_ids = set(EXPERT_HEAD_IDS)
    if {str(record.get("head_id")) for record in records} != expected_ids:
        raise ValueError("linear fit did not return the complete nine-head contract")
    for record in records:
        head_id = str(record["head_id"])
        if record.get("status") == "missing":
            result[head_id] = None
            continue
        path = (directory / str(record["path"])).resolve()
        if path.parent != directory.resolve() or not path.is_file():
            raise ValueError(f"fit head path is invalid: {head_id}")
        model = joblib.load(path)
        if not isinstance(model, _LinearBoundaryModel) or not callable(
            getattr(model, "predict_numeric", None)
        ):
            raise ValueError(f"fit head is not a validated linear boundary model: {head_id}")
        result[head_id] = model
    return result


def _score_oof(
    store: _ResearchLabelStore,
    data: ResearchArrays,
    horizon: int,
    refs: NDArray[np.integer[Any]],
    predictions: NDArray[np.int32],
) -> dict[str, Any]:
    labels, masks = store.read_label_batch(np.asarray(refs, dtype=np.int64), horizon)
    result: dict[str, Any] = {}
    for head_id, label_position in zip(REGRESSION_EXPERT_HEADS, REGRESSION_LABEL_POSITIONS):
        valid = masks[:, label_position] == 0
        if not np.any(valid):
            result[head_id] = {"status": "no_mature_labels", "observation_count": 0}
            continue
        column = EXPERT_HEAD_IDS.index(head_id)
        residuals = np.asarray(predictions[valid, column], dtype=np.int64) - np.asarray(
            labels[valid, label_position], dtype=np.int64
        )
        result[head_id] = {
            "status": "evaluated",
            "observation_count": int(np.sum(valid)),
            "mae_bp": _mean_abs_int(residuals),
            "rmse_bp": _rmse_int(residuals),
        }
    for head_id, label_position in zip(
        CLASSIFICATION_EXPERT_HEADS, CLASSIFICATION_LABEL_POSITIONS
    ):
        valid = (masks[:, label_position] == 0) & np.isin(
            labels[:, label_position], (0, 1)
        )
        if not np.any(valid):
            result[head_id] = {"status": "no_mature_labels", "observation_count": 0}
            continue
        column = EXPERT_HEAD_IDS.index(head_id)
        probability_bp = np.asarray(predictions[valid, column], dtype=np.int64)
        target_bp = np.asarray(labels[valid, label_position], dtype=np.int64) * 10_000
        errors = probability_bp - target_bp
        result[head_id] = {
            "status": "evaluated",
            "observation_count": int(np.sum(valid)),
            "brier_score_bp2": _mean_square_int(errors),
            "threshold_accuracy_bp": _ratio_bp(
                int(np.sum((probability_bp >= 5_000) == (target_bp >= 5_000))),
                int(np.sum(valid)),
            ),
            "observed_positive_rate_bp": _ratio_bp(
                int(np.sum(target_bp == 10_000)), int(np.sum(valid))
            ),
        }
    return result


def _bounded_fit_refs(
    refs: NDArray[np.integer[Any]],
    maximum: int | None,
) -> NDArray[np.int64]:
    values = np.asarray(refs, dtype=np.int64)
    if maximum is None or len(values) <= maximum:
        return values
    positions = _deterministic_bounded_indexes(
        row_count=len(values), maximum=maximum
    )
    return values[positions]


def _fit_naive_baseline(
    *,
    store: _ResearchLabelStore,
    horizon: int,
    train_refs: NDArray[np.int64],
    prediction_count: int,
    batch_size: int,
) -> tuple[NDArray[np.int32], dict[str, Any]]:
    """僅以同一訓練列計算 mean/rate，建立無特徵的對照基準。"""

    sums = np.zeros(len(LABEL_FIELDS), dtype=np.int64)
    counts = np.zeros(len(LABEL_FIELDS), dtype=np.int64)
    positives = np.zeros(len(LABEL_FIELDS), dtype=np.int64)
    for start in range(0, len(train_refs), batch_size):
        refs = train_refs[start : start + batch_size]
        labels, masks = store.read_label_batch(refs, horizon)
        for position in range(len(LABEL_FIELDS)):
            valid = masks[:, position] == 0
            if not np.any(valid):
                continue
            values = labels[valid, position].astype(np.int64, copy=False)
            sums[position] += int(np.sum(values, dtype=np.int64))
            counts[position] += int(len(values))
            positives[position] += int(np.sum(values == 1))

    head_constants: dict[str, dict[str, int | str]] = {}
    vector = np.zeros(len(EXPERT_HEAD_IDS), dtype=np.int32)
    signed_regressions = {
        "expected_excess_return_bp",
        "expected_sector_excess_return_bp",
    }
    for head_id in EXPERT_HEAD_IDS:
        position = _label_position(head_id)
        count = int(counts[position])
        if count == 0:
            constant = 0
            method = "no_train_labels_zero_fallback"
        elif head_id in CLASSIFICATION_EXPERT_HEADS:
            constant = int(
                (
                    Decimal(int(positives[position]) * 10_000)
                    / Decimal(count)
                ).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
            )
            constant = min(max(constant, 0), 10_000)
            method = "train_positive_rate_bp"
        else:
            constant = int(
                (Decimal(int(sums[position])) / Decimal(count)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_EVEN
                )
            )
            low = -10_000 if head_id in signed_regressions else 0
            constant = min(max(constant, low), 10_000)
            method = "train_target_mean_bp"
        vector[EXPERT_HEAD_IDS.index(head_id)] = constant
        head_constants[head_id] = {
            "method": method,
            "fit_row_count": count,
            "constant_prediction_bp": constant,
        }
    predictions = np.broadcast_to(vector, (prediction_count, len(vector))).copy()
    return predictions, {
        "algorithm": "train_only_intercept_mean_and_positive_rate",
        "fit_row_count": int(len(train_refs)),
        "head_constants": head_constants,
    }


def _materialize_feature_matrix(
    *,
    data: ResearchArrays,
    refs: NDArray[np.integer[Any]],
    columns: NDArray[np.integer[Any]],
    path: Path,
    batch_size: int,
) -> np.memmap:
    """分批投影 feature pack 至 float32 mmap，以限制常駐記憶體。"""

    rows = np.asarray(refs, dtype=np.int64)
    selected_columns = np.asarray(columns, dtype=np.int64)
    if len(rows) < 1 or len(selected_columns) < 1:
        raise ValueError("feature matrix projection must be non-empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    matrix = np.memmap(
        path,
        dtype=FLOAT_DTYPE,
        mode="w+",
        shape=(len(rows), len(selected_columns)),
    )
    for start in range(0, len(rows), batch_size):
        stop = min(start + batch_size, len(rows))
        raw = np.asarray(data.features[rows[start:stop]], dtype=FLOAT_DTYPE)
        matrix[start:stop, :] = raw[:, selected_columns]
    matrix.flush()
    return matrix


def _predict_probability_bp(
    *,
    model: Any,
    data: ResearchArrays,
    refs: NDArray[np.integer[Any]],
    columns: NDArray[np.integer[Any]],
    batch_size: int,
) -> NDArray[np.int64]:
    rows = np.asarray(refs, dtype=np.int64)
    result = np.empty(len(rows), dtype=np.int64)
    selected_columns = np.asarray(columns, dtype=np.int64)
    for start in range(0, len(rows), batch_size):
        stop = min(start + batch_size, len(rows))
        raw = np.asarray(
            data.features[rows[start:stop]], dtype=FLOAT_DTYPE
        )[:, selected_columns]
        probability = np.asarray(model.predict_numeric(raw), dtype=np.float64)
        result[start:stop] = np.asarray(
            np.clip(np.rint(probability * 10_000.0), 0, 10_000),
            dtype=np.int64,
        )
    return result


def _write_heldout_prediction_receipt(
    *,
    path: Path,
    data: ResearchArrays,
    store: _ResearchLabelStore,
    horizon: int,
    pack_id: str,
    refs: NDArray[np.integer[Any]],
    predictions: NDArray[np.int32],
    naive_predictions: NDArray[np.int32],
    batch_size: int,
) -> int:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - runtime preflight
        raise RuntimeError("pyarrow is required for heldout prediction receipts") from exc

    rows = np.asarray(refs, dtype=np.int64)
    if predictions.shape != (len(rows), len(EXPERT_HEAD_IDS)):
        raise ValueError("heldout model prediction receipt shape mismatch")
    if naive_predictions.shape != predictions.shape:
        raise ValueError("heldout baseline prediction receipt shape mismatch")
    schema = pa.schema(
        [
            ("horizon", pa.int16()),
            ("feature_pack", pa.string()),
            ("row_id", pa.string()),
            ("symbol", pa.string()),
            ("decision_date", pa.date32()),
            ("labels_bp", pa.list_(pa.int32(), len(LABEL_FIELDS))),
            ("label_missing_mask", pa.list_(pa.uint8(), len(LABEL_FIELDS))),
            ("model_prediction_bp", pa.list_(pa.int32(), len(EXPERT_HEAD_IDS))),
            ("train_only_naive_prediction_bp", pa.list_(pa.int32(), len(EXPERT_HEAD_IDS))),
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with pq.ParquetWriter(path, schema=schema, compression="zstd") as writer:
        for start in range(0, len(rows), batch_size):
            stop = min(start + batch_size, len(rows))
            batch_refs = rows[start:stop]
            labels, masks = store.read_label_batch(batch_refs, horizon)
            records: list[dict[str, Any]] = []
            for index, ref in enumerate(batch_refs):
                integer_ref = int(ref)
                symbol = bytes(data.symbols[integer_ref]).decode("utf-8").rstrip("\x00")
                records.append(
                    {
                        "horizon": horizon,
                        "feature_pack": pack_id,
                        "row_id": _row_id_from_bytes(data.row_ids[integer_ref]),
                        "symbol": symbol,
                        "decision_date": date.fromordinal(
                            int(data.decision_days[integer_ref])
                        ),
                        "labels_bp": [int(value) for value in labels[index]],
                        "label_missing_mask": [int(value) for value in masks[index]],
                        "model_prediction_bp": [
                            int(value) for value in predictions[start + index]
                        ],
                        "train_only_naive_prediction_bp": [
                            int(value) for value in naive_predictions[start + index]
                        ],
                    }
                )
            writer.write_table(pa.Table.from_pylist(records, schema=schema))
            written += len(records)
    return written


def _record_runtime_memory(evidence: dict[str, Any], stage: str) -> None:
    rss = _current_rss_bytes()
    try:
        import psutil

        process_info = psutil.Process().memory_info()
        available = int(psutil.virtual_memory().available)
        peak_rss = getattr(process_info, "peak_wset", None)
        if peak_rss is None:
            peak_rss = rss
    except (ImportError, OSError):
        available = None
        peak_rss = rss
    samples = evidence.setdefault("snapshots", [])
    samples.append(
        {
            "stage": stage,
            "process_rss_bytes": rss,
            "process_peak_rss_bytes": peak_rss,
            "system_available_memory_bytes": available,
        }
    )
    rss_values = [
        int(item["process_rss_bytes"])
        for item in samples
        if item.get("process_rss_bytes") is not None
    ]
    available_values = [
        int(item["system_available_memory_bytes"])
        for item in samples
        if item.get("system_available_memory_bytes") is not None
    ]
    evidence["peak_process_rss_bytes"] = max(rss_values) if rss_values else None
    peak_values = [
        int(item["process_peak_rss_bytes"])
        for item in samples
        if item.get("process_peak_rss_bytes") is not None
    ]
    evidence["process_peak_working_set_bytes"] = (
        max(peak_values) if peak_values else None
    )
    evidence["minimum_system_available_memory_bytes"] = (
        min(available_values) if available_values else None
    )


def _accumulate_calibration(
    *,
    data: ResearchArrays,
    horizon: int,
    refs: NDArray[np.integer[Any]],
    models: Mapping[str, Any],
    feature_columns: NDArray[np.int64],
    counts: NDArray[np.int64],
    positives: NDArray[np.int64],
    batch_size: int,
) -> None:
    if len(refs) == 0:
        return
    model = models.get("downside_probability_bp")
    if model is None:
        return
    rows = np.asarray(refs, dtype=np.int64)
    selected_columns = np.asarray(feature_columns, dtype=np.int64)
    for start in range(0, len(rows), batch_size):
        stop = min(start + batch_size, len(rows))
        batch_refs = rows[start:stop]
        labels = np.asarray(data.labels[horizon][batch_refs, 2], dtype=np.int64)
        masks = np.asarray(data.label_masks[horizon][batch_refs, 2], dtype=np.uint8)
        valid = (masks == 0) & np.isin(labels, (0, 1))
        if not np.any(valid):
            continue
        raw_matrix = np.asarray(
            data.features[batch_refs], dtype=FLOAT_DTYPE
        )[:, selected_columns]
        raw_probability = np.asarray(model.predict_numeric(raw_matrix), dtype=np.float64)
        probability_bp = np.asarray(
            np.clip(np.rint(raw_probability * 10_000.0), 0, 10_000),
            dtype=np.int64,
        )
        np.add.at(counts, probability_bp[valid], 1)
        np.add.at(positives, probability_bp[valid], labels[valid])


def _mature_training_refs(data: ResearchArrays, horizon: int) -> NDArray[np.int64]:
    asof_date = _aware_datetime(data.training_as_of, field_name="training_as_of").astimezone(TAIPEI).date().toordinal()
    labels_mask = np.asarray(data.label_masks[horizon], dtype=np.uint8)
    observed = np.any(labels_mask == 0, axis=1)
    maturity = np.asarray(data.label_maturities[horizon], dtype=np.int32)
    decisions = np.asarray(data.decision_days, dtype=np.int32)
    return np.flatnonzero(
        observed & (maturity >= 0) & (maturity <= asof_date) & (decisions < asof_date)
    ).astype(np.int64)


def _collect_training_runtime_binding(
    *,
    invocation_argv: Sequence[str] | None,
    dataset_schema_version: str | None = None,
) -> dict[str, Any]:
    """封存模型 trainer、序列化路徑與執行環境的可重播來源指紋。"""

    repository_root = Path(__file__).resolve().parents[1]
    source_hashes: dict[str, str] = {}
    source_files = list(_TRAINING_SOURCE_FILES)
    if dataset_schema_version == "portfolio-ml-restated-research-dataset.v2":
        source_files.extend(_V2_TRAINING_SOURCE_FILES)
    for relative_path in source_files:
        source_path = repository_root / relative_path
        if not source_path.is_file():
            raise FileNotFoundError(f"training dependency source is missing: {relative_path}")
        source_hashes[relative_path] = "sha256:" + hashlib.sha256(
            source_path.read_bytes()
        ).hexdigest()
    versions = {
        distribution: importlib.metadata.version(distribution)
        for distribution in _TRAINING_DISTRIBUTIONS
    }
    return {
        "dataset_schema_version": dataset_schema_version,
        "source_file_sha256": source_hashes,
        "software_versions": versions,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "full_version": sys.version,
        },
        "invocation_argv": list(
            sys.argv[1:] if invocation_argv is None else invocation_argv
        ),
    }


def _read_declared_dataset_schema_version(manifest_path: Path) -> str | None:
    """讀取 manifest 宣告版本，讓 source binding 收錄對應的 identity builder。"""

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read dataset schema version before training") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("dataset manifest must be a JSON object")
    value = payload.get("schema_version")
    return value if isinstance(value, str) else None


def _build_training_identity(
    *,
    data: ResearchArrays,
    horizons: Sequence[int],
    evaluation: Mapping[int, Mapping[str, Any]],
    final_fit: Mapping[int, Mapping[str, Any]],
    calibration_counts: Mapping[str, int],
    calibration_horizon_counts: Mapping[int, int],
    calibration_event_missing_counts: Mapping[int, Mapping[str, int]],
    runtime_binding: Mapping[str, Any],
    max_fit_rows: int | None,
    batch_size: int,
    logistic_iterations: int,
) -> dict[str, Any]:
    return {
        "schema_version": "sealed-restated-allocation-training.v1",
        "model_family": "revision_aware_restated_linear_heads_with_neutral_cash_meta",
        "training_profile": TRAINING_PROFILE,
        "training_runtime_binding": dict(runtime_binding),
        "dataset_id": data.dataset_id,
        "dataset_identity_hash": data.dataset_identity_hash,
        "dataset_manifest_file_hash": data.manifest_file_hash,
        "dataset_source_custody": _source_custody_identity(data),
        "source_manifest_hashes": [list(item) for item in data.source_manifest_hashes],
        "feature_registry_hash": data.feature_registry_hash,
        "feature_order": list(data.feature_ids),
        "feature_order_hash": feature_order_hash(data.feature_ids),
        "feature_packs": [[pack_id, list(ids)] for pack_id, ids in data.feature_packs],
        "label_fields": list(LABEL_FIELDS),
        "horizons": list(horizons),
        "training_as_of": data.training_as_of,
        "feature_event_clock_policy": {
            "source_field": "feature_event_asof_at",
            "semantics": "stock_event_date at 14:30 Asia/Taipei; null remains null",
            "null_sentinel_internal_only": {"event_days": -1, "event_at": "empty string"},
            "training_selection": "retained with original feature missing masks; split uses decision and label maturity clocks",
            "current_inference": "rows without a stock event are rejected",
            "dataset_missing_stock_event_rows": int(
                np.sum(np.asarray(data.event_days, dtype=np.int32) < 0)
            ),
            "dataset_missing_stock_event_row_ids_hash": _row_id_hash(
                data,
                np.flatnonzero(np.asarray(data.event_days, dtype=np.int32) < 0),
            ),
        },
        "restated_research": True,
        "historical_pit": False,
        "formal_oos_allowed": False,
        "heldout_start_date": REPAIR_HELDOUT_START.isoformat(),
        "evaluation_split_by_horizon": {
            str(horizon): _jsonable(evaluation[horizon]) for horizon in horizons
        },
        "final_fit_by_horizon": {
            str(horizon): dict(final_fit[horizon]) for horizon in horizons
        },
        "fit_row_lineage": {
            "schema_version": "allocation-fit-row-commitments.v1",
            "row_id_hash_algorithm": "sha256(canonical_json_array_utf8)",
            "selection": "final mature refs from sealed research rows; each head subset uses label_missing_mask=0",
            "source": "row_id values from manifest-hash-verified Parquet partitions",
        },
        "calibration_fit_fold_counts": dict(calibration_counts),
        "calibration_fit_observation_counts_by_horizon": {
            str(horizon): count
            for horizon, count in calibration_horizon_counts.items()
        },
        "calibration_missing_stock_event_row_counts_by_horizon_and_fold": {
            str(horizon): dict(counts)
            for horizon, counts in calibration_event_missing_counts.items()
        },
        "calibration_population": (
            "shared downside mapping fit from matured predictions across all listed feature packs and horizons"
        ),
        "hyperparameters": {
            "algorithm": "ridge_logistic",
            "ridge_alpha_bp": 100,
            "ridge_alpha_decimal": "0.01",
            "logistic_irls_iterations": logistic_iterations,
            "max_selected_fit_rows": max_fit_rows,
            "fit_row_policy": (
                "all eligible mature rows"
                if max_fit_rows is None
                else "deterministic evenly spaced capped sample"
            ),
            "batch_size": batch_size,
            "preprocessor_strategy": PREPROCESSOR_STRATEGY,
            "median_sample_cap": 100_000,
            "median_sample_rule": "deterministic evenly spaced training rows; sample is restricted to the fit fold",
            "means_and_scales_rule": "stream over all selected fit-fold rows only",
        },
        "purge_and_embargo": {
            "purge_sessions": 60,
            "calibration_interfold_embargo_sessions": 5,
            "heldout_embargo_sessions": 5,
            "label_maturity_required": True,
        },
        "sampled_rows_are_deterministic": max_fit_rows is not None,
    }


def _build_artifact_payload(
    *,
    data: ResearchArrays,
    horizons: Sequence[int],
    final_models: Mapping[str, Mapping[str, Mapping[str, Any]]],
    training_hash: str,
    target_summary: Mapping[str, Any],
) -> dict[str, Any]:
    packs = data.feature_packs
    expert_keys: list[str] = []
    base_models: dict[str, Any] = {}
    fit_lineage_by_horizon: dict[int, dict[str, Any]] = {}
    for pack_id, _feature_ids in packs:
        for horizon in horizons:
            expert_key = f"{pack_id}|h{horizon}|ridge_logistic"
            expert_keys.append(expert_key)
            entry = final_models[str(horizon)][pack_id]
            records = {str(item["head_id"]): item for item in entry["records"]}
            models = entry["models"]
            selected_refs = np.asarray(entry["fit_refs"], dtype=np.int64)
            horizon_value = int(expert_key.split("|h", 1)[1].split("|", 1)[0])
            if horizon_value not in fit_lineage_by_horizon:
                fit_lineage_by_horizon[horizon_value] = _build_fit_row_lineage(
                    data=data,
                    horizon=horizon_value,
                    selected_refs=selected_refs,
                    records=records,
                )
            fit_lineage = fit_lineage_by_horizon[horizon_value]
            fit_by_head: dict[str, list[str]] = {
                head_id: [] for head_id in EXPERT_HEAD_IDS
            }
            missing_reasons = {
                head_id: str(record.get("missing_reason", "unavailable"))
                for head_id, record in records.items()
                if record.get("status") == "missing"
            }
            base_models[expert_key] = {
                "regression_models": {
                    head_id: models[head_id] for head_id in REGRESSION_EXPERT_HEADS
                },
                "classification_models": {
                    head_id: models[head_id] for head_id in CLASSIFICATION_EXPERT_HEADS
                },
                "preprocessing_strategy": PREPROCESSOR_STRATEGY,
                "head_fit_row_ids": fit_by_head,
                "head_missing_reasons": missing_reasons,
                "fit_row_ids": [],
                "fit_row_lineage": fit_lineage,
            }
    meta = {
        "numeric": {
            field: _ConstantRegressionModel(10_000 if field == "cash_bp" else 0)
            for field in _META_FIELDS
        },
        "rebalance": _ConstantProbabilityModel(0),
        "fit_row_ids": [],
    }
    family_weights = _equal_family_weights([pack_id for pack_id, _ids in packs])
    return {
        "artifact_schema_version": "allocation-model-artifact-v3",
        "dataset_id": data.dataset_id,
        "dataset_identity_hash": data.dataset_identity_hash,
        "dataset_manifest_file_hash": data.manifest_file_hash,
        "feature_registry_hash": data.feature_registry_hash,
        "source_manifest_hashes": [list(item) for item in data.source_manifest_hashes],
        "training_as_of": data.training_as_of,
        "feature_packs": [[pack_id, list(ids)] for pack_id, ids in packs],
        "horizons": list(horizons),
        "expert_keys": expert_keys,
        "expert_head_ids": list(EXPERT_HEAD_IDS),
        "expert_vector_width": len(EXPERT_HEAD_IDS) * 2 + 1,
        "rank_contract": RANK_CONTRACT_V2,
        "family_weight_policy": FAMILY_WEIGHT_POLICY_DEGENERATE_EQUAL_V1,
        "feature_family_weights_status": FAMILY_WEIGHT_STATUS_DEGENERATE_UNIDENTIFIED_EQUAL,
        "feature_family_weights_bp": [list(item) for item in family_weights],
        "meta_probability_input": "calibrated",
        "training_profile": TRAINING_PROFILE,
        "complexity_policy": {
            "algorithm_count": 1,
            "horizon_count": len(horizons),
            "formal_oos_allowed": False,
            "production_alpha_bp": 0,
        },
        "base_models": base_models,
        "meta_models": meta,
        "target_summary": dict(target_summary),
        "production_alpha_bp": 0,
        "production_action_allowed": False,
        "formal_oos_allowed": False,
        "broker_order_allowed": False,
    }


def _verified_cash_only_target_summary(training_hash: str) -> dict[str, Any]:
    return {
        "schema_version": "allocation-restated-target-audit.v1",
        "status": "verified_original_targets_constant_cash_only; neutral_meta_policy",
        "training_skipped": True,
        "model_learned_allocation": False,
        "original_direct_rows_verified": 3_353_096,
        "original_direct_target_manifest_hash": TARGET_AUDIT_MANIFEST_HASH,
        "target_values": {
            "target_weight_bp": 0,
            "delta_weight_bp": 0,
            "risk_contribution_bp": 0,
            "risky_budget_bp": 0,
            "cash_bp": 10_000,
            "rebalance": 0,
        },
        "new_restated_rows_target_policy": "all target fields missing; no teacher targets are fabricated or carried forward",
        "neutral_meta_policy": "fixed cash-only schema adapter; allocation heads remain research signals only",
        "target_audit_evidence": {
            "committed_revision": "eba0223b",
            "audit_path": "output/qa/model_repair_review/original_target_values_audit.json",
        },
        "training_manifest_hash": training_hash,
    }


def _run_current_inference_smoke(
    *,
    data: ResearchArrays,
    loaded: Any,
    observed_as_of: datetime,
) -> dict[str, Any]:
    from app_module.allocation_release_adapter import LoadedAllocationRelease
    from ml_module.allocation_contracts import (
        CausalPortfolioState,
        AllocationWeightContract,
        PITFeatureValue,
        PortfolioMLDatasetRow,
        post_freeze_shadow_decision_scope,
    )

    if not isinstance(loaded, LoadedAllocationRelease):
        raise TypeError("current smoke requires the verified AllocationReleaseAdapter output")
    if observed_as_of.tzinfo is None or observed_as_of.utcoffset() is None:
        raise ValueError("current inference smoke clock must be timezone-aware")
    now = observed_as_of.astimezone(TAIPEI)
    if now.timetz().replace(tzinfo=None).hour == 8 and now.minute == 30:
        raise ValueError("current smoke must use actual current time, not historical 08:30")
    max_decision_day = int(np.max(np.asarray(data.decision_days, dtype=np.int32)))
    latest_refs = np.flatnonzero(np.asarray(data.decision_days) == max_decision_day)
    if len(latest_refs) == 0:
        raise ValueError("sealed snapshot has no latest current rows")
    event_days = np.asarray(data.event_days, dtype=np.int32)
    no_stock_event_count = int(np.sum(event_days[latest_refs] < 0))
    current_refs = latest_refs[event_days[latest_refs] >= 0]
    if len(current_refs) == 0:
        raise ValueError("latest research rows have no observed prior stock event")
    current_refs = current_refs[: min(25, len(current_refs))]
    source_id = "sealed_restated_research_dataset"
    source_hashes = dict(data.source_manifest_hashes)
    source_hashes[source_id] = data.manifest_file_hash
    source_pairs = tuple(sorted(source_hashes.items()))
    family_by_feature = {
        feature_id: pack_id
        for pack_id, ids in data.feature_packs
        for feature_id in ids
    }
    current_decision_at = now.isoformat(timespec="seconds")
    rows: list[PortfolioMLDatasetRow] = []
    state_date = date.fromordinal(int(data.event_days[int(current_refs[0])])).isoformat()
    state = CausalPortfolioState.create(
        as_of_date=state_date,
        weights=AllocationWeightContract(positions_bp=(), cash_bp=10_000),
        weekly_turnover_used_bp=0,
    )
    with post_freeze_shadow_decision_scope():
        for ref in current_refs:
            row_key = _row_id_from_bytes(data.row_ids[int(ref)])
            symbol = bytes(data.symbols[int(ref)]).decode("utf-8").rstrip("\x00")
            event_timestamp = bytes(data.event_at[int(ref)]).decode("utf-8").rstrip("\x00")
            available_timestamp = bytes(data.revision_at[int(ref)]).decode("utf-8").rstrip("\x00")
            revision_id = bytes(data.revision_ids[int(ref)]).decode("utf-8").rstrip("\x00")
            if _aware_datetime(event_timestamp, field_name="latest feature event") >= now:
                raise ValueError("latest current feature event is not prior to smoke capture")
            if _aware_datetime(available_timestamp, field_name="latest snapshot observed_at") > now:
                raise ValueError("latest snapshot was not available by actual smoke capture")
            missing_families: set[str] = set()
            feature_values: list[PITFeatureValue] = []
            for column, feature_id in enumerate(data.feature_ids):
                scale = int(data.feature_scales[column])
                raw_value = None
                if np.isfinite(data.features[int(ref), column]):
                    raw_value = int(data.feature_values_i64[int(ref), column])
                family = family_by_feature[feature_id]
                if raw_value is None:
                    missing_families.add(family)
                feature_hash = payload_hash(
                    {
                        "row_id": row_key,
                        "feature_id": feature_id,
                        "value_int": raw_value,
                        "scale": scale,
                        "revision_id": revision_id,
                    }
                )
                feature_values.append(
                    PITFeatureValue(
                        feature_id=feature_id,
                        family_id=family,
                        source_id=source_id,
                        value_int=raw_value,
                        scale=scale,
                        event_at=event_timestamp,
                        available_at=available_timestamp,
                        revision_id=revision_id,
                        quality="observed" if raw_value is not None else "missing",
                        content_hash=feature_hash,
                        observed=raw_value is not None,
                    )
                )
            shadow_row_id = f"row:post-freeze-shadow:{now.date().isoformat()}:{symbol}"
            rows.append(
                PortfolioMLDatasetRow(
                    row_id=shadow_row_id,
                    decision_at=current_decision_at,
                    symbol=symbol,
                    features=tuple(feature_values),
                    missing_family_ids=tuple(sorted(missing_families)),
                    portfolio_state=state,
                    dataset_identity_hash=data.dataset_identity_hash,
                    feature_registry_hash=data.feature_registry_hash,
                    source_manifest_hashes=source_pairs,
                    targets=None,
                )
            )
    result = loaded.infer_research_shadow(
        rows=rows,
        universe_id=f"restated-research-current-{now.date().isoformat()}",
        policy_id=loaded.manifest.missing_policy.policy_id,
        policy_hash=loaded.manifest.missing_policy.policy_hash,
    )
    audit = result.audit_payload()
    row_audits = audit.get("row_audits", [])
    prediction_summary = [
        {
            "row_id": row.get("row_id"),
            "symbol": row.get("symbol"),
            "base_expert_by_horizon": row.get("base_expert_by_horizon"),
            "downside_probability_by_horizon_bp": row.get(
                "downside_probability_by_horizon_bp"
            ),
        }
        for row in row_audits
    ]
    return {
        "schema_version": "restated-current-inference-smoke.v1",
        "status": "passed",
        "observed_at": now.isoformat(),
        "decision_at": current_decision_at,
        "source_manifest_file_hash": data.manifest_file_hash,
        "latest_rows_without_stock_event_rejected": no_stock_event_count,
        "source_revision_ids": sorted(
            {
                bytes(data.revision_ids[int(ref)]).decode("utf-8").rstrip("\x00")
                for ref in current_refs
            }
        ),
        "row_count": len(rows),
        "inference_output_hash": payload_hash(prediction_summary),
        "predictions": prediction_summary,
        "inference_readback_mode": audit.get("inference_readback_mode"),
        "formal_oos_allowed": result.formal_oos_allowed,
        "production_action_allowed": result.production_action_allowed,
        "production_blend_alpha_bp": result.production_blend_alpha_bp,
        "broker_order_allowed": False,
    }


def _read_feature_packs(
    manifest: Mapping[str, Any],
    feature_ids: Sequence[str],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    raw = manifest.get("feature_packs")
    if not isinstance(raw, list) or not raw:
        raise ValueError("sealed manifest must supply feature_packs")
    packs: list[tuple[str, tuple[str, ...]]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError("feature_packs entries must be objects")
        pack_id = _required_row_text(item.get("pack_id"), "feature_packs.pack_id")
        ids_raw = item.get("feature_ids")
        if not isinstance(ids_raw, list) or not ids_raw:
            raise TypeError(f"feature_packs[{pack_id}].feature_ids must be a non-empty array")
        ids = tuple(_required_row_text(value, f"feature_packs[{pack_id}].feature_id") for value in ids_raw)
        if len(ids) != len(set(ids)):
            raise ValueError(f"feature pack contains duplicate ids: {pack_id}")
        packs.append((pack_id, ids))
    if len({pack_id for pack_id, _ids in packs}) != len(packs):
        raise ValueError("feature pack ids must be unique")
    flattened = tuple(feature_id for _pack_id, ids in packs for feature_id in ids)
    if flattened != tuple(feature_ids):
        raise ValueError("feature packs must cover all 62 features in frozen feature order")
    return tuple(packs)


def _validate_complete_restatement_manifest(
    manifest: Mapping[str, Any],
) -> tuple[tuple[str, ...], tuple[int, ...], tuple[tuple[str, tuple[str, ...]], ...], tuple[int, ...]]:
    """驗證封存 restated dataset identity、完整欄位 ABI 與標籤契約。"""

    schema_version = manifest.get("schema_version")
    is_v1 = schema_version == "portfolio-ml-restated-research-dataset.v1"
    is_v2 = schema_version == "portfolio-ml-restated-research-dataset.v2"
    if (
        not (is_v1 or is_v2)
        or manifest.get("status") != "complete_research_build"
        or manifest.get("research_only") is not True
        or manifest.get("restated_research") is not True
        or manifest.get("formal_historical_PIT") is not False
        or manifest.get("formal_oos") is not False
        or manifest.get("promotion_eligible") is not False
    ):
        raise ValueError("completed restated research v1/v2 manifest with non-PIT flags is required")

    try:
        from data_module.ml_restatement_current_inputs import _IDENTITY_FIELDS, _payload_hash
        from data_module.ml_restatement_research_dataset import expected_feature_contract
    except ImportError as exc:  # pragma: no cover - repository module preflight
        raise RuntimeError("restated dataset contract modules are required") from exc

    if is_v1:
        try:
            identity_payload = {name: manifest[name] for name in _IDENTITY_FIELDS}
        except KeyError as exc:
            raise ValueError(f"restated manifest identity field is missing: {exc.args[0]}") from exc
    else:
        try:
            from data_module.ml_restatement_research_dataset_v2_merge import (
                V2_IDENTITY_FIELDS,
            )
        except ImportError as exc:  # pragma: no cover - v2 builder lands with the dataset repair
            raise RuntimeError("restated v2 identity contract module is required") from exc
        try:
            declared_fields = manifest["dataset_identity_fields"]
            if not isinstance(declared_fields, list) or tuple(declared_fields) != tuple(
                V2_IDENTITY_FIELDS
            ):
                raise ValueError("v2 dataset_identity_fields differs from its trusted identity contract")
            identity_payload = {
                "identity_fields": declared_fields,
                **{name: manifest[name] for name in declared_fields},
            }
        except KeyError as exc:
            raise ValueError(f"restated v2 identity field is missing: {exc.args[0]}") from exc
    identity_hash = _payload_hash(identity_payload)
    if (
        manifest.get("dataset_identity_hash") != identity_hash
        or manifest.get("manifest_hash") != identity_hash
    ):
        raise ValueError("restated manifest dataset identity/hash mismatch")
    expected_dataset_id = (
        "ml-restated-research-v2-" + identity_hash[7:31]
        if is_v2
        else "ml-restated-research-" + identity_hash[7:31]
    )
    if manifest.get("dataset_id") != expected_dataset_id:
        raise ValueError("restated manifest dataset id does not match its identity")

    expected_ids, expected_scales = expected_feature_contract()
    feature_ids = _read_sequence(manifest, "feature_ids")
    feature_scales = _read_integer_sequence(manifest, "feature_scales")
    if feature_ids != expected_ids or feature_scales != expected_scales:
        raise ValueError("restated feature order/scales differ from the fixed 62-slot ABI")
    if manifest.get("feature_count") != FEATURE_COUNT:
        raise ValueError("restated feature_count must equal 62")
    expected_order_hash = _payload_hash(list(zip(expected_ids, expected_scales)))
    if manifest.get("feature_order_hash") != expected_order_hash:
        raise ValueError("restated feature_order_hash differs from the fixed 62-slot ABI")
    _normalize_sha(manifest.get("feature_registry_hash"), "manifest.feature_registry_hash")

    label_fields = _read_sequence(manifest, "label_fields")
    label_scales = _read_integer_sequence(manifest, "label_scales")
    if label_fields != LABEL_FIELDS or label_scales != (1,) * len(LABEL_FIELDS):
        raise ValueError("restated label order/scales differ from the nine-label integer-bp ABI")
    if is_v2:
        target_fields = _read_sequence(manifest, "target_fields")
        if target_fields != _META_FIELDS + ("rebalance_worthwhile",):
            raise ValueError("restated v2 target order differs from the original six-column target ABI")
    feature_packs = _read_feature_packs(manifest, feature_ids)
    if isinstance(manifest.get("row_count"), bool) or not isinstance(manifest.get("row_count"), int):
        raise TypeError("restated manifest row_count must be an integer")
    if manifest["row_count"] < 2:
        raise ValueError("restated manifest row_count must be at least two")
    if not isinstance(manifest.get("fold_boundaries"), list) or not manifest["fold_boundaries"]:
        raise ValueError("restated manifest requires its frozen fold boundaries")
    fold_policy = manifest.get("fold_policy")
    if (
        not isinstance(fold_policy, dict)
        or fold_policy.get("purge_trading_days") != 60
        or fold_policy.get("embargo_trading_days") != 5
        or fold_policy.get("revision_heldout_start") != REPAIR_HELDOUT_START.isoformat()
        or fold_policy.get("formal_oos") is not False
    ):
        raise ValueError("restated manifest fold policy differs from the fixed repair split")

    training_as_of = _aware_datetime(manifest.get("training_as_of"), field_name="training_as_of")
    revision_observed_at = _aware_datetime(
        manifest.get("revision_observed_at"), field_name="revision_observed_at"
    )
    if is_v1 and training_as_of != revision_observed_at:
        raise ValueError("v1 training_as_of must equal the sealed revision observation clock")
    if is_v2:
        _validate_v2_dataset_lineage(manifest)
        _validate_v2_patch_summary(manifest)
    # 上方版本 gate 僅會接受兩個固定字串，cast 不改執行期值。
    _validate_manifest_source_links(manifest, schema_version=cast(str, schema_version))

    return feature_ids, feature_scales, feature_packs, label_scales


def _validate_manifest_source_links(
    manifest: Mapping[str, Any],
    *,
    schema_version: str,
) -> None:
    source_hashes = manifest.get("source_hashes")
    if not isinstance(source_hashes, dict):
        raise ValueError("restated manifest source_hashes must be an object")

    def source_digest(key: str, field: str) -> str:
        item = source_hashes.get(key)
        if not isinstance(item, dict):
            raise ValueError(f"restated manifest source_hashes.{key} is required")
        return _normalize_sha(item.get(field), f"source_hashes.{key}.{field}")

    kernel = manifest.get("kernel")
    if not isinstance(kernel, dict):
        raise ValueError("restated manifest kernel binding is required")
    kernel_hash = _normalize_sha(kernel.get("sha256"), "manifest.kernel.sha256")
    builder_hash = _normalize_sha(manifest.get("builder_code_sha256"), "builder_code_sha256")
    expected = {
        "sqlite.daily_prices": source_digest("snapshot_db", "sha256"),
        "direct.manifest": source_digest("direct_manifest", "file_sha256"),
        "direct.discovery_cache": source_digest("discovery_cache", "sha256"),
        "custody.transfer_receipt": source_digest("transfer_receipt", "sha256"),
        "derived.causal_kernel": kernel_hash,
        "derived.label_quality_builder": (
            _normalize_sha(
                manifest.get("corrected_subset_builder_sha256"),
                "corrected_subset_builder_sha256",
            )
            if schema_version == "portfolio-ml-restated-research-dataset.v2"
            else builder_hash
        ),
        "sidecar.corporate_action_adjustments": source_digest(
            "corporate_action_manifest", "sha256"
        ),
    }
    raw = manifest.get("source_manifest_hashes")
    if not isinstance(raw, list):
        raise ValueError("restated manifest source_manifest_hashes must be a list")
    pairs: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, list) or len(item) != 2:
            raise TypeError("source_manifest_hashes entries must be [source_id, sha256]")
        pairs.append(
            (
                _required_row_text(item[0], "source_manifest_hashes.source_id"),
                _normalize_sha(item[1], f"source_manifest_hashes[{item[0]}]"),
            )
        )
    if len({name for name, _digest in pairs}) != len(pairs):
        raise ValueError("source_manifest_hashes contains duplicate source ids")
    actual_pairs = dict(pairs)
    if schema_version == "portfolio-ml-restated-research-dataset.v2":
        lineage = manifest.get("dataset_lineage")
        computation = manifest.get("computation_source_hashes")
        if not isinstance(lineage, dict) or not isinstance(computation, dict):
            raise ValueError("v2 source lineage and computation_source_hashes are required")
        parent = lineage.get("parent_v1")
        corrected = lineage.get("corrected_subset")
        if not isinstance(parent, dict) or not isinstance(corrected, dict):
            raise ValueError("v2 parent and corrected-subset lineage bindings are required")
        extra = {
            "parent.v1.dataset.manifest": _normalize_sha(
                parent.get("manifest_file_sha256"), "dataset_lineage.parent_v1.manifest_file_sha256"
            ),
            "corrected.symbol.subset.dataset.manifest": _normalize_sha(
                corrected.get("manifest_file_sha256"),
                "dataset_lineage.corrected_subset.manifest_file_sha256",
            ),
            "derived.grouped_numeric_parser": _normalize_sha(
                computation.get("grouped_numeric_parser"),
                "computation_source_hashes.grouped_numeric_parser",
            ),
            "derived.v2.row_merge": _normalize_sha(
                computation.get("v2_row_merge"),
                "computation_source_hashes.v2_row_merge",
            ),
            "derived.causal_kernel.impl": _normalize_sha(
                computation.get("causal_kernel_impl"),
                "computation_source_hashes.causal_kernel_impl",
            ),
        }
        if (
            actual_pairs != {**expected, **extra}
            or tuple(name for name, _digest in pairs) != tuple(expected) + tuple(extra)
        ):
            raise ValueError("v2 source_manifest_hashes do not match source, lineage, and computation bindings")
        _validate_v2_computation_hashes(manifest)
    elif actual_pairs != expected:
        raise ValueError("source_manifest_hashes do not match the source and recipe bindings")


def _validate_v2_dataset_lineage(manifest: Mapping[str, Any]) -> None:
    """驗證 v2 parent/subset 清冊與來源快照的身份欄位。"""

    lineage = manifest.get("dataset_lineage")
    if not isinstance(lineage, dict):
        raise ValueError("v2 dataset_lineage is required")
    if set(lineage) != {"parent_v1", "corrected_subset"}:
        raise ValueError("v2 dataset_lineage must contain only parent_v1 and corrected_subset")
    for name in ("parent_v1", "corrected_subset"):
        item = lineage.get(name)
        if not isinstance(item, dict):
            raise ValueError(f"v2 dataset_lineage.{name} is required")
        expected_keys = (
            {"manifest_path", "manifest_file_sha256", "dataset_identity_hash", "row_count", "revision_observed_at"}
            if name == "parent_v1"
            else {"manifest_path", "manifest_file_sha256", "dataset_identity_hash", "row_count", "symbols"}
        )
        if set(item) != expected_keys:
            raise ValueError(f"v2 dataset_lineage.{name} fields differ from the frozen contract")
        path = item.get("manifest_path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"v2 dataset_lineage.{name}.manifest_path is required")
        _normalize_sha(item.get("manifest_file_sha256"), f"dataset_lineage.{name}.manifest_file_sha256")
        _normalize_sha(item.get("dataset_identity_hash"), f"dataset_lineage.{name}.dataset_identity_hash")
        count = item.get("row_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError(f"v2 dataset_lineage.{name}.row_count must be a positive integer")
        if name == "parent_v1":
            parent_revision_clock = _aware_datetime(
                item.get("revision_observed_at"),
                field_name="dataset_lineage.parent_v1.revision_observed_at",
            )
    corrected = lineage["corrected_subset"]
    symbols = corrected.get("symbols")
    try:
        from data_module.ml_restatement_research_dataset_v2_merge import CORRECTED_SYMBOLS
    except ImportError as exc:  # pragma: no cover - v2 builder lands with the dataset repair
        raise RuntimeError("restated v2 corrected-symbol contract module is required") from exc
    if not isinstance(symbols, list) or tuple(sorted(symbols)) != tuple(sorted(CORRECTED_SYMBOLS)):
        raise ValueError("v2 corrected subset symbols differ from the fixed 22-symbol repair scope")
    revision = _normalize_sha(manifest.get("revision"), "manifest.revision")
    if revision != _normalize_sha(
        manifest.get("source_hashes", {}).get("snapshot_db", {}).get("sha256"),
        "source_hashes.snapshot_db.sha256",
    ):
        raise ValueError("v2 revision must identify the sealed source snapshot")
    _aware_datetime(manifest.get("training_as_of"), field_name="training_as_of")
    _aware_datetime(manifest.get("revision_observed_at"), field_name="revision_observed_at")
    _aware_datetime(manifest.get("dataset_created_at"), field_name="dataset_created_at")
    target_audit = manifest.get("original_row_target_audit")
    if not isinstance(target_audit, dict):
        raise ValueError("v2 original_row_target_audit is required")
    if _normalize_sha(
        target_audit.get("artifact_sha256"), "original_row_target_audit.artifact_sha256"
    ) != TARGET_VALUES_AUDIT_HASH:
        raise ValueError("v2 original target audit artifact SHA differs from the verified audit")
    if _normalize_sha(
        target_audit.get("source_manifest_sha256"),
        "original_row_target_audit.source_manifest_sha256",
    ) != TARGET_AUDIT_MANIFEST_HASH:
        raise ValueError("v2 original target audit source manifest differs from Direct OOC")
    direct_baseline_rows = target_audit.get("direct_baseline_row_count")
    observed_target_rows = target_audit.get("target_observed_row_count")
    if (
        isinstance(direct_baseline_rows, bool)
        or direct_baseline_rows != ORIGINAL_DIRECT_TARGET_ROW_COUNT
        or isinstance(observed_target_rows, bool)
        or observed_target_rows != direct_baseline_rows
    ):
        raise ValueError("v2 original target audit row count differs from the verified Direct baseline")
    per_field_counts = target_audit.get("target_field_observed_counts")
    expected_target_names = _META_FIELDS + ("rebalance_worthwhile",)
    if not isinstance(per_field_counts, dict) or per_field_counts != {
        field: direct_baseline_rows for field in expected_target_names
    }:
        raise ValueError("v2 original target audit must verify every target field on every baseline row")


def _verify_v2_lineage_manifest_files(
    manifest: Mapping[str, Any],
) -> tuple[datetime, datetime]:
    """重查 v2 所引用 parent 與 corrected-subset manifest 的檔案 bytes。"""

    lineage = manifest.get("dataset_lineage")
    if not isinstance(lineage, dict):
        raise ValueError("v2 dataset_lineage is required")
    parent_clock: datetime | None = None
    corrected_clock: datetime | None = None
    for name in ("parent_v1", "corrected_subset"):
        binding = lineage[name]
        manifest_path_raw = binding["manifest_path"]
        lineage_path = Path(manifest_path_raw)
        if not lineage_path.is_absolute():
            raise ValueError(f"v2 lineage {name} manifest path must be absolute")
        lineage_path = lineage_path.resolve(strict=True)
        raw = lineage_path.read_bytes()
        if _sha256(raw) != _normalize_sha(
            binding["manifest_file_sha256"], f"dataset_lineage.{name}.manifest_file_sha256"
        ):
            raise ValueError(f"v2 lineage {name} manifest file SHA-256 mismatch")
        child = _json_object(raw, field_name=f"v2 lineage {name} manifest")
        child_identity = _normalize_sha(
            binding["dataset_identity_hash"], f"dataset_lineage.{name}.dataset_identity_hash"
        )
        if (
            child.get("dataset_identity_hash") != child_identity
            or child.get("manifest_hash") != child_identity
            or child.get("row_count") != binding["row_count"]
        ):
            raise ValueError(f"v2 lineage {name} manifest identity or row count mismatch")
        if name == "parent_v1":
            bound_revision_clock = _aware_datetime(
                binding.get("revision_observed_at"),
                field_name="dataset_lineage.parent_v1.revision_observed_at",
            )
            source_revision_clock = _aware_datetime(
                child.get("revision_observed_at"),
                field_name="parent_v1.revision_observed_at",
            )
            if source_revision_clock != bound_revision_clock:
                raise ValueError("v2 parent revision observation clock differs from its source manifest")
            parent_clock = source_revision_clock
        _validate_complete_restatement_manifest(child)
        if name == "corrected_subset":
            source_symbols = child.get("symbol_filter")
            if not isinstance(source_symbols, list) or tuple(sorted(source_symbols)) != tuple(
                sorted(binding.get("symbols", []))
            ):
                raise ValueError("v2 corrected subset symbols differ from its source manifest")
            corrected_clock = _aware_datetime(
                child.get("revision_observed_at"),
                field_name="corrected_subset.revision_observed_at",
            )
            if _aware_datetime(
                manifest.get("training_as_of"), field_name="training_as_of"
            ) != corrected_clock:
                raise ValueError("v2 training_as_of differs from corrected-subset observation clock")
    if parent_clock is None or corrected_clock is None:
        raise ValueError("v2 lineage source observation clocks are incomplete")
    expected_top_revision_clock = max(parent_clock, corrected_clock)
    if _aware_datetime(
        manifest.get("revision_observed_at"), field_name="revision_observed_at"
    ) != expected_top_revision_clock:
        raise ValueError("v2 revision_observed_at must be the latest truthful row observation clock")
    return parent_clock, corrected_clock


def _validate_v2_patch_summary(manifest: Mapping[str, Any]) -> None:
    patch = manifest.get("patch")
    if not isinstance(patch, dict) or patch.get("join_key") != "row_id":
        raise ValueError("v2 patch must declare row_id as its join key")
    parent = manifest["dataset_lineage"]["parent_v1"]
    corrected = manifest["dataset_lineage"]["corrected_subset"]
    counts: dict[str, int] = {}
    for field in ("replaced_row_count", "added_row_count", "corrected_subset_appended_row_count"):
        value = patch.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"v2 patch.{field} must be a non-negative integer")
        counts[field] = value
    if counts["replaced_row_count"] + counts["added_row_count"] != corrected["row_count"]:
        raise ValueError("v2 patched and added row counts must account for every corrected-subset row")
    if counts["added_row_count"] != 0 or counts["replaced_row_count"] != corrected["row_count"]:
        raise ValueError("v2 corrected subset must replace only existing full-parent row IDs")
    if parent["row_count"] + counts["added_row_count"] != manifest["row_count"]:
        raise ValueError("v2 parent and subset-only rows do not account for final row_count")
    if counts["corrected_subset_appended_row_count"] > corrected["row_count"]:
        raise ValueError("v2 corrected-subset appended count exceeds corrected-subset row count")
    if counts["corrected_subset_appended_row_count"] != CORRECTED_SUBSET_APPENDED_ROW_COUNT:
        raise ValueError("v2 corrected-subset append count differs from the verified source scope")
    _normalize_sha(patch.get("merge_recipe_sha256"), "patch.merge_recipe_sha256")
    summary = patch.get("verification_summary")
    if not isinstance(summary, dict):
        raise ValueError("v2 patch verification_summary is required")
    required_true = (
        "parent_row_ids_preserved",
        "parent_targets_exact_for_all_parent_rows",
        "appended_targets_missing",
        "corrected_subset_row_ids_unique",
        "all_subset_rows_joined_or_added",
        "unaffected_feature_and_label_columns_exact",
        "corrected_scope_22_symbols_all_history_and_appends",
        "snapshot_hashes_match",
    )
    if any(summary.get(name) is not True for name in required_true):
        raise ValueError("v2 patch verification_summary contains a failed required invariant")
    expected_counts = {
        "parent_rows": parent["row_count"],
        "final_rows": manifest["row_count"],
        "patched_rows": counts["replaced_row_count"],
        "new_appended_rows": counts["added_row_count"],
        "duplicate_row_ids": 0,
    }
    for field, expected in expected_counts.items():
        value = summary.get(field)
        if isinstance(value, bool) or value != expected:
            raise ValueError(f"v2 patch verification_summary.{field} mismatch")
    unaffected = summary.get("unaffected_rows")
    if isinstance(unaffected, bool) or not isinstance(unaffected, int) or unaffected < 0:
        raise ValueError("v2 patch verification_summary.unaffected_rows must be non-negative")
    if unaffected + counts["replaced_row_count"] != parent["row_count"]:
        raise ValueError("v2 unaffected and patched rows do not account for the parent row count")


def _validate_v2_computation_hashes(manifest: Mapping[str, Any]) -> None:
    computation = manifest.get("computation_source_hashes")
    if not isinstance(computation, dict):
        raise ValueError("v2 computation_source_hashes is required")
    required = (
        "causal_kernel_facade",
        "causal_kernel_impl",
        "grouped_numeric_parser",
        "corrected_subset_builder",
        "v2_row_merge",
    )
    if set(computation) != set(required):
        raise ValueError("v2 computation_source_hashes fields differ from the frozen contract")
    for key in required:
        _normalize_sha(computation.get(key), f"computation_source_hashes.{key}")
    if _normalize_sha(manifest.get("kernel", {}).get("sha256"), "kernel.sha256") != _normalize_sha(
        computation["causal_kernel_facade"], "computation_source_hashes.causal_kernel_facade"
    ):
        raise ValueError("v2 causal kernel facade hash differs from its computation binding")
    if _normalize_sha(manifest.get("corrected_subset_builder_sha256"), "corrected_subset_builder_sha256") != _normalize_sha(
        computation["corrected_subset_builder"], "computation_source_hashes.corrected_subset_builder"
    ):
        raise ValueError("v2 corrected subset builder hash differs from its computation binding")
    if _normalize_sha(manifest.get("patch", {}).get("merge_recipe_sha256"), "patch.merge_recipe_sha256") != _normalize_sha(
        computation["v2_row_merge"], "computation_source_hashes.v2_row_merge"
    ):
        raise ValueError("v2 merge recipe hash differs from its computation binding")


def _read_source_hashes(manifest: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    raw = manifest.get("source_manifest_hashes")
    pairs: list[tuple[str, str]] = []
    if isinstance(raw, dict):
        items: Iterable[Any] = raw.items()
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError("sealed manifest source_manifest_hashes is required")
    for item in items:
        if isinstance(item, tuple) and len(item) == 2:
            source_id, source_hash = item
        elif isinstance(item, list) and len(item) == 2:
            source_id, source_hash = item
        elif isinstance(item, dict):
            source_id = item.get("source_id") or item.get("id")
            source_hash = item.get("sha256") or item.get("hash") or item.get("source_hash")
        else:
            raise TypeError("source_manifest_hashes entries must be pairs or objects")
        source_name = _required_row_text(source_id, "source_manifest_hashes.source_id")
        digest = _normalize_sha(source_hash, "source_manifest_hashes.sha256")
        pairs.append((source_name, digest))
    if not pairs or len({source for source, _digest in pairs}) != len(pairs):
        raise ValueError("source manifest hashes must be non-empty and unique")
    return tuple(sorted(pairs))


def _dataset_files(root: Path, manifest: Mapping[str, Any]) -> tuple[Path, ...]:
    raw = manifest.get("partition_files")
    if not isinstance(raw, list) or not raw:
        raise ValueError("sealed manifest must declare a complete partition_files inventory")
    paths: list[Path] = []
    seen_relative: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError("partition_files entries must be complete descriptor objects")
        relative = item.get("path")
        if not isinstance(relative, str) or not relative.strip():
            raise ValueError("partition_files entries require a relative path")
        normalized = relative.replace("\\", "/")
        if normalized.startswith("/") or ".." in Path(normalized).parts:
            raise ValueError("partition_files paths must be normalized relative paths")
        if relative in seen_relative:
            raise ValueError("partition_files contains a duplicate path")
        seen_relative.add(relative)
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root.resolve()):
            raise ValueError("dataset partition path escapes the sealed root")
        if not candidate.is_file():
            raise FileNotFoundError(f"sealed dataset partition is missing: {candidate}")
        year = item.get("year")
        if isinstance(year, bool) or not isinstance(year, int):
            raise TypeError("partition_files.year must be an integer")
        if normalized != f"year={year}/research_dataset.parquet":
            raise ValueError("partition path must match its declared year")
        for field in ("row_count", "byte_count"):
            value = item.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"partition_files.{field} must be a positive integer")
        paths.append(candidate)
    if len({item["year"] for item in raw}) != len(raw):
        raise ValueError("partition_files must contain one partition per year")
    discovered = {
        path.resolve()
        for path in root.rglob("research_dataset.parquet")
        if path.is_file()
    }
    unique = tuple(sorted(paths))
    if set(unique) != discovered:
        raise ValueError("manifest partition inventory is incomplete or has unlisted Parquet files")
    return unique


def _verify_file_inventory(
    root: Path,
    manifest: Mapping[str, Any],
    files: Sequence[Path],
) -> None:
    raw = manifest.get("partition_files")
    if not isinstance(raw, list) or not raw:
        raise ValueError("sealed manifest must bind every Parquet partition by SHA-256")
    expected: dict[Path, str] = {}
    expected_bytes: dict[Path, int] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError("partition_files entries must be objects with path and sha256")
        relative = item.get("path")
        digest = item.get("sha256") or item.get("file_sha256") or item.get("hash")
        if not isinstance(relative, str):
            raise TypeError("partition_files.path must be text")
        path = (root / relative).resolve()
        expected[path] = _normalize_sha(digest, f"partition_files[{relative}].sha256")
        expected_bytes[path] = int(item["byte_count"])
    if set(expected) != set(files):
        raise ValueError("manifest partition inventory differs from discovered Parquet files")
    for path in files:
        if path.stat().st_size != expected_bytes[path]:
            raise ValueError(f"sealed partition byte count mismatch: {path.name}")
        actual = _file_sha256(path)
        if actual != expected[path]:
            raise ValueError(f"sealed partition SHA-256 mismatch: {path.name}")


def _verify_partition_metadata(
    root: Path,
    manifest: Mapping[str, Any],
    files: Sequence[Path],
) -> int:
    import pyarrow.parquet as pq
    from data_module.ml_restatement_research_dataset import arrow_schema

    raw = manifest["partition_files"]
    descriptors = {
        (root / item["path"]).resolve(): item
        for item in raw
    }
    expected_schema = arrow_schema()
    total_rows = 0
    for path in files:
        parquet = pq.ParquetFile(path)
        metadata = parquet.metadata
        descriptor = descriptors[path]
        if metadata.num_rows != descriptor["row_count"]:
            raise ValueError(f"sealed partition row count mismatch: {path.name}")
        if not parquet.schema_arrow.equals(expected_schema, check_metadata=False):
            raise ValueError(f"sealed partition Arrow schema mismatch: {path.name}")
        total_rows += metadata.num_rows
    if total_rows != manifest["row_count"]:
        raise ValueError("manifest row_count differs from partition metadata")
    return total_rows


def _load_source_custody_args(
    *,
    source_custody_path: Path | None,
    source_custody_hash: str | None,
    manifest_path: Path,
    manifest_hash: str,
    manifest: Mapping[str, Any],
    row_count: int,
) -> tuple[Path | None, str | None, dict[str, Any] | None]:
    if source_custody_path is None and source_custody_hash is None:
        return None, None, None
    if source_custody_path is None or source_custody_hash is None:
        raise ValueError("--source-custody and --source-custody-hash must be provided together")
    path = source_custody_path.resolve(strict=True)
    if path.suffix.lower() != ".json":
        raise ValueError("source custody sidecar must be a JSON file")
    root = manifest_path.parent.resolve()
    if path.is_relative_to(root):
        raise ValueError("source custody JSON must be external to the sealed dataset directory")
    expected_hash = _normalize_sha(source_custody_hash, "source_custody_hash")
    if _file_sha256(path) != expected_hash:
        raise ValueError("source custody sidecar file SHA-256 mismatch")
    payload = _json_object(path.read_bytes(), field_name="source custody sidecar")
    _validate_source_custody(
        payload,
        manifest_path=manifest_path,
        manifest_hash=manifest_hash,
        manifest=manifest,
        row_count=row_count,
    )
    return path, expected_hash, payload


def _require_source_custody_for_row_count(
    row_count: int,
    source_custody_path: Path | None,
) -> None:
    if row_count > 100_000 and source_custody_path is None:
        raise ValueError(
            "datasets above 100000 rows require an external --source-custody sidecar and SHA-256"
        )


def _load_and_validate_source_custody(
    path: Path,
    *,
    expected_hash: str,
    manifest_path: Path,
    manifest_hash: str,
    manifest: Mapping[str, Any],
    row_count: int,
) -> dict[str, Any]:
    if _file_sha256(path) != expected_hash:
        raise RuntimeError("source custody sidecar changed during training")
    payload = _json_object(path.read_bytes(), field_name="source custody sidecar")
    _validate_source_custody(
        payload,
        manifest_path=manifest_path,
        manifest_hash=manifest_hash,
        manifest=manifest,
        row_count=row_count,
    )
    return payload


def _validate_source_custody(
    payload: Mapping[str, Any],
    *,
    manifest_path: Path,
    manifest_hash: str,
    manifest: Mapping[str, Any],
    row_count: int,
) -> None:
    """驗證 A 的外部 source-custody v1 sidecar 與封存資料一致。"""

    if payload.get("schema_version") != "model-repair-source-custody.v1":
        raise ValueError("source custody schema_version must be model-repair-source-custody.v1")
    dataset = payload.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError("source custody dataset binding is required")
    recorded_manifest_path = dataset.get("manifest_path")
    if not isinstance(recorded_manifest_path, str) or not recorded_manifest_path.strip():
        raise ValueError("source custody dataset.manifest_path is required")
    if os.path.normcase(str(Path(recorded_manifest_path).resolve())) != os.path.normcase(
        str(manifest_path.resolve())
    ):
        raise ValueError("source custody sidecar references a different dataset manifest")
    if _normalize_sha(dataset.get("manifest_file_sha256"), "dataset.manifest_file_sha256") != manifest_hash:
        raise ValueError("source custody manifest file hash differs from the sealed manifest")
    if dataset.get("dataset_identity_hash") != manifest.get("dataset_identity_hash"):
        raise ValueError("source custody dataset identity differs from the sealed manifest")
    if dataset.get("build_status") != "complete_research_build":
        raise ValueError("source custody does not confirm a completed dataset build")
    if isinstance(dataset.get("row_count"), bool) or dataset.get("row_count") != row_count:
        raise ValueError("source custody row_count differs from the sealed partitions")
    if manifest.get("schema_version") == "portfolio-ml-restated-research-dataset.v2":
        for field in ("dataset_lineage", "patch", "computation_source_hashes"):
            if payload.get(field) != manifest.get(field):
                raise ValueError(f"source custody {field} differs from the sealed v2 manifest")

    clocks = payload.get("job_clocks")
    if not isinstance(clocks, dict):
        raise ValueError("source custody job_clocks is required")
    if (
        clocks.get("started_at_observed") is not None
        or clocks.get("start_source_verification") != "not_observed_at_job_start"
        or clocks.get("finished_time_basis") != "completion_observed_after_process_exit"
    ):
        raise ValueError("source custody must state that no job-start capture was observed")
    finished_at = _aware_datetime(clocks.get("finished_at"), field_name="job_clocks.finished_at")
    source_check_at = _aware_datetime(
        clocks.get("end_source_verification_at"),
        field_name="job_clocks.end_source_verification_at",
    )
    revision_at = _aware_datetime(
        clocks.get("revision_observed_at"),
        field_name="job_clocks.revision_observed_at",
    )
    manifest_revision_at = _aware_datetime(
        manifest.get("revision_observed_at"), field_name="revision_observed_at"
    )
    if revision_at != manifest_revision_at:
        raise ValueError("source custody revision clock differs from the sealed manifest")
    if source_check_at < finished_at or revision_at > finished_at:
        raise ValueError("source custody completion and observation clocks are inconsistent")

    builder = payload.get("builder")
    if not isinstance(builder, dict):
        raise ValueError("source custody builder binding is required")
    if builder.get("tracked_worktree_clean") is not True:
        raise ValueError("source custody builder tracked worktree must be clean")
    _required_row_text(builder.get("commit"), "builder.commit")
    if _normalize_sha(builder.get("source_sha256"), "builder.source_sha256") != _normalize_sha(
        manifest.get("builder_code_sha256"), "builder_code_sha256"
    ):
        raise ValueError("source custody builder code SHA differs from the dataset identity")
    if manifest.get("schema_version") == "portfolio-ml-restated-research-dataset.v2":
        corrected_builder = payload.get("corrected_subset_builder")
        if not isinstance(corrected_builder, dict):
            raise ValueError("v2 source custody corrected_subset_builder binding is required")
        if _normalize_sha(
            corrected_builder.get("source_sha256"), "corrected_subset_builder.source_sha256"
        ) != _normalize_sha(
            manifest.get("corrected_subset_builder_sha256"), "corrected_subset_builder_sha256"
        ):
            raise ValueError("source custody corrected subset builder SHA differs from the manifest")
        _required_row_text(
            corrected_builder.get("commit"), "corrected_subset_builder.commit"
        )
        if corrected_builder.get("tracked_worktree_clean") is not True:
            raise ValueError("source custody corrected subset builder tracked worktree must be clean")

    kernel = payload.get("kernel")
    manifest_kernel = manifest.get("kernel")
    if not isinstance(kernel, dict) or not isinstance(manifest_kernel, dict):
        raise ValueError("source custody kernel binding is required")
    if kernel.get("tracked_kernel_sources_match_commit") is not True:
        raise ValueError("source custody kernel files do not match their recorded commit")
    _required_row_text(kernel.get("commit"), "kernel.commit")
    manifest_kernel_hash = _normalize_sha(
        manifest_kernel.get("sha256"), "manifest.kernel.sha256"
    )
    if _normalize_sha(
        kernel.get("manifest_kernel_sha256"), "kernel.manifest_kernel_sha256"
    ) != manifest_kernel_hash:
        raise ValueError("source custody kernel SHA differs from the sealed manifest")
    events = kernel.get("audit_events")
    if not isinstance(events, list) or len(events) < 2:
        raise ValueError("source custody needs both midrun and completion kernel audits")
    audit_paths_by_event: list[tuple[str, ...]] = []
    audit_times: list[datetime] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise TypeError("source custody kernel audit event must be an object")
        audit_times.append(_aware_datetime(event.get("at"), field_name=f"kernel.audit_events[{index}].at"))
        timing = _required_row_text(
            event.get("timing"), f"kernel.audit_events[{index}].timing"
        ).casefold()
        if index == 0 and (
            "after job start" not in timing or "not a start capture" not in timing
        ):
            raise ValueError("first kernel audit must be marked post-start, not as a start capture")
        files = event.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError("kernel audit events must bind source files")
        paths: list[str] = []
        for file_index, item in enumerate(files):
            if not isinstance(item, dict):
                raise TypeError("kernel audit source entries must be objects")
            source_path = _required_row_text(
                item.get("path"), f"kernel.audit_events[{index}].files[{file_index}].path"
            )
            paths.append(source_path)
            _normalize_sha(
                item.get("sha256_working_bytes"),
                f"kernel.audit_events[{index}].files[{file_index}].sha256_working_bytes",
            )
            _normalize_sha(
                item.get("sha256_git_blob"),
                f"kernel.audit_events[{index}].files[{file_index}].sha256_git_blob",
            )
            if item.get("crlf_normalized_matches_git") is not True:
                raise ValueError("kernel source bytes do not match their recorded Git blobs")
        if len(set(paths)) != len(paths):
            raise ValueError("kernel audit event repeats a source path")
        audit_paths_by_event.append(tuple(sorted(paths)))
    if len(set(audit_paths_by_event)) != 1 or tuple(audit_times) != tuple(sorted(audit_times)):
        raise ValueError("kernel audit events must cover the same files in chronological order")
    kernel_path = str(manifest_kernel.get("path", "")).replace("\\", "/")
    kernel_basename = kernel_path.rsplit("/", 1)[-1]
    kernel_sha_evidence = [
        item
        for event in events
        for item in event["files"]
        if str(item.get("path", "")).replace("\\", "/").rsplit("/", 1)[-1]
        == kernel_basename
    ]
    if len(kernel_sha_evidence) != len(events) or any(
        _normalize_sha(item.get("sha256_working_bytes"), "kernel source SHA")
        != manifest_kernel_hash
        for item in kernel_sha_evidence
    ):
        raise ValueError("source custody audit bytes differ from the manifest kernel SHA")
    if manifest.get("schema_version") == "portfolio-ml-restated-research-dataset.v2":
        computation = manifest["computation_source_hashes"]
        expected_audit_by_basename = {
            "technical_indicators.py": _normalize_sha(
                computation["causal_kernel_facade"],
                "computation_source_hashes.causal_kernel_facade",
            ),
            "indicator_kernels.py": _normalize_sha(
                computation["causal_kernel_impl"],
                "computation_source_hashes.causal_kernel_impl",
            ),
            "numeric_text.py": _normalize_sha(
                computation["grouped_numeric_parser"],
                "computation_source_hashes.grouped_numeric_parser",
            ),
        }
        for event_index, event in enumerate(events):
            evidence_by_basename = {
                str(item.get("path", "")).replace("\\", "/").rsplit("/", 1)[-1]: item
                for item in event["files"]
            }
            if set(evidence_by_basename) != set(expected_audit_by_basename):
                raise ValueError("v2 source custody must audit the facade, implementation, and numeric parser")
            for basename, digest in expected_audit_by_basename.items():
                if _normalize_sha(
                    evidence_by_basename[basename].get("sha256_working_bytes"),
                    f"kernel.audit_events[{event_index}].{basename}",
                ) != digest:
                    raise ValueError(f"v2 source custody bytes differ for {basename}")
    if audit_times[0] > finished_at or audit_times[-1] > source_check_at:
        raise ValueError("kernel audit clocks fall outside the recorded job completion window")
    if finished_at > source_check_at:
        raise ValueError("final source verification must follow observed build completion")

    runtime = payload.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("source custody runtime binding is required")
    for name in ("python", "numpy", "pandas", "talib"):
        _required_row_text(runtime.get(name), f"runtime.{name}")
    if payload.get("source_hashes") != manifest.get("source_hashes"):
        raise ValueError("source custody source_hashes differ from the sealed manifest")


def _source_custody_identity(data: ResearchArrays) -> dict[str, Any]:
    if data.source_custody is None or data.source_custody_hash is None:
        return {
            "status": "not_provided_small_sample",
            "dataset_row_count": data.row_count,
            "maximum_rows_without_sidecar": 100_000,
        }
    clocks = data.source_custody["job_clocks"]
    identity = {
        "status": "validated_external_sidecar",
        "schema_version": data.source_custody["schema_version"],
        "sidecar_sha256": data.source_custody_hash,
        "dataset_manifest_file_sha256": data.manifest_file_hash,
        "dataset_identity_hash": data.dataset_identity_hash,
        "dataset_row_count": data.row_count,
        "started_at_observed": clocks["started_at_observed"],
        "start_source_verification": clocks["start_source_verification"],
        "finished_at": clocks["finished_at"],
        "end_source_verification_at": clocks["end_source_verification_at"],
        "revision_observed_at": clocks["revision_observed_at"],
        "builder_commit": data.source_custody["builder"]["commit"],
        "kernel_commit": data.source_custody["kernel"]["commit"],
    }
    if data.manifest.get("schema_version") == "portfolio-ml-restated-research-dataset.v2":
        identity.update(
            {
                "dataset_lineage": data.manifest["dataset_lineage"],
                "patch": data.manifest["patch"],
                "computation_source_hashes": data.manifest[
                    "computation_source_hashes"
                ],
            }
        )
    return identity


def _fixed_list_values(array: Any, row_count: int, width: int) -> NDArray[np.int64]:
    if getattr(array.type, "list_size", None) != width:
        raise ValueError(f"fixed-size list width must equal {width}")
    if int(array.null_count) != 0:
        raise ValueError("fixed-size list rows cannot be null")
    values = array.values
    primitive = np.asarray(values.fill_null(0).to_numpy(zero_copy_only=False), dtype=np.int64)
    if primitive.size != row_count * width:
        raise ValueError("fixed-size list child count mismatch")
    return primitive.reshape((row_count, width))


def _fixed_list_null_mask(array: Any, row_count: int, width: int) -> NDArray[np.uint8]:
    if getattr(array.type, "list_size", None) != width:
        raise ValueError(f"fixed-size list width must equal {width}")
    nulls = np.asarray(array.values.is_null().to_numpy(zero_copy_only=False), dtype=np.uint8)
    if nulls.size != row_count * width:
        raise ValueError("fixed-size list null-mask width mismatch")
    return nulls.reshape((row_count, width))


def _read_sequence(
    payload: Mapping[str, Any],
    name: str,
    *,
    alternate: tuple[str, str] | None = None,
) -> tuple[str, ...]:
    value: Any = payload.get(name)
    if value is None and alternate is not None:
        parent = payload.get(alternate[0])
        value = parent.get(alternate[1]) if isinstance(parent, dict) else None
    if not isinstance(value, list) or not value:
        raise ValueError(f"manifest.{name} must be a non-empty string array")
    return tuple(_required_row_text(item, f"manifest.{name}") for item in value)


def _read_integer_sequence(
    payload: Mapping[str, Any],
    name: str,
    *,
    alternate: tuple[str, str] | None = None,
    default: Sequence[int] | None = None,
) -> tuple[int, ...]:
    value: Any = payload.get(name)
    if value is None and alternate is not None:
        parent = payload.get(alternate[0])
        value = parent.get(alternate[1]) if isinstance(parent, dict) else None
    if value is None:
        value = None if default is None else list(default)
    if not isinstance(value, list) or not value:
        raise ValueError(f"manifest.{name} must be a non-empty integer array")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise TypeError(f"manifest.{name} values must be integers")
        result.append(item)
    return tuple(result)


def _read_text(
    payload: Mapping[str, Any],
    name: str,
    *,
    alternate: tuple[str, ...] = (),
) -> str:
    value: Any = payload.get(name)
    for key in alternate:
        if value is None:
            value = payload.get(key)
    return _required_row_text(value, f"manifest.{name}")


def _optional_text(payload: Mapping[str, Any], name: str) -> str | None:
    value = payload.get(name)
    return value if isinstance(value, str) and value.strip() else None


def _optional_sha(
    payload: Mapping[str, Any],
    name: str,
    *,
    alternate: str | None = None,
) -> str | None:
    value = payload.get(name)
    if value is None and alternate is not None:
        value = payload.get(alternate)
    if value is None:
        return None
    return _normalize_sha(value, f"manifest.{name}")


def _open_memmap(path: Path, dtype: np.dtype[Any], shape: tuple[int, ...]) -> np.memmap:
    return np.memmap(path, dtype=dtype, mode="w+", shape=shape)


def _required_row_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    encoded = value.encode("utf-8")
    return value


def _normalize_sha(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be SHA-256 text")
    digest = value.removeprefix("sha256:").lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"{field_name} must be SHA-256")
    return "sha256:" + digest


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _json_object(content: bytes, *, field_name: str) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field_name} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{field_name} must be a JSON object")
    return payload


def _aware_datetime(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        raise ValueError(f"{field_name} must include an explicit timezone and time")
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field_name} must be ISO timestamp text") from exc
    else:
        raise TypeError(f"{field_name} must be a timezone-aware timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _as_date(value: Any, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a date or ISO timestamp")
    try:
        if "T" in value or " " in value:
            return _aware_datetime(value, field_name=field_name).astimezone(TAIPEI).date()
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a canonical date") from exc


def _row_id_from_bytes(value: Any) -> str:
    raw = bytes(value).decode("utf-8").rstrip("\x00")
    if not raw:
        raise ValueError("row_id memmap contains an empty value")
    return raw


def _row_id_hash(data: ResearchArrays, refs: NDArray[np.integer[Any]]) -> str:
    digest = hashlib.sha256()
    digest.update(b"[")
    first = True
    for ref in refs:
        if not first:
            digest.update(b",")
        first = False
        digest.update(
            json.dumps(
                _row_id_from_bytes(data.row_ids[int(ref)]),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    digest.update(b"]")
    return "sha256:" + digest.hexdigest()


def _build_fit_row_lineage(
    *,
    data: ResearchArrays,
    horizon: int,
    selected_refs: NDArray[np.int64],
    records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    overall_hash = _row_id_hash(data, selected_refs)
    head_lineage: dict[str, dict[str, Any]] = {}
    for head_id in EXPERT_HEAD_IDS:
        label_position = _label_position(head_id)
        observed = np.asarray(
            data.label_masks[horizon][selected_refs, label_position],
            dtype=np.uint8,
        ) == 0
        record_count = int(records[head_id].get("fit_row_count", 0))
        observed_count = int(np.sum(observed))
        if record_count != observed_count:
            raise ValueError(f"h{horizon} {head_id} fit lineage count mismatch")
        if observed_count == len(selected_refs):
            row_id_hash = overall_hash
        elif observed_count == 0:
            row_id_hash = _row_id_hash(data, np.empty(0, dtype=np.int64))
        else:
            valid_refs = selected_refs[observed]
            row_id_hash = _row_id_hash(data, valid_refs)
        head_lineage[head_id] = {
            "row_count": record_count,
            "row_id_sha256": row_id_hash,
        }
    return {
        "schema_version": "allocation-fit-row-commitments.v1",
        "mode": "sha256_row_id_commitments",
        "row_count": int(len(selected_refs)),
        "row_id_sha256": overall_hash,
        "heads": head_lineage,
    }


def _label_position(head_id: str) -> int:
    if head_id in REGRESSION_EXPERT_HEADS:
        return REGRESSION_LABEL_POSITIONS[REGRESSION_EXPERT_HEADS.index(head_id)]
    return CLASSIFICATION_LABEL_POSITIONS[CLASSIFICATION_EXPERT_HEADS.index(head_id)]


def _equal_family_weights(pack_ids: Sequence[str]) -> tuple[tuple[str, int], ...]:
    if not pack_ids or len(set(pack_ids)) != len(pack_ids):
        raise ValueError("feature pack ids must be non-empty and unique")
    quotient, remainder = divmod(10_000, len(pack_ids))
    return tuple(
        (pack_id, quotient + int(index == len(pack_ids) - 1) * remainder)
        for index, pack_id in enumerate(pack_ids)
    )


def _model_id(horizons: Sequence[int]) -> str:
    suffix = "-".join(f"h{horizon}" for horizon in horizons)
    return (
        "baldr-ml-allocation-restated-revision-aware-ridge-logistic-"
        f"{suffix}-rank-v2"
    )


def _build_preprocessor_binding(
    *,
    model_id: str,
    order_hash: str,
    training_hash: str,
) -> tuple[PreprocessorBinding, bytes]:
    preprocessor_id = "restated-preprocessor-" + payload_hash(
        {"model_id": model_id, "order_hash": order_hash, "training_hash": training_hash}
    )[7:23]
    binding_fields = {
        "schema_version": "allocation-ml-preprocessor.v1",
        "preprocessor_id": preprocessor_id,
        "strategy": PREPROCESSOR_STRATEGY,
        "feature_order_hash": order_hash,
        "artifact_file": "preprocessor.json",
        "attached_to_model": True,
    }
    provisional_content = (canonical_json(binding_fields) + "\n").encode("utf-8")
    binding = PreprocessorBinding(
        preprocessor_id=preprocessor_id,
        strategy=PREPROCESSOR_STRATEGY,
        feature_order_hash=order_hash,
        artifact_file="preprocessor.json",
        artifact_hash=bytes_hash(provisional_content),
    )
    binding_body = binding.to_dict()
    binding_body.pop("artifact_hash")
    content = (canonical_json(binding_body) + "\n").encode("utf-8")
    if bytes_hash(content) != binding.artifact_hash:
        raise AssertionError("preprocessor sidecar does not match the bound payload")
    return binding, content


def _joblib_bytes(payload: object) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    joblib.dump(payload, buffer, compress=3)
    return buffer.getvalue()


def _write_bytes(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(path: Path, payload: Any) -> None:
    content = (canonical_json(_jsonable(payload)) + "\n").encode("utf-8")
    _write_bytes(path, content)


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _safe_remove_scratch(staging: Path, output_root: Path) -> None:
    resolved_stage = staging.resolve()
    resolved_root = output_root.resolve()
    if resolved_stage.parent != resolved_root or not resolved_stage.name.startswith(".restated-fit-"):
        raise RuntimeError("refusing to remove a scratch directory outside the training root")
    if resolved_stage.exists():
        shutil.rmtree(resolved_stage)


def _mean_abs_int(values: NDArray[np.int64]) -> int:
    if len(values) == 0:
        return 0
    numerator = sum(abs(int(value)) for value in values)
    return int((Decimal(numerator) / Decimal(len(values))).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def _rmse_int(values: NDArray[np.int64]) -> int:
    if len(values) == 0:
        return 0
    square_sum = sum(int(value) * int(value) for value in values)
    return int((Decimal(square_sum).scaleb(0) / Decimal(len(values))).sqrt().quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def _mean_square_int(values: NDArray[np.int64]) -> int:
    if len(values) == 0:
        return 0
    numerator = sum(int(value) * int(value) for value in values)
    return int((Decimal(numerator) / Decimal(len(values))).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def _ratio_bp(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int(
        (Decimal(numerator * 10_000) / Decimal(denominator)).quantize(
            Decimal("1"), rounding=ROUND_HALF_EVEN
        )
    )


def _calibration_ece_bp(probabilities_bp: NDArray[np.int64], targets: NDArray[np.int64]) -> int:
    if len(probabilities_bp) != len(targets) or len(targets) == 0:
        raise ValueError("calibration ECE inputs must be non-empty and aligned")
    bin_error_numerator = 0
    total = len(targets)
    for bin_index in range(10):
        start = bin_index * 1_000
        stop = 10_000 if bin_index == 9 else (bin_index + 1) * 1_000
        selected = (probabilities_bp >= start) & (probabilities_bp <= stop if bin_index == 9 else probabilities_bp < stop)
        count = int(np.sum(selected))
        if count == 0:
            continue
        predicted_sum = sum(int(value) for value in probabilities_bp[selected])
        positive_count = sum(int(value) for value in targets[selected])
        bin_error_numerator += abs(predicted_sum - 10_000 * positive_count)
    return int(
        (Decimal(bin_error_numerator) / Decimal(total)).quantize(
            Decimal("1"), rounding=ROUND_HALF_EVEN
        )
    )


def _cli_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(
        description="Fit and verify a versioned research-only release from sealed restated rows."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--horizons", type=int, nargs="+", default=[5])
    parser.add_argument("--max-fit-rows", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=8_192)
    parser.add_argument("--logistic-iterations", type=int, default=6)
    parser.add_argument("--skip-current-smoke", action="store_true")
    parser.add_argument("--source-custody", type=Path)
    parser.add_argument("--source-custody-hash")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _cli_parser().parse_args(argv)
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    result = train_and_publish(
        manifest_path=args.manifest,
        output_root=args.output_root,
        horizons=tuple(args.horizons),
        max_fit_rows=args.max_fit_rows,
        batch_size=args.batch_size,
        logistic_iterations=args.logistic_iterations,
        run_current_smoke=not args.skip_current_smoke,
        invocation_argv=effective_argv,
        source_custody_path=args.source_custody,
        source_custody_hash=args.source_custody_hash,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
