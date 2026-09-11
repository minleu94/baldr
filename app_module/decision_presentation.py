"""V4.2 每日投資決策的共用唯讀呈現契約。

本模組只把既有 Advice、觀察清單保存結果、Condition Monitor 與持倉 DTO
適配成同一份 presentation read model。它不重新評分、不估計機率、不推導
目標權重，也不產生交易指令；缺少治理來源時維持 ``None``／``unavailable``。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from app_module.advice_dtos import (
    AdviceAction,
    PortfolioAdviceDTO,
    RecommendationAdviceDTO,
)


DECISION_PRESENTATION_SCHEMA_VERSION = "decision-presentation.v1"
_KNOWN_EVIDENCE_STATUSES = {
    "observed",
    "estimated",
    "degraded",
    "missing",
    "unavailable",
    "research",
}
_KNOWN_PROBABILITY_STATUSES = {"available", "unavailable", "research"}


def _strings(value: Any) -> tuple[str, ...]:
    """將來源中的文字集合正規化並去重，保留來源順序。"""

    if value is None:
        return ()
    if isinstance(value, str):
        values = value.replace("\r", "\n").replace("；", "\n").replace(";", "\n").splitlines()
    elif isinstance(value, (tuple, list, set, frozenset)):
        values = [str(item) for item in value]
    else:
        values = [str(value)]
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return tuple(result)


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _integer(value: Any, *, minimum: int | None = None, maximum: int | None = None) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not decimal_value.is_finite() or decimal_value != decimal_value.to_integral_value():
        return None
    result = int(decimal_value)
    if minimum is not None and result < minimum:
        return None
    if maximum is not None and result > maximum:
        return None
    return result


def _bp(value: Any, *, minimum: int = -10000, maximum: int = 10000) -> int | None:
    return _integer(value, minimum=minimum, maximum=maximum)


def _evidence_status(*values: Any) -> str:
    for value in values:
        token = str(value or "").strip().lower()
        if not token:
            continue
        if token in _KNOWN_EVIDENCE_STATUSES:
            return token
        if token in {"formal", "validated", "complete"}:
            return "observed"
        if token in {"candidate", "shadow", "research_only"}:
            return "research"
        if "degrad" in token or "partial" in token:
            return "degraded"
        if "missing" in token or "unavail" in token or "unknown" in token:
            return "unavailable"
    return "unavailable"


def _date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _source_trace(*values: Any) -> tuple[str, ...]:
    items: list[str] = []
    for value in values:
        items.extend(_strings(value))
    return _strings(items)


def _action_text(value: Any) -> str:
    if isinstance(value, AdviceAction):
        return value.value
    return str(value or "UNAVAILABLE").strip().upper() or "UNAVAILABLE"


@dataclass(frozen=True)
class DecisionPresentationDTO:
    """三個決策畫面共用的個股／持倉呈現 read model。

    ``ranking_score`` 與 ``cost_basis`` 使用 Decimal；``*_weight_bp`` 與
    ``calibrated_probability_bp`` 使用整數基點。這個 DTO 沒有任何計算責任，
    只保留上游已經提供、且能被追溯的值。
    """

    stock_code: str
    stock_name: str = ""
    ranking_score: Decimal | None = None
    ranking_percentile_bp: int | None = None
    ranking_method: str = ""
    calibrated_probability_bp: int | None = None
    calibrated_probability_status: str = "research"
    action_suitability: str = "UNAVAILABLE"
    evidence_status: str = "unavailable"
    confidence_tier: str = ""
    sample_size: int | None = None
    horizon: str = ""
    cost_basis: Decimal | None = None
    reasons: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    target_weight_bp: int | None = None
    current_weight_bp: int | None = None
    weight_gap_bp: int | None = None
    decision_date: str = ""
    data_as_of_date: str = ""
    source_trace: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    schema_version: str = DECISION_PRESENTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        stock_code = str(self.stock_code).strip()
        if not stock_code:
            raise ValueError("stock_code is required")
        object.__setattr__(self, "stock_code", stock_code)
        object.__setattr__(self, "stock_name", str(self.stock_name or "").strip())
        object.__setattr__(self, "ranking_score", _decimal(self.ranking_score))
        object.__setattr__(self, "cost_basis", _decimal(self.cost_basis))
        object.__setattr__(self, "action_suitability", _action_text(self.action_suitability))
        object.__setattr__(self, "evidence_status", _evidence_status(self.evidence_status))
        probability_status = str(self.calibrated_probability_status or "research").strip().lower()
        if probability_status not in _KNOWN_PROBABILITY_STATUSES:
            probability_status = "research"
        probability = self.calibrated_probability_bp
        if probability is not None:
            if isinstance(probability, bool) or not isinstance(probability, int):
                raise ValueError("calibrated_probability_bp must be an integer bp value")
            if not 0 <= probability <= 10000:
                raise ValueError("calibrated_probability_bp must be between 0 and 10000 bp")
            probability_status = "available"
        elif probability_status == "available":
            # 沒有合格校準結果時不可讓畫面看起來像有機率。
            probability_status = "unavailable"
        object.__setattr__(self, "calibrated_probability_status", probability_status)
        if self.sample_size is not None:
            if isinstance(self.sample_size, bool) or not isinstance(self.sample_size, int) or self.sample_size < 0:
                raise ValueError("sample_size must be a non-negative integer")
        if self.ranking_percentile_bp is not None:
            if isinstance(self.ranking_percentile_bp, bool) or not isinstance(self.ranking_percentile_bp, int):
                raise ValueError("ranking_percentile_bp must be an integer bp value")
            if not 0 <= self.ranking_percentile_bp <= 10000:
                raise ValueError("ranking_percentile_bp must be between 0 and 10000 bp")
        for field_name in ("target_weight_bp", "current_weight_bp", "weight_gap_bp"):
            value = getattr(self, field_name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(f"{field_name} must be an integer bp value")
                lower = -10000 if field_name == "weight_gap_bp" else 0
                if not lower <= value <= 10000:
                    raise ValueError(f"{field_name} is out of bp range")
        object.__setattr__(self, "reasons", _strings(self.reasons))
        object.__setattr__(self, "risks", _strings(self.risks))
        object.__setattr__(self, "invalidation_conditions", _strings(self.invalidation_conditions))
        object.__setattr__(self, "source_trace", _strings(self.source_trace))
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(self, "decision_date", _date_text(self.decision_date))
        object.__setattr__(self, "data_as_of_date", _date_text(self.data_as_of_date))
        object.__setattr__(self, "horizon", str(self.horizon or "").strip())
        object.__setattr__(self, "confidence_tier", str(self.confidence_tier or "").strip())
        object.__setattr__(self, "ranking_method", str(self.ranking_method or "").strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "ranking_score": None if self.ranking_score is None else str(self.ranking_score),
            "ranking_percentile_bp": self.ranking_percentile_bp,
            "ranking_method": self.ranking_method,
            "calibrated_probability_bp": self.calibrated_probability_bp,
            "calibrated_probability_status": self.calibrated_probability_status,
            "action_suitability": self.action_suitability,
            "evidence_status": self.evidence_status,
            "confidence_tier": self.confidence_tier,
            "sample_size": self.sample_size,
            "horizon": self.horizon,
            "cost_basis": None if self.cost_basis is None else str(self.cost_basis),
            "reasons": list(self.reasons),
            "risks": list(self.risks),
            "invalidation_conditions": list(self.invalidation_conditions),
            "target_weight_bp": self.target_weight_bp,
            "current_weight_bp": self.current_weight_bp,
            "weight_gap_bp": self.weight_gap_bp,
            "decision_date": self.decision_date,
            "data_as_of_date": self.data_as_of_date,
            "source_trace": list(self.source_trace),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DecisionPresentationDTO":
        if not isinstance(value, Mapping):
            raise ValueError("decision presentation payload must be an object")
        return cls(
            stock_code=value.get("stock_code", ""),
            stock_name=value.get("stock_name", ""),
            ranking_score=_decimal(value.get("ranking_score")),
            ranking_percentile_bp=_integer(value.get("ranking_percentile_bp"), minimum=0, maximum=10000),
            ranking_method=value.get("ranking_method", ""),
            calibrated_probability_bp=_integer(value.get("calibrated_probability_bp"), minimum=0, maximum=10000),
            calibrated_probability_status=value.get("calibrated_probability_status", "research"),
            action_suitability=value.get("action_suitability", "UNAVAILABLE"),
            evidence_status=value.get("evidence_status", "unavailable"),
            confidence_tier=value.get("confidence_tier", ""),
            sample_size=_integer(value.get("sample_size"), minimum=0),
            horizon=value.get("horizon", ""),
            cost_basis=_decimal(value.get("cost_basis")),
            reasons=_strings(value.get("reasons")),
            risks=_strings(value.get("risks")),
            invalidation_conditions=_strings(value.get("invalidation_conditions")),
            target_weight_bp=value.get("target_weight_bp"),
            current_weight_bp=value.get("current_weight_bp"),
            weight_gap_bp=value.get("weight_gap_bp"),
            decision_date=value.get("decision_date", ""),
            data_as_of_date=value.get("data_as_of_date", ""),
            source_trace=_strings(value.get("source_trace")),
            warnings=_strings(value.get("warnings")),
            schema_version=str(value.get("schema_version", DECISION_PRESENTATION_SCHEMA_VERSION)),
        )


class DecisionPresentationService:
    """將既有 application DTO 組成共用呈現契約。"""

    def from_market_focus_card(
        self,
        card: Any,
        *,
        as_of_date: date | str | None = None,
    ) -> DecisionPresentationDTO:
        source = str(getattr(card, "source", "decision_desk") or "decision_desk")
        quality = str(getattr(getattr(card, "quality", "unavailable"), "value", getattr(card, "quality", "unavailable")))
        role = str(getattr(card, "role", "priority") or "priority")
        # Market focus card 不是 Advice；即使是 risk card，也只能標成研究焦點，
        # 避免把 UI 的風險提示誤讀成已通過 policy 的 NO_NEW_POSITION。
        action = AdviceAction.RESEARCH.value
        reason = _strings(getattr(card, "reason", ""))
        warning = "市場總覽只提供研究焦點；個股 Advice 需從研究報告確認。"
        if role != "priority":
            warning = "市場總覽的風險焦點只供研究與人工覆盤，不等於正式 NO_NEW_POSITION。"
        return DecisionPresentationDTO(
            stock_code=str(getattr(card, "stock_code", "")),
            stock_name=str(getattr(card, "stock_name", "")),
            action_suitability=action,
            evidence_status=_evidence_status(quality),
            horizon="研究中／未定",
            reasons=reason,
            risks=reason if role != "priority" else (),
            source_trace=(f"decision_desk:{source}",),
            data_as_of_date=_date_text(as_of_date),
            warnings=(warning,),
        )

    def from_watchlist_analysis(self, analysis: Any) -> DecisionPresentationDTO:
        status = str(getattr(analysis, "status", "unavailable") or "unavailable").lower()
        saved = status == "saved"
        evidence = "degraded" if saved else ("missing" if status == "not_in_result" else "unavailable")
        warnings = _strings(getattr(analysis, "message", ""))
        if status == "not_in_result":
            warnings = (*warnings, "未入選不等於看空；目前沒有此股票的保存 Advice。")
        if saved:
            warnings = (*warnings, "保存結果只作研究參考，非即時重新評分。")
        return DecisionPresentationDTO(
            stock_code=str(getattr(analysis, "stock_code", "")),
            ranking_score=_decimal(getattr(analysis, "score", None)),
            ranking_percentile_bp=_integer(
                getattr(analysis, "score_percentile_bp", None), minimum=0, maximum=10000
            ),
            ranking_method=str(getattr(analysis, "ranking_method", "") or ""),
            calibrated_probability_status="research",
            action_suitability=AdviceAction.RESEARCH.value if saved or status == "not_in_result" else "UNAVAILABLE",
            evidence_status=evidence,
            sample_size=_integer(getattr(analysis, "sample_size", None), minimum=0),
            horizon="研究中／未定",
            reasons=_strings(getattr(analysis, "reasons", "")),
            decision_date=getattr(analysis, "decision_date", "") or getattr(analysis, "analysis_date", ""),
            data_as_of_date=getattr(analysis, "data_date", "") or "",
            source_trace=_source_trace(
                getattr(analysis, "result_id", ""),
                getattr(analysis, "source_id", ""),
            ),
            warnings=warnings,
        )

    def from_recommendation_advice(
        self,
        advice: RecommendationAdviceDTO,
        *,
        ranking_score: Any = None,
        ranking_percentile_bp: int | None = None,
        ranking_method: str = "",
        sample_size: int | None = None,
        cost_basis: Any = None,
        source_trace: tuple[str, ...] = (),
        calibrated_probability_bp: int | None = None,
        calibrated_probability_status: str = "research",
    ) -> DecisionPresentationDTO:
        reasons = _strings((*advice.why_reasons, advice.entry_thesis))
        warnings = _strings((*advice.warnings, *advice.refusal_reasons))
        return DecisionPresentationDTO(
            stock_code=advice.stock_code,
            ranking_score=_decimal(ranking_score),
            ranking_percentile_bp=ranking_percentile_bp,
            ranking_method=ranking_method,
            calibrated_probability_bp=calibrated_probability_bp,
            calibrated_probability_status=calibrated_probability_status,
            action_suitability=advice.advice_action.value,
            evidence_status=_evidence_status(advice.data_quality, advice.evidence_tier),
            confidence_tier=advice.confidence_tier,
            sample_size=_integer(sample_size, minimum=0),
            horizon=advice.holding_horizon,
            cost_basis=_decimal(cost_basis),
            reasons=reasons,
            risks=_strings(advice.risk_reasons),
            invalidation_conditions=_strings(advice.invalidation_conditions),
            decision_date=advice.decision_date,
            data_as_of_date=advice.data_as_of_date,
            source_trace=_source_trace(advice.source_trace, source_trace),
            warnings=warnings,
        )

    def from_portfolio_advice(
        self,
        advice: PortfolioAdviceDTO,
        *,
        cost_basis: Any = None,
        ranking_score: Any = None,
        ranking_percentile_bp: int | None = None,
        ranking_method: str = "",
        sample_size: int | None = None,
    ) -> DecisionPresentationDTO:
        return DecisionPresentationDTO(
            stock_code=advice.stock_code,
            ranking_score=_decimal(ranking_score),
            ranking_percentile_bp=ranking_percentile_bp,
            ranking_method=ranking_method,
            action_suitability=advice.advice_action.value,
            evidence_status=_evidence_status(advice.data_quality, advice.evidence_tier),
            confidence_tier=advice.confidence_tier,
            sample_size=_integer(sample_size, minimum=0),
            horizon=advice.holding_horizon,
            cost_basis=_decimal(cost_basis),
            reasons=_strings(advice.reasons),
            risks=_strings(advice.risk_reasons),
            invalidation_conditions=_strings(advice.invalidation_conditions),
            target_weight_bp=advice.target_weight_bp,
            current_weight_bp=advice.current_weight_bp,
            weight_gap_bp=advice.weight_gap_bp,
            decision_date=advice.review_date,
            data_as_of_date="",
            source_trace=advice.source_trace,
            warnings=_strings((*advice.warnings, *advice.diagnostics)),
        )

    def from_position(
        self,
        position: Any,
        *,
        condition_result: Any | None = None,
        feedback_report: Any | None = None,
    ) -> DecisionPresentationDTO:
        source_summary = dict(getattr(position, "source_summary", {}) or {})
        condition_status = str(getattr(condition_result, "status", "") or "").lower()
        action = {
            "valid": AdviceAction.HOLD.value,
            "warning": AdviceAction.REDUCE_CANDIDATE.value,
            "invalid": AdviceAction.EXIT_CANDIDATE.value,
        }.get(condition_status, "UNAVAILABLE")
        evidence = {
            "valid": "observed",
            "warning": "degraded",
            "invalid": "degraded",
        }.get(condition_status, "unavailable")
        health_reasons = _strings(getattr(position, "health_reasons", ()))
        exit_reasons = _strings(getattr(position, "exit_reasons", ()))
        condition_reasons = _strings(getattr(condition_result, "reasons", ()))
        feedback_tokens = _strings(getattr(feedback_report, "summary_tokens", ()))
        explicit_invalidation = _strings(
            source_summary.get("invalidation_conditions")
            or source_summary.get("exit_conditions")
            or source_summary.get("thesis_invalidation")
        )
        invalidation = explicit_invalidation or exit_reasons
        if not invalidation and condition_status in {"warning", "invalid"}:
            # Condition Monitor 已提供的觸發理由可作為唯讀失效線索；不另造規則。
            invalidation = condition_reasons
        warnings: list[str] = ["持倉動作適合度是唯讀候選分類，不是交易指令。"]
        target_weight = _bp(source_summary.get("target_weight_bp"), minimum=0)
        current_weight = _bp(source_summary.get("current_weight_bp"), minimum=0)
        if current_weight is None:
            current_weight = _bp(getattr(position, "exposure_bp", None), minimum=0)
        weight_gap = _bp(source_summary.get("weight_gap_bp"))
        if target_weight is None or current_weight is None or weight_gap is None:
            warnings.append("未提供既有 Portfolio Advice 的完整權重欄位；不由畫面推導權重差距。")
        return DecisionPresentationDTO(
            stock_code=str(getattr(position, "stock_code", "")),
            stock_name=str(getattr(position, "stock_name", "")),
            action_suitability=action,
            evidence_status=evidence,
            horizon=str(source_summary.get("holding_horizon") or ""),
            cost_basis=_decimal(getattr(position, "average_cost", None)),
            reasons=_strings((*condition_reasons, *feedback_tokens, *health_reasons)),
            risks=_strings(
                (
                    *health_reasons,
                    *exit_reasons,
                    *(condition_reasons if condition_status in {"warning", "invalid"} else ()),
                )
            ),
            invalidation_conditions=invalidation,
            target_weight_bp=target_weight,
            current_weight_bp=current_weight,
            weight_gap_bp=weight_gap,
            data_as_of_date=(
                str(source_summary.get("current_price_date") or "")
                or str(getattr(position, "last_trade_date", "") or "")
            ),
            source_trace=_source_trace(
                getattr(position, "source_type", ""),
                getattr(position, "source_id", ""),
                getattr(position, "source_snapshot_hash", ""),
            ),
            warnings=tuple(warnings),
        )

    def from_report_parts(self, advice: Any, position: Any | None = None) -> DecisionPresentationDTO | None:
        portfolio_advice = getattr(advice, "portfolio", None)
        recommendation = getattr(advice, "recommendation", None)
        saved_analysis = getattr(advice, "saved_analysis", None)
        cost_basis = getattr(position, "average_cost", None) if position is not None else None
        ranking_score = getattr(saved_analysis, "score", None) if saved_analysis is not None else None
        ranking_percentile_bp = (
            getattr(saved_analysis, "score_percentile_bp", None) if saved_analysis is not None else None
        )
        ranking_method = getattr(saved_analysis, "ranking_method", "") if saved_analysis is not None else ""
        sample_size = getattr(saved_analysis, "sample_size", None) if saved_analysis is not None else None
        if portfolio_advice is not None:
            presentation = self.from_portfolio_advice(
                portfolio_advice,
                cost_basis=cost_basis,
                ranking_score=ranking_score,
                ranking_percentile_bp=ranking_percentile_bp,
                ranking_method=ranking_method,
                sample_size=sample_size,
            )
            if recommendation is not None:
                presentation = replace(
                    presentation,
                    ranking_score=_decimal(ranking_score),
                    reasons=_strings((*presentation.reasons, *recommendation.why_reasons)),
                    risks=_strings((*presentation.risks, *recommendation.risk_reasons)),
                    invalidation_conditions=_strings(
                        (*presentation.invalidation_conditions, *recommendation.invalidation_conditions)
                    ),
                )
            return presentation
        if recommendation is not None:
            return self.from_recommendation_advice(
                recommendation,
                ranking_score=ranking_score,
                ranking_percentile_bp=ranking_percentile_bp,
                ranking_method=ranking_method,
                sample_size=sample_size,
                cost_basis=cost_basis,
            )
        if saved_analysis is not None:
            return self.from_watchlist_analysis(saved_analysis)
        if position is not None and bool(getattr(position, "is_holding", False)):
            return self.from_position(position)
        return None


def _quality_label(value: str) -> str:
    return {
        "observed": "已觀測",
        "estimated": "估算",
        "degraded": "降級",
        "missing": "缺漏",
        "research": "研究中",
        "unavailable": "不可用",
    }.get(str(value).lower(), str(value) or "未知")


def _action_label(value: str) -> str:
    return {
        "ADD_CANDIDATE": "買進候選",
        "HOLD": "持有",
        "REDUCE_CANDIDATE": "減碼候選",
        "EXIT_CANDIDATE": "退出候選",
        "NO_NEW_POSITION": "不新增部位",
        "RESEARCH": "研究",
        "AVOID": "避開",
        "UNAVAILABLE": "不可用",
    }.get(str(value).upper(), str(value) or "不可用")


def decision_action_label(value: str) -> str:
    """回傳共用契約的使用者可見動作名稱；不改變動作值。"""

    return _action_label(value)


def _bp_text(value: int | None) -> str:
    return "未知" if value is None else f"{value:,} bp"


def _percentile_text(value: int | None) -> str:
    return "未知" if value is None else f"{value // 100}.{value % 100:02d}%"


def _probability_text(presentation: DecisionPresentationDTO) -> str:
    if presentation.calibrated_probability_bp is None:
        status = "研究中" if presentation.calibrated_probability_status == "research" else "不可用"
        return f"不可用（{status}）"
    value = presentation.calibrated_probability_bp
    return f"{value // 100}.{value % 100:02d}%"


def format_decision_presentation(presentation: DecisionPresentationDTO) -> str:
    """供 Qt 三個畫面共用的短版欄位呈現；不在此處計算任何指標。"""

    score = "未知" if presentation.ranking_score is None else format(presentation.ranking_score, "f")
    cost = "未知" if presentation.cost_basis is None else f"TWD {presentation.cost_basis:,.2f}"
    sample = "未知" if presentation.sample_size is None else f"{presentation.sample_size:,}"
    ranking_context = f"｜排名百分位：{_percentile_text(presentation.ranking_percentile_bp)}"
    if presentation.ranking_method:
        ranking_context += f"｜排名方法：{presentation.ranking_method}"
    lines = [
        f"動作適合度：{_action_label(presentation.action_suitability)}",
        f"排名分數：{score}{ranking_context}｜校準機率：{_probability_text(presentation)}",
        f"證據：{_quality_label(presentation.evidence_status)}｜信心：{presentation.confidence_tier or '未提供'}｜樣本數：{sample}",
        f"適用期間：{presentation.horizon or '未提供'}｜成本基準：{cost}",
        f"目標／目前／差距：{_bp_text(presentation.target_weight_bp)}／{_bp_text(presentation.current_weight_bp)}／{_bp_text(presentation.weight_gap_bp)}",
        "理由：" + ("；".join(presentation.reasons) if presentation.reasons else "未提供"),
        "風險：" + ("；".join(presentation.risks) if presentation.risks else "未提供"),
        "失效條件：" + (
            "；".join(presentation.invalidation_conditions)
            if presentation.invalidation_conditions
            else "未提供"
        ),
    ]
    if presentation.decision_date or presentation.data_as_of_date:
        lines.append(
            f"決策日：{presentation.decision_date or '未知'}｜資料日：{presentation.data_as_of_date or '未知'}"
        )
    if presentation.warnings:
        lines.append("限制／警告：" + "；".join(presentation.warnings))
    if presentation.source_trace:
        lines.append("來源追溯：" + "；".join(presentation.source_trace))
    return "\n".join(lines)
