"""Current-restated direct-store 的獨立研究型別與 fit 邊界。"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import gzip
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import stat
import sys
from types import MappingProxyType
from typing import Any, Literal, cast, overload
from uuid import uuid4
import zlib
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.validation import check_is_fitted

from data_module.ml_research_output_boundary import resolve_ml_research_output_path
from ml_module.allocation_training_service import (
    AllocationTrainingService,
    FeaturePackDefinition,
    RestatedOutcomeOnlyFitResult,
)
from ml_module.purged_walk_forward import MLTimeWindowRow, PurgedWalkForwardFold


class CurrentRestatedResearchError(ValueError):
    """current-restated 研究輸入或 artifact 違反明確時鐘／整數契約。"""


# Keep the minimum-history qualification separate from the event calendar's
# cardinality. Earlier v1 receipts described exactly 905 sessions; new v2
# receipts bind the complete verified Direct calendar, which may be longer.
_CURRENT_RESTATED_FOLD_CALENDAR_V1 = "current-restated-verified-fold-qualification.v1"
_CURRENT_RESTATED_FOLD_CALENDAR_V2 = "current-restated-verified-fold-qualification.v2"
_CURRENT_RESTATED_MINIMUM_CALENDAR_SESSIONS = 905


# The annual feed includes stock, indicator and industry rows that are streamed
# for custody but are not retained by this bridge. Keep its workload bounded
# separately from the smaller semantic TAIEX calendar row cap.
_MAX_CURRENT_RESTATED_RAW_SHARD_BYTES = 32 * 1024 * 1024
_MAX_CURRENT_RESTATED_RAW_ROWS = 1_000_000
_MAX_CURRENT_RESTATED_BENCHMARK_ROWS = 100_000
_MAX_CURRENT_RESTATED_RAW_ROW_BYTES = 1 * 1024 * 1024
_MAX_CURRENT_RESTATED_RAW_DATASET_CONTENT_BYTES = 2 * 1024 * 1024 * 1024
_MAX_MODEL_FIT_AUDIT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CurrentRestatedResearchInvocation:
    """舊排程入口共同傳遞的已釘選研究輸入；不代表正式推薦 cohort。"""

    source_context_path: Path
    source_context_sha256: str
    outcome_receipt_path: Path
    outcome_receipt_sha256: str
    raw_publication_manifest_sha256: str
    raw_dataset_manifest_sha256: str
    outcome_feature_registry_sha256: str
    b_consumption_receipt_path: Path
    b_consumption_receipt_sha256: str
    b_candidate_manifest_sha256: str
    b_adapted_manifest_sha256: str
    b_feature_registry_sha256: str
    model_manifest_path: Path
    model_manifest_sha256: str
    model_bundle_sha256: str
    current_symbols: tuple[str, ...]
    current_event_date: str
    b_current_observation_freeze: str
    inference_at: str | None
    output_root: Path

    def __post_init__(self) -> None:
        """Canonicalize pinned digests for direct and CLI construction alike.

        The CLI parser already strips an optional ``sha256:`` prefix. Scheduled
        callers also construct this value directly from receipts, which retain
        that prefix. Store one canonical bare-hex representation so the same
        verified bytes compare identically on either call path.
        """

        digest_fields = (
            "source_context_sha256",
            "outcome_receipt_sha256",
            "raw_publication_manifest_sha256",
            "raw_dataset_manifest_sha256",
            "outcome_feature_registry_sha256",
            "b_consumption_receipt_sha256",
            "b_candidate_manifest_sha256",
            "b_adapted_manifest_sha256",
            "b_feature_registry_sha256",
            "model_manifest_sha256",
            "model_bundle_sha256",
        )
        for field_name in digest_fields:
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                _plain_sha256(value, f"invocation.{field_name}"),
            )

    def stable_binding_payload(self) -> dict[str, Any]:
        """回傳 parent／child 可比較的來源身分；排除每次執行的 inference clock。"""

        return {
            "schema_version": "current-restated-source-row-research-binding.v1",
            "mode": "source_row_outcome_research",
            "source_context_sha256": self.source_context_sha256,
            "outcome_receipt_sha256": self.outcome_receipt_sha256,
            "raw_publication_manifest_sha256": self.raw_publication_manifest_sha256,
            "raw_dataset_manifest_sha256": self.raw_dataset_manifest_sha256,
            "outcome_feature_registry_sha256": self.outcome_feature_registry_sha256,
            "b_consumption_receipt_sha256": self.b_consumption_receipt_sha256,
            "b_candidate_manifest_sha256": self.b_candidate_manifest_sha256,
            "b_adapted_manifest_sha256": self.b_adapted_manifest_sha256,
            "b_feature_registry_sha256": self.b_feature_registry_sha256,
            "model_manifest_sha256": self.model_manifest_sha256,
            "model_bundle_sha256": self.model_bundle_sha256,
            "current_symbols": list(self.current_symbols),
            "current_event_date": self.current_event_date,
            "b_current_observation_freeze": self.b_current_observation_freeze,
            "historical_pit_eligible": False,
            "formal_calibration_performed": False,
            "model_training_performed": False,
            "verified_model_reused": True,
        }

    def child_arguments(self) -> list[str]:
        """將相同外部 pins 轉成既有 Legacy learning child 的 CLI 參數。"""

        values = (
            ("--research-context-file", self.source_context_path),
            ("--research-context-sha256", self.source_context_sha256),
            ("--research-outcome-receipt", self.outcome_receipt_path),
            ("--research-outcome-receipt-sha256", self.outcome_receipt_sha256),
            ("--research-raw-publication-manifest-sha256", self.raw_publication_manifest_sha256),
            ("--research-raw-dataset-manifest-sha256", self.raw_dataset_manifest_sha256),
            ("--research-outcome-feature-registry-sha256", self.outcome_feature_registry_sha256),
            ("--research-b-consumption-receipt", self.b_consumption_receipt_path),
            ("--research-b-consumption-receipt-sha256", self.b_consumption_receipt_sha256),
            ("--research-b-candidate-manifest-sha256", self.b_candidate_manifest_sha256),
            ("--research-b-adapted-manifest-sha256", self.b_adapted_manifest_sha256),
            ("--research-b-feature-registry-sha256", self.b_feature_registry_sha256),
            ("--research-model-manifest", self.model_manifest_path),
            ("--research-model-manifest-sha256", self.model_manifest_sha256),
            ("--research-model-bundle-sha256", self.model_bundle_sha256),
            ("--research-current-symbols", ",".join(self.current_symbols)),
            ("--research-current-event-date", self.current_event_date),
            ("--research-b-current-observation-freeze", self.b_current_observation_freeze),
            ("--research-output-root", self.output_root),
        )
        result = ["--current-restated-research-only"]
        for flag, value in values:
            result.extend((flag, str(value)))
        if self.inference_at is not None:
            result.extend(("--research-inference-at", self.inference_at))
        return result


def add_current_restated_research_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_reference_snapshot: bool = False,
) -> None:
    """為既有入口加入成對的 explicit opt-in 與完整來源 pins。"""

    parser.add_argument(
        "--current-restated-research-only",
        action="store_true",
        help="只執行隔離的 source-row outcome research sidecar，不啟動正式校準／推薦。",
    )
    parser.add_argument("--research-context-file", type=Path, default=None)
    parser.add_argument("--research-context-sha256", default=None)
    parser.add_argument("--research-outcome-receipt", type=Path, default=None)
    parser.add_argument("--research-outcome-receipt-sha256", default=None)
    parser.add_argument("--research-raw-publication-manifest-sha256", default=None)
    parser.add_argument("--research-raw-dataset-manifest-sha256", default=None)
    parser.add_argument("--research-outcome-feature-registry-sha256", default=None)
    parser.add_argument("--research-b-consumption-receipt", type=Path, default=None)
    parser.add_argument("--research-b-consumption-receipt-sha256", default=None)
    parser.add_argument("--research-b-candidate-manifest-sha256", default=None)
    parser.add_argument("--research-b-adapted-manifest-sha256", default=None)
    parser.add_argument("--research-b-feature-registry-sha256", default=None)
    parser.add_argument("--research-model-manifest", type=Path, default=None)
    parser.add_argument("--research-model-manifest-sha256", default=None)
    parser.add_argument("--research-model-bundle-sha256", default=None)
    parser.add_argument("--research-current-symbols", default=None)
    parser.add_argument("--research-current-event-date", default=None)
    parser.add_argument("--research-b-current-observation-freeze", default=None)
    parser.add_argument("--research-inference-at", default=None)
    parser.add_argument("--research-output-root", type=Path, default=None)
    if include_reference_snapshot:
        parser.add_argument("--research-reference-snapshot-result-id", default=None)
        parser.add_argument("--research-reference-snapshot-cohort-hash", default=None)
        parser.add_argument("--research-reference-snapshot-output-path", type=Path, default=None)
        parser.add_argument("--research-reference-snapshot-output-sha256", default=None)


def parse_current_restated_research_invocation(
    args: argparse.Namespace,
    *,
    repository_root: Path | None = None,
    now: datetime | None = None,
) -> CurrentRestatedResearchInvocation | None:
    """驗證 CLI opt-in 的完整 pin group；default run 不受新增欄位影響。"""

    argument_fields = (
        "research_context_file",
        "research_context_sha256",
        "research_outcome_receipt",
        "research_outcome_receipt_sha256",
        "research_raw_publication_manifest_sha256",
        "research_raw_dataset_manifest_sha256",
        "research_outcome_feature_registry_sha256",
        "research_b_consumption_receipt",
        "research_b_consumption_receipt_sha256",
        "research_b_candidate_manifest_sha256",
        "research_b_adapted_manifest_sha256",
        "research_b_feature_registry_sha256",
        "research_model_manifest",
        "research_model_manifest_sha256",
        "research_model_bundle_sha256",
        "research_current_symbols",
        "research_current_event_date",
        "research_b_current_observation_freeze",
        "research_inference_at",
        "research_output_root",
    )
    supplied = [
        name for name in argument_fields if getattr(args, name, None) is not None
    ]
    enabled = getattr(args, "current_restated_research_only", False)
    if not isinstance(enabled, bool):
        raise CurrentRestatedResearchError("research opt-in flag must be bool")
    if not enabled:
        if supplied:
            raise CurrentRestatedResearchError(
                "research pins require --current-restated-research-only"
            )
        return None
    required_fields = tuple(
        name for name in argument_fields if name != "research_inference_at"
    )
    missing = [name for name in required_fields if getattr(args, name, None) is None]
    if missing:
        raise CurrentRestatedResearchError(
            "research-only mode is missing required pins: " + ", ".join(missing)
        )

    def _path_argument(name: str, role: str) -> Path:
        value = getattr(args, name)
        if not isinstance(value, Path):
            raise CurrentRestatedResearchError(f"{role} path must be a Path")
        try:
            path = resolve_ml_research_output_path(
                value,
                repository_root=repository_root,
                access="read",
            )
        except (OSError, TypeError, ValueError) as exc:
            raise CurrentRestatedResearchError(f"{role} path is outside approved research output") from exc
        if path.is_symlink() or not path.is_file() or path.resolve(strict=True) != path:
            raise CurrentRestatedResearchError(f"{role} must be a regular research file")
        return path

    def _digest_argument(name: str) -> str:
        return _plain_sha256(getattr(args, name), name)

    context_path = _path_argument("research_context_file", "source context")
    outcome_receipt_path = _path_argument("research_outcome_receipt", "Direct receipt")
    b_receipt_path = _path_argument("research_b_consumption_receipt", "B consumption receipt")
    model_manifest_path = _path_argument("research_model_manifest", "model manifest")
    symbol_text = getattr(args, "research_current_symbols")
    if not isinstance(symbol_text, str) or not symbol_text:
        raise CurrentRestatedResearchError("research current symbols must be comma-separated text")
    symbols = tuple(symbol_text.split(","))
    if (
        not symbols
        or len(symbols) > 16
        or any(not symbol or symbol != symbol.strip() for symbol in symbols)
        or len(set(symbols)) != len(symbols)
        or any(not all(character.isalnum() for character in symbol) for symbol in symbols)
    ):
        raise CurrentRestatedResearchError("research current symbol list is invalid")
    event_date = getattr(args, "research_current_event_date")
    if not isinstance(event_date, str):
        raise CurrentRestatedResearchError("research current event date must be ISO text")
    _strict_date(event_date, "research_current_event_date")
    b_freeze_text = getattr(args, "research_b_current_observation_freeze")
    b_freeze = _aware_iso(b_freeze_text, "research_b_current_observation_freeze")
    actual_now = now or datetime.now(timezone.utc)
    if actual_now.tzinfo is None or actual_now.utcoffset() is None:
        raise CurrentRestatedResearchError("validator clock must be aware")
    actual_now = actual_now.astimezone(timezone.utc)
    if b_freeze > actual_now:
        raise CurrentRestatedResearchError("B current-observation freeze is later than the actual clock")
    inference_value = getattr(args, "research_inference_at")
    inference_text: str | None = None
    if inference_value is not None:
        if not isinstance(inference_value, str):
            raise CurrentRestatedResearchError("research inference clock must be ISO text")
        inference = _aware_iso(inference_value, "research_inference_at")
        if inference > actual_now:
            raise CurrentRestatedResearchError("research inference clock is later than the actual clock")
        inference_text = inference.isoformat()
    output_value = getattr(args, "research_output_root")
    if not isinstance(output_value, Path):
        raise CurrentRestatedResearchError("research output root must be a Path")
    try:
        output_root = resolve_ml_research_output_path(
            output_value,
            repository_root=repository_root,
            access="write",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise CurrentRestatedResearchError("research output root is outside approved output/ml_research") from exc
    if output_root.is_symlink() or output_root.is_file():
        raise CurrentRestatedResearchError("research output root must be a non-reparse directory path")

    expected_file_pins = (
        (context_path, "research_context_sha256"),
        (outcome_receipt_path, "research_outcome_receipt_sha256"),
        (b_receipt_path, "research_b_consumption_receipt_sha256"),
        (model_manifest_path, "research_model_manifest_sha256"),
    )
    normalized_file_pins = {
        field: _digest_argument(field) for _path, field in expected_file_pins
    }
    for path, field in expected_file_pins:
        if _sha256_file(path) != normalized_file_pins[field]:
            raise CurrentRestatedResearchError(
                f"{field} does not match the input file's current bytes"
            )

    return CurrentRestatedResearchInvocation(
        source_context_path=context_path,
        source_context_sha256=normalized_file_pins["research_context_sha256"],
        outcome_receipt_path=outcome_receipt_path,
        outcome_receipt_sha256=normalized_file_pins["research_outcome_receipt_sha256"],
        raw_publication_manifest_sha256=_digest_argument("research_raw_publication_manifest_sha256"),
        raw_dataset_manifest_sha256=_digest_argument("research_raw_dataset_manifest_sha256"),
        outcome_feature_registry_sha256=_digest_argument("research_outcome_feature_registry_sha256"),
        b_consumption_receipt_path=b_receipt_path,
        b_consumption_receipt_sha256=_digest_argument("research_b_consumption_receipt_sha256"),
        b_candidate_manifest_sha256=_digest_argument("research_b_candidate_manifest_sha256"),
        b_adapted_manifest_sha256=_digest_argument("research_b_adapted_manifest_sha256"),
        b_feature_registry_sha256=_digest_argument("research_b_feature_registry_sha256"),
        model_manifest_path=model_manifest_path,
        model_manifest_sha256=_digest_argument("research_model_manifest_sha256"),
        model_bundle_sha256=_digest_argument("research_model_bundle_sha256"),
        current_symbols=symbols,
        current_event_date=event_date,
        b_current_observation_freeze=b_freeze.isoformat(),
        inference_at=inference_text,
        output_root=output_root,
    )


def current_restated_research_input_binding_sha256(
    invocation: CurrentRestatedResearchInvocation,
) -> str:
    """計算 parent／child 共用的 source/model/vector 選取契約 hash。"""

    return sha256(_canonical_json_bytes(invocation.stable_binding_payload())).hexdigest()


def convert_current_restated_turnover_twd_to_minor(
    value_int: int,
    *,
    decimal_exponent: int,
    source_unit: str,
) -> int:
    """將新 raw contract 的 TWD 成交金額轉為整數分；只允許轉換一次。"""

    if isinstance(value_int, bool) or not isinstance(value_int, int):
        raise TypeError("turnover value_int must be a strict integer")
    if isinstance(decimal_exponent, bool) or not isinstance(decimal_exponent, int):
        raise TypeError("turnover decimal exponent must be an integer")
    if not 0 <= decimal_exponent <= 18:
        raise ValueError("turnover decimal exponent is outside 0..18")
    if source_unit != "TWD":
        raise ValueError("turnover conversion requires the corrected TWD source unit")
    turnover_twd = Decimal(value_int).scaleb(-decimal_exponent)
    turnover_minor = turnover_twd * Decimal(100)
    integral_minor = turnover_minor.to_integral_value()
    if turnover_minor != integral_minor:
        raise ValueError("TWD turnover cannot be represented as an integer minor unit")
    converted = int(integral_minor)
    if not -(2**63) <= converted < 2**63:
        raise ValueError("converted turnover is outside the signed i64 range")
    return converted


def _normalize_direct_feature_carrier(
    value_int: Any,
    *,
    missing: Any,
    quality_blocked: Any,
    stale: Any,
    feature_id: str,
) -> tuple[int | None, bool, bool, bool]:
    """將 A 的 i64 零缺值載體解回語義 None，並原樣保留三種遮罩。"""

    if any(type(flag) is not bool for flag in (missing, quality_blocked, stale)):
        raise CurrentRestatedResearchError(
            f"Direct masks must contain strict booleans: {feature_id}"
        )
    if type(value_int) is not int:
        raise CurrentRestatedResearchError(
            f"Direct source value carrier must be a strict integer: {feature_id}"
        )
    if not -(2**63) <= value_int < 2**63:
        raise CurrentRestatedResearchError(
            f"Direct source value carrier is outside i64: {feature_id}"
        )
    if missing and value_int != 0:
        raise CurrentRestatedResearchError(
            f"missing Direct source carrier must use canonical zero: {feature_id}"
        )
    return None if missing else value_int, quality_blocked, stale, missing


@dataclass(frozen=True, slots=True)
class PreparedCurrentRestatedCore19Dataset:
    """由已驗證 Direct outcome rows 推導的 CORE19 研究資料。"""

    samples: tuple[CurrentRestatedResearchSample, ...]
    rows_by_symbol_date: Mapping[tuple[str, str], CurrentRestatedResearchRow]
    feature_registry: tuple[Mapping[str, Any], ...]
    feature_packs: tuple[FeaturePackDefinition, ...]
    folds: tuple[PurgedWalkForwardFold, ...]
    event_date_calendar: tuple[str, ...]
    excluded_unusable_row_count: int
    derived_at: str
    outcome_cost_contract: Mapping[str, Any]
    raw_source_scan: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class VerifiedCurrentRestatedBVectorBridge:
    """B 當日原始候選與 A 同日 CORE19 投影的精確數值接線。"""

    event_date: str
    vectors_by_symbol: Mapping[str, CurrentRestatedResearchRow]
    b_consumption_receipt_sha256: str
    b_candidate_manifest_sha256: str
    b_adapted_manifest_sha256: str
    b_feature_registry_sha256: str
    payload: Mapping[str, Any]
    payload_sha256: str


def prepare_verified_current_restated_core19_dataset(
    artifact: object,
) -> PreparedCurrentRestatedCore19Dataset:
    """把 A 的已驗證 Direct rows 經既有純數值公式投影成 CORE19。"""

    from data_module.ml_historical_snapshot_provider import (
        HistoricalIndexObservation,
        HistoricalPriceObservation,
        HistoricalTechnicalObservation,
    )
    from data_module.portfolio_ml_current_restated_outcome_store import (
        VerifiedCurrentRestatedOutcomeArtifact,
    )

    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
    from ml_module.historical_feature_builder import (
        CURRENT_RESTATED_CORE19_FEATURE_IDS,
        compute_current_restated_core19_projection,
    )

    if type(artifact) is not VerifiedCurrentRestatedOutcomeArtifact:
        raise CurrentRestatedResearchError(
            "CORE19 input must come from A's verified outcome artifact loader"
        )
    if (
        artifact.status != "current_restated_outcome_numeric_ready"
        or artifact.historical_pit_eligible is not False
        or artifact.formal_training_eligible is not False
        or artifact.full_teacher_qualified is not False
        or artifact.teacher_targets_present is not False
    ):
        raise CurrentRestatedResearchError(
            "Direct artifact does not satisfy the non-PIT, no-teacher research contract"
        )
    observed_now = datetime.now(timezone.utc)
    for name in (
        "source_observed_at",
        "revision_dependencies_verified_at",
        "raw_revision_dependencies_verified_at",
        "raw_generated_at",
        "current_observation_freeze",
        "artifact_available_at",
    ):
        clock = getattr(artifact, name, None)
        if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
            raise CurrentRestatedResearchError(f"Direct artifact {name} must be timezone-aware")
        if clock.astimezone(timezone.utc) > observed_now:
            raise CurrentRestatedResearchError(f"Direct artifact {name} is later than the actual clock")
    if artifact.artifact_available_at < artifact.current_observation_freeze:
        raise CurrentRestatedResearchError("Direct artifact completion precedes its observation freeze")
    _verify_current_restated_outcome_cost_contract(artifact.outcome_cost_contract)
    _verify_current_restated_twd_turnover_contract(artifact)

    registry = tuple(artifact.feature_registry)
    if not registry or len({item.feature_id for item in registry}) != len(registry):
        raise CurrentRestatedResearchError("Direct feature registry is empty or duplicated")
    if _plain_sha256(artifact.feature_registry_sha256, "Direct feature registry SHA") != _plain_sha256(
        _sha256_bytes(_canonical_json_bytes([
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
        ])),
        "Direct feature registry canonical SHA",
    ):
        raise CurrentRestatedResearchError("Direct feature registry canonical hash differs")
    registry_by_source: dict[str, Any] = {}
    for item in registry:
        if item.role not in {"stock", "benchmark"}:
            raise CurrentRestatedResearchError("Direct source registry has an unsupported role")
        if item.feature_id != f"{item.role}/{item.source_feature_id}":
            raise CurrentRestatedResearchError("Direct feature ID differs from its source role")
        if item.feature_id in registry_by_source:
            raise CurrentRestatedResearchError("Direct registry repeats a stable feature ID")
        registry_by_source[item.feature_id] = item

    required_source_ids = (
        "daily_prices.開盤價",
        "daily_prices.最高價",
        "daily_prices.最低價",
        "daily_prices.收盤價",
        "daily_prices.成交股數",
        "daily_prices.成交金額",
        "technical_indicators.RSI",
        "technical_indicators.MACD",
        "technical_indicators.ADX",
    )
    for source_id in required_source_ids:
        stable_id = f"stock/{source_id}"
        if stable_id not in registry_by_source:
            raise CurrentRestatedResearchError(f"Direct registry lacks required CORE source: {source_id}")
    market_close_ids = tuple(
        feature_id
        for feature_id in (
            "benchmark/market_indices.收盤指數",
            "benchmark/market_indices.收盤價",
        )
        if feature_id in registry_by_source
    )
    if not market_close_ids:
        raise CurrentRestatedResearchError("Direct registry lacks a verified TAIEX close feature")

    registry_index = {item.feature_id: index for index, item in enumerate(registry)}
    by_symbol_date: dict[tuple[str, date], Any] = {}
    stock_state_by_key: dict[tuple[str, date], dict[str, tuple[int | None, bool, bool, bool]]] = {}
    direct_market_state_by_date: dict[date, dict[str, tuple[int | None, bool, bool, bool]]] = {}
    direct_market_source_hash_by_date: dict[date, str] = {}
    target_symbols = tuple(artifact.target_symbols)
    if not target_symbols or tuple(sorted(set(target_symbols))) != target_symbols:
        raise CurrentRestatedResearchError("Direct target symbol inventory is not canonical")
    for observation in artifact.observations:
        if observation.symbol not in target_symbols:
            raise CurrentRestatedResearchError("Direct row symbol is outside the pinned target cohort")
        if type(observation.event_date) is not date:
            raise CurrentRestatedResearchError("Direct event date is not a typed date")
        event_date = observation.event_date
        key = (observation.symbol, event_date)
        if key in by_symbol_date:
            raise CurrentRestatedResearchError("Direct artifact repeats a symbol/event-date row")
        if (
            len(observation.feature_values) != len(registry)
            or len(observation.missing_mask) != len(registry)
            or len(observation.quality_blocked_mask) != len(registry)
            or len(observation.staleness_mask) != len(registry)
        ):
            raise CurrentRestatedResearchError("Direct values and masks differ from the ordered registry")
        if observation.event_reference_only is not True or observation.original_source_available_at is not None:
            raise CurrentRestatedResearchError("Direct row altered its event/reference clock semantics")
        if observation.historical_pit_eligible is not False or observation.formal_training_eligible is not False:
            raise CurrentRestatedResearchError("Direct row claims forbidden PIT/formal eligibility")
        if observation.current_value_available_at > artifact.current_observation_freeze:
            raise CurrentRestatedResearchError("Direct row clock exceeds its immutable observation freeze")
        if not isinstance(observation.source_row_identity_hash, str):
            raise CurrentRestatedResearchError("Direct source row identity hash is missing")
        _plain_sha256(observation.source_row_identity_hash, "Direct source row identity hash")
        source_refs: set[tuple[str, str, str, date]] = set()
        for source_row in observation.source_rows:
            source_key = (
                source_row.source_table,
                source_row.source_id,
                source_row.entity_id,
                source_row.event_date,
            )
            if source_key in source_refs or source_row.event_date != event_date:
                raise CurrentRestatedResearchError("Direct source-row references are duplicated or off-date")
            source_refs.add(source_key)
            _plain_sha256(source_row.source_row_hash, "Direct source-row hash")
        if not any(
            table == "daily_prices" and entity == observation.symbol
            for table, _source_id, entity, _day in source_refs
        ):
            raise CurrentRestatedResearchError("Direct row lacks its exact-symbol source price row")
        if not any(
            table == "market_indices" and entity == artifact.benchmark_entity_id
            for table, _source_id, entity, _day in source_refs
        ):
            raise CurrentRestatedResearchError("Direct row lacks its pinned benchmark source row")

        state: dict[str, tuple[int | None, bool, bool, bool]] = {}
        for item in registry:
            index = registry_index[item.feature_id]
            state[item.feature_id] = _normalize_direct_feature_carrier(
                observation.feature_values[index],
                missing=observation.missing_mask[index],
                quality_blocked=observation.quality_blocked_mask[index],
                stale=observation.staleness_mask[index],
                feature_id=item.feature_id,
            )
        by_symbol_date[key] = observation
        stock_state_by_key[key] = {
            feature_id: value for feature_id, value in state.items()
            if registry_by_source[feature_id].role == "stock"
        }
        benchmark_state = {
            feature_id: value for feature_id, value in state.items()
            if registry_by_source[feature_id].role == "benchmark"
        }
        previous_market = direct_market_state_by_date.get(event_date)
        if previous_market is not None and previous_market != benchmark_state:
            raise CurrentRestatedResearchError("TAIEX values/masks differ across target-symbol rows")
        direct_market_state_by_date[event_date] = benchmark_state
        market_refs = sorted(
            source_row.source_row_hash
            for source_row in observation.source_rows
            if source_row.source_table == "market_indices"
            and source_row.entity_id == artifact.benchmark_entity_id
        )
        market_identity = _sha256_bytes(_canonical_json_bytes(market_refs))
        previous_hash = direct_market_source_hash_by_date.get(event_date)
        if previous_hash is not None and previous_hash != market_identity:
            raise CurrentRestatedResearchError("TAIEX source-row hashes differ across target symbols")
        direct_market_source_hash_by_date[event_date] = market_identity

    event_calendar = tuple(item.isoformat() for item in artifact.event_date_calendar)
    calendar_dates = tuple(artifact.event_date_calendar)
    if not calendar_dates or tuple(sorted(set(calendar_dates))) != calendar_dates:
        raise CurrentRestatedResearchError("Direct full event-date calendar is not ordered and unique")
    if any(event_date not in set(calendar_dates) for _symbol, event_date in by_symbol_date):
        raise CurrentRestatedResearchError("Direct source row falls outside the pinned full calendar")
    if _plain_sha256(artifact.event_date_calendar_sha256, "Direct event calendar SHA") != _sha256_bytes(
        _canonical_json_bytes(list(event_calendar))
    ):
        raise CurrentRestatedResearchError("Direct full calendar bytes differ from its SHA pin")

    market_state_by_date, market_source_hash_by_date, raw_source_scan = (
        _load_verified_current_restated_market_history(
            artifact=artifact,
            calendar_dates=calendar_dates,
            registry_by_source=registry_by_source,
            market_close_ids=market_close_ids,
            include_scan=True,
        )
    )
    for event_date, direct_state in direct_market_state_by_date.items():
        raw_state = market_state_by_date.get(event_date)
        if raw_state is None:
            raise CurrentRestatedResearchError(
                "Direct market reference is absent from the full verified benchmark calendar"
            )
        for stable_id in market_close_ids:
            if direct_state[stable_id] != raw_state[stable_id]:
                raise CurrentRestatedResearchError(
                    "Direct close value/mask differs from its verified full-calendar raw row"
                )
        if direct_market_source_hash_by_date.get(event_date) != market_source_hash_by_date.get(event_date):
            raise CurrentRestatedResearchError(
                "Direct market source-row hash differs from the verified full-calendar raw row"
            )

    def source_value(
        state: Mapping[str, tuple[int | None, bool, bool, bool]],
        stable_id: str,
        *,
        expected_unit: str,
        expected_exponent: int,
    ) -> tuple[Decimal | None, bool, bool, bool, Any]:
        definition = registry_by_source.get(stable_id)
        if definition is None:
            raise CurrentRestatedResearchError(f"required Direct source feature is missing: {stable_id}")
        if definition.unit != expected_unit or definition.decimal_exponent != expected_exponent:
            raise CurrentRestatedResearchError(f"Direct source unit/scale differs for {stable_id}")
        value_int, quality, stale, missing = state[stable_id]
        value = None if value_int is None else Decimal(value_int).scaleb(-expected_exponent)
        return value, quality, stale, missing, definition

    prices_by_symbol: dict[str, list[Any]] = {symbol: [] for symbol in target_symbols}
    technicals_by_symbol: dict[str, list[Any]] = {symbol: [] for symbol in target_symbols}
    quality_price: dict[str, set[str]] = {symbol: set() for symbol in target_symbols}
    stale_price: dict[str, set[str]] = {symbol: set() for symbol in target_symbols}
    quality_technical: dict[str, set[str]] = {symbol: set() for symbol in target_symbols}
    stale_technical: dict[str, set[str]] = {symbol: set() for symbol in target_symbols}
    for (symbol, event_date), state in stock_state_by_key.items():
        day = event_date.isoformat()
        open_value, open_quality, open_stale, _open_missing, _ = source_value(
            state, "stock/daily_prices.開盤價", expected_unit="price_1e4", expected_exponent=4
        )
        high_value, high_quality, high_stale, _high_missing, _ = source_value(
            state, "stock/daily_prices.最高價", expected_unit="price_1e4", expected_exponent=4
        )
        low_value, low_quality, low_stale, _low_missing, _ = source_value(
            state, "stock/daily_prices.最低價", expected_unit="price_1e4", expected_exponent=4
        )
        close_value, close_quality, close_stale, _close_missing, _ = source_value(
            state, "stock/daily_prices.收盤價", expected_unit="price_1e4", expected_exponent=4
        )
        volume_value, volume_quality, volume_stale, _volume_missing, volume_def = source_value(
            state, "stock/daily_prices.成交股數", expected_unit="shares", expected_exponent=0
        )
        turnover_value, turnover_quality, turnover_stale, _turnover_missing, turnover_def = source_value(
            state, "stock/daily_prices.成交金額", expected_unit="TWD", expected_exponent=0
        )
        amount_int = state["stock/daily_prices.成交金額"][0]
        turnover_minor = None if amount_int is None else convert_current_restated_turnover_twd_to_minor(
            amount_int,
            decimal_exponent=turnover_def.decimal_exponent,
            source_unit=turnover_def.unit,
        )
        if any((open_quality, high_quality, low_quality, close_quality, volume_quality, turnover_quality)):
            quality_price[symbol].add(day)
        if any((open_stale, high_stale, low_stale, close_stale, volume_stale, turnover_stale)):
            stale_price[symbol].add(day)
        if volume_value is not None and volume_value != volume_value.to_integral_value():
            raise CurrentRestatedResearchError("Direct volume is not an exact integer share count")
        prices_by_symbol[symbol].append(
            HistoricalPriceObservation(
                symbol=symbol,
                trading_date=day,
                open_price=open_value,
                high_price=high_value,
                low_price=low_value,
                close_price=close_value,
                volume=None if volume_value is None else int(volume_value),
                turnover_amount_minor=turnover_minor,
            )
        )
        technical_values: list[Decimal | None] = []
        technical_states: list[tuple[bool, bool]] = []
        for source_id in (
            "stock/technical_indicators.RSI",
            "stock/technical_indicators.MACD",
            "stock/technical_indicators.ADX",
        ):
            value, quality, stale, _missing, _definition = source_value(
                state,
                source_id,
                expected_unit="indicator_1e4",
                expected_exponent=4,
            )
            technical_values.append(value)
            technical_states.append((quality, stale))
        if any(quality for quality, _stale in technical_states):
            quality_technical[symbol].add(day)
        if any(stale for _quality, stale in technical_states):
            stale_technical[symbol].add(day)
        technicals_by_symbol[symbol].append(
            HistoricalTechnicalObservation(
                symbol=symbol,
                trading_date=day,
                rsi=technical_values[0],
                macd=technical_values[1],
                adx=technical_values[2],
            )
        )

    market_rows, quality_market, stale_market, unavailable_market = (
        _build_current_restated_market_observations(
            calendar_dates=calendar_dates,
            state_by_date=market_state_by_date,
            market_close_ids=market_close_ids,
            registry_by_source=registry_by_source,
        )
    )

    for rows in prices_by_symbol.values():
        rows.sort(key=lambda item: item.trading_date)
    for rows in technicals_by_symbol.values():
        rows.sort(key=lambda item: item.trading_date)
    market_rows.sort(key=lambda item: item.trading_date)

    source_prefix_by_symbol_date: dict[tuple[str, date], str] = {}
    for symbol in target_symbols:
        prefix = sha256()
        for event_date in calendar_dates:
            prefix_observation = by_symbol_date.get((symbol, event_date))
            source_rows = []
            if prefix_observation is not None:
                source_rows = sorted(
                    [
                        {
                            "source_table": item.source_table,
                            "entity_id": item.entity_id,
                            "event_date": item.event_date.isoformat(),
                            "source_row_hash": item.source_row_hash,
                        }
                        for item in prefix_observation.source_rows
                    ],
                    key=lambda item: (item["source_table"], item["entity_id"], item["event_date"]),
                )
            record = {
                "event_date": event_date.isoformat(),
                "source_row_identity_hash": (
                    None
                    if prefix_observation is None
                    else prefix_observation.source_row_identity_hash
                ),
                "source_rows": source_rows,
                "feature_values": (
                    None if prefix_observation is None else list(prefix_observation.feature_values)
                ),
                "missing_mask": (
                    None if prefix_observation is None else list(prefix_observation.missing_mask)
                ),
                "quality_blocked_mask": (
                    None
                    if prefix_observation is None
                    else list(prefix_observation.quality_blocked_mask)
                ),
                "staleness_mask": (
                    None
                    if prefix_observation is None
                    else list(prefix_observation.staleness_mask)
                ),
                "market_source_hash": market_source_hash_by_date.get(event_date),
            }
            prefix.update(_canonical_json_bytes(record))
            source_prefix_by_symbol_date[(symbol, event_date)] = prefix.copy().hexdigest()

    rows_by_key: dict[tuple[str, str], CurrentRestatedResearchRow] = {}
    observation_by_id = {item.sample_id: item for item in artifact.observations}
    if len(observation_by_id) != len(artifact.observations):
        raise CurrentRestatedResearchError("Direct sample IDs are duplicated")
    row_by_id: dict[str, CurrentRestatedResearchRow] = {}
    for key in sorted(by_symbol_date, key=lambda item: (item[1], item[0])):
        symbol, event_date = key
        date_text = event_date.isoformat()
        projection = compute_current_restated_core19_projection(
            symbol=symbol,
            event_date=date_text,
            prices=prices_by_symbol[symbol],
            technicals=technicals_by_symbol[symbol],
            market=market_rows,
            unavailable_market_dates=tuple(sorted(unavailable_market)),
            quality_blocked_price_dates=tuple(sorted(quality_price[symbol])),
            stale_price_dates=tuple(sorted(stale_price[symbol])),
            quality_blocked_technical_dates=tuple(sorted(quality_technical[symbol])),
            stale_technical_dates=tuple(sorted(stale_technical[symbol])),
            quality_blocked_market_dates=tuple(sorted(quality_market)),
            stale_market_dates=tuple(sorted(stale_market)),
        )
        derived_at = datetime.now(timezone.utc)
        if derived_at < artifact.artifact_available_at:
            raise CurrentRestatedResearchError("CORE19 derivation clock precedes Direct artifact completion")
        input_prefix = source_prefix_by_symbol_date[key]
        if len(projection.feature_ids) != 19:
            raise CurrentRestatedResearchError("CORE19 projector returned an unsupported feature count")
        quality_ids = tuple(projection.quality_blocked_feature_ids)
        stale_ids = tuple(projection.staleness_blocked_feature_ids)
        missing_ids = tuple(projection.missing_feature_ids)
        source_features: list[CurrentRestatedFeature] = []
        for feature_id, projected_value_int in zip(projection.feature_ids, projection.values, strict=True):
            value_payload = {
                "schema_version": "current-restated-core19-feature-value.v1",
                "direct_manifest_sha256": artifact.artifact_receipt_bytes_sha256,
                "direct_feature_registry_sha256": artifact.feature_registry_sha256,
                "event_date_calendar_sha256": artifact.event_date_calendar_sha256,
                "source_history_prefix_sha256": input_prefix,
                "feature_id": feature_id,
                "value_int": projected_value_int,
                "missing": feature_id in missing_ids,
                "quality_blocked": feature_id in quality_ids,
                "stale": feature_id in stale_ids,
                "source_observed_at": artifact.source_observed_at.isoformat(),
                "current_value_derived_at": derived_at.isoformat(),
            }
            source_hash = "sha256:" + _sha256_bytes(_canonical_json_bytes(value_payload))
            source_features.append(
                CurrentRestatedFeature(
                    feature_id=feature_id,
                    value_int=projected_value_int,
                    scale=0,
                    observed=projected_value_int is not None,
                    event_at=date_text,
                    source_available_at=None,
                    source_observed_at=artifact.source_observed_at.isoformat(),
                    current_value_available_at=derived_at.isoformat(),
                    source_value_hash=source_hash,
                    source_value_hash_semantics="verified_direct_core19_history_prefix_and_derived_value.v1",
                    stale=feature_id in stale_ids,
                )
            )
        direct_observation = by_symbol_date[key]
        row = CurrentRestatedResearchRow(
            row_id=direct_observation.sample_id,
            symbol=symbol,
            event_date=date_text,
            event_at=date_text,
            features=tuple(source_features),
            missing_mask=missing_ids,
            quality_blocked_mask=quality_ids,
            source_observed_at=artifact.source_observed_at.isoformat(),
            staleness_mask=stale_ids,
            historical_pit_eligible=False,
        )
        rows_by_key[(symbol, date_text)] = row
        row_by_id[direct_observation.sample_id] = row

    samples_by_id: dict[str, CurrentRestatedResearchSample] = {}
    excluded_unusable = 0
    for direct_observation in artifact.observations:
        row = row_by_id[direct_observation.sample_id]
        if not any(
            feature.observed
            and not feature.stale
            and feature.feature_id not in row.quality_blocked_mask
            for feature in row.features
        ):
            excluded_unusable += 1
            continue
        labels: list[CurrentRestatedOutcomeLabel] = []
        for label in direct_observation.labels:
            if (
                isinstance(label.horizon, bool)
                or not isinstance(label.horizon, int)
                or label.horizon not in {5, 10, 20, 60}
                or isinstance(label.stock_return_bp, bool)
                or not isinstance(label.stock_return_bp, int)
                or isinstance(label.benchmark_return_bp, bool)
                or not isinstance(label.benchmark_return_bp, int)
                or isinstance(label.benchmark_excess_return_bp, bool)
                or not isinstance(label.benchmark_excess_return_bp, int)
            ):
                raise CurrentRestatedResearchError("Direct gross/net outcome labels must be strict integer bp values")
            if label.next_entry_date <= direct_observation.event_date:
                raise CurrentRestatedResearchError("outcome entry must follow its source event reference date")
            if label.horizon_end_date < label.next_entry_date:
                raise CurrentRestatedResearchError("outcome end date precedes its T+1 entry date")
            if label.inputs_available_at.date() < label.horizon_end_date:
                raise CurrentRestatedResearchError("outcome input availability precedes the horizon end")
            if label.inputs_available_at > artifact.current_observation_freeze:
                raise CurrentRestatedResearchError("outcome inputs were observed after the Direct freeze")
            if label.benchmark_excess_return_bp != (
                label.stock_return_bp - label.benchmark_return_bp - 80
            ):
                raise CurrentRestatedResearchError(
                    "Direct net excess target does not match its gross stock/benchmark labels and 80 bp cost"
                )
            labels.append(
                CurrentRestatedOutcomeLabel(
                    horizon_trading_days=label.horizon,
                    horizon_end_date=label.horizon_end_date.isoformat(),
                    available_at=label.inputs_available_at.isoformat(),
                    benchmark_excess_return_bp=label.benchmark_excess_return_bp,
                    observed=True,
                    source_available_at=None,
                    source_observed_at=artifact.source_observed_at.isoformat(),
                    label_value_hash=label.source_hash,
                )
            )
        if not any(label.horizon_trading_days == 5 for label in labels):
            continue
        samples_by_id[direct_observation.sample_id] = CurrentRestatedResearchSample(
            row=row,
            horizon_labels=tuple(labels),
        )

    direct_folds = tuple(artifact.folds)
    usable_folds: list[PurgedWalkForwardFold] = []
    calendar_index = {item.isoformat(): index for index, item in enumerate(calendar_dates)}
    last_test_end_index: int | None = None
    for direct_fold in direct_folds:
        if direct_fold.purge_trading_days < 60 or direct_fold.embargo_trading_days < 5:
            raise CurrentRestatedResearchError("Direct fold policy weakens the verified 60/5 minimum")
        train = tuple(samples_by_id[item] for item in direct_fold.train_sample_ids if item in samples_by_id)
        test = tuple(samples_by_id[item] for item in direct_fold.test_sample_ids if item in samples_by_id)
        train_dates = tuple(sorted({sample.row.event_date for sample in train}))
        test_dates = tuple(sorted({sample.row.event_date for sample in test}))
        if len(train_dates) < 125 or len(test_dates) < 63:
            continue
        test_start_index = calendar_index[test_dates[0]]
        latest_train_index = max(calendar_index[item] for item in train_dates)
        if test_start_index - latest_train_index - 1 < 60:
            raise CurrentRestatedResearchError("CORE19-filtered Direct fold has fewer than 60 actual purge sessions")
        if last_test_end_index is not None and test_start_index - last_test_end_index - 1 < 5:
            raise CurrentRestatedResearchError("CORE19-filtered Direct folds have fewer than 5 actual embargo sessions")
        if any(
            date.fromisoformat(label.horizon_end_date) >= date.fromisoformat(test_dates[0])
            for sample in train
            for label in sample.horizon_labels
            if label.horizon_trading_days == 5 and label.observed
        ):
            raise CurrentRestatedResearchError("CORE19-filtered train label crosses its test boundary")
        train_rows = tuple(
            MLTimeWindowRow(
                row_id=sample.row.row_id,
                decision_date=sample.row.event_date,
                label_end_date=next(
                    label.horizon_end_date
                    for label in sample.horizon_labels
                    if label.horizon_trading_days == 5
                ),
            )
            for sample in train
        )
        test_rows = tuple(
            MLTimeWindowRow(
                row_id=sample.row.row_id,
                decision_date=sample.row.event_date,
                label_end_date=next(
                    label.horizon_end_date
                    for label in sample.horizon_labels
                    if label.horizon_trading_days == 5
                ),
            )
            for sample in test
        )
        usable_folds.append(
            PurgedWalkForwardFold(
                fold_id=direct_fold.fold_id,
                train_rows=train_rows,
                test_rows=test_rows,
                test_start=test_dates[0],
                test_end=test_dates[-1],
                purge_days=60,
                embargo_days=5,
            )
        )
        last_test_end_index = calendar_index[test_dates[-1]]
    if len(usable_folds) < 4:
        raise CurrentRestatedResearchError(
            f"CORE19 projection leaves only {len(usable_folds)} qualifying mature folds; at least four are required"
        )

    canonical_schema = dict(
        (feature_id, (dtype, unit))
        for feature_id, dtype, unit in CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema
        if feature_id in CURRENT_RESTATED_CORE19_FEATURE_IDS
    )
    feature_registry = tuple(
        MappingProxyType(
            {
                "feature_id": feature_id,
                "scale": 0,
                "dtype": canonical_schema[feature_id][0],
                "unit": canonical_schema[feature_id][1],
                "derivation_contract": "historical_feature_builder.compute_current_restated_core19_projection.v1",
                "source_feature_ids": _core19_source_feature_ids(feature_id),
                "excluded_feature_ids": ("industry_relative_return_20d_bp",),
                "excluded_reason": "verified_symbol_industry_membership_unavailable",
            }
        )
        for feature_id in CURRENT_RESTATED_CORE19_FEATURE_IDS
    )
    pack = FeaturePackDefinition("core19_current_restated", CURRENT_RESTATED_CORE19_FEATURE_IDS)
    ordered_samples = tuple(
        sorted(samples_by_id.values(), key=lambda sample: (sample.row.event_date, sample.row.symbol))
    )
    return PreparedCurrentRestatedCore19Dataset(
        samples=ordered_samples,
        rows_by_symbol_date=MappingProxyType(rows_by_key),
        feature_registry=feature_registry,
        feature_packs=(pack,),
        folds=tuple(usable_folds),
        event_date_calendar=event_calendar,
        excluded_unusable_row_count=excluded_unusable,
        derived_at=datetime.now(timezone.utc).isoformat(),
        outcome_cost_contract=MappingProxyType(_outcome_cost_contract_payload(artifact.outcome_cost_contract)),
        raw_source_scan=_freeze_json(raw_source_scan),
    )


def verify_b_current_vector_against_core19(
    *,
    direct_artifact: object,
    prepared: PreparedCurrentRestatedCore19Dataset,
    b_artifact: object,
    b_consumption_receipt_path: Path,
    expected_b_consumption_receipt_sha256: str,
    expected_b_candidate_manifest_sha256: str,
    expected_b_adapted_manifest_sha256: str,
    expected_b_feature_registry_sha256: str,
    symbols: Sequence[str],
    event_date: str,
) -> VerifiedCurrentRestatedBVectorBridge:
    """逐欄以 Decimal 驗證 B current rows 與 A 同日原始列後回傳 CORE19。"""

    from data_module.ml_research_direct_ooc_adapter import (
        VerifiedMLResearchNumericArtifact,
    )
    from data_module.portfolio_ml_current_restated_outcome_store import (
        VerifiedCurrentRestatedOutcomeArtifact,
    )

    if type(direct_artifact) is not VerifiedCurrentRestatedOutcomeArtifact:
        raise CurrentRestatedResearchError("B-to-CORE19 bridge requires A's verified Direct artifact")
    if type(b_artifact) is not VerifiedMLResearchNumericArtifact:
        raise CurrentRestatedResearchError("B-to-CORE19 bridge requires B's verified numeric artifact")
    if b_artifact.status != "verified_numeric_observations_ready" or b_artifact.historical_pit_eligible is not False:
        raise CurrentRestatedResearchError("B artifact does not satisfy its verified non-PIT numeric status")
    b_receipt_pin = _verified_research_file(
        b_consumption_receipt_path,
        expected_b_consumption_receipt_sha256,
        role="b_consumption_receipt",
    )
    normalized_symbols = tuple(symbols)
    if (
        not normalized_symbols
        or tuple(sorted(set(normalized_symbols))) != normalized_symbols
        or normalized_symbols != tuple(direct_artifact.target_symbols)
    ):
        raise CurrentRestatedResearchError("B vector symbols differ from the pinned Direct target cohort")
    _strict_date(event_date, "B current event date")
    now = datetime.now(timezone.utc)
    if (
        b_artifact.current_observation_freeze.tzinfo is None
        or b_artifact.current_observation_freeze.utcoffset() is None
        or b_artifact.current_observation_freeze.astimezone(timezone.utc) > now
    ):
        raise CurrentRestatedResearchError("B current observation freeze is missing or later than the actual clock")
    expected_pins = {
        "candidate_manifest_bytes_sha256": _plain_sha256(
            expected_b_candidate_manifest_sha256, "expected_b_candidate_manifest_sha256"
        ),
        "adapted_manifest_canonical_sha256": _plain_sha256(
            expected_b_adapted_manifest_sha256, "expected_b_adapted_manifest_sha256"
        ),
        "feature_registry_sha256": _plain_sha256(
            expected_b_feature_registry_sha256, "expected_b_feature_registry_sha256"
        ),
    }
    for key, expected in expected_pins.items():
        actual = _plain_sha256(b_artifact.source_pins.get(key), f"B source pin {key}")
        if actual != expected:
            raise CurrentRestatedResearchError(f"B verified artifact pin differs for {key}")

    direct_by_key = {
        (item.symbol, item.event_date.isoformat()): item
        for item in direct_artifact.observations
    }
    b_by_symbol: dict[str, Any] = {}
    for item in b_artifact.observations:
        if item.event_date == event_date and item.symbol in normalized_symbols:
            if item.symbol in b_by_symbol:
                raise CurrentRestatedResearchError("B current artifact repeats a requested symbol/date row")
            b_by_symbol[item.symbol] = item
    if set(b_by_symbol) != set(normalized_symbols):
        raise CurrentRestatedResearchError("B current artifact is missing one or more requested symbol/date rows")
    registry_by_id: dict[str, Mapping[str, Any]] = {}
    for entry in b_artifact.feature_registry:
        if not isinstance(entry, Mapping):
            raise CurrentRestatedResearchError("B feature registry entry is not a typed mapping")
        feature_id = entry.get("feature_id")
        if not isinstance(feature_id, str) or feature_id in registry_by_id:
            raise CurrentRestatedResearchError("B feature registry has an invalid or duplicate ID")
        registry_by_id[feature_id] = entry
    direct_registry_by_id = {item.feature_id: item for item in direct_artifact.feature_registry}
    required_ids = (
        "daily_prices.開盤價",
        "daily_prices.最高價",
        "daily_prices.最低價",
        "daily_prices.收盤價",
        "daily_prices.成交股數",
        "daily_prices.成交金額",
    )
    if any(feature_id not in registry_by_id for feature_id in required_ids):
        raise CurrentRestatedResearchError("B registry does not contain the six exact OHLCV/turnover inputs")
    bridge_rows: dict[str, CurrentRestatedResearchRow] = {}
    row_records: list[dict[str, Any]] = []
    for symbol in normalized_symbols:
        symbol_date_key = (symbol, event_date)
        direct = direct_by_key.get(symbol_date_key)
        current_row = prepared.rows_by_symbol_date.get(symbol_date_key)
        b_row = b_by_symbol[symbol]
        if direct is None or current_row is None:
            raise CurrentRestatedResearchError("A Direct/core19 source row is missing at the exact B date")
        if b_row.available_at.astimezone(timezone.utc) > b_artifact.current_observation_freeze.astimezone(timezone.utc):
            raise CurrentRestatedResearchError("B row availability exceeds its pinned current freeze")
        b_values: dict[str, Mapping[str, Any]] = {}
        for value in b_row.values:
            feature_id = value.get("feature_id")
            if not isinstance(feature_id, str) or feature_id in b_values:
                raise CurrentRestatedResearchError("B row has an invalid or duplicate feature ID")
            b_values[feature_id] = value
        comparisons: list[dict[str, Any]] = []
        for feature_id in required_ids:
            b_value = b_values.get(feature_id)
            direct_id = f"stock/{feature_id}"
            direct_definition = direct_registry_by_id.get(direct_id)
            if b_value is None or direct_definition is None:
                raise CurrentRestatedResearchError(f"exact B/A source value is absent: {feature_id}")
            if feature_id in b_row.missing_mask or feature_id in b_row.quality_blocked_mask or feature_id in b_row.staleness_mask:
                raise CurrentRestatedResearchError(f"B current source value is masked: {feature_id}")
            if direct_definition.source_table != "daily_prices":
                raise CurrentRestatedResearchError(f"A source table differs from the daily-price contract: {feature_id}")
            b_int = b_value.get("value_int")
            b_scale = b_value.get("scale")
            a_index = next(index for index, item in enumerate(direct_artifact.feature_registry) if item.feature_id == direct_id)
            a_int = direct.feature_values[a_index]
            a_missing = direct.missing_mask[a_index]
            a_quality = direct.quality_blocked_mask[a_index]
            a_stale = direct.staleness_mask[a_index]
            if (
                type(b_int) is not int
                or type(b_scale) is not int
                or type(direct_definition.decimal_exponent) is not int
            ):
                raise CurrentRestatedResearchError(f"B/A numeric scale contract is not strict for {feature_id}")
            b_int_value = cast(int, b_int)
            b_scale_value = cast(int, b_scale)
            direct_exponent = cast(int, direct_definition.decimal_exponent)
            if not 0 <= b_scale_value <= 18 or not 0 <= direct_exponent <= 18:
                raise CurrentRestatedResearchError(f"B/A exponent is outside the reviewed 0..18 range for {feature_id}")
            if isinstance(b_int_value, bool) or isinstance(b_scale_value, bool) or isinstance(a_int, bool):
                raise CurrentRestatedResearchError(f"B/A source integer contains a boolean for {feature_id}")
            if a_missing or a_quality or a_stale or a_int is None:
                raise CurrentRestatedResearchError(f"A same-date source value is missing or blocked: {feature_id}")
            a_int_value = cast(int, a_int)
            expected_b_unit = "TWD/share" if feature_id in required_ids[:4] else (
                "share" if feature_id == "daily_prices.成交股數" else "TWD"
            )
            expected_a_unit = "price_1e4" if feature_id in required_ids[:4] else (
                "shares" if feature_id == "daily_prices.成交股數" else "TWD"
            )
            if b_value.get("unit") != expected_b_unit or direct_definition.unit != expected_a_unit:
                raise CurrentRestatedResearchError(f"B/A source units differ for {feature_id}")
            b_decimal = Decimal(b_int_value).scaleb(-b_scale_value)
            a_decimal = Decimal(a_int_value).scaleb(-direct_exponent)
            if b_decimal != a_decimal:
                raise CurrentRestatedResearchError(f"B/A exact Decimal value differs for {feature_id}")
            comparisons.append(
                {
                    "feature_id": feature_id,
                    "b_value_int": b_int_value,
                    "b_decimal_exponent": b_scale_value,
                    "b_unit": expected_b_unit,
                    "direct_value_int": a_int_value,
                    "direct_decimal_exponent": direct_exponent,
                    "direct_unit": expected_a_unit,
                    "exact_decimal_match": True,
                    "b_source_value_hash": b_value.get("source_value_hash"),
                }
            )
        vector_payload = _current_restated_row_payload(current_row)
        vector_sha = _sha256_bytes(_canonical_json_bytes(vector_payload))
        numeric_vector_sha = _sha256_bytes(
            _canonical_json_bytes(_core19_numeric_vector_payload(current_row))
        )
        row_records.append(
            {
                "symbol": symbol,
                "event_date": event_date,
                "b_row_identity_sha256": b_row.source_projection_row_identity_hash,
                "b_available_at": b_row.available_at.isoformat(),
                "comparisons": comparisons,
                "direct_sample_id": direct.sample_id,
                "direct_source_row_identity_sha256": direct.source_row_identity_hash,
                "core19_vector_sha256": vector_sha,
                "core19_numeric_vector_sha256": numeric_vector_sha,
                "core19_missing_mask": list(current_row.missing_mask),
                "core19_quality_blocked_mask": list(current_row.quality_blocked_mask),
                "core19_staleness_mask": list(current_row.staleness_mask),
            }
        )
        bridge_rows[symbol] = current_row
    _verify_current_restated_raw_source_scan(
        _plain_json(prepared.raw_source_scan, "Prepared raw source scan")
    )
    payload = {
        "schema_version": "current-restated-b7-to-core19-bridge.v1",
        "status": "verified_exact_b7_source_match_core19_derived",
        "mode": "source_row_outcome_research",
        "event_date": event_date,
        "symbols": list(normalized_symbols),
        "b_consumption_receipt_sha256": _plain_sha256(
            expected_b_consumption_receipt_sha256, "expected_b_consumption_receipt_sha256"
        ),
        "b_consumption_receipt_path": b_receipt_pin["path"],
        "b_consumption_receipt_bytes": b_receipt_pin["bytes"],
        "b_candidate_manifest_sha256": expected_pins["candidate_manifest_bytes_sha256"],
        "b_adapted_manifest_sha256": expected_pins["adapted_manifest_canonical_sha256"],
        "b_feature_registry_sha256": expected_pins["feature_registry_sha256"],
        "b_current_observation_freeze": b_artifact.current_observation_freeze.astimezone(timezone.utc).isoformat(),
        "b_revision_status": b_artifact.source_pins.get("source_revision_qualification"),
        "direct_outcome_manifest_sha256": _plain_sha256(
            direct_artifact.artifact_receipt_bytes_sha256, "Direct outcome manifest SHA"
        ),
        "direct_raw_publication_manifest_sha256": _plain_sha256(
            direct_artifact.raw_publication_manifest_bytes_sha256, "Direct raw publication SHA"
        ),
        "direct_raw_dataset_manifest_sha256": _plain_sha256(
            direct_artifact.raw_dataset_manifest_bytes_sha256, "Direct raw dataset SHA"
        ),
        "direct_feature_registry_sha256": _plain_sha256(
            direct_artifact.feature_registry_sha256, "Direct feature registry SHA"
        ),
        "raw_source_scan": _plain_json(prepared.raw_source_scan, "Prepared raw source scan"),
        "event_date_calendar_sha256": _plain_sha256(
            direct_artifact.event_date_calendar_sha256, "Direct calendar SHA"
        ),
        "source_observed_at": direct_artifact.source_observed_at.isoformat(),
        "direct_artifact_available_at": direct_artifact.artifact_available_at.isoformat(),
        "core19_derived_at": prepared.derived_at,
        "industry_membership_status": "blocked_missing_verified_symbol_membership",
        "rows": row_records,
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "model_training_performed": False,
        "production_action_allowed": False,
    }
    return VerifiedCurrentRestatedBVectorBridge(
        event_date=event_date,
        vectors_by_symbol=MappingProxyType(bridge_rows),
        b_consumption_receipt_sha256=payload["b_consumption_receipt_sha256"],
        b_candidate_manifest_sha256=expected_pins["candidate_manifest_bytes_sha256"],
        b_adapted_manifest_sha256=expected_pins["adapted_manifest_canonical_sha256"],
        b_feature_registry_sha256=expected_pins["feature_registry_sha256"],
        payload=_freeze_json(payload),
        payload_sha256=_sha256_bytes(_canonical_json_bytes(payload)),
    )


def verify_current_restated_legacy_terminal_receipt(
    receipt_path: Path,
    *,
    expected_receipt_sha256: str,
    expected_binding_sha256: str,
    repository_root: Path | None = None,
) -> Mapping[str, Any]:
    """驗 Legacy sidecar 的 create-only terminal bytes，供 Bank barrier 使用。"""

    try:
        path = resolve_ml_research_output_path(
            receipt_path,
            repository_root=repository_root,
            access="read",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise CurrentRestatedResearchError("Legacy terminal receipt is outside research output") from exc
    if path.is_symlink() or not path.is_file() or path.resolve(strict=True) != path:
        raise CurrentRestatedResearchError("Legacy terminal receipt must be a regular research file")
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    actual_sha = _sha256_bytes(raw)
    if (
        len(raw) > 2 * 1024 * 1024
        or len(raw) != before.st_size
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or actual_sha != _plain_sha256(expected_receipt_sha256, "expected Legacy receipt SHA")
    ):
        raise CurrentRestatedResearchError("Legacy terminal receipt changed or failed its actual-byte pin")
    failed_path = path.parent / "failed_receipt.json"
    if failed_path.exists() or failed_path.is_symlink():
        raise CurrentRestatedResearchError("Legacy terminal directory contains a failed receipt")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentRestatedResearchError("Legacy terminal receipt is invalid UTF-8 JSON") from exc
    if not isinstance(payload, dict) or _canonical_json_bytes(payload) != raw:
        raise CurrentRestatedResearchError("Legacy terminal receipt is not canonical JSON")
    expected_binding = _plain_sha256(expected_binding_sha256, "expected Legacy binding SHA")
    if (
        payload.get("schema_version") != "current-restated-source-row-learning-terminal.v1"
        or payload.get("lane") != "legacy"
        or payload.get("mode") != "source_row_outcome_research"
        or payload.get("status") != "verified_research_sidecar"
        or payload.get("terminal") is not True
        or payload.get("binding_sha256") != expected_binding
        or payload.get("model_training_performed") is not False
        or payload.get("verified_model_reused") is not True
        or payload.get("formal_calibration_performed") is not False
        or payload.get("historical_pit_eligible") is not False
        or payload.get("decision_time_eligible") is not False
    ):
        raise CurrentRestatedResearchError("Legacy terminal receipt contract or binding is invalid")
    input_binding = payload.get("input_binding")
    if not isinstance(input_binding, dict):
        raise CurrentRestatedResearchError("Legacy terminal receipt is missing its input binding")
    if _sha256_bytes(_canonical_json_bytes(input_binding)) != expected_binding:
        raise CurrentRestatedResearchError("Legacy terminal receipt input binding hash is inconsistent")
    cohort_sha = _plain_sha256(payload.get("sample_cohort_sha256"), "Legacy sample cohort SHA")
    cohort = _mapping(payload.get("sample_cohort"), "Legacy sample cohort")
    if (
        _sha256_bytes(_canonical_json_bytes(cohort)) != cohort_sha
        or cohort.get("schema_version") != "current-restated-source-row-sample-cohort.v1"
        or cohort.get("cohort_kind") != "verified_direct_source_rows_not_daily_recommendations"
        or cohort.get("historical_pit_eligible") is not False
    ):
        raise CurrentRestatedResearchError("Legacy terminal source-row cohort hash or contract is invalid")
    vector_map = payload.get("core19_numeric_vector_sha256_by_symbol")
    if (
        not isinstance(vector_map, dict)
        or not vector_map
        or any(type(symbol) is not str for symbol in vector_map)
        or any(type(digest) is not str for digest in vector_map.values())
        or set(cohort.get("symbols", ())) != set(vector_map)
    ):
        raise CurrentRestatedResearchError("Legacy terminal receipt has invalid CORE19 vector pins")
    for symbol, digest in vector_map.items():
        _plain_sha256(digest, f"Legacy vector SHA for {symbol}")
    return _freeze_json(payload)


def run_current_restated_research_sidecar(
    invocation: CurrentRestatedResearchInvocation,
    *,
    lane: Literal["legacy", "banktaiwan"],
    cost_scenario: Any,
    actual_invocation: Sequence[str],
    upstream_terminal_receipt_path: Path | None = None,
    expected_upstream_terminal_receipt_sha256: str | None = None,
    expected_upstream_binding_sha256: str | None = None,
    repository_root: Path | None = None,
) -> CurrentRestatedResearchSidecarResult:
    """以原舊入口重驗同一 A/B/context/model，再發布研究用途 sidecar。"""

    from data_module.ml_research_direct_ooc_adapter import (
        load_verified_ml_research_numeric_artifact,
    )
    from data_module.portfolio_ml_current_restated_outcome_store import (
        load_verified_current_restated_outcome_artifact,
    )
    from ml_module.recommendation_cost_scenario import (
        RecommendationCostScenario,
        estimate_round_trip_cost,
    )

    if type(invocation) is not CurrentRestatedResearchInvocation:
        raise CurrentRestatedResearchError("sidecar requires the typed shared invocation")
    if lane not in {"legacy", "banktaiwan"}:
        raise CurrentRestatedResearchError("sidecar lane is unsupported")
    if type(cost_scenario) is not RecommendationCostScenario:
        raise CurrentRestatedResearchError("sidecar cost scenario must use the existing typed contract")
    if lane == "legacy":
        if (
            cost_scenario.is_estimated
            or cost_scenario.fixed_round_trip_cost_bp != 50
            or any(
                value is not None
                for value in (
                    upstream_terminal_receipt_path,
                    expected_upstream_terminal_receipt_sha256,
                    expected_upstream_binding_sha256,
                )
            )
        ):
            raise CurrentRestatedResearchError("Legacy sidecar requires its existing fixed 50 bp lane and no upstream receipt")
    elif (
        not cost_scenario.is_estimated
        or upstream_terminal_receipt_path is None
        or expected_upstream_terminal_receipt_sha256 is None
        or expected_upstream_binding_sha256 is None
    ):
        raise CurrentRestatedResearchError("Bank sidecar requires its existing estimated policy and Legacy terminal barrier")

    binding_payload = invocation.stable_binding_payload()
    binding_sha = current_restated_research_input_binding_sha256(invocation)
    upstream: Mapping[str, Any] | None = None
    if lane == "banktaiwan":
        upstream = verify_current_restated_legacy_terminal_receipt(
            cast(Path, upstream_terminal_receipt_path),
            expected_receipt_sha256=cast(str, expected_upstream_terminal_receipt_sha256),
            expected_binding_sha256=cast(str, expected_upstream_binding_sha256),
            repository_root=repository_root,
        )
        if _plain_sha256(
            expected_upstream_binding_sha256, "expected_upstream_binding_sha256"
        ) != binding_sha:
            raise CurrentRestatedResearchError("Bank binding differs from the current source/model pins")
        if _canonical_json_bytes(
            upstream.get("input_binding", {})
        ) != _canonical_json_bytes(binding_payload):
            raise CurrentRestatedResearchError("Bank and Legacy source/model input bindings differ")

    actual_now = datetime.now(timezone.utc)
    context_file = load_verified_current_restated_context_file(
        invocation.source_context_path,
        expected_context_sha256=invocation.source_context_sha256,
    )
    direct = load_verified_current_restated_outcome_artifact(
        invocation.outcome_receipt_path,
        expected_artifact_receipt_sha256=invocation.outcome_receipt_sha256,
        expected_raw_publication_manifest_sha256=invocation.raw_publication_manifest_sha256,
        expected_raw_dataset_manifest_sha256=invocation.raw_dataset_manifest_sha256,
        expected_feature_registry_sha256=invocation.outcome_feature_registry_sha256,
        available_at_or_before=actual_now,
    )
    _verify_direct_context_binding(direct, context_file)
    b_freeze = _aware_iso(
        invocation.b_current_observation_freeze,
        "invocation.b_current_observation_freeze",
    ).astimezone(timezone.utc)
    b_artifact = load_verified_ml_research_numeric_artifact(
        invocation.b_consumption_receipt_path,
        expected_consumption_receipt_sha256=invocation.b_consumption_receipt_sha256,
        expected_candidate_manifest_bytes_sha256=invocation.b_candidate_manifest_sha256,
        expected_adapted_manifest_canonical_sha256=invocation.b_adapted_manifest_sha256,
        expected_feature_registry_sha256=invocation.b_feature_registry_sha256,
        available_at_or_before=b_freeze,
    )
    prepared = prepare_verified_current_restated_core19_dataset(direct)
    vector_bridge = verify_b_current_vector_against_core19(
        direct_artifact=direct,
        prepared=prepared,
        b_artifact=b_artifact,
        b_consumption_receipt_path=invocation.b_consumption_receipt_path,
        expected_b_consumption_receipt_sha256=invocation.b_consumption_receipt_sha256,
        expected_b_candidate_manifest_sha256=invocation.b_candidate_manifest_sha256,
        expected_b_adapted_manifest_sha256=invocation.b_adapted_manifest_sha256,
        expected_b_feature_registry_sha256=invocation.b_feature_registry_sha256,
        symbols=invocation.current_symbols,
        event_date=invocation.current_event_date,
    )
    model = load_current_restated_outcome_model(
        invocation.model_manifest_path,
        expected_manifest_sha256=invocation.model_manifest_sha256,
        expected_model_bundle_sha256=invocation.model_bundle_sha256,
    )
    manifest = model.manifest
    training_vector_bridge_sha = _verify_research_sidecar_model_bindings(
        manifest=manifest,
        manifest_path=model.manifest_path,
        invocation=invocation,
        context_file=context_file,
        direct=direct,
        vector_bridge=vector_bridge,
    )
    vector_sha_by_symbol = {
        str(item["symbol"]): str(item["core19_numeric_vector_sha256"])
        for item in cast(Sequence[Mapping[str, Any]], vector_bridge.payload["rows"])
    }
    if set(vector_sha_by_symbol) != set(invocation.current_symbols):
        raise CurrentRestatedResearchError("verified CORE19 vectors do not match the explicit source-row cohort")
    if upstream is not None:
        if (
            upstream.get("sample_cohort_sha256") != _sidecar_sample_cohort_sha256(direct, invocation)
            or dict(upstream.get("core19_numeric_vector_sha256_by_symbol", {})) != vector_sha_by_symbol
        ):
            raise CurrentRestatedResearchError("Bank source-row cohort or CORE19 vector differs from Legacy terminal")

    inference_clock = (
        _aware_iso(invocation.inference_at, "invocation.inference_at").astimezone(timezone.utc)
        if invocation.inference_at is not None
        else datetime.now(timezone.utc)
    )
    if inference_clock > datetime.now(timezone.utc):
        raise CurrentRestatedResearchError("sidecar inference clock is later than the actual current clock")
    predictions: list[dict[str, Any]] = []
    for symbol in invocation.current_symbols:
        row = vector_bridge.vectors_by_symbol[symbol]
        prediction = predict_current_restated_outcomes(
            model,
            row=row,
            inference_at=inference_clock.isoformat(),
        )
        label = _matching_current_restated_horizon_label(
            direct,
            symbol=symbol,
            event_date=invocation.current_event_date,
            horizon=5,
        )
        outcome_cost = _current_restated_gross_outcome_cost_projection(
            label,
            cost_scenario=cost_scenario,
            lane=lane,
            market_replay_date=invocation.current_event_date,
            estimate_round_trip_cost=estimate_round_trip_cost,
        )
        predictions.append(
            {
                "symbol": symbol,
                "event_date": invocation.current_event_date,
                "core19_numeric_vector_sha256": vector_sha_by_symbol[symbol],
                "input_quality_summary": _plain_json(
                    prediction["input_quality_summary"], "prediction input quality summary"
                ),
                "model_prediction": _plain_json(prediction, "research prediction"),
                "gross_outcome_and_cost": outcome_cost,
            }
        )

    cohort_payload = _sidecar_sample_cohort_payload(direct, invocation)
    cohort_sha = _sha256_bytes(_canonical_json_bytes(cohort_payload))
    receipt_payload = {
        "schema_version": "current-restated-source-row-learning-terminal.v1",
        "status": "verified_research_sidecar",
        "terminal": True,
        "mode": "source_row_outcome_research",
        "lane": lane,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "process_id": os.getpid(),
        "actual_invocation": list(actual_invocation),
        "binding_sha256": binding_sha,
        "input_binding": binding_payload,
        "sample_cohort": cohort_payload,
        "sample_cohort_sha256": cohort_sha,
        "core19_numeric_vector_sha256_by_symbol": vector_sha_by_symbol,
        "predictions": predictions,
        "cost_scenario": cost_scenario.metadata(),
        "source_pins": {
            **binding_payload,
            "direct_manifest_sha256": direct.artifact_receipt_bytes_sha256,
            "direct_feature_registry_sha256": direct.feature_registry_sha256,
            "source_context_revalidated_dependency_bundle_sha256": (
                context_file.revalidated_dependency_bundle_sha256
            ),
            "direct_event_date_calendar_sha256": direct.event_date_calendar_sha256,
            "training_current_vector_bridge_sha256": training_vector_bridge_sha,
            "current_vector_bridge_sha256": vector_bridge.payload_sha256,
        },
        "model_manifest_path": str(invocation.model_manifest_path),
        "model_manifest_sha256": invocation.model_manifest_sha256,
        "model_bundle_sha256": invocation.model_bundle_sha256,
        "inference_at": inference_clock.isoformat(),
        "model_training_performed": False,
        "verified_model_reused": True,
        "formal_calibration_performed": False,
        "formal_order_allowed": False,
        "production_action_allowed": False,
        "historical_pit_eligible": False,
        "decision_time_eligible": False,
        "recommendation_cohort_status": "not_a_daily_recommendation_cohort",
        "full_allocation_status": "blocked_full_allocation_teacher_unavailable",
    }
    payload_bytes = _canonical_json_bytes(receipt_payload)
    output_root = resolve_ml_research_output_path(
        invocation.output_root,
        repository_root=repository_root,
        access="write",
    )
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = output_root / "source_row_research" / lane / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:12]
    )
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=False, exist_ok=False)
    receipt_path = run_dir / "receipt.json"
    try:
        _write_create_only(receipt_path, payload_bytes)
        _fsync_directory(run_dir)
        _fsync_directory(run_dir.parent)
    except OSError as exc:
        failure = {
            "schema_version": "current-restated-source-row-learning-failure.v1",
            "status": "failed_incomplete_research_sidecar",
            "lane": lane,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "receipt_path": str(receipt_path),
            "error_type": type(exc).__name__,
            "binding_sha256": binding_sha,
        }
        try:
            _write_create_only(run_dir / "failed_receipt.json", _canonical_json_bytes(failure))
        except OSError:
            pass
        raise CurrentRestatedResearchError("research sidecar receipt publication failed; partial output preserved") from exc
    receipt_sha = _sha256_bytes(payload_bytes)
    frozen_payload = cast(Mapping[str, Any], _freeze_json(receipt_payload))
    return CurrentRestatedResearchSidecarResult(
        status="verified_research_sidecar",
        receipt_path=receipt_path,
        receipt_sha256=receipt_sha,
        binding_sha256=binding_sha,
        sample_cohort_sha256=cohort_sha,
        core19_numeric_vector_sha256_by_symbol=MappingProxyType(dict(vector_sha_by_symbol)),
        payload=frozen_payload,
    )


def _verify_research_sidecar_model_bindings(
    *,
    manifest: Mapping[str, Any],
    manifest_path: Path,
    invocation: CurrentRestatedResearchInvocation,
    context_file: VerifiedCurrentRestatedContextFile,
    direct: Any,
    vector_bridge: VerifiedCurrentRestatedBVectorBridge,
) -> str:
    """將重載模型的外部 pins 與本次重驗來源逐項閉合。"""

    direct_source = _mapping(manifest.get("direct_source"), "model.direct_source")
    manifest_pin = _mapping(direct_source.get("manifest"), "model.direct_source.manifest")
    registry = _mapping(manifest.get("feature_registry"), "model.feature_registry")
    context_pin = _mapping(manifest.get("source_context_envelope"), "model.source_context_envelope")
    audit = _read_manifest_fit_audit_for_model(manifest, manifest_path=manifest_path)
    bridge_value = _mapping(manifest.get("current_vector_bridge"), "model.current_vector_bridge")
    bridge_payload = _mapping(bridge_value.get("payload"), "model.current_vector_bridge.payload")
    training_vector_bridge_sha = _verify_current_vector_bridge_revalidation(
        bridge_value,
        vector_bridge,
    )
    checks = (
        (_plain_sha256(manifest_pin.get("sha256"), "model Direct manifest SHA"), invocation.outcome_receipt_sha256),
        (_plain_sha256(context_pin.get("sha256"), "model context SHA"), context_file.sha256),
        (_plain_sha256(bridge_payload.get("b_consumption_receipt_sha256"), "model B receipt SHA"), invocation.b_consumption_receipt_sha256),
        (_plain_sha256(bridge_payload.get("b_candidate_manifest_sha256"), "model B candidate SHA"), invocation.b_candidate_manifest_sha256),
        (_plain_sha256(bridge_payload.get("b_adapted_manifest_sha256"), "model B adapted SHA"), invocation.b_adapted_manifest_sha256),
        (_plain_sha256(bridge_payload.get("b_feature_registry_sha256"), "model B registry SHA"), invocation.b_feature_registry_sha256),
        (_plain_sha256(bridge_payload.get("direct_raw_publication_manifest_sha256"), "model raw publication SHA"), invocation.raw_publication_manifest_sha256),
        (_plain_sha256(bridge_payload.get("direct_raw_dataset_manifest_sha256"), "model raw dataset SHA"), invocation.raw_dataset_manifest_sha256),
        (_plain_sha256(audit.get("direct_feature_registry_sha256"), "model Direct registry SHA"), invocation.outcome_feature_registry_sha256),
        (_plain_sha256(registry.get("sha256"), "model CORE19 registry SHA"), _plain_sha256(audit.get("core19_feature_registry_sha256"), "audit CORE19 registry SHA")),
        (_plain_sha256(bridge_payload.get("direct_outcome_manifest_sha256"), "model bridge Direct SHA"), direct.artifact_receipt_bytes_sha256),
    )
    if any(actual != expected for actual, expected in checks):
        raise CurrentRestatedResearchError("reloaded model source/context/Direct/B pins differ from this invocation")
    expected_context_path = str(context_file.path.resolve(strict=True))
    if Path(str(context_pin.get("path", ""))).resolve(strict=False) != Path(expected_context_path):
        raise CurrentRestatedResearchError("reloaded model was trained from another source-context envelope")
    if _plain_sha256(direct.artifact_receipt_bytes_sha256, "Direct receipt SHA") != invocation.outcome_receipt_sha256:
        raise CurrentRestatedResearchError("verified Direct artifact differs from the invocation receipt pin")
    return training_vector_bridge_sha


def _read_manifest_fit_audit_for_model(
    manifest: Mapping[str, Any],
    *,
    manifest_path: Path,
) -> Mapping[str, Any]:
    descriptor = _mapping(manifest.get("fit_audit"), "model.fit_audit")
    model_path = resolve_ml_research_output_path(manifest_path, access="read")
    filename = descriptor.get("filename")
    if type(filename) is not str or Path(filename).name != filename or filename != "fit_audit.json":
        raise CurrentRestatedResearchError("model fit-audit filename is invalid")
    audit_path = model_path.parent / filename
    raw = _read_bounded_fit_audit_bytes(
        audit_path,
        expected_bytes=descriptor.get("bytes"),
        expected_sha256=descriptor.get("sha256"),
        label="reloaded model fit audit",
    )
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentRestatedResearchError("reloaded model fit audit JSON is invalid") from exc
    if not isinstance(value, dict) or _canonical_json_bytes(value) != raw:
        raise CurrentRestatedResearchError("reloaded model fit audit is not canonical JSON")
    return _mapping(value, "model.fit_audit")


def _read_bounded_fit_audit_bytes(
    path: Path,
    *,
    expected_bytes: Any,
    expected_sha256: Any,
    label: str,
) -> bytes:
    """Read one model fit-audit file under the shared bounded custody contract."""
    if path.is_symlink() or not path.is_file() or path.resolve(strict=True) != path:
        raise CurrentRestatedResearchError(f"{label} is not a regular file")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise CurrentRestatedResearchError(f"{label} is not a regular file")
    if before.st_size > _MAX_MODEL_FIT_AUDIT_BYTES:
        raise CurrentRestatedResearchError(f"{label} exceeds its bounded read limit")
    if type(expected_bytes) is not int or expected_bytes < 0 or before.st_size != expected_bytes:
        raise CurrentRestatedResearchError(f"{label} declared byte count differs from the file")

    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_size != before.st_size
            or opened.st_mtime_ns != before.st_mtime_ns
            or getattr(opened, "st_ino", None) != getattr(before, "st_ino", None)
            or getattr(opened, "st_dev", None) != getattr(before, "st_dev", None)
        ):
            raise CurrentRestatedResearchError(f"{label} changed before being read")
        raw = stream.read(_MAX_MODEL_FIT_AUDIT_BYTES + 1)
        opened_after = os.fstat(stream.fileno())
    after = path.stat()
    if (
        len(raw) > _MAX_MODEL_FIT_AUDIT_BYTES
        or len(raw) != expected_bytes
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
        or getattr(before, "st_dev", None) != getattr(after, "st_dev", None)
        or opened_after.st_size != before.st_size
        or opened_after.st_mtime_ns != before.st_mtime_ns
        or getattr(opened_after, "st_ino", None) != getattr(before, "st_ino", None)
        or path.is_symlink()
        or path.resolve(strict=True) != path
    ):
        raise CurrentRestatedResearchError(f"{label} changed while being read")
    if _sha256_bytes(raw) != _plain_sha256(expected_sha256, "model.fit_audit.sha256"):
        raise CurrentRestatedResearchError(f"{label} actual-byte SHA-256 mismatch")
    return raw


def _sidecar_sample_cohort_payload(
    direct: Any,
    invocation: CurrentRestatedResearchInvocation,
) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for observation in direct.observations:
        if observation.event_date.isoformat() == invocation.current_event_date and observation.symbol in invocation.current_symbols:
            if observation.symbol in selected:
                raise CurrentRestatedResearchError("Direct artifact repeats a source-row cohort symbol/date")
            selected[observation.symbol] = observation
    if set(selected) != set(invocation.current_symbols):
        raise CurrentRestatedResearchError("Direct artifact does not contain every pinned source-row sample")
    return {
        "schema_version": "current-restated-source-row-sample-cohort.v1",
        "symbols": list(invocation.current_symbols),
        "event_date": invocation.current_event_date,
        "samples": [
            {
                "symbol": symbol,
                "sample_id": selected[symbol].sample_id,
                "event_date": selected[symbol].event_date.isoformat(),
                "source_row_identity_sha256": selected[symbol].source_row_identity_hash,
                "current_value_available_at": selected[symbol].current_value_available_at.isoformat(),
            }
            for symbol in invocation.current_symbols
        ],
        "cohort_kind": "verified_direct_source_rows_not_daily_recommendations",
        "historical_pit_eligible": False,
    }


def _sidecar_sample_cohort_sha256(
    direct: Any,
    invocation: CurrentRestatedResearchInvocation,
) -> str:
    return _sha256_bytes(_canonical_json_bytes(_sidecar_sample_cohort_payload(direct, invocation)))


def _matching_current_restated_horizon_label(
    direct: Any,
    *,
    symbol: str,
    event_date: str,
    horizon: int,
) -> Any | None:
    matches = [
        item
        for item in direct.observations
        if item.symbol == symbol and item.event_date.isoformat() == event_date
    ]
    if len(matches) != 1:
        raise CurrentRestatedResearchError("Direct gross-label lookup did not find exactly one source observation")
    labels = [item for item in matches[0].labels if item.horizon == horizon]
    if len(labels) > 1:
        raise CurrentRestatedResearchError("Direct gross-label lookup found duplicate horizon labels")
    return labels[0] if labels else None


def _current_restated_gross_outcome_cost_projection(
    label: Any | None,
    *,
    cost_scenario: Any,
    lane: str,
    market_replay_date: str,
    estimate_round_trip_cost: Any,
) -> dict[str, Any]:
    if label is None:
        return {
            "status": "not_mature",
            "horizon": 5,
            "gross_stock_return_bp": None,
            "gross_benchmark_return_bp": None,
            "benchmark_excess_after_standard_80bp_cost": None,
            "round_trip_cost": None,
            "after_lane_cost_stock_return_bp": None,
            "missing_reason": "direct_horizon_5_gross_label_not_yet_mature",
        }
    for field in (
        "stock_return_bp",
        "benchmark_return_bp",
        "benchmark_excess_return_bp",
        "stock_next_entry_open_value_int",
        "stock_next_entry_open_decimal_exponent",
        "stock_exit_close_value_int",
        "stock_exit_close_decimal_exponent",
    ):
        if type(getattr(label, field, None)) is not int:
            raise CurrentRestatedResearchError(f"mature Direct label lacks strict gross field {field}")
    if label.benchmark_excess_return_bp != label.stock_return_bp - label.benchmark_return_bp - 80:
        raise CurrentRestatedResearchError("mature Direct label violates the standard 80 bp target contract")
    entry_exponent = label.stock_next_entry_open_decimal_exponent
    exit_exponent = label.stock_exit_close_decimal_exponent
    if not 0 <= entry_exponent <= 18 or not 0 <= exit_exponent <= 18:
        raise CurrentRestatedResearchError("mature Direct price exponent is outside the reviewed range")
    entry_price = Decimal(label.stock_next_entry_open_value_int).scaleb(-entry_exponent)
    exit_price = Decimal(label.stock_exit_close_value_int).scaleb(-exit_exponent)
    if not entry_price.is_finite() or not exit_price.is_finite() or entry_price <= 0 or exit_price <= 0:
        raise CurrentRestatedResearchError("mature Direct gross price is not positive finite Decimal")
    estimate = estimate_round_trip_cost(
        cost_scenario,
        market_replay_date=market_replay_date,
        buy_price_twd=entry_price,
        sell_price_twd=exit_price,
    )
    cost_bp = estimate.estimated_round_trip_cost_bp
    after_cost = (
        label.stock_return_bp - cost_bp
        if type(cost_bp) is int
        else None
    )
    return {
        "status": "mature_gross_label",
        "horizon": 5,
        "next_entry_date": label.next_entry_date.isoformat(),
        "horizon_end_date": label.horizon_end_date.isoformat(),
        "gross_stock_return_bp": label.stock_return_bp,
        "gross_benchmark_return_bp": label.benchmark_return_bp,
        "benchmark_excess_after_standard_80bp_cost": label.benchmark_excess_return_bp,
        "price_inputs": {
            "stock_entry_open_value_int": label.stock_next_entry_open_value_int,
            "stock_entry_open_decimal_exponent": entry_exponent,
            "stock_exit_close_value_int": label.stock_exit_close_value_int,
            "stock_exit_close_decimal_exponent": exit_exponent,
            "stock_entry_source_hash": label.stock_entry_source_hash,
            "stock_exit_source_hash": label.stock_exit_source_hash,
        },
        "round_trip_cost": estimate.to_dict(),
        "after_lane_cost_stock_return_bp": after_cost,
        "after_lane_cost_semantics": (
            "gross_stock_return_bp_minus_existing_legacy_fixed_50bp"
            if lane == "legacy"
            else "gross_stock_return_bp_minus_existing_estimated_fee_tax_cost_bp; liquidity_and_slippage_unobserved"
        ),
    }


def _current_restated_row_payload(row: CurrentRestatedResearchRow) -> dict[str, Any]:
    return {
        "row_id": row.row_id,
        "symbol": row.symbol,
        "event_date": row.event_date,
        "event_at": row.event_at,
        "features": [
            {
                "feature_id": feature.feature_id,
                "value_int": feature.value_int,
                "scale": feature.scale,
                "observed": feature.observed,
                "event_at": feature.event_at,
                "source_available_at": feature.source_available_at,
                "source_observed_at": feature.source_observed_at,
                "current_value_available_at": feature.current_value_available_at,
                "source_value_hash": feature.source_value_hash,
                "source_value_hash_semantics": feature.source_value_hash_semantics,
                "stale": feature.stale,
            }
            for feature in row.features
        ],
        "missing_mask": list(row.missing_mask),
        "quality_blocked_mask": list(row.quality_blocked_mask),
        "source_observed_at": row.source_observed_at,
        "staleness_mask": list(row.staleness_mask),
        "historical_pit_eligible": False,
    }


def _core19_numeric_vector_payload(row: CurrentRestatedResearchRow) -> dict[str, Any]:
    """產生排除衍生時鐘、保留精確數值與遮罩的穩定 CORE19 身分。"""

    return {
        "schema_version": "current-restated-core19-numeric-vector.v1",
        "row_id": row.row_id,
        "symbol": row.symbol,
        "event_date": row.event_date,
        "features": [
            {
                "feature_id": feature.feature_id,
                "value_int": feature.value_int,
                "scale": feature.scale,
                "observed": feature.observed,
                "stale": feature.stale,
            }
            for feature in row.features
        ],
        "missing_mask": list(row.missing_mask),
        "quality_blocked_mask": list(row.quality_blocked_mask),
        "staleness_mask": list(row.staleness_mask),
        "historical_pit_eligible": False,
    }


def _current_restated_row_from_payload(value: Any) -> CurrentRestatedResearchRow:
    """從已釘選 JSON 向量建構嚴格 typed current-restated 列。"""

    if not isinstance(value, dict):
        raise CurrentRestatedResearchError("current vector root must be an object")
    required = {
        "row_id",
        "symbol",
        "event_date",
        "event_at",
        "features",
        "missing_mask",
        "quality_blocked_mask",
        "source_observed_at",
        "staleness_mask",
        "historical_pit_eligible",
    }
    if set(value) != required:
        raise CurrentRestatedResearchError("saved current vector fields differ from the typed row contract")
    raw_features = value.get("features")
    if not isinstance(raw_features, list):
        raise CurrentRestatedResearchError("current vector features must be an array")
    features: list[CurrentRestatedFeature] = []
    feature_fields = {
        "feature_id",
        "value_int",
        "scale",
        "observed",
        "event_at",
        "source_available_at",
        "source_observed_at",
        "current_value_available_at",
        "source_value_hash",
        "source_value_hash_semantics",
        "stale",
    }
    for item in raw_features:
        if not isinstance(item, dict) or set(item) != feature_fields:
            raise CurrentRestatedResearchError("saved current vector feature fields differ from the typed contract")
        features.append(CurrentRestatedFeature(**item))
    masks = (
        value.get("missing_mask"),
        value.get("quality_blocked_mask"),
        value.get("staleness_mask"),
    )
    if any(not isinstance(mask, list) or any(type(item) is not str for item in mask) for mask in masks):
        raise CurrentRestatedResearchError("saved current vector masks must contain feature IDs")
    return CurrentRestatedResearchRow(
        row_id=value["row_id"],
        symbol=value["symbol"],
        event_date=value["event_date"],
        event_at=value["event_at"],
        features=tuple(features),
        missing_mask=tuple(cast(list[str], masks[0])),
        quality_blocked_mask=tuple(cast(list[str], masks[1])),
        source_observed_at=value["source_observed_at"],
        staleness_mask=tuple(cast(list[str], masks[2])),
        historical_pit_eligible=value["historical_pit_eligible"],
    )


def _core19_source_feature_ids(feature_id: str) -> tuple[str, ...]:
    """回傳本次 CORE19 投影明列的原始來源欄位。"""

    common_price = (
        "daily_prices.開盤價",
        "daily_prices.最高價",
        "daily_prices.最低價",
        "daily_prices.收盤價",
        "daily_prices.成交股數",
        "daily_prices.成交金額",
    )
    mapping = {
        "stock_return_1d_bp": common_price,
        "stock_return_5d_bp": common_price,
        "stock_return_20d_bp": common_price,
        "stock_return_60d_bp": common_price,
        "trailing_volatility_20d_bp": common_price,
        "high_low_range_20d_bp": common_price,
        "close_to_ma_5d_bp": common_price,
        "close_to_ma_20d_bp": common_price,
        "close_to_ma_60d_bp": common_price,
        "rsi_normalized_bp": ("technical_indicators.RSI",),
        "adx_normalized_bp": ("technical_indicators.ADX",),
        "macd_normalized_bp": ("technical_indicators.MACD", "daily_prices.收盤價"),
        "volume_ratio_5d_bp": common_price,
        "volume_ratio_20d_bp": common_price,
        "turnover_amount_minor": ("daily_prices.成交金額",),
        "market_return_5d_bp": ("market_indices.收盤價", "market_indices.收盤指數"),
        "market_return_20d_bp": ("market_indices.收盤價", "market_indices.收盤指數"),
        "market_return_60d_bp": ("market_indices.收盤價", "market_indices.收盤指數"),
        "stock_minus_market_20d_bp": common_price + (
            "market_indices.收盤價",
            "market_indices.收盤指數",
        ),
    }
    try:
        return mapping[feature_id]
    except KeyError as exc:
        raise CurrentRestatedResearchError(f"CORE19 registry contains an unknown feature: {feature_id}") from exc


@overload
def _load_verified_current_restated_market_history(
    *,
    artifact: Any,
    calendar_dates: Sequence[date],
    registry_by_source: Mapping[str, Any],
    market_close_ids: Sequence[str],
    include_scan: Literal[False] = False,
) -> tuple[
    dict[date, dict[str, tuple[int | None, bool, bool, bool]]],
    dict[date, str],
]: ...


@overload
def _load_verified_current_restated_market_history(
    *,
    artifact: Any,
    calendar_dates: Sequence[date],
    registry_by_source: Mapping[str, Any],
    market_close_ids: Sequence[str],
    include_scan: Literal[True],
) -> tuple[
    dict[date, dict[str, tuple[int | None, bool, bool, bool]]],
    dict[date, str],
    dict[str, Any],
]: ...


def _load_verified_current_restated_market_history(
    *,
    artifact: Any,
    calendar_dates: Sequence[date],
    registry_by_source: Mapping[str, Any],
    market_close_ids: Sequence[str],
    include_scan: bool = False,
) -> (
    tuple[
        dict[date, dict[str, tuple[int | None, bool, bool, bool]]],
        dict[date, str],
    ]
    | tuple[
        dict[date, dict[str, tuple[int | None, bool, bool, bool]]],
        dict[date, str],
        dict[str, Any],
    ]
):
    """由 A 已驗證並釘選的 raw 年分片重建完整 benchmark 日期路徑。"""

    from pathlib import PurePosixPath

    publication_path = _verified_research_path(Path(artifact.raw_publication_manifest_path))
    publication_bytes = publication_path.read_bytes()
    if _sha256_bytes(publication_bytes) != _plain_sha256(
        artifact.raw_publication_manifest_bytes_sha256,
        "raw publication manifest SHA",
    ):
        raise CurrentRestatedResearchError("raw publication manifest actual bytes changed")
    try:
        publication = json.loads(publication_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentRestatedResearchError("raw publication manifest is invalid JSON") from exc
    if (
        not isinstance(publication, dict)
        or publication.get("schema_version") != "ml-current-restated-year-shards.v1"
        or publication.get("current_restated") is not True
        or publication.get("historical_pit_eligible") is not False
        or publication.get("formal_training_eligible") is not False
    ):
        raise CurrentRestatedResearchError("raw publication does not match the current-restated contract")
    datasets = publication.get("datasets")
    dataset_entry = datasets.get("core_long_history") if isinstance(datasets, dict) else None
    if not isinstance(dataset_entry, dict):
        raise CurrentRestatedResearchError("raw publication lacks its pinned CORE dataset")

    dataset_path = _verified_research_path(Path(artifact.raw_dataset_manifest_path))
    dataset_bytes = dataset_path.read_bytes()
    if _sha256_bytes(dataset_bytes) != _plain_sha256(
        artifact.raw_dataset_manifest_bytes_sha256,
        "raw dataset manifest SHA",
    ):
        raise CurrentRestatedResearchError("raw dataset manifest actual bytes changed")
    relative_manifest = dataset_entry.get("manifest_path")
    if (
        type(relative_manifest) is not str
        or not relative_manifest
        or "\\" in relative_manifest
    ):
        raise CurrentRestatedResearchError("raw publication dataset path is not canonical POSIX text")
    manifest_parts = PurePosixPath(relative_manifest)
    if manifest_parts.is_absolute() or any(part in {"", ".", ".."} for part in manifest_parts.parts):
        raise CurrentRestatedResearchError("raw publication dataset path contains an unsafe component")
    publication_root = publication_path.parent.resolve(strict=True)
    declared_dataset_path = publication_root.joinpath(*manifest_parts.parts).resolve(strict=True)
    if not declared_dataset_path.is_relative_to(publication_root) or declared_dataset_path != dataset_path:
        raise CurrentRestatedResearchError("raw publication and outcome dataset pins name different files")
    try:
        dataset = json.loads(dataset_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentRestatedResearchError("raw dataset manifest is invalid JSON") from exc
    if (
        not isinstance(dataset, dict)
        or dataset.get("schema_version") != "ml-current-restated-year-shard-dataset.v1"
        or dataset.get("current_restated") is not True
        or dataset.get("historical_pit_eligible") is not False
        or dataset.get("formal_training_eligible") is not False
        or dataset_entry.get("manifest_hash") != dataset.get("manifest_hash")
        or _plain_sha256(dataset.get("source_context_bundle_sha256"), "raw context bundle SHA")
        != _plain_sha256(publication.get("source_context_bundle_sha256"), "publication context bundle SHA")
    ):
        raise CurrentRestatedResearchError("raw dataset manifest identity or non-PIT contract is invalid")

    raw_features_value = dataset.get("features")
    if not isinstance(raw_features_value, list):
        raise CurrentRestatedResearchError("raw dataset feature registry is absent")
    raw_features: dict[str, Mapping[str, Any]] = {}
    for feature in raw_features_value:
        if not isinstance(feature, dict) or type(feature.get("feature_id")) is not str:
            raise CurrentRestatedResearchError("raw dataset feature registry has a malformed row")
        feature_id = feature["feature_id"]
        if feature_id in raw_features:
            raise CurrentRestatedResearchError("raw dataset feature registry repeats an ID")
        raw_features[feature_id] = feature
    for stable_id in market_close_ids:
        direct_definition = registry_by_source.get(stable_id)
        if direct_definition is None:
            raise CurrentRestatedResearchError("Direct registry lost a benchmark close definition")
        raw_definition = raw_features.get(direct_definition.source_feature_id)
        if (
            raw_definition is None
            or raw_definition.get("table_name") != "market_indices"
            or raw_definition.get("unit") != "index_1e4"
            or raw_definition.get("scale") != 4
            or direct_definition.source_table != "market_indices"
            or direct_definition.unit != "index_1e4"
            or direct_definition.decimal_exponent != 4
        ):
            raise CurrentRestatedResearchError("raw and Direct benchmark close schemas differ")

    shard_entries = dataset.get("shards")
    if not isinstance(shard_entries, list) or not shard_entries:
        raise CurrentRestatedResearchError("raw dataset annual shard inventory is absent")
    pins = tuple(artifact.raw_shard_pins)
    pin_by_role = {item.role_id: item for item in pins}
    if len(pin_by_role) != len(pins) or len(pin_by_role) != len(shard_entries):
        raise CurrentRestatedResearchError("raw shard pin inventory is duplicated or incomplete")

    dataset_row_count = dataset.get("row_count")
    if type(dataset_row_count) is not int or dataset_row_count < 0:
        raise CurrentRestatedResearchError("raw dataset declared row_count is invalid")

    validated_shards: list[tuple[Mapping[str, Any], int, Any, Path, int]] = []
    seen_years: set[int] = set()
    declared_total_rows = 0
    for index, shard_value in enumerate(shard_entries):
        if not isinstance(shard_value, dict):
            raise CurrentRestatedResearchError("raw shard manifest entry is malformed")
        year = shard_value.get("year")
        declared_rows = shard_value.get("row_count")
        if isinstance(year, bool) or not isinstance(year, int):
            raise CurrentRestatedResearchError("raw shard year must be an integer")
        if year in seen_years:
            raise CurrentRestatedResearchError("raw annual shard inventory repeats a year")
        seen_years.add(year)
        if type(declared_rows) is not int or declared_rows < 0:
            raise CurrentRestatedResearchError(
                f"raw shard year {year} declared row_count is invalid"
            )
        role_id = f"raw_shard_year_{year}"
        pin = pin_by_role.get(role_id)
        relative_shard = shard_value.get("path")
        if type(relative_shard) is not str or not relative_shard or "\\" in relative_shard:
            raise CurrentRestatedResearchError("raw shard path is not canonical POSIX text")
        shard_parts = PurePosixPath(relative_shard)
        if shard_parts.is_absolute() or any(part in {"", ".", ".."} for part in shard_parts.parts):
            raise CurrentRestatedResearchError("raw shard path contains an unsafe component")
        declared_shard_path = publication_root.joinpath(*shard_parts.parts).resolve(strict=True)
        pinned_shard_path = _verified_research_path(Path(pin.path)) if pin is not None else None
        compressed_bytes = shard_value.get("compressed_bytes")
        if (
            pin is None
            or type(compressed_bytes) is not int
            or compressed_bytes < 0
            or not declared_shard_path.is_relative_to(publication_root)
            or pinned_shard_path != declared_shard_path
            or pin.bytes != compressed_bytes
            or pin.row_count != declared_rows
            or _plain_sha256(pin.sha256, f"{role_id}.sha256")
            != _plain_sha256(shard_value.get("compressed_sha256"), f"{role_id}.compressed_sha256")
            or pin.content_sha256 is None
            or _plain_sha256(pin.content_sha256, f"{role_id}.content_sha256")
            != _plain_sha256(shard_value.get("content_sha256"), f"{role_id}.content_sha256")
        ):
            raise CurrentRestatedResearchError("raw annual shard bytes differ from the verified loader pins")
        declared_total_rows += declared_rows
        if declared_total_rows > _MAX_CURRENT_RESTATED_RAW_ROWS:
            raise CurrentRestatedResearchError(
                "raw annual dataset declared row count exceeds its bound: "
                f"observed={declared_total_rows}; budget={_MAX_CURRENT_RESTATED_RAW_ROWS}"
            )
        validated_shards.append(
            (shard_value, year, pin, declared_shard_path, declared_rows)
        )
    if dataset_row_count is not None and dataset_row_count != declared_total_rows:
        raise CurrentRestatedResearchError(
            "raw dataset row_count differs from its annual shard declarations: "
            f"dataset={dataset_row_count}; shards={declared_total_rows}"
        )

    states: dict[date, dict[str, tuple[int | None, bool, bool, bool]]] = {}
    source_hashes: dict[date, str] = {}
    total_rows = 0
    total_content_bytes = 0
    maximum_row_bytes = 0
    maximum_compressed_bytes = 0
    benchmark_rows = 0
    shard_scan_rows: list[dict[str, Any]] = []
    for shard, year, pin, declared_shard_path, declared_rows in validated_shards:
        role_id = f"raw_shard_year_{year}"
        before = declared_shard_path.stat()
        if (
            not stat.S_ISREG(before.st_mode)
            or declared_shard_path.is_symlink()
            or before.st_size > _MAX_CURRENT_RESTATED_RAW_SHARD_BYTES
            or before.st_size != pin.bytes
            or before.st_mtime_ns != pin.mtime_ns
        ):
            raise CurrentRestatedResearchError("raw annual shard file identity differs from its pin")
        with declared_shard_path.open("rb") as shard_file:
            compressed = shard_file.read(_MAX_CURRENT_RESTATED_RAW_SHARD_BYTES + 1)
        if len(compressed) > _MAX_CURRENT_RESTATED_RAW_SHARD_BYTES:
            raise CurrentRestatedResearchError(
                "raw annual shard compressed bytes exceed their bound: "
                f"observed_at_least={len(compressed)}; "
                f"budget={_MAX_CURRENT_RESTATED_RAW_SHARD_BYTES}"
            )
        compressed_sha256 = _sha256_bytes(compressed)
        if compressed_sha256 != _plain_sha256(pin.sha256, f"{role_id}.sha256"):
            raise CurrentRestatedResearchError("raw annual shard compressed bytes changed")

        content_hash = sha256()
        shard_rows = 0
        shard_content_bytes = 0
        shard_maximum_row_bytes = 0
        shard_benchmark_rows = 0
        try:
            with gzip.GzipFile(fileobj=BytesIO(compressed), mode="rb") as stream:
                line_number = 0
                while True:
                    raw_line = stream.readline(_MAX_CURRENT_RESTATED_RAW_ROW_BYTES + 1)
                    if not raw_line:
                        break
                    line_number += 1
                    if len(raw_line) > _MAX_CURRENT_RESTATED_RAW_ROW_BYTES:
                        raise CurrentRestatedResearchError(
                            "raw annual shard JSONL row exceeds its byte bound: "
                            f"observed_at_least={len(raw_line)}; "
                            f"budget={_MAX_CURRENT_RESTATED_RAW_ROW_BYTES}"
                        )
                    shard_maximum_row_bytes = max(shard_maximum_row_bytes, len(raw_line))
                    maximum_row_bytes = max(maximum_row_bytes, len(raw_line))
                    shard_content_bytes += len(raw_line)
                    total_content_bytes += len(raw_line)
                    if total_content_bytes > _MAX_CURRENT_RESTATED_RAW_DATASET_CONTENT_BYTES:
                        raise CurrentRestatedResearchError(
                            "raw annual dataset decompressed bytes exceed its bound: "
                            f"observed_at_least={total_content_bytes}; "
                            f"budget={_MAX_CURRENT_RESTATED_RAW_DATASET_CONTENT_BYTES}"
                        )
                    content_hash.update(raw_line)
                    if not raw_line.strip():
                        raise CurrentRestatedResearchError("raw annual shard contains an empty row")
                    row = json.loads(raw_line.decode("utf-8"))
                    if not isinstance(row, dict):
                        raise CurrentRestatedResearchError("raw annual shard row is not an object")
                    shard_rows += 1
                    total_rows += 1
                    if total_rows > _MAX_CURRENT_RESTATED_RAW_ROWS:
                        raise CurrentRestatedResearchError(
                            "raw annual dataset actual row count exceeds its bound: "
                            f"observed={total_rows}; budget={_MAX_CURRENT_RESTATED_RAW_ROWS}"
                        )
                    event_date = _strict_date(cast(str, row.get("event_date")), "raw.event_date")
                    if event_date.year != year:
                        raise CurrentRestatedResearchError("raw annual shard contains a cross-year row")
                    if row.get("source_table") != "market_indices" or row.get("entity_id") != artifact.benchmark_entity_id:
                        continue
                    benchmark_rows += 1
                    shard_benchmark_rows += 1
                    if benchmark_rows > _MAX_CURRENT_RESTATED_BENCHMARK_ROWS:
                        raise CurrentRestatedResearchError(
                            "raw TAIEX benchmark row count exceeds its semantic bound: "
                            f"observed={benchmark_rows}; budget={_MAX_CURRENT_RESTATED_BENCHMARK_ROWS}"
                        )
                    if event_date in states:
                        raise CurrentRestatedResearchError("raw shards repeat a TAIEX source date")
                    if (
                        row.get("current_restated") is not True
                        or row.get("event_reference_only") is not True
                        or row.get("source_available_at") is not None
                        or row.get("historical_pit_eligible") is not False
                        or row.get("formal_training_eligible") is not False
                        or _plain_sha256(
                            row.get("source_context_bundle_sha256"),
                            "raw market source context SHA",
                        )
                        != _plain_sha256(
                            dataset.get("source_context_bundle_sha256"),
                            "raw dataset source context SHA",
                        )
                        or _aware_iso(cast(str, row.get("source_observed_at")), "raw market source_observed_at")
                        != artifact.source_observed_at
                    ):
                        raise CurrentRestatedResearchError("raw benchmark row clock or non-PIT identity is invalid")
                    current_available_at = _aware_iso(
                        cast(str, row.get("current_value_available_at")),
                        "raw market current_value_available_at",
                    )
                    if current_available_at > artifact.current_observation_freeze:
                        raise CurrentRestatedResearchError("raw benchmark value is after the Direct observation freeze")
                    row_source_hash = _plain_sha256(row.get("source_row_hash"), "raw market source-row hash")
                    row_state = _parse_current_restated_market_close_state(
                        row.get("values"),
                        market_close_ids=market_close_ids,
                        registry_by_source=registry_by_source,
                        raw_features=raw_features,
                        row_source_id=row.get("source_id"),
                    )
                    usable_values = [
                        value_int
                        for value_int, quality, stale, missing in row_state.values()
                        if value_int is not None and not quality and not stale and not missing
                    ]
                    if len(set(usable_values)) > 1:
                        raise CurrentRestatedResearchError("TAIEX close alias columns conflict")
                    states[event_date] = row_state
                    source_hashes[event_date] = _sha256_bytes(
                        _canonical_json_bytes(["sha256:" + row_source_hash])
                    )
        except CurrentRestatedResearchError:
            raise
        except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError, zlib.error) as exc:
            raise CurrentRestatedResearchError("verified raw annual shard cannot be decoded") from exc
        after = declared_shard_path.stat()
        if (
            (before.st_size, before.st_mtime_ns, before.st_ino)
            != (after.st_size, after.st_mtime_ns, after.st_ino)
            or shard_rows != pin.row_count
            or "sha256:" + content_hash.hexdigest() != pin.content_sha256
        ):
            raise CurrentRestatedResearchError(
                "raw annual shard changed during verified read or its row count differs: "
                f"year={year}; actual_rows={shard_rows}; declared_rows={declared_rows}"
            )
        maximum_compressed_bytes = max(maximum_compressed_bytes, len(compressed))
        shard_scan_rows.append(
            {
                "year": year,
                "declared_rows": declared_rows,
                "actual_rows": shard_rows,
                "compressed_bytes": len(compressed),
                "compressed_sha256": "sha256:" + compressed_sha256,
                "decompressed_bytes": shard_content_bytes,
                "content_sha256": "sha256:" + content_hash.hexdigest(),
                "maximum_jsonl_row_bytes": shard_maximum_row_bytes,
                "benchmark_rows": shard_benchmark_rows,
            }
        )

    if total_rows != declared_total_rows:
        raise CurrentRestatedResearchError(
            "raw annual dataset actual row count differs from its declarations: "
            f"actual={total_rows}; declared={declared_total_rows}"
        )

    expected_dates = tuple(calendar_dates)
    if (
        tuple(sorted(states)) != expected_dates
        or set(source_hashes) != set(expected_dates)
    ):
        raise CurrentRestatedResearchError(
            "verified TAIEX raw rows do not cover the complete pinned benchmark calendar"
        )
    raw_source_scan = {
        "schema_version": "current-restated-raw-source-scan.v1",
        "declared_row_count": declared_total_rows,
        "actual_row_count": total_rows,
        "dataset_manifest_declared_row_count": dataset_row_count,
        "benchmark_row_count": benchmark_rows,
        "decompressed_byte_count": total_content_bytes,
        "maximum_jsonl_row_bytes": _MAX_CURRENT_RESTATED_RAW_ROW_BYTES,
        "maximum_observed_jsonl_row_bytes": maximum_row_bytes,
        "maximum_compressed_shard_bytes": _MAX_CURRENT_RESTATED_RAW_SHARD_BYTES,
        "maximum_observed_compressed_shard_bytes": maximum_compressed_bytes,
        "maximum_decompressed_dataset_bytes": _MAX_CURRENT_RESTATED_RAW_DATASET_CONTENT_BYTES,
        "maximum_raw_rows": _MAX_CURRENT_RESTATED_RAW_ROWS,
        "maximum_benchmark_rows": _MAX_CURRENT_RESTATED_BENCHMARK_ROWS,
        "shards": shard_scan_rows,
    }
    if include_scan:
        return states, source_hashes, raw_source_scan
    return states, source_hashes


def _parse_current_restated_market_close_state(
    raw_values: Any,
    *,
    market_close_ids: Sequence[str],
    registry_by_source: Mapping[str, Any],
    raw_features: Mapping[str, Mapping[str, Any]],
    row_source_id: Any,
) -> dict[str, tuple[int | None, bool, bool, bool]]:
    """依 A 標籤欄位優先序解析收盤值與三種遮罩。"""

    if not isinstance(raw_values, list) or type(row_source_id) is not str or not row_source_id:
        raise CurrentRestatedResearchError("raw benchmark values or source identity is invalid")
    values_by_id: dict[str, Mapping[str, Any]] = {}
    for value in raw_values:
        if not isinstance(value, dict) or type(value.get("feature_id")) is not str:
            raise CurrentRestatedResearchError("raw benchmark feature row is malformed")
        feature_id = value["feature_id"]
        if feature_id in values_by_id:
            raise CurrentRestatedResearchError("raw benchmark feature row repeats an ID")
        values_by_id[feature_id] = value
    result: dict[str, tuple[int | None, bool, bool, bool]] = {}
    for stable_id in market_close_ids:
        direct_definition = registry_by_source.get(stable_id)
        if direct_definition is None:
            raise CurrentRestatedResearchError("Direct close registry definition is absent")
        source_feature_id = direct_definition.source_feature_id
        value = values_by_id.get(source_feature_id)
        raw_definition = raw_features.get(source_feature_id)
        if value is None or raw_definition is None:
            raise CurrentRestatedResearchError("raw benchmark row lacks its registered close feature")
        if (
            raw_definition.get("source_id") != row_source_id
            or raw_definition.get("table_name") != "market_indices"
            or raw_definition.get("unit") != "index_1e4"
            or raw_definition.get("scale") != 4
            or value.get("unit") != "index_1e4"
            or type(value.get("scale")) is not int
            or value.get("scale") != 4
        ):
            raise CurrentRestatedResearchError("raw benchmark close units differ from the pinned registry")
        value_int = value.get("value_int")
        missing = value.get("missing_mask")
        quality = value.get("quality_blocked_mask")
        stale = value.get("staleness_mask")
        if (
            (value_int is not None and (isinstance(value_int, bool) or not isinstance(value_int, int)))
            or any(type(flag) is not bool for flag in (missing, quality, stale))
            or (missing and value_int is not None)
            or (not missing and value_int is None)
            or (value_int is not None and not -(2**63) <= value_int < 2**63)
        ):
            raise CurrentRestatedResearchError("raw benchmark close value or mask is malformed")
        result[stable_id] = (
            cast(int | None, value_int),
            cast(bool, quality),
            cast(bool, stale),
            cast(bool, missing),
        )
    return result


def _build_current_restated_market_observations(
    *,
    calendar_dates: Sequence[date],
    state_by_date: Mapping[date, Mapping[str, tuple[int | None, bool, bool, bool]]],
    market_close_ids: Sequence[str],
    registry_by_source: Mapping[str, Any],
) -> tuple[list[Any], set[str], set[str], set[str]]:
    """把完整 benchmark 日期映射成 CORE19 市場路徑，不壓縮缺值交易日。"""

    from data_module.ml_historical_snapshot_provider import HistoricalIndexObservation

    expected_dates = tuple(calendar_dates)
    if (
        not expected_dates
        or tuple(sorted(set(expected_dates))) != expected_dates
        or tuple(sorted(state_by_date)) != expected_dates
    ):
        raise CurrentRestatedResearchError(
            "CORE19 market rows must cover the complete ordered benchmark calendar"
        )
    if not market_close_ids:
        raise CurrentRestatedResearchError("CORE19 market close registry is empty")
    rows: list[Any] = []
    quality_dates: set[str] = set()
    stale_dates: set[str] = set()
    unavailable_dates: set[str] = set()
    label_preferred_id = "benchmark/market_indices.收盤指數"
    if label_preferred_id not in market_close_ids:
        label_preferred_id = market_close_ids[0]
    for event_date in expected_dates:
        state = state_by_date[event_date]
        if any(stable_id not in state for stable_id in market_close_ids):
            raise CurrentRestatedResearchError("CORE19 market state lacks a registered close alias")
        candidate_values: dict[str, Decimal] = {}
        for stable_id in market_close_ids:
            definition = registry_by_source[stable_id]
            if definition.unit != "index_1e4" or definition.decimal_exponent != 4:
                raise CurrentRestatedResearchError(
                    "TAIEX close unit/scale differs from the research contract"
                )
            current = state[stable_id]
            if current[0] is not None and not current[1] and not current[2] and not current[3]:
                candidate_values[stable_id] = Decimal(current[0]).scaleb(-4)
        if len(set(candidate_values.values())) > 1:
            raise CurrentRestatedResearchError("TAIEX close candidate columns conflict")
        preferred_state = state[label_preferred_id]
        if preferred_state[1] or preferred_state[2]:
            raise CurrentRestatedResearchError(
                "label-preferred TAIEX close is quality-blocked or stale; alternate columns cannot bypass it"
            )
        if not candidate_values and any(
            state[stable_id][1] or state[stable_id][2]
            for stable_id in market_close_ids
        ):
            raise CurrentRestatedResearchError(
                "TAIEX close is quality-blocked or stale; no alternate value can bypass its mask"
            )
        chosen_state = preferred_state
        close_value = candidate_values.get(label_preferred_id)
        day_text = event_date.isoformat()
        if chosen_state[1]:
            quality_dates.add(day_text)
        if chosen_state[2]:
            stale_dates.add(day_text)
        if chosen_state[3] or chosen_state[0] is None:
            unavailable_dates.add(day_text)
        rows.append(
            HistoricalIndexObservation(
                index_name="market",
                trading_date=day_text,
                close_value=close_value,
            )
        )
    return rows, quality_dates, stale_dates, unavailable_dates


def _verify_current_restated_twd_turnover_contract(artifact: Any) -> None:
    """以已釘選 raw registry 驗證成交金額為 TWD，避免少乘或重複乘百。"""

    raw_path = _verified_research_path(Path(str(artifact.raw_dataset_manifest_path)))
    raw_digest = _plain_sha256(artifact.raw_dataset_manifest_bytes_sha256, "raw dataset manifest SHA")
    raw_bytes = raw_path.read_bytes()
    if sha256(raw_bytes).hexdigest() != raw_digest:
        raise CurrentRestatedResearchError("pinned raw dataset manifest actual bytes changed")
    try:
        raw_manifest = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentRestatedResearchError("pinned raw dataset manifest is invalid JSON") from exc
    features = raw_manifest.get("features") if isinstance(raw_manifest, dict) else None
    if not isinstance(features, list):
        raise CurrentRestatedResearchError("raw dataset feature registry is missing")
    matches = [
        item for item in features
        if isinstance(item, dict) and item.get("feature_id") == "daily_prices.成交金額"
    ]
    if len(matches) != 1:
        raise CurrentRestatedResearchError(
            "raw daily transaction amount lacks the verified TWD unit contract"
        )
    descriptor = matches[0]
    source_scale = descriptor.get("scale")
    source_denominator = descriptor.get("source_scale_denominator")
    if (
        descriptor.get("table_name") != "daily_prices"
        or descriptor.get("source_id") != "sqlite.daily_prices"
        or descriptor.get("column_name") != "成交金額"
        or descriptor.get("unit") != "TWD"
        or descriptor.get("unit_contract") != "tw-daily-price-transaction-amount-twd.v1"
        or type(source_scale) is not int
        or source_scale != 0
        or type(source_denominator) is not int
        or source_denominator != 10**source_scale
    ):
        raise CurrentRestatedResearchError(
            "raw daily transaction amount lacks the verified TWD unit contract"
        )


def _verify_current_restated_outcome_cost_contract(contract: Any) -> None:
    """核對 A 的 typed cost contract，避免把 net excess 當 gross label。"""

    from data_module.portfolio_ml_current_restated_outcome_store import (
        CurrentRestatedOutcomeCostContractV1,
    )

    expected = {
        "schema_version": "portfolio-ml-outcome-cost-contract.v1",
        "cost_unit": "basis_points",
        "buy_side_cost_bp": 25,
        "sell_side_cost_bp": 55,
        "total_round_trip_cost_bp": 80,
        "gross_stock_return_metric": "stock_return_bp",
        "gross_benchmark_return_metric": "benchmark_return_bp",
        "net_excess_metric": "benchmark_excess_return_bp",
        "net_excess_formula": (
            "stock_return_bp - benchmark_return_bp - buy_side_cost_bp - sell_side_cost_bp"
        ),
        "source": "data_module.portfolio_ml_dataset_assembler._build_label_spool",
    }
    if type(contract) is not CurrentRestatedOutcomeCostContractV1:
        raise CurrentRestatedResearchError("Direct outcome cost contract must be A's typed immutable value")
    actual = {
        field: getattr(contract, field)
        for field in expected
    }
    if actual != expected or any(type(actual[name]) is not int for name in (
        "buy_side_cost_bp", "sell_side_cost_bp", "total_round_trip_cost_bp"
    )):
        raise CurrentRestatedResearchError("Direct outcome cost semantics differ from the pinned 25/55/80 bp contract")


def _outcome_cost_contract_payload(contract: Any) -> dict[str, Any]:
    _verify_current_restated_outcome_cost_contract(contract)
    return {
        "schema_version": contract.schema_version,
        "cost_unit": contract.cost_unit,
        "buy_side_cost_bp": contract.buy_side_cost_bp,
        "sell_side_cost_bp": contract.sell_side_cost_bp,
        "total_round_trip_cost_bp": contract.total_round_trip_cost_bp,
        "gross_stock_return_metric": contract.gross_stock_return_metric,
        "gross_benchmark_return_metric": contract.gross_benchmark_return_metric,
        "net_excess_metric": contract.net_excess_metric,
        "net_excess_formula": contract.net_excess_formula,
        "source": contract.source,
    }


def _outcome_target_contract(cost_contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "current-restated-outcome-target.v1",
        "target_metric": "benchmark_excess_after_standard_80bp_cost",
        "source_metric": "benchmark_excess_return_bp",
        "gross_stock_metric": "stock_return_bp",
        "gross_benchmark_metric": "benchmark_return_bp",
        "cost_contract": dict(cost_contract),
    }


def _expected_outcome_cost_contract_payload() -> dict[str, Any]:
    return {
        "schema_version": "portfolio-ml-outcome-cost-contract.v1",
        "cost_unit": "basis_points",
        "buy_side_cost_bp": 25,
        "sell_side_cost_bp": 55,
        "total_round_trip_cost_bp": 80,
        "gross_stock_return_metric": "stock_return_bp",
        "gross_benchmark_return_metric": "benchmark_return_bp",
        "net_excess_metric": "benchmark_excess_return_bp",
        "net_excess_formula": (
            "stock_return_bp - benchmark_return_bp - buy_side_cost_bp - sell_side_cost_bp"
        ),
        "source": "data_module.portfolio_ml_dataset_assembler._build_label_spool",
    }


def _context_envelope_pin(
    context_file: VerifiedCurrentRestatedContextFile | None,
) -> dict[str, Any] | None:
    if context_file is None:
        return None
    return _verified_research_file(
        context_file.path, context_file.sha256, role="source_context_envelope"
    )


def _verify_direct_context_payload_binding(
    context_payload: Mapping[str, Any],
    context_file: VerifiedCurrentRestatedContextFile,
) -> None:
    if context_payload != dict(context_file.saved_payload):
        raise CurrentRestatedResearchError("source context envelope payload differs from the fit context")
    saved_dependencies = context_payload.get("revision_dependency_files")
    if not isinstance(saved_dependencies, list):
        raise CurrentRestatedResearchError("saved source dependency inventory is invalid")
    if _dependency_inventory_sha256(saved_dependencies) != context_file.revalidated_dependency_inventory_sha256:
        raise CurrentRestatedResearchError("source context physical dependency inventory changed")


def _dependency_inventory_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    """以不含擷取時鐘的實體檔案身分計算 namespace 依賴閉包。"""

    identity_fields = ("namespace", "role_id", "path", "bytes", "mtime_ns", "sha256")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise CurrentRestatedResearchError("source dependency inventory row is invalid")
        namespace = row.get("namespace")
        role_id = row.get("role_id")
        raw_path = row.get("path")
        byte_count = row.get("bytes")
        mtime_ns = row.get("mtime_ns")
        if (
            type(namespace) is not str
            or not namespace
            or type(role_id) is not str
            or not role_id
            or type(raw_path) is not str
            or not raw_path
            or type(byte_count) is not int
            or byte_count < 0
            or type(mtime_ns) is not int
            or mtime_ns < 0
        ):
            raise CurrentRestatedResearchError(
                f"source dependency inventory row {index} has invalid identity fields"
            )
        path = Path(raw_path)
        try:
            if path.is_symlink() or not path.is_file() or path.resolve(strict=True) != path:
                raise CurrentRestatedResearchError("source dependency inventory contains a non-regular path")
        except OSError as exc:
            raise CurrentRestatedResearchError("source dependency inventory path cannot be verified") from exc
        key = (namespace, role_id, raw_path)
        if key in seen:
            raise CurrentRestatedResearchError("source dependency inventory has duplicate identities")
        seen.add(key)
        normalized.append(
            {
                "namespace": namespace,
                "role_id": role_id,
                "path": raw_path,
                "bytes": byte_count,
                "mtime_ns": mtime_ns,
                "sha256": _plain_sha256(row.get("sha256"), "source dependency file SHA"),
            }
        )
    if not normalized:
        raise CurrentRestatedResearchError("source dependency inventory is empty")
    normalized.sort(key=lambda item: (item["namespace"], item["role_id"], item["path"]))
    return _sha256_bytes(_canonical_json_bytes(normalized))


def _namespace_inventory_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    """重驗 snapshot namespace 的完整實體檔案閉包。"""

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise CurrentRestatedResearchError("source namespace inventory row is invalid")
        raw_path = row.get("path")
        byte_count = row.get("bytes")
        mtime_ns = row.get("mtime_ns")
        if (
            type(raw_path) is not str
            or not raw_path
            or type(byte_count) is not int
            or byte_count < 0
            or type(mtime_ns) is not int
            or mtime_ns < 0
        ):
            raise CurrentRestatedResearchError(
                f"source namespace inventory row {index} has invalid identity fields"
            )
        path = Path(raw_path)
        try:
            if path.is_symlink() or not path.is_file() or path.resolve(strict=True) != path:
                raise CurrentRestatedResearchError("source namespace inventory contains a non-regular path")
            stat_result = path.stat()
            actual_sha = _sha256_file(path)
        except OSError as exc:
            raise CurrentRestatedResearchError("source namespace inventory path cannot be verified") from exc
        expected_sha = _plain_sha256(row.get("sha256"), "source namespace file SHA")
        if (
            stat_result.st_size != byte_count
            or stat_result.st_mtime_ns != mtime_ns
            or actual_sha != expected_sha
        ):
            raise CurrentRestatedResearchError("source namespace file differs from its immutable pin")
        if raw_path in seen:
            raise CurrentRestatedResearchError("source namespace inventory has duplicate paths")
        seen.add(raw_path)
        normalized.append(
            {"path": raw_path, "bytes": byte_count, "mtime_ns": mtime_ns, "sha256": expected_sha}
        )
    if not normalized:
        raise CurrentRestatedResearchError("source namespace inventory is empty")
    normalized.sort(key=lambda item: item["path"].casefold())
    return _sha256_bytes(_canonical_json_bytes(normalized))


def _current_vector_bridge_manifest(
    bridge: VerifiedCurrentRestatedBVectorBridge | None,
) -> dict[str, Any] | None:
    if bridge is None:
        return None
    payload = _plain_json(bridge.payload, "current vector bridge")
    actual_sha = _sha256_bytes(_canonical_json_bytes(payload))
    if actual_sha != _plain_sha256(bridge.payload_sha256, "current vector bridge SHA"):
        raise CurrentRestatedResearchError("current vector bridge payload SHA mismatch")
    if payload.get("status") != "verified_exact_b7_source_match_core19_derived":
        raise CurrentRestatedResearchError("current vector bridge status is not verified")
    return {
        "schema_version": "current-restated-b7-to-core19-bridge.v1",
        "sha256": actual_sha,
        "payload": payload,
    }


def _stable_current_vector_bridge_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    """移除每次重算才會改變的時計雜湊，保留所有來源與數值證據。"""

    payload = _plain_json(value, "current vector bridge revalidation")
    if (
        payload.get("schema_version") != "current-restated-b7-to-core19-bridge.v1"
        or payload.get("status") != "verified_exact_b7_source_match_core19_derived"
        or payload.get("mode") != "source_row_outcome_research"
        or payload.get("historical_pit_eligible") is not False
        or payload.get("formal_training_eligible") is not False
        or payload.get("model_training_performed") is not False
        or payload.get("production_action_allowed") is not False
    ):
        raise CurrentRestatedResearchError("B-to-CORE19 bridge has an invalid research-only contract")
    _strict_date(str(payload.get("event_date")), "current vector bridge event_date")
    for name in (
        "b_consumption_receipt_sha256",
        "b_candidate_manifest_sha256",
        "b_adapted_manifest_sha256",
        "b_feature_registry_sha256",
        "direct_outcome_manifest_sha256",
        "direct_raw_publication_manifest_sha256",
        "direct_raw_dataset_manifest_sha256",
        "direct_feature_registry_sha256",
        "event_date_calendar_sha256",
    ):
        _plain_sha256(payload.get(name), f"current vector bridge {name}")
    for name in ("source_observed_at", "direct_artifact_available_at", "b_current_observation_freeze", "core19_derived_at"):
        _aware_iso(str(payload.get(name)), f"current vector bridge {name}")
    if "raw_source_scan" in payload:
        _verify_current_restated_raw_source_scan(payload.get("raw_source_scan"))
    symbols = payload.get("symbols")
    rows = payload.get("rows")
    if (
        not isinstance(symbols, list)
        or not symbols
        or any(type(symbol) is not str or not symbol.isalnum() for symbol in symbols)
        or len(set(symbols)) != len(symbols)
        or not isinstance(rows, list)
        or len(rows) != len(symbols)
    ):
        raise CurrentRestatedResearchError("B-to-CORE19 bridge has an invalid source-row inventory")
    row_symbols: list[str] = []
    for index, row_value in enumerate(rows):
        row = _mapping(row_value, f"current vector bridge rows[{index}]")
        symbol = row.get("symbol")
        if type(symbol) is not str or symbol not in symbols or symbol in row_symbols:
            raise CurrentRestatedResearchError("B-to-CORE19 bridge has duplicate or unexpected symbols")
        row_symbols.append(symbol)
        if row.get("event_date") != payload.get("event_date"):
            raise CurrentRestatedResearchError("B-to-CORE19 bridge row date differs from its cohort")
        for name in (
            "b_row_identity_sha256",
            "direct_source_row_identity_sha256",
            "core19_vector_sha256",
            "core19_numeric_vector_sha256",
        ):
            _plain_sha256(row.get(name), f"current vector bridge rows[{index}].{name}")
        _aware_iso(str(row.get("b_available_at")), f"current vector bridge rows[{index}].b_available_at")
        if type(row.get("direct_sample_id")) is not str or not row.get("direct_sample_id"):
            raise CurrentRestatedResearchError("B-to-CORE19 bridge row has no Direct sample identity")
        comparisons = row.get("comparisons")
        if not isinstance(comparisons, list) or not comparisons:
            raise CurrentRestatedResearchError("B-to-CORE19 bridge row has no exact B/Direct comparisons")
        for comparison_index, comparison_value in enumerate(comparisons):
            comparison = _mapping(
                comparison_value,
                f"current vector bridge rows[{index}].comparisons[{comparison_index}]",
            )
            if comparison.get("exact_decimal_match") is not True:
                raise CurrentRestatedResearchError("B-to-CORE19 bridge contains a nonmatching source value")
            _plain_sha256(
                comparison.get("b_source_value_hash"),
                f"current vector bridge rows[{index}].comparisons[{comparison_index}].b_source_value_hash",
            )
        masks = [
            row.get("core19_missing_mask"),
            row.get("core19_quality_blocked_mask"),
            row.get("core19_staleness_mask"),
        ]
        if any(
            not isinstance(mask, list) or any(type(item) is not bool for item in mask)
            for mask in masks
        ) or len({len(cast(list[Any], mask)) for mask in masks}) != 1:
            raise CurrentRestatedResearchError("B-to-CORE19 bridge row masks are invalid")
    if row_symbols != symbols:
        raise CurrentRestatedResearchError("B-to-CORE19 bridge row order differs from its symbol cohort")

    stable = dict(payload)
    stable.pop("core19_derived_at")
    stable_rows: list[dict[str, Any]] = []
    for row_value in rows:
        stable_row = dict(cast(Mapping[str, Any], row_value))
        stable_row.pop("core19_vector_sha256")
        stable_rows.append(stable_row)
    stable["rows"] = stable_rows
    return stable


def _verify_current_restated_raw_source_scan(value: Any) -> None:
    scan = _mapping(value, "current vector bridge raw_source_scan")
    if scan.get("schema_version") != "current-restated-raw-source-scan.v1":
        raise CurrentRestatedResearchError("raw-source scan diagnostic schema is invalid")
    expected_budgets = {
        "maximum_jsonl_row_bytes": _MAX_CURRENT_RESTATED_RAW_ROW_BYTES,
        "maximum_compressed_shard_bytes": _MAX_CURRENT_RESTATED_RAW_SHARD_BYTES,
        "maximum_decompressed_dataset_bytes": _MAX_CURRENT_RESTATED_RAW_DATASET_CONTENT_BYTES,
        "maximum_raw_rows": _MAX_CURRENT_RESTATED_RAW_ROWS,
        "maximum_benchmark_rows": _MAX_CURRENT_RESTATED_BENCHMARK_ROWS,
    }
    for name, expected in expected_budgets.items():
        if type(scan.get(name)) is not int or scan.get(name) != expected:
            raise CurrentRestatedResearchError(
                f"raw-source scan resource budget is invalid: {name}"
            )
    integer_fields = (
        "declared_row_count",
        "actual_row_count",
        "benchmark_row_count",
        "decompressed_byte_count",
        "maximum_observed_jsonl_row_bytes",
        "maximum_observed_compressed_shard_bytes",
    )
    for name in integer_fields:
        item = scan.get(name)
        if type(item) is not int or item < 0:
            raise CurrentRestatedResearchError(
                f"raw-source scan resource count is invalid: {name}"
            )
    manifest_rows = scan.get("dataset_manifest_declared_row_count")
    if type(manifest_rows) is not int or manifest_rows < 0:
        raise CurrentRestatedResearchError(
            "raw-source scan dataset manifest row count is invalid"
        )
    actual_rows = cast(int, scan["actual_row_count"])
    declared_rows = cast(int, scan["declared_row_count"])
    benchmark_rows = cast(int, scan["benchmark_row_count"])
    decompressed_bytes = cast(int, scan["decompressed_byte_count"])
    maximum_row_bytes = cast(int, scan["maximum_observed_jsonl_row_bytes"])
    maximum_compressed_bytes = cast(int, scan["maximum_observed_compressed_shard_bytes"])
    if (
        actual_rows != declared_rows
        or manifest_rows != declared_rows
        or actual_rows > _MAX_CURRENT_RESTATED_RAW_ROWS
        or benchmark_rows > _MAX_CURRENT_RESTATED_BENCHMARK_ROWS
        or decompressed_bytes > _MAX_CURRENT_RESTATED_RAW_DATASET_CONTENT_BYTES
        or maximum_row_bytes > _MAX_CURRENT_RESTATED_RAW_ROW_BYTES
        or maximum_compressed_bytes > _MAX_CURRENT_RESTATED_RAW_SHARD_BYTES
    ):
        raise CurrentRestatedResearchError(
            "raw-source scan resource metrics exceed their declared bounds or disagree"
        )
    shards = scan.get("shards")
    if not isinstance(shards, list) or not shards:
        raise CurrentRestatedResearchError("raw-source scan shard metrics are absent")
    seen_years: set[int] = set()
    sum_rows = 0
    sum_benchmark_rows = 0
    sum_decompressed_bytes = 0
    max_shard_row_bytes = 0
    max_shard_compressed_bytes = 0
    for index, shard_value in enumerate(shards):
        shard = _mapping(shard_value, f"raw_source_scan.shards[{index}]")
        year = shard.get("year")
        if type(year) is not int or year in seen_years:
            raise CurrentRestatedResearchError("raw-source scan has invalid or duplicate shard year")
        seen_years.add(year)
        for name in (
            "declared_rows",
            "actual_rows",
            "compressed_bytes",
            "decompressed_bytes",
            "maximum_jsonl_row_bytes",
            "benchmark_rows",
        ):
            item = shard.get(name)
            if type(item) is not int or item < 0:
                raise CurrentRestatedResearchError(
                    f"raw-source scan shard metric is invalid: {name}"
                )
        shard_declared_rows = cast(int, shard["declared_rows"])
        shard_actual_rows = cast(int, shard["actual_rows"])
        shard_compressed_bytes = cast(int, shard["compressed_bytes"])
        shard_decompressed_bytes = cast(int, shard["decompressed_bytes"])
        shard_max_row_bytes = cast(int, shard["maximum_jsonl_row_bytes"])
        shard_benchmark_rows = cast(int, shard["benchmark_rows"])
        if (
            shard_declared_rows != shard_actual_rows
            or shard_actual_rows > _MAX_CURRENT_RESTATED_RAW_ROWS
            or shard_compressed_bytes > _MAX_CURRENT_RESTATED_RAW_SHARD_BYTES
            or shard_decompressed_bytes > _MAX_CURRENT_RESTATED_RAW_DATASET_CONTENT_BYTES
            or shard_max_row_bytes > _MAX_CURRENT_RESTATED_RAW_ROW_BYTES
            or shard_benchmark_rows > _MAX_CURRENT_RESTATED_BENCHMARK_ROWS
        ):
            raise CurrentRestatedResearchError(
                "raw-source scan shard metrics exceed their declared bounds or disagree"
            )
        _plain_sha256(shard.get("compressed_sha256"), "raw-source scan compressed shard SHA")
        _plain_sha256(shard.get("content_sha256"), "raw-source scan content SHA")
        sum_rows += shard_actual_rows
        sum_benchmark_rows += shard_benchmark_rows
        sum_decompressed_bytes += shard_decompressed_bytes
        max_shard_row_bytes = max(max_shard_row_bytes, shard_max_row_bytes)
        max_shard_compressed_bytes = max(max_shard_compressed_bytes, shard_compressed_bytes)
    if (
        sum_rows != actual_rows
        or sum_benchmark_rows != benchmark_rows
        or sum_decompressed_bytes != decompressed_bytes
        or max_shard_row_bytes != maximum_row_bytes
        or max_shard_compressed_bytes != maximum_compressed_bytes
    ):
        raise CurrentRestatedResearchError("raw-source scan aggregate metrics differ from its shard rows")


def _verify_current_vector_bridge_revalidation(
    saved_bridge: Mapping[str, Any],
    refreshed_bridge: VerifiedCurrentRestatedBVectorBridge,
) -> str:
    """核對模型建置與每次 sidecar 的穩定數值／來源證據。"""

    saved_payload = _mapping(saved_bridge.get("payload"), "model.current_vector_bridge.payload")
    saved_sha = _plain_sha256(saved_bridge.get("sha256"), "model.current_vector_bridge.sha256")
    if (
        saved_bridge.get("schema_version") != "current-restated-b7-to-core19-bridge.v1"
        or _sha256_bytes(_canonical_json_bytes(saved_payload)) != saved_sha
    ):
        raise CurrentRestatedResearchError("saved B-to-CORE19 full bridge proof is inconsistent")
    refreshed_manifest = _current_vector_bridge_manifest(refreshed_bridge)
    if refreshed_manifest is None:
        raise CurrentRestatedResearchError("fresh B-to-CORE19 bridge proof is missing")
    saved_stable_sha = _sha256_bytes(
        _canonical_json_bytes(_stable_current_vector_bridge_payload(saved_payload))
    )
    refreshed_stable_sha = _sha256_bytes(
        _canonical_json_bytes(
            _stable_current_vector_bridge_payload(cast(Mapping[str, Any], refreshed_manifest["payload"]))
        )
    )
    if saved_stable_sha != refreshed_stable_sha:
        raise CurrentRestatedResearchError(
            "fresh B-to-CORE19 source rows or numeric vectors differ from the model's training bridge"
        )
    return saved_sha


def _verify_current_vector_bridge(
    bridge: VerifiedCurrentRestatedBVectorBridge,
    fit_audit: Mapping[str, Any],
) -> None:
    bridge_manifest = _current_vector_bridge_manifest(bridge)
    if bridge_manifest is None:
        raise CurrentRestatedResearchError("B-to-CORE19 bridge is missing")
    if fit_audit.get("current_vector_bridge_sha256") != bridge_manifest["sha256"]:
        raise CurrentRestatedResearchError("fit audit does not bind the exact B-to-CORE19 bridge")
    payload = cast(Mapping[str, Any], bridge_manifest["payload"])
    if payload.get("model_training_performed") is not False or payload.get("historical_pit_eligible") is not False:
        raise CurrentRestatedResearchError("B-to-CORE19 bridge overstates training or PIT eligibility")
    if set(bridge.vectors_by_symbol) != set(payload.get("symbols", ())):
        raise CurrentRestatedResearchError("B-to-CORE19 vector symbols differ from the bridge receipt")


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _aware_iso(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field} must be an aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include an explicit timezone")
    return parsed


def _strict_date(value: str, field: str) -> date:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be ISO YYYY-MM-DD")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be normalized ISO YYYY-MM-DD")
    return parsed


@dataclass(frozen=True, slots=True)
class CurrentRestatedFeature:
    """一個 scaled-int feature；原始 availability unknown 保留為 None。"""

    feature_id: str
    value_int: int | None
    scale: int
    observed: bool
    event_at: str
    source_available_at: str | None
    source_observed_at: str
    current_value_available_at: str
    source_value_hash: str
    source_value_hash_semantics: str
    stale: bool = False

    def __post_init__(self) -> None:
        if not self.feature_id.strip():
            raise ValueError("feature_id is required")
        if isinstance(self.scale, bool) or not isinstance(self.scale, int):
            raise TypeError("scale must be a decimal exponent integer")
        if not 0 <= self.scale <= 18:
            raise ValueError("scale exponent is outside 0..18")
        if not isinstance(self.observed, bool):
            raise TypeError("observed must be bool")
        if not isinstance(self.stale, bool):
            raise TypeError("stale must be bool")
        if self.observed:
            if isinstance(self.value_int, bool) or not isinstance(self.value_int, int):
                raise TypeError("observed value_int must be a strict integer")
            if not -(2**63) <= self.value_int < 2**63:
                raise ValueError("value_int is outside the signed i64 range")
        elif self.value_int is not None:
            raise ValueError("missing value must not carry a scaled integer")
        _aware_iso(self.source_observed_at, "source_observed_at")
        _aware_iso(self.current_value_available_at, "current_value_available_at")
        if self.source_available_at is not None:
            _aware_iso(self.source_available_at, "source_available_at")
        if not self.source_value_hash.startswith("sha256:"):
            raise ValueError("source_value_hash must be a pinned SHA-256")
        if not self.source_value_hash_semantics:
            raise ValueError("source_value_hash_semantics is required")


@dataclass(frozen=True, slots=True)
class CurrentRestatedOutcomeLabel:
    """一個直接儲存的 benchmark excess label；未觀測時不補零。"""

    horizon_trading_days: int
    horizon_end_date: str
    available_at: str | None
    benchmark_excess_return_bp: int | None
    observed: bool
    source_available_at: str | None
    source_observed_at: str
    label_value_hash: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.horizon_trading_days, bool)
            or not isinstance(self.horizon_trading_days, int)
            or self.horizon_trading_days <= 0
        ):
            raise TypeError("horizon_trading_days must be a positive integer")
        _strict_date(self.horizon_end_date, "horizon_end_date")
        if not isinstance(self.observed, bool):
            raise TypeError("label observed must be bool")
        if self.observed:
            if isinstance(self.benchmark_excess_return_bp, bool) or not isinstance(
                self.benchmark_excess_return_bp, int
            ):
                raise TypeError("observed benchmark excess must be an integer bp value")
            if not -(2**31) <= self.benchmark_excess_return_bp < 2**31:
                raise ValueError("benchmark excess label is outside signed i32 range")
            if self.available_at is None:
                raise ValueError("observed outcome label needs an availability clock")
            available = _aware_iso(self.available_at, "label.available_at")
            if available.date() < _strict_date(self.horizon_end_date, "horizon_end_date"):
                raise ValueError("outcome label is available before its horizon end")
        elif self.benchmark_excess_return_bp is not None:
            raise ValueError("missing outcome label must not carry a numeric target")
        if self.available_at is not None:
            _aware_iso(self.available_at, "label.available_at")
        if self.source_available_at is not None:
            _aware_iso(self.source_available_at, "label.source_available_at")
        _aware_iso(self.source_observed_at, "label.source_observed_at")
        if not self.label_value_hash.startswith("sha256:"):
            raise ValueError("label_value_hash must be a pinned SHA-256")


@dataclass(frozen=True, slots=True)
class CurrentRestatedResearchRow:
    """研究事件列；event date 與實際 current-value clock 分開保存。"""

    row_id: str
    symbol: str
    event_date: str
    event_at: str
    features: tuple[CurrentRestatedFeature, ...]
    missing_mask: tuple[str, ...]
    quality_blocked_mask: tuple[str, ...]
    source_observed_at: str
    staleness_mask: tuple[str, ...] = ()
    historical_pit_eligible: bool = False

    def __post_init__(self) -> None:
        if not self.row_id.strip() or not self.symbol.strip():
            raise ValueError("row_id and symbol are required")
        _strict_date(self.event_date, "event_date")
        _aware_iso(self.source_observed_at, "source_observed_at")
        if self.historical_pit_eligible is not False:
            raise ValueError("current-restated rows must remain non-PIT")
        if len({feature.feature_id for feature in self.features}) != len(self.features):
            raise ValueError("row feature IDs must be unique")
        expected_missing = {feature.feature_id for feature in self.features if not feature.observed}
        if set(self.missing_mask) != expected_missing:
            raise ValueError("row missing mask disagrees with scaled-int values")
        if len(set(self.missing_mask)) != len(self.missing_mask):
            raise ValueError("row missing mask has duplicates")
        if len(set(self.quality_blocked_mask)) != len(self.quality_blocked_mask):
            raise ValueError("row quality-blocked mask has duplicates")
        expected_stale = {feature.feature_id for feature in self.features if feature.stale}
        if set(self.staleness_mask) != expected_stale:
            raise ValueError("row staleness mask disagrees with feature metadata")
        if len(set(self.staleness_mask)) != len(self.staleness_mask):
            raise ValueError("staleness mask has duplicates")


@dataclass(frozen=True, slots=True)
class CurrentRestatedResearchSample:
    row: CurrentRestatedResearchRow
    horizon_labels: tuple[CurrentRestatedOutcomeLabel, ...]
    dataset_temporality: str = "current_restated_research"
    historical_pit: bool = False

    def __post_init__(self) -> None:
        if self.dataset_temporality != "current_restated_research":
            raise ValueError("sample temporality is not the current-restated research contract")
        if self.historical_pit is not False:
            raise ValueError("current-restated sample must not claim historical PIT")
        horizons = tuple(label.horizon_trading_days for label in self.horizon_labels)
        if not horizons or len(horizons) != len(set(horizons)):
            raise ValueError("sample outcome horizons must be non-empty and unique")


@dataclass(frozen=True, slots=True)
class CurrentRestatedInputFilePin:
    """Direct input byte pin emitted by the verified numeric-store loader."""

    role: str
    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedCurrentRestatedContextFile:
    """跨 parent/child 傳遞的原始 context bytes 與本次重新驗證結果。"""

    path: Path
    sha256: str
    context: Any
    saved_payload: Mapping[str, Any]
    revalidated_at: str
    revalidated_dependency_bundle_sha256: str
    revalidated_dependency_inventory_sha256: str


@dataclass(frozen=True, slots=True)
class CurrentRestatedSavedModel:
    manifest_path: Path
    manifest_sha256: str
    model_bundle_sha256: str
    model_keys: tuple[str, ...]
    target_contract: Mapping[str, Any]
    current_vector_paths: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class CurrentRestatedResearchSidecarResult:
    """舊排程入口可回傳的已驗 source-row research terminal。"""

    status: str
    receipt_path: Path
    receipt_sha256: str
    binding_sha256: str
    sample_cohort_sha256: str
    core19_numeric_vector_sha256_by_symbol: Mapping[str, str]
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class LoadedCurrentRestatedModel:
    manifest_path: Path
    manifest_sha256: str
    manifest: Mapping[str, Any]
    models: Mapping[str, Any]


def capture_current_restated_training_code_pins() -> Mapping[str, str]:
    """Capture the source files whose exact implementation fits and reads models."""

    root = Path(__file__).resolve().parents[1]
    relatives = (
        "ml_module/current_restated_research_bridge.py",
        "ml_module/allocation_training_service.py",
        "ml_module/historical_feature_builder.py",
        "ml_module/feature_registry.py",
        "ml_module/model_artifact_loader.py",
        "data_module/ml_daily_price_revision_gate.py",
        "data_module/portfolio_ml_current_restated_outcome_store.py",
        "data_module/ml_pit_year_shard_exporter.py",
        "data_module/portfolio_ml_dataset_assembler.py",
        "data_module/ml_historical_snapshot_provider.py",
        "data_module/ml_price_availability_contract.py",
        "data_module/portfolio_ml_direct_numeric_store.py",
        "data_module/ml_research_direct_ooc_adapter.py",
        "scripts/train_bounded_restated_research.py",
    )
    pins: dict[str, str] = {}
    for relative in relatives:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise CurrentRestatedResearchError(f"research code pin is missing: {relative}")
        pins[relative] = _sha256_file(path)
    return MappingProxyType(pins)


@dataclass(frozen=True, slots=True)
class CurrentRestatedOutcomeFitRun:
    """單次 verified Direct→CORE19→pure-fit/save 的完整研究結果。"""

    prepared: PreparedCurrentRestatedCore19Dataset
    fit_result: RestatedOutcomeOnlyFitResult
    saved_model: CurrentRestatedSavedModel
    vector_bridge: VerifiedCurrentRestatedBVectorBridge


def _require_unoccupied_research_model_output(output_directory: Path) -> Path:
    """Resolve a research model output slot and require create-only absence."""

    candidate = Path(output_directory)
    if candidate.is_symlink():
        raise CurrentRestatedResearchError(
            f"research model output must not be a symlink: {candidate}"
        )
    output_dir = resolve_ml_research_output_path(candidate, access="write")
    if output_dir.exists():
        raise CurrentRestatedResearchError(
            f"research model output already exists: {output_dir}"
        )
    return output_dir


def fit_and_save_verified_current_restated_core19_model(
    *,
    direct_artifact: object,
    source_context_file: VerifiedCurrentRestatedContextFile,
    b_artifact: object,
    b_consumption_receipt_path: Path,
    expected_b_consumption_receipt_sha256: str,
    expected_b_candidate_manifest_sha256: str,
    expected_b_adapted_manifest_sha256: str,
    expected_b_feature_registry_sha256: str,
    current_symbols: Sequence[str],
    current_event_date: str,
    output_directory: Path,
    actual_invocation: Sequence[str],
    fit_progress: dict[str, bool] | None = None,
) -> CurrentRestatedOutcomeFitRun:
    """以已驗 A/B 輸入執行 CORE19 純 outcome fit，並存入隔離 research root。"""

    from data_module.ml_daily_price_revision_gate import VerifiedCurrentRestatedSourceContext
    from data_module.portfolio_ml_current_restated_outcome_store import (
        VerifiedCurrentRestatedOutcomeArtifact,
    )

    # Reject an occupied create-only model slot before preparing or fitting the
    # research model. The final writer repeats this check immediately before
    # creating the leaf to close the fit-time race.
    output_directory = _require_unoccupied_research_model_output(output_directory)

    if type(direct_artifact) is not VerifiedCurrentRestatedOutcomeArtifact:
        raise CurrentRestatedResearchError("fit requires A's public verified outcome artifact")
    if type(source_context_file) is not VerifiedCurrentRestatedContextFile:
        raise CurrentRestatedResearchError("fit requires a revalidated shared source-context envelope")
    if type(source_context_file.context) is not VerifiedCurrentRestatedSourceContext:
        raise CurrentRestatedResearchError("shared source context is not A's verified type")
    _verify_direct_context_binding(direct_artifact, source_context_file)
    prepared = prepare_verified_current_restated_core19_dataset(direct_artifact)
    _require_complete_current_restated_event_calendar(
        prepared.event_date_calendar,
        expected_direct_calendar_sha256=direct_artifact.event_date_calendar_sha256,
    )
    vector_bridge = verify_b_current_vector_against_core19(
        direct_artifact=direct_artifact,
        prepared=prepared,
        b_artifact=b_artifact,
        b_consumption_receipt_path=b_consumption_receipt_path,
        expected_b_consumption_receipt_sha256=expected_b_consumption_receipt_sha256,
        expected_b_candidate_manifest_sha256=expected_b_candidate_manifest_sha256,
        expected_b_adapted_manifest_sha256=expected_b_adapted_manifest_sha256,
        expected_b_feature_registry_sha256=expected_b_feature_registry_sha256,
        symbols=current_symbols,
        event_date=current_event_date,
    )
    cutoff = datetime.now(timezone.utc)
    if direct_artifact.artifact_available_at > cutoff:
        raise CurrentRestatedResearchError("Direct artifact completion is later than the actual fit clock")
    if _aware_iso(source_context_file.revalidated_at, "source_context.revalidated_at") > cutoff:
        raise CurrentRestatedResearchError("source context was revalidated after the actual fit clock")
    _verify_direct_context_binding(direct_artifact, source_context_file)
    code_pins_before = capture_current_restated_training_code_pins()
    if fit_progress is not None:
        fit_progress["started"] = True
    fit_result = AllocationTrainingService(
        random_state=42,
        hgb_max_iter=60,
        ridge_alpha=1,
    ).fit_current_restated_outcome_only(
        samples=cast(Sequence[Any], prepared.samples),
        feature_packs=prepared.feature_packs,
        folds=prepared.folds,
        training_as_of=cutoff.isoformat(),
        dataset_manifest_file_hash=(
            "sha256:"
            + _plain_sha256(
                direct_artifact.artifact_receipt_bytes_sha256,
                "Direct outcome manifest SHA for typed fitter input",
            )
        ),
        event_date_calendar=prepared.event_date_calendar,
        horizons=(5,),
        algorithms=("ridge_logistic",),
        minimum_train_dates=125,
        minimum_test_dates=63,
        minimum_purge_days=60,
        minimum_embargo_days=5,
    )
    if fit_progress is not None:
        fit_progress["completed"] = True
    fit_audit = _bind_verified_current_restated_fold_qualification(
        fit_result.audit,
        folds=prepared.folds,
        event_date_calendar=prepared.event_date_calendar,
        direct_manifest_sha256=direct_artifact.artifact_receipt_bytes_sha256,
        direct_event_date_calendar_sha256=direct_artifact.event_date_calendar_sha256,
    )
    outcome_cost_contract = dict(prepared.outcome_cost_contract)
    target_contract = _outcome_target_contract(outcome_cost_contract)
    fit_result = replace(
        fit_result,
        audit={
            **fit_audit,
            "target_contract": target_contract,
            "outcome_cost_contract": outcome_cost_contract,
            "direct_feature_registry_sha256": _plain_sha256(
                direct_artifact.feature_registry_sha256, "Direct feature registry SHA"
            ),
            "core19_feature_registry_sha256": _sha256_bytes(
                _canonical_json_bytes([dict(item) for item in prepared.feature_registry])
            ),
            "current_vector_bridge_sha256": vector_bridge.payload_sha256,
            "source_context_envelope_sha256": source_context_file.sha256,
            "fit_selection": {
                "profile": "core19_current_restated_outcome_only.v1",
                "horizons": [5],
                "algorithms": ["ridge_logistic"],
                "random_state": 42,
                "ridge_alpha": 1,
                "hgb_max_iter": 60,
                "hgb_max_iter_applicability": "not_used_by_ridge_logistic_profile",
            },
        },
    )
    input_pins = _verified_direct_artifact_input_pins(direct_artifact)
    input_pins = (
        *input_pins,
        CurrentRestatedInputFilePin(
            role="source_context_envelope",
            path=str(source_context_file.path),
            bytes=source_context_file.path.stat().st_size,
            sha256=source_context_file.sha256,
        ),
        CurrentRestatedInputFilePin(
            role="b_consumption_receipt",
            path=str(b_consumption_receipt_path),
            bytes=b_consumption_receipt_path.stat().st_size,
            sha256=expected_b_consumption_receipt_sha256,
        ),
    )
    b_receipt_pin = input_pins[-1]
    b_receipt_file = _verified_research_file(
        Path(b_receipt_pin.path), expected_b_consumption_receipt_sha256,
        role="b_consumption_receipt",
    )
    input_pins = (*input_pins[:-1], CurrentRestatedInputFilePin(
        role="b_consumption_receipt",
        path=b_receipt_file["path"],
        bytes=b_receipt_file["bytes"],
        sha256=b_receipt_file["sha256"],
    ))
    saved = save_current_restated_outcome_model(
        fit_result=fit_result,
        feature_registry=prepared.feature_registry,
        feature_packs=prepared.feature_packs,
        source_context=source_context_file.context,
        source_context_file=source_context_file,
        direct_manifest_path=Path(direct_artifact.artifact_receipt_path),
        expected_direct_manifest_sha256=direct_artifact.artifact_receipt_bytes_sha256,
        direct_receipt_path=Path(direct_artifact.artifact_receipt_path),
        expected_direct_receipt_sha256=direct_artifact.artifact_receipt_bytes_sha256,
        input_file_pins=input_pins,
        fit_code_pins_before=code_pins_before,
        training_as_of=cutoff.isoformat(),
        output_directory=output_directory,
        actual_invocation=actual_invocation,
        current_vector_bridge=vector_bridge,
    )
    return CurrentRestatedOutcomeFitRun(
        prepared=prepared,
        fit_result=fit_result,
        saved_model=saved,
        vector_bridge=vector_bridge,
    )


def _require_complete_current_restated_event_calendar(
    event_date_calendar: Sequence[str],
    *,
    expected_direct_calendar_sha256: str,
) -> tuple[tuple[str, ...], str]:
    """Validate the full pinned event calendar before fitting or qualification."""

    calendar = tuple(event_date_calendar)
    if len(calendar) < _CURRENT_RESTATED_MINIMUM_CALENDAR_SESSIONS:
        raise CurrentRestatedResearchError(
            "current-restated fit requires at least 905 verified event-date sessions"
        )
    parsed_calendar = tuple(_strict_date(value, "event_date_calendar") for value in calendar)
    if parsed_calendar != tuple(sorted(set(parsed_calendar))):
        raise CurrentRestatedResearchError("verified event-date calendar must be ordered and unique")
    calendar_sha256 = _sha256_bytes(_canonical_json_bytes(list(calendar)))
    if _plain_sha256(
        expected_direct_calendar_sha256,
        "Direct event-date calendar SHA",
    ) != calendar_sha256:
        raise CurrentRestatedResearchError(
            "complete event-date calendar differs from the verified Direct manifest"
        )
    return calendar, calendar_sha256


def _bind_verified_current_restated_fold_qualification(
    audit_value: Mapping[str, Any],
    *,
    folds: Sequence[PurgedWalkForwardFold],
    event_date_calendar: Sequence[str],
    direct_manifest_sha256: str,
    direct_event_date_calendar_sha256: str,
) -> dict[str, Any]:
    """將 public Direct loader 的完整 calendar 與實際 fold 邊界寫入 audit。"""

    calendar, calendar_sha256 = _require_complete_current_restated_event_calendar(
        event_date_calendar,
        expected_direct_calendar_sha256=direct_event_date_calendar_sha256,
    )
    calendar_index = {value: index for index, value in enumerate(calendar)}
    direct_sha = _plain_sha256(direct_manifest_sha256, "Direct manifest SHA")
    audit = _plain_json(audit_value, "fit audit")
    raw_fold_rows = audit.get("folds")
    if not isinstance(raw_fold_rows, list):
        raise CurrentRestatedResearchError("fit audit fold rows are missing")
    audit_by_fold: dict[str, list[Mapping[str, Any]]] = {}
    for item in raw_fold_rows:
        if not isinstance(item, Mapping) or not isinstance(item.get("fold_id"), str):
            raise CurrentRestatedResearchError("fit audit contains an invalid fold row")
        audit_by_fold.setdefault(str(item["fold_id"]), []).append(item)

    qualified: list[dict[str, Any]] = []
    used_test_indices: set[int] = set()
    previous_test_end_index: int | None = None
    ordered_folds = tuple(sorted(folds, key=lambda item: (item.test_start, item.fold_id)))
    if len(ordered_folds) < 4 or len({item.fold_id for item in ordered_folds}) != len(ordered_folds):
        raise CurrentRestatedResearchError("at least four unique verified Direct folds are required")
    for fold in ordered_folds:
        start = _strict_date(fold.test_start, "fold.test_start").isoformat()
        end = _strict_date(fold.test_end, "fold.test_end").isoformat()
        if start not in calendar_index or end not in calendar_index:
            raise CurrentRestatedResearchError("fold bounds are outside the verified full calendar")
        train_dates = sorted({row.decision_date for row in fold.train_rows})
        test_dates = sorted({row.decision_date for row in fold.test_rows})
        train_indices = sorted({calendar_index[value] for value in train_dates if value in calendar_index})
        test_indices = sorted({calendar_index[value] for value in test_dates if value in calendar_index})
        if (
            not train_indices
            or not test_indices
            or len(train_indices) != len(train_dates)
            or len(test_indices) != len(test_dates)
            or test_indices[0] != calendar_index[start]
            or test_indices[-1] != calendar_index[end]
            or len(test_indices) < 63
            or used_test_indices.intersection(test_indices)
        ):
            raise CurrentRestatedResearchError("verified fold event dates do not match the full calendar")
        used_test_indices.update(test_indices)
        actual_purge = test_indices[0] - train_indices[-1] - 1
        if actual_purge < 60:
            raise CurrentRestatedResearchError("verified fold calendar has fewer than 60 actual purge sessions")
        if previous_test_end_index is None:
            if fold.embargo_days < 5:
                raise CurrentRestatedResearchError("first verified Direct fold weakens its 5-session embargo")
            actual_embargo = fold.embargo_days
            embargo_basis = "public_direct_loader_verified_initial_fold_policy"
        else:
            actual_embargo = test_indices[0] - previous_test_end_index - 1
            embargo_basis = "complete_verified_calendar_between_test_windows"
            if actual_embargo < 5:
                raise CurrentRestatedResearchError("verified fold calendar has fewer than 5 actual embargo sessions")
        previous_test_end_index = test_indices[-1]
        latest_train_label_end = max(
            _strict_date(row.label_end_date, "train.label_end_date")
            for row in fold.train_rows
        )
        if latest_train_label_end >= _strict_date(start, "fold.test_start"):
            raise CurrentRestatedResearchError("verified training label reaches the test start")
        matching_rows = audit_by_fold.get(fold.fold_id, [])
        if not matching_rows:
            raise CurrentRestatedResearchError("fit audit omits a verified Direct fold")
        train_counts = {item.get("training_mature_date_count") for item in matching_rows}
        test_counts = {item.get("test_date_count") for item in matching_rows}
        if (
            len(train_counts) != 1
            or len(test_counts) != 1
            or any(type(value) is not int for value in (*train_counts, *test_counts))
        ):
            raise CurrentRestatedResearchError("fold model audits disagree on mature train/test counts")
        mature_train_dates = cast(int, next(iter(train_counts)))
        test_date_count = cast(int, next(iter(test_counts)))
        if mature_train_dates < 125 or test_date_count < 63:
            raise CurrentRestatedResearchError("verified fold is below the mature 125/63 date minimum")
        if mature_train_dates > len(train_indices) or test_date_count != len(test_indices):
            raise CurrentRestatedResearchError("fit audit date counts disagree with Direct fold indices")
        qualified.append(
            {
                "fold_id": fold.fold_id,
                "test_start": start,
                "test_end": end,
                "train_date_indices": train_indices,
                "test_date_indices": test_indices,
                "mature_train_date_count": mature_train_dates,
                "test_date_count": test_date_count,
                "actual_purge_trading_days": actual_purge,
                "actual_embargo_trading_days": actual_embargo,
                "embargo_verification_basis": embargo_basis,
                "max_train_label_end_date": latest_train_label_end.isoformat(),
            }
        )
    return {
        **audit,
        "fit_selection": {
            "profile": "core19_current_restated_outcome_only.v1",
            "horizons": [5],
            "algorithms": ["ridge_logistic"],
            "random_state": 42,
            "ridge_alpha": 1,
            "hgb_max_iter": 60,
            "hgb_max_iter_applicability": "not_used_by_ridge_logistic_profile",
        },
        "current_restated_verified_fold_qualification": {
            "schema_version": _CURRENT_RESTATED_FOLD_CALENDAR_V2,
            "direct_manifest_sha256": direct_sha,
            "direct_event_date_calendar_sha256": calendar_sha256,
            "calendar_scope": "complete_verified_direct_event_date_calendar",
            "minimum_event_date_calendar_count": _CURRENT_RESTATED_MINIMUM_CALENDAR_SESSIONS,
            "event_date_calendar_count": len(calendar),
            "event_date_calendar_sha256": calendar_sha256,
            "minimum_mature_train_dates": 125,
            "minimum_test_dates": 63,
            "minimum_purge_trading_days": 60,
            "minimum_embargo_trading_days": 5,
            "minimum_qualified_fold_count": 4,
            "folds": qualified,
        },
    }


def _verify_direct_context_binding(
    direct_artifact: Any,
    context_file: VerifiedCurrentRestatedContextFile,
) -> None:
    context = context_file.context
    identities = (
        ("source_database_sha256", direct_artifact.source_database_sha256),
        ("snapshot_database_sha256", direct_artifact.snapshot_database_sha256),
        ("snapshot_receipt_sha256", direct_artifact.snapshot_receipt_sha256),
    )
    for field, direct_value in identities:
        context_value = _plain_sha256(getattr(context, field, None), f"source_context.{field}")
        if context_value != _plain_sha256(direct_value, f"Direct.{field}"):
            raise CurrentRestatedResearchError(f"Direct artifact and strict context differ for {field}")
    if context.source_observed_at != direct_artifact.source_observed_at:
        raise CurrentRestatedResearchError("Direct artifact and strict context source observation clocks differ")
    if (
        Path(str(context.source_database_path)).resolve(strict=False)
        != Path(str(direct_artifact.source_database_path)).resolve(strict=False)
        or Path(str(context.snapshot_database_path)).resolve(strict=False)
        != Path(str(direct_artifact.snapshot_database_path)).resolve(strict=False)
        or Path(str(context.snapshot_receipt_path)).resolve(strict=False)
        != Path(str(direct_artifact.snapshot_receipt_path)).resolve(strict=False)
    ):
        raise CurrentRestatedResearchError("Direct artifact source paths differ from the revalidated context")

    manifest_path = _verified_research_path(Path(str(direct_artifact.artifact_receipt_path)))
    if direct_artifact.status != "current_restated_outcome_numeric_ready":
        raise CurrentRestatedResearchError("Direct artifact is not a verified numeric-ready artifact")
    manifest_before = manifest_path.stat()
    manifest_pin = _verified_research_file(
        manifest_path,
        str(direct_artifact.artifact_receipt_bytes_sha256),
        role="verified Direct outcome manifest",
    )
    manifest_after = manifest_path.stat()
    if (
        manifest_pin["bytes"] != manifest_before.st_size
        or manifest_after.st_size != manifest_before.st_size
        or manifest_after.st_mtime_ns != manifest_before.st_mtime_ns
    ):
        raise CurrentRestatedResearchError("verified Direct manifest changed while being hashed")
    proof_bytes = getattr(direct_artifact, "source_context_revalidation_json", None)
    if not isinstance(proof_bytes, bytes) or not proof_bytes or len(proof_bytes) > 4 * 1024 * 1024:
        raise CurrentRestatedResearchError("verified Direct source-context proof is missing or exceeds 4 MiB")
    proof_sha = _plain_sha256(
        getattr(direct_artifact, "source_context_revalidation_sha256", None),
        "Direct source-context proof SHA",
    )
    if _sha256_bytes(proof_bytes) != proof_sha:
        raise CurrentRestatedResearchError("verified Direct source-context proof bytes differ from its SHA pin")
    try:
        direct_context = json.loads(proof_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentRestatedResearchError("verified Direct source-context proof is invalid UTF-8 JSON") from exc
    if (
        not isinstance(direct_context, dict)
        or _canonical_json_bytes(direct_context) != proof_bytes
    ):
        raise CurrentRestatedResearchError("verified Direct source-context proof is not canonical JSON")
    direct_bundle_sha = _plain_sha256(
        direct_artifact.revision_dependency_bundle_sha256,
        "Direct.revision_dependency_bundle_sha256",
    )
    if (
        _plain_sha256(
            direct_context.get("revision_dependency_bundle_sha256"),
            "Direct lineage revision dependency bundle",
        )
        != direct_bundle_sha
        or _sha256_bytes(_canonical_json_bytes(direct_context))
        != proof_sha
    ):
        raise CurrentRestatedResearchError("Direct verified proof does not bind its original context lineage")

    saved_payload = context_file.saved_payload
    direct_context_fields = (
        "source_database_path",
        "source_database_sha256",
        "source_wal_path",
        "source_wal_sha256",
        "source_wal_present",
        "snapshot_database_path",
        "snapshot_database_sha256",
        "snapshot_receipt_path",
        "snapshot_receipt_sha256",
        "source_observed_at",
        "source_generation",
        "revision_namespace_bundle_sha256",
    )
    for field in direct_context_fields:
        if saved_payload.get(field) != direct_context.get(field):
            raise CurrentRestatedResearchError(
                f"shared context does not retain Direct's original lineage field {field}"
            )
    direct_decision_at = _aware_iso(
        str(direct_context.get("decision_at")), "Direct.source_context.decision_at"
    )
    shared_decision_at = _aware_iso(
        str(saved_payload.get("decision_at")), "shared source_context.decision_at"
    )
    if direct_decision_at.astimezone(ZoneInfo("Asia/Taipei")).date() != shared_decision_at.astimezone(
        ZoneInfo("Asia/Taipei")
    ).date():
        raise CurrentRestatedResearchError("Direct and fresh source context use different Taiwan cutoff dates")
    direct_evidence = _mapping(
        direct_context.get("source_revision_evidence"),
        "Direct.source_revision_evidence",
    )
    if _plain_sha256(
        direct_evidence.get("digest_sha256"), "Direct source revision evidence SHA"
    ) != _plain_sha256(
        saved_payload.get("source_revision_evidence_sha256"),
        "shared source revision evidence SHA",
    ):
        raise CurrentRestatedResearchError("shared context source revision evidence differs from Direct")
    if (
        direct_evidence.get("cutoff_date")
        != saved_payload.get("source_revision_evidence_cutoff_date")
        or direct_evidence.get("schema_version")
        != saved_payload.get("source_revision_evidence_schema_version")
        or direct_evidence.get("scope_id")
        != saved_payload.get("source_revision_evidence_scope_id")
    ):
        raise CurrentRestatedResearchError("shared context typed revision-evidence cutoff differs from Direct")

    direct_dependency_rows = direct_context.get("revision_dependency_files")
    saved_dependency_rows = saved_payload.get("revision_dependency_files")
    fresh_dependency_rows = _source_context_plain_payload(context).get("revision_dependency_files")
    if (
        not isinstance(direct_dependency_rows, list)
        or not isinstance(saved_dependency_rows, list)
        or not isinstance(fresh_dependency_rows, list)
        or _dependency_inventory_sha256(direct_dependency_rows)
        != context_file.revalidated_dependency_inventory_sha256
        or _dependency_inventory_sha256(saved_dependency_rows)
        != context_file.revalidated_dependency_inventory_sha256
        or _dependency_inventory_sha256(fresh_dependency_rows)
        != context_file.revalidated_dependency_inventory_sha256
    ):
        raise CurrentRestatedResearchError(
            "Direct original and fresh source-context physical dependency closures differ"
        )
    direct_namespace_rows = direct_context.get("revision_namespace_files")
    saved_namespace_rows = saved_payload.get("revision_namespace_files")
    fresh_namespace_rows = _source_context_plain_payload(context).get("revision_namespace_files")
    if (
        not isinstance(direct_namespace_rows, list)
        or not isinstance(saved_namespace_rows, list)
        or not isinstance(fresh_namespace_rows, list)
        or _namespace_inventory_sha256(direct_namespace_rows)
        != _namespace_inventory_sha256(saved_namespace_rows)
        or _namespace_inventory_sha256(direct_namespace_rows)
        != _namespace_inventory_sha256(fresh_namespace_rows)
    ):
        raise CurrentRestatedResearchError(
            "Direct and fresh source-context snapshot namespace inventories differ"
        )


def _verified_direct_artifact_input_pins(artifact: Any) -> tuple[CurrentRestatedInputFilePin, ...]:
    pins: list[CurrentRestatedInputFilePin] = []
    seen: dict[str, tuple[int, str]] = {}

    def add(role: str, raw_path: str, expected_bytes: int, expected_sha: str) -> None:
        path = _verified_research_path(Path(raw_path))
        actual_bytes = path.stat().st_size
        actual_sha = _sha256_file(path)
        if actual_bytes != expected_bytes or actual_sha != _plain_sha256(expected_sha, f"{role}.sha256"):
            raise CurrentRestatedResearchError(f"Direct input artifact changed: {role}")
        key = str(path)
        prior = seen.get(key)
        if prior is not None:
            if prior != (actual_bytes, actual_sha):
                raise CurrentRestatedResearchError("same Direct input path has conflicting byte pins")
            return
        seen[key] = (actual_bytes, actual_sha)
        pins.append(CurrentRestatedInputFilePin(role=role, path=key, bytes=actual_bytes, sha256=actual_sha))

    add(
        "raw_publication_manifest",
        artifact.raw_publication_manifest_path,
        Path(artifact.raw_publication_manifest_path).stat().st_size,
        artifact.raw_publication_manifest_bytes_sha256,
    )
    add(
        "raw_dataset_manifest",
        artifact.raw_dataset_manifest_path,
        Path(artifact.raw_dataset_manifest_path).stat().st_size,
        artifact.raw_dataset_manifest_bytes_sha256,
    )
    for item in artifact.raw_shard_pins:
        add(f"raw_shard:{item.role_id}", item.path, item.bytes, item.sha256)
    for item in artifact.array_pins:
        add(f"direct_array:{item.name}", item.path, item.bytes, item.sha256)
    return tuple(pins)


def save_current_restated_outcome_model(
    *,
    fit_result: RestatedOutcomeOnlyFitResult,
    feature_registry: Sequence[Mapping[str, Any]],
    feature_packs: Sequence[FeaturePackDefinition],
    source_context: object,
    source_context_file: VerifiedCurrentRestatedContextFile | None = None,
    current_vector_bridge: VerifiedCurrentRestatedBVectorBridge | None = None,
    direct_manifest_path: Path,
    expected_direct_manifest_sha256: str,
    direct_receipt_path: Path,
    expected_direct_receipt_sha256: str,
    input_file_pins: Sequence[CurrentRestatedInputFilePin],
    fit_code_pins_before: Mapping[str, str],
    training_as_of: str,
    output_directory: Path,
    actual_invocation: Sequence[str],
) -> CurrentRestatedSavedModel:
    """Save a verified current-restated base outcome model, manifest last.

    ``source_context`` must be returned by A's strict source-context loader and
    ``input_file_pins`` by the verified Direct numeric-artifact loader. The
    saved profile is research-only and cannot represent portfolio allocation.
    """

    context_payload = _verified_context_payload(source_context, training_as_of)
    cutoff = _aware_iso(training_as_of, "training_as_of")
    audit = _plain_json(fit_result.audit, "fit audit")
    if audit.get("schema_version") != "current-restated-outcome-only-fit-audit.v1":
        raise CurrentRestatedResearchError("fit result has an unexpected audit schema")
    if audit.get("status") != "verified_base_outcome_only" or audit.get("historical_pit") is not False:
        raise CurrentRestatedResearchError("fit result is not a non-PIT base-outcome fit")
    if audit.get("formal_oos_allowed") is not False or audit.get("production_action_allowed") is not False:
        raise CurrentRestatedResearchError("fit result claims a forbidden production capability")
    if _aware_iso(str(audit.get("training_as_of")), "fit audit training_as_of") != cutoff:
        raise CurrentRestatedResearchError("fit audit cutoff differs from the supplied fit freeze")
    if audit.get("full_allocation_status") != "blocked_full_allocation_teacher_unavailable":
        raise CurrentRestatedResearchError("fit result did not preserve the missing-teacher block")
    if audit.get("target_heads") != ["benchmark_excess_return_bp"]:
        raise CurrentRestatedResearchError("fit result has unsupported target heads")
    outcome_cost_contract = audit.get("outcome_cost_contract")
    target_contract = audit.get("target_contract")
    if not isinstance(outcome_cost_contract, dict) or not isinstance(target_contract, dict):
        raise CurrentRestatedResearchError("fit result lacks the explicit outcome cost/target contract")
    expected_target_contract = _outcome_target_contract(outcome_cost_contract)
    if outcome_cost_contract != _expected_outcome_cost_contract_payload():
        raise CurrentRestatedResearchError("fit result outcome cost contract differs from A's verified 25/55/80 bp terms")
    if target_contract != expected_target_contract:
        raise CurrentRestatedResearchError("fit result target is not the after-standard-80bp benchmark excess")
    if source_context_file is not None:
        if type(source_context_file) is not VerifiedCurrentRestatedContextFile:
            raise CurrentRestatedResearchError("shared context file does not have the verified envelope type")
        if source_context_file.context is not source_context:
            raise CurrentRestatedResearchError("saved source context differs from the revalidated envelope context")
        _verify_direct_context_payload_binding(context_payload, source_context_file)
    if current_vector_bridge is not None:
        _verify_current_vector_bridge(current_vector_bridge, fit_result.audit)

    canonical_packs = tuple(sorted(feature_packs, key=lambda pack: pack.pack_id))
    if not canonical_packs:
        raise CurrentRestatedResearchError("model feature packs are required")
    pack_ids = [pack.pack_id for pack in canonical_packs]
    ordered_ids = [feature_id for pack in canonical_packs for feature_id in pack.feature_ids]
    if len(pack_ids) != len(set(pack_ids)) or len(ordered_ids) != len(set(ordered_ids)):
        raise CurrentRestatedResearchError("model feature packs contain duplicate IDs")
    normalized_registry = tuple(_plain_json(item, "feature registry entry") for item in feature_registry)
    registry_ids: list[str] = []
    scales: dict[str, int] = {}
    for entry in normalized_registry:
        if not isinstance(entry, dict):
            raise CurrentRestatedResearchError("feature registry entries must be objects")
        feature_id = entry.get("feature_id")
        scale = entry.get("scale")
        if not isinstance(feature_id, str) or not feature_id.strip():
            raise CurrentRestatedResearchError("feature registry ID is invalid")
        if isinstance(scale, bool) or not isinstance(scale, int) or not 0 <= scale <= 18:
            raise CurrentRestatedResearchError("feature registry scale must be an integer exponent in 0..18")
        if feature_id in scales:
            raise CurrentRestatedResearchError("feature registry IDs must be unique")
        registry_ids.append(feature_id)
        scales[feature_id] = scale
    if registry_ids != ordered_ids:
        raise CurrentRestatedResearchError("ordered Direct registry differs from fit feature packs")
    if audit.get("feature_scale_exponents") != scales:
        raise CurrentRestatedResearchError("fit scale map differs from the verified feature registry")
    audit_packs = audit.get("feature_ids_by_pack")
    expected_packs = [
        {"pack_id": pack.pack_id, "feature_ids": list(pack.feature_ids)}
        for pack in canonical_packs
    ]
    if audit_packs != expected_packs:
        raise CurrentRestatedResearchError("fit audit feature packs differ from save request")

    direct_manifest_pin = _verified_research_file(
        direct_manifest_path,
        expected_direct_manifest_sha256,
        role="direct_store_manifest",
    )
    if _plain_sha256(
        audit.get("dataset_manifest_file_hash"), "fit_audit.dataset_manifest_file_hash"
    ) != direct_manifest_pin["sha256"]:
        raise CurrentRestatedResearchError(
            "fit dataset manifest differs from the exact Direct manifest bytes supplied to save"
        )
    qualification_for_pin = _mapping(
        audit.get("current_restated_verified_fold_qualification"),
        "fit_audit.current_restated_verified_fold_qualification",
    )
    if qualification_for_pin.get("schema_version") == _CURRENT_RESTATED_FOLD_CALENDAR_V2:
        direct_manifest_pin["event_date_calendar_sha256"] = _plain_sha256(
            qualification_for_pin.get("direct_event_date_calendar_sha256"),
            "fit_audit.direct_event_date_calendar_sha256",
        )
    _validate_verified_current_restated_fold_qualification(
        audit,
        expected_direct_manifest_sha256=direct_manifest_pin["sha256"],
        expected_direct_event_date_calendar_sha256=cast(
            str | None, direct_manifest_pin.get("event_date_calendar_sha256")
        ),
    )
    direct_receipt_pin = _verified_research_file(
        direct_receipt_path,
        expected_direct_receipt_sha256,
        role="direct_store_receipt",
    )
    extra_pins = tuple(_verify_input_file_pin(pin) for pin in input_file_pins)
    pins_by_path: dict[str, tuple[int, str]] = {}
    for pin in (direct_manifest_pin, direct_receipt_pin, *extra_pins):
        identity = (int(pin["bytes"]), str(pin["sha256"]))
        prior = pins_by_path.get(str(pin["path"]))
        if prior is not None and prior != identity:
            raise CurrentRestatedResearchError("one input path is bound to conflicting Direct byte pins")
        pins_by_path[str(pin["path"])] = identity
    extras_by_role = {str(item["role"]): item for item in extra_pins}
    if source_context_file is not None:
        context_pin = extras_by_role.get("source_context_envelope")
        if (
            context_pin is None
            or context_pin["sha256"] != source_context_file.sha256
            or context_pin["path"] != str(source_context_file.path.resolve(strict=True))
        ):
            raise CurrentRestatedResearchError("fit input pins omit the exact verified source-context envelope")
    if current_vector_bridge is not None:
        bridge_payload = cast(Mapping[str, Any], _current_vector_bridge_manifest(current_vector_bridge))["payload"]
        b_pin = extras_by_role.get("b_consumption_receipt")
        if (
            b_pin is None
            or b_pin["sha256"] != bridge_payload.get("b_consumption_receipt_sha256")
            or b_pin["path"] != bridge_payload.get("b_consumption_receipt_path")
            or b_pin["bytes"] != bridge_payload.get("b_consumption_receipt_bytes")
        ):
            raise CurrentRestatedResearchError("fit input pins omit the exact B receipt used by the current vector bridge")
        if bridge_payload.get("direct_outcome_manifest_sha256") != direct_manifest_pin["sha256"]:
            raise CurrentRestatedResearchError("B bridge was derived from a different Direct outcome manifest")
        raw_publication_pin = extras_by_role.get("raw_publication_manifest")
        raw_dataset_pin = extras_by_role.get("raw_dataset_manifest")
        if (
            raw_publication_pin is None
            or raw_dataset_pin is None
            or bridge_payload.get("direct_raw_publication_manifest_sha256") != raw_publication_pin["sha256"]
            or bridge_payload.get("direct_raw_dataset_manifest_sha256") != raw_dataset_pin["sha256"]
        ):
            raise CurrentRestatedResearchError("B bridge raw-source pins differ from the fitted Direct artifact")

    code_pins_before = _normalize_code_pins(fit_code_pins_before)
    code_pins_after = dict(capture_current_restated_training_code_pins())
    if dict(code_pins_before) != code_pins_after:
        raise CurrentRestatedResearchError("C/A training source code changed during fit")

    models = dict(fit_result.models)
    model_keys = tuple(sorted(models))
    if not model_keys:
        raise CurrentRestatedResearchError("fit result contains no final model")
    model_shapes = _validate_model_bundle(models, model_keys, canonical_packs)
    model_stream = BytesIO()
    joblib.dump(models, model_stream, compress=3)
    model_bytes = model_stream.getvalue()
    if not model_bytes:
        raise CurrentRestatedResearchError("serialized model bundle is empty")

    registry_bytes = _canonical_json_bytes(normalized_registry)
    audit_bytes = _canonical_json_bytes(audit)
    generated_at = datetime.now(timezone.utc)
    output_dir = _require_unoccupied_research_model_output(output_directory)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=False, exist_ok=False)
    manifest_path = output_dir / "manifest.json"
    vector_descriptors: list[dict[str, Any]] = []
    try:
        _write_create_only(output_dir / "models.joblib", model_bytes)
        _write_create_only(output_dir / "feature_registry.json", registry_bytes)
        _write_create_only(output_dir / "fit_audit.json", audit_bytes)
        if current_vector_bridge is not None:
            vectors_dir = output_dir / "current_vectors"
            vectors_dir.mkdir()
            for symbol in sorted(current_vector_bridge.vectors_by_symbol):
                row = current_vector_bridge.vectors_by_symbol[symbol]
                vector_payload = _current_restated_row_payload(row)
                vector_bytes = _canonical_json_bytes(vector_payload)
                vector_path = vectors_dir / f"{symbol}.json"
                _write_create_only(vector_path, vector_bytes)
                vector_descriptors.append(
                    {
                        "symbol": symbol,
                        "event_date": row.event_date,
                        "filename": f"current_vectors/{symbol}.json",
                        "bytes": len(vector_bytes),
                        "sha256": sha256(vector_bytes).hexdigest(),
                        "core19_vector_sha256": sha256(
                            _canonical_json_bytes(_current_restated_row_payload(row))
                        ).hexdigest(),
                        "core19_numeric_vector_sha256": sha256(
                            _canonical_json_bytes(_core19_numeric_vector_payload(row))
                        ).hexdigest(),
                    }
                )
        manifest = {
            "schema_version": "ml-current-restated-base-outcome-model.v1",
            "status": "verified_base_outcome_only",
            "profile": "benchmark_excess_regression_only",
            "dataset_temporality": "current_restated_research",
            "historical_pit": False,
            "historical_pit_eligible": False,
            "formal_training_eligible": False,
            "formal_oos_allowed": False,
            "full_allocation_status": "blocked_full_allocation_teacher_unavailable",
            "production_alpha_bp": 0,
            "production_action_allowed": False,
            "direct_source": {
                "manifest": direct_manifest_pin,
                "receipt": direct_receipt_pin,
                "artifacts": list(extra_pins),
            },
            "source_context": context_payload,
            "source_context_envelope": _context_envelope_pin(source_context_file) if source_context_file else None,
            "current_vector_bridge": _current_vector_bridge_manifest(current_vector_bridge) if current_vector_bridge else None,
            "current_vectors": vector_descriptors,
            "training_as_of": cutoff.isoformat(),
            "fit_completed_at": generated_at.isoformat(),
            "model_available_at": generated_at.isoformat(),
            "fit_execution": {
                "process_id": os.getpid(),
                "argv": list(actual_invocation),
                "fit_cutoff": cutoff.isoformat(),
                "started_or_frozen_at": cutoff.isoformat(),
            },
            "model_bundle": {
                "filename": "models.joblib",
                "bytes": len(model_bytes),
                "sha256": sha256(model_bytes).hexdigest(),
                "model_keys": list(model_keys),
                "shapes": model_shapes,
                "estimator_classes": _declared_estimator_classes(model_keys),
            },
            "feature_registry": {
                "filename": "feature_registry.json",
                "bytes": len(registry_bytes),
                "sha256": sha256(registry_bytes).hexdigest(),
                "sha256_semantics": "canonical_ordered_registry_bytes",
                "feature_ids": registry_ids,
                "scale_exponents": scales,
                "entries": list(normalized_registry),
            },
            "feature_packs": [
                {"pack_id": pack.pack_id, "feature_ids": list(pack.feature_ids)}
                for pack in canonical_packs
            ],
            "mask_policy": {
                "missing_or_quality_blocked_values": "NaN at model boundary",
                "hist_gradient_boosting_mask": "one means missing or quality blocked",
                "quality_blocked_values_never_fit": True,
            },
            "fit_audit": {
                "filename": "fit_audit.json",
                "bytes": len(audit_bytes),
                "sha256": sha256(audit_bytes).hexdigest(),
            },
            "target_heads": list(audit["target_heads"]),
            "target_contract": target_contract,
            "outcome_cost_contract": outcome_cost_contract,
            "unfitted_heads": list(audit["unfitted_heads"]),
            "code_pins": code_pins_after,
            "runtime_versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "scikit_learn": sklearn.__version__,
                "joblib": joblib.__version__,
            },
            "actual_invocation": list(actual_invocation),
        }
        manifest_bytes = _canonical_json_bytes(manifest)
        _write_create_only(manifest_path, manifest_bytes)
        _fsync_directory(output_dir)
    except Exception as exc:
        failure = {
            "schema_version": "ml-current-restated-model-failure-receipt.v1",
            "status": "failed_incomplete_research_artifact",
            "error_type": type(exc).__name__,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "output_directory": str(output_dir),
            "manifest_present": manifest_path.exists(),
        }
        try:
            _write_create_only(output_dir / "failed_receipt.json", _canonical_json_bytes(failure))
        except OSError:
            pass
        raise CurrentRestatedResearchError(
            f"research model save failed; incomplete output retained at {output_dir}: {exc}"
        ) from exc
    return CurrentRestatedSavedModel(
        manifest_path=manifest_path,
        manifest_sha256=sha256(manifest_bytes).hexdigest(),
        model_bundle_sha256=sha256(model_bytes).hexdigest(),
        model_keys=model_keys,
        target_contract=MappingProxyType(dict(target_contract)),
        current_vector_paths=tuple(
            output_dir / str(item["filename"]) for item in vector_descriptors
        ),
    )


def load_current_restated_outcome_model(
    manifest_path: Path,
    *,
    expected_manifest_sha256: str,
    expected_model_bundle_sha256: str,
) -> LoadedCurrentRestatedModel:
    """Load a controlled research artifact from externally pinned exact bytes.

    The caller must obtain both digests from a trusted training receipt or
    another out-of-band trusted channel. The model digest is required because
    a digest written only inside the manifest cannot establish pickle trust.
    All JSON context, clocks, code/runtime pins, registry and declared estimator
    profile checks run before deserialization. The verified in-memory bytes are
    then passed through the repository's same-private-buffer loader contract.
    """

    path = resolve_ml_research_output_path(manifest_path, access="read")
    if path.name != "manifest.json" or path.is_symlink() or not path.is_file():
        raise CurrentRestatedResearchError("research model manifest is not a regular manifest.json")
    failed_receipt = path.parent / "failed_receipt.json"
    if failed_receipt.exists() or failed_receipt.is_symlink():
        raise CurrentRestatedResearchError("research model directory contains a failed receipt")
    raw_manifest = path.read_bytes()
    actual_manifest_sha = sha256(raw_manifest).hexdigest()
    if actual_manifest_sha != _plain_sha256(expected_manifest_sha256, "expected_manifest_sha256"):
        raise CurrentRestatedResearchError("research model manifest actual-byte SHA-256 mismatch")
    trusted_model_sha = _plain_sha256(expected_model_bundle_sha256, "expected_model_bundle_sha256")
    try:
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentRestatedResearchError("research model manifest is invalid JSON") from exc
    if not isinstance(manifest, dict):
        raise CurrentRestatedResearchError("research model manifest root must be an object")
    if (
        manifest.get("schema_version") != "ml-current-restated-base-outcome-model.v1"
        or manifest.get("status") != "verified_base_outcome_only"
        or manifest.get("profile") != "benchmark_excess_regression_only"
        or manifest.get("dataset_temporality") != "current_restated_research"
        or manifest.get("historical_pit") is not False
        or manifest.get("historical_pit_eligible") is not False
        or manifest.get("formal_training_eligible") is not False
        or manifest.get("formal_oos_allowed") is not False
        or manifest.get("production_action_allowed") is not False
        or manifest.get("full_allocation_status") != "blocked_full_allocation_teacher_unavailable"
    ):
        raise CurrentRestatedResearchError("research model manifest capability contract is invalid")
    runtime = manifest.get("runtime_versions")
    expected_runtime = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scikit_learn": sklearn.__version__,
        "joblib": joblib.__version__,
    }
    if runtime != expected_runtime:
        raise CurrentRestatedResearchError("model runtime versions differ from the pinned fit runtime")
    code_pins = manifest.get("code_pins")
    if _normalize_code_pins(code_pins) != dict(capture_current_restated_training_code_pins()):
        raise CurrentRestatedResearchError("model training or loader source-code pins changed")
    model_entry_value = manifest.get("model_bundle")
    registry_entry_value = manifest.get("feature_registry")
    audit_entry_value = manifest.get("fit_audit")
    if not all(isinstance(value, dict) for value in (model_entry_value, registry_entry_value, audit_entry_value)):
        raise CurrentRestatedResearchError("model manifest file descriptors are incomplete")
    model_entry = cast(Mapping[str, Any], model_entry_value)
    registry_entry = cast(Mapping[str, Any], registry_entry_value)
    audit_entry = cast(Mapping[str, Any], audit_entry_value)
    if (
        model_entry.get("filename") != "models.joblib"
        or registry_entry.get("filename") != "feature_registry.json"
        or audit_entry.get("filename") != "fit_audit.json"
    ):
        raise CurrentRestatedResearchError("model manifest contains an unexpected artifact filename")
    model_bytes = _read_verified_child(path.parent, model_entry)
    registry_bytes = _read_verified_child(path.parent, registry_entry)
    audit_bytes = _read_verified_child(path.parent, audit_entry)
    try:
        registry = json.loads(registry_bytes.decode("utf-8"))
        audit = json.loads(audit_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentRestatedResearchError("model registry or audit JSON is invalid") from exc
    if not isinstance(registry, list) or not isinstance(audit, dict):
        raise CurrentRestatedResearchError("model registry or audit root has the wrong type")
    if _canonical_json_bytes(registry) != registry_bytes or _canonical_json_bytes(audit) != audit_bytes:
        raise CurrentRestatedResearchError("model registry or audit is not canonical JSON")
    if audit.get("schema_version") != "current-restated-outcome-only-fit-audit.v1":
        raise CurrentRestatedResearchError("fit audit schema is unsupported")
    if audit_entry.get("sha256") != sha256(audit_bytes).hexdigest():
        raise CurrentRestatedResearchError("fit audit hash differs from model manifest")
    manifest_cost = manifest.get("outcome_cost_contract")
    manifest_target = manifest.get("target_contract")
    if (
        manifest_cost != _expected_outcome_cost_contract_payload()
        or audit.get("outcome_cost_contract") != manifest_cost
        or not isinstance(manifest_target, dict)
        or manifest_target != _outcome_target_contract(manifest_cost)
        or audit.get("target_contract") != manifest_target
    ):
        raise CurrentRestatedResearchError("model target/cost contract is missing or inconsistent")
    context_envelope = manifest.get("source_context_envelope")
    if context_envelope is not None:
        envelope_pin = _mapping(context_envelope, "source_context_envelope")
        _verified_research_file(
            Path(str(envelope_pin.get("path", ""))),
            str(envelope_pin.get("sha256", "")),
            role="source_context_envelope",
        )
        if (
            envelope_pin.get("bytes")
            != Path(str(envelope_pin.get("path", ""))).stat().st_size
        ):
            raise CurrentRestatedResearchError("source context envelope size differs from its model pin")
    bridge_value = manifest.get("current_vector_bridge")
    if bridge_value is not None:
        bridge_map = _mapping(bridge_value, "current_vector_bridge")
        bridge_payload = _mapping(bridge_map.get("payload"), "current_vector_bridge.payload")
        if (
            bridge_map.get("schema_version") != "current-restated-b7-to-core19-bridge.v1"
            or _sha256_bytes(_canonical_json_bytes(bridge_payload))
            != _plain_sha256(bridge_map.get("sha256"), "current_vector_bridge.sha256")
            or audit.get("current_vector_bridge_sha256") != bridge_map.get("sha256")
            or bridge_payload.get("model_training_performed") is not False
            or bridge_payload.get("historical_pit_eligible") is not False
        ):
            raise CurrentRestatedResearchError("B-to-CORE19 bridge descriptor is inconsistent")
        direct_source_value = _mapping(manifest.get("direct_source"), "direct_source")
        direct_receipt_value = _mapping(direct_source_value.get("receipt"), "direct_source.receipt")
        artifacts_value = direct_source_value.get("artifacts")
        if not isinstance(artifacts_value, list):
            raise CurrentRestatedResearchError("model input artifact pins are missing")
        pinned_by_role = {
            str(item.get("role")): item
            for item in artifacts_value
            if isinstance(item, dict)
        }
        b_pin = pinned_by_role.get("b_consumption_receipt")
        payload_b_sha = _plain_sha256(
            bridge_payload.get("b_consumption_receipt_sha256"),
            "current_vector_bridge.b_consumption_receipt_sha256",
        )
        if (
            b_pin is None
            or b_pin.get("sha256") != payload_b_sha
            or b_pin.get("path") != bridge_payload.get("b_consumption_receipt_path")
            or b_pin.get("bytes") != bridge_payload.get("b_consumption_receipt_bytes")
            or direct_receipt_value.get("sha256")
            != bridge_payload.get("direct_outcome_manifest_sha256")
        ):
            raise CurrentRestatedResearchError("model Direct/B receipt pins do not match the saved vector bridge")
        if (
            pinned_by_role.get("raw_publication_manifest", {}).get("sha256")
            != bridge_payload.get("direct_raw_publication_manifest_sha256")
            or pinned_by_role.get("raw_dataset_manifest", {}).get("sha256")
            != bridge_payload.get("direct_raw_dataset_manifest_sha256")
        ):
            raise CurrentRestatedResearchError("model raw-source pins do not match the saved vector bridge")
    vector_descriptors = manifest.get("current_vectors")
    if not isinstance(vector_descriptors, list):
        raise CurrentRestatedResearchError("current research vector inventory is invalid")
    vector_symbols: set[str] = set()
    for vector_descriptor in vector_descriptors:
        vector_meta = _mapping(vector_descriptor, "current vector descriptor")
        symbol = vector_meta.get("symbol")
        filename = vector_meta.get("filename")
        if (
            not isinstance(symbol, str)
            or not symbol
            or symbol in vector_symbols
            or filename != f"current_vectors/{symbol}.json"
            or not symbol.isalnum()
        ):
            raise CurrentRestatedResearchError("current vector path or symbol is invalid")
        vector_symbols.add(symbol)
        vector_path = path.parent / str(filename)
        raw_vector = _read_verified_current_vector(vector_path, vector_meta)
        try:
            vector_payload = json.loads(raw_vector.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CurrentRestatedResearchError("saved current vector is invalid JSON") from exc
        if (
            not isinstance(vector_payload, dict)
            or vector_payload.get("symbol") != symbol
            or vector_payload.get("event_date") != vector_meta.get("event_date")
            or _sha256_bytes(_canonical_json_bytes(vector_payload))
            != vector_meta.get("core19_vector_sha256")
            or _sha256_bytes(_canonical_json_bytes(_core19_numeric_vector_payload(
                _current_restated_row_from_payload(vector_payload)
            ))) != vector_meta.get("core19_numeric_vector_sha256")
        ):
            raise CurrentRestatedResearchError("saved CORE19 current vector differs from its pinned descriptor")
    if bool(vector_descriptors) != (bridge_value is not None):
        raise CurrentRestatedResearchError("current vector files and bridge receipt presence differ")
    registry_ids, scales, packs = _validate_manifest_registry(manifest, registry)
    del registry_ids
    if audit.get("feature_scale_exponents") != scales:
        raise CurrentRestatedResearchError("fit audit scale map differs from the verified registry")
    expected_pack_audit = [
        {"pack_id": pack.pack_id, "feature_ids": list(pack.feature_ids)}
        for pack in packs
    ]
    if audit.get("feature_ids_by_pack") != expected_pack_audit:
        raise CurrentRestatedResearchError("fit audit feature packs differ from the verified registry")
    _verify_source_context_payload(manifest.get("source_context"), manifest.get("training_as_of"))
    _verify_model_fit_clocks(manifest, audit)
    model_keys = _validate_declared_model_contract(model_entry, audit, packs)
    direct_source_for_qualification = _mapping(manifest.get("direct_source"), "direct_source")
    direct_manifest_for_qualification = _mapping(
        direct_source_for_qualification.get("manifest"), "direct_source.manifest"
    )
    _validate_verified_current_restated_fold_qualification(
        audit,
        expected_direct_manifest_sha256=_plain_sha256(
            direct_manifest_for_qualification.get("sha256"),
            "direct_source.manifest.sha256",
        ),
        expected_direct_event_date_calendar_sha256=(
            cast(str, direct_manifest_for_qualification.get("event_date_calendar_sha256"))
            if direct_manifest_for_qualification.get("event_date_calendar_sha256") is not None
            else None
        ),
    )
    if model_entry.get("sha256") != trusted_model_sha or sha256(model_bytes).hexdigest() != trusted_model_sha:
        raise CurrentRestatedResearchError("model bundle does not match the out-of-band trusted SHA-256")
    try:
        # This is the existing same-private-buffer deserialization path. Its
        # safety relies on the required out-of-band model-byte pin above.
        from ml_module.model_artifact_loader import _deserialize_verified_joblib_buffer

        models = _deserialize_verified_joblib_buffer(BytesIO(model_bytes))
    except Exception as exc:
        raise CurrentRestatedResearchError("model bytes cannot be deserialized") from exc
    if not isinstance(models, dict):
        raise CurrentRestatedResearchError("serialized model bundle must be a dictionary")
    if model_keys != sorted(models):
        raise CurrentRestatedResearchError("serialized model keys differ from manifest")
    actual_shapes = _validate_model_bundle(models, tuple(model_keys), packs)
    if actual_shapes != model_entry.get("shapes"):
        raise CurrentRestatedResearchError("fitted estimator shapes differ from the prevalidated descriptors")
    immutable_manifest = _freeze_json(manifest)
    return LoadedCurrentRestatedModel(
        manifest_path=path,
        manifest_sha256=actual_manifest_sha,
        manifest=immutable_manifest,
        models=MappingProxyType(dict(models)),
    )


def predict_current_restated_outcomes(
    model: LoadedCurrentRestatedModel,
    *,
    row: CurrentRestatedResearchRow,
    inference_at: str,
) -> Mapping[str, Any]:
    """Infer benchmark-excess bp for an exact current-observed research vector."""

    inference_clock = _aware_iso(inference_at, "inference_at")
    if inference_clock > datetime.now(timezone.utc):
        raise CurrentRestatedResearchError("inference_at cannot be later than the actual current clock")
    model_available = _aware_iso(str(model.manifest["model_available_at"]), "model_available_at")
    if inference_clock < model_available:
        raise CurrentRestatedResearchError("model is not available at the requested inference clock")
    if row.historical_pit_eligible is not False:
        raise CurrentRestatedResearchError("current-restated row cannot claim historical PIT")
    if _aware_iso(row.source_observed_at, "row.source_observed_at") > inference_clock:
        raise CurrentRestatedResearchError("inference row source observation is in the future")
    registry = model.manifest["feature_registry"]["entries"]
    registry_ids = tuple(str(item["feature_id"]) for item in registry)
    features = {feature.feature_id: feature for feature in row.features}
    if tuple(features) != registry_ids and set(features) != set(registry_ids):
        raise CurrentRestatedResearchError("inference vector differs from ordered feature registry")
    if set(features) != set(registry_ids):
        raise CurrentRestatedResearchError("inference vector differs from model registry")
    blocked = set(row.quality_blocked_mask) | set(row.staleness_mask)
    if not blocked.issubset(set(registry_ids)):
        raise CurrentRestatedResearchError("inference quality/staleness mask is outside the model registry")
    usable_feature_ids = tuple(
        definition_id
        for definition_id in registry_ids
        if features[definition_id].observed
        and not features[definition_id].stale
        and definition_id not in blocked
    )
    if not usable_feature_ids:
        raise CurrentRestatedResearchError(
            "inference row has no usable observed feature; imputation alone cannot qualify a prediction"
        )
    matrix_values: dict[str, float | None] = {}
    for definition in registry:
        feature_id = str(definition["feature_id"])
        feature = features[feature_id]
        current_available = _aware_iso(feature.current_value_available_at, "feature.current_value_available_at")
        source_observed = _aware_iso(feature.source_observed_at, "feature.source_observed_at")
        if current_available > inference_clock or source_observed > inference_clock:
            raise CurrentRestatedResearchError("inference vector contains a future source clock")
        if feature.source_available_at is not None and _aware_iso(
            feature.source_available_at, "feature.source_available_at"
        ) > inference_clock:
            raise CurrentRestatedResearchError("inference vector has a future source-availability clock")
        if feature.scale != definition["scale"]:
            raise CurrentRestatedResearchError("inference vector scale differs from model registry")
        if feature.observed and not feature.stale and feature_id not in blocked:
            assert feature.value_int is not None
            numeric = float(Decimal(feature.value_int).scaleb(-feature.scale))
            if not np.isfinite(numeric):
                raise CurrentRestatedResearchError("inference feature is non-finite at model boundary")
            matrix_values[feature_id] = numeric
        else:
            matrix_values[feature_id] = None
    packs = {
        str(item["pack_id"]): tuple(str(value) for value in item["feature_ids"])
        for item in model.manifest["feature_packs"]
    }
    predicted: dict[str, int] = {}
    for key, estimator in model.models.items():
        prefix, pack_id, horizon_text, algorithm = key.split("|", 3)
        if prefix != "final":
            raise CurrentRestatedResearchError("model contains a non-final fit artifact")
        feature_ids = packs[pack_id]
        values = [matrix_values[feature_id] for feature_id in feature_ids]
        if algorithm == "hist_gradient_boosting":
            input_values = values + [1.0 if value is None else 0.0 for value in values]
        elif algorithm == "ridge_logistic":
            input_values = values
        else:
            raise CurrentRestatedResearchError("model key has an unsupported algorithm")
        matrix = np.asarray([input_values], dtype=float)
        estimate = np.asarray(estimator.predict(matrix), dtype=float)
        if estimate.shape != (1,) or not np.isfinite(estimate[0]):
            raise CurrentRestatedResearchError("model returned an invalid benchmark-excess estimate")
        predicted[key] = _quantize_model_bp(estimate[0])
    return MappingProxyType(
        {
            "schema_version": "ml-current-restated-outcome-prediction.v1",
            "status": "research_prediction_only",
            "model_manifest_sha256": model.manifest_sha256,
            "model_available_at": model_available.isoformat(),
            "inference_at": inference_clock.isoformat(),
            "consumer_process_id": os.getpid(),
            "consumer_argv": list(sys.argv),
            "row_id": row.row_id,
            "symbol": row.symbol,
            "event_date": row.event_date,
            "dataset_temporality": "current_restated_research",
            "historical_pit": False,
            "decision_time_eligible": False,
            "production_action_allowed": False,
            "target_metric": model.manifest["target_contract"]["target_metric"],
            "outcome_cost_contract": model.manifest["outcome_cost_contract"],
            "input_quality_summary": MappingProxyType(
                {
                    "registry_feature_count": len(registry_ids),
                    "usable_feature_count": len(usable_feature_ids),
                    "missing_feature_count": len(row.missing_mask),
                    "quality_blocked_feature_count": len(row.quality_blocked_mask),
                    "stale_feature_count": len(row.staleness_mask),
                    "usable_feature_ids": usable_feature_ids,
                    "missing_feature_ids": row.missing_mask,
                    "quality_blocked_feature_ids": row.quality_blocked_mask,
                    "stale_feature_ids": row.staleness_mask,
                }
            ),
            "predicted_benchmark_excess_return_bp": MappingProxyType(predicted),
        }
    )


def save_verified_current_restated_context_file(
    source_context: object,
    *,
    output_path: str | Path,
    fit_cutoff: str,
) -> tuple[Path, str]:
    """以 create-only 將已驗 context 固定為可由舊入口共同傳遞的 bytes。"""

    context_payload = _verified_context_payload(source_context, fit_cutoff)
    envelope = {
        "schema_version": "ml-current-restated-source-context-envelope.v1",
        "source_context": context_payload,
    }
    payload_bytes = _canonical_json_bytes(envelope)
    target = resolve_ml_research_output_path(output_path, access="write")
    if target.is_symlink() or not target.parent.is_dir():
        raise CurrentRestatedResearchError(
            "context envelope parent must already exist below output/ml_research"
        )
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise CurrentRestatedResearchError("context envelope is create-only") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload_bytes)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    _fsync_directory(target.parent)
    return target, sha256(payload_bytes).hexdigest()


def load_verified_current_restated_context_file(
    context_path: str | Path,
    *,
    expected_context_sha256: str,
) -> VerifiedCurrentRestatedContextFile:
    """核對跨流程固定 bytes，並以 A 的 strict loader 重新驗原始來源。"""

    target = resolve_ml_research_output_path(context_path, access="read")
    if target.is_symlink() or not target.is_file():
        raise CurrentRestatedResearchError("source context envelope must be a regular file")
    try:
        before = target.stat()
        context_bytes = target.read_bytes()
        after = target.stat()
    except OSError as exc:
        raise CurrentRestatedResearchError("source context envelope cannot be read") from exc
    if (
        len(context_bytes) > 4 * 1024 * 1024
        or len(context_bytes) != before.st_size
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or target.resolve(strict=True) != target
    ):
        raise CurrentRestatedResearchError("source context envelope changed or exceeds 4 MiB")
    actual_sha256 = sha256(context_bytes).hexdigest()
    _plain_sha256(expected_context_sha256, "expected_context_sha256")
    if actual_sha256 != expected_context_sha256.removeprefix("sha256:"):
        raise CurrentRestatedResearchError("source context envelope actual-byte SHA-256 mismatch")
    try:
        envelope = json.loads(context_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentRestatedResearchError("source context envelope is invalid UTF-8 JSON") from exc
    if not isinstance(envelope, dict) or _canonical_json_bytes(envelope) != context_bytes:
        raise CurrentRestatedResearchError("source context envelope is not canonical JSON")
    if envelope.get("schema_version") != "ml-current-restated-source-context-envelope.v1":
        raise CurrentRestatedResearchError("source context envelope schema is unsupported")
    saved_context = _mapping(envelope.get("source_context"), "source_context")
    _verify_source_context_payload(saved_context, datetime.now(timezone.utc).isoformat())
    from data_module.ml_daily_price_revision_gate import (
        load_verified_current_restated_source_context,
    )

    try:
        fresh_context = load_verified_current_restated_source_context(
            Path(str(saved_context["snapshot_database_path"])),
            Path(str(saved_context["snapshot_receipt_path"])),
            expected_snapshot_database_sha256=str(
                saved_context["snapshot_database_sha256"]
            ),
            expected_snapshot_receipt_sha256=str(
                saved_context["snapshot_receipt_sha256"]
            ),
            original_database_path=Path(str(saved_context["source_database_path"])),
            decision_at=str(saved_context["decision_at"]),
            training_as_of=str(saved_context["training_as_of"]),
        )
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        raise CurrentRestatedResearchError(
            f"source context physical revalidation failed: {type(exc).__name__}: {exc}"
        ) from exc
    fresh_payload = _source_context_plain_payload(fresh_context)
    stable_context_fields = set(saved_context) - {
        "revision_dependencies_verified_at",
        "revision_dependency_bundle_sha256",
        "revision_dependency_files",
    }
    changed_context_fields = sorted(
        field
        for field in stable_context_fields
        if saved_context.get(field) != fresh_payload.get(field)
    )
    saved_dependencies = saved_context.get("revision_dependency_files")
    fresh_dependencies = fresh_payload.get("revision_dependency_files")
    if not isinstance(saved_dependencies, list) or not isinstance(fresh_dependencies, list):
        raise CurrentRestatedResearchError(
            "saved/current source context dependency inventory is invalid"
        )
    saved_inventory_sha256 = _dependency_inventory_sha256(saved_dependencies)
    fresh_inventory_sha256 = _dependency_inventory_sha256(fresh_dependencies)
    if saved_inventory_sha256 != fresh_inventory_sha256:
        changed_context_fields.append("revision_dependency_files")
    if changed_context_fields:
        raise CurrentRestatedResearchError(
            "source context pins changed since the parent captured its shared envelope: "
            + ", ".join(changed_context_fields)
        )
    from dataclasses import replace as dataclass_replace
    from data_module.ml_daily_price_revision_gate import VerifiedRevisionDependencyV1

    try:
        saved_dependency_rows = tuple(
            VerifiedRevisionDependencyV1(
                namespace=str(item["namespace"]),
                role_id=str(item["role_id"]),
                path=str(item["path"]),
                bytes=int(item["bytes"]),
                mtime_ns=int(item["mtime_ns"]),
                sha256=str(item["sha256"]),
                captured_at=_aware_iso(str(item["captured_at"]), "captured_at"),
            )
            for item in saved_dependencies
            if isinstance(item, Mapping)
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CurrentRestatedResearchError("saved dependency pins are malformed") from exc
    pinned_context = dataclass_replace(
        fresh_context,
        revision_dependencies_verified_at=_aware_iso(
            str(saved_context["revision_dependencies_verified_at"]),
            "saved revision_dependencies_verified_at",
        ),
        revision_dependency_files=saved_dependency_rows,
        revision_dependency_bundle_sha256=str(
            saved_context["revision_dependency_bundle_sha256"]
        ),
    )
    return VerifiedCurrentRestatedContextFile(
        path=target,
        sha256=actual_sha256,
        context=pinned_context,
        saved_payload=MappingProxyType(dict(saved_context)),
        revalidated_at=fresh_context.revision_dependencies_verified_at.isoformat(),
        revalidated_dependency_bundle_sha256=fresh_context.revision_dependency_bundle_sha256,
        revalidated_dependency_inventory_sha256=fresh_inventory_sha256,
    )


def _verified_context_payload(source_context: object, training_as_of: str) -> dict[str, Any]:
    from data_module.ml_daily_price_revision_gate import VerifiedCurrentRestatedSourceContext

    if type(source_context) is not VerifiedCurrentRestatedSourceContext:
        raise CurrentRestatedResearchError("source context must come from A's strict verified loader")
    context = cast(VerifiedCurrentRestatedSourceContext, source_context)
    cutoff = _aware_iso(training_as_of, "training_as_of")
    for name in ("decision_at", "training_as_of", "source_observed_at", "revision_dependencies_verified_at"):
        value = getattr(context, name, None)
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise CurrentRestatedResearchError(f"verified source context {name} is not timezone-aware")
        if value > cutoff:
            raise CurrentRestatedResearchError(f"verified source context {name} is after the fit freeze")
    if context.current_restated is not True or context.historical_pit_eligible is not False:
        raise CurrentRestatedResearchError("source context capability flags are invalid")
    return _source_context_plain_payload(context)


def _source_context_plain_payload(context: object) -> dict[str, Any]:
    from dataclasses import fields
    from data_module.ml_daily_price_revision_gate import VerifiedCurrentRestatedSourceContext

    payload: dict[str, Any] = {}
    if type(context) is not VerifiedCurrentRestatedSourceContext:
        raise CurrentRestatedResearchError("source context serializer requires A's verified type")
    typed_context = cast(VerifiedCurrentRestatedSourceContext, context)
    for item in fields(typed_context):
        value = getattr(typed_context, item.name)
        if isinstance(value, datetime):
            payload[item.name] = value.isoformat()
        elif isinstance(value, tuple):
            payload[item.name] = [
                {
                    field.name: (
                        getattr(entry, field.name).isoformat()
                        if isinstance(getattr(entry, field.name), datetime)
                        else getattr(entry, field.name)
                    )
                    for field in fields(entry)
                }
                if hasattr(entry, "__dataclass_fields__")
                else entry
                for entry in value
            ]
        else:
            payload[item.name] = value
    return _plain_json(payload, "source context")


def _verify_source_context_payload(value: Any, training_as_of: Any) -> None:
    payload = _mapping(value, "source_context")
    cutoff = _aware_iso(str(training_as_of), "training_as_of")
    for field in ("decision_at", "training_as_of", "source_observed_at", "revision_dependencies_verified_at"):
        clock = _aware_iso(str(payload.get(field)), f"source_context.{field}")
        if clock > cutoff:
            raise CurrentRestatedResearchError(f"source context {field} exceeds the fit cutoff")
    if payload.get("current_restated") is not True or payload.get("historical_pit_eligible") is not False:
        raise CurrentRestatedResearchError("serialized source context capability flags are invalid")
    for field in (
        "source_database_sha256",
        "snapshot_database_sha256",
        "snapshot_receipt_sha256",
        "revision_namespace_bundle_sha256",
        "source_revision_evidence_sha256",
        "revision_dependency_bundle_sha256",
    ):
        _plain_sha256(str(payload.get(field)), f"source_context.{field}")
    wal_present = payload.get("source_wal_present", True)
    if type(wal_present) is not bool:
        raise CurrentRestatedResearchError("source context WAL presence flag is invalid")
    if wal_present:
        _plain_sha256(
            str(payload.get("source_wal_sha256")), "source_context.source_wal_sha256"
        )
    else:
        database_value = payload.get("source_database_path")
        wal_value = payload.get("source_wal_path")
        expected_wal = (
            Path(database_value).with_name(Path(database_value).name + "-wal")
            if isinstance(database_value, str) and database_value.strip()
            else None
        )
        if (
            payload.get("schema_version") != "verified-current-restated-source-context.v2"
            or payload.get("source_wal_sha256") is not None
            or not isinstance(wal_value, str)
            or not Path(wal_value).is_absolute()
            or expected_wal is None
            or os.path.normcase(os.path.abspath(wal_value)).casefold()
            != os.path.normcase(os.path.abspath(str(expected_wal))).casefold()
        ):
            raise CurrentRestatedResearchError(
                "absent source WAL context is not explicitly and consistently pinned"
            )


def _validate_model_bundle(
    models: Mapping[str, Any],
    model_keys: tuple[str, ...],
    packs: Sequence[FeaturePackDefinition],
) -> dict[str, dict[str, Any]]:
    pack_by_id = {pack.pack_id: pack for pack in packs}
    if set(models) != set(model_keys):
        raise CurrentRestatedResearchError("model keys disagree with the fit audit")
    shape_map: dict[str, dict[str, Any]] = {}
    for key, model in models.items():
        try:
            prefix, pack_id, horizon_text, algorithm = key.split("|", 3)
            horizon = int(horizon_text.removeprefix("h"))
        except (ValueError, TypeError) as exc:
            raise CurrentRestatedResearchError("model key is malformed") from exc
        if prefix != "final" or pack_id not in pack_by_id or horizon <= 0:
            raise CurrentRestatedResearchError("model key is outside the final research profile")
        width = len(pack_by_id[pack_id].feature_ids)
        if algorithm == "ridge_logistic":
            if type(model) is not Pipeline:
                raise CurrentRestatedResearchError("Ridge estimator is not the expected sklearn pipeline")
            try:
                check_is_fitted(model)
            except Exception as exc:
                raise CurrentRestatedResearchError("Ridge pipeline is not fitted") from exc
            if tuple(name for name, _ in model.steps) != ("imputer", "scaler", "model"):
                raise CurrentRestatedResearchError("Ridge pipeline steps are incompatible")
            imputer = model.named_steps["imputer"]
            scaler = model.named_steps["scaler"]
            regressor = model.named_steps["model"]
            if (
                type(imputer) is not SimpleImputer
                or imputer.strategy != "median"
                or imputer.add_indicator is not True
                or imputer.keep_empty_features is not True
                or type(scaler) is not StandardScaler
                or type(regressor) is not Ridge
                or int(model.n_features_in_) != width
            ):
                raise CurrentRestatedResearchError("Ridge pipeline parameters or width are incompatible")
            for fitted_component in (imputer, scaler, regressor):
                try:
                    check_is_fitted(fitted_component)
                except Exception as exc:
                    raise CurrentRestatedResearchError("Ridge pipeline contains an unfitted component") from exc
            indicator = getattr(imputer, "indicator_", None)
            indicator_indices_value = getattr(indicator, "features_", None)
            if (
                indicator is None
                or not isinstance(indicator_indices_value, np.ndarray)
                or indicator_indices_value.ndim != 1
                or not np.issubdtype(indicator_indices_value.dtype, np.integer)
            ):
                raise CurrentRestatedResearchError("Ridge pipeline missing-indicator metadata is invalid")
            indicator_indices = tuple(int(value) for value in indicator_indices_value.tolist())
            if (
                len(indicator_indices) != len(set(indicator_indices))
                or tuple(sorted(indicator_indices)) != indicator_indices
                or any(value < 0 or value >= width for value in indicator_indices)
            ):
                raise CurrentRestatedResearchError("Ridge pipeline missing-indicator columns are invalid")
            transformed_width = width + len(indicator_indices)
            if (
                getattr(imputer, "statistics_", np.empty(0)).shape != (width,)
                or getattr(scaler, "n_features_in_", None) != transformed_width
                or getattr(regressor, "n_features_in_", None) != transformed_width
            ):
                raise CurrentRestatedResearchError("Ridge pipeline fitted component shapes are incompatible")
            matrix_width = transformed_width
        elif algorithm == "hist_gradient_boosting":
            if type(model) is not HistGradientBoostingRegressor or int(model.n_features_in_) != width * 2:
                raise CurrentRestatedResearchError("HistGradientBoosting shape or estimator class is incompatible")
            try:
                check_is_fitted(model)
            except Exception as exc:
                raise CurrentRestatedResearchError("HistGradientBoosting estimator is not fitted") from exc
            matrix_width = width * 2
            transformed_width = matrix_width
            indicator_indices = ()
        else:
            raise CurrentRestatedResearchError("model key names an unsupported algorithm")
        shape_map[key] = {
            "feature_width": width,
            "matrix_width": matrix_width,
            "transformed_width": transformed_width,
            "missing_indicator_indices": list(indicator_indices),
            "horizon": horizon,
        }
    return shape_map


def _validate_manifest_registry(
    manifest: Mapping[str, Any], registry: Sequence[Mapping[str, Any]]
) -> tuple[tuple[str, ...], dict[str, int], tuple[FeaturePackDefinition, ...]]:
    entry = _mapping(manifest.get("feature_registry"), "feature_registry")
    ids: list[str] = []
    scales: dict[str, int] = {}
    for item in registry:
        feature_id = item.get("feature_id")
        scale = item.get("scale")
        if not isinstance(feature_id, str) or isinstance(scale, bool) or not isinstance(scale, int) or not 0 <= scale <= 18:
            raise CurrentRestatedResearchError("loaded feature registry has an invalid ID or exponent")
        ids.append(feature_id)
        scales[feature_id] = scale
    if len(ids) != len(set(ids)) or ids != entry.get("feature_ids") or scales != entry.get("scale_exponents"):
        raise CurrentRestatedResearchError("loaded registry order or scales differ from model manifest")
    if sha256(_canonical_json_bytes(registry)).hexdigest() != entry.get("sha256"):
        raise CurrentRestatedResearchError("feature registry canonical hash mismatch")
    raw_packs = manifest.get("feature_packs")
    if not isinstance(raw_packs, list) or not raw_packs:
        raise CurrentRestatedResearchError("model feature packs are absent")
    packs = tuple(
        FeaturePackDefinition(str(item["pack_id"]), tuple(str(value) for value in item["feature_ids"]))
        for item in raw_packs
        if isinstance(item, dict)
    )
    if len(packs) != len(raw_packs) or [feature for pack in packs for feature in pack.feature_ids] != ids:
        raise CurrentRestatedResearchError("model packs do not partition the ordered registry")
    return tuple(ids), scales, packs


def _declared_estimator_classes(model_keys: Sequence[str]) -> dict[str, str]:
    classes: dict[str, str] = {}
    for key in model_keys:
        try:
            prefix, _pack_id, horizon_text, algorithm = key.split("|", 3)
            horizon = int(horizon_text.removeprefix("h"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise CurrentRestatedResearchError("model key is malformed") from exc
        if prefix != "final" or horizon <= 0:
            raise CurrentRestatedResearchError("model key is outside the approved final profile")
        if algorithm == "ridge_logistic":
            classes[key] = "sklearn.pipeline.Pipeline"
        elif algorithm == "hist_gradient_boosting":
            classes[key] = "sklearn.ensemble.HistGradientBoostingRegressor"
        else:
            raise CurrentRestatedResearchError("model key names an unsupported estimator profile")
    return classes


def _validate_declared_model_contract(
    entry: Mapping[str, Any],
    audit: Mapping[str, Any],
    packs: Sequence[FeaturePackDefinition],
) -> list[str]:
    """Validate declared identity and dimensions using JSON before loading pickle bytes."""

    keys_value = entry.get("model_keys")
    if (
        not isinstance(keys_value, list)
        or not keys_value
        or any(not isinstance(key, str) for key in keys_value)
        or keys_value != sorted(set(keys_value))
    ):
        raise CurrentRestatedResearchError("model key list must be a sorted unique string list")
    model_keys = cast(list[str], keys_value)
    if audit.get("model_keys") != model_keys:
        raise CurrentRestatedResearchError("fit audit model keys differ from the declared bundle")
    classes = entry.get("estimator_classes")
    if not isinstance(classes, dict) or classes != _declared_estimator_classes(model_keys):
        raise CurrentRestatedResearchError("declared estimator classes differ from the fixed research profile")
    shapes = entry.get("shapes")
    if not isinstance(shapes, dict) or set(shapes) != set(model_keys):
        raise CurrentRestatedResearchError("declared model shapes are incomplete")
    pack_by_id = {pack.pack_id: pack for pack in packs}
    horizons: set[int] = set()
    algorithms: set[str] = set()
    for key in model_keys:
        try:
            prefix, pack_id, horizon_text, algorithm = key.split("|", 3)
            horizon_text_value = horizon_text.removeprefix("h")
            horizon = int(horizon_text_value)
        except (AttributeError, TypeError, ValueError) as exc:
            raise CurrentRestatedResearchError("model key is malformed") from exc
        if (
            prefix != "final"
            or pack_id not in pack_by_id
            or horizon <= 0
            or str(horizon) != horizon_text_value
            or algorithm not in {"ridge_logistic", "hist_gradient_boosting"}
        ):
            raise CurrentRestatedResearchError("model key is outside the declared feature/horizon profile")
        width = len(pack_by_id[pack_id].feature_ids)
        shape = shapes.get(key)
        if not isinstance(shape, dict):
            raise CurrentRestatedResearchError("declared model shape is outside the fixed profile")
        indicator_indices = shape.get("missing_indicator_indices")
        if (
            not isinstance(indicator_indices, list)
            or any(type(value) is not int for value in indicator_indices)
            or len(indicator_indices) != len(set(indicator_indices))
            or indicator_indices != sorted(indicator_indices)
            or any(value < 0 or value >= width for value in indicator_indices)
        ):
            raise CurrentRestatedResearchError("declared missing-indicator columns are invalid")
        transformed_width = width + len(indicator_indices) if algorithm == "ridge_logistic" else width * 2
        expected_matrix_width = transformed_width
        if algorithm == "hist_gradient_boosting" and indicator_indices:
            raise CurrentRestatedResearchError("HistGradientBoosting cannot declare imputer indicators")
        if (
            not isinstance(shape, dict)
            or set(shape)
            != {
                "feature_width",
                "matrix_width",
                "transformed_width",
                "missing_indicator_indices",
                "horizon",
            }
            or any(
                isinstance(shape.get(field), bool) or not isinstance(shape.get(field), int)
                for field in ("feature_width", "matrix_width", "transformed_width", "horizon")
            )
            or shape
            != {
                "feature_width": width,
                "matrix_width": expected_matrix_width,
                "transformed_width": transformed_width,
                "missing_indicator_indices": indicator_indices,
                "horizon": horizon,
            }
        ):
            raise CurrentRestatedResearchError("declared model shape is outside the fixed profile")
        horizons.add(horizon)
        algorithms.add(algorithm)
    audit_algorithms = audit.get("algorithm_ids")
    if (
        not isinstance(audit_algorithms, list)
        or any(not isinstance(item, str) for item in audit_algorithms)
        or sorted(set(audit_algorithms)) != sorted(algorithms)
        or len(audit_algorithms) != len(algorithms)
        or audit.get("horizons") != sorted(horizons)
    ):
        raise CurrentRestatedResearchError("fit audit algorithm or horizon inventory differs from model keys")
    if (
        audit.get("schema_version") != "current-restated-outcome-only-fit-audit.v1"
        or audit.get("dataset_temporality") != "current_restated_research"
        or audit.get("target_heads") != ["benchmark_excess_return_bp"]
        or audit.get("status") != "verified_base_outcome_only"
        or audit.get("historical_pit") is not False
        or audit.get("formal_oos_allowed") is not False
        or audit.get("production_action_allowed") is not False
        or audit.get("full_allocation_status") != "blocked_full_allocation_teacher_unavailable"
    ):
        raise CurrentRestatedResearchError("fit audit capability contract is invalid")
    sample_count = audit.get("sample_count")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0:
        raise CurrentRestatedResearchError("fit audit sample count is invalid")
    calendar_value = audit.get("event_date_calendar")
    if (
        not isinstance(calendar_value, list)
        or not calendar_value
        or any(not isinstance(value, str) for value in calendar_value)
    ):
        raise CurrentRestatedResearchError("fit audit complete event-date calendar is invalid")
    parsed_calendar = [_strict_date(value, "fit_audit.event_date_calendar") for value in calendar_value]
    if parsed_calendar != sorted(set(parsed_calendar)):
        raise CurrentRestatedResearchError("fit audit event-date calendar is not sorted and unique")
    calendar_bytes = json.dumps(
        calendar_value,
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if audit.get("event_date_calendar_sha256") != sha256(calendar_bytes).hexdigest():
        raise CurrentRestatedResearchError("fit audit event-date calendar hash mismatch")
    calendar_value = audit.get("event_date_calendar")
    if (
        not isinstance(calendar_value, list)
        or not calendar_value
        or any(not isinstance(value, str) for value in calendar_value)
    ):
        raise CurrentRestatedResearchError("fit audit complete event-date calendar is invalid")
    parsed_calendar = [_strict_date(value, "fit_audit.event_date_calendar") for value in calendar_value]
    if parsed_calendar != sorted(set(parsed_calendar)):
        raise CurrentRestatedResearchError("fit audit event-date calendar is not sorted and unique")
    calendar_bytes = json.dumps(
        calendar_value,
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if audit.get("event_date_calendar_sha256") != sha256(calendar_bytes).hexdigest():
        raise CurrentRestatedResearchError("fit audit event-date calendar hash mismatch")
    folds = audit.get("folds")
    if not isinstance(folds, list) or not folds:
        raise CurrentRestatedResearchError("fit audit fold records are missing")
    for fold in folds:
        if (
            not isinstance(fold, dict)
            or fold.get("label_head") != "benchmark_excess_return_bp"
            or isinstance(fold.get("purge_trading_days"), bool)
            or fold.get("purge_trading_days") != 60
            or isinstance(fold.get("embargo_trading_days"), bool)
            or fold.get("embargo_trading_days") != 5
            or fold.get("preprocessing_fit_scope") != "fold-local-training-rows-only"
        ):
            raise CurrentRestatedResearchError("fit audit fold contract is invalid")
    return model_keys


def _validate_verified_current_restated_fold_qualification(
    audit: Mapping[str, Any],
    *,
    expected_direct_manifest_sha256: str,
    expected_direct_event_date_calendar_sha256: str | None = None,
) -> None:
    """拒絕只宣告 60/5 或小型 smoke fold 的模型發布與重載。"""

    qualification = audit.get("current_restated_verified_fold_qualification")
    fit_selection = audit.get("fit_selection")
    expected_fit_selection = {
        "profile": "core19_current_restated_outcome_only.v1",
        "horizons": [5],
        "algorithms": ["ridge_logistic"],
        "random_state": 42,
        "ridge_alpha": 1,
        "hgb_max_iter": 60,
        "hgb_max_iter_applicability": "not_used_by_ridge_logistic_profile",
    }
    if fit_selection != expected_fit_selection:
        raise CurrentRestatedResearchError("fit audit estimator selection differs from the fixed CORE19 profile")
    if not isinstance(qualification, Mapping):
        raise CurrentRestatedResearchError("fit audit lacks verified full-calendar fold qualification")
    calendar = audit.get("event_date_calendar")
    if not isinstance(calendar, list) or any(type(item) is not str for item in calendar):
        raise CurrentRestatedResearchError("fit audit complete event-date calendar is invalid")
    qualification_schema = qualification.get("schema_version")
    calendar_count = qualification.get("event_date_calendar_count")
    common_policy_valid = (
        type(calendar_count) is int
        and qualification.get("minimum_mature_train_dates") == 125
        and qualification.get("minimum_test_dates") == 63
        and qualification.get("minimum_purge_trading_days") == 60
        and qualification.get("minimum_embargo_trading_days") == 5
        and qualification.get("minimum_qualified_fold_count") == 4
    )
    if qualification_schema == _CURRENT_RESTATED_FOLD_CALENDAR_V1:
        calendar_contract_valid = len(calendar) == _CURRENT_RESTATED_MINIMUM_CALENDAR_SESSIONS and (
            calendar_count == _CURRENT_RESTATED_MINIMUM_CALENDAR_SESSIONS
        )
    elif qualification_schema == _CURRENT_RESTATED_FOLD_CALENDAR_V2:
        calendar_contract_valid = (
            len(calendar) >= _CURRENT_RESTATED_MINIMUM_CALENDAR_SESSIONS
            and calendar_count == len(calendar)
            and qualification.get("minimum_event_date_calendar_count")
            == _CURRENT_RESTATED_MINIMUM_CALENDAR_SESSIONS
            and qualification.get("calendar_scope")
            == "complete_verified_direct_event_date_calendar"
            and _plain_sha256(
                qualification.get("direct_event_date_calendar_sha256"),
                "fold_qualification.direct_event_date_calendar_sha256",
            )
            == _plain_sha256(
                qualification.get("event_date_calendar_sha256"),
                "fold_qualification.event_date_calendar_sha256",
            )
            and expected_direct_event_date_calendar_sha256 is not None
            and _plain_sha256(
                qualification.get("direct_event_date_calendar_sha256"),
                "fold_qualification.direct_event_date_calendar_sha256",
            )
            == _plain_sha256(
                expected_direct_event_date_calendar_sha256,
                "expected_direct_event_date_calendar_sha256",
            )
        )
    else:
        calendar_contract_valid = False
    if not common_policy_valid or not calendar_contract_valid:
        raise CurrentRestatedResearchError(
            "fit audit does not bind a complete verified calendar with the required 905/125/63/60/5/minimum-4 profile"
        )
    expected_direct = _plain_sha256(
        expected_direct_manifest_sha256, "expected_direct_manifest_sha256"
    )
    if _plain_sha256(
        qualification.get("direct_manifest_sha256"), "fold_qualification.direct_manifest_sha256"
    ) != expected_direct:
        raise CurrentRestatedResearchError("fold qualification is bound to another Direct manifest")
    parsed_calendar = [_strict_date(item, "fit_audit.event_date_calendar") for item in calendar]
    if parsed_calendar != sorted(set(parsed_calendar)):
        raise CurrentRestatedResearchError("fit audit event-date calendar is not sorted and unique")
    calendar_sha = _sha256_bytes(_canonical_json_bytes(calendar))
    if (
        _plain_sha256(
            audit.get("event_date_calendar_sha256"), "fit_audit.event_date_calendar_sha256"
        ) != calendar_sha
        or _plain_sha256(
            qualification.get("event_date_calendar_sha256"),
            "fold_qualification.event_date_calendar_sha256",
        ) != calendar_sha
    ):
        raise CurrentRestatedResearchError("fit audit calendar hash differs from qualified calendar bytes")
    calendar_positions = {value: index for index, value in enumerate(calendar)}
    raw_fold_rows = audit.get("folds")
    qualified_folds = qualification.get("folds")
    if not isinstance(raw_fold_rows, list) or not isinstance(qualified_folds, list):
        raise CurrentRestatedResearchError("fit audit fold inventories are invalid")
    if len(qualified_folds) < 4:
        raise CurrentRestatedResearchError("fit audit has fewer than four qualified folds")
    qualified_by_id: dict[str, Mapping[str, Any]] = {}
    previous_test_end: int | None = None
    for item in qualified_folds:
        if not isinstance(item, Mapping) or not isinstance(item.get("fold_id"), str):
            raise CurrentRestatedResearchError("qualified fold record is malformed")
        fold_id = str(item["fold_id"])
        if fold_id in qualified_by_id:
            raise CurrentRestatedResearchError("qualified fold ids are duplicated")
        qualified_by_id[fold_id] = item
        start_text = item.get("test_start")
        end_text = item.get("test_end")
        if type(start_text) is not str or type(end_text) is not str:
            raise CurrentRestatedResearchError("qualified fold test bounds are missing")
        start_date = _strict_date(start_text, "qualified_fold.test_start")
        end_date = _strict_date(end_text, "qualified_fold.test_end")
        if start_text not in calendar_positions or end_text not in calendar_positions:
            raise CurrentRestatedResearchError("qualified fold bounds are outside the full calendar")
        start_index = calendar_positions[start_text]
        end_index = calendar_positions[end_text]
        train_indices = item.get("train_date_indices")
        test_indices = item.get("test_date_indices")
        int_list = lambda value: (
            isinstance(value, list)
            and all(type(entry) is int and 0 <= entry < len(calendar) for entry in value)
            and value == sorted(set(value))
        )
        if not int_list(train_indices) or not int_list(test_indices):
            raise CurrentRestatedResearchError("qualified fold calendar indices are invalid")
        if (
            not train_indices
            or not test_indices
            or test_indices[0] != start_index
            or test_indices[-1] != end_index
            or len(test_indices) < 63
            or len(train_indices) < 125
        ):
            raise CurrentRestatedResearchError("qualified fold has fewer than 125/63 calendar dates")
        actual_purge = start_index - train_indices[-1] - 1
        if (
            type(item.get("actual_purge_trading_days")) is not int
            or item.get("actual_purge_trading_days") != actual_purge
            or actual_purge < 60
        ):
            raise CurrentRestatedResearchError("qualified fold does not prove 60 actual purge sessions")
        actual_embargo = item.get("actual_embargo_trading_days")
        if type(actual_embargo) is not int or actual_embargo < 5:
            raise CurrentRestatedResearchError("qualified fold does not prove 5 embargo sessions")
        if previous_test_end is None:
            if item.get("embargo_verification_basis") != "public_direct_loader_verified_initial_fold_policy":
                raise CurrentRestatedResearchError("first fold lacks the Direct-loader verified embargo basis")
        else:
            calendar_gap = start_index - previous_test_end - 1
            if (
                item.get("embargo_verification_basis") != "complete_verified_calendar_between_test_windows"
                or actual_embargo != calendar_gap
                or calendar_gap < 5
            ):
                raise CurrentRestatedResearchError("qualified fold embargo differs from full calendar dates")
        previous_test_end = end_index
        mature_count = item.get("mature_train_date_count")
        test_count = item.get("test_date_count")
        if (
            type(mature_count) is not int
            or mature_count < 125
            or mature_count > len(train_indices)
            or type(test_count) is not int
            or test_count != len(test_indices)
            or test_count < 63
        ):
            raise CurrentRestatedResearchError("qualified fold mature train/test counts are insufficient")
        max_label_end = item.get("max_train_label_end_date")
        if type(max_label_end) is not str or _strict_date(
            max_label_end, "qualified_fold.max_train_label_end_date"
        ) >= start_date:
            raise CurrentRestatedResearchError("qualified fold train label reaches its test boundary")
        if end_date < start_date:
            raise CurrentRestatedResearchError("qualified fold date bounds are reversed")

    grouped_raw: dict[str, list[Mapping[str, Any]]] = {}
    for row in raw_fold_rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("fold_id"), str):
            raise CurrentRestatedResearchError("fit audit fold row is malformed")
        grouped_raw.setdefault(str(row["fold_id"]), []).append(row)
    if set(grouped_raw) != set(qualified_by_id):
        raise CurrentRestatedResearchError("fit audit fold qualification does not cover every fitted fold")
    for fold_id, rows in grouped_raw.items():
        qualified = qualified_by_id[fold_id]
        for row in rows:
            if (
                row.get("label_head") != "benchmark_excess_return_bp"
                or row.get("preprocessing_fit_scope") != "fold-local-training-rows-only"
                or row.get("purge_trading_days") != 60
                or row.get("embargo_trading_days") != 5
                or row.get("training_mature_date_count") != qualified.get("mature_train_date_count")
                or row.get("test_date_count") != qualified.get("test_date_count")
            ):
                raise CurrentRestatedResearchError("fitted fold audit disagrees with actual qualification")


def _verify_model_fit_clocks(manifest: Mapping[str, Any], audit: Mapping[str, Any]) -> None:
    fit_cutoff = _aware_iso(str(manifest.get("training_as_of")), "manifest.training_as_of")
    audit_cutoff = _aware_iso(str(audit.get("training_as_of")), "fit_audit.training_as_of")
    fit_completed = _aware_iso(str(manifest.get("fit_completed_at")), "manifest.fit_completed_at")
    model_available = _aware_iso(str(manifest.get("model_available_at")), "manifest.model_available_at")
    if audit_cutoff != fit_cutoff or fit_completed < fit_cutoff or model_available != fit_completed:
        raise CurrentRestatedResearchError("manifest and audit fit clocks are inconsistent")
    execution = manifest.get("fit_execution")
    if not isinstance(execution, dict):
        raise CurrentRestatedResearchError("fit execution receipt is missing")
    if (
        execution.get("fit_cutoff") != fit_cutoff.isoformat()
        or execution.get("started_or_frozen_at") != fit_cutoff.isoformat()
    ):
        raise CurrentRestatedResearchError("fit execution receipt clock differs from the fit cutoff")
    process_id = execution.get("process_id")
    argv = execution.get("argv")
    if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0:
        raise CurrentRestatedResearchError("fit process identity is invalid")
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
        raise CurrentRestatedResearchError("fit invocation receipt is invalid")


def _verify_input_file_pin(pin: CurrentRestatedInputFilePin) -> dict[str, Any]:
    if type(pin) is not CurrentRestatedInputFilePin:
        raise CurrentRestatedResearchError("input file pin must be emitted as a typed Direct pin")
    path = _verified_research_path(Path(pin.path))
    stat_result = path.stat()
    if isinstance(pin.bytes, bool) or not isinstance(pin.bytes, int) or pin.bytes < 0 or stat_result.st_size != pin.bytes:
        raise CurrentRestatedResearchError("Direct input byte count differs from its pin")
    actual_sha = _sha256_file(path)
    if actual_sha != _plain_sha256(pin.sha256, "input_file_pin.sha256"):
        raise CurrentRestatedResearchError("Direct input actual-byte hash differs from its pin")
    if not pin.role.strip():
        raise CurrentRestatedResearchError("Direct input role is required")
    return {"role": pin.role, "path": str(path), "bytes": pin.bytes, "sha256": actual_sha}


def _verified_research_file(path: Path, expected_sha256: str, *, role: str) -> dict[str, Any]:
    resolved = _verified_research_path(path)
    stat_result = resolved.stat()
    actual_sha = _sha256_file(resolved)
    if actual_sha != _plain_sha256(expected_sha256, role):
        raise CurrentRestatedResearchError(f"{role} actual-byte hash differs from expected pin")
    return {"role": role, "path": str(resolved), "bytes": stat_result.st_size, "sha256": actual_sha}


def _verified_research_path(path: Path) -> Path:
    resolved = resolve_ml_research_output_path(path, access="read")
    if resolved.is_symlink() or not resolved.is_file() or resolved.resolve(strict=True) != resolved:
        raise CurrentRestatedResearchError("Direct input must be a regular file below output/ml_research")
    return resolved


def _read_verified_child(root: Path, entry: Mapping[str, Any]) -> bytes:
    filename = entry.get("filename")
    if filename not in {"models.joblib", "feature_registry.json", "fit_audit.json"}:
        raise CurrentRestatedResearchError("manifest artifact filename is not allowlisted")
    path = root / str(filename)
    if filename == "fit_audit.json":
        return _read_bounded_fit_audit_bytes(
            path,
            expected_bytes=entry.get("bytes"),
            expected_sha256=entry.get("sha256"),
            label="model fit audit",
        )
    if path.is_symlink() or not path.is_file() or path.resolve(strict=True) != path:
        raise CurrentRestatedResearchError("model artifact file is missing or not regular")
    raw = path.read_bytes()
    if len(raw) != entry.get("bytes") or sha256(raw).hexdigest() != entry.get("sha256"):
        raise CurrentRestatedResearchError(f"model artifact hash or size mismatch: {filename}")
    return raw


def _read_verified_current_vector(path: Path, descriptor: Mapping[str, Any]) -> bytes:
    if path.is_symlink() or not path.is_file() or path.resolve(strict=True) != path:
        raise CurrentRestatedResearchError("saved current vector is missing or not regular")
    raw = path.read_bytes()
    expected_bytes = descriptor.get("bytes")
    expected_sha = descriptor.get("sha256")
    if (
        type(expected_bytes) is not int
        or len(raw) != expected_bytes
        or sha256(raw).hexdigest() != _plain_sha256(expected_sha, "current vector SHA")
    ):
        raise CurrentRestatedResearchError("saved current vector size or bytes SHA mismatch")
    return raw


def _normalize_code_pins(value: Any) -> Mapping[str, str]:
    pins = _mapping(value, "code_pins")
    expected = {
        "ml_module/current_restated_research_bridge.py",
        "ml_module/allocation_training_service.py",
        "ml_module/historical_feature_builder.py",
        "ml_module/feature_registry.py",
        "ml_module/model_artifact_loader.py",
        "data_module/ml_daily_price_revision_gate.py",
        "data_module/portfolio_ml_current_restated_outcome_store.py",
        "data_module/ml_pit_year_shard_exporter.py",
        "data_module/portfolio_ml_dataset_assembler.py",
        "data_module/ml_historical_snapshot_provider.py",
        "data_module/ml_price_availability_contract.py",
        "data_module/portfolio_ml_direct_numeric_store.py",
        "data_module/ml_research_direct_ooc_adapter.py",
        "scripts/train_bounded_restated_research.py",
    }
    if set(pins) != expected:
        raise CurrentRestatedResearchError("training code pin inventory is incomplete")
    normalized: dict[str, str] = {}
    for path, digest in pins.items():
        normalized[str(path)] = _plain_sha256(digest, f"code_pins.{path}")
    return MappingProxyType(normalized)


def _plain_sha256(value: Any, field: str) -> str:
    if isinstance(value, str) and value.startswith("sha256:"):
        value = value[7:]
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise CurrentRestatedResearchError(f"{field} must be a lowercase SHA-256")
    return value


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            _plain_json(value, "JSON payload"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CurrentRestatedResearchError("payload is not canonical finite JSON") from exc


def _plain_json(value: Any, field: str) -> Any:
    if value is None or type(value) in {str, int, bool}:
        return value
    if isinstance(value, float):
        raise CurrentRestatedResearchError(f"{field} cannot contain naked float values")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CurrentRestatedResearchError(f"{field} datetime must be aware")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise CurrentRestatedResearchError(f"{field} mapping keys must be strings")
        return {key: _plain_json(item, f"{field}.{key}") for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_json(item, f"{field}[{index}]") for index, item in enumerate(value)]
    raise CurrentRestatedResearchError(f"{field} contains unsupported JSON type {type(value).__name__}")


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise CurrentRestatedResearchError(f"{field} must be a string-keyed object")
    return value


def _write_create_only(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _quantize_model_bp(value: float) -> int:
    if not np.isfinite(value):
        raise CurrentRestatedResearchError("model prediction must be finite")
    rounded = int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return max(-10_000, min(10_000, rounded))
