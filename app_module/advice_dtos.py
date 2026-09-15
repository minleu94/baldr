from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, cast


class AdviceAction(str, Enum):
    RESEARCH = "RESEARCH"
    ADD_CANDIDATE = "ADD_CANDIDATE"
    HOLD = "HOLD"
    REDUCE_CANDIDATE = "REDUCE_CANDIDATE"
    EXIT_CANDIDATE = "EXIT_CANDIDATE"
    AVOID = "AVOID"
    NO_NEW_POSITION = "NO_NEW_POSITION"


class AdviceMode(str, Enum):
    GUIDED = "GUIDED"
    PROFESSIONAL = "PROFESSIONAL"


class AdviceClassification(str, Enum):
    FORMAL_ADVICE = "FORMAL_ADVICE"
    PROFESSIONAL_CANDIDATE = "PROFESSIONAL_CANDIDATE"


def _payload(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Advice JSON payload must be an object")
    return value


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("Advice JSON collection must be an array")
    if not all(isinstance(item, str) for item in value):
        raise ValueError("Advice JSON collection items must be strings")
    return tuple(value)


def _validate_bp(field_name: str, value: Any, *, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer bp value")
    if not minimum <= value <= maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum} bp")


@dataclass(frozen=True)
class AdvicePolicyConfig:
    mode: AdviceMode = AdviceMode.GUIDED
    min_cash_reserve_bp: int = 2000
    max_positions: int = 8
    max_single_position_bp: int = 1500

    def __post_init__(self) -> None:
        _validate_bp("min_cash_reserve_bp", self.min_cash_reserve_bp, minimum=0, maximum=10000)
        if isinstance(self.max_positions, bool) or not isinstance(self.max_positions, int):
            raise ValueError("max_positions must be an integer")
        if not 1 <= self.max_positions <= 8:
            raise ValueError("max_positions must be between 1 and 8")
        _validate_bp("max_single_position_bp", self.max_single_position_bp, minimum=0, maximum=1500)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "min_cash_reserve_bp": self.min_cash_reserve_bp,
            "max_positions": self.max_positions,
            "max_single_position_bp": self.max_single_position_bp,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AdvicePolicyConfig:
        payload = _payload(value)
        return cls(
            mode=AdviceMode(payload.get("mode", AdviceMode.GUIDED.value)),
            min_cash_reserve_bp=payload.get("min_cash_reserve_bp", 2000),
            max_positions=payload.get("max_positions", 8),
            max_single_position_bp=payload.get("max_single_position_bp", 1500),
        )


@dataclass(frozen=True)
class RecommendationAdviceDTO:
    stock_code: str
    advice_action: AdviceAction
    classification: AdviceClassification = AdviceClassification.FORMAL_ADVICE
    why_reasons: tuple[str, ...] = ()
    why_not_reasons: tuple[str, ...] = ()
    risk_reasons: tuple[str, ...] = ()
    confidence_tier: str = ""
    evidence_tier: str = ""
    data_quality: str = ""
    warnings: tuple[str, ...] = ()
    strategy_version: str = ""
    decision_date: str = ""
    data_as_of_date: str = ""
    holding_horizon: str = ""
    entry_thesis: str = ""
    invalidation_conditions: tuple[str, ...] = ()
    market_regime: str = ""
    liquidity_state: str = ""
    execution_feasibility: str = ""
    source_trace: tuple[str, ...] = ()
    refusal_reasons: tuple[str, ...] = ()
    ranking_score_bp: int | None = None
    ranking_percentile_bp: int | None = None
    ranking_method: str = ""
    calibrated_probability_bp: int | None = None
    calibrated_probability_status: str = "research"
    after_cost_profit_probability_bp: int | None = None
    after_cost_profit_probability_status: str = "research"
    evidence_confidence: str = ""
    sample_size: int | None = None
    cost_basis_bp: int | None = None
    calibration_model_version: str = ""
    calibration_dataset_version: str = ""
    calibration_source: str = ""
    calibration_probability_transform_id: str = ""
    calibration_probability_baseline_id: str = ""
    calibration_probability_baseline_kind: str = ""
    calibration_probability_baseline_probability_bp: int | None = None
    calibration_raw_probability_bp: int | None = None
    calibration_raw_after_cost_probability_bp: int | None = None
    # P1 immutable projection receipt/provenance; presentation never recomputes it.
    calibration_provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            self.classification is AdviceClassification.PROFESSIONAL_CANDIDATE
            and self.advice_action is not AdviceAction.RESEARCH
        ):
            raise ValueError("professional candidates must remain RESEARCH only")
        _validate_optional_bp("ranking_percentile_bp", self.ranking_percentile_bp)
        _validate_optional_bp("calibrated_probability_bp", self.calibrated_probability_bp)
        _validate_optional_bp("after_cost_profit_probability_bp", self.after_cost_profit_probability_bp)
        _validate_optional_bp("cost_basis_bp", self.cost_basis_bp)
        _validate_optional_bp(
            "calibration_probability_baseline_probability_bp",
            self.calibration_probability_baseline_probability_bp,
        )
        _validate_optional_bp("calibration_raw_probability_bp", self.calibration_raw_probability_bp)
        _validate_optional_bp(
            "calibration_raw_after_cost_probability_bp",
            self.calibration_raw_after_cost_probability_bp,
        )
        if self.ranking_score_bp is not None and isinstance(self.ranking_score_bp, bool):
            raise ValueError("ranking_score_bp must be an integer basis-point value")
        if self.sample_size is not None and (isinstance(self.sample_size, bool) or self.sample_size < 0):
            raise ValueError("sample_size must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "advice_action": self.advice_action.value,
            "classification": self.classification.value,
            "why_reasons": list(self.why_reasons),
            "why_not_reasons": list(self.why_not_reasons),
            "risk_reasons": list(self.risk_reasons),
            "confidence_tier": self.confidence_tier,
            "evidence_tier": self.evidence_tier,
            "data_quality": self.data_quality,
            "warnings": list(self.warnings),
            "strategy_version": self.strategy_version,
            "decision_date": self.decision_date,
            "data_as_of_date": self.data_as_of_date,
            "holding_horizon": self.holding_horizon,
            "entry_thesis": self.entry_thesis,
            "invalidation_conditions": list(self.invalidation_conditions),
            "market_regime": self.market_regime,
            "liquidity_state": self.liquidity_state,
            "execution_feasibility": self.execution_feasibility,
            "source_trace": list(self.source_trace),
            "refusal_reasons": list(self.refusal_reasons),
            "ranking_score_bp": self.ranking_score_bp,
            "ranking_percentile_bp": self.ranking_percentile_bp,
            "ranking_method": self.ranking_method,
            "calibrated_probability_bp": self.calibrated_probability_bp,
            "calibrated_probability_status": self.calibrated_probability_status,
            "after_cost_profit_probability_bp": self.after_cost_profit_probability_bp,
            "after_cost_profit_probability_status": self.after_cost_profit_probability_status,
            "evidence_confidence": self.evidence_confidence,
            "sample_size": self.sample_size,
            "cost_basis_bp": self.cost_basis_bp,
            "calibration_model_version": self.calibration_model_version,
            "calibration_dataset_version": self.calibration_dataset_version,
            "calibration_source": self.calibration_source,
            "calibration_probability_transform_id": self.calibration_probability_transform_id,
            "calibration_probability_baseline_id": self.calibration_probability_baseline_id,
            "calibration_probability_baseline_kind": self.calibration_probability_baseline_kind,
            "calibration_probability_baseline_probability_bp": self.calibration_probability_baseline_probability_bp,
            "calibration_raw_probability_bp": self.calibration_raw_probability_bp,
            "calibration_raw_after_cost_probability_bp": self.calibration_raw_after_cost_probability_bp,
            "calibration_provenance": dict(self.calibration_provenance),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RecommendationAdviceDTO:
        payload = _payload(value)
        return cls(
            stock_code=payload["stock_code"],
            advice_action=AdviceAction(payload["advice_action"]),
            classification=AdviceClassification(
                payload.get("classification", AdviceClassification.FORMAL_ADVICE.value)
            ),
            why_reasons=_string_tuple(payload.get("why_reasons")),
            why_not_reasons=_string_tuple(payload.get("why_not_reasons")),
            risk_reasons=_string_tuple(payload.get("risk_reasons")),
            confidence_tier=payload.get("confidence_tier", ""),
            evidence_tier=payload.get("evidence_tier", ""),
            data_quality=payload.get("data_quality", ""),
            warnings=_string_tuple(payload.get("warnings")),
            strategy_version=payload.get("strategy_version", ""),
            decision_date=payload.get("decision_date", ""),
            data_as_of_date=payload.get("data_as_of_date", ""),
            holding_horizon=payload.get("holding_horizon", ""),
            entry_thesis=payload.get("entry_thesis", ""),
            invalidation_conditions=_string_tuple(payload.get("invalidation_conditions")),
            market_regime=payload.get("market_regime", ""),
            liquidity_state=payload.get("liquidity_state", ""),
            execution_feasibility=payload.get("execution_feasibility", ""),
            source_trace=_string_tuple(payload.get("source_trace")),
            refusal_reasons=_string_tuple(payload.get("refusal_reasons")),
            ranking_score_bp=payload.get("ranking_score_bp"),
            ranking_percentile_bp=payload.get("ranking_percentile_bp"),
            ranking_method=payload.get("ranking_method", ""),
            calibrated_probability_bp=payload.get("calibrated_probability_bp"),
            calibrated_probability_status=payload.get("calibrated_probability_status", "research"),
            after_cost_profit_probability_bp=payload.get("after_cost_profit_probability_bp"),
            after_cost_profit_probability_status=payload.get("after_cost_profit_probability_status", "research"),
            evidence_confidence=payload.get("evidence_confidence", ""),
            sample_size=payload.get("sample_size"),
            cost_basis_bp=payload.get("cost_basis_bp"),
            calibration_model_version=payload.get("calibration_model_version", ""),
            calibration_dataset_version=payload.get("calibration_dataset_version", ""),
            calibration_source=payload.get("calibration_source", ""),
            calibration_probability_transform_id=payload.get("calibration_probability_transform_id", ""),
            calibration_probability_baseline_id=payload.get("calibration_probability_baseline_id", ""),
            calibration_probability_baseline_kind=payload.get("calibration_probability_baseline_kind", ""),
            calibration_probability_baseline_probability_bp=payload.get(
                "calibration_probability_baseline_probability_bp"
            ),
            calibration_raw_probability_bp=payload.get("calibration_raw_probability_bp"),
            calibration_raw_after_cost_probability_bp=payload.get("calibration_raw_after_cost_probability_bp"),
            calibration_provenance=(
                dict(cast(Mapping[str, Any], payload.get("calibration_provenance")))
                if isinstance(payload.get("calibration_provenance"), Mapping)
                else {}
            ),
        )


@dataclass(frozen=True)
class PortfolioAdviceDTO:
    stock_code: str
    advice_action: AdviceAction
    target_weight_bp: int
    current_weight_bp: int | None
    weight_gap_bp: int | None
    executable_weight_bp: int | None = None
    reasons: tuple[str, ...] = ()
    risk_reasons: tuple[str, ...] = ()
    confidence_tier: str = ""
    evidence_tier: str = ""
    data_quality: str = ""
    warnings: tuple[str, ...] = ()
    holding_horizon: str = ""
    entry_thesis: str = ""
    invalidation_conditions: tuple[str, ...] = ()
    market_regime: str = ""
    strategy_version: str = ""
    liquidity_state: str = ""
    execution_feasibility: str = ""
    source_trace: tuple[str, ...] = ()
    review_date: str = ""
    diagnostics: tuple[str, ...] = ()
    ranking_score_bp: int | None = None
    ranking_percentile_bp: int | None = None
    ranking_method: str = ""
    calibrated_probability_bp: int | None = None
    calibrated_probability_status: str = "research"
    after_cost_profit_probability_bp: int | None = None
    after_cost_profit_probability_status: str = "research"
    evidence_confidence: str = ""
    sample_size: int | None = None
    cost_basis_bp: int | None = None
    calibration_model_version: str = ""
    calibration_dataset_version: str = ""
    calibration_source: str = ""
    calibration_probability_transform_id: str = ""
    calibration_probability_baseline_id: str = ""
    calibration_probability_baseline_kind: str = ""
    calibration_probability_baseline_probability_bp: int | None = None
    calibration_raw_probability_bp: int | None = None
    calibration_raw_after_cost_probability_bp: int | None = None
    # Same read-only provenance shape for portfolio advice sourced from a
    # recommendation projection; absent means legacy/other portfolio data.
    calibration_provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_bp("target_weight_bp", self.target_weight_bp, minimum=0, maximum=10000)
        if self.current_weight_bp is not None:
            _validate_bp("current_weight_bp", self.current_weight_bp, minimum=0, maximum=10000)
        if self.weight_gap_bp is not None:
            _validate_bp("weight_gap_bp", self.weight_gap_bp, minimum=-10000, maximum=10000)
        if self.executable_weight_bp is not None:
            _validate_bp(
                "executable_weight_bp",
                self.executable_weight_bp,
                minimum=0,
                maximum=10000,
            )
        _validate_optional_bp("ranking_percentile_bp", self.ranking_percentile_bp)
        _validate_optional_bp("calibrated_probability_bp", self.calibrated_probability_bp)
        _validate_optional_bp("after_cost_profit_probability_bp", self.after_cost_profit_probability_bp)
        _validate_optional_bp("cost_basis_bp", self.cost_basis_bp)
        _validate_optional_bp(
            "calibration_probability_baseline_probability_bp",
            self.calibration_probability_baseline_probability_bp,
        )
        _validate_optional_bp("calibration_raw_probability_bp", self.calibration_raw_probability_bp)
        _validate_optional_bp(
            "calibration_raw_after_cost_probability_bp",
            self.calibration_raw_after_cost_probability_bp,
        )
        if self.ranking_score_bp is not None and isinstance(self.ranking_score_bp, bool):
            raise ValueError("ranking_score_bp must be an integer basis-point value")
        if self.sample_size is not None and (isinstance(self.sample_size, bool) or self.sample_size < 0):
            raise ValueError("sample_size must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "advice_action": self.advice_action.value,
            "target_weight_bp": self.target_weight_bp,
            "current_weight_bp": self.current_weight_bp,
            "weight_gap_bp": self.weight_gap_bp,
            "executable_weight_bp": self.executable_weight_bp,
            "reasons": list(self.reasons),
            "risk_reasons": list(self.risk_reasons),
            "confidence_tier": self.confidence_tier,
            "evidence_tier": self.evidence_tier,
            "data_quality": self.data_quality,
            "warnings": list(self.warnings),
            "holding_horizon": self.holding_horizon,
            "entry_thesis": self.entry_thesis,
            "invalidation_conditions": list(self.invalidation_conditions),
            "market_regime": self.market_regime,
            "strategy_version": self.strategy_version,
            "liquidity_state": self.liquidity_state,
            "execution_feasibility": self.execution_feasibility,
            "source_trace": list(self.source_trace),
            "review_date": self.review_date,
            "diagnostics": list(self.diagnostics),
            "ranking_score_bp": self.ranking_score_bp,
            "ranking_percentile_bp": self.ranking_percentile_bp,
            "ranking_method": self.ranking_method,
            "calibrated_probability_bp": self.calibrated_probability_bp,
            "calibrated_probability_status": self.calibrated_probability_status,
            "after_cost_profit_probability_bp": self.after_cost_profit_probability_bp,
            "after_cost_profit_probability_status": self.after_cost_profit_probability_status,
            "evidence_confidence": self.evidence_confidence,
            "sample_size": self.sample_size,
            "cost_basis_bp": self.cost_basis_bp,
            "calibration_model_version": self.calibration_model_version,
            "calibration_dataset_version": self.calibration_dataset_version,
            "calibration_source": self.calibration_source,
            "calibration_probability_transform_id": self.calibration_probability_transform_id,
            "calibration_probability_baseline_id": self.calibration_probability_baseline_id,
            "calibration_probability_baseline_kind": self.calibration_probability_baseline_kind,
            "calibration_probability_baseline_probability_bp": self.calibration_probability_baseline_probability_bp,
            "calibration_raw_probability_bp": self.calibration_raw_probability_bp,
            "calibration_raw_after_cost_probability_bp": self.calibration_raw_after_cost_probability_bp,
            "calibration_provenance": dict(self.calibration_provenance),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PortfolioAdviceDTO:
        payload = _payload(value)
        return cls(
            stock_code=payload["stock_code"],
            advice_action=AdviceAction(payload["advice_action"]),
            target_weight_bp=payload["target_weight_bp"],
            current_weight_bp=payload["current_weight_bp"],
            weight_gap_bp=payload["weight_gap_bp"],
            executable_weight_bp=payload.get("executable_weight_bp"),
            reasons=_string_tuple(payload.get("reasons")),
            risk_reasons=_string_tuple(payload.get("risk_reasons")),
            confidence_tier=payload.get("confidence_tier", ""),
            evidence_tier=payload.get("evidence_tier", ""),
            data_quality=payload.get("data_quality", ""),
            warnings=_string_tuple(payload.get("warnings")),
            holding_horizon=payload.get("holding_horizon", ""),
            entry_thesis=payload.get("entry_thesis", ""),
            invalidation_conditions=_string_tuple(payload.get("invalidation_conditions")),
            market_regime=payload.get("market_regime", ""),
            strategy_version=payload.get("strategy_version", ""),
            liquidity_state=payload.get("liquidity_state", ""),
            execution_feasibility=payload.get("execution_feasibility", ""),
            source_trace=_string_tuple(payload.get("source_trace")),
            review_date=payload.get("review_date", ""),
            diagnostics=_string_tuple(payload.get("diagnostics")),
            ranking_score_bp=payload.get("ranking_score_bp"),
            ranking_percentile_bp=payload.get("ranking_percentile_bp"),
            ranking_method=payload.get("ranking_method", ""),
            calibrated_probability_bp=payload.get("calibrated_probability_bp"),
            calibrated_probability_status=payload.get("calibrated_probability_status", "research"),
            after_cost_profit_probability_bp=payload.get("after_cost_profit_probability_bp"),
            after_cost_profit_probability_status=payload.get("after_cost_profit_probability_status", "research"),
            evidence_confidence=payload.get("evidence_confidence", ""),
            sample_size=payload.get("sample_size"),
            cost_basis_bp=payload.get("cost_basis_bp"),
            calibration_model_version=payload.get("calibration_model_version", ""),
            calibration_dataset_version=payload.get("calibration_dataset_version", ""),
            calibration_source=payload.get("calibration_source", ""),
            calibration_probability_transform_id=payload.get("calibration_probability_transform_id", ""),
            calibration_probability_baseline_id=payload.get("calibration_probability_baseline_id", ""),
            calibration_probability_baseline_kind=payload.get("calibration_probability_baseline_kind", ""),
            calibration_probability_baseline_probability_bp=payload.get(
                "calibration_probability_baseline_probability_bp"
            ),
            calibration_raw_probability_bp=payload.get("calibration_raw_probability_bp"),
            calibration_raw_after_cost_probability_bp=payload.get("calibration_raw_after_cost_probability_bp"),
            calibration_provenance=(
                dict(cast(Mapping[str, Any], payload.get("calibration_provenance")))
                if isinstance(payload.get("calibration_provenance"), Mapping)
                else {}
            ),
        )


@dataclass(frozen=True)
class AdviceDashboardDTO:
    decision_date: str
    data_as_of_date: str
    mode: AdviceMode
    policy: AdvicePolicyConfig
    recommendations: tuple[RecommendationAdviceDTO, ...] = ()
    portfolio_rows: tuple[PortfolioAdviceDTO, ...] = ()
    diagnostics: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_date": self.decision_date,
            "data_as_of_date": self.data_as_of_date,
            "mode": self.mode.value,
            "policy": self.policy.to_dict(),
            "recommendations": [row.to_dict() for row in self.recommendations],
            "portfolio_rows": [row.to_dict() for row in self.portfolio_rows],
            "diagnostics": list(self.diagnostics),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AdviceDashboardDTO:
        payload = _payload(value)
        recommendations = payload.get("recommendations", ())
        portfolio_rows = payload.get("portfolio_rows", ())
        if not isinstance(recommendations, (list, tuple)):
            raise ValueError("Advice dashboard recommendations must be an array")
        if not isinstance(portfolio_rows, (list, tuple)):
            raise ValueError("Advice dashboard portfolio_rows must be an array")
        return cls(
            decision_date=payload["decision_date"],
            data_as_of_date=payload["data_as_of_date"],
            mode=AdviceMode(payload["mode"]),
            policy=AdvicePolicyConfig.from_dict(payload.get("policy", {})),
            recommendations=tuple(RecommendationAdviceDTO.from_dict(row) for row in recommendations),
            portfolio_rows=tuple(PortfolioAdviceDTO.from_dict(row) for row in portfolio_rows),
            diagnostics=_string_tuple(payload.get("diagnostics")),
            warnings=_string_tuple(payload.get("warnings")),
        )


def _validate_optional_bp(field_name: str, value: Any) -> None:
    if value is None:
        return
    _validate_bp(field_name, value, minimum=0, maximum=10_000)
