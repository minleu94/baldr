"""V4.1 推薦校準研究切片。

本模組只消費已保存的 Evidence Event／Outcome，所有來源連線都由呼叫端以
唯讀方式提供。它不修改 ScoringEngine、不修改推薦權重，也不產生正式 ML
promotion pointer。核心機率與評估數值使用整數 bp 或 Decimal；isotonic
校準採整數計數，避免在策略／績效邊界新增裸 ``float`` 計算。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

from app_module.evidence_event_dtos import (
    EvidenceDataQuality,
    EvidenceEvent,
    EvidenceEventType,
    EvidenceOutcome,
    EvidenceOutcomeStatus,
    normalize_data_quality,
    normalize_event_type,
    normalize_outcome_status,
)


SCHEMA_VERSION = "recommendation-calibration.v1"
PROBABILITY_MAX_BP = 10_000
PRIMARY_HORIZON_DAYS = 20
AUXILIARY_HORIZON_DAYS = 5
DEFAULT_UNIVERSE_POLICY_ID = "evidence_event_included_v1"
DEFAULT_FEATURE_SETS = ("score_percentile_v1", "price_volume_v1")
TARGETS = ("upside", "after_cost_profit")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_payload(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _date_text(value: str) -> str:
    parsed = date.fromisoformat(str(value)[:10])
    return parsed.isoformat()


def _round_int(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _bounded_probability(value: int) -> int:
    return max(0, min(PROBABILITY_MAX_BP, int(value)))


def _coerce_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return None


def _coerce_score_bp(value: object) -> int | None:
    """將既有 0..100 分數或 bp 值轉成整數 bp。

    Evidence metadata 的 component 欄位明確以 ``*_bp`` 保存；沒有 suffix 的
    舊樣本才依既有推薦分數慣例把 0..100 轉為 bp。
    """

    return _coerce_int(value)


def _quality_value(value: EvidenceDataQuality | str) -> str:
    return value.value if isinstance(value, EvidenceDataQuality) else str(value)


def _status_value(value: EvidenceOutcomeStatus | str) -> str:
    return value.value if isinstance(value, EvidenceOutcomeStatus) else str(value)


@dataclass(frozen=True)
class RecommendationCalibrationObservation:
    """一筆 event／horizon 配對的成熟 forward evidence。"""

    row_id: str
    event_id: str
    symbol: str
    decision_date: str
    horizon_days: int
    label_end_date: str
    ranking_score_bp: int | None
    score_percentile_bp: int | None
    forward_return_bp: int
    benchmark_return_bp: int | None
    benchmark_excess_bp: int | None
    liquidity_cost_bp: int | None
    event_data_quality: str
    outcome_data_quality: str
    event_warnings: tuple[str, ...] = ()
    outcome_warnings: tuple[str, ...] = ()
    data_as_of_date: str | None = None
    universe_policy_id: str = DEFAULT_UNIVERSE_POLICY_ID
    cost_model_id: str = ""
    benchmark_id: str | None = None
    feature_values_bp: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_date", _date_text(self.decision_date))
        object.__setattr__(self, "label_end_date", _date_text(self.label_end_date))
        if self.data_as_of_date:
            object.__setattr__(self, "data_as_of_date", _date_text(self.data_as_of_date))
        object.__setattr__(self, "horizon_days", int(self.horizon_days))
        object.__setattr__(self, "ranking_score_bp", _coerce_int(self.ranking_score_bp))
        percentile = _coerce_int(self.score_percentile_bp)
        if percentile is not None and not 0 <= percentile <= PROBABILITY_MAX_BP:
            raise ValueError("score_percentile_bp must be within 0..10000")
        object.__setattr__(self, "score_percentile_bp", percentile)
        object.__setattr__(self, "forward_return_bp", int(self.forward_return_bp))
        object.__setattr__(self, "benchmark_return_bp", _coerce_int(self.benchmark_return_bp))
        object.__setattr__(self, "benchmark_excess_bp", _coerce_int(self.benchmark_excess_bp))
        cost = _coerce_int(self.liquidity_cost_bp)
        if cost is not None and cost < 0:
            raise ValueError("liquidity_cost_bp must be non-negative")
        object.__setattr__(self, "liquidity_cost_bp", cost)
        object.__setattr__(self, "event_warnings", tuple(str(item) for item in self.event_warnings))
        object.__setattr__(self, "outcome_warnings", tuple(str(item) for item in self.outcome_warnings))
        object.__setattr__(
            self,
            "feature_values_bp",
            {str(key): int(value) for key, value in self.feature_values_bp.items()},
        )

    @property
    def observed_liquidity_cost_bp(self) -> int | None:
        return self.liquidity_cost_bp

    @property
    def evidence_confidence(self) -> str:
        if self.event_data_quality == EvidenceDataQuality.MISSING.value:
            return "low"
        if self.outcome_data_quality == EvidenceDataQuality.MISSING.value:
            return "low"
        if self.event_warnings or self.outcome_warnings or self.liquidity_cost_bp is None:
            return "degraded"
        if self.event_data_quality != EvidenceDataQuality.OBSERVED.value:
            return "degraded"
        if self.outcome_data_quality != EvidenceDataQuality.OBSERVED.value:
            return "degraded"
        return "observed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "event_id": self.event_id,
            "symbol": self.symbol,
            "decision_date": self.decision_date,
            "horizon_days": self.horizon_days,
            "label_end_date": self.label_end_date,
            "ranking_score_bp": self.ranking_score_bp,
            "score_percentile_bp": self.score_percentile_bp,
            "forward_return_bp": self.forward_return_bp,
            "benchmark_return_bp": self.benchmark_return_bp,
            "benchmark_excess_bp": self.benchmark_excess_bp,
            "liquidity_cost_bp": self.liquidity_cost_bp,
            "observed_liquidity_cost_bp": self.observed_liquidity_cost_bp,
            "event_data_quality": self.event_data_quality,
            "outcome_data_quality": self.outcome_data_quality,
            "event_warnings": list(self.event_warnings),
            "outcome_warnings": list(self.outcome_warnings),
            "data_as_of_date": self.data_as_of_date,
            "universe_policy_id": self.universe_policy_id,
            "cost_model_id": self.cost_model_id,
            "benchmark_id": self.benchmark_id,
            "feature_values_bp": dict(self.feature_values_bp),
            "evidence_confidence": self.evidence_confidence,
        }


@dataclass(frozen=True)
class RecommendationCalibrationDataset:
    observations: tuple[RecommendationCalibrationObservation, ...]
    source_mode: str
    input_event_count: int
    input_outcome_count: int
    excluded_row_count: int
    diagnostics: tuple[str, ...]
    dataset_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_mode": self.source_mode,
            "input_event_count": self.input_event_count,
            "input_outcome_count": self.input_outcome_count,
            "observation_count": len(self.observations),
            "excluded_row_count": self.excluded_row_count,
            "decision_date_min": min((row.decision_date for row in self.observations), default=None),
            "decision_date_max": max((row.decision_date for row in self.observations), default=None),
            "horizon_counts": {
                str(horizon): sum(row.horizon_days == horizon for row in self.observations)
                for horizon in (AUXILIARY_HORIZON_DAYS, PRIMARY_HORIZON_DAYS)
            },
            "dataset_fingerprint": self.dataset_fingerprint,
            "diagnostics": list(self.diagnostics),
        }


def build_recommendation_calibration_dataset(
    events: Iterable[EvidenceEvent],
    outcomes: Iterable[EvidenceOutcome],
    *,
    source_mode: str = "in_memory",
    universe_policy_id: str = DEFAULT_UNIVERSE_POLICY_ID,
    horizons: Sequence[int] = (PRIMARY_HORIZON_DAYS, AUXILIARY_HORIZON_DAYS),
) -> RecommendationCalibrationDataset:
    """以成熟 Evidence Outcome 建立固定 universe policy 的研究 dataset。

    缺 outcome、未成熟 outcome、future-dated input 與 stale data-as-of row 都
    fail-closed。缺 liquidity cost 的 row 可以進入 upside 目標，但不會被補成
    零，也不會進入 after-cost profit label。
    """

    event_rows = tuple(events)
    outcome_rows = tuple(outcomes)
    target_horizons = tuple(sorted({int(item) for item in horizons}, reverse=True))
    outcomes_by_key: dict[tuple[str, int], list[EvidenceOutcome]] = defaultdict(list)
    for outcome in outcome_rows:
        if outcome.window_days in target_horizons:
            outcomes_by_key[(outcome.event_id, outcome.window_days)].append(outcome)

    diagnostics: defaultdict[str, int] = defaultdict(int)
    observations: list[RecommendationCalibrationObservation] = []
    excluded = 0

    for event in event_rows:
        try:
            event_type = normalize_event_type(event.event_type)
        except ValueError:
            diagnostics["invalid_event_type"] += 1
            continue
        if event_type != EvidenceEventType.RECOMMENDATION_INCLUDED:
            continue
        if not event.symbol:
            diagnostics["event_missing_symbol"] += 1
            continue
        try:
            decision = _date_text(event.decision_date)
        except ValueError:
            diagnostics["invalid_decision_date"] += 1
            continue

        invalid_input_date = False
        for field_name in ("event_date", "as_of_date", "available_date"):
            value = getattr(event, field_name, "")
            if not value:
                diagnostics[f"event_missing_{field_name}"] += 1
                invalid_input_date = True
                break
            try:
                if _date_text(value) > decision:
                    diagnostics[f"event_{field_name}_after_decision"] += 1
                    invalid_input_date = True
                    break
            except ValueError:
                diagnostics[f"invalid_event_{field_name}"] += 1
                invalid_input_date = True
                break
        if invalid_input_date:
            continue

        event_policy = str(event.metadata.get("universe_policy_id") or "").strip()
        if event_policy and event_policy != universe_policy_id:
            diagnostics["universe_policy_mismatch"] += 1
            continue
        if not event_policy:
            diagnostics["universe_policy_assumed"] += 1

        ranking_score = _coerce_int(event.score_bp)
        score_percentile = _coerce_int(event.score_percentile_bp)
        if score_percentile is not None and not 0 <= score_percentile <= PROBABILITY_MAX_BP:
            diagnostics["score_percentile_out_of_range"] += 1
            score_percentile = None

        feature_values: dict[str, int] = {}
        for key in ("indicator_score_bp", "volume_score_bp", "pattern_score_bp"):
            value = _coerce_score_bp(event.metadata.get(key))
            if value is not None and 0 <= value <= PROBABILITY_MAX_BP:
                feature_values[key] = value

        for horizon in target_horizons:
            matched = outcomes_by_key.get((event.event_id, horizon), [])
            if not matched:
                diagnostics[f"missing_outcome_{horizon}d"] += 1
                excluded += 1
                continue
            if len(matched) > 1:
                diagnostics[f"duplicate_outcome_{horizon}d"] += 1
                excluded += 1
                continue
            outcome = matched[0]
            try:
                status = normalize_outcome_status(outcome.outcome_status)
            except ValueError:
                diagnostics[f"invalid_outcome_status_{horizon}d"] += 1
                excluded += 1
                continue
            if status != EvidenceOutcomeStatus.READY:
                diagnostics[f"outcome_not_ready_{horizon}d"] += 1
                excluded += 1
                continue
            if outcome.forward_return_bp is None or not outcome.outcome_price_date:
                diagnostics[f"outcome_incomplete_{horizon}d"] += 1
                excluded += 1
                continue
            try:
                label_end = _date_text(outcome.outcome_price_date)
            except ValueError:
                diagnostics[f"invalid_label_end_date_{horizon}d"] += 1
                excluded += 1
                continue
            if label_end <= decision:
                diagnostics[f"label_end_not_after_decision_{horizon}d"] += 1
                excluded += 1
                continue
            data_as_of = None
            if outcome.data_as_of_date:
                try:
                    data_as_of = _date_text(outcome.data_as_of_date)
                except ValueError:
                    diagnostics[f"invalid_data_as_of_date_{horizon}d"] += 1
                    excluded += 1
                    continue
                if data_as_of < label_end:
                    diagnostics[f"data_as_of_before_label_end_{horizon}d"] += 1
                    excluded += 1
                    continue
            cost = _coerce_int(outcome.liquidity_cost_bp)
            if cost is not None and cost < 0:
                diagnostics[f"negative_liquidity_cost_{horizon}d"] += 1
                cost = None

            observations.append(
                RecommendationCalibrationObservation(
                    row_id=f"{event.event_id}:{horizon}",
                    event_id=event.event_id,
                    symbol=str(event.symbol),
                    decision_date=decision,
                    horizon_days=horizon,
                    label_end_date=label_end,
                    ranking_score_bp=ranking_score,
                    score_percentile_bp=score_percentile,
                    forward_return_bp=int(outcome.forward_return_bp),
                    benchmark_return_bp=outcome.benchmark_return_bp,
                    benchmark_excess_bp=outcome.benchmark_excess_bp,
                    liquidity_cost_bp=cost,
                    event_data_quality=_quality_value(event.data_quality),
                    outcome_data_quality=_quality_value(outcome.data_quality),
                    event_warnings=event.warnings,
                    outcome_warnings=outcome.warnings,
                    data_as_of_date=data_as_of,
                    universe_policy_id=universe_policy_id,
                    cost_model_id=event.cost_model_id,
                    benchmark_id=event.benchmark_id,
                    feature_values_bp=feature_values,
                )
            )

    observations.sort(key=lambda item: (item.decision_date, item.row_id))
    fingerprint = _sha256_payload([item.to_dict() for item in observations])
    diagnostics_tuple = tuple(
        f"{key}:{count}" for key, count in sorted(diagnostics.items())
    )
    return RecommendationCalibrationDataset(
        observations=tuple(observations),
        source_mode=source_mode,
        input_event_count=len(event_rows),
        input_outcome_count=len(outcome_rows),
        excluded_row_count=excluded,
        diagnostics=diagnostics_tuple,
        dataset_fingerprint=fingerprint,
    )


@dataclass(frozen=True)
class RecommendationCalibrationConfig:
    primary_horizon_days: int = PRIMARY_HORIZON_DAYS
    auxiliary_horizon_days: int = AUXILIARY_HORIZON_DAYS
    minimum_train_dates: int = 12
    calibration_date_count: int = 8
    test_date_count: int = 8
    purge_trading_days: int = 20
    embargo_trading_days: int = 1
    minimum_calibration_samples: int = 8
    minimum_test_samples: int = 5
    probability_bin_count: int = 10
    fixed_round_trip_cost_bp: int = 0
    action_threshold_bp: int = 6_000
    universe_policy_id: str = DEFAULT_UNIVERSE_POLICY_ID
    feature_sets: tuple[str, ...] = DEFAULT_FEATURE_SETS

    def __post_init__(self) -> None:
        for name in (
            "primary_horizon_days",
            "auxiliary_horizon_days",
            "minimum_train_dates",
            "calibration_date_count",
            "test_date_count",
            "purge_trading_days",
            "embargo_trading_days",
            "minimum_calibration_samples",
            "minimum_test_samples",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if not 2 <= int(self.probability_bin_count) <= 20:
            raise ValueError("probability_bin_count must be between 2 and 20")
        if int(self.fixed_round_trip_cost_bp) < 0:
            raise ValueError("fixed_round_trip_cost_bp must be non-negative")
        if not 0 <= int(self.action_threshold_bp) <= PROBABILITY_MAX_BP:
            raise ValueError("action_threshold_bp must be within 0..10000")
        if not self.universe_policy_id.strip():
            raise ValueError("universe_policy_id must not be empty")
        if not self.feature_sets:
            raise ValueError("feature_sets must not be empty")

    @property
    def horizons(self) -> tuple[int, int]:
        return (self.primary_horizon_days, self.auxiliary_horizon_days)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_horizon_days": self.primary_horizon_days,
            "auxiliary_horizon_days": self.auxiliary_horizon_days,
            "minimum_train_dates": self.minimum_train_dates,
            "calibration_date_count": self.calibration_date_count,
            "test_date_count": self.test_date_count,
            "purge_trading_days": self.purge_trading_days,
            "embargo_trading_days": self.embargo_trading_days,
            "minimum_calibration_samples": self.minimum_calibration_samples,
            "minimum_test_samples": self.minimum_test_samples,
            "probability_bin_count": self.probability_bin_count,
            "fixed_round_trip_cost_bp": self.fixed_round_trip_cost_bp,
            "action_threshold_bp": self.action_threshold_bp,
            "universe_policy_id": self.universe_policy_id,
            "feature_sets": list(self.feature_sets),
        }


@dataclass(frozen=True)
class _WalkForwardFold:
    fold_id: str
    train_rows: tuple[RecommendationCalibrationObservation, ...]
    calibration_rows: tuple[RecommendationCalibrationObservation, ...]
    test_rows: tuple[RecommendationCalibrationObservation, ...]
    train_end_date: str
    calibration_start_date: str
    calibration_end_date: str
    test_start_date: str
    test_end_date: str


def _build_folds(
    observations: Sequence[RecommendationCalibrationObservation],
    config: RecommendationCalibrationConfig,
) -> tuple[_WalkForwardFold, ...]:
    dates = sorted({item.decision_date for item in observations})
    folds: list[_WalkForwardFold] = []
    train_end_index = config.minimum_train_dates
    fold_number = 1
    while True:
        calibration_start_index = train_end_index + config.purge_trading_days
        calibration_end_index = calibration_start_index + config.calibration_date_count
        # Calibration labels must be mature before the untouched test block
        # starts.  The primary 20-day label therefore creates a second
        # horizon-sized maturity gap after the calibration window.
        test_start_index = (
            calibration_end_index
            + max(config.horizons)
            + config.embargo_trading_days
        )
        test_end_index = test_start_index + config.test_date_count
        if test_end_index > len(dates):
            break
        calibration_start = dates[calibration_start_index]
        calibration_end = dates[calibration_end_index - 1]
        test_start = dates[test_start_index]
        test_end = dates[test_end_index - 1]
        train_date_end = dates[train_end_index - 1]

        train_rows = tuple(
            row
            for row in observations
            if row.decision_date < calibration_start and row.label_end_date < calibration_start
        )
        calibration_rows = tuple(
            row
            for row in observations
            if calibration_start <= row.decision_date < test_start
            and row.label_end_date < test_start
        )
        test_rows = tuple(
            row for row in observations if test_start <= row.decision_date <= test_end
        )
        if train_rows and calibration_rows and test_rows:
            folds.append(
                _WalkForwardFold(
                    fold_id=f"fold-{fold_number:03d}",
                    train_rows=train_rows,
                    calibration_rows=calibration_rows,
                    test_rows=test_rows,
                    train_end_date=train_date_end,
                    calibration_start_date=calibration_start,
                    calibration_end_date=calibration_end,
                    test_start_date=test_start,
                    test_end_date=test_end,
                )
            )
            fold_number += 1
        train_end_index = test_end_index
    return tuple(folds)


def _target_label(
    observation: RecommendationCalibrationObservation,
    target: str,
    config: RecommendationCalibrationConfig,
) -> int | None:
    if target == "upside":
        return 1 if observation.forward_return_bp > 0 else 0
    if target == "after_cost_profit":
        total_cost = observation.liquidity_cost_bp
        if total_cost is None:
            return None
        total_cost += config.fixed_round_trip_cost_bp
        return 1 if observation.forward_return_bp > total_cost else 0
    raise ValueError(f"unsupported target: {target}")


@dataclass(frozen=True)
class _FeatureEncoder:
    feature_set_id: str
    score_min_bp: int | None
    score_max_bp: int | None
    indicator_weight_bp: int = 5_000

    def raw_probability_bp(self, observation: RecommendationCalibrationObservation) -> int | None:
        if self.feature_set_id == "score_percentile_v1":
            if observation.score_percentile_bp is not None:
                return observation.score_percentile_bp
            if observation.ranking_score_bp is None:
                return None
            if self.score_min_bp is None or self.score_max_bp is None:
                return None
            if self.score_max_bp == self.score_min_bp:
                return 5_000
            numerator = (observation.ranking_score_bp - self.score_min_bp) * PROBABILITY_MAX_BP
            denominator = self.score_max_bp - self.score_min_bp
            return _bounded_probability(_round_int(Decimal(numerator) / Decimal(denominator)))
        if self.feature_set_id == "price_volume_v1":
            indicator = observation.feature_values_bp.get("indicator_score_bp")
            volume = observation.feature_values_bp.get("volume_score_bp")
            if indicator is None or volume is None:
                return None
            numerator = indicator * self.indicator_weight_bp + volume * (
                PROBABILITY_MAX_BP - self.indicator_weight_bp
            )
            return _bounded_probability(
                _round_int(Decimal(numerator) / Decimal(PROBABILITY_MAX_BP))
            )
        raise ValueError(f"unsupported feature set: {self.feature_set_id}")


def _fit_feature_encoder(
    rows: Sequence[RecommendationCalibrationObservation],
    *,
    feature_set_id: str,
    target: str,
    config: RecommendationCalibrationConfig,
) -> _FeatureEncoder:
    scores = [row.ranking_score_bp for row in rows if row.ranking_score_bp is not None]
    score_min = min(scores) if scores else None
    score_max = max(scores) if scores else None
    if feature_set_id != "price_volume_v1":
        return _FeatureEncoder(feature_set_id, score_min, score_max)

    candidates = tuple(range(0, PROBABILITY_MAX_BP + 1, 500))
    labelled = [
        row
        for row in rows
        if row.feature_values_bp.get("indicator_score_bp") is not None
        and row.feature_values_bp.get("volume_score_bp") is not None
        and _target_label(row, target, config) is not None
    ]
    if not labelled:
        return _FeatureEncoder(feature_set_id, score_min, score_max)
    best_weight = 5_000
    best_brier: int | None = None
    for weight in candidates:
        encoder = _FeatureEncoder(feature_set_id, score_min, score_max, weight)
        predictions = [encoder.raw_probability_bp(row) for row in labelled]
        labels = [_target_label(row, target, config) for row in labelled]
        if any(value is None for value in predictions) or any(value is None for value in labels):
            continue
        brier = _brier_score_bp(
            tuple(int(value) for value in predictions if value is not None),
            tuple(int(value) for value in labels if value is not None),
        )
        if best_brier is None or (brier, abs(weight - 5_000)) < (best_brier, abs(best_weight - 5_000)):
            best_brier = brier
            best_weight = weight
    return _FeatureEncoder(feature_set_id, score_min, score_max, best_weight)


@dataclass(frozen=True)
class _IsotonicBlock:
    minimum_probability_bp: int
    maximum_probability_bp: int
    prediction_bp: int
    count: int
    positive_count: int


@dataclass(frozen=True)
class _IntegerIsotonic:
    blocks: tuple[_IsotonicBlock, ...]

    def predict(self, probability_bp: int) -> int:
        value = _bounded_probability(probability_bp)
        for block in self.blocks:
            if value <= block.maximum_probability_bp:
                return block.prediction_bp
        return self.blocks[-1].prediction_bp


def _fit_integer_isotonic(
    probabilities: Sequence[int],
    labels: Sequence[int],
    *,
    minimum_samples: int,
) -> tuple[_IntegerIsotonic | None, str | None]:
    if len(probabilities) != len(labels):
        raise ValueError("probabilities and labels must have equal lengths")
    if len(probabilities) < minimum_samples:
        return None, "insufficient_calibration_samples"
    if set(labels) != {0, 1}:
        return None, "calibration_requires_two_label_classes"
    grouped: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for probability, label in zip(probabilities, labels):
        if label not in (0, 1):
            raise ValueError("labels must be binary")
        grouped[_bounded_probability(probability)][0] += 1
        grouped[_bounded_probability(probability)][1] += label
    blocks: list[dict[str, int]] = [
        {
            "minimum": probability,
            "maximum": probability,
            "count": values[0],
            "positive": values[1],
        }
        for probability, values in sorted(grouped.items())
    ]
    index = 0
    while index < len(blocks) - 1:
        left = blocks[index]
        right = blocks[index + 1]
        if left["positive"] * right["count"] > right["positive"] * left["count"]:
            merged = {
                "minimum": left["minimum"],
                "maximum": right["maximum"],
                "count": left["count"] + right["count"],
                "positive": left["positive"] + right["positive"],
            }
            blocks[index : index + 2] = [merged]
            if index > 0:
                index -= 1
        else:
            index += 1
    return (
        _IntegerIsotonic(
            tuple(
                _IsotonicBlock(
                    minimum_probability_bp=item["minimum"],
                    maximum_probability_bp=item["maximum"],
                    prediction_bp=_bounded_probability(
                        _round_int(
                            Decimal(item["positive"] * PROBABILITY_MAX_BP)
                            / Decimal(item["count"])
                        )
                    ),
                    count=item["count"],
                    positive_count=item["positive"],
                )
                for item in blocks
            )
        ),
        None,
    )


def _brier_score_bp(probabilities: Sequence[int], labels: Sequence[int]) -> int:
    if len(probabilities) != len(labels):
        raise ValueError("probabilities and labels must have equal lengths")
    if not probabilities:
        raise ValueError("brier score requires observations")
    numerator = sum(
        probability * probability if label == 0 else (PROBABILITY_MAX_BP - probability) ** 2
        for probability, label in zip(probabilities, labels)
    )
    return _round_int(Decimal(numerator) / Decimal(len(probabilities) * PROBABILITY_MAX_BP))


def _wilson_interval_bp(success_count: int, sample_count: int) -> dict[str, int]:
    if sample_count <= 0:
        return {"lower_bp": 0, "upper_bp": 0}
    n = Decimal(sample_count)
    z = Decimal("1.96")
    p = Decimal(success_count) / n
    denominator = Decimal(1) + z * z / n
    centre = (p + z * z / (Decimal(2) * n)) / denominator
    half = z * (
        (p * (Decimal(1) - p) / n + z * z / (Decimal(4) * n * n)).sqrt()
    ) / denominator
    return {
        "lower_bp": _bounded_probability(_round_int((centre - half) * PROBABILITY_MAX_BP)),
        "upper_bp": _bounded_probability(_round_int((centre + half) * PROBABILITY_MAX_BP)),
    }


def _mean_summary(values: Sequence[int]) -> dict[str, Any]:
    if not values:
        return {"mean_bp": None, "ci95_bp": None, "sample_count": 0}
    mean = Decimal(sum(values)) / Decimal(len(values))
    if len(values) <= 1:
        lower = upper = mean
    else:
        variance = sum((Decimal(value) - mean) ** 2 for value in values) / Decimal(len(values) - 1)
        half = Decimal("1.96") * (variance / Decimal(len(values))).sqrt()
        lower = mean - half
        upper = mean + half
    return {
        "mean_bp": _round_int(mean),
        "ci95_bp": {"lower_bp": _round_int(lower), "upper_bp": _round_int(upper)},
        "sample_count": len(values),
    }


def _discrimination_summary(
    records: Sequence[tuple[RecommendationCalibrationObservation, int, int]],
) -> dict[str, Any]:
    """以整數 bp 保存 pairwise AUC，避免把辨識力寫成裸 float。"""

    positives = [(probability, row.row_id) for row, label, probability in records if label == 1]
    negatives = [(probability, row.row_id) for row, label, probability in records if label == 0]
    pair_count = len(positives) * len(negatives)
    if not positives or not negatives:
        return {
            "status": "not_evaluable",
            "reason": "requires_two_label_classes",
            "auc_bp": None,
            "positive_count": len(positives),
            "negative_count": len(negatives),
            "pair_count": pair_count,
        }
    wins = sum(probability > negative for probability, _ in positives for negative, _ in negatives)
    ties = sum(probability == negative for probability, _ in positives for negative, _ in negatives)
    auc_bp = _round_int(
        Decimal(wins * PROBABILITY_MAX_BP + ties * (PROBABILITY_MAX_BP // 2))
        / Decimal(pair_count)
    )
    return {
        "status": "measured",
        "auc_bp": _bounded_probability(auc_bp),
        "positive_count": len(positives),
        "negative_count": len(negatives),
        "pair_count": pair_count,
        "concordant_pair_count": wins,
        "tied_pair_count": ties,
    }


def _turnover_summary(
    records: Sequence[tuple[RecommendationCalibrationObservation, int, int]],
    *,
    action_threshold_bp: int,
) -> dict[str, Any]:
    """以跨決策日 symbol membership churn 估計研究 turnover。"""

    by_date: dict[str, set[str]] = defaultdict(set)
    for row, _, probability in records:
        if probability >= action_threshold_bp:
            by_date[row.decision_date].add(row.symbol)
    dates = sorted(by_date)
    if len(dates) < 2:
        return {
            "status": "not_evaluable",
            "reason": "requires_two_decision_dates",
            "turnover_bp": None,
            "decision_date_count": len(dates),
            "selected_symbol_count": sum(len(by_date[item]) for item in dates),
        }
    churn = 0
    denominator = 0
    for previous, current in zip(dates, dates[1:]):
        previous_set = by_date[previous]
        current_set = by_date[current]
        churn += len(previous_set.symmetric_difference(current_set))
        denominator += max(len(previous_set), len(current_set))
    turnover = (
        None
        if denominator == 0
        else _round_int(Decimal(churn * PROBABILITY_MAX_BP) / Decimal(denominator))
    )
    return {
        "status": "measured" if turnover is not None else "not_evaluable",
        "reason": None if turnover is not None else "no_selected_membership",
        "turnover_bp": turnover,
        "decision_date_count": len(dates),
        "selected_symbol_count": sum(len(by_date[item]) for item in dates),
        "membership_churn_count": churn,
        "turnover_definition": "sum symmetric-difference selected symbols / sum adjacent max holdings",
    }


def _probability_bins(
    probabilities: Sequence[int],
    labels: Sequence[int],
    *,
    bin_count: int,
) -> list[dict[str, Any]]:
    bins: list[list[tuple[int, int]]] = [[] for _ in range(bin_count)]
    for probability, label in zip(probabilities, labels):
        index = min(bin_count - 1, probability * bin_count // PROBABILITY_MAX_BP)
        bins[index].append((probability, label))
    result: list[dict[str, Any]] = []
    for index, rows in enumerate(bins):
        lower = index * PROBABILITY_MAX_BP // bin_count
        upper = (
            PROBABILITY_MAX_BP
            if index == bin_count - 1
            else (index + 1) * PROBABILITY_MAX_BP // bin_count - 1
        )
        count = len(rows)
        positive = sum(label for _, label in rows)
        result.append(
            {
                "bin_index": index,
                "lower_probability_bp": lower,
                "upper_probability_bp": upper,
                "sample_count": count,
                "positive_count": positive,
                "observed_rate_bp": None if count == 0 else _round_int(
                    Decimal(positive * PROBABILITY_MAX_BP) / Decimal(count)
                ),
                "mean_probability_bp": None if count == 0 else _round_int(
                    Decimal(sum(probability for probability, _ in rows)) / Decimal(count)
                ),
                "brier_score_bp": None if count == 0 else _brier_score_bp(
                    tuple(probability for probability, _ in rows),
                    tuple(label for _, label in rows),
                ),
                "observed_rate_ci95_bp": None if count == 0 else _wilson_interval_bp(positive, count),
            }
        )
    return result


def _metric_payload(
    records: Sequence[tuple[RecommendationCalibrationObservation, int, int]],
    *,
    config: RecommendationCalibrationConfig,
    coverage_denominator: int | None = None,
) -> dict[str, Any]:
    denominator = len(records) if coverage_denominator is None else max(0, int(coverage_denominator))
    coverage_bp = (
        None
        if denominator == 0
        else _round_int(Decimal(len(records) * PROBABILITY_MAX_BP) / Decimal(denominator))
    )
    if len(records) < config.minimum_test_samples:
        return {
            "status": "not_evaluable",
            "reason": "insufficient_test_samples",
            "sample_count": len(records),
            "positive_count": sum(label for _, label, _ in records),
            "brier_score_bp": None,
            "ece_bp": None,
            "probability_bins": [],
            "positive_rate_ci95_bp": None,
            "performance": {},
            "discrimination": _discrimination_summary(records),
            "turnover": _turnover_summary(
                records,
                action_threshold_bp=config.action_threshold_bp,
            ),
            "coverage": {
                "evaluated_sample_count": len(records),
                "denominator_sample_count": denominator,
                "coverage_bp": coverage_bp,
            },
            "uncertainty": {
                "positive_rate_ci95_bp": None,
                "performance_ci95": {},
            },
        }
    labels = tuple(label for _, label, _ in records)
    probabilities = tuple(probability for _, _, probability in records)
    predicted_by_bin = [0] * config.probability_bin_count
    observed_by_bin = [0] * config.probability_bin_count
    for probability, label in zip(probabilities, labels):
        bin_index = min(
            config.probability_bin_count - 1,
            probability * config.probability_bin_count // PROBABILITY_MAX_BP,
        )
        predicted_by_bin[bin_index] += probability
        observed_by_bin[bin_index] += label * PROBABILITY_MAX_BP
    ece_numerator = sum(
        abs(predicted_by_bin[index] - observed_by_bin[index])
        for index in range(config.probability_bin_count)
    )
    ece = _round_int(Decimal(ece_numerator) / Decimal(len(records)))
    positive_count = sum(labels)
    performance_rows: dict[str, list[int]] = {
        "forward_return_bp": [],
        "benchmark_return_bp": [],
        "benchmark_excess_bp": [],
        "cost_adjusted_return_bp": [],
        "cost_adjusted_benchmark_excess_bp": [],
    }
    for observation, _, _ in records:
        performance_rows["forward_return_bp"].append(observation.forward_return_bp)
        if observation.benchmark_return_bp is not None:
            performance_rows["benchmark_return_bp"].append(observation.benchmark_return_bp)
        if observation.benchmark_excess_bp is not None:
            performance_rows["benchmark_excess_bp"].append(observation.benchmark_excess_bp)
        if observation.observed_liquidity_cost_bp is not None:
            performance_rows["cost_adjusted_return_bp"].append(
                observation.forward_return_bp
                - observation.observed_liquidity_cost_bp
                - config.fixed_round_trip_cost_bp
            )
            if observation.benchmark_excess_bp is not None:
                performance_rows["cost_adjusted_benchmark_excess_bp"].append(
                    observation.benchmark_excess_bp
                    - observation.observed_liquidity_cost_bp
                    - config.fixed_round_trip_cost_bp
                )
    return {
        "status": "measured",
        "sample_count": len(records),
        "positive_count": positive_count,
        "positive_rate_bp": _round_int(
            Decimal(positive_count * PROBABILITY_MAX_BP) / Decimal(len(records))
        ),
        "positive_rate_ci95_bp": _wilson_interval_bp(positive_count, len(records)),
        "brier_score_bp": _brier_score_bp(probabilities, labels),
        "ece_bp": ece,
        "probability_bins": _probability_bins(
            probabilities,
            labels,
            bin_count=config.probability_bin_count,
        ),
        "performance": {
            key: _mean_summary(values) for key, values in performance_rows.items()
        },
        "discrimination": _discrimination_summary(records),
        "turnover": _turnover_summary(
            records,
            action_threshold_bp=config.action_threshold_bp,
        ),
        "coverage": {
            "evaluated_sample_count": len(records),
            "denominator_sample_count": denominator,
            "coverage_bp": coverage_bp,
        },
        "uncertainty": {
            "positive_rate_ci95_bp": _wilson_interval_bp(positive_count, len(records)),
            "performance_ci95": {
                key: summary["ci95_bp"]
                for key, summary in (
                    (metric, _mean_summary(values))
                    for metric, values in performance_rows.items()
                )
                if summary["ci95_bp"] is not None
            },
        },
    }


def _target_metrics(
    records: Sequence[tuple[RecommendationCalibrationObservation, int, int]],
    *,
    config: RecommendationCalibrationConfig,
    coverage_denominator: int | None = None,
) -> dict[str, Any]:
    return _metric_payload(
        records,
        config=config,
        coverage_denominator=coverage_denominator,
    )


def _comparison_payload(
    baseline: dict[str, Any],
    raw: dict[str, Any],
    calibrated: dict[str, Any],
) -> dict[str, Any]:
    baseline_brier = baseline.get("brier_score_bp")
    raw_brier = raw.get("brier_score_bp")
    calibrated_brier = calibrated.get("brier_score_bp")
    return {
        "raw_brier_improvement_vs_baseline_bp": (
            None
            if baseline_brier is None or raw_brier is None
            else baseline_brier - raw_brier
        ),
        "calibrated_brier_improvement_vs_baseline_bp": (
            None
            if baseline_brier is None or calibrated_brier is None
            else baseline_brier - calibrated_brier
        ),
        "calibrated_brier_improvement_vs_raw_bp": (
            None
            if raw_brier is None or calibrated_brier is None
            else raw_brier - calibrated_brier
        ),
    }


def _evaluate_fold_target_feature(
    fold: _WalkForwardFold,
    *,
    horizon_days: int,
    target: str,
    feature_set_id: str,
    config: RecommendationCalibrationConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[tuple[RecommendationCalibrationObservation, int, int]], dict[str, Any]]:
    train_rows = [row for row in fold.train_rows if row.horizon_days == horizon_days]
    calibration_rows = [row for row in fold.calibration_rows if row.horizon_days == horizon_days]
    test_rows = [row for row in fold.test_rows if row.horizon_days == horizon_days]
    encoder = _fit_feature_encoder(
        train_rows,
        feature_set_id=feature_set_id,
        target=target,
        config=config,
    )

    train_labelled: list[RecommendationCalibrationObservation] = []
    train_labels: list[int] = []
    for row in train_rows:
        label = _target_label(row, target, config)
        if label is not None:
            train_labelled.append(row)
            train_labels.append(int(label))
    if not train_labels:
        baseline_probability = None
    else:
        baseline_probability = _round_int(
            Decimal(sum(train_labels) * PROBABILITY_MAX_BP) / Decimal(len(train_labels))
        )

    calibration_pairs: list[tuple[int, int]] = []
    for row in calibration_rows:
        probability = encoder.raw_probability_bp(row)
        label = _target_label(row, target, config)
        if probability is not None and label is not None:
            calibration_pairs.append((int(probability), int(label)))
    calibrator, calibration_reason = _fit_integer_isotonic(
        tuple(probability for probability, _ in calibration_pairs),
        tuple(label for _, label in calibration_pairs),
        minimum_samples=config.minimum_calibration_samples,
    )

    raw_records: list[tuple[RecommendationCalibrationObservation, int, int]] = []
    baseline_records: list[tuple[RecommendationCalibrationObservation, int, int]] = []
    calibrated_records: list[tuple[RecommendationCalibrationObservation, int, int]] = []
    prediction_rows: list[dict[str, Any]] = []
    for row in test_rows:
        label = _target_label(row, target, config)
        raw_probability = encoder.raw_probability_bp(row)
        if label is None or raw_probability is None:
            continue
        raw_records.append((row, int(label), raw_probability))
        if baseline_probability is not None:
            baseline_records.append((row, int(label), baseline_probability))
        calibrated_probability = None if calibrator is None else calibrator.predict(raw_probability)
        if calibrated_probability is not None:
            calibrated_records.append((row, int(label), calibrated_probability))
        prediction_rows.append(
            {
                "row_id": row.row_id,
                "feature_set_id": feature_set_id,
                "target": target,
                "horizon_days": horizon_days,
                "ranking_score_bp": row.ranking_score_bp,
                "score_percentile_bp": row.score_percentile_bp,
                "raw_probability_bp": raw_probability,
                "calibrated_probability_bp": calibrated_probability,
                "baseline_probability_bp": baseline_probability,
            }
        )

    coverage_denominator = len(test_rows)
    baseline_metrics = _target_metrics(
        baseline_records,
        config=config,
        coverage_denominator=coverage_denominator,
    )
    raw_metrics = _target_metrics(
        raw_records,
        config=config,
        coverage_denominator=coverage_denominator,
    )
    calibrated_metrics = _target_metrics(
        calibrated_records,
        config=config,
        coverage_denominator=coverage_denominator,
    )
    payload = {
        "status": "measured" if raw_metrics["status"] == "measured" else "not_evaluable",
        "feature_set_id": feature_set_id,
        "target": target,
        "horizon_days": horizon_days,
        "train_sample_count": len(train_labelled),
        "calibration_sample_count": len(calibration_pairs),
        "test_sample_count": len(raw_records),
        "baseline_probability_bp": baseline_probability,
        "calibration_status": "measured" if calibrator is not None else "not_evaluable",
        "calibration_reason": calibration_reason,
        "indicator_weight_bp": encoder.indicator_weight_bp,
        "baseline": baseline_metrics,
        "raw_score": raw_metrics,
        "calibrated": calibrated_metrics,
        "comparison": _comparison_payload(baseline_metrics, raw_metrics, calibrated_metrics),
    }
    records = calibrated_records
    return payload, prediction_rows, records, {
        "baseline_records": baseline_records,
        "raw_records": raw_records,
        "calibrated_records": records,
    }


def _aggregate_metric_records(
    records: Sequence[tuple[RecommendationCalibrationObservation, int, int]],
    *,
    config: RecommendationCalibrationConfig,
    coverage_denominator: int | None = None,
) -> dict[str, Any]:
    return _metric_payload(
        records,
        config=config,
        coverage_denominator=coverage_denominator,
    )


def _target_name(target: str, horizon_days: int) -> str:
    return f"{target}_{horizon_days}d"


def evaluate_recommendation_calibration(
    dataset: RecommendationCalibrationDataset,
    *,
    config: RecommendationCalibrationConfig | None = None,
) -> dict[str, Any]:
    """執行 expanding train/calibration/untouched-test walk-forward 研究。"""

    cfg = config or RecommendationCalibrationConfig()
    if dataset.observations and any(
        row.universe_policy_id != cfg.universe_policy_id for row in dataset.observations
    ):
        raise ValueError("dataset universe policy does not match calibration config")
    folds = _build_folds(dataset.observations, cfg)
    fold_payloads: list[dict[str, Any]] = []
    aggregate: dict[str, dict[str, dict[str, list[tuple[RecommendationCalibrationObservation, int, int]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    aggregate_coverage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    primary_prediction_rows: dict[str, dict[str, Any]] = {}
    oos_prediction_rows: list[dict[str, Any]] = []

    for fold in folds:
        fold_targets: dict[str, Any] = {}
        for horizon_days in cfg.horizons:
            for target in TARGETS:
                name = _target_name(target, horizon_days)
                feature_payloads: dict[str, Any] = {}
                for feature_set_id in cfg.feature_sets:
                    payload, prediction_rows, _, raw_records = _evaluate_fold_target_feature(
                        fold,
                        horizon_days=horizon_days,
                        target=target,
                        feature_set_id=feature_set_id,
                        config=cfg,
                    )
                    feature_payloads[feature_set_id] = payload
                    aggregate[name][feature_set_id]["baseline"].extend(raw_records["baseline_records"])
                    aggregate[name][feature_set_id]["raw"].extend(raw_records["raw_records"])
                    aggregate[name][feature_set_id]["calibrated"].extend(raw_records["calibrated_records"])
                    aggregate_coverage[name][feature_set_id] += len(
                        [row for row in fold.test_rows if row.horizon_days == horizon_days]
                    )
                    for item in prediction_rows:
                        item = {**item, "fold_id": fold.fold_id}
                        oos_prediction_rows.append(item)
                        if feature_set_id == "score_percentile_v1":
                            current = primary_prediction_rows.setdefault(
                                item["row_id"],
                                {
                                    "row_id": item["row_id"],
                                    "horizon_days": horizon_days,
                                    "ranking_score_bp": item["ranking_score_bp"],
                                    "score_percentile_bp": item["score_percentile_bp"],
                                },
                            )
                            current[f"{target}_raw_probability_bp"] = item["raw_probability_bp"]
                            current[f"{target}_probability_bp"] = item["calibrated_probability_bp"]
                            current[f"{target}_baseline_probability_bp"] = item["baseline_probability_bp"]
                fold_targets[name] = {
                    "horizon_days": horizon_days,
                    "target": target,
                    "feature_sets": feature_payloads,
                }
        fold_payloads.append(
            {
                "fold_id": fold.fold_id,
                "train_end_date": fold.train_end_date,
                "calibration_start_date": fold.calibration_start_date,
                "calibration_end_date": fold.calibration_end_date,
                "test_start_date": fold.test_start_date,
                "test_end_date": fold.test_end_date,
                "train_row_count": len(fold.train_rows),
                "calibration_row_count": len(fold.calibration_rows),
                "test_row_count": len(fold.test_rows),
                "targets": fold_targets,
            }
        )

    oos_targets: dict[str, Any] = {}
    for horizon_days in cfg.horizons:
        for target in TARGETS:
            name = _target_name(target, horizon_days)
            feature_sets: dict[str, Any] = {}
            for feature_set_id in cfg.feature_sets:
                baseline = _aggregate_metric_records(
                    aggregate[name][feature_set_id]["baseline"],
                    config=cfg,
                    coverage_denominator=aggregate_coverage[name][feature_set_id],
                )
                raw = _aggregate_metric_records(
                    aggregate[name][feature_set_id]["raw"],
                    config=cfg,
                    coverage_denominator=aggregate_coverage[name][feature_set_id],
                )
                calibrated = _aggregate_metric_records(
                    aggregate[name][feature_set_id]["calibrated"],
                    config=cfg,
                    coverage_denominator=aggregate_coverage[name][feature_set_id],
                )
                feature_sets[feature_set_id] = {
                    "feature_set_id": feature_set_id,
                    "target": target,
                    "horizon_days": horizon_days,
                    "baseline": baseline,
                    "raw_score": raw,
                    "calibrated": calibrated,
                    "comparison": _comparison_payload(baseline, raw, calibrated),
                }
            oos_targets[name] = {"horizon_days": horizon_days, "target": target, "feature_sets": feature_sets}

    predictions: list[dict[str, Any]] = []
    for row_id, current in sorted(primary_prediction_rows.items(), key=lambda item: item[0]):
        row = next((item for item in dataset.observations if item.row_id == row_id), None)
        if row is None:
            continue
        current["event_id"] = row.event_id
        current["symbol"] = row.symbol
        current["decision_date"] = row.decision_date
        current["label_end_date"] = row.label_end_date
        current["universe_policy_id"] = row.universe_policy_id
        current["evidence_confidence"] = row.evidence_confidence
        current["upside_probability_bp"] = current.get("upside_probability_bp")
        current["after_cost_profit_probability_bp"] = current.get("after_cost_profit_probability_bp")
        after_cost_probability = current.get("after_cost_profit_probability_bp")
        if after_cost_probability is None:
            current["action_suitability"] = "not_evaluable"
        elif row.evidence_confidence != "observed":
            current["action_suitability"] = "research_review"
        elif after_cost_probability >= cfg.action_threshold_bp:
            current["action_suitability"] = "research_candidate"
        else:
            current["action_suitability"] = "research_watch"
        predictions.append(current)

    decision = "retain_current_method_insufficient_matched_oos"
    primary_upside = oos_targets.get(_target_name("upside", cfg.primary_horizon_days), {})
    current_metrics = (
        primary_upside.get("feature_sets", {})
        .get("score_percentile_v1", {})
        .get("calibrated", {})
    )
    challenger_metrics = (
        primary_upside.get("feature_sets", {})
        .get("price_volume_v1", {})
        .get("calibrated", {})
    )
    current_brier = current_metrics.get("brier_score_bp")
    challenger_brier = challenger_metrics.get("brier_score_bp")
    if current_brier is not None and challenger_brier is not None:
        if challenger_brier < current_brier:
            decision = "price_volume_descriptive_improvement_not_promoted"
        else:
            decision = "retain_current_method_no_oos_improvement"

    limitations = [
        "本報告只使用歷史 Evidence Event／成熟 Outcome；不計入自然 forward evidence credit。",
        "結果為 research-only calibration diagnostics，不改 ScoringEngine、推薦權重、threshold、alpha 或 production scheduler。",
        "Benchmark 使用 EvidenceOutcome 的 benchmark_return／benchmark_excess；缺欄位時只保留可計算的子統計，不補零。",
        "成本定義為 fixed_round_trip_cost_bp + observed liquidity_cost_bp；缺 liquidity cost 的 row 不進 after-cost label。",
        "score_percentile_v1 是排序分數的機率化輸入，不等於自然勝率；calibrated probability 才是本切片的校準輸出。",
    ]
    if cfg.fixed_round_trip_cost_bp == 0:
        limitations.append("fixed_round_trip_cost_bp=0；成本後結果仍未包含未提供的手續費、證交稅或完整成交帳本成本。")
    if not folds:
        limitations.append("沒有足夠的時間序列形成 train/calibration/untouched-test fold。")
    if not any(
        value.get("calibrated", {}).get("status") == "measured"
        for value in oos_targets.values()
        for value in value.get("feature_sets", {}).values()
    ):
        limitations.append("沒有任何 feature／target 完成可評估的 calibrated OOS 結果。")

    dataset_manifest: dict[str, Any] = {
        "schema_version": "recommendation-calibration-dataset-manifest.v1",
        "dataset_fingerprint": dataset.dataset_fingerprint,
        "source_mode": dataset.source_mode,
        "source_tables": ["evidence_events", "evidence_outcomes"],
        "feature_registry": {
            "ranking_score_bp": "EvidenceEvent.score_bp；只作 ranking output，不直接當 probability。",
            "score_percentile_bp": "EvidenceEvent.score_percentile_bp；decision-time raw calibration input。",
            "indicator_score_bp": "future EvidenceEvent.metadata indicator component；optional challenger input。",
            "volume_score_bp": "future EvidenceEvent.metadata volume component；optional challenger input。",
        },
        "label_registry": {
            "upside": "forward_return_bp > 0",
            "after_cost_profit": "forward_return_bp > fixed_round_trip_cost_bp + observed liquidity_cost_bp",
            "primary_horizon_days": cfg.primary_horizon_days,
            "auxiliary_horizon_days": cfg.auxiliary_horizon_days,
        },
        "universe_policy_id": cfg.universe_policy_id,
        "decision_timing": "decision_t_uses_event_persisted_features",
        "split_policy": "expanding_train_calibration_untouched_test_with_trading_date_purge_and_label_maturity_gap",
        "shadow_only": True,
        "production_eligible": False,
    }
    dataset_manifest["manifest_hash"] = _sha256_payload(dataset_manifest)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "measured_research_only" if folds else "not_evaluable",
        "generated_at": date.today().isoformat(),
        "access_boundary": {
            "writes_allowed": False,
            "production_eligible": False,
            "production_scheduler_allowed": False,
            "recommendation_weights_changed": False,
            "ranking_score_replaced": False,
            "natural_forward_evidence_credit": False,
        },
        "contract": {
            "decision_time": "EvidenceEvent.decision_date；event_date/as_of_date/available_date 必須不晚於 decision_date。",
            "primary_target": {
                "horizon_days": cfg.primary_horizon_days,
                "upside_label": "forward_return_bp > 0",
                "after_cost_profit_label": "forward_return_bp > fixed_round_trip_cost_bp + observed liquidity_cost_bp",
            },
            "auxiliary_target": {
                "horizon_days": cfg.auxiliary_horizon_days,
                "same_labels_as_primary": True,
            },
            "return_definition": "EvidenceOutcome.close_to_close_event_date；label_end_date 使用 outcome_price_date。",
            "benchmark_definition": "EvidenceOutcome.benchmark_return_bp 與 benchmark_excess_bp；不重算、不補缺。",
            "cost_definition": {
                "model_id": "fixed_round_trip_plus_observed_liquidity_v1",
                "fixed_round_trip_cost_bp": cfg.fixed_round_trip_cost_bp,
                "liquidity_cost_source": "EvidenceOutcome.liquidity_cost_bp",
                "missing_cost_policy": "exclude_after_cost_label",
            },
            "universe_policy": {
                "id": cfg.universe_policy_id,
                "inclusion": "event_type=recommendation_included 且 symbol 非空",
                "identity_rule": "使用 event 當時保存的 universe／rank evidence；不讀目前 universe，不回填歷史事件。",
            },
            "training_policy": "按 decision_date 的 expanding train/calibration/untouched-test；training/calibration label_end 必須在各自切點前成熟。",
            "calibration_label_maturity_gap_trading_days": max(cfg.horizons),
        },
        "dataset": dataset.to_dict(),
        "dataset_manifest": dataset_manifest,
        "config": cfg.to_dict(),
        "lookahead_checks": {
            "event_inputs_before_decision": True,
            "train_labels_before_calibration_start": True,
            "calibration_labels_before_test_start": True,
            "test_rows_never_used_for_fit": True,
            "current_universe_not_used": True,
            "future_outcomes_used_only_as_labels": True,
        },
        "fold_count": len(folds),
        "folds": fold_payloads,
        "oos": {"targets": oos_targets},
        "oos_predictions": sorted(
            oos_prediction_rows,
            key=lambda item: (
                str(item.get("decision_date") or ""),
                str(item.get("row_id") or ""),
                str(item.get("feature_set_id") or ""),
                str(item.get("target") or ""),
            ),
        ),
        "decision": {
            "feature_set_policy": "若 challenger 沒有 matched OOS improvement，保留 current score method；本報告不自動 promote。",
            "research_decision": decision,
            "current_method": "score_percentile_v1",
            "challenger_method": "price_volume_v1",
        },
        "predictions": predictions,
        "limitations": limitations,
    }


def sample_evidence_rows() -> tuple[tuple[EvidenceEvent, ...], tuple[EvidenceOutcome, ...]]:
    """提供 deterministic、非正式資料的 CLI／單元測試樣本。"""

    dates: list[str] = []
    current = date(2024, 1, 2)
    while len(dates) < 210:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    symbols = ("1101", "2330", "2454")
    events: list[EvidenceEvent] = []
    outcomes: list[EvidenceOutcome] = []
    for index, decision_date in enumerate(dates[:-PRIMARY_HORIZON_DAYS - 1]):
        for symbol_index, symbol in enumerate(symbols):
            score = 500 + ((index * 911 + symbol_index * 2_217) % 9_000)
            indicator = _bounded_probability((score * 7_000 + (index * 113) % 3_000) // 10_000)
            volume = _bounded_probability((score * 4_000 + (symbol_index * 1_700)) // 10_000)
            event_id = f"sample-{index:03d}-{symbol}"
            event = EvidenceEvent(
                event_id=event_id,
                event_hash=f"hash-{event_id}",
                event_date=decision_date,
                decision_date=decision_date,
                symbol=symbol,
                event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
                event_family="recommendation",
                source_type="sample",
                profile_id="sample",
                score_bp=score,
                score_percentile_bp=score,
                data_quality=EvidenceDataQuality.OBSERVED,
                as_of_date=decision_date,
                available_date=decision_date,
                source_version="recommendation_calibration_sample_v1",
                cost_model_id="sample_liquidity_v1",
                benchmark_id="sample_equal_weight",
                metadata={
                    "universe_policy_id": DEFAULT_UNIVERSE_POLICY_ID,
                    "indicator_score_bp": indicator,
                    "volume_score_bp": volume,
                    "pattern_score_bp": _bounded_probability((score + 1_500) % 10_001),
                },
            )
            events.append(event)
            for horizon in (PRIMARY_HORIZON_DAYS, AUXILIARY_HORIZON_DAYS):
                outcome_index = index + horizon
                outcome_date = dates[outcome_index]
                noise = ((index * 223 + symbol_index * 71 + horizon * 13) % 1_401) - 700
                forward_return = (score - 5_000) // 2 + noise
                benchmark_return = ((index * 197 + symbol_index * 89 + horizon * 31) % 601) - 300
                outcomes.append(
                    EvidenceOutcome(
                        outcome_id=f"out-{event_id}-{horizon}",
                        event_id=event_id,
                        window_days=horizon,
                        window_type="trading_days",
                        return_basis="close_to_close_event_date",
                        event_price_date=decision_date,
                        outcome_price_date=outcome_date,
                        forward_return_bp=forward_return,
                        benchmark_return_bp=benchmark_return,
                        benchmark_excess_bp=forward_return - benchmark_return,
                        liquidity_cost_bp=40 + symbol_index * 5,
                        outcome_status=EvidenceOutcomeStatus.READY,
                        data_quality=EvidenceDataQuality.OBSERVED,
                        data_as_of_date=outcome_date,
                    )
                )
    return tuple(events), tuple(outcomes)


def sample_recommendation_calibration_dataset(
    *,
    config: RecommendationCalibrationConfig | None = None,
) -> RecommendationCalibrationDataset:
    cfg = config or RecommendationCalibrationConfig()
    events, outcomes = sample_evidence_rows()
    return build_recommendation_calibration_dataset(
        events,
        outcomes,
        source_mode="sample_only",
        universe_policy_id=cfg.universe_policy_id,
        horizons=cfg.horizons,
    )
