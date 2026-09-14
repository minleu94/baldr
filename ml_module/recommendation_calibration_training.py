"""受控推薦校準候選的可重跑訓練與 shadow inference artifact。

這個模組只處理「可在當時取得的 feature」與已成熟的絕對報酬 label。它不
修改正式資料庫、不授權下單，也不把 benchmark-relative return 偷換成推薦
校準目標：

* ``upside`` = forward stock return > 0；
* ``after_cost_profit`` = forward stock return > 固定 round-trip cost +
  當時可取得的 observed liquidity cost。

模型 fitting 內部使用 sklearn 的浮點數是明確隔離的分析邊界；輸出的機率、
報酬排序、成本與所有可持久化數值一律回到 integer basis points。候選 artifact
永遠保持 ``shadow_only``，只有外部 promotion authority 通過後才可由可選的
consumer projection 讀取，且不會改變正式 rule path。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from io import BytesIO
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import joblib
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml_module.model_artifact_manifest import FeatureSchema, ModelArtifactManifest
from ml_module.probability_calibration import FittedShadowProbabilityCalibrator, ShadowProbabilityCalibrator
from ml_module.purged_walk_forward import MLTimeWindowRow, PurgedWalkForwardFold, PurgedWalkForwardSplitter
from ml_module.recommendation_probability_transform import (
    AFTER_COST_DECLARED_BASELINE_ID,
    AFTER_COST_NULL_BENCHMARK_BASELINE_ID,
    AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP,
    NULL_BENCHMARK_BASELINE_ID,
)


RECOMMENDATION_LABEL_CONTRACT_ID = "recommendation-absolute-labels-v1"
RECOMMENDATION_LABEL_DEFINITIONS: Mapping[str, str] = {
    "upside": "absolute forward stock return over 20 trading days > 0 bp",
    "after_cost_profit": (
        "absolute forward stock return over 20 trading days > fixed round-trip "
        "cost bp + observed liquidity cost bp; missing liquidity cost stays missing"
    ),
}
RECOMMENDATION_HORIZON_TRADING_DAYS = 20


def recommendation_label_registry_hash() -> str:
    """Return the stable hash for the two absolute recommendation labels."""

    payload = {
        "registry_id": RECOMMENDATION_LABEL_CONTRACT_ID,
        "horizon_trading_days": RECOMMENDATION_HORIZON_TRADING_DAYS,
        "definitions": dict(RECOMMENDATION_LABEL_DEFINITIONS),
        "missing_policy": "pending_is_not_zero",
        "benchmark_role": "evaluation_context_only_not_target",
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def feature_schema_hash(feature_schema: FeatureSchema) -> str:
    """Hash the exact id/dtype/unit schema consumed by a candidate."""

    return _hash_payload({"feature_schema": [list(item) for item in feature_schema]})


def recommendation_cost_contract_hash(
    fixed_round_trip_cost_bp: int,
    horizon_trading_days: int = RECOMMENDATION_HORIZON_TRADING_DAYS,
) -> str:
    """Hash the fixed cost contract; observed liquidity remains a required row field."""

    if horizon_trading_days != RECOMMENDATION_HORIZON_TRADING_DAYS:
        raise ValueError("recommendation calibration horizon is locked to 20 trading days")
    return _hash_payload(
        {
            "fixed_round_trip_cost_bp": fixed_round_trip_cost_bp,
            "observed_liquidity_cost_required": True,
            "after_cost_baseline_contract": "independent_null_benchmark_v1",
            "after_cost_null_benchmark_baseline_id": AFTER_COST_NULL_BENCHMARK_BASELINE_ID,
            "after_cost_null_benchmark_probability_bp": AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP,
            "horizon_trading_days": horizon_trading_days,
        }
    )


@dataclass(frozen=True)
class RecommendationCalibrationSample:
    """一筆 point-in-time recommendation training row。

    ``benchmark_return_bp`` 僅用作同日評估內容，不參與兩個校準 target。
    """

    row_id: str
    symbol: str
    decision_date: str
    feature_as_of_date: str
    feature_available_date: str
    label_end_date: str
    label_available_date: str
    feature_values: tuple[int | None, ...]
    stock_return_bp: int
    benchmark_return_bp: int
    fixed_round_trip_cost_bp: int
    observed_liquidity_cost_bp: int | None
    rule_probability_bp: int
    upside_label: int
    after_cost_profit_label: int | None
    rule_after_cost_probability_bp: int | None = None
    rule_after_cost_baseline_id: str | None = None
    rule_baseline_id: str = NULL_BENCHMARK_BASELINE_ID
    source_quality: str = "research"

    def __post_init__(self) -> None:
        decision = _date(self.decision_date)
        feature_as_of = _date(self.feature_as_of_date)
        feature_available = _date(self.feature_available_date)
        label_end = _date(self.label_end_date)
        label_available = _date(self.label_available_date)
        if feature_as_of >= decision:
            raise ValueError("feature_as_of_date must be before decision_date")
        if feature_available > decision:
            raise ValueError("feature_available_date must not be later than decision_date")
        if label_end < decision or label_available < label_end:
            raise ValueError("label dates must mature after decision_date")
        if not self.row_id.strip() or not self.symbol.strip():
            raise ValueError("row_id and symbol are required")
        if not self.rule_baseline_id.strip():
            raise ValueError("rule_baseline_id is required")
        if isinstance(self.fixed_round_trip_cost_bp, bool) or self.fixed_round_trip_cost_bp < 0:
            raise ValueError("fixed_round_trip_cost_bp must be a non-negative integer")
        for field_name, value in {
            "upside_label": self.upside_label,
            "after_cost_profit_label": self.after_cost_profit_label,
        }.items():
            if value is not None and (isinstance(value, bool) or value not in (0, 1)):
                raise ValueError(f"{field_name} must be 0, 1, or None")
        if not 0 <= self.rule_probability_bp <= 10_000:
            raise ValueError("rule_probability_bp must be within 0..10000 bp")
        # The after-cost target has an independent baseline contract.  When a
        # traceable liquidity cost makes the target observable, an omitted
        # baseline means the explicit after-cost null benchmark—not the
        # upside baseline—is used.  A non-null caller-supplied probability is
        # retained as a named declared baseline for compatibility.
        if self.observed_liquidity_cost_bp is not None and self.after_cost_profit_label is not None:
            after_cost_probability_was_missing = self.rule_after_cost_probability_bp is None
            if self.rule_after_cost_probability_bp is None:
                object.__setattr__(
                    self,
                    "rule_after_cost_probability_bp",
                    AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP,
                )
            if self.rule_after_cost_baseline_id is None:
                object.__setattr__(
                    self,
                    "rule_after_cost_baseline_id",
                    (
                        AFTER_COST_NULL_BENCHMARK_BASELINE_ID
                        if after_cost_probability_was_missing
                        else AFTER_COST_DECLARED_BASELINE_ID
                    ),
                )
        if self.rule_after_cost_probability_bp is not None and not 0 <= self.rule_after_cost_probability_bp <= 10_000:
            raise ValueError("rule_after_cost_probability_bp must be within 0..10000 bp")
        if self.rule_after_cost_baseline_id is not None:
            if not self.rule_after_cost_baseline_id.strip():
                raise ValueError("rule_after_cost_baseline_id must not be empty")
            if (
                self.rule_after_cost_baseline_id == AFTER_COST_NULL_BENCHMARK_BASELINE_ID
                and self.rule_after_cost_probability_bp != AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP
            ):
                raise ValueError("after-cost null benchmark probability must be 5000 bp")
        expected_upside = int(self.stock_return_bp > 0)
        if self.upside_label != expected_upside:
            raise ValueError("upside_label must use absolute stock return > 0")
        if self.observed_liquidity_cost_bp is None:
            if self.after_cost_profit_label is not None:
                raise ValueError("after_cost_profit_label must be missing when liquidity cost is missing")
        else:
            if self.observed_liquidity_cost_bp < 0:
                raise ValueError("observed_liquidity_cost_bp must be non-negative")
            expected_after_cost = int(
                self.stock_return_bp
                > self.fixed_round_trip_cost_bp + self.observed_liquidity_cost_bp
            )
            if self.after_cost_profit_label != expected_after_cost:
                raise ValueError("after_cost_profit_label must use absolute return after cost")

    @classmethod
    def from_forward_return(
        cls,
        *,
        row_id: str,
        symbol: str,
        decision_date: str,
        feature_as_of_date: str,
        feature_available_date: str,
        label_end_date: str,
        label_available_date: str,
        feature_values: tuple[int | None, ...],
        stock_return_bp: int,
        benchmark_return_bp: int,
        fixed_round_trip_cost_bp: int,
        observed_liquidity_cost_bp: int | None,
        rule_probability_bp: int,
        rule_after_cost_probability_bp: int | None = None,
        rule_after_cost_baseline_id: str | None = None,
        rule_baseline_id: str = NULL_BENCHMARK_BASELINE_ID,
        source_quality: str = "research",
    ) -> "RecommendationCalibrationSample":
        after_cost = None
        if observed_liquidity_cost_bp is not None:
            after_cost = int(
                stock_return_bp
                > fixed_round_trip_cost_bp + observed_liquidity_cost_bp
            )
        return cls(
            row_id=row_id,
            symbol=symbol,
            decision_date=decision_date,
            feature_as_of_date=feature_as_of_date,
            feature_available_date=feature_available_date,
            label_end_date=label_end_date,
            label_available_date=label_available_date,
            feature_values=feature_values,
            stock_return_bp=stock_return_bp,
            benchmark_return_bp=benchmark_return_bp,
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
            observed_liquidity_cost_bp=observed_liquidity_cost_bp,
            rule_probability_bp=rule_probability_bp,
            rule_after_cost_probability_bp=rule_after_cost_probability_bp,
            rule_after_cost_baseline_id=rule_after_cost_baseline_id,
            rule_baseline_id=rule_baseline_id,
            upside_label=int(stock_return_bp > 0),
            after_cost_profit_label=after_cost,
            source_quality=source_quality,
        )


@dataclass(frozen=True)
class RecommendationCalibrationTrainingConfig:
    """可審核的訓練邊界；promotion threshold 不在此處偷偷調整。"""

    minimum_training_rows: int = 20
    minimum_fold_train_rows: int = 10
    minimum_calibration_samples: int = 20
    minimum_train_dates: int = 30
    test_date_count: int = 5
    purge_trading_days: int = 20
    embargo_trading_days: int = 0
    random_state: int = 42
    horizon_trading_days: int = RECOMMENDATION_HORIZON_TRADING_DAYS

    def __post_init__(self) -> None:
        for field_name in (
            "minimum_training_rows",
            "minimum_fold_train_rows",
            "minimum_calibration_samples",
            "minimum_train_dates",
            "test_date_count",
            "horizon_trading_days",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or value <= 0:
                raise ValueError(f"{field_name} must be positive")
        if self.minimum_calibration_samples < 10:
            raise ValueError("minimum_calibration_samples must be at least ten")
        if self.purge_trading_days < 0 or self.embargo_trading_days < 0:
            raise ValueError("purge and embargo days must be non-negative")
        if self.horizon_trading_days != RECOMMENDATION_HORIZON_TRADING_DAYS:
            raise ValueError("recommendation calibration horizon is locked to 20 trading days")


@dataclass(frozen=True)
class RecommendationPrediction:
    ranking_score_bp: int
    calibrated_probability_bp: int | None
    after_cost_profit_probability_bp: int | None
    calibrated_probability_status: str
    after_cost_profit_probability_status: str
    model_id: str
    dataset_id: str
    training_as_of: str
    horizon_trading_days: int
    sample_size: int
    source: str = "shadow_candidate"


@dataclass
class RunnableRecommendationCalibrationModel:
    """可由 candidate pointer 載入的完整模型，不是只存 method/hash。"""

    model_id: str
    dataset_id: str
    model_family: str
    feature_names: tuple[str, ...]
    feature_schema: FeatureSchema
    training_as_of: str
    horizon_trading_days: int
    training_row_count: int
    return_model: Any
    upside_model: Any
    after_cost_model: Any | None
    upside_calibrator: FittedShadowProbabilityCalibrator
    after_cost_calibrator: FittedShadowProbabilityCalibrator | None
    calibration_sample_count: int
    after_cost_calibration_sample_count: int
    rule_baseline_id: str
    after_cost_baseline_id: str | None = None
    shadow_only: bool = True
    production_eligible: bool = False
    production_action_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.shadow_only or self.production_eligible or self.production_action_allowed:
            raise ValueError("recommendation calibration model must remain shadow-only")
        if len(self.feature_names) != len(self.feature_schema):
            raise ValueError("feature names and schema length mismatch")

    def predict(self, feature_values: Sequence[int | None]) -> RecommendationPrediction:
        if len(feature_values) != len(self.feature_names):
            raise ValueError("feature vector does not match persisted feature schema")
        matrix = _matrix_from_values(feature_values)
        # numeric-boundary: sklearn inference uses floats; public output is integer bp.
        return_prediction = self.return_model.predict(matrix)[0]
        upside_raw = self.upside_model.predict_proba(matrix)[0][1]
        upside_probability = _calibrated_bp(self.upside_calibrator, upside_raw)
        after_probability: int | None = None
        after_status = "unavailable"
        if self.after_cost_model is not None and self.after_cost_calibrator is not None:
            after_raw = self.after_cost_model.predict_proba(matrix)[0][1]
            after_probability = _calibrated_bp(self.after_cost_calibrator, after_raw)
            after_status = "shadow_candidate"
        return RecommendationPrediction(
            ranking_score_bp=_bounded_int(round(float(return_prediction)), -2_147_483_648, 2_147_483_647),
            calibrated_probability_bp=upside_probability,
            after_cost_profit_probability_bp=after_probability,
            calibrated_probability_status="shadow_candidate",
            after_cost_profit_probability_status=after_status,
            model_id=self.model_id,
            dataset_id=self.dataset_id,
            training_as_of=self.training_as_of,
            horizon_trading_days=self.horizon_trading_days,
            sample_size=self.training_row_count,
        )

    def predict_shadow_bp(self, feature_values: Sequence[int | None]) -> int:
        """Compatibility hook for existing shadow model consumers."""

        return self.predict(feature_values).ranking_score_bp


@dataclass(frozen=True)
class RecommendationCalibrationTrainingResult:
    candidate_id: str
    dataset_id: str
    dataset_hash: str
    model: RunnableRecommendationCalibrationModel
    manifest: ModelArtifactManifest
    artifact_bytes: bytes
    artifact_hash: str
    fold_ids: tuple[str, ...]
    calibration_fold_ids: tuple[str, ...]
    evaluation_fold_id: str
    evaluation: Mapping[str, Any]
    target_definitions: Mapping[str, str]
    fixed_round_trip_cost_bp: int
    liquidity_cost_coverage: str
    training_data_eligible: bool = True
    forward_evidence_eligible: bool = False
    formal_candidate_eligible: bool = False
    candidate_blockers: tuple[str, ...] = (
        "training_artifact_is_shadow_only",
        "natural_forward_evidence_must_be_supplied_to_authority",
    )
    prospective_source_contract_ready: bool = False
    prospective_price_up_promotion_ready: bool = False
    historical_replay_candidate_blockers: tuple[str, ...] = ()
    after_cost_blockers: tuple[str, ...] = ()
    actual_execution_blockers: tuple[str, ...] = ()
    lane_status: Mapping[str, Any] = field(default_factory=dict)

    @property
    def training_row_count(self) -> int:
        return self.model.training_row_count

    @property
    def calibration_gap_bp(self) -> int:
        return int(self.evaluation.get("calibrated_probability_gap_bp", 0))

    def persist(self, candidate_root: str | Path) -> Path:
        """Create an immutable candidate directory and return its path."""

        root = Path(candidate_root).resolve()
        if root.exists() and any(root.iterdir()):
            raise FileExistsError(f"candidate directory already contains files: {root}")
        root.mkdir(parents=True, exist_ok=True)
        (root / self.manifest.artifact_filename).write_bytes(self.artifact_bytes)
        _write_json(root / "manifest.json", self.manifest.to_dict())
        _write_json(root / "candidate.json", self.to_dict())
        return root

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "recommendation-calibration-candidate.v1",
            "candidate_id": self.candidate_id,
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "model_id": self.model.model_id,
            "model_version": self.model.model_id,
            "model_family": self.model.model_family,
            "feature_names": list(self.model.feature_names),
            "feature_schema": [list(item) for item in self.model.feature_schema],
            "feature_registry_hash": self.manifest.feature_registry_hash,
            "feature_schema_hash": feature_schema_hash(self.model.feature_schema),
            "label_registry_hash": self.manifest.label_registry_hash,
            "training_as_of": self.model.training_as_of,
            "horizon_trading_days": self.model.horizon_trading_days,
            "training_row_count": self.model.training_row_count,
            "calibration_sample_count": self.model.calibration_sample_count,
            "after_cost_calibration_sample_count": self.model.after_cost_calibration_sample_count,
            "calibration_gap_bp": self.calibration_gap_bp,
            "fold_ids": list(self.fold_ids),
            "calibration_fold_ids": list(self.calibration_fold_ids),
            "evaluation_fold_id": self.evaluation_fold_id,
            "evaluation": dict(self.evaluation),
            "target_definitions": dict(self.target_definitions),
            "benchmark_role": "same-date evaluation context only; not a target",
            "fixed_round_trip_cost_bp": self.fixed_round_trip_cost_bp,
            "cost_contract_hash": recommendation_cost_contract_hash(
                self.fixed_round_trip_cost_bp,
                self.model.horizon_trading_days,
            ),
            "candidate_frozen_at": self.manifest.created_at,
            "rule_baseline_id": self.model.rule_baseline_id,
            "after_cost_baseline_id": self.model.after_cost_baseline_id,
            "after_cost_baseline_probability_bp": (
                AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP
                if self.model.after_cost_baseline_id == AFTER_COST_NULL_BENCHMARK_BASELINE_ID
                else None
            ),
            "after_cost_baseline_contract": (
                "independent_null_benchmark_v1"
                if self.model.after_cost_baseline_id == AFTER_COST_NULL_BENCHMARK_BASELINE_ID
                else "declared_or_missing"
            ),
            "liquidity_cost_coverage": self.liquidity_cost_coverage,
            "training_data_eligible": self.training_data_eligible,
            "forward_evidence_eligible": self.forward_evidence_eligible,
            "formal_candidate_eligible": self.formal_candidate_eligible,
            "candidate_blockers": list(self.candidate_blockers),
            "prospective_source_contract_ready": self.prospective_source_contract_ready,
            "prospective_price_up_promotion_ready": self.prospective_price_up_promotion_ready,
            "historical_replay_candidate_blockers": list(self.historical_replay_candidate_blockers),
            "after_cost_blockers": list(self.after_cost_blockers),
            "actual_execution_blockers": list(self.actual_execution_blockers),
            "lane_status": dict(self.lane_status),
            "shadow_only": True,
            "production_eligible": False,
            "production_action_allowed": False,
            "artifact_hash": self.artifact_hash,
            "manifest_hash": self.manifest.manifest_hash,
            "candidate_freeze_hash": candidate_freeze_hash(
                candidate_id=self.candidate_id,
                dataset_hash=self.dataset_hash,
                manifest_hash=self.manifest.manifest_hash,
                artifact_hash=self.artifact_hash,
                evaluation=self.evaluation,
            ),
        }


class RecommendationCalibrationTrainingService:
    """Train a runnable absolute-label candidate with purged OOF calibration."""

    MODEL_FAMILY = "recommendation_absolute_calibration_v1"

    def fit(
        self,
        *,
        dataset_id: str,
        dataset_hash: str,
        samples: Sequence[RecommendationCalibrationSample],
        feature_names: tuple[str, ...],
        feature_schema: FeatureSchema,
        feature_registry_hash: str,
        training_as_of: str,
        fixed_round_trip_cost_bp: int,
        dataset_quality: Mapping[str, Any] | None = None,
        created_at: str | None = None,
        config: RecommendationCalibrationTrainingConfig | None = None,
    ) -> RecommendationCalibrationTrainingResult:
        cfg = config or RecommendationCalibrationTrainingConfig()
        ordered = tuple(sorted(samples, key=lambda row: (row.decision_date, row.row_id)))
        if len(ordered) < cfg.minimum_training_rows:
            raise ValueError("insufficient recommendation calibration training rows")
        if not feature_names or len(feature_names) != len(feature_schema):
            raise ValueError("feature_names and feature_schema are required and aligned")
        if any(len(row.feature_values) != len(feature_names) for row in ordered):
            raise ValueError("sample feature vector does not match feature schema")
        cutoff = _date(training_as_of)
        eligible = tuple(
            row
            for row in ordered
            if _date(row.decision_date) <= cutoff and _date(row.label_available_date) <= cutoff
        )
        if len(eligible) < cfg.minimum_training_rows:
            raise ValueError("insufficient rows mature by training_as_of")
        if any(row.fixed_round_trip_cost_bp != fixed_round_trip_cost_bp for row in eligible):
            raise ValueError("fixed cost contract changed inside one dataset")
        baseline_ids = {row.rule_baseline_id for row in eligible}
        if len(baseline_ids) != 1:
            raise ValueError("one dataset must use one predeclared rule probability baseline")
        after_cost_baseline_ids = {
            row.rule_after_cost_baseline_id
            for row in eligible
            if row.after_cost_profit_label is not None
        }
        if len(after_cost_baseline_ids) > 1:
            raise ValueError("one dataset must use one predeclared after-cost probability baseline")

        windows = tuple(
            MLTimeWindowRow(row.row_id, row.decision_date, row.label_end_date)
            for row in eligible
        )
        splitter = PurgedWalkForwardSplitter(
            minimum_train_dates=cfg.minimum_train_dates,
            test_date_count=cfg.test_date_count,
            purge_trading_days=cfg.purge_trading_days,
            embargo_trading_days=cfg.embargo_trading_days,
        )
        folds = splitter.split(windows)
        usable = tuple(
            fold
            for fold in folds
            if len(
                tuple(
                    row
                    for row in _rows_for_ids(eligible, fold.train_rows)
                    if _date(row.label_available_date) < _date(fold.test_start)
                )
            ) >= cfg.minimum_fold_train_rows
            and _has_two_classes(
                tuple(
                    row
                    for row in _rows_for_ids(eligible, fold.train_rows)
                    if _date(row.label_available_date) < _date(fold.test_start)
                ),
                "upside_label",
            )
        )
        if len(usable) < 3:
            raise ValueError("at least three usable purged folds are required")
        by_id = {row.row_id: row for row in eligible}
        evaluation_fold = usable[-1]
        calibration_folds = usable[:-1]
        oof_upside: list[tuple[float, int, str, RecommendationCalibrationSample]] = []
        oof_after: list[tuple[float, int, str, RecommendationCalibrationSample]] = []
        split_diagnostics: dict[str, dict[str, Any]] = {}
        evaluation_cutoff = _date(evaluation_fold.test_start)
        for fold in calibration_folds:
            train_rows = tuple(
                by_id[row.row_id]
                for row in fold.train_rows
                if row.row_id in by_id
                and _date(by_id[row.row_id].label_available_date) < _date(fold.test_start)
                and _date(by_id[row.row_id].label_available_date) < evaluation_cutoff
            )
            test_rows = tuple(
                by_id[row.row_id]
                for row in fold.test_rows
                if row.row_id in by_id
                and _date(by_id[row.row_id].label_available_date) < evaluation_cutoff
            )
            split_diagnostics[fold.fold_id] = {
                "train": _split_row_diagnostics(train_rows, "upside_label"),
                "test": _split_row_diagnostics(test_rows, "upside_label"),
            }
            if len(train_rows) < cfg.minimum_fold_train_rows or not test_rows:
                continue
            upside_model = _fit_classifier(train_rows, "upside_label", cfg.random_state)
            # numeric-boundary: OOF probabilities are temporary sklearn analytics values.
            upside_probabilities = upside_model.predict_proba(_matrix(test_rows))[:, 1]
            oof_upside.extend(
                (float(probability), row.upside_label, fold.fold_id, row)
                for row, probability in zip(test_rows, upside_probabilities)
            )
            after_rows = tuple(row for row in train_rows if row.after_cost_profit_label is not None)
            after_test_rows = tuple(row for row in test_rows if row.after_cost_profit_label is not None)
            if len(after_rows) >= cfg.minimum_fold_train_rows and _has_two_classes(after_rows, "after_cost_profit_label") and after_test_rows:
                fold_after_model = _fit_classifier(after_rows, "after_cost_profit_label", cfg.random_state)
                after_probabilities = fold_after_model.predict_proba(_matrix(after_test_rows))[:, 1]
                for row, probability in zip(after_test_rows, after_probabilities):
                    oof_after.append(
                        (float(probability), _required_int(row.after_cost_profit_label, "after_cost_profit_label"), fold.fold_id, row)
                    )

        if len(oof_upside) < cfg.minimum_calibration_samples or len({item[2] for item in oof_upside}) < 2:
            raise ValueError("insufficient purged OOF samples for upside calibration")
        try:
            upside_calibrator = ShadowProbabilityCalibrator(
                minimum_samples=cfg.minimum_calibration_samples
            ).fit(
                model_id=f"{dataset_id}-upside",
                raw_probabilities=np.asarray([item[0] for item in oof_upside], dtype=float),
                labels=np.asarray([item[1] for item in oof_upside], dtype=int),
                fold_ids=[item[2] for item in oof_upside],
            )
        except ValueError as exc:
            raise ValueError(
                "upside OOF calibration failed: "
                f"{exc}; oof_label_distribution={_label_distribution(item[1] for item in oof_upside)}; "
                f"oof_sample_count={len(oof_upside)}; "
                f"oof_fold_count={len({item[2] for item in oof_upside})}; "
                "split_diagnostics="
                f"{json.dumps({'usable_fold_count': len(usable), 'calibration_fold_count': len(calibration_folds), 'evaluation_fold_id': evaluation_fold.fold_id, 'folds': split_diagnostics}, sort_keys=True, separators=(',', ':'))}"
            ) from exc
        after_calibrator: FittedShadowProbabilityCalibrator | None = None
        if len(oof_after) >= cfg.minimum_calibration_samples and len({item[2] for item in oof_after}) >= 2:
            try:
                after_calibrator = ShadowProbabilityCalibrator(
                    minimum_samples=cfg.minimum_calibration_samples
                ).fit(
                    model_id=f"{dataset_id}-after-cost",
                    raw_probabilities=np.asarray([item[0] for item in oof_after], dtype=float),
                    labels=np.asarray([item[1] for item in oof_after], dtype=int),
                    fold_ids=[item[2] for item in oof_after],
                )
            except ValueError as exc:
                raise ValueError(
                    "after-cost OOF calibration failed: "
                    f"{exc}; oof_label_distribution={_label_distribution(item[1] for item in oof_after)}; "
                    f"oof_sample_count={len(oof_after)}; "
                    f"oof_fold_count={len({item[2] for item in oof_after})}; "
                    "oof_fold_diagnostics="
                    f"{json.dumps(_oof_fold_diagnostics(oof_after, len(usable), evaluation_fold.fold_id, 'after_cost_profit_label'), sort_keys=True, separators=(',', ':'))}"
                ) from exc

        final_train = tuple(
            by_id[row.row_id]
            for row in evaluation_fold.train_rows
            if row.row_id in by_id
            and _date(by_id[row.row_id].label_available_date) < evaluation_cutoff
        )
        if len(final_train) < cfg.minimum_fold_train_rows:
            raise ValueError("evaluation fold has insufficient causal training rows")
        return_model = _fit_return(final_train)
        upside_model = _fit_classifier(final_train, "upside_label", cfg.random_state)
        final_after_rows = tuple(row for row in final_train if row.after_cost_profit_label is not None)
        after_model: Any | None = None
        if after_calibrator is not None and _has_two_classes(final_after_rows, "after_cost_profit_label"):
            after_model = _fit_classifier(final_after_rows, "after_cost_profit_label", cfg.random_state)

        observed_label_dates = [row.label_available_date for row in final_train]
        observed_label_dates.extend(item[3].label_available_date for item in oof_upside)
        observed_label_dates.extend(item[3].label_available_date for item in oof_after)
        train_cutoff = max(observed_label_dates)
        candidate_id = _candidate_id(dataset_id, dataset_hash, train_cutoff, feature_schema)
        model = RunnableRecommendationCalibrationModel(
            model_id=candidate_id,
            dataset_id=dataset_id,
            model_family=self.MODEL_FAMILY,
            feature_names=feature_names,
            feature_schema=feature_schema,
            training_as_of=train_cutoff,
            horizon_trading_days=cfg.horizon_trading_days,
            training_row_count=len(final_train),
            return_model=return_model,
            upside_model=upside_model,
            after_cost_model=after_model,
            upside_calibrator=upside_calibrator,
            after_cost_calibrator=after_calibrator,
            calibration_sample_count=len(oof_upside),
            after_cost_calibration_sample_count=len(oof_after),
            rule_baseline_id=next(iter(baseline_ids)),
            after_cost_baseline_id=(
                next(iter(after_cost_baseline_ids))
                if after_cost_baseline_ids
                else None
            ),
        )
        evaluation_rows = tuple(by_id[row.row_id] for row in evaluation_fold.test_rows if row.row_id in by_id)
        evaluation = _evaluate(model, evaluation_rows)
        artifact_buffer = BytesIO()
        joblib.dump(model, artifact_buffer, compress=0)
        artifact_bytes = artifact_buffer.getvalue()
        artifact_hash = f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}"
        hyperparameters_hash = _hash_payload(
            {
                "model_family": self.MODEL_FAMILY,
                "random_state": cfg.random_state,
                "calibration_method": "isotonic_oof",
                "target_definitions": dict(RECOMMENDATION_LABEL_DEFINITIONS),
            }
        )
        manifest = ModelArtifactManifest.create(
            model_id=candidate_id,
            dataset_id=dataset_id,
            created_run_id=candidate_id,
            created_at=created_at or datetime.now(timezone.utc).isoformat(),
            model_family=self.MODEL_FAMILY,
            feature_registry_hash=feature_registry_hash,
            label_registry_hash=recommendation_label_registry_hash(),
            feature_schema=feature_schema,
            training_as_of=train_cutoff,
            hyperparameters_hash=hyperparameters_hash,
            library_versions=_library_versions(),
            serialization_format="joblib",
            artifact_filename="recommendation_calibration.joblib",
            artifact_hash=artifact_hash,
            blend_selection_metric="untouched_test_brier_bp",
            blend_selection_label_cutoff=train_cutoff,
            blend_selection_threshold_bp=0,
        )
        liquidity_coverage = (
            "observed"
            if all(row.observed_liquidity_cost_bp is not None for row in eligible)
            else "partial_or_missing"
        )
        quality = dict(dataset_quality or {})
        training_data_eligible = quality.get("training_data_eligible", True) is not False
        forward_evidence_eligible = quality.get("forward_evidence_eligible", False) is True
        formal_candidate_eligible = quality.get("formal_candidate_eligible") is True
        prospective_source_contract_ready = quality.get("prospective_source_contract_ready") is True
        prospective_price_up_promotion_ready = (
            quality.get("prospective_price_up_promotion_ready") is True
        )
        candidate_blockers = tuple(
            str(item)
            for item in quality.get("candidate_blockers", ())
            if str(item).strip()
        )
        if not formal_candidate_eligible and not candidate_blockers:
            candidate_blockers = (
                "training_artifact_is_shadow_only",
                "natural_forward_evidence_must_be_supplied_to_authority",
            )
        historical_replay_candidate_blockers = tuple(
            str(item)
            for item in quality.get("historical_replay_candidate_blockers", ())
            if str(item).strip()
        )
        after_cost_blockers = tuple(
            str(item)
            for item in quality.get("after_cost_blockers", ())
            if str(item).strip()
        )
        actual_execution_blockers = tuple(
            str(item)
            for item in quality.get("actual_execution_blockers", ())
            if str(item).strip()
        )
        lane_status_value = quality.get("lane_status")
        lane_status = dict(lane_status_value) if isinstance(lane_status_value, Mapping) else {}
        return RecommendationCalibrationTrainingResult(
            candidate_id=candidate_id,
            dataset_id=dataset_id,
            dataset_hash=dataset_hash,
            model=model,
            manifest=manifest,
            artifact_bytes=artifact_bytes,
            artifact_hash=artifact_hash,
            fold_ids=tuple(fold.fold_id for fold in usable),
            calibration_fold_ids=tuple(fold.fold_id for fold in calibration_folds),
            evaluation_fold_id=evaluation_fold.fold_id,
            evaluation=evaluation,
            target_definitions=RECOMMENDATION_LABEL_DEFINITIONS,
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
            liquidity_cost_coverage=liquidity_coverage,
            training_data_eligible=training_data_eligible,
            forward_evidence_eligible=forward_evidence_eligible,
            formal_candidate_eligible=formal_candidate_eligible,
            candidate_blockers=candidate_blockers,
            prospective_source_contract_ready=prospective_source_contract_ready,
            prospective_price_up_promotion_ready=prospective_price_up_promotion_ready,
            historical_replay_candidate_blockers=historical_replay_candidate_blockers,
            after_cost_blockers=after_cost_blockers,
            actual_execution_blockers=actual_execution_blockers,
            lane_status=lane_status,
        )


def _fit_return(rows: Sequence[RecommendationCalibrationSample]) -> Pipeline:
    # numeric-boundary: model fitting is analytics-only; return is rounded to bp at inference.
    return Pipeline(
        (
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=1.0)),
        )
    ).fit(_matrix(rows), np.asarray([row.stock_return_bp for row in rows], dtype=float))


def _fit_classifier(
    rows: Sequence[RecommendationCalibrationSample],
    label_name: str,
    random_state: int,
) -> Pipeline:
    labels = [getattr(row, label_name) for row in rows]
    if any(label is None for label in labels) or not _has_two_classes(rows, label_name):
        raise ValueError(f"{label_name} requires two non-missing classes")
    # numeric-boundary: sklearn classifier fitting is isolated from financial units.
    return Pipeline(
        (
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(C=1.0, max_iter=500, random_state=random_state),
            ),
        )
    ).fit(_matrix(rows), np.asarray(labels, dtype=int))


def _evaluate(
    model: RunnableRecommendationCalibrationModel,
    rows: Sequence[RecommendationCalibrationSample],
) -> dict[str, Any]:
    if not rows:
        raise ValueError("untouched evaluation fold is empty")
    predictions = [model.predict(row.feature_values) for row in rows]
    new_probabilities = [
        prediction.calibrated_probability_bp
        for prediction in predictions
        if prediction.calibrated_probability_bp is not None
    ]
    if len(new_probabilities) != len(rows):
        raise ValueError("upside inference unexpectedly missing on evaluation fold")
    old_probabilities = [row.rule_probability_bp for row in rows]
    labels = [row.upside_label for row in rows]
    new_brier = _brier_bp(new_probabilities, labels)
    old_brier = _brier_bp(old_probabilities, labels)
    new_gap = _calibration_gap_bp(new_probabilities, labels)
    old_gap = _calibration_gap_bp(old_probabilities, labels)
    after_rows = tuple(
        (row, prediction.after_cost_profit_probability_bp)
        for row, prediction in zip(rows, predictions)
        if row.after_cost_profit_label is not None and prediction.after_cost_profit_probability_bp is not None
    )
    after_brier: int | None = None
    after_old_brier: int | None = None
    after_improvement: int | None = None
    after_gap: int | None = None
    after_old_gap: int | None = None
    after_count = len(after_rows)
    after_status = "missing_candidate_or_label" if not after_rows else "observed"
    if after_rows:
        after_probabilities = [item[1] for item in after_rows]
        after_labels = [_required_int(item[0].after_cost_profit_label, "after_cost_profit_label") for item in after_rows]
        after_brier = _brier_bp(after_probabilities, after_labels)
        after_gap = _calibration_gap_bp(after_probabilities, after_labels)
        old_after_rows = tuple(
            item
            for item in after_rows
            if item[0].rule_after_cost_probability_bp is not None
        )
        if len(old_after_rows) == len(after_rows):
            after_old_probabilities = [
                _required_int(item[0].rule_after_cost_probability_bp, "rule_after_cost_probability_bp") for item in old_after_rows
            ]
            after_old_brier = _brier_bp(after_old_probabilities, after_labels)
            after_old_gap = _calibration_gap_bp(after_old_probabilities, after_labels)
            after_improvement = after_old_brier - after_brier
        else:
            after_status = "old_baseline_missing_fail_closed"
    return {
        "untouched_test_sample_count": len(rows),
        "old_brier_bp": old_brier,
        "new_brier_bp": new_brier,
        "brier_improvement_bp": old_brier - new_brier,
        "old_calibrated_probability_gap_bp": old_gap,
        "calibrated_probability_gap_bp": new_gap,
        "after_cost_untouched_test_sample_count": after_count,
        "after_cost_old_brier_bp": after_old_brier,
        "after_cost_new_brier_bp": after_brier,
        "after_cost_brier_improvement_bp": after_improvement,
        "after_cost_old_calibrated_probability_gap_bp": after_old_gap,
        "after_cost_calibrated_probability_gap_bp": after_gap,
        "after_cost_evaluation_status": after_status,
        "after_cost_baseline_id": model.after_cost_baseline_id,
        "after_cost_baseline_probability_bp": (
            AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP
            if model.after_cost_baseline_id == AFTER_COST_NULL_BENCHMARK_BASELINE_ID
            else None
        ),
        "rule_baseline_id": model.rule_baseline_id,
        "evaluation_sample_fingerprint": _hash_payload(
            {
                "row_ids": [row.row_id for row in rows],
                "decision_dates": [row.decision_date for row in rows],
                "label_end_dates": [row.label_end_date for row in rows],
                "fixed_round_trip_cost_bp": [row.fixed_round_trip_cost_bp for row in rows],
                "horizon_trading_days": model.horizon_trading_days,
            }
        ),
        "cost_contract_hash": recommendation_cost_contract_hash(
            rows[0].fixed_round_trip_cost_bp,
            model.horizon_trading_days,
        ) if len({row.fixed_round_trip_cost_bp for row in rows}) == 1 else None,
        "candidate_prediction_hash": _hash_payload(
            {
                "row_ids": [row.row_id for row in rows],
                "probabilities_bp": new_probabilities,
                "labels": labels,
            }
        ),
        "rule_prediction_hash": _hash_payload(
            {
                "row_ids": [row.row_id for row in rows],
                "probabilities_bp": old_probabilities,
                "labels": labels,
                "baseline_id": model.rule_baseline_id,
            }
        ),
    }


def _matrix(rows: Sequence[RecommendationCalibrationSample]) -> np.ndarray:
    return _matrix_from_values(row.feature_values for row in rows)


def _matrix_from_values(values: Iterable[Sequence[int | None]] | Sequence[int | None]) -> np.ndarray:
    if values and isinstance(values, Sequence) and values and not isinstance(values[0], (tuple, list)):
        rows: Iterable[Sequence[int | None]] = (values,)  # type: ignore[assignment]
    else:
        rows = values  # type: ignore[assignment]
    # numeric-boundary: sklearn accepts NaN float matrices; missing is never replaced by zero.
    return np.asarray(
        [[np.nan if value is None else value for value in row] for row in rows],
        dtype=float,
    )


def _calibrated_bp(
    calibrator: FittedShadowProbabilityCalibrator,
    raw_probability: float,
) -> int:
    value = calibrator.predict(np.asarray([raw_probability], dtype=float))[0]
    return _bounded_int(round(float(value) * 10_000), 0, 10_000)


def _brier_bp(probabilities: Sequence[int | None], labels: Sequence[int]) -> int:
    values = [probability for probability in probabilities if probability is not None]
    if len(values) != len(labels) or not values:
        raise ValueError("probability and label lengths must match")
    return sum((probability - label * 10_000) ** 2 for probability, label in zip(values, labels)) // (
        len(values) * 10_000
    )


def _calibration_gap_bp(probabilities: Sequence[int | None], labels: Sequence[int]) -> int:
    values = [probability for probability in probabilities if probability is not None]
    if len(values) != len(labels) or not values:
        raise ValueError("probability and label lengths must match")
    mean_probability = sum(values) // len(values)
    mean_label = sum(labels) * 10_000 // len(labels)
    return abs(mean_probability - mean_label)


def _has_two_classes(rows: Sequence[RecommendationCalibrationSample], label_name: str) -> bool:
    values = {getattr(row, label_name) for row in rows if getattr(row, label_name) is not None}
    return values == {0, 1}


def _label_distribution(values: Iterable[int | None]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = "missing" if value is None else str(int(value))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _date_window(rows: Sequence[RecommendationCalibrationSample], field_name: str) -> dict[str, str | None]:
    values = sorted(str(getattr(row, field_name))[:10] for row in rows)
    return {
        "start": values[0] if values else None,
        "end": values[-1] if values else None,
    }


def _split_row_diagnostics(
    rows: Sequence[RecommendationCalibrationSample],
    label_name: str,
) -> dict[str, Any]:
    return {
        "sample_count": len(rows),
        "label_distribution": _label_distribution(getattr(row, label_name, None) for row in rows),
        "decision_date_window": _date_window(rows, "decision_date"),
        "label_available_date_window": _date_window(rows, "label_available_date"),
    }


def _oof_fold_diagnostics(
    rows: Sequence[tuple[float, int, str, RecommendationCalibrationSample]],
    usable_fold_count: int,
    evaluation_fold_id: str,
    label_name: str,
) -> dict[str, Any]:
    grouped: dict[str, list[RecommendationCalibrationSample]] = {}
    for _probability, _label, fold_id, row in rows:
        grouped.setdefault(fold_id, []).append(row)
    return {
        "usable_fold_count": usable_fold_count,
        "calibration_fold_count": len(grouped),
        "evaluation_fold_id": evaluation_fold_id,
        "folds": {
            fold_id: _split_row_diagnostics(fold_rows, label_name)
            for fold_id, fold_rows in sorted(grouped.items())
        },
    }


def _rows_for_ids(
    source: Sequence[RecommendationCalibrationSample],
    rows: Sequence[MLTimeWindowRow],
) -> tuple[RecommendationCalibrationSample, ...]:
    by_id = {row.row_id: row for row in source}
    return tuple(by_id[row.row_id] for row in rows if row.row_id in by_id)


def _candidate_id(
    dataset_id: str,
    dataset_hash: str,
    training_as_of: str,
    feature_schema: FeatureSchema,
) -> str:
    payload = {
        "dataset_id": dataset_id,
        "dataset_hash": dataset_hash,
        "training_as_of": training_as_of,
        "feature_schema": [list(item) for item in feature_schema],
    }
    return "rec-cal-" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]


def candidate_freeze_hash(
    *,
    candidate_id: str,
    dataset_hash: str,
    manifest_hash: str,
    artifact_hash: str,
    evaluation: Mapping[str, Any],
) -> str:
    """Hash only immutable candidate identity/evaluation facts (no mutable pointer)."""

    payload = {
        "candidate_id": candidate_id,
        "dataset_hash": dataset_hash,
        "manifest_hash": manifest_hash,
        "artifact_hash": artifact_hash,
        "evaluation_sample_fingerprint": evaluation.get("evaluation_sample_fingerprint"),
        "cost_contract_hash": evaluation.get("cost_contract_hash"),
        "candidate_prediction_hash": evaluation.get("candidate_prediction_hash"),
        "rule_prediction_hash": evaluation.get("rule_prediction_hash"),
    }
    return _hash_payload(payload)


def _hash_payload(payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def _library_versions() -> dict[str, str]:
    import joblib as _joblib
    import sklearn as _sklearn

    return {
        "joblib": str(_joblib.__version__),
        "numpy": str(np.__version__),
        "scikit-learn": str(_sklearn.__version__),
    }


def _date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _bounded_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _required_int(value: int | None, field_name: str) -> int:
    if value is None:
        raise ValueError(f"{field_name} is required")
    return int(value)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
