"""將已注入的研究輸入組合為唯讀 Advice dashboard。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping, Sequence

from app_module.advice_dtos import (
    AdviceAction,
    AdviceClassification,
    AdviceDashboardDTO,
    AdviceMode,
    PortfolioAdviceDTO,
    RecommendationAdviceDTO,
)
from app_module.advice_policy import AdvicePolicy
from app_module.recommendation.legacy_dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation_calibration_consumer import RecommendationCalibrationProjection
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.recommendation.contracts import StrategyAdviceContractSnapshot
from app_module.saved_recommendation_queries import (
    execution_result_config,
    saved_recommendation_capture_projection,
    verified_saved_calibration_projections,
)
from app_module.portfolio_construction_dtos import PortfolioAllocationRow, PortfolioConstructionResult
from app_module.portfolio_allocation_dtos import (
    PortfolioAllocationResultV2,
    PortfolioAllocationRowV2,
)


@dataclass(frozen=True)
class _SavedExecutionRecommendationRow:
    """Advice 所需的保存值投影，不將 execution row 解碼成舊 DTO。"""

    stock_code: str
    stock_name: str | None
    close_price: object
    price_change: object
    total_score: object
    indicator_score: object
    pattern_score: object
    volume_score: object
    recommendation_reasons: str
    industry: str
    regime_match: bool | None
    score_percentile_bp: int | None
    eligible_universe_size: int | None
    eligible_universe_date: str | None
    ranking_method: str | None
    threshold_mode: str | None


class AdviceComposer:
    """僅依呼叫端注入的 payload 組裝可追溯 Advice，不讀取任何外部狀態。"""

    def __init__(self, policy: AdvicePolicy) -> None:
        self._policy = policy

    def compose(
        self,
        *,
        recommendations: RecommendationResultDTO | RecommendationExecutionReadModel | Sequence[RecommendationDTO],
        portfolio_result: PortfolioConstructionResult | PortfolioAllocationResultV2 | None,
        evidence_quality: str | None,
        decision_date: date | str,
        data_as_of_date: date | str,
        mode: AdviceMode,
        evidence_warnings: Sequence[str] = (),
        research_only: bool = False,
        evidence_quality_by_stock: Mapping[str, str] | None = None,
        current_weights_bp: Mapping[str, int] | None = None,
        calibration_by_stock_code: Mapping[str, object] | None = None,
    ) -> AdviceDashboardDTO:
        if type(research_only) is not bool:
            raise TypeError("research_only 必須是 bool")
        quality_by_stock = self._quality_by_stock(evidence_quality_by_stock)
        decision_date_text = self._date_text(decision_date, "decision_date")
        data_as_of_date_text = self._date_text(data_as_of_date, "data_as_of_date")
        if data_as_of_date_text > decision_date_text:
            raise ValueError("data_as_of_date must not be later than decision_date")
        if portfolio_result is not None:
            portfolio_decision_date = self._date_text(
                portfolio_result.decision_date,
                "portfolio_result.decision_date",
            )
            if portfolio_decision_date > decision_date_text:
                raise ValueError(
                    "portfolio_result.decision_date must not be later than decision_date"
                )

        warning_values = self._strings(evidence_warnings, "evidence_warnings")
        current_weights_known = current_weights_bp is not None
        current_weights = self._weights(current_weights_bp or {})
        calibration_by_stock = dict(calibration_by_stock_code or {})
        result_id, config, recommendation_rows, source_trace_kind = self._recommendation_payload(recommendations)
        source_payload_sha256 = self._verified_source_payload_sha256(
            recommendations,
            expected_result_id=result_id,
        )
        source_provenance = (
            (f"canonical_payload_sha256:{source_payload_sha256.removeprefix('sha256:')}",)
            if source_payload_sha256 is not None
            else ()
        )
        # A normal RecommendationService run persists the projection fields on
        # each RecommendationDTO.  Reuse that exact object for portfolio rows
        # as well, so Advice does not require a parallel caller-only mapping.
        saved_projections = (
            verified_saved_calibration_projections(recommendations)
            if isinstance(recommendations, RecommendationExecutionReadModel)
            else {}
        )
        advice_contract_snapshot = None
        if (
            isinstance(recommendations, RecommendationExecutionReadModel)
            and recommendations.integrity_basis == "canonical_payload_and_index_verified"
            and recommendations.execution is not None
        ):
            advice_contract_snapshot = (
                getattr(
                    recommendations.execution.context,
                    "advice_contract_snapshot",
                    None,
                )
            )
        for recommendation in recommendation_rows:
            calibration_by_stock.setdefault(
                recommendation.stock_code,
                saved_projections.get(recommendation.stock_code)
                or (recommendation if isinstance(recommendation, RecommendationDTO) else None),
            )
        legacy_allocations = (
            portfolio_result.allocations
            if isinstance(portfolio_result, PortfolioConstructionResult)
            else ()
        )
        allocation_v2_rows = (
            portfolio_result.rows
            if isinstance(portfolio_result, PortfolioAllocationResultV2)
            else ()
        )
        targets = {
            row.stock_code: self._bp(row.constrained_weight_bp, "target_weight_bp")
            for row in legacy_allocations
        }
        targets.update(
            {
                row.stock_code: self._bp(row.target_weight_bp, "target_weight_bp")
                for row in allocation_v2_rows
            }
        )
        cash_reserve_bp = self._cash_reserve_bp(portfolio_result)
        current_position_count = (
            sum(1 for weight in current_weights.values() if weight > 0)
            if current_weights_known
            else None
        )
        # research_only 保留為舊呼叫相容參數，不再把系統建議降成非正式輸出。
        strategy_status = self._string_or_none(config.get("strategy_status"))
        parameters_locked = self._bool_or_none(config.get("parameters_locked"))
        disclosure_complete = self._bool_or_none(config.get("disclosure_complete"))
        execution_feasible = config.get("execution_feasible")
        risk_budget_available = config.get("risk_budget_available")

        recommendation_advice: tuple[RecommendationAdviceDTO, ...]
        if evidence_quality == "MISSING":
            recommendation_advice = (
                self._refusal_recommendation(
                    decision_date_text,
                    data_as_of_date_text,
                    warning_values,
                ),
            )
        else:
            source_evidence_by_stock = self._source_evidence_by_stock(
                recommendations,
                expected_result_id=result_id,
            )
            liquidity_state_by_stock = self._liquidity_state_by_stock(
                recommendations,
                expected_result_id=result_id,
            )
            recommendation_advice = tuple(
                self._recommendation_advice(
                    recommendation,
                    result_id=result_id,
                    strategy_status=strategy_status,
                    parameters_locked=parameters_locked,
                    disclosure_complete=disclosure_complete,
                    mode=mode,
                    evidence_quality=quality_by_stock.get(
                        recommendation.stock_code, evidence_quality
                    ),
                    execution_feasible=execution_feasible,
                    risk_budget_available=risk_budget_available,
                    current_position_count=current_position_count,
                    cash_reserve_bp=cash_reserve_bp,
                    target_weight_bp=targets.get(recommendation.stock_code),
                    decision_date=decision_date_text,
                    data_as_of_date=data_as_of_date_text,
                    warnings=warning_values,
                    strategy_version=self._string_or_empty(config.get("strategy_version")),
                    market_regime=self._string_or_empty(config.get("market_regime") or config.get("regime")),
                    calibration=calibration_by_stock.get(recommendation.stock_code),
                    source_trace_kind=source_trace_kind,
                    source_provenance=source_provenance,
                    source_payload_sha256=source_payload_sha256,
                    source_evidence=source_evidence_by_stock.get(
                        recommendation.stock_code,
                        ("保存結果沒有可核對的同股逐筆篩選／Why Not／流動性證據；不能據此推定沒有反證或風險。",),
                    ),
                    liquidity_state=liquidity_state_by_stock.get(
                        recommendation.stock_code,
                        "UNKNOWN",
                    ),
                    portfolio_sizing_requested=portfolio_result is not None,
                    advice_contract_snapshot=advice_contract_snapshot,
                )
                for recommendation in recommendation_rows
            )

        legacy_portfolio_advice = tuple(
            self._portfolio_advice(
                allocation,
                current_weights=current_weights,
                result_id=result_id,
                data_as_of_date=data_as_of_date_text,
                evidence_quality=evidence_quality or "",
                warnings=warning_values,
                calibration=calibration_by_stock.get(allocation.stock_code),
            )
            for allocation in legacy_allocations
        )
        v2_portfolio_advice: tuple[PortfolioAdviceDTO, ...] = ()
        if isinstance(portfolio_result, PortfolioAllocationResultV2):
            v2_portfolio_advice = tuple(
                self._portfolio_advice_v2(
                    allocation,
                    result=portfolio_result,
                    data_as_of_date=data_as_of_date_text,
                    evidence_quality=evidence_quality or "",
                    warnings=warning_values,
                    calibration=calibration_by_stock.get(allocation.stock_code),
                )
                for allocation in allocation_v2_rows
            )
        portfolio_advice = (*legacy_portfolio_advice, *v2_portfolio_advice)
        diagnostics = (
            tuple(portfolio_result.diagnostics)
            if isinstance(portfolio_result, PortfolioConstructionResult)
            else tuple(portfolio_result.reasons)
            if isinstance(portfolio_result, PortfolioAllocationResultV2)
            else ("portfolio_result_missing",)
        )
        return AdviceDashboardDTO(
            decision_date=decision_date_text,
            data_as_of_date=data_as_of_date_text,
            mode=mode,
            policy=self._policy._config,
            recommendations=recommendation_advice,
            portfolio_rows=portfolio_advice,
            diagnostics=diagnostics,
            warnings=warning_values,
        )

    @staticmethod
    def _quality_by_stock(value: Mapping[str, str] | None) -> dict[str, str]:
        """驗證同次結果綁定的逐股品質覆寫；缺列仍沿用整體品質。"""

        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise TypeError("evidence_quality_by_stock 必須是 mapping 或 None")
        allowed = {"OBSERVED", "DEGRADED", "MISSING", "UNKNOWN"}
        normalized: dict[str, str] = {}
        for stock_code, quality in value.items():
            if type(stock_code) is not str or not stock_code.strip():
                raise ValueError("evidence_quality_by_stock 的股票代碼不可為空")
            if type(quality) is not str or quality not in allowed:
                raise ValueError(
                    "evidence_quality_by_stock 僅接受 OBSERVED/DEGRADED/MISSING/UNKNOWN"
                )
            normalized[stock_code] = quality
        return normalized

    def _recommendation_advice(
        self,
        recommendation: Any,
        *,
        result_id: str,
        strategy_status: str | None,
        parameters_locked: bool | None,
        disclosure_complete: bool | None,
        mode: AdviceMode,
        evidence_quality: str | None,
        execution_feasible: object,
        risk_budget_available: object,
        current_position_count: int | None,
        cash_reserve_bp: int | None,
        target_weight_bp: int | None,
        decision_date: str,
        data_as_of_date: str,
        warnings: tuple[str, ...],
        strategy_version: str,
        market_regime: str,
        calibration: object | None,
        source_trace_kind: str = "RecommendationResultDTO",
        source_provenance: tuple[str, ...] = (),
        source_payload_sha256: str | None = None,
        source_evidence: tuple[str, ...] = (),
        liquidity_state: str = "UNKNOWN",
        portfolio_sizing_requested: bool = False,
        advice_contract_snapshot: StrategyAdviceContractSnapshot | None = None,
    ) -> RecommendationAdviceDTO:
        decision = self._policy.decide(
            mode=mode,
            strategy_status=strategy_status,
            parameters_locked=parameters_locked,
            disclosure_complete=disclosure_complete,
            strategy_advice_contract_verified=(
                advice_contract_snapshot is not None
            ),
            data_quality=evidence_quality,
            execution_feasible=self._bool_or_none(execution_feasible),
            risk_budget_available=self._bool_or_none(risk_budget_available),
            current_position_count=current_position_count,
            cash_reserve_bp=cash_reserve_bp,
            target_weight_bp=target_weight_bp,
        )
        calibration_fields = self._calibration_fields(
            calibration if calibration is not None else recommendation,
            expected_stock_code=recommendation.stock_code,
        )
        # 校準觀察期間不是策略作者聲明的持有期間。
        calibration_fields.pop("holding_horizon", None)
        source_trace = (
            (source_trace_kind,)
            + ((str(result_id),) if result_id else ())
            + source_provenance
            + tuple(calibration_fields.pop("_source_trace", ()))
        )
        risk_reasons = self._recommendation_risk_reasons(
            evidence_quality=evidence_quality,
            execution_feasible=self._bool_or_none(execution_feasible),
            risk_budget_available=self._bool_or_none(risk_budget_available),
            portfolio_sizing_requested=portfolio_sizing_requested,
        )
        contract = (
            advice_contract_snapshot.contract
            if advice_contract_snapshot is not None
            else None
        )
        contract_trace = (
            (
                "strategy_advice_contract:",
                advice_contract_snapshot.strategy_version_id,
                advice_contract_snapshot.contract_sha256,
            )
            if advice_contract_snapshot is not None
            else ()
        )
        return RecommendationAdviceDTO(
            stock_code=recommendation.stock_code,
            stock_name=str(getattr(recommendation, "stock_name", "") or ""),
            advice_action=decision.action,
            classification=self._classification(
                mode,
                strategy_status=strategy_status,
            ),
            why_reasons=tuple(self._split_reasons(recommendation.recommendation_reasons)),
            why_not_reasons=decision.reasons,
            risk_reasons=risk_reasons,
            data_quality=evidence_quality or "",
            warnings=warnings,
            strategy_version=strategy_version,
            decision_date=decision_date,
            data_as_of_date=data_as_of_date,
            market_regime=market_regime,
            holding_horizon=contract.holding_horizon if contract is not None else "",
            entry_thesis=contract.thesis if contract is not None else "",
            invalidation_conditions=(
                contract.invalidation_conditions if contract is not None else ()
            ),
            review_cadence=contract.review_cadence if contract is not None else "",
            execution_feasibility=self._feasibility_text(execution_feasible),
            liquidity_state=liquidity_state,
            source_evidence=source_evidence,
            source_trace=source_trace + contract_trace,
            source_result_id=self._safe_source_result_id(result_id),
            source_payload_sha256=source_payload_sha256,
            refusal_reasons=decision.reasons,
            total_score=self._source_numeric_text(
                getattr(recommendation, "total_score", None)
            ),
            score_percentile_bp=getattr(recommendation, "score_percentile_bp", None),
            eligible_universe_size=getattr(
                recommendation, "eligible_universe_size", None
            ),
            eligible_universe_date=self._source_date_text(
                getattr(recommendation, "eligible_universe_date", None)
            ),
            industry=(
                str(getattr(recommendation, "industry", "") or "").strip() or None
            ),
            close_price=self._source_numeric_text(
                getattr(recommendation, "close_price", None)
            ),
            price_change=self._source_numeric_text(
                getattr(recommendation, "price_change", None)
            ),
            **calibration_fields,
        )

    @staticmethod
    def _source_evidence_by_stock(
        recommendations: RecommendationResultDTO | RecommendationExecutionReadModel | Sequence[RecommendationDTO],
        *,
        expected_result_id: str,
    ) -> dict[str, tuple[str, ...]]:
        """只呈現同一保存結果、同一股票代碼的既有逐股證據摘要。"""

        try:
            if isinstance(recommendations, RecommendationResultDTO):
                projection: Mapping[str, object] = {
                    "result_id": recommendations.result_id,
                    "screening_matrix_json": recommendations.screening_matrix_json,
                    "why_not_payload_json": recommendations.why_not_payload_json,
                    "liquidity_gate_payload_json": recommendations.liquidity_gate_payload_json,
                }
            elif isinstance(recommendations, RecommendationExecutionReadModel):
                projection = saved_recommendation_capture_projection(recommendations)
            else:
                return {}
        except (AttributeError, KeyError, TypeError, ValueError):
            return {}
        if projection.get("result_id") != expected_result_id:
            return {}

        evidence: dict[str, list[str]] = {}
        fields = (
            ("screening_matrix_json", "篩選"),
            ("why_not_payload_json", "Why Not"),
            ("liquidity_gate_payload_json", "流動性"),
        )
        status_labels = {
            "pass": "通過",
            "fail": "未通過",
            "degraded": "降級",
            "missing": "缺資料",
            "skipped": "略過",
        }
        quality_labels = {
            "observed": "已觀測",
            "estimated": "估算",
            "degraded": "降級",
            "missing": "缺資料",
            "unknown": "未知",
        }
        for field_name, label in fields:
            rows = projection.get(field_name)
            if not isinstance(rows, (tuple, list)):
                continue
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                stock_code = row.get("stock_code")
                if type(stock_code) is not str or not stock_code.strip():
                    continue
                codes = row.get("reason_codes", row.get("exclusion_reason_codes", ()))
                if codes is None:
                    codes = ()
                if not isinstance(codes, (tuple, list)) or any(type(code) is not str for code in codes):
                    continue
                stage = row.get("stage")
                status = row.get("status")
                quality = row.get("quality")
                details: list[str] = []
                if type(stage) is str and stage.strip():
                    details.append(f"階段={stage.strip()[:80]}")
                if type(status) is str and status.strip():
                    token = status.strip().lower()
                    details.append(f"結果={status_labels.get(token, f'未知（{token[:40]}）')}")
                if type(quality) is str and quality.strip():
                    token = quality.strip().lower()
                    details.append(f"資料品質={quality_labels.get(token, f'未知（{token[:40]}）')}")
                clean_codes = tuple(code.strip()[:100] for code in codes if code.strip())
                if clean_codes:
                    details.append("來源理由碼=" + ", ".join(clean_codes[:8]))
                if not details:
                    continue
                evidence.setdefault(stock_code, []).append(f"{label}：" + "；".join(details))
        return {
            stock_code: tuple(dict.fromkeys(lines))
            for stock_code, lines in evidence.items()
        }

    @staticmethod
    def _liquidity_state_by_stock(
        recommendations: RecommendationResultDTO | RecommendationExecutionReadModel | Sequence[RecommendationDTO],
        *,
        expected_result_id: str,
    ) -> dict[str, str]:
        """只投影同一保存結果中可核驗的負向流動性門檻，不推論通過。"""

        try:
            if isinstance(recommendations, RecommendationResultDTO):
                projection: Mapping[str, object] = {
                    "result_id": recommendations.result_id,
                    "liquidity_gate_payload_json": recommendations.liquidity_gate_payload_json,
                }
            elif isinstance(recommendations, RecommendationExecutionReadModel):
                projection = saved_recommendation_capture_projection(recommendations)
            else:
                return {}
        except (AttributeError, KeyError, TypeError, ValueError):
            return {}
        if projection.get("result_id") != expected_result_id:
            return {}

        rows = projection.get("liquidity_gate_payload_json")
        if not isinstance(rows, (tuple, list)):
            return {}
        by_stock: dict[str, list[Mapping[str, object]]] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            stock_code = row.get("stock_code")
            if type(stock_code) is str and stock_code.strip():
                by_stock.setdefault(stock_code, []).append(row)

        states: dict[str, str] = {}
        for stock_code, stock_rows in by_stock.items():
            if len(stock_rows) != 1:
                states[stock_code] = "UNKNOWN"
                continue
            row = stock_rows[0]
            reason_codes = row.get("reason_codes", row.get("exclusion_reason_codes", ()))
            if reason_codes is None:
                reason_codes = ()
            if not isinstance(reason_codes, (tuple, list)) or any(
                type(code) is not str for code in reason_codes
            ):
                states[stock_code] = "UNKNOWN"
                continue
            reason_text = " ".join(reason_codes).lower()
            threshold_name = row.get("threshold_name", "")
            if type(threshold_name) is not str:
                states[stock_code] = "UNKNOWN"
                continue
            has_liquidity_basis = (
                "liquidity" in reason_text or "liquidity" in threshold_name.lower()
            )
            status = row.get("status")
            quality = row.get("quality")
            states[stock_code] = (
                "GATE_FAIL"
                if (
                    has_liquidity_basis
                    and status == "fail"
                    and quality == "observed"
                )
                else "UNKNOWN"
            )
        return states

    @staticmethod
    def _refusal_recommendation(decision_date: str, data_as_of_date: str, warnings: tuple[str, ...]) -> RecommendationAdviceDTO:
        return RecommendationAdviceDTO(
            stock_code="",
            advice_action=AdviceAction.NO_NEW_POSITION,
            data_quality="MISSING",
            liquidity_state="UNKNOWN",
            warnings=warnings,
            decision_date=decision_date,
            data_as_of_date=data_as_of_date,
            source_trace=("AdviceComposer.refusal",),
            why_not_reasons=("evidence_quality_missing",),
            risk_reasons=("evidence_quality_missing", *warnings),
            refusal_reasons=("evidence_quality_missing",),
        )

    def _portfolio_advice(
        self,
        allocation: PortfolioAllocationRow,
        *,
        current_weights: Mapping[str, int],
        result_id: str,
        data_as_of_date: str,
        evidence_quality: str,
        warnings: tuple[str, ...],
        calibration: object | None,
    ) -> PortfolioAdviceDTO:
        stock_code = allocation.stock_code
        target_weight_bp = self._bp(allocation.constrained_weight_bp, "target_weight_bp")
        missing_current_weight = stock_code not in current_weights
        current_weight_bp = current_weights.get(stock_code)
        weight_gap_bp = (
            None if current_weight_bp is None else target_weight_bp - current_weight_bp
        )
        diagnostics = tuple(allocation.diagnostics) + (("current_weight_missing",) if missing_current_weight else ())
        calibration_fields = self._calibration_fields(
            calibration,
            expected_stock_code=stock_code,
        )
        source_trace = (
            ("PortfolioConstructionResult",)
            + ((str(result_id),) if result_id else ())
            + tuple(calibration_fields.pop("_source_trace", ()))
        )
        action, reasons = self._allocation_action(
            target_weight_bp=target_weight_bp,
            current_weight_bp=current_weight_bp,
            weight_gap_bp=weight_gap_bp,
        )
        return PortfolioAdviceDTO(
            stock_code=stock_code,
            advice_action=action,
            target_weight_bp=target_weight_bp,
            current_weight_bp=current_weight_bp,
            weight_gap_bp=weight_gap_bp,
            executable_weight_bp=None,
            reasons=reasons,
            risk_reasons=tuple(
                diagnostic
                for diagnostic in diagnostics
                if any(
                    token in diagnostic.lower()
                    for token in ("risk", "health", "watch", "exit", "liquidity", "cash", "cap")
                )
            ),
            data_quality=evidence_quality,
            warnings=warnings,
            execution_feasibility=(
                "UNKNOWN" if missing_current_weight else "FEASIBLE"
            ),
            source_trace=source_trace,
            review_date=data_as_of_date,
            diagnostics=diagnostics,
            **calibration_fields,
        )

    def _portfolio_advice_v2(
        self,
        allocation: PortfolioAllocationRowV2,
        *,
        result: PortfolioAllocationResultV2,
        data_as_of_date: str,
        evidence_quality: str,
        warnings: tuple[str, ...],
        calibration: object | None,
    ) -> PortfolioAdviceDTO:
        current_weight_bp = allocation.current_weight_bp
        executable_weight_bp = allocation.executable_weight_bp
        diagnostics = tuple(allocation.diagnostics)
        action, action_reasons = self._allocation_action_v2(
            target_weight_bp=allocation.target_weight_bp,
            current_weight_bp=current_weight_bp,
            weight_gap_bp=allocation.gap_weight_bp,
            executable_weight_bp=executable_weight_bp,
            diagnostics=diagnostics,
        )
        calibration_fields = self._calibration_fields(
            calibration,
            expected_stock_code=allocation.stock_code,
        )
        source_trace = (
            "PortfolioAllocationResultV2",
            result.dataset_identity_hash,
            result.dataset_manifest_file_hash,
            result.model_hash,
            result.policy_hash,
            *tuple(calibration_fields.pop("_source_trace", ())),
        )
        risk_reasons = tuple(
            diagnostic
            for diagnostic in diagnostics
            if any(
                token in diagnostic.lower()
                for token in (
                    "risk",
                    "health",
                    "watch",
                    "exit",
                    "liquidity",
                    "cash",
                    "cap",
                    "cooldown",
                )
            )
        )
        return PortfolioAdviceDTO(
            stock_code=allocation.stock_code,
            advice_action=action,
            target_weight_bp=allocation.target_weight_bp,
            current_weight_bp=current_weight_bp,
            weight_gap_bp=allocation.gap_weight_bp,
            executable_weight_bp=executable_weight_bp,
            reasons=tuple(dict.fromkeys((*action_reasons, *result.reasons))),
            risk_reasons=risk_reasons,
            data_quality=evidence_quality,
            warnings=warnings,
            execution_feasibility=(
                "UNKNOWN"
                if current_weight_bp is None or executable_weight_bp is None
                else "FEASIBLE"
            ),
            source_trace=source_trace,
            review_date=data_as_of_date,
            diagnostics=diagnostics,
            **calibration_fields,
        )

    @staticmethod
    def _calibration_fields(
        calibration: object | None,
        *,
        expected_stock_code: str | None = None,
    ) -> dict[str, Any]:
        """Map only typed producer projections into Advice without calculations.

        The optional stock-code mapping is an integration seam, so a plain JSON
        mapping must not be allowed to promote a number or status into a
        probability.  Normal RecommendationService output remains supported via
        ``RecommendationDTO``; explicit calibration maps must use the existing
        frozen consumer projection.
        """

        if calibration is None:
            return {}
        if isinstance(calibration, Mapping):
            return {}
        if isinstance(calibration, RecommendationCalibrationProjection):
            if expected_stock_code and calibration.stock_code != expected_stock_code:
                return {}
            has_probability = (
                calibration.calibrated_probability_bp is not None
                or calibration.after_cost_profit_probability_bp is not None
            )
            if has_probability and not AdviceComposer._typed_projection_has_scope(calibration):
                return {}
        elif isinstance(calibration, RecommendationDTO):
            if expected_stock_code and calibration.stock_code != expected_stock_code:
                return {}
            has_probability = (
                calibration.calibrated_probability_bp is not None
                or calibration.after_cost_profit_probability_bp is not None
            )
            if has_probability and not AdviceComposer._recommendation_dto_has_scope(calibration):
                return {}
        else:
            return {}

        def value(name: str, default: Any = None) -> Any:
            return getattr(calibration, name, default)

        source_trace = value("source_trace", value("calibration_source_trace", ()))
        if not isinstance(source_trace, (list, tuple)):
            source_trace = ()
        calibration_source = str(
            value("calibration_source", value("source", "")) or ""
        )
        if not calibration_source and source_trace:
            calibration_source = str(source_trace[0])
        raw_provenance = value("calibration_provenance", None)
        if isinstance(raw_provenance, Mapping):
            calibration_provenance = dict(raw_provenance)
        else:
            calibration_provenance = {}
            for name in (
                "training_provenance",
                "inference_provenance",
                "provenance_compatibility",
                "provenance_status",
                "projection_contract_hash",
                "selection_authority",
                "selection_score_kind",
                "selection_percentile_kind",
                "model_ranking_kind",
            ):
                item = value(name, None)
                if item not in (None, "", {}, ()):
                    calibration_provenance[name] = item
        provenance_trace = tuple(
            f"{key}:{calibration_provenance[key]}"
            for key in (
                "provenance_status",
                "projection_receipt_path",
                "projection_receipt_hash",
                "inference_source_hash",
                "inference_pit_hash",
                "feature_snapshot_fingerprint",
            )
            if calibration_provenance.get(key) not in (None, "")
        )
        return {
            "ranking_score_bp": value("ranking_score_bp"),
            "ranking_percentile_bp": value("ranking_percentile_bp"),
            "ranking_method": str(value("ranking_method", "") or ""),
            "confidence_tier": str(value("confidence_tier", "") or ""),
            "calibrated_probability_bp": value("calibrated_probability_bp"),
            "calibrated_probability_status": str(value("calibrated_probability_status", "research") or "research"),
            "after_cost_profit_probability_bp": value("after_cost_profit_probability_bp"),
            "after_cost_profit_probability_status": str(value("after_cost_profit_probability_status", "research") or "research"),
            "evidence_confidence": str(value("evidence_confidence", "") or ""),
            "sample_size": value("sample_size"),
            "cost_basis_bp": value("cost_basis_bp"),
            "calibration_model_version": str(
                value("model_version", value("calibration_model_version", "")) or ""
            ),
            "calibration_dataset_version": str(
                value("dataset_version", value("calibration_dataset_version", "")) or ""
            ),
            "calibration_source": calibration_source,
            "calibration_probability_transform_id": str(
                value("probability_transform_id", value("calibration_probability_transform_id", "")) or ""
            ),
            "calibration_probability_baseline_id": str(
                value("probability_baseline_id", value("calibration_probability_baseline_id", "")) or ""
            ),
            "calibration_probability_baseline_kind": str(
                value("probability_baseline_kind", value("calibration_probability_baseline_kind", "")) or ""
            ),
            "calibration_probability_baseline_probability_bp": value(
                "probability_baseline_probability_bp",
                value("calibration_probability_baseline_probability_bp"),
            ),
            "calibration_raw_probability_bp": value(
                "raw_calibrated_probability_bp",
                value("calibration_raw_probability_bp"),
            ),
            "calibration_raw_after_cost_probability_bp": value(
                "raw_after_cost_profit_probability_bp",
                value("calibration_raw_after_cost_probability_bp"),
            ),
            "holding_horizon": str(value("holding_horizon", "") or ""),
            "calibration_horizon": str(
                value("horizon", value("calibration_horizon", "")) or ""
            ),
            "calibration_provenance": calibration_provenance,
            "_source_trace": tuple(str(item) for item in source_trace) + provenance_trace,
        }

    @staticmethod
    def _typed_projection_has_scope(projection: RecommendationCalibrationProjection) -> bool:
        """Require the fields emitted by the existing consumer for probability rows.

        This is a shape/scope check only.  Natural evidence authority remains in
        the existing learning verifier; an active candidate is still rendered as
        research/shadow by the downstream presentation contract.
        """

        required_text = (
            projection.model_version,
            projection.dataset_version,
            projection.horizon,
            projection.cost_basis,
        )
        if not all(str(value or "").strip() for value in required_text):
            return False
        if not projection.source_trace:
            return False
        trace = " ".join(str(item).lower() for item in projection.source_trace)
        if not any(token in trace for token in ("candidate:", "active:", "recommendation_calibration_consumer")):
            return False
        if projection.status != "active_candidate":
            return False
        valid_probability_statuses = {"active_effective", "shadow_candidate"}
        if projection.calibrated_probability_bp is not None and (
            projection.calibrated_probability_status not in valid_probability_statuses
        ):
            return False
        if projection.after_cost_profit_probability_bp is not None and (
            projection.after_cost_profit_probability_status not in valid_probability_statuses
        ):
            return False
        if projection.after_cost_profit_probability_bp is not None and not any(
            str(item).startswith("after_cost_baseline:") for item in projection.source_trace
        ):
            return False
        return True

    @staticmethod
    def _recommendation_dto_has_scope(recommendation: RecommendationDTO) -> bool:
        """Keep persisted producer DTOs fail-closed without a projection scope."""

        required_text = (
            recommendation.calibration_model_version,
            recommendation.calibration_dataset_version,
            recommendation.calibration_horizon,
            recommendation.calibration_source,
        )
        if not all(str(value or "").strip() for value in required_text):
            return False
        if recommendation.calibration_status != "active_candidate":
            return False
        if not recommendation.calibration_source_trace:
            return False
        trace = " ".join(str(item).lower() for item in recommendation.calibration_source_trace)
        if not any(token in trace for token in ("candidate:", "active:", "recommendation_calibration_consumer")):
            return False
        if recommendation.cost_basis_bp is None and not (
            "cost_scenario:" in trace and "cost_estimate_source:" in trace
        ):
            return False
        valid_probability_statuses = {"active_effective", "shadow_candidate"}
        if recommendation.calibrated_probability_bp is not None and (
            recommendation.calibrated_probability_status not in valid_probability_statuses
        ):
            return False
        if recommendation.after_cost_profit_probability_bp is not None and (
            recommendation.after_cost_profit_probability_status not in valid_probability_statuses
        ):
            return False
        if recommendation.after_cost_profit_probability_bp is not None and not any(
            str(item).startswith("after_cost_baseline:")
            for item in recommendation.calibration_source_trace
        ):
            return False
        return True

    @staticmethod
    def _allocation_action(
        *,
        target_weight_bp: int,
        current_weight_bp: int | None,
        weight_gap_bp: int | None,
    ) -> tuple[AdviceAction, tuple[str, ...]]:
        if current_weight_bp is None or weight_gap_bp is None:
            return AdviceAction.NO_NEW_POSITION, ("current_weight_missing",)
        if target_weight_bp == 0 and current_weight_bp > 0:
            return AdviceAction.EXIT_CANDIDATE, ("target_weight_zero",)
        if weight_gap_bp <= -300:
            return AdviceAction.REDUCE_CANDIDATE, ("allocation_gap_reduce",)
        if weight_gap_bp >= 300:
            return AdviceAction.ADD_CANDIDATE, ("allocation_gap_add",)
        return AdviceAction.HOLD, ("within_rebalance_band",)

    @classmethod
    def _allocation_action_v2(
        cls,
        *,
        target_weight_bp: int,
        current_weight_bp: int | None,
        weight_gap_bp: int | None,
        executable_weight_bp: int | None,
        diagnostics: tuple[str, ...],
    ) -> tuple[AdviceAction, tuple[str, ...]]:
        if (
            current_weight_bp is None
            or weight_gap_bp is None
            or executable_weight_bp is None
        ):
            return AdviceAction.NO_NEW_POSITION, ("current_portfolio_state_incomplete",)
        diagnostic_text = "|".join(diagnostics).lower()
        hard_exit = any(
            token in diagnostic_text
            for token in ("hard_risk:", "exit_candidate", "closed_target_zero")
        )
        if target_weight_bp == 0 and current_weight_bp > 0 and hard_exit:
            return AdviceAction.EXIT_CANDIDATE, ("hard_exit_target_zero",)
        executable_gap = executable_weight_bp - current_weight_bp
        if executable_gap < 0:
            return AdviceAction.REDUCE_CANDIDATE, ("executable_weight_reduction",)
        if executable_gap > 0:
            return AdviceAction.ADD_CANDIDATE, ("executable_weight_increase",)
        return cls._allocation_action(
            target_weight_bp=target_weight_bp,
            current_weight_bp=current_weight_bp,
            weight_gap_bp=weight_gap_bp,
        )

    @staticmethod
    def _recommendation_payload(
        recommendations: RecommendationResultDTO | RecommendationExecutionReadModel | Sequence[RecommendationDTO],
    ) -> tuple[str, Mapping[str, object], tuple[Any, ...], str]:
        if isinstance(recommendations, RecommendationResultDTO):
            return (
                recommendations.result_id,
                recommendations.config,
                tuple(recommendations.recommendations),
                "RecommendationResultDTO",
            )
        if isinstance(recommendations, RecommendationExecutionReadModel):
            if recommendations.legacy_result is not None:
                legacy = recommendations.legacy_result
                return (
                    legacy.result_id,
                    legacy.config,
                    tuple(legacy.recommendations),
                    "RecommendationResultDTO",
                )
            execution = recommendations.execution
            if execution is None or execution.decision is None:
                return recommendations.result_id, {}, (), "RecommendationExecution"
            config = execution_result_config(execution)
            if execution.context.strategy_identity is not None:
                strategy_version = execution.context.strategy_identity.strategy_version_id
                if strategy_version:
                    config.setdefault("strategy_version", strategy_version)
            if execution.decision.regime is not None:
                config.setdefault("regime", execution.decision.regime)
            rows = tuple(
                _SavedExecutionRecommendationRow(
                    stock_code=item.stock_code,
                    stock_name=item.stock_name,
                    close_price=item.close_price,
                    price_change=item.price_change,
                    total_score=item.rule_score,
                    indicator_score=item.indicator_score,
                    pattern_score=item.pattern_score,
                    volume_score=item.volume_score,
                    recommendation_reasons=(
                        item.reason_text
                        if item.reason_text is not None
                        else "; ".join(item.reasons)
                    ),
                    industry=item.industry or "",
                    regime_match=item.regime_match,
                    score_percentile_bp=item.score_percentile_bp,
                    eligible_universe_size=item.eligible_universe_size,
                    eligible_universe_date=AdviceComposer._source_date_text(
                        getattr(item, "eligible_universe_date", None)
                    ),
                    ranking_method=item.ranking_method,
                    threshold_mode=item.threshold_mode,
                )
                for item in execution.decision.items
            )
            return (
                execution.result_id,
                config,
                rows,
                "RecommendationExecution",
            )
        return "", {}, tuple(recommendations), "RecommendationResultDTO"

    @staticmethod
    def _verified_source_provenance(
        recommendations: RecommendationResultDTO | RecommendationExecutionReadModel | Sequence[RecommendationDTO],
    ) -> tuple[str, ...]:
        """只沿用 query 已核驗的 canonical payload hash，不提升 legacy hash 資格。"""

        payload_hash = AdviceComposer._verified_source_payload_sha256(recommendations)
        if payload_hash is None:
            return ()
        return (f"canonical_payload_sha256:{payload_hash.removeprefix('sha256:')}",)

    @staticmethod
    def _verified_source_payload_sha256(
        recommendations: RecommendationResultDTO | RecommendationExecutionReadModel | Sequence[RecommendationDTO],
        *,
        expected_result_id: str | None = None,
    ) -> str | None:
        """回傳同一 canonical execution read model 已核驗的 payload hash。"""

        if not isinstance(recommendations, RecommendationExecutionReadModel):
            return None
        execution = recommendations.execution
        if (
            execution is None
            or recommendations.legacy_result is not None
            or recommendations.integrity_basis != "canonical_payload_and_index_verified"
        ):
            return None
        execution_result_id = getattr(execution, "result_id", None)
        if (
            not isinstance(execution_result_id, str)
            or not execution_result_id
            or execution_result_id.strip() != execution_result_id
            or (expected_result_id is not None and execution_result_id != expected_result_id)
        ):
            return None
        payload_hash = recommendations.payload_hash
        if not isinstance(payload_hash, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", payload_hash) is None:
            return None
        return payload_hash

    @staticmethod
    def _safe_source_result_id(result_id: object) -> str | None:
        """只將符合 Advice DTO 身份契約的保存結果 ID 接回 Advice。"""

        if (
            type(result_id) is not str
            or not result_id
            or result_id in {".", ".."}
            or result_id.strip() != result_id
            or len(result_id) > 128
            or any(character in result_id for character in ("/", "\\", "\x00"))
        ):
            return None
        return result_id

    @classmethod
    def _weights(cls, values: Mapping[str, int]) -> dict[str, int]:
        return {str(stock_code): cls._bp(weight, "current_weight_bp") for stock_code, weight in values.items()}

    @classmethod
    def _cash_reserve_bp(
        cls,
        result: PortfolioConstructionResult | PortfolioAllocationResultV2 | None,
    ) -> int | None:
        if isinstance(result, PortfolioAllocationResultV2):
            return result.target_weights.cash_weight_bp
        if result is None or result.capital_amount <= Decimal(0):
            return None
        try:
            return int((result.residual_cash * Decimal(10000)) // result.capital_amount)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _bp(value: object, field_name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10000:
            raise ValueError(f"{field_name} must be an integer bp value between 0 and 10000")
        return value

    @staticmethod
    def _date_text(value: date | str, field_name: str) -> str:
        if isinstance(value, date):
            return value.isoformat()
        try:
            return date.fromisoformat(value).isoformat()
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field_name} must be an ISO date") from error

    @staticmethod
    def _strings(values: Sequence[str], field_name: str) -> tuple[str, ...]:
        if not all(isinstance(value, str) for value in values):
            raise ValueError(f"{field_name} must contain strings")
        return tuple(values)

    @staticmethod
    def _string_or_none(value: object) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _string_or_empty(value: object) -> str:
        return value if isinstance(value, str) else ""

    @staticmethod
    def _bool_or_none(value: object) -> bool | None:
        return value if isinstance(value, bool) else None

    @staticmethod
    def _split_reasons(value: object) -> tuple[str, ...]:
        return tuple(part.strip() for part in str(value).replace("；", ";").split(";") if part.strip())

    @staticmethod
    def _recommendation_risk_reasons(
        *,
        evidence_quality: str | None,
        execution_feasible: bool | None,
        risk_budget_available: bool | None,
        portfolio_sizing_requested: bool,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if evidence_quality != "OBSERVED":
            reasons.append(
                "data_quality_missing"
                if evidence_quality is None
                else f"data_quality:{evidence_quality.lower()}"
            )
        if execution_feasible is not True:
            reasons.append("execution_feasibility_not_confirmed")
        if portfolio_sizing_requested and risk_budget_available is not True:
            reasons.append("risk_budget_not_confirmed")
        return tuple(dict.fromkeys(reasons))

    @staticmethod
    def _source_numeric_text(value: object) -> str | None:
        """保留保存數值的精確文字，不轉換精度或補入推導值。"""

        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return str(value) if parsed.is_finite() else None

    @staticmethod
    def _source_date_text(value: object) -> str | None:
        """只沿用保存的 ISO 日期，不以 Advice 顯示日代填。"""

        if type(value) is date:
            return value.isoformat()
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _feasibility_text(value: object) -> str:
        if value is True:
            return "FEASIBLE"
        if value is False:
            return "NOT_FEASIBLE"
        return "UNKNOWN"

    @staticmethod
    def _classification(
        mode: AdviceMode,
        *,
        strategy_status: str | None,
    ) -> AdviceClassification:
        del mode, strategy_status
        return AdviceClassification.FORMAL_ADVICE
